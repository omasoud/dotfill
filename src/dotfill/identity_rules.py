"""Evaluate configured dynamic identity rules."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field

from .config_models import IdentityDefinition
from .errors import ConfigSchemaError
from .identity_facts import ADFacts


@dataclass(frozen=True)
class IdentityRuleResult:
    """Detected value produced by one configured identity rule."""

    name: str
    value: str | None
    diagnostics: list[str] = field(default_factory=list)


def evaluate_identity_rules(
    identities: Mapping[str, IdentityDefinition],
    *,
    ad_facts: ADFacts | None = None,
    environ: Mapping[str, str] | None = None,
    explicit_values: Mapping[str, str | None] | None = None,
) -> dict[str, IdentityRuleResult]:
    """Evaluate enabled identity definitions into detected identity values."""
    env = os.environ if environ is None else environ
    explicit = {} if explicit_values is None else explicit_values
    ordered = _topological_identity_order(identities)
    values: dict[str, IdentityRuleResult] = {}
    for name in ordered:
        definition = identities[name]
        values[name] = _evaluate_one(
            definition,
            values,
            ad_facts=ad_facts,
            environ=env,
            explicit_values=explicit,
        )
    return values


def _topological_identity_order(
    identities: Mapping[str, IdentityDefinition],
) -> list[str]:
    order: list[str] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(name: str) -> None:
        if name in visited:
            return
        if name in visiting:
            raise ConfigSchemaError(f"identities.{name}: identity dependency cycle")
        if name not in identities:
            raise ConfigSchemaError(f"identities.{name}: unknown identity reference")
        visiting.add(name)
        dependency = _identity_dependency(identities[name])
        if dependency is not None:
            if dependency not in identities:
                raise ConfigSchemaError(
                    f"identities.{name}: unknown or disabled identity {dependency!r}"
                )
            visit(dependency)
        visiting.remove(name)
        visited.add(name)
        order.append(name)

    for name in sorted(identities):
        visit(name)
    return order


def _identity_dependency(definition: IdentityDefinition) -> str | None:
    if definition.source == "local_part":
        value = definition.params.get("from")
        return str(value) if value is not None else None
    return None


def _evaluate_one(
    definition: IdentityDefinition,
    values: Mapping[str, IdentityRuleResult],
    *,
    ad_facts: ADFacts | None,
    environ: Mapping[str, str],
    explicit_values: Mapping[str, str | None],
) -> IdentityRuleResult:
    source = definition.source
    diagnostics: list[str] = []
    if source == "literal":
        value = str(definition.params.get("value", ""))
    elif source == "env":
        env_name = str(definition.params.get("name", ""))
        value = environ.get(env_name)
    elif source == "local_part":
        source_name = str(definition.params.get("from", ""))
        source_value = _effective_upstream_value(
            detected=values[source_name].value,
            explicit=explicit_values.get(source_name),
        )
        value = (
            source_value.split("@", 1)[0]
            if source_value and "@" in source_value
            else None
        )
    elif source == "windows_ad.email_by_domain":
        value = _email_by_domain(ad_facts, str(definition.params.get("domain", "")))
        diagnostics.extend(ad_facts.diagnostics if ad_facts is not None else [])
    elif source == "windows_ad.sam":
        value = ad_facts.sam if ad_facts is not None else None
        diagnostics.extend(ad_facts.diagnostics if ad_facts is not None else [])
    elif source == "windows_ad.domain":
        value = ad_facts.domain if ad_facts is not None else None
        diagnostics.extend(ad_facts.diagnostics if ad_facts is not None else [])
    else:
        raise ConfigSchemaError(
            f"identities.{definition.name}.source: unsupported identity source {source!r}"
        )
    return IdentityRuleResult(
        name=definition.name,
        value=value or None,
        diagnostics=diagnostics,
    )


def _effective_upstream_value(
    *,
    detected: str | None,
    explicit: str | None,
) -> str | None:
    if explicit is not None and explicit != "":
        return explicit
    if detected is not None and detected != "":
        return detected
    return None


def _email_by_domain(ad_facts: ADFacts | None, domain: str) -> str | None:
    if ad_facts is None:
        return None
    normalized_domain = domain.lower().removeprefix("@")
    suffix = "@" + normalized_domain
    return next((email for email in ad_facts.emails if email.endswith(suffix)), None)
