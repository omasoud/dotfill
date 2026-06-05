"""Domain models for dotfill.

A mix of plain dataclasses (for core domain) and Pydantic models (for API
boundary use). SecretStr is used for token-like inbound values.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, SecretStr

from .config_models import EffectiveConfig
from .config_paths import ConfigContext

# ---- Identity models -------------------------------------------------------


@dataclass
class PrimaryIdentityState:
    name: str
    detected_value: str | None
    explicit_value: str | None
    effective_value: str | None
    source: Literal["detected", "aligned", "diverged", "unresolved"]


# ---- Derived variable models -----------------------------------------------


@dataclass
class DerivedVariableState:
    variable_name: str
    current_value: str | None
    computed_default: str | None
    source_identity_name: str
    status: Literal["missing", "aligned", "diverged", "unresolved"]


TestStatus = Literal["missing", "set", "testing", "working", "failed"]


@dataclass
class ServiceState:
    service_id: str
    display_name: str
    token_var: str
    token_present: bool
    masked_token: str | None
    resolved_token_url: str
    resolved_test_url: str
    test_status: TestStatus
    icon: str | None = None


@dataclass
class TestResult:
    status: TestStatus
    http_status: int | None = None
    error_message: str | None = None
    fingerprint: str | None = None


# ---- Import models ---------------------------------------------------------


ImportStatus = Literal["new", "replace", "no_change", "unmapped"]
MappingKind = Literal["exact", "heuristic", "none"]


@dataclass
class ImportMappingRow:
    source_key: str
    target_key: str | None
    mapping_kind: MappingKind
    locked: bool
    status: ImportStatus
    masked_source_value: str | None


@dataclass
class ImportScanSession:
    scan_id: str
    source_label: str
    candidates: dict[str, SecretStr]  # source variable name -> source value
    proposed_rows: list[ImportMappingRow]
    occupied_targets: list[str]  # managed targets that have non-empty values in current .env


# ---- Session and app state -------------------------------------------------


@dataclass
class SessionState:
    token: str
    backup_created: bool = False
    backup_path: Path | None = None
    test_results: dict[str, TestResult] = field(default_factory=dict)
    import_scans: dict[str, ImportScanSession] = field(default_factory=dict)
    queue_test_all_on_dashboard_load: bool = False


# AppState is defined here as a forward-friendly dataclass; EnvDocument is
# imported lazily where needed to avoid an import cycle at module load.
@dataclass
class AppState:
    env_path: Path
    config_context: ConfigContext
    config_name: str | None
    env_doc: object  # EnvDocument, but avoid circular import
    effective_config: EffectiveConfig
    identities: list[PrimaryIdentityState]
    derived: list[DerivedVariableState]
    services: list[ServiceState]
    session: SessionState


# ---- Pydantic API payloads -------------------------------------------------


class SaveTokenRequest(BaseModel):
    """Body of POST /api/token/{service_id}."""

    model_config = ConfigDict(extra="forbid")
    token: SecretStr


class ScanDroppedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filename: str
    content: SecretStr


class ImportMappingChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sourceKey: str
    targetKey: str | None  # None means "Skip"


class CommitImportRequest(BaseModel):
    """Body of POST /api/import/commit. Must NOT contain raw source values."""

    model_config = ConfigDict(extra="forbid")
    scanId: str
    mappings: list[ImportMappingChoice]


class ImportTestRequest(BaseModel):
    """Body of POST /api/import/test. Must NOT contain raw source values."""

    model_config = ConfigDict(extra="forbid")
    scanId: str
    sourceKey: str
    targetKey: str
