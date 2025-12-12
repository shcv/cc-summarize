"""Tool call compaction utilities."""

from pathlib import Path
from typing import Dict, List, Any, Optional


def compact_tool_calls(
    messages: List[Any],
    detail_level: str = 'normal',
    file_descriptions: Optional[Dict[str, str]] = None
) -> List[str]:
    """Compact tool calls by grouping file operations per file.

    For 'normal' detail level, groups Read/Edit/Write/MultiEdit by file path
    and shows a compact summary like "Read + Edit: filename.py"

    For 'detailed' level, returns all tool calls individually.
    For 'minimal' level, only shows file edits and bash commands.

    Args:
        messages: List of Message objects with tool_name and tool_args attributes
        detail_level: One of 'minimal', 'normal', 'detailed'
        file_descriptions: Optional dict mapping filename to AI-generated description
                          of what was done to that file

    Returns:
        List of compacted tool call descriptions
    """
    if file_descriptions is None:
        file_descriptions = {}
    if detail_level == 'detailed':
        # Return all tool calls individually
        tool_calls = []
        for msg in messages:
            tool_name = getattr(msg, 'tool_name', None)
            if tool_name:
                tool_args = getattr(msg, 'tool_args', None) or {}
                tool_desc = f"{tool_name}"
                args_summary = _summarize_tool_args(tool_name, tool_args)
                if args_summary:
                    tool_desc += f": {args_summary}"
                tool_calls.append(tool_desc)
        return tool_calls

    # Group file operations by path
    file_ops: Dict[str, List[str]] = {}  # path -> list of operations
    other_tools: List[str] = []

    file_tools = {'Read', 'Edit', 'MultiEdit', 'Write'}

    for msg in messages:
        tool_name = getattr(msg, 'tool_name', None)
        if not tool_name:
            continue

        tool_args = getattr(msg, 'tool_args', None) or {}

        if tool_name in file_tools:
            file_path = tool_args.get('file_path', '')
            if file_path:
                if file_path not in file_ops:
                    file_ops[file_path] = []
                if tool_name not in file_ops[file_path]:
                    file_ops[file_path].append(tool_name)
        elif detail_level == 'minimal':
            # For minimal, only include Bash commands
            if tool_name == 'Bash':
                desc = tool_args.get('description', '')
                cmd = tool_args.get('command', '')[:50]
                other_tools.append(f"Bash: {desc or cmd}")
        else:
            # For normal, include other tools but compacted (deduplicated)
            if tool_name == 'Bash':
                desc = tool_args.get('description', '')
                cmd = tool_args.get('command', '')[:50]
                tool_str = f"Bash: {desc or cmd}"
                if tool_str not in other_tools:
                    other_tools.append(tool_str)
            elif tool_name in ['Grep', 'Glob']:
                pattern = tool_args.get('pattern', '')
                tool_str = f"{tool_name}: {pattern}"
                if tool_str not in other_tools:
                    other_tools.append(tool_str)
            elif tool_name == 'Task':
                desc = tool_args.get('description', '')
                other_tools.append(f"Task: {desc}")

    # Build compacted output
    result = []

    # Add file operations (sorted by operation order: Read -> Edit -> MultiEdit -> Write)
    op_order = ['Read', 'Edit', 'MultiEdit', 'Write']
    for file_path, ops in file_ops.items():
        display_path = Path(file_path).name
        sorted_ops = sorted(set(ops), key=lambda x: op_order.index(x) if x in op_order else 99)
        ops_str = ' + '.join(sorted_ops)

        # Check if we have an AI-generated description for this file
        description = file_descriptions.get(display_path, '')
        if description:
            result.append(f"{ops_str}: {display_path} — {description}")
        else:
            result.append(f"{ops_str}: {display_path}")

    # Add other tools
    result.extend(other_tools)

    return result


def _summarize_edit(old_string: str, new_string: str) -> str:
    """Generate a one-liner summary of what an edit did."""
    if not old_string and new_string:
        # Pure addition
        lines = new_string.strip().split('\n')
        if len(lines) == 1:
            preview = lines[0][:40]
            return f"added: {preview}..." if len(lines[0]) > 40 else f"added: {preview}"
        return f"added {len(lines)} lines"

    if old_string and not new_string:
        # Pure deletion
        lines = old_string.strip().split('\n')
        if len(lines) == 1:
            return "deleted line"
        return f"deleted {len(lines)} lines"

    if old_string and new_string:
        old_lines = old_string.split('\n')
        new_lines = new_string.split('\n')

        # Check for simple rename/replace patterns
        old_stripped = old_string.strip()
        new_stripped = new_string.strip()

        # Single line change
        if len(old_lines) == 1 and len(new_lines) == 1:
            # Look for common patterns
            if 'def ' in old_stripped and 'def ' in new_stripped:
                return "renamed function"
            if 'class ' in old_stripped and 'class ' in new_stripped:
                return "renamed class"
            if 'import ' in old_stripped and 'import ' in new_stripped:
                return "changed import"
            return "changed line"

        # Multi-line changes
        diff = len(new_lines) - len(old_lines)
        if diff > 0:
            return f"expanded ({diff:+d} lines)"
        elif diff < 0:
            return f"reduced ({diff:+d} lines)"
        else:
            return f"modified {len(old_lines)} lines"

    return "modified"


def _summarize_tool_args(tool_name: str, tool_args: Dict) -> str:
    """Create a brief summary of tool arguments."""
    if tool_name == 'Edit':
        file_path = tool_args.get('file_path', '')
        filename = Path(file_path).name if file_path else ''
        old_string = tool_args.get('old_string', '')
        new_string = tool_args.get('new_string', '')
        edit_summary = _summarize_edit(old_string, new_string)
        return f"{filename} ({edit_summary})"
    elif tool_name == 'MultiEdit':
        file_path = tool_args.get('file_path', '')
        filename = Path(file_path).name if file_path else ''
        edits = tool_args.get('edits', [])
        return f"{filename} ({len(edits)} edits)"
    elif tool_name == 'Write':
        file_path = tool_args.get('file_path', '')
        filename = Path(file_path).name if file_path else ''
        content = tool_args.get('content', '')
        lines = len(content.split('\n')) if content else 0
        return f"{filename} ({lines} lines)"
    elif tool_name == 'Read':
        file_path = tool_args.get('file_path', '')
        return Path(file_path).name if file_path else ''
    elif tool_name == 'Bash':
        desc = tool_args.get('description', '')
        command = tool_args.get('command', '')[:80]
        return desc or command
    elif tool_name in ['Grep', 'Glob']:
        return tool_args.get('pattern', '')
    elif tool_name == 'Task':
        return tool_args.get('description', '')
    return ""
