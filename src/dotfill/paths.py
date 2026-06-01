"""Path helpers for dotfill."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


def default_env_path() -> Path:
    """The default `.env` path: %USERPROFILE%\\.env on Windows."""
    return Path.home() / ".env"


def backup_path_for(env_path: Path, *, now: datetime | None = None) -> Path:
    """Compute the per-session backup filename for the given env file.

    Format: `.env.<YYYY-MM-DD-HHMM>.bak` placed alongside the env file.
    """
    when = now or datetime.now()
    stamp = when.strftime("%Y-%m-%d-%H%M")
    return env_path.with_name(f"{env_path.name}.{stamp}.bak")
