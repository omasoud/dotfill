"""Outbound HTTP test for a service token."""

from __future__ import annotations

import base64
import logging
from collections.abc import Mapping
from dataclasses import dataclass

import httpx

from .config_models import ServiceDefinition
from .errors import ServiceTestError
from .models import TestResult

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class PreparedServiceTestRequest:
    """Non-secret shape of the outbound service-test request."""

    url: str
    headers: dict[str, str]


def _basic_username(
    svc: ServiceDefinition,
    *,
    service_id: str,
    identity_values: Mapping[str, str | None] | None,
) -> str | None:
    if svc.auth.username is not None:
        return svc.auth.username
    if svc.auth.username_identity is None:
        return None
    if identity_values is None:
        return None
    value = identity_values.get(svc.auth.username_identity)
    if value is None or value == "":
        log.warning(
            "Service test failed for %s: basic username identity is unresolved",
            service_id,
        )
        return None
    if ":" in value:
        log.warning(
            "Service test failed for %s: basic username identity is invalid",
            service_id,
        )
        return None
    return value


def prepare_service_test_request(
    svc: ServiceDefinition,
    *,
    service_id: str,
    resolved_test_url: str,
    token: str,
    identity_values: Mapping[str, str | None] | None = None,
) -> PreparedServiceTestRequest | TestResult:
    """Prepare headers for a configured service-test auth mode."""
    headers = {"Accept": "application/json"}
    headers.update(svc.test_headers)
    if svc.auth.kind == "bearer":
        headers["Authorization"] = f"Bearer {token}"
    elif svc.auth.kind == "header":
        if svc.auth.header is None:
            raise ServiceTestError(f"{service_id}: header auth is missing header")
        headers[svc.auth.header] = token
    elif svc.auth.kind == "basic":
        username = _basic_username(
            svc,
            service_id=service_id,
            identity_values=identity_values,
        )
        if username is None:
            return TestResult(
                status="failed",
                error_message="Basic username identity is unresolved",
            )
        credentials = f"{username}:{token}".encode("utf-8")
        encoded = base64.b64encode(credentials).decode("ascii")
        headers["Authorization"] = f"Basic {encoded}"
    else:
        raise ServiceTestError(f"{service_id}: unsupported auth mode {svc.auth.kind!r}")
    return PreparedServiceTestRequest(url=resolved_test_url, headers=headers)


def run_service_test(
    svc: ServiceDefinition,
    *,
    service_id: str,
    resolved_test_url: str,
    token: str,
    identity_values: Mapping[str, str | None] | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    client: httpx.Client | None = None,
) -> TestResult:
    """Perform a configured-auth GET against the test URL and classify the result."""
    if not token:
        raise ServiceTestError(f"{service_id}: token is empty")
    request = prepare_service_test_request(
        svc,
        service_id=service_id,
        resolved_test_url=resolved_test_url,
        token=token,
        identity_values=identity_values,
    )
    if isinstance(request, TestResult):
        return request
    owns_client = client is None
    if client is None:
        client = httpx.Client(timeout=timeout, verify=svc.tls_verify)
    try:
        response = client.get(request.url, headers=request.headers)
    except httpx.HTTPError as exc:
        log.warning(
            "Service test transport error for %s: %s",
            service_id,
            exc,
        )
        return TestResult(
            status="failed",
            error_message="Service test transport error",
        )
    finally:
        if owns_client:
            client.close()

    status_code = response.status_code
    if 200 <= status_code < 300:
        log.info("Service test passed for %s (HTTP %d)", service_id, status_code)
        return TestResult(status="working", http_status=status_code)
    if status_code in (401, 403):
        log.warning("Service test failed for %s: authentication failed (HTTP %d)", service_id, status_code)
        return TestResult(
            status="failed",
            http_status=status_code,
            error_message="Authentication failed",
        )
    log.warning("Service test failed for %s: unexpected status (HTTP %d)", service_id, status_code)
    return TestResult(
        status="failed",
        http_status=status_code,
        error_message=f"Unexpected status {status_code}",
    )
