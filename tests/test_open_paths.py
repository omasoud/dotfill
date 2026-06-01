"""Tests for platform file-browser opening helpers."""

from __future__ import annotations

from pathlib import Path

from dotfill import open_paths


def test_open_directory_creates_only_directory(
    monkeypatch, tmp_path: Path
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(open_paths, "_open_with_subprocess", calls.append)

    target = tmp_path / "config-dir"

    open_paths.open_directory(target, create=True, platform="linux")

    assert target.is_dir()
    assert not (target / "config_common.toml").exists()
    assert not (target / "config.toml").exists()
    assert calls == [["xdg-open", str(target)]]


def test_open_directory_windows_uses_explorer(
    monkeypatch, tmp_path: Path
) -> None:
    calls: list[list[str]] = []
    unlocks: list[bool] = []
    monkeypatch.setattr(open_paths, "_open_with_subprocess", calls.append)
    monkeypatch.setattr(open_paths, "_unlock_windows_foreground", lambda: unlocks.append(True))

    target = tmp_path / "config-dir"
    target.mkdir()

    open_paths.open_directory(target, platform="win32")

    assert unlocks == [True]
    assert calls == [["explorer", str(target)]]


def test_open_env_location_windows_selects_existing_file(
    monkeypatch, tmp_path: Path
) -> None:
    selected: list[Path] = []
    calls: list[list[str]] = []
    unlocks: list[bool] = []
    monkeypatch.setattr(open_paths, "_open_windows_select", selected.append)
    monkeypatch.setattr(open_paths, "_open_with_subprocess", calls.append)
    monkeypatch.setattr(open_paths, "_unlock_windows_foreground", lambda: unlocks.append(True))

    target = tmp_path / ".env"
    target.write_text("", encoding="utf-8")

    open_paths.open_env_location(target, platform="win32")

    assert unlocks == [True]
    assert selected == [target]
    assert calls == []


def test_open_env_location_windows_opens_parent_when_missing(
    monkeypatch, tmp_path: Path
) -> None:
    selected: list[Path] = []
    calls: list[list[str]] = []
    monkeypatch.setattr(open_paths, "_open_windows_select", selected.append)
    monkeypatch.setattr(open_paths, "_open_with_subprocess", calls.append)
    monkeypatch.setattr(open_paths, "_unlock_windows_foreground", lambda: None)

    target = tmp_path / ".env"

    open_paths.open_env_location(target, platform="win32")

    assert selected == []
    assert calls == [["explorer", str(tmp_path)]]


def test_open_env_location_macos_reveals_existing_file(
    monkeypatch, tmp_path: Path
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(open_paths, "_open_with_subprocess", calls.append)

    target = tmp_path / ".env"
    target.write_text("", encoding="utf-8")

    open_paths.open_env_location(target, platform="darwin")

    assert calls == [["open", "-R", str(target)]]


def test_open_env_location_linux_opens_parent(
    monkeypatch, tmp_path: Path
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(open_paths, "_open_with_subprocess", calls.append)

    target = tmp_path / ".env"
    target.write_text("", encoding="utf-8")

    open_paths.open_env_location(target, platform="linux")

    assert calls == [["xdg-open", str(tmp_path)]]
