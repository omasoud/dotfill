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

## Start from an existing `.env`

If you already have a `.env`, you can use it as a map for your first
`config.toml`. Work from a sanitized copy, not the real file:

1. Copy the `.env` to a temporary file.
2. Remove all API tokens, passwords, private keys, and other secret values.
3. Redact private identity values unless you intentionally want to share them.
4. Keep variable names and helpful non-secret comments.

For example:

```dotenv
# GitHub personal access token
GITHUB_TOKEN=<redacted>

# Internal issue tracker token
JIRA_API_TOKEN=

WORK_EMAIL=<redacted>
```

You can then ask an AI coding agent to draft a config. A useful prompt is:

```text
Create a dotfill config.toml for my personal use from this sanitized .env.
Use dotfill directly; do not create a wrapper package.
Use only dotfill's public user docs:
- README.md
- docs/getting-started.md
- docs/config-schema.md

Treat API token variables as services using their existing variable names as
token_var values. Treat stable non-secret user facts as identities. Use derived
variables only when a value should be copied from an identity. Do not invent
secret values. If token_url, test_url, auth kind, or required headers are
unknown, use safe placeholders or TODO comments and point out what I need to
review.

Here is the sanitized .env:
...
```

Review the generated TOML before using it. The agent can usually infer service
names and token variable names, but you should verify:

- `token_var` exactly matches the variable names in your real `.env`;
- `token_url` points to the page where you create or manage that token;
- `test_url` points to an endpoint that accepts the configured auth mode;
- `[services.<ID>.auth]` matches the API, especially for header API-key or
  basic auth services;
- identities and derived variables do not expose values you want masked in the
  dashboard or CLI;
- import aliases map old variable names to the intended managed targets.

Save the reviewed `config.toml` at the path printed by:

```powershell
dotfill config path --user
```

Then validate the config without opening the dashboard:

```powershell
dotfill status
```

When the status output looks right, point dotfill at your real `.env` if needed:

```powershell
dotfill --env-path C:\work\project\.env status
dotfill --env-path C:\work\project\.env
```

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

Use the service card to paste and save a token. Missing enabled derived variables are filled during token saves, and the dashboard can fill or reset individual derived variables to their computed defaults. Identity variables are read as explicit overrides when present, but dotfill does not write identity variables automatically.

Service tests support configured bearer, header API-key, and basic auth requests to the configured `test_url` after explicit user action.

## Import from another `.env` file

The import workflow can scan:

- a file selected with Browse;
- a dropped file.

Import responses show masked values only. Empty source values are skipped. Import targets are enabled service token variables and enabled derived variables; identity variables are not import targets. Import commits also fill missing enabled derived variables when dotfill can compute their defaults.

## More reference

- [TOML config schema](config-schema.md)
- [Troubleshooting](troubleshooting.md)
