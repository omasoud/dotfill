"""Entra ID identity detector backed by a silent Microsoft Graph `/me` lookup.

The token comes from the Windows sign-in broker through MSAL Python in
process; no PowerShell or other child process is started.
"""

from __future__ import annotations

import logging
import re
import sys
import threading
from collections.abc import Mapping
from time import monotonic
from typing import Any

import httpx

from .config_models import EntraDetectorConfig
from .identity_facts import DetectorResult, IdentityFacts, make_identity_facts

log = logging.getLogger(__name__)

ENTRA_TIMEOUT_SECONDS = 20.0
GRAPH_TIMEOUT_SECONDS = 10.0
BUILTIN_CLIENT_ID = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"
BUILTIN_SCOPES = ["https://graph.microsoft.com/.default"]
CONFIGURED_SCOPES = ["User.Read"]
GRAPH_ME_URL = (
    "https://graph.microsoft.com/v1.0/me?$select=mail,userPrincipalName,proxyAddresses"
)

# Owned until the actual worker exits, including after its caller times out.
_lookup_slot = threading.Lock()

_BROKER_UNAVAILABLE = "entra: Windows sign-in broker unavailable"
_INTERACTION_REQUIRED = "entra: sign-in interaction required"
_STATUS_RE = re.compile(r"Status_[A-Za-z]+")
_STATUS_MESSAGES = {
    "Status_InteractionRequired": _INTERACTION_REQUIRED,
    "Status_AccountUnusable": _INTERACTION_REQUIRED,
    "Status_AccountNotFound": _INTERACTION_REQUIRED,
    "Status_IncorrectConfiguration": "entra: client not authorized for Microsoft Graph",
    "Status_NoNetwork": "entra: sign-in service unreachable",
    "Status_NetworkTemporarilyUnavailable": "entra: sign-in service unreachable",
    "Status_ServerTemporarilyUnavailable": "entra: sign-in service unreachable",
    "Status_TransientError": "entra: sign-in service unreachable",
    "Status_DeviceNotRegistered": "entra: no work or school account available",
    "Status_RequiredBrokerMissing": "entra: no work or school account available",
}


class _UiBlocked(RuntimeError):
    """Raised by the UI hook so MSAL can never show a prompt or open a browser."""

    def __init__(self, ui: str) -> None:
        super().__init__(ui)
        self.ui = ui


def _block_ui(**kwargs: object) -> None:
    raise _UiBlocked(str(kwargs.get("ui", "")))


def _on_windows() -> bool:
    return sys.platform == "win32"


def entra_scopes(settings: EntraDetectorConfig) -> list[str]:
    """Return the one scope set used for the configured client mode.

    The built-in client ID is pre-authorized only for the Graph `.default`
    scope; a configured client ID requests `User.Read`. There is no retry
    with a different scope set.
    """
    return list(BUILTIN_SCOPES if settings.client_id is None else CONFIGURED_SCOPES)


def entra_authority(settings: EntraDetectorConfig) -> str:
    """Return the Microsoft identity platform authority for the tenant setting."""
    return f"https://login.microsoftonline.com/{settings.tenant}"


def _create_app(client_id: str, authority: str) -> Any:
    import msal

    return msal.PublicClientApplication(
        client_id,
        authority=authority,
        enable_broker_on_windows=True,
        timeout=ENTRA_TIMEOUT_SECONDS,
    )


def _failed(message: str) -> DetectorResult:
    return DetectorResult(
        detector="entra", facts=IdentityFacts(diagnostics=[message]), outcome="failed"
    )


def _timed_out() -> DetectorResult:
    """Return the diagnostic for an expired lookup."""
    return _failed(f"entra: lookup timed out after {ENTRA_TIMEOUT_SECONDS:g}s")


def token_error_message(result: Mapping[str, object]) -> str:
    """Map an MSAL error result to a short diagnostic without its raw text."""
    status_text = f"{result.get('_broker_status') or ''} {result.get('error_description') or ''}"
    match = _STATUS_RE.search(status_text)
    status = match.group(0) if match else None
    if "AADSTS65002" in status_text:
        return _STATUS_MESSAGES["Status_IncorrectConfiguration"]
    if status in _STATUS_MESSAGES:
        return _STATUS_MESSAGES[status]
    if result.get("error") == "interaction_required":
        return _INTERACTION_REQUIRED
    if status:
        return f"entra: token request failed ({status})"
    return "entra: token request failed"


def _graph_me(token: str, *, timeout: float) -> DetectorResult:
    try:
        response = httpx.get(
            GRAPH_ME_URL,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=timeout,
        )
    except httpx.HTTPError as exc:
        log.debug("Entra Graph request failed: %s", type(exc).__name__)
        return _failed("entra: Microsoft Graph request failed")
    if response.status_code != 200:
        return _failed(f"entra: Microsoft Graph request failed ({response.status_code})")
    try:
        data = response.json()
    except ValueError:
        return _failed("entra: Microsoft Graph returned an invalid response")
    if not isinstance(data, dict):
        return _failed("entra: Microsoft Graph returned an invalid response")
    proxies = data.get("proxyAddresses")
    facts = make_identity_facts(
        mail=data.get("mail") if isinstance(data.get("mail"), str) else None,
        user_principal_name=data.get("userPrincipalName")
        if isinstance(data.get("userPrincipalName"), str)
        else None,
        proxy_addresses=[p for p in proxies if isinstance(p, str)]
        if isinstance(proxies, list)
        else [],
    )
    return DetectorResult(detector="entra", facts=facts, outcome="complete")


def _lookup(settings: EntraDetectorConfig, deadline: float) -> DetectorResult:
    if monotonic() >= deadline:
        return _timed_out()
    try:
        app = _create_app(settings.client_id or BUILTIN_CLIENT_ID, entra_authority(settings))
    except ImportError:
        return _failed(_BROKER_UNAVAILABLE)
    if monotonic() >= deadline:
        return _timed_out()
    try:
        result = app.acquire_token_interactive(
            entra_scopes(settings),
            prompt="none",
            parent_window_handle=app.CONSOLE_WINDOW_HANDLE,
            on_before_launching_ui=_block_ui,
        )
    except _UiBlocked as exc:
        # MSAL falls back to a browser only when the broker is unavailable.
        return _failed(_BROKER_UNAVAILABLE if exc.ui == "browser" else _INTERACTION_REQUIRED)
    except ValueError as exc:
        if type(exc).__name__ == "RedirectUriError":
            return _failed("entra: client_id is missing the broker redirect URI")
        log.debug("Entra token request raised %s", type(exc).__name__)
        return _failed("entra: token request failed")
    if not isinstance(result, dict):
        return _failed("entra: token request failed")
    token = result.pop("access_token", None)
    if not isinstance(token, str) or not token:
        return _failed(token_error_message(result))
    remaining = deadline - monotonic()
    if remaining <= 0:
        return _timed_out()
    return _graph_me(token, timeout=min(GRAPH_TIMEOUT_SECONDS, remaining))


def _safe_lookup(settings: EntraDetectorConfig, deadline: float) -> DetectorResult:
    try:
        return _lookup(settings, deadline)
    except Exception as exc:  # noqa: BLE001 - detectors must never break state
        log.debug("Entra lookup raised %s", type(exc).__name__)
        if type(exc).__module__.split(".", 1)[0] in {"requests", "urllib3"}:
            return _failed("entra: sign-in service unreachable")
        return _failed(f"entra: lookup failed ({type(exc).__name__})")


def detect_entra(settings: object | None = None) -> DetectorResult:
    """Silently look up the signed-in Entra user's email addresses via Graph `/me`."""
    config = settings if isinstance(settings, EntraDetectorConfig) else EntraDetectorConfig()
    if not _on_windows():
        return _failed("entra: unavailable on this platform")
    if not _lookup_slot.acquire(blocking=False):
        return _failed("entra: previous lookup still running")
    deadline = monotonic() + ENTRA_TIMEOUT_SECONDS
    results: list[DetectorResult] = []

    def run() -> None:
        """Keep the lookup slot until native work and cleanup actually finish."""
        try:
            result = _safe_lookup(config, deadline)
            results.append(_timed_out() if monotonic() >= deadline else result)
        finally:
            _lookup_slot.release()

    try:
        worker = threading.Thread(target=run, name="dotfill-entra-lookup", daemon=True)
        worker.start()
    except RuntimeError:
        _lookup_slot.release()
        raise
    worker.join(max(deadline - monotonic(), 0.0))
    if not results:
        # A retry must not start more native work while this worker is alive.
        return _timed_out()
    return results[0]
