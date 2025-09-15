"""Date parsing utilities for --since option."""

from datetime import datetime, timedelta, timezone
import re
from typing import Optional


def parse_since_date(since_str: str) -> datetime:
    """Parse both relative and absolute date formats for --since option.

    Supported formats:
    - Relative: 1d, 2h, 30m, 1w (days, hours, minutes, weeks)
    - Absolute: 2024-12-01, 2024-12-01T10:00, "2024-12-01 10:00"

    Args:
        since_str: Date string to parse

    Returns:
        datetime object representing the cutoff time

    Raises:
        ValueError: If the date format is not recognized
    """
    since_str = since_str.strip()

    # Try relative format first: 1d, 2h, 30m, 1w
    relative_pattern = r'^(\d+)([dhwm])$'
    match = re.match(relative_pattern, since_str.lower())
    if match:
        amount, unit = int(match.group(1)), match.group(2)
        now = datetime.now(timezone.utc)

        if unit == 'd':
            return now - timedelta(days=amount)
        elif unit == 'h':
            return now - timedelta(hours=amount)
        elif unit == 'm':
            return now - timedelta(minutes=amount)
        elif unit == 'w':
            return now - timedelta(weeks=amount)

    # Try absolute formats
    # Handle various datetime formats
    formats_to_try = [
        '%Y-%m-%d',                    # 2024-12-01
        '%Y-%m-%d %H:%M',             # 2024-12-01 10:00
        '%Y-%m-%d %H:%M:%S',          # 2024-12-01 10:00:30
        '%Y-%m-%dT%H:%M',             # 2024-12-01T10:00
        '%Y-%m-%dT%H:%M:%S',          # 2024-12-01T10:00:30
        '%Y-%m-%dT%H:%M:%SZ',         # 2024-12-01T10:00:30Z
    ]

    for fmt in formats_to_try:
        try:
            # Parse the date
            parsed_date = datetime.strptime(since_str, fmt)

            # If no timezone info, assume local timezone
            if parsed_date.tzinfo is None:
                # Convert local time to UTC for consistent comparison
                parsed_date = parsed_date.replace(tzinfo=timezone.utc)

            return parsed_date
        except ValueError:
            continue

    # Try ISO format parsing as fallback
    try:
        # Handle ISO format with timezone
        return datetime.fromisoformat(since_str.replace('Z', '+00:00'))
    except ValueError:
        pass

    # If all parsing attempts fail, raise an error
    raise ValueError(
        f"Invalid date format: '{since_str}'. "
        f"Supported formats: relative (1d, 2h, 30m, 1w) or absolute (2024-12-01, 2024-12-01T10:00)"
    )


def format_since_description(since_str: str, parsed_date: datetime) -> str:
    """Create a human-readable description of the since filter.

    Args:
        since_str: Original input string
        parsed_date: Parsed datetime

    Returns:
        Human-readable description
    """
    now = datetime.now(timezone.utc)

    # Check if it was a relative format
    relative_pattern = r'^(\d+)([dhwm])$'
    match = re.match(relative_pattern, since_str.lower())
    if match:
        amount, unit = int(match.group(1)), match.group(2)
        unit_names = {'d': 'day', 'h': 'hour', 'm': 'minute', 'w': 'week'}
        unit_name = unit_names[unit]
        plural = 's' if amount != 1 else ''
        return f"since {amount} {unit_name}{plural} ago"

    # For absolute dates, show both the original and how long ago
    time_diff = now - parsed_date
    if time_diff.days > 0:
        return f"since {parsed_date.strftime('%Y-%m-%d %H:%M')} ({time_diff.days} days ago)"
    elif time_diff.seconds > 3600:
        hours = time_diff.seconds // 3600
        return f"since {parsed_date.strftime('%Y-%m-%d %H:%M')} ({hours} hours ago)"
    else:
        minutes = time_diff.seconds // 60
        return f"since {parsed_date.strftime('%Y-%m-%d %H:%M')} ({minutes} minutes ago)"


def validate_since_date(since_str: str) -> Optional[str]:
    """Validate a since date string without parsing it.

    Args:
        since_str: Date string to validate

    Returns:
        None if valid, error message if invalid
    """
    try:
        parse_since_date(since_str)
        return None
    except ValueError as e:
        return str(e)


# Examples for testing/documentation
SINCE_EXAMPLES = [
    # Relative formats
    ("1d", "Last 24 hours"),
    ("2h", "Last 2 hours"),
    ("30m", "Last 30 minutes"),
    ("1w", "Last week"),

    # Absolute formats
    ("2024-12-01", "Since December 1st, 2024"),
    ("2024-12-01 10:00", "Since December 1st, 2024 at 10:00"),
    ("2024-12-01T10:00:00", "Since December 1st, 2024 at 10:00:00"),
]