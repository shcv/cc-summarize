"""Plain text output formatter for Claude Code sessions."""

import sys
from typing import List, Dict, Any, TextIO
from datetime import datetime

from parser import ConversationTurn, Message
from cache import SummaryResult


class PlainFormatter:
    """Formats session summaries as plain text suitable for piping."""
    
    def __init__(self, separator: str = None):
        """Initialize with custom separator or default em-dashes."""
        self.separator = separator or ("—" * 24)  # Em-dashes, shorter length
    
    def format_session_summary(
        self, 
        turns: List[ConversationTurn], 
        summaries: List[SummaryResult], 
        session_metadata: Dict[str, Any],
        include_metadata: bool = False,
        output_file: TextIO = None
    ) -> str:
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
    
    def _format_turn(
        self, 
        turn: ConversationTurn, 
        summary: SummaryResult,
        include_metadata: bool = False
    ) -> List[str]:
        """Format a single conversation turn as plain text."""
        lines = []
        
        # User message
        user_content = self._extract_user_content(turn.user_message.content)
        
        # Add timestamp if metadata requested
        if include_metadata and turn.user_message.timestamp:
            try:
                dt = datetime.fromisoformat(turn.user_message.timestamp.replace('Z', '+00:00'))
                timestamp = dt.strftime('%Y-%m-%d %H:%M:%S')
                lines.append(f"[{timestamp}]")
            except:
                pass
        
        # User content
        if user_content.strip():
            lines.append(user_content)
        else:
            lines.append("[Empty user message]")
        
        # Assistant summary (if not user-only mode)
        if summary and summary.summary:
            lines.append("")  # Blank line between user and assistant
            lines.append("Assistant:")
            
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
    
    def format_messages(self, messages: List[dict], session_metadata: dict, include_metadata: bool = False, output_file: TextIO = None) -> str:
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
                # Add category label with better names
                category = message['category']
                if category == 'session_summary':
                    label = 'SUMMARY'
                elif category == 'subagent':
                    label = 'SUBAGENT'
                else:
                    label = category.upper()
                
                lines.append(f"[{label}] {message['content']}")
                
                if message != messages[-1]:  # Don't add separator after last message
                    lines.append("")
                    lines.append(self.separator)
                    lines.append("")
        
        plain_content = '\n'.join(lines)
        if output_file:
            output_file.write(plain_content)
        
        return plain_content
    
    def format_user_prompts_only(
        self, 
        prompts: List[Dict], 
        session_metadata: Dict[str, Any],
        include_metadata: bool = False,
        output_file: TextIO = None
    ) -> str:
        """Format user prompts only as plain text."""
        
        lines = []
        
        # Session header (optional)
        if include_metadata:
            session_id = session_metadata.get('session_id', 'Unknown')
            lines.append(f"User Prompts - Session: {session_id}")
            lines.append(f"Total: {len(prompts)} prompts")
            lines.append(self.separator)
            lines.append("")
        
        # Process each prompt
        for i, prompt in enumerate(prompts):
            if i > 0:  # Add separator between prompts
                lines.append("")
                lines.append(self.separator)
                lines.append("")
            
            # Add timestamp if metadata requested
            if include_metadata and prompt.get('timestamp'):
                try:
                    dt = datetime.fromisoformat(prompt['timestamp'].replace('Z', '+00:00'))
                    timestamp = dt.strftime('%Y-%m-%d %H:%M:%S')
                    lines.append(f"[{timestamp}]")
                except:
                    pass
            
            # Prompt content
            content = prompt['content']
            if content.strip():
                lines.append(content)
            else:
                lines.append("[Empty prompt]")
        
        plain_content = '\n'.join(lines)
        
        if output_file:
            output_file.write(plain_content)
        
        return plain_content
    
    def format_session_list(self, sessions: List[Dict[str, Any]], output_file: TextIO = None, verbose: bool = False) -> str:
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
                
                # Format file size
                file_size = session.get('file_size', 0)
                if file_size > 1024 * 1024:
                    size_str = f"{file_size / (1024 * 1024):.1f}MB"
                elif file_size > 1024:
                    size_str = f"{file_size / 1024:.0f}KB"
                else:
                    size_str = f"{file_size}B"
                
                # Format date
                last_modified = session.get('last_modified', '')
                if last_modified:
                    try:
                        dt = datetime.fromisoformat(last_modified.replace('Z', '+00:00'))
                        date_str = dt.strftime('%Y-%m-%d %H:%M')
                    except:
                        date_str = last_modified[:16]
                else:
                    date_str = 'Unknown'
                
                lines.append(f"{session_id} | {message_count} messages | {size_str} | {date_str}")
        
        lines.append("")
        plain_content = '\n'.join(lines)
        
        if output_file:
            output_file.write(plain_content)
        
        return plain_content


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