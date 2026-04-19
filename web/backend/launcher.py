"""Console-script launcher for the optional web dashboard.

Keeps the script importable even when web extras are not installed, and
returns a clear installation hint instead of a raw stack trace.
"""

from __future__ import annotations


def main() -> None:
    try:
        from web.backend.app import main as run_web
    except ModuleNotFoundError as exc:
        missing = {"fastapi", "uvicorn", "websockets", "dotenv"}
        if exc.name in missing:
            raise SystemExit(
                "Web dashboard dependencies are missing. "
                "Install with: pip install \"tradingagents[web]\""
            ) from exc
        raise

    run_web()
