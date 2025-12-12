"""Display formatting utilities."""


def format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable format.

    Args:
        size_bytes: Size in bytes

    Returns:
        Formatted string like '1.5MB', '256KB', '1024B'
    """
    if size_bytes > 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f}MB"
    elif size_bytes > 1024:
        return f"{size_bytes / 1024:.0f}KB"
    else:
        return f"{size_bytes}B"


def format_file_size_short(size_bytes: int) -> str:
    """Format file size in compact format for tables.

    Args:
        size_bytes: Size in bytes

    Returns:
        Formatted string like '1.5M', '256K', '1024B'
    """
    if size_bytes > 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f}M"
    elif size_bytes > 1024:
        return f"{size_bytes / 1024:.0f}K"
    else:
        return f"{size_bytes}B"
