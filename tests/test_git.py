"""Tests for git module."""

import pytest
import tempfile
from datetime import date
from pathlib import Path
from src.git import (
    is_git_repo,
    get_daily_git_summary,
    format_git_summary,
    get_git_user_email,
    get_project_display_name,
)


def test_is_git_repo_positive():
    """Test that current directory is recognized as a git repo."""
    # This test assumes it's run from within the cc-summarize repo
    assert is_git_repo('.') is True


def test_is_git_repo_negative():
    """Test that /tmp is not a git repo."""
    assert is_git_repo('/tmp') is False


def test_get_daily_git_summary_non_repo():
    """Test git summary for non-git directory."""
    result = get_daily_git_summary('/tmp', date.today())
    assert result['is_git_repo'] is False
    assert result['commits'] == []
    assert result['stats']['lines_added'] == 0


def test_get_daily_git_summary_repo():
    """Test git summary structure for git directory."""
    result = get_daily_git_summary('.', date.today())
    assert result['is_git_repo'] is True
    assert 'commits' in result
    assert 'stats' in result
    assert 'lines_added' in result['stats']
    assert 'lines_removed' in result['stats']
    assert 'files_changed' in result['stats']


def test_format_git_summary_non_repo():
    """Test formatting for non-git directory."""
    data = {'is_git_repo': False, 'commits': [], 'stats': {}}
    assert format_git_summary(data) == "Not a git repository"


def test_format_git_summary_no_commits():
    """Test formatting when no commits."""
    data = {
        'is_git_repo': True,
        'commits': [],
        'stats': {'lines_added': 0, 'lines_removed': 0, 'files_changed': 0}
    }
    assert format_git_summary(data) == "No commits"


def test_format_git_summary_with_commits():
    """Test formatting with commits."""
    data = {
        'is_git_repo': True,
        'commits': [{'hash': 'abc123', 'message': 'test', 'author': 'test@test.com', 'timestamp': '2025-01-01'}],
        'stats': {'lines_added': 10, 'lines_removed': 5, 'files_changed': 2}
    }
    result = format_git_summary(data)
    assert '1 commit' in result
    assert '+10/-5' in result
    assert '2 files' in result


def test_format_git_summary_multiple_commits():
    """Test formatting with multiple commits."""
    data = {
        'is_git_repo': True,
        'commits': [
            {'hash': 'abc123', 'message': 'test1', 'author': 'test@test.com', 'timestamp': '2025-01-01'},
            {'hash': 'def456', 'message': 'test2', 'author': 'test@test.com', 'timestamp': '2025-01-01'}
        ],
        'stats': {'lines_added': 20, 'lines_removed': 10, 'files_changed': 3}
    }
    result = format_git_summary(data)
    assert '2 commits' in result  # plural


def test_get_git_user_email():
    """Test getting git user email."""
    # This test assumes git is configured
    email = get_git_user_email('.')
    # Email may or may not be set, just check it returns something or None
    assert email is None or isinstance(email, str)


def test_display_name_normal_project():
    """Test display name for a normal project directory."""
    assert get_project_display_name('/home/user/projects/my-app') == 'my-app'


def test_display_name_common_branch_name():
    """Test display name qualifies common branch names with parent."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a directory named 'main' (common branch name)
        main_dir = Path(tmpdir) / 'myproject' / 'main'
        main_dir.mkdir(parents=True)
        assert get_project_display_name(str(main_dir)) == 'myproject/main'

        # Same for 'dev'
        dev_dir = Path(tmpdir) / 'myproject' / 'dev'
        dev_dir.mkdir(parents=True)
        assert get_project_display_name(str(dev_dir)) == 'myproject/dev'


def test_display_name_worktree():
    """Test display name for a git worktree."""
    with tempfile.TemporaryDirectory() as tmpdir:
        worktree_dir = Path(tmpdir) / 'main'
        worktree_dir.mkdir()

        # Create a fake .git file like a real worktree
        bare_repo = Path(tmpdir) / 'myrepo.git' / 'worktrees' / 'main'
        bare_repo.mkdir(parents=True)
        (worktree_dir / '.git').write_text(
            f'gitdir: {bare_repo}\n'
        )

        assert get_project_display_name(str(worktree_dir)) == 'myrepo/main'


def test_display_name_submodule_not_treated_as_worktree():
    """Test that submodules (no /worktrees/ in gitdir) use normal naming."""
    with tempfile.TemporaryDirectory() as tmpdir:
        sub_dir = Path(tmpdir) / 'my-submodule'
        sub_dir.mkdir()

        # Submodule .git file points to modules, not worktrees
        (sub_dir / '.git').write_text(
            'gitdir: ../.git/modules/my-submodule\n'
        )

        assert get_project_display_name(str(sub_dir)) == 'my-submodule'


def test_display_name_hyphenated_not_confused():
    """Test that hyphenated names aren't mistaken for branch names."""
    assert get_project_display_name('/home/user/projects/claude-investigations') == 'claude-investigations'
