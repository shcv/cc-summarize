"""Rich terminal output formatter for Claude Code sessions."""

from typing import List, Dict, Any, Optional, TextIO

from rich.console import Console
from rich.text import Text
from rich.panel import Panel
from rich.table import Table
from rich import box

try:
    from .base import BaseFormatter
    from ..utils import (
        extract_user_content,
        parse_iso_timestamp,
        format_timestamp_short,
        format_timestamp_full,
        format_file_size,
        format_file_size_short,
    )
    from ..config import CONTENT_TRUNCATION_USER, CATEGORY_LABELS
except ImportError:
    from formatters.base import BaseFormatter
    from utils import (
        extract_user_content,
        parse_iso_timestamp,
        format_timestamp_short,
        format_timestamp_full,
        format_file_size,
        format_file_size_short,
    )
    from config import CONTENT_TRUNCATION_USER, CATEGORY_LABELS


class TerminalFormatter(BaseFormatter):
    """Formats session summaries for rich terminal display."""

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()

        # Color scheme
        self.colors = {
            'user': 'bright_blue',
            'assistant': 'bright_green',
            'summary': 'yellow',
            'tool': 'magenta',
            'error': 'red',
            'metadata': 'dim blue',
            'timestamp': 'dim white',
            'border': 'dim white',
            'subagent': 'bright_yellow',
            'plan': 'bright_cyan',
        }

        # Category colors for message display
        self.category_colors = {
            'USER': 'bright_green',
            'SUBAGENT': 'bright_yellow',
            'PLAN': 'bright_cyan',
            'ASSISTANT': 'bright_magenta',
            'SUMMARY': 'bright_blue',
        }

    def format_session_summary(
        self,
        turns: List,
        summaries: List,
        session_metadata: Dict[str, Any],
        include_metadata: bool = False,
        output_file: Optional[TextIO] = None
    ) -> Optional[str]:
        """Format and display a complete session summary."""
        # Session header
        self._print_session_header(session_metadata)

        # Process each turn
        for i, (turn, summary) in enumerate(zip(turns, summaries)):
            self._print_turn(i + 1, turn, summary, include_metadata)

            # Add spacing between turns
            if i < len(turns) - 1:
                self.console.print()

        return None  # Output written directly to console

    def format_session_list(
        self,
        sessions: List[Dict[str, Any]],
        output_file: Optional[TextIO] = None,
        verbose: bool = False
    ) -> Optional[str]:
        """Format and display a list of available sessions."""
        if not sessions:
            self.console.print("No sessions found.", style=self.colors['metadata'])
            return None

        # Create table
        table = Table(
            title="Available Sessions",
            box=box.ROUNDED,
            border_style=self.colors['border'],
            title_style="bold"
        )

        # Set column width based on verbose flag
        session_id_width = 36 if verbose else 14
        table.add_column("Session ID", style=self.colors['user'], width=session_id_width)
        table.add_column("Messages", justify="right", style=self.colors['metadata'])
        table.add_column("Size", justify="right", style=self.colors['metadata'])
        table.add_column("Last Modified", style=self.colors['timestamp'])

        for session in sessions:
            session_id = session.get('session_id', 'Unknown')
            if not verbose and len(session_id) > 11:
                session_id = session_id[:11] + '...'
            message_count = str(session.get('message_count', 0))

            # Format file size
            file_size = session.get('file_size', 0)
            size_str = format_file_size_short(file_size)

            # Format date
            last_modified = session.get('last_modified', '')
            dt = parse_iso_timestamp(last_modified)
            date_str = dt.strftime('%m-%d %H:%M') if dt else 'Unknown'

            table.add_row(session_id, message_count, size_str, date_str)

        self.console.print(table)
        return None

    def format_messages(
        self,
        messages: List[Dict],
        session_metadata: Dict[str, Any],
        include_metadata: bool = False,
        output_file: Optional[TextIO] = None
    ) -> Optional[str]:
        """Format categorized messages for terminal display."""
        # Session header
        session_id = session_metadata.get('session_id', 'Unknown')[:8]
        header_text = f"Messages from Session {session_id}... ({len(messages)} messages)"

        self.console.print(
            Panel(
                Text(header_text, style='bright_blue'),
                box=box.ROUNDED,
                border_style='blue',
                padding=(0, 1)
            )
        )
        self.console.print()

        # Display each message with category labels
        for i, message in enumerate(messages, 1):
            # Format timestamp if available
            timestamp_text = ""
            dt = parse_iso_timestamp(message.get('timestamp'))
            if dt:
                timestamp_text = f" [{format_timestamp_short(dt)}]"

            # Create title with category
            category = message['category']
            label = CATEGORY_LABELS.get(category, category.upper())
            category_color = self.category_colors.get(label, 'white')

            title = Text(f"[{label}] Message {i}", style=f"bold {category_color}")
            if timestamp_text:
                title.append(timestamp_text, style="dim white")

            content = message['content']
            if len(content) > CONTENT_TRUNCATION_USER:
                content = content[:CONTENT_TRUNCATION_USER] + "\n\n[... content truncated ...]"

            self.console.print(
                Panel(
                    content,
                    title=title,
                    title_align="left",
                    border_style=category_color,
                    padding=(0, 1)
                )
            )

            if i < len(messages):
                self.console.print()

        return None

    def format_cache_stats(
        self,
        stats: Dict[str, int],
        output_file: Optional[TextIO] = None
    ) -> Optional[str]:
        """Format and display cache statistics."""
        total_summaries = stats.get('successful_summaries', 0) + stats.get('failed_summaries', 0)
        cache_size = stats.get('total_size_bytes', 0)
        size_str = format_file_size(cache_size)

        cache_info = [
            "📦 Cache Statistics",
            "",
            f"Total cached summaries: {total_summaries}",
            f"  • Successful: {stats.get('successful_summaries', 0)}",
            f"  • Failed: {stats.get('failed_summaries', 0)}",
            f"Cache size: {size_str}",
        ]

        self.console.print(
            Panel(
                "\n".join(cache_info),
                border_style=self.colors['metadata'],
                padding=(0, 1)
            )
        )
        return None

    def _print_session_header(self, metadata: Dict[str, Any]) -> None:
        """Print session overview header."""
        session_id = metadata.get('session_id', 'Unknown')[:8]
        message_count = metadata.get('message_count', 0)
        start_time = metadata.get('start_time', '')
        file_size = metadata.get('file_size', 0)

        size_str = format_file_size(file_size)

        dt = parse_iso_timestamp(start_time)
        time_str = format_timestamp_full(dt) if dt else 'Unknown'

        header_text = f"Session {session_id}... | {message_count} messages | {size_str} | {time_str}"

        self.console.print(
            Panel(
                Text(header_text, style=self.colors['metadata']),
                box=box.ROUNDED,
                border_style=self.colors['border'],
                padding=(0, 1)
            )
        )
        self.console.print()

    def _print_turn(
        self,
        turn_num: int,
        turn,
        summary,
        include_metadata: bool = False
    ) -> None:
        """Print a single conversation turn."""
        # Turn header
        turn_header = f"Turn {turn_num}"
        if include_metadata:
            if turn.duration_seconds:
                turn_header += f" ({turn.duration_seconds:.1f}s"
                if turn.total_tokens:
                    turn_header += f", {turn.total_tokens} tokens"
                turn_header += ")"
            elif turn.total_tokens:
                turn_header += f" ({turn.total_tokens} tokens)"

        self.console.print(Text(turn_header, style="bold"))

        # User message
        self._print_user_message(turn.user_message, include_metadata)

        # Assistant summary
        self._print_assistant_summary(summary, turn.assistant_messages)

    def _print_user_message(self, message, include_metadata: bool = False) -> None:
        """Print user message with formatting."""
        content = extract_user_content(message.content)

        if not content.strip():
            content = "[Empty message]"

        # Truncate very long messages
        if len(content) > CONTENT_TRUNCATION_USER:
            content = content[:CONTENT_TRUNCATION_USER] + "..."

        # Format timestamp
        timestamp_text = ""
        dt = parse_iso_timestamp(message.timestamp)
        if dt:
            timestamp_text = f" [{format_timestamp_short(dt)}]"

        # User message panel
        user_text = Text("👤 User", style=f"bold {self.colors['user']}")
        if timestamp_text:
            user_text.append(timestamp_text, style=self.colors['timestamp'])

        self.console.print(
            Panel(
                content,
                title=user_text,
                title_align="left",
                border_style=self.colors['user'],
                padding=(0, 1)
            )
        )

    def _print_assistant_summary(self, summary, assistant_messages: List = None) -> None:
        """Print assistant summary with tool calls."""
        if summary.error:
            # Error case
            error_text = Text("❌ Assistant (Error)", style=f"bold {self.colors['error']}")
            self.console.print(
                Panel(
                    f"Failed to generate summary: {summary.error}",
                    title=error_text,
                    title_align="left",
                    border_style=self.colors['error'],
                    padding=(0, 1)
                )
            )
            return

        # Success case
        assistant_text = Text("🤖 Assistant", style=f"bold {self.colors['assistant']}")

        # Add timestamp from first assistant message
        if assistant_messages and assistant_messages[0].timestamp:
            dt = parse_iso_timestamp(assistant_messages[0].timestamp)
            if dt:
                timestamp_text = f" [{format_timestamp_short(dt)}]"
                assistant_text.append(timestamp_text, style=self.colors['timestamp'])

        if summary.tokens_used:
            assistant_text.append(f" [{summary.tokens_used} tokens]", style=self.colors['metadata'])

        # Main content
        content_parts = []

        if summary.summary:
            content_parts.append(summary.summary)

        # Add tool calls if present
        if summary.tool_calls:
            content_parts.append("")  # Spacing
            content_parts.append("🔧 Tools used:")
            for tool_call in summary.tool_calls[:10]:  # Limit to 10 tools
                content_parts.append(f"  • {tool_call}")

            if len(summary.tool_calls) > 10:
                content_parts.append(f"  • ... and {len(summary.tool_calls) - 10} more")

        content = "\n".join(content_parts) if content_parts else "[No summary available]"

        self.console.print(
            Panel(
                content,
                title=assistant_text,
                title_align="left",
                border_style=self.colors['assistant'],
                padding=(0, 1)
            )
        )
