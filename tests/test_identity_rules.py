"""Tests for configured dynamic identity rule evaluation."""

from __future__ import annotations

import pytest

from dotfill.config_models import IdentityDefinition
from dotfill.errors import ConfigSchemaError
from dotfill.identity_facts import make_ad_facts
from dotfill.identity_rules import evaluate_identity_rules


def _identity(
    identity_name: str,
    source: str,
    **params: object,
) -> IdentityDefinition:
    return IdentityDefinition(name=identity_name, source=source, params=params)


def test_literal_source() -> None:
    result = evaluate_identity_rules(
        {"WORK_EMAIL": _identity("WORK_EMAIL", "literal", value="user@example.com")}
    )

    assert result["WORK_EMAIL"].value == "user@example.com"


def test_env_source(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOTFILL_TEST_USER", "jdoe")

    result = evaluate_identity_rules(
        {"WORK_USER": _identity("WORK_USER", "env", name="DOTFILL_TEST_USER")}
    )

    assert result["WORK_USER"].value == "jdoe"


def test_local_part_dependency_resolution() -> None:
    result = evaluate_identity_rules(
        {
            "WORK_USER": _identity("WORK_USER", "local_part", **{"from": "WORK_EMAIL"}),
            "WORK_EMAIL": _identity(
                "WORK_EMAIL", "literal", value="person@example.com"
            ),
        }
    )

    assert result["WORK_USER"].value == "person"


def test_local_part_uses_explicit_upstream_identity_override() -> None:
    result = evaluate_identity_rules(
        {
            "WORK_EMAIL": _identity("WORK_EMAIL", "env", name="MISSING_WORK_EMAIL"),
            "WORK_USER": _identity("WORK_USER", "local_part", **{"from": "WORK_EMAIL"}),
        },
        environ={},
        explicit_values={"WORK_EMAIL": "manual@example.com"},
    )

    assert result["WORK_EMAIL"].value is None
    assert result["WORK_USER"].value == "manual"


def test_cycle_rejection() -> None:
    identities = {
        "A": _identity("A", "local_part", **{"from": "B"}),
        "B": _identity("B", "local_part", **{"from": "A"}),
    }

    with pytest.raises(ConfigSchemaError, match="cycle"):
        evaluate_identity_rules(identities)


def test_missing_reference_rejection() -> None:
    identities = {
        "A": _identity("A", "local_part", **{"from": "DISABLED_OR_MISSING"}),
    }

    with pytest.raises(ConfigSchemaError, match="unknown or disabled"):
        evaluate_identity_rules(identities)


def test_windows_ad_email_by_domain_source() -> None:
    facts = make_ad_facts(
        mail="person@example.com",
        proxy_addresses=["smtp:person@other.example.com"],
    )

    result = evaluate_identity_rules(
        {
            "WORK_EMAIL": _identity(
                "WORK_EMAIL", "windows_ad.email_by_domain", domain="other.example.com"
            )
        },
        ad_facts=facts,
    )

    assert result["WORK_EMAIL"].value == "person@other.example.com"


def test_windows_ad_sam_and_domain_sources() -> None:
    facts = make_ad_facts(sam="jdoe", domain="CORP")

    result = evaluate_identity_rules(
        {
            "WORK_SAM": _identity("WORK_SAM", "windows_ad.sam"),
            "WORK_DOMAIN": _identity("WORK_DOMAIN", "windows_ad.domain"),
        },
        ad_facts=facts,
    )

    assert result["WORK_SAM"].value == "jdoe"
    assert result["WORK_DOMAIN"].value == "CORP"


def test_windows_ad_failure_stays_diagnostic_without_match() -> None:
    facts = make_ad_facts(diagnostics=["PowerShell not found on PATH"])

    result = evaluate_identity_rules(
        {
            "WORK_EMAIL": _identity(
                "WORK_EMAIL", "windows_ad.email_by_domain", domain="example.com"
            )
        },
        ad_facts=facts,
    )

    assert result["WORK_EMAIL"].value is None
    assert result["WORK_EMAIL"].diagnostics == ["PowerShell not found on PATH"]
