from typing import List, Dict, Any
import logging
import pandas as pd
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class ReportMetrics:
    """Class to handle fetching and processing Slack channel metrics."""
 
    def __init__(self, app, channel_tracker):
        """Initialize the ReportMetrics class.

        Args:
            app: The Slack app instance
            channel_tracker: channel tracker instance
        """
        self.app = app
        self.channel_tracker = channel_tracker
        self.channels_data = []

    def generate_report(self, days: int = 30) -> str:
        """Generate a complete report of channel metrics.
        
        Args:
            days (int, optional): Number of days to look back. Defaults to 30.
            
        Returns:
            str: Formatted report message for Slack
        """
        self.days = days

        try:
            # Get the raw message data
            df = self._process_channel_data()

            if df.empty:
                logger.info("No messages found in the specified time period")
                return "No messages found in the specified time period"
                
            # Compute metrics
            metrics = self._compute_message_counts(df)
            
            logger.info(
                f"Successfully computed metrics for {len(metrics)} channels"
            )
            
            # Format and return the Slack message
            return self._format_slack_message(metrics)
            
        except Exception as e:
            logger.error(f"Error generating report: {str(e)}")
            return "Sorry, there was an error generating the report"

    def _format_slack_message(
        self, 
        metrics: Dict[str, Dict[str, int]]
    ) -> Dict[str, Any]:
        """Format the metrics into a Slack message using Block Kit.
        
        Args:
            metrics (Dict[str, Dict[str, int]]): Dictionary mapping channel names to
                their respective subtype counts
            
        Returns:
            Dict[str, Any]: Slack message JSON payload with blocks
        """
        # Initialize blocks list
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"📊 Channel Pulse Report (Last {self.days} days)",
                    "emoji": True
                }
            },
            {
                "type": "divider"
            }
        ]
        
        for channel_name, counts in metrics.items():
            # Add channel header
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*#{channel_name}*"
                }
            })
            
            # Sort subtypes by count (descending)
            sorted_counts = sorted(
                counts.items(),
                key=lambda x: x[1],
                reverse=True
            )
            
            # Add message counts
            for subtype, count in sorted_counts:
                display_subtype = subtype.replace('_', ' ').title()
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"• {display_subtype}: {count}"
                    }
                })
            
            # Add divider between channels
            blocks.append({"type": "divider"})
        
        return {
            "blocks": blocks,
            "response_type": "ephemeral"
        }

    def _process_channel_data(self) -> pd.DataFrame:
        """Process all public channel message data and create a DataFrame.
        
        Returns:
            pd.DataFrame: DataFrame containing channel_id, channel_name, timestamp,
                         message data, message type and subtype
        """
        # Get list of channels where bot is installed
        installed_channels = self.channel_tracker.get_installed_channels()
        if not installed_channels:
            logger.warning("No installed channels found")
            return pd.DataFrame()
        
        all_messages = []
        
        for channel_id in installed_channels:
            try:
                # Get channel info
                channel_info = self.app.client.conversations_info(channel=channel_id)
                if not channel_info["ok"]:
                    logger.error(
                        f"Failed to get info for channel {channel_id}: "
                        f"{channel_info['error']}"
                    )
                    continue
                    
                channel_name = channel_info["channel"]["name"]
                
                # Add messages from this page
                messages = self._fetch_channel_history(channel_id)
         
                for message in messages:
                    all_messages.append({
                        "channel_id": channel_id,
                        "channel_name": channel_name,
                        "ts": message.get("ts"),
                        "message": message.get("text", ""),
                        "type": message.get("type", "message"),  # Default to "message" if not specified
                        "subtype": message.get("subtype", "message")  # Default string if no subtype
                    })
            
            except Exception as e:
                logger.error(
                    f"Error processing channel {channel_id}: {str(e)}"
                )
                continue
        
        # Create DataFrame
        df = pd.DataFrame(all_messages)
        
        # Convert timestamp to datetime
        if not df.empty:
            df["ts"] = pd.to_datetime(df["ts"].astype(float), unit="s")
            
        return df
        
    def _fetch_channel_history(self, channel_id: str) -> List[Dict[str, Any]]:
        """Fetch conversation history for a specific channel.
        
        Args:
            channel_id (str): The ID of the channel to fetch history from
            
        Returns:
            List[Dict[str, Any]]: List of all messages from the channel
        """
        try:
            all_messages = []
            cursor = None
            
            # Calculate oldest timestamp (days ago)
            oldest_ts = int((datetime.now() - timedelta(days=self.days)).timestamp())
            logger.info(f"Fetching messages from {self.days} days ago")
            
            while True:
                # Prepare parameters for the API call
                params = {
                    "channel": channel_id,
                    "inclusive": True,
                    "limit": 200,
                    "oldest": str(oldest_ts)
                }
                
                # Add latest timestamp if we have one
                if "latest" in locals():
                    params["latest"] = latest
                
                # Add cursor if we have one
                if cursor:
                    params["cursor"] = cursor
                
                response = self.app.client.conversations_history(**params)
                
                if not response["ok"]:
                    error_msg = (
                        f"Failed to fetch history for channel {channel_id}: "
                        f"{response['error']}"
                    )
                    logger.error(error_msg)
                    return all_messages
                
                # Add messages from this page
                messages = response["messages"]
                all_messages.extend(messages)
                
                # Check if there are more pages
                if not response.get("has_more", False):
                    break
                
                # Get the timestamp of the last message for time-based pagination
                if messages:
                    last_message = messages[-1]
                    latest = last_message["ts"]
                
                # Get cursor for next page if available
                cursor = response.get("response_metadata", {}).get("next_cursor")
                if not cursor:
                    break
            
            logger.info(
                f"Fetched {len(all_messages)} messages from channel {channel_id} "
                f"in the last {self.days} days"
            )
            return all_messages
            
        except Exception as e:
            logger.error(
                f"Error fetching history for channel {channel_id}: {str(e)}"
            )
            return []

    def _compute_message_counts(self, df: pd.DataFrame) -> Dict[str, Dict[str, int]]:
        """Compute message counts by subtype for each channel.
        
        Args:
            df (pd.DataFrame): DataFrame containing message data
            
        Returns:
            Dict[str, Dict[str, int]]: Dictionary mapping channel_id to 
                dictionary of subtype counts
        """
        try:
            # Group by channel and subtype, then count messages
            counts = df.groupby(['channel_name', 'subtype']).size().reset_index(name='count')
            
            # Convert to nested dictionary format
            result = {}
            for _, row in counts.iterrows():
                channel_name = row['channel_name']
                subtype = row['subtype']
                count = row['count']
                
                if channel_name not in result:
                    result[channel_name] = {}
                result[channel_name][subtype] = count
                
            return result
            
        except Exception as e:
            logger.error(f"Error computing message counts: {str(e)}")
            return {}
 