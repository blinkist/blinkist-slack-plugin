import os
import json
import logging
import time
import requests

logger = logging.getLogger(__name__)

class OpenAIClient:
    def __init__(self):
        self.api_key = self._get_api_key()
        self.assistant_id = "asst_nBpfbR9DssV3SkBAEdGymbOf"
        self.base_url = "https://api.openai.com/v1"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "OpenAI-Beta": "assistants=v2"
        }
        logger.info("OpenAI client initialized with v2 headers")

    def _get_api_key(self):
        """Retrieve OpenAI API key from environment variables"""
        api_key = os.getenv('OPENAI_API_KEY_ASSISTANT') or os.getenv('OPENAI_API_KEY')
        if not api_key:
            logger.error("OpenAI API key not found in environment variables")
            raise ValueError("OpenAI API key not found in environment variables")
        return api_key

    def get_recommendations(self, skill_scores):
        """Get recommendations using direct API calls with v2 header"""
        try:
            # Create a thread
            thread_response = requests.post(
                f"{self.base_url}/threads",
                headers=self.headers,
                json={}
            )
            thread_response.raise_for_status()
            thread_id = thread_response.json()["id"]
            logger.info(f"Created thread with ID: {thread_id}")
            
            # Format the message content with specific instructions for the expected format
            message_content = (
                "Based on the following skill assessment scores, provide recommendations in JSON format. "
                "The response should follow this exact structure:\n"
                "{\n"
                '  "overview": "Overview text here",\n'
                '  "reasoning": "Reasoning text here",\n'
                '  "recommendations": [\n'
                "    {\n"
                '      "content_title": "Title of the content",\n'
                '      "content_description": "Description of the content",\n'
                '      "content_type": "guide or collection",\n'
                '      "content_id": "UUID of the content",\n'
                '      "slug": "URL slug for the content"\n'
                "    }\n"
                "  ]\n"
                "}\n\n"
                f"Skill Scores:\n{json.dumps(skill_scores, indent=2)}"
            )
            
            # Add message to thread
            message_response = requests.post(
                f"{self.base_url}/threads/{thread_id}/messages",
                headers=self.headers,
                json={
                    "role": "user",
                    "content": message_content
                }
            )
            message_response.raise_for_status()
            logger.info("Added message to thread")
            
            # Run the assistant
            run_response = requests.post(
                f"{self.base_url}/threads/{thread_id}/runs",
                headers=self.headers,
                json={
                    "assistant_id": self.assistant_id
                }
            )
            run_response.raise_for_status()
            run_id = run_response.json()["id"]
            logger.info(f"Started run with ID: {run_id}")
            
            # Wait for completion
            max_attempts = 30
            for attempt in range(max_attempts):
                run_status_response = requests.get(
                    f"{self.base_url}/threads/{thread_id}/runs/{run_id}",
                    headers=self.headers
                )
                run_status_response.raise_for_status()
                run_status = run_status_response.json()["status"]
                logger.info(f"Run status: {run_status}")
                
                if run_status not in ["queued", "in_progress"]:
                    break
                    
                time.sleep(2)  # Wait 2 seconds before checking again
            
            if run_status == "completed":
                # Get the assistant's response
                messages_response = requests.get(
                    f"{self.base_url}/threads/{thread_id}/messages",
                    headers=self.headers
                )
                messages_response.raise_for_status()
                messages = messages_response.json()["data"]
                
                # Get the assistant messages
                assistant_messages = [msg for msg in messages if msg["role"] == "assistant"]
                if assistant_messages:
                    response_text = assistant_messages[0]["content"][0]["text"]["value"]
                    logger.info("Received response from assistant")
                    logger.info(f"Raw response: {response_text[:500]}...")
                    
                    # Extract JSON from the response
                    try:
                        if "```json" in response_text:
                            response_text = response_text.split("```json")[1].split("```")[0]
                        elif "```" in response_text:
                            response_text = response_text.split("```")[1]
                        
                        recommendations = json.loads(response_text.strip())
                        logger.info("Successfully parsed recommendations")
                        logger.info(f"Parsed recommendations: {json.dumps(recommendations)[:500]}...")
                        
                        # Ensure the structure matches what's expected
                        if "recommendations" not in recommendations:
                            recommendations["recommendations"] = []
                        
                        # Ensure each recommendation has the required fields
                        for rec in recommendations["recommendations"]:
                            if "content_title" not in rec:
                                rec["content_title"] = "Recommended Content"
                            if "content_description" not in rec:
                                rec["content_description"] = "No description available"
                            if "content_type" not in rec:
                                rec["content_type"] = "guide"
                            if "content_id" not in rec:
                                rec["content_id"] = "default"
                            if "slug" not in rec:
                                rec["slug"] = rec["content_id"]
                        
                        return recommendations
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse assistant response as JSON: {str(e)}")
                        return self._fallback()
                else:
                    logger.error("No assistant messages found in thread")
                    return self._fallback()
            else:
                logger.error(f"Assistant run failed with status: {run_status}")
                return self._fallback()
            
        except Exception as e:
            logger.error(f"Error getting recommendations from OpenAI: {str(e)}")
            return self._fallback()

    def _fallback(self):
        return {
            "overview": "Based on your skill assessment, I've identified areas where you can grow professionally.",
            "reasoning": "The recommendations focus on your areas with lower scores to help you develop those skills.",
            "recommendations": []
        }

    def test_connection(self):
        """Test the connection to OpenAI API with v2 header"""
        try:
            response = requests.get(
                f"{self.base_url}/models",
                headers=self.headers
            )
            response.raise_for_status()
            models = response.json()
            logger.info(f"Connection successful, found {len(models['data'])} models")
            return True
        except Exception as e:
            logger.error(f"OpenAI connection test failed: {str(e)}")
            return False 