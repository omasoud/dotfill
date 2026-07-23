"""Tests for local server wiring."""

from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi.testclient import TestClient

from dotfill.api import AppContext
from dotfill.config_paths import resolve_config_context
from dotfill.models import SessionState
from dotfill.server import build_full_app, run_server


def test_javascript_media_type_ignores_host_mime_mapping(tmp_path: Path) -> None:
    ctx = AppContext(
        session=SessionState(token="session-token-x"),
        config_context=resolve_config_context(config_root=tmp_path, environ={}),
        env_path=tmp_path / ".env",
    )
    original_media_type = mimetypes.guess_type("app.js")[0]

    try:
        mimetypes.add_type("text/plain", ".js", strict=True)
        assert mimetypes.guess_type("app.js")[0] == "text/plain"

        response = TestClient(build_full_app(ctx)).get("/app.js")
    finally:
        if original_media_type is None:
            mimetypes.types_map.pop(".js", None)
        else:
            mimetypes.add_type(original_media_type, ".js", strict=True)

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/javascript"


def test_run_server_binds_to_loopback_only(
    tmp_path: Path, monkeypatch
) -> None:
    calls: list[dict[str, object]] = []
    ctx = AppContext(
        session=SessionState(token="session-token-x"),
        config_context=resolve_config_context(config_root=tmp_path, environ={}),
        env_path=tmp_path / ".env",
    )

    def fake_run(app, *, host: str, port: int, log_config):  # type: ignore[no-untyped-def]
        calls.append({"host": host, "port": port, "log_config": log_config})

    monkeypatch.setattr("dotfill.server.uvicorn.run", fake_run)

    run_server(ctx, port=43123, open_browser=False)

    assert calls == [{"host": "127.0.0.1", "port": 43123, "log_config": None}]
