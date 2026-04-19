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


def test_get_unknown_report_404(client) -> None:
    r = client.get("/api/reports/NOSUCH_20250101_000000")
    assert r.status_code == 404


def test_report_folder_path_traversal_blocked(client) -> None:
    r = client.get("/api/reports/..%2F..%2Fetc%2Fpasswd")
    assert r.status_code == 404
