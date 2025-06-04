import sys
import os
import logging
import schedule
import threading
import time
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from utils.channel_utils import ChannelTracker
from handlers.skill_assessment import SkillAssessmentHandler
from handlers.report_metrics import ReportMetrics
from handlers.daily_pulse import start_daily_pulse_scheduler

# Set up detailed logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Read tokens from environment variables
SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_APP_TOKEN = os.environ["SLACK_APP_TOKEN"]

logger.info("Starting Slack bot initialization...")

# Initialize the Slack app
app = App(token=SLACK_BOT_TOKEN)
logger.info("Slack app initialized successfully")

# Initialize channel tracker
try:
    channel_tracker = ChannelTracker(app)
    channel_tracker.update_installed_channels()
    logger.info("Channel tracker initialized successfully")
except Exception as e:
    logger.error(f"Error initializing channel tracker: {e}")
    raise

# Initialize handlers
try:
    skill_assessment_handler = SkillAssessmentHandler(app)
    logger.info("Skill assessment handler initialized successfully")
    
    report_metrics = ReportMetrics(app, channel_tracker)
    logger.info("Report metrics handler initialized successfully")
except Exception as e:
    logger.error(f"Error initializing handlers: {e}")
    raise

@app.command("/pulse-assess")
def handle_pulse_assess_command(ack, body, client, logger):
    logger.info(f"Received /pulse-assess command from user {body.get('user_id')}")
    try:
        ack()
        skill_assessment_handler.open_channel_select_modal(body, client, logger)
        logger.info("Successfully handled /pulse-assess command")
    except Exception as e:
        logger.error(f"Error handling /pulse-assess command: {e}")
        ack()

@app.view("skill_assess_channel_select")
def handle_skill_assess_view_submission(ack, body, client, logger):
    logger.info("Received skill assessment view submission")
    try:
        ack()
        skill_assessment_handler.handle_channel_select_submission(
            view=body["view"],
            user=body["user"]["id"],
            client=client,
            logger=logger
        )
        logger.info("Successfully handled skill assessment view submission")
    except Exception as e:
        logger.error(f"Error handling skill assessment view submission: {e}")

@app.command("/pulse-report")
def pulse_report_command(ack, body, client, logger):
    logger.info(f"Received /pulse-report command from user {body.get('user_id')}")
    try:
        ack()
        
        days = 30
        if body["text"].strip():
            try:
                days = int(body["text"].strip())
                if days <= 0:
                    client.chat_postMessage(
                        channel=body["user_id"],
                        text="Please provide a positive number of days"
                    )
                    return
            except ValueError:
                client.chat_postMessage(
                    channel=body["user_id"],
                    text="Please provide a valid number of days"
                )
                return
        
        report_metrics.open_channel_select_modal(body, client, logger, days)
        logger.info(f"Successfully handled /pulse-report command with {days} days")
    except Exception as e:
        logger.error(f"Error handling /pulse-report command: {e}")

@app.view("pulse_report_channel_select")
def handle_channel_select_submission(ack, body, client, logger):
    logger.info("Received pulse report channel select submission")
    try:
        ack()
        
        days = int(body["view"]["private_metadata"])
        report_metrics.handle_channel_select_submission(
            body["view"],
            body["user"]["id"],
            client,
            logger,
            days
        )
        logger.info("Successfully handled pulse report channel select submission")
    except Exception as e:
        logger.error(f"Error handling pulse report channel select submission: {e}")

@app.action("get_content_recommendations")
def handle_content_recommendations(ack, body, client, logger):
    logger.info("Received content recommendations action")
    try:
        ack()
        report_metrics.handle_content_recommendations(body, client, logger)
        logger.info("Successfully handled content recommendations action")
    except Exception as e:
        logger.error(f"Error handling content recommendations action: {e}")

@app.event("message")
def handle_message_events(event, logger):
    """Handle message events to prevent unhandled request errors."""
    # Ignore bot messages and message changes to prevent loops
    if event.get("subtype") in ["bot_message", "message_changed", "message_deleted"]:
        return
    
    logger.info(f"Received message event: {event}")
    # Add any message handling logic here if needed

def run_scheduler():
    """Run the scheduler for periodic tasks."""
    logger.info("Starting periodic scheduler thread")
    try:
        schedule.every().day.at("08:00").do(
            channel_tracker.update_installed_channels
        )
        logger.info("Scheduled daily channel tracker update at 08:00")
        
        while True:
            schedule.run_pending()
            time.sleep(60)
    except Exception as e:
        logger.error(f"Error in scheduler thread: {e}")

def main():
    logger.info("Starting main application...")
    
    try:
        # Start the daily Blinkist Pulse scheduler
        logger.info("Starting daily pulse scheduler...")
        start_daily_pulse_scheduler()
        logger.info("Daily pulse scheduler started successfully")
    except Exception as e:
        logger.error(f"Error starting daily pulse scheduler: {e}")
        # Don't raise - continue with the rest of the app

    try:
        # Start the scheduler in a separate thread
        logger.info("Starting periodic scheduler thread...")
        scheduler_thread = threading.Thread(target=run_scheduler)
        scheduler_thread.daemon = True
        scheduler_thread.start()
        logger.info("Periodic scheduler thread started successfully")
    except Exception as e:
        logger.error(f"Error starting scheduler thread: {e}")
    
    try:
        logger.info("Starting Slack socket mode handler...")
        handler = SocketModeHandler(app, SLACK_APP_TOKEN)
        logger.info("Socket mode handler initialized, starting connection...")
        handler.start()
    except Exception as e:
        logger.error(f"Error starting socket mode handler: {e}")
        raise

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"Fatal error in main: {e}")
        raise
