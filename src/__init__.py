"""Claude Code Session Summarizer.

A Python CLI tool for managing, viewing, and summarizing Claude Code sessions.
"""

__version__ = "1.2.0"

from .parser import SessionParser, Message, ConversationTurn
from .session_finder import (
    list_sessions,
    find_session_by_id,
    SessionNotFoundError,
    format_no_sessions_error,
)
from .cache import SummaryCache, SummaryResult
from .config import (
    CONTENT_TRUNCATION_TERMINAL,
    CONTENT_TRUNCATION_USER,
    DEFAULT_MODEL,
    DEFAULT_SEPARATOR,
)

__all__ = [
    # Core classes
    'SessionParser',
    'Message',
    'ConversationTurn',
    # Session discovery
    'list_sessions',
    'find_session_by_id',
    'SessionNotFoundError',
    'format_no_sessions_error',
    # Cache
    'SummaryCache',
    'SummaryResult',
    # Config
    'CONTENT_TRUNCATION_TERMINAL',
    'CONTENT_TRUNCATION_USER',
    'DEFAULT_MODEL',
    'DEFAULT_SEPARATOR',
]
