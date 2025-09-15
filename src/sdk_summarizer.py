"""AI-powered summarization using Claude Code SDK."""

import os
import anyio
from typing import List, Optional, Dict
import subprocess
import json
import tempfile
import hashlib
from pathlib import Path

try:
    # Try relative imports first (when imported as a module)
    from .parser import Message, ConversationTurn
    from .cache import SummaryCache, SummaryResult
except ImportError:
    # Fall back to absolute imports (when running directly or with sys.path manipulation)
    from parser import Message, ConversationTurn
    from cache import SummaryCache, SummaryResult


class SDKSummarizer:
    """Summarizes Claude Code sessions using the Claude Code SDK for local processing."""
    
    def __init__(self, cache_dir: Optional[str] = None, project_path: Optional[str] = None):
        """Initialize the SDK summarizer.

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

        # Create isolated working directory for SDK
        self._isolated_cwd = self._create_isolated_cwd()
    
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
                "npm install -g @anthropic-ai/claude-code"
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError("Claude Code CLI check timed out")

    def _create_isolated_cwd(self) -> str:
        """Create an isolated working directory for SDK operations to avoid session clutter."""
        # Create a unique directory name based on project path
        if self.project_path:
            # Use project path to create a consistent but isolated directory
            project_hash = hashlib.md5(str(self.project_path).encode()).hexdigest()[:8]
            project_name = Path(self.project_path).name
            dir_name = f"cc-summarize-{project_name}-{project_hash}"
        else:
            # Fallback to a generic directory
            dir_name = "cc-summarize-session"

        # Create directory in /tmp
        isolated_dir = Path(tempfile.gettempdir()) / dir_name
        isolated_dir.mkdir(exist_ok=True)

        return str(isolated_dir)
    
    def _get_system_prompt(self, detail_level: str) -> str:
        """Get cached system prompt for the given detail level."""
        if detail_level in self._system_prompts:
            return self._system_prompts[detail_level]
        
        if detail_level == 'minimal':
            prompt = """You are summarizing Claude Code assistant actions between user messages. 
Focus ONLY on file edits (Edit, MultiEdit, Write) and bash commands (Bash). 
Summarize each action in one line, focusing on what was changed or executed.
Ignore all other tool calls and system messages.
Be very concise and specific about file names and key changes.
Output only the summary, no additional formatting."""
            
        elif detail_level == 'normal':
            prompt = """You are summarizing Claude Code assistant actions between user messages.
Include file operations (Edit, MultiEdit, Write, Read), bash commands (Bash), and search operations (Grep, Glob, LS).
Summarize the overall flow of actions taken by the assistant.
For tool calls, briefly describe what was done without including full outputs.
Be concise but capture the key activities and their purpose.
Output only the summary, no additional formatting."""
            
        else:  # detailed
            prompt = """You are summarizing Claude Code assistant actions between user messages.
Include ALL tool calls and assistant reasoning.
Provide a comprehensive summary of what the assistant did, including:
- All tool calls and their purposes
- Any reasoning or explanations given
- The overall approach taken
- Key decisions made
Be thorough but organized.
Output only the summary, no additional formatting."""
        
        self._system_prompts[detail_level] = prompt
        return prompt
    
    def _build_prompt(self, turn: ConversationTurn, detail_level: str) -> str:
        """Build a prompt from a conversation turn for summarization."""
        parts = []
        
        # Add user message
        parts.append(f"User message: {self._extract_message_content(turn.user_message)}\n")
        
        # Add assistant responses
        if turn.assistant_messages:
            parts.append("Assistant actions:\n")
            for msg in turn.assistant_messages:
                content = self._extract_message_content(msg)
                if msg.tool_name:
                    parts.append(f"- Tool: {msg.tool_name}")
                    if msg.tool_args and detail_level != 'minimal':
                        # Include some tool args for context
                        args_summary = self._summarize_tool_args(msg.tool_name, msg.tool_args)
                        if args_summary:
                            parts.append(f"  {args_summary}")
                if content and not msg.tool_name:
                    # Include non-tool assistant messages
                    parts.append(f"- Response: {content[:500]}...")
        
        # Add instruction
        parts.append("\nPlease summarize what the assistant did in response to the user's message.")
        
        return '\n'.join(parts)
    
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
    
    def _summarize_tool_args(self, tool_name: str, tool_args: Dict) -> str:
        """Create a brief summary of tool arguments."""
        if tool_name in ['Edit', 'MultiEdit', 'Write', 'Read']:
            file_path = tool_args.get('file_path', '')
            return f"File: {file_path}"
        elif tool_name == 'Bash':
            command = tool_args.get('command', '')[:100]
            return f"Command: {command}"
        elif tool_name in ['Grep', 'Glob']:
            pattern = tool_args.get('pattern', '')
            return f"Pattern: {pattern}"
        elif tool_name == 'Task':
            desc = tool_args.get('description', '')
            return f"Task: {desc}"
        return ""
    
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
            from claude_code_sdk import query, ClaudeCodeOptions
            
            # Use the already built content as prompt
            prompt = content
            
            # Configure SDK options
            options = ClaudeCodeOptions(
                system_prompt=self._get_system_prompt(detail_level),
                permission_mode='default',  # Use default permission mode (valid option)
                max_thinking_tokens=2000,
                cwd=self._isolated_cwd  # Use isolated working directory
            )
            
            # Collect summary from SDK
            summary_parts = []
            async for message in query(prompt=prompt, options=options):
                # The SDK returns message objects, extract text content
                if hasattr(message, 'content'):
                    # Handle message objects with content attribute
                    if isinstance(message.content, str):
                        summary_parts.append(message.content)
                    elif isinstance(message.content, list):
                        # Handle structured content
                        for item in message.content:
                            if isinstance(item, dict) and item.get('type') == 'text':
                                summary_parts.append(item.get('text', ''))
                            elif isinstance(item, str):
                                summary_parts.append(item)
                elif isinstance(message, str):
                    # Handle direct string messages
                    summary_parts.append(message)
                else:
                    # Fallback: convert to string
                    summary_parts.append(str(message))

            summary = ''.join(summary_parts).strip()
            
            # Extract tool calls for the result
            tool_calls = []
            for msg in turn.assistant_messages:
                if msg.tool_name:
                    tool_desc = f"{msg.tool_name}"
                    if msg.tool_args:
                        args_summary = self._summarize_tool_args(msg.tool_name, msg.tool_args)
                        if args_summary:
                            tool_desc += f": {args_summary}"
                    tool_calls.append(tool_desc)
            
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
            error_msg = f"Claude Code SDK not available: {str(e)}"
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


class SDKAvailability:
    """Helper class to check SDK availability without importing it."""
    
    @staticmethod
    def is_available() -> bool:
        """Check if Claude Code SDK and CLI are both available."""
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
        
        # Check Python SDK
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
        
        # Check Python SDK
        try:
            import claude_code_sdk
        except ImportError:
            messages.append(
                "Claude Code Python SDK not found. Install with: pip install claude-code-sdk"
            )
        
        return " | ".join(messages) if messages else "Unknown SDK error"