"""Storage-agnostic immutable product-record persistence for Chapter 9B."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from typing import Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, field_validator

from asymmetric_engine.domain.causal import CausalAnalysis
from asymmetric_engine.domain.execution import ExecutionPlan, ExecutionPolicy
from asymmetric_engine.domain.learning import DecisionLearningCase, DecisionLearningEvaluation
from asymmetric_engine.domain.opportunity import OpportunityState
from asymmetric_engine.domain.portfolio import (
    MarginalDecision,
    OwnerPortfolioPolicy,
    PolicyConstrainedMarginalDecision,
    PortfolioExposure,
    PortfolioFit,
    PortfolioState,
    PortfolioStateDraft,
    PositionReview,
    ReplacementDecision,
)

PRODUCT_RECORD_ENVELOPE_VERSION = "product-record-envelope-v1"


class ProductRecordKind(StrEnum):
    """Admitted immutable product records for the first persisted product slice."""

    CAUSAL_ANALYSIS = "causal_analysis"
    OPPORTUNITY_STATE = "opportunity_state"
    PORTFOLIO_STATE_DRAFT = "portfolio_state_draft"
    PORTFOLIO_STATE = "portfolio_state"
    PORTFOLIO_EXPOSURE = "portfolio_exposure"
    PORTFOLIO_FIT = "portfolio_fit"
    MARGINAL_DECISION = "marginal_decision"
    POSITION_REVIEW = "position_review"
    OWNER_PORTFOLIO_POLICY = "owner_portfolio_policy"
    POLICY_CONSTRAINED_DECISION = "policy_constrained_decision"
    REPLACEMENT_DECISION = "replacement_decision"
    EXECUTION_POLICY = "execution_policy"
    EXECUTION_PLAN = "execution_plan"
    LEARNING_CASE = "learning_case"
    LEARNING_EVALUATION = "learning_evaluation"


_PRODUCT_RECORD_SPECS: dict[ProductRecordKind, tuple[type[BaseModel], str]] = {
    ProductRecordKind.CAUSAL_ANALYSIS: (CausalAnalysis, "causal-analysis-json-v1"),
    ProductRecordKind.OPPORTUNITY_STATE: (OpportunityState, "opportunity-state-json-v1"),
    ProductRecordKind.PORTFOLIO_STATE_DRAFT: (PortfolioStateDraft, "portfolio-state-draft-json-v1"),
    ProductRecordKind.PORTFOLIO_STATE: (PortfolioState, "portfolio-state-json-v1"),
    ProductRecordKind.PORTFOLIO_EXPOSURE: (PortfolioExposure, "portfolio-exposure-json-v1"),
    ProductRecordKind.PORTFOLIO_FIT: (PortfolioFit, "portfolio-fit-json-v1"),
    ProductRecordKind.MARGINAL_DECISION: (MarginalDecision, "marginal-decision-json-v1"),
    ProductRecordKind.POSITION_REVIEW: (PositionReview, "position-review-json-v1"),
    ProductRecordKind.OWNER_PORTFOLIO_POLICY: (
        OwnerPortfolioPolicy,
        "owner-portfolio-policy-json-v1",
    ),
    ProductRecordKind.POLICY_CONSTRAINED_DECISION: (
        PolicyConstrainedMarginalDecision,
        "policy-constrained-decision-json-v1",
    ),
    ProductRecordKind.REPLACEMENT_DECISION: (ReplacementDecision, "replacement-decision-json-v1"),
    ProductRecordKind.EXECUTION_POLICY: (ExecutionPolicy, "execution-policy-json-v1"),
    ProductRecordKind.EXECUTION_PLAN: (ExecutionPlan, "execution-plan-json-v1"),
    ProductRecordKind.LEARNING_CASE: (DecisionLearningCase, "learning-case-json-v1"),
    ProductRecordKind.LEARNING_EVALUATION: (
        DecisionLearningEvaluation,
        "learning-evaluation-json-v1",
    ),
}


class ProductRecordEnvelope(BaseModel):
    """Append-only storage envelope around one canonical JSON product record."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    envelope_version: str = PRODUCT_RECORD_ENVELOPE_VERSION
    record_id: UUID
    kind: ProductRecordKind
    schema_version: str
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    stored_at: datetime
    payload_json: str = Field(min_length=2)

    @field_validator("envelope_version")
    @classmethod
    def require_current_envelope_version(cls, value: str) -> str:
        if value != PRODUCT_RECORD_ENVELOPE_VERSION:
            raise ValueError(f"envelope_version must be {PRODUCT_RECORD_ENVELOPE_VERSION!r}")
        return value

    @field_validator("stored_at")
    @classmethod
    def require_timezone_aware_storage_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("stored_at must be timezone-aware")
        return value


class ProductAppendStatus(StrEnum):
    """Whether a product record was first persisted or already existed identically."""

    INSERTED = "inserted"
    ALREADY_PRESENT = "already_present"


@dataclass(frozen=True, slots=True)
class ProductAppendResult:
    """Append result preserving the first durable storage timestamp."""

    status: ProductAppendStatus
    envelope: ProductRecordEnvelope


@dataclass(frozen=True, slots=True)
class LoadedProductRecord:
    """Verified stored envelope and its reconstructed admitted canonical record."""

    envelope: ProductRecordEnvelope
    record: BaseModel


class ProductRecordConflictError(RuntimeError):
    """Raised when one immutable storage identity is reused with conflicting content."""


class ProductRecordIntegrityError(RuntimeError):
    """Raised when stored bytes, content hash, or content-addressed identity do not agree."""


class ProductRecordSchemaError(RuntimeError):
    """Raised when a stored record requires an unsupported schema or migration."""


class ProductPersistenceClock(Protocol):
    """Clock used to attest when AIE first persisted a product record locally."""

    def now(self) -> datetime:
        """Return a timezone-aware storage timestamp."""


class ProductRecordRepository(Protocol):
    """Append-only repository port for immutable product records."""

    def append(self, envelope: ProductRecordEnvelope) -> ProductAppendResult:
        """Persist a new envelope or return the identical first-stored envelope."""

    def get(self, record_id: UUID) -> ProductRecordEnvelope:
        """Load one exact persisted envelope by immutable storage identity."""

    def list_by_kind(self, kind: ProductRecordKind) -> tuple[ProductRecordEnvelope, ...]:
        """List persisted envelopes of one admitted kind ordered by first storage time."""


def product_record_kind_for(record: BaseModel) -> ProductRecordKind:
    """Return the admitted storage kind for an exact canonical model type."""

    record_type = type(record)
    for kind, (model_type, _) in _PRODUCT_RECORD_SPECS.items():
        if record_type is model_type:
            return kind
    raise TypeError(f"unsupported product record type: {record_type.__module__}.{record_type.__name__}")


def product_record_schema_version(kind: ProductRecordKind) -> str:
    """Return the currently admitted JSON schema version for one record kind."""

    return _PRODUCT_RECORD_SPECS[kind][1]


def _canonical_json(record: BaseModel) -> str:
    return json.dumps(
        record.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _record_id(*, kind: ProductRecordKind, schema_version: str, payload_sha256: str) -> UUID:
    return uuid5(
        NAMESPACE_URL,
        "asymmetric-insight-engine:product-record:"
        f"{kind.value}:{schema_version}:{payload_sha256}",
    )


def verify_product_record_envelope(envelope: ProductRecordEnvelope) -> LoadedProductRecord:
    """Verify persisted bytes and rebuild the explicitly admitted concrete record type."""

    model_type, current_schema_version = _PRODUCT_RECORD_SPECS[envelope.kind]
    if envelope.schema_version != current_schema_version:
        raise ProductRecordSchemaError(
            f"stored {envelope.kind.value} schema {envelope.schema_version!r} requires an explicit "
            f"migration; current schema is {current_schema_version!r}"
        )

    payload_bytes = envelope.payload_json.encode("utf-8")
    actual_sha256 = sha256(payload_bytes).hexdigest()
    if actual_sha256 != envelope.payload_sha256:
        raise ProductRecordIntegrityError("stored product payload hash does not match payload bytes")
    expected_record_id = _record_id(
        kind=envelope.kind,
        schema_version=envelope.schema_version,
        payload_sha256=envelope.payload_sha256,
    )
    if expected_record_id != envelope.record_id:
        raise ProductRecordIntegrityError("stored product record_id is not content-addressed correctly")

    try:
        record = model_type.model_validate_json(envelope.payload_json)
    except ValueError as exc:
        raise ProductRecordIntegrityError("stored product payload no longer validates") from exc
    if _canonical_json(record) != envelope.payload_json:
        raise ProductRecordIntegrityError("stored product payload is not in canonical JSON form")
    return LoadedProductRecord(envelope=envelope, record=record)


class StoreProductRecord:
    """Serialize one admitted immutable product record and preserve its first storage time."""

    def __init__(self, *, repository: ProductRecordRepository, clock: ProductPersistenceClock) -> None:
        self._repository = repository
        self._clock = clock

    def execute(self, record: BaseModel) -> ProductAppendResult:
        """Persist one canonical record without granting the store any financial authority."""

        kind = product_record_kind_for(record)
        schema_version = product_record_schema_version(kind)
        payload_json = _canonical_json(record)
        payload_sha256 = sha256(payload_json.encode("utf-8")).hexdigest()
        envelope = ProductRecordEnvelope(
            record_id=_record_id(
                kind=kind,
                schema_version=schema_version,
                payload_sha256=payload_sha256,
            ),
            kind=kind,
            schema_version=schema_version,
            payload_sha256=payload_sha256,
            stored_at=self._clock.now(),
            payload_json=payload_json,
        )
        return self._repository.append(envelope)


class LoadProductRecord:
    """Load and verify one persisted record before any downstream canonical replay."""

    def __init__(self, repository: ProductRecordRepository) -> None:
        self._repository = repository

    def execute(
        self,
        record_id: UUID,
        *,
        expected_kind: ProductRecordKind | None = None,
    ) -> LoadedProductRecord:
        """Return a storage-verified record; decision owners must still replay it before use."""

        envelope = self._repository.get(record_id)
        if expected_kind is not None and envelope.kind is not expected_kind:
            raise ProductRecordIntegrityError(
                f"record kind {envelope.kind.value!r} does not match expected {expected_kind.value!r}"
            )
        return verify_product_record_envelope(envelope)


class ListProductRecords:
    """List storage-verified immutable records of one kind."""

    def __init__(self, repository: ProductRecordRepository) -> None:
        self._repository = repository

    def execute(self, kind: ProductRecordKind) -> tuple[LoadedProductRecord, ...]:
        """Verify every returned envelope rather than trusting database metadata."""

        return tuple(
            verify_product_record_envelope(envelope)
            for envelope in self._repository.list_by_kind(kind)
        )


__all__ = [
    "PRODUCT_RECORD_ENVELOPE_VERSION",
    "ListProductRecords",
    "LoadProductRecord",
    "LoadedProductRecord",
    "ProductAppendResult",
    "ProductAppendStatus",
    "ProductPersistenceClock",
    "ProductRecordConflictError",
    "ProductRecordEnvelope",
    "ProductRecordIntegrityError",
    "ProductRecordKind",
    "ProductRecordRepository",
    "ProductRecordSchemaError",
    "StoreProductRecord",
    "product_record_kind_for",
    "product_record_schema_version",
    "verify_product_record_envelope",
]
