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

## The browser opens to a blank page

Open the browser developer tools with `F12` and check the Console. If it says a
module script was served as `text/plain`, the workstation maps `.js` files to
the wrong MIME type. HTTP `200` or `304` entries in the Network tab do not mean
the browser executed the module.

Current dotfill versions explicitly serve packaged JavaScript as
`application/javascript`, independent of host MIME mappings. Upgrade dotfill
and restart it. The corrected entry-module URL uses a new cache key, but a hard
refresh with `Ctrl+Shift+R` is also safe.

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

If the selected path exists and is a directory, dotfill uses that directory's
`.env` file.

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

An identity can be unresolved when dotfill cannot find a configured value, environment variable, dependent identity, or detector fact. Fix it by changing the identity source, setting the referenced environment variable, adding a literal value, or putting an explicit non-empty identity assignment in the target `.env`.

Unresolved identities never stop dotfill from loading. The dashboard and
`dotfill status` show each unresolved identity with a short reason, for
example `windows_ad: directory lookup timed out after 15s` or
`entra: sign-in interaction required`. While detection is still running, the
dashboard shows "detecting…" and refreshes itself.

Common causes on Windows:

- **Off the corporate network.** The Windows AD detector needs a reachable
  directory controller. Reconnect to VPN, or enable the `entra` detector, which
  queries Microsoft Graph instead.
- **Windows Hello PIN sign-in on a cloud-joined device.** If directory lookups
  fail with errors such as "The user name or password is incorrect" or "A
  local error has occurred", and the System event log shows Kerberos event 19
  ("The KDC certificate for the domain controller does not contain the KDC
  Extended Key Usage"), the domain controllers' certificates lack the KDC
  Authentication EKU. Signing in with a password works around it; a domain
  administrator must fix the certificates. The `entra` detector is unaffected.
- **Silent Entra lookup unavailable.** `entra: sign-in interaction required`
  or `entra: client not authorized for Microsoft Graph` means tenant policy
  does not allow the silent lookup for that client. Configure an approved
  `client_id` (see [config-schema.md](config-schema.md#entra-detector)) or use
  an explicit `.env` value.

Failed lookups are retried automatically with backoff, so a VPN reconnect is
picked up without restarting dotfill.

For a `windows_ad.*` identity, being connected to a VPN does not by itself
confirm that Windows can locate and query a directory controller. Check the
current user's directory context in PowerShell:

```powershell
$env:USERDNSDOMAIN
whoami /upn
nltest /dsgetdc:$env:USERDNSDOMAIN
```

dotfill validates `USERDNSDOMAIN` and uses it as an explicit LDAP search root.
If it is unavailable, dotfill tries the domain suffix from `whoami /upn`, then
uses the device's default directory context only as a compatibility fallback.
If the commands above do not return a usable user domain or cannot locate a
controller, reconnect through a network path that provides directory DNS and
LDAP access. An explicit non-empty assignment for the configured identity in
the target `.env` remains the offline override.

## Duplicate managed variables are reported

dotfill rejects duplicate managed variables before writing. Remove or combine duplicate assignments for enabled identity names, derived variable names, and service token variables.

Duplicate unrelated variables are preserved and do not block writes.

## A service test fails

Service tests support bearer, header API-key, and basic auth. Check the
configured auth table matches the API:

```toml
[services.EXAMPLE.auth]
kind = "bearer"
```

Check that:

- the token is current;
- `test_url` points to an endpoint that accepts the configured auth mode;
- any required static headers are configured in `[services.<ID>.test_headers]`;
- basic auth `username_identity` is resolved or `username` is configured;
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
