"""Windows AD fact detection and identity value resolution."""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass

from .config_models import CompareMode
from .identity_facts import DetectorResult, facts_have_values, make_identity_facts
from .value_policy import values_equal

log = logging.getLogger(__name__)

WINDOWS_AD_TIMEOUT_SECONDS = 15.0
_NAME_SAM_COMPATIBLE = 2
_NAME_USER_PRINCIPAL = 8

_DNS_LABEL_RE = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$"
)

_POWERSHELL_TEMPLATE = r"""
$ErrorActionPreference = 'Stop'
try {
    $samCompound = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    if (-not $samCompound) { Write-Output "ERR:no-current-identity"; exit 0 }
    $parts = $samCompound -split '\\', 2
    if ($parts.Length -ne 2) {
        $sam = $samCompound
        $domain = $env:USERDOMAIN
    } else {
        $domain = $parts[0]
        $sam = $parts[1]
    }
    Write-Output "SAM:$sam"
    Write-Output "DOMAIN:$domain"

    function Test-DnsDomain {
        param([string] $Value)
        if (-not $Value -or $Value.Length -gt 253) { return $false }
        foreach ($label in $Value.Split('.')) {
            if (-not $label -or $label.Length -gt 63) { return $false }
            if ($label -notmatch '^[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?$') {
                return $false
            }
        }
        return $true
    }

    $dnsDomain = '__DOMAIN_HINT__'
    if (-not $dnsDomain) {
        try {
            $upnCandidate = (whoami /upn 2>$null | Select-Object -First 1)
            if ($upnCandidate -and $upnCandidate.Contains('@')) {
                $candidateDomain = $upnCandidate.Substring(
                    $upnCandidate.IndexOf('@') + 1
                ).Trim()
                if (Test-DnsDomain $candidateDomain) {
                    $dnsDomain = $candidateDomain
                }
            }
        } catch { }
    }

    Add-Type -AssemblyName System.DirectoryServices

    function Invoke-UserSearch {
        param([string] $Root)
        if ($Root) {
            $entry = New-Object System.DirectoryServices.DirectoryEntry("LDAP://$Root")
            $searcher = New-Object System.DirectoryServices.DirectorySearcher($entry)
        } else {
            $searcher = New-Object System.DirectoryServices.DirectorySearcher
        }
        $searcher.Filter = "(&(objectClass=user)(sAMAccountName=$sam))"
        $searcher.PropertiesToLoad.AddRange(
            @("mail", "proxyAddresses", "userPrincipalName")
        ) | Out-Null
        return $searcher.FindOne()
    }

    $result = $null
    $explicitSearchCompleted = $false
    $searchErrors = @()
    if ($dnsDomain) {
        try {
            $result = Invoke-UserSearch -Root $dnsDomain
            $explicitSearchCompleted = $true
        } catch {
            $searchErrors += "explicit bind ($dnsDomain): " + $_.Exception.Message
        }
    }
    if (-not $explicitSearchCompleted) {
        try {
            $result = Invoke-UserSearch -Root $null
        } catch {
            $searchErrors += "serverless bind: " + $_.Exception.Message
        }
    }

    if ($null -ne $result) {
        $props = $result.Properties
        if ($props['mail'].Count -gt 0) {
            Write-Output ("MAIL:" + $props['mail'][0])
        } else {
            Write-Output "MAIL:"
        }
        if ($props['userprincipalname'].Count -gt 0) {
            Write-Output ("UPN:" + $props['userprincipalname'][0])
        }
        foreach ($addr in $props['proxyaddresses']) {
            if ($addr -cmatch '^SMTP:' -or $addr -cmatch '^smtp:') {
                Write-Output ("PROXY:" + $addr.Substring(5))
            }
        }
    } else {
        Write-Output "MAIL:"
        foreach ($searchError in $searchErrors) {
            Write-Output ("ERR:" + $searchError)
        }
    }
} catch {
    Write-Output ("ERR:" + $_.Exception.Message)
}
"""


def _is_valid_dns_domain(value: str) -> bool:
    """Return whether *value* is safe and structurally valid as a DNS domain."""
    if not value or len(value) > 253:
        return False
    return all(_DNS_LABEL_RE.fullmatch(label) for label in value.split("."))


def _search_domain_hint(environ: Mapping[str, str] | None = None) -> str:
    """Return a validated user directory DNS domain from the environment."""
    env = os.environ if environ is None else environ
    value = (env.get("USERDNSDOMAIN") or "").strip()
    return value if _is_valid_dns_domain(value) else ""


def _build_probe_script(domain_hint: str) -> str:
    """Build the PowerShell probe with a validated explicit-domain hint."""
    safe_hint = domain_hint.strip()
    if not _is_valid_dns_domain(safe_hint):
        safe_hint = ""
    return _POWERSHELL_TEMPLATE.replace("__DOMAIN_HINT__", safe_hint).strip()


@dataclass
class _RawProbe:
    sam: str | None = None
    domain: str | None = None
    mail: str | None = None
    proxy_addresses: list[str] | None = None
    upn: str | None = None
    errors: list[str] | None = None
    lookup_completed: bool = False


def _parse_probe_output(out: str) -> _RawProbe:
    probe = _RawProbe(errors=[], proxy_addresses=[])
    saw_mail = False
    for raw_line in out.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("SAM:"):
            probe.sam = line[4:].strip() or None
        elif line.startswith("DOMAIN:"):
            probe.domain = line[7:].strip() or None
        elif line.startswith("MAIL:"):
            saw_mail = True
            probe.mail = line[5:].strip() or None
        elif line.startswith("UPN:"):
            probe.upn = line[4:].strip() or None
        elif line.startswith("PROXY:"):
            addr = line[6:].strip()
            if addr:
                probe.proxy_addresses = (probe.proxy_addresses or []) + [addr]
        elif line.startswith("ERR:"):
            probe.errors = (probe.errors or []) + [line[4:].strip()]
    probe.lookup_completed = saw_mail and not probe.errors
    return probe


def _as_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _run_powershell_probe() -> _RawProbe:
    pwsh = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
    if not pwsh:
        return _RawProbe(errors=["PowerShell not found on PATH"])
    script = _build_probe_script(_search_domain_hint())
    try:
        proc = subprocess.run(  # noqa: S603 - controlled args
            [pwsh, "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=WINDOWS_AD_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        # Never surface exc text: it embeds the generated script.
        probe = _parse_probe_output(_as_text(exc.stdout))
        probe.errors = [
            f"directory lookup timed out after {WINDOWS_AD_TIMEOUT_SECONDS:g}s"
        ]
        probe.lookup_completed = False
        return probe
    except OSError as exc:
        return _RawProbe(errors=[f"PowerShell could not start ({type(exc).__name__})"])
    probe = _parse_probe_output(proc.stdout or "")
    if proc.returncode != 0:
        probe.errors = (probe.errors or []) + [
            f"PowerShell exit code {proc.returncode}"
        ]
        probe.lookup_completed = False
    return probe


def _windows_logon_names() -> tuple[str | None, str | None]:
    """Return the SAM-compatible name and UPN without contacting a directory."""
    if sys.platform != "win32":
        return None, None
    import ctypes
    from ctypes import wintypes

    try:
        get_user_name_ex = ctypes.windll.secur32.GetUserNameExW  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        return None, None
    get_user_name_ex.argtypes = [
        ctypes.c_int,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.ULONG),
    ]
    get_user_name_ex.restype = wintypes.BOOLEAN

    def read(name_format: int) -> str | None:
        size = wintypes.ULONG(0)
        get_user_name_ex(name_format, None, ctypes.byref(size))
        if size.value == 0:
            return None
        buffer = ctypes.create_unicode_buffer(size.value)
        if not get_user_name_ex(name_format, buffer, ctypes.byref(size)):
            return None
        return buffer.value or None

    return read(_NAME_SAM_COMPATIBLE), read(_NAME_USER_PRINCIPAL)


def _split_sam_compatible(value: str | None) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    domain, sep, sam = value.partition("\\")
    if not sep:
        return value, None
    return sam or None, domain or None


def detect_windows_ad(settings: object | None = None) -> DetectorResult:
    """Detect generic Windows AD facts without mapping to organization identities."""
    sam_compatible, local_upn = _windows_logon_names()
    local_sam, local_domain = _split_sam_compatible(sam_compatible)
    probe = _run_powershell_probe()
    facts = make_identity_facts(
        sam=probe.sam or local_sam,
        domain=probe.domain or local_domain,
        mail=probe.mail,
        user_principal_name=probe.upn or local_upn,
        proxy_addresses=probe.proxy_addresses or [],
        diagnostics=[f"windows_ad: {error}" for error in probe.errors or []],
    )
    if probe.lookup_completed:
        outcome = "complete"
    elif facts_have_values(facts):
        outcome = "partial"
    else:
        outcome = "failed"
    return DetectorResult(detector="windows_ad", facts=facts, outcome=outcome)


def resolve_primary_identity(
    *,
    name: str,
    detected: str | None,
    explicit: str | None,
    compare: CompareMode = "exact",
) -> tuple[str | None, str]:
    """Apply effective-value resolution for a primary identity.

    Returns (effective_value, source) where source is one of
    'detected', 'aligned', 'diverged', or 'unresolved'.
    """
    if explicit is not None and explicit != "":
        if detected is not None and detected != "":
            return (
                explicit,
                "aligned" if values_equal(explicit, detected, compare) else "diverged",
            )
        return explicit, "aligned"
    if detected is not None and detected != "":
        return detected, "detected"
    return None, "unresolved"
