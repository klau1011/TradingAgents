"""Verify AnalysisRunner emits the expected ordered event stream.

Drives the runner against a stub TradingAgentsGraph that yields fake LangGraph
chunks, so this runs without any LLM call or network access.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any
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
    def create_initial_state(self, *args, **kwargs) -> dict[str, Any]:
        return {}

    def get_graph_args(self, **kwargs) -> dict[str, Any]:
        return {"config": {}}


class _StubInnerGraph:
    def __init__(self, chunks):
        self._chunks = chunks

    def stream(self, init_state, **kwargs):
        yield from self._chunks


class _RunnerGraphAPI:
    @contextmanager
    def checkpoint_scope(self, *args):
        self.checkpoint_open = True
        try:
            yield "test-thread"
        finally:
            self.checkpoint_open = False

    def create_run_state(self, *args):
        return {}

    def checkpoint_input(self, state):
        return state

    def stream_run(self, state, **args):
        for chunk in self.graph.stream(state, **args):
            yield chunk.get("messages", []), chunk

    def record_decision(self, *args):
        self.recorded = args[-1]

    def clear_checkpoint_on_success(self, *args):
        self.cleared = True

    def save_reports(self, state, ticker, path):
        return runner_mod.save_report_to_disk(state, ticker, path)


class _StubGraph(_RunnerGraphAPI):
    """Stand-in for TradingAgentsGraph."""

    def __init__(self, *_, **__):
        self.propagator = _StubPropagator()
        self.graph = _StubInnerGraph(_FAKE_CHUNKS)

    def process_signal(self, decision: str) -> str:
        return "BUY"


_FAKE_CHUNKS: list[dict[str, Any]] = [
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
        "final_trade_decision": "Rating: Buy\nPM says BUY",
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
    for agent in ("Market Analyst", "Sentiment Analyst", "News Analyst", "Fundamentals Analyst",
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

    # Done event carries the decision, a report path, and the opaque folder
    # reference the web UI links to
    done = [e for e in events if isinstance(e, DoneEvent)]
    assert done and done[-1].decision == "Buy"
    assert done[-1].report_folder == runner.save_path.name
    report = runner.save_path / "complete_report.md"
    assert report.exists()
    report_text = report.read_text(encoding="utf-8")
    assert "## Market\nlooks strong" in report_text
    assert "PM says BUY" in report_text


def test_runner_error_event_is_sanitized(tmp_path: Path) -> None:
    """ErrorEvent messages are rendered verbatim in browsers, so they must
    carry the exception summary only — no traceback / server internals."""
    from tradingagents.runner_events import ErrorEvent

    class _BoomInner:
        def stream(self, init_state, **kwargs):
            raise RuntimeError("boom")
            yield  # pragma: no cover

    class _BoomGraph(_RunnerGraphAPI):
        def __init__(self, *_, **__):
            self.propagator = _StubPropagator()
            self.graph = _BoomInner()

    events: list = []
    cfg = RunnerConfig(ticker="ERR", analysis_date="2025-01-02", analysts=["market"])
    with patch.object(runner_mod, "TradingAgentsGraph", _BoomGraph):
        runner = AnalysisRunner(config=cfg, on_event=events.append, save_dir=tmp_path)
        with pytest.raises(RuntimeError):
            runner.run()

    errors = [e for e in events if isinstance(e, ErrorEvent)]
    assert errors and errors[-1].message == "RuntimeError: boom"
    assert "Traceback" not in errors[-1].message


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


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------


def test_run_status_includes_cancelled() -> None:
    """The wire-format Literal must list ``cancelled`` so type checkers and the
    TS mirror in ``web/frontend/src/types.ts`` stay aligned."""
    import typing

    from tradingagents.runner_events import RunStatus

    assert "cancelled" in typing.get_args(RunStatus)


def test_runner_raises_run_cancelled_when_event_set_before_start(
    tmp_path: Path,
) -> None:
    """Pre-set cancel events must be honored on the very first chunk."""
    import threading

    from tradingagents.runner import RunCancelled
    from tradingagents.runner_events import (
        ErrorEvent,
        MessageEvent,
        StatusEvent,
    )

    events: list = []
    cancel_event = threading.Event()
    cancel_event.set()

    cfg = RunnerConfig(
        ticker="TEST",
        analysis_date="2025-01-02",
        analysts=["market"],
    )
    with patch.object(runner_mod, "TradingAgentsGraph", _StubGraph):
        runner = AnalysisRunner(
            config=cfg,
            on_event=events.append,
            save_dir=tmp_path,
            cancel_event=cancel_event,
        )
        with pytest.raises(RunCancelled):
            runner.run()

    statuses = [e.status for e in events if isinstance(e, StatusEvent)]
    # Lifecycle: running -> cancelled (no done, no error).
    assert statuses[0] == "running"
    assert statuses[-1] == "cancelled"
    assert "done" not in statuses and "error" not in statuses
    # User-facing message went out.
    assert any(
        isinstance(e, MessageEvent) and "cancelled" in e.content.lower()
        for e in events
    )
    # No ErrorEvent for cooperative cancel.
    assert not any(isinstance(e, ErrorEvent) for e in events)


def test_runner_cancels_mid_stream_between_chunks(tmp_path: Path) -> None:
    """The cancel flag is checked between chunks; setting it after the first
    chunk yields cancellation before subsequent chunks run."""
    import threading

    from tradingagents.runner import RunCancelled
    from tradingagents.runner_events import StatusEvent

    cancel_event = threading.Event()
    chunks_seen: list[int] = []

    class _LongInner:
        def stream(self, init_state, **kwargs):
            for i in range(10):
                chunks_seen.append(i)
                if i == 1:
                    # Trip cancel after the second chunk has been processed;
                    # the loop should bail before chunk 2 emits anything.
                    cancel_event.set()
                yield {"messages": [], "market_report": f"chunk {i}"}

    class _LongGraph(_RunnerGraphAPI):
        def __init__(self, *_, **__):
            self.propagator = _StubPropagator()
            self.graph = _LongInner()

        def process_signal(self, decision: str) -> str:
            return "BUY"

    cfg = RunnerConfig(
        ticker="LONG",
        analysis_date="2025-01-02",
        analysts=["market"],
    )
    events: list = []
    with patch.object(runner_mod, "TradingAgentsGraph", _LongGraph):
        runner = AnalysisRunner(
            config=cfg,
            on_event=events.append,
            save_dir=tmp_path,
            cancel_event=cancel_event,
        )
        with pytest.raises(RunCancelled):
            runner.run()

    # We only consumed 2 chunks before bailing (cancel set after chunk 1).
    assert chunks_seen == [0, 1]
    statuses = [e.status for e in events if isinstance(e, StatusEvent)]
    assert statuses[-1] == "cancelled"


def test_runner_default_cancel_event_does_not_cancel(tmp_path: Path) -> None:
    """When no cancel_event is provided, the runner constructs an unset one and
    the run completes normally."""
    cfg = RunnerConfig(
        ticker="OK",
        analysis_date="2025-01-02",
        analysts=["market"],
    )
    with patch.object(runner_mod, "TradingAgentsGraph", _StubGraph):
        runner = AnalysisRunner(config=cfg, save_dir=tmp_path)
        assert runner.cancel_event is not None
        assert not runner.cancel_event.is_set()
        runner.run()  # no exception -> success


def test_runner_activates_ohlcv_cache_during_streaming(tmp_path: Path) -> None:
    """The per-run OHLCV cache must be active while the graph streams chunks.

    Regression: previously the cache scope only wrapped
    ``TradingAgentsGraph._run_graph``, but the web/CLI paths bypass that and
    stream directly via ``graph.graph.stream``. Without an active cache,
    duplicate yfinance fetches across analysts went undeduped.
    """
    from tradingagents.dataflows.ohlcv_cache import cache_get, cache_put

    seen_active: list[bool] = []

    class _CacheProbingInnerGraph(_StubInnerGraph):
        def stream(self, init_state, **kwargs):
            # Probe: writing then reading a key only round-trips when a cache
            # context is active; otherwise ``cache_get`` returns ``None``.
            cache_put(("probe",), "sentinel")
            seen_active.append(cache_get(("probe",)) == "sentinel")
            yield from super().stream(init_state, **kwargs)

    class _StubGraphWithProbe(_StubGraph):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self.graph = _CacheProbingInnerGraph(_FAKE_CHUNKS)

    cfg = RunnerConfig(ticker="CACHE", analysis_date="2025-01-02", analysts=["market"])
    with patch.object(runner_mod, "TradingAgentsGraph", _StubGraphWithProbe):
        AnalysisRunner(config=cfg, save_dir=tmp_path).run()

    assert seen_active == [True], (
        "OHLCV cache was not active inside AnalysisRunner._stream; "
        "yfinance dedup hooks would be no-ops on the web/CLI paths."
    )
    # And the cache must be torn down after the run (no leak across runs).
    assert cache_get(("probe",)) is None


def test_parallel_analysts_remain_active_until_their_reports(tmp_path):
    cfg = RunnerConfig(ticker="TEST", analysis_date="2025-01-02", analysts=["market", "news"])
    runner = AnalysisRunner(cfg, save_dir=tmp_path)
    runner._process_chunk({"messages": []})
    assert runner._agent_status["Market Analyst"] == "in_progress"
    assert runner._agent_status["News Analyst"] == "in_progress"
    runner._process_chunk({"market_report": "filed"})
    assert runner._agent_status["Market Analyst"] == "completed"
    assert runner._agent_status["News Analyst"] == "in_progress"


def test_portfolio_report_streams_without_legacy_judge_field(tmp_path):
    cfg = RunnerConfig(ticker="TEST", analysis_date="2025-01-02", analysts=["market"])
    runner = AnalysisRunner(cfg, save_dir=tmp_path)
    runner._process_chunk({"risk_debate_state": {"history": "debate"},
                           "final_trade_decision": "Rating: Sell"})
    assert "Rating: Sell" in runner._report_sections["final_trade_decision"]
    assert runner._agent_status["Portfolio Manager"] == "completed"
    assert runner._agent_status["Investor Briefing"] == "in_progress"


@pytest.mark.parametrize("cancel", [False, True])
def test_runner_closes_stream_and_checkpoint_and_records_only_success(tmp_path, cancel):
    import threading

    from tradingagents.runner import RunCancelled

    cancel_event = threading.Event()
    instances = []

    class LifecycleGraph(_StubGraph):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            instances.append(self)
            self.closed = False
            self.recorded = None
            self.cleared = False

        def stream_run(self, state, **args):
            assert args["config"]["configurable"]["thread_id"] == "test-thread"
            try:
                if cancel:
                    cancel_event.set()
                # Typed final_rating is authoritative, even when prose quotes Buy.
                yield [], {"final_trade_decision": "Rating: Buy", "final_rating": "Underweight"}
            finally:
                self.closed = True

    events = []
    cfg = RunnerConfig(ticker="TEST", analysis_date="2025-01-02", analysts=["market"])
    with patch.object(runner_mod, "TradingAgentsGraph", LifecycleGraph):
        runner = AnalysisRunner(cfg, on_event=events.append, save_dir=tmp_path, cancel_event=cancel_event)
        if cancel:
            with pytest.raises(RunCancelled):
                runner.run()
        else:
            runner.run()
    graph = instances[0]
    assert graph.closed and not graph.checkpoint_open
    assert graph.cleared is (not cancel)
    assert (graph.recorded is not None) is (not cancel)
    if not cancel:
        assert next(e for e in events if isinstance(e, DoneEvent)).decision == "Underweight"


def test_research_manager_plan_streams_without_legacy_judge_field(tmp_path):
    cfg = RunnerConfig(ticker="TEST", analysis_date="2025-01-02", analysts=["market"])
    runner = AnalysisRunner(cfg, save_dir=tmp_path)
    runner._process_chunk({"investment_debate_state": {"history": "debate"},
                           "investment_plan": "Rating: Overweight"})
    assert "Rating: Overweight" in runner._report_sections["investment_plan"]
    assert runner._agent_status["Research Manager"] == "completed"
    assert runner._agent_status["Trader"] == "in_progress"


def test_cumulative_states_do_not_restart_agents_or_replace_finished_reports(tmp_path):
    events = []
    cfg = RunnerConfig(ticker="TEST", analysis_date="2025-01-02", analysts=["market"])
    runner = AnalysisRunner(cfg, on_event=events.append, save_dir=tmp_path)
    state = {"messages": []}
    for chunk in [*_FAKE_CHUNKS,
                  {"investment_plan": "Rating: Overweight\nResearch decision"},
                  {"investor_briefing": "Plain-language summary"},
                  {}]:
        state.update(chunk)
        runner._process_chunk(state)
    last = {}
    for event in events:
        if isinstance(event, AgentStatusEvent):
            assert last.get(event.agent) != "completed", f"{event.agent} restarted"
            last[event.agent] = event.status
    assert runner._report_sections["final_trade_decision"] == state["final_trade_decision"]
    assert "Research decision" in runner._report_sections["investment_plan"]
