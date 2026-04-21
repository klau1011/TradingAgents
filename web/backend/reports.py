"""Discovery + reading of past report folders."""

from __future__ import annotations

import datetime
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from tradingagents.default_config import DEFAULT_CONFIG

logger = logging.getLogger(__name__)

_CORRUPT_PLACEHOLDER = "_(content unavailable: file could not be read)_"

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


def list_reports(include_incomplete: bool = False) -> List[Dict[str, Any]]:
    """List discoverable report folders.

    By default only folders containing ``complete_report.md`` are returned.
    Pass ``include_incomplete=True`` to also surface in-progress / abandoned
    folders with ``status="incomplete"`` so the UI can display them.
    """
    seen: Dict[str, Dict[str, Any]] = {}
    for root in _report_roots():
        try:
            entries = list(root.iterdir())
        except OSError as exc:
            logger.warning("Could not list report root %s: %s", root, exc)
            continue
        for entry in entries:
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
            is_complete = complete.exists()
            if not is_complete and not include_incomplete:
                continue
            seen[entry.name] = {
                "folder": entry.name,
                "ticker": m.group("ticker"),
                "timestamp": ts.isoformat(),
                "path": str(entry),
                "root": str(root),
                "decision": _peek_decision(entry) if is_complete else None,
                "status": "complete" if is_complete else "incomplete",
            }
    return sorted(seen.values(), key=lambda r: r["timestamp"], reverse=True)


_RATING_KEYWORDS = (
    "STRONG BUY",
    "STRONG SELL",
    "OVERWEIGHT",
    "UNDERWEIGHT",
    "BUY",
    "SELL",
    "HOLD",
)
# Matches the explicit "Rating" line the Portfolio Manager writes at the top of
# decision.md, e.g. "1. **Rating**: **Sell**" or "Rating: Strong Buy".
_RATING_LINE_RE = re.compile(
    r"rating\s*\**\s*[:\-]\s*\**\s*(strong\s+buy|strong\s+sell|overweight|underweight|buy|sell|hold)\b",
    flags=re.IGNORECASE,
)


def _peek_decision(folder: Path) -> Optional[str]:
    """Best-effort: extract a BUY/HOLD/SELL-style label from the portfolio file.

    Prefer the explicit ``**Rating**: **X**`` line written at the top of the
    Portfolio Manager's decision; only fall back to keyword scanning if that
    line is absent. A document-wide priority scan is unsafe because the
    narrative often discusses other ratings (e.g. a Sell decision saying
    "Hold is too passive"), which would cause the badge to disagree with the
    actual decision.
    """
    decision_file = folder / "5_portfolio" / "decision.md"
    if not decision_file.exists():
        return None
    try:
        text = decision_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    m = _RATING_LINE_RE.search(text)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).upper()
    # Fallback: scan only the first non-empty line, which is usually the rating.
    for line in text.splitlines():
        if not line.strip():
            continue
        for keyword in _RATING_KEYWORDS:
            if re.search(rf"\b{keyword}\b", line, flags=re.IGNORECASE):
                return keyword
        break
    return None


def _safe_read(path: Path) -> str:
    """Read a markdown file without ever raising.

    A single corrupt or unreadable file should not 500 the entire report
    endpoint; substitute a placeholder and log instead.
    """
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.warning("Could not read report file %s: %s", path, exc)
        return _CORRUPT_PLACEHOLDER


def _resolve_folder(safe: str, *, require_complete: bool = False) -> Optional[Path]:
    """Resolve a folder name across report roots.

    When multiple roots contain the same folder, prefer the later root to match
    list_reports() overwrite semantics. For detail reads, callers can require a
    complete report so an incomplete shadow in an earlier root does not mask a
    complete folder in a later root.
    """
    chosen: Optional[Path] = None
    for root in _report_roots():
        candidate = root / safe
        if not candidate.exists() or not candidate.is_dir():
            continue
        if require_complete and not (candidate / "complete_report.md").exists():
            continue
        chosen = candidate
    return chosen


def get_report(folder: str) -> Optional[Dict[str, Any]]:
    safe = _safe_folder(folder)
    if safe is None:
        return None
    candidate = _resolve_folder(safe, require_complete=True)
    if candidate is None:
        return None
    complete = candidate / "complete_report.md"
    sections: Dict[str, Dict[str, str]] = {}
    for sub in ("0_summary", "1_analysts", "2_research", "3_trading", "4_risk", "5_portfolio"):
        sub_dir = candidate / sub
        if not sub_dir.exists():
            continue
        try:
            sub_entries = sorted(sub_dir.iterdir())
        except OSError as exc:
            logger.warning("Could not list report subdir %s: %s", sub_dir, exc)
            continue
        files: Dict[str, str] = {}
        for f in sub_entries:
            if f.suffix == ".md":
                files[f.stem] = _safe_read(f)
        if files:
            sections[sub] = files
    m = _FOLDER_RE.match(safe)
    briefing_path = candidate / "0_summary" / "briefing.md"
    briefing = _safe_read(briefing_path) if briefing_path.exists() else None
    return {
        "folder": safe,
        "ticker": m.group("ticker") if m else safe,
        "briefing": briefing,
        "complete_report": _safe_read(complete),
        "sections": sections,
        "decision": _peek_decision(candidate),
        "path": str(candidate),
    }


def _safe_folder(folder: str) -> Optional[str]:
    """Reject anything that isn't a plain ``TICKER_TIMESTAMP`` segment."""
    if not folder or "/" in folder or "\\" in folder or os.sep in folder:
        return None
    if folder in {".", ".."}:
        return None
    if not _FOLDER_RE.match(folder):
        return None
    return folder
