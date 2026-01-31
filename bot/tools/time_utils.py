"""Time utilities for GemGem."""
from datetime import datetime
import pytz


def get_current_time(timezone: str = "America/Los_Angeles") -> str:
    """Get current time in a human-readable format."""
    try:
        tz = pytz.timezone(timezone)
        now = datetime.now(tz)
        return now.strftime("%A, %B %d, %Y at %I:%M %p %Z")
    except Exception:
        now = datetime.now()
        return now.strftime("%A, %B %d, %Y at %I:%M %p")


def get_date_context() -> str:
    """Get current date context for prompt injection."""
    now = datetime.now()
    return f"Today is {now.strftime('%A, %B %d, %Y')}."
