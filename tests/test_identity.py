"""Tests for generic identity detection helpers."""

from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from dotfill.identity import (
    WINDOWS_AD_TIMEOUT_SECONDS,
    _RawProbe,
    _build_probe_script,
    _parse_probe_output,
    _run_powershell_probe,
    _search_domain_hint,
    _split_sam_compatible,
    detect_windows_ad,
    resolve_primary_identity,
)


def _detect(probe: _RawProbe, logon: tuple[str | None, str | None] = (None, None)):
    with (
        patch("dotfill.identity._run_powershell_probe", return_value=probe),
        patch("dotfill.identity._windows_logon_names", return_value=logon),
    ):
        return detect_windows_ad()


def test_detect_windows_ad_collects_generic_probe_fields() -> None:
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
        lookup_completed=True,
    )

    detected = _detect(fake_probe)
    result = detected.facts

    assert detected.detector == "windows_ad"
    assert detected.outcome == "complete"
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


def test_detect_windows_ad_allows_missing_email_fields() -> None:
    fake_probe = _RawProbe(sam="jdoe", domain="CORP", errors=[], lookup_completed=True)

    detected = _detect(fake_probe)

    assert detected.facts.sam == "jdoe"
    assert detected.facts.domain == "CORP"
    assert detected.facts.emails == []
    assert detected.outcome == "complete"


def test_detect_windows_ad_prefixes_diagnostics_and_fails_without_facts() -> None:
    detected = _detect(_RawProbe(errors=["probe failed"]))

    assert detected.facts.diagnostics == ["windows_ad: probe failed"]
    assert detected.outcome == "failed"


def test_detect_windows_ad_keeps_in_process_upn_when_lookup_fails() -> None:
    detected = _detect(
        _RawProbe(errors=["directory lookup timed out after 15s"]),
        logon=("CORP\\jdoe", "jdoe@example.com"),
    )

    assert detected.outcome == "partial"
    assert detected.facts.sam == "jdoe"
    assert detected.facts.domain == "CORP"
    assert detected.facts.user_principal_name == "jdoe@example.com"
    assert detected.facts.emails == ["jdoe@example.com"]
    assert detected.facts.diagnostics == [
        "windows_ad: directory lookup timed out after 15s"
    ]


def test_detect_windows_ad_prefers_directory_upn_over_local() -> None:
    detected = _detect(
        _RawProbe(upn="dir@example.com", errors=[], lookup_completed=True),
        logon=("CORP\\jdoe", "local@example.com"),
    )

    assert detected.facts.user_principal_name == "dir@example.com"


def test_parse_probe_output_marks_completed_lookup() -> None:
    completed = _parse_probe_output("SAM:jdoe\nDOMAIN:CORP\nMAIL:\n")
    failed = _parse_probe_output("SAM:jdoe\nMAIL:\nERR:serverless bind: failed\n")
    unfinished = _parse_probe_output("SAM:jdoe\nDOMAIN:CORP\n")

    assert completed.lookup_completed is True
    assert failed.lookup_completed is False
    assert unfinished.lookup_completed is False


def test_probe_timeout_diagnostic_omits_script_and_keeps_partial_output() -> None:
    script_marker = "Write-Output"

    def timeout(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(
            cmd=["powershell.exe", "-Command", f"{script_marker} secret-script"],
            timeout=WINDOWS_AD_TIMEOUT_SECONDS,
            output="SAM:jdoe\nDOMAIN:CORP\n",
        )

    with (
        patch("dotfill.identity.shutil.which", return_value="powershell.exe"),
        patch("dotfill.identity.subprocess.run", side_effect=timeout),
    ):
        probe = _run_powershell_probe()

    assert probe.sam == "jdoe"
    assert probe.domain == "CORP"
    assert probe.lookup_completed is False
    assert probe.errors == ["directory lookup timed out after 15s"]
    assert all(script_marker not in error for error in probe.errors or [])


def test_probe_nonzero_exit_omits_stderr() -> None:
    completed = subprocess.CompletedProcess(
        args=["powershell.exe"],
        returncode=1,
        stdout="SAM:jdoe\nMAIL:\n",
        stderr="At line:1 char:1 Write-Output secret-script",
    )

    with (
        patch("dotfill.identity.shutil.which", return_value="powershell.exe"),
        patch("dotfill.identity.subprocess.run", return_value=completed),
    ):
        probe = _run_powershell_probe()

    assert probe.errors == ["PowerShell exit code 1"]
    assert probe.lookup_completed is False


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("CORP\\jdoe", ("jdoe", "CORP")),
        ("jdoe", ("jdoe", None)),
        (None, (None, None)),
        ("", (None, None)),
    ],
)
def test_split_sam_compatible(
    value: str | None, expected: tuple[str | None, str | None]
) -> None:
    assert _split_sam_compatible(value) == expected


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
