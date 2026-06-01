"""Cross-platform helpers for opening config and `.env` locations."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _open_with_subprocess(args: list[str]) -> None:
    subprocess.Popen(args)  # noqa: S603


def _unlock_windows_foreground() -> None:
    import ctypes

    # Simulate Alt key press/release to unlock Windows foreground focus.
    user32 = ctypes.windll.user32
    user32.keybd_event(0x12, 0, 0x0001, 0)  # Alt down
    user32.keybd_event(0x12, 0, 0x0003, 0)  # Alt up


def _open_windows_select(target: Path) -> None:
    import ctypes

    shell32 = ctypes.windll.shell32
    ole32 = ctypes.windll.ole32
    ole32.CoInitialize(None)
    pidl = ctypes.c_void_p()
    shell32.SHParseDisplayName(str(target), None, ctypes.byref(pidl), 0, None)
    if pidl:
        shell32.SHOpenFolderAndSelectItems(pidl, 0, None, 0)
        ole32.CoTaskMemFree(pidl)


def open_env_location(target: Path, *, platform: str | None = None) -> None:
    """Reveal an existing `.env` file, or open its parent directory."""
    platform_name = sys.platform if platform is None else platform
    if platform_name == "win32":
        _unlock_windows_foreground()
        if target.exists():
            _open_windows_select(target)
        else:
            _open_with_subprocess(["explorer", str(target.parent)])
    elif platform_name == "darwin":
        if target.exists():
            _open_with_subprocess(["open", "-R", str(target)])
        else:
            _open_with_subprocess(["open", str(target.parent)])
    else:
        _open_with_subprocess(["xdg-open", str(target.parent)])


def open_directory(
    directory: Path,
    *,
    create: bool = False,
    platform: str | None = None,
) -> None:
    """Open a directory in the platform file browser."""
    if create:
        directory.mkdir(parents=True, exist_ok=True)
    platform_name = sys.platform if platform is None else platform
    if platform_name == "win32":
        _unlock_windows_foreground()
        _open_with_subprocess(["explorer", str(directory)])
    elif platform_name == "darwin":
        _open_with_subprocess(["open", str(directory)])
    else:
        _open_with_subprocess(["xdg-open", str(directory)])
