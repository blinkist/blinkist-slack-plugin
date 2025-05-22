from typing import Dict, Any
import logging
import pandas as pd
from utils.message_retriever import MessageRetriever
from utils.metrics import ParticipationEquityIndex, Metric

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
        # Initialize metric models
        self.metric_models = [ParticipationEquityIndex()]
        # Initialize metric names
        self.metrics = Metric()

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
            
            # Compute all metrics
            metrics = self._compute_metrics(df, metrics)
            
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
        metrics: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Format the metrics into a Slack message using Block Kit.
        
        Args:
            metrics (Dict[str, Dict[str, Any]]): Dictionary mapping channel names to
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
            if self.metrics.PEI in channel_metrics:
                pei = channel_metrics[self.metrics.PEI]
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

    def _compute_metrics(
        self, 
        df: pd.DataFrame,
        metrics: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """Compute all metrics for each channel.
        
        Args:
            df (pd.DataFrame): DataFrame containing message data
            metrics (Dict[str, Dict[str, Any]]): Dictionary to update with metric values
            
        Returns:
            Dict[str, Dict[str, Any]]: Updated metrics dictionary
        """
        try:
            # Compute each metric
            for metric in self.metric_models:
                metric_values = metric.compute(df)
                
                # Add metric values to metrics dictionary
                for channel_name, value in metric_values.items():
                    if channel_name in metrics:
                        metrics[channel_name][metric.name] = value
                
            return metrics
                
        except Exception as e:
            logger.error(f"Error computing metrics: {str(e)}")
            return metrics
 