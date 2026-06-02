"""Load, merge, and validate generic TOML configuration."""

from __future__ import annotations

import os
import re
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from .config_merge import merge_config_layers
from .config_models import (
    CompareMode,
    DerivedVariableDefinition,
    DisplayMode,
    EffectiveConfig,
    IdentityDefinition,
    IdentityDetectorConfig,
    ImportAliasDefinition,
    ServiceDefinition,
    TargetConfig,
)
from .config_paths import ConfigContext
from .envdoc import is_valid_var_name
from .errors import ConfigLoadError, ConfigSchemaError

SUPPORTED_VERSION = 1
SUPPORTED_IDENTITY_SOURCES = {
    "windows_ad.email_by_domain",
    "local_part",
    "literal",
    "env",
    "windows_ad.sam",
    "windows_ad.domain",
}

_SERVICE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_PLACEHOLDER_RE = re.compile(r"\{([^{}]+)\}")
_TOP_LEVEL_KEYS = {
    "version",
    "name",
    "target",
    "identity",
    "identities",
    "derived",
    "services",
    "import_aliases",
}
_IDENTITY_SOURCE_FIELDS = {
    "windows_ad.email_by_domain": {"domain"},
    "local_part": {"from"},
    "literal": {"value"},
    "env": {"name"},
    "windows_ad.sam": set(),
    "windows_ad.domain": set(),
}
_METADATA_FIELDS = {"display", "compare"}
_DISPLAY_VALUES = {"plain", "masked"}
_COMPARE_VALUES = {"exact", "casefold"}
_SERVICE_FIELDS = {
    "auth",
    "display_name",
    "enabled",
    "icon",
    "test_url",
    "tls_verify",
    "token_url",
    "token_var",
}


def load_effective_config(context: ConfigContext) -> EffectiveConfig:
    """Load `config_common.toml` and `config.toml` for a resolved context."""
    layers = [
        _load_toml_file(context.common_config_path),
        _load_toml_file(context.user_config_path),
    ]
    present_layers = [layer for layer in layers if layer is not None]
    merged = merge_config_layers(present_layers)
    return build_effective_config(merged)


def build_effective_config(data: Mapping[str, Any]) -> EffectiveConfig:
    """Validate merged TOML data and return an effective config."""
    _reject_unknown_keys(data, _TOP_LEVEL_KEYS, "config")
    name = _optional_str(data, "name", "name")
    target = _build_target(_optional_table(data, "target", "target"))
    detector_cfg = _build_identity_detectors(
        _optional_table(data, "identity", "identity")
    )
    identities = _build_identities(_optional_table(data, "identities", "identities"))
    derived = _build_derived(
        _optional_table(data, "derived", "derived"),
        identities=identities,
    )
    services = _build_services(
        _optional_table(data, "services", "services"),
        identities=identities,
    )
    aliases = _build_import_aliases(
        _optional_table(data, "import_aliases", "import_aliases"),
        services=services,
        derived=derived,
    )
    _validate_ad_detector_dependencies(detector_cfg, identities)
    return EffectiveConfig(
        name=name,
        target=target,
        identity_detectors=detector_cfg,
        identities=identities,
        derived_variables=derived,
        services=services,
        import_aliases=aliases,
    )


def _load_toml_file(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigLoadError(f"{path}: TOML parse error: {exc}") from exc
    except OSError as exc:
        raise ConfigLoadError(f"{path}: failed to read config: {exc}") from exc
    version = data.get("version")
    if version != SUPPORTED_VERSION:
        raise ConfigSchemaError(
            f"{path}: version must be {SUPPORTED_VERSION}; got {version!r}"
        )
    return data


def _build_target(data: Mapping[str, Any]) -> TargetConfig:
    _reject_unknown_keys(data, {"default_env_path"}, "target")
    raw_path = _optional_str(data, "default_env_path", "target.default_env_path")
    return TargetConfig(
        default_env_path=_resolve_configured_path(raw_path) if raw_path else None
    )


def _build_identity_detectors(data: Mapping[str, Any]) -> IdentityDetectorConfig:
    _reject_unknown_keys(data, {"detectors"}, "identity")
    detectors = _optional_table(data, "detectors", "identity.detectors")
    _reject_unknown_keys(detectors, {"windows_ad"}, "identity.detectors")
    windows_ad = _optional_table(
        detectors, "windows_ad", "identity.detectors.windows_ad"
    )
    _reject_unknown_keys(windows_ad, {"enabled"}, "identity.detectors.windows_ad")
    enabled = _optional_bool(
        windows_ad,
        "enabled",
        "identity.detectors.windows_ad.enabled",
        default=True,
    )
    return IdentityDetectorConfig(windows_ad_enabled=enabled)


def _build_identities(data: Mapping[str, Any]) -> dict[str, IdentityDefinition]:
    out: dict[str, IdentityDefinition] = {}
    for name in sorted(data):
        section = _required_table(data, name, f"identities.{name}")
        _validate_var_name(name, f"identities.{name}")
        enabled = _optional_bool(
            section, "enabled", f"identities.{name}.enabled", default=True
        )
        source = _optional_str(section, "source", f"identities.{name}.source")
        if source is not None:
            if source not in SUPPORTED_IDENTITY_SOURCES:
                raise ConfigSchemaError(
                    f"identities.{name}.source: unsupported identity source {source!r}"
                )
            allowed = (
                {"enabled", "source"}
                | _METADATA_FIELDS
                | _IDENTITY_SOURCE_FIELDS[source]
            )
        else:
            allowed = {"enabled"} | _METADATA_FIELDS
        _reject_unknown_keys(section, allowed, f"identities.{name}")
        if not enabled:
            continue
        display = _optional_display(
            section, "display", f"identities.{name}.display"
        )
        compare = _optional_compare(
            section, "compare", f"identities.{name}.compare"
        )
        if source is None:
            source = _required_str(section, "source", f"identities.{name}.source")
        params = {
            str(k): v
            for k, v in section.items()
            if k not in {"enabled", "source", "display", "compare"}
        }
        _validate_identity_source_fields(name, source, params)
        out[name] = IdentityDefinition(
            name=name,
            enabled=True,
            source=source,
            params=params,
            display=display,
            compare=compare,
        )
    _validate_identity_references(out)
    return out


def _build_derived(
    data: Mapping[str, Any],
    *,
    identities: dict[str, IdentityDefinition],
) -> dict[str, DerivedVariableDefinition]:
    out: dict[str, DerivedVariableDefinition] = {}
    for name in sorted(data):
        section = _required_table(data, name, f"derived.{name}")
        _reject_unknown_keys(
            section,
            {"enabled", "from_identity"} | _METADATA_FIELDS,
            f"derived.{name}",
        )
        _validate_var_name(name, f"derived.{name}")
        enabled = _optional_bool(
            section, "enabled", f"derived.{name}.enabled", default=True
        )
        if not enabled:
            continue
        display = _optional_display(section, "display", f"derived.{name}.display")
        compare = _optional_compare(section, "compare", f"derived.{name}.compare")
        source = _required_str(section, "from_identity", f"derived.{name}.from_identity")
        if source not in identities:
            raise ConfigSchemaError(
                f"derived.{name}.from_identity: unknown or disabled identity {source!r}"
            )
        out[name] = DerivedVariableDefinition(
            variable_name=name,
            source_identity_name=source,
            display=display,
            compare=compare,
        )
    return out


def _build_services(
    data: Mapping[str, Any],
    *,
    identities: dict[str, IdentityDefinition],
) -> dict[str, ServiceDefinition]:
    out: dict[str, ServiceDefinition] = {}
    for service_id in sorted(data):
        section = _required_table(data, service_id, f"services.{service_id}")
        _reject_unknown_keys(section, _SERVICE_FIELDS, f"services.{service_id}")
        if not _SERVICE_ID_RE.fullmatch(service_id):
            raise ConfigSchemaError(f"services.{service_id}: invalid service id")
        enabled = _optional_bool(
            section, "enabled", f"services.{service_id}.enabled", default=True
        )
        if not enabled:
            continue
        token_var = _required_str(
            section, "token_var", f"services.{service_id}.token_var"
        )
        _validate_var_name(token_var, f"services.{service_id}.token_var")
        token_url = _required_str(
            section, "token_url", f"services.{service_id}.token_url"
        )
        test_url = _required_str(
            section, "test_url", f"services.{service_id}.test_url"
        )
        display_name = _required_str(
            section, "display_name", f"services.{service_id}.display_name"
        )
        auth = _optional_str(section, "auth", f"services.{service_id}.auth")
        if auth is None:
            auth = "bearer"
        if auth != "bearer":
            raise ConfigSchemaError(
                f"services.{service_id}.auth: unsupported auth value {auth!r}"
            )
        icon = _optional_str(section, "icon", f"services.{service_id}.icon")
        tls_verify = _optional_bool(
            section, "tls_verify", f"services.{service_id}.tls_verify", default=True
        )
        _validate_url_placeholders(token_url, identities, f"services.{service_id}.token_url")
        _validate_url_placeholders(test_url, identities, f"services.{service_id}.test_url")
        out[service_id] = ServiceDefinition(
            service_id=service_id,
            token_var=token_var,
            token_url_template=token_url,
            test_url_template=test_url,
            display_name=display_name,
            auth="bearer",
            icon=icon,
            tls_verify=tls_verify,
        )
    return out


def _build_import_aliases(
    data: Mapping[str, Any],
    *,
    services: dict[str, ServiceDefinition],
    derived: dict[str, DerivedVariableDefinition],
) -> dict[str, ImportAliasDefinition]:
    targets = {svc.token_var for svc in services.values()} | set(derived)
    out: dict[str, ImportAliasDefinition] = {}
    for source_key in sorted(data):
        section = _required_table(data, source_key, f"import_aliases.{source_key}")
        _reject_unknown_keys(
            section,
            {"enabled", "target"},
            f"import_aliases.{source_key}",
        )
        _validate_var_name(source_key, f"import_aliases.{source_key}")
        enabled = _optional_bool(
            section,
            "enabled",
            f"import_aliases.{source_key}.enabled",
            default=True,
        )
        if not enabled:
            continue
        target = _required_str(
            section, "target", f"import_aliases.{source_key}.target"
        )
        _validate_var_name(target, f"import_aliases.{source_key}.target")
        if target not in targets:
            raise ConfigSchemaError(
                f"import_aliases.{source_key}.target: {target!r} is not an enabled import target"
            )
        out[source_key] = ImportAliasDefinition(
            source_key=source_key,
            target_key=target,
        )
    return out


def _validate_identity_source_fields(
    name: str,
    source: str,
    params: Mapping[str, object],
) -> None:
    if source == "windows_ad.email_by_domain":
        _require_param_str(params, "domain", f"identities.{name}.domain")
    elif source == "local_part":
        _require_param_str(params, "from", f"identities.{name}.from")
    elif source == "literal":
        _require_param_str(params, "value", f"identities.{name}.value")
    elif source == "env":
        env_name = _require_param_str(params, "name", f"identities.{name}.name")
        _validate_var_name(env_name, f"identities.{name}.name")


def _validate_identity_references(
    identities: dict[str, IdentityDefinition],
) -> None:
    for name, definition in identities.items():
        if definition.source != "local_part":
            continue
        source_identity = str(definition.params["from"])
        if source_identity not in identities:
            raise ConfigSchemaError(
                f"identities.{name}.from: unknown or disabled identity {source_identity!r}"
            )


def _validate_ad_detector_dependencies(
    detector_cfg: IdentityDetectorConfig,
    identities: dict[str, IdentityDefinition],
) -> None:
    if detector_cfg.windows_ad_enabled:
        return
    for name, definition in identities.items():
        if definition.source.startswith("windows_ad."):
            raise ConfigSchemaError(
                f"identities.{name}.source: windows_ad detector is disabled"
            )


def _validate_url_placeholders(
    template: str,
    identities: dict[str, IdentityDefinition],
    path: str,
) -> None:
    for placeholder in _PLACEHOLDER_RE.findall(template):
        if placeholder not in identities:
            raise ConfigSchemaError(
                f"{path}: unknown or disabled identity placeholder {{{placeholder}}}"
            )


def _resolve_configured_path(value: str) -> Path:
    expanded = os.path.expandvars(value)
    path = Path(expanded).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve(strict=False)


def _reject_unknown_keys(
    data: Mapping[str, Any],
    allowed: set[str],
    path: str,
) -> None:
    unknown = sorted(str(key) for key in data if str(key) not in allowed)
    if unknown:
        key = unknown[0]
        raise ConfigSchemaError(f"{path}.{key}: unknown field")


def _required_table(data: Mapping[str, Any], key: str, path: str) -> Mapping[str, Any]:
    if key not in data:
        raise ConfigSchemaError(f"{path}: table is required")
    value = data[key]
    if not isinstance(value, Mapping):
        raise ConfigSchemaError(f"{path}: expected table")
    return value


def _optional_table(data: Mapping[str, Any], key: str, path: str) -> Mapping[str, Any]:
    if key not in data:
        return {}
    value = data[key]
    if not isinstance(value, Mapping):
        raise ConfigSchemaError(f"{path}: expected table")
    return value


def _required_str(data: Mapping[str, Any], key: str, path: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or value == "":
        raise ConfigSchemaError(f"{path}: non-empty string is required")
    return value


def _optional_str(data: Mapping[str, Any], key: str, path: str) -> str | None:
    if key not in data:
        return None
    value = data[key]
    if not isinstance(value, str):
        raise ConfigSchemaError(f"{path}: expected string")
    return value


def _optional_display(
    data: Mapping[str, Any],
    key: str,
    path: str,
) -> DisplayMode:
    value = _optional_str(data, key, path)
    if value is None:
        return "plain"
    if value not in _DISPLAY_VALUES:
        raise ConfigSchemaError(f"{path}: unsupported display value {value!r}")
    return cast(DisplayMode, value)


def _optional_compare(
    data: Mapping[str, Any],
    key: str,
    path: str,
) -> CompareMode:
    value = _optional_str(data, key, path)
    if value is None:
        return "exact"
    if value not in _COMPARE_VALUES:
        raise ConfigSchemaError(f"{path}: unsupported compare value {value!r}")
    return cast(CompareMode, value)


def _optional_bool(
    data: Mapping[str, Any],
    key: str,
    path: str,
    *,
    default: bool,
) -> bool:
    if key not in data:
        return default
    value = data[key]
    if not isinstance(value, bool):
        raise ConfigSchemaError(f"{path}: expected boolean")
    return value


def _require_param_str(
    params: Mapping[str, object],
    key: str,
    path: str,
) -> str:
    value = params.get(key)
    if not isinstance(value, str) or value == "":
        raise ConfigSchemaError(f"{path}: non-empty string is required")
    return value


def _validate_var_name(name: str, path: str) -> None:
    if not is_valid_var_name(name):
        raise ConfigSchemaError(f"{path}: {name!r} is not a valid variable name")
