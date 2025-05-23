"""Slack app initialization and command handlers."""
import logging
import os
import schedule
import sys
import threading
import time
from pathlib import Path

from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

# Load environment variables from env file
load_dotenv('.env')

from utils.channel_utils import ChannelTracker
from handlers.quiet_channel import QuietChannelHandler
from handlers.question_tracker import QuestionTracker
from handlers.weekly_summary import WeeklySummary
from handlers.command_handler import CommandHandler
from handlers.report_metrics import ReportMetrics

# Set up logging
logger = logging.getLogger(__name__)

# Initialize the Slack app
app = App(token=os.environ.get("SLACK_BOT_TOKEN"))

# Initialize channel tracker
channel_tracker = ChannelTracker(app)

# Initialize handlers
quiet_channel = QuietChannelHandler(app)
question_tracker = QuestionTracker(app)
weekly_summary = WeeklySummary(app)
command_handler = CommandHandler(app)
report_metrics = ReportMetrics(app, channel_tracker)

# TODO: remove this once scheduler works
channel_tracker.update_installed_channels()

# Register message events
@app.message("")
def handle_message(message, say):
    # Reset quiet channel timer
    quiet_channel.reset_timer(message['channel'])
    
    # Check for questions
    if message.get('text', '').strip().endswith('?'):
        question_tracker.track_question(message)
    
    # Update weekly summary data
    weekly_summary.process_message(message)

# Register slash commands
@app.command("/tell-joke")
def handle_joke_command(ack, respond):
    ack()
    command_handler.tell_joke(respond)

@app.command("/channel-mood")
def handle_mood_command(ack, command, respond):
    ack()
    command_handler.analyze_channel_mood(command['channel_id'], respond)

@app.command("/pulse-report")
def pulse_report_command(ack, body, client, logger):
    """Handle the /pulse-report command.
    
    Opens a modal for channel selection and then generates a report for the
    selected channels.
    
    Args:
        days (optional): Number of days to look back (default: 30)
    """
    # Acknowledge the command request
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
    """Handle the submission of the channel selection modal.
    
    Args:
        ack: Function to acknowledge the view submission
        body: The view submission data
        client: The Slack client instance
        logger: Logger instance
    """
    # Acknowledge the view submission
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

def run_scheduler():
    """Run the scheduler for periodic tasks."""
    # Schedule channel tracker every morning
    # schedule.every().day.at("08:00").do(
    #     channel_tracker.update_installed_channels
    # )
    schedule.every(5).minutes.do(
        channel_tracker.update_installed_channels
    )  # TODO: remove this

    # Schedule question checks every minute
    schedule.every(1).minutes.do(
        question_tracker.check_unanswered_questions
    )
    
    # Schedule weekly summary
    schedule.every().friday.at("16:00").do(
        weekly_summary.generate_and_post_summary
    )
    
    while True:
        schedule.run_pending()
        time.sleep(60)

def main():
    """Start the Slack app and scheduler."""
    # Start the scheduler in a separate thread
    scheduler_thread = threading.Thread(target=run_scheduler)
    scheduler_thread.daemon = True
    scheduler_thread.start()
    
    # Start the app
    handler = SocketModeHandler(app, os.environ.get("SLACK_APP_TOKEN"))
    handler.start()

if __name__ == "__main__":
    main() 