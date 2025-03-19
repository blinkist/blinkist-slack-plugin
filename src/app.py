import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from config.settings import Settings
from handlers.quiet_channel import QuietChannelHandler
from handlers.question_tracker import QuestionTracker
from handlers.weekly_summary import WeeklySummary
from handlers.command_handler import CommandHandler
from handlers.content_moderator import ContentModerator
import schedule
import time
import threading
import logging

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Initialize the Slack app
logger.info("Initializing Slack app")
app = App(token=Settings.SLACK_BOT_TOKEN)

# Initialize handlers
logger.info("Initializing handlers")
quiet_channel = QuietChannelHandler(app)
question_tracker = QuestionTracker(app)
weekly_summary = WeeklySummary(app)
command_handler = CommandHandler(app)
content_moderator = ContentModerator(app)

# Register message events
@app.message("")
def handle_message(message, say, logger):
    # Get full message text for better logging
    text = message.get('text', '')
    logger.debug(f"Received message: {text[:100]}{'...' if len(text) > 100 else ''}")
    logger.debug(f"Message details: channel={message.get('channel')}, user={message.get('user')}, ts={message.get('ts')}")
    
    # Reset quiet channel timer
    quiet_channel.reset_timer(message['channel'])
    
    # Always pass to question tracker for analysis
    logger.info(f"Passing message to question tracker for analysis")
    question_tracker.track_question(message)
    
    # Update weekly summary data
    weekly_summary.process_message(message)
    
    # Check message for unprofessional content
    content_moderator.check_message(message)

# Register slash commands
@app.command("/tell-joke")
def handle_joke_command(ack, respond):
    ack()
    command_handler.tell_joke(respond)

@app.command("/channel-mood")
def handle_mood_command(ack, command, respond):
    ack()
    command_handler.analyze_channel_mood(command['channel_id'], respond)

def run_scheduler():
    logger.info("Starting scheduler thread")
    
    # We still need to check for unanswered questions periodically
    schedule.every(10).minutes.do(question_tracker.check_unanswered_questions)
    logger.info("Scheduled question checks to run every 10 minutes")
    
    # Check for answers to existing questions
    schedule.every(10).minutes.do(question_tracker._check_for_answers)
    logger.info("Scheduled answer checks to run every 10 minutes")
    
    # Schedule quiet channel checks every hour
    schedule.every(1).hour.do(quiet_channel.check_channels)
    logger.info("Scheduled quiet channel checks to run every hour")
    
    # Schedule weekly summary
    schedule.every().friday.at("16:00").do(weekly_summary.generate_and_post_summary)
    logger.info("Scheduled weekly summary to run every Friday at 16:00")
    
    while True:
        try:
            schedule.run_pending()
            logger.debug("Scheduler tick - ran pending tasks")
        except Exception as e:
            logger.error(f"Error in scheduler: {e}")
        time.sleep(60)

def main():
    logger.info("Starting Slack Assistant application")
    
    # Start the scheduler in a separate thread
    logger.info("Initializing scheduler thread")
    scheduler_thread = threading.Thread(target=run_scheduler)
    scheduler_thread.daemon = True
    scheduler_thread.start()
    logger.info("Scheduler thread started")
    
    # Start the app
    logger.info("Starting Socket Mode handler")
    handler = SocketModeHandler(app, Settings.SLACK_APP_TOKEN)
    handler.start()

if __name__ == "__main__":
    main() 