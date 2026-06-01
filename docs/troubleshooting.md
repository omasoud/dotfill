# Troubleshooting dotfill

## `dotfill` is not found

From a source checkout, run commands through uv:

```powershell
uv run dotfill --help
uv run dotfill status
```

If a virtual environment is activated or dotfill is installed, `dotfill --help` should work directly.

## No services are configured

This is expected for the generic package until you create TOML config. Add services to `config.toml`, or run dotfill through a wrapper package that provides managed `config_common.toml` content.

Find the user config file path with:

```powershell
dotfill config path --user
```

## dotfill is using the wrong config directory

Check the resolved paths:

```powershell
dotfill config path --root
dotfill config path --common
dotfill config path --user
```

Config root precedence is:

1. CLI `--config-root`.
2. `DOTFILL_CONFIG_ROOT`.
3. the platform default user config directory.

Profile precedence is:

1. CLI `--profile`.
2. `DOTFILL_PROFILE`.
3. no profile.

When a profile is active, config files live under `profiles/<name>` inside the config root.

## dotfill is using the wrong `.env`

The target `.env` path is resolved in this order:

1. CLI `--env-path`.
2. `[target].default_env_path` in TOML.
3. `~/.env`.

Run `dotfill status` to see the resolved target path.

## TOML validation fails

Every present config file must include:

```toml
version = 1
```

The schema is strict. Unknown top-level sections and unknown fields inside known tables are rejected. See [config-schema.md](config-schema.md) for the accepted fields and examples.

## A configured item will not disable

Use `enabled = false` inside the keyed item you want to remove from the effective config:

```toml
version = 1

[services.EXAMPLE]
enabled = false
```

This works for inherited services, identities, derived variables, and import aliases.

## An identity is unresolved

An identity can be unresolved when dotfill cannot find a configured value, environment variable, dependent identity, or Windows AD fact. Fix it by changing the identity source, setting the referenced environment variable, adding a literal value, or putting an explicit non-empty identity assignment in the target `.env`.

Unresolved identities block state construction only when enabled derived variables, service URL templates, or dependent identity rules need them.

## Duplicate managed variables are reported

dotfill rejects duplicate managed variables before writing. Remove or combine duplicate assignments for enabled identity names, derived variable names, and service token variables.

Duplicate unrelated variables are preserved and do not block writes.

## A service test fails

Service tests currently support bearer authentication only. The configured API must accept:

```http
Authorization: Bearer <token>
Accept: application/json
```

Check that:

- the token is current;
- `test_url` points to an endpoint that accepts bearer tokens;
- all URL template identities resolve;
- TLS verification is appropriate for the service.

`tls_verify = false` should be used only when the configured service explicitly requires it.

## Import does not find a value

Import scans skip empty source values. They also do not import identity variables. Valid import targets are enabled service token variables and enabled derived variables.

If a source variable name differs from the target name, add an import alias:

```toml
version = 1

[import_aliases.OLD_EXAMPLE_TOKEN]
target = "EXAMPLE_TOKEN"
```

## Browse or drop only shows a filename

Browsers expose the selected or dropped file name to the page, not the full source path. dotfill shows `Selected file: <filename>` or `Dropped file: <filename>` and rescans the cached browser-provided file content when you click Scan again.
