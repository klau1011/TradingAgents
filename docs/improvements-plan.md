# Improvements plan — analysis & web UI

Status of the six-part improvement plan (2026-07). CLI is explicitly out of
scope: keep it working, invest nothing in it. Guiding constraint throughout:
shortest working diff, reuse existing utilities, no new dependencies.

**Done:**

- **PR 1 — Eval integrity** (`03f30bb`): fundamentals look-ahead closed
  (`disable_lookahead_tools` guards on `get_fundamentals`,
  `get_analyst_recommendations`, `get_insider_transactions`); `summarize()`
  gained `cost=`/`seed=`, null baselines (buy-and-hold, always-Buy, seeded
  random ±1), per-confidence slices, and `confidence_weighted_alpha`
  (0.5/1.0/1.5 weights); `direction()` now lives in
  `tradingagents/agents/utils/rating.py`.
- **PR 2 — Web robustness** (`dabc5d4`): terminal run summaries persisted to
  `<results_dir>/web_runs/`, API-key preflight (400), sanitized `ErrorEvent`,
  opaque `report_folder` references + "View report" link, History staleness
  fixes, rehydrated-run handling in `useRunStream`.

**Remaining: PRs 3–6 below.** Each is a self-contained change; suggested
order preserved. Per-PR verification: `pytest -m "unit or smoke"` (conftest
stubs API keys), plus `npm run build` in `web/frontend` when frontend files
change.

---

## PR 3 — Cost & progress in the web UI

Surface token usage (already tracked for the CLI) in the web dashboard.

1. Move `cli/stats_handler.py` → `tradingagents/stats_handler.py` unchanged;
   update the single importer (`cli/main.py`).
2. `tradingagents/runner_events.py`: add `StatsEvent` dataclass
   (`llm_calls`, `tool_calls`, `tokens_in`, `tokens_out`, `type="stats"`) to
   the `RunEvent` union.
3. `tradingagents/runner.py`: in `__init__`, always create a
   `StatsCallbackHandler` and append it to `self.callbacks` (these are
   already forwarded to the LLMs via `TradingAgentsGraph(callbacks=...)`, so
   `web/backend/runs.py` needs zero changes). In `_stream`, after each
   `_process_chunk`, emit a `StatsEvent` when the counters changed since the
   last emit; emit a final one before `DoneEvent`.
4. Frontend: add `StatsEvent` to `types.ts`; add a `stats` field to the
   `useRunStream` reducer; render a one-line stats strip (LLM calls / tool
   calls / tokens in-out) in the `Run.tsx` hero.
5. ETA (optional, only if trivial): emit an initial pending
   `AgentStatusEvent` for the full roster at run start so the frontend knows
   the total agent count, then show `avg(completed durations) × remaining` in
   `AgentTimeline.tsx`. Skip if pending rows don't render cleanly — elapsed
   time already exists.

Not doing: dollar cost (needs a per-model price table to maintain), per-agent
token attribution, CLI footer changes.

Verify: `event_to_dict(StatsEvent)` round-trip + stub-graph stats-emission
test in `tests/test_runner_events.py` (`_StubGraph` pattern);
`python -c "import cli.main"` smoke.

## PR 4 — Model routing + adaptive risk debate

Two opt-in config knobs, both defaulting to today's exact behavior.

**Per-stage model assignment**

1. `tradingagents/default_config.py`: add `"agent_llm_map": {}`. Stages:
   `analysts`, `researchers`, `research_manager`, `trader`, `risk_analysts`,
   `portfolio_manager`, `investor_briefing`; values `"quick"` / `"deep"`.
   Empty dict = current behavior (analysts + trader on quick, managers on
   deep). No env override (the `_coerce` machinery doesn't do dicts).
2. `tradingagents/graph/setup.py`: `GraphSetup.__init__` gains
   `llm_map: dict | None = None` plus a `_llm(stage, default)` helper
   (raise `ValueError` on unknown stage/value); replace the hardcoded
   quick/deep picks (~lines 61–78).
3. `tradingagents/graph/trading_graph.py` (~line 116): pass
   `self.config.get("agent_llm_map")`.

No UI exposure; reachable via config / `RunnerConfig.extra_config`.

**Adaptive risk debate**

Cheap deterministic disagreement signal, verified present in state: by the
time `should_continue_risk_analysis` runs, `state["investment_plan"]`
(Research Manager) and `state["trader_investment_plan"]` (Trader) both carry
parseable ratings (`parse_rating` in `agents/utils/rating.py`; `direction()`
landed in PR 1).

1. `tradingagents/graph/conditional_logic.py`: `__init__` gains
   `adaptive_extra_rounds=0`. In `should_continue_risk_analysis`, past the
   base cap but under `3 * (max_risk_discuss_rounds + adaptive_extra_rounds)`,
   continue only if
   `direction(parse_rating(investment_plan)) != direction(parse_rating(trader_investment_plan))`.
2. `default_config.py`: `"adaptive_extra_rounds": 0`;
   `trading_graph.py` (~lines 112–115) passes it through.

Not doing: adaptive bull/bear debate (they disagree by construction),
LLM-judged disagreement scoring.

Verify: pure-state `ConditionalLogic` unit tests (no LLM): agreement → stop
at base cap; disagreement → exactly N extra cycles then stop; default 0 →
identical to today.

## PR 5 — Memory & reflection

**Relevance-based retrieval.** `tradingagents/agents/utils/memory.py`
`get_past_context` (~line 70): same-ticker selection stays recency (recent
context on the same name is genuinely most relevant); cross-ticker selection
changes from "last 3" to "top 3 by |alpha|" (biggest realized wins/losses
carry the most instructive reflections), tie-break recency. Needs a small
`_parse_pct("+3.2%") -> float | None` helper since entries store alpha as a
formatted string (written in `update_with_outcome`, ~line 122). This is a
magnitude heuristic; the upgrade path is tag/embedding matching. Not doing:
embeddings, LLM relevance scoring, regime tags (on-disk format change).

**Wider injection.** Copy the guarded block pattern from
`agents/managers/portfolio_manager.py:35-40` ("Past lessons" section,
rendered only when `past_context` is non-empty) into:
`researchers/bull_researcher.py`, `researchers/bear_researcher.py`,
`trader/trader.py`, `risk_mgmt/aggressive_debator.py`,
`risk_mgmt/conservative_debator.py`, `risk_mgmt/neutral_debator.py`.
`past_context` is already in graph state (`graph/propagation.py:40`); all six
nodes already receive `state`. Accepted token cost: the string is bounded by
`n_same`/`n_cross` and the 300-char cross-ticker truncation.

Verify: `tests/test_memory_log.py` — |alpha| cross-ticker ordering and
`_parse_pct`; per-agent prompt-capture tests with a fake `llm.invoke`
(researchers/debators call `llm.invoke(prompt)` directly; trader via the
fake-structured-LLM pattern in `tests/test_structured_agents.py`). Assert
the block is present iff `past_context` is set. Measure the behavior change
with the PR 1 harness before/after.

## PR 6 — Sizing outputs

Make the Portfolio Manager's sizing real instead of dead prose fields.

1. `tradingagents/agents/schemas.py` `PortfolioDecision`: add
   `stop_loss: float | None` and `position_size_pct: float | None`
   (`ge=0, le=100`). Extend the existing `_coerce_optional_float`
   `field_validator` list (~line 233). Add a `model_validator(mode="after")`
   that **nulls** `stop_loss` when inconsistent with the rating direction vs
   `price_target` (long: stop < target; short: inverse) — fail-open like
   `_NULLISH_FLOAT`, never fail the structured call.
2. `render_pm_decision`: append `**Stop Loss**` / `**Position Size**` lines
   when set (same conditional pattern as `price_target`).
3. Persistence is free: `pm_decision` is `model_dump()`-ed and written to
   `decision.json`. Pass-throughs:
   - `web/backend/reports.py` `_load_validated_decision_json`: validate the
     two new optional numeric fields (copy the `price_target` handling,
     ~lines 141–151);
   - `web/frontend/src/types.ts` `PortfolioDecisionDetail`: add both fields;
   - `tradingagents/backtest.py` `_run_point_llm`: record
     `pm.get("stop_loss")` / `pm.get("position_size_pct")` in the row dict
     (forward-compatible; the weighting metric already landed in PR 1 as
     `confidence_weighted_alpha`).

Not doing: portfolio simulator, stop-loss simulation in the backtest (needs
forward price paths), touching `TraderProposal`'s optional string fields.

Verify: schema tests (coercion, bounds, consistency-nulling, render
round-trip) in `tests/test_structured_agents.py`; a `reports.py`
pass-through test in `tests/test_reports_module.py`.

---

## Known residual caveats (documented, deliberately unfixed)

- ETF profile tools still read "now" in eval mode (noted in the backtest
  report caveat); guard them like the PR 1 tools if ETF backtests become a
  real use case.
- Web run persistence is JSON-per-run with no locking (single-process
  server); move to sqlite if multi-worker ever happens.
