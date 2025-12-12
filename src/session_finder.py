"""Session discovery and filtering for Claude Code projects."""

import os
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple
import re


class SessionNotFoundError(Exception):
    """Raised when no sessions are found for a project."""

    def __init__(self, message: str, project_path: str = None, searched_path: str = None):
        self.project_path = project_path
        self.searched_path = searched_path
        super().__init__(message)


def path_to_project_name(project_path: str) -> str:
    """Convert a project path to Claude Code's hyphenated format.
    
    Example: /home/user/projects/my-app -> -home-user-projects-my-app
    """
    return project_path.replace('/', '-')


def find_claude_projects_dir() -> Path:
    """Find the Claude Code projects directory."""
    claude_dir = Path.home() / '.claude' / 'projects'
    if not claude_dir.exists():
        raise FileNotFoundError(
            f"Claude Code projects directory not found at {claude_dir}. "
            "Make sure Claude Code has been used at least once."
        )
    return claude_dir


def find_session_files(project_path: str) -> List[Path]:
    """Find all session files for a given project path."""
    claude_dir = find_claude_projects_dir()
    project_name = path_to_project_name(str(Path(project_path).resolve()))
    project_dir = claude_dir / project_name

    if not project_dir.exists():
        return []

    # Find all .jsonl files, excluding agent-* subagent files
    session_files = [
        f for f in project_dir.glob('*.jsonl')
        if not f.name.startswith('agent-')
    ]
    return sorted(session_files, key=lambda f: f.stat().st_mtime, reverse=True)


def get_session_metadata(session_file: Path) -> Dict:
    """Extract basic metadata from a session file."""
    try:
        with open(session_file, 'r') as f:
            # Read lines to get basic info
            session_id = session_file.stem
            start_time = None
            summary = None
            first_user_content = None
            message_count = 0

            for line in f:
                message_count += 1
                line = line.strip()
                if not line:
                    continue

                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Look for session summary (Claude Code stores these)
                if msg.get('type') == 'summary' and msg.get('summary'):
                    summary = msg.get('summary')

                # Get session ID from first message with sessionId
                if not start_time and msg.get('sessionId'):
                    session_id = msg.get('sessionId', session_id)
                    start_time = msg.get('timestamp')

                # Get first user message content as fallback description
                if first_user_content is None and msg.get('type') == 'user':
                    message = msg.get('message', {})
                    content = message.get('content', '')
                    if isinstance(content, str) and content:
                        # Skip meta/command/warmup messages
                        if not content.startswith(('<command-', '<local-command-', 'Caveat:')) and content.strip() != 'Warmup':
                            first_user_content = content
                    elif isinstance(content, list):
                        for item in content:
                            if isinstance(item, dict) and item.get('type') == 'text':
                                text = item.get('text', '')
                                if text and not text.startswith(('<command-', '<local-command-')) and text.strip() != 'Warmup':
                                    first_user_content = text
                                    break

            # Get file modification time as last activity
            last_modified = datetime.fromtimestamp(
                session_file.stat().st_mtime,
                tz=timezone.utc
            )

            # Use summary if available, otherwise first user content
            description = summary or first_user_content or ''
            # Sanitize description: collapse whitespace, remove newlines
            if description:
                description = ' '.join(description.split())

            # Mark as empty if no real content (only system messages, warmup, etc.)
            has_content = bool(summary or first_user_content)

            return {
                'session_id': session_id,
                'file_path': session_file,
                'message_count': message_count,
                'start_time': start_time,
                'last_modified': last_modified.isoformat(),
                'file_size': session_file.stat().st_size,
                'description': description,
                'has_content': has_content
            }

    except (json.JSONDecodeError, IOError, KeyError) as e:
        return {
            'session_id': session_file.stem,
            'file_path': session_file,
            'error': str(e)
        }


def filter_sessions_by_date(
    sessions: List[Dict], 
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None
) -> List[Dict]:
    """Filter sessions by date range."""
    filtered = []
    
    for session in sessions:
        if 'error' in session:
            continue
        
        # Use start_time if available, otherwise last_modified
        date_str = session.get('start_time') or session.get('last_modified')
        if not date_str:
            continue
        
        try:
            session_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            session_date = session_date.replace(tzinfo=timezone.utc)
            
            if from_date and session_date < from_date.replace(tzinfo=timezone.utc):
                continue
            if to_date and session_date > to_date.replace(tzinfo=timezone.utc):
                continue
                
            filtered.append(session)
        except (ValueError, AttributeError):
            # Skip sessions with invalid dates
            continue
    
    return filtered


def list_sessions(
    project_path: str,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    limit: Optional[int] = None,
    include_empty: bool = False
) -> List[Dict]:
    """List all sessions for a project with optional filtering.

    Args:
        project_path: Path to the project directory
        from_date: Only include sessions after this date
        to_date: Only include sessions before this date
        limit: Maximum number of sessions to return
        include_empty: If False (default), exclude sessions with no real content
    """
    session_files = find_session_files(project_path)

    sessions = []
    for session_file in session_files:
        metadata = get_session_metadata(session_file)
        if metadata:  # Only include valid sessions
            # Skip empty sessions unless explicitly requested
            if not include_empty and not metadata.get('has_content', True):
                continue
            sessions.append(metadata)
    
    # Filter by date if specified
    if from_date or to_date:
        sessions = filter_sessions_by_date(sessions, from_date, to_date)
    
    # Apply limit
    if limit:
        sessions = sessions[:limit]
    
    return sessions


def find_session_by_id(project_path: str, session_id: str) -> Optional[Path]:
    """Find a specific session file by ID.

    Supports both full session IDs and partial IDs (prefixes).
    If multiple sessions match a partial ID, returns the most recent one.
    """
    session_files = find_session_files(project_path)
    matches = []

    for session_file in session_files:
        full_session_id = session_file.stem
        # First try exact match
        if full_session_id == session_id:
            return session_file
        # Then try prefix match
        elif full_session_id.startswith(session_id):
            matches.append(session_file)

    # If we have partial matches, return the most recent one
    if matches:
        # Files are already sorted by modification time (most recent first)
        return matches[0]

    return None


def get_session_search_info(project_path: str) -> Dict[str, str]:
    """Get diagnostic information about session search paths.

    Returns info about where sessions would be looked for,
    useful for error messages.
    """
    try:
        claude_dir = find_claude_projects_dir()
        project_name = path_to_project_name(str(Path(project_path).resolve()))
        project_dir = claude_dir / project_name

        return {
            'project_path': str(Path(project_path).resolve()),
            'claude_projects_dir': str(claude_dir),
            'expected_session_dir': str(project_dir),
            'session_dir_exists': project_dir.exists(),
        }
    except FileNotFoundError as e:
        return {
            'project_path': str(Path(project_path).resolve()),
            'error': str(e),
        }


def format_no_sessions_error(project_path: str) -> str:
    """Format a helpful error message when no sessions are found."""
    info = get_session_search_info(project_path)

    lines = ["No sessions found matching criteria."]
    lines.append("")

    if 'error' in info:
        lines.append(f"Error: {info['error']}")
    else:
        lines.append(f"Project path: {info['project_path']}")
        lines.append(f"Searched in: {info['expected_session_dir']}")

        if not info['session_dir_exists']:
            lines.append("")
            lines.append("The session directory does not exist.")
            lines.append("This could mean:")
            lines.append("  - Claude Code hasn't been used in this project yet")
            lines.append("  - The project path is incorrect")
            lines.append("")
            lines.append("Tip: Run 'cc-summarize --list' from within your project directory")

    return '\n'.join(lines)