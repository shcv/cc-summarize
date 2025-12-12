"""Timing estimation for summarization using collected statistics."""

import json
import os
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
import numpy as np


def get_data_dir() -> Path:
    """Get XDG data directory for cc-summarize."""
    xdg_data = os.environ.get('XDG_DATA_HOME', os.path.expanduser('~/.local/share'))
    return Path(xdg_data) / 'cc-summarize'


@dataclass
class TimingSample:
    """A single timing measurement."""
    duration_seconds: float
    num_messages: int
    num_tools: int
    content_length: int


class TimingEstimator:
    """Estimates summarization time using collected data and linear regression.

    With 0-1 samples: uses simple heuristic
    With 2+ samples: uses least squares regression to learn coefficients
    Each new sample refines the model.
    """

    def __init__(self):
        self.samples: List[TimingSample] = []
        self.coefficients: Optional[np.ndarray] = None
        self._load_samples()

    def _get_stats_file(self) -> Path:
        """Get path to timing statistics file."""
        data_dir = get_data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir / 'timing_stats.json'

    def _load_samples(self):
        """Load saved timing samples from disk."""
        stats_file = self._get_stats_file()
        if stats_file.exists():
            try:
                with open(stats_file, 'r') as f:
                    data = json.load(f)
                self.samples = [TimingSample(**s) for s in data.get('samples', [])]
                self._fit_model()
            except (json.JSONDecodeError, KeyError, TypeError):
                self.samples = []

    def _save_samples(self):
        """Save timing samples to disk."""
        stats_file = self._get_stats_file()
        # Keep only last 100 samples to avoid unbounded growth
        recent_samples = self.samples[-100:]
        data = {'samples': [asdict(s) for s in recent_samples]}
        with open(stats_file, 'w') as f:
            json.dump(data, f, indent=2)

    def _fit_model(self):
        """Fit linear regression model to samples."""
        if len(self.samples) < 2:
            self.coefficients = None
            return

        # Build feature matrix: [1, num_messages, num_tools, content_length/1000]
        X = np.array([
            [1, s.num_messages, s.num_tools, s.content_length / 1000]
            for s in self.samples
        ])
        y = np.array([s.duration_seconds for s in self.samples])

        # Least squares: (X^T X)^-1 X^T y
        try:
            self.coefficients = np.linalg.lstsq(X, y, rcond=None)[0]
        except np.linalg.LinAlgError:
            self.coefficients = None

    def add_sample(self, duration: float, num_messages: int, num_tools: int, content_length: int):
        """Add a new timing sample and update the model."""
        sample = TimingSample(
            duration_seconds=duration,
            num_messages=num_messages,
            num_tools=num_tools,
            content_length=content_length
        )
        self.samples.append(sample)
        self._fit_model()
        self._save_samples()

    def estimate_duration(self, num_messages: int, num_tools: int, content_length: int) -> float:
        """Estimate duration for a turn with given characteristics.

        Returns estimated seconds.
        """
        if self.coefficients is not None and len(self.samples) >= 2:
            # Use learned model
            features = np.array([1, num_messages, num_tools, content_length / 1000])
            estimate = float(np.dot(self.coefficients, features))
            # Clamp to reasonable range (at least 1 second, at most 5 minutes)
            return max(1.0, min(300.0, estimate))
        elif len(self.samples) == 1:
            # One sample: use ratio based on content length
            s = self.samples[0]
            if s.content_length > 0:
                ratio = content_length / s.content_length
                return max(1.0, s.duration_seconds * ratio)
            return s.duration_seconds
        else:
            # No samples: use simple heuristic (rough guess)
            # Assume ~2 seconds base + 0.5s per message + 0.2s per tool + 0.001s per char
            return 2.0 + num_messages * 0.5 + num_tools * 0.2 + content_length * 0.001

    def get_turn_features(self, turn) -> Tuple[int, int, int]:
        """Extract features from a conversation turn."""
        num_messages = len(turn.assistant_messages)
        num_tools = sum(1 for m in turn.assistant_messages if m.tool_name)

        content_length = 0
        for msg in turn.assistant_messages:
            if isinstance(msg.content, str):
                content_length += len(msg.content)
            elif isinstance(msg.content, list):
                for item in msg.content:
                    if isinstance(item, dict) and item.get('type') == 'text':
                        content_length += len(item.get('text', ''))

        return num_messages, num_tools, content_length

    def estimate_turn_duration(self, turn) -> float:
        """Estimate duration for a conversation turn."""
        num_messages, num_tools, content_length = self.get_turn_features(turn)
        return self.estimate_duration(num_messages, num_tools, content_length)

    def get_stats(self) -> Dict:
        """Get current model statistics."""
        return {
            'num_samples': len(self.samples),
            'coefficients': self.coefficients.tolist() if self.coefficients is not None else None,
            'has_model': self.coefficients is not None,
        }
