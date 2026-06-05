"""Effective state resolution from TOML config, identity facts, and `.env`."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import hmac
import json
from pathlib import Path

from .config import collect_managed_variable_names, resolve_url_template
from .config_loader import load_effective_config
from .config_models import AuthConfig, EffectiveConfig, ServiceDefinition
from .config_paths import ConfigContext, resolve_config_context
from .envdoc import EnvDocument
from .errors import DuplicateManagedVariableError, UnresolvedIdentityError
from .identity import detect_ad_facts, resolve_primary_identity
from .identity_facts import ADFacts
from .identity_rules import IdentityRuleResult, evaluate_identity_rules
from .models import (
    AppState,
    DerivedVariableState,
    PrimaryIdentityState,
    ServiceState,
    SessionState,
    TestResult,
)
from .paths import default_env_path
from .value_policy import mask_value, values_equal

DEFAULT_SERVICE_ICON = "key"


def _mask_token(value: str) -> str:
    return mask_value(value)


def service_icon(icon_key: str | None) -> str:
    return icon_key or DEFAULT_SERVICE_ICON


def service_test_fingerprint(
    *,
    service_id: str,
    token_var: str,
    resolved_test_url: str,
    auth_config: AuthConfig,
    test_headers: Mapping[str, str],
    tls_verify: bool,
    token: str,
    session_token: str,
    basic_username: str | None = None,
) -> str:
    """Return a non-secret, session-scoped fingerprint for cached test status."""
    token_digest = hmac.new(
        session_token.encode("utf-8"),
        token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    username_digest = (
        hmac.new(
            session_token.encode("utf-8"),
            basic_username.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if basic_username is not None
        else None
    )
    auth_payload: dict[str, object]
    kind = getattr(auth_config, "kind")
    if kind == "bearer":
        auth_payload = {"kind": "bearer"}
    elif kind == "header":
        auth_payload = {
            "kind": "header",
            "header": str(getattr(auth_config, "header")).casefold(),
        }
    elif kind == "basic":
        username_identity = getattr(auth_config, "username_identity")
        auth_payload = {
            "kind": "basic",
            "username_identity": username_identity,
            "username_source": "identity" if username_identity else "literal",
            "username": username_digest,
        }
    else:
        auth_payload = {"kind": str(kind)}
    header_payload = [
        [name.casefold(), value]
        for name, value in sorted(
            test_headers.items(),
            key=lambda item: item[0].casefold(),
        )
    ]
    payload = {
        "service_id": service_id,
        "token_var": token_var,
        "resolved_test_url": resolved_test_url,
        "auth": auth_payload,
        "test_headers": header_payload,
        "tls_verify": tls_verify,
        "token": token_digest,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _basic_fingerprint_username(
    service: ServiceDefinition,
    identity_values: Mapping[str, str | None],
) -> str | None:
    if service.auth.kind != "basic":
        return None
    if service.auth.username is not None:
        return service.auth.username
    if service.auth.username_identity is None:
        return None
    value = identity_values.get(service.auth.username_identity)
    if value is None or value == "":
        return None
    return value


def _needs_ad_facts(config: EffectiveConfig) -> bool:
    return any(
        identity.source.startswith("windows_ad.")
        for identity in config.identities.values()
    )


def _resolve_env_path(
    *,
    config: EffectiveConfig,
    env_path_override: Path | None,
) -> Path:
    if env_path_override is not None:
        return env_path_override.expanduser().resolve(strict=False)
    if config.target.default_env_path is not None:
        return config.target.default_env_path
    return default_env_path()


def build_primary_identities(
    doc: EnvDocument,
    config: EffectiveConfig,
    detected: dict[str, IdentityRuleResult],
) -> list[PrimaryIdentityState]:
    """Resolve configured identities using explicit `.env` overrides first."""
    out: list[PrimaryIdentityState] = []
    for name in sorted(detected):
        definition = config.identities[name]
        explicit = doc.get(name)
        det = detected[name].value
        effective, source = resolve_primary_identity(
            name=name,
            detected=det,
            explicit=explicit,
            compare=definition.compare,
        )
        out.append(
            PrimaryIdentityState(
                name=name,
                detected_value=det,
                explicit_value=explicit,
                effective_value=effective,
                source=source,  # type: ignore[arg-type]
            )
        )
    return out


def build_derived_states(
    doc: EnvDocument,
    config: EffectiveConfig,
    identity_values: dict[str, str | None],
) -> list[DerivedVariableState]:
    out: list[DerivedVariableState] = []
    for name in sorted(config.derived_variables):
        definition = config.derived_variables[name]
        current = doc.get(name)
        source_value = identity_values.get(definition.source_identity_name)
        if source_value is None or source_value == "":
            raise UnresolvedIdentityError(
                f"Derived variable {name} requires unresolved identity "
                f"{definition.source_identity_name}"
            )
        if current in (None, ""):
            status = "missing"
        elif values_equal(current, source_value, definition.compare):
            status = "aligned"
        else:
            status = "diverged"
        out.append(
            DerivedVariableState(
                variable_name=name,
                current_value=current,
                computed_default=source_value,
                source_identity_name=definition.source_identity_name,
                status=status,
            )
        )
    return out


def build_service_states(
    doc: EnvDocument,
    config: EffectiveConfig,
    identity_values: dict[str, str | None],
    *,
    test_results: dict[str, TestResult] | None = None,
    session_token: str,
) -> list[ServiceState]:
    out: list[ServiceState] = []
    for service_id in sorted(
        config.services,
        key=lambda key: config.services[key].display_name.lower(),
    ):
        service = config.services[service_id]
        token_value = doc.get(service.token_var)
        token_present = bool(token_value)
        masked = _mask_token(token_value) if token_present else None
        resolved_token_url = resolve_url_template(
            service.token_url_template,
            identity_values,
            allowed_identities=config.identities,
        )
        resolved_test_url = resolve_url_template(
            service.test_url_template,
            identity_values,
            allowed_identities=config.identities,
        )
        if token_present:
            fingerprint = service_test_fingerprint(
                service_id=service_id,
                token_var=service.token_var,
                resolved_test_url=resolved_test_url,
                auth_config=service.auth,
                test_headers=service.test_headers,
                tls_verify=service.tls_verify,
                token=token_value,
                session_token=session_token,
                basic_username=_basic_fingerprint_username(
                    service,
                    identity_values,
                ),
            )
            cached = (test_results or {}).get(service_id)
        else:
            fingerprint = None
            cached = None
        if cached is not None and cached.fingerprint == fingerprint:
            test_status = cached.status
        else:
            test_status = "missing" if not token_present else "set"
        out.append(
            ServiceState(
                service_id=service_id,
                display_name=service.display_name,
                token_var=service.token_var,
                token_present=token_present,
                masked_token=masked,
                resolved_token_url=resolved_token_url,
                resolved_test_url=resolved_test_url,
                test_status=test_status,  # type: ignore[arg-type]
                icon=service_icon(service.icon),
            )
        )
    return out


def build_app_state(
    config_context: ConfigContext | None,
    session: SessionState,
    *,
    env_path_override: Path | None = None,
    ad_facts_override: ADFacts | None = None,
) -> AppState:
    """The single pipeline producing AppState. Used by CLI and API alike."""
    context = config_context or resolve_config_context()
    config = load_effective_config(context)
    env_path = _resolve_env_path(config=config, env_path_override=env_path_override)
    doc = EnvDocument.from_path(env_path)

    managed = collect_managed_variable_names(config)
    duplicates = doc.duplicates(managed)
    if duplicates:
        key = next(iter(duplicates))
        raise DuplicateManagedVariableError(key=key, line_numbers=duplicates[key])

    ad_facts = None
    if _needs_ad_facts(config):
        ad_facts = ad_facts_override if ad_facts_override is not None else detect_ad_facts()
    explicit_identity_values = {name: doc.get(name) for name in config.identities}
    detected = evaluate_identity_rules(
        config.identities,
        ad_facts=ad_facts,
        explicit_values=explicit_identity_values,
    )
    identities = build_primary_identities(doc, config, detected)
    identity_values: dict[str, str | None] = {
        identity.name: identity.effective_value for identity in identities
    }
    derived = build_derived_states(doc, config, identity_values)
    services = build_service_states(
        doc,
        config,
        identity_values,
        test_results=session.test_results,
        session_token=session.token,
    )
    return AppState(
        env_path=env_path,
        config_context=context,
        config_name=config.name,
        env_doc=doc,
        effective_config=config,
        identities=identities,
        derived=derived,
        services=services,
        session=session,
    )
