# TradingAgents — Extended Fork

> Multi-agent LLM trading framework. Extended fork of
> [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents),
> adding a web dashboard, a look-ahead-safe backtest harness, per-stage model
> routing, ETF support, and more.

The base framework runs a firm-like pipeline of LLM agents — fundamentals,
sentiment, news, and technical analysts feed bull/bear researchers, a trader,
a risk-debate team, and a portfolio manager — to produce a trading decision.
This fork keeps all of that and builds new surfaces on top of it.

> ⚠️ Research use only. This is not financial, investment, or trading advice.
> See the [upstream disclaimer](https://tauric.ai/disclaimer/).

---

## What this fork adds

Everything below is new in this fork (i.e. on top of upstream). The broad
multi-provider LLM support and Claude Sonnet 5 / Fable 5 are **upstream**
features, not fork additions.

- **Web dashboard** (`web/`) — FastAPI + React/Vite/TypeScript/Tailwind. Launch
  analyses from the browser, watch live progress over WebSocket, view an agent
  timeline/Gantt, cancel and resume runs, browse run history and past reports,
  read investor summaries, with API-key preflight and sanitized errors.
- **Backtest / evaluation harness** (`tradingagents/backtest.py`) —
  look-ahead-safe, resumable JSONL output, null baselines (buy-and-hold,
  always-Buy, seeded random), a cost model, and a confidence-weighted alpha
  metric.
- **Per-stage model routing** (`agent_llm_map`) — assign quick vs deep models
  per agent stage — plus **adaptive risk-debate rounds** (`adaptive_extra_rounds`)
  that extend the debate only while the Research Manager and Trader disagree.
- **Memory / reflection upgrades** — cross-ticker lessons selected top-3 by
  `|alpha|`, with wider past-lessons injection into researchers, the trader,
  and the risk debators.
- **ETF analysis support** — dedicated ETF data tools and flows.
- **Run-scoped OHLCV cache** — price/volume fetched once per run and reused.
- **Extra volume indicators** — relative volume (rvol), volume z-score, and
  volume trend slope, with vendor fallback.
- **Prediction-market tools** — event-probability signals for the analysts.
- **Headless runner + typed event protocol** (`tradingagents/runner.py`,
  `runner_events.py`) — the shared substrate the CLI and dashboard both sit on.
- **Investor briefings + structured position sizing** — a dedicated briefing
  agent, plus stop-loss / position-size fields on the portfolio decision.
- **GPT-5.6 models** in the catalog — Sol (deep), Luna (cost-sensitive),
  Terra (balanced).

---

## Running the new surfaces

### Web dashboard

```bash
pip install -e ".[web]"
tradingagents-web            # serves the app; open the printed URL
```

For dev mode (Vite dev server + `uvicorn --reload`) and the full architecture,
see [`web/README.md`](web/README.md).

### Backtest / evaluation harness

The harness is a Python API (not a CLI). It appends one JSONL row per evaluated
`(ticker, date)` and skips already-resolved points, so a killed run resumes for
free.

```python
from tradingagents.backtest import run_backtest

rows = run_backtest(
    tickers=["NVDA", "AAPL"],
    start="2026-01-01",
    end="2026-06-01",
    cadence_days=21,        # how often to sample an entry
    holding_days=5,         # forward window per entry
    results_path="backtest.jsonl",
    config=None,            # or a DEFAULT_CONFIG.copy()
)
```

See `tradingagents/backtest.py` for `summarize()`, baselines, and the cost model.

### Per-stage model routing & adaptive risk debate

```python
from tradingagents.default_config import DEFAULT_CONFIG

config = DEFAULT_CONFIG.copy()
config["agent_llm_map"] = {
    # keys: analysts, researchers, research_manager, trader,
    #       risk_analysts, portfolio_manager, investor_briefing
    # values: "quick" | "deep"   (empty map = current defaults)
    "analysts": "quick",
    "research_manager": "deep",
    "portfolio_manager": "deep",
}
config["adaptive_extra_rounds"] = 2   # 0 = today's fixed cap
```

---

## Base install & usage

For the full base install, provider API keys, Docker, and the interactive CLI,
see the
[upstream README](https://github.com/TauricResearch/TradingAgents#installation-and-cli).
Minimal quickstart so this repo runs standalone:

```bash
git clone https://github.com/klau1011/TradingAgents.git
cd TradingAgents
pip install .
export OPENAI_API_KEY=...   # or any supported provider's key
tradingagents               # interactive CLI
```

Programmatic use is unchanged from upstream:

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

ta = TradingAgentsGraph(debug=True, config=DEFAULT_CONFIG.copy())
_, decision = ta.propagate("NVDA", "2026-01-15")
print(decision)
```

---

## Fork changelog

Notable fork commits on top of upstream (`git log upstream/main..HEAD`):

- Web dashboard: backend/frontend, cancellable + resumable streams, agent
  Gantt, run persistence, key preflight, report links, investor summaries.
- Backtest / evaluation harness with look-ahead fixes, baselines, and cost.
- Model routing + adaptive risk debate; memory relevance + wider lessons.
- ETF analysis support; run-scoped OHLCV cache; volume indicators.
- GPT-5.6 model support.

---

## Attribution & citation

Forked from [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents).
All credit for the base multi-agent framework goes to the original authors.
Please cite their work:

```
@misc{xiao2025tradingagentsmultiagentsllmfinancial,
      title={TradingAgents: Multi-Agents LLM Financial Trading Framework}, 
      author={Yijia Xiao and Edward Sun and Di Luo and Wei Wang},
      year={2025},
      eprint={2412.20138},
      archivePrefix={arXiv},
      primaryClass={q-fin.TR},
      url={https://arxiv.org/abs/2412.20138}, 
}
```
