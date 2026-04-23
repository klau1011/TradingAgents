"""Headless analysis runner.

Wraps :class:`TradingAgentsGraph` with a streaming, event-emitting interface
that's reusable across the CLI, the FastAPI web dashboard, and tests.

The runner:
- Streams the LangGraph chunks
- Tracks agent status transitions and tool calls
- Emits structured :mod:`tradingagents.runner_events` to a callback
- Persists the final report to disk under ``<results_dir>/<TICKER>_<TIMESTAMP>``
  with the same folder layout used by the CLI (``1_analysts``, ``2_research``,
  ``3_trading``, ``4_risk``, ``5_portfolio`` + ``complete_report.md``).

It is intentionally synchronous; callers that need async behavior should run
``AnalysisRunner.run`` in a thread executor (the FastAPI backend does this).
"""

from __future__ import annotations

import datetime
import threading
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


class RunCancelled(Exception):
    """Raised inside the runner when an external cancel is requested."""


from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.runner_events import (
    AgentStatusEvent,
    DoneEvent,
    ErrorEvent,
    MessageEvent,
    ReportSectionEvent,
    RunEvent,
    StatusEvent,
    ToolCallEvent,
)


# ---------------------------------------------------------------------------
# Constants mirroring cli/main.py so behavior matches the existing CLI exactly.
# ---------------------------------------------------------------------------

ANALYST_ORDER: List[str] = ["market", "social", "news", "fundamentals"]

ANALYST_AGENT_NAMES: Dict[str, str] = {
    "market": "Market Analyst",
    "social": "Social Analyst",
    "news": "News Analyst",
    "fundamentals": "Fundamentals Analyst",
}

ANALYST_REPORT_MAP: Dict[str, str] = {
    "market": "market_report",
    "social": "sentiment_report",
    "news": "news_report",
    "fundamentals": "fundamentals_report",
}

FIXED_AGENTS: Dict[str, List[str]] = {
    "Research Team": ["Bull Researcher", "Bear Researcher", "Research Manager"],
    "Trading Team": ["Trader"],
    "Risk Management": [
        "Aggressive Analyst",
        "Neutral Analyst",
        "Conservative Analyst",
    ],
    "Portfolio Management": ["Portfolio Manager"],
    "Investor Briefing": ["Investor Briefing"],
}

# section -> (analyst_key controlling the section, finalizing agent name)
REPORT_SECTIONS: Dict[str, tuple] = {
    "market_report": ("market", "Market Analyst"),
    "sentiment_report": ("social", "Social Analyst"),
    "news_report": ("news", "News Analyst"),
    "fundamentals_report": ("fundamentals", "Fundamentals Analyst"),
    "investment_plan": (None, "Research Manager"),
    "trader_investment_plan": (None, "Trader"),
    "final_trade_decision": (None, "Portfolio Manager"),
    "investor_briefing": (None, "Investor Briefing"),
}


EventCallback = Callable[[RunEvent], None]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class RunnerConfig:
    """User-facing configuration for a single analysis run.

    Mirrors the shape of the CLI ``selections`` dict but typed and explicit.
    """

    ticker: str
    analysis_date: str
    analysts: List[str]  # subset of ANALYST_ORDER
    research_depth: int = 1
    llm_provider: str = "openai"
    backend_url: str = "https://api.openai.com/v1"
    shallow_thinker: str = "gpt-5.4-mini"
    deep_thinker: str = "gpt-5.4"
    output_language: str = "English"
    google_thinking_level: Optional[str] = None
    openai_reasoning_effort: Optional[str] = None
    anthropic_effort: Optional[str] = None
    extra_config: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Normalize and validate user-provided config values early."""
        self.ticker = self.ticker.strip().upper()
        if not self.ticker:
            raise ValueError("ticker must be a non-empty string")

        normalized: List[str] = []
        for analyst in self.analysts:
            key = str(analyst).strip().lower()
            if key not in ANALYST_ORDER:
                valid = ", ".join(ANALYST_ORDER)
                raise ValueError(
                    f"Unknown analyst '{analyst}'. Valid analysts: {valid}"
                )
            if key not in normalized:
                normalized.append(key)

        if not normalized:
            raise ValueError("analysts must include at least one analyst")

        self.analysts = normalized

    def to_graph_config(self) -> Dict[str, Any]:
        """Build the dict consumed by ``TradingAgentsGraph``."""
        cfg = DEFAULT_CONFIG.copy()
        cfg["max_debate_rounds"] = self.research_depth
        cfg["max_risk_discuss_rounds"] = self.research_depth
        cfg["quick_think_llm"] = self.shallow_thinker
        cfg["deep_think_llm"] = self.deep_thinker
        cfg["backend_url"] = self.backend_url
        cfg["llm_provider"] = self.llm_provider.lower()
        cfg["google_thinking_level"] = self.google_thinking_level
        cfg["openai_reasoning_effort"] = self.openai_reasoning_effort
        cfg["anthropic_effort"] = self.anthropic_effort
        cfg["output_language"] = self.output_language
        cfg.update(self.extra_config)
        return cfg


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class AnalysisRunner:
    """Run a single analysis and emit events.

    Parameters
    ----------
    config:
        :class:`RunnerConfig` describing what to run.
    on_event:
        Callable invoked for every event. Must be cheap and non-blocking; the
        web layer pushes events into an asyncio queue from this callback.
    save_dir:
        Where to write the report folder. Defaults to ``<results_dir>``.
    callbacks:
        Optional LangChain-style callbacks (e.g. token-stat handler) forwarded
        to the underlying graph.
    """

    def __init__(
        self,
        config: RunnerConfig,
        on_event: Optional[EventCallback] = None,
        save_dir: Optional[Path] = None,
        callbacks: Optional[List[Any]] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> None:
        self.config = config
        self.on_event = on_event or (lambda _e: None)
        self.callbacks = callbacks or []
        # Cooperative cancellation: checked between graph chunks.
        self.cancel_event = cancel_event or threading.Event()

        graph_config = config.to_graph_config()
        self._graph_config = graph_config

        results_root = Path(save_dir) if save_dir else Path(graph_config["results_dir"])
        # Microsecond precision + short uuid suffix prevents collisions when
        # multiple concurrent runs target the same ticker in the same second.
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        suffix = uuid.uuid4().hex[:6]
        self.save_path: Path = results_root / f"{config.ticker}_{timestamp}_{suffix}"

        # Internal state mirroring cli MessageBuffer
        self._selected_analysts = [a.lower() for a in config.analysts]
        self._agent_status: Dict[str, str] = {}
        self._report_sections: Dict[str, Optional[str]] = {}
        self._processed_message_ids: set = set()

        for key in self._selected_analysts:
            if key in ANALYST_AGENT_NAMES:
                self._agent_status[ANALYST_AGENT_NAMES[key]] = "pending"
        for agents in FIXED_AGENTS.values():
            for agent in agents:
                self._agent_status[agent] = "pending"

        for section, (analyst_key, _) in REPORT_SECTIONS.items():
            if analyst_key is None or analyst_key in self._selected_analysts:
                self._report_sections[section] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> Dict[str, Any]:
        """Execute the analysis. Returns the final state dict."""
        try:
            self._emit(StatusEvent(status="running"))
            self._emit(
                MessageEvent(
                    message_type="System",
                    content=f"Selected ticker: {self.config.ticker}",
                )
            )
            self._emit(
                MessageEvent(
                    message_type="System",
                    content=f"Analysis date: {self.config.analysis_date}",
                )
            )
            self._emit(
                MessageEvent(
                    message_type="System",
                    content=f"Selected analysts: {', '.join(self._selected_analysts)}",
                )
            )

            graph = TradingAgentsGraph(
                self._selected_analysts,
                config=self._graph_config,
                debug=False,
                callbacks=self.callbacks,
            )

            # Mark first analyst in_progress immediately for snappy UI
            if self._selected_analysts:
                first = ANALYST_AGENT_NAMES[self._selected_analysts[0]]
                self._set_agent_status(first, "in_progress")

            init_state = graph.propagator.create_initial_state(
                self.config.ticker, self.config.analysis_date
            )
            args = graph.propagator.get_graph_args(callbacks=self.callbacks)

            final_state = self._stream(graph, init_state, args)

            # Mark every agent completed
            for agent in list(self._agent_status.keys()):
                self._set_agent_status(agent, "completed")

            # Flush any final report sections
            for section in self._report_sections:
                if section in final_state and final_state[section]:
                    self._set_report_section(section, final_state[section])

            decision = graph.process_signal(final_state["final_trade_decision"])

            report_path = save_report_to_disk(
                final_state, self.config.ticker, self.save_path
            )

            self._emit(
                DoneEvent(
                    decision=decision,
                    final_state_path=str(self.save_path),
                    report_path=str(report_path),
                )
            )
            self._emit(StatusEvent(status="done"))
            return final_state

        except RunCancelled:
            self._emit(
                MessageEvent(
                    message_type="System",
                    content="Run cancelled by user.",
                )
            )
            self._emit(StatusEvent(status="cancelled"))
            raise
        except Exception as exc:  # noqa: BLE001
            self._emit(
                ErrorEvent(message=f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}")
            )
            self._emit(StatusEvent(status="error"))
            raise

    # ------------------------------------------------------------------
    # Streaming loop
    # ------------------------------------------------------------------

    def _stream(self, graph, init_state, args) -> Dict[str, Any]:
        trace = []
        for chunk in graph.graph.stream(init_state, **args):
            if self.cancel_event.is_set():
                raise RunCancelled("Run cancelled by user")
            self._process_chunk(chunk)
            trace.append(chunk)
        if not trace:
            raise RuntimeError("Graph produced no output chunks")
        return trace[-1]

    def _process_chunk(self, chunk: Dict[str, Any]) -> None:
        # Messages + tool calls
        for message in chunk.get("messages", []):
            msg_id = getattr(message, "id", None)
            if msg_id is not None:
                if msg_id in self._processed_message_ids:
                    continue
                self._processed_message_ids.add(msg_id)

            msg_type, content = _classify_message(message)
            if content and content.strip():
                self._emit(MessageEvent(message_type=msg_type, content=content))

            if hasattr(message, "tool_calls") and message.tool_calls:
                for tc in message.tool_calls:
                    if isinstance(tc, dict):
                        name = tc.get("name", "<unknown>")
                        raw_args = tc.get("args")
                    else:
                        name = getattr(tc, "name", "<unknown>")
                        raw_args = getattr(tc, "args", None)
                    self._emit(
                        ToolCallEvent(tool_name=name, args=_coerce_tool_args(raw_args))
                    )

        self._update_analyst_statuses(chunk)

        # Research debate
        debate = chunk.get("investment_debate_state")
        if debate:
            bull = (debate.get("bull_history") or "").strip()
            bear = (debate.get("bear_history") or "").strip()
            judge = (debate.get("judge_decision") or "").strip()
            if bull or bear:
                self._set_research_team_status("in_progress")
            if bull:
                self._set_report_section(
                    "investment_plan", f"### Bull Researcher Analysis\n{bull}"
                )
            if bear:
                self._set_report_section(
                    "investment_plan", f"### Bear Researcher Analysis\n{bear}"
                )
            if judge:
                self._set_report_section(
                    "investment_plan", f"### Research Manager Decision\n{judge}"
                )
                self._set_research_team_status("completed")
                self._set_agent_status("Trader", "in_progress")

        # Trader
        if chunk.get("trader_investment_plan"):
            self._set_report_section(
                "trader_investment_plan", chunk["trader_investment_plan"]
            )
            if self._agent_status.get("Trader") != "completed":
                self._set_agent_status("Trader", "completed")
                self._set_agent_status("Aggressive Analyst", "in_progress")

        # Risk debate
        risk = chunk.get("risk_debate_state")
        if risk:
            agg = (risk.get("aggressive_history") or "").strip()
            con = (risk.get("conservative_history") or "").strip()
            neu = (risk.get("neutral_history") or "").strip()
            judge = (risk.get("judge_decision") or "").strip()
            if agg:
                if self._agent_status.get("Aggressive Analyst") != "completed":
                    self._set_agent_status("Aggressive Analyst", "in_progress")
                self._set_report_section(
                    "final_trade_decision", f"### Aggressive Analyst Analysis\n{agg}"
                )
            if con:
                if self._agent_status.get("Conservative Analyst") != "completed":
                    self._set_agent_status("Conservative Analyst", "in_progress")
                self._set_report_section(
                    "final_trade_decision", f"### Conservative Analyst Analysis\n{con}"
                )
            if neu:
                if self._agent_status.get("Neutral Analyst") != "completed":
                    self._set_agent_status("Neutral Analyst", "in_progress")
                self._set_report_section(
                    "final_trade_decision", f"### Neutral Analyst Analysis\n{neu}"
                )
            if judge:
                if self._agent_status.get("Portfolio Manager") != "completed":
                    self._set_agent_status("Portfolio Manager", "in_progress")
                    self._set_report_section(
                        "final_trade_decision", f"### Portfolio Manager Decision\n{judge}"
                    )
                    self._set_agent_status("Aggressive Analyst", "completed")
                    self._set_agent_status("Conservative Analyst", "completed")
                    self._set_agent_status("Neutral Analyst", "completed")
                    self._set_agent_status("Portfolio Manager", "completed")
                    self._set_agent_status("Investor Briefing", "in_progress")

        # Investor briefing (plain-language summary, runs last)
        if chunk.get("investor_briefing"):
            self._set_report_section("investor_briefing", chunk["investor_briefing"])
            self._set_agent_status("Investor Briefing", "completed")

    def _update_analyst_statuses(self, chunk: Dict[str, Any]) -> None:
        found_active = False
        for analyst_key in ANALYST_ORDER:
            if analyst_key not in self._selected_analysts:
                continue
            agent_name = ANALYST_AGENT_NAMES[analyst_key]
            report_key = ANALYST_REPORT_MAP[analyst_key]

            if chunk.get(report_key):
                self._set_report_section(report_key, chunk[report_key])

            has_report = bool(self._report_sections.get(report_key))
            if has_report:
                self._set_agent_status(agent_name, "completed")
            elif not found_active:
                self._set_agent_status(agent_name, "in_progress")
                found_active = True
            else:
                self._set_agent_status(agent_name, "pending")

        if not found_active and self._selected_analysts:
            if self._agent_status.get("Bull Researcher") == "pending":
                self._set_agent_status("Bull Researcher", "in_progress")

    # ------------------------------------------------------------------
    # State mutations + emission helpers (deduplicate to avoid noisy events)
    # ------------------------------------------------------------------

    def _emit(self, event: RunEvent) -> None:
        self.on_event(event)

    def _set_agent_status(self, agent: str, status: str) -> None:
        if agent not in self._agent_status:
            return
        if self._agent_status[agent] == status:
            return
        self._agent_status[agent] = status
        self._emit(AgentStatusEvent(agent=agent, status=status))  # type: ignore[arg-type]

    def _set_report_section(self, section: str, content: str) -> None:
        if section not in self._report_sections:
            return
        if self._report_sections[section] == content:
            return
        self._report_sections[section] = content
        self._emit(ReportSectionEvent(section=section, content=content))

    def _set_research_team_status(self, status: str) -> None:
        for agent in FIXED_AGENTS["Research Team"]:
            self._set_agent_status(agent, status)


# ---------------------------------------------------------------------------
# Helpers (extracted from cli/main.py)
# ---------------------------------------------------------------------------


def _extract_content_string(content) -> Optional[str]:
    """Extract a display string from a LangChain message ``content`` field."""
    import ast

    def is_empty(val) -> bool:
        if val is None or val == "":
            return True
        if isinstance(val, str):
            s = val.strip()
            if not s:
                return True
            try:
                return not bool(ast.literal_eval(s))
            except (ValueError, SyntaxError):
                return False
        return not bool(val)

    if is_empty(content):
        return None
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, dict):
        text = content.get("text", "")
        return text.strip() if not is_empty(text) else None
    if isinstance(content, list):
        parts = [
            item.get("text", "").strip()
            if isinstance(item, dict) and item.get("type") == "text"
            else (item.strip() if isinstance(item, str) else "")
            for item in content
        ]
        result = " ".join(p for p in parts if p and not is_empty(p))
        return result or None
    return str(content).strip() if not is_empty(content) else None


def _coerce_tool_args(raw: Any) -> Dict[str, Any]:
    """Best-effort normalize a tool-call ``args`` payload into a dict.

    Some providers emit ``args`` as ``None`` (zero-arg tools) or as already-
    serialized scalars. We never want a malformed payload to crash the run.
    """
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return dict(raw)
    except (TypeError, ValueError):
        return {"value": raw}


def _classify_message(message) -> tuple:
    """Return ``(message_type, content)`` for a LangChain message."""
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    content = _extract_content_string(getattr(message, "content", None))
    if isinstance(message, HumanMessage):
        if content and content.strip() == "Continue":
            return ("Control", content)
        return ("User", content)
    if isinstance(message, ToolMessage):
        return ("Data", content)
    if isinstance(message, AIMessage):
        return ("Agent", content)
    return ("System", content)


def save_report_to_disk(final_state: Dict[str, Any], ticker: str, save_path: Path) -> Path:
    """Persist the final report to disk using the CLI's folder layout.

    Returns the path to the consolidated ``complete_report.md``.
    """
    save_path.mkdir(parents=True, exist_ok=True)
    sections: List[str] = []

    # 0. Investor briefing (plain-language summary, shown first)
    briefing = final_state.get("investor_briefing")
    if briefing:
        summary_dir = save_path / "0_summary"
        summary_dir.mkdir(exist_ok=True)
        (summary_dir / "briefing.md").write_text(briefing, encoding="utf-8")
        sections.append(f"## 0. Investor Briefing\n\n{briefing}")

    # 1. Analysts
    analysts_dir = save_path / "1_analysts"
    analyst_parts = []
    if final_state.get("market_report"):
        analysts_dir.mkdir(exist_ok=True)
        (analysts_dir / "market.md").write_text(
            final_state["market_report"], encoding="utf-8"
        )
        analyst_parts.append(("Market Analyst", final_state["market_report"]))
    if final_state.get("sentiment_report"):
        analysts_dir.mkdir(exist_ok=True)
        (analysts_dir / "sentiment.md").write_text(
            final_state["sentiment_report"], encoding="utf-8"
        )
        analyst_parts.append(("Social Analyst", final_state["sentiment_report"]))
    if final_state.get("news_report"):
        analysts_dir.mkdir(exist_ok=True)
        (analysts_dir / "news.md").write_text(
            final_state["news_report"], encoding="utf-8"
        )
        analyst_parts.append(("News Analyst", final_state["news_report"]))
    if final_state.get("fundamentals_report"):
        analysts_dir.mkdir(exist_ok=True)
        (analysts_dir / "fundamentals.md").write_text(
            final_state["fundamentals_report"], encoding="utf-8"
        )
        analyst_parts.append(
            ("Fundamentals Analyst", final_state["fundamentals_report"])
        )
    if analyst_parts:
        body = "\n\n".join(f"### {name}\n{text}" for name, text in analyst_parts)
        sections.append(f"## I. Analyst Team Reports\n\n{body}")

    # 2. Research debate
    debate = final_state.get("investment_debate_state") or {}
    if debate:
        research_dir = save_path / "2_research"
        research_parts = []
        if debate.get("bull_history"):
            research_dir.mkdir(exist_ok=True)
            (research_dir / "bull.md").write_text(
                debate["bull_history"], encoding="utf-8"
            )
            research_parts.append(("Bull Researcher", debate["bull_history"]))
        if debate.get("bear_history"):
            research_dir.mkdir(exist_ok=True)
            (research_dir / "bear.md").write_text(
                debate["bear_history"], encoding="utf-8"
            )
            research_parts.append(("Bear Researcher", debate["bear_history"]))
        if debate.get("judge_decision"):
            research_dir.mkdir(exist_ok=True)
            (research_dir / "manager.md").write_text(
                debate["judge_decision"], encoding="utf-8"
            )
            research_parts.append(("Research Manager", debate["judge_decision"]))
        if research_parts:
            body = "\n\n".join(f"### {n}\n{t}" for n, t in research_parts)
            sections.append(f"## II. Research Team Decision\n\n{body}")

    # 3. Trader
    if final_state.get("trader_investment_plan"):
        trading_dir = save_path / "3_trading"
        trading_dir.mkdir(exist_ok=True)
        (trading_dir / "trader.md").write_text(
            final_state["trader_investment_plan"], encoding="utf-8"
        )
        sections.append(
            "## III. Trading Team Plan\n\n### Trader\n"
            + final_state["trader_investment_plan"]
        )

    # 4. Risk
    risk = final_state.get("risk_debate_state") or {}
    if risk:
        risk_dir = save_path / "4_risk"
        risk_parts = []
        for key, label, fname in (
            ("aggressive_history", "Aggressive Analyst", "aggressive.md"),
            ("conservative_history", "Conservative Analyst", "conservative.md"),
            ("neutral_history", "Neutral Analyst", "neutral.md"),
        ):
            if risk.get(key):
                risk_dir.mkdir(exist_ok=True)
                (risk_dir / fname).write_text(risk[key], encoding="utf-8")
                risk_parts.append((label, risk[key]))
        if risk_parts:
            body = "\n\n".join(f"### {n}\n{t}" for n, t in risk_parts)
            sections.append(f"## IV. Risk Management Team Decision\n\n{body}")

        # 5. Portfolio
        if risk.get("judge_decision"):
            portfolio_dir = save_path / "5_portfolio"
            portfolio_dir.mkdir(exist_ok=True)
            (portfolio_dir / "decision.md").write_text(
                risk["judge_decision"], encoding="utf-8"
            )
            sections.append(
                "## V. Portfolio Manager Decision\n\n### Portfolio Manager\n"
                + risk["judge_decision"]
            )

    header = (
        f"# Trading Analysis Report: {ticker}\n\n"
        f"Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    )
    out = save_path / "complete_report.md"
    out.write_text(header + "\n\n".join(sections), encoding="utf-8")
    return out
