"""Generic identity detector fact models."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ADFacts:
    """Generic Windows Active Directory facts for identity rules."""

    sam: str | None = None
    domain: str | None = None
    mail: str | None = None
    user_principal_name: str | None = None
    proxy_addresses: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)


def collect_ad_emails(
    *,
    mail: str | None = None,
    user_principal_name: str | None = None,
    proxy_addresses: list[str] | None = None,
) -> list[str]:
    """Collect normalized, de-duplicated AD email addresses in stable order."""
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
        else:
            add(address)
    return out


def make_ad_facts(
    *,
    sam: str | None = None,
    domain: str | None = None,
    mail: str | None = None,
    user_principal_name: str | None = None,
    proxy_addresses: list[str] | None = None,
    diagnostics: list[str] | None = None,
) -> ADFacts:
    """Build `ADFacts` while deriving the normalized email list."""
    proxy = list(proxy_addresses or [])
    return ADFacts(
        sam=sam,
        domain=domain,
        mail=mail,
        user_principal_name=user_principal_name,
        proxy_addresses=proxy,
        emails=collect_ad_emails(
            mail=mail,
            user_principal_name=user_principal_name,
            proxy_addresses=proxy,
        ),
        diagnostics=list(diagnostics or []),
    )
