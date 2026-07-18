"""Windows AD fact detection and identity value resolution."""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass

from .config_models import CompareMode
from .identity_facts import ADFacts, make_ad_facts
from .value_policy import values_equal

log = logging.getLogger(__name__)

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
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return _RawProbe(errors=[f"PowerShell invocation failed: {exc}"])
    out = proc.stdout or ""
    probe = _RawProbe(errors=[], proxy_addresses=[])
    for raw_line in out.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("SAM:"):
            probe.sam = line[4:].strip() or None
        elif line.startswith("DOMAIN:"):
            probe.domain = line[7:].strip() or None
        elif line.startswith("MAIL:"):
            probe.mail = line[5:].strip() or None
        elif line.startswith("UPN:"):
            probe.upn = line[4:].strip() or None
        elif line.startswith("PROXY:"):
            addr = line[6:].strip()
            if addr:
                probe.proxy_addresses = (probe.proxy_addresses or []) + [addr]
        elif line.startswith("ERR:"):
            probe.errors = (probe.errors or []) + [line[4:].strip()]
    if proc.returncode != 0:
        probe.errors = (probe.errors or []) + [
            f"PowerShell exit code {proc.returncode}"
        ]
        if proc.stderr:
            probe.errors.append(proc.stderr.strip())
    return probe


def detect_ad_facts() -> ADFacts:
    """Detect generic Windows AD facts without mapping to organization identities."""
    probe = _run_powershell_probe()
    return make_ad_facts(
        sam=probe.sam,
        domain=probe.domain,
        mail=probe.mail,
        user_principal_name=probe.upn,
        proxy_addresses=probe.proxy_addresses or [],
        diagnostics=list(probe.errors or []),
    )


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
