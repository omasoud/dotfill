# Getting started with dotfill

dotfill is a local-only helper for maintaining configured token and identity variables in a personal `.env` file. The generic package ships with no built-in services, so the first step is to create a TOML config.

## Run dotfill

From a source checkout:

```powershell
uv run dotfill --help
uv run dotfill status
uv run dotfill
```

From an activated virtual environment or installed package:

```powershell
dotfill --help
dotfill status
dotfill
```

`dotfill` starts the local web UI. `dotfill status` prints the resolved config and target `.env` information without opening the dashboard.

## Find the config files

Print the resolved config paths:

```powershell
dotfill config path --root
dotfill config path --common
dotfill config path --user
```

Open the final config directory:

```powershell
dotfill config open
```

`config open` creates the directory if needed, but it does not create TOML files.

## Create a first config

Create `config.toml` at the path printed by `dotfill config path --user`:

```toml
version = 1
name = "Personal tokens"

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
tls_verify = true
icon = "key"

[services.EXAMPLE.auth]
kind = "bearer"
```

Then run:

```powershell
dotfill status
dotfill
```

The dashboard should show the configured identity, derived variable, service, target `.env`, and collapsed dotfill config location.

## Use profiles

Profiles keep separate configs under `profiles/<name>` inside the config root:

```powershell
dotfill --profile demo config path --user
dotfill --profile demo
```

You can also set `DOTFILL_PROFILE` for a shell session.

Use `--config-root <path>` or `DOTFILL_CONFIG_ROOT` to point dotfill at a different config root.

## Choose the target `.env`

The target `.env` path is resolved in this order:

1. CLI `--env-path`.
2. `[target].default_env_path` in TOML.
3. `~/.env`.

The target `.env` contains ordinary environment assignments. dotfill updates only configured managed variables and preserves unrelated comments, blank lines, and variables.

## Save and test tokens

Open the dashboard with:

```powershell
dotfill
```

Use the service card to paste and save a token. Missing enabled derived variables are filled during token saves. Identity variables are read as explicit overrides when present, but dotfill does not write identity variables automatically.

Service tests support configured bearer, header API-key, and basic auth requests to the configured `test_url` after explicit user action.

## Import from another `.env` file

The import workflow can scan:

- a file selected with Browse;
- a dropped file.

Import responses show masked values only. Empty source values are skipped. Import targets are enabled service token variables and enabled derived variables; identity variables are not import targets.

## More reference

- [TOML config schema](config-schema.md)
- [Troubleshooting](troubleshooting.md)
