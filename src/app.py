import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from handlers.command_handler import CommandHandler
from handlers.skill_assessment import SkillAssessmentHandler

# Read tokens from environment variables
SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_APP_TOKEN = os.environ["SLACK_APP_TOKEN"]

# Initialize the Slack app
app = App(token=SLACK_BOT_TOKEN)

# Initialize handlers
command_handler = CommandHandler(app)
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
    main() 