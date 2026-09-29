# dotfill implementation status and roadmap

Status: Active maintainer tracker
Requirements: `requirements.md`
Design reference: `design-specification.md`
Config schema: `../../docs/config-schema.md`

This document records the current implementation state, verification expectations, and future work for public development. It is intentionally current-state focused, not a migration history.

## Current Implementation Status

- [x] Python 3.14 package using Typer, FastAPI/Uvicorn, Pydantic, httpx, platformdirs, and static HTML/CSS/vanilla JavaScript.
- [x] Generic package ships with no built-in services, identities, domains, token variables, or import aliases.
- [x] `config_common.toml` and `config.toml` load from the resolved config directory, with strict schema validation.
- [x] Config-root precedence is CLI/entrypoint override, `DOTFILL_CONFIG_ROOT`, then platform user config directory.
- [x] Profile precedence is CLI/entrypoint profile, `DOTFILL_PROFILE`, then no profile.
- [x] Final config directory is root mode or `profiles/<name>` mode; direct `config_dir` entrypoint mode is supported.
- [x] `dotfill config open` and dashboard config-open create only the final config directory and do not create TOML files.
- [x] Present TOML files must include `version = 1`.
- [x] Top-level sections and known table fields are strict; unknown entries are rejected.
- [x] Later config layers override scalars and merge keyed tables, with service
      auth replacing as a unit and service test headers merging by
      case-insensitive header name.
- [x] `enabled = false` removes inherited services, identities, derived variables, and import aliases before required-field validation.
- [x] Target `.env` path resolves from CLI `--env-path`, then `[target].default_env_path`, then home `.env`; an existing directory target resolves to that directory's `.env` file.
- [x] `.env` parsing preserves comments, blank lines, unrelated variables, unrelated duplicates, quote style, and line endings.
- [x] Writes are explicit, atomic, and create at most one backup per process session before the first write.
- [x] Managed variables are enabled identities, enabled derived variables, and enabled service token variables.
- [x] Duplicate managed variables block state construction with line-number context.
- [x] Identity rules support `literal`, `env`, `local_part`, `windows_ad.email_by_domain`, `windows_ad.sam`, and `windows_ad.domain`.
- [x] Identity and derived definitions support `display = "plain" | "masked"` and `compare = "exact" | "casefold"` metadata.
- [x] Windows AD probing returns generic facts only, runs only when an enabled
      identity needs AD facts, and prefers a validated explicit user-domain
      LDAP root before controlled serverless fallback.
- [x] Explicit non-empty `.env` identity overrides participate in identity state as aligned, diverged, or unresolved, using configured comparison metadata.
- [x] dotfill never writes identity variables automatically.
- [x] Derived variables copy enabled identities, use configured comparison metadata for aligned/diverged state, and are filled when missing or empty during token saves or import commits.
- [x] Save flow writes the selected service token plus missing enabled derived variables.
- [x] Dashboard row actions can fill missing derived variables or reset
      diverged derived variables to their computed defaults, guard against
      same-row requests in flight, and treat repeated aligned requests as
      idempotent no-ops.
- [x] Service tests support bearer, header API-key, and basic auth.
- [x] Service tests send configured auth headers and `Accept: application/json`,
      apply static test headers, verify TLS by default, and classify status
      safely.
- [x] Cached service-test results are process-local and invalidated by token,
      service, auth config, static headers, resolved basic username, TLS, or
      URL changes.
- [x] Import scans target enabled service token variables and enabled derived variables; identities are never import targets.
- [x] Import scans skip empty source values and return masked values only.
- [x] Import aliases are configured in TOML and never hardcoded.
- [x] Import scan responses include per-row target status metadata so manual
      import remaps can show `No change`, `New`, or `Replace` without exposing
      raw source values.
- [x] Import commit validates selected targets against current effective config, rejects duplicate selected targets, recomputes latest status, skips no-change rows using derived comparison metadata where applicable, fills missing enabled derived variables, and invalidates affected service test status.
- [x] Import wizard tracks typed path, selected file, and dropped file sources separately.
- [x] Browse mode displays `Selected file: <filename>` and rescans cached file content.
- [x] Drop mode displays `Dropped file: <filename>` and rescans cached file content.
- [x] Manual edits to the import source field switch back to typed-path mode.
- [x] Import wizard can test unsaved scan candidate values for service-token rows without saving or mutating the dashboard service-test cache.
- [x] Import row test buttons render immediately before `Status`, use icon-only row status, and reset on target/source changes.
- [x] CLI supports default launch, `serve`, `status`, `config path`, `config open`, `--config-root`, `--profile`, `--env-path`, and `--verbose`.
- [x] Stable wrapper-facing entrypoints are exposed through `dotfill.entrypoints`.
- [x] `run_dotfill(...) -> int` supports `config_dir`, `config_root`, `profile`,
      `default_profile`, `locked_profile`, `env_path`, `argv`, `program_name`,
      paired `wrapper_name`/`wrapper_version`, and `before_config_load`.
- [x] Wrapper entrypoints can use `locked_profile` to enforce one profile while preserving config-root, env-path, argv, program-name, and before-config-load behavior.
- [x] Local server binds to `127.0.0.1`; `/api/bootstrap` is public and all other API endpoints require `X-Dotfill-Session`.
- [x] Mutating API endpoints reject unexpected non-local `Origin` headers and emit no permissive CORS headers.
- [x] Domain errors map to non-secret JSON responses.
- [x] Static frontend uses no browser storage for secrets and keeps token/import input in memory only.
- [x] Static frontend persists only the non-secret `dotfill.theme` color-theme preference.
- [x] Dashboard shows target `.env` path as the primary path and config directory inside a collapsed `dotfill config` disclosure.
- [x] Dashboard includes a persisted light/dark mode toggle.
- [x] Browser tabs use a local package favicon instead of the browser default.
- [x] Service icon config values are validated against a public service icon
      registry and unknown icon names are rejected during config loading.
- [x] The bundled SVG sprite contains public service icons and private UI
      control symbols without making every sprite symbol service-configurable.
- [x] Frontend icon rendering falls back to the `key` symbol if a referenced
      SVG symbol is unavailable.
- [x] Dashboard supports empty generic state when no services, identities, or derived variables are configured.
- [x] Dashboard version display keeps the dotfill package version visible and
      appends optional wrapper name/version metadata supplied by the stable
      entrypoint.
- [x] Unresolved identities never fail state construction; derived variables
      report `unresolved`, and service token-page/test URLs resolve
      independently with per-URL missing identities.
- [x] Identity detectors `windows_ad` and opt-in `entra` support per-detector
      `priority`; `email_by_domain` picks the first match in priority order.
- [x] Identity detection runs as chained, single-flight background passes with
      outcome-based caching (`complete`/`partial`/`failed`) and backoff; the
      dashboard shows pending detection, polls within a server deadline, and
      rechecks when a retry is due or the page becomes visible.
- [x] The Entra detector silently reads Graph `/me` through MSAL's Windows
      broker in process (no child process), with a fixed scope set per client
      mode, keeps only SMTP proxy addresses, and never logs or stores the
      token.
- [x] The Windows AD detector reads SAM name and UPN in-process and reports
      short timeout diagnostics without the generated script.

## Verification Matrix

Run before publishing a release or accepting broad behavior changes:

```powershell
uv run pytest
uv build
uv run dotfill --help
uv run python -m dotfill --help
```

Focused verification areas:

- [x] Config path/root/profile resolution.
- [x] TOML load, merge, disable semantics, strict schema validation, and useful non-secret errors.
- [x] Empty config state with no built-in services.
- [x] Identity fact collection and dynamic identity rule evaluation.
- [x] Explicit-domain Windows AD lookup, DNS-hint validation, no-match boundary,
      compatibility fallback, and diagnostic parsing.
- [x] `.env` parser/writer preservation and duplicate managed-variable handling.
- [x] Save and backup behavior.
- [x] Import scan and commit behavior, including derived default fill and no raw source values in responses.
- [x] Derived default API and dashboard actions for missing and diverged values.
- [x] Repeated derived-default API no-op behavior and frontend in-flight guard.
- [x] Import-row service testing with backend-held candidate values and no saved-token cache mutation.
- [x] Bearer, header API-key, and basic service test behavior with
      secret-safe logging.
- [x] API session protection, origin checks, CORS absence, and bootstrap behavior.
- [x] CLI commands and stable entrypoint behavior.
- [x] Wrapper display-metadata validation, launch propagation, bootstrap payload,
      and text-only frontend formatting.
- [x] Frontend static checks for no secret browser storage and generic bundled assets.
- [x] Frontend theme preference and import-test state helper behavior.
- [x] Public service icon registry validation and bundled sprite alignment.
- [x] Build artifact inspection includes static assets such as `app.js`, `app.css`, and helper modules.
- [x] Non-blocking unresolved state across resolver, API (state, test, test-all,
      import test), CLI `status`, and dashboard service actions.
- [x] Detector schema, priority ordering, lazy chaining, caching/backoff,
      pending deadlines, and single-flight passes with fake detectors and an
      injectable clock.
- [x] Entra helper request construction, output parsing, failure mapping, and
      token secret boundary; AD in-process names and timeout sanitizing.


## Implemented: Locked Wrapper Profiles

Goal: let wrappers enforce one profile through the stable entrypoint.

- [x] Add `locked_profile: str | None = None` to `run_dotfill(...)`.
- [x] Validate entrypoint combinations: `locked_profile` cannot be combined with
      `config_dir`, `profile`, or `default_profile`.
- [x] Preserve valid wrapper inputs with locked profiles: `config_root`,
      `env_path`, `argv`, `program_name`, and `before_config_load`.
- [x] Enforce locked profile resolution in the CLI callback so the resolved
      `ConfigContext.profile` is always the locked profile.
- [x] Accept redundant CLI `--profile <locked>` and reject CLI
      `--profile <other>` with a clean CLI error.
- [x] Accept absent `DOTFILL_PROFILE` and matching `DOTFILL_PROFILE=<locked>`;
      reject non-matching `DOTFILL_PROFILE`.
- [x] Keep `--config-root` precedence working with locked profiles.
- [x] Add focused tests for valid locked-profile context resolution, invalid
      entrypoint combinations, CLI profile mismatch, environment profile
      mismatch, redundant matching profile input, `--config-root`, and
      `before_config_load` timing.
- [x] Update public README and user docs for wrapper authors after the API is
      implemented.

## Implemented: Identity and Derived Display/Compare Metadata

Goal: allow generic TOML config to control presentation and equality semantics
for identity-like values without changing service-token secrecy rules.

- [x] Add config model fields for identity and derived metadata:
      `display = "plain" | "masked"` and
      `compare = "exact" | "casefold"`.
- [x] Validate the new fields in strict TOML schema loading, with defaults
      `display = "plain"` and `compare = "exact"`.
- [x] Add shared helpers for display masking and comparison equality.
- [x] Apply identity `compare` when resolving explicit `.env` identity values
      against detected values.
- [x] Apply derived `compare` when computing derived `aligned`/`diverged`
      status.
- [x] Apply derived `compare` to import scan and commit no-change detection for
      derived targets.
- [x] Keep service token display and comparison behavior unchanged: always
      masked, always exact.
- [x] Ensure comparison metadata never normalizes or rewrites stored values by
      itself.
- [x] Apply identity/derived `display` to API responses, CLI `status`, and
      dashboard rendering so masked items do not expose raw values.
- [x] Keep import scan source previews masked regardless of target display
      metadata.
- [x] Add focused tests for schema validation/defaults, identity casefold
      alignment, derived casefold alignment, derived import no-change behavior,
      masked identity/derived API payloads, masked CLI status output, and
      unchanged service-token behavior.
- [x] Update `docs/config-schema.md`, getting-started/troubleshooting examples
      as needed, and README references after implementation.


## Implemented: Persisted Light/Dark Theme

Goal: let users switch between light and dark modes and keep the selected
theme across browser sessions without relaxing the secret-storage boundary.

- [x] Add a small theme module in the static frontend that resolves the active
      theme from `localStorage`, then `prefers-color-scheme`, then a stable
      default.
- [x] Persist only a non-secret preference key such as `dotfill.theme`, with
      allowed values `light` and `dark`.
- [x] Handle unavailable or blocked browser storage gracefully by falling back
      to session-only theme state.
- [x] Apply the resolved theme to the document before main app rendering where
      practical to avoid a visible theme flash.
- [x] Add a compact light/dark toggle to the dashboard header with accessible
      label/title text and a state that reflects the active theme.
- [x] Add dark-theme CSS tokens for page, surfaces, borders, text, form
      controls, buttons, badges, errors, dropzone, mapping table, and focus
      outlines.
- [x] Keep the UI readable in both themes, including disabled states and
      status colors.
- [x] Update static frontend storage checks to allow only the theme preference
      storage path and continue rejecting secret/session/import persistence.
- [x] Add focused frontend tests or static checks for theme resolution,
      persistence key/value constraints, and toggle wiring.
- [x] After implementation, update the current-status checklist to mark the
      persisted light/dark mode as implemented.

## Implemented: Import Row Service Tests

Goal: allow users to test an imported service token before committing it,
using the backend-held scan candidate value and without saving the value.

- [x] Add an API request model for import-row service tests containing
      `scanId`, `sourceKey`, and `targetKey`.
- [x] Add a dedicated mutating endpoint such as `POST /api/import/test` behind
      normal session and origin protection.
- [x] Validate that the scan exists, the source key exists in
      `ImportScanSession.candidates`, and the selected target key belongs to
      an enabled service token variable.
- [x] Reject skipped/unmapped targets, derived-variable targets, and unknown
      service token variables with non-secret errors.
- [x] Resolve the selected service's test URL using the current effective
      identity values.
- [x] Run `run_service_test` with the scan candidate's raw value from backend
      session memory, never from the browser.
- [x] Return only non-secret result fields: service ID, status, HTTP status,
      and sanitized error message.
- [x] Do not write the target `.env`, mutate `ImportScanSession`, create a
      backup, or update `SessionState.test_results`.
- [x] Add API tests for successful candidate testing, failed authentication,
      unknown scan/source/target errors, derived-target rejection, and
      unchanged saved-token cache behavior.
- [x] Add frontend state for per-row import-test status: untested, testing,
      working, and failed.
- [x] Render a narrow action column immediately before `Status`.
- [x] Show an approximately checkbox-sized button with the same test icon used
      by main service-test actions only when the current `Save as` value
      resolves to an enabled service token variable and the row status is not
      `no_change`.
- [x] Hide the button for skipped/unmapped rows, derived-variable targets,
      non-service targets, and no-change rows.
- [x] Add tooltip/title text explaining that the button tests the selected
      service using the imported API key.
- [x] On click, call the import-test endpoint with scan ID, source key, and
      current target key; disable or show in-progress state while the request
      is running.
- [x] On success, show a green check; on failure, show a red x without
      embedding detailed failure context in row tooltip or status text.
- [x] Ensure detailed import-test success/failure context is reported through
      the existing service-test logger/console path, with any extra diagnostic
      context gated by normal `--verbose` logging behavior.
- [x] Reset the row's test state when its `Save as` selection changes.
- [x] Reset all import row test states when Scan is pressed, when the path
      input changes, or when a file is browsed or dropped.
- [x] Add focused frontend/static tests for eligibility, action-column wiring,
      API payload shape, and reset behavior.
- [x] Verify the import table remains compact and usable on narrow viewports.
- [x] After implementation, update current-status and verification checklists
      to mark import-row service testing as implemented.

## Implemented: Multi-Mode Service-Test Auth

Goal: let configured services test bearer tokens, header API keys, and basic
auth credentials through generic TOML without adding provider-specific behavior
or weakening secret boundaries. Query-string auth remains deferred.

- [x] Add an `AuthConfig` config model with supported kinds `bearer`,
      `header`, and `basic`; keep omitted service auth defaulting to bearer.
- [x] Add `test_headers: dict[str, str]` to `ServiceDefinition`, defaulting to
      no extra headers.
- [x] Reject scalar service auth values such as `auth = "bearer"`; a present
      auth value must be `[services.<ID>.auth]`.
- [x] Validate auth tables strictly:
      unknown kinds, `kind = "query"`, unknown fields, missing required fields,
      invalid HTTP header names, basic auth with both or neither username
      source, basic literal usernames containing `:`, and unknown or disabled
      `username_identity` references must fail schema loading with non-secret
      errors.
- [x] Validate `test_headers` as a string table with valid HTTP header names,
      non-empty values, and no case-insensitive duplicate header names.
- [x] Reject case-insensitive conflicts between static `test_headers` and the
      auth-generated header for bearer, header, or basic auth.
- [x] Update config merge semantics so `[services.<ID>.auth]` replaces as a
      unit when present in a later layer.
- [x] Update config merge semantics so `[services.<ID>.test_headers]` merges
      by case-insensitive header name, with later layers overriding earlier
      values while preserving the later configured casing.
- [x] Add a centralized service-test request preparation helper that starts
      with `Accept: application/json`, applies static test headers, then adds
      the auth-generated header.
- [x] Implement bearer request preparation as
      `Authorization: Bearer <token>`.
- [x] Implement header API-key request preparation by placing the token in the
      configured header name.
- [x] Implement basic auth request preparation as
      `Authorization: Basic <base64(username:token)>`, resolving
      `username_identity` from current identity state at test time.
- [x] Make unresolved basic `username_identity` fail only that service test
      with non-secret error context unless another state dependency already
      requires the same identity.
- [x] Thread current identity values through saved-token tests, test-all, and
      import-row candidate tests so all paths use the same auth preparation.
- [x] Expand the service-test fingerprint to include normalized auth config,
      normalized static headers, TLS setting, resolved test URL, service ID,
      token variable, session-scoped token digest, and session-scoped digest of
      any resolved basic username material.
- [x] Keep service-test logs and API responses free of raw tokens, generated
      auth headers, configured API-key headers, Basic-encoded credentials,
      dropped import contents, and full `.env` contents.
- [x] Add config-loader and merge tests for valid bearer/header/basic auth,
      omitted-auth defaults, scalar-auth rejection, query rejection, strict
      auth field validation, static header validation, header conflicts, auth
      table replacement, and case-insensitive static-header overrides.
- [x] Add service-test unit tests for outbound bearer, header API-key, basic
      auth, static headers, default `Accept`, TLS behavior, unresolved basic
      username handling, and secret-safe logs.
- [x] Add resolver/API tests proving cached status invalidates when auth kind,
      auth header, static headers, basic username source or resolved value,
      TLS, URL, or token changes.
- [x] Add import-row service-test API tests proving unsaved candidate values
      use the configured auth mode without updating saved-token cache.
- [x] Update `README.md`, `docs/config-schema.md`, `docs/getting-started.md`,
      and `docs/troubleshooting.md` after implementation so public docs no
      longer describe service tests as bearer-only.
- [x] After implementation, update current-status and verification checklists
      to mark bearer/header/basic auth and static service test headers as
      implemented.

## Implemented: Public Service Icon Registry

Goal: make service icons a documented, validated config contract while keeping
the frontend sprite local, small, and separate from private UI-control symbols.

- [x] Add `src/dotfill/icons.py` with `DEFAULT_SERVICE_ICON = "key"` and the
      public `SERVICE_ICON_KEYS` registry:
      `key`, `ticket`, `book`, `git-branch`, `package`, `cloud`,
      `brand-github`, `brand-gitlab`, `server`, `database`, `terminal`,
      `shield`, `search`, `globe`, and `lock`.
- [x] Update `resolver.py` to import `DEFAULT_SERVICE_ICON` from `icons.py` so
      the default service icon is defined beside the public registry.
- [x] Update `config_loader.py` to validate optional
      `services.<ID>.icon` values against `SERVICE_ICON_KEYS`; omitted icons
      continue to resolve to `DEFAULT_SERVICE_ICON`, and unknown values raise a
      `ConfigSchemaError` naming the bad value and valid keys.
- [x] Add bundled Tabler-style SVG symbols in `static/index.html` for the new
      public service icons that are not already present: `server`, `database`,
      `terminal`, `shield`, `search`, `globe`, and `lock`.
- [x] Keep private UI symbols such as `arrow-left`, `arrow-right`, `check`,
      `x`, `alert`, `refresh`, `cloud-upload`, `sun`, and `moon` out of
      `SERVICE_ICON_KEYS`.
- [x] Update the frontend `icon()` helper in `static/app.js` to check for
      `document.getElementById("ic-<name>")` and fall back to `ic-key` when a
      referenced symbol is unavailable; this is only a render-time guard, not
      the config validation source of truth.
- [x] Add config-loader tests for a valid newly added icon, omitted-icon
      default behavior, and unknown-icon `ConfigSchemaError` messaging.
- [x] Add static asset tests that parse `static/index.html` for `ic-*` symbols
      and assert every `SERVICE_ICON_KEYS` entry has a matching symbol, without
      requiring every sprite symbol to be service-configurable.
- [x] Add or update frontend/static tests proving the icon helper includes the
      missing-symbol fallback path.
- [x] Update `docs/config-schema.md` to publish the supported service icon
      keys and state that unknown names are config errors; refresh README or
      getting-started examples only if their icon wording becomes incomplete.
- [x] Run focused verification with `uv run pytest tests/test_config_loader.py
      tests/test_static_assets.py`, then run the full `uv run pytest` suite.

## Implemented: Derived Default Fill and Reset Actions

Goal: keep derived-variable fill-in behavior conservative while allowing users
to explicitly write computed defaults for missing or customized derived values.

- [x] Update `dev/docs/requirements.md` and
      `dev/docs/design-specification.md` to define identity and derived states,
      import-fill behavior, and explicit derived default actions.
- [x] Add a session-protected mutating endpoint:
      `POST /api/derived/{variable_name}/default`.
- [x] In the endpoint, reload current state and allow writes only when
      `{variable_name}` is an enabled derived variable, the current derived
      status is `missing` or `diverged`, and `computed_default` is available.
- [x] Reject unknown or non-derived targets with `404`, treat already-aligned
      rows as successful no-ops, and reject unresolved or otherwise
      non-computable derived rows with `409`.
- [x] Write exactly `{variable_name: computed_default}` through the existing
      save pipeline and return `{"ok": true, "updated": ["VARIABLE"]}`.
- [x] Update import commit so selected import updates are built first, then
      missing enabled derived defaults are added with
      `updates.setdefault(d.variable_name, d.computed_default)`.
- [x] Preserve explicit import mappings over computed defaults; do not
      overwrite aligned/diverged values automatically, and do not write
      unresolved values, disabled derived variables, or identity variables.
- [x] Add dashboard row actions in the derived-variable list:
      `Fill with default` for missing rows and `Use default` for diverged rows.
      Aligned and unresolved rows should have no write action.
- [x] After a derived default action succeeds, reload dashboard state; on
      stale or ineligible failures, report the existing API error message
      through the current error surface.
- [x] Add API tests for missing fill, diverged reset, aligned no-op behavior,
      unknown/non-derived rejection, and ensuring the endpoint cannot write
      identities or arbitrary keys.
- [x] Add import tests proving import commits fill missing computable derived
      defaults, explicit imported derived values win, diverged values are
      preserved, and disabled derived variables and identities are not written.
- [x] Keep existing regressions green for token-save fill, diverged
      token-save preservation, casefold alignment without rewrite, and derived
      import no-change comparison.
- [x] Update public docs after implementation if the dashboard row actions or
      import-fill behavior need user-facing explanation.
- [x] After implementation, update current-status and verification checklists
      to mark derived import-fill and dashboard default actions as implemented.

## Implemented: Explicit-Domain Windows AD Lookup

Goal: resolve generic Windows AD facts on devices that can reach the user
directory but do not provide a usable computer-domain default naming context.

- [x] AD-BIND-01 Document the explicit-domain bind strategy, safe domain-hint
      selection, compatibility fallback boundary, and neutral diagnostics.
- [x] AD-BIND-02 Add a failing regression test for a valid explicit user-domain
      hint on a device where a serverless lookup is unavailable.
- [x] AD-BIND-03 Refactor the PowerShell probe to prefer a DNS-safe
      `USERDNSDOMAIN`, fall back to a valid `whoami /upn` suffix, and root the
      search at `LDAP://<dns-domain>`.
- [x] AD-BIND-04 Retain serverless lookup only when no valid hint exists or the
      explicit bind/search raises; do not cross into the default context after
      a successful explicit search returns no match.
- [x] AD-BIND-05 Preserve the existing generic fact protocol and surface safe
      diagnostics when both explicit and compatibility lookup paths fail.
- [x] AD-BIND-06 Add focused tests for valid, missing, and unsafe hints;
      explicit-root construction; exception fallback; no-match behavior; and
      unchanged fact parsing.
- [x] AD-BIND-07 Verify the probe on a traditional domain-joined device and on
      a cloud/hybrid-joined device with directory-controller reachability, then
      run the full test suite.
- [x] AD-BIND-08 Update user-facing troubleshooting guidance after the behavior
      is implemented, using only neutral domains and device descriptions.

## Implemented: Idempotent Derived Default Actions

Goal: make rapid, repeated, or stale derived-default requests harmless and
keep the dashboard from presenting a false failure after the first request
already succeeded.

- [x] DERIVED-IDEM-01 Document aligned requests as successful no-ops and define
      the frontend per-variable in-flight guard.
- [x] DERIVED-IDEM-02 Add an API reproducer that posts the same missing-derived
      default action twice and expects the second response to succeed with
      `updated = []` while preserving the first value.
- [x] DERIVED-IDEM-03 Change the endpoint to return idempotent success for an
      already-aligned value while retaining `404` for unknown/disabled targets
      and `409` for unresolved/non-computable targets.
- [x] DERIVED-IDEM-04 Disable the clicked row action immediately and suppress a
      second request for the same variable until the first request and refresh
      settle.
- [x] DERIVED-IDEM-05 Add frontend regression coverage for the in-flight guard,
      disabled state, retry after failure, and no error banner after an aligned
      no-op response.
- [x] DERIVED-IDEM-06 Run focused API/frontend tests and the full test suite;
      update user-facing troubleshooting text only if the corrected behavior
      changes useful user guidance.

## Implemented: Wrapper Version Display Metadata

Goal: let a wrapper identify its own command/version in the dashboard while
keeping the dotfill package version visible and authoritative.

- [x] WRAP-META-01 Document paired optional `wrapper_name`/`wrapper_version`
      entrypoint inputs, bootstrap payload shape, and dashboard formatting.
- [x] WRAP-META-02 Add paired optional parameters to `run_dotfill(...)`, reject
      partial or blank metadata, and keep `program_name` behavior independent.
- [x] WRAP-META-03 Propagate validated metadata through both dashboard launch
      paths into `AppContext` and expose a structured nullable `wrapper` value
      from `/api/bootstrap`.
- [x] WRAP-META-04 Render direct launches as `v<dotfill-version>` and wrapped
      launches as
      `v<dotfill-version> (<wrapper-name> v<wrapper-version>)` using text nodes.
- [x] WRAP-META-05 Add entrypoint, CLI propagation, API bootstrap, and static
      frontend tests for absent, valid, partial, blank, and markup-like metadata.
- [x] WRAP-META-06 Update README and wrapper-author documentation with a neutral
      `run_dotfill(...)` example after implementation, then run packaging and
      full-suite verification.

## Implemented: Deterministic JavaScript MIME Type

Goal: keep the local dashboard usable when host-level MIME configuration maps
`.js` files to `text/plain`.

- [x] STATIC-MIME-01 Document that packaged JavaScript assets must be served
      with an explicit JavaScript media type independent of host MIME mappings.
- [x] STATIC-MIME-02 Add a server regression test that forces the host `.js`
      mapping to `text/plain` and still expects a JavaScript response type.
- [x] STATIC-MIME-03 Override the static response media type for `.js` assets
      without changing other static-file behavior.
- [x] STATIC-MIME-04 Change the entry-module cache key so browsers do not reuse
      a previously cached response with the invalid media type.
- [x] STATIC-MIME-05 Run focused server/static tests and the full test suite,
      then update troubleshooting and release-note documentation.

## Planned: Identity Resolution Resilience

Goal: keep dotfill usable when identity detection partially fails. Examples
include devices off the corporate network, cloud-joined devices where
directory Kerberos fails (for example Windows Hello sign-in against domain
controllers without the KDC Authentication EKU), and sessions that change
sign-in method while the server is running. Add a silent Entra/Microsoft Graph
detector that works without directory reachability.

Field findings that motivate this work (cloud-joined Windows device, hybrid
account):

- Password sign-in on the corporate network: Windows AD lookup succeeds.
- Off VPN: the AD probe hits its 15-second timeout; every state refresh repeats
  the wait and then fails with `409` because a derived variable needs the
  unresolved identity.
- Windows Hello PIN sign-in: Kerberos/LDAP binds hang (System log Kerberos
  event 19, KDC certificate missing EKU `1.3.6.1.5.2.3.5`); same `409`.
- `GetUserNameExW(NameUserPrincipal)` returns the UPN instantly in all cases.
- Silent Web Account Manager token + Graph `/me` returns `mail` and
  `proxyAddresses` for every configured domain in about 0.6 seconds, with PIN
  sign-in and without Kerberos.

### Phase 1 — Non-blocking unresolved state

ID-RESILIENCE-24 refines ID-RESILIENCE-04/-07: token and test URLs resolve
independently rather than being cleared together.

- [x] ID-RESILIENCE-01 Update requirements/design so unresolved identities never
      fail state construction; add `unresolved` derived status, per-service
      unresolved URLs, and test-endpoint behavior.
- [x] ID-RESILIENCE-02 Replace
      `test_unresolved_identity_required_by_derived_blocks_state` with a
      failing reproducer expecting an `unresolved` derived state (with the
      current `.env` value reported) and successful state construction.
- [x] ID-RESILIENCE-03 Change `build_derived_states` to emit `unresolved` with
      `computed_default = None` instead of raising.
- [x] ID-RESILIENCE-04 Add a failing reproducer for a service URL template that
      needs an unresolved identity; resolve service URLs per service, set
      `resolved_token_url`/`resolved_test_url` to `None`, and populate
      `ServiceState.unresolved_identities`.
- [x] ID-RESILIENCE-05 Make `POST /api/test/{service_id}` return a non-secret
      `409`, `POST /api/test-all` record a per-service failure and continue,
      and `POST /api/import/test` fail only that row when a test URL needs an
      unresolved identity; add API tests for each path.
- [x] ID-RESILIENCE-06 Add API tests proving `/api/state` returns `200` with
      unresolved identity/derived/service items, token saves still work and
      skip unresolved derived fills, and the derived-default endpoint keeps
      returning `409` for unresolved rows.
- [x] ID-RESILIENCE-07 Render unresolved items inline in the dashboard: derived
      rows with an `Unresolved` badge and no write action; service cards
      without token link/test actions and naming the missing identity. Add
      frontend/static tests.
- [x] ID-RESILIENCE-08 Show unresolved derived rows and services with missing
      identities in CLI `status` without failing the command; add CLI tests.
- [x] ID-RESILIENCE-24 Resolve `token_url` and `test_url` independently with
      `token_url_unresolved_identities`/`test_url_unresolved_identities`; keep
      the test action when only the token URL is unresolved and the token link
      when only the test URL is unresolved. Add resolver, API, and frontend
      tests for each one-sided case.

### Phase 2 — Detector framework, caching, and AD hardening

ID-RESILIENCE-25 through -27 refine ID-RESILIENCE-12: caching is outcome-based
(`complete`/`partial`/`failed`) with backoff, and detection runs in the
background within a state wait budget. ID-RESILIENCE-32 and -33 refine -26 and
-27: detection is one chained background pass, and the server reports how
long the dashboard should poll and when to recheck. ID-RESILIENCE-33 code and
automated tests are done; its manual open-dashboard VPN-reconnect check is
pending with ID-RESILIENCE-30.

- [x] ID-RESILIENCE-09 Extend `[identity.detectors.<name>]` schema with
      `priority` and the `entra` detector (`enabled`, `priority`, optional
      `client_id`, `tenant`); validate types, GUID/DNS-safe values, and
      unknown keys; add loader tests.
- [x] ID-RESILIENCE-10 Add the detector-neutral `email_by_domain` source and
      `entra.email_by_domain`; reject pinned sources whose detector is
      disabled and `email_by_domain` when no detector is enabled; add loader
      and rule tests.
- [x] ID-RESILIENCE-11 Add `identity_detectors.py` with priority ordering,
      lazy execution (skip lower-priority detectors once all needed domains
      are matched; honor explicit `.env` overrides), and per-identity
      detector attribution and diagnostics; add tests with injected fake
      detectors.
- [x] ID-RESILIENCE-12 Cache detector results in `SessionState`, keyed by
      detector name and config fingerprint: successes for the process
      lifetime, failures/empty results for a 60-second retry interval. Add
      tests with an injectable clock proving refreshes do not re-run
      successful detectors, failures retry after the interval, and config
      changes invalidate the cache.
- [x] ID-RESILIENCE-13 Add a reproducer showing a probe timeout diagnostic
      currently embeds the generated script; replace it with a short
      non-secret diagnostic and keep stdout emitted before the timeout
      parseable.
- [x] ID-RESILIENCE-14 Read SAM-compatible name and UPN in-process via
      `GetUserNameExW` so they survive LDAP failure or timeout; skip the call
      off Windows; add tests with the Windows API call stubbed.
- [x] ID-RESILIENCE-15 Surface per-identity detector diagnostics through the
      API identity payload, dashboard (tooltip or detail text), and CLI
      `status`; keep them short and non-secret; add tests.
- [x] ID-RESILIENCE-25 Classify detector runs as `complete`, `partial`, or
      `failed`. Cache only `complete` for the process lifetime; retry `partial`
      and `failed` with backoff (60 seconds doubling to a 15-minute cap, reset
      on complete). Treat an AD run with in-process facts but an LDAP
      failure/timeout as `partial`. Add clock-injected tests, including a
      partial-to-complete transition that resolves a previously missing
      domain.
- [x] ID-RESILIENCE-26 Add a single-flight background `DetectorRunner`: state
      builds wait at most a budget (default 2 seconds), mark still-running
      identities `unresolved` with a `detection pending` diagnostic, and set
      `identity_detection_pending`; backoff retries run in the background; CLI
      `status` waits for completion. Add tests with a blocking fake detector
      proving refreshes return within the budget and concurrent builds share
      one run.
- [x] ID-RESILIENCE-27 Show a dashboard pending indicator and re-fetch state on
      a bounded poll while detection is pending; stop polling when it clears
      or the poll limit is reached. Add frontend/static tests.
- [x] ID-RESILIENCE-32 Run detection as a single chained background pass: after
      each detector finishes, immediately start the next needed detector
      without waiting for another state build; keep
      `identity_detection.pending` true until the pass ends; report
      `pending_deadline_seconds` as the sum of the remaining queued/running
      detector timeouts plus a margin. Add tests with fake detectors: a slow
      Entra failure followed by a slow AD success resolves the identities with
      no further state request, `pending` stays true across both runs, and the
      deadline covers both.
- [ ] ID-RESILIENCE-33 Report `next_retry_seconds` in state; in the dashboard,
      bound polling by the server-reported `pending_deadline_seconds`,
      schedule one state fetch when a retry becomes due, and re-fetch when the
      page becomes visible again. Add frontend tests with fake timers for the
      poll bound, the retry-due fetch, visibility re-fetch, and no duplicate
      timers. Manually verify that an open dashboard recovers after a VPN
      reconnect without a manual refresh.
- [x] ID-RESILIENCE-39 Review fix: when the detector config changes during a
      pass, report the new request's detectors as pending (deadline includes
      the running pass), start a pass for the latest request as soon as the
      old pass ends, and make `wait=None` wait for the caller's own
      detectors. Tests cover an Entra-only to AD-only change mid-pass and an
      unbounded wait behind another pass.
- [x] ID-RESILIENCE-40 Review fix: cache test-all failures for unresolved
      test URLs with a fingerprint of service, token digest, and missing
      identities so a state refresh keeps showing `failed` until the
      identities resolve. Tests cover the post-refresh view and clearing
      once the identity resolves.
- [x] ID-RESILIENCE-41 Add a regression for a config change behind a stalled
      detector pass; make the queued request's polling deadline expire even
      when repeated state requests arrive after the original deadline.
- [x] ID-RESILIENCE-42 Add regressions for more than 1,024 consecutive failed
      or partial results; keep backoff capped without overflow and preserve
      the initial delay after detector configuration changes.
- [x] ID-RESILIENCE-43 Document the deadline and backoff fixes, run the
      detector regressions and full test suite, and reconcile the session.

### Phase 3 — Entra (Microsoft Graph) detector

ID-RESILIENCE-35 supersedes ID-RESILIENCE-28. The ID-RESILIENCE-34 probe showed
that, for the built-in client ID, every `User.Read` request fails with
`AADSTS65002`, and that Microsoft first-party clients return the same broad
scopes whatever is requested. Each client mode therefore uses one fixed request
form, with no format fallback. ID-RESILIENCE-29 and -30 extend ID-RESILIENCE-19
with failure handling and second-user verification; the built-in client ID is
best-effort, not a guarantee. ID-RESILIENCE-28 stays open only as superseded.
Manual progress on ID-RESILIENCE-19 (2026-09-28, one cloud-joined device with
Kerberos to the directory failing): Entra resolved both configured domains in
about 1 second with AD skipped, a tenant-domain authority also worked, and
with Entra disabled AD returned a partial result (in-process UPN) and
unresolved identities with diagnostics instead of an error. Off-VPN and
password-sign-in runs are still pending.

- [x] ID-RESILIENCE-16 Implement `identity_entra.py`: a Windows PowerShell 5.1
      helper using `WebAuthenticationCoreManager.GetTokenSilentlyAsync` with
      resource `https://graph.microsoft.com`, the configured or built-in
      client ID (Azure CLI public client), and a hard timeout; call Graph
      `/me?$select=mail,userPrincipalName,proxyAddresses` and emit only
      `MAIL`/`UPN`/`PROXY`/`ERR` lines.
- [x] ID-RESILIENCE-17 Add tests for helper generation (validated
      `client_id`/`tenant` interpolation, no interactive token API, no token
      output), output parsing into shared facts, silent-token/Graph/timeout
      failures as diagnostics, and non-Windows unavailability.
- [x] ID-RESILIENCE-18 Add a static/secret-boundary test proving the helper
      never writes, logs, or returns the access token and that no dotfill log
      line contains token-like material from the Entra path.
- [ ] ID-RESILIENCE-19 Verify manually on a cloud-joined device: password
      sign-in, Windows Hello PIN sign-in, and off-VPN. Confirm Entra resolves
      both email domains without delay, AD is skipped when Entra satisfies
      all domains, and disabling Entra falls back to AD.
- [ ] ID-RESILIENCE-28 Request the delegated `https://graph.microsoft.com/User.Read`
      scope through Web Account Manager, falling back to the v1 Graph resource
      form only if the broker rejects scoped requests. Record which form works
      and add tests for the request construction.
- [x] ID-RESILIENCE-29 Map silent-token failures (interaction required,
      client blocked by policy, provider unavailable) to distinct short
      diagnostics and a `failed` outcome, and verify fallback to
      lower-priority detectors and explicit `.env` values; add tests.
- [ ] ID-RESILIENCE-30 Manual verification with Graph unavailable (Entra
      disabled or silent acquisition failing) and VPN disconnected: the
      dashboard stays responsive within the wait budget and shows pending,
      then unresolved with diagnostics; no refresh stalls on AD retries; a VPN
      reconnect resolves the identities after the next retry. Also verify the
      built-in client ID on a second user or device.
- [x] ID-RESILIENCE-34 Probe silent Web Account Manager request forms for the
      Azure CLI (built-in) and Graph PowerShell client IDs on a cloud-joined
      device, without logging tokens; record the success/failure and effective
      `scp` results in the design's Entra Detector evidence table.
- [x] ID-RESILIENCE-35 Use one fixed request form per client mode: built-in ID
      with an empty scope plus the Graph `resource` property; configured
      `client_id` with `User.Read` plus the Graph `resource` property. Never
      retry with a different form. Map `AADSTS65002` to
      `entra: client not authorized for Microsoft Graph`. Add request
      construction tests for both modes and a test proving no alternate-form
      retry occurs.
- [x] ID-RESILIENCE-36 Keep only `smtp:`/`SMTP:` proxy addresses in Entra
      helper output and drop other types such as `X500:`; add a parsing test
      with mixed proxy address types.
- [ ] ID-RESILIENCE-37 When an approved app registration consented for
      `User.Read` is available, verify through `client_id` that silent
      acquisition succeeds and that the effective `scp` is limited to that
      grant; record the result in the design evidence table.

### Phase 4 — Documentation and release

Released 1.5.0 on 2026-09-29. Verification passed: 427 automated tests,
CLI/module help smoke checks, wheel and source builds with metadata and asset
inspection, the GitHub trusted-publishing workflow, and a fresh installation
from PyPI. The manual device/VPN checks above remain open.

- [x] ID-RESILIENCE-20 Update `docs/config-schema.md` with detector
      `priority`, the `entra` detector options, `email_by_domain` and
      `entra.email_by_domain`, and the unresolved-state behavior.
- [x] ID-RESILIENCE-31 Document in `docs/config-schema.md` and
      `docs/troubleshooting.md` that the built-in Entra client ID is
      best-effort. Describe configuring an approved app registration through
      `client_id` (public client, delegated `User.Read`, Web Account Manager
      redirect URI) and explicit `.env` values as fallbacks.
- [x] ID-RESILIENCE-38 Document in `docs/config-schema.md` that the built-in
      client ID yields tokens with broad pre-authorized delegated scopes that
      dotfill confines to the helper for a single `/me` call, and that only an
      approved registration consented for `User.Read` provides least
      privilege.
- [x] ID-RESILIENCE-21 Update `docs/troubleshooting.md` for unresolved
      identities: off-network directory lookups, Windows Hello sign-in with
      domain controller certificates lacking the KDC Authentication EKU
      (Kerberos event 19), silent Entra token failures, and explicit `.env`
      overrides as the manual fallback.
- [x] ID-RESILIENCE-22 Update README and getting-started examples where
      detector configuration appears, using neutral domains.
- [x] ID-RESILIENCE-23 Run the full verification matrix, update the
      current-status and verification checklists, add a CHANGELOG entry, and
      release a minor version so wrapper packages can raise their dotfill
      floor.

## Implemented: Entra Detector via MSAL Broker

Goal: remove the Windows PowerShell helper from the Entra detector so endpoint
security tools do not flag dotfill. The 1.5.0 helper runs
`powershell.exe -EncodedCommand` from `python.exe` with a token-acquisition
script, which matches common EDR and AMSI heuristics. The detector instead
calls Microsoft's broker library (MSAL Python with `pymsalruntime`) in
process, the supported path that Azure CLI also uses on Windows, and reads
Graph `/me` with `httpx`. Detector behavior, diagnostics, and fallbacks are
otherwise unchanged.

Field evidence (2026-09-29, one cloud-joined device): MSAL 1.39.0 with
`pymsalruntime` 0.20.6 on Python 3.14 obtained tokens silently with
`acquire_token_interactive(prompt="none")`, never reaching the UI hook. The
built-in client ID worked with `https://graph.microsoft.com/.default` and
failed on `User.Read` with broker status `Status_IncorrectConfiguration`
(error code `0xCAA20002`). A consented public client worked with `User.Read`.
The first token took about 3 seconds; repeat and cross-process requests took
milliseconds because the Windows broker caches tokens.

- [x] ENTRA-BROKER-01 Update requirements and design: in-process MSAL broker,
      per-mode scopes (`https://graph.microsoft.com/.default` for the built-in
      ID, `User.Read` for a configured `client_id`), silent-only call, token
      handling rules, broker-status diagnostics, and a hard timeout.
- [x] ENTRA-BROKER-02 Add `msal[broker]` as a Windows-only dependency, import it
      lazily only when the Entra detector runs, and keep `msal` logs at
      WARNING outside `--verbose`.
- [x] ENTRA-BROKER-03 Replace the PowerShell helper with an MSAL broker token
      request plus an `httpx` Graph `/me` call, with a hard overall timeout that
      abandons a hung broker call without blocking the detection pass.
- [x] ENTRA-BROKER-04 Rewrite Entra detector tests with a fake MSAL app and
      mocked Graph: per-mode scopes and authority, `prompt="none"` with a
      UI hook that fails, no alternate-scope retry, broker-status and
      redirect-URI error mapping, Graph HTTP errors, timeout, missing broker
      library, non-Windows, SMTP-only proxy parsing, and no token in logs,
      diagnostics, or results.
- [x] ENTRA-BROKER-05 Verify live on a cloud-joined device that the detector
      resolves both configured domains with no PowerShell process started.
      Verified 2026-09-29: 0.38 seconds, both domains, no new `powershell.exe`;
      an isolated install of the built 1.5.1 wheel resolved both identities
      with only the Entra detector enabled.
- [x] ENTRA-BROKER-06 Update `docs/config-schema.md`, `docs/troubleshooting.md`,
      README privacy notes, and the CHANGELOG; bump to 1.5.1.
- [x] ENTRA-BROKER-07 Reproduce timed-out lookups overlapping automatic
      retries, including config changes and stalled authority, broker, and
      Graph calls; verify recovery after the original worker exits.
- [x] ENTRA-BROKER-08 Keep one Entra lookup active per process until its worker
      exits, skip subsequent work after its deadline, and bound HTTP waits.
- [ ] ENTRA-BROKER-09 Document timeout and retry behavior, run the release
      checks, and publish and verify 1.5.1 on GitHub and PyPI.

Pre-release verification (2026-09-29): all 442 tests pass, including six
regressions first observed failing before the timeout fix. The 1.5.1 wheel and
sdist build successfully, pass metadata and content checks and a publish dry
run, and the isolated wheel's CLI help works. Open code, secret, and dependency
alert counts are zero. Stale AnyIO alerts #3 and #4 were marked inaccurate
with evidence: GitHub's dependency inventory reported 4.13.0 while the current
remote and release lockfiles already resolve 4.15.1 (patched minimum 4.14.2).

## Future Roadmap

- [ ] Add query-string service-test auth after redacted URL plumbing and tests
      cover logs, `TestResult.error_message`, API responses, exception paths,
      and debug output.
- [ ] Consider a generic health-check response matcher for APIs where any 2xx is not sufficient.
- [ ] Add in-UI affordances for editing or locating TOML config files without turning the UI into a config editor.
- [ ] Add optional same-target import warnings for typed path imports when source and target resolve to the same file.
- [ ] Add richer browser/DOM regression coverage for the import wizard once a lightweight frontend test harness exists.
- [ ] Consider command output format flags for `status` if scripting use grows.
- [ ] Add release automation once package metadata and public repository settings settle.

## Maintainer Notes

- Prefer changing behavior in the shared domain layer before adding API/UI-only logic.
- Keep wrapper packages outside the generic package. They should call stable entrypoints and provide config, not import internal CLI objects.
- Treat raw tokens, dropped import contents, generated auth headers/credentials, and full `.env` contents as secret material.
- Keep browser state transient except explicitly allowed non-secret UI preferences; never store secrets, session tokens, import contents, or full `.env` contents in `localStorage`, `sessionStorage`, IndexedDB, or cookies.
- Keep generated build artifacts out of commits unless explicitly preparing release artifacts.
