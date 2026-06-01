# dotfill TOML config schema

Status: Active schema reference

dotfill loads `config_common.toml` first and `config.toml` second from the resolved config directory. Both files are optional, but every present file must include:

```toml
version = 1
```

The schema is strict: unknown top-level sections and unknown fields inside known tables are rejected instead of ignored.

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

## Derived Variables

Derived keys must be valid environment variable names.

```toml
version = 1

[identities.WORK_EMAIL]
source = "literal"
value = "alice@example.com"

[derived.WORK_USERNAME]
from_identity = "WORK_EMAIL"
```

| Field | Required | Description |
|---|---:|---|
| `from_identity` | yes | Enabled identity to copy when filling the derived variable. |
| `enabled` | no | Defaults to `true`; `false` removes the derived variable. |

Enabled derived variables may be filled when saving a token. Disabled derived variables are not written.

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
auth = "bearer"
tls_verify = true
icon = "key"
```

| Field | Required | Description |
|---|---:|---|
| `display_name` | yes | Label shown in the UI. |
| `token_var` | yes | Target `.env` variable for the token. |
| `token_url` | yes | URL template for opening the service token page. |
| `test_url` | yes | URL template for bearer-token testing. |
| `auth` | no | Defaults to `bearer`; only `bearer` is supported. |
| `tls_verify` | no | Defaults to `true`. |
| `icon` | no | Frontend icon key; fallback is `key`. |
| `enabled` | no | Defaults to `true`; `false` removes the service. |

URL templates may reference enabled identities with `{IDENTITY_NAME}` placeholders.

`tls_verify = false` should be used only when the configured service explicitly requires it.

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
