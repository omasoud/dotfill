"""Deterministic TOML config merge semantics."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from .errors import ConfigMergeError


def _merge_dict(
    base: dict[str, Any],
    overlay: Mapping[str, Any],
    *,
    path: str,
) -> dict[str, Any]:
    out = deepcopy(base)
    for key, value in overlay.items():
        existing = out.get(key)
        current_path = f"{path}.{key}" if path else key
        if isinstance(existing, dict) and isinstance(value, Mapping):
            out[key] = _merge_dict(existing, value, path=current_path)
        elif isinstance(value, Mapping):
            out[key] = _merge_dict({}, value, path=current_path)
        elif isinstance(value, list):
            raise ConfigMergeError(
                f"{current_path}: arrays are not supported in dotfill config"
            )
        else:
            out[key] = value
    return out


def merge_config_layers(layers: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Merge config layers in order, with later values overriding earlier ones."""
    merged: dict[str, Any] = {}
    for layer in layers:
        merged = _merge_dict(merged, layer, path="")
    return merged
