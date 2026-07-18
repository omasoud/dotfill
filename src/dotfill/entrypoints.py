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


def _normalize_wrapper_metadata(
    wrapper_name: str | None,
    wrapper_version: str | None,
) -> tuple[str | None, str | None]:
    """Validate and normalize optional paired wrapper display metadata."""
    if wrapper_name is None and wrapper_version is None:
        return None, None
    if wrapper_name is None or wrapper_version is None:
        raise ValueError(
            "wrapper_name and wrapper_version must be provided together"
        )
    normalized_name = wrapper_name.strip()
    normalized_version = wrapper_version.strip()
    if not normalized_name or not normalized_version:
        raise ValueError(
            "wrapper_name and wrapper_version must be non-empty strings"
        )
    return normalized_name, normalized_version


def run_dotfill(
    *,
    config_dir: str | os.PathLike[str] | None = None,
    config_root: str | os.PathLike[str] | None = None,
    profile: str | None = None,
    default_profile: str | None = None,
    locked_profile: str | None = None,
    env_path: str | os.PathLike[str] | None = None,
    argv: Sequence[str] | None = None,
    program_name: str = "dotfill",
    wrapper_name: str | None = None,
    wrapper_version: str | None = None,
    before_config_load: BeforeConfigLoad | None = None,
) -> int:
    """Run dotfill without calling ``sys.exit``.

    Wrapper packages can either supply an explicit ``config_dir`` containing
    TOML files, or supply a normal config root/profile/default-profile policy.

    Args:
        config_dir: Final directory containing ``config_common.toml`` and
            ``config.toml``. This direct mode cannot be combined with
            ``config_root``, ``profile``, or ``default_profile``.
        config_root: Root directory for dotfill configuration. When omitted,
            resolution uses ``DOTFILL_CONFIG_ROOT`` and then the platform
            default config directory.
        profile: Explicit profile name under ``config_root / "profiles"``.
            CLI ``--profile`` can still override this; otherwise this overrides
            ``DOTFILL_PROFILE`` and ``default_profile``.
        default_profile: Wrapper-provided fallback profile name. It is used
            only when neither CLI input, ``profile``, nor ``DOTFILL_PROFILE``
            selects a profile.
        locked_profile: Wrapper-enforced profile name. CLI ``--profile`` and
            ``DOTFILL_PROFILE`` are accepted only when they match this value.
            This cannot be combined with ``config_dir``, ``profile``, or
            ``default_profile``.
        env_path: Path to the target ``.env`` file. This is passed to the CLI
            as the entrypoint default and can still be overridden by
            ``--env-path`` in ``argv``.
        argv: Command-line arguments to pass to dotfill, excluding the program
            name. ``None`` reads arguments from the active process.
        program_name: Program name shown in CLI help and error output.
        wrapper_name: Optional wrapper name shown beside dotfill's dashboard
            version. Must be supplied with ``wrapper_version``.
        wrapper_version: Optional wrapper version shown beside dotfill's
            dashboard version. Must be supplied with ``wrapper_name``.
        before_config_load: Optional hook called with the resolved
            ``ConfigContext`` after path resolution and before TOML loading.
    """
    if config_dir is not None and (
        config_root is not None
        or profile is not None
        or default_profile is not None
        or locked_profile is not None
    ):
        raise ValueError(
            "config_dir cannot be combined with config_root, profile, "
            "default_profile, or locked_profile"
        )
    if locked_profile is not None and (
        profile is not None or default_profile is not None
    ):
        raise ValueError(
            "locked_profile cannot be combined with profile or default_profile"
        )

    normalized_wrapper_name, normalized_wrapper_version = (
        _normalize_wrapper_metadata(wrapper_name, wrapper_version)
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
        if locked_profile is not None:
            obj["entry_locked_profile"] = locked_profile

    if env_path is not None:
        obj["entry_env_path"] = Path(env_path)
    if normalized_wrapper_name is not None:
        obj["entry_wrapper_name"] = normalized_wrapper_name
        obj["entry_wrapper_version"] = normalized_wrapper_version
    if before_config_load is not None:
        obj["entry_before_config_load"] = before_config_load

    from .cli import run_cli

    return run_cli(argv=argv, program_name=program_name, obj=obj)


def main() -> None:
    """Console-script shim."""
    program_name = Path(sys.argv[0]).name or "dotfill"
    sys.exit(run_dotfill(argv=sys.argv[1:], program_name=program_name))
