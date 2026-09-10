"""Local product presentation over existing application contracts; no financial formulas."""

from __future__ import annotations

import json
import secrets
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlsplit
from uuid import UUID
from wsgiref.simple_server import make_server

from pydantic import Field, TypeAdapter, ValidationError

from asymmetric_engine.application.product_persistence import (
    LoadedProductRecord,
    ProductRecordIntegrityError,
    ProductRecordKind,
    ProductRecordSchemaError,
    StoreProductRecord,
)
from asymmetric_engine.domain.portfolio import MarginalDecision, PortfolioFit
from asymmetric_engine.interfaces.api import (
    BuildMarginalDecisionRequest,
    BuildPortfolioStateRequest,
)
from asymmetric_engine.interfaces.decision_card import ProjectDecisionCard
from asymmetric_engine.interfaces.operator_workspace import (
    OperatorWorkspace,
    WorkspaceWriteUnavailable,
    workspace_submission_json,
)
from asymmetric_engine.interfaces.prospective_intake import (
    AieProspectiveIntake,
    BuildOpportunityStateRequest,
)
from asymmetric_engine.interfaces.workspace_web import (
    LOCAL_WORKSPACE_HOST,
    WRITE_TOKEN_HEADER,
    StartResponse,
    WorkspaceWsgiApp,
    WsgiBody,
    WsgiEnviron,
    _json_response,
    _projection,
    _response,
)

PRODUCT_UI_VERSION = "aie-product-ui-v1"
_REQUEST = TypeAdapter[
    BuildMarginalDecisionRequest | BuildPortfolioStateRequest | BuildOpportunityStateRequest
](
    Annotated[
        BuildMarginalDecisionRequest | BuildPortfolioStateRequest | BuildOpportunityStateRequest,
        Field(discriminator="operation"),
    ]
)
_CANONICAL_IDS = (
    "opportunity_id",
    "portfolio_state_id",
    "fit_id",
    "decision_id",
    "policy_decision_id",
    "replacement_decision_id",
    "review_id",
    "exposure_id",
    "analysis_id",
)


def _summary(item: LoadedProductRecord) -> dict[str, Any]:
    record = item.record.model_dump(mode="json")
    boundary = record.get("knowledge_boundary", {})
    label = record.get("title") or record.get("candidate_id") or item.envelope.kind.value
    causal = record.get("causal_analysis", {})
    beneficiaries = [
        node
        for node in causal.get("nodes", [])
        if node.get("subject_id") == record.get("candidate_id")
        and node.get("kind") == "beneficiary"
    ]
    if len(beneficiaries) == 1:
        label = beneficiaries[0]["label"]
    if isinstance(record.get("candidate_instrument"), dict):
        label = record["candidate_instrument"]["name"]
    if isinstance(record.get("alternative"), dict):
        label = record["alternative"]["label"]
    return {
        "record_id": str(item.envelope.record_id),
        "kind": item.envelope.kind.value,
        "label": label,
        "canonical_id": next((str(record[k]) for k in _CANONICAL_IDS if k in record), None),
        "input_fingerprint": record.get("input_fingerprint"),
        "as_of": boundary.get("as_of"),
        "knowledge_mode": boundary.get("knowledge_mode"),
        "stored_at": item.envelope.stored_at.isoformat(),
        "payload_sha256": item.envelope.payload_sha256,
        "opportunity_id": (record.get("opportunity_state") or {}).get("opportunity_id"),
        "opportunity_fingerprint": (record.get("opportunity_state") or {}).get("input_fingerprint"),
    }


class ProductUiService:
    """Storage views and explicit, reviewed invocations of already admitted commands."""

    def __init__(
        self,
        workspace: OperatorWorkspace,
        *,
        intake: AieProspectiveIntake | None = None,
        store: StoreProductRecord | None = None,
        reference_data: bool = False,
    ) -> None:
        if (intake is None) != (store is None):
            raise ValueError("intake requires its canonical product store")
        self.workspace = workspace
        self.intake = intake
        self.store = store
        self.reference_data = reference_data

    def records(self) -> list[dict[str, Any]]:
        return [
            _summary(self.workspace.load_record(item.record_id))
            for item in self.workspace.list_records()
        ]

    def detail(self, record_id: UUID) -> dict[str, Any]:
        item = self.workspace.load_record(record_id)
        card = _projection(item)
        fits: list[dict[str, Any]] = []
        if isinstance(item.record, MarginalDecision):
            references = {r.fit_id: r for r in item.record.portfolio_fits}
            selected: list[PortfolioFit] = []
            for summary in self.workspace.list_records(ProductRecordKind.PORTFOLIO_FIT):
                loaded = self.workspace.load_record(summary.record_id)
                fit = loaded.record
                if isinstance(fit, PortfolioFit) and fit.fit_id in references:
                    reference = references[fit.fit_id]
                    if reference.input_fingerprint != fit.input_fingerprint:
                        raise ProductRecordIntegrityError("Portfolio Fit fingerprint mismatch")
                    selected.append(fit)
                    fits.append(
                        {"summary": _summary(loaded), "record": fit.model_dump(mode="json")}
                    )
            if len(selected) != len(references):
                raise ProductRecordIntegrityError(
                    "Decision has missing exact Portfolio Fit records"
                )
            card = (
                "Decision Card",
                ProjectDecisionCard.from_marginal_decision(item.record, tuple(selected)).model_dump(
                    mode="json"
                ),
            )
        return {
            "summary": _summary(item),
            "record": item.record.model_dump(mode="json"),
            "card": card[1] if card is not None else None,
            "fits": fits,
            "verification": "storage_verified_not_financial_replay",
        }

    def _require_write(self) -> None:
        if not self.workspace.write_enabled:
            raise WorkspaceWriteUnavailable("Product UI is read-only")

    def prepare(self, payload: str) -> dict[str, Any]:
        self._require_write()
        request = _REQUEST.validate_json(payload)
        if isinstance(request, BuildOpportunityStateRequest) and self.intake is None:
            raise WorkspaceWriteUnavailable("Underwriting intake is not configured")
        return {"request": request.model_dump(mode="json"), "verification": "schema_only"}

    def submit(self, payload: str) -> dict[str, Any]:
        self._require_write()
        request = _REQUEST.validate_json(payload)
        if isinstance(request, BuildOpportunityStateRequest):
            if self.intake is None or self.store is None:
                raise WorkspaceWriteUnavailable("Underwriting intake is not configured")
            response = self.intake.build_opportunity_state(request)
            appended = self.store.execute(response.result)
            return {
                "response": response.model_dump(mode="json"),
                "persisted": [
                    {
                        "kind": appended.envelope.kind.value,
                        "record_id": str(appended.envelope.record_id),
                        "status": appended.status.value,
                    }
                ],
            }
        submission = self.workspace.submit(request)
        return json.loads(workspace_submission_json(submission))  # type: ignore[no-any-return]


def _require_local_origin(environ: WsgiEnviron) -> None:
    host = str(environ.get("HTTP_HOST", ""))
    parsed = urlsplit("http://" + host)
    if (
        parsed.hostname not in {"127.0.0.1", "localhost"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise PermissionError("Product UI accepts only an explicit loopback host")
    origin = environ.get("HTTP_ORIGIN")
    if origin is not None and origin != "http://" + host:
        raise PermissionError("Cross-origin product requests are forbidden")
    site = environ.get("HTTP_SEC_FETCH_SITE")
    if site is not None and site not in {"same-origin", "none"}:
        raise PermissionError("Cross-site product requests are forbidden")


class ProductUiWsgiApp:
    """Opt-in same-origin static frontend and JSON adapter beside the operator workspace."""

    def __init__(
        self, service: ProductUiService, frontend_dist: Path, *, write_token: str | None = None
    ) -> None:
        self.service = service
        self.frontend_dist = frontend_dist.resolve(strict=True)
        if not (self.frontend_dist / "index.html").is_file():
            raise ValueError("Build frontend/dist before opening the product UI")
        if service.workspace.write_enabled and not write_token:
            raise ValueError("write-enabled product UI requires a local write token")
        self.write_token = write_token
        self.operator = WorkspaceWsgiApp(service.workspace, write_token=write_token)

    @staticmethod
    def _json(start: StartResponse, payload: dict[str, Any], status: str = "200 OK") -> WsgiBody:
        return _json_response(start, status, {"contract_version": PRODUCT_UI_VERSION, **payload})

    def __call__(self, environ: WsgiEnviron, start: StartResponse) -> WsgiBody:
        path = str(environ.get("PATH_INFO", "/"))
        method = str(environ.get("REQUEST_METHOD", "GET")).upper()
        try:
            _require_local_origin(environ)
            if method == "GET" and path in {"/app", "/app/"}:
                return self._asset("index.html", start)
            if method == "GET" and path.startswith("/app/assets/"):
                return self._asset(path.removeprefix("/app/"), start)
            if path == "/ui-api/session" and method == "GET":
                return self._json(
                    start,
                    {
                        "write_enabled": self.service.workspace.write_enabled,
                        "intake_enabled": self.service.intake is not None,
                        "reference_data": self.service.reference_data,
                        "write_token": self.write_token,
                    },
                )
            if path == "/ui-api/records" and method == "GET":
                return self._json(start, {"records": self.service.records()})
            if path.startswith("/ui-api/records/") and method == "GET":
                record_id = UUID(path.removeprefix("/ui-api/records/"))
                return self._json(start, self.service.detail(record_id))
            if path in {"/ui-api/prepare", "/ui-api/submit"} and method == "POST":
                self.service._require_write()
                supplied = str(environ.get(WRITE_TOKEN_HEADER, ""))
                if not self.write_token or not secrets.compare_digest(self.write_token, supplied):
                    raise PermissionError("Missing or invalid product write token")
                if str(environ.get("CONTENT_TYPE", "")).split(";")[0] != "application/json":
                    raise ValueError("Product commands require application/json")
                payload = WorkspaceWsgiApp._read_body(environ).decode("utf-8")
                if path == "/ui-api/prepare":
                    return self._json(start, self.service.prepare(payload))
                return self._json(start, self.service.submit(payload), "201 Created")
            if path.startswith(("/ui-api/", "/app/")):
                raise KeyError("Product route not found")
            return self.operator(environ, start)
        except ValidationError as exc:
            return self._json(
                start,
                {
                    "blocking": True,
                    "error": "ValidationError",
                    "fields": exc.errors(include_context=False, include_input=False),
                },
                "400 Bad Request",
            )
        except (PermissionError, WorkspaceWriteUnavailable) as exc:
            return self._json(start, {"blocking": True, "message": str(exc)}, "403 Forbidden")
        except (KeyError, FileNotFoundError):
            return self._json(
                start, {"blocking": True, "message": "Record or asset not found"}, "404 Not Found"
            )
        except (ValueError, ProductRecordIntegrityError, ProductRecordSchemaError) as exc:
            return self._json(start, {"blocking": True, "message": str(exc)}, "409 Conflict")

    def _asset(self, relative: str, start: StartResponse) -> WsgiBody:
        path = (self.frontend_dist / relative).resolve(strict=True)
        if not path.is_relative_to(self.frontend_dist) or not path.is_file():
            raise PermissionError("Asset path is outside the frontend build")
        types = {".html": "text/html", ".css": "text/css", ".js": "text/javascript"}
        if path.suffix not in types:
            raise PermissionError("Asset type is not admitted")
        text = path.read_text(encoding="utf-8")
        if path.suffix != ".html":
            return _response(
                start, "200 OK", text, content_type=types[path.suffix] + "; charset=utf-8"
            )
        body = text.encode("utf-8")
        start(
            "200 OK",
            [
                ("Content-Type", "text/html; charset=utf-8"),
                ("Content-Length", str(len(body))),
                ("Cache-Control", "no-store"),
                ("X-Content-Type-Options", "nosniff"),
                ("X-Frame-Options", "DENY"),
                ("Referrer-Policy", "no-referrer"),
                (
                    "Content-Security-Policy",
                    "default-src 'none'; script-src 'self'; "
                    "style-src 'self'; connect-src 'self'; img-src 'self'; "
                    "base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
                ),
            ],
        )
        return [body]


def serve_product_ui(service: ProductUiService, frontend_dist: Path, *, port: int = 8765) -> None:
    if not 1 <= port <= 65535:
        raise ValueError("Product UI port must be between 1 and 65535")
    token = secrets.token_urlsafe(32) if service.workspace.write_enabled else None
    app = ProductUiWsgiApp(service, frontend_dist, write_token=token)
    with make_server(LOCAL_WORKSPACE_HOST, port, app) as server:
        server.serve_forever()
