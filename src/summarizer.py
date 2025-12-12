"""AI-powered summarization using Claude Agent SDK."""

import os
import anyio
from typing import List, Optional, Dict
import subprocess
import json
import hashlib
from pathlib import Path

try:
    # Try relative imports first (when imported as a module)
    from .parser import Message, ConversationTurn
    from .cache import SummaryCache, SummaryResult
    from .utils import compact_tool_calls
except ImportError:
    # Fall back to absolute imports (when running directly or with sys.path manipulation)
    from parser import Message, ConversationTurn
    from cache import SummaryCache, SummaryResult
    from utils import compact_tool_calls


def get_data_dir() -> Path:
    """Get XDG data directory for cc-summarize."""
    xdg_data = os.environ.get('XDG_DATA_HOME', os.path.expanduser('~/.local/share'))
    return Path(xdg_data) / 'cc-summarize'


def get_claude_config_dir() -> Path:
    """Get isolated Claude config directory for cc-summarize."""
    return get_data_dir() / 'claude'


def ensure_claude_config() -> Path:
    """Ensure Claude config directory exists with symlinked credentials."""
    claude_dir = get_claude_config_dir()
    claude_dir.mkdir(parents=True, exist_ok=True)

    # Symlink credentials from user's Claude config
    user_creds = Path.home() / '.claude' / '.credentials.json'
    our_creds = claude_dir / '.credentials.json'

    if user_creds.exists() and not our_creds.exists():
        our_creds.symlink_to(user_creds)

    # Also symlink settings.json if it exists
    user_settings = Path.home() / '.claude' / 'settings.json'
    our_settings = claude_dir / 'settings.json'

    if user_settings.exists() and not our_settings.exists():
        our_settings.symlink_to(user_settings)

    return claude_dir


class Summarizer:
    """Summarizes Claude Code sessions using the Claude Agent SDK."""

    def __init__(self, cache_dir: Optional[str] = None, project_path: Optional[str] = None):
        """Initialize the summarizer.

        Args:
            cache_dir: Optional directory for caching summaries
            project_path: Optional project path for creating isolated CWD
        """
        self.cache = SummaryCache(cache_dir)
        self.project_path = project_path

        # Check if Claude Code is available
        self._check_claude_code_available()

        # Cache system prompts (these don't change)
        self._system_prompts = {}

        # Set up isolated Claude config directory
        self._claude_config_dir = ensure_claude_config()

        # Temp directory for message files passed to SDK
        self._temp_dir = get_data_dir() / 'tmp'
        self._temp_dir.mkdir(parents=True, exist_ok=True)
    
    def _check_claude_code_available(self):
        """Check if Claude Code CLI is installed and available."""
        try:
            result = subprocess.run(
                ['claude', '--version'], 
                capture_output=True, 
                text=True,
                timeout=5
            )
            if result.returncode != 0:
                raise RuntimeError("Claude Code CLI is not properly installed")
        except FileNotFoundError:
            raise RuntimeError(
                "Claude Code CLI not found. Please install it with: "
                "npm install -g @anthropic-ai/claude-code (or see https://docs.anthropic.com/en/docs/claude-code)"
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError("Claude Code CLI check timed out")

    def _clear_temp_directory(self):
        """Clear the temp directory for fresh file generation."""
        if self._temp_dir.exists():
            for file_path in self._temp_dir.glob("*"):
                try:
                    if file_path.is_file():
                        file_path.unlink()
                    elif file_path.is_dir():
                        import shutil
                        shutil.rmtree(file_path)
                except (OSError, PermissionError):
                    pass

    def _get_cache_path(self, turn: ConversationTurn, detail_level: str, session_id: str) -> Path:
        """Get the cache file path for a turn."""
        content = self._build_prompt(turn, detail_level)
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
        cache_key = f"{session_id}_{content_hash}_{detail_level}"
        return self.cache.summaries_dir / f"{cache_key}.json"

    def is_cached(self, turn: ConversationTurn, detail_level: str, session_id: str) -> bool:
        """Check if a turn's summary is already cached.

        Uses the same content hash as store_summary for consistency.
        """
        cache_path = self._get_cache_path(turn, detail_level, session_id)
        return cache_path.exists()

    def clear_turn_cache(self, turn: ConversationTurn, detail_level: str, session_id: str) -> bool:
        """Clear the cache entry for a specific turn.

        Returns True if a cache entry was cleared, False if none existed.
        """
        cache_path = self._get_cache_path(turn, detail_level, session_id)
        if cache_path.exists():
            cache_path.unlink()
            return True
        return False

    def _write_message_files(self, turn: ConversationTurn, detail_level: str) -> list:
        """Write assistant messages to separate files and return file references."""
        self._clear_temp_directory()

        file_refs = []

        # Write user message to file
        user_content = self._extract_message_content(turn.user_message)
        if user_content:
            user_file = self._temp_dir / "user_message.txt"
            with open(user_file, 'w', encoding='utf-8') as f:
                f.write(user_content)
            file_refs.append(("user", str(user_file)))

        # Write each assistant message to a separate file
        for i, msg in enumerate(turn.assistant_messages):
            # Extract text content
            content = self._extract_message_content(msg)

            # Create filename based on message index and type
            if msg.tool_name:
                filename = f"assistant_{i:02d}_{msg.tool_name.lower()}.txt"
            else:
                filename = f"assistant_{i:02d}_text.txt"

            msg_file = self._temp_dir / filename

            # Build content including both text and tool information
            file_content_parts = []

            if content:
                file_content_parts.append(f"Content: {content}")

            if msg.tool_name and msg.tool_args:
                tool_info = self._format_tool_call_for_prompt(msg.tool_name, msg.tool_args, detail_level)
                file_content_parts.append(f"Tool Call: {tool_info}")

                # For detailed mode, include full tool arguments
                if detail_level == 'detailed' and msg.tool_args:
                    file_content_parts.append(f"Tool Arguments: {json.dumps(msg.tool_args, indent=2)}")

            if file_content_parts:
                with open(msg_file, 'w', encoding='utf-8') as f:
                    f.write('\n\n'.join(file_content_parts))
                file_refs.append(("assistant", str(msg_file)))

        return file_refs

    def _extract_sdk_message_content(self, message) -> str:
        """Extract text content from SDK message objects."""

        # Handle ResultMessage objects (final summaries)
        if hasattr(message, 'result') and message.result:
            return str(message.result)

        # Handle SystemMessage objects
        if hasattr(message, 'data') and isinstance(message.data, dict):
            # Skip system init/config messages
            if message.data.get('type') == 'system':
                return ""

        # Handle messages with content attribute (standard format)
        if hasattr(message, 'content'):
            if isinstance(message.content, str):
                return message.content
            elif isinstance(message.content, list):
                # Handle structured content (list of items)
                text_parts = []
                for item in message.content:
                    if isinstance(item, dict) and item.get('type') == 'text':
                        text_parts.append(item.get('text', ''))
                    elif isinstance(item, str):
                        text_parts.append(item)
                return '\n'.join(text_parts)

        # Handle direct string messages
        if isinstance(message, str):
            return message

        # Handle messages with text attribute
        if hasattr(message, 'text'):
            return str(message.text)

        # Skip system/metadata messages, return empty for unknown types
        return ""
    
    def _get_system_prompt(self, detail_level: str) -> str:
        """Get cached system prompt for the given detail level."""
        if detail_level in self._system_prompts:
            return self._system_prompts[detail_level]

        # Common instruction for file edit descriptions
        edit_instruction = """
For each file that was edited, provide a one-line description of what changed.
Format file changes as: "- filename.py: description of change"
List these at the end under "Files changed:"."""

        if detail_level == 'minimal':
            prompt = f"""You are summarizing Claude Code assistant actions between user messages.
Focus ONLY on file edits (Edit, MultiEdit, Write) and bash commands (Bash).
Be very concise - one sentence for the overall action.
{edit_instruction}"""

        elif detail_level == 'normal':
            prompt = f"""You are summarizing Claude Code assistant actions between user messages.
Summarize the overall flow of actions taken by the assistant in 2-3 sentences.
Be concise but capture the key activities and their purpose.
{edit_instruction}"""

        else:  # detailed
            prompt = f"""You are summarizing Claude Code assistant actions between user messages.
Provide a comprehensive summary of what the assistant did, including:
- All tool calls and their purposes
- Any reasoning or explanations given
- The overall approach taken
Be thorough but organized.
{edit_instruction}"""

        self._system_prompts[detail_level] = prompt
        return prompt
    
    def _build_prompt(self, turn: ConversationTurn, detail_level: str) -> str:
        """Build a prompt using file references for message content."""
        # Write messages to separate files and get file references
        file_refs = self._write_message_files(turn, detail_level)

        parts = []
        parts.append("Please analyze the following conversation turn and provide a concise summary of what the assistant accomplished.")
        parts.append("")

        # Add file references for each message
        for msg_type, file_path in file_refs:
            if msg_type == "user":
                parts.append(f"USER MESSAGE: @{file_path}")
            elif msg_type == "assistant":
                parts.append(f"ASSISTANT MESSAGE: @{file_path}")

        parts.append("")
        parts.append("---")

        # Add instruction based on detail level
        if detail_level == 'minimal':
            parts.append("Provide a one-line summary focusing only on file operations and key commands executed.")
        elif detail_level == 'normal':
            parts.append("Provide a concise summary of the assistant's actions and their purpose.")
        else:  # detailed
            parts.append("Provide a comprehensive summary including all actions taken, reasoning, and outcomes.")

        return '\n'.join(parts)

    def _format_tool_call_for_prompt(self, tool_name: str, tool_args: Dict, detail_level: str) -> str:
        """Format tool call information for inclusion in prompts."""
        if detail_level == 'minimal':
            # For minimal detail, just show the tool name and key parameter
            if tool_name in ['Edit', 'MultiEdit', 'Write', 'Read']:
                file_path = tool_args.get('file_path', '')
                return f"{tool_name} {file_path}"
            elif tool_name == 'Bash':
                command = tool_args.get('command', '')[:50]
                return f"{tool_name}: {command}"
            else:
                return tool_name

        elif detail_level == 'normal':
            # For normal detail, include key parameters
            if tool_name in ['Edit', 'MultiEdit']:
                file_path = tool_args.get('file_path', '')
                old_str = tool_args.get('old_string', '')[:100]
                new_str = tool_args.get('new_string', '')[:100]
                return f"{tool_name} {file_path}: '{old_str}' -> '{new_str}'"
            elif tool_name == 'Write':
                file_path = tool_args.get('file_path', '')
                content_preview = tool_args.get('content', '')[:200]
                return f"{tool_name} {file_path}: {content_preview}"
            elif tool_name == 'Read':
                file_path = tool_args.get('file_path', '')
                return f"{tool_name} {file_path}"
            elif tool_name == 'Bash':
                command = tool_args.get('command', '')
                desc = tool_args.get('description', '')
                return f"{tool_name}: {desc or command}"
            elif tool_name in ['Grep', 'Glob']:
                pattern = tool_args.get('pattern', '')
                path = tool_args.get('path', '.')
                return f"{tool_name}: '{pattern}' in {path}"
            else:
                # Generic tool info
                key_args = []
                for key in ['file_path', 'command', 'pattern', 'description']:
                    if key in tool_args:
                        value = str(tool_args[key])[:50]
                        key_args.append(f"{key}={value}")
                return f"{tool_name}: {', '.join(key_args)}"

        else:  # detailed
            # For detailed, include all relevant parameters
            return f"{tool_name}: {json.dumps(tool_args, indent=None)}"
    
    def _extract_message_content(self, msg: Message) -> str:
        """Extract readable content from a message."""
        if isinstance(msg.content, str):
            return msg.content
        elif isinstance(msg.content, list):
            text_parts = []
            for item in msg.content:
                if isinstance(item, dict) and item.get('type') == 'text':
                    text_parts.append(item.get('text', ''))
                elif isinstance(item, dict) and item.get('type') == 'tool_use':
                    # Briefly describe tool use
                    tool_name = item.get('name', 'Unknown')
                    text_parts.append(f"[Uses {tool_name} tool]")
            return ' '.join(text_parts)
        else:
            return str(msg.content)

    def _parse_summary_response(self, response: str) -> tuple:
        """Parse AI response to extract summary and file changes.

        The AI is asked to format file changes as:
        Files changed:
        - filename.py: description of change

        Returns:
            (summary_text, dict mapping filename to description)
        """
        import re

        # Look for "Files changed:" section
        files_pattern = r'(?:Files changed:|Files edited:|Changes:)\s*\n((?:[-•*]\s+.+\n?)+)'
        match = re.search(files_pattern, response, re.IGNORECASE)

        if match:
            # Extract the summary (everything before "Files changed:")
            files_start = response.lower().find('files changed:')
            if files_start == -1:
                files_start = response.lower().find('files edited:')
            if files_start == -1:
                files_start = response.lower().find('changes:')

            summary = response[:files_start].strip() if files_start > 0 else ""

            # Parse file changes into a dict: filename -> description
            file_descriptions = {}
            changes_text = match.group(1)
            for line in changes_text.split('\n'):
                line = line.strip()
                if line.startswith(('-', '•', '*')):
                    # Remove the bullet and clean up
                    change = line.lstrip('-•* ').strip()
                    if change and ':' in change:
                        # Split on first colon to get filename and description
                        filename, description = change.split(':', 1)
                        filename = filename.strip()
                        description = description.strip()
                        if filename and description:
                            # Normalize to just the basename for matching
                            from pathlib import Path
                            basename = Path(filename).name
                            file_descriptions[basename] = description

            return summary, file_descriptions
        else:
            # No structured file changes found, return full response as summary
            return response, {}

    async def summarize_turn_async(
        self, 
        turn: ConversationTurn, 
        detail_level: str, 
        session_id: str
    ) -> SummaryResult:
        """Asynchronously summarize a conversation turn using Claude Code SDK.
        
        Args:
            turn: The conversation turn to summarize
            detail_level: Level of detail ('minimal', 'normal', 'detailed')
            session_id: Session identifier for caching
            
        Returns:
            SummaryResult with the generated summary
        """
        # Build content for cache key
        content = self._build_prompt(turn, detail_level)
        
        # Check cache first
        cached_result = self.cache.get_summary(session_id, content, detail_level)
        if cached_result:
            return cached_result
        
        try:
            # Import SDK here to handle import errors gracefully
            from claude_agent_sdk import query, ClaudeAgentOptions
            
            # Use the already built content as prompt
            prompt = content
            
            # Configure SDK options with isolated config directory
            options = ClaudeAgentOptions(
                system_prompt=self._get_system_prompt(detail_level),
                permission_mode='default',
                env={'CLAUDE_CONFIG_DIR': str(self._claude_config_dir)}
            )
            
            # Collect summary from SDK
            summary_parts = []
            async for message in query(prompt=prompt, options=options):
                # Extract text content from different SDK message types
                text_content = self._extract_sdk_message_content(message)
                if text_content:
                    summary_parts.append(text_content)

            full_response = ''.join(summary_parts).strip()

            # Parse the response to extract summary and file descriptions
            summary, file_descriptions = self._parse_summary_response(full_response)

            # Generate compacted tool calls, merging in AI-generated file descriptions
            tool_calls = compact_tool_calls(
                turn.assistant_messages,
                detail_level,
                file_descriptions=file_descriptions
            )

            # Create result
            result = SummaryResult(
                summary=summary,
                tool_calls=tool_calls,
                tokens_used=None  # SDK doesn't provide token count
            )
            
            # Cache the result
            self.cache.store_summary(session_id, content, detail_level, result)
            
            return result
            
        except ImportError as e:
            # SDK not installed properly
            error_msg = f"Claude Agent SDK not available: {str(e)}"
            return SummaryResult(
                summary="",
                tool_calls=[],
                tokens_used=None,
                error=error_msg
            )
        except Exception as e:
            # Other errors
            error_msg = f"SDK summarization failed: {str(e)}"
            return SummaryResult(
                summary="",
                tool_calls=[],
                tokens_used=None,
                error=error_msg
            )
    
    def summarize_turn(
        self, 
        turn: ConversationTurn, 
        detail_level: str, 
        session_id: str
    ) -> SummaryResult:
        """Synchronous wrapper for async summarization.
        
        Args:
            turn: The conversation turn to summarize
            detail_level: Level of detail ('minimal', 'normal', 'detailed')
            session_id: Session identifier for caching
            
        Returns:
            SummaryResult with the generated summary
        """
        return anyio.run(self.summarize_turn_async, turn, detail_level, session_id)
    
    def summarize_session(
        self, 
        turns: List[ConversationTurn], 
        detail_level: str,
        session_id: str = ''
    ) -> List[SummaryResult]:
        """Summarize all turns in a session.
        
        Args:
            turns: List of conversation turns
            detail_level: Level of detail for summaries
            session_id: Session identifier for caching
            
        Returns:
            List of SummaryResult objects
        """
        results = []
        
        for turn in turns:
            result = self.summarize_turn(turn, detail_level, session_id)
            results.append(result)
        
        return results


class SummarizerAvailability:
    """Helper class to check summarizer availability without importing the SDK."""

    @staticmethod
    def is_available() -> bool:
        """Check if Claude Agent SDK and CLI are both available."""
        # Check CLI
        try:
            result = subprocess.run(
                ['claude', '--version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode != 0:
                return False
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

        # Check Python SDK (try new name first, then old for backwards compat)
        try:
            import claude_agent_sdk
            return True
        except ImportError:
            try:
                import claude_code_sdk
                return True
            except ImportError:
                return False

    @staticmethod
    def get_error_message() -> str:
        """Get a helpful error message if SDK is not available."""
        messages = []

        # Check CLI
        try:
            subprocess.run(
                ['claude', '--version'],
                capture_output=True,
                text=True,
                timeout=5
            )
        except FileNotFoundError:
            messages.append(
                "Claude Code CLI not found. Install with: npm install -g @anthropic-ai/claude-code"
            )

        # Check Python SDK (try new name first, then old)
        try:
            import claude_agent_sdk
        except ImportError:
            try:
                import claude_code_sdk
            except ImportError:
                messages.append(
                    "Claude Agent SDK not found. Install with: pip install claude-agent-sdk"
                )

        return " | ".join(messages) if messages else "Unknown SDK error"