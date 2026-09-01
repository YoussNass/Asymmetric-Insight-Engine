"""Unit hardening for Chapter 9B immutable product persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from asymmetric_engine.application.product_persistence import (
    LoadProductRecord,
    ProductAppendResult,
    ProductAppendStatus,
    ProductRecordEnvelope,
    ProductRecordIntegrityError,
    ProductRecordKind,
    ProductRecordRepository,
    StoreProductRecord,
    verify_product_record_envelope,
)
from asymmetric_engine.domain.learning import DecisionLearningCase
from tests.learning_factories import make_allocation_learning_case


class NaiveClock:
    def now(self) -> datetime:
        return datetime(2026, 9, 1, 11, 0)


class FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 9, 1, 11, 0, tzinfo=UTC)


class MemoryRepository(ProductRecordRepository):
    def __init__(self) -> None:
        self.envelopes: dict[UUID, ProductRecordEnvelope] = {}

    def append(self, envelope: ProductRecordEnvelope) -> ProductAppendResult:
        existing = self.envelopes.get(envelope.record_id)
        if existing is not None:
            return ProductAppendResult(ProductAppendStatus.ALREADY_PRESENT, existing)
        self.envelopes[envelope.record_id] = envelope
        return ProductAppendResult(ProductAppendStatus.INSERTED, envelope)

    def get(self, record_id: UUID) -> ProductRecordEnvelope:
        try:
            return self.envelopes[record_id]
        except KeyError as exc:
            raise KeyError(record_id) from exc

    def list_by_kind(self, kind: ProductRecordKind) -> tuple[ProductRecordEnvelope, ...]:
        return tuple(item for item in self.envelopes.values() if item.kind is kind)


def _learning_case() -> DecisionLearningCase:
    return make_allocation_learning_case()[-1]


def test_store_rejects_naive_storage_clock() -> None:
    repository = MemoryRepository()
    with pytest.raises(ValidationError, match="stored_at must be timezone-aware"):
        StoreProductRecord(repository=repository, clock=NaiveClock()).execute(_learning_case())
    assert repository.envelopes == {}


def test_load_rejects_expected_kind_mismatch() -> None:
    repository = MemoryRepository()
    result = StoreProductRecord(repository=repository, clock=FixedClock()).execute(_learning_case())
    with pytest.raises(ProductRecordIntegrityError, match="does not match expected"):
        LoadProductRecord(repository).execute(
            result.envelope.record_id,
            expected_kind=ProductRecordKind.EXECUTION_PLAN,
        )


def test_verifier_rejects_content_addressed_id_tampering() -> None:
    repository = MemoryRepository()
    result = StoreProductRecord(repository=repository, clock=FixedClock()).execute(_learning_case())
    tampered = result.envelope.model_copy(update={"record_id": uuid4()})
    with pytest.raises(ProductRecordIntegrityError, match="content-addressed"):
        verify_product_record_envelope(tampered)
