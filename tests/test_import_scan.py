"""Tests for import_scan with TOML-backed generic config."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import SecretStr

from dotfill.config_loader import build_effective_config
from dotfill.envdoc import EnvDocument
from dotfill.errors import ImportScanError
from dotfill.import_scan import (
    build_updates_from_choices,
    scan_source_path,
    scan_source_text,
)


def _config():
    return build_effective_config(
        {
            "identities": {
                "WORK_EMAIL": {"source": "literal", "value": "user@example.com"},
            },
            "derived": {
                "WORK_USERNAME": {"from_identity": "WORK_EMAIL"},
            },
            "services": {
                "EXAMPLE": {
                    "display_name": "Example",
                    "token_var": "EXAMPLE_TOKEN",
                    "token_url": "https://example.com/token",
                    "test_url": "https://example.com/me",
                }
            },
            "import_aliases": {
                "OLD_EXAMPLE_TOKEN": {"target": "EXAMPLE_TOKEN"},
            },
        }
    )


def _casefold_derived_config():
    return build_effective_config(
        {
            "identities": {
                "WORK_EMAIL": {"source": "literal", "value": "user@example.com"},
            },
            "derived": {
                "WORK_USERNAME": {
                    "from_identity": "WORK_EMAIL",
                    "compare": "casefold",
                },
            },
            "services": {
                "EXAMPLE": {
                    "display_name": "Example",
                    "token_var": "EXAMPLE_TOKEN",
                    "token_url": "https://example.com/token",
                    "test_url": "https://example.com/me",
                }
            },
        }
    )


def _empty_state(tmp_path: Path) -> tuple[EnvDocument, object]:
    env = tmp_path / ".env"
    env.write_text("", encoding="utf-8")
    return EnvDocument.from_path(env), _config()


def test_scan_exact_match(tmp_path: Path) -> None:
    doc, cfg = _empty_state(tmp_path)
    scan = scan_source_text(
        source_label="src",
        source_text="EXAMPLE_TOKEN=abcdefghij\n",
        current_doc=doc,
        config=cfg,
    )

    rows = {r.source_key: r for r in scan.proposed_rows}
    assert rows["EXAMPLE_TOKEN"].target_key == "EXAMPLE_TOKEN"
    assert rows["EXAMPLE_TOKEN"].mapping_kind == "exact"
    assert rows["EXAMPLE_TOKEN"].status == "new"
    assert rows["EXAMPLE_TOKEN"].masked_source_value == "••••••••ghij"
    assert isinstance(scan.candidates["EXAMPLE_TOKEN"], SecretStr)
    assert scan.candidates["EXAMPLE_TOKEN"].get_secret_value() == "abcdefghij"
    assert "abcdefghij" not in repr(scan.candidates["EXAMPLE_TOKEN"])


def test_scan_configured_alias(tmp_path: Path) -> None:
    doc, cfg = _empty_state(tmp_path)
    scan = scan_source_text(
        source_label="src",
        source_text="OLD_EXAMPLE_TOKEN=tokvalue1234\n",
        current_doc=doc,
        config=cfg,
    )

    rows = {r.source_key: r for r in scan.proposed_rows}
    assert rows["OLD_EXAMPLE_TOKEN"].target_key == "EXAMPLE_TOKEN"
    assert rows["OLD_EXAMPLE_TOKEN"].mapping_kind == "heuristic"


def test_scan_unmapped(tmp_path: Path) -> None:
    doc, cfg = _empty_state(tmp_path)
    scan = scan_source_text(
        source_label="src",
        source_text="WEIRD_THING=hello\n",
        current_doc=doc,
        config=cfg,
    )

    rows = {r.source_key: r for r in scan.proposed_rows}
    assert rows["WEIRD_THING"].target_key is None
    assert rows["WEIRD_THING"].mapping_kind == "none"
    assert rows["WEIRD_THING"].status == "unmapped"


def test_scan_skips_empty_source_values(tmp_path: Path) -> None:
    doc, cfg = _empty_state(tmp_path)
    scan = scan_source_text(
        source_label="src",
        source_text="EXAMPLE_TOKEN=\nOLD_EXAMPLE_TOKEN=tokvalue1234\n",
        current_doc=doc,
        config=cfg,
    )

    source_keys = {row.source_key for row in scan.proposed_rows}
    assert "EXAMPLE_TOKEN" not in source_keys
    assert "EXAMPLE_TOKEN" not in scan.candidates
    assert "OLD_EXAMPLE_TOKEN" in source_keys


def test_scan_no_change_and_replace(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("EXAMPLE_TOKEN=same\nWORK_USERNAME=oldvalue\n", encoding="utf-8")
    doc = EnvDocument.from_path(env)
    scan = scan_source_text(
        source_label="src",
        source_text="EXAMPLE_TOKEN=same\nWORK_USERNAME=newvalue\n",
        current_doc=doc,
        config=_config(),
    )

    rows = {r.source_key: r for r in scan.proposed_rows}
    assert rows["EXAMPLE_TOKEN"].status == "no_change"
    assert rows["WORK_USERNAME"].status == "replace"


def test_scan_uses_casefold_compare_for_derived_no_change(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "EXAMPLE_TOKEN=TokenValue\nWORK_USERNAME=User@Example.com\n",
        encoding="utf-8",
    )
    doc = EnvDocument.from_path(env)
    scan = scan_source_text(
        source_label="src",
        source_text="EXAMPLE_TOKEN=tokenvalue\nWORK_USERNAME=user@example.com\n",
        current_doc=doc,
        config=_casefold_derived_config(),
    )

    rows = {r.source_key: r for r in scan.proposed_rows}
    assert rows["EXAMPLE_TOKEN"].status == "replace"
    assert rows["WORK_USERNAME"].status == "no_change"


def test_scan_skips_configured_identity_but_not_old_meta(tmp_path: Path) -> None:
    doc, cfg = _empty_state(tmp_path)
    scan = scan_source_text(
        source_label="src",
        source_text=(
            "LEGACY_ENV_CONFIG_SERVICE=A|u|t|n\n"
            "WORK_EMAIL=other@example.com\n"
            "EXAMPLE_TOKEN=xyz\n"
        ),
        current_doc=doc,
        config=cfg,
    )

    source_keys = {r.source_key for r in scan.proposed_rows}
    assert "WORK_EMAIL" not in source_keys
    assert "LEGACY_ENV_CONFIG_SERVICE" in source_keys
    assert "EXAMPLE_TOKEN" in source_keys


def test_scan_path_missing_raises(tmp_path: Path) -> None:
    doc, cfg = _empty_state(tmp_path)
    with pytest.raises(ImportScanError):
        scan_source_path(tmp_path / "absent.env", doc, cfg)


def test_build_updates_from_choices_filters_skips(tmp_path: Path) -> None:
    doc, cfg = _empty_state(tmp_path)
    scan = scan_source_text(
        source_label="src",
        source_text="EXAMPLE_TOKEN=abc\nWEIRD=zzz\n",
        current_doc=doc,
        config=cfg,
    )

    updates = build_updates_from_choices(
        scan,
        [
            ("EXAMPLE_TOKEN", "EXAMPLE_TOKEN"),
            ("WEIRD", None),
        ],
        allowed_targets={"EXAMPLE_TOKEN"},
    )

    assert updates == {"EXAMPLE_TOKEN": "abc"}


def test_build_updates_recomputes_no_change_at_commit_time(tmp_path: Path) -> None:
    doc, cfg = _empty_state(tmp_path)
    scan = scan_source_text(
        source_label="src",
        source_text="EXAMPLE_TOKEN=abc\nWORK_USERNAME=user@example.com\n",
        current_doc=doc,
        config=cfg,
    )
    latest_env = tmp_path / ".env"
    latest_env.write_text(
        "EXAMPLE_TOKEN=abc\nWORK_USERNAME=old@example.com\n",
        encoding="utf-8",
    )
    latest_doc = EnvDocument.from_path(latest_env)

    updates = build_updates_from_choices(
        scan,
        [
            ("EXAMPLE_TOKEN", "EXAMPLE_TOKEN"),
            ("WORK_USERNAME", "WORK_USERNAME"),
        ],
        allowed_targets={"EXAMPLE_TOKEN", "WORK_USERNAME"},
        current_doc=latest_doc,
    )

    assert updates == {"WORK_USERNAME": "user@example.com"}


def test_build_updates_uses_casefold_compare_for_derived_no_change(
    tmp_path: Path,
) -> None:
    cfg = _casefold_derived_config()
    env = tmp_path / ".env"
    env.write_text("", encoding="utf-8")
    doc = EnvDocument.from_path(env)
    scan = scan_source_text(
        source_label="src",
        source_text="EXAMPLE_TOKEN=tokenvalue\nWORK_USERNAME=user@example.com\n",
        current_doc=doc,
        config=cfg,
    )
    latest_env = tmp_path / "latest.env"
    latest_env.write_text(
        "EXAMPLE_TOKEN=TokenValue\nWORK_USERNAME=User@Example.com\n",
        encoding="utf-8",
    )
    latest_doc = EnvDocument.from_path(latest_env)

    updates = build_updates_from_choices(
        scan,
        [
            ("EXAMPLE_TOKEN", "EXAMPLE_TOKEN"),
            ("WORK_USERNAME", "WORK_USERNAME"),
        ],
        allowed_targets={"EXAMPLE_TOKEN", "WORK_USERNAME"},
        current_doc=latest_doc,
        config=cfg,
    )

    assert updates == {"EXAMPLE_TOKEN": "tokenvalue"}


def test_build_updates_rejects_invalid_target(tmp_path: Path) -> None:
    doc, cfg = _empty_state(tmp_path)
    scan = scan_source_text(
        source_label="src",
        source_text="SOMEVAR=value\n",
        current_doc=doc,
        config=cfg,
    )

    with pytest.raises(ImportScanError):
        build_updates_from_choices(
            scan,
            [("SOMEVAR", "WORK_EMAIL")],
            allowed_targets={"EXAMPLE_TOKEN"},
        )


def test_build_updates_rejects_duplicate_selected_targets(tmp_path: Path) -> None:
    doc, cfg = _empty_state(tmp_path)
    scan = scan_source_text(
        source_label="src",
        source_text="EXAMPLE_TOKEN=first\nOLD_EXAMPLE_TOKEN=second\n",
        current_doc=doc,
        config=cfg,
    )

    with pytest.raises(ImportScanError, match="selected more than once"):
        build_updates_from_choices(
            scan,
            [
                ("EXAMPLE_TOKEN", "EXAMPLE_TOKEN"),
                ("OLD_EXAMPLE_TOKEN", "EXAMPLE_TOKEN"),
            ],
            allowed_targets={"EXAMPLE_TOKEN"},
        )


def test_scan_returns_occupied_targets(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("EXAMPLE_TOKEN=existing\nWORK_USERNAME=\n", encoding="utf-8")
    doc = EnvDocument.from_path(env)
    scan = scan_source_text(
        source_label="src",
        source_text="UNKNOWN_VAR=foo\n",
        current_doc=doc,
        config=_config(),
    )

    assert "EXAMPLE_TOKEN" in scan.occupied_targets
    assert "WORK_USERNAME" not in scan.occupied_targets
