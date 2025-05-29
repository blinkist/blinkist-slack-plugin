import os
import logging
import pytz
import httpx
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from slack_sdk.web.async_client import AsyncWebClient
import asyncio
import threading
import json

CHANNEL = "#blinkist-pulse-daily"
TIMEZONE = os.getenv("TIMEZONE", "Europe/Berlin")
LANGDOCK_API_URL = "https://api.langdock.com/assistant/v1/chat/completions"
ASSISTANT_ID = "4293ff67-7204-4936-aca2-b82f058099e9"

logger = logging.getLogger("daily_pulse")

def get_cet_now():
    tz = pytz.timezone(TIMEZONE)
    return datetime.now(tz)

async def fetch_langdock_recommendation():
    """Fetch daily recommendation from Langdock API."""
    api_key = os.getenv("LANGDOCK_API_KEY")
    if not api_key:
        logger.error("LANGDOCK_API_KEY not found in environment variables")
        return None

    headers = {
        "Authorization": f"{api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "assistantId": ASSISTANT_ID,
        "messages": [
            {
                "role": "user",
                "content": (
                    "Generate a daily Blinkist book recommendation with insights "
                    "for a professional team. Include the book title, author, "
                    "key insight, and a practical daily tip."
                )
            }
        ],
        "output": {
            "type": "enum",
            "enum": ["<string>"],
            "schema": {}
        }
    }

    logger.info(f"Making request to: {LANGDOCK_API_URL}")
    logger.info(f"Using assistant ID: {ASSISTANT_ID}")
    logger.info(f"Payload: {payload}")

    async with httpx.AsyncClient() as client:
        try:
            logger.info("Attempting Langdock API call")
            response = await client.post(
                LANGDOCK_API_URL,
                headers=headers,
                json=payload,
                timeout=30.0
            )
            
            logger.info(f"Response status: {response.status_code}")
            logger.info(f"Response headers: {dict(response.headers)}")
            logger.info(f"Response text: {response.text}")
            
            if response.status_code == 200:
                data = response.json()
                logger.info("Successfully fetched recommendation from Langdock")
                return data
            else:
                logger.error(f"Langdock API error: {response.status_code} - {response.text}")
                return None
                
        except httpx.TimeoutException as e:
            logger.error(f"Langdock API timeout: {e}")
            return None
        except httpx.RequestError as e:
            logger.error(f"Langdock API request error: {e}")
            return None
        except Exception as e:
            logger.error(f"Langdock API unexpected error: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None

def build_slack_blocks(data):
    """Build Slack blocks from Langdock API response."""
    try:
        # Find the final assistant response with JSON
        assistant_content = None
        for message in reversed(data.get("result", [])):
            if message.get("role") == "assistant" and isinstance(message.get("content"), str):
                content = message["content"]
                if content.startswith("```json") and content.endswith("```"):
                    # Extract JSON from code block
                    assistant_content = content.replace("```json\n", "").replace("\n```", "")
                    break
                elif content.startswith("{") and content.endswith("}"):
                    # Direct JSON response
                    assistant_content = content
                    break
        
        if not assistant_content:
            raise ValueError("No JSON content found in response")
        
        # Parse the JSON
        import json
        parsed_data = json.loads(assistant_content)
        
        # Extract fields from the API response
        message_title = parsed_data.get("message_title", "Daily Insight")
        message = parsed_data.get("message", "")
        content_title = parsed_data.get("content_title", "Unknown Book")
        content_author = parsed_data.get("content_author", "Unknown Author")
        content_slug = parsed_data.get("content_slug", "")
        content_id = parsed_data.get("content_id", "")
        
        # Create the deeplink URL
        deeplink_url = f"https://www.blinkist.com/app/books/{content_slug}" if content_slug else "https://www.blinkist.com"
        
        # Create the image URL using content_id
        image_url = f"https://images.blinkist.io/images/books/{content_id}/1_1/470.jpg" if content_id else "https://images.blinkist.io/images/books/53a195b66335360007300000/1_1/470.jpg"
        
        # Create blocks with image and text
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"🌟 *Daily Blinkist Pulse* 📚\n\n**{message_title}**\n\n{message}\n\n📖 **Book**: {content_title}\n✍️ **Author**: {content_author}"
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
                            "text": "Read on Blinkist",
                            "emoji": True
                        },
                        "url": deeplink_url,
                        "action_id": "read_on_blinkist"
                    }
                ]
            }
        ]
        
        return blocks
        
    except Exception as e:
        logger.error(f"Error building Slack blocks: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        # Return a simple fallback block
        return [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "🌟 *Daily Blinkist Pulse* 📚\n\nSorry, there was an issue formatting today's recommendation."
                }
            }
        ]

async def post_daily_pulse():
    logger.info("=== DAILY PULSE JOB TRIGGERED ===")
    try:
        slack_token = os.getenv("SLACK_BOT_TOKEN")
        if not slack_token:
            logger.error("SLACK_BOT_TOKEN not found in environment")
            return
            
        logger.info("Creating Slack client...")
        client = AsyncWebClient(token=slack_token)
        
        logger.info("Fetching recommendation from Langdock...")
        data = await fetch_langdock_recommendation()
        
        if not data:
            logger.error("Failed to fetch daily recommendation from Langdock.")
            return
            
        logger.info(f"Successfully fetched data from Langdock: {data}")
        
        logger.info("Building Slack blocks...")
        blocks = build_slack_blocks(data)
        
        logger.info(f"Posting message to channel: {CHANNEL}")
        await client.chat_postMessage(
            channel=CHANNEL, 
            blocks=blocks, 
            text="Daily Blinkist Pulse"
        )
        logger.info("Successfully posted daily Blinkist Pulse to Slack.")
        
    except Exception as e:
        logger.error(f"Error in post_daily_pulse: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")

def start_daily_pulse_scheduler():
    import asyncio
    import threading
    
    logger.info("=== STARTING DAILY PULSE SCHEDULER ===")
    
    def run_scheduler():
        logger.info("Daily pulse scheduler thread started")
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            logger.info("Created new event loop for daily pulse scheduler")
            
            # Trigger first pulse immediately
            logger.info("Triggering first daily pulse immediately...")
            loop.run_until_complete(post_daily_pulse())
            
            scheduler = AsyncIOScheduler(timezone=pytz.timezone(TIMEZONE))
            logger.info(f"Created AsyncIOScheduler with timezone: {TIMEZONE}")
            
            # Schedule every 30 minutes for subsequent runs
            scheduler.add_job(post_daily_pulse, "interval", minutes=30)
            logger.info("Added daily pulse job to scheduler (every 30 minutes)")
            
            scheduler.start()
            logger.info("AsyncIOScheduler started successfully")
            
            loop.run_forever()
            
        except Exception as e:
            logger.error(f"Error in daily pulse scheduler thread: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
    
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    logger.info("Daily pulse scheduler thread started successfully") 