"""Unit tests for the evidence-to-underwriting causal domain contract."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from asymmetric_engine.domain.causal import (
    CausalAnalysisDraft,
    CausalEdgeKind,
    CausalNode,
    CausalNodeKind,
    CausalReadiness,
)
from asymmetric_engine.domain.evidence import (
    ClaimType,
    ConfidenceCalibrationStatus,
    EvidenceItem,
)
from asymmetric_engine.domain.temporal import KnowledgeBoundary, KnowledgeMode
from tests.causal_factories import RECORDED_AT, make_causal_draft, make_reference_sources


def rebuild(draft: CausalAnalysisDraft, **overrides: object) -> CausalAnalysisDraft:
    values = draft.model_dump(mode="python")
    values.update(overrides)
    return CausalAnalysisDraft.model_validate(values)


def test_reference_causal_path_is_ready_only_for_underwriting() -> None:
    draft = make_causal_draft()

    assert draft.readiness is CausalReadiness.READY_FOR_UNDERWRITING
    assert [node.kind for node in draft.nodes] == [
        CausalNodeKind.REAL_WORLD_CHANGE,
        CausalNodeKind.ECONOMIC_DRIVER,
        CausalNodeKind.SUPPLY_CHAIN_ACTOR,
        CausalNodeKind.BENEFICIARY,
    ]
    assert [edge.kind for edge in draft.edges] == [
        CausalEdgeKind.CHANGE_DRIVES_DRIVER,
        CausalEdgeKind.DRIVER_TRANSMITS_TO_ACTOR,
        CausalEdgeKind.ACTOR_MAPS_TO_BENEFICIARY,
    ]
    assert draft.missing_data
    assert draft.invalidation_conditions
    assert draft.readiness_rationale
    assert all(
        claim.confidence.calibration_status is ConfidenceCalibrationStatus.UNCALIBRATED
        for claim in draft.claims
    )
    change = draft.nodes[0]
    signal_claims = {
        claim.claim_id: claim for claim in draft.claims if claim.claim_id in change.claim_ids
    }
    assert {claim.claim_type for claim in signal_claims.values()} == {ClaimType.OBSERVATION}
    assert "portfolio" not in draft.model_dump_json().lower()


def test_evidence_source_link_is_all_or_nothing() -> None:
    draft = make_causal_draft()
    item = draft.evidence[0]
    values = item.model_dump(mode="python")
    values["source_locator"] = None

    with pytest.raises(ValidationError, match="must be provided together"):
        EvidenceItem.model_validate(values)


def test_node_identity_and_edge_reference_invariants() -> None:
    draft = make_causal_draft()

    with pytest.raises(ValidationError, match="beneficiary requires"):
        CausalNode(
            node_id="beneficiary:unknown",
            kind=CausalNodeKind.BENEFICIARY,
            label="Unknown beneficiary",
            claim_ids=(draft.claims[0].claim_id,),
        )
    with pytest.raises(ValidationError, match="only beneficiary"):
        CausalNode(
            node_id="driver:incorrect-subject",
            kind=CausalNodeKind.ECONOMIC_DRIVER,
            label="Incorrectly identified driver",
            subject_id="company:test",
            claim_ids=(draft.claims[0].claim_id,),
        )

    duplicated_claim_node = draft.nodes[0].model_copy(
        update={"claim_ids": (draft.nodes[0].claim_ids[0],) * 2}
    )
    with pytest.raises(ValidationError, match="duplicate claim_ids"):
        duplicated_claim_node.__class__.model_validate(
            duplicated_claim_node.model_dump(mode="python")
        )

    duplicated_claim_edge = draft.edges[0].model_copy(
        update={"claim_ids": (draft.edges[0].claim_ids[0],) * 2}
    )
    with pytest.raises(ValidationError, match="duplicate claim_ids"):
        duplicated_claim_edge.__class__.model_validate(
            duplicated_claim_edge.model_dump(mode="python")
        )

    self_edge = draft.edges[0].model_copy(update={"target_node_id": draft.edges[0].source_node_id})
    with pytest.raises(ValidationError, match="same node"):
        self_edge.__class__.model_validate(self_edge.model_dump(mode="python"))


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("source_document_ids", "duplicate source_document_ids"),
        ("nodes", "duplicate node_ids"),
        ("edges", "duplicate edge_ids"),
        ("evidence", "duplicate evidence_ids"),
        ("claims", "duplicate claim_ids"),
    ],
)
def test_analysis_rejects_duplicate_material_objects(field: str, message: str) -> None:
    draft = make_causal_draft()
    values = draft.model_dump(mode="python")
    records = values[field]
    values[field] = (*records, records[0])

    with pytest.raises(ValidationError, match=message):
        CausalAnalysisDraft.model_validate(values)


@pytest.mark.parametrize("field", ["invalidation_conditions", "missing_data", "assumptions"])
def test_analysis_rejects_duplicate_disclosures(field: str) -> None:
    draft = make_causal_draft()
    values = draft.model_dump(mode="python")
    records = values[field]
    values[field] = (*records, records[0])

    with pytest.raises(ValidationError, match="duplicate disclosure"):
        CausalAnalysisDraft.model_validate(values)


def test_analysis_requires_every_evidence_item_to_link_to_a_declared_document() -> None:
    draft = make_causal_draft()
    unlinked = draft.evidence[0].model_copy(
        update={
            "source_document_id": None,
            "source_locator": None,
            "extraction_method": None,
        }
    )
    with pytest.raises(ValidationError, match="must link to an immutable"):
        rebuild(draft, evidence=(unlinked, *draft.evidence[1:]))

    undeclared = draft.evidence[0].model_copy(update={"source_document_id": uuid4()})
    with pytest.raises(ValidationError, match="undeclared source"):
        rebuild(draft, evidence=(undeclared, *draft.evidence[1:]))


@pytest.mark.parametrize(
    ("knowledge_mode", "available_delta", "recorded_delta", "message"),
    [
        (
            KnowledgeMode.HISTORICAL_RECONSTRUCTION,
            timedelta(hours=1),
            timedelta(hours=1),
            "source_not_available",
        ),
        (
            KnowledgeMode.LIVE_SYSTEM_REPLAY,
            timedelta(hours=-1),
            timedelta(hours=1),
            "record_not_ingested",
        ),
    ],
)
def test_analysis_rejects_evidence_outside_the_knowledge_boundary(
    knowledge_mode: KnowledgeMode,
    available_delta: timedelta,
    recorded_delta: timedelta,
    message: str,
) -> None:
    draft = make_causal_draft()
    as_of = RECORDED_AT
    shifted = tuple(
        item.model_copy(
            update={
                "available_at": as_of + available_delta,
                "recorded_at": as_of + recorded_delta,
            }
        )
        for item in draft.evidence
    )
    boundary = KnowledgeBoundary(as_of=as_of, knowledge_mode=knowledge_mode)

    with pytest.raises(ValidationError, match=message):
        rebuild(draft, evidence=shifted, knowledge_boundary=boundary)


def test_historical_reconstruction_allows_later_system_ingestion() -> None:
    draft = make_causal_draft()
    as_of = RECORDED_AT
    shifted = tuple(
        item.model_copy(
            update={
                "available_at": as_of - timedelta(hours=1),
                "recorded_at": as_of + timedelta(hours=1),
            }
        )
        for item in draft.evidence
    )

    rebuilt = rebuild(
        draft,
        evidence=shifted,
        knowledge_boundary=KnowledgeBoundary(
            as_of=as_of,
            knowledge_mode=KnowledgeMode.HISTORICAL_RECONSTRUCTION,
        ),
    )

    assert rebuilt.evidence == shifted


def test_claim_lineage_rejects_unknown_and_unused_evidence() -> None:
    draft = make_causal_draft()
    unknown = draft.claims[0].model_copy(update={"evidence_ids": (uuid4(),)})
    with pytest.raises(ValidationError, match="unknown evidence_ids"):
        rebuild(draft, claims=(unknown, *draft.claims[1:]))

    unused = draft.evidence[0].model_copy(update={"evidence_id": uuid4()})
    with pytest.raises(ValidationError, match="every evidence item"):
        rebuild(draft, evidence=(*draft.evidence, unused))


def test_edge_lineage_rejects_unknown_nodes_claims_and_wrong_roles() -> None:
    draft = make_causal_draft()
    unknown_node = draft.edges[0].model_copy(update={"source_node_id": "change:missing"})
    with pytest.raises(ValidationError, match="unknown node"):
        rebuild(draft, edges=(unknown_node, *draft.edges[1:]))

    unknown_claim = draft.edges[0].model_copy(update={"claim_ids": (uuid4(),)})
    with pytest.raises(ValidationError, match="unknown claim_ids"):
        rebuild(draft, edges=(unknown_claim, *draft.edges[1:]))

    wrong_roles = draft.edges[0].model_copy(
        update={"kind": CausalEdgeKind.DRIVER_TRANSMITS_TO_ACTOR}
    )
    with pytest.raises(ValidationError, match="typed causal roles"):
        rebuild(draft, edges=(wrong_roles, *draft.edges[1:]))


def test_edge_requires_inferential_support_and_no_claim_can_dangle() -> None:
    draft = make_causal_draft()
    edge_claim_id = draft.edges[0].claim_ids[0]
    observation = next(
        claim for claim in draft.claims if claim.claim_id == edge_claim_id
    ).model_copy(update={"claim_type": ClaimType.OBSERVATION})
    changed_claims = tuple(
        observation if claim.claim_id == edge_claim_id else claim for claim in draft.claims
    )
    with pytest.raises(ValidationError, match="inference or hypothesis"):
        rebuild(draft, claims=changed_claims)

    unused_claim = draft.claims[0].model_copy(update={"claim_id": uuid4()})
    with pytest.raises(ValidationError, match="every claim"):
        rebuild(draft, claims=(*draft.claims, unused_claim))


def test_real_world_change_requires_a_separate_observed_signal_claim() -> None:
    draft = make_causal_draft()
    inference_claim_id = draft.edges[0].claim_ids[0]
    unsupported_change = draft.nodes[0].model_copy(update={"claim_ids": (inference_claim_id,)})

    with pytest.raises(ValidationError, match="observed or statistical signal"):
        rebuild(draft, nodes=(unsupported_change, *draft.nodes[1:]))

    unknown_signal = draft.nodes[0].model_copy(update={"claim_ids": (uuid4(),)})
    with pytest.raises(ValidationError, match="unknown claim_ids"):
        rebuild(draft, nodes=(unknown_signal, *draft.nodes[1:]))


def test_every_node_and_source_document_must_participate() -> None:
    draft = make_causal_draft()
    unused_node = CausalNode(
        node_id="driver:unused",
        kind=CausalNodeKind.ECONOMIC_DRIVER,
        label="Unused driver",
        claim_ids=(draft.claims[0].claim_id,),
    )
    with pytest.raises(ValidationError, match="every node"):
        rebuild(draft, nodes=(*draft.nodes, unused_node))

    with pytest.raises(ValidationError, match="every declared source"):
        rebuild(draft, source_document_ids=(*draft.source_document_ids, uuid4()))


def test_ready_for_underwriting_requires_one_connected_complete_path() -> None:
    draft = make_causal_draft()
    disconnected_driver = CausalNode(
        node_id="driver:disconnected",
        kind=CausalNodeKind.ECONOMIC_DRIVER,
        label="Disconnected driver",
        claim_ids=(draft.nodes[1].claim_ids[0],),
    )
    disconnected_edge = draft.edges[1].model_copy(
        update={"source_node_id": disconnected_driver.node_id}
    )

    with pytest.raises(ValidationError, match="complete change-to-beneficiary"):
        rebuild(
            draft,
            nodes=(*draft.nodes, disconnected_driver),
            edges=(draft.edges[0], disconnected_edge, draft.edges[2]),
        )


def test_readiness_states_require_honest_disclosures() -> None:
    draft = make_causal_draft()

    with pytest.raises(ValidationError, match="explicit missing_data"):
        rebuild(
            draft,
            readiness=CausalReadiness.INSUFFICIENT_EVIDENCE,
            missing_data=(),
        )
    with pytest.raises(ValidationError, match="requires invalidation_reason"):
        rebuild(draft, readiness=CausalReadiness.INVALIDATED)
    with pytest.raises(ValidationError, match="allowed only"):
        rebuild(draft, invalidation_reason="A reason on a non-invalidated case.")

    invalidated = rebuild(
        draft,
        readiness=CausalReadiness.INVALIDATED,
        invalidation_reason="Micron did not qualify its HBM product.",
    )
    assert invalidated.readiness is CausalReadiness.INVALIDATED


def test_reference_sources_use_real_sec_identifiers_but_synthetic_bytes() -> None:
    documents, content = make_reference_sources()

    assert {document.provider_version for document in documents} == {
        "0001045810-24-000029",
        "0000723125-24-000027",
    }
    assert all(b"SYNTHETIC TEST FIXTURE" in content[document.document_id] for document in documents)
    assert {document.subject_id for document in documents} == {
        "company:sec-cik-0001045810",
        "company:sec-cik-0000723125",
    }
