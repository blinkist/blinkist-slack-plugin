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
MIN_INITIATED_DECISIONS = 3
# Minimum confidence threshold for including a thread in DCR calculation
MIN_CONFIDENCE_THRESHOLD = 0.5


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
            # Check if DataFrame is empty
            if df.empty:
                logger.info("Input DataFrame is empty")
                return {}
            
            # Check if required columns exist
            required_columns = ['is_thread', 'channel_name', 'thread_id', 'user_id']
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                logger.error(f"Missing required columns: {missing_columns}")
                return {}
            
            # Filter for threads and group
            thread_df = df[df['is_thread']]

            valid_threads = (
                thread_df.groupby(['channel_name', 'thread_id'])
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
            
            # Initialize DataFrame for analysis results with explicit dtypes
            analysis_df = pd.DataFrame(
                columns=[
                    'channel_id',
                    'channel_name',
                    'thread_id',
                    'decision_initiation',
                    'decision_closure',
                    'confidence',
                    'decision_making_strengths',
                    'decision_making_improvements'
                ]
            ).astype({
                'channel_id': str,
                'channel_name': str,
                'thread_id': str,
                'decision_initiation': int,
                'decision_closure': int,
                'confidence': float,
                'decision_making_strengths': str,
                'decision_making_improvements': str
            })
            
            # Process each channel
            channel_metrics = {}
            unique_channels = valid_threaded_messages['channel_name'].unique()
            logger.info(f"Processing {len(unique_channels)} unique channels")
            
            for channel_name in unique_channels:                
                # Get all threads for this channel
                channel_threads = valid_threaded_messages[
                    valid_threaded_messages['channel_name'] == channel_name
                ]
                
                # Format all thread messages for the channel
                channel_threads_formatted = {}
                for thread_id, thread_df in channel_threads.groupby('thread_id'):
                    formatted_messages = self._format_thread_for_prompt(thread_df)
                    channel_threads_formatted[thread_id] = formatted_messages
                
                # Create complete prompt for channel analysis
                prompt = self._create_prompt(channel_threads_formatted)
                
                # Get decision analysis for all threads in channel
                analysis = self._get_decision_analysis(prompt)
                
                # Get channel insights once
                channel_insights = {
                    'decision_making_strengths': analysis['channel_insights']['decision_making_strengths'],
                    'decision_making_improvements': analysis['channel_insights']['decision_making_improvements']
                }
                
                # Process thread-level results
                for thread_id, thread_analysis in analysis['thread_analyses'].items():
                    # Get channel ID for this thread
                    thread_channel_id = (
                        channel_threads[
                            channel_threads['thread_id'] == thread_id
                        ]['channel_id'].iloc[0]
                    )
                    
                    # Create new row with explicit dtypes
                    new_row = pd.DataFrame([{
                        'channel_id': str(thread_channel_id),
                        'channel_name': str(channel_name),
                        'thread_id': str(thread_id),
                        'decision_initiation': int(thread_analysis['decision_initiation']),
                        'decision_closure': int(thread_analysis['decision_closure']),
                        'confidence': float(thread_analysis['confidence']),
                        'decision_making_strengths': channel_insights['decision_making_strengths'],
                        'decision_making_improvements': channel_insights['decision_making_improvements']
                    }])
                    
                    # Concatenate with explicit ignore_index
                    analysis_df = pd.concat(
                        [analysis_df, new_row],
                        ignore_index=True,
                        axis=0
                    )
                
                # Calculate DCR for this channel
                channel_data = analysis_df[
                    (analysis_df['channel_name'] == channel_name) & 
                    (analysis_df['confidence'] >= MIN_CONFIDENCE_THRESHOLD)
                ]
                
                # Count initiated and closed decisions
                initiated_decisions = int(channel_data['decision_initiation'].sum())
                closed_decisions = int(channel_data['decision_closure'].sum())
                
                # Only calculate DCR if we have enough data
                if initiated_decisions >= MIN_INITIATED_DECISIONS:
                    dcr = (closed_decisions / initiated_decisions) * 100
                    channel_metrics[channel_name] = {
                        'dcr': dcr,
                        'insights': channel_insights
                    }
                    
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
                    channel_metrics[channel_name] = {
                        'dcr': None,
                        'insights': channel_insights
                    }

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
        channel_threads: Dict[str, List[str]]
    ) -> List[Dict[str, str]]:
        """Create a complete prompt for analysis.
        
        Args:
            channel_threads: Dictionary mapping thread IDs to their formatted messages
            
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
            
            # Format all threads for the prompt with clear thread boundaries
            threads_text = []
            for thread_id, messages in channel_threads.items():
                # Create a clear thread header
                thread_header = f"\n{'='*50}\nThread ID: {thread_id}\n{'='*50}\n"
                
                # Format messages with clear separation
                thread_messages = []
                for msg in messages:
                    thread_messages.append(f"  {msg}")  # Indent messages for clarity
                
                # Combine header and messages
                thread_text = thread_header + "\n".join(thread_messages)
                threads_text.append(thread_text)
            
            # Add a final separator
            threads_text.append("\n" + "="*50 + "\n")
            
            # Create the user prompt by combining the template with all threads
            try:
                user_prompt = prompt_data["user_prompt_template"].format(
                    messages="\n".join(threads_text)
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
            Dict: Analysis result with thread-level analyses and channel insights
            
        Raises:
            ValueError: If the response cannot be parsed as valid JSON
        """
        try:
            logger.info("Sending request to OpenAI API")
            response = self.openai_client.chat.completions.create(
                model="gpt-4-0125-preview",  # EU-hosted model version
                messages=prompt,
                temperature=0.1,  # Low temperature for consistent results
                max_tokens=500,  # Increased for channel insights
                response_format={"type": "json_object"}  # Ensure JSON response
            )
            
            content = response.choices[0].message.content.strip()
            logger.info(f"Received response from OpenAI API: {content}")
            
            # Parse and validate response
            try:
                analysis = json.loads(content)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse response as JSON: {content}")
                raise ValueError(f"Invalid JSON response from OpenAI API: {str(e)}")
            
            required_fields = [
                "thread_analyses",
                "channel_insights"
            ]
            
            # Check for missing fields
            missing_fields = [field for field in required_fields if field not in analysis]
            if missing_fields:
                logger.error(f"Response missing required fields: {missing_fields}")
                raise ValueError(f"Response missing required fields: {missing_fields}")
            
            # Validate thread analyses
            for thread_id, thread_analysis in analysis['thread_analyses'].items():
                thread_fields = [
                    "decision_initiation",
                    "decision_closure",
                    "confidence"
                ]
                missing_thread_fields = [
                    field for field in thread_fields 
                    if field not in thread_analysis
                ]
                if missing_thread_fields:
                    logger.error(
                        f"Thread {thread_id} analysis missing fields: "
                        f"{missing_thread_fields}"
                    )
                    raise ValueError(
                        f"Thread analysis missing required fields: "
                        f"{missing_thread_fields}"
                    )
                
                # Ensure decision_closure is only 1 if decision_initiation is 1
                if (thread_analysis['decision_initiation'] == 0 and 
                        thread_analysis['decision_closure'] == 1):
                    logger.warning(
                        f"Invalid state in thread {thread_id}: "
                        "decision_closure=1 but decision_initiation=0. "
                        "Setting decision_closure to 0."
                    )
                    thread_analysis['decision_closure'] = 0
            
            return analysis
            
        except Exception as e:
            logger.error(f"Error getting decision analysis: {str(e)}")
            raise 