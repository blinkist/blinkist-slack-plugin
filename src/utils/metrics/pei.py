"""Participation Equity Index (PEI) metric implementation."""
import logging
import pandas as pd
from typing import Dict
from .base import MetricModel, Metric

logger = logging.getLogger(__name__)

# Minimum number of messages required in a channel to compute PEI
MIN_MESSAGES_FOR_PEI = 10


class ParticipationEquityIndex(MetricModel):
    """Class to compute Participation Equity Index (PEI) for Slack channels.
    
    The PEI measures how evenly participation is distributed among channel members.
    It is calculated using the Gini coefficient of message counts per user.
    A PEI of 1.0 indicates perfect equity, while 0.0 indicates complete inequality.
    """
    
    name = Metric.PEI.value

    def compute(self, df: pd.DataFrame) -> Dict[str, float]:
        """Compute Participation Equity Index (PEI) for all channels using Gini coefficient.
        
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
            
        Returns:
            Dict[str, float]: Dictionary mapping channel names to their PEI values.
                Channels that don't meet the criteria for PEI calculation are excluded.
        """
        try:
            # Filter for relevant message types
            valid_messages = df[df['subtype'].isin(['message', 'thread_broadcast'])]
            
            # Group by channel and user to get message counts
            user_counts = valid_messages.groupby(['channel_name', 'user_id']).size()
            
            # Initialize result dictionary
            pei_values = {}
            
            # Process each channel
            for channel_name in df['channel_name'].unique():
                try:
                    # Get message counts for this channel
                    channel_counts = user_counts[channel_name]
                    
                    if len(channel_counts) < 2:
                        # Not enough users to calculate meaningful equity
                        logger.info(
                            f"Not enough users to calculate meaningful PEI for "
                            f"channel {channel_name}"
                        )
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
                        continue
                    
                    if total_sum == 0:
                        # All users have zero messages
                        logger.info(
                            f"All users have zero messages for channel {channel_name}"
                        )
                        continue
                    
                    # Calculate Gini coefficient using discrete formula
                    weighted_sum = sum(
                        (2 * i - n - 1) * x 
                        for i, x in enumerate(sorted_counts, start=1)
                    )
                    gini = abs(weighted_sum / (n * total_sum))
                    
                    # Calculate PEI (1 - Gini)
                    pei = 1 - gini
                    
                    logger.info(
                        f"Channel {channel_name} PEI: {pei:.3f} (based on {n} users)"
                    )
                    
                    pei_values[channel_name] = pei
                    
                except KeyError:
                    # Channel has no valid messages
                    continue
                    
            return pei_values
                
        except Exception as e:
            logger.error(f"Error computing PEI: {str(e)}")
            return {} 