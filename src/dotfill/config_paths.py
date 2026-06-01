"""Configuration root/profile path resolution."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_config_dir

from .errors import InvalidProfileNameError

CONFIG_ROOT_ENV = "DOTFILL_CONFIG_ROOT"
PROFILE_ENV = "DOTFILL_PROFILE"

_PROFILE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


@dataclass(frozen=True)
class ConfigContext:
    """Resolved configuration paths for one dotfill invocation."""

    config_root: Path
    profile: str | None
    config_dir: Path
    common_config_path: Path
    user_config_path: Path


def default_config_root() -> Path:
    """Return the platform user config directory for generic dotfill."""
    return Path(user_config_dir("dotfill", appauthor=False, roaming=True))


def validate_profile_name(profile: str) -> str:
    """Validate and return a safe profile directory name."""
    if profile in {"", ".", ".."} or not _PROFILE_RE.fullmatch(profile):
        raise InvalidProfileNameError(
            "Profile names must match "
            "^[A-Za-z0-9][A-Za-z0-9_.-]*$ and may not be '.', '..', or a path."
        )
    return profile


def _normalize_path(path: str | os.PathLike[str]) -> Path:
    out = Path(path).expanduser()
    if not out.is_absolute():
        out = Path.cwd() / out
    return out.resolve(strict=False)


def resolve_config_context(
    *,
    config_root: str | os.PathLike[str] | None = None,
    profile: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> ConfigContext:
    """Resolve config root, active profile, and final TOML paths.

    Resolution is intentionally pure: it does not create directories and does
    not read config files.
    """
    env = os.environ if environ is None else environ

    root_input: str | os.PathLike[str] | None = config_root
    if root_input is None:
        root_input = env.get(CONFIG_ROOT_ENV)
    root = _normalize_path(root_input) if root_input else default_config_root()

    profile_input = profile
    if profile_input is None:
        profile_input = env.get(PROFILE_ENV)
    active_profile = validate_profile_name(profile_input) if profile_input else None

    config_dir = root if active_profile is None else root / "profiles" / active_profile
    return ConfigContext(
        config_root=root,
        profile=active_profile,
        config_dir=config_dir,
        common_config_path=config_dir / "config_common.toml",
        user_config_path=config_dir / "config.toml",
    )
