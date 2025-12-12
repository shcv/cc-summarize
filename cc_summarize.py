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
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn, TimeRemainingColumn

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from session_finder import list_sessions, find_session_by_id, format_no_sessions_error
from parser import SessionParser
from no_ai_summarizer import NoAISummarizer, UserOnlyExtractor, MessageExtractor
from cache import SummaryCache
from date_parser import parse_since_date, format_since_description
from formatters import (
    TerminalFormatter,
    MarkdownFormatter,
    JSONLFormatter,
    PlainFormatter,
    should_use_plain_output,
)
from cli.summary_gen import (
    generate_commit_summary,
    generate_requirements_summary,
    generate_work_summary,
)

# Load environment variables from .env file
load_dotenv()

# Initialize console for rich output
console = Console()

@click.command()
@click.option('--project', '-p',
              default='.', help='Project directory - relative or absolute path (default: current)')
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
              help='Generate AI summaries using Claude Agent SDK. Levels: minimal, normal, detailed')
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
@click.option('--summary', type=click.Choice(['default', 'commit', 'requirements']),
              help='Generate a summary: default (session work), commit (conventional commit message), requirements (extract user requirements)')
@click.version_option(version='1.2.0')
def main(project, session, from_date, to_date, output_format, with_plans, with_summaries, with_subagent,
         with_assistant, with_all, summarize, plain, separator, output, metadata, interactive, list_sessions,
         retry_failed, clear_cache, redo, verbose, no_truncate, since, summary):
    """Claude Code Session Summarizer

    Manage, view, and summarize Claude Code sessions for a project.
    """

    # Handle project path - support both relative and absolute paths
    # Convert to absolute path even if directory doesn't exist
    if os.path.isabs(project):
        project_path = Path(project)
    else:
        project_path = Path.cwd() / project
    project_path = project_path.resolve()
    
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
        
        # Validate SDK availability for AI summarization
        if summarize:
            from src.summarizer import SummarizerAvailability
            if not SummarizerAvailability.is_available():
                error_msg = SummarizerAvailability.get_error_message()
                click.echo(f"Error: Claude Agent SDK not available: {error_msg}", err=True)
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
            categories, separator, output, metadata, bool(summarize), no_truncate, since_date, redo, summary
        )
        
    except KeyboardInterrupt:
        click.echo("\nOperation cancelled by user.", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        sys.exit(1)


def get_summarizer(project_path: Optional[str] = None):
    """Get the SDK summarizer.

    Args:
        project_path: Optional project path for the summarizer

    Returns:
        Summarizer instance
    """
    from src.summarizer import Summarizer
    return Summarizer(project_path=project_path)


def get_turn_description(turn, max_length: int = 50) -> str:
    """Extract a short description from a conversation turn for progress display."""
    from src.utils import extract_user_content

    content = extract_user_content(turn.user_message.content)
    # Take first line and truncate
    first_line = content.split('\n')[0].strip()
    if len(first_line) > max_length:
        return first_line[:max_length-3] + "..."
    return first_line if first_line else "(empty)"




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
    """Handle retrying failed summaries.

    Note: This feature is currently disabled. Use --redo to regenerate summaries.
    """
    cache = SummaryCache()
    failed_entries = cache.get_failed_entries(session_id)

    if not failed_entries:
        click.echo("No failed summaries found to retry.")
        return

    click.echo(f"Found {len(failed_entries)} failed summaries:", err=True)
    click.echo("", err=True)

    for entry in failed_entries:
        click.echo(f"  Session: {entry.session_id[:16]}...", err=True)
        click.echo(f"  Error: {entry.summary_result.error}", err=True)
        click.echo("", err=True)

    click.echo("To regenerate these summaries, use:", err=True)
    click.echo("  cc-summarize --summarize normal --redo", err=True)
    click.echo("", err=True)
    click.echo("Or clear the cache first:", err=True)
    click.echo("  cc-summarize --clear-cache", err=True)


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
    include_metadata: bool, use_ai_summaries: bool = False, no_truncate: bool = False,
    since_date = None, redo: bool = False, generate_summary: Optional[str] = None
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
            click.echo(format_no_sessions_error(str(project_path)), err=True)
            return
        session_files = [s.get('file_path') for s in sessions if s.get('file_path')]

    if not session_files:
        click.echo(format_no_sessions_error(str(project_path)), err=True)
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

    # Handle redo flag: clear cache only for the filtered turns
    if redo and use_ai_summaries:
        from src.summarizer import Summarizer
        summarizer = Summarizer(project_path=str(project_path))
        merged_session_id = f"merged-{len(session_files)}-sessions"

        # Clear cache entries only for the turns that match the current filter
        cleared_count = 0
        for turn in turns:
            if summarizer.clear_turn_cache(turn, detail_level, merged_session_id):
                cleared_count += 1

        click.echo(f"Cleared {cleared_count} cached summaries for filtered turns (--redo)", err=True)
    
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

        # Capture output if summary generation is requested
        import io
        if generate_summary:
            # Create a string buffer to capture output
            output_buffer = io.StringIO()
            actual_output = output_buffer
        else:
            actual_output = output_file

        if output_format == 'terminal':
            formatter = TerminalFormatter(console)
            formatter.format_messages(messages, merged_session_metadata, include_metadata, actual_output)
        elif output_format == 'plain':
            formatter = PlainFormatter(separator)
            formatter.format_messages(messages, merged_session_metadata, include_metadata, actual_output)
        elif output_format == 'markdown':
            formatter = MarkdownFormatter()
            formatter.format_messages(messages, merged_session_metadata, include_metadata, actual_output)
        elif output_format == 'jsonl':
            formatter = JSONLFormatter()
            formatter.format_messages(messages, merged_session_metadata, include_metadata, actual_output)

        category_summary = ', '.join(categories)
        click.echo(f"  ✅ Extracted {len(messages)} messages ({category_summary})")

        # Generate and output summary if requested
        if generate_summary:
            captured_content = output_buffer.getvalue()

            # Determine which summary generator to use
            if generate_summary == 'commit':
                click.echo("\n" + "="*80, err=True)
                click.echo("Generating conventional commit message...", err=True)
                click.echo("="*80 + "\n", err=True)
                summary_title = "CONVENTIONAL COMMIT MESSAGE"
                generator = generate_commit_summary
            elif generate_summary == 'requirements':
                click.echo("\n" + "="*80, err=True)
                click.echo("Extracting requirements from session...", err=True)
                click.echo("="*80 + "\n", err=True)
                summary_title = "EXTRACTED REQUIREMENTS"
                generator = generate_requirements_summary
            else:  # 'default'
                click.echo("\n" + "="*80, err=True)
                click.echo("Generating detailed work summary...", err=True)
                click.echo("="*80 + "\n", err=True)
                summary_title = "DETAILED WORK SUMMARY"
                generator = generate_work_summary

            try:
                summary_result = generator(captured_content, str(project_path))
                # Output the original content first
                output_file.write(captured_content)
                # Then output the summary
                output_file.write("\n\n" + "="*80 + "\n")
                output_file.write(summary_title + "\n")
                output_file.write("="*80 + "\n\n")
                output_file.write(summary_result)
                output_file.write("\n")
            except Exception as e:
                import traceback
                click.echo(f"Error generating summary: {e}", err=True)
                click.echo(traceback.format_exc(), err=True)

    elif extraction_mode == 'hybrid':
        # Hybrid mode: extract selected categories, summarize the rest
        extractor = MessageExtractor(no_truncate=no_truncate)
        extracted_messages = extractor.extract_messages(turns, categories)

        # Determine which categories to summarize (everything not in the selected categories)
        all_categories = ['user', 'subagent', 'plan', 'assistant', 'session_summary']
        categories_to_summarize = [cat for cat in all_categories if cat not in categories]

        if categories_to_summarize:
            # Generate summaries for the filtered-out categories
            summarizer = get_summarizer(str(project_path))

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
                formatter = TerminalFormatter(console)
                formatter.format_messages(all_entries, merged_session_metadata, include_metadata, output_file)
            elif output_format == 'plain':
                formatter = PlainFormatter(separator)
                formatter.format_messages(all_entries, merged_session_metadata, include_metadata, output_file)
            elif output_format == 'markdown':
                formatter = MarkdownFormatter()
                formatter.format_messages(all_entries, merged_session_metadata, include_metadata, output_file)
            elif output_format == 'jsonl':
                formatter = JSONLFormatter()
                formatter.format_messages(all_entries, merged_session_metadata, include_metadata, output_file)

            category_summary = ', '.join(categories)
            summary_summary = ', '.join(categories_to_summarize)
            click.echo(f"  ✅ Hybrid mode: Extracted {len(extracted_messages)} messages ({category_summary}), Summarized {len(summary_entries)} blocks ({summary_summary})")
        else:
            # No categories to summarize, fall back to pure extraction
            if output_format == 'terminal':
                formatter = TerminalFormatter(console)
                formatter.format_messages(extracted_messages, merged_session_metadata, include_metadata, output_file)
            elif output_format == 'plain':
                formatter = PlainFormatter(separator)
                formatter.format_messages(extracted_messages, merged_session_metadata, include_metadata, output_file)
            elif output_format == 'markdown':
                formatter = MarkdownFormatter()
                formatter.format_messages(extracted_messages, merged_session_metadata, include_metadata, output_file)
            elif output_format == 'jsonl':
                formatter = JSONLFormatter()
                formatter.format_messages(extracted_messages, merged_session_metadata, include_metadata, output_file)

            category_summary = ', '.join(categories)
            click.echo(f"  ✅ Extracted {len(extracted_messages)} messages ({category_summary})")

    else:
        # Summarization modes (AI or no-AI)
        if not use_ai_summaries:
            summarizer = NoAISummarizer()
        else:
            # Get SDK summarizer
            summarizer = get_summarizer(str(project_path))

        is_ai_summarizer = 'Summarizer' in str(type(summarizer)) and 'NoAI' not in str(type(summarizer))

        # Pre-check cache to determine which turns need summarization
        session_id = merged_session_metadata['session_id']
        cached_turns = []
        uncached_turns = []
        uncached_indices = []

        if is_ai_summarizer and hasattr(summarizer, 'is_cached'):
            for i, turn in enumerate(turns):
                if summarizer.is_cached(turn, detail_level, session_id):
                    cached_turns.append(i)
                else:
                    uncached_turns.append(turn)
                    uncached_indices.append(i)
        else:
            uncached_turns = turns
            uncached_indices = list(range(len(turns)))

        # Report cache status
        if cached_turns:
            console.print(f"[dim]Found {len(cached_turns)} cached summaries, generating {len(uncached_turns)} new[/dim]")

        # Initialize timing estimator for progress tracking
        from src.timing import TimingEstimator
        timing = TimingEstimator()

        # Calculate estimated durations only for uncached turns
        if uncached_turns:
            turn_estimates = [timing.estimate_turn_duration(turn) for turn in uncached_turns]
            total_estimated = sum(turn_estimates)
        else:
            turn_estimates = []
            total_estimated = 0

        # Generate summaries
        summaries = [None] * len(turns)  # Pre-allocate for correct ordering
        import time

        # First, quickly get cached summaries (no progress bar needed)
        if is_ai_summarizer:
            for i, turn in enumerate(turns):
                if i in cached_turns:
                    summary = summarizer.summarize_turn(turn, detail_level, session_id)
                    summaries[i] = summary

        # Then process uncached turns with progress display
        if uncached_turns:
            num_turns = len(uncached_turns)
            use_full_progress = num_turns >= 3

            if use_full_progress:
                # Full progress bar for 3+ turns
                progress = Progress(
                    SpinnerColumn(),
                    TextColumn("[bold blue]{task.description}", justify="left"),
                    BarColumn(bar_width=30),
                    TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                    TextColumn("•"),
                    TimeElapsedColumn(),
                    TextColumn("/"),
                    TimeRemainingColumn(),
                    console=console,
                    transient=False,
                    refresh_per_second=4,  # Update display more frequently
                )
                progress.start()
                task = progress.add_task(
                    f"Summarizing {num_turns} turns",
                    total=total_estimated if total_estimated > 0 else num_turns,
                )
            else:
                # Simple spinner for small counts
                progress = Progress(
                    SpinnerColumn(),
                    TextColumn("[bold blue]{task.description}"),
                    TimeElapsedColumn(),
                    console=console,
                    transient=False,
                    refresh_per_second=4,
                )
                progress.start()
                task = progress.add_task(f"Summarizing {num_turns} turn{'s' if num_turns > 1 else ''}...")

            try:
                completed_time = 0.0
                for j, (turn, orig_idx) in enumerate(zip(uncached_turns, uncached_indices)):
                    if use_full_progress:
                        # Update description with current turn number
                        progress.update(task, description=f"Summarizing turn {j+1}/{num_turns}")

                    # Time the summarization
                    start_time = time.time()

                    # Summarize
                    if is_ai_summarizer:
                        summary = summarizer.summarize_turn(turn, detail_level, session_id)
                    else:
                        summary = summarizer.summarize_turn(turn, session_id)

                    elapsed = time.time() - start_time

                    # Record timing for future estimates (only for AI summarizer, only for actual API calls)
                    if is_ai_summarizer and elapsed > 0.5:  # Only record if it took real time (not cached)
                        num_msgs, num_tools, content_len = timing.get_turn_features(turn)
                        timing.add_sample(elapsed, num_msgs, num_tools, content_len)

                    # Check for errors and fail fast
                    if summary.error:
                        progress.stop()
                        click.echo(f"\nError: Failed to summarize turn: {summary.error}", err=True)
                        sys.exit(1)

                    summaries[orig_idx] = summary

                    # Update progress using estimated time for this turn
                    if use_full_progress:
                        completed_time += turn_estimates[j] if turn_estimates else 1
                        progress.update(task, completed=completed_time)
            finally:
                progress.stop()
        else:
            console.print("[green]All summaries loaded from cache[/green]")
        
        # Capture output if summary generation is requested
        import io
        if generate_summary:
            # Create a string buffer to capture output
            output_buffer = io.StringIO()
            actual_output = output_buffer
        else:
            actual_output = output_file

        # Format and output
        if output_format == 'terminal':
            formatter = TerminalFormatter(console)
            formatter.format_session_summary(turns, summaries, merged_session_metadata, include_metadata)
        elif output_format == 'plain':
            formatter = PlainFormatter(separator)
            formatter.format_session_summary(turns, summaries, merged_session_metadata, include_metadata, actual_output)
        elif output_format == 'markdown':
            formatter = MarkdownFormatter()
            formatter.format_session_summary(turns, summaries, merged_session_metadata, include_metadata, actual_output)
        elif output_format == 'jsonl':
            formatter = JSONLFormatter()
            formatter.format_session_summary(turns, summaries, merged_session_metadata, include_metadata, actual_output)

        # Report summary statistics
        total_tokens = sum(s.tokens_used or 0 for s in summaries)
        error_count = sum(1 for s in summaries if s.error)

        if error_count > 0:
            click.echo(f"  ⚠️  {error_count} summaries failed")
        if total_tokens > 0:
            click.echo(f"  💰 Used {total_tokens} tokens")
        click.echo(f"  ✅ Processed {len(session_files)} sessions → {len(turns)} unique turns")

        # Generate and output summary if requested
        if generate_summary:
            captured_content = output_buffer.getvalue()

            # Determine which summary generator to use
            if generate_summary == 'commit':
                click.echo("\n" + "="*80, err=True)
                click.echo("Generating conventional commit message...", err=True)
                click.echo("="*80 + "\n", err=True)
                summary_title = "CONVENTIONAL COMMIT MESSAGE"
                generator = generate_commit_summary
            elif generate_summary == 'requirements':
                click.echo("\n" + "="*80, err=True)
                click.echo("Extracting requirements from session...", err=True)
                click.echo("="*80 + "\n", err=True)
                summary_title = "EXTRACTED REQUIREMENTS"
                generator = generate_requirements_summary
            else:  # 'default'
                click.echo("\n" + "="*80, err=True)
                click.echo("Generating detailed work summary...", err=True)
                click.echo("="*80 + "\n", err=True)
                summary_title = "DETAILED WORK SUMMARY"
                generator = generate_work_summary

            try:
                summary_result = generator(captured_content, str(project_path))
                # Output the original content first
                output_file.write(captured_content)
                # Then output the summary
                output_file.write("\n\n" + "="*80 + "\n")
                output_file.write(summary_title + "\n")
                output_file.write("="*80 + "\n\n")
                output_file.write(summary_result)
                output_file.write("\n")
            except Exception as e:
                import traceback
                click.echo(f"Error generating summary: {e}", err=True)
                click.echo(traceback.format_exc(), err=True)




if __name__ == '__main__':
    main()