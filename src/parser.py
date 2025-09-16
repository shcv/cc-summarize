"""JSONL session file parser for Claude Code sessions."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
import re
import hashlib


@dataclass
class Message:
    """Represents a single message in a Claude Code session."""
    uuid: str
    parent_uuid: Optional[str]
    type: str  # 'user', 'assistant', 'system', 'tool-use'
    timestamp: str
    content: Any  # Can be string, dict, or list depending on message type
    session_id: str
    cwd: Optional[str] = None
    git_branch: Optional[str] = None
    tool_name: Optional[str] = None
    tool_args: Optional[Dict] = None
    usage: Optional[Dict] = None  # Token usage info
    message_category: Optional[str] = None  # user, subagent, plan, tool_response, etc.
    
    @property
    def datetime(self) -> datetime:
        """Get timestamp as datetime object."""
        try:
            # Handle both ISO format with Z and timezone-aware formats
            timestamp_str = self.timestamp.replace('Z', '+00:00')
            return datetime.fromisoformat(timestamp_str)
        except (ValueError, AttributeError):
            return datetime.now(timezone.utc)


@dataclass
class ConversationTurn:
    """Represents a user prompt and all assistant responses until the next user message."""
    user_message: Message
    assistant_messages: List[Message]
    system_messages: List[Message]
    tool_messages: List[Message]
    duration_seconds: Optional[float] = None
    total_tokens: Optional[int] = None


class SessionParser:
    """Parser for Claude Code session JSONL files."""
    
    def __init__(self):
        self.messages: List[Message] = []
        self.message_map: Dict[str, Message] = {}
    
    def parse_file(self, file_path: Path) -> List[Message]:
        """Parse a JSONL session file and return all messages."""
        messages = []
        
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                
                try:
                    raw_msg = json.loads(line)
                    message = self._parse_message(raw_msg, line_num)
                    if message:
                        messages.append(message)
                except json.JSONDecodeError as e:
                    print(f"Warning: Invalid JSON on line {line_num}: {e}")
                    continue
                except Exception as e:
                    print(f"Warning: Error parsing line {line_num}: {e}")
                    continue
        
        # Sort by timestamp to ensure chronological order
        messages.sort(key=lambda m: m.datetime)
        
        self.messages = messages
        self.message_map = {msg.uuid: msg for msg in messages}
        
        return messages
    
    def _parse_message(self, raw: Dict, line_num: int) -> Optional[Message]:
        """Parse a single message from raw JSON."""
        try:
            msg_type = raw.get('type', 'unknown')
            uuid = raw.get('uuid', f'line_{line_num}')
            parent_uuid = raw.get('parentUuid')
            timestamp = raw.get('timestamp', '')
            session_id = raw.get('sessionId', '')
            cwd = raw.get('cwd')
            git_branch = raw.get('gitBranch')
            
            content = None
            tool_name = None
            tool_args = None
            usage = None
            
            # Extract content based on message type
            if msg_type == 'user':
                message_data = raw.get('message', {})
                content = message_data.get('content', '')
                
            elif msg_type == 'assistant':
                message_data = raw.get('message', {})
                content = message_data.get('content', [])
                usage = message_data.get('usage')
                
            elif msg_type == 'system':
                content = raw.get('content', '')
                
            elif msg_type == 'summary':
                content = raw.get('summary', '')
                
            else:
                # Handle other message types
                content = raw.get('content', raw.get('message', ''))
            
            # Extract tool information if present
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get('type') == 'tool_use':
                        tool_name = item.get('name')
                        tool_args = item.get('input', {})
                        break
            
            return Message(
                uuid=uuid,
                parent_uuid=parent_uuid,
                type=msg_type,
                timestamp=timestamp,
                content=content,
                session_id=session_id,
                cwd=cwd,
                git_branch=git_branch,
                tool_name=tool_name,
                tool_args=tool_args,
                usage=usage
            )
            
        except Exception as e:
            print(f"Error parsing message: {e}")
            return None
    
    def build_conversation_turns(self, messages: Optional[List[Message]] = None) -> List[ConversationTurn]:
        """Group messages into conversation turns (user message + responses)."""
        if messages is None:
            messages = self.messages

        turns = []
        current_user_message = None
        current_assistant_messages = []
        current_system_messages = []
        current_tool_messages = []

        for message in messages:
            if message.type == 'user':
                # Skip if this is a tool response masquerading as a user message
                if self._is_tool_response(message):
                    continue

                # Skip if this is system noise
                if self._is_system_noise_message(message):
                    continue

                # Skip if this is a session summary
                if self._is_session_summary_message(message):
                    continue

                # Save previous turn if we have one
                if current_user_message:
                    turn = ConversationTurn(
                        user_message=current_user_message,
                        assistant_messages=current_assistant_messages,
                        system_messages=current_system_messages,
                        tool_messages=current_tool_messages
                    )
                    turn.duration_seconds = self._calculate_turn_duration(turn)
                    turn.total_tokens = self._calculate_turn_tokens(turn)
                    turns.append(turn)

                # Start new turn
                current_user_message = message
                current_assistant_messages = []
                current_system_messages = []
                current_tool_messages = []

            elif message.type == 'assistant':
                current_assistant_messages.append(message)
            elif message.type == 'system':
                current_system_messages.append(message)
            else:
                current_tool_messages.append(message)

        # Don't forget the last turn
        if current_user_message:
            turn = ConversationTurn(
                user_message=current_user_message,
                assistant_messages=current_assistant_messages,
                system_messages=current_system_messages,
                tool_messages=current_tool_messages
            )
            turn.duration_seconds = self._calculate_turn_duration(turn)
            turn.total_tokens = self._calculate_turn_tokens(turn)
            turns.append(turn)

        return turns

    def _is_tool_response(self, message) -> bool:
        """Check if a user message is actually a tool response."""
        content = message.content

        if isinstance(content, list) and content:
            # Check if the first item is a tool_result
            first_item = content[0]
            if isinstance(first_item, dict) and first_item.get("type") == "tool_result":
                return True

        return False

    def _is_system_noise_message(self, message) -> bool:
        """Check if message content is system noise rather than actual user input."""
        content = self._extract_text_content(message.content)
        if not content:
            return True

        content_lower = content.lower().strip()

        # Skip command-related messages
        if (
            content.startswith("<command-")
            or content.startswith("<local-command-")
            or "command-message" in content
            or "[Request interrupted" in content
        ):
            return True

        # Skip very short generic responses
        if len(content_lower) < 10:
            return True

        # Skip pure formatting/caveat messages
        noise_patterns = [
            "caveat: the messages below",
            "do not respond to these messages",
            "kept model as",
        ]

        for pattern in noise_patterns:
            if pattern in content_lower:
                return True

        return False

    def _is_session_summary_message(self, message) -> bool:
        """Check if message content is a session continuation summary."""
        content = self._extract_text_content(message.content)
        if not content:
            return False

        content_lower = content.lower().strip()

        # Check for session continuation indicators
        session_summary_phrases = [
            "this session is being continued",
            "analysis:",
            "summary:",
            "looking through the conversation chronologically",
            "the conversation is summarized below",
            "primary request and intent",
            "key technical concepts",
            "files and code sections",
        ]

        return any(phrase in content_lower for phrase in session_summary_phrases)

    def _extract_text_content(self, content) -> str:
        """Extract clean text from message content."""
        if isinstance(content, str):
            return content.strip()
        elif isinstance(content, list):
            # Handle tool results and complex content
            parts = []
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        parts.append(item.get("text", ""))
            return " ".join(parts).strip()
        else:
            return ""

    def _calculate_turn_duration(self, turn: ConversationTurn) -> Optional[float]:
        """Calculate duration of a conversation turn in seconds."""
        if not turn.assistant_messages:
            return None
        
        start_time = turn.user_message.datetime
        end_time = turn.assistant_messages[-1].datetime
        
        return (end_time - start_time).total_seconds()
    
    def _calculate_turn_tokens(self, turn: ConversationTurn) -> Optional[int]:
        """Calculate total tokens used in a conversation turn."""
        total = 0
        found_any = False
        
        for msg in turn.assistant_messages:
            if msg.usage and isinstance(msg.usage, dict):
                # Sum different token types
                total += msg.usage.get('input_tokens', 0)
                total += msg.usage.get('output_tokens', 0)
                total += msg.usage.get('cache_creation_input_tokens', 0)
                total += msg.usage.get('cache_read_input_tokens', 0)
                found_any = True
        
        return total if found_any else None
    
    def filter_tool_messages(self, messages: List[Message], tool_filter: List[str]) -> List[Message]:
        """Filter messages to only include specified tool types."""
        if not tool_filter:
            return messages
        
        filtered = []
        for msg in messages:
            if msg.type != 'assistant' or not msg.tool_name:
                filtered.append(msg)
                continue
            
            if msg.tool_name in tool_filter:
                filtered.append(msg)
        
        return filtered
    
    def extract_git_info(self, messages: List[Message]) -> Dict[str, str]:
        """Extract git branch and other git info from messages."""
        git_info = {}
        
        for msg in messages:
            if msg.git_branch:
                git_info['branch'] = msg.git_branch
            if msg.cwd:
                git_info['cwd'] = msg.cwd
        
        return git_info
    
    def _hash_content(self, content: Any) -> str:
        """Generate a hash for message content for deduplication."""
        # Convert content to a stable string representation
        content_str = json.dumps(content, sort_keys=True) if not isinstance(content, str) else content
        return hashlib.sha256(content_str.encode()).hexdigest()[:16]
    
    def deduplicate_messages(self, messages: List[Message]) -> List[Message]:
        """Remove duplicate messages based on UUID and content hash."""
        seen_uuids = set()
        seen_content_hashes = set()
        unique_messages = []
        
        # Sort by timestamp to ensure chronological order and keep earliest duplicates
        sorted_messages = sorted(messages, key=lambda m: m.datetime)
        
        for msg in sorted_messages:
            is_duplicate = False
            
            # Check UUID first (most reliable)
            if msg.uuid and msg.uuid in seen_uuids:
                is_duplicate = True
            elif msg.uuid:
                seen_uuids.add(msg.uuid)
            
            # Fallback to content hash for messages without UUIDs or UUID collisions
            if not is_duplicate:
                content_hash = self._hash_content(msg.content)
                if content_hash in seen_content_hashes:
                    is_duplicate = True
                else:
                    seen_content_hashes.add(content_hash)
            
            if not is_duplicate:
                unique_messages.append(msg)
        
        return unique_messages
    
    def parse_multiple_files(self, file_paths: List[Path]) -> List[Message]:
        """Parse multiple session files and deduplicate messages."""
        all_messages = []
        
        for file_path in file_paths:
            file_messages = self.parse_file(file_path)
            all_messages.extend(file_messages)
        
        # Deduplicate and sort by timestamp
        deduplicated = self.deduplicate_messages(all_messages)
        
        # Categorize messages to identify subagent prompts, plans, etc.
        categorized = self.categorize_messages(deduplicated)
        
        # Update internal state with categorized messages
        self.messages = categorized
        self.message_map = {msg.uuid: msg for msg in categorized if msg.uuid}
        
        return categorized
    
    def categorize_messages(self, messages: List[Message]) -> List[Message]:
        """Categorize messages by their role (user, subagent, plan, tool_response, etc.)."""
        # Track Task tool prompts
        task_prompts = {}
        
        # First pass: collect Task tool prompts from assistant messages
        for message in messages:
            if message.type == 'assistant' and isinstance(message.content, list):
                for item in message.content:
                    if isinstance(item, dict) and item.get('type') == 'tool_use':
                        if item.get('name', '').lower() == 'task':
                            prompt = item.get('input', {}).get('prompt', '')
                            if prompt:
                                # Store first 150 chars as key for matching
                                task_prompts[prompt[:150]] = True
        
        # Second pass: categorize all messages
        categorized_messages = []
        for message in messages:
            # Create a copy to avoid modifying the original
            categorized_message = Message(
                uuid=message.uuid,
                parent_uuid=message.parent_uuid,
                type=message.type,
                timestamp=message.timestamp,
                content=message.content,
                session_id=message.session_id,
                cwd=message.cwd,
                git_branch=message.git_branch,
                tool_name=message.tool_name,
                tool_args=message.tool_args,
                usage=message.usage,
                message_category=self._determine_category(message, task_prompts)
            )
            categorized_messages.append(categorized_message)
        
        return categorized_messages
    
    def _determine_category(self, message: Message, task_prompts: dict) -> str:
        """Determine the category of a message."""
        # Tool responses
        if message.type == 'user' and isinstance(message.content, list):
            for item in message.content:
                if isinstance(item, dict) and item.get('type') == 'tool_result':
                    return 'tool_response'
        
        # Session continuation summaries
        if message.type == 'user':
            # Extract text from both string and list content
            content_text = ""
            if isinstance(message.content, str):
                content_text = message.content
            elif isinstance(message.content, list):
                for item in message.content:
                    if isinstance(item, dict) and item.get('type') == 'text':
                        content_text += item.get('text', '')
            
            # Only detect session summaries that start with the continuation phrase
            # and are long (>1000 chars), indicating they're system-generated summaries
            if (content_text.lower().startswith('this session is being continued') and 
                len(content_text) > 1000):
                return 'session_summary'
        
        # System/command noise
        if message.type == 'user' and isinstance(message.content, str):
            if (message.content.startswith('<command-') or 
                message.content.startswith('<local-command-') or
                'command-message' in message.content):
                return 'system_noise'
        
        # Check for subagent prompts (user messages matching Task prompts)
        if message.type == 'user' and isinstance(message.content, str):
            content_key = message.content[:150]
            if content_key in task_prompts:
                return 'subagent'
        
        # Assistant responses with plans
        if message.type == 'assistant' and isinstance(message.content, list):
            for item in message.content:
                if isinstance(item, dict):
                    # Check text items for plan keywords
                    if item.get('type') == 'text':
                        text = item.get('text', '').lower()
                        if any(phrase in text for phrase in [
                            '## plan', '# plan', 'implementation plan', 
                            '## comprehensive', '## step', '### step'
                        ]):
                            return 'plan'
                    # Check tool_use items for ExitPlanMode calls
                    elif item.get('type') == 'tool_use' and item.get('name') == 'ExitPlanMode':
                        return 'plan'
        
        # Default categories based on type
        if message.type == 'user':
            return 'user'
        elif message.type == 'assistant':
            return 'assistant'
        elif message.type == 'system':
            return 'system'
        elif message.type == 'summary':
            return 'session_summary'
        else:
            return 'other'