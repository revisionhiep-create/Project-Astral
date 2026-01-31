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


def get_date_context(timezone: str = "America/Los_Angeles") -> str:
    """Get current date and time context for prompt injection."""
    try:
        tz = pytz.timezone(timezone)
        now = datetime.now(tz)
        return f"Current time: {now.strftime('%A, %B %d, %Y at %I:%M %p %Z')}."
    except Exception:
        now = datetime.now()
        return f"Current time: {now.strftime('%A, %B %d, %Y at %I:%M %p')}."
