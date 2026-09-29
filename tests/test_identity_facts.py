"""Tests for generic identity fact helpers."""

from __future__ import annotations

from dotfill.identity_facts import (
    IdentityFacts,
    collect_emails,
    facts_have_values,
    make_identity_facts,
)


def test_collect_emails_from_all_sources_without_company_domains() -> None:
    emails = collect_emails(
        mail="First.Last@example.com",
        user_principal_name="first.last@login.example.com",
        proxy_addresses=[
            "SMTP:first.last@example.com",
            "smtp:alias@example.org",
            "other@example.net",
        ],
    )

    assert emails == [
        "first.last@example.com",
        "first.last@login.example.com",
        "alias@example.org",
        "other@example.net",
    ]


def test_collect_emails_deduplicates_case_insensitively() -> None:
    emails = collect_emails(
        mail="User@Example.com",
        user_principal_name="user@example.com",
        proxy_addresses=["SMTP:USER@example.com", "second@example.com"],
    )

    assert emails == ["user@example.com", "second@example.com"]


def test_collect_emails_ignores_non_smtp_typed_proxy_addresses() -> None:
    emails = collect_emails(
        proxy_addresses=[
            "X500:/o=example/ou=exchange/cn=recipients/cn=user@example.com",
            "SIP:user@example.com",
            "smtp:alias@example.org",
        ],
    )

    assert emails == ["alias@example.org"]


def test_make_identity_facts_derives_emails() -> None:
    facts = make_identity_facts(
        sam="jdoe",
        domain="CORP",
        mail="jdoe@example.com",
        proxy_addresses=["smtp:john.doe@example.org"],
        diagnostics=["diag"],
    )

    assert facts.sam == "jdoe"
    assert facts.domain == "CORP"
    assert facts.emails == ["jdoe@example.com", "john.doe@example.org"]
    assert facts.diagnostics == ["diag"]


def test_facts_have_values() -> None:
    assert facts_have_values(IdentityFacts()) is False
    assert facts_have_values(IdentityFacts(diagnostics=["x"])) is False
    assert facts_have_values(make_identity_facts(user_principal_name="a@example.com"))
