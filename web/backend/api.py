"""REST + WebSocket routes for the dashboard."""

from __future__ import annotations

import asyncio
import datetime
import json
import os
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Response, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, field_validator

from tradingagents.default_config import ANALYST_ORDER, VALID_ANALYSTS
from tradingagents.llm_clients.model_catalog import MODEL_OPTIONS

from .reports import (
    get_decision,
    get_report,
    list_reports,
)
from .runs import registry
from tradingagents.runner import RunnerConfig

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


_TICKER_RE = re.compile(r"^[A-Z0-9.\-]{1,15}$")
_VALID_PROVIDERS = set(MODEL_OPTIONS.keys()) | {"openrouter", "azure"}


class StartRunRequest(BaseModel):
    ticker: str
    analysis_date: str
    analysts: List[str] = Field(default_factory=lambda: list(ANALYST_ORDER))
    research_depth: int = 1
    llm_provider: str = "openai"
    backend_url: str = "https://api.openai.com/v1"
    shallow_thinker: str = "gpt-5.4-mini"
    deep_thinker: str = "gpt-5.5"
    output_language: str = "English"
    google_thinking_level: Optional[str] = None
    openai_reasoning_effort: Optional[str] = None
    anthropic_effort: Optional[str] = None

    @field_validator("ticker")
    @classmethod
    def _v_ticker(cls, v: str) -> str:
        v = v.strip().upper()
        if not _TICKER_RE.match(v):
            raise ValueError("Invalid ticker symbol")
        return v

    @field_validator("analysis_date")
    @classmethod
    def _v_date(cls, v: str) -> str:
        try:
            d = datetime.datetime.strptime(v.strip(), "%Y-%m-%d").date()
        except ValueError as exc:
            raise ValueError("analysis_date must be YYYY-MM-DD") from exc
        if d > datetime.date.today():
            raise ValueError("analysis_date cannot be in the future")
        return v.strip()

    @field_validator("analysts")
    @classmethod
    def _v_analysts(cls, v: List[str]) -> List[str]:
        v = [a.lower() for a in v]
        if not v:
            raise ValueError("Select at least one analyst")
        bad = [a for a in v if a not in VALID_ANALYSTS]
        if bad:
            raise ValueError(f"Unknown analysts: {bad}")
        return v

    @field_validator("research_depth")
    @classmethod
    def _v_depth(cls, v: int) -> int:
        if v not in (1, 3, 5):
            raise ValueError("research_depth must be 1, 3, or 5")
        return v

    @field_validator("llm_provider")
    @classmethod
    def _v_provider(cls, v: str) -> str:
        v = v.lower()
        if v not in _VALID_PROVIDERS:
            raise ValueError(f"Unsupported provider: {v}")
        return v


# ---------------------------------------------------------------------------
# Config / options
# ---------------------------------------------------------------------------


_PROVIDER_ENV_KEYS: Dict[str, List[str]] = {
    "openai": ["OPENAI_API_KEY"],
    "anthropic": ["ANTHROPIC_API_KEY"],
    "google": ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
    "xai": ["XAI_API_KEY"],
    "deepseek": ["DEEPSEEK_API_KEY"],
    "qwen": ["DASHSCOPE_API_KEY"],
    "glm": ["ZHIPUAI_API_KEY"],
    "openrouter": ["OPENROUTER_API_KEY"],
    "azure": ["AZURE_OPENAI_API_KEY"],
    "ollama": [],  # local, no key required
}


def _provider_key_status() -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for prov, keys in _PROVIDER_ENV_KEYS.items():
        if not keys:
            out[prov] = {"required": False, "set": True, "env_vars": []}
            continue
        present = any(os.getenv(k) for k in keys)
        out[prov] = {"required": True, "set": present, "env_vars": keys}
    return out


@router.get("/api/config/options")
def config_options() -> Dict[str, Any]:
    return {
        "analysts": [
            {"key": "market", "label": "Market Analyst"},
            {"key": "social", "label": "Social Media Analyst"},
            {"key": "news", "label": "News Analyst"},
            {"key": "fundamentals", "label": "Fundamentals Analyst"},
        ],
        "research_depths": [
            {"value": 1, "label": "Shallow (1 round)"},
            {"value": 3, "label": "Medium (3 rounds)"},
            {"value": 5, "label": "Deep (5 rounds)"},
        ],
        "providers": sorted(_VALID_PROVIDERS),
        "models": MODEL_OPTIONS,
        "api_key_status": _provider_key_status(),
        "languages": ["English", "Chinese", "Japanese", "Spanish", "French", "German"],
    }


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------


@router.post("/api/runs", status_code=202)
async def start_run(payload: StartRunRequest, response: Response) -> Dict[str, Any]:
    config = RunnerConfig(
        ticker=payload.ticker,
        analysis_date=payload.analysis_date,
        analysts=payload.analysts,
        research_depth=payload.research_depth,
        llm_provider=payload.llm_provider,
        backend_url=payload.backend_url,
        shallow_thinker=payload.shallow_thinker,
        deep_thinker=payload.deep_thinker,
        output_language=payload.output_language,
        google_thinking_level=payload.google_thinking_level,
        openai_reasoning_effort=payload.openai_reasoning_effort,
        anthropic_effort=payload.anthropic_effort,
    )
    record = await registry.submit(config)
    response.headers["Location"] = f"/api/runs/{record.run_id}"
    return record.to_summary()


@router.get("/api/runs")
def list_runs() -> Dict[str, Any]:
    return {"runs": registry.list_runs()}


@router.get("/api/runs/{run_id}")
def get_run(run_id: str) -> Dict[str, Any]:
    record = registry.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return {
        **record.to_summary(),
        "events": list(record.events),
    }


@router.delete("/api/runs/{run_id}")
def cancel_run(run_id: str) -> Dict[str, Any]:
    """Request cancellation of a queued or running analysis.

    Returns the *response* status, which is one of:

    * ``"cancelling"`` \u2014 cancel was accepted; the run is still winding down.
      Once it actually stops, ``RunRecord.status`` flips to ``"cancelled"``
      and a corresponding ``StatusEvent`` is emitted on the WebSocket.
    * ``"done" | "error" | "cancelled"`` \u2014 the run was already terminal;
      no signal was issued.

    The transient ``"cancelling"`` value is *never* persisted to the run
    record nor emitted on the event stream; it only describes this HTTP
    response.
    """
    new_status = registry.cancel(run_id)
    if new_status is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"run_id": run_id, "status": new_status}


@router.websocket("/api/runs/{run_id}/stream")
async def stream_run(websocket: WebSocket, run_id: str) -> None:
    await websocket.accept()
    sub = registry.subscribe(run_id)
    if sub is None:
        await websocket.send_json({"type": "error", "message": "Run not found"})
        await websocket.close()
        return

    buffered, queue = sub
    try:
        for event in buffered:
            await websocket.send_json(event)
        while True:
            event = await queue.get()
            if event is None:
                break
            await websocket.send_json(event)
    except WebSocketDisconnect:
        pass
    finally:
        registry.unsubscribe(run_id, queue)
        try:
            await websocket.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


@router.get("/api/reports")
def reports_index(include_incomplete: bool = Query(False)) -> Dict[str, Any]:
    return {"reports": list_reports(include_incomplete=include_incomplete)}


@router.get("/api/reports/{folder}")
def report_detail(folder: str) -> Dict[str, Any]:
    report = get_report(folder)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@router.get("/api/reports/{folder}/decision")
def report_decision(folder: str) -> Dict[str, Any]:
    """Return the structured PortfolioDecision JSON for a report.

    404s when the report has no ``decision.json`` (legacy runs predating the
    structured-output persistence change). Frontend should fall back to the
    rendered markdown in that case.
    """
    decision = get_decision(folder)
    if decision is None:
        raise HTTPException(status_code=404, detail="Structured decision not available")
    return decision
