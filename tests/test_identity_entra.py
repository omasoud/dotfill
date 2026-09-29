"""Tests for the Entra (Microsoft Graph) identity detector."""

from __future__ import annotations

import logging
import re
import subprocess

import pytest

from dotfill import identity_entra
from dotfill.config_models import EntraDetectorConfig
from dotfill.identity_entra import (
    BUILTIN_CLIENT_ID,
    build_helper_script,
    detect_entra,
    parse_helper_output,
)

_FAKE_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.eyJzY3AiOiJVc2VyLlJlYWQifQ.c2lnbmF0dXJl"


def test_builtin_client_uses_resource_form_without_scope() -> None:
    script = build_helper_script(EntraDetectorConfig(enabled=True))

    assert f"::new($provider, '', '{BUILTIN_CLIENT_ID}')" in script
    assert "@('resource', 'https://graph.microsoft.com')" in script
    assert "FindAccountProviderAsync('https://login.microsoft.com', 'organizations')" in script


def test_configured_client_uses_user_read_with_resource() -> None:
    client_id = "00000000-0000-0000-0000-00000000abcd"

    script = build_helper_script(EntraDetectorConfig(enabled=True, client_id=client_id))

    assert f"::new($provider, 'User.Read', '{client_id}')" in script
    assert "@('resource', 'https://graph.microsoft.com')" in script
    assert BUILTIN_CLIENT_ID not in script


def test_tenant_selects_authority() -> None:
    tenant = "11111111-2222-3333-4444-555555555555"

    script = build_helper_script(EntraDetectorConfig(enabled=True, tenant=tenant))

    assert f"'https://login.microsoftonline.com/{tenant}'" in script


@pytest.mark.parametrize(
    "settings",
    [
        EntraDetectorConfig(client_id="not-a-guid'; Write-Output x"),
        EntraDetectorConfig(tenant="bad tenant'; x"),
    ],
)
def test_unsafe_settings_are_rejected_before_interpolation(
    settings: EntraDetectorConfig,
) -> None:
    with pytest.raises(ValueError):
        build_helper_script(settings)


def test_helper_is_silent_only_with_a_single_request_form() -> None:
    script = build_helper_script(EntraDetectorConfig(enabled=True))

    assert "RequestTokenAsync" not in script
    assert script.count("GetTokenSilentlyAsync") == 1
    assert script.count("WebTokenRequest]::new(") == 1
    assert "AADSTS65002" in script
    assert "Fail 'client_not_authorized'" in script


def test_helper_never_outputs_the_token() -> None:
    script = build_helper_script(EntraDetectorConfig(enabled=True))

    output_lines = [line for line in script.splitlines() if "Write-Output" in line]
    assert output_lines
    assert all("$token" not in line for line in output_lines)
    token_uses = [line.strip() for line in script.splitlines() if "$token" in line]
    assert token_uses == [
        "$token = $result.ResponseData[0].Token",
        (
            "$me = Invoke-RestMethod -Uri 'https://graph.microsoft.com/v1.0/me?$select="
            "mail,userPrincipalName,proxyAddresses' -Headers @{ Authorization = "
            "('Bearer ' + $token) } -TimeoutSec 10"
        ),
        "$token = $null",
        "$token = $null",
    ]
    assert "smtp:" in script


def test_parse_success_keeps_smtp_addresses_and_is_complete() -> None:
    result = parse_helper_output(
        "MAIL:Person@Example.com\n"
        "UPN:login@example.org\n"
        "PROXY:person@example.com\n"
        "PROXY:alias@other.example\n"
        "GRAPH:ok\n"
    )

    assert result.detector == "entra"
    assert result.outcome == "complete"
    assert result.facts.emails == [
        "person@example.com",
        "login@example.org",
        "alias@other.example",
    ]
    assert result.facts.diagnostics == []


def test_parse_ignores_unknown_and_token_like_lines() -> None:
    result = parse_helper_output(f"{_FAKE_TOKEN}\nnoise\nMAIL:a@example.com\nGRAPH:ok\n")

    assert result.outcome == "complete"
    assert result.facts.emails == ["a@example.com"]
    assert _FAKE_TOKEN not in repr(result)


@pytest.mark.parametrize(
    ("output", "diagnostic"),
    [
        ("ERR:interaction_required", "entra: sign-in interaction required"),
        ("ERR:client_not_authorized", "entra: client not authorized for Microsoft Graph"),
        ("ERR:no_account_provider", "entra: no work or school account available"),
        ("ERR:winrt_unavailable", "entra: Windows sign-in broker unavailable"),
        ("ERR:token_failed:ProviderError", "entra: token request failed (ProviderError)"),
        ("ERR:graph_failed:403", "entra: Microsoft Graph request failed (403)"),
        ("ERR:graph_failed:has spaces and stuff", "entra: Microsoft Graph request failed"),
        ("ERR:something_new", "entra: lookup failed"),
        ("", "entra: lookup returned no result"),
    ],
)
def test_parse_failures_map_to_short_diagnostics(output: str, diagnostic: str) -> None:
    result = parse_helper_output(output)

    assert result.outcome == "failed"
    assert result.facts.emails == []
    assert result.facts.diagnostics == [diagnostic]


def test_error_line_wins_over_success_marker() -> None:
    result = parse_helper_output("MAIL:a@example.com\nERR:graph_failed:500\nGRAPH:ok\n")

    assert result.outcome == "failed"


def test_detect_entra_unavailable_off_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(identity_entra.sys, "platform", "linux")

    result = detect_entra(EntraDetectorConfig(enabled=True))

    assert result.outcome == "failed"
    assert result.facts.diagnostics == ["entra: unavailable on this platform"]


def test_detect_entra_timeout_is_short_diagnostic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(identity_entra.sys, "platform", "win32")

    def timeout(_script: str) -> str:
        raise subprocess.TimeoutExpired(cmd=["powershell.exe", "-EncodedCommand", "x"], timeout=20)

    monkeypatch.setattr(identity_entra, "_run_helper", timeout)

    result = detect_entra(EntraDetectorConfig(enabled=True))

    assert result.facts.diagnostics == ["entra: lookup timed out after 20s"]


def test_detect_entra_missing_powershell(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(identity_entra.sys, "platform", "win32")

    def missing(_script: str) -> str:
        raise FileNotFoundError("powershell.exe")

    monkeypatch.setattr(identity_entra, "_run_helper", missing)

    result = detect_entra(EntraDetectorConfig(enabled=True))

    assert result.facts.diagnostics == ["entra: Windows PowerShell unavailable"]


def test_detect_entra_success_keeps_token_out_of_logs(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(identity_entra.sys, "platform", "win32")
    monkeypatch.setattr(
        identity_entra,
        "_run_helper",
        lambda _script: f"{_FAKE_TOKEN}\nMAIL:user@example.com\nGRAPH:ok\n",
    )

    with caplog.at_level(logging.DEBUG):
        result = detect_entra(EntraDetectorConfig(enabled=True))

    assert result.outcome == "complete"
    assert result.facts.emails == ["user@example.com"]
    assert _FAKE_TOKEN not in caplog.text
    assert not re.search(r"eyJ[A-Za-z0-9_-]+\.", caplog.text)


def test_run_helper_uses_encoded_windows_powershell(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(args, 0, stdout="GRAPH:ok\n", stderr="")

    monkeypatch.setattr(identity_entra, "_windows_powershell", lambda: "powershell.exe")
    monkeypatch.setattr(identity_entra.subprocess, "run", fake_run)

    out = identity_entra._run_helper("Write-Output 'x'")

    args = captured["args"]
    assert isinstance(args, list)
    assert args[:4] == ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand"]
    assert captured["kwargs"]["timeout"] == identity_entra.ENTRA_TIMEOUT_SECONDS
    assert out == "GRAPH:ok\n"
