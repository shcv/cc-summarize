"""AI-powered summary generation functions."""

import os
import subprocess
import shutil
from typing import Optional

import click


def generate_commit_summary(content: str, project_path: str) -> str:
    """Generate a conventional commit message for current git changes.

    Args:
        content: Session content to provide context
        project_path: Path to the project directory

    Returns:
        Generated commit message or error string
    """
    # Get git status and diff
    try:
        # Check for staged changes first
        staged_result = subprocess.run(
            ['git', 'diff', '--cached'],
            capture_output=True,
            text=True,
            cwd=project_path
        )

        # If no staged changes, get unstaged changes
        if not staged_result.stdout.strip():
            diff_result = subprocess.run(
                ['git', 'diff'],
                capture_output=True,
                text=True,
                cwd=project_path
            )
            git_diff = diff_result.stdout
            change_type = "unstaged"
        else:
            git_diff = staged_result.stdout
            change_type = "staged"

        if not git_diff.strip():
            return "No changes to commit (working directory clean)"

    except Exception as e:
        return f"Error getting git diff: {e}"

    commit_prompt = f"""Generate a conventional commit message for these {change_type} changes.

Session context (what led to these changes):
{content}

Git diff:
{git_diff}

Requirements:
- Use conventional commit format: type(scope): description
- Types: feat, fix, refactor, docs, test, chore, style, perf
- Keep the first line under 72 characters
- Add a blank line and detailed body if needed
- Consider the session history to understand WHY these changes were made
- Focus on the intent and impact, not just the mechanics

Generate ONLY the commit message, nothing else."""

    return _run_ai_prompt(commit_prompt, project_path)


def generate_requirements_summary(content: str, project_path: str) -> str:
    """Extract requirements from user messages, including implied corrections.

    Args:
        content: Session content to extract requirements from
        project_path: Path to the project directory

    Returns:
        Extracted requirements or error string
    """
    requirements_prompt = f"""Extract and list all requirements specified or implied by the user in this session.

Session content (focus on USER messages):
{content}

Instructions:
- List each requirement as a bullet point
- Include explicit requirements (what user directly asked for)
- Include implicit requirements (inferred from corrections or follow-ups)
- When the user corrects the assistant, note what requirement was misunderstood
- Group related requirements together
- Be specific about what was requested

Format:
## Explicit Requirements
- [requirement 1]
- [requirement 2]

## Implied/Corrected Requirements
- [correction 1 - what was misunderstood and what was actually needed]
- [correction 2]

Generate the requirements extraction:"""

    return _run_ai_prompt(requirements_prompt, project_path)


def generate_work_summary(content: str, project_path: str) -> str:
    """Generate a detailed summary of all work done.

    Args:
        content: Session content to summarize
        project_path: Path to the project directory

    Returns:
        Generated work summary or error string
    """
    summary_prompt = """Please provide a detailed summary of all the work done in this Claude Code session.

Focus on:
- What features were implemented or bugs were fixed
- What files were modified and how
- What technical decisions were made
- Any important patterns or approaches used
- Overall project progress and outcomes

Session content:
---
""" + content

    return _run_ai_prompt(summary_prompt, project_path)


def _run_ai_prompt(prompt: str, project_path: str) -> str:
    """Run an AI prompt using SDK or API.

    Args:
        prompt: The prompt to send to the AI
        project_path: Path to the project directory

    Returns:
        AI response or raises RuntimeError
    """
    # Try SDK first (check if claude command exists)
    if shutil.which('claude'):
        try:
            result = subprocess.run(
                ['claude'],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=120
            )
            if result.returncode == 0:
                return result.stdout.strip()
            else:
                click.echo(f"SDK generation failed with code {result.returncode}: {result.stderr}", err=True)
        except Exception as e:
            click.echo(f"SDK generation exception: {e}", err=True)

    # Fallback to API
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if api_key:
        return _run_api_prompt(prompt, api_key)

    raise RuntimeError("Neither Claude Code SDK nor API key available for generation")


def _run_api_prompt(prompt: str, api_key: str) -> str:
    """Run a prompt using the Anthropic API via subprocess.

    Uses subprocess to avoid pydantic conflicts.

    Args:
        prompt: The prompt to send
        api_key: Anthropic API key

    Returns:
        API response text or raises RuntimeError
    """
    import json
    import tempfile

    # Create a temp script to run anthropic
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(f'''
import json
from anthropic import Anthropic

api_key = "{api_key}"
prompt = json.loads(r"""{json.dumps(prompt)}""")

client = Anthropic(api_key=api_key)
response = client.messages.create(
    model="claude-3-5-haiku-20241022",
    max_tokens=4096,
    messages=[{{"role": "user", "content": prompt}}]
)
print(response.content[0].text)
''')
        temp_script = f.name

    try:
        result = subprocess.run(
            ['python', temp_script],
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode == 0:
            return result.stdout.strip()
        else:
            click.echo(f"API generation failed: {result.stderr}", err=True)
            raise RuntimeError(f"API generation failed: {result.stderr}")
    finally:
        # Clean up temp file
        os.unlink(temp_script)
