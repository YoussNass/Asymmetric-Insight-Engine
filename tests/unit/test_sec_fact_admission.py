"""Golden and red-team tests for fail-closed Chapter 11C canonical SEC fact admission."""

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
    DeterministicSecFactReconciler,
    SecCalculationComponent,
    SecCalculationStatus,
    SecCandidateReconciliation,
    SecFactAdmissionRequest,
    SecFactAdmissionStatus,
    SecFactReconciler,
    SecStatementObservation,
)
from asymmetric_engine.application.sec_xbrl_extraction import (
    ExtractSecXbrlCandidates,
    ProcessorXbrlFact,
    SecXbrlCandidate,
    SecXbrlCandidateSet,
    SecXbrlDimension,
    SecXbrlExtractionError,
    SecXbrlPeriodKind,
)
from asymmetric_engine.application.source_verification import SourceDocumentIntegrityError
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
USD_MEASURE = "{http://www.xbrl.org/2003/iso4217}USD"
EUR_MEASURE = "{http://www.xbrl.org/2003/iso4217}EUR"
SHARES_MEASURE = "{http://www.xbrl.org/2003/instance}shares"


def source_document(
    *,
    provider_version: str = "0000320193-24-000123",
    content_hash: str | None = None,
) -> SourceDocument:
    observed_at = datetime(2024, 11, 1, 12, 0, tzinfo=UTC)
    return SourceDocument(
        document_id=DOCUMENT_ID,
        provider="sec-edgar",
        provider_record_id="0000320193:10-K:20240928",
        provider_version=provider_version,
        subject_id="company:sec-cik-0000320193",
        title="Fixture issuer — 10-K for 20240928",
        source_uri="https://www.sec.gov/Archives/edgar/data/example.txt",
        source_type=SourceType.FILING,
        effective_at=datetime(2024, 9, 28, tzinfo=UTC),
        availability_basis=AvailabilityBasis.OBSERVED_AT_INGESTION,
        available_at=observed_at,
        recorded_at=observed_at,
        media_type="text/plain",
        content_hash=content_hash or sha256(CONTENT).hexdigest(),
        content_size_bytes=len(CONTENT),
    )


class FakeRepository:
    def __init__(
        self,
        document: SourceDocument | None = None,
        content: bytes = CONTENT,
    ) -> None:
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


class FakeProcessor:
    processor_name = "Arelle"
    processor_version = "2.44.5"

    def __init__(self, facts: tuple[ProcessorXbrlFact, ...]) -> None:
        self.facts = facts

    def extract(self, *, content: bytes, source_uri: str) -> tuple[ProcessorXbrlFact, ...]:
        assert content == CONTENT
        assert source_uri
        return self.facts


def fy_period() -> FinancialPeriod:
    return FinancialPeriod(
        kind=FinancialPeriodKind.DURATION,
        start_date=date(2023, 10, 1),
        end_date=date(2024, 9, 28),
        duration_scope=FinancialPeriodScope.FISCAL_YEAR,
    )


def processor_fact(
    *,
    concept_name: str = "RevenueFromContractWithCustomerExcludingAssessedTax",
    raw_value: str = "391035000000",
    unit_measure: str = USD_MEASURE,
    namespace: str = "http://fasb.org/us-gaap/2024",
    dimensions: tuple[SecXbrlDimension, ...] = (),
    period_start: date = date(2023, 10, 1),
    period_end: date = date(2024, 9, 28),
    source_locator: str = "annual.htm#fact",
) -> ProcessorXbrlFact:
    return ProcessorXbrlFact(
        concept_namespace=namespace,
        concept_name=concept_name,
        context_id=f"{period_start.isoformat()}:{period_end.isoformat()}",
        period_kind=SecXbrlPeriodKind.DURATION,
        period_start=period_start,
        period_end=period_end,
        unit_id="USD" if unit_measure == USD_MEASURE else "unit",
        unit_numerator=(unit_measure,),
        unit_denominator=(),
        dimensions=dimensions,
        decimals="-6",
        precision=None,
        raw_value=raw_value,
        is_numeric=True,
        is_nil=False,
        source_locator=source_locator,
    )


def candidate_set(*facts: ProcessorXbrlFact) -> SecXbrlCandidateSet:
    return ExtractSecXbrlCandidates(
        repository=FakeRepository(),
        processor=FakeProcessor(facts),
    ).execute(DOCUMENT_ID)


class FakeReconciler:
    def __init__(
        self,
        *,
        calculation_status: SecCalculationStatus = SecCalculationStatus.CONSISTENT,
        statement_present: bool = True,
        statement_value: Decimal | None = None,
        inspector_name: str = "fixture-statement-inspector",
        inspector_version: str = "1.0.0",
    ) -> None:
        self.calculation_status = calculation_status
        self.statement_present = statement_present
        self.statement_value = statement_value
        self.inspector_name = inspector_name
        self.inspector_version = inspector_version
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
            calculation_detail=(
                "Calculation relationship is consistent or explicitly not applicable."
            ),
            reconciler_name="fixture-statement-reconciler",
            reconciler_version="1.0.0",
            inspector_name=self.inspector_name,
            inspector_version=self.inspector_version,
        )


def service(
    reconciler: SecFactReconciler | None = None,
    *,
    repository: FakeRepository | None = None,
) -> AdmitSecReportedFact:
    return AdmitSecReportedFact(
        repository=repository or FakeRepository(),
        reconciler=reconciler or FakeReconciler(),
    )


def revenue_request() -> SecFactAdmissionRequest:
    return SecFactAdmissionRequest(
        metric=FinancialMetric.REVENUE,
        period=fy_period(),
        expected_currency="USD",
    )


def test_revenue_admission_builds_deterministic_underwriting_lineage() -> None:
    facts = candidate_set(processor_fact())
    request = revenue_request()

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
    assert "fixture-statement-inspector@1.0.0" in str(bundle.evidence.extraction_method)


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
            processor_fact(
                concept_name=concept_name,
                raw_value=raw_value,
                unit_measure=unit_measure,
            )
        ),
        request=SecFactAdmissionRequest(
            metric=metric,
            period=fy_period(),
            expected_currency=(
                None
                if metric is FinancialMetric.DILUTED_WEIGHTED_AVERAGE_SHARES
                else "USD"
            ),
        ),
    )

    assert result.status is SecFactAdmissionStatus.ADMITTED
    assert result.bundle is not None
    assert result.bundle.financial_fact.value == expected_value


@pytest.mark.parametrize(
    ("namespace", "concept_name"),
    [
        ("http://fasb.org/us-gaap/2022", "SalesRevenueNet"),
        ("http://fasb.org/us-gaap/2023", "Revenues"),
        (
            "http://fasb.org/us-gaap/2024",
            "RevenueFromContractWithCustomerExcludingAssessedTax",
        ),
    ],
)
def test_heterogeneous_standard_taxonomy_vintages_remain_deterministic(
    namespace: str,
    concept_name: str,
) -> None:
    result = service().execute(
        candidate_set=candidate_set(
            processor_fact(namespace=namespace, concept_name=concept_name)
        ),
        request=revenue_request(),
    )

    assert result.status is SecFactAdmissionStatus.ADMITTED
    assert result.bundle is not None
    assert result.bundle.financial_fact.value == Decimal("391035")


def test_unsupported_economic_semantics_remain_explicitly_unadmitted() -> None:
    facts = candidate_set(processor_fact())
    for metric in (
        FinancialMetric.CASH_AND_INVESTMENTS,
        FinancialMetric.TOTAL_DEBT,
        FinancialMetric.DILUTED_SHARES_OUTSTANDING,
    ):
        result = service().execute(
            candidate_set=facts,
            request=SecFactAdmissionRequest(metric=metric, period=fy_period()),
        )

        assert result.status is SecFactAdmissionStatus.UNSUPPORTED
        assert result.bundle is None


def test_issuer_extensions_and_dimension_only_facts_fail_closed_as_missing() -> None:
    dimension = SecXbrlDimension(
        axis_namespace="http://example.com/issuer/2024",
        axis_name="SegmentAxis",
        member_namespace="http://example.com/issuer/2024",
        member_name="CloudMember",
    )
    issuer_extension = processor_fact(namespace="http://example.com/issuer/2024")
    dimensioned = processor_fact(dimensions=(dimension,))

    for fact in (issuer_extension, dimensioned):
        result = service().execute(
            candidate_set=candidate_set(fact),
            request=revenue_request(),
        )
        assert result.status is SecFactAdmissionStatus.MISSING
        assert result.bundle is None


def test_multiple_exact_standard_candidates_are_ambiguous_even_when_values_match() -> None:
    facts = candidate_set(
        processor_fact(concept_name="Revenues", source_locator="annual.htm#revenues"),
        processor_fact(
            concept_name="RevenueFromContractWithCustomerExcludingAssessedTax",
            source_locator="annual.htm#contract-revenue",
        ),
    )

    result = service().execute(candidate_set=facts, request=revenue_request())

    assert result.status is SecFactAdmissionStatus.AMBIGUOUS
    assert set(result.considered_candidate_ids) == {
        item.candidate_id for item in facts.candidates
    }
    assert result.bundle is None


@pytest.mark.parametrize(
    ("fact", "expected_currency", "reason"),
    [
        (processor_fact(unit_measure=EUR_MEASURE), "USD", "currency"),
        (processor_fact(unit_measure=SHARES_MEASURE), "USD", "ISO currency"),
        (processor_fact(raw_value="not-a-number"), "USD", "finite decimal"),
    ],
)
def test_unit_currency_and_numeric_conflicts_are_never_silently_normalized(
    fact: ProcessorXbrlFact,
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


@pytest.mark.parametrize(
    ("metric", "concept_name", "raw_value", "reason"),
    [
        (FinancialMetric.REVENUE, "Revenues", "0", "greater than zero"),
        (
            FinancialMetric.CAPITAL_EXPENDITURES,
            "PaymentsToAcquirePropertyPlantAndEquipment",
            "-1",
            "cannot be negative",
        ),
        (
            FinancialMetric.SHARE_BASED_COMPENSATION,
            "ShareBasedCompensation",
            "-1",
            "cannot be negative",
        ),
    ],
)
def test_underwriting_value_domain_conflicts_fail_closed_before_model_construction(
    metric: FinancialMetric,
    concept_name: str,
    raw_value: str,
    reason: str,
) -> None:
    result = service().execute(
        candidate_set=candidate_set(
            processor_fact(concept_name=concept_name, raw_value=raw_value)
        ),
        request=SecFactAdmissionRequest(
            metric=metric,
            period=fy_period(),
            expected_currency="USD",
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
        candidate_set=candidate_set(processor_fact()),
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
        (
            FakeReconciler(inspector_name=""),
            "missing_statement_inspector_identity",
        ),
    )
    facts = candidate_set(processor_fact())
    for reconciler, reason in scenarios:
        result = service(reconciler).execute(
            candidate_set=facts,
            request=revenue_request(),
        )
        assert result.status is SecFactAdmissionStatus.RECONCILIATION_FAILED
        assert reason in result.reasons
        assert result.bundle is None


def test_calculation_not_applicable_is_explicitly_admissible() -> None:
    reconciler = FakeReconciler(calculation_status=SecCalculationStatus.NOT_APPLICABLE)

    result = service(reconciler).execute(
        candidate_set=candidate_set(processor_fact()),
        request=revenue_request(),
    )

    assert result.status is SecFactAdmissionStatus.ADMITTED


class FakeInspector:
    def __init__(
        self,
        *,
        parent: Decimal | None,
        components: tuple[SecCalculationComponent, ...],
        complete: bool = True,
    ) -> None:
        self.parent = parent
        self.components = components
        self.complete = complete

    def inspect(
        self,
        *,
        candidate: SecXbrlCandidate,
        candidate_set: SecXbrlCandidateSet,
    ) -> SecStatementObservation:
        assert candidate_set.source_document_id == candidate.source_document_id
        value = Decimal(candidate.raw_value)
        return SecStatementObservation(
            candidate_id=candidate.candidate_id,
            statement_present=True,
            statement_role_uri="http://example.com/role/IncomeStatement",
            statement_locator="income-statement#line-1",
            statement_value=value,
            calculation_parent_value=self.parent,
            calculation_components=self.components,
            calculation_relationship_complete=self.complete,
            inspector_name="fixture-relationship-inspector",
            inspector_version="1.0.0",
        )


def test_aie_owned_reconciler_computes_calculation_consistency() -> None:
    facts = candidate_set(processor_fact(raw_value="100"))
    reconciler = DeterministicSecFactReconciler(
        FakeInspector(
            parent=Decimal("100"),
            components=(
                SecCalculationComponent(value=Decimal("70"), weight=Decimal("1")),
                SecCalculationComponent(value=Decimal("30"), weight=Decimal("1")),
            ),
        )
    )

    result = reconciler.reconcile(candidate=facts.candidates[0], candidate_set=facts)

    assert result.calculation_status is SecCalculationStatus.CONSISTENT
    assert result.reconciler_name == "aie-sec-deterministic-reconciler"
    assert result.inspector_name == "fixture-relationship-inspector"


@pytest.mark.parametrize(
    ("inspector", "expected_status"),
    [
        (
            FakeInspector(parent=None, components=()),
            SecCalculationStatus.NOT_APPLICABLE,
        ),
        (
            FakeInspector(
                parent=Decimal("100"),
                components=(
                    SecCalculationComponent(value=Decimal("99"), weight=Decimal("1")),
                ),
            ),
            SecCalculationStatus.INCONSISTENT,
        ),
        (
            FakeInspector(parent=Decimal("100"), components=(), complete=False),
            SecCalculationStatus.UNKNOWN,
        ),
    ],
)
def test_aie_owned_reconciler_preserves_fail_closed_calculation_states(
    inspector: FakeInspector,
    expected_status: SecCalculationStatus,
) -> None:
    facts = candidate_set(processor_fact(raw_value="100"))
    result = DeterministicSecFactReconciler(inspector).reconcile(
        candidate=facts.candidates[0],
        candidate_set=facts,
    )

    assert result.calculation_status is expected_status


def test_aie_owned_reconciler_can_drive_end_to_end_fact_admission() -> None:
    facts = candidate_set(processor_fact(raw_value="1000000000"))
    reconciler = DeterministicSecFactReconciler(
        FakeInspector(parent=None, components=())
    )

    result = service(reconciler).execute(candidate_set=facts, request=revenue_request())

    assert result.status is SecFactAdmissionStatus.ADMITTED
    assert result.bundle is not None
    assert result.bundle.financial_fact.value == Decimal("1000")


def test_unreviewed_extraction_version_cannot_cross_into_underwriting() -> None:
    facts = candidate_set(processor_fact())
    unreviewed = replace(facts, extraction_version="sec-xbrl-shadow-v2")

    with pytest.raises(ValueError, match="unsupported extraction version"):
        service().execute(candidate_set=unreviewed, request=revenue_request())


def test_candidate_payload_tampering_cannot_cross_into_underwriting() -> None:
    facts = candidate_set(processor_fact())
    tampered_candidate = replace(facts.candidates[0], raw_value="999000000000")
    tampered_set = replace(facts, candidates=(tampered_candidate,))

    with pytest.raises(SecXbrlExtractionError, match="content address"):
        service().execute(candidate_set=tampered_set, request=revenue_request())


def test_verified_source_identity_must_match_the_content_addressed_candidate_set() -> None:
    facts = candidate_set(processor_fact())
    wrong_accession_repository = FakeRepository(
        document=source_document(provider_version="0000320193-24-999999")
    )

    with pytest.raises(ValueError, match="accession"):
        service(repository=wrong_accession_repository).execute(
            candidate_set=facts,
            request=revenue_request(),
        )


def test_tampered_source_bytes_fail_the_canonical_integrity_gate() -> None:
    facts = candidate_set(processor_fact())
    repository = FakeRepository(content=b"tampered filing bytes")

    with pytest.raises(SourceDocumentIntegrityError):
        service(repository=repository).execute(
            candidate_set=facts,
            request=revenue_request(),
        )
