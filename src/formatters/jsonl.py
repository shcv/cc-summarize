"""JSONL output formatter for Claude Code sessions."""

import json
from datetime import datetime
from typing import List, Dict, Any, TextIO, Optional

try:
    from .base import BaseFormatter
    from ..utils import extract_user_content
    from ..config import CATEGORY_LABELS
except ImportError:
    from formatters.base import BaseFormatter
    from utils import extract_user_content
    from config import CATEGORY_LABELS


class JSONLFormatter(BaseFormatter):
    """Formats session summaries as structured JSONL output."""

    def format_session_summary(
        self,
        turns: List,
        summaries: List,
        session_metadata: Dict[str, Any],
        include_metadata: bool = False,
        output_file: Optional[TextIO] = None
    ) -> Optional[str]:
        """Format a complete session summary as JSONL."""
        lines = []

        # Session header record
        session_record = {
            "type": "session_header",
            "session_id": session_metadata.get('session_id'),
            "message_count": session_metadata.get('message_count'),
            "turn_count": len(turns),
            "timestamp": datetime.now().isoformat()
        }

        if include_metadata:
            session_record.update({
                "start_time": session_metadata.get('start_time'),
                "last_modified": session_metadata.get('last_modified'),
                "file_size": session_metadata.get('file_size')
            })

        lines.append(json.dumps(session_record))

        # Process each turn
        for i, (turn, summary) in enumerate(zip(turns, summaries)):
            turn_record = self._format_turn(i + 1, turn, summary, include_metadata)
            lines.append(json.dumps(turn_record))

        jsonl_content = '\n'.join(lines)

        if output_file:
            output_file.write(jsonl_content)

        return jsonl_content

    def format_session_list(
        self,
        sessions: List[Dict[str, Any]],
        output_file: Optional[TextIO] = None,
        verbose: bool = False
    ) -> Optional[str]:
        """Format session list as JSONL records."""
        lines = []

        # Header record
        header_record = {
            "type": "session_list",
            "count": len(sessions),
            "timestamp": datetime.now().isoformat()
        }
        lines.append(json.dumps(header_record))

        # Session records
        for session in sessions:
            session_record = {
                "type": "session_info",
                "session_id": session.get('session_id'),
                "message_count": session.get('message_count'),
                "file_size": session.get('file_size'),
                "start_time": session.get('start_time'),
                "last_modified": session.get('last_modified')
            }

            # Remove None values for cleaner JSON
            session_record = {k: v for k, v in session_record.items() if v is not None}
            lines.append(json.dumps(session_record))

        jsonl_content = '\n'.join(lines)

        if output_file:
            output_file.write(jsonl_content)

        return jsonl_content

    def format_messages(
        self,
        messages: List[Dict],
        session_metadata: Dict[str, Any],
        include_metadata: bool = False,
        output_file: Optional[TextIO] = None
    ) -> Optional[str]:
        """Format categorized messages as JSONL."""
        lines = []

        # Header record
        header_record = {
            "type": "categorized_messages_session",
            "session_id": session_metadata.get('session_id'),
            "message_count": len(messages),
            "timestamp": datetime.now().isoformat()
        }
        lines.append(json.dumps(header_record))

        # Message records
        for message in messages:
            message_record = {
                "type": "categorized_message",
                "number": message['number'],
                "category": message['category'],
                "content": message['content'],
                "uuid": message['uuid']
            }

            if include_metadata:
                if message.get('timestamp'):
                    message_record["timestamp"] = message['timestamp']
                if message.get('cwd'):
                    message_record["cwd"] = message['cwd']
                if message.get('git_branch'):
                    message_record["git_branch"] = message['git_branch']

            lines.append(json.dumps(message_record))

        jsonl_content = '\n'.join(lines)
        if output_file:
            output_file.write(jsonl_content)

        return jsonl_content

    def format_cache_stats(
        self,
        stats: Dict[str, int],
        output_file: Optional[TextIO] = None
    ) -> Optional[str]:
        """Format cache statistics as JSON record."""
        cache_record = {
            "type": "cache_stats",
            "timestamp": datetime.now().isoformat(),
            "successful_summaries": stats.get('successful_summaries', 0),
            "failed_summaries": stats.get('failed_summaries', 0),
            "total_size_bytes": stats.get('total_size_bytes', 0)
        }

        json_content = json.dumps(cache_record, indent=2)

        if output_file:
            output_file.write(json_content)

        return json_content

    def _format_turn(
        self,
        turn_num: int,
        turn,
        summary,
        include_metadata: bool = False
    ) -> Dict[str, Any]:
        """Format a single conversation turn as a JSON record."""
        # Base turn record
        turn_record = {
            "type": "conversation_turn",
            "turn_number": turn_num,
            "user_message": self._format_user_message(turn.user_message, include_metadata),
            "assistant_summary": self._format_assistant_summary(summary)
        }

        # Add metadata if requested
        if include_metadata:
            if turn.duration_seconds is not None:
                turn_record["duration_seconds"] = turn.duration_seconds
            if turn.total_tokens is not None:
                turn_record["total_tokens"] = turn.total_tokens

            # Include raw assistant message count and system message count
            turn_record["assistant_message_count"] = len(turn.assistant_messages)
            turn_record["system_message_count"] = len(turn.system_messages)
            turn_record["tool_message_count"] = len(turn.tool_messages)

        return turn_record

    def _format_user_message(self, message, include_metadata: bool = False) -> Dict[str, Any]:
        """Format user message as JSON record."""
        user_record = {
            "uuid": message.uuid,
            "content": extract_user_content(message.content),
            "timestamp": message.timestamp
        }

        if include_metadata:
            if message.cwd:
                user_record["cwd"] = message.cwd
            if message.git_branch:
                user_record["git_branch"] = message.git_branch

        return user_record

    def _format_assistant_summary(self, summary) -> Dict[str, Any]:
        """Format assistant summary as JSON record."""
        summary_record = {
            "summary": summary.summary,
            "tool_calls": summary.tool_calls
        }

        if summary.error:
            summary_record["error"] = summary.error

        if summary.tokens_used is not None:
            summary_record["tokens_used"] = summary.tokens_used

        return summary_record
