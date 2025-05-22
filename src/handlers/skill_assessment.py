from slack_sdk.errors import SlackApiError
from utils.skill_model import SkillModel
import logging
import datetime

class SkillAssessmentHandler:
    def __init__(self, app):
        self.app = app
        self.skill_model = SkillModel()

    def open_channel_select_modal(self, body, client, logger):
        user_id = body["user_id"]
        try:
            # Acknowledge the command immediately
            trigger_id = body["trigger_id"]
            
            # Get bot's user ID
            bot_info = client.auth_test()
            bot_id = bot_info["user_id"]
            
            # Fetch list of channels the user is a member of
            response = client.users_conversations(user=user_id, types="public_channel,private_channel")
            user_channels = response["channels"]
            
            # Fetch list of channels the bot is a member of
            bot_response = client.users_conversations(user=bot_id, types="public_channel,private_channel")
            bot_channel_ids = [ch["id"] for ch in bot_response["channels"]]
            
            # Filter to only include channels where both user and bot are members
            valid_channels = [ch for ch in user_channels if ch["id"] in bot_channel_ids]
            
            # Create options from valid channels
            options = [
                {
                    "text": {"type": "plain_text", "text": ch["name"]},
                    "value": ch["id"]
                }
                for ch in valid_channels
            ]
            
            # Open modal immediately with filtered channels
            client.views_open(
                trigger_id=trigger_id,
                view={
                    "type": "modal",
                    "callback_id": "skill_assess_channel_select",
                    "title": {"type": "plain_text", "text": "Skill Assessment"},
                    "submit": {"type": "plain_text", "text": "Assess"},
                    "blocks": [
                        {
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": "Select channels to analyze your messages from the last 30 days:"}
                        },
                        {
                            "type": "input",
                            "block_id": "channels_block",
                            "element": {
                                "type": "multi_static_select",
                                "action_id": "channels_select",
                                "placeholder": {"type": "plain_text", "text": "Select channels"},
                                "options": options
                            },
                            "label": {"type": "plain_text", "text": "Choose channels to assess"}
                        }
                    ]
                }
            )
            
        except SlackApiError as e:
            logger.error(f"Error opening channel select modal: {e}")

    def handle_channel_select_submission(self, view, user, client, logger):
        # Extract selected channel IDs from the modal submission
        selected_channels = view["state"]["values"]["channels_block"]["channels_select"]["selected_options"]
        channel_ids = [ch["value"] for ch in selected_channels]
        logger.info(f"User {user} selected channels: {channel_ids}")

        # Send acknowledgment message
        try:
            client.chat_postMessage(
                channel=user,
                text="🔍 *Processing your skill assessment...*\nThis may take a minute or two. I'll message you when it's ready."
            )
        except SlackApiError as e:
            logger.error(f"Error sending acknowledgment message: {e}")

        # Fetch messages from each channel (last 30 days)
        all_messages = []
        oldest_ts = (datetime.datetime.now() - datetime.timedelta(days=30)).timestamp()
        for channel_id in channel_ids:
            try:
                has_more = True
                cursor = None
                while has_more:
                    response = client.conversations_history(
                        channel=channel_id,
                        oldest=str(oldest_ts),
                        limit=200,
                        cursor=cursor
                    )
                    # Only keep messages sent by the user
                    user_msgs = [
                        msg for msg in response["messages"]
                        if msg.get("user") == user and "subtype" not in msg
                    ]
                    all_messages.extend(user_msgs)
                    has_more = response.get("has_more", False)
                    cursor = response.get("response_metadata", {}).get("next_cursor")
                    
                    logger.info(f"Fetched batch of messages from {channel_id}, found {len(user_msgs)} user messages")
                    
            except SlackApiError as e:
                logger.error(f"Error fetching messages from channel {channel_id}: {e}")

        logger.info(f"Fetched {len(all_messages)} messages from selected channels for user {user}")

        if not all_messages:
            try:
                client.chat_postMessage(
                    channel=user,
                    text="⚠️ *No messages found*\nI couldn't find any of your messages in the selected channels from the last 30 days."
                )
                return
            except SlackApiError as e:
                logger.error(f"Error sending no messages found notification: {e}")
                return

        # Pass messages to skill model for assessment
        skill_scores = self.skill_model.assess_skills(all_messages)

        # Format and send results to user (DM)
        self._send_results_to_user(user, skill_scores, client, logger)

    def _send_results_to_user(self, user_id, skill_scores, client, logger):
        try:
            # Get detailed assessment if available
            detailed_assessment = getattr(self.skill_model, 'last_assessment_details', {})
            
            # Format a summary with explanations
            summary = "*Your Skill Assessment Results:*\n\n"
            summary += "_Based on your messages from the selected channels over the last 30 days._\n\n"
            
            # Group skills by score for better visualization
            score_groups = {5: [], 4: [], 3: [], 2: [], 1: [], 0: []}
            for skill, score in skill_scores.items():
                score_groups[score].append(skill)
            
            # Add emojis and descriptions based on score
            emojis = {5: "🌟", 4: "✨", 3: "👍", 2: "🔍", 1: "🌱", 0: "❓"}
            descriptions = {
                5: "Outstanding - Exceptional demonstration",
                4: "Strong - Clear, consistent evidence",
                3: "Good - Solid evidence present",
                2: "Developing - Some evidence shown",
                1: "Emerging - Limited evidence found",
                0: "Insufficient data to assess"
            }
            
            # Format the results
            has_skills = False
            for score in sorted(score_groups.keys(), reverse=True):
                if score_groups[score] and score > 0:  # Only show skills with scores > 0
                    has_skills = True
                    summary += f"\n*{emojis[score]} Score {score}: {descriptions[score]}*\n"
                    for skill in sorted(score_groups[score]):
                        summary += f"• *{skill}*"
                        
                        # Add explanation if available
                        skill_detail = detailed_assessment.get(skill, {})
                        explanation = skill_detail.get("explanation", "")
                        confidence = skill_detail.get("confidence", "")
                        example = skill_detail.get("example", "")
                        
                        if explanation:
                            summary += f": _{explanation}_"
                        if confidence:
                            summary += f" (Confidence: {confidence})"
                        if example:
                            summary += f"\n  _Example: \"{example}\"_"
                        
                        summary += "\n"
            
            # If no skills with scores > 0, show a message
            if not has_skills:
                summary += "\n_Not enough data was found to confidently assess your skills. Try selecting more channels or continuing to engage in conversations._\n"
            
            # Add a note about skills with score 0
            if score_groups[0]:
                summary += "\n*Skills with insufficient evidence:*\n"
                summary += ", ".join([f"_{skill}_" for skill in sorted(score_groups[0])]) + "\n"
                summary += "_These skills couldn't be assessed from your messages. This doesn't mean you lack these skills - they may just not be evident in your Slack communications._\n"
            
            client.chat_postMessage(
                channel=user_id,
                text=summary
            )
        except SlackApiError as e:
            logger.error(f"Error sending skill assessment results to user: {e}")

# ... (add more methods as you build out the feature) ... 