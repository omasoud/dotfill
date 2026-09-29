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
- Allow wrapper entrypoints to provide optional display name/version metadata
  for the dashboard without changing dotfill's package identity or CLI
  behavior.
- Preserve `.env` comments, blank lines, ordering, unrelated variables, unrelated duplicates, and line endings.
- Write only after explicit user action.
- Keep the dashboard and `status` usable when some configured identities
  cannot be resolved.
- Create at most one backup per process session before the first write.
- Keep raw token values, dropped import values, generated auth headers/credentials, and full `.env` contents out of logs, API responses, and browser storage. Browser storage may contain only explicitly allowed non-secret UI preferences, such as the persisted color theme.
- Keep all UI assets local to the package.

## Non-Goals

- No dotfill-operated cloud backend, accounts, telemetry, shared token storage,
  or remote sync. Opt-in identity detectors may query the user's own identity
  provider.
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

- If a selected target path exists and is a directory, dotfill targets that
  directory's `.env` file.
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
- `[identity.detectors.entra]`
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
- `email_by_domain`
- `windows_ad.email_by_domain`
- `windows_ad.sam`
- `windows_ad.domain`
- `entra.email_by_domain`

Identity detectors return generic facts only. They do not map facts to
organization-specific identity names.

Supported identity detectors are `windows_ad` and `entra`, configured under
`[identity.detectors.<name>]`:

- `enabled` defaults to `true` for `windows_ad` and `false` for `entra`.
  Entra stays opt-in because the built-in client ID yields a broadly scoped
  token; profiles that enable it should record that tradeoff.
- `priority` is an integer; lower values run first. It defaults to `20` for
  `windows_ad` and `10` for `entra`. Ties are ordered by detector name.
- `entra` also accepts an optional `client_id` (a GUID) and `tenant`
  (`organizations`, a tenant GUID, or a DNS-safe tenant domain; default
  `organizations`). Invalid or unsafe values are schema errors.

Detector-pinned sources (`windows_ad.*`, `entra.*`) read facts only from the
named detector, which must be enabled. `email_by_domain` requires at least one
enabled detector and resolves to the first email in the configured domain from
the enabled detectors in priority order.

Detectors run only when an enabled identity needs their facts. Pinned sources
always need their detector. For `email_by_domain` identities, a detector runs
only while at least one of them is still undetected after all higher-priority
detectors. A detector failure never fails state construction; affected
identities become unresolved with short, non-secret diagnostics.

Detector results are cached in process memory for the server session and are
never written to disk. Each detector run has one outcome:

- `complete`: the detector's primary lookup finished (Windows AD: the LDAP
  search completed, with or without a match; Entra: Graph `/me` returned
  success). Complete results are reused until the process exits.
- `partial`: some facts were collected but the primary lookup did not finish,
  for example an in-process UPN with an LDAP timeout. Partial facts are used
  immediately, and the detector is retried.
- `failed`: no usable facts. The detector is retried.

Partial and failed results are retried with backoff, starting at 60 seconds
and capped at 15 minutes; the backoff resets after a complete result. A
transient network or sign-in problem therefore neither stalls refreshes nor
becomes permanent: when the lookup succeeds again, for example after a VPN
reconnect, missing domains resolve. A config change that affects a detector
invalidates its cached result.

Detection must not hold up the dashboard. Detection runs as a background pass
that executes the needed detectors in priority order. Each next detector starts
as soon as the previous one finishes without supplying every needed domain, so
the pass continues without waiting for another state request. Each detector is
single-flight. The dashboard's state request waits at most a short budget
(default 2 seconds). It then returns the current results and reports detection
as pending until the whole pass finishes, along with an upper bound on the
pass's remaining time. It also reports when the next scheduled retry is due.
When a retry becomes due or the page becomes visible again, an open dashboard
rechecks automatically. Identities therefore recover, for example after a VPN
reconnect, without a manual refresh. One-shot CLI commands such as `status`
wait for the pass to finish, bounded by the detector timeouts.

Windows AD user lookup must work when the current user can reach a directory
controller but the device does not expose a usable computer-domain default
naming context. The lookup must:

- prefer an explicit LDAP search root derived from a valid user directory DNS
  domain, using `USERDNSDOMAIN` first and a valid `whoami /upn` suffix as a
  fallback;
- accept only DNS-safe domain hints before using them in an LDAP path or
  generated PowerShell command;
- retain serverless `DirectorySearcher` behavior only as a compatibility
  fallback when no valid user-domain hint is available or the explicit bind
  fails;
- not search a different default naming context merely because a successful
  explicit-domain search found no matching account; and
- preserve generic fact output and non-secret diagnostics without embedding
  any organization-specific domain.

The Windows AD detector reads the current user's SAM-compatible name and user
principal name in-process, without contacting a directory controller, before
its LDAP lookup. Those facts remain available when the LDAP lookup fails or
times out. Probe timeouts and failures produce short diagnostics that never
include the generated probe script, command line, or process arguments.

The `entra` detector:

- runs only on Windows and reports a non-secret unavailable diagnostic on other
  platforms;
- obtains a Microsoft Graph access token for the signed-in work or school
  account silently through the Windows Web Account Manager. It never shows an
  interactive sign-in, account-picker, or consent prompt, and uses exactly one
  request form per client mode, with no automatic format fallback:
  - built-in client ID: the Microsoft Graph resource without a scope, the only
    form that the built-in client ID is pre-authorized for;
  - configured `client_id`: the delegated `User.Read` scope with the Microsoft
    Graph resource;
- does not claim least privilege for the built-in client ID: its tokens carry
  that client's broad pre-authorized delegated scopes. Only a configured app
  registration that is consented for `User.Read` alone can yield a
  least-privilege token;
- is best-effort: silent acquisition may be unavailable when tenant policy
  requires interaction or blocks the client. Such failures are reported as
  short non-secret diagnostics, and identities fall back to lower-priority
  detectors or explicit `.env` values;
- uses a built-in Microsoft public client ID unless `client_id` is configured.
  The built-in ID is not guaranteed to work in every tenant; tenants that block
  it can configure an approved app registration through `client_id`;
- reads only `mail`, `userPrincipalName`, and `proxyAddresses` from Graph
  `/me`, keeps only SMTP proxy addresses (other types such as `X500:` are
  ignored), and normalizes them like Windows AD facts; `otherMails` is
  ignored;
- keeps the access token inside the helper process: it is never logged,
  written, cached by dotfill, or returned to Python, the API, or the browser;
  and
- contacts only the Microsoft identity platform and Microsoft Graph, only when
  enabled in config. It is not a dotfill-operated backend.

Resolution model:

- `detected`: no explicit non-empty `.env` value exists, and the configured
  source resolved a value.
- `aligned`: an explicit non-empty `.env` value exists and matches the
  detected value under the identity comparison mode.
- `diverged`: an explicit non-empty `.env` value exists and differs from the
  detected value under the identity comparison mode.
- `unresolved`: neither an explicit non-empty `.env` value nor a detected value
  is available.

Explicit non-empty `.env` values win for effective identity values, including
when the identity is `aligned` or `diverged`.

Identity equality uses the identity definition's `compare` mode. With
`compare = "casefold"`, explicit and detected values that differ only by
casefold-equivalent casing are `aligned`; the effective value remains the
original explicit value.

Unresolved identities never fail state construction. Dependent identity rules,
derived variables, and service URL templates that need an unresolved identity
report their own unresolved state instead. An unresolved detector-sourced
identity carries the non-secret diagnostics explaining why detection failed,
and detected identities record which detector supplied the value.

dotfill never writes identity variables automatically.

## Derived Variable Requirements

Derived variables copy an effective identity into a configured `.env` variable.

Rules:

- `from_identity` must reference an enabled identity.
- Missing or empty enabled derived variables are filled on token saves.
- Missing or empty enabled derived variables are filled on import commits when
  a computed default is available. If the import explicitly maps a source value
  to the same derived variable, the explicit import value wins.
- Existing non-empty derived values are preserved during automatic token-save
  and import-fill behavior.
- Existing non-empty derived values may be reset to the computed default only
  through an explicit row-level user action.
- The row-level default operation is idempotent: if a stale or repeated request
  arrives after the value is already aligned with its computed default, it
  succeeds without writing and reports no updated variables.
- Disabled derived variables are not filled or written.

Derived state values are:

- `missing`: the configured derived variable is absent or empty in the target
  `.env`, and the computed default is available.
- `aligned`: the current non-empty `.env` value matches the computed default
  under the derived comparison mode.
- `diverged`: the current non-empty `.env` value differs from the computed
  default under the derived comparison mode.
- `unresolved`: the source identity is unresolved, so no computed default is
  available; any current `.env` value is still reported.

Disabled derived variables do not appear in derived state. A derived variable
whose source identity is unresolved is not eligible for automatic fill or
explicit reset, and it does not block state construction.

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

Service `icon` values are public service-config icon keys, not arbitrary SVG
symbol IDs. Omitted `icon` defaults to `key`. Unknown service icon keys are
configuration schema errors, not warnings.

Supported service icon keys:

```text
key
ticket
book
git-branch
package
cloud
brand-github
brand-gitlab
server
database
terminal
shield
search
globe
lock
```

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

Service `token_url` and `test_url` may reference identities as `{NAME}`
placeholders. The two URLs resolve independently, and each tracks the
unresolved identities it needs. When the token-page URL needs an unresolved
identity, only its token-page link is unavailable. When the test URL does, only
the service test is unavailable. Saving the service token always works, and
other services are unaffected. When the test URL is unresolved, a
single-service test returns a non-secret `409`, test-all reports a per-service
failure and continues, and an import-row test reports a failure for that row.

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
When a user manually remaps a source row to a different import target, the
wizard must use scan-time backend status metadata for that selected target so a
same-value remap shows `No change` rather than `Replace` while still keeping raw
source values out of API responses.

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

`run_dotfill(...)` may also accept paired `wrapper_name` and `wrapper_version`
display metadata. Both values must be supplied together as non-empty strings.
When omitted, direct dotfill behavior is unchanged. Wrapper display metadata:

- is independent of `program_name`, which continues to control CLI help and
  error output;
- does not affect config, profile, target-path, command, or version resolution;
- is propagated only to dashboard bootstrap/presentation state; and
- is rendered as text, never interpreted as HTML.

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
- Return `/api/state` successfully when identities are unresolved, reporting
  unresolved identities, derived variables, and service URLs as item states
  rather than as a request error. Also report the identity detection status:
  whether a detection pass is still pending, the remaining-time bound for that
  pass, and when the next scheduled retry is due.
- Serve packaged `.js` assets with an explicit JavaScript media type instead of
  inheriting host or operating-system MIME mappings.
- Treat `POST /api/derived/{variable_name}/default` as an idempotent desired-state
  operation: missing or diverged values are written, already-aligned values
  return success with `updated = []`, unknown variables return `404`, and
  unresolved or otherwise non-computable values return `409`.
- Return optional wrapper display metadata from `/api/bootstrap` as a structured
  object only when a wrapper supplied both values.

## Frontend Requirements

- Show target `.env` path.
- Keep the target `.env` path visually primary.
- Show config directory in a collapsed `dotfill config` disclosure, including profile directory when a profile is active.
- Render dynamic identities, derived variables, and services.
- Show unresolved identities, derived variables, and service URLs inline with
  a short non-secret reason; disable only the actions that need the missing
  value.
- While identity detection is pending, show a pending indicator and poll state
  until the pass finishes, bounded by the server-reported remaining pass time.
  Also re-fetch state once when a reported retry becomes due and whenever the
  page becomes visible again.
- Disable a derived-variable default action immediately while its request is in
  flight and suppress additional requests for the same row until it settles.
- Show the package version as `v<dotfill-version>` for direct launches. When
  wrapper metadata is present, append
  ` (<wrapper-name> v<wrapper-version>)`, for example
  `v1.4.1 (team-dotfill v1.0.1)`.
- Render service icons from configured public service icon keys.
- Fall back to the `key` icon if a referenced SVG symbol is unavailable at
  render time; backend config validation remains the primary guard against
  invalid icon names.
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
- User-facing `docs/config-schema.md` documents schema, merge rules, disable semantics, identity sources, identity detectors with their `priority` and Entra options, identity/derived `display` and `compare`, import aliases, `tls_verify`, and the supported service icon keys.
- User-facing docs include getting-started and troubleshooting guidance.
- Troubleshooting covers unresolved identities, including off-network
  directory lookups, Windows Hello sign-in on cloud-joined devices whose domain
  controller certificates lack the KDC Authentication EKU, and silent Entra
  token failures.
- Examples use neutral domains such as `example.com`.
- Override-only `config.toml` examples include `version = 1`.
