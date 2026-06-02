"""Tests for stable wrapper-facing entrypoints."""

from __future__ import annotations

from pathlib import Path

import pytest

from dotfill.config_paths import ConfigContext
from dotfill.entrypoints import run_dotfill


def test_direct_config_dir_invocation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config_dir = tmp_path / "managed-config"

    code = run_dotfill(config_dir=config_dir, argv=["config", "path"])

    assert code == 0
    assert capsys.readouterr().out.strip() == str(config_dir.resolve(strict=False))


def test_wrapper_argv_pass_through_and_program_name(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = run_dotfill(
        config_root=tmp_path,
        argv=["missing-command"],
        program_name="wrapped-dotfill",
    )

    captured = capsys.readouterr()
    assert code != 0
    assert "wrapped-dotfill" in captured.err


def test_invalid_direct_config_dir_combinations(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="config_dir cannot be combined"):
        run_dotfill(config_dir=tmp_path / "direct", config_root=tmp_path / "root")

    with pytest.raises(ValueError, match="config_dir cannot be combined"):
        run_dotfill(config_dir=tmp_path / "direct", profile="team")

    with pytest.raises(ValueError, match="config_dir cannot be combined"):
        run_dotfill(config_dir=tmp_path / "direct", default_profile="team")

    with pytest.raises(ValueError, match="config_dir cannot be combined"):
        run_dotfill(config_dir=tmp_path / "direct", locked_profile="team")


def test_invalid_locked_profile_combinations(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="locked_profile cannot be combined"):
        run_dotfill(locked_profile="team", profile="explicit")

    with pytest.raises(ValueError, match="locked_profile cannot be combined"):
        run_dotfill(locked_profile="team", default_profile="fallback")


def test_before_config_load_can_write_common_toml(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    env = tmp_path / ".env"
    env.write_text("", encoding="utf-8")
    config_dir = tmp_path / "config"

    def sync_config(context: ConfigContext) -> None:
        context.config_dir.mkdir(parents=True, exist_ok=True)
        context.common_config_path.write_text(
            f"""
version = 1

[target]
default_env_path = "{env.as_posix()}"

[services.TOOL]
display_name = "Tool"
token_var = "TOOL_TOKEN"
token_url = "https://service.example.com/tokens"
test_url = "https://service.example.com/me"
""".strip(),
            encoding="utf-8",
        )

    code = run_dotfill(
        config_dir=config_dir,
        argv=["status"],
        before_config_load=sync_config,
    )

    assert code == 0
    out = capsys.readouterr().out
    assert f"config: {config_dir.resolve(strict=False)}" in out
    assert "TOOL_TOKEN" in out


def test_status_masks_configured_identity_and_derived_values(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    env = tmp_path / ".env"
    env.write_text("WORK_USERNAME=alice@example.com\n", encoding="utf-8")
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_dir.joinpath("config.toml").write_text(
        f"""
version = 1

[target]
default_env_path = "{env.as_posix()}"

[identities.WORK_EMAIL]
source = "literal"
value = "alice@example.com"
display = "masked"

[derived.WORK_USERNAME]
from_identity = "WORK_EMAIL"
display = "masked"
""".strip(),
        encoding="utf-8",
    )

    code = run_dotfill(config_dir=config_dir, argv=["status"])

    assert code == 0
    out = capsys.readouterr().out
    assert "alice@example.com" not in out
    assert "••••••••.com" in out


def test_default_profile_precedence(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "config-root"
    monkeypatch.delenv("DOTFILL_PROFILE", raising=False)

    code = run_dotfill(
        config_root=root,
        default_profile="team",
        argv=["config", "path"],
    )
    assert code == 0
    assert capsys.readouterr().out.strip() == str(
        root.resolve(strict=False) / "profiles" / "team"
    )

    monkeypatch.setenv("DOTFILL_PROFILE", "from-env")
    code = run_dotfill(
        config_root=root,
        default_profile="team",
        argv=["config", "path"],
    )
    assert code == 0
    assert capsys.readouterr().out.strip() == str(
        root.resolve(strict=False) / "profiles" / "from-env"
    )

    code = run_dotfill(
        config_root=root,
        profile="explicit",
        default_profile="team",
        argv=["config", "path"],
    )
    assert code == 0
    assert capsys.readouterr().out.strip() == str(
        root.resolve(strict=False) / "profiles" / "explicit"
    )


def test_locked_profile_forces_profile(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DOTFILL_PROFILE", raising=False)
    root = tmp_path / "config-root"

    code = run_dotfill(
        config_root=root,
        locked_profile="team",
        argv=["config", "path"],
    )

    assert code == 0
    assert capsys.readouterr().out.strip() == str(
        root.resolve(strict=False) / "profiles" / "team"
    )


def test_locked_profile_accepts_matching_cli_profile(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DOTFILL_PROFILE", raising=False)
    root = tmp_path / "config-root"

    code = run_dotfill(
        config_root=root,
        locked_profile="team",
        argv=["--profile", "team", "config", "path"],
    )

    assert code == 0
    assert capsys.readouterr().out.strip() == str(
        root.resolve(strict=False) / "profiles" / "team"
    )


def test_locked_profile_rejects_mismatched_cli_profile(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DOTFILL_PROFILE", raising=False)

    code = run_dotfill(
        config_root=tmp_path,
        locked_profile="team",
        argv=["--profile", "other", "config", "path"],
    )

    assert code != 0
    assert "locked profile 'team'" in capsys.readouterr().err


def test_locked_profile_rejects_mismatched_env_profile(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DOTFILL_PROFILE", "other")

    code = run_dotfill(
        config_root=tmp_path,
        locked_profile="team",
        argv=["config", "path"],
    )

    assert code != 0
    assert "locked profile 'team'" in capsys.readouterr().err


def test_locked_profile_accepts_matching_env_profile(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DOTFILL_PROFILE", "team")
    root = tmp_path / "config-root"

    code = run_dotfill(
        config_root=root,
        locked_profile="team",
        argv=["config", "path"],
    )

    assert code == 0
    assert capsys.readouterr().out.strip() == str(
        root.resolve(strict=False) / "profiles" / "team"
    )


def test_locked_profile_keeps_config_root_cli_override(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DOTFILL_PROFILE", raising=False)
    entry_root = tmp_path / "entry-root"
    cli_root = tmp_path / "cli-root"

    code = run_dotfill(
        config_root=entry_root,
        locked_profile="team",
        argv=["--config-root", str(cli_root), "config", "path"],
    )

    assert code == 0
    assert capsys.readouterr().out.strip() == str(
        cli_root.resolve(strict=False) / "profiles" / "team"
    )


def test_locked_profile_context_paths_and_hook_timing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DOTFILL_PROFILE", raising=False)
    root = tmp_path / "config-root"
    seen: list[ConfigContext] = []

    def capture_context(context: ConfigContext) -> None:
        seen.append(context)

    code = run_dotfill(
        config_root=root,
        locked_profile="team",
        argv=["config", "path", "--common"],
        before_config_load=capture_context,
    )

    assert code == 0
    resolved_root = root.resolve(strict=False)
    expected_dir = resolved_root / "profiles" / "team"
    assert capsys.readouterr().out.strip() == str(expected_dir / "config_common.toml")
    assert seen == [
        ConfigContext(
            config_root=resolved_root,
            profile="team",
            config_dir=expected_dir,
            common_config_path=expected_dir / "config_common.toml",
            user_config_path=expected_dir / "config.toml",
        )
    ]


def test_direct_config_dir_context_paths(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: list[ConfigContext] = []
    config_dir = tmp_path / "direct"

    def capture_context(context: ConfigContext) -> None:
        seen.append(context)

    code = run_dotfill(
        config_dir=config_dir,
        argv=["config", "path", "--common"],
        before_config_load=capture_context,
    )

    assert code == 0
    resolved = config_dir.resolve(strict=False)
    assert capsys.readouterr().out.strip() == str(resolved / "config_common.toml")
    assert seen == [
        ConfigContext(
            config_root=resolved.parent,
            profile=None,
            config_dir=resolved,
            common_config_path=resolved / "config_common.toml",
            user_config_path=resolved / "config.toml",
        )
    ]
