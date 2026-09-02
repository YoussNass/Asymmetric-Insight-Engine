"""End-to-end prospective operation over evidence, intake, API, persistence, and workspace."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from asymmetric_engine.application.product_persistence import ProductRecordKind
from asymmetric_engine.domain.evidence import SourceDocument
from asymmetric_engine.interfaces.api import BuildPortfolioStateRequest
from asymmetric_engine.interfaces.prospective_intake import (
    BuildCausalAnalysisRequest,
    BuildOpportunityStateRequest,
)
from asymmetric_engine.product_runtime import (
    LocalProductPaths,
    LocalProductRuntime,
    build_local_product_runtime,
    initialize_local_product_stores,
)
from tests.causal_factories import make_causal_draft, make_reference_sources
from tests.portfolio_factories import make_portfolio_draft
from tests.underwriting_factories import make_underwriting_draft, make_underwriting_sources


def _append_sources(
    runtime: LocalProductRuntime,
    documents: tuple[SourceDocument, ...],
    contents: dict[UUID, bytes],
) -> None:
    for document in documents:
        runtime.evidence_repository.append(document, contents[document.document_id])


def test_local_runtime_connects_upstream_intake_to_downstream_workspace(tmp_path: Path) -> None:
    paths = LocalProductPaths(
        evidence_database=tmp_path / "evidence.sqlite",
        product_database=tmp_path / "products.sqlite",
    )
    initialize_local_product_stores(paths)
    runtime = build_local_product_runtime(paths)
    assert runtime.workspace.write_enabled is True

    causal_documents, causal_contents = make_reference_sources()
    _append_sources(runtime, causal_documents, causal_contents)
    causal_submission = runtime.submit_intake(
        BuildCausalAnalysisRequest(draft=make_causal_draft(documents=causal_documents))
    )
    assert causal_submission.persisted.envelope.kind is ProductRecordKind.CAUSAL_ANALYSIS
    assert causal_submission.persisted.envelope.payload_json == (
        runtime.product_repository.get(causal_submission.persisted.envelope.record_id).payload_json
    )

    underwriting_documents, underwriting_contents = make_underwriting_sources()
    _append_sources(runtime, underwriting_documents, underwriting_contents)
    underwriting_draft = make_underwriting_draft(
        causal_analysis=causal_submission.response.result,
        documents=underwriting_documents,
    )
    opportunity_submission = runtime.submit_intake(
        BuildOpportunityStateRequest(draft=underwriting_draft)
    )
    assert opportunity_submission.persisted.envelope.kind is ProductRecordKind.OPPORTUNITY_STATE

    portfolio_request = BuildPortfolioStateRequest(draft=make_portfolio_draft())
    direct = runtime.api.build_portfolio_state(portfolio_request)
    workspace_submission = runtime.workspace.submit(portfolio_request)
    assert workspace_submission.response == direct
    assert len(workspace_submission.persisted) == 1
    assert workspace_submission.persisted[0].envelope.kind is ProductRecordKind.PORTFOLIO_STATE

    kinds = {summary.kind for summary in runtime.workspace.list_records()}
    assert ProductRecordKind.CAUSAL_ANALYSIS in kinds
    assert ProductRecordKind.OPPORTUNITY_STATE in kinds
    assert ProductRecordKind.PORTFOLIO_STATE in kinds


def test_runtime_construction_fails_closed_when_stores_are_missing(tmp_path: Path) -> None:
    paths = LocalProductPaths(
        evidence_database=tmp_path / "missing-evidence.sqlite",
        product_database=tmp_path / "missing-products.sqlite",
    )

    try:
        build_local_product_runtime(paths)
    except FileNotFoundError:
        pass
    else:  # pragma: no cover - failure diagnostic
        raise AssertionError("runtime must reject missing durable stores")

    assert not paths.evidence_database.exists()
    assert not paths.product_database.exists()
