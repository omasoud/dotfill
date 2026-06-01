"""Tests for generic identity fact helpers."""

from __future__ import annotations

from dotfill.identity_facts import collect_ad_emails, make_ad_facts


def test_collect_ad_emails_from_all_sources_without_company_domains() -> None:
    emails = collect_ad_emails(
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


def test_collect_ad_emails_deduplicates_case_insensitively() -> None:
    emails = collect_ad_emails(
        mail="User@Example.com",
        user_principal_name="user@example.com",
        proxy_addresses=["SMTP:USER@example.com", "second@example.com"],
    )

    assert emails == ["user@example.com", "second@example.com"]


def test_make_ad_facts_derives_emails() -> None:
    facts = make_ad_facts(
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
