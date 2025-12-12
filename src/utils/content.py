"""Content extraction utilities."""

from typing import Any


def extract_user_content(content: Any) -> str:
    """Extract clean text from user message content.

    Handles various content formats from Claude Code sessions:
    - Plain strings
    - Lists with text/tool_result items
    - Other types (converted to string)

    Args:
        content: Message content in any format

    Returns:
        Cleaned text content as string
    """
    if isinstance(content, str):
        # Clean up session hooks and other noise
        content = content.replace('<session-start-hook>', '')
        content = content.replace('</session-start-hook>', '')
        return content.strip()

    elif isinstance(content, list):
        # Handle tool results and complex content
        parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get('type') == 'text':
                    parts.append(item.get('text', ''))
                elif item.get('type') == 'tool_result':
                    # Skip tool results in user display - they're noise
                    continue
                else:
                    # Other content types
                    parts.append(str(item))
            else:
                parts.append(str(item))
        return '\n'.join(parts).strip()

    else:
        return str(content)


def extract_text_from_content(content: Any) -> str:
    """Extract only text content, ignoring tool calls and results.

    Similar to extract_user_content but also skips tool_use items.

    Args:
        content: Message content in any format

    Returns:
        Text-only content as string
    """
    if isinstance(content, str):
        return content.strip()

    elif isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get('type') == 'text':
                    parts.append(item.get('text', ''))
                # Skip tool_result and tool_use
            elif isinstance(item, str):
                parts.append(item)
        return '\n'.join(parts).strip()

    else:
        return str(content)


def truncate_content(content: str, max_length: int, suffix: str = "...") -> str:
    """Truncate content to maximum length with suffix.

    Args:
        content: Content to truncate
        max_length: Maximum length before truncation
        suffix: Suffix to append when truncated

    Returns:
        Truncated content with suffix if needed
    """
    if len(content) <= max_length:
        return content
    return content[:max_length - len(suffix)] + suffix
