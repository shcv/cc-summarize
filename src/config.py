"""Configuration constants for cc-summarize."""

import json
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone


def _get_config_path() -> Path:
    """Get path to user config file."""
    xdg_config = os.environ.get('XDG_CONFIG_HOME', os.path.expanduser('~/.config'))
    return Path(xdg_config) / 'cc-summarize' / 'config.json'


def load_user_config() -> dict:
    """Load user configuration from ~/.config/cc-summarize/config.json.

    Returns a dict with defaults filled in for missing keys.
    """
    defaults = {
        'day_start_hour': 0,  # Hour (0-23) when the "day" rolls over
    }

    config_path = _get_config_path()
    if config_path.exists():
        try:
            with open(config_path) as f:
                user_config = json.load(f)
            defaults.update(user_config)
        except (json.JSONDecodeError, IOError):
            pass

    return defaults


def get_day_start_hour() -> int:
    """Get the configured day start hour (0-23)."""
    config = load_user_config()
    hour = config.get('day_start_hour', 0)
    return max(0, min(23, int(hour)))


def today_with_offset() -> datetime:
    """Get the start of 'today' adjusted for day_start_hour.

    If day_start_hour is 5 and it's currently 3am, 'today' is actually
    yesterday (since the day hasn't turned over yet).
    """
    now = datetime.now(timezone.utc)
    hour = get_day_start_hour()

    if hour == 0:
        return datetime.combine(now.date(), datetime.min.time()).replace(tzinfo=timezone.utc)

    # If current time is before the turnover hour, we're still in "yesterday"
    if now.hour < hour:
        effective_date = now.date() - timedelta(days=1)
    else:
        effective_date = now.date()

    return datetime.combine(effective_date, datetime.min.time()).replace(
        hour=hour, tzinfo=timezone.utc
    )


# Truncation limits
CONTENT_TRUNCATION_TERMINAL = 2000
CONTENT_TRUNCATION_USER = 1000
TOOL_COMMAND_TRUNCATION = 50
TOOL_ARG_TRUNCATION = 100

# Model configuration
DEFAULT_MODEL = "claude-3-5-haiku-20241022"

# Default separator for plain text output
DEFAULT_SEPARATOR = "—" * 24

# Tool filtering by detail level
MINIMAL_TOOLS = ['Edit', 'MultiEdit', 'Write', 'Bash']
NORMAL_TOOLS = MINIMAL_TOOLS + ['Read', 'Grep', 'Glob', 'LS', 'Task']
# DETAILED_TOOLS = None means show all tools

# Message categories
ALL_CATEGORIES = ['user', 'subagent', 'plan', 'assistant', 'session_summary']
EXCLUDED_CATEGORIES = {'system_noise', 'tool_response'}

# Category display labels
CATEGORY_LABELS = {
    'user': 'USER',
    'assistant': 'ASSISTANT',
    'subagent': 'SUBAGENT',
    'plan': 'PLAN',
    'session_summary': 'SUMMARY',
}
