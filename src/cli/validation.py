"""CLI input validation utilities."""

from pathlib import Path
from typing import Optional, Tuple, List

from ..session_finder import find_session_files, find_session_by_id


def validate_since_option(since: str) -> Tuple[bool, Optional[str]]:
    """Validate --since option value.

    Args:
        since: The since value to validate (e.g., '1d', '2h', '2024-12-01')

    Returns:
        Tuple of (is_valid, error_message)
    """
    from ..date_parser import parse_since_date

    try:
        parse_since_date(since)
        return True, None
    except ValueError as e:
        return False, str(e)


def validate_session_id(
    project_path: Path,
    session_id: str
) -> Tuple[bool, Optional[str], List[str]]:
    """Validate session ID, warn on ambiguous partial matches.

    Args:
        project_path: Path to the project directory
        session_id: Full or partial session ID

    Returns:
        Tuple of (is_valid, error_message, matching_ids)
    """
    session_files = find_session_files(str(project_path))

    if not session_files:
        return False, f"No sessions found for project at {project_path}", []

    # Find all matching sessions
    matches = []
    for session_file in session_files:
        full_id = session_file.stem
        if full_id == session_id:
            # Exact match
            return True, None, [full_id]
        elif full_id.startswith(session_id):
            matches.append(full_id)

    if len(matches) == 0:
        return False, f"No session found matching '{session_id}'", []
    elif len(matches) == 1:
        return True, None, matches
    else:
        # Ambiguous match
        return True, f"Warning: '{session_id}' matches {len(matches)} sessions, using most recent", matches


def validate_output_writable(output_path: str) -> Tuple[bool, Optional[str]]:
    """Validate output file is writable.

    Args:
        output_path: Path to the output file

    Returns:
        Tuple of (is_valid, error_message)
    """
    if output_path == '-':
        # stdout is always writable
        return True, None

    path = Path(output_path)

    # Check if parent directory exists
    if not path.parent.exists():
        return False, f"Parent directory does not exist: {path.parent}"

    # Check if parent directory is writable
    if not os.access(path.parent, os.W_OK):
        return False, f"Cannot write to directory: {path.parent}"

    # Check if file exists and is writable
    if path.exists() and not os.access(path, os.W_OK):
        return False, f"File is not writable: {path}"

    return True, None


import os
