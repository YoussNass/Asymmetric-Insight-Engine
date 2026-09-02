"""Integration coverage for the Chapter 9B immutable product persistence slice."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict

from asymmetric_engine.application.learning import BuildDecisionLearningEvaluation
from asymmetric_engine.application.marginal_decision import RecordPositionHold
from asymmetric_engine.application.product_persistence import (
    ListProductRecords,
    LoadProductRecord,
    ProductAppendStatus,
    ProductRecordIntegrityError,
    ProductRecordKind,
    ProductRecordSchemaError,
    StoreProductRecord,
    product_record_kind_for,
)
from asymmetric_engine.domain.portfolio import (
    DecisionConfidence,
    DecisionConfidenceLevel,
    PortfolioStateDraft,
    PositionReviewInput,
)
from asymmetric_engine.infrastructure.persistence.sqlite_product_store import (
    METADATA_TABLE,
    PRODUCT_TABLE,
    SQLiteProductRecordRepository,
)
from tests.decision_factories import EXISTING_POSITION_ID
from tests.learning_factories import (
    make_allocation_evaluation_input,
    make_allocation_learning_case,
)


class AdvancingClock:
    """Deterministic storage clock that makes first-write preservation observable."""

    def __init__(self) -> None:
        self._current = datetime(2026, 9, 1, 11, 0, tzinfo=UTC)

    def now(self) -> datetime:
        value = self._current
        self._current += timedelta(seconds=1)
        return value


def _records() -> tuple[BaseModel, ...]:
    context, execution_policy, execution_plan, _, learning_case = make_allocation_learning_case()
    decision = context.decision_context
    portfolio_draft = PortfolioStateDraft.model_validate(
        {
            field_name: getattr(decision.portfolio_state, field_name)
            for field_name in PortfolioStateDraft.model_fields
        }
    )
    hold_input = PositionReviewInput(
        knowledge_boundary=decision.portfolio_state.knowledge_boundary,
        position_id=EXISTING_POSITION_ID,
        rationale=("Retain the existing position without allocating incremental capital.",),
        main_risks_and_unknowns=("The standalone position review remains uncalibrated.",),
        change_conditions=("Re-underwrite the position if the standalone thesis changes.",),
        confidence=DecisionConfidence(
            level=DecisionConfidenceLevel.CONDITIONAL,
            rationale="The HOLD record is explicit but has no new-capital authority.",
        ),
    )
    position_review = RecordPositionHold(
        state_builder=decision.state_builder,
        exposure_builder=decision.exposure_builder,
    ).execute(
        portfolio_state=decision.portfolio_state,
        current_exposure=decision.current_exposure,
        review_input=hold_input,
    )
    learning_evaluation = BuildDecisionLearningEvaluation().execute(
        case=learning_case,
        evaluation_input=make_allocation_evaluation_input(learning_case),
    )
    return (
        decision.opportunity_state.causal_analysis,
        decision.opportunity_state,
        portfolio_draft,
        decision.portfolio_state,
        decision.current_exposure,
        context.marginal_result.fits[0],
        context.marginal_result.decision,
        position_review,
        context.owner_policy,
        context.policy_decision,
        context.replacement_decision,
        execution_policy,
        execution_plan,
        learning_case,
        learning_evaluation,
    )


def test_sqlite_product_store_round_trips_every_admitted_record_kind(tmp_path: Path) -> None:
    repository = SQLiteProductRecordRepository(tmp_path / "product-records.sqlite3")
    clock = AdvancingClock()
    store = StoreProductRecord(repository=repository, clock=clock)
    loader = LoadProductRecord(repository)

    records = _records()
    assert {product_record_kind_for(record) for record in records} == set(ProductRecordKind)

    first_results = tuple(store.execute(record) for record in records)
    assert all(result.status is ProductAppendStatus.INSERTED for result in first_results)
    assert len({result.envelope.record_id for result in first_results}) == len(first_results)

    for original, result in zip(records, first_results, strict=True):
        loaded = loader.execute(
            result.envelope.record_id,
            expected_kind=product_record_kind_for(original),
        )
        assert type(loaded.record) is type(original)
        assert loaded.record == original
        assert loaded.envelope == result.envelope

    duplicate = store.execute(records[0])
    assert duplicate.status is ProductAppendStatus.ALREADY_PRESENT
    assert duplicate.envelope == first_results[0].envelope

    causal_records = ListProductRecords(repository).execute(ProductRecordKind.CAUSAL_ANALYSIS)
    assert len(causal_records) == 1
    assert causal_records[0].record == records[0]


def test_sqlite_product_store_is_physically_append_only(tmp_path: Path) -> None:
    database_path = tmp_path / "append-only.sqlite3"
    repository = SQLiteProductRecordRepository(database_path)
    store = StoreProductRecord(repository=repository, clock=AdvancingClock())
    result = store.execute(_records()[3])

    with sqlite3.connect(database_path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                f"UPDATE {PRODUCT_TABLE} SET payload_json = '{{}}' WHERE record_id = ?",
                (str(result.envelope.record_id),),
            )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                f"DELETE FROM {PRODUCT_TABLE} WHERE record_id = ?",
                (str(result.envelope.record_id),),
            )


def test_load_detects_corruption_if_database_guards_are_bypassed(tmp_path: Path) -> None:
    database_path = tmp_path / "corrupt.sqlite3"
    repository = SQLiteProductRecordRepository(database_path)
    store = StoreProductRecord(repository=repository, clock=AdvancingClock())
    result = store.execute(_records()[3])

    with sqlite3.connect(database_path) as connection:
        connection.execute("DROP TRIGGER product_records_no_update")
        connection.execute(
            f"UPDATE {PRODUCT_TABLE} SET payload_json = '{{}}' WHERE record_id = ?",
            (str(result.envelope.record_id),),
        )

    read_repository = SQLiteProductRecordRepository(database_path, initialize_schema=False)
    with pytest.raises(ProductRecordIntegrityError, match="hash"):
        LoadProductRecord(read_repository).execute(result.envelope.record_id)


def test_database_schema_changes_require_explicit_migration(tmp_path: Path) -> None:
    database_path = tmp_path / "schema.sqlite3"
    SQLiteProductRecordRepository(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            f"UPDATE {METADATA_TABLE} SET metadata_value = '999' WHERE metadata_key = ?",
            ("database_schema_version",),
        )

    with pytest.raises(ProductRecordSchemaError, match="explicit migration"):
        SQLiteProductRecordRepository(database_path, initialize_schema=False)


def test_read_mode_never_creates_a_missing_product_store(tmp_path: Path) -> None:
    database_path = tmp_path / "missing.sqlite3"
    with pytest.raises(FileNotFoundError):
        SQLiteProductRecordRepository(database_path, initialize_schema=False)
    assert not database_path.exists()


class UnsupportedRecord(BaseModel):
    model_config = ConfigDict(frozen=True)
    value: str


def test_store_rejects_unregistered_shadow_record_types(tmp_path: Path) -> None:
    repository = SQLiteProductRecordRepository(tmp_path / "shadow.sqlite3")
    store = StoreProductRecord(repository=repository, clock=AdvancingClock())
    with pytest.raises(TypeError, match="unsupported product record type"):
        store.execute(UnsupportedRecord(value="not canonical"))
