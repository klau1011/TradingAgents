"""TradingAgents dashboard FastAPI app.

Run dev server::

    uvicorn web.backend.app:app --reload --port 8000

For production (after building the frontend with ``npm run build``)::

    python -m web.backend.app
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import router as api_router

load_dotenv()
load_dotenv(".env.enterprise", override=False)


def create_app() -> FastAPI:
    app = FastAPI(title="TradingAgents Dashboard", version="0.1.0")

    # Local-only CORS for the Vite dev server.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    # Serve built frontend if present (production / single-process deploy)
    static_dir = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    if static_dir.exists():
        app.mount(
            "/assets",
            StaticFiles(directory=static_dir / "assets"),
            name="assets",
        )

        @app.get("/{full_path:path}")
        def spa_fallback(full_path: str):
            # API routes are matched before this fallback because FastAPI
            # dispatches in registration order; this only catches non-API URLs.
            target = static_dir / full_path
            if target.is_file():
                return FileResponse(target)
            return FileResponse(static_dir / "index.html")

    return app


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run("web.backend.app:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
