"""Evidence-domain invariant tests."""

from datetime import timedelta

import pytest
from pydantic import ValidationError

from asymmetric_engine.domain.evidence import (
    Claim,
    ClaimType,
    Confidence,
    ConfidenceCalibrationStatus,
    DataQuality,
)
from asymmetric_engine.domain.temporal import KnowledgeBoundary, KnowledgeMode
from tests.factories import BASE_TIME, make_evidence


def test_evidence_rejects_recording_before_availability() -> None:
    with pytest.raises(ValidationError, match="recorded_at"):
        make_evidence(recorded_at=BASE_TIME - timedelta(seconds=1))


def test_evidence_requires_timezone_aware_timestamps() -> None:
    with pytest.raises(ValidationError):
        make_evidence(available_at=BASE_TIME.replace(tzinfo=None))


def test_data_quality_rejects_duplicate_missing_fields() -> None:
    with pytest.raises(ValidationError, match="duplicate"):
        DataQuality(
            coverage=0.5,
            source_reliability=0.5,
            point_in_time_integrity=0.5,
            missing_fields=("revenue", "revenue"),
        )


def test_claim_requires_explicit_evidence() -> None:
    with pytest.raises(ValidationError, match="at least one"):
        Claim(
            text="An unsupported material claim.",
            claim_type=ClaimType.HYPOTHESIS,
            evidence_ids=(),
            confidence=Confidence(score=0.2, rationale="Preliminary idea."),
            invalidation_condition="Contradictory primary evidence appears.",
        )


def test_claim_rejects_duplicate_evidence_references() -> None:
    evidence = make_evidence()
    with pytest.raises(ValidationError, match="duplicate"):
        Claim(
            text="The same source must not count twice.",
            claim_type=ClaimType.OBSERVATION,
            evidence_ids=(evidence.evidence_id, evidence.evidence_id),
            confidence=Confidence(score=0.9, rationale="Single primary source."),
            invalidation_condition="The primary source is corrected.",
        )


def test_calibrated_confidence_requires_an_identifiable_method() -> None:
    with pytest.raises(ValidationError, match="requires method_version"):
        Confidence(
            score=0.8,
            rationale="A calibration claim without an identifiable method.",
            calibration_status=ConfidenceCalibrationStatus.CALIBRATED,
        )

    calibrated = Confidence(
        score=0.8,
        rationale="Validated on a declared out-of-sample calibration set.",
        calibration_status=ConfidenceCalibrationStatus.CALIBRATED,
        method_version="claim-confidence-v1",
    )
    assert calibrated.method_version == "claim-confidence-v1"


def test_evidence_uses_the_shared_knowledge_boundary() -> None:
    evidence = make_evidence(
        available_at=BASE_TIME - timedelta(days=1),
        recorded_at=BASE_TIME + timedelta(days=1),
    )

    reconstruction = KnowledgeBoundary(
        as_of=BASE_TIME,
        knowledge_mode=KnowledgeMode.HISTORICAL_RECONSTRUCTION,
    )
    replay = KnowledgeBoundary(
        as_of=BASE_TIME,
        knowledge_mode=KnowledgeMode.LIVE_SYSTEM_REPLAY,
    )

    assert evidence.is_knowable_at(reconstruction)
    assert not evidence.is_knowable_at(replay)
