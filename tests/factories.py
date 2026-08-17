"""Deterministic test factories."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from asymmetric_engine.domain.evidence import (
    Claim,
    ClaimType,
    Confidence,
    DataQuality,
    EvidenceItem,
    SourceType,
)

BASE_TIME = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)


def make_evidence(
    *,
    evidence_id: UUID | None = None,
    available_at: datetime = BASE_TIME,
    recorded_at: datetime | None = None,
) -> EvidenceItem:
    values: dict[str, object] = {
        "title": "Quarterly filing",
        "source_uri": "https://example.test/filing",
        "source_type": SourceType.FILING,
        "effective_at": available_at - timedelta(days=30),
        "available_at": available_at,
        "recorded_at": recorded_at or available_at,
        "content_hash": "a" * 64,
        "quality": DataQuality(
            coverage=0.9,
            source_reliability=1.0,
            point_in_time_integrity=1.0,
        ),
    }
    if evidence_id is not None:
        values["evidence_id"] = evidence_id
    return EvidenceItem.model_validate(values)


def make_claim(evidence: EvidenceItem) -> Claim:
    return Claim(
        text="Published capacity increased compared with the prior period.",
        claim_type=ClaimType.OBSERVATION,
        evidence_ids=(evidence.evidence_id,),
        confidence=Confidence(score=0.9, rationale="Directly disclosed in a filing."),
        invalidation_condition="The filing is amended or the capacity definition changes.",
    )
