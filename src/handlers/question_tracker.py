from datetime import datetime, timedelta
from config.settings import Settings
import re
import logging
import threading
import time

class QuestionTracker:
    def __init__(self, app):
        self.app = app
        self.questions = {}  # Format: {ts: {channel, user, text, timestamp}}
        self.logger = logging.getLogger(__name__)
        # Start the periodic check
        self._start_periodic_check()
    
    def _start_periodic_check(self):
        """Start a background thread to check questions periodically"""
        self.logger.info("Starting periodic question check thread")
        self.check_thread = threading.Thread(target=self._periodic_check_worker, daemon=True)
        self.check_thread.start()
    
    def _periodic_check_worker(self):
        """Worker function that runs in background thread to check questions every minute"""
        while True:
            try:
                self.logger.debug("Running scheduled check for unanswered questions")
                self.check_unanswered_questions()
            except Exception as e:
                self.logger.error(f"Error in periodic question check: {e}")
            
            # Sleep for 60 seconds (1 minute)
            time.sleep(60)
    
    def track_question(self, message):
        """Track a new question"""
        # Basic question detection
        text = message.get('text', '').strip()
        self.logger.info(f"Analyzing potential question: {text[:100]}{'...' if len(text) > 100 else ''}")
        
        # Check if message has required fields
        if not all(key in message for key in ['text', 'user', 'channel', 'ts']):
            missing = [key for key in ['text', 'user', 'channel', 'ts'] if key not in message]
            self.logger.warning(f"Message missing required fields: {missing}. Skipping.")
            return
        
        if not self._is_question(text):
            self.logger.info("Message not detected as a question - criteria not met")
            return
            
        self.logger.info(f"✓ Question detected from user {message['user']} in channel {message['channel']}")
        self.questions[message['ts']] = {
            'channel': message['channel'],
            'user': message['user'],
            'text': text,
            'timestamp': datetime.now(),
            'reminded': False
        }
        self.logger.info(f"Question tracked. Total questions being tracked: {len(self.questions)}")
    
    def _is_question(self, text):
        """Determine if a message is likely a question"""
        # Check for question marks
        if '?' in text:
            self.logger.info("Question detected: Message contains a question mark")
            return True
            
        # Check for common question starters
        question_starters = [
            'what', 'why', 'how', 'when', 'where', 
            'who', 'which', 'can', 'could', 'would'
        ]
        
        lower_text = text.lower()
        for word in question_starters:
            if lower_text.startswith(word):
                self.logger.info(f"Question detected: Message starts with question word '{word}'")
                return True
        
        self.logger.debug("No question patterns found in message")
        return False
    
    def check_unanswered_questions(self):
        """Check for questions that need reminders"""
        current_time = datetime.now()
        self.logger.debug(f"Checking unanswered questions. Currently tracking {len(self.questions)} questions")
        
        for ts, question in list(self.questions.items()):
            self.logger.debug(f"Checking question from {question['user']}, asked at {question['timestamp']}")
            
            # Skip if we've already reminded or if it's too early
            if question['reminded']:
                self.logger.debug("Skipping - already reminded")
                continue
                
            time_diff = (current_time - question['timestamp']).total_seconds()
            reminder_threshold = Settings.QUESTION_REMINDER_MINUTES * 60
            
            if time_diff < reminder_threshold:
                self.logger.debug(f"Skipping - too early. {int((reminder_threshold - time_diff)/60)} minutes remaining")
                continue
            
            # Check if question has replies
            try:
                self.logger.info(f"Checking replies for question in channel {question['channel']}, ts {ts}")
                replies = self.app.client.conversations_replies(
                    channel=question['channel'],
                    ts=ts
                )
                if len(replies['messages']) > 1:  # Has replies
                    self.logger.info(f"Question has {len(replies['messages'])-1} replies, removing from tracking")
                    del self.questions[ts]
                    continue
                    
                self.logger.info(f"Sending reminder for unanswered question to user {question['user']}")
                self._send_reminder(question)
                question['reminded'] = True
                
            except Exception as e:
                self.logger.error(f"Error checking replies: {e}")
    
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
            self.logger.info(f"Sending reminder DM to user {question['user']}")
            self.app.client.chat_postMessage(
                channel=question['user'],
                text=message,
                unfurl_links=False
            )
            self.logger.debug("Reminder sent successfully")
        except Exception as e:
            self.logger.error(f"Error sending reminder: {e}")
    
    def fetch_recent_messages(self, minutes=5):
        """Fetch recent messages from channels to analyze for questions
        
        Args:
            minutes: How far back to look for messages (default: 5 minutes)
        """
        self.logger.info(f"Fetching messages from the last {minutes} minutes")
        
        # Check for answers to existing questions
        self._check_for_answers()
        
        # Get list of channels the bot is in
        try:
            # Only get channels where the bot is a member
            result = self.app.client.conversations_list(
                types="public_channel,private_channel",
                exclude_archived=True
            )
            
            if not result["ok"]:
                self.logger.error(f"Error listing channels: {result.get('error', 'unknown error')}")
                return
            
            # Filter to only include channels where the bot is a member
            channels = [c for c in result["channels"] if c.get("is_member", False)]
            self.logger.info(f"Bot is a member of {len(channels)} channels")
            
            if len(channels) == 0:
                self.logger.warning("Bot is not a member of any channels. Add the bot to channels to monitor questions.")
                return
            
            # Get current time and calculate the oldest timestamp to fetch
            now = datetime.now()
            oldest_ts = (now - timedelta(minutes=minutes)).timestamp()
            
            messages_analyzed = 0
            questions_found = 0
            
            for channel in channels:
                channel_id = channel["id"]
                channel_name = channel.get("name", "unknown")
                
                self.logger.info(f"Checking channel #{channel_name} ({channel_id})")
                
                try:
                    # Get recent messages in the channel
                    result = self.app.client.conversations_history(
                        channel=channel_id,
                        oldest=str(oldest_ts)
                    )
                    
                    if not result["ok"]:
                        self.logger.error(f"Error fetching messages from #{channel_name}: {result.get('error', 'unknown error')}")
                        continue
                    
                    channel_messages = result.get("messages", [])
                    self.logger.info(f"Found {len(channel_messages)} recent messages in #{channel_name}")
                    
                    # Process each message
                    for message in channel_messages:
                        # Skip bot messages and thread replies
                        if message.get("subtype") == "bot_message" or "thread_ts" in message:
                            continue
                        
                        # Add channel ID to the message object
                        message["channel"] = channel_id
                        
                        # Analyze the message
                        messages_analyzed += 1
                        message_text = message.get("text", "").strip()
                        
                        # Check if it's a question
                        if self._is_question(message_text):
                            questions_found += 1
                            # Print the full question
                            self.logger.info(f"QUESTION DETECTED in #{channel_name}:")
                            self.logger.info(f"FULL TEXT: {message_text}")
                            
                            # Add to tracking if not already tracked
                            if message["ts"] not in self.questions:
                                self.questions[message["ts"]] = {
                                    'channel': channel_id,
                                    'user': message.get('user'),
                                    'text': message_text,
                                    'timestamp': datetime.fromtimestamp(float(message["ts"])),
                                    'reminded': False
                                }
                                self.logger.info(f"Added question to tracking system")
                
                except Exception as e:
                    self.logger.error(f"Error fetching messages from channel {channel_id}: {e}")
            
            self.logger.info(f"Message fetch complete. Analyzed {messages_analyzed} messages, found {questions_found} questions")
        
        except Exception as e:
            self.logger.error(f"Error listing channels: {e}")

    def _check_for_answers(self):
        """Check if any tracked questions have been answered and remove them from tracking"""
        self.logger.info(f"Checking for answers to {len(self.questions)} tracked questions")
        
        for ts, question in list(self.questions.items()):
            try:
                self.logger.debug(f"Checking if question in channel {question['channel']}, ts {ts} has been answered")
                replies = self.app.client.conversations_replies(
                    channel=question['channel'],
                    ts=ts
                )
                if len(replies['messages']) > 1:  # Has replies
                    self.logger.info(f"Question has {len(replies['messages'])-1} replies, removing from tracking")
                    del self.questions[ts]
            except Exception as e:
                self.logger.error(f"Error checking replies for question {ts}: {e}") 