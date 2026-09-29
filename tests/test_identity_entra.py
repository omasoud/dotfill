"""Tests for the Entra (Microsoft Graph) identity detector."""

from __future__ import annotations

import logging
import re
import subprocess
import sys
import threading
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
import respx

from dotfill import identity_entra
from dotfill.config_models import EntraDetectorConfig
from dotfill.identity_detectors import DetectionRequest, DetectorRunner, DetectorSpec
from dotfill.identity_entra import (
    BUILTIN_CLIENT_ID,
    GRAPH_ME_URL,
    detect_entra,
    entra_authority,
    entra_scopes,
    token_error_message,
)

_FAKE_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.eyJzY3AiOiJVc2VyLlJlYWQifQ.c2lnbmF0dXJl"
_CONFIGURED_ID = "00000000-0000-0000-0000-00000000abcd"


class RedirectUriError(ValueError):
    """Stand-in with the same name as `msal.broker.RedirectUriError`."""


class FakeApp:
    """Records `acquire_token_interactive` calls and returns a scripted result."""

    CONSOLE_WINDOW_HANDLE = object()

    def __init__(self, result: object = None, *, raises: BaseException | None = None) -> None:
        self.result = result if result is not None else {"access_token": _FAKE_TOKEN}
        self.raises = raises
        self.calls: list[dict[str, Any]] = []

    def acquire_token_interactive(self, scopes: list[str], **kwargs: Any) -> object:
        self.calls.append({"scopes": scopes, **kwargs})
        if self.raises is not None:
            raise self.raises
        return dict(self.result) if isinstance(self.result, dict) else self.result


@pytest.fixture
def on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(identity_entra, "_on_windows", lambda: True)


@pytest.fixture
def no_child_processes(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbid(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("the Entra detector must not start child processes")

    monkeypatch.setattr(subprocess, "run", forbid)
    monkeypatch.setattr(subprocess, "Popen", forbid)


def _use_app(monkeypatch: pytest.MonkeyPatch, app: FakeApp) -> list[tuple[str, str]]:
    created: list[tuple[str, str]] = []

    def create(client_id: str, authority: str) -> FakeApp:
        created.append((client_id, authority))
        return app

    monkeypatch.setattr(identity_entra, "_create_app", create)
    return created


def _graph_ok(payload: dict[str, object] | None = None) -> respx.Route:
    return respx.get(GRAPH_ME_URL).mock(
        return_value=httpx.Response(
            200,
            json=payload
            or {
                "mail": "Person@Example.com",
                "userPrincipalName": "login@example.org",
                "proxyAddresses": [
                    "SMTP:person@example.com",
                    "smtp:alias@other.example",
                    "X500:/o=example/ou=exchange/cn=recipients/cn=person",
                ],
            },
        )
    )


# ---- request construction -------------------------------------------------


def test_builtin_client_requests_graph_default_scope() -> None:
    settings = EntraDetectorConfig(enabled=True)

    assert entra_scopes(settings) == ["https://graph.microsoft.com/.default"]
    assert entra_authority(settings) == "https://login.microsoftonline.com/organizations"


def test_configured_client_requests_user_read() -> None:
    settings = EntraDetectorConfig(enabled=True, client_id=_CONFIGURED_ID, tenant="contoso.example.com")

    assert entra_scopes(settings) == ["User.Read"]
    assert entra_authority(settings) == "https://login.microsoftonline.com/contoso.example.com"


def test_msal_authority_requests_have_a_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    options: dict[str, Any] = {}

    def create(_client_id: str, **kwargs: Any) -> FakeApp:
        options.update(kwargs)
        return FakeApp()

    monkeypatch.setitem(sys.modules, "msal", SimpleNamespace(PublicClientApplication=create))
    identity_entra._create_app(BUILTIN_CLIENT_ID, entra_authority(EntraDetectorConfig()))

    assert options["enable_broker_on_windows"] is True
    assert 0 < options["timeout"] <= identity_entra.ENTRA_TIMEOUT_SECONDS


@respx.mock
def test_builtin_lookup_is_silent_only_in_process(
    monkeypatch: pytest.MonkeyPatch, on_windows: None, no_child_processes: None
) -> None:
    app = FakeApp()
    created = _use_app(monkeypatch, app)
    route = _graph_ok()

    result = detect_entra(EntraDetectorConfig(enabled=True))

    assert result.outcome == "complete"
    assert created == [(BUILTIN_CLIENT_ID, "https://login.microsoftonline.com/organizations")]
    assert len(app.calls) == 1
    call = app.calls[0]
    assert call["scopes"] == ["https://graph.microsoft.com/.default"]
    assert call["prompt"] == "none"
    assert call["parent_window_handle"] is FakeApp.CONSOLE_WINDOW_HANDLE
    with pytest.raises(Exception, match="browser"):
        call["on_before_launching_ui"](ui="browser")
    assert route.calls.last.request.headers["Authorization"] == f"Bearer {_FAKE_TOKEN}"


@respx.mock
def test_configured_client_lookup_uses_its_id_and_user_read(
    monkeypatch: pytest.MonkeyPatch, on_windows: None
) -> None:
    app = FakeApp()
    created = _use_app(monkeypatch, app)
    _graph_ok()

    detect_entra(EntraDetectorConfig(enabled=True, client_id=_CONFIGURED_ID))

    assert created[0][0] == _CONFIGURED_ID
    assert app.calls[0]["scopes"] == ["User.Read"]


def test_failed_token_request_is_not_retried_with_other_scopes(
    monkeypatch: pytest.MonkeyPatch, on_windows: None
) -> None:
    app = FakeApp(
        {
            "error": "broker_error",
            "error_description": "(pii). Status: Response_Status.Status_IncorrectConfiguration, "
            "Error code: 3399614466, Tag: 557973643",
        }
    )
    _use_app(monkeypatch, app)

    result = detect_entra(EntraDetectorConfig(enabled=True))

    assert len(app.calls) == 1
    assert result.facts.diagnostics == ["entra: client not authorized for Microsoft Graph"]


# ---- Graph response parsing ------------------------------------------------


@respx.mock
def test_success_keeps_smtp_addresses_only(monkeypatch: pytest.MonkeyPatch, on_windows: None) -> None:
    _use_app(monkeypatch, FakeApp())
    _graph_ok()

    result = detect_entra(EntraDetectorConfig(enabled=True))

    assert result.detector == "entra"
    assert result.outcome == "complete"
    assert result.facts.emails == [
        "person@example.com",
        "login@example.org",
        "alias@other.example",
    ]
    assert result.facts.diagnostics == []


@respx.mock
@pytest.mark.parametrize(
    ("response", "diagnostic"),
    [
        (httpx.Response(403), "entra: Microsoft Graph request failed (403)"),
        (httpx.Response(200, text="not json"), "entra: Microsoft Graph returned an invalid response"),
        (httpx.Response(200, json=["list"]), "entra: Microsoft Graph returned an invalid response"),
    ],
)
def test_graph_failures_map_to_short_diagnostics(
    monkeypatch: pytest.MonkeyPatch, on_windows: None, response: httpx.Response, diagnostic: str
) -> None:
    _use_app(monkeypatch, FakeApp())
    respx.get(GRAPH_ME_URL).mock(return_value=response)

    result = detect_entra(EntraDetectorConfig(enabled=True))

    assert result.outcome == "failed"
    assert result.facts.diagnostics == [diagnostic]


@respx.mock
def test_graph_transport_error_is_short_diagnostic(
    monkeypatch: pytest.MonkeyPatch, on_windows: None
) -> None:
    _use_app(monkeypatch, FakeApp())
    respx.get(GRAPH_ME_URL).mock(side_effect=httpx.ConnectError("boom"))

    result = detect_entra(EntraDetectorConfig(enabled=True))

    assert result.facts.diagnostics == ["entra: Microsoft Graph request failed"]


# ---- token errors ----------------------------------------------------------


@pytest.mark.parametrize(
    ("result", "diagnostic"),
    [
        ({"_broker_status": "Response_Status.Status_InteractionRequired"}, "entra: sign-in interaction required"),
        ({"error_description": "x. Status: Response_Status.Status_AccountUnusable, y"}, "entra: sign-in interaction required"),
        ({"error_description": "Status: Response_Status.Status_IncorrectConfiguration"}, "entra: client not authorized for Microsoft Graph"),
        ({"error_description": "AADSTS65002: consent must be configured"}, "entra: client not authorized for Microsoft Graph"),
        ({"error_description": "Status: Response_Status.Status_NoNetwork"}, "entra: sign-in service unreachable"),
        ({"error_description": "Status: Response_Status.Status_DeviceNotRegistered"}, "entra: no work or school account available"),
        ({"error_description": "Status: Response_Status.Status_Unexpected, secret-ish detail"}, "entra: token request failed (Status_Unexpected)"),
        ({"error": "interaction_required", "error_description": "AADSTS50076 MFA"}, "entra: sign-in interaction required"),
        ({"error": "invalid_grant", "error_description": "anything"}, "entra: token request failed"),
    ],
)
def test_token_errors_map_without_raw_text(result: dict[str, object], diagnostic: str) -> None:
    assert token_error_message(result) == diagnostic


@pytest.mark.parametrize(
    ("raises", "diagnostic"),
    [
        (RedirectUriError("needs ms-appx-web://..."), "entra: client_id is missing the broker redirect URI"),
        (ValueError("other"), "entra: token request failed"),
        (RuntimeError("boom"), "entra: lookup failed (RuntimeError)"),
    ],
)
def test_token_request_exceptions_map_to_short_diagnostics(
    monkeypatch: pytest.MonkeyPatch, on_windows: None, raises: BaseException, diagnostic: str
) -> None:
    _use_app(monkeypatch, FakeApp(raises=raises))

    result = detect_entra(EntraDetectorConfig(enabled=True))

    assert result.facts.diagnostics == [diagnostic]


@pytest.mark.parametrize(
    ("ui", "diagnostic"),
    [
        ("browser", "entra: Windows sign-in broker unavailable"),
        ("broker", "entra: sign-in interaction required"),
    ],
)
def test_ui_launch_attempt_is_blocked_and_reported(
    monkeypatch: pytest.MonkeyPatch, on_windows: None, ui: str, diagnostic: str
) -> None:
    class UiApp(FakeApp):
        def acquire_token_interactive(self, scopes: list[str], **kwargs: Any) -> object:
            kwargs["on_before_launching_ui"](ui=ui)
            raise AssertionError("UI must never launch")

    _use_app(monkeypatch, UiApp())

    result = detect_entra(EntraDetectorConfig(enabled=True))

    assert result.facts.diagnostics == [diagnostic]


def test_network_exception_from_msal_is_unreachable(
    monkeypatch: pytest.MonkeyPatch, on_windows: None
) -> None:
    connection_error = type("ConnectionError", (OSError,), {"__module__": "requests.exceptions"})

    def create(_client_id: str, _authority: str) -> FakeApp:
        raise connection_error("offline")

    monkeypatch.setattr(identity_entra, "_create_app", create)

    result = detect_entra(EntraDetectorConfig(enabled=True))

    assert result.facts.diagnostics == ["entra: sign-in service unreachable"]


def test_missing_broker_library_is_unavailable(
    monkeypatch: pytest.MonkeyPatch, on_windows: None
) -> None:
    def create(_client_id: str, _authority: str) -> FakeApp:
        raise ImportError("No module named 'msal'")

    monkeypatch.setattr(identity_entra, "_create_app", create)

    result = detect_entra(EntraDetectorConfig(enabled=True))

    assert result.facts.diagnostics == ["entra: Windows sign-in broker unavailable"]


def test_unavailable_off_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(identity_entra, "_on_windows", lambda: False)

    result = detect_entra(EntraDetectorConfig(enabled=True))

    assert result.outcome == "failed"
    assert result.facts.diagnostics == ["entra: unavailable on this platform"]


def test_hung_lookup_times_out_without_blocking(
    monkeypatch: pytest.MonkeyPatch, on_windows: None
) -> None:
    release = threading.Event()
    workers: list[threading.Thread] = []

    class HangingApp(FakeApp):
        def acquire_token_interactive(self, scopes: list[str], **kwargs: Any) -> object:
            workers.append(threading.current_thread())
            release.wait(5)
            return {"error": "late"}

    _use_app(monkeypatch, HangingApp())
    monkeypatch.setattr(identity_entra, "ENTRA_TIMEOUT_SECONDS", 0.05)

    try:
        result = detect_entra(EntraDetectorConfig(enabled=True))
    finally:
        release.set()
        for worker in workers:
            worker.join(5)

    assert result.facts.diagnostics == ["entra: lookup timed out after 0.05s"]


@pytest.mark.parametrize("blocked_stage", ["authority", "broker", "graph"])
@pytest.mark.parametrize("changed_config", [False, True])
def test_timed_out_lookup_blocks_retries_until_worker_exits(
    monkeypatch: pytest.MonkeyPatch,
    on_windows: None,
    blocked_stage: str,
    changed_config: bool,
) -> None:
    release = threading.Event()
    workers: list[threading.Thread] = []
    created: list[str] = []
    graph_calls: list[str] = []
    now = [0.0]

    def block(stage: str) -> None:
        if stage == blocked_stage and not release.is_set():
            workers.append(threading.current_thread())
            assert release.wait(5), "test must release the stalled lookup"

    class SlowApp(FakeApp):
        def acquire_token_interactive(self, scopes: list[str], **kwargs: Any) -> object:
            block("broker")
            return super().acquire_token_interactive(scopes, **kwargs)

    app = SlowApp()

    def create(client_id: str, _authority: str) -> FakeApp:
        created.append(client_id)
        block("authority")
        return app

    def graph(url: str, **_kwargs: Any) -> httpx.Response:
        graph_calls.append(url)
        block("graph")
        return httpx.Response(200, json={"mail": "user@example.com"})

    def request(settings: EntraDetectorConfig) -> DetectionRequest:
        return DetectionRequest(
            order=["entra"], settings={"entra": settings}, pinned=frozenset({"entra"})
        )

    monkeypatch.setattr(identity_entra, "_create_app", create)
    monkeypatch.setattr(identity_entra.httpx, "get", graph)
    monkeypatch.setattr(identity_entra, "ENTRA_TIMEOUT_SECONDS", 0.05)
    runner = DetectorRunner(
        specs={"entra": DetectorSpec("entra", detect_entra, 0.05)},
        clock=lambda: now[0],
    )
    settings = EntraDetectorConfig(enabled=True)
    retry_settings = (
        EntraDetectorConfig(enabled=True, client_id=_CONFIGURED_ID)
        if changed_config else settings
    )
    try:
        first = runner.detect(request(settings), wait=None)
        assert first.results["entra"].facts.diagnostics == [
            "entra: lookup timed out after 0.05s"
        ]
        now[0] = 60.0
        retry = runner.detect(request(retry_settings), wait=None)
        assert retry.results["entra"].facts.diagnostics == [
            "entra: previous lookup still running"
        ]
        assert created == [BUILTIN_CLIENT_ID]
        assert len(workers) == 1
    finally:
        release.set()
        for worker in workers:
            worker.join(5)

    assert all(not worker.is_alive() for worker in workers)
    # Expired authority/broker work must not advance to another request.
    assert len(app.calls) == (0 if blocked_stage == "authority" else 1)
    assert len(graph_calls) == (1 if blocked_stage == "graph" else 0)

    now[0] = 180.0
    recovered = runner.detect(request(retry_settings), wait=None)
    assert recovered.results["entra"].outcome == "complete"
    assert recovered.results["entra"].facts.emails == ["user@example.com"]
    assert created == [BUILTIN_CLIENT_ID, retry_settings.client_id or BUILTIN_CLIENT_ID]


@respx.mock
def test_graph_timeout_uses_remaining_lookup_budget(
    monkeypatch: pytest.MonkeyPatch, on_windows: None
) -> None:
    now = [0.0]

    class SlowApp(FakeApp):
        def acquire_token_interactive(self, scopes: list[str], **kwargs: Any) -> object:
            now[0] = identity_entra.ENTRA_TIMEOUT_SECONDS - 3.0
            return super().acquire_token_interactive(scopes, **kwargs)

    monkeypatch.setattr(identity_entra, "monotonic", lambda: now[0])
    _use_app(monkeypatch, SlowApp())
    route = _graph_ok()

    result = detect_entra(EntraDetectorConfig(enabled=True))

    assert result.outcome == "complete"
    assert set(route.calls.last.request.extensions["timeout"].values()) == {3.0}


@respx.mock
def test_worker_start_failure_does_not_block_later_lookups(
    monkeypatch: pytest.MonkeyPatch, on_windows: None
) -> None:
    def fail_to_start(_thread: threading.Thread) -> None:
        raise RuntimeError("cannot start thread")

    _use_app(monkeypatch, FakeApp())
    _graph_ok()
    with monkeypatch.context() as failing:
        failing.setattr(threading.Thread, "start", fail_to_start)
        with pytest.raises(RuntimeError, match="cannot start thread"):
            detect_entra(EntraDetectorConfig(enabled=True))

    assert detect_entra(EntraDetectorConfig(enabled=True)).outcome == "complete"


# ---- secret boundary -------------------------------------------------------


@respx.mock
def test_token_never_reaches_logs_results_or_diagnostics(
    monkeypatch: pytest.MonkeyPatch, on_windows: None, caplog: pytest.LogCaptureFixture
) -> None:
    _use_app(monkeypatch, FakeApp())
    _graph_ok()

    with caplog.at_level(logging.DEBUG):
        ok = detect_entra(EntraDetectorConfig(enabled=True))
    respx.get(GRAPH_ME_URL).mock(return_value=httpx.Response(500))
    with caplog.at_level(logging.DEBUG):
        failed = detect_entra(EntraDetectorConfig(enabled=True))

    for text in (caplog.text, repr(ok), repr(failed)):
        assert _FAKE_TOKEN not in text
        assert not re.search(r"eyJ[A-Za-z0-9_-]+\.", text)


def test_module_has_no_subprocess_or_powershell_usage() -> None:
    source = (
        __import__("pathlib").Path(identity_entra.__file__).read_text(encoding="utf-8")
    )

    assert "subprocess" not in source
    assert "powershell.exe" not in source.lower()
    assert "pwsh" not in source.lower()
    assert "EncodedCommand" not in source
