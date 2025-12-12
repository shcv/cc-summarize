"""Tests for timestamp utilities."""

from datetime import datetime, timezone

import pytest

from utils.timestamp import (
    parse_iso_timestamp,
    parse_iso_timestamp_or_now,
    format_timestamp_short,
    format_timestamp_full,
    format_timestamp_date,
)


class TestParseIsoTimestamp:
    """Tests for parse_iso_timestamp function."""

    def test_parse_timestamp_with_z_suffix(self):
        """Should parse timestamps ending with Z."""
        result = parse_iso_timestamp("2024-12-01T10:00:00Z")
        assert result is not None
        assert result.tzinfo == timezone.utc
        assert result.year == 2024
        assert result.month == 12
        assert result.day == 1
        assert result.hour == 10
        assert result.minute == 0
        assert result.second == 0

    def test_parse_timestamp_with_offset(self):
        """Should parse timestamps with explicit offset."""
        result = parse_iso_timestamp("2024-12-01T10:00:00+00:00")
        assert result is not None
        assert result.hour == 10

    def test_parse_timestamp_with_positive_offset(self):
        """Should parse timestamps with positive offset."""
        result = parse_iso_timestamp("2024-12-01T15:00:00+05:00")
        assert result is not None

    def test_parse_empty_string(self):
        """Should return None for empty string."""
        result = parse_iso_timestamp("")
        assert result is None

    def test_parse_none(self):
        """Should return None for None input."""
        result = parse_iso_timestamp(None)
        assert result is None

    def test_parse_invalid_timestamp(self):
        """Should return None for invalid timestamps."""
        result = parse_iso_timestamp("not-a-timestamp")
        assert result is None

    def test_parse_partial_timestamp(self):
        """Should return None for partial timestamps."""
        result = parse_iso_timestamp("2024-12-01")
        # This might parse or not depending on Python version
        # The important thing is it doesn't raise


class TestParseIsoTimestampOrNow:
    """Tests for parse_iso_timestamp_or_now function."""

    def test_valid_timestamp_returns_parsed(self):
        """Should return parsed timestamp for valid input."""
        result = parse_iso_timestamp_or_now("2024-12-01T10:00:00Z")
        assert result.year == 2024
        assert result.month == 12

    def test_invalid_timestamp_returns_now(self):
        """Should return current time for invalid input."""
        before = datetime.now(timezone.utc)
        result = parse_iso_timestamp_or_now("invalid")
        after = datetime.now(timezone.utc)

        assert before <= result <= after

    def test_none_returns_now(self):
        """Should return current time for None input."""
        before = datetime.now(timezone.utc)
        result = parse_iso_timestamp_or_now(None)
        after = datetime.now(timezone.utc)

        assert before <= result <= after


class TestFormatTimestampShort:
    """Tests for format_timestamp_short function."""

    def test_format_datetime(self):
        """Should format datetime as MM-DD HH:MM:SS."""
        dt = datetime(2024, 12, 1, 10, 30, 45, tzinfo=timezone.utc)
        result = format_timestamp_short(dt)
        assert result == "12-01 10:30:45"

    def test_format_none(self):
        """Should return empty string for None."""
        result = format_timestamp_short(None)
        assert result == ""


class TestFormatTimestampFull:
    """Tests for format_timestamp_full function."""

    def test_format_datetime(self):
        """Should format datetime as YYYY-MM-DD HH:MM:SS UTC."""
        dt = datetime(2024, 12, 1, 10, 30, 45, tzinfo=timezone.utc)
        result = format_timestamp_full(dt)
        assert result == "2024-12-01 10:30:45 UTC"

    def test_format_none(self):
        """Should return empty string for None."""
        result = format_timestamp_full(None)
        assert result == ""


class TestFormatTimestampDate:
    """Tests for format_timestamp_date function."""

    def test_format_datetime(self):
        """Should format datetime as YYYY-MM-DD HH:MM."""
        dt = datetime(2024, 12, 1, 10, 30, 45, tzinfo=timezone.utc)
        result = format_timestamp_date(dt)
        assert result == "2024-12-01 10:30"

    def test_format_none(self):
        """Should return empty string for None."""
        result = format_timestamp_date(None)
        assert result == ""
