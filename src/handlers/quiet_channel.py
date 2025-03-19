import time
import json
import random
import logging
import os
from datetime import datetime
from config.settings import Settings

class QuietChannelHandler:
    def __init__(self, app):
        self.app = app
        self.last_message_times = {}
        self.last_nudge_times = {}
        self.logger = logging.getLogger(__name__)
        
        # Load data jokes
        try:
            with open('src/data/jokes.json', 'r') as f:
                self.jokes = json.load(f)
            self.logger.info(f"Loaded {len(self.jokes)} jokes for quiet channel nudges")
        except Exception as e:
            self.logger.error(f"Error loading jokes: {e}")
            self.jokes = ["Why don't scientists trust atoms? Because they make up everything!"]
        
        # Initialize by getting all channels the bot is in
        self._refresh_monitored_channels()
    
    def _refresh_monitored_channels(self):
        """Get all channels the bot is a member of"""
        try:
            result = self.app.client.conversations_list(
                types="public_channel,private_channel",
                exclude_archived=True
            )
            
            if not result["ok"]:
                self.logger.error(f"Error listing channels: {result.get('error', 'unknown error')}")
                return
            
            # Filter to only include channels where the bot is a member
            channels = [c["id"] for c in result["channels"] if c.get("is_member", False)]
            
            # Initialize timers for any new channels
            for channel in channels:
                if channel not in self.last_message_times:
                    self.last_message_times[channel] = 0
                    self.last_nudge_times[channel] = 0
                    self.logger.info(f"Added new channel {channel} to monitoring")
            
            self.logger.info(f"Bot is monitoring {len(channels)} channels")
            
        except Exception as e:
            self.logger.error(f"Error refreshing monitored channels: {e}")
    
    def reset_timer(self, channel):
        """Reset the quiet timer for a channel"""
        current_time = time.time()
        self.last_message_times[channel] = current_time
        self.logger.debug(f"Reset quiet timer for channel {channel}")
        
        # Calculate when the next check should happen
        next_check_time = current_time + (float(os.environ.get("QUIET_THRESHOLD_HOURS", "4")) * 3600)
        next_check_datetime = datetime.fromtimestamp(next_check_time)
        self.logger.info(f"Channel {channel} activity detected. Next quiet check scheduled for {next_check_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
    
    def check_channels(self):
        """Check all monitored channels for inactivity"""
        self.logger.info("Checking monitored channels for inactivity")
        
        # Refresh the list of channels to ensure we're monitoring all current channels
        self._refresh_monitored_channels()
        
        if not self._is_working_hours():
            self.logger.info("Outside of working hours, skipping quiet channel check")
            return
            
        current_time = time.time()
        quiet_threshold_hours = float(os.environ.get("QUIET_THRESHOLD_HOURS", "4"))
        
        for channel, last_message_time in self.last_message_times.items():
            last_nudge_time = self.last_nudge_times.get(channel, 0)
            
            hours_since_message = (current_time - last_message_time) / 3600
            hours_since_nudge = (current_time - last_nudge_time) / 3600
            
            self.logger.debug(f"Channel {channel}: {hours_since_message:.1f} hours since last message, {hours_since_nudge:.1f} hours since last nudge")
            
            # Send nudge if channel is quiet and we haven't sent one recently
            if (hours_since_message >= quiet_threshold_hours and 
                hours_since_nudge >= quiet_threshold_hours):
                self.logger.info(f"Channel {channel} is quiet ({hours_since_message:.1f} hours). Sending nudge.")
                self.send_nudge(channel)
                self.last_nudge_times[channel] = current_time
            else:
                self.logger.debug(f"Channel {channel} doesn't need a nudge yet")
    
    def _is_working_hours(self):
        """Check if current time is within working hours"""
        # Get working hours from environment variables
        start_hour = int(os.environ.get("WORKING_HOURS_START", "9"))
        end_hour = int(os.environ.get("WORKING_HOURS_END", "17"))
        
        # For testing, you can uncomment this to always return True
        # return True
        
        now = datetime.now()
        return (
            now.weekday() < 5 and  # Monday to Friday
            start_hour <= now.hour < end_hour  # Within specified hours
        )
    
    def send_nudge(self, channel):
        """Send a nudge message with a random data joke"""
        joke = random.choice(self.jokes)
        message = (
            ":wave: *It's been pretty quiet in here!*\n\n"
            "Why not start a conversation? Here's a data joke to break the ice:\n"
            f"_{joke}_"
        )
        
        try:
            self.logger.info(f"Sending quiet channel nudge to channel {channel}")
            self.app.client.chat_postMessage(
                channel=channel,
                text=message,
                unfurl_links=False
            )
            self.logger.info("Nudge sent successfully")
        except Exception as e:
            self.logger.error(f"Error sending nudge to channel {channel}: {e}") 