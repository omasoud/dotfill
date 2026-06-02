"""Tests for generic TOML config loading and validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from dotfill.config_loader import load_effective_config
from dotfill.config_paths import ConfigContext
from dotfill.errors import ConfigLoadError, ConfigSchemaError


def _context(config_dir: Path) -> ConfigContext:
    return ConfigContext(
        config_root=config_dir,
        profile=None,
        config_dir=config_dir,
        common_config_path=config_dir / "config_common.toml",
        user_config_path=config_dir / "config.toml",
    )


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _base_config() -> str:
    return """
version = 1
name = "Example profile"

[target]
default_env_path = "local.env"

[identities.WORK_EMAIL]
source = "literal"
value = "user@example.com"

[identities.WORK_USER]
source = "local_part"
from = "WORK_EMAIL"

[derived.WORK_USERNAME]
from_identity = "WORK_EMAIL"

[services.EXAMPLE]
display_name = "Example"
token_var = "EXAMPLE_TOKEN"
token_url = "https://service.example.com/{WORK_USER}/tokens"
test_url = "https://service.example.com/me"
auth = "bearer"
icon = "key"

[import_aliases.OLD_EXAMPLE_TOKEN]
target = "EXAMPLE_TOKEN"
""".strip()


def test_missing_config_files_produce_empty_config(tmp_path: Path) -> None:
    cfg = load_effective_config(_context(tmp_path))

    assert cfg.name is None
    assert cfg.target.default_env_path is None
    assert cfg.identities == {}
    assert cfg.derived_variables == {}
    assert cfg.services == {}
    assert cfg.import_aliases == {}


def test_loads_only_common_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write(tmp_path / "config_common.toml", _base_config())

    cfg = load_effective_config(_context(tmp_path))

    assert cfg.name == "Example profile"
    assert cfg.target.default_env_path == (tmp_path / "local.env").resolve(strict=False)
    assert set(cfg.identities) == {"WORK_EMAIL", "WORK_USER"}
    assert set(cfg.derived_variables) == {"WORK_USERNAME"}
    assert set(cfg.services) == {"EXAMPLE"}
    assert set(cfg.import_aliases) == {"OLD_EXAMPLE_TOKEN"}
    assert cfg.identities["WORK_EMAIL"].display == "plain"
    assert cfg.identities["WORK_EMAIL"].compare == "exact"
    assert cfg.derived_variables["WORK_USERNAME"].display == "plain"
    assert cfg.derived_variables["WORK_USERNAME"].compare == "exact"


def test_loads_only_user_config(tmp_path: Path) -> None:
    _write(tmp_path / "config.toml", _base_config())

    cfg = load_effective_config(_context(tmp_path))

    assert cfg.services["EXAMPLE"].display_name == "Example"


def test_identity_and_derived_metadata_load(tmp_path: Path) -> None:
    _write(
        tmp_path / "config.toml",
        """
version = 1

[identities.WORK_EMAIL]
source = "literal"
value = "user@example.com"
display = "masked"
compare = "casefold"

[derived.WORK_USERNAME]
from_identity = "WORK_EMAIL"
display = "masked"
compare = "casefold"
""".strip(),
    )

    cfg = load_effective_config(_context(tmp_path))

    identity = cfg.identities["WORK_EMAIL"]
    derived = cfg.derived_variables["WORK_USERNAME"]
    assert identity.display == "masked"
    assert identity.compare == "casefold"
    assert derived.display == "masked"
    assert derived.compare == "casefold"


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (
            """
version = 1

[identities.WORK_EMAIL]
source = "literal"
value = "user@example.com"
display = "hidden"
""",
            "unsupported display",
        ),
        (
            """
version = 1

[identities.WORK_EMAIL]
source = "literal"
value = "user@example.com"
compare = "lower"
""",
            "unsupported compare",
        ),
        (
            """
version = 1

[identities.WORK_EMAIL]
source = "literal"
value = "user@example.com"

[derived.WORK_USERNAME]
from_identity = "WORK_EMAIL"
display = "hidden"
""",
            "unsupported display",
        ),
        (
            """
version = 1

[identities.WORK_EMAIL]
source = "literal"
value = "user@example.com"

[derived.WORK_USERNAME]
from_identity = "WORK_EMAIL"
compare = "lower"
""",
            "unsupported compare",
        ),
    ],
)
def test_invalid_display_and_compare_values_raise(
    body: str,
    message: str,
    tmp_path: Path,
) -> None:
    _write(tmp_path / "config.toml", body.strip())

    with pytest.raises(ConfigSchemaError, match=message):
        load_effective_config(_context(tmp_path))


def test_user_config_scalar_overrides_common(tmp_path: Path) -> None:
    _write(tmp_path / "config_common.toml", "version = 1\nname = \"Common\"\n")
    _write(tmp_path / "config.toml", "version = 1\nname = \"User\"\n")

    cfg = load_effective_config(_context(tmp_path))

    assert cfg.name == "User"


def test_keyed_service_inherits_and_partially_overrides(tmp_path: Path) -> None:
    _write(tmp_path / "config_common.toml", _base_config())
    _write(
        tmp_path / "config.toml",
        """
version = 1

[services.EXAMPLE]
display_name = "User Example"
tls_verify = false
""".strip(),
    )

    cfg = load_effective_config(_context(tmp_path))
    service = cfg.services["EXAMPLE"]
    assert service.display_name == "User Example"
    assert service.token_var == "EXAMPLE_TOKEN"
    assert service.tls_verify is False


def test_enabled_false_disables_inherited_items(tmp_path: Path) -> None:
    _write(tmp_path / "config_common.toml", _base_config())
    _write(
        tmp_path / "config.toml",
        """
version = 1

[services.EXAMPLE]
enabled = false

[derived.WORK_USERNAME]
enabled = false

[identities.WORK_USER]
enabled = false

[import_aliases.OLD_EXAMPLE_TOKEN]
enabled = false
""".strip(),
    )

    cfg = load_effective_config(_context(tmp_path))

    assert cfg.services == {}
    assert cfg.derived_variables == {}
    assert "WORK_USER" not in cfg.identities
    assert "WORK_EMAIL" in cfg.identities
    assert cfg.import_aliases == {}


def test_disabled_identity_cannot_be_referenced(tmp_path: Path) -> None:
    _write(
        tmp_path / "config.toml",
        """
version = 1

[identities.WORK_EMAIL]
enabled = false

[identities.WORK_USER]
source = "local_part"
from = "WORK_EMAIL"
""".strip(),
    )

    with pytest.raises(ConfigSchemaError, match="unknown or disabled"):
        load_effective_config(_context(tmp_path))


def test_disabled_item_does_not_need_required_fields_after_merge(tmp_path: Path) -> None:
    _write(
        tmp_path / "config.toml",
        """
version = 1

[services.INCOMPLETE]
enabled = false
""".strip(),
    )

    cfg = load_effective_config(_context(tmp_path))

    assert cfg.services == {}


def test_enabled_item_missing_required_field_raises(tmp_path: Path) -> None:
    _write(
        tmp_path / "config.toml",
        """
version = 1

[services.INCOMPLETE]
display_name = "Incomplete"
token_var = "INCOMPLETE_TOKEN"
token_url = "https://example.com/token"
""".strip(),
    )

    with pytest.raises(ConfigSchemaError, match="test_url"):
        load_effective_config(_context(tmp_path))


def test_invalid_toml_reports_file(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    _write(path, "version = 1\n[services\n")

    with pytest.raises(ConfigLoadError, match="config.toml"):
        load_effective_config(_context(tmp_path))


def test_invalid_variable_name_raises(tmp_path: Path) -> None:
    _write(
        tmp_path / "config.toml",
        """
version = 1

[identities.1BAD]
source = "literal"
value = "x"
""".strip(),
    )

    with pytest.raises(ConfigSchemaError, match="valid variable name"):
        load_effective_config(_context(tmp_path))


def test_invalid_service_id_raises(tmp_path: Path) -> None:
    _write(
        tmp_path / "config.toml",
        """
version = 1

[services."-bad"]
display_name = "Bad"
token_var = "BAD_TOKEN"
token_url = "https://example.com/token"
test_url = "https://example.com/me"
""".strip(),
    )

    with pytest.raises(ConfigSchemaError, match="invalid service id"):
        load_effective_config(_context(tmp_path))


def test_unsupported_auth_raises(tmp_path: Path) -> None:
    _write(
        tmp_path / "config.toml",
        _base_config().replace('auth = "bearer"', 'auth = "basic"'),
    )

    with pytest.raises(ConfigSchemaError, match="unsupported auth"):
        load_effective_config(_context(tmp_path))


@pytest.mark.parametrize(
    "body",
    [
        "version = 1\nunknown = true\n",
        "version = 1\n[target]\ndefault_env_path = \"x\"\ndefault_env_pth = \"y\"\n",
        "version = 1\n[identity]\nunknown = true\n",
        "version = 1\n[identity.detectors]\nunknown = true\n",
        "version = 1\n[identity.detectors.windows_ad]\nenabled = true\nmode = \"strict\"\n",
        """
version = 1

[identities.WORK_EMAIL]
source = "literal"
value = "user@example.com"
domain = "example.com"
""",
        """
version = 1

[derived.WORK_USERNAME]
from_identity = "WORK_EMAIL"
from_ident = "WORK_EMAIL"
""",
        """
version = 1

[services.EXAMPLE]
display_name = "Example"
token_var = "EXAMPLE_TOKEN"
token_url = "https://example.com/token"
test_url = "https://example.com/me"
tls_verfiy = false
""",
        """
version = 1

[import_aliases.OLD_EXAMPLE_TOKEN]
target = "EXAMPLE_TOKEN"
targte = "EXAMPLE_TOKEN"
""",
    ],
)
def test_unknown_config_fields_raise(body: str, tmp_path: Path) -> None:
    _write(tmp_path / "config.toml", body.strip())

    with pytest.raises(ConfigSchemaError, match="unknown field"):
        load_effective_config(_context(tmp_path))


def test_unknown_url_placeholder_raises(tmp_path: Path) -> None:
    _write(
        tmp_path / "config.toml",
        _base_config().replace("{WORK_USER}", "{UNKNOWN_IDENTITY}"),
    )

    with pytest.raises(ConfigSchemaError, match="UNKNOWN_IDENTITY"):
        load_effective_config(_context(tmp_path))


def test_import_alias_target_must_be_enabled_import_target(tmp_path: Path) -> None:
    _write(
        tmp_path / "config.toml",
        _base_config().replace('target = "EXAMPLE_TOKEN"', 'target = "MISSING_TOKEN"'),
    )

    with pytest.raises(ConfigSchemaError, match="enabled import target"):
        load_effective_config(_context(tmp_path))


def test_target_path_expands_environment_and_relative_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DOTFILL_TEST_ENV_DIR", str(tmp_path / "env-dir"))
    _write(
        tmp_path / "config.toml",
        """
version = 1

[target]
default_env_path = "$DOTFILL_TEST_ENV_DIR/../target.env"
""".strip(),
    )

    cfg = load_effective_config(_context(tmp_path))

    assert cfg.target.default_env_path == (tmp_path / "target.env").resolve(strict=False)


def test_tls_verify_defaults_true_and_accepts_false(tmp_path: Path) -> None:
    _write(tmp_path / "config_common.toml", _base_config())
    _write(
        tmp_path / "config.toml",
        """
version = 1

[services.EXPLICIT_FALSE]
display_name = "Explicit False"
token_var = "EXPLICIT_FALSE_TOKEN"
token_url = "https://example.com/token"
test_url = "https://example.com/me"
tls_verify = false
""".strip(),
    )

    cfg = load_effective_config(_context(tmp_path))

    assert cfg.services["EXAMPLE"].tls_verify is True
    assert cfg.services["EXPLICIT_FALSE"].tls_verify is False


def test_disabling_one_inherited_alias_keeps_others(tmp_path: Path) -> None:
    _write(
        tmp_path / "config_common.toml",
        _base_config()
        + """

[import_aliases.LEGACY_EXAMPLE_TOKEN]
target = "EXAMPLE_TOKEN"
""",
    )
    _write(
        tmp_path / "config.toml",
        """
version = 1

[import_aliases.OLD_EXAMPLE_TOKEN]
enabled = false
""".strip(),
    )

    cfg = load_effective_config(_context(tmp_path))

    assert "OLD_EXAMPLE_TOKEN" not in cfg.import_aliases
    assert "LEGACY_EXAMPLE_TOKEN" in cfg.import_aliases


def test_present_toml_file_must_include_version(tmp_path: Path) -> None:
    _write(
        tmp_path / "config.toml",
        """
[services.EXAMPLE]
enabled = false
""".strip(),
    )

    with pytest.raises(ConfigSchemaError, match="version"):
        load_effective_config(_context(tmp_path))


def test_disabled_windows_ad_detector_with_dependent_identity_fails(tmp_path: Path) -> None:
    _write(
        tmp_path / "config.toml",
        """
version = 1

[identity.detectors.windows_ad]
enabled = false

[identities.WORK_EMAIL]
source = "windows_ad.email_by_domain"
domain = "example.com"
""".strip(),
    )

    with pytest.raises(ConfigSchemaError, match="windows_ad detector is disabled"):
        load_effective_config(_context(tmp_path))
