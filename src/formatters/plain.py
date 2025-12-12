"""Plain text output formatter for Claude Code sessions."""

import sys
from typing import List, Dict, Any, TextIO, Optional

try:
    from .base import BaseFormatter
    from ..utils import (
        extract_user_content,
        parse_iso_timestamp,
        format_timestamp_short,
        format_file_size,
    )
    from ..config import DEFAULT_SEPARATOR, CATEGORY_LABELS
except ImportError:
    from formatters.base import BaseFormatter
    from utils import (
        extract_user_content,
        parse_iso_timestamp,
        format_timestamp_short,
        format_file_size,
    )
    from config import DEFAULT_SEPARATOR, CATEGORY_LABELS


class PlainFormatter(BaseFormatter):
    """Formats session summaries as plain text suitable for piping."""

    def __init__(self, separator: str = None):
        """Initialize with custom separator or default em-dashes."""
        self.separator = separator or DEFAULT_SEPARATOR

    def format_session_summary(
        self,
        turns: List,
        summaries: List,
        session_metadata: Dict[str, Any],
        include_metadata: bool = False,
        output_file: Optional[TextIO] = None
    ) -> Optional[str]:
        """Format a complete session summary as plain text."""
        output = output_file or sys.stdout
        lines = []

        # Session header (optional, only if metadata requested)
        if include_metadata:
            session_id = session_metadata.get('session_id', 'Unknown')
            message_count = session_metadata.get('message_count', 0)
            lines.append(f"Session: {session_id}")
            lines.append(f"Messages: {message_count}")
            lines.append(self.separator)

        # Process each turn
        for i, (turn, summary) in enumerate(zip(turns, summaries)):
            if i > 0:  # Add separator between turns
                lines.append("")
                lines.append(self.separator)
                lines.append("")

            lines.extend(self._format_turn(turn, summary, include_metadata))

        plain_content = '\n'.join(lines)

        if output_file:
            output_file.write(plain_content)

        return plain_content

    def format_session_list(
        self,
        sessions: List[Dict[str, Any]],
        output_file: Optional[TextIO] = None,
        verbose: bool = False
    ) -> Optional[str]:
        """Format session list as plain text."""
        lines = []

        lines.append("Available Claude Code Sessions")
        lines.append(self.separator)
        lines.append("")

        if not sessions:
            lines.append("No sessions found.")
        else:
            for session in sessions:
                session_id = session.get('session_id', 'Unknown')
                if not verbose and len(session_id) > 15:
                    session_id = session_id[:15] + '...'
                message_count = session.get('message_count', 0)

                file_size = session.get('file_size', 0)
                size_str = format_file_size(file_size)

                last_modified = session.get('last_modified', '')
                dt = parse_iso_timestamp(last_modified)
                date_str = dt.strftime('%Y-%m-%d %H:%M') if dt else 'Unknown'

                lines.append(f"{session_id} | {message_count} messages | {size_str} | {date_str}")

        lines.append("")
        plain_content = '\n'.join(lines)

        if output_file:
            output_file.write(plain_content)

        return plain_content

    def format_messages(
        self,
        messages: List[Dict],
        session_metadata: Dict[str, Any],
        include_metadata: bool = False,
        output_file: Optional[TextIO] = None
    ) -> Optional[str]:
        """Format categorized messages as plain text."""
        lines = []

        session_id = session_metadata.get('session_id', 'Unknown')
        lines.append(f"Messages from Session {session_id}")
        lines.append(self.separator)
        lines.append("")

        if not messages:
            lines.append("No messages found.")
        else:
            for message in messages:
                # Add category label
                category = message['category']
                label = CATEGORY_LABELS.get(category, category.upper())

                # Add timestamp to the label
                timestamp_str = ""
                dt = parse_iso_timestamp(message.get('timestamp'))
                if dt:
                    timestamp_str = f" [{format_timestamp_short(dt)}]"

                lines.append(f"[{label}]{timestamp_str} {message['content']}")

                if message != messages[-1]:  # Don't add separator after last message
                    lines.append("")
                    lines.append(self.separator)
                    lines.append("")

        plain_content = '\n'.join(lines)
        if output_file:
            output_file.write(plain_content)

        return plain_content

    def _format_turn(
        self,
        turn,
        summary,
        include_metadata: bool = False
    ) -> List[str]:
        """Format a single conversation turn as plain text."""
        lines = []

        # User message
        user_content = extract_user_content(turn.user_message.content)

        # Add timestamp for user message
        dt = parse_iso_timestamp(turn.user_message.timestamp)
        if dt:
            timestamp = format_timestamp_short(dt)
            lines.append(f"User [{timestamp}]:")
        else:
            lines.append("User:")

        # User content
        if user_content.strip():
            lines.append(user_content)
        else:
            lines.append("[Empty user message]")

        # Assistant summary (if not user-only mode)
        if summary and summary.summary:
            lines.append("")  # Blank line between user and assistant

            # Format assistant header with timestamp
            assistant_header = "Assistant"
            if turn.assistant_messages and turn.assistant_messages[0].timestamp:
                dt = parse_iso_timestamp(turn.assistant_messages[0].timestamp)
                if dt:
                    timestamp = format_timestamp_short(dt)
                    assistant_header += f" [{timestamp}]"
            assistant_header += ":"
            lines.append(assistant_header)

            # Add token count if available and metadata requested
            if include_metadata and summary.tokens_used:
                lines.append(f"[{summary.tokens_used} tokens]")

            lines.append(summary.summary)

            # Add tool calls if present and not empty
            if summary.tool_calls:
                lines.append("")
                lines.append("Tools used:")
                for tool_call in summary.tool_calls:
                    lines.append(f"• {tool_call}")

        return lines


def should_use_plain_output() -> bool:
    """Detect if output should be plain text (when piping or NO_COLOR is set)."""
    import os

    # Check if output is being piped (not a terminal)
    if not sys.stdout.isatty():
        return True

    # Check for NO_COLOR environment variable
    if os.getenv('NO_COLOR'):
        return True

    return False
