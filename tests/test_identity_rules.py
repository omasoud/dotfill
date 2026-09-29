"""Tests for configured dynamic identity rule evaluation."""

from __future__ import annotations

import pytest

from dotfill.config_models import IdentityDefinition
from dotfill.errors import ConfigSchemaError
from dotfill.identity_facts import DetectorResult, IdentityFacts, make_identity_facts
from dotfill.identity_rules import evaluate_identity_rules


def _results(**facts_by_detector: IdentityFacts) -> dict[str, DetectorResult]:
    return {
        name: DetectorResult(detector=name, facts=facts, outcome="complete")
        for name, facts in facts_by_detector.items()
    }


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
    facts = make_identity_facts(
        mail="person@example.com",
        proxy_addresses=["smtp:person@other.example.com"],
    )

    result = evaluate_identity_rules(
        {
            "WORK_EMAIL": _identity(
                "WORK_EMAIL", "windows_ad.email_by_domain", domain="other.example.com"
            )
        },
        detector_results=_results(windows_ad=facts),
    )

    assert result["WORK_EMAIL"].value == "person@other.example.com"
    assert result["WORK_EMAIL"].detector == "windows_ad"


def test_windows_ad_sam_and_domain_sources() -> None:
    facts = make_identity_facts(sam="jdoe", domain="CORP")

    result = evaluate_identity_rules(
        {
            "WORK_SAM": _identity("WORK_SAM", "windows_ad.sam"),
            "WORK_DOMAIN": _identity("WORK_DOMAIN", "windows_ad.domain"),
        },
        detector_results=_results(windows_ad=facts),
    )

    assert result["WORK_SAM"].value == "jdoe"
    assert result["WORK_DOMAIN"].value == "CORP"


def test_windows_ad_failure_stays_diagnostic_without_match() -> None:
    facts = make_identity_facts(diagnostics=["PowerShell not found on PATH"])

    result = evaluate_identity_rules(
        {
            "WORK_EMAIL": _identity(
                "WORK_EMAIL", "windows_ad.email_by_domain", domain="example.com"
            )
        },
        detector_results=_results(windows_ad=facts),
    )

    assert result["WORK_EMAIL"].value is None
    assert result["WORK_EMAIL"].diagnostics == ["PowerShell not found on PATH"]


def test_entra_email_by_domain_reads_only_entra_facts() -> None:
    result = evaluate_identity_rules(
        {
            "CLOUD_EMAIL": _identity(
                "CLOUD_EMAIL", "entra.email_by_domain", domain="example.com"
            )
        },
        detector_results=_results(
            windows_ad=make_identity_facts(mail="ad@example.com"),
            entra=make_identity_facts(mail="cloud@example.com"),
        ),
    )

    assert result["CLOUD_EMAIL"].value == "cloud@example.com"
    assert result["CLOUD_EMAIL"].detector == "entra"


def test_neutral_email_by_domain_uses_priority_order() -> None:
    identities = {
        "WORK_EMAIL": _identity("WORK_EMAIL", "email_by_domain", domain="example.com"),
        "OTHER_EMAIL": _identity("OTHER_EMAIL", "email_by_domain", domain="other.example"),
    }
    results = _results(
        entra=make_identity_facts(mail="cloud@example.com"),
        windows_ad=make_identity_facts(
            mail="ad@example.com", proxy_addresses=["smtp:ad@other.example"]
        ),
    )

    result = evaluate_identity_rules(
        identities,
        detector_results=results,
        detector_order=["entra", "windows_ad"],
    )

    assert result["WORK_EMAIL"].value == "cloud@example.com"
    assert result["WORK_EMAIL"].detector == "entra"
    assert result["OTHER_EMAIL"].value == "ad@other.example"
    assert result["OTHER_EMAIL"].detector == "windows_ad"


def test_neutral_email_by_domain_reports_diagnostics_and_pending() -> None:
    result = evaluate_identity_rules(
        {"WORK_EMAIL": _identity("WORK_EMAIL", "email_by_domain", domain="example.com")},
        detector_results=_results(
            entra=make_identity_facts(diagnostics=["entra: sign-in interaction required"])
        ),
        detector_order=["entra", "windows_ad"],
        pending_detectors={"windows_ad"},
    )

    assert result["WORK_EMAIL"].value is None
    assert result["WORK_EMAIL"].detector is None
    assert result["WORK_EMAIL"].diagnostics == [
        "entra: sign-in interaction required",
        "windows_ad: detection pending",
    ]
