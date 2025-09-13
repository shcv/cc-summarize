"""No-AI summarizer that uses existing summaries and todos from session logs."""

import hashlib
from typing import List, Optional
from parser import Message, ConversationTurn
from cache import SummaryResult


class NoAISummarizer:
    """Extracts existing summaries and todos from session logs without AI."""

    def __init__(self):
        pass

    def summarize_turn(
        self, turn: ConversationTurn, session_id: str = ""
    ) -> SummaryResult:
        """Create summary using existing session data (todos, summaries)."""

        # Look for existing summary messages in the turn
        existing_summaries = []
        todo_activities = []

        # Check system messages for TodoWrite activities
        for msg in turn.system_messages:
            if self._is_todo_activity(msg):
                todo_activities.append(self._extract_todo_content(msg))

        # Check for summary type messages
        for msg in turn.assistant_messages + turn.system_messages:
            if msg.type == "summary":
                existing_summaries.append(str(msg.content))

        # Extract tool calls for context
        tool_calls = []
        for msg in turn.assistant_messages:
            if msg.tool_name:
                tool_calls.append(
                    f"{msg.tool_name}: {self._format_tool_args(msg.tool_args)}"
                )

        # Build summary from available information
        summary_parts = []

        if existing_summaries:
            summary_parts.extend(existing_summaries)

        if todo_activities:
            if summary_parts:
                summary_parts.append("Activities:")
            summary_parts.extend(todo_activities)

        if not summary_parts and tool_calls:
            # Fallback to simple tool listing if no summaries/todos available
            summary_parts = [
                f"Used tools: {', '.join([t.split(':')[0] for t in tool_calls[:5]])}"
            ]

        final_summary = (
            "\n".join(summary_parts)
            if summary_parts
            else "No summary information available in logs."
        )

        return SummaryResult(
            summary=final_summary,
            tool_calls=tool_calls,
            tokens_used=None,  # No API calls made
        )

    def _is_todo_activity(self, msg: Message) -> bool:
        """Check if a system message relates to todo activities."""
        if not msg.content:
            return False

        content_lower = str(msg.content).lower()
        todo_indicators = [
            "todowrite",
            "todo",
            "task",
            "working on",
            "implementing",
            "starting",
            "completing",
            "finished",
            "adding",
            "creating",
        ]

        return any(indicator in content_lower for indicator in todo_indicators)

    def _extract_todo_content(self, msg: Message) -> str:
        """Extract meaningful content from todo-related system messages."""
        content = str(msg.content)

        # Clean up formatting and extract key information
        if "todowrite" in content.lower():
            return "Updated todo list with current tasks"
        elif "completed successfully" in content.lower():
            return "Completed task successfully"
        elif "running" in content.lower() and "tool" in content.lower():
            return "Executing tools and commands"
        else:
            # Generic cleanup
            cleaned = content.replace("\u001b[1m", "").replace(
                "\u001b[22m", ""
            )  # Remove bold codes
            cleaned = cleaned.replace("[velcro handler]", "")
            cleaned = cleaned.strip()
            return cleaned[:100] + ("..." if len(cleaned) > 100 else "")

    def _format_tool_args(self, tool_args: Optional[dict]) -> str:
        """Format tool arguments concisely."""
        if not tool_args:
            return ""

        # Extract key information based on tool type
        if "file_path" in tool_args:
            return tool_args["file_path"]
        elif "command" in tool_args:
            cmd = tool_args["command"]
            return cmd[:50] + ("..." if len(cmd) > 50 else "")
        elif "pattern" in tool_args:
            return f"pattern: {tool_args['pattern']}"
        else:
            # Generic handling
            return str(tool_args)[:50] + ("..." if len(str(tool_args)) > 50 else "")

    def summarize_session(
        self, turns: List[ConversationTurn], session_id: str = ""
    ) -> List[SummaryResult]:
        """Summarize all turns in a session using existing log data."""
        results = []

        for turn in turns:
            result = self.summarize_turn(turn, session_id)
            results.append(result)

        return results


class UserOnlyExtractor:
    """Extracts only user prompts from sessions."""

    def __init__(self):
        pass

    def extract_user_prompts(self, turns: List[ConversationTurn]) -> List[dict]:
        """Extract clean user prompts with metadata, filtering out tool responses."""
        prompts = []
        prompt_number = 1  # Sequential numbering for actual prompts only

        for turn in turns:
            # Skip summary messages (type='summary' from session continuation)
            if turn.user_message.type == "summary":
                continue

            # Skip turns that are actually tool responses
            if self._is_tool_response(turn.user_message):
                continue

            # Extract clean user content
            content = self._extract_user_content(turn.user_message.content)

            # Skip empty or very short content
            if not content or len(content.strip()) < 5:
                continue

            # Skip system/command noise
            if self._is_system_noise(content):
                continue

            # Skip session continuation summaries
            if self._is_session_summary(content):
                continue

            prompt_data = {
                "turn_number": prompt_number,
                "timestamp": turn.user_message.timestamp,
                "content": content,
                "uuid": turn.user_message.uuid,
            }

            # Add optional metadata
            if turn.user_message.cwd:
                prompt_data["cwd"] = turn.user_message.cwd
            if turn.user_message.git_branch:
                prompt_data["git_branch"] = turn.user_message.git_branch

            prompts.append(prompt_data)
            prompt_number += 1

        # Final deduplication pass on extracted prompts
        return self._deduplicate_prompts(prompts)

    def _deduplicate_prompts(self, prompts: List[dict]) -> List[dict]:
        """Remove duplicate prompts based on content similarity."""
        if not prompts:
            return prompts

        seen_content_hashes = set()
        unique_prompts = []

        # Sort by timestamp to keep earliest occurrence
        sorted_prompts = sorted(prompts, key=lambda p: p.get("timestamp", ""))

        for prompt in sorted_prompts:
            content = prompt["content"]
            # Use the same hashing approach as the parser
            content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]

            if content_hash not in seen_content_hashes:
                seen_content_hashes.add(content_hash)
                unique_prompts.append(prompt)

        # Renumber the prompts after deduplication
        for i, prompt in enumerate(unique_prompts, 1):
            prompt["turn_number"] = i

        return unique_prompts

    def _is_tool_response(self, message) -> bool:
        """Check if a user message is actually a tool response."""
        content = message.content

        if isinstance(content, list) and content:
            # Check if the first item is a tool_result
            first_item = content[0]
            if isinstance(first_item, dict) and first_item.get("type") == "tool_result":
                return True

        return False

    def _is_system_noise(self, content: str) -> bool:
        """Check if content is system noise rather than actual user input."""
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

    def _is_session_summary(self, content: str) -> bool:
        """Check if content is a session continuation summary."""
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

    def _extract_user_content(self, content) -> str:
        """Extract clean text from user message content."""
        if isinstance(content, str):
            # Clean up session hooks and other noise
            content = content.replace("<session-start-hook>", "")
            content = content.replace("</session-start-hook>", "")
            return content.strip()

        elif isinstance(content, list):
            # Handle tool results and complex content
            parts = []
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        parts.append(item.get("text", ""))
                    elif item.get("type") == "tool_result":
                        # Skip tool results in user display - they're noise
                        continue
                    else:
                        # Other content types
                        parts.append(str(item))
                else:
                    parts.append(str(item))
            return "\n".join(parts).strip()

        else:
            return str(content)


class MessageExtractor:
    """Extracts messages by category from sessions."""

    def __init__(self, no_truncate: bool = False):
        self.no_truncate = no_truncate

    def extract_messages(
        self, turns: List[ConversationTurn], categories: List[str] = None
    ) -> List[dict]:
        """Extract messages based on specified categories.

        Args:
            turns: List of conversation turns
            categories: List of categories to extract. If None, extracts all.
                       Valid categories: 'user', 'subagent', 'plan', 'assistant', 'session_summary', 'tool_response'
        """
        if categories is None:
            categories = ["user", "subagent", "plan", "assistant"]

        # Always exclude noise categories
        excluded_categories = {"system_noise", "tool_response"}

        messages = []
        message_number = 1

        for turn in turns:
            # Process user message
            if (
                turn.user_message.message_category in categories
                and turn.user_message.message_category not in excluded_categories
            ):
                content = self._extract_content(turn.user_message.content)
                if content and len(content.strip()) > 5:
                    message_data = {
                        "number": message_number,
                        "category": turn.user_message.message_category,
                        "timestamp": turn.user_message.timestamp,
                        "content": content,
                        "uuid": turn.user_message.uuid,
                    }

                    # Add optional metadata
                    if turn.user_message.cwd:
                        message_data["cwd"] = turn.user_message.cwd
                    if turn.user_message.git_branch:
                        message_data["git_branch"] = turn.user_message.git_branch

                    messages.append(message_data)
                    message_number += 1

            # Process assistant messages (for plans, etc.)
            for assistant_msg in turn.assistant_messages:
                if (
                    assistant_msg.message_category in categories
                    and assistant_msg.message_category not in excluded_categories
                ):
                    content = self._extract_content(assistant_msg.content)
                    if content and len(content.strip()) > 5:
                        message_data = {
                            "number": message_number,
                            "category": assistant_msg.message_category,
                            "timestamp": assistant_msg.timestamp,
                            "content": content,
                            "uuid": assistant_msg.uuid,
                        }

                        messages.append(message_data)
                        message_number += 1

        return messages

    def _extract_content(self, content) -> str:
        """Extract clean text from message content."""
        if isinstance(content, str):
            # Clean up session hooks and other noise
            content = content.replace("<session-start-hook>", "")
            content = content.replace("</session-start-hook>", "")
            return content.strip()

        elif isinstance(content, list):
            # Handle complex content structures
            parts = []
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        parts.append(item.get("text", ""))
                    elif item.get("type") == "tool_result":
                        # Skip tool results for now
                        continue
                    elif item.get("type") == "tool_use":
                        # Format tool use nicely
                        tool_name = item.get("name", "Unknown")
                        tool_input = item.get("input", {})

                        # Special handling for specific tools
                        if tool_name == "ExitPlanMode":
                            # Extract plan content from ExitPlanMode tool calls
                            if "plan" in tool_input:
                                parts.append(tool_input["plan"])
                        elif tool_name == "Task":
                            # Format Task tool calls
                            desc = tool_input.get("description", "")
                            prompt = tool_input.get("prompt", "")
                            subagent = tool_input.get("subagent_type", "")
                            if desc:
                                parts.append(f"[Task: {desc}]")
                            if subagent:
                                parts.append(f"Using {subagent} agent")
                            if prompt:
                                if self.no_truncate:
                                    parts.append(f"Prompt: {prompt}")
                                else:
                                    parts.append(f"Prompt: {prompt}")
                        elif tool_name == "Write":
                            # Format Write tool calls
                            file_path = tool_input.get("file_path", "")
                            content = tool_input.get("content", "")
                            parts.append(f"Writing to {file_path}")
                            if content:
                                if self.no_truncate:
                                    parts.append(f"Content: {content}")
                                else:
                                    content_preview = content[:100]
                                    suffix = "..." if len(content) > 100 else ""
                                    parts.append(
                                        f"Content preview: {content_preview}{suffix}"
                                    )
                        elif tool_name == "Edit":
                            # Format Edit tool calls
                            file_path = tool_input.get("file_path", "")
                            old_str = tool_input.get("old_string", "")
                            new_str = tool_input.get("new_string", "")
                            parts.append(f"Editing {file_path}")
                            if old_str:
                                if self.no_truncate:
                                    parts.append(f"Replacing: {old_str}")
                                else:
                                    truncated = old_str[:50]
                                    suffix = "..." if len(old_str) > 50 else ""
                                    parts.append(f"Replacing: {truncated}{suffix}")
                            if new_str:
                                if self.no_truncate:
                                    parts.append(f"With: {new_str}")
                                else:
                                    truncated = new_str[:50]
                                    suffix = "..." if len(new_str) > 50 else ""
                                    parts.append(f"With: {truncated}{suffix}")
                        elif tool_name == "Read":
                            # Format Read tool calls
                            file_path = tool_input.get("file_path", "")
                            parts.append(f"Reading {file_path}")
                        elif tool_name == "Bash":
                            # Format Bash tool calls
                            command = tool_input.get("command", "")
                            desc = tool_input.get("description", "")
                            if desc:
                                parts.append(f"Running: {desc}")
                            elif command:
                                if self.no_truncate:
                                    parts.append(f"$ {command}")
                                else:
                                    truncated = (
                                        command[:100] if len(command) > 100 else command
                                    )
                                    suffix = "..." if len(command) > 100 else ""
                                    parts.append(f"$ {truncated}{suffix}")
                        elif tool_name == "Grep":
                            # Format Grep tool calls
                            pattern = tool_input.get("pattern", "")
                            path = tool_input.get("path", ".")
                            parts.append(f"Searching for '{pattern}' in {path}")
                        elif tool_name == "Glob":
                            # Format Glob tool calls
                            pattern = tool_input.get("pattern", "")
                            path = tool_input.get("path", ".")
                            parts.append(
                                f"Finding files matching '{pattern}' in {path}"
                            )
                        else:
                            # Generic tool formatting
                            parts.append(f"[{tool_name}]")
                            # Add key parameters if they exist
                            for key in [
                                "file_path",
                                "command",
                                "pattern",
                                "query",
                                "description",
                            ]:
                                if key in tool_input:
                                    value = str(tool_input[key])
                                    if self.no_truncate:
                                        parts.append(f"  {key}: {value}")
                                    else:
                                        truncated = (
                                            value[:100] if len(value) > 100 else value
                                        )
                                        suffix = "..." if len(value) > 100 else ""
                                        parts.append(f"  {key}: {truncated}{suffix}")
                    else:
                        # Other content types - format better
                        if "type" in item:
                            parts.append(f"[{item['type']}]")
                        else:
                            parts.append(str(item))
                else:
                    parts.append(str(item))
            return "\n".join(parts).strip()

        else:
            return str(content)
