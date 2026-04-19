"""Verify AnalysisRunner emits the expected ordered event stream.

Drives the runner against a stub TradingAgentsGraph that yields fake LangGraph
chunks, so this runs without any LLM call or network access.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

import pytest

from tradingagents import runner as runner_mod
from tradingagents.runner import AnalysisRunner, RunnerConfig
from tradingagents.runner_events import (
    AgentStatusEvent,
    DoneEvent,
    ReportSectionEvent,
    StatusEvent,
)


class _StubPropagator:
    def create_initial_state(self, *args, **kwargs) -> Dict[str, Any]:
        return {}

    def get_graph_args(self, **kwargs) -> Dict[str, Any]:
        return {}


class _StubInnerGraph:
    def __init__(self, chunks):
        self._chunks = chunks

    def stream(self, init_state, **kwargs):
        for c in self._chunks:
            yield c


class _StubGraph:
    """Stand-in for TradingAgentsGraph."""

    def __init__(self, *_, **__):
        self.propagator = _StubPropagator()
        self.graph = _StubInnerGraph(_FAKE_CHUNKS)

    def process_signal(self, decision: str) -> str:
        return "BUY"


_FAKE_CHUNKS: List[Dict[str, Any]] = [
    {"messages": [], "market_report": "## Market\nlooks strong"},
    {"messages": [], "sentiment_report": "## Social\nbullish"},
    {"messages": [], "news_report": "## News\nneutral"},
    {"messages": [], "fundamentals_report": "## Fundamentals\nsolid"},
    {
        "messages": [],
        "investment_debate_state": {
            "bull_history": "bull case",
            "bear_history": "bear case",
            "judge_decision": "research mgr says BUY",
        },
    },
    {"messages": [], "trader_investment_plan": "Trade plan: BUY"},
    {
        "messages": [],
        "risk_debate_state": {
            "aggressive_history": "agg",
            "conservative_history": "con",
            "neutral_history": "neu",
            "judge_decision": "PM says BUY",
        },
        "final_trade_decision": "BUY",
    },
]


def test_runner_emits_expected_event_sequence(tmp_path: Path) -> None:
    events: list = []
    cfg = RunnerConfig(
        ticker="TEST",
        analysis_date="2025-01-02",
        analysts=["market", "social", "news", "fundamentals"],
    )
    with patch.object(runner_mod, "TradingAgentsGraph", _StubGraph):
        runner = AnalysisRunner(
            config=cfg,
            on_event=events.append,
            save_dir=tmp_path,
        )
        runner.run()

    types = [type(e).__name__ for e in events]
    # Lifecycle bookends
    assert StatusEvent.__name__ in types
    assert types[-1] == "StatusEvent"
    assert events[-1].status == "done"
    # First event is the running status
    first_status = next(e for e in events if isinstance(e, StatusEvent))
    assert first_status.status == "running"

    # Each analyst transitioned at least once and is finally completed
    final_status = {}
    for e in events:
        if isinstance(e, AgentStatusEvent):
            final_status[e.agent] = e.status
    for agent in ("Market Analyst", "Social Analyst", "News Analyst", "Fundamentals Analyst",
                  "Bull Researcher", "Bear Researcher", "Research Manager",
                  "Trader",
                  "Aggressive Analyst", "Conservative Analyst", "Neutral Analyst",
                  "Portfolio Manager"):
        assert final_status.get(agent) == "completed", f"{agent} not completed"

    # Every report section emitted at least once
    sections_seen = {e.section for e in events if isinstance(e, ReportSectionEvent)}
    for required in ("market_report", "sentiment_report", "news_report",
                     "fundamentals_report", "investment_plan",
                     "trader_investment_plan", "final_trade_decision"):
        assert required in sections_seen

    # Done event carries the decision and a report path
    done = [e for e in events if isinstance(e, DoneEvent)]
    assert done and done[-1].decision == "BUY"
    assert (runner.save_path / "complete_report.md").exists()


def test_runner_dedups_repeat_status(tmp_path: Path) -> None:
    """Identical agent_status updates should not be re-emitted."""
    events: list = []
    cfg = RunnerConfig(ticker="DUP", analysis_date="2025-01-02", analysts=["market"])
    with patch.object(runner_mod, "TradingAgentsGraph", _StubGraph):
        AnalysisRunner(config=cfg, on_event=events.append, save_dir=tmp_path).run()

    # No two consecutive AgentStatusEvents for the same (agent, status)
    last: dict = {}
    for e in events:
        if isinstance(e, AgentStatusEvent):
            assert last.get(e.agent) != e.status
            last[e.agent] = e.status


def test_runner_save_paths_do_not_collide(tmp_path: Path) -> None:
    """Two runners constructed back-to-back for the same ticker get distinct paths."""
    cfg = RunnerConfig(ticker="SAME", analysis_date="2025-01-02", analysts=["market"])
    with patch.object(runner_mod, "TradingAgentsGraph", _StubGraph):
        paths = {
            AnalysisRunner(config=cfg, save_dir=tmp_path).save_path
            for _ in range(20)
        }
    assert len(paths) == 20


def test_coerce_tool_args_handles_none_and_scalars() -> None:
    from tradingagents.runner import _coerce_tool_args

    assert _coerce_tool_args(None) == {}
    assert _coerce_tool_args({"a": 1}) == {"a": 1}
    # Non-mapping payload must not raise; gets wrapped.
    out = _coerce_tool_args(42)
    assert isinstance(out, dict)
    assert out.get("value") == 42 or out == {}  # tolerate either policy


def test_runner_config_normalizes_and_validates_analysts() -> None:
    cfg = RunnerConfig(
        ticker=" test ",
        analysis_date="2025-01-02",
        analysts=["Market", "market", "news"],
    )
    assert cfg.ticker == "TEST"
    assert cfg.analysts == ["market", "news"]

    with pytest.raises(ValueError, match="Unknown analyst"):
        RunnerConfig(
            ticker="TEST",
            analysis_date="2025-01-02",
            analysts=["market", "invalid"],
        )
