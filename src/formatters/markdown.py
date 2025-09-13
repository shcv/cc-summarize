"""Markdown output formatter for Claude Code sessions."""

from typing import List, Dict, Any, TextIO
import sys
from datetime import datetime

from parser import ConversationTurn, Message
from cache import SummaryResult


class MarkdownFormatter:
    """Formats session summaries as Markdown documents."""
    
    def format_session_summary(
        self, 
        turns: List[ConversationTurn], 
        summaries: List[SummaryResult], 
        session_metadata: Dict[str, Any],
        include_metadata: bool = False,
        output_file: TextIO = None
    ) -> str:
        """Format a complete session summary as Markdown."""
        
        output = output_file or sys.stdout
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
    
    def _format_header(self, session_id: str, metadata: Dict[str, Any], include_metadata: bool) -> List[str]:
        """Format document header."""
        lines = []
        
        # Main title
        lines.append(f"# Claude Code Session Summary")
        lines.append("")
        
        # Session info
        lines.append(f"**Session ID:** `{session_id}`")
        
        if include_metadata:
            message_count = metadata.get('message_count', 'Unknown')
            lines.append(f"**Messages:** {message_count}")
            
            start_time = metadata.get('start_time')
            if start_time:
                try:
                    dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                    formatted_time = dt.strftime('%B %d, %Y at %H:%M:%S UTC')
                    lines.append(f"**Started:** {formatted_time}")
                except:
                    lines.append(f"**Started:** {start_time}")
            
            file_size = metadata.get('file_size')
            if file_size:
                if file_size > 1024 * 1024:
                    size_str = f"{file_size / (1024 * 1024):.1f}MB"
                elif file_size > 1024:
                    size_str = f"{file_size / 1024:.1f}KB"
                else:
                    size_str = f"{file_size}B"
                lines.append(f"**File Size:** {size_str}")
        
        lines.append("")
        lines.append("---")
        lines.append("")
        
        return lines
    
    def _format_toc(self, turns: List[ConversationTurn]) -> List[str]:
        """Format table of contents."""
        lines = []
        lines.append("## Table of Contents")
        lines.append("")
        
        for i, turn in enumerate(turns):
            # Extract first line of user message for TOC
            content = self._extract_user_content(turn.user_message.content)
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
        turn: ConversationTurn, 
        summary: SummaryResult,
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
        lines.extend(self._format_assistant_summary(summary))
        
        lines.append("")
        
        return lines
    
    def _format_user_message(self, message: Message, include_metadata: bool = False) -> List[str]:
        """Format user message."""
        lines = []
        
        # User section header
        header = "### 👤 User"
        if include_metadata and message.timestamp:
            try:
                dt = datetime.fromisoformat(message.timestamp.replace('Z', '+00:00'))
                time_str = dt.strftime('%H:%M:%S')
                header += f" _{time_str}_"
            except:
                pass
        
        lines.append(header)
        lines.append("")
        
        # User content
        content = self._extract_user_content(message.content)
        if not content.strip():
            content = "_[Empty message]_"
        
        # Format as blockquote
        for line in content.split('\n'):
            lines.append(f"> {line}")
        
        lines.append("")
        
        return lines
    
    def _format_assistant_summary(self, summary: SummaryResult) -> List[str]:
        """Format assistant summary."""
        lines = []
        
        # Assistant section header
        header = "### 🤖 Assistant"
        if summary.tokens_used:
            header += f" _{summary.tokens_used} tokens_"
        
        lines.append(header)
        lines.append("")
        
        if summary.error:
            lines.append("**❌ Error generating summary:**")
            lines.append("")
            lines.append(f"```")
            lines.append(summary.error)
            lines.append(f"```")
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
            
            lines.append(f"| `{session_id}` | {message_count} | {size_str} | {date_str} |")
        
        lines.append("")
        
        markdown_content = '\n'.join(lines)
        
        if output_file:
            output_file.write(markdown_content)
        
        return markdown_content