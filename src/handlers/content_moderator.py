import logging
import openai
import os
import random

class ContentModerator:
    def __init__(self, app):
        self.app = app
        self.logger = logging.getLogger(__name__)
        
        # Get API key directly from environment variables
        openai_api_key = os.environ.get("OPENAI_API_KEY", "")
        if not openai_api_key:
            self.logger.error("OpenAI API key not found in environment variables")
        
        self.openai_client = openai.OpenAI(api_key=openai_api_key)
        
        self.logger.info("Content moderator initialized")
    
    def check_message(self, message):
        """Check if a message contains unprofessional or offensive content"""
        # Skip messages that are too short or from bots
        text = message.get('text', '').strip()
        if len(text) < 10 or message.get('subtype') == 'bot_message':
            return
            
        user_id = message.get('user')
        if not user_id:
            return
            
        self.logger.debug(f"Checking message from user {user_id} for unprofessional content")
        
        try:
            # Call OpenAI to analyze the message and provide a book recommendation
            response = self.openai_client.chat.completions.create(
                model="gpt-4o",  # Use an appropriate model
                messages=[
                    {"role": "system", "content": """
                    You are a professional communication coach. Your task is to identify if a message contains 
                    unprofessional, offensive, or non-inclusive language. If it does, explain why it might be 
                    problematic and suggest a more professional alternative.
                    
                    Only respond with problematic content. If the message is professional and appropriate, 
                    respond with "APPROPRIATE".
                    
                    If the message is problematic, format your response as:
                    INAPPROPRIATE
                    [explanation of why the message might be problematic]
                    [suggestion for improvement]
                    BOOK RECOMMENDATION:
                    [title] by [author]
                    [brief description of how this book can help with this specific communication issue]
                    
                    The book recommendation should be a real, non-fiction book focused on communication, 
                    leadership, or professional development that specifically addresses the issue in the message.
                    """},
                    {"role": "user", "content": text}
                ],
                temperature=0.3,
                max_tokens=500
            )
            
            analysis = response.choices[0].message.content.strip()
            self.logger.debug(f"OpenAI analysis: {analysis[:100]}...")
            
            # If the message is inappropriate, send feedback to the user
            if analysis.startswith("INAPPROPRIATE"):
                self.logger.info(f"Detected inappropriate content in message from user {user_id}")
                self._send_feedback(user_id, text, analysis[13:].strip())  # Remove "INAPPROPRIATE" prefix
        
        except Exception as e:
            self.logger.error(f"Error analyzing message: {e}")
    
    def _send_feedback(self, user_id, original_message, analysis):
        """Send private feedback to the user about their message"""
        # Split the analysis to separate the explanation/suggestion from the book recommendation
        parts = analysis.split("BOOK RECOMMENDATION:")
        
        if len(parts) == 2:
            feedback = parts[0].strip()
            book_recommendation = parts[1].strip()
        else:
            feedback = analysis
            book_recommendation = "Effective Communication by Various Authors - A general resource for improving workplace communication."
        
        message = (
            ":speech_balloon: *Communication Coach*\n\n"
            "I noticed that a recent message you sent might be perceived as unprofessional or potentially offensive:\n\n"
            f">{original_message}\n\n"
            f"{feedback}\n\n"
            "*Resource for Effective Communication:*\n"
            f"📚 *{book_recommendation}*\n\n"
            "_This is an automated message to help foster a positive and inclusive communication environment._"
        )
        
        try:
            self.logger.info(f"Sending communication feedback to user {user_id}")
            self.app.client.chat_postMessage(
                channel=user_id,
                text=message,
                unfurl_links=False
            )
            self.logger.debug("Feedback sent successfully")
        except Exception as e:
            self.logger.error(f"Error sending feedback: {e}") 