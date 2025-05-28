import json
import os
import openai
import logging
import random

class SkillModel:
    def __init__(self):
        # Set up logging
        self.logger = logging.getLogger(__name__)
        
        # Load skill descriptions from JSON
        data_path = os.path.join(os.path.dirname(__file__), "../data/skill_descriptions.json")
        with open(data_path, "r") as f:
            self.skill_descriptions = json.load(f)
        
        # Get OpenAI API key from environment
        openai_api_key = os.environ.get("OPENAI_API_KEY", "")
        if not openai_api_key:
            self.logger.error("OpenAI API key not found in environment variables")
            raise ValueError("OpenAI API key not found in environment variables")
        
        # Initialize OpenAI client with minimal arguments
        try:
            self.openai_client = openai.OpenAI(api_key=openai_api_key)
        except TypeError as e:
            self.logger.warning(f"Error initializing OpenAI client with default arguments: {e}")
            # Try alternative initialization without proxies
            self.openai_client = openai.OpenAI(
                api_key=openai_api_key,
                http_client=None  # Let OpenAI create its own client
            )

    def assess_skills(self, messages):
        # Prepare the text corpus from user messages
        user_texts = [msg.get("text", "") for msg in messages if msg.get("text")]
        if not user_texts:
            self.logger.warning("No message texts found in the provided messages")
            return {skill: 0 for skill in self.skill_descriptions.keys()}

        # Store a few example messages for each skill assessment
        message_examples = random.sample(user_texts, min(5, len(user_texts)))
        self.message_examples = message_examples

        # Compose the system prompt
        skills_list = "\n".join([f"- {skill}: {desc}" for skill, desc in self.skill_descriptions.items()])
        system_prompt = (
            "You are an expert in workplace soft skills assessment. "
            "Given a user's Slack messages, analyze and score the user on each of the following soft skills "
            "from 1 (limited evidence) to 5 (exceptional evidence). "
            "IMPORTANT: Only assign a score when there is sufficient evidence in the messages. "
            "If there's insufficient evidence for a skill, assign it a score of 0 (not assessable). "
            "For each skill with a score above 0, include: "
            "1) A brief explanation of why you assigned that score "
            "2) Your confidence level (high/medium/low) "
            "3) A specific example from their messages that demonstrates this skill "
            "Return your answer as a JSON object with this structure: "
            "{ \"skills\": { \"SkillName\": { \"score\": number, \"confidence\": \"high|medium|low\", "
            "\"explanation\": \"text\", \"example\": \"specific message example\" } } }"
            "\n\n"
            "Skills:\n"
            f"{skills_list}\n"
        )

        # Prepare the user prompt (truncate if too long)
        max_messages = 30
        selected_texts = user_texts[:max_messages]
        user_prompt = (
            "Here are the user's recent Slack messages:\n\n"
            + "\n".join([f"- {t}" for t in selected_texts])
        )

        self.logger.info(f"Assessing skills based on {len(selected_texts)} messages")
        
        try:
            self.logger.info("Sending request to OpenAI API")
            response = self.openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.2,
                max_tokens=2000,
                response_format={"type": "json_object"}  # Ensure JSON response
            )
            content = response.choices[0].message.content.strip()
            self.logger.info(f"Received response from OpenAI API: {content[:100]}...")
            
            # Parse the JSON result
            try:
                result_data = json.loads(content)
                self.logger.info("Successfully parsed JSON response")
                
                # Extract skills data
                skills_data = result_data.get("skills", {})
                
                # Convert to simple score dictionary for backward compatibility
                scores = {}
                for skill in self.skill_descriptions.keys():
                    skill_info = skills_data.get(skill, {})
                    score = skill_info.get("score", 0)
                    try:
                        score = int(score)
                    except Exception:
                        score = 0
                    scores[skill] = max(0, min(5, score))
                
                # Store the full data for detailed reporting
                self.last_assessment_details = skills_data
                
                self.logger.info(f"Completed skill assessment with scores: {scores}")
                return scores
                
            except json.JSONDecodeError as e:
                self.logger.error(f"Failed to parse JSON response: {e}")
                self.logger.error(f"Raw response: {content}")
                return {skill: 0 for skill in self.skill_descriptions.keys()}
            
        except Exception as e:
            # On error, return zeros for all skills
            self.logger.error(f"Error in LLM skill assessment: {e}")
            return {skill: 0 for skill in self.skill_descriptions.keys()} 