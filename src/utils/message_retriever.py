"""Utilities for retrieving and processing Slack messages."""
import logging
from typing import List, Dict, Any
import pandas as pd
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class MessageRetriever:
    """Class to handle fetching and processing Slack messages."""

    def __init__(self, app, channel_tracker):
        """Initialize the MessageRetriever.

        Args:
            app: The Slack app instance
            channel_tracker: Instance of ChannelTracker to get installed channels
        """
        self.app = app
        self.channel_tracker = channel_tracker

    def get_channel_messages(
        self, 
        days: int = 30, 
        channel_id_list: List[str] = None
    ) -> pd.DataFrame:
        """Get messages from specified channels for the given time period.

        Args:
            days (int, optional): Number of days to look back. Defaults to 30.
            channel_id_list (List[str], optional): List of channel IDs to fetch 
                messages from. If None, fetches from all installed channels.

        Returns:
            pd.DataFrame: DataFrame containing message data with columns:
                - channel_id: ID of the channel
                - channel_name: Name of the channel
                - ts: Timestamp of the message as datetime
                - ts_str: Original timestamp string from Slack
                - message: Text content of the message
                - type: Type of the message (e.g., "message")
                - subtype: Subtype of the message (e.g., "thread_broadcast", 
                    "channel_join")
                - is_thread: Boolean indicating if message is part of a thread
                - is_parent: Boolean indicating if message is a thread parent 
                    (True), thread reply (False), or unthreaded message (None)
                - user_id: ID of the user who sent the message
                - thread_id: ID of the thread this message belongs to (same as ts 
                    for parent/unthreaded messages)
                - reactions: Dictionary mapping reaction names to their counts
        """
        try:
            # Get list of channels to process
            if channel_id_list is None:
                channel_id_list = self.channel_tracker.get_installed_channels()
            
            if not channel_id_list:
                logger.warning("No channels to process")
                return pd.DataFrame()

            all_messages = []

            for channel_id in channel_id_list:
                try:
                    # Get channel info
                    channel_info = self._get_channel_info(channel_id)
                    if not channel_info:
                        continue

                    # Fetch messages from this channel
                    messages = self._get_channel_history(channel_id, days)

                    # Process messages
                    for message in messages:
                        # Determine thread_id
                        thread_ts = message.get("thread_ts")
                        is_thread = bool(thread_ts)
                        is_parent = (
                            message.get("ts") == thread_ts if thread_ts else None
                        )
                        
                        # Use thread_ts as thread_id for both parent messages and 
                        # replies. For unthreaded messages, use their own ts as 
                        # thread_id. Convert to string to ensure thread_id is 
                        # always a string identifier
                        thread_id = str(
                            thread_ts if is_thread else message.get("ts")
                        )
                        
                        # Add the main message
                        all_messages.append({
                            "channel_id": channel_id,
                            "channel_name": channel_info["name"],
                            "ts_str": message.get("ts"),  # Store original string
                            "message": message.get("text", ""),
                            "type": message.get("type", "message"),
                            "subtype": message.get("subtype", "message"),
                            "is_thread": is_thread,
                            "is_parent": is_parent,
                            "user_id": message.get("user"),
                            "thread_id": thread_id,
                            "reactions": {}  # Initialize empty reactions
                        })

                        # Process thread replies if any
                        if is_thread and message.get("reply_count", 0) > 0:
                            thread_messages = self._get_thread_replies(
                                channel_id, 
                                thread_ts,
                                channel_info["name"]
                            )
                            all_messages.extend(thread_messages)

                    logger.info(
                        f"Fetched {len(messages)} messages from channel "
                        f"{channel_id} in the last {days} days"
                    )

                except Exception as e:
                    logger.error(
                        f"Error processing channel {channel_id}: {str(e)}"
                    )
                    continue

            # Create DataFrame
            df = pd.DataFrame(all_messages)

            # Convert timestamp to datetime
            if not df.empty:
                df["ts"] = pd.to_datetime(df["ts_str"].astype(float), unit="s")
                
                # Deduplicate: Thread broadcasts appear twice:
                # in channel messages and in thread replies
                df = df.drop_duplicates(
                    subset=["channel_id", "ts_str", "user_id", "message"],
                    keep="first"
                )
                
                # Fetch reactions for all messages
                for idx, row in df.iterrows():
                    reactions = self._get_message_reactions(
                        row["channel_id"],
                        row["ts_str"]
                    )
                    df.at[idx, "reactions"] = reactions
                
                logger.info(
                    f"Deduplicated messages and fetched reactions. "
                    f"Final count: {len(df)} messages"
                )

            return df

        except Exception as e:
            logger.error(f"Error retrieving messages: {str(e)}")
            return pd.DataFrame()
    
    def _get_channel_info(self, channel_id: str) -> Dict[str, Any]:
        """Get information about a channel from its ID.

        Args:
            channel_id (str): The ID of the channel

        Returns:
            Dict[str, Any]: Dictionary containing channel information with keys:
                - name: Name of the channel
                Returns None if channel info couldn't be retrieved
        """
        try:
            channel_info = self.app.client.conversations_info(
                channel=channel_id
            )
            
            if not channel_info["ok"]:
                logger.error(
                    f"Failed to get info for channel {channel_id}: "
                    f"{channel_info['error']}"
                )
                return None

            channel = channel_info["channel"]
            return {
                "name": channel.get("name")
            }

        except Exception as e:
            logger.error(
                f"Error getting channel info for {channel_id}: {str(e)}"
            )
            return None


    def _get_channel_history(
        self, 
        channel_id: str, 
        days: int
    ) -> List[Dict[str, Any]]:
        """Fetch conversation history for a specific channel.

        Args:
            channel_id (str): The ID of the channel to fetch history from
            days (int): Number of days to look back

        Returns:
            List[Dict[str, Any]]: List of all messages from the channel
        """
        try:
            all_messages = []
            cursor = None
            latest = None

            # Calculate oldest timestamp (days ago)
            oldest_ts = int(
                (datetime.now() - timedelta(days=days)).timestamp()
            )
            logger.info(f"Fetching messages from {days} days ago")

            while True:
                # Prepare parameters for the API call
                params = {
                    "channel": channel_id,
                    "inclusive": True,
                    "limit": 200,
                    "oldest": str(oldest_ts)
                }

                # Add latest timestamp if we have one
                if latest:
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
                f"in the last {days} days"
            )
            return all_messages

        except Exception as e:
            logger.error(
                f"Error fetching history for channel {channel_id}: {str(e)}"
            )
            return [] 

    def _get_thread_replies(
        self, 
        channel_id: str, 
        thread_ts: str,
        channel_name: str
    ) -> List[Dict[str, Any]]:
        """Process thread replies for a message.

        Args:
            channel_id: The ID of the channel
            thread_ts: The timestamp of the thread parent message
            channel_name: The name of the channel

        Returns:
            List[Dict[str, Any]]: List of thread reply messages
        """
        thread_messages = []
        cursor = None
        latest = None

        try:
            while True:
                # Prepare parameters for the API call
                params = {
                    "channel": channel_id,
                    "ts": thread_ts,
                    "inclusive": True,
                    "limit": 200
                }

                # Add latest timestamp if we have one
                if latest:
                    params["latest"] = latest

                # Add cursor if we have one
                if cursor:
                    params["cursor"] = cursor

                # Fetch thread replies
                thread_replies = self.app.client.conversations_replies(**params)
                
                if not thread_replies["ok"]:
                    logger.error(
                        f"Failed to fetch thread replies: {thread_replies['error']}"
                    )
                    break

                messages = thread_replies["messages"]
                if len(messages) > 1:  # Skip first message as it's the parent
                    for reply in messages[1:]:
                        thread_messages.append({
                            "channel_id": channel_id,
                            "channel_name": channel_name,
                            "ts_str": reply.get("ts"),  # Store original string
                            "message": reply.get("text", ""),
                            "type": reply.get("type", "message"),
                            "subtype": reply.get("subtype", "message"),
                            "is_thread": True,
                            "is_parent": reply.get("ts") == reply.get("thread_ts"),
                            "user_id": reply.get("user"),
                            "thread_id": str(thread_ts),  # Convert to string
                            "reactions": {}  # Initialize empty reactions
                        })

                # Check if there are more pages
                if not thread_replies.get("has_more", False):
                    break

                # Get the timestamp of the last message for time-based pagination
                if messages:
                    last_message = messages[-1]
                    latest = last_message["ts"]

                # Get cursor for next page if available
                cursor = thread_replies.get("response_metadata", {}).get("next_cursor")
                if not cursor:
                    break

            logger.info(
                f"Fetched {len(thread_messages)} thread replies for message {thread_ts}"
            )

        except Exception as e:
            logger.error(
                f"Error fetching thread replies for message {thread_ts}: {str(e)}"
            )
        
        return thread_messages 

    def _get_message_reactions(
        self,
        channel_id: str,
        timestamp: str
    ) -> Dict[str, int]:
        """Get reactions for a specific message.
        
        Args:
            channel_id (str): The ID of the channel containing the message
            timestamp (str): The timestamp of the message
            
        Returns:
            Dict[str, int]: Dictionary mapping reaction names to their counts
        """
        try:
            response = self.app.client.reactions_get(
                channel=channel_id,
                timestamp=timestamp
            )
            
            if not response["ok"]:
                logger.error(
                    f"Failed to get reactions for message {timestamp}: "
                    f"{response['error']}"
                )
                return {}
            
            # Extract reactions from response
            reactions = {}
            if "message" in response and "reactions" in response["message"]:
                for reaction in response["message"]["reactions"]:
                    reactions[reaction["name"]] = reaction["count"]
            
            return reactions
            
        except Exception as e:
            logger.error(
                f"Error getting reactions for message {timestamp}: {str(e)}"
            )
            return {} 