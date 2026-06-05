"""Generic TOML configuration domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

DisplayMode = Literal["plain", "masked"]
CompareMode = Literal["exact", "casefold"]
AuthKind = Literal["bearer", "header", "basic"]


@dataclass(frozen=True)
class TargetConfig:
    """Target `.env` configuration."""

    default_env_path: Path | None = None


@dataclass(frozen=True)
class IdentityDetectorConfig:
    """Configured identity detector switches."""

    windows_ad_enabled: bool = True


@dataclass(frozen=True)
class IdentityDefinition:
    """One configured dynamic identity."""

    name: str
    source: str
    params: dict[str, object] = field(default_factory=dict)
    enabled: bool = True
    display: DisplayMode = "plain"
    compare: CompareMode = "exact"


@dataclass(frozen=True)
class DerivedVariableDefinition:
    """One `.env` variable derived from an identity."""

    variable_name: str
    source_identity_name: str
    display: DisplayMode = "plain"
    compare: CompareMode = "exact"


@dataclass(frozen=True)
class AuthConfig:
    """One service-test authentication configuration."""

    kind: AuthKind = "bearer"
    header: str | None = None
    username_identity: str | None = None
    username: str | None = None


@dataclass(frozen=True)
class ServiceDefinition:
    """One managed service token definition."""

    service_id: str
    token_var: str
    token_url_template: str
    test_url_template: str
    display_name: str
    auth: AuthConfig = field(default_factory=AuthConfig)
    test_headers: dict[str, str] = field(default_factory=dict)
    icon: str | None = None
    tls_verify: bool = True


@dataclass(frozen=True)
class ImportAliasDefinition:
    """One import heuristic mapping."""

    source_key: str
    target_key: str


@dataclass(frozen=True)
class EffectiveConfig:
    """Merged, validated generic dotfill configuration."""

    name: str | None
    target: TargetConfig
    identity_detectors: IdentityDetectorConfig
    identities: dict[str, IdentityDefinition]
    derived_variables: dict[str, DerivedVariableDefinition]
    services: dict[str, ServiceDefinition]
    import_aliases: dict[str, ImportAliasDefinition]
