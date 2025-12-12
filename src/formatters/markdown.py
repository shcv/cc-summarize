"""Markdown output formatter for Claude Code sessions."""

import sys
from datetime import datetime
from typing import List, Dict, Any, TextIO, Optional

try:
    from .base import BaseFormatter
    from ..utils import (
        extract_user_content,
        parse_iso_timestamp,
        format_timestamp_short,
        format_file_size,
    )
    from ..config import CATEGORY_LABELS
except ImportError:
    from formatters.base import BaseFormatter
    from utils import (
        extract_user_content,
        parse_iso_timestamp,
        format_timestamp_short,
        format_file_size,
    )
    from config import CATEGORY_LABELS


class MarkdownFormatter(BaseFormatter):
    """Formats session summaries as Markdown documents."""

    def format_session_summary(
        self,
        turns: List,
        summaries: List,
        session_metadata: Dict[str, Any],
        include_metadata: bool = False,
        output_file: Optional[TextIO] = None
    ) -> Optional[str]:
        """Format a complete session summary as Markdown."""
        lines = []

        # Document header
        session_id = session_metadata.get('session_id', 'Unknown')
        lines.extend(self._format_header(session_id, session_metadata, include_metadata))

        # Table of contents for long sessions
        if len(turns) > 5:
            lines.extend(self._format_toc(turns))

        # Process each turn
        for i, (turn, summary) in enumerate(zip(turns, summaries)):
            lines.extend(self._format_turn(i + 1, turn, summary, include_metadata))

        # Footer with metadata
        if include_metadata:
            lines.extend(self._format_footer(session_metadata))

        markdown_content = '\n'.join(lines)

        if output_file:
            output_file.write(markdown_content)

        return markdown_content

    def format_session_list(
        self,
        sessions: List[Dict[str, Any]],
        output_file: Optional[TextIO] = None,
        verbose: bool = False
    ) -> Optional[str]:
        """Format session list as Markdown table."""
        lines = []

        lines.append("# Available Claude Code Sessions")
        lines.append("")

        if not sessions:
            lines.append("_No sessions found._")
            markdown_content = '\n'.join(lines)

            if output_file:
                output_file.write(markdown_content)

            return markdown_content

        # Create table
        lines.append("| Session ID | Messages | Size | Last Modified |")
        lines.append("|------------|----------|------|---------------|")

        for session in sessions:
            session_id = session.get('session_id', 'Unknown')
            if not verbose and len(session_id) > 15:
                session_id = session_id[:15] + '...'
            message_count = str(session.get('message_count', 0))

            file_size = session.get('file_size', 0)
            size_str = format_file_size(file_size)

            last_modified = session.get('last_modified', '')
            dt = parse_iso_timestamp(last_modified)
            date_str = dt.strftime('%Y-%m-%d %H:%M') if dt else 'Unknown'

            lines.append(f"| `{session_id}` | {message_count} | {size_str} | {date_str} |")

        lines.append("")

        markdown_content = '\n'.join(lines)

        if output_file:
            output_file.write(markdown_content)

        return markdown_content

    def format_messages(
        self,
        messages: List[Dict],
        session_metadata: Dict[str, Any],
        include_metadata: bool = False,
        output_file: Optional[TextIO] = None
    ) -> Optional[str]:
        """Format categorized messages as Markdown."""
        lines = []
        session_id = session_metadata.get('session_id', 'Unknown')

        lines.append(f"# Messages from Session {session_id}")
        lines.append("")
        lines.append(f"**Session ID:** `{session_id}`")
        lines.append(f"**Total Messages:** {len(messages)}")
        lines.append("")
        lines.append("---")
        lines.append("")

        for i, message in enumerate(messages, 1):
            category = message['category']
            label = CATEGORY_LABELS.get(category, category.upper())

            # Add timestamp to the header
            timestamp_str = ""
            dt = parse_iso_timestamp(message.get('timestamp'))
            if dt:
                timestamp_str = f" _{format_timestamp_short(dt)}_"

            lines.append(f"## [{label}]{timestamp_str} Message {i}")
            lines.append("")

            # Format content as blockquote
            for line in message['content'].split('\n'):
                lines.append(f"> {line}")

            lines.append("")
            lines.append("---")
            lines.append("")

        markdown_content = '\n'.join(lines)
        if output_file:
            output_file.write(markdown_content)

        return markdown_content

    def _format_header(self, session_id: str, metadata: Dict[str, Any], include_metadata: bool) -> List[str]:
        """Format document header."""
        lines = []

        # Main title
        lines.append("# Claude Code Session Summary")
        lines.append("")

        # Session info
        lines.append(f"**Session ID:** `{session_id}`")

        if include_metadata:
            message_count = metadata.get('message_count', 'Unknown')
            lines.append(f"**Messages:** {message_count}")

            start_time = metadata.get('start_time')
            if start_time:
                dt = parse_iso_timestamp(start_time)
                if dt:
                    formatted_time = dt.strftime('%B %d, %Y at %H:%M:%S UTC')
                    lines.append(f"**Started:** {formatted_time}")
                else:
                    lines.append(f"**Started:** {start_time}")

            file_size = metadata.get('file_size')
            if file_size:
                size_str = format_file_size(file_size)
                lines.append(f"**File Size:** {size_str}")

        lines.append("")
        lines.append("---")
        lines.append("")

        return lines

    def _format_toc(self, turns: List) -> List[str]:
        """Format table of contents."""
        lines = []
        lines.append("## Table of Contents")
        lines.append("")

        for i, turn in enumerate(turns):
            # Extract first line of user message for TOC
            content = extract_user_content(turn.user_message.content)
            first_line = content.split('\n')[0].strip()[:80]
            if len(first_line) < len(content):
                first_line += "..."

            lines.append(f"{i + 1}. [Turn {i + 1}: {first_line}](#turn-{i + 1})")

        lines.append("")
        lines.append("---")
        lines.append("")

        return lines

    def _format_turn(
        self,
        turn_num: int,
        turn,
        summary,
        include_metadata: bool = False
    ) -> List[str]:
        """Format a single conversation turn."""
        lines = []

        # Turn header
        anchor = f"turn-{turn_num}"
        header = f"## Turn {turn_num}"

        if include_metadata:
            metadata_parts = []
            if turn.duration_seconds:
                metadata_parts.append(f"{turn.duration_seconds:.1f}s")
            if turn.total_tokens:
                metadata_parts.append(f"{turn.total_tokens} tokens")

            if metadata_parts:
                header += f" _({', '.join(metadata_parts)})_"

        lines.append(f'<a id="{anchor}"></a>')
        lines.append(header)
        lines.append("")

        # User message
        lines.extend(self._format_user_message(turn.user_message, include_metadata))

        # Assistant summary
        lines.extend(self._format_assistant_summary(summary, turn.assistant_messages))

        lines.append("")

        return lines

    def _format_user_message(self, message, include_metadata: bool = False) -> List[str]:
        """Format user message."""
        lines = []

        # User section header
        header = "### 👤 User"
        dt = parse_iso_timestamp(message.timestamp)
        if dt:
            time_str = format_timestamp_short(dt)
            header += f" _{time_str}_"

        lines.append(header)
        lines.append("")

        # User content
        content = extract_user_content(message.content)
        if not content.strip():
            content = "_[Empty message]_"

        # Format as blockquote
        for line in content.split('\n'):
            lines.append(f"> {line}")

        lines.append("")

        return lines

    def _format_assistant_summary(self, summary, assistant_messages: List = None) -> List[str]:
        """Format assistant summary."""
        lines = []

        # Assistant section header
        header = "### 🤖 Assistant"

        # Add timestamp from first assistant message
        if assistant_messages and assistant_messages[0].timestamp:
            dt = parse_iso_timestamp(assistant_messages[0].timestamp)
            if dt:
                time_str = format_timestamp_short(dt)
                header += f" _{time_str}_"

        if summary.tokens_used:
            header += f" _{summary.tokens_used} tokens_"

        lines.append(header)
        lines.append("")

        if summary.error:
            lines.append("**❌ Error generating summary:**")
            lines.append("")
            lines.append("```")
            lines.append(summary.error)
            lines.append("```")
        else:
            # Summary content
            if summary.summary:
                lines.append(summary.summary)
            else:
                lines.append("_[No summary available]_")

            # Tool calls
            if summary.tool_calls:
                lines.append("")
                lines.append("**🔧 Tools used:**")
                lines.append("")

                for tool_call in summary.tool_calls:
                    lines.append(f"- `{tool_call}`")

        lines.append("")

        return lines

    def _format_footer(self, metadata: Dict[str, Any]) -> List[str]:
        """Format document footer with metadata."""
        lines = []
        lines.append("---")
        lines.append("")
        lines.append("## Session Metadata")
        lines.append("")

        # Format all available metadata
        if metadata.get('session_id'):
            lines.append(f"- **Session ID:** `{metadata['session_id']}`")

        if metadata.get('message_count'):
            lines.append(f"- **Total Messages:** {metadata['message_count']}")

        if metadata.get('start_time'):
            lines.append(f"- **Start Time:** {metadata['start_time']}")

        if metadata.get('last_modified'):
            lines.append(f"- **Last Modified:** {metadata['last_modified']}")

        if metadata.get('file_size'):
            lines.append(f"- **File Size:** {metadata['file_size']} bytes")

        lines.append("")
        lines.append(f"_Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}_")
        lines.append("")

        return lines
