"""Entra ID identity detector backed by a silent Microsoft Graph `/me` lookup."""

from __future__ import annotations

import base64
import logging
import os
import re
import shutil
import subprocess
import sys

from .config_models import EntraDetectorConfig
from .identity_facts import DetectorResult, IdentityFacts, make_identity_facts

log = logging.getLogger(__name__)

ENTRA_TIMEOUT_SECONDS = 20.0
BUILTIN_CLIENT_ID = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"
GRAPH_RESOURCE = "https://graph.microsoft.com"

_GUID_RE = re.compile(
    r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$"
)
_DNS_LABEL_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
_DETAIL_RE = re.compile(r"^[A-Za-z0-9]{1,32}$")

_ERROR_MESSAGES = {
    "winrt_unavailable": "entra: Windows sign-in broker unavailable",
    "no_account_provider": "entra: no work or school account available",
    "interaction_required": "entra: sign-in interaction required",
    "client_not_authorized": "entra: client not authorized for Microsoft Graph",
    "token_failed": "entra: token request failed",
    "graph_failed": "entra: Microsoft Graph request failed",
}

_HELPER_TEMPLATE = r"""
$ErrorActionPreference = 'Stop'
function Fail([string] $Code, [string] $Detail) {
    if ($Detail) { Write-Output ("ERR:" + $Code + ":" + $Detail) } else { Write-Output ("ERR:" + $Code) }
    exit 0
}
try {
    Add-Type -AssemblyName System.Runtime.WindowsRuntime
    $asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
        $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
        $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
    })[0]
    $null = [Windows.Security.Authentication.Web.Core.WebAuthenticationCoreManager, Windows.Security.Authentication.Web.Core, ContentType=WindowsRuntime]
    $null = [Windows.Security.Authentication.Web.Core.WebTokenRequest, Windows.Security.Authentication.Web.Core, ContentType=WindowsRuntime]
    $null = [Windows.Security.Credentials.WebAccountProvider, Windows.Security.Credentials, ContentType=WindowsRuntime]
    $dictAdd = [System.Collections.Generic.IDictionary[string,string]].GetMethod('Add')
} catch { Fail 'winrt_unavailable' '' }
function Await($Operation, [Type] $ResultType) {
    $task = $asTaskGeneric.MakeGenericMethod($ResultType).Invoke($null, @($Operation))
    if (-not $task.Wait(__WAIT_MS__)) { throw 'broker timeout' }
    $task.Result
}
try {
    $provider = Await ([Windows.Security.Authentication.Web.Core.WebAuthenticationCoreManager]::FindAccountProviderAsync('https://login.microsoft.com', '__AUTHORITY__')) ([Windows.Security.Credentials.WebAccountProvider])
} catch { Fail 'no_account_provider' '' }
if ($null -eq $provider) { Fail 'no_account_provider' '' }
try {
    $request = [Windows.Security.Authentication.Web.Core.WebTokenRequest]::new($provider, '__SCOPE__', '__CLIENT_ID__')
    $null = $dictAdd.Invoke($request.Properties, @('resource', '__RESOURCE__'))
    $result = Await ([Windows.Security.Authentication.Web.Core.WebAuthenticationCoreManager]::GetTokenSilentlyAsync($request)) ([Windows.Security.Authentication.Web.Core.WebTokenRequestResult])
} catch { Fail 'token_failed' '' }
$status = [string] $result.ResponseStatus
if ($status -eq 'UserInteractionRequired') { Fail 'interaction_required' '' }
if ($status -ne 'Success') {
    $message = ''
    if ($result.ResponseError) { $message = [string] $result.ResponseError.ErrorMessage }
    if ($message -match 'AADSTS65002') { Fail 'client_not_authorized' '' }
    Fail 'token_failed' $status
}
$token = $result.ResponseData[0].Token
$result = $null
try {
    $me = Invoke-RestMethod -Uri 'https://graph.microsoft.com/v1.0/me?$select=mail,userPrincipalName,proxyAddresses' -Headers @{ Authorization = ('Bearer ' + $token) } -TimeoutSec __HTTP_TIMEOUT__
} catch {
    $token = $null
    $httpStatus = ''
    try { $httpStatus = [string] [int] $_.Exception.Response.StatusCode } catch { }
    Fail 'graph_failed' $httpStatus
}
$token = $null
Write-Output ("MAIL:" + [string] $me.mail)
Write-Output ("UPN:" + [string] $me.userPrincipalName)
foreach ($address in @($me.proxyAddresses)) {
    if ([string] $address -match '^(?i)smtp:') { Write-Output ("PROXY:" + ([string] $address).Substring(5)) }
}
Write-Output 'GRAPH:ok'
"""


def _is_valid_tenant(value: str) -> bool:
    if value == "organizations" or _GUID_RE.fullmatch(value):
        return True
    if not value or len(value) > 253:
        return False
    return all(_DNS_LABEL_RE.fullmatch(label) for label in value.split("."))


def build_helper_script(settings: EntraDetectorConfig) -> str:
    """Build the Web Account Manager helper for one client mode.

    The built-in client ID requests the Graph resource without a scope, the
    only form it is pre-authorized for; a configured client ID requests
    `User.Read` with the Graph resource. There is no alternate-form retry.
    """
    client_id = settings.client_id or BUILTIN_CLIENT_ID
    if not _GUID_RE.fullmatch(client_id):
        raise ValueError("Entra client_id must be a GUID")
    if not _is_valid_tenant(settings.tenant):
        raise ValueError("Entra tenant must be 'organizations', a GUID, or a DNS domain")
    authority = (
        "organizations"
        if settings.tenant == "organizations"
        else f"https://login.microsoftonline.com/{settings.tenant}"
    )
    scope = "" if settings.client_id is None else "User.Read"
    broker_wait_ms = int(ENTRA_TIMEOUT_SECONDS * 1000 / 2)
    http_timeout = int(ENTRA_TIMEOUT_SECONDS / 2)
    return (
        _HELPER_TEMPLATE.replace("__AUTHORITY__", authority)
        .replace("__SCOPE__", scope)
        .replace("__CLIENT_ID__", client_id)
        .replace("__RESOURCE__", GRAPH_RESOURCE)
        .replace("__WAIT_MS__", str(broker_wait_ms))
        .replace("__HTTP_TIMEOUT__", str(http_timeout))
        .strip()
    )


def _windows_powershell() -> str | None:
    system_root = os.environ.get("SystemRoot") or os.environ.get("WINDIR")
    if system_root:
        candidate = os.path.join(
            system_root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe"
        )
        if os.path.isfile(candidate):
            return candidate
    return shutil.which("powershell.exe")


def _run_helper(script: str) -> str:
    """Run the helper in Windows PowerShell 5.1 and return its stdout."""
    executable = _windows_powershell()
    if executable is None:
        raise FileNotFoundError("Windows PowerShell not found")
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    proc = subprocess.run(  # noqa: S603 - controlled args
        [executable, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
        capture_output=True,
        text=True,
        timeout=ENTRA_TIMEOUT_SECONDS,
        check=False,
    )
    return proc.stdout or ""


def parse_helper_output(out: str) -> DetectorResult:
    """Parse helper stdout, keeping only the known non-secret line types."""
    mail: str | None = None
    upn: str | None = None
    proxies: list[str] = []
    diagnostics: list[str] = []
    graph_ok = False
    for raw_line in out.splitlines():
        line = raw_line.strip()
        if line.startswith("MAIL:"):
            mail = line[5:].strip() or None
        elif line.startswith("UPN:"):
            upn = line[4:].strip() or None
        elif line.startswith("PROXY:"):
            address = line[6:].strip()
            if address:
                proxies.append(f"smtp:{address}")
        elif line.startswith("ERR:"):
            diagnostics.append(_error_message(line[4:].strip()))
        elif line == "GRAPH:ok":
            graph_ok = True
    if graph_ok and not diagnostics:
        facts = make_identity_facts(mail=mail, user_principal_name=upn, proxy_addresses=proxies)
        return DetectorResult(detector="entra", facts=facts, outcome="complete")
    if not diagnostics:
        diagnostics.append("entra: lookup returned no result")
    return DetectorResult(
        detector="entra", facts=IdentityFacts(diagnostics=diagnostics), outcome="failed"
    )


def _error_message(payload: str) -> str:
    code, _, detail = payload.partition(":")
    message = _ERROR_MESSAGES.get(code, "entra: lookup failed")
    if detail and _DETAIL_RE.fullmatch(detail):
        message = f"{message} ({detail})"
    return message


def _failed(message: str) -> DetectorResult:
    return DetectorResult(
        detector="entra", facts=IdentityFacts(diagnostics=[message]), outcome="failed"
    )


def detect_entra(settings: object | None = None) -> DetectorResult:
    """Silently look up the signed-in Entra user's email addresses via Graph `/me`."""
    config = settings if isinstance(settings, EntraDetectorConfig) else EntraDetectorConfig()
    if sys.platform != "win32":
        return _failed("entra: unavailable on this platform")
    try:
        script = build_helper_script(config)
    except ValueError:
        return _failed("entra: invalid detector configuration")
    try:
        out = _run_helper(script)
    except subprocess.TimeoutExpired:
        return _failed(f"entra: lookup timed out after {ENTRA_TIMEOUT_SECONDS:g}s")
    except OSError as exc:
        log.debug("Entra helper could not start: %s", type(exc).__name__)
        return _failed("entra: Windows PowerShell unavailable")
    return parse_helper_output(out)
