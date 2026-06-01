"""Local-only Uvicorn server wiring static frontend + JSON API."""

from __future__ import annotations

import logging
import socket
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .api import AppContext, create_app

log = logging.getLogger(__name__)

_BIND_HOST = "127.0.0.1"


def pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((_BIND_HOST, 0))
        return int(s.getsockname()[1])


def static_dir() -> Path:
    return Path(__file__).resolve().parent / "static"


def build_full_app(ctx: AppContext) -> FastAPI:
    app = create_app(ctx)
    static = static_dir()
    if static.exists():
        app.mount(
            "/",
            StaticFiles(directory=str(static), html=True),
            name="static",
        )
    return app


def run_server(ctx: AppContext, *, port: int | None = None, open_browser: bool = True) -> None:
    if port is None:
        port = pick_free_port()
    app = build_full_app(ctx)
    url = f"http://{_BIND_HOST}:{port}/"
    log.info("dotfill listening on %s", url)
    if open_browser:
        import webbrowser
        webbrowser.open(url + f"?session={ctx.session.token}")
    uvicorn.run(app, host=_BIND_HOST, port=port, log_config=None)
