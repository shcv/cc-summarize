"""Tests for session_finder module."""

import pytest
import json
import tempfile
from pathlib import Path
from src.session_finder import (
    path_to_project_name,
    get_project_cwd_from_session,
    list_all_projects,
)


def test_path_to_project_name():
    """Test path to project name conversion."""
    assert path_to_project_name('/home/user/projects/my-app') == '-home-user-projects-my-app'
    assert path_to_project_name('/home/user/claude-investigations') == '-home-user-claude-investigations'


def test_get_project_cwd_from_session_with_cwd():
    """Test extracting cwd from a session file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        # Write a session file with cwd
        f.write(json.dumps({
            'type': 'user',
            'cwd': '/home/user/my-project',
            'sessionId': 'test-session',
            'message': {'content': 'Hello'}
        }) + '\n')
        f.write(json.dumps({
            'type': 'assistant',
            'cwd': '/home/user/my-project',
            'message': {'content': 'Hi there'}
        }) + '\n')
        f.flush()

        result = get_project_cwd_from_session(Path(f.name))
        assert result == '/home/user/my-project'

    Path(f.name).unlink()


def test_get_project_cwd_from_session_uses_last_cwd():
    """Test that we use the last cwd in the file (handles project moves)."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        # First message with old cwd
        f.write(json.dumps({
            'type': 'user',
            'cwd': '/home/user/old-location',
            'message': {'content': 'Hello'}
        }) + '\n')
        # Later message with new cwd (project moved)
        f.write(json.dumps({
            'type': 'user',
            'cwd': '/home/user/new-location',
            'message': {'content': 'Hello again'}
        }) + '\n')
        f.flush()

        result = get_project_cwd_from_session(Path(f.name))
        # Should return the last (most recent) cwd
        assert result == '/home/user/new-location'

    Path(f.name).unlink()


def test_get_project_cwd_from_session_no_cwd():
    """Test handling session files without cwd field."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        f.write(json.dumps({
            'type': 'user',
            'sessionId': 'test-session',
            'message': {'content': 'Hello'}
        }) + '\n')
        f.flush()

        result = get_project_cwd_from_session(Path(f.name))
        assert result is None

    Path(f.name).unlink()


def test_get_project_cwd_from_session_invalid_json():
    """Test handling session files with invalid JSON."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        f.write('not valid json\n')
        f.write(json.dumps({
            'type': 'user',
            'cwd': '/home/user/my-project',
            'message': {'content': 'Hello'}
        }) + '\n')
        f.flush()

        # Should still find the valid line with cwd
        result = get_project_cwd_from_session(Path(f.name))
        assert result == '/home/user/my-project'

    Path(f.name).unlink()


def test_get_project_cwd_from_session_nonexistent():
    """Test handling nonexistent files."""
    result = get_project_cwd_from_session(Path('/nonexistent/file.jsonl'))
    assert result is None


def test_get_project_cwd_preserves_hyphens():
    """Test that cwd with hyphens is preserved correctly."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        # Project path with hyphens in name
        f.write(json.dumps({
            'type': 'user',
            'cwd': '/home/user/claude-investigations',
            'message': {'content': 'Hello'}
        }) + '\n')
        f.flush()

        result = get_project_cwd_from_session(Path(f.name))
        # The cwd should be preserved exactly as-is
        assert result == '/home/user/claude-investigations'
        # Path.name should work correctly
        assert Path(result).name == 'claude-investigations'

    Path(f.name).unlink()
