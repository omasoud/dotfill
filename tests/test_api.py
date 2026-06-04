"""End-to-end API tests using FastAPI TestClient."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from dotfill.api import SESSION_HEADER, AppContext, create_app
from dotfill.config_paths import resolve_config_context
from dotfill.models import SessionState, TestResult as DotfillTestResult


@pytest.fixture()
def env_path(tmp_path: Path) -> Path:
    p = tmp_path / ".env"
    p.write_text("", encoding="utf-8")
    return p


@pytest.fixture()
def config_root(tmp_path: Path, env_path: Path) -> Path:
    root = tmp_path / "config"
    root.mkdir()
    (root / "config.toml").write_text(
        f"""
version = 1
name = "API test"

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

[services.SERVICE_A]
display_name = "Service A"
token_var = "SERVICE_A_TOKEN"
token_url = "https://service-a.example.com/{{WORK_USER}}/tokens"
test_url = "https://service-a.example.com/api/v1/me"
icon = "ticket"

[services.SERVICE_B]
display_name = "Service B"
token_var = "SERVICE_B_TOKEN"
token_url = "https://service-b.example.com/tokens"
test_url = "https://service-b.example.com/api/v1/me"
icon = "book"

[import_aliases.LEGACY_SHARED_TOKEN]
target = "SERVICE_B_TOKEN"
""".strip(),
        encoding="utf-8",
    )
    return root


@pytest.fixture()
def ctx(config_root: Path) -> AppContext:
    return AppContext(
        session=SessionState(token="session-token-x"),
        config_context=resolve_config_context(config_root=config_root, environ={}),
    )


@pytest.fixture()
def client(ctx: AppContext) -> TestClient:
    app = create_app(ctx)
    return TestClient(app)


def _headers(ctx: AppContext) -> dict[str, str]:
    return {SESSION_HEADER: ctx.session.token}


def test_bootstrap_returns_session_token(client: TestClient, ctx: AppContext) -> None:
    r = client.get("/api/bootstrap")
    assert r.status_code == 200
    data = r.json()
    assert data["session_token"] == ctx.session.token
    assert "version" in data


def test_state_requires_session_header(client: TestClient) -> None:
    r = client.get("/api/state")
    assert r.status_code == 401


@pytest.mark.parametrize(
    ("method", "path", "json_body"),
    [
        ("get", "/api/state", None),
        ("post", "/api/open-folder", None),
        ("post", "/api/open-config-folder", None),
        ("post", "/api/token/SERVICE_A", {"token": "x"}),
        ("post", "/api/test/SERVICE_A", None),
        ("post", "/api/test-all", None),
        ("post", "/api/import/scan-path", {"path": "source.env"}),
        ("post", "/api/import/scan-dropped", {"filename": "x.env", "content": "A=1\n"}),
        (
            "post",
            "/api/import/test",
            {"scanId": "missing", "sourceKey": "A", "targetKey": "SERVICE_A_TOKEN"},
        ),
        ("post", "/api/import/commit", {"scanId": "missing", "mappings": []}),
    ],
)
def test_all_non_bootstrap_api_endpoints_require_session(
    client: TestClient,
    method: str,
    path: str,
    json_body: dict[str, object] | None,
) -> None:
    request = getattr(client, method)

    r = request(path, json=json_body) if json_body is not None else request(path)

    assert r.status_code == 401


def test_state_returns_payload(client: TestClient, ctx: AppContext) -> None:
    r = client.get("/api/state", headers=_headers(ctx))
    assert r.status_code == 200
    body = r.json()
    assert "config" in body
    assert body["config"]["name"] == "API test"
    service_ids = {s["service_id"] for s in body["services"]}
    assert {"SERVICE_A", "SERVICE_B"}.issubset(service_ids)


def test_state_masks_configured_identity_and_derived_values(
    client: TestClient,
    ctx: AppContext,
    config_root: Path,
    env_path: Path,
) -> None:
    config_file = config_root / "config.toml"
    config_file.write_text(
        config_file.read_text(encoding="utf-8")
        .replace(
            'value = "alice@example.com"',
            'value = "alice@example.com"\ndisplay = "masked"',
        )
        .replace(
            "[derived.WORK_USERNAME]\nfrom_identity = \"WORK_EMAIL\"",
            (
                "[derived.WORK_USERNAME]\n"
                "from_identity = \"WORK_EMAIL\"\n"
                "display = \"masked\""
            ),
        ),
        encoding="utf-8",
    )
    env_path.write_text("WORK_USERNAME=alice@example.com\n", encoding="utf-8")

    r = client.get("/api/state", headers=_headers(ctx))

    assert r.status_code == 200
    body = r.json()
    work_email = next(i for i in body["identities"] if i["name"] == "WORK_EMAIL")
    derived = next(d for d in body["derived"] if d["variable_name"] == "WORK_USERNAME")
    assert work_email["effective_value"] == "••••••••.com"
    assert work_email["detected_value"] == "••••••••.com"
    assert derived["current_value"] == "••••••••.com"
    assert derived["computed_default"] == "••••••••.com"
    assert "alice@example.com" not in r.text


def test_state_invalid_config_error_is_non_secret(tmp_path: Path) -> None:
    config_root = tmp_path / "config"
    config_root.mkdir()
    (config_root / "config.toml").write_text(
        """
version = 1

[services.BAD]
display_name = "Bad"
token_var = "SECRET_TOKEN_VALUE"
""".strip(),
        encoding="utf-8",
    )
    ctx = AppContext(
        session=SessionState(token="session-token-x"),
        config_context=resolve_config_context(config_root=config_root, environ={}),
    )
    client = TestClient(create_app(ctx))

    r = client.get("/api/state", headers=_headers(ctx))

    assert r.status_code == 400
    body = r.json()
    assert body["error"] == "ConfigSchemaError"
    assert "SECRET_TOKEN_VALUE" not in body["message"]


def test_open_folder_uses_env_location_helper(
    client: TestClient, ctx: AppContext, env_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[Path] = []
    monkeypatch.setattr("dotfill.api.open_env_location", calls.append)

    r = client.post("/api/open-folder", headers=_headers(ctx))

    assert r.status_code == 200
    assert calls == [env_path.resolve(strict=False)]


def test_open_config_folder_uses_final_config_dir_without_toml_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_root = tmp_path / "config-root"
    local_ctx = AppContext(
        session=SessionState(token="session-token-x"),
        config_context=resolve_config_context(
            config_root=config_root,
            profile="team",
            environ={},
        ),
    )
    local_client = TestClient(create_app(local_ctx))
    calls: list[tuple[Path, bool]] = []

    def fake_open_directory(directory: Path, *, create: bool = False) -> None:
        calls.append((directory, create))
        if create:
            directory.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("dotfill.api.open_directory", fake_open_directory)

    r = local_client.post("/api/open-config-folder", headers=_headers(local_ctx))

    expected = config_root.resolve(strict=False) / "profiles" / "team"
    assert r.status_code == 200
    assert calls == [(expected, True)]
    assert expected.is_dir()
    assert not (expected / "config_common.toml").exists()
    assert not (expected / "config.toml").exists()


def test_save_token_writes_env_and_fills_derived(
    client: TestClient, ctx: AppContext, env_path: Path
) -> None:
    r = client.post(
        "/api/token/SERVICE_A",
        headers=_headers(ctx),
        json={"token": "newtokenvalue"},
    )

    assert r.status_code == 200, r.text
    text = env_path.read_text(encoding="utf-8")
    assert "SERVICE_A_TOKEN=newtokenvalue" in text
    assert "WORK_USERNAME=alice@example.com" in text


def test_cross_origin_mutating_request_rejected(
    client: TestClient, ctx: AppContext
) -> None:
    r = client.post(
        "/api/token/SERVICE_A",
        headers={**_headers(ctx), "Origin": "https://evil.example"},
        json={"token": "newtokenvalue"},
    )

    assert r.status_code == 403
    assert "access-control-allow-origin" not in r.headers


def test_local_origin_mutating_request_allowed_without_cors_header(
    client: TestClient, ctx: AppContext
) -> None:
    r = client.post(
        "/api/token/SERVICE_A",
        headers={**_headers(ctx), "Origin": "http://127.0.0.1:41235"},
        json={"token": "newtokenvalue"},
    )

    assert r.status_code == 200
    assert "access-control-allow-origin" not in r.headers


def test_save_token_unknown_service_404(client: TestClient, ctx: AppContext) -> None:
    r = client.post(
        "/api/token/UNKNOWN", headers=_headers(ctx), json={"token": "x"}
    )
    assert r.status_code == 404


@respx.mock
def test_test_endpoint_success(
    client: TestClient, ctx: AppContext, env_path: Path
) -> None:
    env_path.write_text("SERVICE_A_TOKEN=t\n", encoding="utf-8")
    respx.get("https://service-a.example.com/api/v1/me").mock(
        return_value=httpx.Response(200)
    )

    r = client.post("/api/test/SERVICE_A", headers=_headers(ctx))

    assert r.status_code == 200, r.text
    assert r.json()["status"] == "working"


def test_test_endpoint_no_token_400(client: TestClient, ctx: AppContext) -> None:
    r = client.post("/api/test/SERVICE_A", headers=_headers(ctx))
    assert r.status_code == 400


@respx.mock
def test_test_all_skips_services_without_tokens(
    client: TestClient, ctx: AppContext, env_path: Path
) -> None:
    env_path.write_text("SERVICE_A_TOKEN=t\n", encoding="utf-8")
    respx.get("https://service-a.example.com/api/v1/me").mock(
        return_value=httpx.Response(200)
    )

    r = client.post("/api/test-all", headers=_headers(ctx))

    assert r.status_code == 200
    results = r.json()["results"]
    assert len(results) == 1
    assert results[0]["service_id"] == "SERVICE_A"
    assert results[0]["status"] == "working"


@respx.mock
def test_import_test_uses_scan_candidate_without_saving_or_caching(
    client: TestClient, ctx: AppContext, env_path: Path
) -> None:
    ctx.session.test_results["SERVICE_A"] = DotfillTestResult(
        status="failed",
        http_status=401,
        error_message="Authentication failed",
    )
    route = respx.get("https://service-a.example.com/api/v1/me").mock(
        return_value=httpx.Response(200)
    )
    r = client.post(
        "/api/import/scan-dropped",
        headers=_headers(ctx),
        json={"filename": "src.env", "content": "SERVICE_A_TOKEN=imported-token\n"},
    )
    scan_id = r.json()["scan_id"]

    r2 = client.post(
        "/api/import/test",
        headers=_headers(ctx),
        json={
            "scanId": scan_id,
            "sourceKey": "SERVICE_A_TOKEN",
            "targetKey": "SERVICE_A_TOKEN",
        },
    )

    assert r2.status_code == 200, r2.text
    assert r2.json()["service_id"] == "SERVICE_A"
    assert r2.json()["status"] == "working"
    assert route.called
    assert route.calls[0].request.headers["Authorization"] == "Bearer imported-token"
    assert env_path.read_text(encoding="utf-8") == ""
    assert ctx.session.backup_created is False
    assert ctx.session.test_results["SERVICE_A"].status == "failed"
    assert "SERVICE_A_TOKEN" in ctx.session.import_scans[scan_id].candidates


@respx.mock
def test_import_test_reports_failed_candidate_without_saved_cache_mutation(
    client: TestClient, ctx: AppContext
) -> None:
    ctx.session.test_results["SERVICE_A"] = DotfillTestResult(
        status="working",
        http_status=200,
    )
    respx.get("https://service-a.example.com/api/v1/me").mock(
        return_value=httpx.Response(403)
    )
    r = client.post(
        "/api/import/scan-dropped",
        headers=_headers(ctx),
        json={"filename": "src.env", "content": "SERVICE_A_TOKEN=bad-token\n"},
    )
    scan_id = r.json()["scan_id"]

    r2 = client.post(
        "/api/import/test",
        headers=_headers(ctx),
        json={
            "scanId": scan_id,
            "sourceKey": "SERVICE_A_TOKEN",
            "targetKey": "SERVICE_A_TOKEN",
        },
    )

    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["service_id"] == "SERVICE_A"
    assert body["status"] == "failed"
    assert body["http_status"] == 403
    assert body["error_message"] == "Authentication failed"
    assert ctx.session.test_results["SERVICE_A"].status == "working"


def test_import_test_rejects_unknown_scan(client: TestClient, ctx: AppContext) -> None:
    r = client.post(
        "/api/import/test",
        headers=_headers(ctx),
        json={
            "scanId": "missing",
            "sourceKey": "SERVICE_A_TOKEN",
            "targetKey": "SERVICE_A_TOKEN",
        },
    )

    assert r.status_code == 404
    assert r.json()["detail"] == "Unknown scan_id"


@pytest.mark.parametrize(
    ("source_key", "target_key", "message"),
    [
        ("MISSING_SOURCE", "SERVICE_A_TOKEN", "Unknown source key in scan"),
        ("SERVICE_A_TOKEN", "WORK_USERNAME", "Import target is not a service token"),
        ("SERVICE_A_TOKEN", "UNKNOWN_TOKEN", "Import target is not a service token"),
    ],
)
def test_import_test_rejects_invalid_source_or_target(
    client: TestClient,
    ctx: AppContext,
    source_key: str,
    target_key: str,
    message: str,
) -> None:
    r = client.post(
        "/api/import/scan-dropped",
        headers=_headers(ctx),
        json={"filename": "src.env", "content": "SERVICE_A_TOKEN=imported-token\n"},
    )
    scan_id = r.json()["scan_id"]

    r2 = client.post(
        "/api/import/test",
        headers=_headers(ctx),
        json={
            "scanId": scan_id,
            "sourceKey": source_key,
            "targetKey": target_key,
        },
    )

    assert r2.status_code == 400
    assert r2.json()["detail"] == message


def test_import_scan_and_commit_flow(
    client: TestClient, ctx: AppContext, env_path: Path
) -> None:
    r = client.post(
        "/api/import/scan-dropped",
        headers=_headers(ctx),
        json={
            "filename": "dropped.env",
            "content": (
                "SERVICE_A_TOKEN=fromsource1234\n"
                "LEGACY_SHARED_TOKEN=alias-secret-9999\n"
            ),
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    scan_id = body["scan_id"]
    assert body["source_label"] == "Dropped file: dropped.env"
    row_by_source = {row["source_key"]: row for row in body["rows"]}
    assert row_by_source["SERVICE_A_TOKEN"]["target_key"] == "SERVICE_A_TOKEN"
    assert row_by_source["LEGACY_SHARED_TOKEN"]["target_key"] == "SERVICE_B_TOKEN"

    r2 = client.post(
        "/api/import/commit",
        headers=_headers(ctx),
        json={
            "scanId": scan_id,
            "mappings": [
                {"sourceKey": "SERVICE_A_TOKEN", "targetKey": "SERVICE_A_TOKEN"},
                {
                    "sourceKey": "LEGACY_SHARED_TOKEN",
                    "targetKey": "SERVICE_B_TOKEN",
                },
            ],
        },
    )

    assert r2.status_code == 200, r2.text
    text = env_path.read_text(encoding="utf-8")
    assert "SERVICE_A_TOKEN=fromsource1234" in text
    assert "SERVICE_B_TOKEN=alias-secret-9999" in text


def test_import_commit_unknown_scan_404(client: TestClient, ctx: AppContext) -> None:
    r = client.post(
        "/api/import/commit",
        headers=_headers(ctx),
        json={"scanId": "nope", "mappings": []},
    )
    assert r.status_code == 404


def test_duplicate_managed_var_blocks_state(
    client: TestClient, ctx: AppContext, env_path: Path
) -> None:
    env_path.write_text(
        "SERVICE_A_TOKEN=a\nSERVICE_A_TOKEN=b\n", encoding="utf-8"
    )

    r = client.get("/api/state", headers=_headers(ctx))

    assert r.status_code == 409
    assert "SERVICE_A_TOKEN" in r.json()["message"]


def test_scan_response_includes_occupied_targets_for_status_recomputation(
    client: TestClient, ctx: AppContext, env_path: Path
) -> None:
    env_path.write_text("SERVICE_A_TOKEN=existing\n", encoding="utf-8")
    r = client.post(
        "/api/import/scan-dropped",
        headers=_headers(ctx),
        json={"filename": "source.env", "content": "WEIRD_THING=value123\n"},
    )

    assert r.status_code == 200
    body = r.json()
    assert "occupied_targets" in body
    assert "SERVICE_A_TOKEN" in body["occupied_targets"]
    assert "SERVICE_B_TOKEN" not in body["occupied_targets"]


def test_token_save_does_not_write_primary_identity(
    client: TestClient, ctx: AppContext, env_path: Path
) -> None:
    r = client.post(
        "/api/token/SERVICE_A",
        headers=_headers(ctx),
        json={"token": "mytoken"},
    )

    assert r.status_code == 200
    text = env_path.read_text(encoding="utf-8")
    assert "SERVICE_A_TOKEN=mytoken" in text
    assert "WORK_EMAIL=" not in text
    assert "WORK_USER=" not in text


def test_token_save_preserves_diverged_derived(
    client: TestClient, ctx: AppContext, env_path: Path
) -> None:
    env_path.write_text("WORK_USERNAME=custom@other.com\n", encoding="utf-8")

    r = client.post(
        "/api/token/SERVICE_A",
        headers=_headers(ctx),
        json={"token": "t"},
    )

    assert r.status_code == 200
    text = env_path.read_text(encoding="utf-8")
    assert "WORK_USERNAME=custom@other.com" in text


def test_token_save_does_not_fill_disabled_derived(tmp_path: Path) -> None:
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
source = "literal"
value = "alice@example.com"

[derived.WORK_USERNAME]
enabled = false
from_identity = "WORK_EMAIL"

[services.EXAMPLE]
display_name = "Example"
token_var = "EXAMPLE_TOKEN"
token_url = "https://example.com/tokens"
test_url = "https://example.com/me"
""".strip(),
        encoding="utf-8",
    )
    local_ctx = AppContext(
        session=SessionState(token="session-token-x"),
        config_context=resolve_config_context(config_root=config_root, environ={}),
    )
    local_client = TestClient(create_app(local_ctx))

    r = local_client.post(
        "/api/token/EXAMPLE",
        headers=_headers(local_ctx),
        json={"token": "mytoken"},
    )

    assert r.status_code == 200
    text = env.read_text(encoding="utf-8")
    assert "EXAMPLE_TOKEN=mytoken" in text
    assert "WORK_USERNAME=" not in text


def test_scan_path_endpoint(
    client: TestClient, ctx: AppContext, env_path: Path, tmp_path: Path
) -> None:
    source = tmp_path / "source.env"
    source.write_text("SERVICE_A_TOKEN=fromfile\n", encoding="utf-8")

    r = client.post(
        "/api/import/scan-path",
        headers=_headers(ctx),
        json={"path": str(source)},
    )

    assert r.status_code == 200
    body = r.json()
    assert "scan_id" in body
    assert "rows" in body
    assert body["source_label"] == str(source)
    assert body["rows"][0]["source_key"] == "SERVICE_A_TOKEN"
    assert body["rows"][0]["status"] == "new"


def test_scan_path_not_found(
    client: TestClient, ctx: AppContext, tmp_path: Path
) -> None:
    r = client.post(
        "/api/import/scan-path",
        headers=_headers(ctx),
        json={"path": str(tmp_path / "nonexistent.env")},
    )
    assert r.status_code == 400


@respx.mock
def test_token_save_invalidates_test_result(
    client: TestClient, ctx: AppContext, env_path: Path
) -> None:
    env_path.write_text("SERVICE_A_TOKEN=oldtoken\n", encoding="utf-8")
    respx.get("https://service-a.example.com/api/v1/me").mock(
        return_value=httpx.Response(200)
    )
    r = client.post("/api/test/SERVICE_A", headers=_headers(ctx))
    assert r.json()["status"] == "working"

    r2 = client.post(
        "/api/token/SERVICE_A",
        headers=_headers(ctx),
        json={"token": "newtoken"},
    )
    assert r2.status_code == 200

    r3 = client.get("/api/state", headers=_headers(ctx))
    service_a = next(s for s in r3.json()["services"] if s["service_id"] == "SERVICE_A")
    assert service_a["test_status"] == "set"


@respx.mock
def test_hand_editing_token_invalidates_cached_test_result(
    client: TestClient, ctx: AppContext, env_path: Path
) -> None:
    env_path.write_text("SERVICE_A_TOKEN=oldtoken\n", encoding="utf-8")
    respx.get("https://service-a.example.com/api/v1/me").mock(
        return_value=httpx.Response(200)
    )

    r = client.post("/api/test/SERVICE_A", headers=_headers(ctx))
    assert r.json()["status"] == "working"
    r2 = client.get("/api/state", headers=_headers(ctx))
    service_a = next(s for s in r2.json()["services"] if s["service_id"] == "SERVICE_A")
    assert service_a["test_status"] == "working"

    env_path.write_text("SERVICE_A_TOKEN=changedtoken\n", encoding="utf-8")

    r3 = client.get("/api/state", headers=_headers(ctx))
    service_a = next(s for s in r3.json()["services"] if s["service_id"] == "SERVICE_A")
    assert service_a["test_status"] == "set"


@respx.mock
def test_changing_test_url_invalidates_cached_test_result(
    client: TestClient, ctx: AppContext, config_root: Path, env_path: Path
) -> None:
    env_path.write_text("SERVICE_A_TOKEN=oldtoken\n", encoding="utf-8")
    respx.get("https://service-a.example.com/api/v1/me").mock(
        return_value=httpx.Response(200)
    )
    r = client.post("/api/test/SERVICE_A", headers=_headers(ctx))
    assert r.json()["status"] == "working"

    config_file = config_root / "config.toml"
    config_file.write_text(
        config_file.read_text(encoding="utf-8").replace(
            "https://service-a.example.com/api/v1/me",
            "https://service-a.example.com/api/v2/me",
        ),
        encoding="utf-8",
    )

    r2 = client.get("/api/state", headers=_headers(ctx))
    service_a = next(s for s in r2.json()["services"] if s["service_id"] == "SERVICE_A")
    assert service_a["resolved_test_url"] == "https://service-a.example.com/api/v2/me"
    assert service_a["test_status"] == "set"


def test_token_save_to_new_env_reports_backup_created(
    client: TestClient, ctx: AppContext, env_path: Path
) -> None:
    env_path.unlink(missing_ok=True)

    r = client.post(
        "/api/token/SERVICE_A",
        headers=_headers(ctx),
        json={"token": "mytoken"},
    )
    assert r.status_code == 200

    r2 = client.get("/api/state", headers=_headers(ctx))
    session_data = r2.json()["session"]
    assert session_data["backup_created"] is True
    assert session_data["backup_path"] is None


def test_import_commit_invalidates_test_result(
    client: TestClient, ctx: AppContext, env_path: Path
) -> None:
    env_path.write_text("SERVICE_A_TOKEN=oldtoken\n", encoding="utf-8")
    ctx.session.test_results["SERVICE_A"] = DotfillTestResult(
        status="working",
        http_status=200,
    )

    r = client.post(
        "/api/import/scan-dropped",
        headers=_headers(ctx),
        json={"filename": "src.env", "content": "SERVICE_A_TOKEN=replaced\n"},
    )
    scan_id = r.json()["scan_id"]
    r2 = client.post(
        "/api/import/commit",
        headers=_headers(ctx),
        json={
            "scanId": scan_id,
            "mappings": [{"sourceKey": "SERVICE_A_TOKEN", "targetKey": "SERVICE_A_TOKEN"}],
        },
    )
    assert r2.status_code == 200

    r3 = client.get("/api/state", headers=_headers(ctx))
    service_a = next(s for s in r3.json()["services"] if s["service_id"] == "SERVICE_A")
    assert service_a["test_status"] == "set"


def test_import_commit_skips_latest_no_change_rows(
    client: TestClient, ctx: AppContext, env_path: Path
) -> None:
    r = client.post(
        "/api/import/scan-dropped",
        headers=_headers(ctx),
        json={"filename": "src.env", "content": "SERVICE_A_TOKEN=scanned\n"},
    )
    scan_id = r.json()["scan_id"]
    env_path.write_text("SERVICE_A_TOKEN=scanned\n", encoding="utf-8")

    r2 = client.post(
        "/api/import/commit",
        headers=_headers(ctx),
        json={
            "scanId": scan_id,
            "mappings": [{"sourceKey": "SERVICE_A_TOKEN", "targetKey": "SERVICE_A_TOKEN"}],
        },
    )

    assert r2.status_code == 200
    assert r2.json()["updated"] == []
    assert env_path.read_text(encoding="utf-8") == "SERVICE_A_TOKEN=scanned\n"
    assert ctx.session.backup_created is False
