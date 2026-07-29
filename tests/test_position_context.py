"""Tests for the optional per-run position note.

The note rides on ``instrument_context``, which is the one string every agent
already reads, so these cover the two ends: it reaches the context when set,
and the API bounds it before it lands in a prompt.
"""

from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.runner import RunnerConfig
from web.backend.api import StartRunRequest


def _context(config: dict) -> str:
    graph = MagicMock(spec=TradingAgentsGraph)
    graph.config = config
    with patch(
        "tradingagents.graph.trading_graph.resolve_instrument_identity",
        return_value={"company_name": "ServiceNow"},
    ):
        return TradingAgentsGraph.resolve_instrument_context(graph, "NOW")


@pytest.mark.unit
class TestPositionContextInPrompt:
    def test_note_reaches_the_instrument_context(self):
        out = _context({"position_context": "200 sh @ 412, ~6% of book"})
        assert "200 sh @ 412, ~6% of book" in out

    def test_note_carries_the_anti_anchoring_instruction(self):
        """A bare position note invites rationalizing the existing holding."""
        out = _context({"position_context": "200 sh @ 412"}).lower()
        assert "not evidence" in out
        assert "cost basis" in out

    @pytest.mark.parametrize("config", [{}, {"position_context": ""}, {"position_context": "   "}])
    def test_absent_note_leaves_context_unchanged(self, config):
        assert "current position" not in _context(config)


@pytest.mark.unit
class TestRunnerConfigThreading:
    def test_position_context_reaches_graph_config(self):
        cfg = RunnerConfig(
            ticker="NOW",
            analysis_date="2026-07-29",
            analysts=["market"],
            position_context="200 sh @ 412",
        ).to_graph_config()
        assert cfg["position_context"] == "200 sh @ 412"

    def test_defaults_to_position_agnostic(self):
        cfg = RunnerConfig(
            ticker="NOW", analysis_date="2026-07-29", analysts=["market"]
        ).to_graph_config()
        assert cfg["position_context"] == ""


@pytest.mark.unit
class TestApiBoundaryValidation:
    def _request(self, note: str) -> StartRunRequest:
        return StartRunRequest(
            ticker="NOW", analysis_date="2026-07-29", position_context=note
        )

    def test_strips_control_characters(self):
        """Control chars can smuggle structure into the prompt."""
        assert self._request("200 sh\x00\x1b[31m @ 412").position_context == (
            "200 sh[31m @ 412"
        )

    def test_keeps_newlines_and_trims(self):
        assert self._request("  200 sh\n6% of book  ").position_context == (
            "200 sh\n6% of book"
        )

    def test_rejects_oversized_note(self):
        with pytest.raises(ValidationError):
            self._request("x" * 501)

    def test_defaults_to_empty(self):
        assert StartRunRequest(
            ticker="NOW", analysis_date="2026-07-29"
        ).position_context == ""
