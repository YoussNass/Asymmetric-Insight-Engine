"""Golden-fixture tests for fail-closed Chapter 11C canonical SEC fact admission."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from hashlib import sha256
from uuid import UUID

import pytest

from asymmetric_engine.application.evidence_ingestion import AppendResult
from asymmetric_engine.application.sec_fact_admission import (
    AdmitSecReportedFact,
    SecCalculationStatus,
    SecCandidateReconciliation,
    SecFactAdmissionRequest,
    SecFactAdmissionStatus,
)
from asymmetric_engine.application.sec_xbrl_extraction import (
    SecXbrlAuthority,
    SecXbrlCandidate,
    SecXbrlCandidateSet,
    SecXbrlPeriodKind,
)
from asymmetric_engine.domain.evidence import (
    AvailabilityBasis,
    ClaimType,
    SourceDocument,
    SourceType,
)
from asymmetric_engine.domain.opportunity.models import (
    FinancialFactBasis,
    FinancialMetric,
    FinancialPeriod,
    FinancialPeriodKind,
    FinancialPeriodScope,
    FinancialUnit,
)


CONTENT = b"<SEC-DOCUMENT>immutable filing bytes</SEC-DOCUMENT>"
DOCUMENT_ID = UUID("22222222-2222-2222-2222-222222222222")
EXTRACTION_ID = UUID("33333333-3333-3333-3333-333333333333")
USD_MEASURE = "{http://www.xbrl.org/2003/iso4217}USD"
SHARES_MEASURE = "{http://www.xbrl.org/2003/instance}shares"


def source_document() -> SourceDocument:
    observed_at = datetime(2024, 11, 1, 12, 0, tzinfo=UTC)
    return SourceDocument(
        document_id=DOCUMENT_ID,
        provider="sec-edgar",
        provider_record_id="0000320193:10-K:20240928",
        provider_version="0000320193-24-000123",
        subject_id="company:sec-cik-0000320193",
        title="Fixture issuer — 10-K for 20240928",
        source_uri="https://www.sec.gov/Archives/edgar/data/example.txt",
        source_type=SourceType.FILING,
        effective_at=datetime(2024, 9, 28, tzinfo=UTC),
        availability_basis=AvailabilityBasis.OBSERVED_AT_INGESTION,
        available_at=observed_at,
        recorded_at=observed_at,
        media_type="text/plain",
        content_hash=sha256(CONTENT).hexdigest(),
        content_size_bytes=len(CONTENT),
    )


class FakeRepository:
    def __init__(self, document: SourceDocument | None = None, content: bytes = CONTENT) -> None:
        self.document = document or source_document()
        self.content = content

    def append(self, document: SourceDocument, content: bytes) -> AppendResult:
        raise AssertionError("admission never appends source evidence")

    def list_by_subject(self, subject_id: str) -> tuple[SourceDocument, ...]:
        return (self.document,) if subject_id == self.document.subject_id else ()

    def get(self, document_id: UUID) -> SourceDocument:
        if document_id != self.document.document_id:
            raise KeyError(document_id)
        return self.document

    def read_content(self, document_id: UUID) -> bytes:
        if document_id != self.document.document_id:
            raise KeyError(document_id)
        return self.content


def fy_period() -> FinancialPeriod:
    return FinancialPeriod(
        kind=FinancialPeriodKind.DURATION,
        start_date=date(2023, 10, 1),
        end_date=date(2024, 9, 28),
        duration_scope=FinancialPeriodScope.FISCAL_YEAR,
    )


def candidate(
    *,
    concept_name: str = "RevenueFromContractWithCustomerExcludingAssessedTax",
    raw_value: str = "391035000000",
    unit_measure: str = USD_MEASURE,
    candidate_id: str = "a" * 64,
    namespace: str = "http://fasb.org/us-gaap/2024",
    dimensions: tuple[object, ...] = (),
) -> SecXbrlCandidate:
    return SecXbrlCandidate(
        candidate_id=candidate_id,
        source_document_id=DOCUMENT_ID,
        source_content_hash=sha256(CONTENT).hexdigest(),
        accession="0000320193-24-000123",
        concept_namespace=namespace,
        concept_name=concept_name,
        context_id="FY2024",
        period_kind=SecXbrlPeriodKind.DURATION,
        period_start=date(2023, 10, 1),
        period_end=date(2024, 9, 28),
        unit_id="USD" if unit_measure == USD_MEASURE else "shares",
        unit_numerator=(unit_measure,),
        unit_denominator=(),
        dimensions=dimensions,  # type: ignore[arg-type]
        decimals="-6",
        precision=None,
        raw_value=raw_value,
        is_numeric=True,
        is_nil=False,
        source_locator=f"annual.htm#{candidate_id[:8]}",
        processor_name="Arelle",
        processor_version="2.44.5",
        extraction_method="sec-xbrl-shadow-extraction",
        extraction_version="sec-xbrl-shadow-v1",
    )


def candidate_set(*facts: SecXbrlCandidate) -> SecXbrlCandidateSet:
    return SecXbrlCandidateSet(
        extraction_id=EXTRACTION_ID,
        input_fingerprint="f" * 64,
        source_document_id=DOCUMENT_ID,
        source_content_hash=sha256(CONTENT).hexdigest(),
        accession="0000320193-24-000123",
        processor_name="Arelle",
        processor_version="2.44.5",
        extraction_method="sec-xbrl-shadow-extraction",
        extraction_version="sec-xbrl-shadow-v1",
        candidates=facts,
        warnings=("shadow_extraction_not_admitted_for_underwriting",),
        authority=SecXbrlAuthority.SHADOW_ONLY,
    )


class FakeReconciler:
    def __init__(
        self,
        *,
        calculation_status: SecCalculationStatus = SecCalculationStatus.CONSISTENT,
        statement_present: bool = True,
        statement_value: Decimal | None = None,
    ) -> None:
        self.calculation_status = calculation_status
        self.statement_present = statement_present
        self.statement_value = statement_value
        self.calls: list[str] = []

    def reconcile(
        self,
        *,
        candidate: SecXbrlCandidate,
        candidate_set: SecXbrlCandidateSet,
    ) -> SecCandidateReconciliation:
        assert candidate_set.source_document_id == candidate.source_document_id
        self.calls.append(candidate.candidate_id)
        value = self.statement_value
        if value is None:
            value = Decimal(candidate.raw_value)
        return SecCandidateReconciliation(
            candidate_id=candidate.candidate_id,
            statement_present=self.statement_present,
            statement_role_uri="http://example.com/role/ConsolidatedStatements",
            statement_locator="statement-1#line-4",
            statement_value=value,
            calculation_status=self.calculation_status,
            calculation_detail="Calculation relationship is consistent or explicitly not applicable.",
            reconciler_name="fixture-statement-reconciler",
            reconciler_version="1.0.0",
        )


def service(reconciler: FakeReconciler | None = None) -> AdmitSecReportedFact:
    return AdmitSecReportedFact(
        repository=FakeRepository(),
        reconciler=reconciler or FakeReconciler(),
    )


def test_revenue_admission_builds_deterministic_underwriting_lineage() -> None:
    facts = candidate_set(candidate())
    request = SecFactAdmissionRequest(
        metric=FinancialMetric.REVENUE,
        period=fy_period(),
        expected_currency="USD",
    )

    first = service().execute(candidate_set=facts, request=request)
    second = service().execute(candidate_set=facts, request=request)

    assert first == second
    assert first.status is SecFactAdmissionStatus.ADMITTED
    assert first.reasons == ()
    assert first.bundle is not None
    bundle = first.bundle
    assert bundle.mapping_version == "sec-canonical-fact-mapping-v1"
    assert bundle.financial_fact.metric is FinancialMetric.REVENUE
    assert bundle.financial_fact.value == Decimal("391035")
    assert bundle.financial_fact.unit is FinancialUnit.MONEY_MILLIONS
    assert bundle.financial_fact.currency == "USD"
    assert bundle.financial_fact.basis is FinancialFactBasis.REPORTED
    assert bundle.financial_fact.period == fy_period()
    assert bundle.financial_fact.claim_ids == (bundle.claim.claim_id,)
    assert bundle.claim.claim_type is ClaimType.OBSERVATION
    assert bundle.claim.evidence_ids == (bundle.evidence.evidence_id,)
    assert bundle.evidence.source_document_id == DOCUMENT_ID
    assert "annual.htm" in str(bundle.evidence.source_locator)
    assert "sec-canonical-fact-mapping-v1" in str(bundle.evidence.extraction_method)


@pytest.mark.parametrize(
    ("metric", "concept_name", "raw_value", "unit_measure", "expected_value"),
    [
        (
            FinancialMetric.REVENUE,
            "Revenues",
            "1000000000",
            USD_MEASURE,
            Decimal("1000"),
        ),
        (
            FinancialMetric.GROSS_PROFIT,
            "GrossProfit",
            "400000000",
            USD_MEASURE,
            Decimal("400"),
        ),
        (
            FinancialMetric.OPERATING_INCOME,
            "OperatingIncomeLoss",
            "250000000",
            USD_MEASURE,
            Decimal("250"),
        ),
        (
            FinancialMetric.NET_INCOME,
            "NetIncomeLoss",
            "-50000000",
            USD_MEASURE,
            Decimal("-50"),
        ),
        (
            FinancialMetric.OPERATING_CASH_FLOW,
            "NetCashProvidedByUsedInOperatingActivities",
            "320000000",
            USD_MEASURE,
            Decimal("320"),
        ),
        (
            FinancialMetric.CAPITAL_EXPENDITURES,
            "PaymentsToAcquirePropertyPlantAndEquipment",
            "120000000",
            USD_MEASURE,
            Decimal("120"),
        ),
        (
            FinancialMetric.DILUTED_WEIGHTED_AVERAGE_SHARES,
            "WeightedAverageNumberOfDilutedSharesOutstanding",
            "1500000000",
            SHARES_MEASURE,
            Decimal("1500"),
        ),
        (
            FinancialMetric.SHARE_BASED_COMPENSATION,
            "ShareBasedCompensation",
            "90000000",
            USD_MEASURE,
            Decimal("90"),
        ),
    ],
)
def test_golden_corpus_admits_only_exact_v1_metric_families(
    metric: FinancialMetric,
    concept_name: str,
    raw_value: str,
    unit_measure: str,
    expected_value: Decimal,
) -> None:
    result = service().execute(
        candidate_set=candidate_set(
            candidate(
                concept_name=concept_name,
                raw_value=raw_value,
                unit_measure=unit_measure,
            )
        ),
        request=SecFactAdmissionRequest(
            metric=metric,
            period=fy_period(),
            expected_currency=None
            if metric is FinancialMetric.DILUTED_WEIGHTED_AVERAGE_SHARES
            else "USD",
        ),
    )

    assert result.status is SecFactAdmissionStatus.ADMITTED
    assert result.bundle is not None
    assert result.bundle.financial_fact.value == expected_value


def test_unsupported_economic_semantics_remain_explicitly_unadmitted() -> None:
    for metric in (
        FinancialMetric.CASH_AND_INVESTMENTS,
        FinancialMetric.TOTAL_DEBT,
        FinancialMetric.DILUTED_SHARES_OUTSTANDING,
    ):
        result = service().execute(
            candidate_set=candidate_set(candidate()),
            request=SecFactAdmissionRequest(metric=metric, period=fy_period()),
        )

        assert result.status is SecFactAdmissionStatus.UNSUPPORTED
        assert result.bundle is None


def test_issuer_extensions_and_dimension_only_facts_fail_closed_as_missing() -> None:
    issuer_extension = candidate(namespace="http://example.com/issuer/2024")
    dimensioned = replace(
        candidate(candidate_id="b" * 64),
        dimensions=(
            replace_dimension(),
        ),
    )

    for fact in (issuer_extension, dimensioned):
        result = service().execute(
            candidate_set=candidate_set(fact),
            request=SecFactAdmissionRequest(
                metric=FinancialMetric.REVENUE,
                period=fy_period(),
                expected_currency="USD",
            ),
        )
        assert result.status is SecFactAdmissionStatus.MISSING
        assert result.bundle is None


def replace_dimension():
    from asymmetric_engine.application.sec_xbrl_extraction import SecXbrlDimension

    return SecXbrlDimension(
        axis_namespace="http://example.com/issuer/2024",
        axis_name="SegmentAxis",
        member_namespace="http://example.com/issuer/2024",
        member_name="CloudMember",
    )


def test_multiple_exact_standard_candidates_are_ambiguous_even_when_values_match() -> None:
    first = candidate(candidate_id="a" * 64, concept_name="Revenues")
    second = candidate(
        candidate_id="b" * 64,
        concept_name="RevenueFromContractWithCustomerExcludingAssessedTax",
    )

    result = service().execute(
        candidate_set=candidate_set(first, second),
        request=SecFactAdmissionRequest(
            metric=FinancialMetric.REVENUE,
            period=fy_period(),
            expected_currency="USD",
        ),
    )

    assert result.status is SecFactAdmissionStatus.AMBIGUOUS
    assert set(result.considered_candidate_ids) == {"a" * 64, "b" * 64}
    assert result.bundle is None


@pytest.mark.parametrize(
    ("fact", "expected_currency", "reason"),
    [
        (
            candidate(unit_measure="{http://www.xbrl.org/2003/iso4217}EUR"),
            "USD",
            "currency",
        ),
        (
            candidate(unit_measure=SHARES_MEASURE),
            "USD",
            "ISO currency",
        ),
        (
            replace(candidate(), raw_value="not-a-number"),
            "USD",
            "finite decimal",
        ),
    ],
)
def test_unit_currency_and_numeric_conflicts_are_never_silently_normalized(
    fact: SecXbrlCandidate,
    expected_currency: str,
    reason: str,
) -> None:
    result = service().execute(
        candidate_set=candidate_set(fact),
        request=SecFactAdmissionRequest(
            metric=FinancialMetric.REVENUE,
            period=fy_period(),
            expected_currency=expected_currency,
        ),
    )

    assert result.status is SecFactAdmissionStatus.CONFLICT
    assert any(reason in item for item in result.reasons)
    assert result.bundle is None


def test_exact_period_is_required_and_fiscal_scope_is_never_inferred() -> None:
    quarter = FinancialPeriod(
        kind=FinancialPeriodKind.DURATION,
        start_date=date(2024, 6, 30),
        end_date=date(2024, 9, 28),
        duration_scope=FinancialPeriodScope.FISCAL_QUARTER,
    )

    result = service().execute(
        candidate_set=candidate_set(candidate()),
        request=SecFactAdmissionRequest(
            metric=FinancialMetric.REVENUE,
            period=quarter,
            expected_currency="USD",
        ),
    )

    assert result.status is SecFactAdmissionStatus.MISSING


def test_reconciliation_must_confirm_statement_value_and_calculation_status() -> None:
    scenarios = (
        (
            FakeReconciler(statement_present=False),
            "candidate_not_presented_on_reconciled_statement",
        ),
        (
            FakeReconciler(statement_value=Decimal("1")),
            "statement_value_conflict",
        ),
        (
            FakeReconciler(calculation_status=SecCalculationStatus.INCONSISTENT),
            "calculation_inconsistent",
        ),
        (
            FakeReconciler(calculation_status=SecCalculationStatus.UNKNOWN),
            "calculation_unknown",
        ),
    )
    for reconciler, reason in scenarios:
        result = service(reconciler).execute(
            candidate_set=candidate_set(candidate()),
            request=SecFactAdmissionRequest(
                metric=FinancialMetric.REVENUE,
                period=fy_period(),
                expected_currency="USD",
            ),
        )
        assert result.status is SecFactAdmissionStatus.RECONCILIATION_FAILED
        assert reason in result.reasons
        assert result.bundle is None


def test_calculation_not_applicable_is_explicitly_admissible() -> None:
    reconciler = FakeReconciler(calculation_status=SecCalculationStatus.NOT_APPLICABLE)

    result = service(reconciler).execute(
        candidate_set=candidate_set(candidate()),
        request=SecFactAdmissionRequest(
            metric=FinancialMetric.REVENUE,
            period=fy_period(),
            expected_currency="USD",
        ),
    )

    assert result.status is SecFactAdmissionStatus.ADMITTED


def test_unreviewed_extraction_version_cannot_cross_into_underwriting() -> None:
    unreviewed = replace(candidate_set(candidate()), extraction_version="sec-xbrl-shadow-v2")

    with pytest.raises(ValueError, match="unsupported extraction version"):
        service().execute(
            candidate_set=unreviewed,
            request=SecFactAdmissionRequest(
                metric=FinancialMetric.REVENUE,
                period=fy_period(),
                expected_currency="USD",
            ),
        )


def test_candidate_set_must_match_verified_source_hash_and_accession() -> None:
    mismatched_hash = replace(candidate_set(candidate()), source_content_hash="0" * 64)
    mismatched_accession = replace(candidate_set(candidate()), accession="0000320193-24-999999")

    with pytest.raises(ValueError, match="source hash"):
        service().execute(
            candidate_set=mismatched_hash,
            request=SecFactAdmissionRequest(
                metric=FinancialMetric.REVENUE,
                period=fy_period(),
                expected_currency="USD",
            ),
        )
    with pytest.raises(ValueError, match="accession"):
        service().execute(
            candidate_set=mismatched_accession,
            request=SecFactAdmissionRequest(
                metric=FinancialMetric.REVENUE,
                period=fy_period(),
                expected_currency="USD",
            ),
        )
