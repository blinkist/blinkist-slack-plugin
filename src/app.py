import sys
import os
import schedule
import time
import threading
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables from env file
load_dotenv('.env')

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from handlers.quiet_channel import QuietChannelHandler
from handlers.question_tracker import QuestionTracker
from handlers.weekly_summary import WeeklySummary
from handlers.command_handler import CommandHandler
from handlers.report_metrics import ReportMetrics

# Initialize the Slack app
app = App(token=os.environ.get("SLACK_BOT_TOKEN"))

# Initialize handlers
quiet_channel = QuietChannelHandler(app)
question_tracker = QuestionTracker(app)
weekly_summary = WeeklySummary(app)
command_handler = CommandHandler(app)
report_metrics = ReportMetrics(app)

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
def pulse_report_command(ack, command, respond):
    """Handle the /pulse-report command.
    
    Args:
        days (optional): Number of days to look back (default: 30)
    """
    # Acknowledge the command request
    ack()
    
    try:
        # Get the number of days (default to 30 if not specified)
        days = 30
        if command["text"].strip():
            try:
                days = int(command["text"].strip())
                if days <= 0:
                    respond("Please provide a positive number of days")
                    return
            except ValueError:
                respond("Please provide a valid number of days")
                return
        
        # Generate and return the report
        report = report_metrics.generate_report(days)
        respond(report)
        
    except Exception as e:
        logger.error(f"Error generating report: {str(e)}")
        respond("Sorry, there was an error generating the report")

def run_scheduler():
    # Schedule question checks every minute
    schedule.every(1).minutes.do(question_tracker.check_unanswered_questions)
    
    # Schedule weekly summary
    schedule.every().friday.at("16:00").do(weekly_summary.generate_and_post_summary)
    
    while True:
        schedule.run_pending()
        time.sleep(60)

def main():
    # Start the scheduler in a separate thread
    scheduler_thread = threading.Thread(target=run_scheduler)
    scheduler_thread.daemon = True
    scheduler_thread.start()
    
    # Start the app
    handler = SocketModeHandler(app, os.environ.get("SLACK_APP_TOKEN"))
    handler.start()

if __name__ == "__main__":
    main() 