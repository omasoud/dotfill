"""Tests for config root/profile path resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from dotfill.config_paths import (
    CONFIG_ROOT_ENV,
    PROFILE_ENV,
    ConfigContext,
    resolve_config_context,
    validate_profile_name,
)
from dotfill.errors import InvalidProfileNameError


def test_explicit_config_root_wins_over_environment(tmp_path: Path) -> None:
    cli_root = tmp_path / "cli-root"
    env_root = tmp_path / "env-root"

    ctx = resolve_config_context(
        config_root=cli_root,
        environ={CONFIG_ROOT_ENV: str(env_root)},
    )

    assert ctx.config_root == cli_root.resolve(strict=False)
    assert ctx.config_dir == cli_root.resolve(strict=False)


def test_environment_config_root_used_when_no_explicit_root(tmp_path: Path) -> None:
    env_root = tmp_path / "env-root"

    ctx = resolve_config_context(environ={CONFIG_ROOT_ENV: str(env_root)})

    assert ctx.config_root == env_root.resolve(strict=False)
    assert ctx.config_dir == env_root.resolve(strict=False)


def test_default_config_root_uses_platformdirs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    platform_root = tmp_path / "platform-root"
    monkeypatch.setattr(
        "dotfill.config_paths.user_config_dir",
        lambda *args, **kwargs: str(platform_root),
    )

    ctx = resolve_config_context(environ={})

    assert ctx.config_root == platform_root
    assert ctx.config_dir == platform_root


def test_explicit_profile_wins_over_environment(tmp_path: Path) -> None:
    root = tmp_path / "root"

    ctx = resolve_config_context(
        config_root=root,
        profile="team",
        environ={PROFILE_ENV: "other"},
    )

    expected_root = root.resolve(strict=False)
    assert ctx.profile == "team"
    assert ctx.config_dir == expected_root / "profiles" / "team"


def test_environment_profile_used_when_no_explicit_profile(tmp_path: Path) -> None:
    root = tmp_path / "root"

    ctx = resolve_config_context(
        config_root=root,
        environ={PROFILE_ENV: "team"},
    )

    expected_root = root.resolve(strict=False)
    assert ctx.profile == "team"
    assert ctx.config_dir == expected_root / "profiles" / "team"


def test_no_profile_uses_config_root_as_config_dir(tmp_path: Path) -> None:
    root = tmp_path / "root"

    ctx = resolve_config_context(config_root=root, environ={})

    expected_root = root.resolve(strict=False)
    assert ctx.profile is None
    assert ctx.config_dir == expected_root


@pytest.mark.parametrize(
    "profile",
    ["", ".", "..", "/bad", "bad/name", r"bad\name", "-bad", "_bad"],
)
def test_invalid_profile_names_raise(profile: str) -> None:
    with pytest.raises(InvalidProfileNameError):
        validate_profile_name(profile)


@pytest.mark.parametrize("profile", ["a", "a.b", "a-b", "a_b", "Team01"])
def test_valid_profile_names(profile: str) -> None:
    assert validate_profile_name(profile) == profile


def test_relative_config_root_resolves_against_cwd(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)

    ctx = resolve_config_context(config_root="relative-root", environ={})

    assert ctx.config_root == (tmp_path / "relative-root").resolve(strict=False)


def test_tilde_config_root_expands_to_home() -> None:
    ctx = resolve_config_context(config_root="~/dotfill-config", environ={})

    assert ctx.config_root == (Path.home() / "dotfill-config").resolve(strict=False)


def test_resolution_does_not_create_directories_or_read_files(tmp_path: Path) -> None:
    root = tmp_path / "missing-root"

    ctx = resolve_config_context(config_root=root, profile="team", environ={})

    assert isinstance(ctx, ConfigContext)
    assert not root.exists()
    assert not ctx.config_dir.exists()
    assert ctx.common_config_path == ctx.config_dir / "config_common.toml"
    assert ctx.user_config_path == ctx.config_dir / "config.toml"
