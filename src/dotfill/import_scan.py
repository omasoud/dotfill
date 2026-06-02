"""Import-from-file scanning and mapping proposal."""

from __future__ import annotations

import secrets
from pathlib import Path

from pydantic import SecretStr

from .config_models import EffectiveConfig
from .envdoc import EnvDocument
from .errors import ImportScanError
from .models import (
    ImportMappingRow,
    ImportScanSession,
)
from .value_policy import mask_value, values_equal


def _mask_value(value: str) -> str:
    return mask_value(value)


def _target_values_equal(
    target_key: str,
    current_value: str,
    candidate_value: str,
    config: EffectiveConfig | None,
) -> bool:
    if config is None or target_key not in config.derived_variables:
        return current_value == candidate_value
    return values_equal(
        current_value,
        candidate_value,
        config.derived_variables[target_key].compare,
    )


def scan_source_text(
    *,
    source_label: str,
    source_text: str,
    current_doc: EnvDocument,
    config: EffectiveConfig,
) -> ImportScanSession:
    """Parse a source .env-like text and propose mappings.

    The returned session holds raw source values backend-side; only masked
    values and target proposals are intended for the wire.
    """
    try:
        source_doc = EnvDocument.from_text(source_text)
    except Exception as exc:  # noqa: BLE001
        raise ImportScanError(f"Failed to parse source: {exc}") from exc

    import_targets = {service.token_var for service in config.services.values()} | set(
        config.derived_variables
    )
    identities = set(config.identities)
    candidates: dict[str, SecretStr] = {}
    rows: list[ImportMappingRow] = []

    for key in source_doc.keys():
        if key in identities:
            # Primary identity vars are never written by dotfill.
            continue
        value = source_doc.get(key)
        if value is None or value == "":
            continue
        candidates[key] = SecretStr(value)

        # Decide target + kind.
        if key in import_targets:
            target = key
            kind: str = "exact"
            locked = False
        elif key in config.import_aliases and config.import_aliases[key].target_key in import_targets:
            target = config.import_aliases[key].target_key
            kind = "heuristic"
            locked = False
        else:
            target = None
            kind = "none"
            locked = False

        # Status based on diff against current_doc.
        if target is None:
            status = "unmapped"
        else:
            current_value = current_doc.get(target)
            if current_value is None:
                status = "new"
            elif _target_values_equal(target, current_value, value, config):
                status = "no_change"
            else:
                status = "replace"

        rows.append(
            ImportMappingRow(
                source_key=key,
                target_key=target,
                mapping_kind=kind,  # type: ignore[arg-type]
                locked=locked,
                status=status,  # type: ignore[arg-type]
                masked_source_value=_mask_value(value),
            )
        )

    scan_id = secrets.token_urlsafe(16)

    # Compute which import targets currently have non-empty values in .env.
    occupied_targets = sorted(
        t for t in import_targets if current_doc.has_non_empty(t)
    )

    return ImportScanSession(
        scan_id=scan_id,
        source_label=source_label,
        candidates=candidates,
        proposed_rows=rows,
        occupied_targets=occupied_targets,
    )


def scan_source_path(
    path: Path, current_doc: EnvDocument, config: EffectiveConfig
) -> ImportScanSession:
    if not path.exists():
        raise ImportScanError(f"Source path does not exist: {path}")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ImportScanError(f"Failed to read {path}: {exc}") from exc
    return scan_source_text(
        source_label=str(path),
        source_text=text,
        current_doc=current_doc,
        config=config,
    )


def build_updates_from_choices(
    scan: ImportScanSession,
    choices: list[tuple[str, str | None]],
    *,
    allowed_targets: set[str] | None = None,
    current_doc: EnvDocument | None = None,
    config: EffectiveConfig | None = None,
) -> dict[str, str]:
    """Materialize {target_var: raw_value} from user-chosen mappings.

    `choices` is a list of (source_key, target_key_or_None). Skipped entries
    contribute nothing. Raises ImportScanError if a source_key is unknown.
    When current_doc is provided, scan-time statuses are recomputed and
    no-change rows are skipped.
    """
    updates: dict[str, str] = {}
    selected_targets: set[str] = set()
    for source_key, target_key in choices:
        if target_key is None:
            continue
        if source_key not in scan.candidates:
            raise ImportScanError(f"Unknown source key in scan: {source_key}")
        if allowed_targets is not None and target_key not in allowed_targets:
            raise ImportScanError(f"Invalid import target: {target_key}")
        if target_key in selected_targets:
            raise ImportScanError(
                f"Import target {target_key} was selected more than once."
            )
        selected_targets.add(target_key)
        value = scan.candidates[source_key].get_secret_value()
        if current_doc is not None:
            current_value = current_doc.get(target_key)
            if current_value is not None and _target_values_equal(
                target_key,
                current_value,
                value,
                config,
            ):
                continue
        updates[target_key] = value
    return updates
