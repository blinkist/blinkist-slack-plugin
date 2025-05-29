import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
import schedule
import time
import threading
from handlers.daily_pulse import start_daily_pulse_scheduler
from handlers.skill_assessment import SkillAssessmentHandler

# Read tokens from environment variables
SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_APP_TOKEN = os.environ["SLACK_APP_TOKEN"]

# Initialize the Slack app
app = App(token=SLACK_BOT_TOKEN)

# Initialize handlers
skill_assessment_handler = SkillAssessmentHandler(app)

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

def main():
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()

if __name__ == "__main__":
    # Start the daily Blinkist Pulse scheduler
    start_daily_pulse_scheduler()
