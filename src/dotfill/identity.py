"""Windows AD fact detection and identity value resolution."""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass

from .identity_facts import ADFacts, make_ad_facts

log = logging.getLogger(__name__)

_POWERSHELL_SCRIPT = r"""
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
    Add-Type -AssemblyName System.DirectoryServices
    $searcher = New-Object System.DirectoryServices.DirectorySearcher
    $searcher.Filter = "(&(objectClass=user)(sAMAccountName=$sam))"
    $searcher.PropertiesToLoad.AddRange(@("mail", "proxyAddresses", "userPrincipalName"))
    $result = $searcher.FindOne()
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
    }
} catch {
    Write-Output ("ERR:" + $_.Exception.Message)
}
""".strip()


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
    try:
        proc = subprocess.run(  # noqa: S603 - controlled args
            [pwsh, "-NoProfile", "-NonInteractive", "-Command", _POWERSHELL_SCRIPT],
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
    *, name: str, detected: str | None, explicit: str | None
) -> tuple[str | None, str]:
    """Apply effective-value resolution for a primary identity.

    Returns (effective_value, source) where source is one of
    'detected', 'aligned', 'diverged', or 'unresolved'.
    """
    if explicit is not None and explicit != "":
        if detected is not None and detected != "":
            return explicit, "aligned" if explicit == detected else "diverged"
        return explicit, "aligned"
    if detected is not None and detected != "":
        return detected, "detected"
    return None, "unresolved"
