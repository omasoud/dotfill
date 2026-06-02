# dotfill

dotfill is a local-only helper for maintaining token and identity variables in a personal `.env` file. It runs a Python CLI plus a localhost web UI, reads TOML configuration, and writes only after explicit user action.

Generic `dotfill` ships with no services, identities, domains, token names, or import aliases. A user config or a wrapper package supplies those definitions.

## Installation

For CLI use, install dotfill as an isolated tool:

```powershell
uv tool install dotfill
```

or:

```powershell
pipx install dotfill
```

For use as a library or project dependency:

```powershell
uv add dotfill
```

or:

```powershell
pip install dotfill
```

dotfill requires Python 3.14 or newer.

## Quick Start

```powershell
dotfill status
dotfill
dotfill config path
dotfill config open
```

Useful options:

```powershell
dotfill --config-root C:\tmp\dotfill-config --profile demo status
dotfill --env-path C:\work\project\.env
```

## Documentation

- [Getting started](docs/getting-started.md) walks through the first config and dashboard run.
- [TOML config schema](docs/config-schema.md) is the full user-facing config reference.
- [Troubleshooting](docs/troubleshooting.md) covers common setup, config, import, and service-test issues.

Maintainer requirements, design notes, and implementation tracking live under `dev/docs/`.

## Configuration

dotfill loads two optional TOML files from the resolved config directory:

```text
config_common.toml
config.toml
```

`config_common.toml` is intended for managed baseline configuration. `config.toml` is intended for user-owned overrides. Both files must include `version = 1` when present.

See [docs/config-schema.md](docs/config-schema.md) for the complete schema.

Default config root:

```text
platformdirs.user_config_dir("dotfill", appauthor=False, roaming=True)
```

Profiles live under `profiles/<name>` inside the config root.

Example:

```toml
version = 1
name = "Example profile"

[target]
default_env_path = "~/.env"

[identities.WORK_EMAIL]
source = "literal"
value = "alice@example.com"

[identities.WORK_USER]
source = "local_part"
from = "WORK_EMAIL"

[derived.WORK_USERNAME]
from_identity = "WORK_EMAIL"

[services.EXAMPLE]
display_name = "Example"
token_var = "EXAMPLE_TOKEN"
token_url = "https://service.example.com/users/{WORK_USER}/tokens"
test_url = "https://service.example.com/me"
auth = "bearer"
tls_verify = true
icon = "key"

[import_aliases.OLD_EXAMPLE_TOKEN]
target = "EXAMPLE_TOKEN"
```

Set `enabled = false` in `config.toml` to disable an inherited service, identity, derived variable, or import alias.

## `.env` Behavior

The target `.env` contains ordinary environment values only. dotfill no longer reads legacy service or derived-variable meta-configuration from `.env`; those assignments are unrelated content unless their exact names are explicitly configured as managed variables in TOML.

The parser/writer preserves comments, blank lines, unrelated variables, unrelated duplicates, and line endings. Duplicate managed variables are rejected before writes.

## Local UI

`dotfill` starts a server bound to `127.0.0.1`, opens the dashboard, and serves static assets from the installed package. The dashboard can:

- show configured identities, derived variables, services, config directory, and target `.env`;
- save service tokens;
- fill missing enabled derived variables during saves;
- import token/derived values from another `.env`-like file;
- test configured bearer tokens on explicit user action.

When no services are configured, the dashboard shows an empty generic state.

## Privacy

- No cloud backend, accounts, telemetry, or remote sync.
- Raw token values are not returned by state/import APIs.
- Dropped import values are kept only in backend session memory as secret values.
- The browser keeps session and token input in memory only; no browser storage is used.
- Service tests send `Authorization: Bearer <token>` only to configured test URLs.
- Service tests verify TLS by default. Use `tls_verify = false` only when a configured service explicitly requires it.

## Wrapper Packages

Wrapper packages can provide managed `config_common.toml` content and launch dotfill through:

```python
from dotfill.entrypoints import run_dotfill

raise SystemExit(
    run_dotfill(
        locked_profile="team",
        before_config_load=sync_managed_config,
    )
)
```

Use `locked_profile` when the wrapper command should always mean one profile.
Use `default_profile` only when CLI `--profile` or `DOTFILL_PROFILE` should be
allowed to select another profile. Wrappers should not import the Typer app
directly. User overrides remain in `config.toml`.

## Development

From a source checkout:

```powershell
uv sync
uv run pytest
uv run dotfill status
uv build
```

If the virtual environment is activated, `dotfill --help` works directly. Without activation, use `uv run dotfill ...` or `.\.venv\Scripts\dotfill.exe ...`.
