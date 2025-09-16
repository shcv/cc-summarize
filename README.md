# CC-Summarize

A tool for managing, viewing, and summarizing Claude Code sessions.

## Features

- Extract and format Claude Code session messages
- Multiple output formats (plain, terminal, markdown, JSONL)
- AI-powered summarization with both API and SDK backends
- Smart caching and filtering capabilities
- Date-based filtering and session management

## Installation

```bash
pip install cc-summarize
```

## Usage

```bash
# List sessions for current project
cc-summarize --list

# Show user messages only
cc-summarize

# Generate AI summaries
cc-summarize --summarize normal

# Filter by date
cc-summarize --since 3d

# Multiple output formats
cc-summarize --format markdown
```

## Requirements

- Python 3.10+
- Claude Code sessions in `~/.claude/projects/`
- Optional: ANTHROPIC_API_KEY for API-based summarization
- Optional: Claude Code SDK for local summarization