import os
import logging
import pytz
import httpx
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from slack_sdk.web.async_client import AsyncWebClient
import asyncio
import threading
import json

CHANNEL = "#blinkist-pulse-daily"
TIMEZONE = os.getenv("TIMEZONE", "Europe/Berlin")
LANGDOCK_API_URL = "https://api.langdock.com/assistant/v1/chat/completions"
ASSISTANT_ID = "4293ff67-7204-4936-aca2-b82f058099e9"
HISTORY_FILE = "daily_pulse_history.json"

logger = logging.getLogger("daily_pulse")

def get_cet_now():
    tz = pytz.timezone(TIMEZONE)
    return datetime.now(tz)

def load_history():
    """Load the history of past recommendations."""
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, 'r') as f:
                history = json.load(f)
                logger.info(f"Loaded history with {len(history)} entries")
                return history
        else:
            logger.info("No history file found, starting fresh")
            return []
    except Exception as e:
        logger.error(f"Error loading history: {e}")
        return []

def save_history(history):
    """Save the history of recommendations."""
    try:
        with open(HISTORY_FILE, 'w') as f:
            json.dump(history, f, indent=2)
        logger.info(f"Saved history with {len(history)} entries")
    except Exception as e:
        logger.error(f"Error saving history: {e}")

def clean_old_history(history, days=30):
    """Remove entries older than specified days."""
    cutoff_date = datetime.now() - timedelta(days=days)
    
    cleaned_history = []
    for entry in history:
        try:
            entry_date = datetime.fromisoformat(entry['date'])
            if entry_date > cutoff_date:
                cleaned_history.append(entry)
        except (KeyError, ValueError) as e:
            logger.warning(f"Invalid history entry: {entry}, error: {e}")
    
    logger.info(f"Cleaned history: {len(history)} -> {len(cleaned_history)} entries")
    return cleaned_history

def get_exclusions():
    """Get excluded news topics and books from history."""
    history = load_history()
    history = clean_old_history(history)
    
    excluded_news_topics = []
    excluded_books = []
    
    for entry in history:
        if 'news_topic' in entry and entry['news_topic']:
            excluded_news_topics.append(entry['news_topic'])
        if 'content_id' in entry and entry['content_id']:
            excluded_books.append(entry['content_id'])
    
    logger.info(f"Exclusions - News topics: {len(excluded_news_topics)}, Books: {len(excluded_books)}")
    return excluded_news_topics, excluded_books

def save_recommendation(news_topic, content_id):
    """Save a new recommendation to history."""
    history = load_history()
    history = clean_old_history(history)
    
    new_entry = {
        'date': datetime.now().isoformat(),
        'news_topic': news_topic,
        'content_id': content_id
    }
    
    history.append(new_entry)
    save_history(history)
    logger.info(f"Saved new recommendation: {news_topic} -> {content_id}")

async def fetch_langdock_recommendation():
    """Fetch daily recommendation from Langdock API."""
    api_key = os.getenv("LANGDOCK_API_KEY")
    if not api_key:
        logger.error("LANGDOCK_API_KEY not found in environment variables")
        return None

    # Get exclusions from history
    excluded_news_topics, excluded_books = get_exclusions()

    headers = {
        "Authorization": f"{api_key}",
        "Content-Type": "application/json"
    }
    
    # Build the base prompt with exclusions included
    base_prompt = "Recommend"
    
    # Add exclusions to the base prompt
    if excluded_news_topics or excluded_books:
        base_prompt += "\n\nIMPORTANT EXCLUSIONS:"
        if excluded_news_topics:
            base_prompt += f"\nExcluded news topics (do not use): {excluded_news_topics}"
        if excluded_books:
            base_prompt += f"\nExcluded book content IDs (do not recommend): {excluded_books}"
    
    payload = {
        "assistantId": ASSISTANT_ID,
        "messages": [
            {
                "role": "user",
                "content": base_prompt
            }
        ],
        "output": {
            "type": "enum",
            "enum": ["<string>"],
            "schema": {}
        }
    }

    logger.info(f"Making request with {len(excluded_news_topics)} excluded news topics and {len(excluded_books)} excluded books")
    logger.info(f"Base prompt: {base_prompt}")
    logger.info(f"Full request URL: {LANGDOCK_API_URL}")
    logger.info(f"Full request headers: {headers}")
    logger.info(f"Full request payload: {json.dumps(payload, indent=2)}")

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
                
        except Exception as e:
            logger.error(f"Langdock API error: {e}")
            return None

def build_slack_blocks(data):
    """Build Slack blocks from Langdock API response."""
    try:
        # Log the full response to see what we're getting
        logger.info(f"Full API response data: {data}")
        
        # Find the final assistant response with JSON
        assistant_content = None
        for message in reversed(data.get("result", [])):
            if message.get("role") == "assistant" and isinstance(message.get("content"), str):
                content = message["content"]
                logger.info(f"Assistant content: {content}")
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
        
        logger.info(f"Extracted assistant content: {assistant_content}")
        
        # Parse the JSON
        import json
        parsed_data = json.loads(assistant_content)
        logger.info(f"Parsed data: {parsed_data}")
        
        # Extract fields from the API response - NO FALLBACKS
        message_title = parsed_data.get("message_title")
        message = parsed_data.get("message")
        content_title = parsed_data.get("content_title")
        content_author = parsed_data.get("content_author")
        content_slug = parsed_data.get("content_slug")
        content_id = parsed_data.get("content_id")
        
        # Validate required fields
        if not message_title:
            raise ValueError("Missing required field: message_title")
        if not message:
            raise ValueError("Missing required field: message")
        if not content_title:
            raise ValueError("Missing required field: content_title")
        if not content_author:
            raise ValueError("Missing required field: content_author")
        if not content_id:
            raise ValueError("Missing required field: content_id")
        
        logger.info(f"Extracted fields - title: {content_title}, author: {content_author}, id: {content_id}, slug: {content_slug}")
        
        # Create the deeplink URL
        if content_slug:
            deeplink_url = f"https://www.blinkist.com/app/books/{content_slug}"
        else:
            raise ValueError("Missing required field: content_slug")
        
        # Create the image URL using content_id
        image_url = f"https://images.blinkist.io/images/books/{content_id}/1_1/470.jpg"
        
        logger.info(f"Using image URL: {image_url}")
        logger.info(f"Using deeplink URL: {deeplink_url}")
        
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
        # Return error block instead of fallback
        return [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"❌ *Daily Blinkist Pulse Error*\n\nFailed to process recommendation: {str(e)}"
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
            # Post error message to Slack
            await client.chat_postMessage(
                channel=CHANNEL,
                text="❌ Daily Blinkist Pulse failed: Could not fetch recommendation from Langdock API"
            )
            return
            
        logger.info(f"Successfully fetched data from Langdock: {data}")
        
        logger.info("Building Slack blocks...")
        blocks = build_slack_blocks(data)
        
        # Extract news topic and content ID for history
        try:
            # Parse the response to get news_topic and content_id
            for message in reversed(data.get("result", [])):
                if message.get("role") == "assistant" and isinstance(message.get("content"), str):
                    content = message["content"]
                    if content.startswith("```json") and content.endswith("```"):
                        assistant_content = content.replace("```json\n", "").replace("\n```", "")
                    elif content.startswith("{") and content.endswith("}"):
                        assistant_content = content
                    else:
                        continue
                    
                    parsed_data = json.loads(assistant_content)
                    news_topic = parsed_data.get("news_topic", "")
                    content_id = parsed_data.get("content_id", "")
                    
                    if news_topic and content_id:
                        save_recommendation(news_topic, content_id)
                        logger.info(f"Saved recommendation to history: {news_topic} -> {content_id}")
                    break
        except Exception as e:
            logger.warning(f"Could not save recommendation to history: {e}")
        
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
        
        # Post error to Slack
        try:
            slack_token = os.getenv("SLACK_BOT_TOKEN")
            if slack_token:
                client = AsyncWebClient(token=slack_token)
                await client.chat_postMessage(
                    channel=CHANNEL,
                    text=f"❌ Daily Blinkist Pulse failed: {str(e)}"
                )
        except Exception as slack_error:
            logger.error(f"Failed to post error to Slack: {slack_error}")

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
            scheduler.add_job(post_daily_pulse, "interval", minutes=60)
            logger.info("Added daily pulse job to scheduler (every 60 minutes)")
            
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