"""Unit tests for web.backend.reports discovery + read helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from web.backend import reports as reports_mod


@pytest.fixture()
def fake_reports_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the reports module at a temporary root with no real reports."""
    monkeypatch.setattr(reports_mod, "_report_roots", lambda: [tmp_path])
    return tmp_path


def _write_complete(folder: Path, *, decision_text: str = "1. **Rating**: **Buy**\n") -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "complete_report.md").write_text("# Report\n", encoding="utf-8")
    portfolio = folder / "5_portfolio"
    portfolio.mkdir()
    (portfolio / "decision.md").write_text(decision_text, encoding="utf-8")


def test_list_reports_skips_incomplete_by_default(fake_reports_root: Path) -> None:
    incomplete = fake_reports_root / "FOO_20260101_120000"
    incomplete.mkdir()
    (incomplete / "1_analysts").mkdir()

    complete = fake_reports_root / "BAR_20260102_120000"
    _write_complete(complete)

    listed = reports_mod.list_reports()
    folders = {r["folder"] for r in listed}
    assert folders == {"BAR_20260102_120000"}


def test_list_reports_can_include_incomplete(fake_reports_root: Path) -> None:
    incomplete = fake_reports_root / "FOO_20260101_120000"
    incomplete.mkdir()

    complete = fake_reports_root / "BAR_20260102_120000"
    _write_complete(complete)

    listed = reports_mod.list_reports(include_incomplete=True)
    by_folder = {r["folder"]: r for r in listed}
    assert by_folder["FOO_20260101_120000"]["status"] == "incomplete"
    assert by_folder["FOO_20260101_120000"]["decision"] is None
    assert by_folder["BAR_20260102_120000"]["status"] == "complete"
    assert by_folder["BAR_20260102_120000"]["decision"] == "BUY"


def test_get_report_tolerates_unreadable_section_file(
    fake_reports_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = fake_reports_root / "BAZ_20260103_120000"
    _write_complete(folder)
    bad = folder / "1_analysts"
    bad.mkdir()
    bad_file = bad / "market.md"
    bad_file.write_text("ok", encoding="utf-8")

    real_read = Path.read_text

    def flaky_read_text(self: Path, *args, **kwargs):  # type: ignore[no-untyped-def]
        if self == bad_file:
            raise OSError("simulated read failure")
        return real_read(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", flaky_read_text)

    report = reports_mod.get_report("BAZ_20260103_120000")
    assert report is not None
    assert report["sections"]["1_analysts"]["market"] == reports_mod._CORRUPT_PLACEHOLDER
    # The complete report and decision should still come through.
    assert report["complete_report"].startswith("# Report")


def test_get_report_uses_complete_folder_across_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    early_root = tmp_path / "early"
    later_root = tmp_path / "later"
    early_root.mkdir()
    later_root.mkdir()

    folder_name = "DUP_20260107_120000"
    (early_root / folder_name).mkdir()
    _write_complete(later_root / folder_name)

    monkeypatch.setattr(reports_mod, "_report_roots", lambda: [early_root, later_root])

    report = reports_mod.get_report(folder_name)
    assert report is not None
    assert report["path"] == str(later_root / folder_name)


def test_get_report_returns_none_for_invalid_folder(fake_reports_root: Path) -> None:
    assert reports_mod.get_report("../etc") is None
    assert reports_mod.get_report("not a folder name") is None


def test_get_report_returns_none_for_incomplete(fake_reports_root: Path) -> None:
    incomplete = fake_reports_root / "INC_20260105_120000"
    incomplete.mkdir()
    (incomplete / "1_analysts").mkdir()
    assert reports_mod.get_report("INC_20260105_120000") is None


def test_decision_json_overrides_markdown_for_peek(fake_reports_root: Path) -> None:
    folder = fake_reports_root / "JSN_20260108_120000"
    _write_complete(folder, decision_text='**Rating**: **Hold**\n')
    import json as _json
    (folder / "5_portfolio" / "decision.json").write_text(
        _json.dumps({
            "rating": "Sell",
            "executive_summary": "exit",
            "investment_thesis": "thesis",
            "price_target": 12.5,
            "time_horizon": "3-6 months",
        }),
        encoding="utf-8",
    )

    listed = reports_mod.list_reports()
    by_folder = {r["folder"]: r for r in listed}
    # JSON wins over the markdown rating line.
    assert by_folder["JSN_20260108_120000"]["decision"] == "SELL"


def test_get_decision_returns_full_dict(fake_reports_root: Path) -> None:
    folder = fake_reports_root / "FUL_20260109_120000"
    _write_complete(folder)
    import json as _json
    payload = {
        "rating": "Buy",
        "executive_summary": "summary",
        "investment_thesis": "thesis",
        "price_target": None,
        "time_horizon": None,
    }
    (folder / "5_portfolio" / "decision.json").write_text(
        _json.dumps(payload), encoding="utf-8"
    )

    got = reports_mod.get_decision("FUL_20260109_120000")
    assert got == payload


def test_get_decision_returns_none_when_missing(fake_reports_root: Path) -> None:
    folder = fake_reports_root / "NOJ_20260110_120000"
    _write_complete(folder)
    assert reports_mod.get_decision("NOJ_20260110_120000") is None


def test_get_report_includes_decision_detail(fake_reports_root: Path) -> None:
    folder = fake_reports_root / "DET_20260111_120000"
    _write_complete(folder)
    import json as _json
    payload = {
        "rating": "Overweight",
        "executive_summary": "s",
        "investment_thesis": "t",
        "price_target": 99.0,
        "time_horizon": "1y",
    }
    (folder / "5_portfolio" / "decision.json").write_text(
        _json.dumps(payload), encoding="utf-8"
    )
    report = reports_mod.get_report("DET_20260111_120000")
    assert report is not None
    assert report["decision_detail"] == payload
    assert report["decision"] == "OVERWEIGHT"


def test_get_decision_rejects_incomplete_shape(fake_reports_root: Path) -> None:
    folder = fake_reports_root / "BAD_20260112_120000"
    _write_complete(folder)
    import json as _json
    payload = {
        "rating": "Buy",
        "executive_summary": "summary",
        # Missing required field: investment_thesis
    }
    (folder / "5_portfolio" / "decision.json").write_text(
        _json.dumps(payload), encoding="utf-8"
    )

    assert reports_mod.get_decision("BAD_20260112_120000") is None


def test_get_report_drops_invalid_decision_detail_and_falls_back_to_markdown_rating(
    fake_reports_root: Path,
) -> None:
    folder = fake_reports_root / "MAL_20260113_120000"
    _write_complete(folder, decision_text="**Rating**: **Hold**\n")
    import json as _json
    payload = {
        "rating": "Sell",
        "executive_summary": "summary",
        "investment_thesis": "thesis",
        "price_target": "not-a-number",
    }
    (folder / "5_portfolio" / "decision.json").write_text(
        _json.dumps(payload), encoding="utf-8"
    )

    report = reports_mod.get_report("MAL_20260113_120000")
    assert report is not None
    assert report["decision_detail"] is None
    # When decision.json is invalid, the markdown rating is used as fallback.
    assert report["decision"] == "HOLD"


def test_get_decision_normalizes_missing_optional_fields(fake_reports_root: Path) -> None:
    folder = fake_reports_root / "NOR_20260114_120000"
    _write_complete(folder)
    import json as _json
    payload = {
        "rating": "Buy",
        "executive_summary": "summary",
        "investment_thesis": "thesis",
    }
    (folder / "5_portfolio" / "decision.json").write_text(
        _json.dumps(payload), encoding="utf-8"
    )

    got = reports_mod.get_decision("NOR_20260114_120000")
    assert got is not None
    assert got["rating"] == "Buy"
    assert got["executive_summary"] == "summary"
    assert got["investment_thesis"] == "thesis"
    assert got["price_target"] is None
    assert got["time_horizon"] is None
