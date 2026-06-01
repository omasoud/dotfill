"""Reusable test helpers for generic dotfill fixtures."""

from __future__ import annotations

from pathlib import Path

from dotfill.models import SessionState


def make_session(token: str = "test-session-token") -> SessionState:
    return SessionState(token=token)


def write_env(tmp_path: Path, text: str = "") -> Path:
    path = tmp_path / ".env"
    path.write_text(text, encoding="utf-8")
    return path


def write_config(
    root: Path,
    *,
    common: str | None = None,
    user: str | None = None,
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    if common is not None:
        (root / "config_common.toml").write_text(common, encoding="utf-8")
    if user is not None:
        (root / "config.toml").write_text(user, encoding="utf-8")
    return root


def generic_config_text(env_path: Path) -> str:
    return f"""
version = 1
name = "Test profile"

[target]
default_env_path = "{env_path.as_posix()}"

[identities.WORK_EMAIL]
source = "literal"
value = "alice@example.com"

[identities.WORK_USER]
source = "local_part"
from = "WORK_EMAIL"

[derived.WORK_USERNAME]
from_identity = "WORK_EMAIL"

[services.EXAMPLE]
display_name = "Example"
token_var = "EXAMPLE_TOKEN"
token_url = "https://service.example.com/{{WORK_USER}}/tokens"
test_url = "https://service.example.com/me"
icon = "key"
""".strip()
