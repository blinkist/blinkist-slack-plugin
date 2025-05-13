from datetime import datetime, timedelta
import re

class QuestionTracker:
    def __init__(self, app):
        self.app = app
        self.questions = {}  # Format: {ts: {channel, user, text, timestamp}}
    
    def track_question(self, message):
        """Track a new question"""
        # Basic question detection
        text = message.get('text', '').strip()
        if not self._is_question(text):
            return
            
        self.questions[message['ts']] = {
            'channel': message['channel'],
            'user': message['user'],
            'text': text,
            'timestamp': datetime.now(),
            'reminded': False
        }
    
    def _is_question(self, text):
        """Determine if a message is likely a question"""
        # Check for question marks
        if text.endswith('?'):
            return True
            
        # Check for common question starters
        question_starters = [
            'what', 'why', 'how', 'when', 'where', 
            'who', 'which', 'can', 'could', 'would'
        ]
        return any(text.lower().startswith(word) for word in question_starters)
    
    def check_unanswered_questions(self):
        """Check for questions that need reminders"""
        current_time = datetime.now()
        
        for ts, question in list(self.questions.items()):
            # Skip if we've already reminded or if it's too early
            if (question['reminded'] or 
                (current_time - question['timestamp']).total_seconds() < 
                os.environ.get('QUESTION_REMINDER_MINUTES') * 60):  # Changed from hours to minutes
                continue
            
            # Check if question has replies
            try:
                replies = self.app.client.conversations_replies(
                    channel=question['channel'],
                    ts=ts
                )
                if len(replies['messages']) > 1:  # Has replies
                    del self.questions[ts]
                    continue
                    
                self._send_reminder(question)
                question['reminded'] = True
                
            except Exception as e:
                print(f"Error checking replies: {e}")
    
    def _send_reminder(self, question):
        """Send a reminder DM about an unanswered question"""
        suggestions = [
            "• Add any relevant error messages or logs",
            "• Provide more context about what you're trying to achieve",
            "• Mention specific technologies or tools you're using",
            "• Tag team members who might have expertise in this area"
        ]
        
        message = (
            f"Hi! I noticed your question hasn't received any responses yet:\n\n"
            f">{question['text']}\n\n"
            "To help get answers, you might want to:\n"
            f"{chr(10).join(suggestions)}"
        )
        
        try:
            self.app.client.chat_postMessage(
                channel=question['user'],
                text=message,
                unfurl_links=False
            )
        except Exception as e:
            print(f"Error sending reminder: {e}") 