import json
import os
import openai
import logging

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
        self.openai_client = openai.OpenAI(api_key=openai_api_key)

    def assess_skills(self, messages):
        # Prepare the text corpus from user messages
        user_texts = [msg.get("text", "") for msg in messages if msg.get("text")]
        if not user_texts:
            self.logger.warning("No message texts found in the provided messages")
            return {skill: 0 for skill in self.skill_descriptions.keys()}

        # Compose the system prompt
        skills_list = "\n".join([f"- {skill}: {desc}" for skill, desc in self.skill_descriptions.items()])
        system_prompt = (
            "You are an expert in workplace soft skills assessment. "
            "Given a user's Slack messages, analyze and score the user on each of the following 20 soft skills "
            "from 0 (no evidence) to 5 (excellent evidence). "
            "Base your scores only on the provided messages. "
            "Return your answer as a JSON object mapping each skill to a score (0-5), no extra text.\n\n"
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
                max_tokens=600,
                response_format={"type": "json_object"}  # Ensure JSON response
            )
            content = response.choices[0].message.content.strip()
            self.logger.info(f"Received response from OpenAI API: {content[:100]}...")
            
            # Parse the JSON result
            try:
                scores = json.loads(content)
                self.logger.info("Successfully parsed JSON response")
            except json.JSONDecodeError as e:
                self.logger.error(f"Failed to parse JSON response: {e}")
                self.logger.error(f"Raw response: {content}")
                return {skill: 0 for skill in self.skill_descriptions.keys()}
            
            # Ensure all skills are present and valid
            result = {}
            for skill in self.skill_descriptions.keys():
                val = scores.get(skill, 0)
                try:
                    val = int(val)
                except Exception:
                    self.logger.warning(f"Invalid score for skill {skill}: {val}")
                    val = 0
                result[skill] = max(0, min(5, val))
            
            self.logger.info(f"Completed skill assessment with scores: {result}")
            return result
        except Exception as e:
            # On error, return zeros for all skills
            self.logger.error(f"Error in LLM skill assessment: {e}")
            return {skill: 0 for skill in self.skill_descriptions.keys()} 