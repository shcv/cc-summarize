"""AI-powered summarization using Claude 3.5 Haiku."""

import os
import asyncio
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
import json
import hashlib

from anthropic import Anthropic
from parser import Message, ConversationTurn
from cache import SummaryCache, SummaryResult


# Tool filtering based on detail level
MINIMAL_TOOLS = ['Edit', 'MultiEdit', 'Write', 'Bash']
NORMAL_TOOLS = MINIMAL_TOOLS + ['Read', 'Grep', 'Glob', 'LS', 'Task']
DETAILED_TOOLS = None  # Show all tools


class SessionSummarizer:
    """Summarizes Claude Code sessions using Claude 3.5 Haiku."""
    
    def __init__(self, api_key: Optional[str] = None, cache_dir: Optional[str] = None):
        self.api_key = api_key or os.getenv('ANTHROPIC_API_KEY')
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY is required")
        
        self.client = Anthropic(api_key=self.api_key)
        self.model = "claude-3-5-haiku-20241022"
        
        # Initialize cache
        self.cache = SummaryCache(cache_dir)
        
        # Cache system prompts (these don't change)
        self._system_prompts = {}
    
    def _get_system_prompt(self, detail_level: str) -> str:
        """Get cached system prompt for the given detail level."""
        if detail_level in self._system_prompts:
            return self._system_prompts[detail_level]
        
        if detail_level == 'minimal':
            prompt = """You are summarizing Claude Code assistant actions between user messages. 
Focus ONLY on file edits (Edit, MultiEdit, Write) and bash commands (Bash). 
Summarize each action in one line, focusing on what was changed or executed.
Ignore all other tool calls and system messages.
Be very concise and specific about file names and key changes."""
            
        elif detail_level == 'normal':
            prompt = """You are summarizing Claude Code assistant actions between user messages.
Include file operations (Edit, MultiEdit, Write, Read), bash commands (Bash), and search operations (Grep, Glob, LS).
Summarize the overall flow of actions taken by the assistant.
For tool calls, briefly describe what was done without including full outputs.
Be concise but capture the key activities and their purpose."""
            
        else:  # detailed
            prompt = """You are summarizing Claude Code assistant actions between user messages.
Include ALL tool calls and assistant reasoning.
Provide a comprehensive summary of what the assistant did, including:
- All tool calls and their purposes
- Any reasoning or explanations given
- The overall approach taken
- Key decisions made
Be thorough but organized."""
        
        self._system_prompts[detail_level] = prompt
        return prompt
    
    def _filter_tools(self, messages: List[Message], detail_level: str) -> List[Message]:
        """Filter messages based on detail level tool requirements."""
        if detail_level == 'detailed':
            return messages  # Include everything
        
        tool_filter = MINIMAL_TOOLS if detail_level == 'minimal' else NORMAL_TOOLS
        
        filtered = []
        for msg in messages:
            if msg.type != 'assistant':
                filtered.append(msg)
                continue
            
            # Include message if it has no tool call or if tool is in filter
            if not msg.tool_name or msg.tool_name in tool_filter:
                filtered.append(msg)
        
        return filtered
    
    def _extract_tool_calls(self, messages: List[Message]) -> List[str]:
        """Extract tool call descriptions from messages."""
        tool_calls = []
        
        for msg in messages:
            if msg.type == 'assistant' and msg.tool_name:
                # Create a brief description of the tool call
                if msg.tool_name == 'Edit' and msg.tool_args:
                    file_path = msg.tool_args.get('file_path', '')
                    tool_calls.append(f"Edit: {file_path}")
                
                elif msg.tool_name == 'Bash' and msg.tool_args:
                    command = msg.tool_args.get('command', '')[:50]
                    tool_calls.append(f"Bash: {command}...")
                
                elif msg.tool_name == 'Read' and msg.tool_args:
                    file_path = msg.tool_args.get('file_path', '')
                    tool_calls.append(f"Read: {file_path}")
                
                else:
                    # Generic tool description
                    tool_calls.append(f"{msg.tool_name}: {str(msg.tool_args)[:50]}...")
        
        return tool_calls
    
    def _build_content_for_summary(self, messages: List[Message]) -> str:
        """Build content string for summarization."""
        content_parts = []
        
        for msg in messages:
            if msg.type == 'assistant':
                # Extract text content
                if isinstance(msg.content, list):
                    text_parts = []
                    for item in msg.content:
                        if isinstance(item, dict):
                            if item.get('type') == 'text':
                                text_parts.append(item.get('text', ''))
                            elif item.get('type') == 'tool_use':
                                tool_name = item.get('name', 'unknown')
                                tool_input = item.get('input', {})
                                text_parts.append(f"[Tool: {tool_name} with {tool_input}]")
                    
                    if text_parts:
                        content_parts.append('\n'.join(text_parts))
                
                elif isinstance(msg.content, str):
                    content_parts.append(msg.content)
            
            elif msg.type == 'system' and msg.content:
                # Include some system messages for context
                content_parts.append(f"[System: {msg.content}]")
        
        return '\n\n'.join(content_parts)
    
    def summarize_turn(self, turn: ConversationTurn, detail_level: str = 'normal', session_id: str = '') -> SummaryResult:
        """Summarize a single conversation turn with caching."""
        # Filter messages based on detail level
        filtered_messages = self._filter_tools(
            turn.assistant_messages + turn.system_messages, 
            detail_level
        )
        
        if not filtered_messages:
            return SummaryResult(
                summary="No relevant assistant actions found.",
                tool_calls=[]
            )
        
        # Extract tool calls
        tool_calls = self._extract_tool_calls(turn.assistant_messages)
        
        # Build content for summarization
        content = self._build_content_for_summary(filtered_messages)
        
        if not content.strip():
            return SummaryResult(
                summary="No content to summarize.",
                tool_calls=tool_calls
            )
        
        # Check cache first
        cached_result = self.cache.get_summary(session_id, content, detail_level)
        if cached_result:
            # Update tool_calls from current analysis (they might have changed)
            cached_result.tool_calls = tool_calls
            return cached_result
        
        try:
            # Make API call to Claude
            response = self.client.messages.create(
                model=self.model,
                max_tokens=500,  # Keep summaries concise
                temperature=0.1,  # Low temperature for consistent summaries
                system=self._get_system_prompt(detail_level),
                messages=[{
                    "role": "user",
                    "content": f"Summarize these Claude Code assistant actions:\n\n{content}"
                }]
            )
            
            summary = response.content[0].text.strip()
            tokens_used = response.usage.input_tokens + response.usage.output_tokens
            
            result = SummaryResult(
                summary=summary,
                tool_calls=tool_calls,
                tokens_used=tokens_used
            )
            
            # Cache the result
            self.cache.store_summary(session_id, content, detail_level, result)
            
            return result
            
        except Exception as e:
            result = SummaryResult(
                summary="",
                tool_calls=tool_calls,
                error=str(e)
            )
            
            # Cache the error too
            self.cache.store_summary(session_id, content, detail_level, result)
            
            return result
    
    def summarize_session(self, turns: List[ConversationTurn], detail_level: str = 'normal', session_id: str = '') -> List[SummaryResult]:
        """Summarize all turns in a session."""
        results = []
        
        for turn in turns:
            result = self.summarize_turn(turn, detail_level, session_id)
            results.append(result)
        
        return results
    
    def batch_summarize_turns(self, turns: List[ConversationTurn], detail_level: str = 'normal', batch_size: int = 5) -> List[SummaryResult]:
        """Batch multiple turns together for more efficient API usage.
        
        Note: This combines multiple assistant response sections into one summary.
        Use with caution as it may lose some granularity.
        """
        results = []
        
        for i in range(0, len(turns), batch_size):
            batch = turns[i:i + batch_size]
            
            # Combine all assistant messages from the batch
            all_messages = []
            all_tool_calls = []
            
            for turn in batch:
                filtered = self._filter_tools(
                    turn.assistant_messages + turn.system_messages,
                    detail_level
                )
                all_messages.extend(filtered)
                all_tool_calls.extend(self._extract_tool_calls(turn.assistant_messages))
            
            if not all_messages:
                # Add empty results for this batch
                for _ in batch:
                    results.append(SummaryResult(
                        summary="No relevant assistant actions found.",
                        tool_calls=[]
                    ))
                continue
            
            # Build content and summarize
            content = self._build_content_for_summary(all_messages)
            
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=1000,  # Larger for batch summaries
                    temperature=0.1,
                    system=self._get_system_prompt(detail_level),
                    messages=[{
                        "role": "user",
                        "content": f"Summarize these Claude Code assistant actions from {len(batch)} conversation turns:\n\n{content}"
                    }]
                )
                
                summary = response.content[0].text.strip()
                tokens_used = response.usage.input_tokens + response.usage.output_tokens
                
                # Distribute the summary across all turns in the batch
                # (This is a simplification - in practice you might want to split it)
                for j, turn in enumerate(batch):
                    turn_tool_calls = self._extract_tool_calls(turn.assistant_messages)
                    results.append(SummaryResult(
                        summary=f"[Batch {i//batch_size + 1}, Turn {j+1}] {summary}",
                        tool_calls=turn_tool_calls,
                        tokens_used=tokens_used // len(batch) if j == 0 else 0
                    ))
                
            except Exception as e:
                # Add error results for this batch
                for turn in batch:
                    turn_tool_calls = self._extract_tool_calls(turn.assistant_messages)
                    results.append(SummaryResult(
                        summary="",
                        tool_calls=turn_tool_calls,
                        error=str(e)
                    ))
        
        return results