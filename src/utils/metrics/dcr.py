"""Decision Closure Rate (DCR) metric implementation."""
import logging
import json
import os
from typing import Dict, List
import pandas as pd
from datetime import datetime
from pathlib import Path
import openai
from .base import MetricModel, Metric

logger = logging.getLogger(__name__)

# Minimum number of participants required in a thread
MIN_THREAD_PARTICIPANTS = 2
# Minimum number of initiated decisions required for DCR calculation
MIN_INITIATED_DECISIONS = 1


class DecisionClosureRate(MetricModel):
    """Decision Closure Rate (DCR) metric for Slack channels.
    
    Measures how quickly decisions are made and closed in threaded conversations.
    """
    
    name = Metric.DCR.value

    def __init__(self):
        """Initialize the DecisionClosureRate metric.
        
        Raises:
            ValueError: If OpenAI API key is not found in environment variables
        """
        
        # Get OpenAI API key from environment
        openai_api_key = os.environ.get("OPENAI_API_KEY", "")
        if not openai_api_key:
            logger.error("OpenAI API key not found in environment variables")
            raise ValueError("OpenAI API key not found in environment variables")
        
        # Initialize OpenAI client with minimal arguments
        try:
            self.openai_client = openai.OpenAI(api_key=openai_api_key)
        except TypeError as e:
            logger.warning(
                f"Error initializing OpenAI client with default arguments: {e}"
            )
            # Try alternative initialization without proxies
            self.openai_client = openai.OpenAI(
                api_key=openai_api_key,
                http_client=None  # Let OpenAI create its own client
            )

    def compute(self, df: pd.DataFrame) -> Dict[str, float]:
        """Compute the Decision Closure Rate (DCR) for each channel.
        
        Args:
            df: DataFrame containing message data
            
        Returns:
            Dict[str, float]: Dictionary mapping channel names to their DCR 
            values
        """
        try:
            # Get valid threads with sufficient participation in one operation
            valid_threads = (
                df[df['is_thread']]
                .groupby(['channel_name', 'thread_id'])
                .agg({'user_id': 'nunique'})
                .query('user_id >= @MIN_THREAD_PARTICIPANTS')
            )
            
            if valid_threads.empty:
                logger.info(
                    f"No threads found with {MIN_THREAD_PARTICIPANTS} or more "
                    "participants"
                )
                return {}
            
            # Get messages from valid threads
            valid_threaded_messages = df[
                df['is_thread'] & 
                df['thread_id'].isin(
                    valid_threads.index.get_level_values('thread_id')
                )
            ]
            
            # Initialize DataFrame for analysis results
            analysis_df = pd.DataFrame(
                columns=[
                    'channel_id',
                    'channel_name',
                    'thread_id',
                    'decision_initiation',
                    'decision_closure',
                    'confidence'
                ]
            )
            
            # Process each thread
            for (channel_name, thread_id), thread_df in (
                valid_threaded_messages.groupby(['channel_name', 'thread_id'])
            ):
                # Format thread messages for prompt
                formatted_messages = self._format_thread_for_prompt(thread_df)
                
                # Create complete prompt
                prompt = self._create_prompt(formatted_messages)
                
                # Get decision analysis
                analysis = self._get_decision_analysis(prompt)
                
                # Add results to DataFrame
                new_row = pd.DataFrame([{
                    'channel_id': thread_df['channel_id'].iloc[0],
                    'channel_name': channel_name,
                    'thread_id': thread_id,
                    'decision_initiation': analysis['decision_initiation'],
                    'decision_closure': analysis['decision_closure'],
                    'confidence': analysis['confidence']
                }])
                analysis_df = pd.concat(
                    [analysis_df, new_row], 
                    ignore_index=True
                )
            
            logger.debug(
                f"Processed {len(analysis_df)} threads for decision analysis"
            )
            
            # Calculate DCR for each channel
            channel_metrics = {}
            for channel_name in analysis_df['channel_name'].unique():
                channel_data = analysis_df[analysis_df['channel_name'] == channel_name]
                
                # Count initiated and closed decisions
                initiated_decisions = channel_data['decision_initiation'].sum()
                closed_decisions = channel_data['decision_closure'].sum()
                
                # Only calculate DCR if we have enough data
                if initiated_decisions >= MIN_INITIATED_DECISIONS:
                    dcr = (closed_decisions / initiated_decisions) * 100
                    channel_metrics[channel_name] = dcr
                    
                    logger.debug(
                        f"Channel {channel_name}: DCR = {dcr:.2f}% "
                        f"({closed_decisions}/{initiated_decisions} decisions)"
                    )
                else:
                    logger.debug(
                        f"Channel {channel_name}: Insufficient data "
                        f"({initiated_decisions} initiated decisions, "
                        f"minimum {MIN_INITIATED_DECISIONS} required)"
                    )
            
            return channel_metrics
            
        except Exception as e:
            logger.error(f"Error computing DCR: {str(e)}")
            return {}

    def _format_thread_for_prompt(
        self, 
        thread_messages: pd.DataFrame
    ) -> List[str]:
        """Format thread messages for LLM analysis.
        
        Args:
            thread_messages: DataFrame containing messages from a single thread
            
        Returns:
            List[str]: List of formatted messages with user and timestamp
        """
        # Sort messages by timestamp
        thread_messages = thread_messages.sort_values('ts')
        
        # Format each message
        formatted_messages = []
        for _, msg in thread_messages.iterrows():
            # Format timestamp directly from Pandas Timestamp
            formatted_time = msg['ts'].strftime('%Y-%m-%d %H:%M:%S')
            
            # Clean and escape the message text
            message_text = msg['message'].replace('"', '\\"').replace('\n', ' ')
            
            # Format message with user and timestamp
            formatted_msg = (
                f"User {msg['user_id']} ({formatted_time}): "
                f"{message_text}"
            )
            formatted_messages.append(formatted_msg)
        
        return formatted_messages

    def _create_prompt(
        self, 
        formatted_messages: List[str]
    ) -> List[Dict[str, str]]:
        """Create a complete prompt for analysis.
        
        Args:
            formatted_messages: List of formatted thread messages
            
        Returns:
            List[Dict[str, str]]: List of message dictionaries for analysis
        """
        try:
            # Load prompt template from JSON file
            prompt_path = (
                Path(__file__).parent.parent.parent / 'data' / 
                'dcr_base_prompt.json'
            )
            with open(prompt_path, 'r') as f:
                prompt_data = json.load(f)
            
            # Format the messages as a bulleted list
            messages_text = "\n".join([f"- {msg}" for msg in formatted_messages])
            
            # Create the user prompt by combining the template with the messages
            try:
                user_prompt = prompt_data["user_prompt_template"].format(
                    messages=messages_text
                )
            except KeyError as e:
                logger.error(
                    f"Error formatting template. Missing key: {e}. "
                    f"Template: {prompt_data['user_prompt_template']}"
                )
                raise
            except Exception as e:
                logger.error(
                    f"Error formatting template: {str(e)}. "
                    f"Template: {prompt_data['user_prompt_template']}"
                )
                raise
            
            # Create prompt
            prompt = [
                {
                    "role": "system",
                    "content": prompt_data["system_prompt"]
                },
                {
                    "role": "user",
                    "content": user_prompt
                }
            ]
            
            return prompt
            
        except Exception as e:
            logger.error(f"Error creating prompt: {str(e)}")
            raise

    def _get_decision_analysis(
        self, 
        prompt: List[Dict[str, str]]
    ) -> Dict:
        """Send prompt to OpenAI API and get decision analysis.
        
        Args:
            prompt: List of message dictionaries for OpenAI API
            
        Returns:
            Dict: Analysis result with decision_initiation, decision_closure, 
            and confidence
            
        Raises:
            ValueError: If the response cannot be parsed as valid JSON
        """
        try:
            logger.info("Sending request to OpenAI API")
            response = self.openai_client.chat.completions.create(
                model="gpt-4-0125-preview",  # EU-hosted model version
                messages=prompt,
                temperature=0.1,  # Low temperature for consistent results
                max_tokens=150,  # Short response expected
                response_format={"type": "json_object"}  # Ensure JSON response
            )
            
            content = response.choices[0].message.content.strip()
            logger.info(f"Received response from OpenAI API: {content}")
            
            # Parse and validate response
            try:
                analysis = json.loads(content)
                logger.debug(f"Parsed analysis: {analysis}")
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse response as JSON: {content}")
                raise ValueError(f"Invalid JSON response from OpenAI API: {str(e)}")
            
            required_fields = [
                "decision_initiation", 
                "decision_closure", 
                "confidence"
            ]
            
            # Check for missing fields
            missing_fields = [field for field in required_fields if field not in analysis]
            if missing_fields:
                logger.error(f"Response missing required fields: {missing_fields}")
                logger.error(f"Full response: {analysis}")
                raise ValueError(f"Response missing required fields: {missing_fields}")
            
            # Ensure decision_closure is only 1 if decision_initiation is 1
            if analysis['decision_initiation'] == 0 and analysis['decision_closure'] == 1:
                logger.warning(
                    "Invalid state: decision_closure=1 but decision_initiation=0. "
                    "Setting decision_closure to 0."
                )
                analysis['decision_closure'] = 0
            
            return analysis
            
        except Exception as e:
            logger.error(f"Error getting decision analysis: {str(e)}")
            raise 