"""Tests for formatting utilities."""

import pytest

from utils.formatting import format_file_size, format_file_size_short


class TestFormatFileSize:
    """Tests for format_file_size function."""

    def test_format_bytes(self):
        """Should format small sizes as bytes."""
        assert format_file_size(100) == "100B"
        assert format_file_size(1023) == "1023B"

    def test_format_kilobytes(self):
        """Should format KB sizes (>1024 bytes)."""
        result = format_file_size(1025)
        assert "KB" in result

        result = format_file_size(512 * 1024)
        assert "KB" in result

    def test_format_megabytes(self):
        """Should format MB sizes (>1MB)."""
        result = format_file_size(1024 * 1024 + 1)
        assert "MB" in result

        result = format_file_size(int(1.5 * 1024 * 1024))
        assert "MB" in result
        assert "1.5" in result

    def test_format_zero(self):
        """Should handle zero bytes."""
        result = format_file_size(0)
        assert result == "0B"


class TestFormatFileSizeShort:
    """Tests for format_file_size_short function."""

    def test_format_bytes(self):
        """Should format small sizes as bytes."""
        assert format_file_size_short(100) == "100B"

    def test_format_kilobytes_short(self):
        """Should use 'K' for kilobytes."""
        result = format_file_size_short(2048)
        assert "K" in result

    def test_format_megabytes_short(self):
        """Should use 'M' for megabytes."""
        result = format_file_size_short(2 * 1024 * 1024)
        assert "M" in result
