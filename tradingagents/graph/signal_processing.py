# TradingAgents/graph/signal_processing.py

import re
from typing import Any

# Ordered by specificity: multi-word ratings first, then single-word
_RATING_PATTERNS = [
    r'\bOVERWEIGHT\b',
    r'\bUNDERWEIGHT\b',
    r'\bBUY\b',
    r'\bSELL\b',
    r'\bHOLD\b',
]
_COMBINED_RE = re.compile('|'.join(_RATING_PATTERNS), re.IGNORECASE)


class SignalProcessor:
    """Processes trading signals to extract actionable decisions."""

    def __init__(self, quick_thinking_llm: Any):
        """Initialize with an LLM for fallback processing."""
        self.quick_thinking_llm = quick_thinking_llm

    def process_signal(self, full_signal: str) -> str:
        """
        Process a full trading signal to extract the core decision.

        Uses regex extraction first; falls back to LLM only if no match found.

        Args:
            full_signal: Complete trading signal text

        Returns:
            Extracted rating (BUY, OVERWEIGHT, HOLD, UNDERWEIGHT, or SELL)
        """
        match = _COMBINED_RE.search(full_signal)
        if match:
            return match.group(0).upper()

        # Fallback to LLM if regex finds nothing
        messages = [
            (
                "system",
                "You are an efficient assistant that extracts the trading decision from analyst reports. "
                "Extract the rating as exactly one of: BUY, OVERWEIGHT, HOLD, UNDERWEIGHT, SELL. "
                "Output only the single rating word, nothing else.",
            ),
            ("human", full_signal),
        ]

        return self.quick_thinking_llm.invoke(messages).content
