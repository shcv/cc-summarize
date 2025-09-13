"""Rich terminal output formatter for Claude Code sessions."""

from typing import List, Dict, Any, Optional
from datetime import datetime
import textwrap

from rich.console import Console
from rich.text import Text
from rich.panel import Panel
from rich.columns import Columns
from rich.table import Table
from rich.syntax import Syntax
from rich import box

from parser import ConversationTurn, Message
from cache import SummaryResult


class TerminalFormatter:
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
            'border': 'dim white'
        }
    
    def format_session_summary(
        self, 
        turns: List[ConversationTurn], 
        summaries: List[SummaryResult], 
        session_metadata: Dict[str, Any],
        include_metadata: bool = False
    ) -> None:
        """Format and display a complete session summary."""
        
        # Session header
        self._print_session_header(session_metadata)
        
        # Process each turn
        for i, (turn, summary) in enumerate(zip(turns, summaries)):
            self._print_turn(i + 1, turn, summary, include_metadata)
            
            # Add spacing between turns
            if i < len(turns) - 1:
                self.console.print()
    
    def _print_session_header(self, metadata: Dict[str, Any]) -> None:
        """Print session overview header."""
        session_id = metadata.get('session_id', 'Unknown')[:8]
        message_count = metadata.get('message_count', 0)
        start_time = metadata.get('start_time', '')
        file_size = metadata.get('file_size', 0)
        
        # Format file size
        if file_size > 1024 * 1024:
            size_str = f"{file_size / (1024 * 1024):.1f}MB"
        elif file_size > 1024:
            size_str = f"{file_size / 1024:.1f}KB"
        else:
            size_str = f"{file_size}B"
        
        # Format start time
        if start_time:
            try:
                dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                time_str = dt.strftime('%Y-%m-%d %H:%M:%S UTC')
            except:
                time_str = start_time
        else:
            time_str = 'Unknown'
        
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
        turn: ConversationTurn, 
        summary: SummaryResult,
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
        self._print_assistant_summary(summary)
        
    def _print_user_message(self, message: Message, include_metadata: bool = False) -> None:
        """Print user message with formatting."""
        
        # Extract clean user content
        content = self._extract_user_content(message.content)
        
        if not content.strip():
            content = "[Empty message]"
        
        # Truncate very long messages
        if len(content) > 1000:
            content = content[:1000] + "..."
        
        # Format timestamp if requested
        timestamp_text = ""
        if include_metadata and message.timestamp:
            try:
                dt = datetime.fromisoformat(message.timestamp.replace('Z', '+00:00'))
                timestamp_text = f" [{dt.strftime('%H:%M:%S')}]"
            except:
                pass
        
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
    
    def _print_assistant_summary(self, summary: SummaryResult) -> None:
        """Print assistant summary with tool calls."""
        
        if summary.error:
            # Error case
            error_text = Text(f"❌ Assistant (Error)", style=f"bold {self.colors['error']}")
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
    
    def format_session_list(self, sessions: List[Dict[str, Any]], verbose: bool = False) -> None:
        """Format and display a list of available sessions."""
        
        if not sessions:
            self.console.print("No sessions found.", style=self.colors['metadata'])
            return
        
        # Create table
        table = Table(
            title="Available Sessions",
            box=box.ROUNDED,
            border_style=self.colors['border'],
            title_style="bold"
        )
        
        # Set column width based on verbose flag: full UUID (36 chars) or truncated (14 chars)
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
            if file_size > 1024 * 1024:
                size_str = f"{file_size / (1024 * 1024):.1f}M"
            elif file_size > 1024:
                size_str = f"{file_size / 1024:.0f}K"
            else:
                size_str = f"{file_size}B"
            
            # Format date
            last_modified = session.get('last_modified', '')
            if last_modified:
                try:
                    dt = datetime.fromisoformat(last_modified.replace('Z', '+00:00'))
                    date_str = dt.strftime('%m-%d %H:%M')
                except:
                    date_str = last_modified[:16]
            else:
                date_str = 'Unknown'
            
            table.add_row(session_id, message_count, size_str, date_str)
        
        self.console.print(table)
    
    def format_cache_stats(self, stats: Dict[str, int]) -> None:
        """Format and display cache statistics."""
        
        total_summaries = stats.get('successful_summaries', 0) + stats.get('failed_summaries', 0)
        cache_size = stats.get('total_size_bytes', 0)
        
        if cache_size > 1024 * 1024:
            size_str = f"{cache_size / (1024 * 1024):.2f}MB"
        elif cache_size > 1024:
            size_str = f"{cache_size / 1024:.1f}KB"
        else:
            size_str = f"{cache_size}B"
        
        cache_info = [
            f"📦 Cache Statistics",
            f"",
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