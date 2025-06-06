"""Content recommender using Langdock assistant API."""
import os
import logging
import requests
import json
from typing import Dict, Any, List


logger = logging.getLogger(__name__)


class ContentRecommender:
    """Class to handle content recommendations using Langdock assistant API.
    
    This class manages the connection to the Langdock assistant API and processes
    responses to create formatted Slack message blocks.
    """
    
    def __init__(self):
        """Initialize the ContentRecommender.
        
        Raises:
            ValueError: If Langdock API key is not found in environment variables
            ConnectionError: If unable to establish connection to Langdock API
        """
        # Get Langdock API key from environment
        self.api_key = os.environ["LANGDOCK_API_KEY"]
        if not self.api_key:
            logger.error(
                "Langdock API key not found in environment variables"
            )
            raise ValueError(
                "Langdock API key not found in environment variables"
            )
        
        # Set up API endpoint and headers
        self.api_url = "https://api.langdock.com/assistant/v1/chat/completions"
        self.assistant_id = "a1a5f9f9-edfb-430c-aa08-a9ef2740dab9"
        self.headers = {
            "Authorization": f"{self.api_key}",
            "Content-Type": "application/json"
        }
        
        # Test connection
        self._test_connection()

    def get_recommendations(
        self,
        channel_name: str = None,
        improvements: str = None,
        prompt: str = None
    ) -> Dict[str, Any]:
        """Generate content recommendations based on input.
        
        Args:
            channel_name (str, optional): Name of the channel
            improvements (str, optional): Areas for improvement
            prompt (str, optional): Direct prompt for recommendations
            
        Returns:
            Dict[str, Any]: Dictionary containing formatted recommendations
            
        Raises:
            ValueError: If neither channel insights nor prompt is provided
        """
        try:
            # Determine which prompt to use
            if prompt:
                final_prompt = prompt
            elif all([channel_name, improvements]):
                final_prompt = self._create_prompt(
                    channel_name, improvements
                )
            else:
                raise ValueError(
                    "Either provide a direct prompt or channel name and improvements"
                )

            # Prepare API payload
            payload = {
                "assistantId": self.assistant_id,
                "messages": [
                    {
                        "role": "user",
                        "content": final_prompt
                    }
                ],
                "output": {
                    "type": "object",
                    "enum": ["<string>"],
                    "schema": {
                        "recommendations": [
                            {
                                "content_id": "unique identifier",
                                "content_type": "book/collection/guide",
                                "title": "content title",
                                "slug": "url-friendly-identifier",
                                "description": "short content description"
                            }
                        ],
                        "reasoning": "Brief rationale for content recommendations"
                    }
                }
            }

            # Send request to API
            response = requests.request(
                "POST",
                self.api_url,
                json=payload,
                headers=self.headers
            )
            response.raise_for_status()
            # Process and return recommendations
            return self._process_api_response(response.json())
            
        except Exception as e:
            logger.error(f"Error generating recommendations: {str(e)}")
            return {
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": (
                                "Sorry, there was an error generating "
                                "recommendations."
                            )
                        }
                    }
                ]
            }
    
    def _test_connection(self) -> None:
        """Test the connection to the Langdock API.
        
        Raises:
            ConnectionError: If unable to establish connection to Langdock API
        """
        try:
            # Prepare test payload
            payload = {
                "assistantId": self.assistant_id,
                "messages": [
                    {
                        "role": "user",
                        "content": "hello world"
                    }
                ],
                "output": {
                    "type": "enum",
                    "enum": ["<string>"],
                    "schema": {}
                }
            }

            # Send test request
            response = requests.request(
                "POST",
                self.api_url,
                json=payload,
                headers=self.headers
            )
            
            # Check for successful response
            response.raise_for_status()
            logger.info("Successfully connected to Langdock API")
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to connect to Langdock API: {str(e)}")
            raise ConnectionError(
                f"Failed to connect to Langdock API: {str(e)}"
            )

    def _create_prompt(
        self,
        channel_name: str,
        improvements: str
    ) -> str:
        """Create a prompt for channel-specific recommendations.
        
        Args:
            channel_name (str): Name of the channel
            improvements (str): Areas for improvement identified for the channel
            
        Returns:
            str: Formatted prompt for the Langdock API
        """
        prompt = (
            f"Based on the decision-making analysis for channel #{channel_name}, "
            "please provide up to 3 recommendations that address the areas for "
            "improvement. Prioritize practical, actionable content that can be "
            "immediately applied to improve decision-making processes in the workplace.\n\n"
            f"Context:\n"
            f"- Areas for Improvement: {improvements}\n\n"
            "Additionally, provide 2 more recommendations that focus on improving "
            "decision-making skills more generally. Remember that the "
            "recommendations should be relevant to decision-making at work.\n\n"
            "Provide an overall reasoning for your content recommendations:\n"
            "- Why is this particular combination of content valuable for "
            "enhancing decision-making efficiency?\n"
            "- How can the team best leverage these resources together?\n"
            "- Do not include information about the approach you used to find the content.\n\n"
            "IMPORTANT:\n"
            "- Use a semantic search approach to find matching content items.\n"
            "- Try to recommend at least one collection.\n"
            "- DO NOT recommend the book 'The French Revolution' as it is not "
            "relevant to decision-making."
        ) 

        return prompt

    def _format_blinkist_content(
        self,
        content: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Format Blinkist content into Slack blocks with image and button.

        Args:
            content: Dictionary containing content details

        Returns:
            List of Slack blocks
        """
        try:
            # Get URLs using helper methods
            url = self._get_url(content)
            image_url = self._get_image_url(content)
            
            # Get content details
            title = content.get("title", "Untitled")
            description = content.get(
                "description",
                "No description available"
            )
            
            # Log content details for debugging
            logger.info(
                "Formatting content: %s",
                {
                    "title": title,
                    "url": url,
                    "image_url": image_url,
                    "description": description
                }
            )
            
            # Create blocks for the content
            blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"{description}"
                    },
                    "accessory": {
                        "type": "image",
                        "image_url": image_url,
                        "alt_text": title
                    }
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "Read on Blinkist",
                                "emoji": True
                            },
                            "url": url,
                            "action_id": "read_on_blinkist"
                        }
                    ]
                }
            ]
            
            return blocks
            
        except Exception as e:
            logger.error("Error formatting content: %s", str(e))
            return []

    def _process_api_response(
        self,
        response: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process the API response into Slack message blocks.
        
        Args:
            response (Dict[str, Any]): Raw response from Langdock API
            
        Returns:
            Dict[str, Any]: Formatted Slack message blocks
        """
        try:
            # Extract the assistant's response from the result array
            if not response.get("result") or not response["result"]:
                raise ValueError("No response content found in API response")
            
            # Find the assistant message with valid JSON content
            content_data = None
            for message in reversed(response["result"]):
                if message.get("role") == "assistant":
                    content = message.get("content", "")
                    # Skip tool-call messages
                    if '"type": "tool-call"' in content:
                        continue
                    
                    if isinstance(content, str):
                        # Select JSON content in code blocks
                        if "```json" in content:
                            json_content = content[content.find("```json"):].strip("```json")
                            json_content = json_content[:json_content.find("```")].strip("```")
                        else:
                            json_content = content
                        
                        try:
                            # Extract the JSON content
                            parsed_content = json.loads(json_content)
                            # Validate the parsed content structure
                            if (
                                "recommendations" in parsed_content and
                                "reasoning" in parsed_content and
                                len(parsed_content["recommendations"]) > 0 and
                                all(
                                    isinstance(rec, dict) and
                                    "content_id" in rec and
                                    "content_type" in rec and
                                    "title" in rec and
                                    "slug" in rec and
                                    "description" in rec
                                    for rec in parsed_content["recommendations"]
                                )
                            ):
                                content_data = parsed_content
                                break
                        except json.JSONDecodeError:
                            continue
            
            if not content_data:
                raise ValueError(
                    "No valid recommendations found in the response"
                )
            
            # Start with header and reasoning
            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "📚 Content Recommendations",
                        "emoji": True
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"*Why These Recommendations?*\n"
                            f"{content_data['reasoning']}"
                        )
                    }
                },
                {
                    "type": "divider"
                }
            ]
            
            # Add each recommendation
            for i, rec in enumerate(content_data["recommendations"]):
                blocks.extend(self._format_blinkist_content(rec))
                if i < len(content_data["recommendations"]) - 1:
                    blocks.append({"type": "divider"})
            
            return {"blocks": blocks}
            
        except Exception as e:
            logger.error(f"Error processing API response: {str(e)}")
            return {
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": (
                                "Sorry, I couldn't process the recommendations "
                                "at this time."
                            )
                        }
                    }
                ]
            }

    def _get_image_url(self, content: Dict[str, Any]) -> str:
        """Get the image URL for a content item.
        
        Args:
            content (Dict[str, Any]): Content recommendation data
            
        Returns:
            str: Image URL for the content
        """
        content_type = content.get("content_type", "").lower()
        content_id = content.get("content_id", "")
        
        if content_type == "collection":
            return (
                f"https://images.blinkist.io/images/curated_lists/"
                f"{content_id}/1_1/470.jpg"
            )
        elif content_type == "guide":
            return (
                f"https://images.blinkist.io/images/courses/"
                f"{content_id}/cover/470.jpg"
            )
        else:  # Default to book
            return (
                f"https://images.blinkist.io/images/books/"
                f"{content_id}/1_1/470.jpg"
            )

    def _get_url(self, content: Dict[str, Any]) -> str:
        """Get the URL for a content item.
        
        Args:
            content (Dict[str, Any]): Content recommendation data
            
        Returns:
            str: URL for the content
        """
        content_type = content.get("content_type", "").lower()
        slug = content.get("slug", content.get("content_id", ""))
        
        if content_type == "collection":
            return f"https://www.blinkist.com/app/collections/{slug}"
        elif content_type == "guide":
            return f"https://www.blinkist.com/app/guides/{slug}"
        else:  # Default to book
            return f"https://www.blinkist.com/app/books/{slug}"
