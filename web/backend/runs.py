"""In-process run registry with concurrency-limited execution.

Three runs may execute concurrently; additional submissions are queued.
Each run owns a bounded event buffer (so late WebSocket subscribers can replay
recent state) plus a fan-out broadcaster that pushes new events to every live
subscriber's asyncio queue.
"""

from __future__ import annotations

import asyncio
import datetime
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional

from tradingagents.runner import AnalysisRunner, RunnerConfig
from tradingagents.runner_events import (
    RunEvent,
    StatusEvent,
    event_to_dict,
)

MAX_CONCURRENT_RUNS = 3
MAX_RECENT_RUNS = 50
EVENT_BUFFER_SIZE = 500
SUBSCRIBER_QUEUE_SIZE = 1000


@dataclass
class RunRecord:
    run_id: str
    config: RunnerConfig
    status: str = "queued"  # queued | running | done | error
    queue_position: Optional[int] = None
    created_at: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    decision: Optional[str] = None
    report_path: Optional[str] = None
    error: Optional[str] = None

    # Internal: bounded event log + live subscribers
    events: Deque[Dict[str, Any]] = field(default_factory=lambda: deque(maxlen=EVENT_BUFFER_SIZE))
    subscribers: List[asyncio.Queue] = field(default_factory=list)

    def to_summary(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "ticker": self.config.ticker,
            "analysis_date": self.config.analysis_date,
            "status": self.status,
            "queue_position": self.queue_position,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "decision": self.decision,
            "report_path": self.report_path,
            "error": self.error,
        }


class RunRegistry:
    """Manages the lifecycle of analysis runs."""

    def __init__(self, max_concurrent: int = MAX_CONCURRENT_RUNS) -> None:
        self._max_concurrent = max_concurrent
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._runs: Dict[str, RunRecord] = {}
        self._order: Deque[str] = deque(maxlen=MAX_RECENT_RUNS)
        self._lock = asyncio.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def _ensure_semaphore(self) -> asyncio.Semaphore:
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._max_concurrent)
        return self._semaphore

    # ------------------------------------------------------------------
    # Submission
    # ------------------------------------------------------------------

    async def submit(self, config: RunnerConfig) -> RunRecord:
        run_id = uuid.uuid4().hex[:12]
        record = RunRecord(run_id=run_id, config=config)
        async with self._lock:
            self._runs[run_id] = record
            self._order.append(run_id)
            self._evict_overflow()
            record.queue_position = self._compute_queue_position(record)

        self._loop = asyncio.get_running_loop()

        # Emit initial queued event
        self._record_event(
            record,
            StatusEvent(status="queued", queue_position=record.queue_position),
        )

        asyncio.create_task(self._execute(record))
        return record

    def _compute_queue_position(self, record: RunRecord) -> Optional[int]:
        queued_before = [
            r for r in self._runs.values()
            if r.status == "queued" and r.created_at < record.created_at
        ]
        return len(queued_before)

    def _evict_overflow(self) -> None:
        # Drop terminal runs that fall outside the recent window
        live_ids = {rid for rid in self._order}
        for rid in list(self._runs.keys()):
            if rid not in live_ids and self._runs[rid].status in {"done", "error"}:
                self._runs.pop(rid, None)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def _execute(self, record: RunRecord) -> None:
        sem = self._ensure_semaphore()
        async with sem:
            record.status = "running"
            record.queue_position = None
            record.started_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
            await self._refresh_queue_positions()

            loop = asyncio.get_running_loop()

            def on_event(event: RunEvent) -> None:
                # Called from worker thread; hop back to event loop.
                loop.call_soon_threadsafe(self._record_event, record, event)

            runner = AnalysisRunner(
                config=record.config,
                on_event=on_event,
            )

            try:
                await loop.run_in_executor(None, runner.run)
                record.status = "done"
                record.report_path = str(runner.save_path / "complete_report.md")
                # Pull decision from the latest done event if present
                for ev in reversed(record.events):
                    if ev.get("type") == "done":
                        record.decision = ev.get("decision")
                        break
            except Exception as exc:  # noqa: BLE001
                record.status = "error"
                record.error = f"{type(exc).__name__}: {exc}"
            finally:
                record.finished_at = datetime.datetime.now(
                    datetime.timezone.utc
                ).isoformat()
                # Close all subscriber queues so WS endpoints exit gracefully
                for q in list(record.subscribers):
                    self._close_subscriber(record, q)

    async def _refresh_queue_positions(self) -> None:
        async with self._lock:
            queued = sorted(
                [r for r in self._runs.values() if r.status == "queued"],
                key=lambda r: r.created_at,
            )
            for idx, r in enumerate(queued):
                if r.queue_position != idx:
                    r.queue_position = idx
                    self._record_event(
                        r, StatusEvent(status="queued", queue_position=idx)
                    )

    # ------------------------------------------------------------------
    # Event fan-out
    # ------------------------------------------------------------------

    def _record_event(self, record: RunRecord, event: RunEvent) -> None:
        payload = event_to_dict(event)
        record.events.append(payload)
        for q in list(record.subscribers):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                # Subscriber too slow; close and drop the connection.
                self._close_subscriber(record, q)

    def _close_subscriber(self, record: RunRecord, q: asyncio.Queue) -> None:
        if q in record.subscribers:
            record.subscribers.remove(q)
        self._enqueue_close_signal(q)

    @staticmethod
    def _enqueue_close_signal(q: asyncio.Queue) -> None:
        try:
            q.put_nowait(None)
            return
        except asyncio.QueueFull:
            # Make room for a terminal sentinel if possible.
            try:
                q.get_nowait()
                q.put_nowait(None)
            except Exception:
                pass
        except Exception:
            pass

    def subscribe(self, run_id: str) -> Optional[tuple]:
        """Return ``(buffered_events, queue)`` for a run, or ``None``."""
        record = self._runs.get(run_id)
        if record is None:
            return None
        q: asyncio.Queue = asyncio.Queue(maxsize=SUBSCRIBER_QUEUE_SIZE)
        record.subscribers.append(q)
        return list(record.events), q

    def unsubscribe(self, run_id: str, q: asyncio.Queue) -> None:
        record = self._runs.get(run_id)
        if record and q in record.subscribers:
            record.subscribers.remove(q)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get(self, run_id: str) -> Optional[RunRecord]:
        return self._runs.get(run_id)

    def list_runs(self) -> List[Dict[str, Any]]:
        return [self._runs[rid].to_summary() for rid in self._order if rid in self._runs]


registry = RunRegistry()
