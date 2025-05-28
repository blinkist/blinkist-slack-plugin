"""Content recommender using Langdock assistant API."""
import os
import logging
import requests
import json
from typing import Dict, Any


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
        self.api_key = os.environ.get("LANGDOCK_API_KEY", "")
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
        strengths: str = None,
        improvements: str = None,
        prompt: str = None
    ) -> Dict[str, Any]:
        """Generate content recommendations based on input.
        
        Args:
            channel_name (str, optional): Name of the channel
            strengths (str, optional): Decision-making strengths
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
            elif all([channel_name, strengths, improvements]):
                final_prompt = self._create_prompt(
                    channel_name, strengths, improvements
                )
            else:
                raise ValueError(
                    "Either provide a direct prompt or all channel insights"
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
                    "type": "enum",
                    "enum": ["<string>"],
                    "schema": {}
                }
            }
            
            # Send request to API
            response = requests.request(
                "POST",
                self.api_url,
                json=payload,
                headers=self.headers,
                timeout=30
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
                headers=self.headers,
                timeout=10
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
        strengths: str,
        improvements: str
    ) -> str:
        """Create a prompt for channel-specific recommendations.
        
        Args:
            channel_name (str): Name of the channel
            strengths (str): Decision-making strengths identified for the channel
            improvements (str): Areas for improvement identified for the channel
            
        Returns:
            str: Formatted prompt for the Langdock API
        """
        prompt = (
            f"Based on the decision-making analysis for channel #{channel_name}, "
            "provide up to 5 content recommendations that would help the team "
            "enhance their decision-making effectiveness.\n\n"
            f"Context:\n"
            f"- Current Strengths: {strengths}\n"
            f"- Areas for Improvement: {improvements}\n\n"
            "Provide an overall reasoning for your content recommendations:\n"
            "- Why is this particular combination of content valuable for "
            "enhancing decision-making efficiency?\n"
            "- How can the team best leverage these resources together?\n\n"
            "OUTPUT FORMAT:\n"
            "Respond in JSON format with:\n"
            "{\n"
            '    "recommendations": [\n'
            "        {\n"
            '            "content_id": "unique identifier",\n'
            '            "content_type": "book/collection",\n'
            '            "title": "content title",\n'
            '            "slug": "url-friendly-identifier"\n'
            "        },\n"
            "        ...\n"
            "    ],\n"
            '    "reasoning": "Brief rationale for content recommendations"\n'
            "}\n\n"
            "Focus especially on content that addresses the areas for "
            "improvement while building upon existing strengths. Prioritize "
            "practical, actionable content that can be immediately applied to "
            "improve decision-making processes."
        )
        
        return prompt

    def _format_blinkist_content(
        self,
        content: Dict[str, Any],
        index: int
    ) -> Dict[str, Any]:
        """Format a single Blinkist content recommendation into Slack blocks.
        
        Args:
            content (Dict[str, Any]): Content recommendation data
            index (int): Index of the recommendation
            
        Returns:
            Dict[str, Any]: Formatted Slack blocks for the content
        """
        try:
            # Extract content details
            content_title = content.get("title", f"Recommendation {index+1}")
            content_type = content.get("content_type", "").lower()
            content_id = content.get("content_id", "")
            slug = content.get("slug", content_id)
            
            # Log the content details
            logger.info(
                f"Processing recommendation {index+1}: {content_title}"
            )
            logger.info(
                f"Content type: {content_type}, Content ID: {content_id}"
            )
            
            # Determine URL and image URL based on content type
            if content_type == "collection":
                url = f"https://www.blinkist.com/app/collections/{slug}"
                image_url = (
                    f"https://images.blinkist.io/images/curated_lists/"
                    f"{content_id}/1_1/470.jpg"
                )
            elif content_type == "guide":
                url = f"https://www.blinkist.com/app/guides/{slug}"
                image_url = (
                    f"https://images.blinkist.io/images/courses/"
                    f"{content_id}/cover/470.jpg"
                )
            else:  # Default to book
                url = f"https://www.blinkist.com/app/books/{slug}"
                image_url = (
                    f"https://images.blinkist.io/images/books/"
                    f"{content_id}/cover/470.jpg"
                )
            
            logger.info(f"URL: {url}")
            logger.info(f"Image URL: {image_url}")
            
            # Create blocks for the content
            return [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*{content_title}*"
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
                            "action_id": f"view_content_{index}"
                        }
                    ]
                }
            ]
            
        except Exception as e:
            logger.error(f"Error formatting content {index+1}: {str(e)}")
            # Return a simple text block as fallback
            return [{
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{content_title}*\n<{url}|View Content>"
                }
            }]

    def _process_api_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
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
            
            # Find the last assistant message with valid JSON content
            content_data = None
            for message in reversed(response["result"]):
                if message.get("role") == "assistant":
                    content = message.get("content", "")
                    if isinstance(content, str):
                        try:
                            parsed_content = json.loads(content)
                            if (
                                isinstance(parsed_content, dict) and
                                "recommendations" in parsed_content and
                                "reasoning" in parsed_content
                            ):
                                content_data = parsed_content
                                break
                        except json.JSONDecodeError:
                            continue
            
            if not content_data:
                raise ValueError("No valid JSON response found with recommendations")
            
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
                blocks.extend(self._format_blinkist_content(rec, i))
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
                            "text": "Error processing recommendations"
                        }
                    }
                ]
            }
