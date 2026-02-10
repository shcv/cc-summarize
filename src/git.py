"""Git utilities for daily summary generation."""

import subprocess
from datetime import datetime, date, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def is_git_repo(project_path: str) -> bool:
    """Check if the given path is inside a git repository."""
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--git-dir'],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def get_commits_for_date(
    project_path: str,
    target_date: date,
    author_email: Optional[str] = None
) -> List[Dict]:
    """Get all commits made on a specific date.

    Args:
        project_path: Path to the git repository
        target_date: The date to get commits for
        author_email: Optional email to filter by author

    Returns:
        List of commit dictionaries with 'hash', 'message', 'author', 'timestamp'
    """
    if not is_git_repo(project_path):
        return []

    # Format date range for git log
    since = target_date.strftime('%Y-%m-%d 00:00:00')
    until = target_date.strftime('%Y-%m-%d 23:59:59')

    cmd = [
        'git', 'log',
        f'--since={since}',
        f'--until={until}',
        '--format=%H|%s|%ae|%aI',  # hash|subject|author_email|iso_date
    ]

    if author_email:
        cmd.append(f'--author={author_email}')

    try:
        result = subprocess.run(
            cmd,
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            return []

        commits = []
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
            parts = line.split('|', 3)
            if len(parts) >= 4:
                commits.append({
                    'hash': parts[0][:8],
                    'message': parts[1],
                    'author': parts[2],
                    'timestamp': parts[3]
                })

        return commits

    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return []


def get_diff_stats_for_date(
    project_path: str,
    target_date: date,
    author_email: Optional[str] = None
) -> Dict:
    """Get diff statistics (lines added/removed) for commits on a specific date.

    Args:
        project_path: Path to the git repository
        target_date: The date to get stats for
        author_email: Optional email to filter by author

    Returns:
        Dictionary with 'lines_added', 'lines_removed', 'files_changed'
    """
    if not is_git_repo(project_path):
        return {'lines_added': 0, 'lines_removed': 0, 'files_changed': 0}

    since = target_date.strftime('%Y-%m-%d 00:00:00')
    until = target_date.strftime('%Y-%m-%d 23:59:59')

    cmd = [
        'git', 'log',
        f'--since={since}',
        f'--until={until}',
        '--numstat',
        '--format=',  # No commit info, just stats
    ]

    if author_email:
        cmd.append(f'--author={author_email}')

    try:
        result = subprocess.run(
            cmd,
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            return {'lines_added': 0, 'lines_removed': 0, 'files_changed': 0}

        lines_added = 0
        lines_removed = 0
        files_changed = set()

        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
            parts = line.split('\t')
            if len(parts) >= 3:
                try:
                    # Binary files show as '-' for additions/deletions
                    added = int(parts[0]) if parts[0] != '-' else 0
                    removed = int(parts[1]) if parts[1] != '-' else 0
                    lines_added += added
                    lines_removed += removed
                    files_changed.add(parts[2])
                except ValueError:
                    continue

        return {
            'lines_added': lines_added,
            'lines_removed': lines_removed,
            'files_changed': len(files_changed)
        }

    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return {'lines_added': 0, 'lines_removed': 0, 'files_changed': 0}


def get_git_user_email(project_path: str) -> Optional[str]:
    """Get the configured git user email for a repository."""
    try:
        result = subprocess.run(
            ['git', 'config', 'user.email'],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def get_daily_git_summary(
    project_path: str,
    target_date: date,
    include_other_authors: bool = False
) -> Dict:
    """Get a comprehensive git summary for a specific day.

    Args:
        project_path: Path to the git repository
        target_date: The date to summarize
        include_other_authors: If True, include all authors' commits

    Returns:
        Dictionary with 'is_git_repo', 'commits', 'stats', 'author_email'
    """
    if not is_git_repo(project_path):
        return {
            'is_git_repo': False,
            'commits': [],
            'stats': {'lines_added': 0, 'lines_removed': 0, 'files_changed': 0},
            'author_email': None
        }

    author_email = None if include_other_authors else get_git_user_email(project_path)

    commits = get_commits_for_date(project_path, target_date, author_email)
    stats = get_diff_stats_for_date(project_path, target_date, author_email)

    return {
        'is_git_repo': True,
        'commits': commits,
        'stats': stats,
        'author_email': author_email
    }


_COMMON_BRANCH_NAMES = frozenset({
    'main', 'master', 'dev', 'develop', 'staging', 'production', 'prod',
    'release', 'hotfix', 'trunk', 'stable', 'next', 'canary', 'beta',
    'alpha', 'nightly',
})


def get_project_display_name(project_path: str) -> str:
    """Get a display name for a project, handling worktrees and branch-named dirs.

    For git worktrees, returns "repo/branch" (e.g., "kingsage/main").
    For directories named after common branches, returns "parent/name".
    Otherwise returns just the directory name.
    """
    path = Path(project_path)
    name = path.name

    # Check for git worktree: .git is a file (not a directory)
    git_path = path / '.git'
    if git_path.is_file():
        try:
            content = git_path.read_text().strip()
            # Worktrees have: gitdir: /path/to/repo.git/worktrees/branch
            # Submodules have: gitdir: ../.git/modules/name
            if content.startswith('gitdir:'):
                gitdir = content.split(':', 1)[1].strip()
                if '/worktrees/' in gitdir:
                    # Extract the repo name from the bare repo path
                    # e.g., /home/user/projects/kingsage/kingsage.git/worktrees/main
                    #   → bare repo path: /home/user/projects/kingsage/kingsage.git
                    worktrees_idx = gitdir.index('/worktrees/')
                    bare_path = Path(gitdir[:worktrees_idx])
                    repo_name = bare_path.stem  # "kingsage.git" → "kingsage"
                    return f"{repo_name}/{name}"
        except (IOError, ValueError):
            pass

    # Fallback: if directory name is a common branch name, qualify with parent
    if name.lower() in _COMMON_BRANCH_NAMES:
        return f"{path.parent.name}/{name}"

    return name


def format_git_summary(git_data: Dict) -> str:
    """Format git data into a human-readable summary string."""
    if not git_data.get('is_git_repo'):
        return "Not a git repository"

    commits = git_data.get('commits', [])
    stats = git_data.get('stats', {})

    if not commits:
        return "No commits"

    lines = []
    lines.append(f"{len(commits)} commit{'s' if len(commits) != 1 else ''}")

    added = stats.get('lines_added', 0)
    removed = stats.get('lines_removed', 0)
    files = stats.get('files_changed', 0)

    if added or removed:
        lines.append(f"+{added}/-{removed} lines in {files} file{'s' if files != 1 else ''}")

    return ", ".join(lines)
