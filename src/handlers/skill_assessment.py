from slack_sdk.errors import SlackApiError
from utils.skill_model import SkillModel
import logging
import datetime
import json
import os
import random
from utils.openai_client import OpenAIClient

class SkillAssessmentHandler:
    def __init__(self, app):
        self.app = app
        self.skill_model = SkillModel()
        self.user_quiz_data = {}  # Store quiz state for users
        self.openai_client = OpenAIClient()
        
        # Test OpenAI connection
        connection_test = self.openai_client.test_connection()
        if connection_test:
            logging.info("OpenAI connection test successful")
        else:
            logging.error("OpenAI connection test failed")
        
        # Load quiz questions
        quiz_path = os.path.join(os.path.dirname(__file__), "../data/quiz_data_long.json")
        try:
            with open(quiz_path, "r") as f:
                self.quiz_data = json.load(f)
        except FileNotFoundError:
            # Create a basic quiz data structure if file not found
            self.quiz_data = {"questions": []}
            print(f"Warning: Quiz data file not found at {quiz_path}")
        
        # Register action handlers for quiz buttons
        for i in range(1, 6):  # For answer values 1-5
            for j in range(10):  # For up to 10 questions
                app.action(f"quiz_answer_{i}_{j}")(self.handle_quiz_answer)
        
        app.action("start_quiz")(self.start_quiz)

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
            
            # Add a note about skills with score 0 and offer a quiz
            if score_groups[0]:
                # Store the unassessed skills for this user
                self.user_quiz_data[user_id] = {
                    "unassessed_skills": score_groups[0],
                    "current_question": 0,
                    "answers": {},
                    "questions": []
                }
                
                summary += "\n*Skills with insufficient evidence:*\n"
                summary += ", ".join([f"_{skill}_" for skill in sorted(score_groups[0])]) + "\n"
                summary += "_These skills couldn't be assessed from your messages. This doesn't mean you lack these skills - they may just not be evident in your Slack communications._\n\n"
                
                # Add a button to start the quiz
                client.chat_postMessage(
                    channel=user_id,
                    text=summary,
                    blocks=[
                        {
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": summary}
                        },
                        {
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": "Would you like to take a short quiz to assess these skills?"},
                            "accessory": {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "Start Quiz"},
                                "action_id": "start_quiz",
                                "style": "primary"
                            }
                        }
                    ]
                )
            else:
                # If there are no unassessed skills, send recommendations immediately
                client.chat_postMessage(
                    channel=user_id,
                    text=summary
                )
                
                # Get recommendations from OpenAI Assistant
                try:
                    logger.info("Getting recommendations from OpenAI Assistant")
                    recommendations = self.openai_client.get_recommendations(skill_scores)
                    self._send_recommendations(user_id, recommendations, client, logger)
                except Exception as e:
                    logger.error(f"Error getting recommendations: {e}")
                
        except SlackApiError as e:
            logger.error(f"Error sending skill assessment results to user: {e}")

    def _send_recommendations(self, user_id, recommendations, client, logger):
        """Send personalized recommendations to the user"""
        try:
            # Extract data from recommendations
            overview = recommendations.get("overview", "")
            reasoning = recommendations.get("reasoning", "")
            content_recommendations = recommendations.get("recommendations", [])
            
            logger.info(f"Sending recommendations to user {user_id}")
            logger.info(f"Content recommendations: {json.dumps(content_recommendations)}")
            
            # First, send the overview message
            if len(overview) > 3000:
                overview = overview[:3000] + "..."
                
            client.chat_postMessage(
                channel=user_id,
                text=f"*Personalized Recommendations*\n\n{overview}"
            )
            
            # Then, send reasoning in a separate message if it exists
            if reasoning:
                if len(reasoning) > 3000:
                    reasoning = reasoning[:3000] + "..."
                    
                client.chat_postMessage(
                    channel=user_id,
                    text=f"*Why These Recommendations?*\n\n{reasoning}"
                )
            
            # Finally, send content recommendations one by one
            if content_recommendations:
                client.chat_postMessage(
                    channel=user_id,
                    text="*Recommended Content:*"
                )
                
                # Process each content recommendation
                for i, content in enumerate(content_recommendations[:5]):
                    try:
                        content_title = content.get("content_title", f"Recommendation {i+1}")
                        content_description = content.get("content_description", "No description available")
                        content_type = content.get("content_type", "").lower()
                        content_id = content.get("content_id", "")
                        slug = content.get("slug", content_id)
                        
                        # Log the content details
                        logger.info(f"Processing recommendation {i+1}: {content_title}")
                        logger.info(f"Content type: {content_type}, Content ID: {content_id}, Slug: {slug}")
                        
                        # Truncate description if too long
                        if len(content_description) > 200:
                            content_description = content_description[:200] + "..."
                        
                        # Determine URL and image URL based on content type
                        if content_type == "collection":
                            url = f"https://www.blinkist.com/app/collections/{slug}"
                            image_url = f"https://images.blinkist.io/images/curated_lists/{content_id}/1_1/640.jpg"
                        else:  # Default to guide
                            url = f"https://www.blinkist.com/app/guides/{slug}"
                            image_url = f"https://images.blinkist.io/images/courses/{content_id}/cover/640.png"
                        
                        logger.info(f"URL: {url}")
                        logger.info(f"Image URL: {image_url}")
                        
                        # Send a message with blocks for both text and image
                        blocks = [
                            {
                                "type": "section",
                                "text": {
                                    "type": "mrkdwn",
                                    "text": f"*<{url}|{content_title}>*\n{content_description}"
                                },
                                "accessory": {
                                    "type": "image",
                                    "image_url": image_url,
                                    "alt_text": content_title
                                }
                            },
                            {
                                "type": "actions",
                                "elements": [
                                    {
                                        "type": "button",
                                        "text": {
                                            "type": "plain_text",
                                            "text": "View Content",
                                            "emoji": True
                                        },
                                        "url": url,
                                        "action_id": f"view_content_{i}"
                                    }
                                ]
                            }
                        ]
                        
                        response = client.chat_postMessage(
                            channel=user_id,
                            blocks=blocks
                        )
                        
                        logger.info(f"Sent recommendation with response: {response}")
                        
                    except Exception as e:
                        logger.error(f"Error sending recommendation {i+1}: {str(e)}")
                        # Send a simple text message as fallback
                        client.chat_postMessage(
                            channel=user_id,
                            text=f"*{content_title}*\n{content_description}\n\n<{url}|View Content>"
                        )
                        
            else:
                # Send a message if no content recommendations
                client.chat_postMessage(
                    channel=user_id,
                    text="No specific content recommendations were found for your skill profile."
                )
                
        except Exception as e:
            logger.error(f"Error sending recommendations: {str(e)}")
            # Send a fallback message
            client.chat_postMessage(
                channel=user_id,
                text="I've analyzed your skills and have some personalized recommendations, but encountered an error displaying them. Please try the assessment again later."
            )

    def start_quiz(self, ack, body, client, logger):
        """Start the quiz for unassessed skills"""
        ack()
        user_id = body["user"]["id"]
        
        if user_id not in self.user_quiz_data:
            client.chat_postMessage(
                channel=user_id,
                text="Sorry, I don't have any quiz data for you. Please run the skill assessment first."
            )
            return
        
        # Get unassessed skills for this user
        unassessed_skills = self.user_quiz_data[user_id]["unassessed_skills"]
        
        # Find questions related to these skills
        relevant_questions = []
        for question in self.quiz_data["questions"]:
            if any(skill in unassessed_skills for skill in question["skills"]):
                relevant_questions.append(question)
        
        # If no relevant questions, inform the user
        if not relevant_questions:
            client.chat_postMessage(
                channel=user_id,
                text="Sorry, I don't have any quiz questions for your unassessed skills."
            )
            return
        
        # Select up to 5 random questions
        selected_questions = random.sample(relevant_questions, min(5, len(relevant_questions)))
        self.user_quiz_data[user_id]["questions"] = selected_questions
        
        # Send the first question
        self._send_quiz_question(user_id, 0, client, logger)

    def _send_quiz_question(self, user_id, question_index, client, logger):
        """Send a quiz question to the user"""
        if user_id not in self.user_quiz_data:
            return
        
        quiz_data = self.user_quiz_data[user_id]
        questions = quiz_data["questions"]
        
        if question_index >= len(questions):
            # Quiz is complete, show results
            self._show_quiz_results(user_id, client, logger)
            return
        
        question = questions[question_index]
        quiz_data["current_question"] = question_index
        
        # Create the question message with buttons
        client.chat_postMessage(
            channel=user_id,
            text=f"Question {question_index + 1} of {len(questions)}",
            blocks=[
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*Question {question_index + 1} of {len(questions)}*\n\n{question['text']}"}
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Strongly Disagree"},
                            "value": "1",
                            "action_id": f"quiz_answer_1_{question_index}"
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Disagree"},
                            "value": "2",
                            "action_id": f"quiz_answer_2_{question_index}"
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Neutral"},
                            "value": "3",
                            "action_id": f"quiz_answer_3_{question_index}"
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Agree"},
                            "value": "4",
                            "action_id": f"quiz_answer_4_{question_index}"
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Strongly Agree"},
                            "value": "5",
                            "action_id": f"quiz_answer_5_{question_index}"
                        }
                    ]
                }
            ]
        )

    def handle_quiz_answer(self, ack, body, client, logger):
        """Handle a quiz answer from the user"""
        ack()
        user_id = body["user"]["id"]
        action_id = body["actions"][0]["action_id"]
        answer_value = int(body["actions"][0]["value"])
        
        if user_id not in self.user_quiz_data:
            return
        
        quiz_data = self.user_quiz_data[user_id]
        current_question = quiz_data["current_question"]
        question = quiz_data["questions"][current_question]
        
        # Store the answer
        quiz_data["answers"][current_question] = {
            "question": question["text"],
            "skills": question["skills"],
            "answer": answer_value
        }
        
        # Move to the next question
        self._send_quiz_question(user_id, current_question + 1, client, logger)

    def _show_quiz_results(self, user_id, client, logger):
        """Show the quiz results to the user and get recommendations"""
        if user_id not in self.user_quiz_data:
            return
        
        quiz_data = self.user_quiz_data[user_id]
        answers = quiz_data["answers"]
        
        # Calculate scores for each skill
        skill_scores = {}
        skill_counts = {}
        
        for q_idx, answer_data in answers.items():
            answer_value = answer_data["answer"]
            for skill in answer_data["skills"]:
                if skill not in skill_scores:
                    skill_scores[skill] = 0
                    skill_counts[skill] = 0
                
                skill_scores[skill] += answer_value
                skill_counts[skill] += 1
        
        # Calculate average scores
        avg_scores = {}
        for skill, total in skill_scores.items():
            count = skill_counts[skill]
            if count > 0:
                avg_scores[skill] = round(total / count, 1)
        
        # Format the results
        result_text = "*Your Self-Assessment Quiz Results:*\n\n"
        result_text += "_Based on your responses to the quiz questions._\n\n"
        
        for skill, score in sorted(avg_scores.items(), key=lambda x: x[1], reverse=True):
            # Convert 1-5 scale to descriptive text
            if score >= 4.5:
                level = "Very Strong"
                emoji = "🌟"
            elif score >= 3.5:
                level = "Strong"
                emoji = "✨"
            elif score >= 2.5:
                level = "Moderate"
                emoji = "👍"
            elif score >= 1.5:
                level = "Developing"
                emoji = "🔍"
            else:
                level = "Emerging"
                emoji = "🌱"
            
            result_text += f"{emoji} *{skill}*: {score}/5 - {level}\n"
        
        result_text += "\n_This self-assessment complements your message-based skill assessment. Remember that self-perception and actual demonstration of skills can differ._"
        
        client.chat_postMessage(
            channel=user_id,
            text=result_text
        )
        
        # Send loading message - don't store the timestamp
        client.chat_postMessage(
            channel=user_id,
            text="🔄 Generating personalized recommendations based on your assessment... This may take a moment."
        )
        
        # Combine message-based assessment with quiz results
        combined_scores = {}
        
        # First, add any scores from the original assessment
        if hasattr(self, 'last_assessment_scores') and user_id in self.last_assessment_scores:
            combined_scores.update(self.last_assessment_scores[user_id])
        
        # Then add/update with quiz results for previously unassessed skills
        for skill, score in avg_scores.items():
            # Convert 1-5 scale to 0-5 scale (matching the message assessment)
            combined_scores[skill] = min(5, max(0, int(round(score))))
        
        # Get recommendations based on combined scores
        try:
            logger.info(f"Getting recommendations from OpenAI Assistant for user {user_id}")
            logger.info(f"Combined scores: {combined_scores}")
            
            recommendations = self.openai_client.get_recommendations(combined_scores)
            
            # Send completion message instead of updating
            client.chat_postMessage(
                channel=user_id,
                text="✅ Your personalized recommendations are ready!"
            )
            
            self._send_recommendations(user_id, recommendations, client, logger)
        except Exception as e:
            logger.error(f"Error getting recommendations: {e}")
            # Send error message instead of updating
            client.chat_postMessage(
                channel=user_id,
                text="❌ I encountered an error while generating your recommendations. Please try again later."
            )
        
        # Clear the quiz data for this user
        del self.user_quiz_data[user_id]

    def process_skill_assessment(self, body, client, logger):
        """Process the skill assessment request"""
        user_id = body["user"]["id"]
        view = body["view"]
        
        # Get selected channels
        selected_channels = []
        try:
            selected_values = view["state"]["values"]["channels_block"]["channels_select"]["selected_options"]
            selected_channels = [option["value"] for option in selected_values]
        except Exception as e:
            logger.error(f"Error extracting selected channels: {e}")
        
        if not selected_channels:
            client.chat_postMessage(
                channel=user_id,
                text="You didn't select any channels. Please try again and select at least one channel."
            )
            return
        
        # Acknowledge the request
        client.chat_postMessage(
            channel=user_id,
            text="I'm analyzing your messages from the selected channels. This may take a minute..."
        )
        
        # Fetch messages from the selected channels
        messages = []
        for channel_id in selected_channels:
            try:
                # Get messages from the last 30 days
                thirty_days_ago = datetime.datetime.now() - datetime.timedelta(days=30)
                oldest_timestamp = thirty_days_ago.timestamp()
                
                response = client.conversations_history(
                    channel=channel_id,
                    oldest=oldest_timestamp
                )
                
                # Filter to only include messages from this user
                user_messages = [msg for msg in response["messages"] if msg.get("user") == user_id]
                messages.extend(user_messages)
                
                logger.info(f"Found {len(user_messages)} messages from user in channel {channel_id}")
                
            except SlackApiError as e:
                logger.error(f"Error fetching messages from channel {channel_id}: {e}")
        
        if not messages:
            client.chat_postMessage(
                channel=user_id,
                text="I couldn't find any of your messages in the selected channels from the last 30 days. Please try selecting different channels."
            )
            return
        
        # Assess skills based on messages
        skill_scores = self.skill_model.assess_skills(messages)
        
        # Store the assessment scores for this user
        if not hasattr(self, 'last_assessment_scores'):
            self.last_assessment_scores = {}
        self.last_assessment_scores[user_id] = skill_scores
        
        # Send results to the user
        self._send_results_to_user(user_id, skill_scores, client, logger)

# ... (add more methods as you build out the feature) ... 