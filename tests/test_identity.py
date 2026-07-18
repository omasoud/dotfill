"""Tests for generic identity detection helpers."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from dotfill.identity import (
    _RawProbe,
    _build_probe_script,
    _search_domain_hint,
    detect_ad_facts,
    resolve_primary_identity,
)


def test_detect_ad_facts_collects_generic_probe_fields() -> None:
    fake_probe = _RawProbe(
        sam="jdoe",
        domain="CORP",
        mail="John.Doe@example.com",
        upn="jdoe@corp.example.com",
        proxy_addresses=[
            "john.doe@example.com",
            "j.doe@service.example.com",
        ],
        errors=[],
    )

    with patch("dotfill.identity._run_powershell_probe", return_value=fake_probe):
        result = detect_ad_facts()

    assert result.sam == "jdoe"
    assert result.domain == "CORP"
    assert result.mail == "John.Doe@example.com"
    assert result.user_principal_name == "jdoe@corp.example.com"
    assert result.proxy_addresses == [
        "john.doe@example.com",
        "j.doe@service.example.com",
    ]
    assert result.emails == [
        "john.doe@example.com",
        "jdoe@corp.example.com",
        "j.doe@service.example.com",
    ]


def test_detect_ad_facts_allows_missing_email_fields() -> None:
    fake_probe = _RawProbe(sam="jdoe", domain="CORP", errors=[])

    with patch("dotfill.identity._run_powershell_probe", return_value=fake_probe):
        result = detect_ad_facts()

    assert result.sam == "jdoe"
    assert result.domain == "CORP"
    assert result.emails == []


def test_detect_ad_facts_preserves_diagnostics() -> None:
    fake_probe = _RawProbe(errors=["probe failed"])

    with patch("dotfill.identity._run_powershell_probe", return_value=fake_probe):
        result = detect_ad_facts()

    assert result.diagnostics == ["probe failed"]


def test_resolve_primary_identity_diverged() -> None:
    value, source = resolve_primary_identity(
        name="WORK_EMAIL", detected="det@example.com", explicit="exp@example.com"
    )
    assert value == "exp@example.com"
    assert source == "diverged"


def test_resolve_primary_identity_aligned() -> None:
    value, source = resolve_primary_identity(
        name="WORK_EMAIL", detected="same@example.com", explicit="same@example.com"
    )
    assert value == "same@example.com"
    assert source == "aligned"


def test_resolve_primary_identity_casefold_aligned_preserves_explicit() -> None:
    value, source = resolve_primary_identity(
        name="WORK_EMAIL",
        detected="same@example.com",
        explicit="Same@Example.com",
        compare="casefold",
    )
    assert value == "Same@Example.com"
    assert source == "aligned"


def test_resolve_primary_identity_detected_fallback() -> None:
    value, source = resolve_primary_identity(
        name="WORK_EMAIL", detected="det@example.com", explicit=None
    )
    assert value == "det@example.com"
    assert source == "detected"


def test_resolve_primary_identity_detected_when_explicit_empty() -> None:
    value, source = resolve_primary_identity(
        name="WORK_EMAIL", detected="det@example.com", explicit=""
    )
    assert value == "det@example.com"
    assert source == "detected"


def test_resolve_primary_identity_explicit_without_detected() -> None:
    value, source = resolve_primary_identity(
        name="WORK_EMAIL", detected=None, explicit="user@example.com"
    )
    assert value == "user@example.com"
    assert source == "aligned"


def test_resolve_primary_identity_unresolved() -> None:
    value, source = resolve_primary_identity(
        name="WORK_EMAIL", detected=None, explicit=None
    )
    assert value is None
    assert source == "unresolved"


def test_search_domain_hint_returns_trimmed_valid_user_domain() -> None:
    assert _search_domain_hint({"USERDNSDOMAIN": "  corp.example.com  "}) == (
        "corp.example.com"
    )


def test_search_domain_hint_missing_returns_empty() -> None:
    assert _search_domain_hint({}) == ""
    assert _search_domain_hint({"USERDNSDOMAIN": ""}) == ""


@pytest.mark.parametrize(
    "value",
    [
        "corp.example.com'; Write-Output unsafe",
        "corp example.com",
        ".corp.example.com",
        "corp..example.com",
        "-corp.example.com",
        "corp.example.com-",
    ],
)
def test_search_domain_hint_rejects_unsafe_or_invalid_values(value: str) -> None:
    assert _search_domain_hint({"USERDNSDOMAIN": value}) == ""


def test_build_probe_script_uses_explicit_domain_root_before_serverless() -> None:
    script = _build_probe_script("corp.example.com")

    assert "$dnsDomain = 'corp.example.com'" in script
    assert 'DirectoryEntry("LDAP://$Root")' in script
    assert "$explicitSearchCompleted = $true" in script
    assert "if (-not $explicitSearchCompleted)" in script
    assert "__DOMAIN_HINT__" not in script


def test_build_probe_script_without_hint_uses_validated_upn_fallback() -> None:
    script = _build_probe_script("")

    assert "$dnsDomain = ''" in script
    assert "whoami /upn" in script
    assert "Test-DnsDomain" in script
    assert "__DOMAIN_HINT__" not in script


def test_build_probe_script_does_not_interpolate_unsafe_hint() -> None:
    unsafe = "corp.example.com'; Write-Output unsafe"

    script = _build_probe_script(unsafe)

    assert unsafe not in script
    assert "$dnsDomain = ''" in script
