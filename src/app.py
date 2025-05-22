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
from handlers.skill_assessment import SkillAssessmentHandler
import schedule
import time
import threading

# Initialize the Slack app
app = App(token=Settings.SLACK_BOT_TOKEN)

# Initialize handlers
quiet_channel = QuietChannelHandler(app)
question_tracker = QuestionTracker(app)
weekly_summary = WeeklySummary(app)
command_handler = CommandHandler(app)
skill_assessment_handler = SkillAssessmentHandler(app)

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
    handler = SocketModeHandler(app, Settings.SLACK_APP_TOKEN)
    handler.start()

if __name__ == "__main__":
    main() 