import time
import json
import random
from datetime import datetime
from config.settings import Settings

class QuietChannelHandler:
    def __init__(self, app):
        self.app = app
        self.last_message_times = {}
        self.last_nudge_times = {}
        
        # Load data jokes
        with open('src/data/jokes.json', 'r') as f:
            self.jokes = json.load(f)
    
    def reset_timer(self, channel):
        """Reset the quiet timer for a channel"""
        self.last_message_times[channel] = time.time()
        
    def check_channels(self):
        """Check all monitored channels for inactivity"""
        if not Settings.is_working_hours():
            return
            
        current_time = time.time()
        
        for channel in Settings.MONITORED_CHANNELS:
            last_message_time = self.last_message_times.get(channel, 0)
            last_nudge_time = self.last_nudge_times.get(channel, 0)
            
            hours_since_message = (current_time - last_message_time) / 3600
            hours_since_nudge = (current_time - last_nudge_time) / 3600
            
            # Send nudge if channel is quiet and we haven't sent one recently
            if (hours_since_message >= Settings.QUIET_THRESHOLD_HOURS and 
                hours_since_nudge >= Settings.QUIET_THRESHOLD_HOURS):
                self.send_nudge(channel)
                self.last_nudge_times[channel] = current_time
    
    def send_nudge(self, channel):
        """Send a nudge message with a random data joke"""
        joke = random.choice(self.jokes)
        message = (
            ":wave: *It's been pretty quiet in here!*\n\n"
            "Why not start a conversation? Here's a data joke to break the ice:\n"
            f"_{joke}_"
        )
        
        try:
            self.app.client.chat_postMessage(
                channel=channel,
                text=message,
                unfurl_links=False
            )
        except Exception as e:
            print(f"Error sending nudge: {e}") 