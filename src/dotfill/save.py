"""Save pipeline: backup + atomic write of `.env`."""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from pathlib import Path

from .envdoc import EnvDocument
from .errors import SaveError
from .models import SessionState
from .paths import backup_path_for

log = logging.getLogger(__name__)


def ensure_backup(env_path: Path, session: SessionState) -> Path | None:
    """Create one backup per session before the first save.

    Returns the backup path (newly created or pre-existing for this session),
    or None if there is no env file to back up.
    """
    if session.backup_created:
        return session.backup_path
    if not env_path.exists():
        session.backup_created = True
        session.backup_path = None
        return None
    backup = backup_path_for(env_path)
    try:
        shutil.copy2(env_path, backup)
    except OSError as exc:
        raise SaveError(f"Failed to create backup at {backup}: {exc}") from exc
    session.backup_created = True
    session.backup_path = backup
    log.info("Created session backup", extra={"backup_path": str(backup)})
    return backup


def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    """Write `content` to `path` atomically via a sibling temp file + os.replace.

    Uses `newline=""` so the EnvDocument's preserved line endings are written
    byte-for-byte without translation.
    """
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=parent
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="") as f:
            f.write(content)
        os.replace(tmp_path, path)
    except OSError as exc:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise SaveError(f"Failed to write {path}: {exc}") from exc


def save_assignments(
    env_path: Path,
    doc: EnvDocument,
    updates: dict[str, str],
    session: SessionState,
) -> None:
    """Apply updates to the document and persist atomically (with backup)."""
    if not updates:
        return
    ensure_backup(env_path, session)
    doc.set_values(updates)
    rendered = doc.render()
    atomic_write_text(env_path, rendered)
