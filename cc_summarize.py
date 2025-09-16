#!/usr/bin/env python3
"""
Claude Code Session Summarizer

A tool for managing, viewing, and summarizing Claude Code sessions.
"""

import os
import sys
import click
from typing import List, Optional
from dotenv import load_dotenv
from pathlib import Path
from rich.console import Console

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from session_finder import list_sessions, find_session_by_id
from parser import SessionParser
from no_ai_summarizer import NoAISummarizer, UserOnlyExtractor, MessageExtractor
from cache import SummaryCache
from date_parser import parse_since_date, format_since_description
from formatters.terminal import TerminalFormatter
from formatters.markdown import MarkdownFormatter
from formatters.jsonl import JSONLFormatter
from formatters.plain import PlainFormatter, should_use_plain_output

# Load environment variables from .env file
load_dotenv()

# Initialize console for rich output
console = Console()

@click.command()
@click.option('--project', '-p', type=click.Path(exists=True, file_okay=False, dir_okay=True), 
              default='.', help='Project directory (default: current)')
@click.option('--session', '-s', help='Specific session ID to process')
@click.option('--from-date', '--from', 'from_date', type=click.DateTime(formats=['%Y-%m-%d']),
              help='Start date filter (YYYY-MM-DD)')
@click.option('--to-date', '--to', 'to_date', type=click.DateTime(formats=['%Y-%m-%d']),
              help='End date filter (YYYY-MM-DD)')
@click.option('--format', 'output_format', type=click.Choice(['auto', 'terminal', 'markdown', 'jsonl', 'plain']), 
              default='auto', help='Output format (auto detects plain when piping)')
@click.option('--with-plans', is_flag=True, help='Include assistant plan responses')
@click.option('--with-summaries', is_flag=True, help='Include session summary messages')
@click.option('--with-subagent', is_flag=True, help='Include subagent prompts')
@click.option('--with-assistant', is_flag=True, help='Include all assistant responses')
@click.option('--with-all', is_flag=True, help='Include all message types')
@click.option('--summarize', type=click.Choice(['minimal', 'normal', 'detailed']), 
              help='Generate AI summaries (requires API key). Default: normal level')
@click.option('--backend', type=click.Choice(['auto', 'api', 'sdk']), default='auto',
              help='Backend for AI summaries: auto (SDK if available, else API), api (Anthropic API), sdk (Claude Code SDK)')
@click.option('--plain', is_flag=True, help='Force plain text output (auto-enabled when piping)')
@click.option('--separator', default='—————————————————————————', help='Separator between prompts in plain mode (default: em-dashes)')
@click.option('--output', '-o', type=click.File('w'), default='-', 
              help='Output file (default: stdout)')
@click.option('--metadata', is_flag=True, help='Include timestamps, durations, and token counts')
@click.option('--interactive', '-i', is_flag=True, help='Launch interactive wizard')
@click.option('--list', 'list_sessions', is_flag=True, help='List available sessions for project')
@click.option('--retry-failed', is_flag=True, help='Retry failed summaries from cache')
@click.option('--clear-cache', is_flag=True, help='Clear all summary cache (all projects)')
@click.option('--redo', is_flag=True, help='Regenerate summaries, ignoring cache (for current filters)')
@click.option('--verbose', '-v', is_flag=True, help='Show verbose output (e.g., full session IDs)')
@click.option('--no-truncate', is_flag=True, help='Show full content without truncation')
@click.option('--since', help='Include only messages since date/time (e.g., 1d, 2h, 30m, 1w, 2024-12-01)')
@click.version_option(version='0.1.0')
def main(project, session, from_date, to_date, output_format, with_plans, with_summaries, with_subagent,
         with_assistant, with_all, summarize, backend, plain, separator, output, metadata, interactive, list_sessions,
         retry_failed, clear_cache, redo, verbose, no_truncate, since):
    """Claude Code Session Summarizer
    
    Manage, view, and summarize Claude Code sessions for a project.
    """
    
    project_path = Path(project).resolve()
    
    # Determine actual output format
    actual_format = output_format
    if output_format == 'auto':
        actual_format = 'plain' if (plain or should_use_plain_output()) else 'terminal'
    elif plain:
        actual_format = 'plain'
    
    try:
        # Validate conflicting options
        if redo and clear_cache:
            click.echo("Error: Cannot use --redo and --clear-cache together. Use one or the other.", err=True)
            sys.exit(1)

        if redo and not summarize:
            click.echo("Error: --redo flag requires --summarize option (nothing to regenerate without AI summaries).", err=True)
            sys.exit(1)

        # Handle cache operations first
        if clear_cache:
            # Only pass project_path if user explicitly specified a project, otherwise do global clear
            project_for_cache = project_path if project != '.' else None
            handle_clear_cache(session, project_for_cache)
            return
        
        # Handle session listing
        if list_sessions:
            handle_list_sessions(project_path, from_date, to_date, actual_format, separator, output, verbose)
            return
        
        # Handle interactive mode
        if interactive:
            click.echo("Interactive mode not implemented yet.", err=True)
            sys.exit(1)
        
        # Validate API key for AI summarization operations (only needed when --summarize is used with API backend)
        api_key = os.getenv('ANTHROPIC_API_KEY')
        if summarize and backend != 'sdk':
            # Check if we need API key (for 'api' or 'auto' modes)
            if backend == 'api' and not api_key:
                click.echo("Error: ANTHROPIC_API_KEY environment variable is required for API backend.", err=True)
                click.echo("Set it in your environment or create a .env file.", err=True)
                click.echo("Use --backend sdk to use Claude Code SDK instead (no API key required).", err=True)
                sys.exit(1)
            elif backend == 'auto':
                # Check if SDK is available for auto mode
                from src.sdk_summarizer import SDKAvailability
                if not SDKAvailability.is_available() and not api_key:
                    click.echo("Error: Neither Claude Code SDK nor API key is available.", err=True)
                    click.echo("Either:", err=True)
                    click.echo("  1. Set ANTHROPIC_API_KEY environment variable for API access", err=True)
                    click.echo("  2. Install Claude Code: npm install -g @anthropic-ai/claude-code", err=True)
                    click.echo("Use without --summarize flag to extract messages only (no AI required).", err=True)
                    sys.exit(1)
        
        # Handle retry failed summaries
        if retry_failed:
            detail_level = summarize if summarize else 'normal'
            handle_retry_failed(project_path, session, detail_level)
            return
        
        # Convert new parameters to processing logic
        detail_level = summarize if summarize else 'normal'
        user_only_mode = not bool(summarize)  # Default is user-only unless --summarize is used
        
        # Build categories list from new flags
        categories = ['user']  # Always include user messages
        if with_plans:
            categories.append('plan')
        if with_summaries:
            categories.append('session_summary') 
        if with_subagent:
            categories.append('subagent')
        if with_assistant:
            categories.append('assistant')
        if with_all:
            categories = ['user', 'subagent', 'plan', 'assistant', 'session_summary']

        # Parse since date if provided
        since_date = None
        if since:
            try:
                since_date = parse_since_date(since)
                description = format_since_description(since, since_date)
                click.echo(f"Filtering messages {description}", err=True)
            except ValueError as e:
                click.echo(f"Error: {e}", err=True)
                sys.exit(1)

        # Main processing logic
        handle_summarization(
            project_path, session, from_date, to_date, detail_level, actual_format,
            categories, separator, output, metadata, api_key, bool(summarize), no_truncate, backend, since_date, redo
        )
        
    except KeyboardInterrupt:
        click.echo("\nOperation cancelled by user.", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        sys.exit(1)


def get_summarizer(backend: str, api_key: Optional[str] = None, detail_level: str = 'normal', project_path: Optional[str] = None):
    """Get the appropriate summarizer based on backend selection.
    
    Args:
        backend: Backend choice ('auto', 'api', 'sdk')
        api_key: Optional API key for Anthropic API
        detail_level: Level of detail for summaries
        
    Returns:
        Summarizer instance (SessionSummarizer or SDKSummarizer)
    """
    from src.sdk_summarizer import SDKAvailability, SDKSummarizer
    
    if backend == 'auto':
        # Try SDK first
        if SDKAvailability.is_available():
            try:
                click.echo("Using Claude Code SDK for summarization", err=True)
                return SDKSummarizer(project_path=project_path)
            except Exception as e:
                click.echo(f"SDK initialization failed: {e}, falling back to API", err=True)
                # Fall through to API
        
        # Fallback to API
        if api_key:
            click.echo("Using Anthropic API for summarization", err=True)
            from summarizer import SessionSummarizer
            return SessionSummarizer(api_key)
        else:
            raise ValueError("No API key provided and Claude Code SDK not available")
            
    elif backend == 'sdk':
        if not SDKAvailability.is_available():
            error_msg = SDKAvailability.get_error_message()
            raise RuntimeError(f"Claude Code SDK not available: {error_msg}")
        click.echo("Using Claude Code SDK for summarization", err=True)
        return SDKSummarizer(project_path=project_path)
        
    else:  # backend == 'api'
        if not api_key:
            raise ValueError("API key required for API backend")
        click.echo("Using Anthropic API for summarization", err=True)
        from summarizer import SessionSummarizer
        return SessionSummarizer(api_key)


def handle_clear_cache(session_id: str = None, project_path: Path = None) -> None:
    """Handle cache clearing operations."""
    cache = SummaryCache()

    if session_id:
        cleared = cache.clear_cache(session_id)
        click.echo(f"Cleared {cleared} cache entries for session {session_id}")
    elif project_path:
        # Clear cache for this specific project
        sessions = list_sessions(str(project_path))
        if not sessions:
            click.echo("No sessions found for this project - nothing to clear.")
            return

        session_ids = [Path(s.get('file_path', '')).stem for s in sessions if s.get('file_path')]
        if session_ids:
            cleared = cache.clear_cache_for_sessions(session_ids)
            project_name = project_path.name
            click.echo(f"Cleared {cleared} cache entries for project '{project_name}' ({len(session_ids)} sessions)")
        else:
            click.echo("No valid session IDs found for this project.")
    else:
        # Show cache stats first
        stats = cache.get_cache_stats()
        if stats['successful_summaries'] == 0 and stats['failed_summaries'] == 0:
            click.echo("Cache is already empty.")
            return

        # Confirm before clearing all
        if click.confirm(f"Clear all cache ({stats['successful_summaries'] + stats['failed_summaries']} entries)?"):
            cache.clear_all_cache()
            click.echo("Cache cleared successfully.")
        else:
            click.echo("Cache clearing cancelled.")


def handle_list_sessions(project_path: Path, from_date, to_date, output_format: str, separator: str, output_file, verbose: bool = False) -> None:
    """Handle session listing operations."""
    sessions = list_sessions(str(project_path), from_date, to_date)
    
    if output_format == 'terminal':
        formatter = TerminalFormatter(console)
        formatter.format_session_list(sessions, verbose)
        
        # Also show cache stats
        cache = SummaryCache()
        stats = cache.get_cache_stats()
        formatter.format_cache_stats(stats)
        
    elif output_format == 'plain':
        formatter = PlainFormatter(separator)
        formatter.format_session_list(sessions, output_file, verbose)
        
    elif output_format == 'markdown':
        formatter = MarkdownFormatter()
        formatter.format_session_list(sessions, output_file, verbose)
        
    elif output_format == 'jsonl':
        formatter = JSONLFormatter()
        formatter.format_session_list(sessions, output_file, verbose)


def handle_retry_failed(project_path: Path, session_id: str, detail_level: str) -> None:
    """Handle retrying failed summaries."""
    cache = SummaryCache()
    failed_entries = cache.get_failed_entries(session_id)
    
    if not failed_entries:
        click.echo("No failed summaries found to retry.")
        return
    
    click.echo(f"Found {len(failed_entries)} failed summaries to retry...")
    
    summarizer = SessionSummarizer()
    
    for i, entry in enumerate(failed_entries, 1):
        click.echo(f"Retrying {i}/{len(failed_entries)}: {entry.session_id[:8]}...")
        
        # We can't easily reconstruct the original content from cache,
        # so we'll need to re-parse the session
        # For now, just report what needs to be retried
        click.echo(f"  Session: {entry.session_id}")
        click.echo(f"  Detail level: {entry.detail_level}")
        click.echo(f"  Error: {entry.summary_result.error}")
    
    click.echo("Retry functionality requires re-implementing. Use --clear-cache and re-run instead.")


def filter_messages_since(messages, since_date):
    """Filter messages to only include those since the specified date."""
    if since_date is None:
        return messages

    filtered = []
    for msg in messages:
        try:
            # Use the existing datetime property from Message class
            msg_time = msg.datetime
            if msg_time >= since_date:
                filtered.append(msg)
        except (ValueError, AttributeError):
            # Include messages without valid timestamps
            filtered.append(msg)

    return filtered


def handle_summarization(
    project_path: Path, session_id: str, from_date, to_date, detail_level: str,
    output_format: str, categories: List[str], separator: str, output_file,
    include_metadata: bool, api_key: str, use_ai_summaries: bool = False, no_truncate: bool = False,
    backend: str = 'auto', since_date = None, redo: bool = False
) -> None:
    """Handle main summarization operations."""
    
    # Find sessions to process
    if session_id:
        session_file = find_session_by_id(str(project_path), session_id)
        if not session_file:
            click.echo(f"Session {session_id} not found.", err=True)
            sys.exit(1)
        session_files = [session_file]
    else:
        sessions = list_sessions(str(project_path), from_date, to_date)
        if not sessions:
            click.echo("No sessions found matching criteria.")
            return
        session_files = [s.get('file_path') for s in sessions if s.get('file_path')]
    
    if not session_files:
        click.echo("No session files found.")
        return
    
    # Initialize parser and parse all files with deduplication
    parser = SessionParser()
    click.echo(f"Processing {len(session_files)} session files with deduplication...")
    
    # Use the new parse_multiple_files method for automatic deduplication
    messages = parser.parse_multiple_files(session_files)

    # Apply since date filter if specified
    if since_date:
        original_count = len(messages)
        messages = filter_messages_since(messages, since_date)
        filtered_count = len(messages)
        click.echo(f"Filtered from {original_count} to {filtered_count} messages based on --since filter")

    turns = parser.build_conversation_turns(messages)

    click.echo(f"Found {len(turns)} unique conversation turns after deduplication")

    # Handle redo flag: clear cache for current sessions before processing
    if redo and use_ai_summaries:
        # Use the merged session ID pattern that will be used for caching
        merged_session_id = f"merged-{len(session_files)}-sessions"
        session_ids = [merged_session_id]

        cache = SummaryCache()
        cleared_count = cache.clear_cache_for_sessions(session_ids)
        click.echo(f"Cleared {cleared_count} cached summaries for current sessions (--redo)", err=True)
    
    # Create session metadata for the merged result
    merged_session_metadata = {
        'session_id': f"merged-{len(session_files)}-sessions",
        'message_count': len(messages),
        'session_count': len(session_files)
    }
    
    # Determine extraction mode
    if use_ai_summaries and len(categories) == 1 and categories[0] == 'user':
        # Pure AI summarization mode (only user messages shown)
        extraction_mode = 'summaries'
    elif use_ai_summaries and len(categories) > 1:
        # Hybrid mode: show selected categories, summarize the rest
        extraction_mode = 'hybrid'
    elif use_ai_summaries:
        # AI summarization with specific category filtering
        extraction_mode = 'summaries'
    else:
        # Pure message extraction mode
        extraction_mode = 'messages'
    
    if extraction_mode == 'messages':
        # Message extraction mode
        extractor = MessageExtractor(no_truncate=no_truncate)
        messages = extractor.extract_messages(turns, categories)
        
        if output_format == 'terminal':
            format_messages_terminal(messages, merged_session_metadata, include_metadata, no_truncate)
        elif output_format == 'plain':
            formatter = PlainFormatter(separator)
            formatter.format_messages(messages, merged_session_metadata, include_metadata, output_file)
        elif output_format == 'markdown':
            format_messages_markdown(messages, merged_session_metadata, include_metadata, output_file, no_truncate)
        elif output_format == 'jsonl':
            format_messages_jsonl(messages, merged_session_metadata, include_metadata, output_file)
        
        category_summary = ', '.join(categories)
        click.echo(f"  ✅ Extracted {len(messages)} messages ({category_summary})")

    elif extraction_mode == 'hybrid':
        # Hybrid mode: extract selected categories, summarize the rest
        extractor = MessageExtractor(no_truncate=no_truncate)
        extracted_messages = extractor.extract_messages(turns, categories)

        # Determine which categories to summarize (everything not in the selected categories)
        all_categories = ['user', 'subagent', 'plan', 'assistant', 'session_summary']
        categories_to_summarize = [cat for cat in all_categories if cat not in categories]

        if categories_to_summarize:
            # Generate summaries for the filtered-out categories
            summarizer = get_summarizer(backend, api_key, detail_level, str(project_path))

            # Create summary entries for content that was filtered out
            summary_entries = []
            for turn in turns:
                # Check if this turn has content in categories that need summarizing
                turn_needs_summary = False

                # Check if there are assistant messages when assistant is not in displayed categories
                if 'assistant' in categories_to_summarize and turn.assistant_messages:
                    turn_needs_summary = True

                # Add other category checks as needed
                # (plan, subagent, session_summary checks would go here)

                if turn_needs_summary:
                    summary = summarizer.summarize_turn(turn, detail_level, merged_session_metadata['session_id'])
                    if not summary.error:
                        # Create a summary message entry
                        summary_entry = {
                            'number': len(summary_entries) + len(extracted_messages) + 1,
                            'category': 'summary',
                            'content': summary.summary,
                            'timestamp': turn.user_message.timestamp if turn.user_message else None,
                            'uuid': f"summary-{len(summary_entries)}"
                        }
                        summary_entries.append(summary_entry)

            # Combine extracted messages and summaries, sort by timestamp/order
            all_entries = extracted_messages + summary_entries
            # Re-number for proper display order
            for i, entry in enumerate(all_entries, 1):
                entry['number'] = i

            # Display the hybrid result
            if output_format == 'terminal':
                format_messages_terminal(all_entries, merged_session_metadata, include_metadata, no_truncate)
            elif output_format == 'plain':
                formatter = PlainFormatter(separator)
                formatter.format_messages(all_entries, merged_session_metadata, include_metadata, output_file)
            elif output_format == 'markdown':
                format_messages_markdown(all_entries, merged_session_metadata, include_metadata, output_file, no_truncate)
            elif output_format == 'jsonl':
                format_messages_jsonl(all_entries, merged_session_metadata, include_metadata, output_file)

            category_summary = ', '.join(categories)
            summary_summary = ', '.join(categories_to_summarize)
            click.echo(f"  ✅ Hybrid mode: Extracted {len(extracted_messages)} messages ({category_summary}), Summarized {len(summary_entries)} blocks ({summary_summary})")
        else:
            # No categories to summarize, fall back to pure extraction
            if output_format == 'terminal':
                format_messages_terminal(extracted_messages, merged_session_metadata, include_metadata, no_truncate)
            elif output_format == 'plain':
                formatter = PlainFormatter(separator)
                formatter.format_messages(extracted_messages, merged_session_metadata, include_metadata, output_file)
            elif output_format == 'markdown':
                format_messages_markdown(extracted_messages, merged_session_metadata, include_metadata, output_file, no_truncate)
            elif output_format == 'jsonl':
                format_messages_jsonl(extracted_messages, merged_session_metadata, include_metadata, output_file)

            category_summary = ', '.join(categories)
            click.echo(f"  ✅ Extracted {len(extracted_messages)} messages ({category_summary})")

    else:
        # Summarization modes (AI or no-AI)
        if not use_ai_summaries:
            summarizer = NoAISummarizer()
        else:
            # Use the new backend selection logic
            summarizer = get_summarizer(backend, api_key, detail_level, str(project_path))
        
        # Generate summaries
        with click.progressbar(
            length=len(turns), 
            label="Summarizing turns"
        ) as bar:
            summaries = []
            for turn in turns:
                if hasattr(summarizer, 'summarize_turn'):
                    # Check if it's an AI summarizer (SessionSummarizer or SDKSummarizer)
                    if 'SessionSummarizer' in str(type(summarizer)) or 'SDKSummarizer' in str(type(summarizer)):
                        summary = summarizer.summarize_turn(turn, detail_level, merged_session_metadata['session_id'])
                    else:
                        # NoAISummarizer
                        summary = summarizer.summarize_turn(turn, merged_session_metadata['session_id'])
                else:
                    summary = summarizer.summarize_turn(turn)

                # Check for errors and fail fast
                if summary.error:
                    click.echo(f"Error: Failed to summarize turn: {summary.error}", err=True)
                    sys.exit(1)

                summaries.append(summary)
                bar.update(1)
        
        # Format and output
        if output_format == 'terminal':
            formatter = TerminalFormatter(console)
            formatter.format_session_summary(turns, summaries, merged_session_metadata, include_metadata)
        elif output_format == 'plain':
            formatter = PlainFormatter(separator)
            formatter.format_session_summary(turns, summaries, merged_session_metadata, include_metadata, output_file)
        elif output_format == 'markdown':
            formatter = MarkdownFormatter()
            formatter.format_session_summary(turns, summaries, merged_session_metadata, include_metadata, output_file)
        elif output_format == 'jsonl':
            formatter = JSONLFormatter()
            formatter.format_session_summary(turns, summaries, merged_session_metadata, include_metadata, output_file)
        
        # Report summary statistics
        total_tokens = sum(s.tokens_used or 0 for s in summaries)
        error_count = sum(1 for s in summaries if s.error)
        
        if error_count > 0:
            click.echo(f"  ⚠️  {error_count} summaries failed")
        if total_tokens > 0:
            click.echo(f"  💰 Used {total_tokens} tokens")
        click.echo(f"  ✅ Processed {len(session_files)} sessions → {len(turns)} unique turns")




def format_messages_terminal(messages: list, session_metadata: dict, include_metadata: bool, no_truncate: bool = False):
    """Format categorized messages for terminal display."""
    from rich.panel import Panel
    from rich.text import Text
    from rich import box
    from datetime import datetime
    
    # Session header
    session_id = session_metadata.get('session_id', 'Unknown')[:8]
    header_text = f"Messages from Session {session_id}... ({len(messages)} messages)"
    
    console.print(
        Panel(
            Text(header_text, style='bright_blue'),
            box=box.ROUNDED,
            border_style='blue',
            padding=(0, 1)
        )
    )
    console.print()
    
    # Display each message with category labels
    for i, message in enumerate(messages, 1):
        # Format timestamp if available and requested
        timestamp_text = ""
        if include_metadata and message.get('timestamp'):
            try:
                dt = datetime.fromisoformat(message['timestamp'].replace('Z', '+00:00'))
                timestamp_text = f" [{dt.strftime('%H:%M:%S')}]"
            except:
                pass
        
        # Create title with category (with better labels)
        category = message['category']
        if category == 'session_summary':
            label = 'SUMMARY'
        elif category == 'subagent':
            label = 'SUBAGENT'
        else:
            label = category.upper()
            
        category_colors = {
            'USER': 'bright_green',
            'SUBAGENT': 'bright_yellow', 
            'PLAN': 'bright_cyan',
            'ASSISTANT': 'bright_magenta',
            'SUMMARY': 'bright_blue'
        }
        category_color = category_colors.get(label, 'white')
        
        title = Text(f"[{label}] Message {i}", style=f"bold {category_color}")
        if timestamp_text:
            title.append(timestamp_text, style="dim white")
        
        content = message['content']
        if not no_truncate and len(content) > 2000:
            content = content[:2000] + "\n\n[... content truncated ...]"
        
        console.print(
            Panel(
                content,
                title=title,
                title_align="left",
                border_style=category_color,
                padding=(0, 1)
            )
        )
        
        if i < len(messages):
            console.print()


def format_messages_markdown(messages: list, session_metadata: dict, include_metadata: bool, output_file, no_truncate: bool = False):
    """Format categorized messages as Markdown."""
    from datetime import datetime
    
    lines = []
    session_id = session_metadata.get('session_id', 'Unknown')
    
    lines.append(f"# Messages from Session {session_id}")
    lines.append("")
    lines.append(f"**Session ID:** `{session_id}`")
    lines.append(f"**Total Messages:** {len(messages)}")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    for i, message in enumerate(messages, 1):
        category = message['category'].upper()
        lines.append(f"## [{category}] Message {i}")
        
        if include_metadata and message.get('timestamp'):
            try:
                dt = datetime.fromisoformat(message['timestamp'].replace('Z', '+00:00'))
                time_str = dt.strftime('%Y-%m-%d %H:%M:%S UTC')
                lines.append(f"**Time:** {time_str}")
            except:
                pass
            lines.append("")
        
        # Format content as blockquote
        for line in message['content'].split('\n'):
            lines.append(f"> {line}")
        
        lines.append("")
        lines.append("---")
        lines.append("")
    
    markdown_content = '\n'.join(lines)
    if output_file:
        output_file.write(markdown_content)


def format_messages_jsonl(messages: list, session_metadata: dict, include_metadata: bool, output_file):
    """Format categorized messages as JSONL."""
    import json
    from datetime import datetime
    
    lines = []
    
    # Header record
    header_record = {
        "type": "categorized_messages_session",
        "session_id": session_metadata.get('session_id'),
        "message_count": len(messages),
        "timestamp": datetime.now().isoformat()
    }
    lines.append(json.dumps(header_record))
    
    # Message records
    for message in messages:
        message_record = {
            "type": "categorized_message",
            "number": message['number'],
            "category": message['category'],
            "content": message['content'],
            "uuid": message['uuid']
        }
        
        if include_metadata:
            if message.get('timestamp'):
                message_record["timestamp"] = message['timestamp']
            if message.get('cwd'):
                message_record["cwd"] = message['cwd']
            if message.get('git_branch'):
                message_record["git_branch"] = message['git_branch']
        
        lines.append(json.dumps(message_record))
    
    jsonl_content = '\n'.join(lines)
    if output_file:
        output_file.write(jsonl_content)


if __name__ == '__main__':
    main()