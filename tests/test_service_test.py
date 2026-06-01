"""Tests for service_test.test_service."""

from __future__ import annotations

import logging

import httpx
import pytest
import respx

from dotfill.errors import ServiceTestError
from dotfill.config_models import ServiceDefinition
from dotfill.service_test import run_service_test


def _svc(*, tls_verify: bool = True) -> ServiceDefinition:
    return ServiceDefinition(
        service_id="EXAMPLE",
        token_var="EXAMPLE_TOKEN",
        token_url_template="https://example.com/token",
        test_url_template="https://example.com/api/test",
        display_name="Example",
        tls_verify=tls_verify,
    )


@respx.mock
def test_service_success() -> None:
    url = "https://example.com/api/test"
    route = respx.get(url).mock(return_value=httpx.Response(200, json={"ok": True}))
    result = run_service_test(_svc(), service_id="EXAMPLE", resolved_test_url=url, token="tok")
    assert result.status == "working"
    assert result.http_status == 200
    assert route.called
    request = route.calls.last.request
    assert request.headers["authorization"] == "Bearer tok"
    assert request.headers["accept"] == "application/json"


@respx.mock
def test_service_auth_failure() -> None:
    url = "https://example.com/api/test"
    respx.get(url).mock(return_value=httpx.Response(401))
    result = run_service_test(_svc(), service_id="EXAMPLE", resolved_test_url=url, token="tok")
    assert result.status == "failed"
    assert result.http_status == 401


@respx.mock
def test_service_unexpected_status() -> None:
    url = "https://example.com/api/test"
    respx.get(url).mock(return_value=httpx.Response(500))
    result = run_service_test(_svc(), service_id="EXAMPLE", resolved_test_url=url, token="tok")
    assert result.status == "failed"
    assert result.http_status == 500


@respx.mock
def test_service_transport_error() -> None:
    url = "https://example.com/api/test"
    respx.get(url).mock(side_effect=httpx.ConnectError("boom"))
    result = run_service_test(_svc(), service_id="EXAMPLE", resolved_test_url=url, token="tok")
    assert result.status == "failed"
    assert result.http_status is None
    assert "boom" in (result.error_message or "")


def test_service_empty_token_raises() -> None:
    with pytest.raises(ServiceTestError):
        run_service_test(_svc(), service_id="EXAMPLE", resolved_test_url="https://example.com", token="")


def test_service_default_uses_tls_verification(monkeypatch: pytest.MonkeyPatch) -> None:
    verify_values: list[bool] = []

    class FakeClient:
        def __init__(self, *, timeout: float, verify: bool) -> None:
            verify_values.append(verify)

        def get(self, resolved_test_url: str, *, headers: dict[str, str]) -> httpx.Response:
            return httpx.Response(200)

        def close(self) -> None:
            pass

    monkeypatch.setattr("dotfill.service_test.httpx.Client", FakeClient)

    result = run_service_test(
        _svc(),
        service_id="EXAMPLE",
        resolved_test_url="https://example.com",
        token="tok",
    )

    assert result.status == "working"
    assert verify_values == [True]


def test_service_tls_verify_false_is_honored(monkeypatch: pytest.MonkeyPatch) -> None:
    verify_values: list[bool] = []

    class FakeClient:
        def __init__(self, *, timeout: float, verify: bool) -> None:
            verify_values.append(verify)

        def get(self, resolved_test_url: str, *, headers: dict[str, str]) -> httpx.Response:
            return httpx.Response(200)

        def close(self) -> None:
            pass

    monkeypatch.setattr("dotfill.service_test.httpx.Client", FakeClient)

    result = run_service_test(
        _svc(tls_verify=False),
        service_id="EXAMPLE",
        resolved_test_url="https://example.com",
        token="tok",
    )

    assert result.status == "working"
    assert verify_values == [False]


def test_service_anonymous_looking_200_is_not_special_cased() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={"type": "anonymous", "displayName": "Anonymous"},
            )
        )
    )

    result = run_service_test(
        _svc(),
        service_id="GENERIC",
        resolved_test_url="https://example.com",
        token="tok",
        client=client,
    )

    assert result.status == "working"


def test_service_test_logs_do_not_include_token_or_auth_header(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(403))
    )

    with caplog.at_level(logging.WARNING):
        result = run_service_test(
            _svc(),
            service_id="GENERIC",
            resolved_test_url="https://example.com",
            token="super-secret-token",
            client=client,
        )

    assert result.status == "failed"
    assert "super-secret-token" not in caplog.text
    assert "Authorization" not in caplog.text
    assert "Bearer" not in caplog.text

