"""Session discovery and filtering for Claude Code projects."""

import os
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple
import re


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
    
    # Find all .jsonl files in the project directory
    session_files = list(project_dir.glob('*.jsonl'))
    return sorted(session_files, key=lambda f: f.stat().st_mtime, reverse=True)


def get_session_metadata(session_file: Path) -> Dict:
    """Extract basic metadata from a session file."""
    try:
        with open(session_file, 'r') as f:
            # Read first few lines to get basic info
            first_line = f.readline().strip()
            if not first_line:
                return {}
            
            first_msg = json.loads(first_line)
            
            # Get session ID and start time
            session_id = first_msg.get('sessionId', session_file.stem)
            start_time = first_msg.get('timestamp')
            
            # Count total lines (messages)
            f.seek(0)
            message_count = sum(1 for _ in f)
            
            # Get file modification time as last activity
            last_modified = datetime.fromtimestamp(
                session_file.stat().st_mtime, 
                tz=timezone.utc
            )
            
            return {
                'session_id': session_id,
                'file_path': session_file,
                'message_count': message_count,
                'start_time': start_time,
                'last_modified': last_modified.isoformat(),
                'file_size': session_file.stat().st_size
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
    limit: Optional[int] = None
) -> List[Dict]:
    """List all sessions for a project with optional filtering."""
    session_files = find_session_files(project_path)
    
    sessions = []
    for session_file in session_files:
        metadata = get_session_metadata(session_file)
        if metadata:  # Only include valid sessions
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