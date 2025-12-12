"""Timestamp parsing and formatting utilities."""

from datetime import datetime, timezone
from typing import Optional


def parse_iso_timestamp(timestamp_str: Optional[str]) -> Optional[datetime]:
    """Parse ISO timestamp handling 'Z' suffix.

    Handles Claude Code format: 2024-12-01T10:00:30Z
    Returns None on parse failure instead of raising.

    Args:
        timestamp_str: ISO format timestamp with optional Z suffix

    Returns:
        datetime in UTC timezone, or None if parsing fails
    """
    if not timestamp_str:
        return None

    try:
        return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
    except (ValueError, AttributeError, TypeError):
        return None


def parse_iso_timestamp_or_now(timestamp_str: Optional[str]) -> datetime:
    """Parse ISO timestamp, falling back to current time on failure.

    Args:
        timestamp_str: ISO format timestamp with optional Z suffix

    Returns:
        datetime in UTC timezone
    """
    result = parse_iso_timestamp(timestamp_str)
    return result if result is not None else datetime.now(timezone.utc)


def format_timestamp_short(dt: Optional[datetime]) -> str:
    """Format datetime as 'MM-DD HH:MM:SS'.

    Args:
        dt: datetime object to format

    Returns:
        Formatted string, or empty string if dt is None
    """
    if dt is None:
        return ""
    return dt.strftime('%m-%d %H:%M:%S')


def format_timestamp_full(dt: Optional[datetime]) -> str:
    """Format datetime as 'YYYY-MM-DD HH:MM:SS UTC'.

    Args:
        dt: datetime object to format

    Returns:
        Formatted string, or empty string if dt is None
    """
    if dt is None:
        return ""
    return dt.strftime('%Y-%m-%d %H:%M:%S UTC')


def format_timestamp_date(dt: Optional[datetime]) -> str:
    """Format datetime as 'YYYY-MM-DD HH:MM'.

    Args:
        dt: datetime object to format

    Returns:
        Formatted string, or empty string if dt is None
    """
    if dt is None:
        return ""
    return dt.strftime('%Y-%m-%d %H:%M')
