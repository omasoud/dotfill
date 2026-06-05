# dotfill TOML config schema

Status: Active schema reference

dotfill loads `config_common.toml` first and `config.toml` second from the resolved config directory. Both files are optional, but every present file must include:

```toml
version = 1
```

The schema is strict: unknown top-level sections and unknown fields inside known tables are rejected instead of ignored.

## Display and Comparison Metadata

Identity and derived-variable tables support optional metadata:

| Field | Values | Default | Description |
|---|---|---|---|
| `display` | `plain`, `masked` | `plain` | Controls whether CLI/API/UI output shows the full value or a masked value. |
| `compare` | `exact`, `casefold` | `exact` | Controls equality checks for identity and derived status. |

`display = "masked"` does not change stored values. It only masks values before they leave the backend in CLI/API/UI output.

`compare = "casefold"` uses Python `str.casefold()` for equality. It can make casing-only differences count as aligned/no-change, but dotfill does not rewrite values just to normalize casing.

Service token values are always masked and always compared exactly; service tables do not support `display` or `compare`.

## Layering

Later layers override earlier layers.

Scalars replace earlier values:

```toml
version = 1

[target]
default_env_path = "C:/work/project/.env"
```

Keyed tables merge by key:

```toml
version = 1

[services.EXAMPLE]
display_name = "Example"
token_var = "EXAMPLE_TOKEN"
token_url = "https://service.example.com/tokens"
test_url = "https://service.example.com/me"
```

Service auth tables replace as a unit when a later layer supplies
`[services.<ID>.auth]`. Static service test headers merge by case-insensitive
header name, with later layers overriding earlier header values.

An override can disable an inherited item:

```toml
version = 1

[services.EXAMPLE]
enabled = false
```

Disabled items are removed from the effective config before required-field validation.

## Top Level

```toml
version = 1
name = "Example profile"
```

| Field | Required | Description |
|---|---:|---|
| `version` | yes | Must be `1`. |
| `name` | no | Human-readable config name shown by CLI/UI. |

## Target

```toml
version = 1

[target]
default_env_path = "~/.env"
```

| Field | Required | Description |
|---|---:|---|
| `default_env_path` | no | Default target `.env` when CLI `--env-path` is absent. |

Path handling:

- expands `~`;
- expands platform environment variables;
- resolves relative paths against the current working directory.

## Identity Detectors

```toml
version = 1

[identity.detectors.windows_ad]
enabled = true
```

Windows AD detection is enabled by default. If disabled, enabled identities cannot use Windows AD sources.

The detector runs only when at least one enabled identity needs it.

## Identities

Identity keys must be valid environment variable names.

### Literal

```toml
version = 1

[identities.WORK_EMAIL]
source = "literal"
value = "alice@example.com"
display = "plain"
compare = "exact"
```

### Environment Variable

```toml
version = 1

[identities.WORK_EMAIL]
source = "env"
name = "WORK_EMAIL_FROM_ENV"
```

### Local Part

```toml
version = 1

[identities.WORK_EMAIL]
source = "literal"
value = "alice@example.com"

[identities.WORK_USER]
source = "local_part"
from = "WORK_EMAIL"
```

### Windows AD Email By Domain

```toml
version = 1

[identities.WORK_EMAIL]
source = "windows_ad.email_by_domain"
domain = "example.com"
```

### Windows AD Account Facts

```toml
version = 1

[identities.WORK_ACCOUNT]
source = "windows_ad.sam"

[identities.WORK_DOMAIN]
source = "windows_ad.domain"
```

Supported sources:

| Source | Required Fields |
|---|---|
| `literal` | `value` |
| `env` | `name` |
| `local_part` | `from` |
| `windows_ad.email_by_domain` | `domain` |
| `windows_ad.sam` | none |
| `windows_ad.domain` | none |

All identity tables support `enabled = false`.

Identity `compare` controls whether explicit `.env` identity values align with detected values. With `compare = "casefold"`, `Alice@Example.com` and `alice@example.com` are aligned, and the explicit `.env` value remains the effective value.

## Derived Variables

Derived keys must be valid environment variable names.

```toml
version = 1

[identities.WORK_EMAIL]
source = "literal"
value = "alice@example.com"

[derived.WORK_USERNAME]
from_identity = "WORK_EMAIL"
display = "plain"
compare = "exact"
```

| Field | Required | Description |
|---|---:|---|
| `from_identity` | yes | Enabled identity to copy when filling the derived variable. |
| `enabled` | no | Defaults to `true`; `false` removes the derived variable. |
| `display` | no | Defaults to `plain`; use `masked` to mask CLI/API/UI output. |
| `compare` | no | Defaults to `exact`; use `casefold` for case-insensitive equality. |

Enabled derived variables may be filled when saving a token. Disabled derived variables are not written.

Derived `compare` controls aligned/diverged status and import no-change checks for derived targets. It does not affect service token comparisons.

## Services

```toml
version = 1

[identities.WORK_USER]
source = "literal"
value = "alice"

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

| Field | Required | Description |
|---|---:|---|
| `display_name` | yes | Label shown in the UI. |
| `token_var` | yes | Target `.env` variable for the token. |
| `token_url` | yes | URL template for opening the service token page. |
| `test_url` | yes | URL template for explicit service testing. |
| `[services.<ID>.auth]` | no | Auth table for service testing. Omitted auth defaults to bearer. |
| `[services.<ID>.test_headers]` | no | Static non-secret headers to include in service tests. |
| `tls_verify` | no | Defaults to `true`. |
| `icon` | no | Frontend icon key; fallback is `key`. |
| `enabled` | no | Defaults to `true`; `false` removes the service. |

URL templates may reference enabled identities with `{IDENTITY_NAME}` placeholders.

`tls_verify = false` should be used only when the configured service explicitly requires it.

If `auth` is present, it must be a table. Scalar `auth = "bearer"` is invalid.

### Bearer Auth

```toml
[services.GITHUB.auth]
kind = "bearer"
```

Generated auth header:

```http
Authorization: Bearer <token>
```

### Header API-Key Auth

```toml
[services.ANTHROPIC.auth]
kind = "header"
header = "x-api-key"

[services.ANTHROPIC.test_headers]
anthropic-version = "2023-06-01"
```

Generated auth header:

```http
x-api-key: <token>
```

### Basic Auth

Use an identity-derived username:

```toml
[services.JIRA.auth]
kind = "basic"
username_identity = "WORK_EMAIL"
```

or a fixed username:

```toml
[services.INTERNAL.auth]
kind = "basic"
username = "fixed-user"
```

Generated auth header:

```http
Authorization: Basic base64(username:token)
```

Basic literal usernames may not contain `:`. `username_identity` must reference
an enabled identity. If that identity is unresolved at test time, only that
service test fails.

### Service Auth Validation

dotfill rejects:

- unknown auth kinds;
- `kind = "query"`;
- unknown fields for the selected auth kind;
- missing required auth fields;
- invalid HTTP header names;
- case-insensitive duplicate `test_headers`;
- auth-generated header conflicts with `test_headers`;
- basic auth with both or neither username source;
- basic literal usernames containing `:`;
- `username_identity` references to unknown or disabled identities.

## Import Aliases

```toml
version = 1

[services.EXAMPLE]
display_name = "Example"
token_var = "EXAMPLE_TOKEN"
token_url = "https://service.example.com/tokens"
test_url = "https://service.example.com/me"

[import_aliases.OLD_EXAMPLE_TOKEN]
target = "EXAMPLE_TOKEN"
```

| Field | Required | Description |
|---|---:|---|
| `target` | yes | Enabled service token variable or enabled derived variable. |
| `enabled` | no | Defaults to `true`; `false` removes the alias. |

Exact target-name matches take priority over aliases.

## Override-Only Examples

Disable an inherited service:

```toml
version = 1

[services.EXAMPLE]
enabled = false
```

Override only the target `.env` path:

```toml
version = 1

[target]
default_env_path = "C:/work/project/.env"
```

Disable an inherited import alias:

```toml
version = 1

[import_aliases.OLD_EXAMPLE_TOKEN]
enabled = false
```

## `.env` Meta Configuration

The target `.env` file is not a configuration source. Legacy service or derived-variable meta-configuration assignments in `.env` are unrelated content unless their exact variable names are explicitly configured as managed names in TOML.
