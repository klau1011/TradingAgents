"""Discovery + reading of past report folders."""

from __future__ import annotations

import datetime
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from tradingagents.default_config import DEFAULT_CONFIG

# Folder name patterns:
#   legacy:  TICKER_YYYYMMDD_HHMMSS                       (e.g. MSFT_20260413_203023)
#   current: TICKER_YYYYMMDD_HHMMSS_microseconds_uuid6    (collision-safe)
_FOLDER_RE = re.compile(
    r"^(?P<ticker>[A-Za-z0-9.\-]+)_(?P<ts>\d{8}_\d{6})(?:_(?P<us>\d+))?(?:_(?P<uid>[a-f0-9]{4,}))?$"
)
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _report_roots() -> List[Path]:
    """Directories scanned for past reports.

    Reads from both the repo's local ``reports/`` and the user's configured
    ``results_dir``; new runs are written to ``results_dir`` (per default
    config), but legacy reports living in the repo are still surfaced.
    """
    roots: List[Path] = []
    repo_reports = _REPO_ROOT / "reports"
    if repo_reports.exists():
        roots.append(repo_reports)
    results_dir = Path(DEFAULT_CONFIG["results_dir"])
    if results_dir.exists() and results_dir not in roots:
        roots.append(results_dir)
    return roots


def list_reports() -> List[Dict[str, Any]]:
    seen: Dict[str, Dict[str, Any]] = {}
    for root in _report_roots():
        for entry in root.iterdir():
            if not entry.is_dir():
                continue
            m = _FOLDER_RE.match(entry.name)
            if not m:
                continue
            try:
                ts = datetime.datetime.strptime(m.group("ts"), "%Y%m%d_%H%M%S")
                if m.group("us"):
                    ts = ts.replace(microsecond=int(m.group("us")[:6].ljust(6, "0")))
            except ValueError:
                continue
            complete = entry / "complete_report.md"
            if not complete.exists():
                continue
            key = entry.name
            decision = _peek_decision(entry)
            seen[key] = {
                "folder": entry.name,
                "ticker": m.group("ticker"),
                "timestamp": ts.isoformat(),
                "path": str(entry),
                "root": str(root),
                "decision": decision,
            }
    return sorted(seen.values(), key=lambda r: r["timestamp"], reverse=True)


def _peek_decision(folder: Path) -> Optional[str]:
    """Best-effort: extract a BUY/HOLD/SELL-style label from the portfolio file."""
    decision_file = folder / "5_portfolio" / "decision.md"
    if not decision_file.exists():
        return None
    try:
        text = decision_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for keyword in (
        "STRONG BUY",
        "BUY",
        "OVERWEIGHT",
        "HOLD",
        "UNDERWEIGHT",
        "SELL",
        "STRONG SELL",
    ):
        if re.search(rf"\b{keyword}\b", text, flags=re.IGNORECASE):
            return keyword
    return None


def get_report(folder: str) -> Optional[Dict[str, Any]]:
    safe = _safe_folder(folder)
    if safe is None:
        return None
    for root in _report_roots():
        candidate = root / safe
        if not candidate.exists() or not candidate.is_dir():
            continue
        complete = candidate / "complete_report.md"
        if not complete.exists():
            continue
        sections: Dict[str, Dict[str, str]] = {}
        for sub in ("1_analysts", "2_research", "3_trading", "4_risk", "5_portfolio"):
            sub_dir = candidate / sub
            if not sub_dir.exists():
                continue
            files: Dict[str, str] = {}
            for f in sorted(sub_dir.iterdir()):
                if f.suffix == ".md":
                    files[f.stem] = f.read_text(encoding="utf-8", errors="replace")
            if files:
                sections[sub] = files
        m = _FOLDER_RE.match(safe)
        return {
            "folder": safe,
            "ticker": m.group("ticker") if m else safe,
            "complete_report": complete.read_text(encoding="utf-8", errors="replace"),
            "sections": sections,
            "decision": _peek_decision(candidate),
            "path": str(candidate),
        }
    return None


def _safe_folder(folder: str) -> Optional[str]:
    """Reject anything that isn't a plain ``TICKER_TIMESTAMP`` segment."""
    if not folder or "/" in folder or "\\" in folder or os.sep in folder:
        return None
    if folder in {".", ".."}:
        return None
    if not _FOLDER_RE.match(folder):
        return None
    return folder
