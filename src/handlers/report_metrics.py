from typing import Dict, Any, List
import logging
import pandas as pd
from datetime import datetime, timedelta
from slack_sdk.errors import SlackApiError
from utils.message_retriever import MessageRetriever
from utils.metrics import ParticipationEquityIndex, DecisionClosureRate, Metric

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
        self.metric_models = [
            ParticipationEquityIndex(),
            DecisionClosureRate()
        ]

    def open_channel_select_modal(self, body, client, logger, days: int = 30):
        """Open a modal for channel selection.
        
        Args:
            body: The request body from Slack
            client: The Slack client instance
            logger: Logger instance
            days: Number of days to look back (default: 30)
        """
        try:
            # Acknowledge the command immediately
            trigger_id = body["trigger_id"]
            
            # Get list of channels where bot is installed
            installed_channels = self.channel_tracker.get_installed_channels()
            
            # Fetch channel info for installed channels
            valid_channels = []
            for channel_id in installed_channels:
                try:
                    channel_info = client.conversations_info(channel=channel_id)
                    if channel_info["ok"]:
                        channel = channel_info["channel"]
                        valid_channels.append({
                            "id": channel["id"],
                            "name": channel["name"]
                        })
                except SlackApiError as e:
                    logger.error(f"Error fetching info for channel {channel_id}: {e}")
            
            # Create options from valid channels
            options = [
                {
                    "text": {"type": "plain_text", "text": "All Channels"},
                    "value": "all"
                }
            ]
            # Add individual channel options
            options.extend([
                {
                    "text": {"type": "plain_text", "text": ch["name"]},
                    "value": ch["id"]
                }
                for ch in valid_channels
            ])
            
            # Open modal with channel selection
            client.views_open(
                trigger_id=trigger_id,
                view={
                    "type": "modal",
                    "callback_id": "pulse_report_channel_select",
                    "private_metadata": str(days),  # Store days in private metadata
                    "title": {"type": "plain_text", "text": "Channel Pulse Report"},
                    "submit": {"type": "plain_text", "text": "Generate Report"},
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"Select channels to analyze from the last {days} days:"
                            }
                        },
                        {
                            "type": "input",
                            "block_id": "channels_block",
                            "element": {
                                "type": "multi_static_select",
                                "action_id": "channels_select",
                                "placeholder": {
                                    "type": "plain_text",
                                    "text": "Select channels"
                                },
                                "options": options
                            },
                            "label": {
                                "type": "plain_text",
                                "text": "Choose channels to analyze"
                            }
                        }
                    ]
                }
            )
            
        except SlackApiError as e:
            logger.error(f"Error opening channel select modal: {e}")

    def handle_channel_select_submission(self, view, user, client, logger, days: int = 30):
        """Handle the channel selection submission.
        
        Args:
            view: The view submission data
            user: The user ID who submitted the form
            client: The Slack client instance
            logger: Logger instance
            days: Number of days to look back (default: 30)
        """
        # Extract selected channel IDs from the modal submission
        selected_channels = view["state"]["values"]["channels_block"]["channels_select"]["selected_options"]
        
        # Check if "All Channels" was selected
        if any(ch["value"] == "all" for ch in selected_channels):
            channel_ids = None  # None means all channels
            logger.info(f"User {user} selected all channels")
        else:
            channel_ids = [ch["value"] for ch in selected_channels]
            logger.info(f"User {user} selected channels: {channel_ids}")

        # Send acknowledgment message
        try:
            client.chat_postMessage(
                channel=user,
                text=":loading: *Processing the channels report...*\n"
                     "I'll message you when it's ready."
            )
        except SlackApiError as e:
            logger.error(f"Error sending acknowledgment message: {e}")

        try:
            # Generate report for selected channels
            report = self.generate_slack_report(days=days, channel_id_list=channel_ids)
            
            # Send report to user
            client.chat_postMessage(
                channel=user,
                blocks=report["blocks"]
            )
            
        except Exception as e:
            logger.error(f"Error generating report: {e}")
            try:
                client.chat_postMessage(
                    channel=user,
                    text="⚠️ *Error generating report*\n"
                         "Sorry, there was an error generating the report. "
                         "Please try again later."
                )
            except SlackApiError as e:
                logger.error(f"Error sending error notification: {e}")

    def generate_slack_report(self, days: int = 30, channel_id_list: List[str] = None) -> str:
        """Generate a complete report of channel metrics for Slack.
        
        Args:
            days (int, optional): Number of days to look back. Defaults to 30.
            channel_id_list (List[str], optional): List of channel IDs to analyze.
                If None, analyzes all installed channels.
            
        Returns:
            str: Formatted report message for Slack
        """
        self.days = days

        try:
            # Get the raw message data
            df = self._process_channel_data(channel_id_list)

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

    def _process_channel_data(self, channel_id_list: List[str] = None) -> pd.DataFrame:
        """Process all public channel message data and create a DataFrame.
        
        Args:
            channel_id_list (List[str], optional): List of channel IDs to process.
                If None, processes all installed channels.
        
        Returns:
            pd.DataFrame: DataFrame containing channel_id, channel_name, timestamp,
                         message data, message type and subtype
        """
        try:
            # Use MessageRetriever to get messages
            message_retriever = MessageRetriever(self.app, self.channel_tracker)
            return message_retriever.get_channel_messages(
                days=self.days,
                channel_id_list=channel_id_list
            )

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
            if Metric.PEI in channel_metrics:
                pei = channel_metrics[Metric.PEI]
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"• Participation Equity Index: {pei:.2f}"
                    }
                })
            
            # Add DCR if available
            if Metric.DCR in channel_metrics:
                dcr = channel_metrics[Metric.DCR]
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"• Decision Closure Rate: {dcr:.2f}%"
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
 