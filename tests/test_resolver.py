"""Tests for resolver.build_app_state and helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from dotfill.config_paths import resolve_config_context
from dotfill.errors import DuplicateManagedVariableError, UnresolvedIdentityError
from dotfill.identity_facts import make_ad_facts
from dotfill.models import SessionState, TestResult as DotfillTestResult
from dotfill.resolver import _mask_token, build_app_state, service_test_fingerprint


def _session() -> SessionState:
    return SessionState(token="test-session-token")


def _write_config(root: Path, *, env_path: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "config.toml").write_text(
        f"""
version = 1
name = "Test profile"

[target]
default_env_path = "{env_path.as_posix()}"

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
token_url = "https://service.example.com/{{WORK_USER}}/tokens"
test_url = "https://service.example.com/me"
icon = "key"
""".strip(),
        encoding="utf-8",
    )


def _context(root: Path):
    return resolve_config_context(config_root=root, environ={})


def test_mask_token_short() -> None:
    assert _mask_token("abcd") == "••••"
    assert _mask_token("abc") == "••••"


def test_mask_token_long() -> None:
    assert _mask_token("abcdefghij") == "••••••••ghij"


def test_build_app_state_with_no_config_is_empty_generic(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("", encoding="utf-8")

    state = build_app_state(_context(tmp_path / "config"), _session(), env_path_override=env)

    assert state.identities == []
    assert state.derived == []
    assert state.services == []
    assert state.effective_config.services == {}


def test_old_meta_variables_do_not_create_config_or_duplicates(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "LEGACY_ENV_CONFIG_SERVICE=A|u|t|n\nLEGACY_ENV_CONFIG_SERVICE=B|u|t|n\n",
        encoding="utf-8",
    )

    state = build_app_state(_context(tmp_path / "config"), _session(), env_path_override=env)

    assert state.services == []
    assert state.identities == []


def test_build_app_state_with_configured_identity(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("", encoding="utf-8")
    config_root = tmp_path / "config"
    _write_config(config_root, env_path=env)

    state = build_app_state(_context(config_root), _session())

    by_name = {i.name: i for i in state.identities}
    assert by_name["WORK_EMAIL"].effective_value == "alice@example.com"
    assert by_name["WORK_EMAIL"].source == "detected"
    assert by_name["WORK_USER"].effective_value == "alice"


def test_unresolved_unused_identity_does_not_block_state(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("", encoding="utf-8")
    config_root = tmp_path / "config"
    config_root.mkdir()
    (config_root / "config.toml").write_text(
        f"""
version = 1

[target]
default_env_path = "{env.as_posix()}"

[identities.OPTIONAL_USER]
source = "env"
name = "DOTFILL_MISSING_OPTIONAL_USER"
""".strip(),
        encoding="utf-8",
    )

    state = build_app_state(_context(config_root), _session())

    identity = state.identities[0]
    assert identity.name == "OPTIONAL_USER"
    assert identity.source == "unresolved"


def test_explicit_identity_overrides_detected(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("WORK_EMAIL=override@example.com\n", encoding="utf-8")
    config_root = tmp_path / "config"
    _write_config(config_root, env_path=env)

    state = build_app_state(_context(config_root), _session())

    by_name = {i.name: i for i in state.identities}
    assert by_name["WORK_EMAIL"].effective_value == "override@example.com"
    assert by_name["WORK_EMAIL"].source == "diverged"


def test_casefold_identity_alignment_preserves_explicit_value(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("WORK_EMAIL=Alice@Example.com\n", encoding="utf-8")
    config_root = tmp_path / "config"
    config_root.mkdir()
    (config_root / "config.toml").write_text(
        f"""
version = 1

[target]
default_env_path = "{env.as_posix()}"

[identities.WORK_EMAIL]
source = "literal"
value = "alice@example.com"
compare = "casefold"
""".strip(),
        encoding="utf-8",
    )

    state = build_app_state(_context(config_root), _session())

    identity = state.identities[0]
    assert identity.source == "aligned"
    assert identity.effective_value == "Alice@Example.com"


def test_local_part_uses_effective_upstream_identity_from_env(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("WORK_EMAIL=manual@example.com\n", encoding="utf-8")
    config_root = tmp_path / "config"
    config_root.mkdir()
    (config_root / "config.toml").write_text(
        f"""
version = 1

[target]
default_env_path = "{env.as_posix()}"

[identities.WORK_EMAIL]
source = "windows_ad.email_by_domain"
domain = "example.com"

[identities.WORK_USER]
source = "local_part"
from = "WORK_EMAIL"

[services.EXAMPLE]
display_name = "Example"
token_var = "EXAMPLE_TOKEN"
token_url = "https://service.example.com/{{WORK_USER}}/tokens"
test_url = "https://service.example.com/me"
""".strip(),
        encoding="utf-8",
    )

    state = build_app_state(
        _context(config_root),
        _session(),
        ad_facts_override=make_ad_facts(diagnostics=["AD unavailable"]),
    )

    by_name = {i.name: i for i in state.identities}
    assert by_name["WORK_EMAIL"].effective_value == "manual@example.com"
    assert by_name["WORK_USER"].effective_value == "manual"
    service = next(s for s in state.services if s.service_id == "EXAMPLE")
    assert service.resolved_token_url == "https://service.example.com/manual/tokens"


def test_duplicate_configured_identity_blocks_state(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("WORK_EMAIL=a@example.com\nWORK_EMAIL=b@example.com\n", encoding="utf-8")
    config_root = tmp_path / "config"
    _write_config(config_root, env_path=env)

    with pytest.raises(DuplicateManagedVariableError):
        build_app_state(_context(config_root), _session())


def test_unresolved_identity_required_by_derived_blocks_state(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("", encoding="utf-8")
    config_root = tmp_path / "config"
    config_root.mkdir()
    (config_root / "config.toml").write_text(
        f"""
version = 1

[target]
default_env_path = "{env.as_posix()}"

[identities.WORK_EMAIL]
source = "env"
name = "DOTFILL_MISSING_TEST_ENV"

[derived.WORK_USERNAME]
from_identity = "WORK_EMAIL"
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(UnresolvedIdentityError):
        build_app_state(_context(config_root), _session())


def test_derived_status_missing_aligned_diverged(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("WORK_USERNAME=diff@example.com\n", encoding="utf-8")
    config_root = tmp_path / "config"
    _write_config(config_root, env_path=env)

    state = build_app_state(_context(config_root), _session())

    by_name = {d.variable_name: d for d in state.derived}
    derived = by_name["WORK_USERNAME"]
    assert derived.status == "diverged"
    assert derived.computed_default == "alice@example.com"


def test_casefold_derived_alignment_preserves_current_value(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("WORK_USERNAME=Alice@Example.com\n", encoding="utf-8")
    config_root = tmp_path / "config"
    config_root.mkdir()
    (config_root / "config.toml").write_text(
        f"""
version = 1

[target]
default_env_path = "{env.as_posix()}"

[identities.WORK_EMAIL]
source = "literal"
value = "alice@example.com"

[derived.WORK_USERNAME]
from_identity = "WORK_EMAIL"
compare = "casefold"
""".strip(),
        encoding="utf-8",
    )

    state = build_app_state(_context(config_root), _session())

    derived = state.derived[0]
    assert derived.status == "aligned"
    assert derived.current_value == "Alice@Example.com"
    assert derived.computed_default == "alice@example.com"


def test_service_token_masking_in_state(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("EXAMPLE_TOKEN=supersecrettoken\n", encoding="utf-8")
    config_root = tmp_path / "config"
    _write_config(config_root, env_path=env)

    state = build_app_state(_context(config_root), _session())

    service = next(s for s in state.services if s.service_id == "EXAMPLE")
    assert service.token_present is True
    assert service.masked_token == "••••••••oken"
    assert service.test_status == "set"
    assert service.icon == "key"
    assert service.resolved_token_url == "https://service.example.com/alice/tokens"


def test_cli_env_path_override_wins_over_target_config(tmp_path: Path) -> None:
    configured_env = tmp_path / "configured.env"
    override_env = tmp_path / "override.env"
    configured_env.write_text("EXAMPLE_TOKEN=configured\n", encoding="utf-8")
    override_env.write_text("EXAMPLE_TOKEN=override\n", encoding="utf-8")
    config_root = tmp_path / "config"
    _write_config(config_root, env_path=configured_env)

    state = build_app_state(
        _context(config_root),
        _session(),
        env_path_override=override_env,
    )

    assert state.env_path == override_env.resolve(strict=False)
    service = next(s for s in state.services if s.service_id == "EXAMPLE")
    assert service.masked_token == "••••••••ride"


def test_disabled_service_not_duplicate_managed(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("EXAMPLE_TOKEN=a\nEXAMPLE_TOKEN=b\n", encoding="utf-8")
    config_root = tmp_path / "config"
    config_root.mkdir()
    (config_root / "config.toml").write_text(
        f"""
version = 1

[target]
default_env_path = "{env.as_posix()}"

[services.EXAMPLE]
enabled = false
""".strip(),
        encoding="utf-8",
    )

    state = build_app_state(_context(config_root), _session())

    assert state.services == []


def test_duplicate_managed_var_blocks_state(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("EXAMPLE_TOKEN=a\nEXAMPLE_TOKEN=b\n", encoding="utf-8")
    config_root = tmp_path / "config"
    _write_config(config_root, env_path=env)

    with pytest.raises(DuplicateManagedVariableError):
        build_app_state(_context(config_root), _session())


def test_stale_test_result_cleared_when_token_removed(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("", encoding="utf-8")
    config_root = tmp_path / "config"
    _write_config(config_root, env_path=env)
    session = _session()
    session.test_results["EXAMPLE"] = DotfillTestResult(status="working", http_status=200)

    state = build_app_state(_context(config_root), session)

    service = next(s for s in state.services if s.service_id == "EXAMPLE")
    assert service.token_present is False
    assert service.test_status == "missing"


def test_cached_test_result_requires_matching_fingerprint(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("EXAMPLE_TOKEN=supersecrettoken\n", encoding="utf-8")
    config_root = tmp_path / "config"
    _write_config(config_root, env_path=env)
    session = _session()
    session.test_results["EXAMPLE"] = DotfillTestResult(
        status="working",
        http_status=200,
        fingerprint=service_test_fingerprint(
            service_id="EXAMPLE",
            token_var="EXAMPLE_TOKEN",
            resolved_test_url="https://service.example.com/me",
            auth="bearer",
            tls_verify=True,
            token="supersecrettoken",
            session_token=session.token,
        ),
    )

    state = build_app_state(_context(config_root), session)
    service = next(s for s in state.services if s.service_id == "EXAMPLE")
    assert service.test_status == "working"

    env.write_text("EXAMPLE_TOKEN=changedtoken\n", encoding="utf-8")
    state = build_app_state(_context(config_root), session)
    service = next(s for s in state.services if s.service_id == "EXAMPLE")
    assert service.test_status == "set"


def test_cached_test_result_ignored_when_test_url_changes(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("EXAMPLE_TOKEN=supersecrettoken\n", encoding="utf-8")
    config_root = tmp_path / "config"
    _write_config(config_root, env_path=env)
    session = _session()
    session.test_results["EXAMPLE"] = DotfillTestResult(
        status="working",
        http_status=200,
        fingerprint=service_test_fingerprint(
            service_id="EXAMPLE",
            token_var="EXAMPLE_TOKEN",
            resolved_test_url="https://service.example.com/me",
            auth="bearer",
            tls_verify=True,
            token="supersecrettoken",
            session_token=session.token,
        ),
    )
    (config_root / "config.toml").write_text(
        f"""
version = 1

[target]
default_env_path = "{env.as_posix()}"

[services.EXAMPLE]
display_name = "Example"
token_var = "EXAMPLE_TOKEN"
token_url = "https://service.example.com/tokens"
test_url = "https://service.example.com/new-me"
""".strip(),
        encoding="utf-8",
    )

    state = build_app_state(_context(config_root), session)

    service = next(s for s in state.services if s.service_id == "EXAMPLE")
    assert service.resolved_test_url == "https://service.example.com/new-me"
    assert service.test_status == "set"


def test_disabled_service_ignores_cached_test_result(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("EXAMPLE_TOKEN=supersecrettoken\n", encoding="utf-8")
    config_root = tmp_path / "config"
    config_root.mkdir()
    (config_root / "config.toml").write_text(
        f"""
version = 1

[target]
default_env_path = "{env.as_posix()}"

[services.EXAMPLE]
enabled = false
""".strip(),
        encoding="utf-8",
    )
    session = _session()
    session.test_results["EXAMPLE"] = DotfillTestResult(
        status="working",
        http_status=200,
        fingerprint="old",
    )

    state = build_app_state(_context(config_root), session)

    assert state.services == []


def test_ad_probe_not_run_without_ad_dependent_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = tmp_path / ".env"
    env.write_text("", encoding="utf-8")
    config_root = tmp_path / "config"
    _write_config(config_root, env_path=env)

    def fail_probe():
        raise AssertionError("AD probe should not run")

    monkeypatch.setattr("dotfill.resolver.detect_ad_facts", fail_probe)

    state = build_app_state(_context(config_root), _session())

    assert {identity.name for identity in state.identities} == {
        "WORK_EMAIL",
        "WORK_USER",
    }
