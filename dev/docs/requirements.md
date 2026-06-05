# dotfill requirements

Status: Active generic requirements
Design reference: `design-specification.md`
Task tracker: `implementation-plan.md`

dotfill is a generic local-only utility for maintaining configured token and identity variables in a personal `.env` file. It is configured by TOML files, not by special assignments inside `.env`.

## Goals

- Ship generic `dotfill` with no company-specific services, domains, identities, token names, import aliases, or defaults.
- Load `config_common.toml` and `config.toml` from a resolved config directory.
- Support config roots, profiles, and wrapper-style Python entrypoints.
- Support wrapper entrypoints that lock a wrapper to one profile without
  wrapper-side command-line parsing.
- Preserve `.env` comments, blank lines, ordering, unrelated variables, unrelated duplicates, and line endings.
- Write only after explicit user action.
- Create at most one backup per process session before the first write.
- Keep raw token values, dropped import values, generated auth headers/credentials, and full `.env` contents out of logs, API responses, and browser storage. Browser storage may contain only explicitly allowed non-secret UI preferences, such as the persisted color theme.
- Keep all UI assets local to the package.

## Non-Goals

- No cloud backend, accounts, telemetry, shared token storage, or remote sync.
- No generic built-in service catalog.
- No browser-side persistence of secrets, session tokens, or import contents.
- No automatic token validation except explicit Test actions.
- No secret vault or token rotation policy engine.
- No in-UI TOML editor in the current version.
- No query-string service-test authentication in the current version.

## Target `.env`

Resolution precedence:

1. CLI `--env-path`.
2. `[target].default_env_path` from effective TOML config.
3. `Path.home() / ".env"`.

File behavior:

- Missing target files are normal and are created on first save.
- Input and output use UTF-8.
- Managed assignments are updated in place when possible.
- Missing managed assignments are appended.
- Writes are atomic where the OS permits.
- Existing line endings are preserved where practical.
- Duplicate managed variables block state construction.
- Duplicate unrelated variables remain unrelated content.

Managed variables are:

- enabled identity names, because they may be explicit overrides;
- enabled derived variable names;
- enabled service token variables.

Disabled config items are not managed.

## Configuration

The config directory contains two optional files:

```text
config_common.toml
config.toml
```

Layer order:

1. `config_common.toml`
2. `config.toml`

Every present TOML file must include:

```toml
version = 1
```

`config_common.toml` is the managed baseline layer. `config.toml` is the user-owned override layer.

Supported sections:

- `[target]`
- `[identity.detectors.windows_ad]`
- `[identities.<NAME>]`
- `[derived.<VARIABLE>]`
- `[services.<ID>]`
- `[services.<ID>.auth]`
- `[services.<ID>.test_headers]`
- `[import_aliases.<SOURCE>]`

All keyed items support `enabled = false`, which removes the inherited item from the effective config.

Config tables merge recursively except `[services.<ID>.auth]`, which replaces
as a unit when present in a later layer. `[services.<ID>.test_headers]` merges
by case-insensitive header name, with later layers overriding earlier header
values while preserving the later layer's configured casing.

Identity and derived-variable definitions may include display/comparison
metadata:

- `display = "plain"` shows the value in local CLI/API/UI output.
- `display = "masked"` shows only a masked representation in local CLI/API/UI
  output; raw values for masked items must not be included in those responses.
- `compare = "exact"` compares values with exact string equality.
- `compare = "casefold"` compares values using Python `str.casefold()` for
  equality decisions.

Identity and derived-variable `display` default to `plain`. Identity and
derived-variable `compare` default to `exact`. Display metadata does not change
state construction, save behavior, import mapping, or stored values. Comparison
metadata does not normalize values before writing.

Service token values are always masked in user-facing output and always compare
exactly; service definitions do not support configurable `display` or `compare`
metadata.

## Identity Requirements

Identity names are dynamic TOML keys and must be valid environment variable names.

Supported sources:

- `literal`
- `env`
- `local_part`
- `windows_ad.email_by_domain`
- `windows_ad.sam`
- `windows_ad.domain`

Windows AD detection returns generic facts only. It does not map facts to organization-specific identity names.

Resolution model:

- Explicit non-empty `.env` value wins.
- Explicit matching detected value is `aligned`.
- Explicit differing detected value is `diverged`.
- Detected value with no explicit value is `detected`.
- Missing explicit and detected values are `unresolved`.

Identity equality uses the identity definition's `compare` mode. With
`compare = "casefold"`, explicit and detected values that differ only by
casefold-equivalent casing are `aligned`; the effective value remains the
original explicit value.

Unresolved identities fail state construction only when required by enabled derived variables, service URL templates, or dependent identity rules.

dotfill never writes identity variables automatically.

## Derived Variable Requirements

Derived variables copy an effective identity into a configured `.env` variable.

Rules:

- `from_identity` must reference an enabled identity.
- Missing or empty enabled derived variables are filled on token saves.
- Existing non-empty derived values are preserved.
- Disabled derived variables are not filled or written.

Derived equality uses the derived definition's `compare` mode. With
`compare = "casefold"`, current and computed values that differ only by
casefold-equivalent casing are `aligned`. Token saves still preserve any
non-empty current derived value, and dotfill does not rewrite a value only to
normalize casing.

## Service Requirements

Each enabled service requires:

- `display_name`
- `token_var`
- `token_url`
- `test_url`

Optional fields:

- `[services.<ID>.auth]`, defaulting to bearer when omitted
- `[services.<ID>.test_headers]`, defaulting to no extra headers
- `tls_verify = true`
- `icon = "key"`

If `auth` is present, it must be a table. Scalar `auth = "bearer"` and other
scalar auth values are invalid. Supported auth table shapes are:

```toml
[services.SERVICE.auth]
kind = "bearer"
```

```toml
[services.SERVICE.auth]
kind = "header"
header = "x-api-key"
```

```toml
[services.SERVICE.auth]
kind = "basic"
username_identity = "WORK_EMAIL"
```

```toml
[services.SERVICE.auth]
kind = "basic"
username = "literal-user"
```

`kind = "query"` is intentionally unsupported until redacted URL handling is
implemented and tested.

Service auth validation must reject unknown auth kinds, unknown fields for the
selected kind, missing required fields, invalid HTTP header names,
case-insensitive duplicate `test_headers`, auth-generated header conflicts
with `test_headers`, basic auth with both or neither username source, basic
literal usernames containing `:`, and `username_identity` references to
unknown or disabled identities.

Service tests:

- support bearer, header API-key, and basic auth request construction;
- send `Accept: application/json` unless a configured static header overrides it;
- include configured static `test_headers` for any auth kind;
- verify TLS by default;
- classify 2xx responses as working;
- classify 401/403 responses as authentication failures;
- store cached test status only in process memory;
- reuse cached status only when the service-test fingerprint still matches;
- include normalized auth config, static test headers, TLS settings, resolved
  test URL, session-scoped token digest, and any resolved basic username
  material in the service-test fingerprint without storing raw secrets;
- report service-test success and failure through the configured logger/console
  with service ID, HTTP status when available, and non-secret error context;
- keep service-test logs secret-safe in normal and `--verbose` modes;
- allow `--verbose` to show additional server/client/debug logging context;
- import-screen service tests may test unsaved scan candidate values by scan ID, source key, and selected target using the configured service auth mode, but must not write the target `.env` or update the saved-token service-test cache.

## Import Requirements

Import targets are enabled service token variables plus enabled derived variable names. Identity variables are never import targets.

Scan behavior:

- Source values are stored backend-side as secret values.
- API responses include masked values only.
- Empty source values are skipped.
- Exact target-name matches win over aliases.
- Configured aliases are heuristic and user-adjustable.

Commit behavior:

- Commit requests contain scan ID plus source/target choices, never raw source values.
- Targets are validated against the current effective target set.
- Duplicate selected targets are rejected.
- Latest status is recomputed against the current `.env`.
- Latest no-change rows are skipped.
- Changed service token variables invalidate cached test status.

Import row test behavior:

- Rows whose `Save as` selection resolves to an enabled service token variable and whose `Status` is not `No change` show a compact test button immediately before the `Status` column.
- The test button is approximately checkbox-sized so it adds only a narrow action column.
- The initial button state uses the same test icon as the main service-test actions, with a tooltip explaining that it tests the service using the imported value for the selected API key.
- Pressing the button tests that service using the backend-held source value for the row, without saving the value.
- Successful tests become a green check. Failed tests become a red x.
- Detailed success/failure context follows the existing service-test reporting
  model: log to the configured console/logger with non-secret context, and rely
  on `--verbose` for additional logging context instead of row tooltip text.
- The button is not shown for skipped/unmapped rows, derived-variable targets, non-service targets, or no-change rows.
- Row test state resets to the initial untested state when the `Save as` selection changes.
- All import row test states reset when the Scan button is pressed, or when a new source path is typed, browsed, or dropped.

No-change detection for derived-variable import targets uses that derived
definition's `compare` mode. No-change detection for service token targets is
always exact. Import scan previews continue to mask source values regardless of
target display metadata.

## CLI Requirements

Required commands and options:

```powershell
dotfill
dotfill serve
dotfill status
dotfill config path
dotfill config open
dotfill --config-root <path>
dotfill --profile <name>
dotfill --env-path <path>
dotfill --verbose
```

`config path` must support:

- `--root`
- `--common`
- `--user`

`config open` creates the final config directory but does not create TOML files.

## Wrapper Entrypoint Requirements

`run_dotfill(...)` must support three profile modes:

- `profile="name"` selects a programmatic explicit profile in the normal
  explicit-profile precedence tier. CLI `--profile` can override it;
  `DOTFILL_PROFILE` is used only when neither CLI nor entrypoint profile input
  selects a profile.
- `default_profile="name"` selects a fallback profile only when CLI input and
  `DOTFILL_PROFILE` do not select one.
- `locked_profile="name"` forces a wrapper-owned profile.

When `locked_profile` is set:

- `config_root`, `env_path`, `argv`, `program_name`, and `before_config_load`
  continue to work normally.
- `config_dir`, `profile`, and `default_profile` are invalid combinations.
- CLI `--profile name` is accepted only when it matches the locked profile.
- CLI `--profile other` is rejected with a clear non-secret CLI error.
- `DOTFILL_PROFILE=name` is accepted only when it matches the locked profile.
- `DOTFILL_PROFILE=other` is rejected with a clear non-secret CLI error.
- The resolved `ConfigContext.profile` is always the locked profile.
- `before_config_load` runs after locked-profile context resolution and before
  TOML loading.

## API and Server Requirements

- Bind only to `127.0.0.1`.
- Pick a free local port unless specified.
- Keep `/api/bootstrap` public.
- Require `X-Dotfill-Session` on all other API endpoints.
- Reject unexpected `Origin` headers on mutating API requests.
- Emit no permissive CORS headers.
- Map domain errors to non-secret JSON responses.

## Frontend Requirements

- Show target `.env` path.
- Keep the target `.env` path visually primary.
- Show config directory in a collapsed `dotfill config` disclosure, including profile directory when a profile is active.
- Render dynamic identities, derived variables, and services.
- Render service icons from configured icon keys with fallback `key`.
- Use a local package favicon so browser tabs do not show the browser default icon.
- Provide a light/dark mode toggle.
- Persist the selected light/dark theme across browser sessions as a non-secret UI preference.
- Show the empty service message:

```text
No services configured.
Run a profile wrapper or edit config.toml.
```

- Build import target dropdowns from dynamic state.
- In the import wizard, show `Selected file: <filename>` for browsed files and `Dropped file: <filename>` for dropped files.
- Make the import Scan button rescan the active source: typed path or cached selected/dropped file content.
- Use no browser storage except the persisted non-secret color-theme preference.
- Keep token wizard and import wizard data in memory only.

## Documentation Requirements

- README describes generic TOML configuration, config locations, CLI usage, privacy, wrapper entrypoints, and links to user documentation under `docs/`.
- User-facing `docs/config-schema.md` documents schema, merge rules, disable semantics, identity sources, identity/derived `display` and `compare`, import aliases, and `tls_verify`.
- User-facing docs include getting-started and troubleshooting guidance.
- Examples use neutral domains such as `example.com`.
- Override-only `config.toml` examples include `version = 1`.
