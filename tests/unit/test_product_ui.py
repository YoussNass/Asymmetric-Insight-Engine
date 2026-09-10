"""Product boundary checks using real canonical services and immutable SQLite stores."""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from asymmetric_engine.application.product_persistence import (
    ListProductRecords,
    LoadProductRecord,
    ProductRecordIntegrityError,
    ProductRecordKind,
)
from asymmetric_engine.cli import main
from asymmetric_engine.domain.opportunity import UnderwritingDraft
from asymmetric_engine.domain.portfolio import PairwiseConclusion, PortfolioStateDraft
from asymmetric_engine.interfaces.api import BuildPortfolioStateRequest
from asymmetric_engine.interfaces.operator_workspace import (
    OperatorWorkspace,
    WorkspaceWriteUnavailable,
)
from asymmetric_engine.interfaces.product_ui import (
    PRODUCT_UI_VERSION,
    ProductUiService,
    ProductUiWsgiApp,
    _require_local_origin,
    serve_product_ui,
)
from asymmetric_engine.interfaces.prospective_intake import BuildOpportunityStateRequest
from asymmetric_engine.interfaces.workspace_web import MAX_REQUEST_BYTES
from tests.decision_factories import rebuild_decision_input
from tests.product_ui_factories import make_product_ui_runtime
from tests.product_ui_reference import create_reference


def test_reference_demo_is_canonical_and_never_overwrites(tmp_path: Path) -> None:
    directory = tmp_path / "reference"
    create_reference(directory)
    assert (directory / "evidence.sqlite").is_file()
    assert (directory / "products.sqlite").is_file()
    command = json.loads((directory / "new-capital.json").read_text())
    assert command["operation"] == "build_marginal_decision"
    with pytest.raises(FileExistsError):
        create_reference(directory)


def frontend(tmp_path: Path) -> Path:
    root = tmp_path / "dist"
    root.mkdir()
    (root / "index.html").write_text('<html lang="it">AIE</html>')
    (root / "assets").mkdir()
    (root / "assets" / "app.js").write_text("console.log('AIE');")
    (root / "assets" / "app.css").write_text("body { color: black; }")
    return root


def call(
    app: ProductUiWsgiApp,
    path: str,
    *,
    method: str = "GET",
    body: bytes = b"",
    extra: dict[str, Any] | None = None,
) -> tuple[str, dict[str, str], str]:
    environ: dict[str, Any] = {
        "HTTP_HOST": "127.0.0.1:8765",
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "CONTENT_LENGTH": str(len(body)),
        "CONTENT_TYPE": "application/json",
        "wsgi.input": BytesIO(body),
    }
    environ.update(extra or {})
    captured: list[tuple[str, dict[str, str]]] = []

    def start(status: str, headers: list[tuple[str, str]]) -> None:
        captured.append((status, dict(headers)))

    payload = b"".join(app(environ, start)).decode()
    return captured[0][0], captured[0][1], payload


def test_full_dossier_to_persisted_decision_matches_canonical_api(tmp_path: Path) -> None:
    runtime, service, request = make_product_ui_runtime(tmp_path)
    expected = runtime.api.build_marginal_decision(request)
    before = service.records()
    prepared = service.prepare(request.model_dump_json())
    assert prepared["verification"] == "schema_only"
    assert prepared["request"] == request.model_dump(mode="json")
    assert service.records() == before
    result = service.submit(request.model_dump_json())
    assert result["response"] == expected.model_dump(mode="json")
    assert len(result["persisted"]) == 5
    detail = service.detail(UUID(result["persisted"][-1]["record_id"]))
    assert detail["record"] == expected.result.decision.model_dump(mode="json")
    assert detail["card"]["action"] == "allocate"
    assert detail["card"]["execution_status"] == "not_evaluated"
    assert len(detail["fits"]) == 4
    assert detail["verification"] == "storage_verified_not_financial_replay"
    assert (
        detail["summary"]["opportunity_fingerprint"] == request.opportunity_state.input_fingerprint
    )
    assert detail["summary"]["opportunity_id"] == str(request.opportunity_state.opportunity_id)
    retry = service.submit(request.model_dump_json())
    assert [x["record_id"] for x in retry["persisted"]] == [
        x["record_id"] for x in result["persisted"]
    ]


def test_no_allocation_is_success_and_preserves_cash(tmp_path: Path) -> None:
    _, service, request = make_product_ui_runtime(tmp_path)
    comparisons = tuple(
        p.model_copy(update={"conclusion": PairwiseConclusion.INDETERMINATE})
        for p in request.decision_input.comparisons
    )
    revised = request.model_copy(
        update={
            "decision_input": rebuild_decision_input(
                request.decision_input, comparisons=comparisons
            )
        }
    )
    result = service.submit(revised.model_dump_json())
    detail = service.detail(UUID(result["persisted"][-1]["record_id"]))
    assert detail["card"]["action"] == "no_allocation"
    assert detail["card"][
        "evaluated_amount"
    ] == request.decision_input.capital_unit.amount.model_dump(mode="json")
    assert detail["card"]["selected_alternative_id"] == "alternative:investment-cash"


def test_tampered_input_never_creates_a_decision(tmp_path: Path) -> None:
    _, service, request = make_product_ui_runtime(tmp_path)
    before = service.records()
    data = request.model_dump(mode="json")
    data["opportunity_state"]["input_fingerprint"] = "0" * 64
    with pytest.raises(ValueError):
        service.submit(json.dumps(data))
    assert service.records() == before


def test_opportunity_intake_uses_real_owner_and_persists_exact_output(tmp_path: Path) -> None:
    runtime, service, request = make_product_ui_runtime(tmp_path)
    draft = UnderwritingDraft.model_validate(
        request.opportunity_state.model_dump(
            mode="python", exclude={"opportunity_id", "input_fingerprint", "source_documents"}
        )
    )
    intake = BuildOpportunityStateRequest(draft=draft)
    prepared = service.prepare(intake.model_dump_json())
    assert prepared["verification"] == "schema_only"
    result = service.submit(intake.model_dump_json())
    assert result["response"] == runtime.intake.build_opportunity_state(intake).model_dump(
        mode="json"
    )
    detail = service.detail(UUID(result["persisted"][0]["record_id"]))
    assert detail["summary"]["label"] == "Micron Technology"
    assert (
        detail["record"]["financial_facts"]
        == request.opportunity_state.model_dump(mode="json")["financial_facts"]
    )
    assert detail["card"] is None


def test_portfolio_preserves_currencies_and_emergency_cash(tmp_path: Path) -> None:
    _, service, request = make_product_ui_runtime(tmp_path)
    draft = PortfolioStateDraft.model_validate(
        request.portfolio_state.model_dump(
            mode="python", exclude={"portfolio_state_id", "input_fingerprint", "decision_record"}
        )
    )
    result = service.submit(BuildPortfolioStateRequest(draft=draft).model_dump_json())
    detail = service.detail(UUID(result["persisted"][0]["record_id"]))
    assert (
        detail["record"]["cash_balances"]
        == request.portfolio_state.model_dump(mode="json")["cash_balances"]
    )
    assert {x["balance"]["currency"] for x in detail["record"]["cash_balances"]} == {"USD", "EUR"}
    assert "total_value" not in detail["record"]


def test_missing_exact_fits_blocks_decision_card(tmp_path: Path) -> None:
    runtime, service, request = make_product_ui_runtime(tmp_path)
    decision = runtime.api.build_marginal_decision(request).result.decision
    persisted = runtime.product_store.execute(decision)
    with pytest.raises(ProductRecordIntegrityError, match="missing exact"):
        service.detail(persisted.envelope.record_id)


def test_service_read_only_and_intake_configuration_fail_closed(tmp_path: Path) -> None:
    runtime, _, request = make_product_ui_runtime(tmp_path)
    readonly = OperatorWorkspace(
        loader=LoadProductRecord(runtime.product_repository),
        lister=ListProductRecords(runtime.product_repository),
    )
    service = ProductUiService(readonly)
    for operation in (service.prepare, service.submit):
        with pytest.raises(WorkspaceWriteUnavailable):
            operation("not json")
    with pytest.raises(ValueError, match="intake requires"):
        ProductUiService(runtime.workspace, intake=runtime.intake)
    draft = UnderwritingDraft.model_validate(
        request.opportunity_state.model_dump(
            mode="python", exclude={"opportunity_id", "input_fingerprint", "source_documents"}
        )
    )
    payload = BuildOpportunityStateRequest(draft=draft).model_dump_json()
    without_intake = ProductUiService(runtime.workspace)
    for operation in (without_intake.prepare, without_intake.submit):
        with pytest.raises(WorkspaceWriteUnavailable):
            operation(payload)
    with pytest.raises(ValidationError):
        without_intake.prepare('{"operation":"execute_broker_trade"}')


@pytest.mark.parametrize(
    "extra",
    [
        {"HTTP_HOST": "attacker.test"},
        {"HTTP_HOST": "127.0.0.1.attacker.test"},
        {"HTTP_HOST": "attacker@127.0.0.1:8765"},
        {"HTTP_HOST": "127.0.0.1/path"},
        {"HTTP_ORIGIN": "http://attacker.test"},
        {"HTTP_ORIGIN": "http://127.0.0.1:9999"},
        {"HTTP_ORIGIN": "null"},
        {"HTTP_SEC_FETCH_SITE": "cross-site"},
        {"HTTP_SEC_FETCH_SITE": "same-site"},
    ],
)
def test_cross_origin_reads_cannot_expose_records_or_write_token(
    tmp_path: Path, extra: dict[str, str]
) -> None:
    _, service, _ = make_product_ui_runtime(tmp_path)
    app = ProductUiWsgiApp(service, frontend(tmp_path), write_token="secret-token")
    status, _, body = call(app, "/ui-api/session", extra=extra)
    assert status == "403 Forbidden"
    assert "secret-token" not in body


def test_http_json_routes_and_operator_remain_available(tmp_path: Path) -> None:
    _, service, _ = make_product_ui_runtime(tmp_path)
    app = ProductUiWsgiApp(service, frontend(tmp_path), write_token="local-token")
    status, headers, body = call(app, "/ui-api/session")
    assert status == "200 OK" and headers["Cache-Control"] == "no-store"
    assert json.loads(body)["contract_version"] == PRODUCT_UI_VERSION
    assert json.loads(body)["write_token"] == "local-token"
    status, _, body = call(app, "/ui-api/records")
    first = json.loads(body)["records"][0]
    assert status == "200 OK"
    status, _, body = call(app, "/ui-api/records/" + first["record_id"])
    assert status == "200 OK" and json.loads(body)["summary"]["record_id"] == first["record_id"]
    status, _, body = call(app, "/")
    assert status == "200 OK" and "Persisted canonical records" in body
    _require_local_origin(
        {
            "HTTP_HOST": "localhost:8765",
            "HTTP_ORIGIN": "http://localhost:8765",
            "HTTP_SEC_FETCH_SITE": "same-origin",
        }
    )


def test_http_commands_require_token_and_explicit_json(tmp_path: Path) -> None:
    _, service, request = make_product_ui_runtime(tmp_path)
    app = ProductUiWsgiApp(service, frontend(tmp_path), write_token="local-token")
    payload = request.model_dump_json().encode()
    assert call(app, "/ui-api/submit", method="POST", body=payload)[0] == "403 Forbidden"
    token = {"HTTP_X_AIE_WORKSPACE_TOKEN": "local-token"}
    status, _, body = call(app, "/ui-api/prepare", method="POST", body=payload, extra=token)
    assert status == "200 OK" and json.loads(body)["verification"] == "schema_only"
    assert call(app, "/ui-api/submit", method="POST", body=payload, extra=token)[0] == "201 Created"
    status, _, body = call(app, "/ui-api/prepare", method="POST", body=b"{}", extra=token)
    assert status == "400 Bad Request" and json.loads(body)["fields"]
    assert (
        call(
            app,
            "/ui-api/prepare",
            method="POST",
            body=payload,
            extra={**token, "CONTENT_TYPE": "text/plain"},
        )[0]
        == "409 Conflict"
    )
    assert (
        call(
            app,
            "/ui-api/prepare",
            method="POST",
            body=payload,
            extra={**token, "CONTENT_LENGTH": str(MAX_REQUEST_BYTES + 1)},
        )[0]
        == "409 Conflict"
    )


@pytest.mark.parametrize(
    "path, expected",
    [
        ("/ui-api/missing", "404 Not Found"),
        ("/ui-api/records/not-uuid", "409 Conflict"),
        ("/ui-api/records/" + str(uuid4()), "404 Not Found"),
        ("/app/missing", "404 Not Found"),
        ("/app/assets/missing.js", "404 Not Found"),
    ],
)
def test_routes_fail_explicitly(tmp_path: Path, path: str, expected: str) -> None:
    _, service, _ = make_product_ui_runtime(tmp_path)
    app = ProductUiWsgiApp(service, frontend(tmp_path), write_token="local-token")
    status, _, body = call(app, path)
    assert status == expected and json.loads(body)["blocking"] is True


def test_static_asset_boundary_and_csp(tmp_path: Path) -> None:
    _, service, _ = make_product_ui_runtime(tmp_path)
    dist = frontend(tmp_path)
    app = ProductUiWsgiApp(service, dist, write_token="local-token")
    status, headers, _ = call(app, "/app/")
    assert status == "200 OK"
    assert "script-src 'self'" in headers["Content-Security-Policy"]
    assert "unsafe-inline" not in headers["Content-Security-Policy"]
    assert headers["X-Frame-Options"] == "DENY"
    assert call(app, "/app/assets/app.js")[1]["Content-Type"].startswith("text/javascript")
    assert call(app, "/app/assets/app.css")[1]["Content-Type"].startswith("text/css")
    (tmp_path / "secret.js").write_text("secret")
    (dist / "assets" / "link.js").symlink_to(tmp_path / "secret.js")
    assert call(app, "/app/assets/../../secret.js")[0] == "403 Forbidden"
    assert call(app, "/app/assets/link.js")[0] == "403 Forbidden"
    (dist / "assets" / "private.json").write_text("{}")
    assert call(app, "/app/assets/private.json")[0] == "403 Forbidden"
    with pytest.raises(ValueError, match="write token"):
        ProductUiWsgiApp(service, dist)
    (dist / "index.html").unlink()
    with pytest.raises(ValueError, match="Build frontend"):
        ProductUiWsgiApp(service, dist, write_token="local-token")
    with pytest.raises(ValueError, match="port"):
        serve_product_ui(service, dist, port=0)


def test_ui_cli_requires_explicit_build_without_creating_databases(tmp_path: Path) -> None:
    assert (
        main(
            [
                "product",
                "ui",
                "--frontend-dist",
                str(tmp_path / "missing"),
                "--evidence-database",
                str(tmp_path / "evidence.sqlite"),
                "--product-database",
                str(tmp_path / "products.sqlite"),
            ]
        )
        == 2
    )
    assert not (tmp_path / "products.sqlite").exists()


def test_ui_cli_composes_real_services_with_selected_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, _, _ = make_product_ui_runtime(tmp_path)
    dist = frontend(tmp_path)
    captured: list[ProductUiService] = []

    def serve(service: ProductUiService, frontend_dist: Path, *, port: int) -> None:
        assert frontend_dist == dist and port == 8766
        assert service.intake is not None and service.store is not None
        captured.append(service)

    monkeypatch.setattr("asymmetric_engine.cli.serve_product_ui", serve)
    assert (
        main(
            [
                "product",
                "ui",
                "--frontend-dist",
                str(dist),
                "--port",
                "8766",
                "--evidence-database",
                str(runtime.paths.evidence_database),
                "--product-database",
                str(runtime.paths.product_database),
            ]
        )
        == 0
    )
    assert captured[0].workspace.list_records(ProductRecordKind.OPPORTUNITY_STATE)
