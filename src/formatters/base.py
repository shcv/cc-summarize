"""Base formatter interface for output formatters."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, TextIO, Optional


class BaseFormatter(ABC):
    """Abstract base class for all output formatters.

    All formatters should implement these methods to ensure
    consistent interface across different output formats.
    """

    @abstractmethod
    def format_session_summary(
        self,
        turns: List,
        summaries: List,
        session_metadata: Dict[str, Any],
        include_metadata: bool = False,
        output_file: Optional[TextIO] = None
    ) -> Optional[str]:
        """Format a complete session summary.

        Args:
            turns: List of ConversationTurn objects
            summaries: List of SummaryResult objects
            session_metadata: Session metadata dict
            include_metadata: Whether to include timestamps, tokens, etc.
            output_file: Optional file to write output to

        Returns:
            Formatted string, or None if output was written directly
        """
        pass

    @abstractmethod
    def format_session_list(
        self,
        sessions: List[Dict[str, Any]],
        output_file: Optional[TextIO] = None,
        verbose: bool = False
    ) -> Optional[str]:
        """Format a list of available sessions.

        Args:
            sessions: List of session metadata dicts
            output_file: Optional file to write output to
            verbose: Whether to show full session IDs

        Returns:
            Formatted string, or None if output was written directly
        """
        pass

    @abstractmethod
    def format_messages(
        self,
        messages: List[Dict],
        session_metadata: Dict[str, Any],
        include_metadata: bool = False,
        output_file: Optional[TextIO] = None
    ) -> Optional[str]:
        """Format categorized messages.

        Args:
            messages: List of message dicts with category, content, etc.
            session_metadata: Session metadata dict
            include_metadata: Whether to include timestamps, etc.
            output_file: Optional file to write output to

        Returns:
            Formatted string, or None if output was written directly
        """
        pass

    def format_cache_stats(
        self,
        stats: Dict[str, int],
        output_file: Optional[TextIO] = None
    ) -> Optional[str]:
        """Format cache statistics.

        Optional method - default implementation returns None.

        Args:
            stats: Cache statistics dict
            output_file: Optional file to write output to

        Returns:
            Formatted string, or None if not implemented/output written directly
        """
        return None
