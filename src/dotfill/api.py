"""HTTP API for the dotfill local web UI."""

from __future__ import annotations

import logging
import secrets
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from .config import resolve_url_template
from .config_paths import ConfigContext, resolve_config_context
from .envdoc import EnvDocument
from .errors import (
    ConfigValidationError,
    DotfillError,
    DuplicateManagedVariableError,
    ImportScanError,
    SaveError,
    ServiceTestError,
    UnresolvedIdentityError,
    UrlTemplateError,
)
from .import_scan import (
    build_updates_from_choices,
    scan_source_text,
)
from .models import (
    AppState,
    CommitImportRequest,
    ImportTestRequest,
    SaveTokenRequest,
    ScanDroppedRequest,
    ScanPathRequest,
    SessionState,
    TestResult,
)
from .open_paths import open_directory, open_env_location
from .resolver import build_app_state, service_icon, service_test_fingerprint
from .save import save_assignments
from .service_test import run_service_test
from .value_policy import display_value

log = logging.getLogger(__name__)

SESSION_HEADER = "X-Dotfill-Session"
_MUTATING_METHODS = {"DELETE", "PATCH", "POST", "PUT"}
_LOCAL_ORIGIN_HOSTS = {"127.0.0.1", "localhost", "::1"}


class AppContext:
    """Shared mutable singleton for the FastAPI app."""

    def __init__(
        self,
        session: SessionState,
        *,
        config_context: ConfigContext | None = None,
        env_path: Path | None = None,
    ) -> None:
        self.config_context = config_context or resolve_config_context()
        self.env_path_override = env_path
        self.session = session


def _require_session(
    ctx: AppContext, provided: str | None
) -> None:
    if not provided or not secrets.compare_digest(provided, ctx.session.token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing session token",
        )


def _state(ctx: AppContext) -> AppState:
    return build_app_state(
        ctx.config_context,
        ctx.session,
        env_path_override=ctx.env_path_override,
    )


def _is_local_origin(origin: str) -> bool:
    parsed = urlsplit(origin)
    return parsed.scheme in {"http", "https"} and parsed.hostname in _LOCAL_ORIGIN_HOSTS


def _identity_payload(state: AppState) -> list[dict[str, object]]:
    return [
        {
            "name": i.name,
            "detected_value": display_value(
                i.detected_value,
                state.effective_config.identities[i.name].display,
            ),
            "explicit_value": display_value(
                i.explicit_value,
                state.effective_config.identities[i.name].display,
            ),
            "effective_value": display_value(
                i.effective_value,
                state.effective_config.identities[i.name].display,
            ),
            "source": i.source,
        }
        for i in state.identities
    ]


def _derived_payload(state: AppState) -> list[dict[str, object]]:
    return [
        {
            "variable_name": d.variable_name,
            "current_value": display_value(
                d.current_value,
                state.effective_config.derived_variables[d.variable_name].display,
            ),
            "computed_default": display_value(
                d.computed_default,
                state.effective_config.derived_variables[d.variable_name].display,
            ),
            "source_identity_name": d.source_identity_name,
            "status": d.status,
        }
        for d in state.derived
    ]


def _service_payload(state: AppState) -> list[dict[str, object]]:
    return [
        {
            "service_id": s.service_id,
            "display_name": s.display_name,
            "token_var": s.token_var,
            "token_present": s.token_present,
            "masked_token": s.masked_token,
            "resolved_token_url": s.resolved_token_url,
            "resolved_test_url": s.resolved_test_url,
            "test_status": s.test_status,
            "icon": s.icon or service_icon(None),
        }
        for s in state.services
    ]


def _state_payload(state: AppState) -> dict[str, object]:
    return {
        "env_path": str(state.env_path),
        "config": {
            "profile": state.config_context.profile,
            "name": state.config_name,
            "config_dir": str(state.config_context.config_dir),
            "common_config_path": str(state.config_context.common_config_path),
            "user_config_path": str(state.config_context.user_config_path),
        },
        "identities": _identity_payload(state),
        "derived": _derived_payload(state),
        "services": _service_payload(state),
        "session": {
            "queue_test_all_on_dashboard_load": state.session.queue_test_all_on_dashboard_load,
            "backup_created": state.session.backup_created,
            "backup_path": str(state.session.backup_path)
            if state.session.backup_path
            else None,
        },
    }


def _service_fingerprint(
    state: AppState,
    *,
    service_id: str,
    resolved_test_url: str,
    token: str,
) -> str:
    svc_def = state.effective_config.services[service_id]
    return service_test_fingerprint(
        service_id=service_id,
        token_var=svc_def.token_var,
        resolved_test_url=resolved_test_url,
        auth=svc_def.auth,
        tls_verify=svc_def.tls_verify,
        token=token,
        session_token=state.session.token,
    )


def create_app(ctx: AppContext) -> FastAPI:
    app = FastAPI(title="dotfill", docs_url=None, redoc_url=None, openapi_url=None)
    api = APIRouter(prefix="/api")

    @app.middleware("http")
    async def reject_unexpected_origin(
        request: Request,
        call_next,  # type: ignore[no-untyped-def]
    ):
        if request.method in _MUTATING_METHODS and request.url.path.startswith("/api/"):
            origin = request.headers.get("origin")
            if origin and not _is_local_origin(origin):
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": "ForbiddenOrigin",
                        "message": "Unexpected request origin",
                    },
                )
        return await call_next(request)

    def session_dep(
        request: Request,
        x_dotfill_session: Annotated[str | None, Header(alias=SESSION_HEADER)] = None,
    ) -> AppContext:
        # Allow the bootstrap endpoint to skip the header.
        if request.url.path == "/api/bootstrap":
            return ctx
        _require_session(ctx, x_dotfill_session)
        return ctx

    @app.exception_handler(DotfillError)
    async def _df_exc_handler(_: Request, exc: DotfillError) -> JSONResponse:
        log.warning("Dotfill error: %s", exc)
        status_map = {
            DuplicateManagedVariableError: 409,
            ConfigValidationError: 400,
            UrlTemplateError: 400,
            UnresolvedIdentityError: 409,
            ImportScanError: 400,
            ServiceTestError: 400,
            SaveError: 500,
        }
        code = next(
            (status_code for error_type, status_code in status_map.items() if isinstance(exc, error_type)),
            500,
        )
        return JSONResponse(
            status_code=code,
            content={"error": type(exc).__name__, "message": str(exc)},
        )

    @api.get("/bootstrap")
    def bootstrap() -> dict[str, object]:
        """Public endpoint: hands the SPA its session token and version."""
        from . import __version__

        return {"session_token": ctx.session.token, "version": __version__}

    @api.post("/open-folder")
    def open_folder(ctx_in: AppContext = Depends(session_dep)) -> dict[str, object]:
        """Open the directory containing the .env file in the system file manager."""
        state = _state(ctx_in)
        open_env_location(state.env_path)
        return {"ok": True}

    @api.post("/open-config-folder")
    def open_config_folder(ctx_in: AppContext = Depends(session_dep)) -> dict[str, object]:
        """Open the resolved dotfill config directory in the system file manager."""
        open_directory(ctx_in.config_context.config_dir, create=True)
        return {"ok": True}

    @api.get("/state")
    def get_state(ctx_in: AppContext = Depends(session_dep)) -> dict[str, object]:
        return _state_payload(_state(ctx_in))

    @api.post("/token/{service_id}")
    def save_token(
        service_id: str,
        body: SaveTokenRequest,
        ctx_in: AppContext = Depends(session_dep),
    ) -> dict[str, object]:
        state = _state(ctx_in)
        svc = next(
            (s for s in state.services if s.service_id == service_id),
            None,
        )
        if svc is None:
            raise HTTPException(status_code=404, detail=f"Unknown service {service_id}")
        # Also fill in derived identity variables that are missing/empty.
        derived_updates = {
            d.variable_name: d.computed_default
            for d in state.derived
            if d.status == "missing" and d.computed_default
        }
        updates: dict[str, str] = dict(derived_updates)
        updates[svc.token_var] = body.token.get_secret_value()
        save_assignments(state.env_path, state.env_doc, updates, ctx_in.session)
        log.info("Token saved for %s", service_id)
        # Invalidate cached test result since the token value changed.
        ctx_in.session.test_results.pop(service_id, None)
        return {"ok": True, "updated": sorted(updates.keys())}

    @api.post("/test/{service_id}")
    def test_one(
        service_id: str,
        ctx_in: AppContext = Depends(session_dep),
    ) -> dict[str, object]:
        state = _state(ctx_in)
        svc_def = state.effective_config.services.get(service_id)
        if svc_def is None:
            raise HTTPException(status_code=404, detail=f"Unknown service {service_id}")
        token = state.env_doc.get(svc_def.token_var)
        if not token:
            raise HTTPException(status_code=400, detail="No token to test")
        identity_values = {i.name: i.effective_value for i in state.identities}
        try:
            resolved = resolve_url_template(svc_def.test_url_template, identity_values)
        except UrlTemplateError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        result = run_service_test(
            svc_def,
            service_id=service_id,
            resolved_test_url=resolved,
            token=token,
        )
        result.fingerprint = _service_fingerprint(
            state,
            service_id=service_id,
            resolved_test_url=resolved,
            token=token,
        )
        ctx_in.session.test_results[service_id] = result
        return {
            "service_id": service_id,
            "status": result.status,
            "http_status": result.http_status,
            "error_message": result.error_message,
        }

    @api.post("/test-all")
    def test_all(
        ctx_in: AppContext = Depends(session_dep),
    ) -> dict[str, object]:
        state = _state(ctx_in)
        identity_values = {i.name: i.effective_value for i in state.identities}
        results: list[dict[str, object]] = []
        for svc_id, svc_def in state.effective_config.services.items():
            token = state.env_doc.get(svc_def.token_var)
            if not token:
                continue
            try:
                resolved = resolve_url_template(
                    svc_def.test_url_template, identity_values
                )
            except UrlTemplateError as exc:
                ctx_in.session.test_results[svc_id] = TestResult(
                    status="failed", error_message=str(exc)
                )
                results.append(
                    {
                        "service_id": svc_id,
                        "status": "failed",
                        "error_message": str(exc),
                    }
                )
                continue
            result = run_service_test(
                svc_def,
                service_id=svc_id,
                resolved_test_url=resolved,
                token=token,
            )
            result.fingerprint = _service_fingerprint(
                state,
                service_id=svc_id,
                resolved_test_url=resolved,
                token=token,
            )
            ctx_in.session.test_results[svc_id] = result
            results.append(
                {
                    "service_id": svc_id,
                    "status": result.status,
                    "http_status": result.http_status,
                    "error_message": result.error_message,
                }
            )
        ctx_in.session.queue_test_all_on_dashboard_load = False
        return {"results": results}

    @api.post("/import/scan-path")
    def scan_path(
        body: ScanPathRequest,
        ctx_in: AppContext = Depends(session_dep),
    ) -> dict[str, object]:
        path = Path(body.path).expanduser()
        if not path.exists():
            raise HTTPException(status_code=400, detail=f"Path not found: {path}")
        text = path.read_text(encoding="utf-8")
        state = _state(ctx_in)
        scan = scan_source_text(
            source_label=str(path),
            source_text=text,
            current_doc=state.env_doc,
            config=state.effective_config,
        )
        ctx_in.session.import_scans[scan.scan_id] = scan
        return _scan_payload(scan)

    @api.post("/import/scan-dropped")
    def scan_dropped(
        body: ScanDroppedRequest,
        ctx_in: AppContext = Depends(session_dep),
    ) -> dict[str, object]:
        state = _state(ctx_in)
        scan = scan_source_text(
            source_label=f"Dropped file: {body.filename}",
            source_text=body.content.get_secret_value(),
            current_doc=state.env_doc,
            config=state.effective_config,
        )
        ctx_in.session.import_scans[scan.scan_id] = scan
        return _scan_payload(scan)

    @api.post("/import/test")
    def test_import_candidate(
        body: ImportTestRequest,
        ctx_in: AppContext = Depends(session_dep),
    ) -> dict[str, object]:
        scan = ctx_in.session.import_scans.get(body.scanId)
        if scan is None:
            raise HTTPException(status_code=404, detail="Unknown scan_id")
        source_value = scan.candidates.get(body.sourceKey)
        if source_value is None:
            raise HTTPException(status_code=400, detail="Unknown source key in scan")
        state = _state(ctx_in)
        token_vars_to_svc = {
            svc.token_var: service_id
            for service_id, svc in state.effective_config.services.items()
        }
        service_id = token_vars_to_svc.get(body.targetKey)
        if service_id is None:
            raise HTTPException(
                status_code=400,
                detail="Import target is not a service token",
            )
        svc_def = state.effective_config.services[service_id]
        identity_values = {i.name: i.effective_value for i in state.identities}
        try:
            resolved = resolve_url_template(svc_def.test_url_template, identity_values)
        except UrlTemplateError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        result = run_service_test(
            svc_def,
            service_id=service_id,
            resolved_test_url=resolved,
            token=source_value.get_secret_value(),
        )
        return {
            "service_id": service_id,
            "status": result.status,
            "http_status": result.http_status,
            "error_message": result.error_message,
        }

    @api.post("/import/commit")
    def commit_import(
        body: CommitImportRequest,
        ctx_in: AppContext = Depends(session_dep),
    ) -> dict[str, object]:
        scan = ctx_in.session.import_scans.get(body.scanId)
        if scan is None:
            raise HTTPException(status_code=404, detail="Unknown scan_id")
        choices = [(c.sourceKey, c.targetKey) for c in body.mappings]
        state = _state(ctx_in)
        allowed_targets = {
            service.token_var for service in state.effective_config.services.values()
        } | set(state.effective_config.derived_variables)
        updates = build_updates_from_choices(
            scan,
            choices,
            allowed_targets=allowed_targets,
            current_doc=state.env_doc,
            config=state.effective_config,
        )
        save_assignments(state.env_path, state.env_doc, updates, ctx_in.session)
        log.info(
            "Import committed: %d variable(s) updated from %s",
            len(updates),
            scan.source_label,
        )
        token_vars_to_svc = {
            s.token_var: sid for sid, s in state.effective_config.services.items()
        }
        for target_key in updates:
            if target_key in token_vars_to_svc:
                ctx_in.session.test_results.pop(token_vars_to_svc[target_key], None)
        # Drop the scan once committed.
        ctx_in.session.import_scans.pop(body.scanId, None)
        return {"ok": True, "updated": sorted(updates.keys())}

    app.include_router(api)
    return app


def _scan_payload(scan) -> dict[str, object]:  # type: ignore[no-untyped-def]
    return {
        "scan_id": scan.scan_id,
        "source_label": scan.source_label,
        "occupied_targets": scan.occupied_targets,
        "rows": [
            {
                "source_key": r.source_key,
                "target_key": r.target_key,
                "mapping_kind": r.mapping_kind,
                "locked": r.locked,
                "status": r.status,
                "masked_source_value": r.masked_source_value,
            }
            for r in scan.proposed_rows
        ],
    }
