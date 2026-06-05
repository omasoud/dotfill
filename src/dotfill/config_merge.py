"""Deterministic TOML config merge semantics."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from .errors import ConfigMergeError


def _is_service_subtable_path(path: str, name: str) -> bool:
    return path.startswith("services.") and path.endswith(f".{name}")


def _merge_case_insensitive_headers(
    base: dict[str, Any],
    overlay: Mapping[str, Any],
    *,
    path: str,
) -> dict[str, Any]:
    out = deepcopy(base)
    lower_to_key = {str(key).casefold(): str(key) for key in out}
    seen_overlay: set[str] = set()
    for key, value in overlay.items():
        key_str = str(key)
        folded = key_str.casefold()
        current_path = f"{path}.{key_str}"
        if folded in seen_overlay:
            raise ConfigMergeError(f"{current_path}: duplicate header name")
        seen_overlay.add(folded)
        if isinstance(value, list):
            raise ConfigMergeError(
                f"{current_path}: arrays are not supported in dotfill config"
            )
        existing_key = lower_to_key.get(folded)
        if existing_key is not None and existing_key != key_str:
            out.pop(existing_key, None)
        out[key_str] = deepcopy(value)
        lower_to_key[folded] = key_str
    return out


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
            if _is_service_subtable_path(current_path, "auth"):
                out[key] = deepcopy(dict(value))
            elif _is_service_subtable_path(current_path, "test_headers"):
                out[key] = _merge_case_insensitive_headers(
                    existing,
                    value,
                    path=current_path,
                )
            else:
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
