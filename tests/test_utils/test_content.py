"""Tests for content extraction utilities."""

import pytest

from utils.content import (
    extract_user_content,
    extract_text_from_content,
    truncate_content,
)


class TestExtractUserContent:
    """Tests for extract_user_content function."""

    def test_extract_plain_string(self):
        """Should return plain strings unchanged (after strip)."""
        result = extract_user_content("Hello, world!")
        assert result == "Hello, world!"

    def test_extract_string_with_whitespace(self):
        """Should strip whitespace from strings."""
        result = extract_user_content("  Hello, world!  ")
        assert result == "Hello, world!"

    def test_extract_removes_session_hooks(self):
        """Should remove session hook tags."""
        content = "<session-start-hook>config</session-start-hook>Actual message"
        result = extract_user_content(content)
        assert "<session-start-hook>" not in result
        assert "</session-start-hook>" not in result
        assert "Actual message" in result

    def test_extract_from_list_with_text(self):
        """Should extract text from list with text items."""
        content = [{"type": "text", "text": "Hello"}]
        result = extract_user_content(content)
        assert result == "Hello"

    def test_extract_from_list_multiple_text(self):
        """Should join multiple text items with newlines."""
        content = [
            {"type": "text", "text": "First line"},
            {"type": "text", "text": "Second line"},
        ]
        result = extract_user_content(content)
        assert "First line" in result
        assert "Second line" in result

    def test_extract_skips_tool_results(self):
        """Should skip tool_result items."""
        content = [
            {"type": "text", "text": "User message"},
            {"type": "tool_result", "content": "Some result"},
        ]
        result = extract_user_content(content)
        assert result == "User message"

    def test_extract_from_other_type(self):
        """Should convert other types to string."""
        result = extract_user_content(12345)
        assert result == "12345"

    def test_extract_empty_list(self):
        """Should return empty string for empty list."""
        result = extract_user_content([])
        assert result == ""


class TestExtractTextFromContent:
    """Tests for extract_text_from_content function."""

    def test_extract_plain_string(self):
        """Should return plain strings unchanged (after strip)."""
        result = extract_text_from_content("Hello, world!")
        assert result == "Hello, world!"

    def test_extract_from_list_text_items(self):
        """Should extract only text type items."""
        content = [
            {"type": "text", "text": "Hello"},
            {"type": "tool_use", "name": "Read"},
        ]
        result = extract_text_from_content(content)
        assert result == "Hello"

    def test_extract_skips_tool_use(self):
        """Should skip tool_use items."""
        content = [{"type": "tool_use", "name": "Read", "input": {}}]
        result = extract_text_from_content(content)
        assert result == ""


class TestTruncateContent:
    """Tests for truncate_content function."""

    def test_no_truncation_needed(self):
        """Should return content unchanged if under max length."""
        content = "Short content"
        result = truncate_content(content, max_length=100)
        assert result == content

    def test_truncation_at_exact_length(self):
        """Should return content unchanged at exact max length."""
        content = "1234567890"
        result = truncate_content(content, max_length=10)
        assert result == content

    def test_truncation_with_default_suffix(self):
        """Should truncate and add default suffix."""
        content = "This is a very long message"
        result = truncate_content(content, max_length=15)
        assert len(result) == 15
        assert result.endswith("...")

    def test_truncation_with_custom_suffix(self):
        """Should truncate and add custom suffix."""
        content = "This is a very long message"
        result = truncate_content(content, max_length=20, suffix="[more]")
        assert len(result) == 20
        assert result.endswith("[more]")

    def test_truncation_preserves_content_start(self):
        """Should preserve the start of the content."""
        content = "ABCDEFGHIJ"
        result = truncate_content(content, max_length=7)
        assert result.startswith("ABCD")
