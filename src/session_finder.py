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


def get_project_cwd_from_session(session_file: Path) -> Optional[str]:
    """Extract the original project path (cwd) from a session file.

    Session files contain a 'cwd' field that stores the actual filesystem path
    where Claude Code was running. This is more reliable than trying to
    reverse-engineer the hyphenated directory name.

    Args:
        session_file: Path to a session JSONL file

    Returns:
        The cwd path string, or None if not found
    """
    try:
        with open(session_file, 'r') as f:
            # Read from the end to get the most recent cwd
            # (in case the project was moved during the session)
            lines = f.readlines()

        # Search backwards for a line with cwd
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
                cwd = msg.get('cwd')
                if cwd:
                    return cwd
            except json.JSONDecodeError:
                continue

        return None
    except (IOError, OSError):
        return None


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


def list_all_projects() -> List[Dict]:
    """List all projects that have Claude Code sessions.

    Returns:
        List of dictionaries with project info:
        - 'project_path': Original file system path (from session cwd)
        - 'session_dir': Path to the session directory
        - 'session_count': Number of session files
        - 'last_activity': Most recent session modification time
    """
    try:
        claude_dir = find_claude_projects_dir()
    except FileNotFoundError:
        return []

    projects = []

    for project_dir in claude_dir.iterdir():
        if not project_dir.is_dir():
            continue

        # Find session files (exclude agent-* subagent files)
        session_files = [
            f for f in project_dir.glob('*.jsonl')
            if not f.name.startswith('agent-')
        ]

        if not session_files:
            continue

        # Sort by modification time (most recent first) to get cwd from latest session
        session_files_sorted = sorted(
            session_files,
            key=lambda f: f.stat().st_mtime,
            reverse=True
        )

        # Extract actual project path from the most recent session's cwd field
        project_path = None
        for session_file in session_files_sorted:
            project_path = get_project_cwd_from_session(session_file)
            if project_path:
                break

        # Fallback to old method if cwd not found in any session
        if not project_path:
            project_name = project_dir.name
            if project_name.startswith('-'):
                project_path = project_name.replace('-', '/')
            else:
                project_path = '/' + project_name.replace('-', '/')

        # Get most recent activity
        most_recent = max(f.stat().st_mtime for f in session_files)
        last_activity = datetime.fromtimestamp(most_recent, tz=timezone.utc)

        projects.append({
            'project_path': project_path,
            'session_dir': str(project_dir),
            'session_count': len(session_files),
            'last_activity': last_activity.isoformat()
        })

    # Sort by most recent activity
    projects.sort(key=lambda p: p['last_activity'], reverse=True)
    return projects


def list_sessions_for_date(
    project_path: str,
    target_date: datetime
) -> List[Dict]:
    """List sessions that have activity on a specific date.

    Args:
        project_path: Path to the project directory
        target_date: The date to filter by (uses date portion only)

    Returns:
        List of session metadata dictionaries
    """
    # Get all sessions
    sessions = list_sessions(project_path, include_empty=False)

    # Filter to sessions with activity on the target date
    target_date_only = target_date.date() if hasattr(target_date, 'date') else target_date
    filtered = []

    for session in sessions:
        if 'error' in session:
            continue

        # Check last_modified date
        last_modified = session.get('last_modified')
        if last_modified:
            try:
                session_dt = datetime.fromisoformat(last_modified.replace('Z', '+00:00'))
                if session_dt.date() == target_date_only:
                    filtered.append(session)
            except (ValueError, AttributeError):
                continue

    return filtered


def get_sessions_across_projects(
    target_date: datetime
) -> List[Tuple[str, List[Dict]]]:
    """Get all sessions across all projects for a specific date.

    Args:
        target_date: The date to filter by

    Returns:
        List of tuples: (project_path, list of session metadata)
    """
    all_projects = list_all_projects()
    results = []

    for project in all_projects:
        project_path = project['project_path']
        sessions = list_sessions_for_date(project_path, target_date)
        if sessions:
            results.append((project_path, sessions))

    return results


def get_sessions_in_range(
    start_date: datetime,
    end_date: datetime = None
) -> List[Tuple[str, List[Dict]]]:
    """Get all sessions across all projects within a date range.

    Args:
        start_date: Start of the range (inclusive)
        end_date: End of the range (inclusive), defaults to now

    Returns:
        List of tuples: (project_path, list of session metadata)
    """
    if end_date is None:
        end_date = datetime.now(timezone.utc)

    all_projects = list_all_projects()
    results = []

    for project in all_projects:
        project_path = project['project_path']

        # Get all sessions and filter by date range
        sessions = list_sessions(project_path)
        filtered = []

        for session in sessions:
            # Parse the last_modified timestamp
            last_mod = session.get('last_modified', '')
            if not last_mod:
                continue

            try:
                # Parse ISO timestamp
                if last_mod.endswith('Z'):
                    session_time = datetime.fromisoformat(last_mod.replace('Z', '+00:00'))
                else:
                    session_time = datetime.fromisoformat(last_mod)

                # Make timezone-aware if needed
                if session_time.tzinfo is None:
                    session_time = session_time.replace(tzinfo=timezone.utc)

                # Check if in range
                if start_date <= session_time <= end_date:
                    filtered.append(session)
            except (ValueError, TypeError):
                continue

        if filtered:
            results.append((project_path, filtered))

    return results