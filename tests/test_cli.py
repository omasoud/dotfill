"""Tests for Typer CLI wiring."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from dotfill.cli import app, run_cli
from dotfill.errors import DotfillError

runner = CliRunner()


def test_config_path_prints_final_config_dir(tmp_path: Path) -> None:
    result = runner.invoke(app, ["--config-root", str(tmp_path), "config", "path"])

    assert result.exit_code == 0
    assert result.stdout.strip() == str(tmp_path.resolve(strict=False))


def test_config_path_flags(tmp_path: Path) -> None:
    root = tmp_path.resolve(strict=False)

    root_result = runner.invoke(app, ["--config-root", str(tmp_path), "config", "path", "--root"])
    common_result = runner.invoke(
        app, ["--config-root", str(tmp_path), "config", "path", "--common"]
    )
    user_result = runner.invoke(app, ["--config-root", str(tmp_path), "config", "path", "--user"])

    assert root_result.exit_code == 0
    assert root_result.stdout.strip() == str(root)
    assert common_result.exit_code == 0
    assert common_result.stdout.strip() == str(root / "config_common.toml")
    assert user_result.exit_code == 0
    assert user_result.stdout.strip() == str(root / "config.toml")


def test_config_path_profile_prints_profile_dir(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["--config-root", str(tmp_path), "--profile", "team", "config", "path"],
    )

    assert result.exit_code == 0
    assert result.stdout.strip() == str(
        tmp_path.resolve(strict=False) / "profiles" / "team"
    )


def test_config_open_creates_and_opens_config_dir(
    tmp_path: Path, monkeypatch
) -> None:
    calls: list[tuple[Path, bool]] = []

    def fake_open_directory(path: Path, *, create: bool = False) -> None:
        calls.append((path, create))
        if create:
            path.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("dotfill.cli.open_directory", fake_open_directory)

    result = runner.invoke(
        app,
        ["--config-root", str(tmp_path), "--profile", "team", "config", "open"],
    )

    expected = tmp_path.resolve(strict=False) / "profiles" / "team"
    assert result.exit_code == 0
    assert calls == [(expected, True)]
    assert expected.is_dir()
    assert not (expected / "config_common.toml").exists()
    assert not (expected / "config.toml").exists()


def test_status_succeeds_with_empty_config(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("UNRELATED=value\n", encoding="utf-8")

    result = runner.invoke(
        app,
        ["--config-root", str(tmp_path / "config"), "--env-path", str(env), "status"],
    )

    assert result.exit_code == 0
    assert f"env: {env.resolve(strict=False)}" in result.stdout
    assert "services:" in result.stdout
    assert "UNRELATED=value" not in result.stdout


def test_status_exits_nonzero_for_invalid_config(tmp_path: Path) -> None:
    config_root = tmp_path / "config"
    config_root.mkdir()
    (config_root / "config.toml").write_text(
        """
version = 1

[services.BAD]
display_name = "Bad"
""".strip(),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["--config-root", str(config_root), "status"])

    assert result.exit_code == 2
    assert "error:" in result.stderr


def test_run_cli_returns_typer_integer_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_app(**kwargs):  # type: ignore[no-untyped-def]
        return 7

    monkeypatch.setattr("dotfill.cli.app", fake_app)

    assert run_cli(argv=["status"]) == 7


def test_run_cli_catches_callback_dotfill_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_before_config_load(_config_context) -> None:  # type: ignore[no-untyped-def]
        raise DotfillError("managed config sync failed")

    code = run_cli(
        argv=["config", "path"],
        obj={
            "entry_config_root": tmp_path,
            "entry_before_config_load": fail_before_config_load,
        },
    )

    captured = capsys.readouterr()
    assert code == 2
    assert "error: managed config sync failed" in captured.err
