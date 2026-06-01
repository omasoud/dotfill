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
- [x] Later config layers override scalars and merge keyed tables.
- [x] `enabled = false` removes inherited services, identities, derived variables, and import aliases before required-field validation.
- [x] Target `.env` path resolves from CLI `--env-path`, then `[target].default_env_path`, then home `.env`.
- [x] `.env` parsing preserves comments, blank lines, unrelated variables, unrelated duplicates, quote style, and line endings.
- [x] Writes are explicit, atomic, and create at most one backup per process session before the first write.
- [x] Managed variables are enabled identities, enabled derived variables, and enabled service token variables.
- [x] Duplicate managed variables block state construction with line-number context.
- [x] Identity rules support `literal`, `env`, `local_part`, `windows_ad.email_by_domain`, `windows_ad.sam`, and `windows_ad.domain`.
- [x] Windows AD probing returns generic facts only and runs only when an enabled identity needs AD facts.
- [x] Explicit non-empty `.env` identity overrides participate in identity state as aligned, diverged, or unresolved.
- [x] dotfill never writes identity variables automatically.
- [x] Derived variables copy enabled identities and are filled only when missing or empty during token saves.
- [x] Save flow writes the selected service token plus missing enabled derived variables.
- [x] Service tests support bearer authentication only.
- [x] Service tests send `Authorization: Bearer <token>` and `Accept: application/json`, verify TLS by default, and classify status safely.
- [x] Cached service-test results are process-local and invalidated by token, service, auth, TLS, or URL changes.
- [x] Import scans target enabled service token variables and enabled derived variables; identities are never import targets.
- [x] Import scans skip empty source values and return masked values only.
- [x] Import aliases are configured in TOML and never hardcoded.
- [x] Import commit validates selected targets against current effective config, rejects duplicate selected targets, recomputes latest status, skips no-change rows, and invalidates affected service test status.
- [x] Import wizard tracks typed path, selected file, and dropped file sources separately.
- [x] Browse mode displays `Selected file: <filename>` and rescans cached file content.
- [x] Drop mode displays `Dropped file: <filename>` and rescans cached file content.
- [x] Manual edits to the import source field switch back to typed-path mode.
- [x] CLI supports default launch, `serve`, `status`, `config path`, `config open`, `--config-root`, `--profile`, `--env-path`, and `--verbose`.
- [x] Stable wrapper-facing entrypoints are exposed through `dotfill.entrypoints`.
- [x] `run_dotfill(...) -> int` supports `config_dir`, `config_root`, `profile`, `default_profile`, `env_path`, `argv`, `program_name`, and `before_config_load`.
- [x] Local server binds to `127.0.0.1`; `/api/bootstrap` is public and all other API endpoints require `X-Dotfill-Session`.
- [x] Mutating API endpoints reject unexpected non-local `Origin` headers and emit no permissive CORS headers.
- [x] Domain errors map to non-secret JSON responses.
- [x] Static frontend uses no browser storage and keeps token/import input in memory only.
- [x] Dashboard shows target `.env` path as the primary path and config directory inside a collapsed `dotfill config` disclosure.
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
- [x] Bearer service test behavior and secret-safe logging.
- [x] API session protection, origin checks, CORS absence, and bootstrap behavior.
- [x] CLI commands and stable entrypoint behavior.
- [x] Frontend static checks for no browser storage and generic bundled assets.
- [x] Build artifact inspection includes static assets such as `app.js`, `app.css`, and helper modules.



## Future Roadmap

- [ ] Add configurable non-bearer service-test auth modes.
- [ ] Support provider-specific static headers when service tests need them.
- [ ] Consider a generic health-check response matcher for APIs where any 2xx is not sufficient.
- [ ] Add in-UI affordances for editing or locating TOML config files without turning the UI into a config editor.
- [ ] Add optional same-target import warnings for typed path imports when source and target resolve to the same file.
- [ ] Add richer browser/DOM regression coverage for the import wizard once a lightweight frontend test harness exists.
- [ ] Consider command output format flags for `status` if scripting use grows.
- [ ] Add release automation once package metadata and public repository settings settle.

## Maintainer Notes

- Prefer changing behavior in the shared domain layer before adding API/UI-only logic.
- Keep wrapper packages outside the generic package. They should call stable entrypoints and provide config, not import internal CLI objects.
- Treat raw tokens, dropped import contents, Authorization headers, and full `.env` contents as secret material.
- Keep browser state transient; no `localStorage`, `sessionStorage`, IndexedDB, or cookies.
- Keep generated build artifacts out of commits unless explicitly preparing release artifacts.
