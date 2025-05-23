"""Base class for channel metrics."""
from typing import Dict, Any
import pandas as pd
from enum import Enum


class Metric(str, Enum):
    """Names of all available metrics."""
    PEI = "participation_equity_index"
    DCR = "decision_closure_rate"


class MetricModel:
    """Base class for channel metrics.
    
    Subclasses must define a class variable:
        name: str
    and implement the compute method.
    The compute method can return different dictionary structures depending on the metric:
    - Simple metrics: Dict[str, float] - e.g., {'channel1': 0.8, 'channel2': 0.6}
    - Structured metrics: Dict[str, Dict[str, Any]] - e.g., 
      {'channel1': {'subtype1': {'metric1': 10, 'metric2': 20}}}
    """
    name: str
    
    def compute(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Compute the metric for all channels.
        
        Args:
            df (pd.DataFrame): DataFrame containing message data
            
        Returns:
            Dict[str, Any]: Dictionary mapping channel names to their metric values.
                Channels that don't meet the criteria for metric calculation are excluded.
        """
        raise NotImplementedError(
            "Subclasses must implement the compute method"
        ) 