from datetime import datetime
import pytz
from config.settings import Settings

def is_working_hours():
    """Check if current time is within working hours"""
    current_time = datetime.now(Settings.TIMEZONE)
    return (
        Settings.WORKING_HOURS_START <= current_time.hour < Settings.WORKING_HOURS_END
        and current_time.weekday() < 5  # Monday to Friday
    )

def format_timestamp(ts):
    """Convert Unix timestamp to formatted datetime string"""
    dt = datetime.fromtimestamp(float(ts))
    return dt.strftime("%Y-%m-%d %H:%M:%S") 