"""Outbound HTTP test for a service token."""

from __future__ import annotations

import logging

import httpx

from .config_models import ServiceDefinition
from .errors import ServiceTestError
from .models import TestResult

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 10.0


def run_service_test(
    svc: ServiceDefinition,
    *,
    service_id: str,
    resolved_test_url: str,
    token: str,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    client: httpx.Client | None = None,
) -> TestResult:
    """Perform a bearer-auth GET against the test URL and classify the result."""
    if not token:
        raise ServiceTestError(f"{service_id}: token is empty")
    if svc.auth != "bearer":
        raise ServiceTestError(f"{service_id}: unsupported auth mode {svc.auth!r}")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    owns_client = client is None
    if client is None:
        client = httpx.Client(timeout=timeout, verify=svc.tls_verify)
    try:
        response = client.get(resolved_test_url, headers=headers)
    except httpx.HTTPError as exc:
        log.warning(
            "Service test transport error for %s: %s",
            service_id,
            exc,
        )
        return TestResult(status="failed", error_message=str(exc))
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
