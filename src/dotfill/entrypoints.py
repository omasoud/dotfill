"""Stable Python entrypoints for wrappers and console scripts."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from .config_paths import ConfigContext
from .config_paths import resolve_config_context as _resolve_config_context


BeforeConfigLoad = Callable[[ConfigContext], None]


def resolve_config_context(
    *,
    config_root: str | os.PathLike[str] | None = None,
    profile: str | None = None,
) -> ConfigContext:
    """Resolve dotfill configuration paths using the public stable API."""
    return _resolve_config_context(config_root=config_root, profile=profile)


def _normalize_config_dir(config_dir: str | os.PathLike[str]) -> Path:
    path = Path(config_dir).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve(strict=False)


def _direct_config_context(config_dir: str | os.PathLike[str]) -> ConfigContext:
    path = _normalize_config_dir(config_dir)
    return ConfigContext(
        config_root=path.parent,
        profile=None,
        config_dir=path,
        common_config_path=path / "config_common.toml",
        user_config_path=path / "config.toml",
    )


def run_dotfill(
    *,
    config_dir: str | os.PathLike[str] | None = None,
    config_root: str | os.PathLike[str] | None = None,
    profile: str | None = None,
    default_profile: str | None = None,
    env_path: str | os.PathLike[str] | None = None,
    argv: Sequence[str] | None = None,
    program_name: str = "dotfill",
    before_config_load: BeforeConfigLoad | None = None,
) -> int:
    """Run dotfill without calling ``sys.exit``.

    Wrapper packages can either supply an explicit ``config_dir`` containing
    TOML files, or supply a normal config root/profile/default-profile policy.
    """
    if config_dir is not None and (
        config_root is not None or profile is not None or default_profile is not None
    ):
        raise ValueError(
            "config_dir cannot be combined with config_root, profile, or default_profile"
        )

    obj: dict[str, object] = {}
    if config_dir is not None:
        obj["entry_config_context"] = _direct_config_context(config_dir)
    else:
        if config_root is not None:
            obj["entry_config_root"] = config_root
        if profile is not None:
            obj["entry_profile"] = profile
        if default_profile is not None:
            obj["entry_default_profile"] = default_profile

    if env_path is not None:
        obj["entry_env_path"] = Path(env_path)
    if before_config_load is not None:
        obj["entry_before_config_load"] = before_config_load

    from .cli import run_cli

    return run_cli(argv=argv, program_name=program_name, obj=obj)


def main() -> None:
    """Console-script shim."""
    program_name = Path(sys.argv[0]).name or "dotfill"
    sys.exit(run_dotfill(argv=sys.argv[1:], program_name=program_name))
