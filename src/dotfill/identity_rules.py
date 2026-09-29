"""Evaluate configured dynamic identity rules."""

from __future__ import annotations

import os
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field

from .config_models import IdentityDefinition
from .errors import ConfigSchemaError
from .identity_facts import DetectorResult, IdentityFacts


@dataclass(frozen=True)
class IdentityRuleResult:
    """Detected value produced by one configured identity rule."""

    name: str
    value: str | None
    diagnostics: list[str] = field(default_factory=list)
    detector: str | None = None


def evaluate_identity_rules(
    identities: Mapping[str, IdentityDefinition],
    *,
    detector_results: Mapping[str, DetectorResult] | None = None,
    detector_order: Sequence[str] = (),
    pending_detectors: Collection[str] = (),
    environ: Mapping[str, str] | None = None,
    explicit_values: Mapping[str, str | None] | None = None,
) -> dict[str, IdentityRuleResult]:
    """Evaluate enabled identity definitions into detected identity values.

    `detector_order` lists enabled detectors in priority order for the
    detector-neutral `email_by_domain` source; `pending_detectors` names
    detectors whose run has not finished yet.
    """
    env = os.environ if environ is None else environ
    explicit = {} if explicit_values is None else explicit_values
    detectors = _DetectorView(
        results=detector_results or {},
        order=list(detector_order),
        pending=set(pending_detectors),
    )
    ordered = _topological_identity_order(identities)
    values: dict[str, IdentityRuleResult] = {}
    for name in ordered:
        definition = identities[name]
        values[name] = _evaluate_one(
            definition,
            values,
            detectors=detectors,
            environ=env,
            explicit_values=explicit,
        )
    return values


@dataclass(frozen=True)
class _DetectorView:
    results: Mapping[str, DetectorResult]
    order: list[str]
    pending: set[str]

    def facts(self, detector: str) -> IdentityFacts | None:
        result = self.results.get(detector)
        return result.facts if result is not None else None

    def diagnostics(self, detector: str) -> list[str]:
        out: list[str] = []
        facts = self.facts(detector)
        if facts is not None:
            out.extend(facts.diagnostics)
        if detector in self.pending:
            out.append(f"{detector}: detection pending")
        return out


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
    detectors: _DetectorView,
    environ: Mapping[str, str],
    explicit_values: Mapping[str, str | None],
) -> IdentityRuleResult:
    source = definition.source
    diagnostics: list[str] = []
    detector: str | None = None
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
    elif source == "email_by_domain":
        domain = str(definition.params.get("domain", ""))
        value = None
        for name in detectors.order:
            value = _email_by_domain(detectors.facts(name), domain)
            if value:
                detector = name
                break
            diagnostics.extend(detectors.diagnostics(name))
    elif source in {"windows_ad.email_by_domain", "entra.email_by_domain"}:
        name = source.split(".", 1)[0]
        value = _email_by_domain(
            detectors.facts(name), str(definition.params.get("domain", ""))
        )
        diagnostics.extend(detectors.diagnostics(name))
        detector = name if value else None
    elif source in {"windows_ad.sam", "windows_ad.domain"}:
        facts = detectors.facts("windows_ad")
        field_name = "sam" if source == "windows_ad.sam" else "domain"
        value = getattr(facts, field_name) if facts is not None else None
        diagnostics.extend(detectors.diagnostics("windows_ad"))
        detector = "windows_ad" if value else None
    else:
        raise ConfigSchemaError(
            f"identities.{definition.name}.source: unsupported identity source {source!r}"
        )
    return IdentityRuleResult(
        name=definition.name,
        value=value or None,
        diagnostics=[] if value else diagnostics,
        detector=detector,
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


def _email_by_domain(facts: IdentityFacts | None, domain: str) -> str | None:
    if facts is None:
        return None
    normalized_domain = domain.lower().removeprefix("@")
    suffix = "@" + normalized_domain
    return next((email for email in facts.emails if email.endswith(suffix)), None)
