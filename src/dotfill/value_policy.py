"""Display and comparison helpers for configured values."""

from __future__ import annotations

from .config_models import CompareMode, DisplayMode


def mask_value(value: str) -> str:
    """Return dotfill's standard masked representation for a configured value."""
    if len(value) <= 4:
        return "••••"
    return "••••••••" + value[-4:]


def display_value(value: str | None, display: DisplayMode) -> str | None:
    """Return the value that may leave the backend boundary."""
    if value is None or value == "" or display == "plain":
        return value
    return mask_value(value)


def values_equal(left: str, right: str, compare: CompareMode) -> bool:
    """Compare configured values according to a config definition."""
    if compare == "casefold":
        return left.casefold() == right.casefold()
    return left == right
