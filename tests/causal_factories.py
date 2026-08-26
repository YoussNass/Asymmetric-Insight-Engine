"""Deterministic causal-analysis fixtures with real SEC identities and synthetic content."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from uuid import NAMESPACE_URL, UUID, uuid5

from asymmetric_engine.domain.causal import (
    CausalAnalysisDraft,
    CausalEdge,
    CausalEdgeKind,
    CausalNode,
    CausalNodeKind,
    CausalReadiness,
)
from asymmetric_engine.domain.evidence import (
    Claim,
    ClaimType,
    Confidence,
    ConfidenceCalibrationStatus,
    DataQuality,
    EvidenceItem,
    SourceDocument,
    SourceDocumentDraft,
    SourceType,
)
from asymmetric_engine.domain.temporal import KnowledgeBoundary, KnowledgeMode
from asymmetric_engine.infrastructure.providers.sec_edgar import SecEdgarProvider

NVIDIA_REFERENCE = "0001045810/0001045810-24-000029"
MICRON_REFERENCE = "0000723125/0000723125-24-000027"
RECORDED_AT = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)
ANALYSIS_AS_OF = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)

NVIDIA_CONTENT = b"""<SEC-DOCUMENT>
<ACCESSION-NUMBER>0001045810-24-000029
<CONFORMED-SUBMISSION-TYPE>10-K
<CONFORMED-PERIOD-OF-REPORT>20240128
<FILER><COMPANY-DATA>
<COMPANY-CONFORMED-NAME>NVIDIA CORP
<CENTRAL-INDEX-KEY>0001045810
</COMPANY-DATA></FILER>
<DOCUMENT>
AIE SYNTHETIC TEST FIXTURE, NOT AN SEC FILING COPY.
NVIDIA reported fiscal 2024 Data Center revenue increased 217% year over year as demand
for AI infrastructure expanded.
</DOCUMENT>
</SEC-DOCUMENT>"""

MICRON_CONTENT = b"""<SEC-DOCUMENT>
<ACCESSION-NUMBER>0000723125-24-000027
<CONFORMED-SUBMISSION-TYPE>10-K
<CONFORMED-PERIOD-OF-REPORT>20240829
<FILER><COMPANY-DATA>
<COMPANY-CONFORMED-NAME>MICRON TECHNOLOGY INC
<CENTRAL-INDEX-KEY>0000723125
</COMPANY-DATA></FILER>
<DOCUMENT>
AIE SYNTHETIC TEST FIXTURE, NOT AN SEC FILING COPY.
AI servers require increasing memory bandwidth and content. HBM3E volume production began.
</DOCUMENT>
</SEC-DOCUMENT>"""

NVIDIA_EVIDENCE_ID = UUID("11111111-1111-4111-8111-111111111111")
MEMORY_DEMAND_EVIDENCE_ID = UUID("22222222-2222-4222-8222-222222222222")
MICRON_HBM_EVIDENCE_ID = UUID("33333333-3333-4333-8333-333333333333")
AI_DEMAND_OBSERVATION_CLAIM_ID = UUID("10101010-1010-4010-8010-101010101010")
MEMORY_REQUIREMENT_OBSERVATION_CLAIM_ID = UUID("20202020-2020-4020-8020-202020202020")
HBM_PRODUCTION_OBSERVATION_CLAIM_ID = UUID("30303030-3030-4030-8030-303030303030")
AI_CHANGE_CLAIM_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
MEMORY_DRIVER_CLAIM_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
MICRON_BENEFICIARY_CLAIM_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")


def _sec_draft(reference: str, content: bytes) -> SourceDocumentDraft:
    return SecEdgarProvider(lambda _: content).fetch(reference)


def _source_document(draft: SourceDocumentDraft) -> SourceDocument:
    identity = json.dumps(
        (draft.provider, draft.provider_record_id, draft.provider_version),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return SourceDocument(
        document_id=uuid5(NAMESPACE_URL, identity),
        provider=draft.provider,
        provider_record_id=draft.provider_record_id,
        provider_version=draft.provider_version,
        subject_id=draft.subject_id,
        title=draft.title,
        source_uri=draft.source_uri,
        source_type=draft.source_type,
        effective_at=draft.effective_at,
        availability_basis=draft.availability_basis,
        available_at=RECORDED_AT,
        recorded_at=RECORDED_AT,
        media_type=draft.media_type,
        content_hash=sha256(draft.content).hexdigest(),
        content_size_bytes=len(draft.content),
    )


def make_reference_sources() -> tuple[
    tuple[SourceDocument, SourceDocument],
    dict[UUID, bytes],
]:
    nvidia = _source_document(_sec_draft(NVIDIA_REFERENCE, NVIDIA_CONTENT))
    micron = _source_document(_sec_draft(MICRON_REFERENCE, MICRON_CONTENT))
    return (nvidia, micron), {
        nvidia.document_id: NVIDIA_CONTENT,
        micron.document_id: MICRON_CONTENT,
    }


def _linked_evidence(
    *,
    evidence_id: UUID,
    document: SourceDocument,
    title: str,
    locator: str,
) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=evidence_id,
        title=title,
        source_uri=document.source_uri,
        source_type=SourceType.FILING,
        effective_at=document.effective_at,
        available_at=document.available_at,
        recorded_at=document.recorded_at,
        content_hash=document.content_hash,
        quality=DataQuality(
            coverage=0.8,
            source_reliability=0.85,
            point_in_time_integrity=1.0,
            missing_fields=("Independent third-party confirmation",),
        ),
        source_document_id=document.document_id,
        source_locator=locator,
        extraction_method="deterministic manual fixture extraction",
    )


def _uncalibrated_confidence(*, score: float, rationale: str) -> Confidence:
    return Confidence(
        score=score,
        rationale=rationale,
        calibration_status=ConfidenceCalibrationStatus.UNCALIBRATED,
        method_version="manual-epistemic-v1",
    )


def make_causal_draft(
    *,
    documents: tuple[SourceDocument, SourceDocument] | None = None,
    boundary: KnowledgeBoundary | None = None,
    readiness: CausalReadiness = CausalReadiness.READY_FOR_UNDERWRITING,
) -> CausalAnalysisDraft:
    if documents is None:
        documents, _ = make_reference_sources()
    by_subject = {document.subject_id: document for document in documents}
    nvidia = by_subject["company:sec-cik-0001045810"]
    micron = by_subject["company:sec-cik-0000723125"]

    nvidia_evidence = _linked_evidence(
        evidence_id=NVIDIA_EVIDENCE_ID,
        document=nvidia,
        title="Issuer-reported expansion in AI infrastructure demand",
        locator="synthetic fixture: AI infrastructure demand sentence",
    )
    memory_evidence = _linked_evidence(
        evidence_id=MEMORY_DEMAND_EVIDENCE_ID,
        document=micron,
        title="Issuer-reported AI-server memory requirements",
        locator="synthetic fixture: memory bandwidth sentence",
    )
    hbm_evidence = _linked_evidence(
        evidence_id=MICRON_HBM_EVIDENCE_ID,
        document=micron,
        title="Issuer-reported HBM3E production status",
        locator="synthetic fixture: HBM3E production sentence",
    )
    claims = (
        Claim(
            claim_id=AI_DEMAND_OBSERVATION_CLAIM_ID,
            text="NVIDIA reported that fiscal 2024 Data Center revenue increased 217%.",
            claim_type=ClaimType.OBSERVATION,
            evidence_ids=(nvidia_evidence.evidence_id,),
            confidence=_uncalibrated_confidence(
                score=0.9,
                rationale=(
                    "Direct issuer disclosure; the annotation is not an empirical probability."
                ),
            ),
            invalidation_condition="NVIDIA amends or restates the reported Data Center growth.",
        ),
        Claim(
            claim_id=MEMORY_REQUIREMENT_OBSERVATION_CLAIM_ID,
            text="Micron reported that AI cloud servers require increasing DRAM, including HBM.",
            claim_type=ClaimType.OBSERVATION,
            evidence_ids=(memory_evidence.evidence_id,),
            confidence=_uncalibrated_confidence(
                score=0.9,
                rationale=(
                    "Direct issuer disclosure; independent demand confirmation remains missing."
                ),
            ),
            invalidation_condition="Micron corrects the disclosed AI-server memory requirement.",
        ),
        Claim(
            claim_id=HBM_PRODUCTION_OBSERVATION_CLAIM_ID,
            text="Micron reported beginning volume production of 8-high 24GB HBM3E in 2024.",
            claim_type=ClaimType.OBSERVATION,
            evidence_ids=(hbm_evidence.evidence_id,),
            confidence=_uncalibrated_confidence(
                score=0.9,
                rationale="Direct issuer disclosure; production economics are not established.",
            ),
            invalidation_condition="Micron corrects or withdraws the production disclosure.",
        ),
        Claim(
            claim_id=AI_CHANGE_CLAIM_ID,
            text="Expanding AI data-centre deployment is increasing AI infrastructure demand.",
            claim_type=ClaimType.INFERENCE,
            evidence_ids=(nvidia_evidence.evidence_id, memory_evidence.evidence_id),
            confidence=_uncalibrated_confidence(
                score=0.7,
                rationale=(
                    "The direction is supported by an issuer filing, but not independently "
                    "verified."
                ),
            ),
            invalidation_condition=(
                "AI deployment growth stops translating into infrastructure demand."
            ),
        ),
        Claim(
            claim_id=MEMORY_DRIVER_CLAIM_ID,
            text="More AI-server deployment increases demand for memory bandwidth and HBM supply.",
            claim_type=ClaimType.INFERENCE,
            evidence_ids=(nvidia_evidence.evidence_id, memory_evidence.evidence_id),
            confidence=_uncalibrated_confidence(
                score=0.7,
                rationale=(
                    "Two issuer disclosures support the mechanism; market-wide data is missing."
                ),
            ),
            invalidation_condition=(
                "AI-server growth no longer raises HBM content or bandwidth demand."
            ),
        ),
        Claim(
            claim_id=MICRON_BENEFICIARY_CLAIM_ID,
            text=(
                "Micron is a candidate HBM beneficiary because it reported HBM3E volume production."
            ),
            claim_type=ClaimType.HYPOTHESIS,
            evidence_ids=(hbm_evidence.evidence_id,),
            confidence=_uncalibrated_confidence(
                score=0.6,
                rationale="Production status supports eligibility, not profitable value capture.",
            ),
            invalidation_condition="Micron fails qualification, ramp, share, or economic capture.",
        ),
    )
    return CausalAnalysisDraft(
        case_id="ai-hbm-micron",
        title="AI infrastructure demand to Micron HBM beneficiary hypothesis",
        knowledge_boundary=boundary
        or KnowledgeBoundary(
            as_of=ANALYSIS_AS_OF,
            knowledge_mode=KnowledgeMode.LIVE_SYSTEM_REPLAY,
        ),
        method_version="causal-vertical-slice-v1",
        readiness=readiness,
        readiness_rationale=(
            "The observed signal and all three causal transitions are evidence-backed, typed, "
            "and falsifiable; unresolved economics remain explicit for Underwriting."
        ),
        source_document_ids=tuple(document.document_id for document in documents),
        nodes=(
            CausalNode(
                node_id="change:ai-data-centre-expansion",
                kind=CausalNodeKind.REAL_WORLD_CHANGE,
                label="Expansion of AI data-centre deployment",
                claim_ids=(AI_DEMAND_OBSERVATION_CLAIM_ID,),
            ),
            CausalNode(
                node_id="driver:memory-bandwidth-demand",
                kind=CausalNodeKind.ECONOMIC_DRIVER,
                label="Rising memory bandwidth and content per AI server",
                claim_ids=(MEMORY_REQUIREMENT_OBSERVATION_CLAIM_ID,),
            ),
            CausalNode(
                node_id="actor:hbm-supply",
                kind=CausalNodeKind.SUPPLY_CHAIN_ACTOR,
                label="High-bandwidth-memory supply",
                claim_ids=(
                    MEMORY_REQUIREMENT_OBSERVATION_CLAIM_ID,
                    HBM_PRODUCTION_OBSERVATION_CLAIM_ID,
                ),
            ),
            CausalNode(
                node_id="beneficiary:micron",
                kind=CausalNodeKind.BENEFICIARY,
                label="Micron Technology",
                subject_id="company:sec-cik-0000723125",
                claim_ids=(HBM_PRODUCTION_OBSERVATION_CLAIM_ID,),
            ),
        ),
        edges=(
            CausalEdge(
                edge_id="edge:ai-change-to-memory-driver",
                kind=CausalEdgeKind.CHANGE_DRIVES_DRIVER,
                source_node_id="change:ai-data-centre-expansion",
                target_node_id="driver:memory-bandwidth-demand",
                mechanism="More AI compute deployment expands infrastructure requirements.",
                claim_ids=(AI_CHANGE_CLAIM_ID,),
            ),
            CausalEdge(
                edge_id="edge:memory-driver-to-hbm",
                kind=CausalEdgeKind.DRIVER_TRANSMITS_TO_ACTOR,
                source_node_id="driver:memory-bandwidth-demand",
                target_node_id="actor:hbm-supply",
                mechanism="Higher bandwidth and memory content transmit demand to HBM suppliers.",
                claim_ids=(MEMORY_DRIVER_CLAIM_ID,),
            ),
            CausalEdge(
                edge_id="edge:hbm-to-micron",
                kind=CausalEdgeKind.ACTOR_MAPS_TO_BENEFICIARY,
                source_node_id="actor:hbm-supply",
                target_node_id="beneficiary:micron",
                mechanism="A qualified HBM producer may capture part of incremental HBM demand.",
                claim_ids=(MICRON_BENEFICIARY_CLAIM_ID,),
            ),
        ),
        evidence=(nvidia_evidence, memory_evidence, hbm_evidence),
        claims=claims,
        invalidation_conditions=(
            "AI infrastructure deployment slows materially.",
            "HBM supply growth persistently exceeds end demand.",
            "Micron cannot qualify, ramp, or economically capture HBM demand.",
        ),
        missing_data=(
            "Independent market-wide HBM supply-and-demand evidence.",
            "Micron HBM pricing, cost, share, and margin evidence.",
            "Valuation and per-share impact, reserved for Underwriting.",
            "Empirical calibration data for claim confidence annotations.",
        ),
        assumptions=(
            "Issuer filings accurately describe product demand and production status.",
            "AI-server memory architecture does not change before Underwriting review.",
        ),
    )
