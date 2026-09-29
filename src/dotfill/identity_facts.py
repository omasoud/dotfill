"""Generic identity detector fact models."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

DetectorOutcome = Literal["complete", "partial", "failed"]

_ADDRESS_TYPE_RE = re.compile(r"^[A-Za-z0-9]+:")


@dataclass(frozen=True)
class IdentityFacts:
    """Generic directory facts reported by an identity detector."""

    sam: str | None = None
    domain: str | None = None
    mail: str | None = None
    user_principal_name: str | None = None
    proxy_addresses: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DetectorResult:
    """Facts from one detector run plus how far the run got."""

    detector: str
    facts: IdentityFacts
    outcome: DetectorOutcome


def collect_emails(
    *,
    mail: str | None = None,
    user_principal_name: str | None = None,
    proxy_addresses: list[str] | None = None,
) -> list[str]:
    """Collect normalized, de-duplicated email addresses in stable order.

    Proxy addresses keep only SMTP entries; other typed addresses such as
    `X500:` are ignored.
    """
    out: list[str] = []
    seen: set[str] = set()

    def add(raw: str | None) -> None:
        if raw is None:
            return
        email = raw.strip().lower()
        if "@" not in email or email in seen:
            return
        seen.add(email)
        out.append(email)

    add(mail)
    add(user_principal_name)
    for address in proxy_addresses or []:
        if address.lower().startswith("smtp:"):
            add(address[5:])
        elif not _ADDRESS_TYPE_RE.match(address):
            add(address)
    return out


def make_identity_facts(
    *,
    sam: str | None = None,
    domain: str | None = None,
    mail: str | None = None,
    user_principal_name: str | None = None,
    proxy_addresses: list[str] | None = None,
    diagnostics: list[str] | None = None,
) -> IdentityFacts:
    """Build `IdentityFacts` while deriving the normalized email list."""
    proxy = list(proxy_addresses or [])
    return IdentityFacts(
        sam=sam,
        domain=domain,
        mail=mail,
        user_principal_name=user_principal_name,
        proxy_addresses=proxy,
        emails=collect_emails(
            mail=mail,
            user_principal_name=user_principal_name,
            proxy_addresses=proxy,
        ),
        diagnostics=list(diagnostics or []),
    )


def facts_have_values(facts: IdentityFacts) -> bool:
    """Return whether *facts* carry any usable identity value."""
    return bool(facts.sam or facts.domain or facts.emails)
