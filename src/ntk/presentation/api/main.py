from __future__ import annotations

import logging
import sys
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ntk.models.settings import SETTINGS

try:
    import logfire
    import uvicorn
    from fastapi import FastAPI, HTTPException, status
except ImportError as err:
    msg = (
        "The API dependencies are not installed. Install them with: pip install 'ntk[api]'",  # noqa: E501
    )
    raise SystemExit(msg) from err


from ntk.logger import setup_logging
from ntk.presentation.cli.app import create_root_parser

from .routers import assessment, calculate, knowledge, resident

app = FastAPI()

logger = setup_logging(debug=SETTINGS.debug)
logging.getLogger("openai._base_client").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

logfire.configure()
logfire.instrument_fastapi(app)


# Serve static assets (index.html lives in src/ntk/static)
_STATIC_DIR = Path(__file__).resolve().parents[2] / "static"
if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


app.include_router(
    calculate.router,
    prefix="/api/v1",
    tags=["calculate"],
)


app.include_router(
    knowledge.router,
    prefix="/api/v1",
    tags=["knowledge"],
)


app.include_router(
    assessment.router,
    prefix="/api/v1",
    tags=["assessment"],
)


app.include_router(
    resident.router,
    prefix="/api/v1",
    tags=["resident"],
)


@app.exception_handler(Exception)
async def handle_exception(_: Request, exc: Exception) -> JSONResponse:
    """Catch-all exception handler that returns JSON and logs the error."""
    logger.error("Unhandled exception while processing request: %s", exc)
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})
    return JSONResponse(status_code=500, content={"error": str(exc)})


@app.get("/", response_class=HTMLResponse)
async def root() -> HTMLResponse:
    """Render the single-page app index.html from the package static folder."""
    index_file = _STATIC_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Index not found",
        )
    return HTMLResponse(index_file.read_text(encoding="utf-8"))


def start(args: list[str] | None = None) -> None:
    """Start the FastAPI server."""
    if args is None:
        args = sys.argv[1:]
    parser = create_root_parser()
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Run in development mode",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",  # noqa: S104
        help="Host to bind the server to",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=SETTINGS.port,
        help="Port to bind the server to",
    )
    ns = parser.parse_args(args)
    uvicorn.run(
        "ntk.presentation.api.main:app",
        host=ns.host,
        port=ns.port,
        reload=ns.dev,
    )
