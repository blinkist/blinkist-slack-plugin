import os
import logging
import pytz
import httpx
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from slack_sdk.web.async_client import AsyncWebClient

CHANNEL = "#blinkist-pulse-daily"
TIMEZONE = os.getenv("TIMEZONE", "Europe/Berlin")
LANGDOCK_API_URL = "https://api.langdock.com/v1/assistants/4293ff67-7204-4936-aca2-b82f058099e9"

logger = logging.getLogger("daily_pulse")

def get_cet_now():
    tz = pytz.timezone(TIMEZONE)
    return datetime.now(tz)

async def fetch_langdock_recommendation():
    api_key = os.getenv("LANGDOCK_API_KEY")
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {"message": "recommend something"}
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(LANGDOCK_API_URL, headers=headers, json=payload)
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.error(f"Langdock API error (attempt {attempt+1}): {e}")
    return None

def build_slack_blocks(data):
    deeplink = f"https://www.blinkist.com/en/app/books/{data['content_slug']}"
    image_url = f"https://images.blinkist.io/images/books/{data['content_id']}/1_1/470.jpg"
    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": "🌟 *Daily Blinkist Pulse* 📚"}},
        {"type": "divider"},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*{data['message_title']}*"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": data['message']}},
        {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": f"📖 *Book*: {data['content_title']}"},
                {"type": "mrkdwn", "text": f"✍️ *Author*: {data['content_author']}"}
            ]
        },
        {
            "type": "image",
            "image_url": image_url,
            "alt_text": data['content_title']
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Read on Blinkist"},
                    "url": deeplink,
                    "style": "primary"
                }
            ]
        }
    ]

async def post_daily_pulse():
    slack_token = os.getenv("SLACK_BOT_TOKEN")
    client = AsyncWebClient(token=slack_token)
    data = await fetch_langdock_recommendation()
    if not data:
        logger.error("Failed to fetch daily recommendation from Langdock.")
        return
    try:
        blocks = build_slack_blocks(data)
        await client.chat_postMessage(channel=CHANNEL, blocks=blocks, text="Daily Blinkist Pulse")
        logger.info("Posted daily Blinkist Pulse to Slack.")
    except Exception as e:
        logger.error(f"Slack API error: {e}")

def start_daily_pulse_scheduler():
    scheduler = AsyncIOScheduler(timezone=pytz.timezone(TIMEZONE))
    scheduler.add_job(post_daily_pulse, "cron", hour=9, minute=0)
    scheduler.start()
    logger.info("Daily Blinkist Pulse scheduler started.") 