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

# Set up logging
logger = logging.getLogger(__name__)

# Read tokens from environment variables
SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_APP_TOKEN = os.environ["SLACK_APP_TOKEN"]

# Initialize the Slack app
app = App(token=SLACK_BOT_TOKEN)

# Initialize channel tracker
channel_tracker = ChannelTracker(app)
# First time update upon startup, then scheduler takes over
channel_tracker.update_installed_channels()

# Initialize handlers
skill_assessment_handler = SkillAssessmentHandler(app)
report_metrics = ReportMetrics(app, channel_tracker)

@app.command("/pulse-assess")
def handle_pulse_assess_command(ack, body, client, logger):
    ack()
    skill_assessment_handler.open_channel_select_modal(body, client, logger)

@app.view("skill_assess_channel_select")
def handle_skill_assess_view_submission(ack, body, client, logger):
    ack()
    skill_assessment_handler.handle_channel_select_submission(
        view=body["view"],
        user=body["user"]["id"],
        client=client,
        logger=logger
    )

@app.command("/pulse-report")
def pulse_report_command(ack, body, client, logger):
    """Handle the /pulse-report command."""
    ack()
    
    try:
        # Get the number of days (default to 30 if not specified)
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
        
        # Open the channel selection modal with the specified days
        report_metrics.open_channel_select_modal(body, client, logger, days)
    except Exception as e:
        logger.error(f"Error opening channel selection modal: {str(e)}")
        client.chat_postMessage(
            channel=body["user_id"],
            text="Sorry, there was an error opening the channel selection. "
                 "Please try again later."
        )

@app.view("pulse_report_channel_select")
def handle_channel_select_submission(ack, body, client, logger):
    """Handle the submission of the channel selection modal."""
    ack()
    
    try:
        # Get the days from the private metadata
        days = int(body["view"]["private_metadata"])
        
        # Handle the channel selection submission
        report_metrics.handle_channel_select_submission(
            body["view"],
            body["user"]["id"],
            client,
            logger,
            days
        )
    except Exception as e:
        logger.error(f"Error handling channel selection submission: {str(e)}")
        client.chat_postMessage(
            channel=body["user"]["id"],
            text="Sorry, there was an error processing your selection. "
                 "Please try again later."
        )

# Register action handlers
app.action("get_content_recommendations")(report_metrics.handle_content_recommendations)

def run_scheduler():
    """Run the scheduler for periodic tasks."""
    # Schedule channel tracker every morning
    schedule.every().day.at("08:00").do(
        channel_tracker.update_installed_channels
    )
    
    while True:
        schedule.run_pending()
        time.sleep(60)

def main():

    # Start the scheduler in a separate thread
    scheduler_thread = threading.Thread(target=run_scheduler)
    scheduler_thread.daemon = True
    scheduler_thread.start()
    
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()

if __name__ == "__main__":
    # Start the daily Blinkist Pulse scheduler
    start_daily_pulse_scheduler()
    import asyncio
    asyncio.get_event_loop().run_forever() 