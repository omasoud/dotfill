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
- [x] Target `.env` path resolves from CLI `--env-path`, then `[target].default_env_path`, then home `.env`.
- [x] `.env` parsing preserves comments, blank lines, unrelated variables, unrelated duplicates, quote style, and line endings.
- [x] Writes are explicit, atomic, and create at most one backup per process session before the first write.
- [x] Managed variables are enabled identities, enabled derived variables, and enabled service token variables.
- [x] Duplicate managed variables block state construction with line-number context.
- [x] Identity rules support `literal`, `env`, `local_part`, `windows_ad.email_by_domain`, `windows_ad.sam`, and `windows_ad.domain`.
- [x] Identity and derived definitions support `display = "plain" | "masked"` and `compare = "exact" | "casefold"` metadata.
- [x] Windows AD probing returns generic facts only and runs only when an enabled identity needs AD facts.
- [x] Explicit non-empty `.env` identity overrides participate in identity state as aligned, diverged, or unresolved, using configured comparison metadata.
- [x] dotfill never writes identity variables automatically.
- [x] Derived variables copy enabled identities, use configured comparison metadata for aligned/diverged state, and are filled only when missing or empty during token saves.
- [x] Save flow writes the selected service token plus missing enabled derived variables.
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
- [x] Import commit validates selected targets against current effective config, rejects duplicate selected targets, recomputes latest status, skips no-change rows using derived comparison metadata where applicable, and invalidates affected service test status.
- [x] Import wizard tracks typed path, selected file, and dropped file sources separately.
- [x] Browse mode displays `Selected file: <filename>` and rescans cached file content.
- [x] Drop mode displays `Dropped file: <filename>` and rescans cached file content.
- [x] Manual edits to the import source field switch back to typed-path mode.
- [x] Import wizard can test unsaved scan candidate values for service-token rows without saving or mutating the dashboard service-test cache.
- [x] Import row test buttons render immediately before `Status`, use icon-only row status, and reset on target/source changes.
- [x] CLI supports default launch, `serve`, `status`, `config path`, `config open`, `--config-root`, `--profile`, `--env-path`, and `--verbose`.
- [x] Stable wrapper-facing entrypoints are exposed through `dotfill.entrypoints`.
- [x] `run_dotfill(...) -> int` supports `config_dir`, `config_root`, `profile`, `default_profile`, `locked_profile`, `env_path`, `argv`, `program_name`, and `before_config_load`.
- [x] Wrapper entrypoints can use `locked_profile` to enforce one profile while preserving config-root, env-path, argv, program-name, and before-config-load behavior.
- [x] Local server binds to `127.0.0.1`; `/api/bootstrap` is public and all other API endpoints require `X-Dotfill-Session`.
- [x] Mutating API endpoints reject unexpected non-local `Origin` headers and emit no permissive CORS headers.
- [x] Domain errors map to non-secret JSON responses.
- [x] Static frontend uses no browser storage for secrets and keeps token/import input in memory only.
- [x] Static frontend persists only the non-secret `dotfill.theme` color-theme preference.
- [x] Dashboard shows target `.env` path as the primary path and config directory inside a collapsed `dotfill config` disclosure.
- [x] Dashboard includes a persisted light/dark mode toggle.
- [x] Browser tabs use a local package favicon instead of the browser default.
- [x] Dashboard supports empty generic state when no services, identities, or derived variables are configured.

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
- [x] `.env` parser/writer preservation and duplicate managed-variable handling.
- [x] Save and backup behavior.
- [x] Import scan and commit behavior, including no raw source values in responses.
- [x] Import-row service testing with backend-held candidate values and no saved-token cache mutation.
- [x] Bearer, header API-key, and basic service test behavior with
      secret-safe logging.
- [x] API session protection, origin checks, CORS absence, and bootstrap behavior.
- [x] CLI commands and stable entrypoint behavior.
- [x] Frontend static checks for no secret browser storage and generic bundled assets.
- [x] Frontend theme preference and import-test state helper behavior.
- [x] Build artifact inspection includes static assets such as `app.js`, `app.css`, and helper modules.


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
