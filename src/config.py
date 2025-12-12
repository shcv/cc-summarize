"""Configuration constants for cc-summarize."""

# Truncation limits
CONTENT_TRUNCATION_TERMINAL = 2000
CONTENT_TRUNCATION_USER = 1000
TOOL_COMMAND_TRUNCATION = 50
TOOL_ARG_TRUNCATION = 100

# Model configuration
DEFAULT_MODEL = "claude-3-5-haiku-20241022"

# Default separator for plain text output
DEFAULT_SEPARATOR = "—" * 24

# Tool filtering by detail level
MINIMAL_TOOLS = ['Edit', 'MultiEdit', 'Write', 'Bash']
NORMAL_TOOLS = MINIMAL_TOOLS + ['Read', 'Grep', 'Glob', 'LS', 'Task']
# DETAILED_TOOLS = None means show all tools

# Message categories
ALL_CATEGORIES = ['user', 'subagent', 'plan', 'assistant', 'session_summary']
EXCLUDED_CATEGORIES = {'system_noise', 'tool_response'}

# Category display labels
CATEGORY_LABELS = {
    'user': 'USER',
    'assistant': 'ASSISTANT',
    'subagent': 'SUBAGENT',
    'plan': 'PLAN',
    'session_summary': 'SUMMARY',
}
