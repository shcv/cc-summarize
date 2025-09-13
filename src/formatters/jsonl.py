"""JSONL output formatter for Claude Code sessions."""

import json
from typing import List, Dict, Any, TextIO
import sys
from datetime import datetime

from parser import ConversationTurn, Message
from cache import SummaryResult


class JSONLFormatter:
    """Formats session summaries as structured JSONL output."""
    
    def format_session_summary(
        self, 
        turns: List[ConversationTurn], 
        summaries: List[SummaryResult], 
        session_metadata: Dict[str, Any],
        include_metadata: bool = False,
        output_file: TextIO = None
    ) -> str:
        """Format a complete session summary as JSONL."""
        
        output = output_file or sys.stdout
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
    
    def _format_turn(
        self, 
        turn_num: int, 
        turn: ConversationTurn, 
        summary: SummaryResult,
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
    
    def _format_user_message(self, message: Message, include_metadata: bool = False) -> Dict[str, Any]:
        """Format user message as JSON record."""
        
        user_record = {
            "uuid": message.uuid,
            "content": self._extract_user_content(message.content),
            "timestamp": message.timestamp
        }
        
        if include_metadata:
            if message.cwd:
                user_record["cwd"] = message.cwd
            if message.git_branch:
                user_record["git_branch"] = message.git_branch
        
        return user_record
    
    def _format_assistant_summary(self, summary: SummaryResult) -> Dict[str, Any]:
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
    
    def _extract_user_content(self, content: Any) -> str:
        """Extract clean text from user message content."""
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
    
    def format_session_list(self, sessions: List[Dict[str, Any]], output_file: TextIO = None, verbose: bool = False) -> str:
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
    
    def format_cache_stats(self, stats: Dict[str, int], output_file: TextIO = None) -> str:
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