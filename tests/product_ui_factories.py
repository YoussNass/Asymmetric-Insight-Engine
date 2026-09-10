"""Deterministic reference dossiers over the real local runtime; never market advice."""

from pathlib import Path

from asymmetric_engine.interfaces.api import BuildMarginalDecisionRequest
from asymmetric_engine.interfaces.product_ui import ProductUiService
from asymmetric_engine.product_runtime import (
    LocalProductPaths,
    LocalProductRuntime,
    build_local_product_runtime,
    initialize_local_product_stores,
)
from tests.causal_factories import make_reference_sources
from tests.decision_factories import make_decision_context
from tests.underwriting_factories import make_underwriting_sources


def make_product_ui_runtime(
    directory: Path,
) -> tuple[LocalProductRuntime, ProductUiService, BuildMarginalDecisionRequest]:
    paths = LocalProductPaths(directory / "evidence.sqlite", directory / "products.sqlite")
    initialize_local_product_stores(paths)
    runtime = build_local_product_runtime(paths)
    for documents, contents in (make_reference_sources(), make_underwriting_sources()):
        for document in documents:
            runtime.evidence_repository.append(document, contents[document.document_id])
    context = make_decision_context()
    for record in (
        context.opportunity_state.causal_analysis,
        context.opportunity_state,
        context.portfolio_state,
        context.current_exposure,
        *context.alternative_exposures,
    ):
        runtime.product_store.execute(record)
    request = BuildMarginalDecisionRequest(
        portfolio_state=context.portfolio_state,
        opportunity_state=context.opportunity_state,
        current_exposure=context.current_exposure,
        alternative_exposures=context.alternative_exposures,
        decision_input=context.decision_input,
    )
    service = ProductUiService(
        runtime.workspace, intake=runtime.intake, store=runtime.product_store
    )
    return runtime, service, request
