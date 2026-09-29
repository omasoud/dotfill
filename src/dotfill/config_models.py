"""Generic TOML configuration domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

DisplayMode = Literal["plain", "masked"]
CompareMode = Literal["exact", "casefold"]
AuthKind = Literal["bearer", "header", "basic"]
DetectorName = Literal["windows_ad", "entra"]
DETECTOR_NAMES: tuple[DetectorName, ...] = ("entra", "windows_ad")


@dataclass(frozen=True)
class TargetConfig:
    """Target `.env` configuration."""

    default_env_path: Path | None = None


@dataclass(frozen=True)
class WindowsAdDetectorConfig:
    """Windows Active Directory detector settings."""

    enabled: bool = True
    priority: int = 20


@dataclass(frozen=True)
class EntraDetectorConfig:
    """Entra ID (Microsoft Graph) detector settings."""

    enabled: bool = False
    priority: int = 10
    client_id: str | None = None
    tenant: str = "organizations"


@dataclass(frozen=True)
class IdentityDetectorConfig:
    """Configured identity detectors."""

    windows_ad: WindowsAdDetectorConfig = field(default_factory=WindowsAdDetectorConfig)
    entra: EntraDetectorConfig = field(default_factory=EntraDetectorConfig)

    def settings(self, name: DetectorName) -> WindowsAdDetectorConfig | EntraDetectorConfig:
        """Return the settings object for one detector."""
        return self.windows_ad if name == "windows_ad" else self.entra

    def is_enabled(self, name: DetectorName) -> bool:
        """Return whether the named detector is enabled."""
        return self.settings(name).enabled

    def enabled_in_priority_order(self) -> list[DetectorName]:
        """Return enabled detector names ordered by `(priority, name)`."""
        ranked = sorted(
            (self.settings(name).priority, name)
            for name in DETECTOR_NAMES
            if self.settings(name).enabled
        )
        return [name for _, name in ranked]


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
