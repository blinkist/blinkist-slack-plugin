"""Utilities for tracking and managing Slack channels."""
import os
import logging
from typing import List, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class ChannelTracker:
    """Class to track channels where the Slack bot is installed."""
    
    def __init__(self, app):
        """Initialize the ChannelTracker.
        
        Args:
            app: The Slack app instance
        """
        self.app = app
        self.channels_data = []
    
    def update_installed_channels(self) -> None:
        """Update the list of channels where the bot is installed.
        
        This method:
        1. Fetches all public channels
        2. Filters for channels where the bot is a member
        3. Stores the channel IDs as an environment variable
        """
        try:
            # Get all public channels
            channels = self._fetch_public_channels()
            
            # Filter for channels where bot is a member
            installed_channels = [
                channel["id"] for channel in channels 
                if channel.get("is_member", False)
            ]
            
            # Store as environment variable
            os.environ["INSTALLED_CHANNELS"] = ",".join(installed_channels)
            
            logger.info(
                f"Updated installed channels list. "
                f"Bot is installed in {len(installed_channels)} channels"
            )
            
        except Exception as e:
            logger.error(f"Error updating installed channels: {str(e)}")
    
    def _fetch_public_channels(self) -> List[Dict[str, Any]]:
        """Fetch all public channels from the Slack workspace.
        
        Returns:
            List[Dict[str, Any]]: List of public channel objects
        """
        try:
            all_channels = []
            cursor = None
            
            while True:
                # Prepare parameters for the API call
                params = {
                    "types": ["public_channel"],
                    "exclude_archived": True,
                    "limit": 100  # Maximum allowed by Slack API
                }
                
                # Add cursor if we have one
                if cursor:
                    params["cursor"] = cursor
                
                response = self.app.client.conversations_list(**params)
                
                if not response["ok"]:
                    logger.error(f"Failed to fetch channels: {response['error']}")
                    return all_channels
                
                # Add channels from this page
                all_channels.extend(response["channels"])
                
                # Check if there are more pages
                if not response.get("response_metadata", {}).get("next_cursor"):
                    break
                    
                # Get cursor for next page
                cursor = response["response_metadata"]["next_cursor"]
            
            logger.info(f"Fetched {len(all_channels)} public channels")
            return all_channels
            
        except Exception as e:
            logger.error(f"Error fetching public channels: {str(e)}")
            return []
    
    @staticmethod
    def get_installed_channels() -> List[str]:
        """Get the list of channels where the bot is installed.
        
        Returns:
            List[str]: List of channel IDs where the bot is installed
        """
        channels_str = os.environ.get("INSTALLED_CHANNELS", "")
        return channels_str.split(",") if channels_str else [] 