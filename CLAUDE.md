# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CC-Summarize is a Python CLI tool for managing, viewing, and summarizing Claude Code sessions. It parses JSONL session files from `~/.claude/projects/`, extracts messages by type, and can generate AI-powered summaries of conversation turns.

## Core Architecture

### Data Flow

1. `session_finder.py` locates JSONL files in `~/.claude/projects/-path-to-project/`
2. `parser.py` parses JSONL → `Message` objects → `ConversationTurn` groups
3. Messages are categorized: `user`, `assistant`, `subagent`, `plan`, `session_summary`, `tool_response`, `system_noise`
4. Summarizers (`sdk_summarizer.py`, `no_ai_summarizer.py`) process turns
5. Formatters (`src/formatters/`) output results in terminal/plain/markdown/jsonl

### Package Structure

```
cc_summarize.py         # CLI entry point (Click framework)
src/
  __init__.py           # Package exports
  config.py             # Centralized constants (truncation limits, model name)
  parser.py             # JSONL parser, Message/ConversationTurn dataclasses
  session_finder.py     # Session discovery, path conversion
  cache.py              # Summary caching with SummaryResult
  summarizer.py         # Claude Agent SDK summarization
  no_ai_summarizer.py   # Non-AI message extraction
  date_parser.py        # Date/time parsing utilities
  utils/                # Shared utilities
    __init__.py
    content.py          # extract_user_content(), truncate_content()
    timestamp.py        # parse_iso_timestamp(), format_timestamp_*()
    formatting.py       # format_file_size()
    tools.py            # compact_tool_calls() for summarization
  formatters/           # Output formatters (all inherit BaseFormatter)
    base.py             # Abstract BaseFormatter interface
    terminal.py         # Rich terminal output
    plain.py            # Plain text (for piping)
    markdown.py         # Markdown document
    jsonl.py            # Structured JSONL
  cli/                  # CLI modules
    summary_gen.py      # generate_commit_summary(), generate_requirements_summary()
    validation.py       # Input validation utilities
tests/
  conftest.py           # Pytest configuration
  test_utils/           # Tests for utility functions
```

### Key Data Structures

- **Message** (`src/parser.py`): Individual message with uuid, type, content, timestamp, message_category
- **ConversationTurn** (`src/parser.py`): Groups user message with assistant responses
- **BaseFormatter** (`src/formatters/base.py`): Abstract interface all formatters implement

## Development Commands

```bash
# Install in editable mode
pip install -e .

# Install with dev dependencies (pytest)
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Basic usage - show user messages only
cc-summarize

# List sessions for current project
cc-summarize --list

# Generate AI summaries (requires Claude Code CLI)
cc-summarize --summarize normal
cc-summarize --summarize detailed

# Generate specialized summaries
cc-summarize --summary commit       # conventional commit message from git diff
cc-summarize --summary requirements # extract user requirements from session

# Include additional message types
cc-summarize --with-assistant --with-plans
cc-summarize --with-all

# Output formats and filtering
cc-summarize --format markdown --since 3d
cc-summarize --format jsonl -o output.jsonl
```

### Environment Setup
- `CC_SUMMARIZE_CACHE_DIR`: Optional custom cache directory (default: `~/.cache/cc-summarize/`)
- AI summarization requires Claude Code CLI to be installed and authenticated

## Important Implementation Details

- Project paths are converted to Claude's hyphenated format: `/home/user/my-app` → `-home-user-my-app`
- Sessions are automatically deduplicated when processing multiple files (by UUID and content hash)
- Caching prevents expensive re-summarization of identical content
- SDK session files are isolated in `~/.local/share/cc-summarize/claude/` to avoid polluting user's Claude history
- Message categorization happens in `parser.py:categorize_messages()` using heuristics
- All formatters implement `BaseFormatter` with `format_session_summary()`, `format_session_list()`, `format_messages()`
- Shared utilities in `src/utils/` eliminate code duplication (timestamp parsing, content extraction)
- Configuration constants centralized in `src/config.py`
