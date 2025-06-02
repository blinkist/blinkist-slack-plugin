"""Decision Closure Rate (DCR) metric implementation."""
import logging
import json
import os
from typing import Dict, List, Any
import pandas as pd
import requests
from .base import MetricModel, Metric
import asyncio


logger = logging.getLogger(__name__)

# Minimum number of participants required in a thread
MIN_THREAD_PARTICIPANTS = 2
# Minimum number of initiated decisions required for DCR calculation
MIN_INITIATED_DECISIONS = 3
# Minimum confidence threshold for including a thread in DCR calculation
MIN_CONFIDENCE_THRESHOLD = 0.5
# Maximum number of threads to include in channel analysis
MAX_THREADS_FOR_ANALYSIS = 15
# Maximum number of concurrent API calls
MAX_CONCURRENT_CALLS = 4


class DecisionClosureRate(MetricModel):
    """Decision Closure Rate (DCR) metric for Slack channels.
    
    Measures how quickly decisions are made and closed in threaded 
    conversations.
    """
    
    name = Metric.DCR.value

    def __init__(self):
        """Initialize the DecisionClosureRate metric.
        
        Raises:
            ValueError: If Langdock API key is not found in environment 
            variables
        """
        
        # Get Langdock API key from environment
        self.api_key = os.environ["LANGDOCK_API_KEY"]
        if not self.api_key:
            logger.error(
                "Langdock API key not found in environment variables"
            )
            raise ValueError(
                "Langdock API key not found in environment variables"
            )
        
        # Set up API endpoint and headers
        self.api_url = "https://api.langdock.com/anthropic/eu/v1/messages"
        self.headers = {
            "Authorization": f"{self.api_key}",
            "Content-Type": "application/json"
        }

        self.system_prompt = self._get_system_prompt()

    def compute(self, df: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
        """Compute Decision Closure Rate for each channel.
        
        Args:
            df (pd.DataFrame): DataFrame containing message data
            
        Returns:
            Dict[str, Dict[str, Any]]: Dictionary mapping channel names to 
            their DCR
        """
        try:
            # Initialize results dictionary
            results = {}
            
            # Process each channel
            for channel_name in df['channel_name'].unique():
                # Reset thread analyses for new channel
                self._thread_analyses = []
                
                # Get channel data
                channel_df = df[df['channel_name'] == channel_name]
                
                # Get thread data
                thread_data = self._get_thread_data(channel_df)
                
                # Analyze threads and get channel analysis asynchronously
                async def analyze_channel():
                    # First analyze all threads
                    tasks = []
                    for thread_ts, messages in thread_data.items():
                        tasks.append(
                            self._get_thread_analysis_async(
                                messages, thread_ts
                            )
                        )
                    thread_analyses = await asyncio.gather(*tasks)
                    
                    # Filter threads by confidence threshold
                    confident_threads = [
                        analysis for analysis in thread_analyses
                        if analysis['confidence'] >= MIN_CONFIDENCE_THRESHOLD
                    ]
                    
                    closed_threads = sum(
                        1 for analysis in confident_threads
                        if analysis['status'] == 'closed'
                    )
                    initiated_threads = sum(
                        1 for analysis in confident_threads
                        if analysis['status'] in [
                            'initiated', 'in_progress', 'closed'
                        ]
                    )
                    
                    # Skip DCR calculation if not enough initiated decisions
                    if initiated_threads < MIN_INITIATED_DECISIONS:
                        logger.info(
                            f"Not enough initiated decisions "
                            f"({initiated_threads}) for channel {channel_name}. "
                            f"Minimum required: {MIN_INITIATED_DECISIONS}"
                        )
                        return {}
                    
                    # Validate logical consistency: closed threads cannot exceed 
                    # initiated threads
                    if closed_threads > initiated_threads:
                        logger.warning(
                            f"Logical inconsistency detected: {closed_threads} "
                            f"closed threads exceeds {initiated_threads} "
                            "initiated threads. Adjusting closed threads count "
                            "to match initiated threads."
                        )
                        closed_threads = initiated_threads
                    
                    dcr = (
                        (closed_threads / initiated_threads) * 100
                    ) if initiated_threads > 0 else 0
                    
                    # Get channel-wide analysis using only confident threads
                    self._thread_analyses = confident_threads
                    channel_analysis = await self._get_channel_analysis()
                    
                    return {
                        'dcr': dcr,
                        'insights': channel_analysis
                    }
                
                # Run async analysis
                results[channel_name] = asyncio.run(analyze_channel())
            
            return results
            
        except Exception as e:
            logger.error(f"Error computing DCR: {str(e)}")
            return {}

    async def _get_analysis_response_async(
        self, prompt: str
    ) -> Dict[str, Any]:
        """Send prompt to analysis API and get response asynchronously.
        
        Args:
            prompt (str): Prompt for analysis
            
        Returns:
            Dict[str, Any]: API response
        """
        try:
            logger.info("Sending request to analysis API")

            payload = {
                "max_tokens": 2000,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "model": "claude-3-7-sonnet-20250219",
                "stream": False,
                "system": self.system_prompt,
                "temperature": 0.5
            }
            
            response = requests.request(
                "POST",
                self.api_url,
                json=payload,
                headers=self.headers
            )
            response.raise_for_status()

            content = response.json()["content"][0]["text"]
            content = self._process_api_response(content)
            logger.info(f"Received response from analysis API: {content}")
            
            # Parse and validate response
            try:
                return json.loads(content)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse response as JSON: {content}")
                raise ValueError(f"Invalid JSON response from API: {str(e)}")
            
        except Exception as e:
            logger.error(f"Error getting response from analysis API: {str(e)}")
            raise

    async def _get_thread_analysis_async(
        self,
        thread_messages: List[Dict[str, Any]],
        thread_ts: str
    ) -> Dict[str, Any]:
        """Get analysis of a single thread for decision-making patterns 
        asynchronously.
        
        Args:
            thread_messages (List[Dict[str, Any]]): List of messages in the 
            thread
            thread_ts (str): Thread timestamp
            
        Returns:
            Dict[str, Any]: Thread analysis results including status, 
            confidence, and process summary
        """
        try:
            # Format messages for analysis
            formatted_messages = self._format_messages_for_analysis(
                thread_messages
            )
            
            # Prepare prompt for thread analysis
            prompt = self._create_thread_prompt(formatted_messages)
            
            # Get analysis from API
            response = await self._get_analysis_response_async(prompt)
            
            # Add thread timestamp to analysis
            response['thread_ts'] = thread_ts

            return response
            
        except Exception as e:
            logger.error(f"Error in thread analysis: {str(e)}")
            return {
                "status": "unknown",
                "confidence": 0.0,
                "thread_ts": thread_ts,
                "process_summary": {
                    "clear_process": "Error analyzing thread",
                    "inclusivity": "Error analyzing thread",
                    "efficiency": "Error analyzing thread",
                    "outcome_clarity": "Error analyzing thread",
                    "collaboration": "Error analyzing thread",
                    "evidence_use": "Error analyzing thread",
                    "accountability": "Error analyzing thread"
                }
            }

    async def _get_channel_analysis(self) -> Dict[str, Any]:
        """Stage 2: Analyze channel-wide decision-making patterns.
        
        Returns:
            Dict[str, Any]: Channel-level analysis results
        """
        try:
            # Prepare channel analysis prompt
            prompt = self._create_channel_prompt()
            
            # Get analysis from API
            response = await self._get_analysis_response_async(prompt)
            
            # Return analysis with default values if keys are missing
            return {
                "decision_making_strengths": response.get(
                    "decision_making_strengths",
                    "No strengths identified"
                ),
                "decision_making_improvements": response.get(
                    "decision_making_improvements",
                    "No improvements identified"
                )
            }
            
        except Exception as e:
            logger.error(f"Error in channel analysis: {str(e)}")
            return {
                "decision_making_strengths": (
                    "Error analyzing channel patterns"
                ),
                "decision_making_improvements": (
                    "Error analyzing channel patterns"
                )
            }

    @staticmethod
    def _get_system_prompt() -> str:
        """Get system prompt for thread analysis.
        
        Returns:
            str: System prompt
        """
        return """Analyze the following Slack thread for decision-making 
effectiveness. First, determine if a decision was initiated:

Decision Status Analysis:
1. Check for Decision Initiation:
   - Look for a message that indicates a decision-making process has started
   - For example, messages containing keywords like "let's decide," 
     "proposal," "vote," or "options" could be flagged
   - Identify when a specific issue or choice is first raised
   - Note if the decision scope and context are clearly defined
   - If no decision initiation is detected, mark as "no_decision"

2. If a decision was initiated, determine its current state:
   - "initiated": Decision was clearly started but not yet in progress
   - "in_progress": Active discussion about the decision is ongoing
   - "closed": Decision was completed with clear resolution
   - For closure, for example, look for messages with keywords like 
     "agreed," "approved," "finalized," or "let's proceed"
   - IMPORTANT: A decision can only be "closed" if there is clear 
     evidence it was previously "initiated"
   - If no clear initiation is found, the status cannot be "closed"

3. If no decision was initiated:
   - Mark as "no_decision"
   - Do not consider any other decision states
   - Focus on the general communication effectiveness instead

Then evaluate the decision-making process using these criteria:

1. **Clarity of the Decision-Making Process**:
   - Assess whether the discussion is structured and focused.
   - Look for clear problem statements and systematic evaluation of options.

2. **Inclusivity and Participation**:
   - Evaluate whether multiple team members contribute to the discussion.
   - Check if diverse perspectives are considered and quieter members are 
     engaged.
   - It is acceptable if only a subset of the team is involved in the 
     discussion.

3. **Efficiency in Reaching Decisions**:
   - Determine if decisions are made within a reasonable timeframe.
   - Look for focused discussions and minimal unnecessary delays.

4. **Clarity of Outcomes**:
   - Check if the final decision is explicitly stated.
   - Look for clear next steps or action items.

5. **Tone and Collaboration**:
   - Assess whether the tone of the discussion is constructive and 
     respectful.
   - Check for openness to different viewpoints and productive handling of 
     disagreements.
   - It is acceptable if the tone is more informal, as long as it is not 
     disrespectful or hostile.

6. **Use of Data and Evidence**:
   - Determine if arguments are supported by data, reports, or facts.
   - Check if decisions are based on evidence rather than intuition.
   - Not all decisions need to be data-driven, but arguments should be 
     clearly stated.

7. **Accountability and Follow-Up**:
   - Evaluate whether ownership of tasks is clearly assigned.
   - Look for follow-up messages to track progress on decisions.
   - It is acceptable if it's obvious that the decision initiator is 
     responsible for the execution of the decision.
"""
    
    def _create_thread_prompt(self, formatted_messages: str) -> str:
        """Create prompt for thread-level analysis.
        
        Args:
            formatted_messages (str): Formatted message history
            
        Returns:
            str: Prompt for thread analysis
        """
        return f"""Analyze the following Slack thread for decision-making 
effectiveness. First, determine if a decision was initiated, and if so, its 
current state. Additionally, indicate how confident you are in your 
assessment, on a scale of 0 to 1.

Then evaluate the decision-making process based on the following criteria:
1. Evidence of Clear Decision-Making Process
2. Inclusivity and Participation
3. Efficiency in Reaching Decisions
4. Clarity of Outcomes
5. Tone and Collaboration
6. Use of Data and Evidence
7. Accountability and Follow-Up

{'='*50}
THREAD MESSAGES:
{'='*50}

{formatted_messages}

{'='*50}

Provide your analysis in this JSON format, and return ONLY the JSON object:
{{
    "status": "initiated|in_progress|closed|no_decision",
    "confidence": <float between 0 and 1>,
    "process_summary": {{
        "clear_process": <evaluation of decision-making process>,
        "inclusivity": <evaluation of participation and inclusivity>,
        "efficiency": <evaluation of decision-making efficiency>,
        "outcome_clarity": <evaluation of outcome clarity>,
        "collaboration": <evaluation of tone and collaboration>,
        "evidence_use": <evaluation of data and evidence usage>,
        "accountability": <evaluation of accountability and follow-up>
    }}
}}"""

    def _create_channel_prompt(self) -> str:
        """Create prompt for channel-level analysis.
        
        Returns:
            str: Prompt for channel analysis
        """
        # Filter and sort thread analyses
        decision_threads = [
            analysis for analysis in self._thread_analyses
            if analysis['status'] in ['initiated', 'in_progress', 'closed']
        ]
        
        # Sort by timestamp (most recent first) and limit to 
        # MAX_THREADS_FOR_ANALYSIS
        decision_threads = sorted(
            decision_threads,
            key=lambda x: x.get('thread_ts', '0'),  # Default to '0' if no 
            # timestamp
            reverse=True  # Most recent first
        )[:MAX_THREADS_FOR_ANALYSIS]
        
        # Format thread analyses for the prompt
        thread_summaries = []
        for analysis in decision_threads:
            summary = (
                f"Thread Status: {analysis['status']}\n"
                f"Confidence: {analysis['confidence']}\n"
                f"Process Summary:\n"
                f"  - Clear Process: "
                f"{analysis['process_summary']['clear_process']}\n"
                f"  - Inclusivity: "
                f"{analysis['process_summary']['inclusivity']}\n"
                f"  - Efficiency: "
                f"{analysis['process_summary']['efficiency']}\n"
                f"  - Outcome Clarity: "
                f"{analysis['process_summary']['outcome_clarity']}\n"
                f"  - Collaboration: "
                f"{analysis['process_summary']['collaboration']}\n"
                f"  - Evidence Use: "
                f"{analysis['process_summary']['evidence_use']}\n"
                f"  - Accountability: "
                f"{analysis['process_summary']['accountability']}\n"
            )
            thread_summaries.append(summary)
        
        return f"""Analyze these thread summaries to identify channel-wide 
decision-making patterns:

{chr(10).join(thread_summaries)}

Focus on:
1. Common patterns in how decisions are made
2. Strengths in the decision-making process
3. Areas for improvement
4. Overall effectiveness of decision-making

Provide your analysis in this JSON format, and return ONLY the JSON object:
{{
    "decision_making_strengths": "Write 2-3 sentences summarizing the key 
    strengths in the team's decision-making process. Focus on patterns that 
    contribute to effective decision-making.",
    "decision_making_improvements": "Write 2-3 sentences summarizing the main 
    areas where decision-making could be improved. Focus on actionable 
    patterns that could enhance the process."
}}"""

    def _format_messages_for_analysis(
        self, messages: List[Dict[str, Any]]
    ) -> str:
        """Format messages for analysis with user and timestamp information.
        
        Args:
            messages (List[Dict[str, Any]]): List of messages
            
        Returns:
            str: Formatted message history with user and timestamp
        """
        formatted_messages = []
        for msg in messages:
            # Format timestamp
            timestamp = pd.to_datetime(msg['ts']).strftime('%Y-%m-%d %H:%M:%S')
            
            # Clean and escape the message text
            message_text = (
                msg['message']
                .replace('"', '\\"')
                .replace('\n', ' ')
            )
            
            # Format message with user and timestamp
            formatted_msg = (
                f"User {msg['user_id']} ({timestamp}): "
                f"{message_text}"
            )
            formatted_messages.append(formatted_msg)
        
        return "\n".join(formatted_messages)

    def _get_thread_data(
        self, channel_df: pd.DataFrame
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Get thread data for a channel.
        
        Args:
            channel_df (pd.DataFrame): DataFrame containing messages from a 
            channel
            
        Returns:
            Dict[str, List[Dict[str, Any]]]: Dictionary mapping thread 
            timestamps to lists of messages in each thread
        """
        try:
            thread_data = {}
            
            # Filter for thread messages only
            thread_df = channel_df[channel_df['is_thread']]
            
            # Group by thread_id to get all messages in each thread
            for thread_id, thread_messages_df in thread_df.groupby(
                'thread_id'
            ):
                # Skip if not enough participants
                if (
                    thread_messages_df['user_id'].nunique() 
                    < MIN_THREAD_PARTICIPANTS
                ):
                    continue
                
                # Get thread timestamp and messages
                thread_ts = thread_messages_df['ts'].iloc[0]
                thread_messages = thread_messages_df.to_dict(orient='records')
                thread_data[thread_ts] = thread_messages
            
            return thread_data
            
        except Exception as e:
            logger.error(f"Error getting thread data: {str(e)}")
            return {}

    def _process_api_response(self, content: str) -> str:
        """Extract JSON content from code blocks in the response.
        
        Args:
            content: Raw content string from API response
            
        Returns:
            Extracted JSON content string
        """
        if "```json" in content:
            # Find the start of the JSON code block
            content = content[
                content.find("```json"):
            ].strip("```json")
            # Find the end of the JSON code block
            content = content[
                :content.find("```")].strip("```")
        
        return content
