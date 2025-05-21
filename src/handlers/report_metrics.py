from typing import Dict, Any
import logging
import pandas as pd
from utils.message_retriever import MessageRetriever

logger = logging.getLogger(__name__)

# Minimum number of messages required in a channel to compute PEI
MIN_MESSAGES_FOR_PEI = 10

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
            
            # Initialize metrics dictionary with channel names
            metrics = {
                channel_name: {} 
                for channel_name in df['channel_name'].unique()
            }
            
            # Add message counts to metrics
            self._compute_message_counts(df, metrics)
            
            # Add participation equity index to metrics
            self._compute_participation_equity_index(df, metrics)
            
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
        metrics: Dict[str, Dict[str, Dict[str, int]]]
    ) -> Dict[str, Any]:
        """Format the metrics into a Slack message using Block Kit.
        
        Args:
            metrics (Dict[str, Dict[str, Dict[str, int]]]): Dictionary mapping channel names to
                their metrics including message counts and participation equity index
            
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
        
        for channel_name, channel_metrics in metrics.items():
            # Add channel header
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*#{channel_name}*"
                }
            })
            
            # Add PEI if available
            if 'participation_equity_index' in channel_metrics:
                pei = channel_metrics['participation_equity_index']
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"• Participation Equity Index: {pei:.2f}"
                    }
                })
            
            # Sort message counts by count (descending)
            sorted_counts = sorted(
                channel_metrics['message_counts'].items(),
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
        try:
            # Use MessageRetriever to get messages
            message_retriever = MessageRetriever(self.app, self.channel_tracker)
            return message_retriever.get_channel_messages(days=self.days)

        except Exception as e:
            logger.error(f"Error processing channel data: {str(e)}")
            return pd.DataFrame()
        
    def _compute_message_counts(
        self, 
        df: pd.DataFrame,
        metrics: Dict[str, Dict[str, Dict[str, int]]]
    ) -> None:
        """Compute message counts by subtype for each channel.
        
        Args:
            df (pd.DataFrame): DataFrame containing message data
            metrics (Dict[str, Dict[str, Dict[str, int]]]): Dictionary to update with message counts
        """
        try:
            # Group by channel and subtype, then count messages
            counts = df.groupby(['channel_name', 'subtype']).size().reset_index(name='count')
            
            # Add message counts to metrics dictionary
            for _, row in counts.iterrows():
                channel_name = row['channel_name']
                subtype = row['subtype']
                count = row['count']
                
                if 'message_counts' not in metrics[channel_name]:
                    metrics[channel_name]['message_counts'] = {}
                metrics[channel_name]['message_counts'][subtype] = count
                
        except Exception as e:
            logger.error(f"Error computing message counts: {str(e)}")

    def _compute_participation_equity_index(
        self, 
        df: pd.DataFrame,
        metrics: Dict[str, Dict[str, Dict[str, int]]]
    ) -> None:
        """Compute Participation Equity Index (PEI) for each channel using Gini coefficient.
        
        The PEI is calculated as follows:
        1. For each channel, count messages per user (only 'message' and 'thread_broadcast' types)
        2. Compute Gini coefficient using the formula for discrete data:
           G = (1/(n*sum(x_i))) * sum((2*i - n - 1)*x_i)
           where:
           - n is the number of users
           - x_i are the sorted message counts
           - i is the rank (1 to n)
        3. Compute PEI as 1 - |Gini| (higher is more equitable)
        
        Args:
            df (pd.DataFrame): DataFrame containing message data with columns:
                - channel_name: Name of the channel
                - user_id: ID of the user who sent the message
                - subtype: Type of the message
            metrics (Dict[str, Dict[str, Dict[str, int]]]): Dictionary to update with PEI values
        """
        try:
            # Filter for relevant message types
            valid_messages = df[df['subtype'].isin(['message', 'thread_broadcast'])]
            
            # Group by channel and user to get message counts
            user_counts = valid_messages.groupby(['channel_name', 'user_id']).size()
            
            # Calculate PEI for each channel
            for channel_name in metrics.keys():
                try:
                    # Get message counts for this channel
                    channel_counts = user_counts[channel_name]
                    
                    if len(channel_counts) < 2:
                        # Not enough users to calculate meaningful equity
                        logger.info(f"Not enough users to calculate meaningful equity for channel {channel_name}")
                        metrics[channel_name]['participation_equity_index'] = pd.NA
                        continue
                    
                    # Sort message counts
                    sorted_counts = sorted(channel_counts)
                    n = len(sorted_counts)
                    total_sum = sum(sorted_counts)
                    
                    # Skip PEI calculation if channel has too few messages
                    if total_sum < MIN_MESSAGES_FOR_PEI:
                        logger.info(
                            f"Channel {channel_name} has only {total_sum} messages, "
                            "skipping PEI calculation"
                        )
                        metrics[channel_name]['participation_equity_index'] = pd.NA
                        continue
                    
                    if total_sum == 0:
                        # All users have zero messages
                        logger.info(f"All users have zero messages for channel {channel_name}")
                        metrics[channel_name]['participation_equity_index'] = pd.NA
                        continue
                    
                    # Calculate Gini coefficient using discrete formula
                    weighted_sum = sum(
                        (2 * i - n - 1) * x 
                        for i, x in enumerate(sorted_counts, start=1)
                    )
                    gini = abs(weighted_sum / (n * total_sum))
                    
                    # Calculate PEI (1 - Gini)
                    pei = 1 - gini
                    metrics[channel_name]['participation_equity_index'] = pei
                    
                    logger.info(
                        f"Channel {channel_name} PEI: {pei:.3f} (based on {n} users)"
                    )
                    
                except KeyError:
                    # Channel has no valid messages
                    metrics[channel_name]['participation_equity_index'] = pd.NA
                    continue
                
        except Exception as e:
            logger.error(f"Error computing PEI: {str(e)}")
 