from __future__ import annotations

import os
import sys
import typing

try:
    import uvicorn
    from fastapi import Depends, FastAPI, HTTPException, status
    from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
except ImportError as err:
    msg = ("The API is not install. Install it with: pip install 'ntk[api]'",)
    raise SystemExit(msg) from err

from ntk.presentation.cli.app import create_root_parser

from .routers import calculate

app = FastAPI()

security_sheme = HTTPBearer()

ntk_api_token = os.getenv("NTK_API_TOKEN")

if ntk_api_token is None:
    msg = "No environment variable for ntk api found."
    raise RuntimeError(msg)


def verify_token(
    credentials: HTTPAuthorizationCredentials | None = None,
) -> str:
    """Verify the provided token."""
    if credentials is None:
        credentials = Depends(security_sheme)
    token = credentials.credentials
    expected_token = os.getenv("NTK_API_TOKEN")
    if expected_token is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server misconfiguration: NTK_API_TOKEN not set",
        )
    if token != expected_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token


app.include_router(
    calculate.router,
    prefix="/api/v1",
    tags=["calculate"],
    dependencies=[Depends(verify_token)],
)


@app.get("/")
async def root(
    token: typing.Annotated[str, Depends(verify_token)],
) -> dict[str, str]:
    """Get root path."""
    return {"message": "Welcome to the Nutrition Toolkit API", "token": token}


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
        default=8000,
        help="Port to bind the server to",
    )
    ns = parser.parse_args(args)
    uvicorn.run(
        "ntk.presentation.api.main:app",
        host=ns.host,
        port=ns.port,
        reload=ns.dev,
    )
