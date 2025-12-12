# CC-Summarize

A CLI tool for managing, viewing, and summarizing Claude Code sessions.

## Features

- Extract and format Claude Code session messages
- Multiple output formats (terminal, plain, markdown, JSONL)
- AI-powered summarization using Claude Agent SDK
- Smart caching to avoid re-summarizing identical content
- Date-based filtering and session management
- Generate specialized summaries (commit messages, requirements extraction)

## Installation

```bash
pip install cc-summarize
```

AI summarization uses the Claude Agent SDK. Ensure it's configured with your Anthropic API key or authenticated account.

## Usage

```bash
# List sessions for current project
cc-summarize --list

# Show user messages only (default)
cc-summarize

# Include additional message types
cc-summarize --with-assistant --with-plans
cc-summarize --with-all

# Generate AI summaries (requires Claude Agent SDK)
cc-summarize --summarize normal
cc-summarize --summarize detailed

# Generate specialized summaries
cc-summarize --summary commit        # conventional commit from git diff
cc-summarize --summary requirements  # extract user requirements

# Filter by date
cc-summarize --since 3d
cc-summarize --since 2h
cc-summarize --from 2024-12-01

# Output formats
cc-summarize --format markdown
cc-summarize --format jsonl -o output.jsonl
cc-summarize --format plain | less
```

## Output Formats

- **terminal** (default): Rich formatted output with colors
- **plain**: Plain text suitable for piping (auto-enabled when not a TTY)
- **markdown**: Markdown document format
- **jsonl**: Structured JSON Lines for programmatic use

## Requirements

- Python 3.10+
- Claude Code sessions in `~/.claude/projects/`
- For AI summaries: configured Claude Agent SDK (API key or authenticated account)

## Environment Variables

- `CC_SUMMARIZE_CACHE_DIR`: Custom cache directory (default: `~/.cache/cc-summarize/`)

## License

CC0-1.0
