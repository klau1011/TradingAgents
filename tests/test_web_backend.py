"""Smoke tests for the FastAPI dashboard backend."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture()
def client():
    from web.backend.app import app

    return TestClient(app)


def test_health(client) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_config_options(client) -> None:
    r = client.get("/api/config/options")
    assert r.status_code == 200
    body = r.json()
    assert "analysts" in body and len(body["analysts"]) == 4
    assert "models" in body and "openai" in body["models"]
    assert "api_key_status" in body
    assert "openai" in body["api_key_status"]


def test_reports_index_runs(client) -> None:
    r = client.get("/api/reports")
    assert r.status_code == 200
    assert "reports" in r.json()


def test_start_run_validates_ticker(client) -> None:
    r = client.post(
        "/api/runs",
        json={"ticker": "bad ticker!!", "analysis_date": "2025-01-02"},
    )
    assert r.status_code == 422


def test_start_run_rejects_future_date(client) -> None:
    r = client.post(
        "/api/runs",
        json={"ticker": "SPY", "analysis_date": "2099-01-02"},
    )
    assert r.status_code == 422


def test_get_unknown_run_404(client) -> None:
    r = client.get("/api/runs/nope")
    assert r.status_code == 404


def test_cancel_unknown_run_404(client) -> None:
    r = client.delete("/api/runs/nope")
    assert r.status_code == 404


def test_cancel_queued_run(client, monkeypatch) -> None:
    """A queued run should accept cancellation and short-circuit before the
    runner ever starts. We patch ``AnalysisRunner.run`` so no real LLM work
    occurs even if the executor wins the race."""
    from web.backend import runs as runs_mod

    monkeypatch.setattr(
        runs_mod.AnalysisRunner,
        "run",
        lambda self: {"final_trade_decision": "HOLD"},
    )

    start = client.post(
        "/api/runs",
        json={"ticker": "SPY", "analysis_date": "2025-01-02"},
    )
    assert start.status_code == 202
    run_id = start.json()["run_id"]

    cancel = client.delete(f"/api/runs/{run_id}")
    assert cancel.status_code == 200
    body = cancel.json()
    assert body["run_id"] == run_id
    assert body["status"] in {"cancelling", "cancelled", "done"}


def test_cancel_running_run_emits_cancelled_status(monkeypatch) -> None:
    """A running run should observe the cancel flag mid-execution and
    transition to the terminal ``cancelled`` status with a corresponding
    StatusEvent recorded on the buffer.

    Uses ``TestClient`` as a context manager so the lifespan is fully
    started \u2014 background asyncio tasks scheduled by route handlers need a
    running event loop to actually progress between requests.
    """
    import time

    from web.backend.app import app
    from web.backend import runs as runs_mod
    from tradingagents.runner import RunCancelled

    def fake_run(self):
        # Long enough that we definitely cancel mid-flight, while polling the
        # cancel flag the same way the real chunk loop does in
        # tradingagents/runner.py::_stream.
        for _ in range(200):
            if self.cancel_event.is_set():
                raise RunCancelled("Run cancelled by user")
            time.sleep(0.05)
        return {"final_trade_decision": "BUY"}

    monkeypatch.setattr(runs_mod.AnalysisRunner, "run", fake_run)

    with TestClient(app) as client:
        start = client.post(
            "/api/runs",
            json={"ticker": "SPY", "analysis_date": "2025-01-02"},
        )
        assert start.status_code == 202
        run_id = start.json()["run_id"]

        # Wait for the executor to leave the queued state so we exercise the
        # running-cancel path (not the queued short-circuit).
        deadline = time.time() + 5.0
        while time.time() < deadline:
            if client.get(f"/api/runs/{run_id}").json()["status"] == "running":
                break
            time.sleep(0.05)
        assert client.get(f"/api/runs/{run_id}").json()["status"] == "running"

        cancel = client.delete(f"/api/runs/{run_id}")
        assert cancel.status_code == 200
        assert cancel.json()["status"] == "cancelling"

        # Poll until the executor winds down. Sleep between polls so the event
        # loop running ``_execute``'s finally block gets CPU time.
        deadline = time.time() + 5.0
        final_status = None
        while time.time() < deadline:
            final_status = client.get(f"/api/runs/{run_id}").json()["status"]
            if final_status in {"cancelled", "done", "error"}:
                break
            time.sleep(0.1)

        assert final_status == "cancelled", (
            f"expected cancelled, got {final_status}"
        )

        # Recorded event buffer must end on a cancelled StatusEvent and
        # never contain a done event.
        detail = client.get(f"/api/runs/{run_id}").json()
        statuses = [
            e["status"] for e in detail["events"] if e.get("type") == "status"
        ]
        assert statuses[-1] == "cancelled"
        assert "done" not in statuses


def test_cancel_terminal_run_returns_terminal_status(monkeypatch) -> None:
    """Cancelling an already-finished run reports its terminal status and
    does not transition anything."""
    import time

    from web.backend.app import app
    from web.backend import runs as runs_mod

    monkeypatch.setattr(
        runs_mod.AnalysisRunner,
        "run",
        lambda self: {"final_trade_decision": "BUY"},
    )

    with TestClient(app) as client:
        start = client.post(
            "/api/runs",
            json={"ticker": "SPY", "analysis_date": "2025-01-02"},
        )
        run_id = start.json()["run_id"]

        deadline = time.time() + 5.0
        status = None
        while time.time() < deadline:
            status = client.get(f"/api/runs/{run_id}").json()["status"]
            if status in {"done", "error", "cancelled"}:
                break
            time.sleep(0.05)
        assert status in {"done", "error"}

        cancel = client.delete(f"/api/runs/{run_id}")
        assert cancel.status_code == 200
        assert cancel.json()["status"] == status  # unchanged, not "cancelling"


def test_get_unknown_report_404(client) -> None:
    r = client.get("/api/reports/NOSUCH_20250101_000000")
    assert r.status_code == 404


def test_report_folder_path_traversal_blocked(client) -> None:
    r = client.get("/api/reports/..%2F..%2Fetc%2Fpasswd")
    assert r.status_code == 404


def test_spa_fallback_blocks_api_root(client) -> None:
    r = client.get("/api")
    assert r.status_code == 404


def test_reports_index_include_incomplete_query(client, monkeypatch) -> None:
    from web.backend import api as api_mod

    captured = {}

    def fake_list(include_incomplete: bool = False):
        captured["include"] = include_incomplete
        return []

    monkeypatch.setattr(api_mod, "list_reports", fake_list)

    client.get("/api/reports?include_incomplete=true")
    assert captured["include"] is True
