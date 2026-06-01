# dotfill design specification

Status: Active generic implementation reference
Requirements: `requirements.md`
Task tracker: `implementation-plan.md`
Config schema: `../../docs/config-schema.md`

## Architecture

dotfill is a Python 3.14 package with:

- Typer CLI;
- FastAPI/Uvicorn local server;
- static HTML/CSS/vanilla JavaScript frontend;
- line-preserving `.env` parser/writer;
- TOML configuration loader and merger;
- generic identity fact/rule evaluation;
- explicit save, import, and service-test workflows.

The generic package contains no built-in services, identities, domains, token variables, or import aliases.

## Package Layout

```text
src/dotfill/
  api.py
  cli.py
  config.py
  config_loader.py
  config_merge.py
  config_models.py
  config_paths.py
  entrypoints.py
  envdoc.py
  errors.py
  identity.py
  identity_facts.py
  identity_rules.py
  import_scan.py
  logging_config.py
  models.py
  open_paths.py
  paths.py
  resolver.py
  save.py
  server.py
  service_test.py
  static/
```

## Configuration Model

`ConfigContext` carries:

- `config_root`;
- `profile`;
- `config_dir`;
- `common_config_path`;
- `user_config_path`.

Config root precedence:

1. CLI or entrypoint override.
2. `DOTFILL_CONFIG_ROOT`.
3. `platformdirs.user_config_dir("dotfill", appauthor=False, roaming=True)`.

Profile precedence:

1. CLI or entrypoint profile.
2. `DOTFILL_PROFILE`.
3. no profile.

When a wrapper passes `default_profile`, it is used only if neither CLI/profile input nor `DOTFILL_PROFILE` supplies a profile.

The final config directory is the config root, or `config_root / "profiles" / profile` when a profile is active. Direct `config_dir` entrypoint mode uses the supplied directory as final.

## TOML Loading

`load_effective_config(context)` reads:

1. `config_common.toml`
2. `config.toml`

Both files are optional. Every present file must include `version = 1`.

The merge is deterministic:

- scalar values override;
- tables merge by key;
- `enabled = false` removes inherited services, identities, derived variables, and aliases after merge.

Validation happens after merge and disable semantics.

## Domain Models

Config models live in `config_models.py`:

- `TargetConfig`
- `IdentityDetectorConfig`
- `IdentityDefinition`
- `DerivedVariableDefinition`
- `ServiceDefinition`
- `ImportAliasDefinition`
- `EffectiveConfig`

Runtime/API models live in `models.py`:

- `PrimaryIdentityState`
- `DerivedVariableState`
- `ServiceState`
- `TestResult`
- `ImportScanSession`
- `SessionState`
- `AppState`
- Pydantic API request payloads

`TestResult.fingerprint` is non-secret, session-scoped, and used only to decide whether cached status still applies.

## State Construction

`resolver.build_app_state(config_context, session, env_path_override=None)` is the shared state pipeline:

1. Load effective TOML config.
2. Resolve target `.env` path from CLI override, config target, or home fallback.
3. Read `.env` into `EnvDocument`.
4. Compute managed variables from enabled identity names, derived names, and service token variables.
5. Reject duplicate managed variables.
6. Run Windows AD detection only when an enabled identity source needs AD facts.
7. Evaluate identity rules.
8. Resolve explicit `.env` identity overrides against detected values.
9. Build derived variable states.
10. Resolve service token/test URLs.
11. Apply cached test status only when the service-test fingerprint matches.

State is rebuilt on each API state request, so TOML edits are visible after refresh.

## Identity Design

Windows AD probing returns generic facts:

- `sam`
- `domain`
- `mail`
- `user_principal_name`
- `proxy_addresses`
- normalized `emails`
- `diagnostics`

Identity rules map config to values. Supported sources:

- `literal`
- `env`
- `local_part`
- `windows_ad.email_by_domain`
- `windows_ad.sam`
- `windows_ad.domain`

Identity state source values are:

- `detected`
- `aligned`
- `diverged`
- `unresolved`

dotfill reads configured identity variables as explicit overrides but never writes identity variables automatically.

## `.env` Document Design

`EnvDocument` parses:

- assignments;
- comments;
- blank lines;
- unparsed lines.

It preserves unrelated content and supports targeted updates. `save_assignments` creates at most one backup per process session, updates the in-memory document, then writes through a sibling temp file and `os.replace`.

## Import Design

Scan targets are enabled service token variables plus enabled derived variable names. Enabled identities and empty source values are skipped as import targets.

Raw source values live only in backend `ImportScanSession.candidates` as `SecretStr`. API scan responses include masked values only.

Commit uses scan ID plus source/target choices. It rejects duplicate selected targets, validates targets against current effective config, recomputes latest status against current `.env`, skips no-change rows, writes only changed rows, and invalidates cached service test status for changed service token variables.

## Service Test Design

Only bearer auth is implemented.

`run_service_test` sends:

```http
Authorization: Bearer <token>
Accept: application/json
```

TLS verification defaults to enabled. `tls_verify = false` must be explicit in TOML.

Status classification:

- 2xx -> `working`
- 401/403 -> `failed` with authentication failure
- other non-2xx -> `failed`
- transport errors -> `failed`

Logs include service ID and non-secret status/error context only.

## CLI and Entry Points

The console script points to `dotfill.entrypoints:main`.

Stable wrapper-facing APIs:

```python
from dotfill.entrypoints import resolve_config_context, run_dotfill
```

`run_dotfill(...) -> int` accepts:

- `config_dir`
- `config_root`
- `profile`
- `default_profile`
- `env_path`
- `argv`
- `program_name`
- `before_config_load`

`config_dir` cannot be combined with root/profile/default-profile input. `before_config_load` runs after context resolution and before TOML loading.

## Server and API Design

The local server binds to `127.0.0.1`.

`GET /api/bootstrap` is public. All other API endpoints require `X-Dotfill-Session`.

Mutating API requests reject unexpected non-local `Origin` headers. No CORS middleware is installed.

FastAPI docs/OpenAPI routes are disabled.

## Frontend Design

The frontend is static and package-local.

Module memory holds:

- session token;
- latest state;
- pasted token values while the wizard is open;
- dropped file content only long enough to POST it.

No `localStorage`, `sessionStorage`, IndexedDB, or cookies are used.

The dashboard shows:

- package version;
- target `.env`;
- collapsed `dotfill config` disclosure with final config/profile directory and open-folder action;
- dynamic identities;
- dynamic derived variables;
- dynamic services;
- empty service state;
- session backup status.

The import wizard builds target dropdowns from dynamic service and derived state. It tracks source mode separately from source text:

- typed paths are sent to the path-scan API;
- browsed files display `Selected file: <filename>` and rescan cached browser-provided file content;
- dropped files display `Dropped file: <filename>` and rescan cached browser-provided file content;
- manual edits to the source field switch back to typed-path mode.

## Error and Secret Boundaries

Domain errors derive from `DotfillError` and are mapped to non-secret JSON responses in the API.

Never expose:

- raw token values;
- Authorization headers;
- dropped source contents;
- full `.env` contents.

Masked token values and masked import previews are allowed.

## Verification

Core verification is pytest-based:

- config paths, loader, merge, and validation;
- identity facts and rules;
- resolver state construction;
- save/backup behavior;
- import scan and commit;
- service tests and secret-safe logging;
- API auth, origin checks, and secret boundaries;
- CLI and stable entrypoint behavior;
- static frontend storage and generic-string audits.

Packaging verification uses:

```powershell
uv build
uv run dotfill --help
uv run python -m dotfill --help
```
