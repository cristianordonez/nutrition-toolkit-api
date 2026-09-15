from __future__ import annotations

import logging
import sys

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from api.models.settings import SETTINGS

try:
    import logfire
    import uvicorn
    from fastapi import FastAPI
except ImportError as err:
    msg = (
        "The API dependencies are not installed. Install them with: pip install 'api[api]'",  # noqa: E501
    )
    raise SystemExit(msg) from err


from api.database.db import initialize_database
from api.presentation.cli.app import create_root_parser
from ntk.logger import setup_logging

from .routers import (
    calculate,
    knowledge,
    nutrition_care_processes,
)

app = FastAPI()

logger = setup_logging(debug=SETTINGS.debug)
logging.getLogger("openai._base_client").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

logfire.configure()
logfire.instrument_fastapi(app)


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
    nutrition_care_processes.router,
    prefix="/api/v1",
    tags=["nutrition-care-processes"],
)


@app.exception_handler(Exception)
async def handle_exception(_: Request, exc: Exception) -> JSONResponse:
    """Catch-all exception handler that returns JSON and logs the error."""
    logger.error("Unhandled exception while processing request: %s", exc)
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})
    return JSONResponse(status_code=500, content={"error": str(exc)})


def start(args: list[str] | None = None) -> None:
    """Start the FastAPI server."""
    initialize_database()
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
        "api.presentation.api.main:app",
        host=ns.host,
        port=ns.port,
        reload=ns.dev,
    )
