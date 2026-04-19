# TradingAgents Web Dashboard

Local web UI to launch analyses, watch live progress, and browse past reports.

## Stack
- **Backend**: FastAPI + asyncio (in-process, max 3 concurrent runs, extras queued)
- **Frontend**: React + Vite + TypeScript + Tailwind, design-locked to [DESIGN.md](../DESIGN.md)
- **Transport**: REST for control, WebSocket for live progress

## Architecture
```
web/
  backend/
    app.py        FastAPI app + static SPA fallback
    api.py        REST + WebSocket routes
    runs.py       RunRegistry (asyncio.Semaphore(3)) + event broadcaster
    reports.py    Past-report discovery (scans repo reports/ + results_dir)
  frontend/
    src/
      components/ui/   Button / Card / StatusBadge — design tokens
      hooks/           useRunStream WS reducer
      routes/          NewRun · Run · History · Report
```
The runner itself lives at [`tradingagents/runner.py`](../tradingagents/runner.py); both
the CLI and the dashboard sit on top of that and the typed event schema in
[`tradingagents/runner_events.py`](../tradingagents/runner_events.py).

## Local development

### 1. Install Python deps
```powershell
pip install -e ".[web]"
```

### 2. Start the backend
```powershell
uvicorn web.backend.app:app --reload --port 8000
```

### 3. Start the Vite dev server
```powershell
cd web/frontend
npm install
npm run dev
```
Open http://localhost:5173.

The Vite proxy forwards `/api/*` (REST + WebSocket) to `http://127.0.0.1:8000`.

## Production / single-process

```powershell
cd web/frontend
npm run build
cd ../..
python -m web.backend.app
```
Open http://127.0.0.1:8000. The FastAPI app serves the built SPA from
`web/frontend/dist`.

## Concurrency
- Up to **3 runs execute concurrently**. Additional submissions enter `queued`
  and surface their queue position in both REST (`/api/runs/{id}`) and the
  WebSocket stream (`status: queued, queue_position: N`).
- The semaphore lives in `RunRegistry` (process-local). Restarting the backend
  drops in-flight runs.

## Reports
- Past reports are read from **both** the repo's `reports/` directory and the
  user-configured `results_dir` (defaults to `~/.tradingagents/logs`).
- New runs write to `results_dir`.

## API keys
- The `/api/config/options` endpoint returns a per-provider `api_key_status`
  block listing which environment variables it inspected and whether one is set.
- Keys are **read-only from the dashboard**. Set them in your `.env`.
