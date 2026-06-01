"""Tests for generic config helper functions."""

from __future__ import annotations

import pytest

from dotfill.config import collect_managed_variable_names, resolve_url_template
from dotfill.config_loader import build_effective_config
from dotfill.errors import UnresolvedIdentityError, UrlTemplateError


def _effective_config():
    return build_effective_config(
        {
            "identities": {
                "WORK_EMAIL": {"source": "literal", "value": "user@example.com"},
                "WORK_USER": {"source": "local_part", "from": "WORK_EMAIL"},
            },
            "derived": {
                "WORK_USERNAME": {"from_identity": "WORK_EMAIL"},
            },
            "services": {
                "EXAMPLE": {
                    "display_name": "Example",
                    "token_var": "EXAMPLE_TOKEN",
                    "token_url": "https://example.com/{WORK_USER}/tokens",
                    "test_url": "https://example.com/me",
                }
            },
        }
    )


def test_resolve_url_template_substitutes_dynamic_identity() -> None:
    url = resolve_url_template(
        "https://x/{WORK_EMAIL}/tokens",
        {"WORK_EMAIL": "user@example.com"},
    )

    assert url == "https://x/user@example.com/tokens"


def test_resolve_url_template_unknown_placeholder_raises() -> None:
    with pytest.raises(UrlTemplateError):
        resolve_url_template("https://x/{NOT_A_VAR}", {"WORK_EMAIL": "x"})


def test_resolve_url_template_missing_value_raises() -> None:
    with pytest.raises(UnresolvedIdentityError):
        resolve_url_template("https://x/{WORK_EMAIL}", {"WORK_EMAIL": None})


def test_collect_managed_variable_names_uses_toml_config_only() -> None:
    cfg = _effective_config()

    managed = collect_managed_variable_names(cfg)

    assert managed == {"WORK_EMAIL", "WORK_USER", "WORK_USERNAME", "EXAMPLE_TOKEN"}


def test_plain_generic_config_has_no_managed_names() -> None:
    cfg = build_effective_config({})

    assert collect_managed_variable_names(cfg) == set()
