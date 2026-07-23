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
  icons.py
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

Normal profile precedence:

1. CLI or entrypoint profile.
2. `DOTFILL_PROFILE`.
3. no profile.

When a wrapper passes `default_profile`, it is used only if neither CLI/profile input nor `DOTFILL_PROFILE` supplies a profile.

When a wrapper passes `locked_profile`, the active profile is always that
profile. CLI `--profile` and `DOTFILL_PROFILE` are accepted only when they
match the locked profile; non-matching profile input is rejected before TOML
loading. `locked_profile` cannot be combined with `config_dir`, `profile`, or
`default_profile`.

The final config directory is the config root, or `config_root / "profiles" / profile` when a profile is active. Direct `config_dir` entrypoint mode uses the supplied directory as final.

## TOML Loading

`load_effective_config(context)` reads:

1. `config_common.toml`
2. `config.toml`

Both files are optional. Every present file must include `version = 1`.

The merge is deterministic:

- scalar values override;
- tables merge by key;
- `[services.<ID>.auth]` replaces as a unit when present in a later layer;
- `[services.<ID>.test_headers]` merges by case-insensitive header name, with
  later layers overriding earlier header values;
- `enabled = false` removes inherited services, identities, derived variables, and aliases after merge.

Validation happens after merge and disable semantics.

Identity and derived-variable definitions support optional metadata:

- `display = "plain" | "masked"`, default `plain`;
- `compare = "exact" | "casefold"`, default `exact`.

`display` controls local CLI/API/UI presentation only. `compare` controls
equality decisions only. Neither option transforms stored values or forces
case normalization on write.

Service token values are always masked in user-facing output and always compare
exactly. Service definitions do not expose configurable display or comparison
metadata, but do carry service-test auth configuration and static test headers.

Service icons are configured by public service icon keys. The service icon
registry lives in `icons.py` and is the config contract:

```python
DEFAULT_SERVICE_ICON = "key"

SERVICE_ICON_KEYS = {
    "key",
    "ticket",
    "book",
    "git-branch",
    "package",
    "cloud",
    "brand-github",
    "brand-gitlab",
    "server",
    "database",
    "terminal",
    "shield",
    "search",
    "globe",
    "lock",
}
```

Config validation rejects `services.<ID>.icon` values outside
`SERVICE_ICON_KEYS` with a `ConfigSchemaError`. Omitted service icons resolve to
`DEFAULT_SERVICE_ICON`.

## Domain Models

Config models live in `config_models.py`:

- `TargetConfig`
- `IdentityDetectorConfig`
- `IdentityDefinition`
- `DerivedVariableDefinition`
- `AuthConfig`
- `ServiceDefinition`
- `ImportAliasDefinition`
- `EffectiveConfig`

`IdentityDefinition` and `DerivedVariableDefinition` carry display and compare
metadata.

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
   If the selected path exists and is a directory, use that directory's `.env`
   file.
3. Read `.env` into `EnvDocument`.
4. Compute managed variables from enabled identity names, derived names, and service token variables.
5. Reject duplicate managed variables.
6. Run Windows AD detection only when an enabled identity source needs AD facts.
7. Evaluate identity rules.
8. Resolve explicit `.env` identity overrides against detected values using
   each identity's comparison mode.
9. Build derived variable states using each derived variable's comparison mode.
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

### Windows AD Bind Strategy

The user lookup must not rely exclusively on a serverless
`DirectorySearcher`. A serverless bind uses the device's default naming
context, which may be absent on a cloud-joined or hybrid-joined device even
when the current user has directory credentials and a directory controller is
reachable through a VPN.

The probe resolves and searches in this order:

1. Read the current Windows identity as today so the generic SAM/domain facts
   remain available.
2. Choose an explicit directory DNS-domain hint from a valid, trimmed
   `USERDNSDOMAIN`; if unavailable, use the suffix of a successfully resolved
   `whoami /upn` value.
3. Validate the hint as a DNS name before placing it in an LDAP path or
   interpolating it into a generated command. Invalid or unsafe values are
   treated as unavailable.
4. When a valid hint exists, root the search at `LDAP://<dns-domain>` with a
   `DirectoryEntry` and construct the `DirectorySearcher` from that entry.
5. Use a serverless search only when no valid explicit hint exists or the
   explicit bind/search raises. If an explicit search completes successfully
   but finds no matching account, report the unresolved result and its safe
   diagnostics rather than searching an unrelated default context.

The existing generic output protocol (`SAM`, `DOMAIN`, `MAIL`, `UPN`, `PROXY`,
and `ERR`) remains stable. The implementation must not contain a built-in
directory domain. Tests should exercise domain selection and validation,
explicit-bind construction, compatibility fallback, successful empty results,
and diagnostic parsing without requiring a live directory.

Identity rules map config to values. Supported sources:

- `literal`
- `env`
- `local_part`
- `windows_ad.email_by_domain`
- `windows_ad.sam`
- `windows_ad.domain`

Identity state source values are:

- `detected`: no explicit non-empty `.env` value exists, and the configured
  source resolved a value.
- `aligned`: an explicit non-empty `.env` value exists and matches the
  detected value under the identity comparison mode.
- `diverged`: an explicit non-empty `.env` value exists and differs from the
  detected value under the identity comparison mode.
- `unresolved`: neither an explicit non-empty `.env` value nor a detected value
  is available.

Identity aligned/diverged decisions use the configured identity comparison mode.
When values are equivalent under `casefold`, the state is `aligned` and the
explicit value remains the effective value. Explicit non-empty `.env` identity
values remain the effective values for both aligned and diverged identities.

dotfill reads configured identity variables as explicit overrides but never writes identity variables automatically.

## Derived Variable Design

Derived variables copy effective identity values into configured `.env`
variables through constrained write flows:

- token saves automatically fill missing or empty enabled derived variables
  when a computed default is available;
- import commits automatically fill missing or empty enabled derived variables
  when a computed default is available, unless the import explicitly maps a
  source value to the same derived variable;
- dashboard row actions may explicitly write a computed default for missing or
  diverged derived variables.

Derived state values are:

- `missing`: the configured derived variable is absent or empty in the target
  `.env`, and the computed default is available.
- `aligned`: the current non-empty `.env` value matches the computed default
  under the derived comparison mode.
- `diverged`: the current non-empty `.env` value differs from the computed
  default under the derived comparison mode.

Derived aligned/diverged decisions use the configured derived comparison mode.
When values are equivalent under `casefold`, the state is `aligned`; dotfill
does not rewrite a non-empty current value just to normalize casing.

Automatic token-save and import-fill behavior must not overwrite non-empty
derived values. Diverged derived values are preserved unless the user explicitly
chooses the row-level default action. Disabled derived variables are absent from
derived state and are never written. Derived variables whose source identity is
unresolved are not eligible for automatic fill or explicit reset.

The row-level default endpoint is a desired-state operation and is idempotent.
After rebuilding current state, it behaves as follows:

- `missing` or `diverged` with a computed default: write exactly the derived
  variable and return it in `updated`;
- `aligned`: perform no write and return success with `updated = []`;
- unresolved or missing computed default: return `409`;
- unknown or disabled derived variable: return `404`.

The frontend also maintains a per-variable in-flight guard. A row action is
disabled synchronously before its request begins, and another activation for
that variable is ignored until the request settles. Success reloads dashboard
state; failure restores the action and uses the existing non-secret error
surface. Backend idempotency remains required because client-side guarding
cannot prevent stale, retried, or non-browser requests.

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

No-change detection for service token targets is always exact. No-change
detection for derived targets uses the derived variable's comparison mode. Scan
previews keep masking source values regardless of target display metadata.
Scan responses include per-row target status metadata for every eligible import
target so the frontend can update manual remaps without receiving raw source
values.

Import-row service testing uses a dedicated import-test endpoint rather than
the saved-token `/api/test/{service_id}` endpoint. The request contains the
scan ID, source key, and currently selected target key. The server validates
that the scan exists, the source key exists in `ImportScanSession.candidates`,
and the selected target key belongs to an enabled service token variable. It
then resolves that service's test URL, runs the normal service-test logic with
the backend-held candidate value, and returns only non-secret status/error
details. This flow never writes the target `.env` and never updates the
dashboard saved-token service-test cache. The frontend uses the result to
choose the row icon state; detailed success/failure context stays in the
normal service-test logger/console path rather than row tooltips.

## Service Test Design

Service-test auth is configured per service. Omitted auth defaults to bearer,
but a present `auth` value must be a table; scalar auth values are invalid.

Supported auth kinds:

- `bearer`: sends `Authorization: Bearer <token>`.
- `header`: sends the token in the configured HTTP header.
- `basic`: sends `Authorization: Basic <base64(username:token)>`, where the
  username comes from either a literal `username` or a resolved
  `username_identity`.

`kind = "query"` is not supported until redacted URL handling is implemented
and tested.

`run_service_test` prepares a request centrally:

- start with `Accept: application/json`;
- apply configured static `test_headers`;
- add the auth-generated header for bearer, header, or basic auth;
- reject static header conflicts with auth-generated headers
  case-insensitively during config validation;
- resolve basic `username_identity` at test time using current identity state.

An unresolved basic `username_identity` fails only that service test with
non-secret error context; it does not block dashboard state construction unless
the same identity is also required by a derived variable, service URL template,
or dependent identity rule.

TLS verification defaults to enabled. `tls_verify = false` must be explicit in TOML.

The service-test fingerprint is non-secret and session-scoped. It includes the
service ID, token variable, resolved test URL, TLS setting, normalized auth
configuration, normalized static test headers, a session-scoped token digest,
and a session-scoped digest of the resolved basic username when basic auth uses
identity-derived or literal username material.

Status classification:

- 2xx -> `working`
- 401/403 -> `failed` with authentication failure
- other non-2xx -> `failed`
- transport errors -> `failed`

Logs include service ID and non-secret status/error context only.
The dashboard presents service-test outcomes as status badges and request-level
errors, not detailed per-service diagnostics. Those diagnostics belong in the
configured logger/console. `--verbose` enables debug-level logging and stops
suppressing supporting Uvicorn/httpx/httpcore logs; all modes must remain
secret-safe.

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
- `locked_profile`
- `env_path`
- `argv`
- `program_name`
- `wrapper_name`
- `wrapper_version`
- `before_config_load`

`profile` is a programmatic explicit profile. `default_profile` is a fallback
used only when CLI input and `DOTFILL_PROFILE` do not select a profile.
`locked_profile` is a wrapper-enforced profile: CLI/environment profile input
must either be absent or match it.

`config_dir` cannot be combined with `config_root`, `profile`, `default_profile`, or `locked_profile`. `locked_profile` cannot be combined with `profile` or `default_profile`. `before_config_load` runs after context resolution and before TOML loading.

`wrapper_name` and `wrapper_version` are optional paired dashboard display
metadata. Supplying only one, or supplying an empty/whitespace-only value, is a
wrapper API error. They are separate from `program_name`: wrapper metadata does
not rename the Typer program and `program_name` does not implicitly opt into
dashboard wrapper branding.

The entrypoint passes validated wrapper metadata through the Typer context to
both the default dashboard launch and the explicit `serve` command.
`AppContext` retains it for bootstrap only. `/api/bootstrap` returns a
structured nullable value such as:

```json
{
  "version": "1.4.1",
  "wrapper": {
    "name": "team-dotfill",
    "version": "1.0.1"
  }
}
```

Direct launches return `"wrapper": null`. The frontend builds the display
with DOM text nodes: `v1.4.1` for direct launches and
`v1.4.1 (team-dotfill v1.0.1)` for wrapped launches. It must not insert wrapper
metadata through `innerHTML`.

## Server and API Design

The local server binds to `127.0.0.1`.

`GET /api/bootstrap` is public. All other API endpoints require `X-Dotfill-Session`.

Mutating API requests reject unexpected non-local `Origin` headers. No CORS middleware is installed.

FastAPI docs/OpenAPI routes are disabled.

Before mounting the packaged static frontend, the server explicitly registers
`.js` as `application/javascript`. This avoids host-level MIME configuration,
including Windows registry mappings, causing module scripts to be returned as
`text/plain` and rejected by the browser. The entry-module query key changes
when its cached response must be invalidated.

## Frontend Design

The frontend is static and package-local.

All frontend icons and favicon assets are bundled with the package. dotfill
does not fetch icon assets from CDNs or external icon packages at runtime.

`index.html` links a local SVG favicon from the packaged static assets so
browser tabs show a dotfill-specific icon. The favicon should use a compact
token/key motif that remains legible at tab size.

`index.html` also contains the inline SVG symbol sprite. Sprite symbols are
implementation assets and may include both public service icons and private UI
control symbols. UI-only symbols such as arrows, status marks, alerts, refresh,
upload, and theme-toggle icons are not automatically valid
`services.<ID>.icon` config values.

Module memory holds:

- session token;
- latest state;
- pasted token values while the wizard is open;
- dropped file content only long enough to POST it.

`localStorage` may store only the persisted light/dark color-theme preference.
No token values, import source contents, Authorization headers, full `.env`
contents, session tokens, or other secret material may be written to
`localStorage`, `sessionStorage`, IndexedDB, or cookies.

The dashboard shows:

- package version;
- optional wrapper name/version beside the package version when supplied by a
  wrapper entrypoint;
- target `.env`;
- collapsed `dotfill config` disclosure with final config/profile directory and open-folder action;
- light/dark mode toggle;
- dynamic identities;
- dynamic derived variables;
- dynamic services;
- empty service state;
- session backup status.

Service cards render the configured public service icon key. The frontend icon
helper checks whether `ic-<name>` exists in the current document and falls back
to `ic-key` when a symbol is missing. This fallback is defense-in-depth for
asset drift; backend schema validation remains responsible for rejecting
unknown configured service icon names.

The selected color theme is applied on startup before rendering app content
where practical. The theme preference persists across browser sessions and may
fall back to the system `prefers-color-scheme` value when no preference exists.

The import wizard builds target dropdowns from dynamic service and derived state. It tracks source mode separately from source text:

- typed paths are sent to the path-scan API;
- browsed files display `Selected file: <filename>` and rescan cached browser-provided file content;
- dropped files display `Dropped file: <filename>` and rescan cached browser-provided file content;
- manual edits to the source field switch back to typed-path mode.

When a user changes a row's `Save as` selection, the wizard recomputes that row's
status from the scan response's per-target status metadata. This lets same-value
manual remaps show `No change` rather than `Replace`; occupied-target data is
only a fallback for older or incomplete scan payloads.

The import mapping table includes a narrow action column immediately before
`Status`. Rows whose `Save as` selection resolves to an enabled service token
variable and whose status is not `No change` show an approximately
checkbox-sized service-test button in that column. The untested state displays
the same test icon used by the main service-test actions, with a tooltip
explaining that the selected service will be tested using the imported API key.
While running, the row shows an in-progress state; on
success it becomes a green check, and on failure it becomes a red x. Detailed
success/failure context is not shown in the row tooltip or status text; it is
reported through the same logger/console path as saved-token service tests,
with additional logging context available under `--verbose`. The button is hidden for
skipped/unmapped rows, derived-variable targets, non-service targets, and
no-change rows. Changing a row's `Save as` selection resets that row's test
state. Pressing Scan, typing a new path, browsing to a new file, or dropping a
new file resets all import row test states.

## Error and Secret Boundaries

Domain errors derive from `DotfillError` and are mapped to non-secret JSON responses in the API.

Never expose:

- raw token values;
- generated auth headers or credentials, including Authorization, configured
  API-key headers, and Basic-encoded credentials;
- dropped source contents;
- full `.env` contents;
- session tokens in browser storage.

Masked token values, masked import previews, and configured masked
identity/derived values are allowed. When an identity or derived variable is
configured with `display = "masked"`, raw values for that item must not be
included in API responses or CLI/status output.

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
- static frontend secret-storage and generic-string audits.
- service icon registry validation, including every `SERVICE_ICON_KEYS` entry
  having a matching `ic-*` symbol in the bundled sprite without requiring every
  sprite symbol to be service-configurable.

Packaging verification uses:

```powershell
uv build
uv run dotfill --help
uv run python -m dotfill --help
```
