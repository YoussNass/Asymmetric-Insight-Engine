"""Cross-domain temporal-boundary invariant tests."""

from datetime import timedelta

import pytest
from pydantic import ValidationError

from asymmetric_engine.domain.temporal import (
    KnowledgeBoundary,
    KnowledgeExclusionReason,
    KnowledgeMode,
)
from tests.factories import BASE_TIME


def make_boundary(mode: KnowledgeMode) -> KnowledgeBoundary:
    return KnowledgeBoundary(as_of=BASE_TIME, knowledge_mode=mode)


def test_boundary_requires_timezone_aware_as_of() -> None:
    with pytest.raises(ValidationError):
        KnowledgeBoundary(
            as_of=BASE_TIME.replace(tzinfo=None),
            knowledge_mode=KnowledgeMode.HISTORICAL_RECONSTRUCTION,
        )


def test_both_modes_exclude_sources_available_after_as_of() -> None:
    for mode in KnowledgeMode:
        reason = make_boundary(mode).exclusion_reason(
            available_at=BASE_TIME + timedelta(seconds=1),
            recorded_at=BASE_TIME + timedelta(seconds=1),
        )

        assert reason is KnowledgeExclusionReason.SOURCE_NOT_AVAILABLE


def test_reconstruction_accepts_a_record_ingested_later() -> None:
    boundary = make_boundary(KnowledgeMode.HISTORICAL_RECONSTRUCTION)

    assert boundary.includes(
        available_at=BASE_TIME - timedelta(days=1),
        recorded_at=BASE_TIME + timedelta(days=1),
    )


def test_live_replay_excludes_a_record_ingested_later() -> None:
    boundary = make_boundary(KnowledgeMode.LIVE_SYSTEM_REPLAY)

    reason = boundary.exclusion_reason(
        available_at=BASE_TIME - timedelta(days=1),
        recorded_at=BASE_TIME + timedelta(days=1),
    )

    assert reason is KnowledgeExclusionReason.RECORD_NOT_INGESTED


def test_boundary_rejects_inconsistent_or_naive_record_timestamps() -> None:
    boundary = make_boundary(KnowledgeMode.HISTORICAL_RECONSTRUCTION)

    with pytest.raises(ValueError, match="recorded_at"):
        boundary.includes(
            available_at=BASE_TIME,
            recorded_at=BASE_TIME - timedelta(seconds=1),
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        boundary.includes(
            available_at=BASE_TIME.replace(tzinfo=None),
            recorded_at=BASE_TIME,
        )
