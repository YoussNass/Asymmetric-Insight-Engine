"""Fail-closed Chapter 11C admission of reconciled SEC XBRL candidates into Underwriting facts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from hashlib import sha256
from typing import Protocol
from uuid import NAMESPACE_URL, uuid5

from asymmetric_engine.application.evidence_ingestion import SourceDocumentRepository
from asymmetric_engine.application.sec_xbrl_extraction import (
    SecXbrlAuthority,
    SecXbrlCandidate,
    SecXbrlCandidateSet,
    SecXbrlPeriodKind,
    validate_sec_xbrl_candidate_set_integrity,
)
from asymmetric_engine.application.source_verification import load_verified_source_document
from asymmetric_engine.domain.evidence import (
    Claim,
    ClaimType,
    Confidence,
    ConfidenceCalibrationStatus,
    DataQuality,
    EvidenceItem,
)
from asymmetric_engine.domain.financial import CurrencyCode
from asymmetric_engine.domain.opportunity.models import (
    FinancialFact,
    FinancialFactBasis,
    FinancialMetric,
    FinancialPeriod,
    FinancialPeriodKind,
    FinancialUnit,
)

_US_GAAP_NAMESPACE = re.compile(r"^https?://fasb\.org/us-gaap/[0-9]{4}(?:q[1-4])?/?$")
_ISO_CURRENCY_MEASURE = re.compile(
    r"^(?:\{http://www\.xbrl\.org/2003/iso4217\}|iso4217:)([A-Z]{3})$"
)
_SHARES_MEASURES = frozenset(
    {
        "{http://www.xbrl.org/2003/instance}shares",
        "xbrli:shares",
    }
)
_MAPPING_VERSION = "sec-canonical-fact-mapping-v1"
_RECONCILIATION_VERSION = "sec-statement-reconciliation-v1"
_SUPPORTED_EXTRACTION_VERSION = "sec-xbrl-shadow-v1"
_MILLION = Decimal("1000000")
_STRICTLY_POSITIVE_ADMISSION_METRICS = {
    FinancialMetric.REVENUE,
    FinancialMetric.DILUTED_WEIGHTED_AVERAGE_SHARES,
}
_NON_NEGATIVE_ADMISSION_METRICS = {
    FinancialMetric.CAPITAL_EXPENDITURES,
    FinancialMetric.SHARE_BASED_COMPENSATION,
}


class SecFactAdmissionStatus(StrEnum):
    """Explicit outcome of one requested canonical metric admission."""

    ADMITTED = "admitted"
    UNSUPPORTED = "unsupported"
    MISSING = "missing"
    AMBIGUOUS = "ambiguous"
    CONFLICT = "conflict"
    RECONCILIATION_FAILED = "reconciliation_failed"


class SecCalculationStatus(StrEnum):
    """How the selected fact relates to available filing calculation relationships."""

    CONSISTENT = "consistent"
    NOT_APPLICABLE = "not_applicable"
    INCONSISTENT = "inconsistent"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class SecCalculationComponent:
    """One raw calculation-network child value and weight observed for a statement fact."""

    value: Decimal
    weight: Decimal


@dataclass(frozen=True, slots=True)
class SecStatementObservation:
    """Untrusted low-level presentation/calculation observation supplied to AIE reconciliation."""

    candidate_id: str
    statement_present: bool
    statement_role_uri: str
    statement_locator: str
    statement_value: Decimal
    calculation_parent_value: Decimal | None
    calculation_components: tuple[SecCalculationComponent, ...]
    calculation_relationship_complete: bool
    inspector_name: str
    inspector_version: str


class SecStatementInspector(Protocol):
    """Replaceable standards-layer inspector that exposes raw statement relationships only."""

    def inspect(
        self,
        *,
        candidate: SecXbrlCandidate,
        candidate_set: SecXbrlCandidateSet,
    ) -> SecStatementObservation:
        """Return raw presentation and calculation observations without admission authority."""


@dataclass(frozen=True, slots=True)
class SecCandidateReconciliation:
    """AIE-owned statement/calculation reconciliation evidence for one exact candidate."""

    candidate_id: str
    statement_present: bool
    statement_role_uri: str
    statement_locator: str
    statement_value: Decimal
    calculation_status: SecCalculationStatus
    calculation_detail: str
    reconciler_name: str
    reconciler_version: str
    inspector_name: str
    inspector_version: str
    reconciliation_version: str = _RECONCILIATION_VERSION


class SecFactReconciler(Protocol):
    """Reconciliation contract consumed by canonical fact admission."""

    def reconcile(
        self,
        *,
        candidate: SecXbrlCandidate,
        candidate_set: SecXbrlCandidateSet,
    ) -> SecCandidateReconciliation:
        """Reconcile the exact candidate against the exact filing statements and calculations."""


class DeterministicSecFactReconciler:
    """Own presentation/calculation consistency decisions over raw standards-layer observations."""

    reconciler_name = "aie-sec-deterministic-reconciler"
    reconciler_version = "1.0.0"

    def __init__(self, inspector: SecStatementInspector) -> None:
        self._inspector = inspector

    @staticmethod
    def _calculation_status(
        observation: SecStatementObservation,
    ) -> tuple[SecCalculationStatus, str]:
        if not observation.calculation_relationship_complete:
            return (
                SecCalculationStatus.UNKNOWN,
                "Calculation relationship observation is incomplete.",
            )
        parent = observation.calculation_parent_value
        components = observation.calculation_components
        if parent is None and not components:
            return (
                SecCalculationStatus.NOT_APPLICABLE,
                "No calculation relationship is declared for the statement fact.",
            )
        if parent is None or not components:
            return (
                SecCalculationStatus.UNKNOWN,
                "Calculation relationship is structurally incomplete.",
            )
        weighted_sum = sum(
            (component.value * component.weight for component in components),
            start=Decimal("0"),
        )
        if parent == observation.statement_value and weighted_sum == parent:
            return (
                SecCalculationStatus.CONSISTENT,
                f"Weighted calculation children reconcile exactly to {parent}.",
            )
        return (
            SecCalculationStatus.INCONSISTENT,
            f"Calculation parent={parent} weighted_children={weighted_sum} "
            f"statement={observation.statement_value}.",
        )

    def reconcile(
        self,
        *,
        candidate: SecXbrlCandidate,
        candidate_set: SecXbrlCandidateSet,
    ) -> SecCandidateReconciliation:
        observation = self._inspector.inspect(
            candidate=candidate,
            candidate_set=candidate_set,
        )
        status, detail = self._calculation_status(observation)
        return SecCandidateReconciliation(
            candidate_id=observation.candidate_id,
            statement_present=observation.statement_present,
            statement_role_uri=observation.statement_role_uri,
            statement_locator=observation.statement_locator,
            statement_value=observation.statement_value,
            calculation_status=status,
            calculation_detail=detail,
            reconciler_name=self.reconciler_name,
            reconciler_version=self.reconciler_version,
            inspector_name=observation.inspector_name,
            inspector_version=observation.inspector_version,
        )


@dataclass(frozen=True, slots=True)
class SecCanonicalMetricRule:
    """Versioned exact concept vocabulary for one directly reported Underwriting metric."""

    metric: FinancialMetric
    concept_names: tuple[str, ...]
    unit: FinancialUnit
    period_kind: FinancialPeriodKind


_RULES = {
    FinancialMetric.REVENUE: SecCanonicalMetricRule(
        metric=FinancialMetric.REVENUE,
        concept_names=(
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "Revenues",
            "SalesRevenueNet",
        ),
        unit=FinancialUnit.MONEY_MILLIONS,
        period_kind=FinancialPeriodKind.DURATION,
    ),
    FinancialMetric.GROSS_PROFIT: SecCanonicalMetricRule(
        metric=FinancialMetric.GROSS_PROFIT,
        concept_names=("GrossProfit",),
        unit=FinancialUnit.MONEY_MILLIONS,
        period_kind=FinancialPeriodKind.DURATION,
    ),
    FinancialMetric.OPERATING_INCOME: SecCanonicalMetricRule(
        metric=FinancialMetric.OPERATING_INCOME,
        concept_names=("OperatingIncomeLoss",),
        unit=FinancialUnit.MONEY_MILLIONS,
        period_kind=FinancialPeriodKind.DURATION,
    ),
    FinancialMetric.NET_INCOME: SecCanonicalMetricRule(
        metric=FinancialMetric.NET_INCOME,
        concept_names=("NetIncomeLoss",),
        unit=FinancialUnit.MONEY_MILLIONS,
        period_kind=FinancialPeriodKind.DURATION,
    ),
    FinancialMetric.OPERATING_CASH_FLOW: SecCanonicalMetricRule(
        metric=FinancialMetric.OPERATING_CASH_FLOW,
        concept_names=("NetCashProvidedByUsedInOperatingActivities",),
        unit=FinancialUnit.MONEY_MILLIONS,
        period_kind=FinancialPeriodKind.DURATION,
    ),
    FinancialMetric.CAPITAL_EXPENDITURES: SecCanonicalMetricRule(
        metric=FinancialMetric.CAPITAL_EXPENDITURES,
        concept_names=("PaymentsToAcquirePropertyPlantAndEquipment",),
        unit=FinancialUnit.MONEY_MILLIONS,
        period_kind=FinancialPeriodKind.DURATION,
    ),
    FinancialMetric.DILUTED_WEIGHTED_AVERAGE_SHARES: SecCanonicalMetricRule(
        metric=FinancialMetric.DILUTED_WEIGHTED_AVERAGE_SHARES,
        concept_names=("WeightedAverageNumberOfDilutedSharesOutstanding",),
        unit=FinancialUnit.SHARES_MILLIONS,
        period_kind=FinancialPeriodKind.DURATION,
    ),
    FinancialMetric.SHARE_BASED_COMPENSATION: SecCanonicalMetricRule(
        metric=FinancialMetric.SHARE_BASED_COMPENSATION,
        concept_names=("ShareBasedCompensation",),
        unit=FinancialUnit.MONEY_MILLIONS,
        period_kind=FinancialPeriodKind.DURATION,
    ),
}


@dataclass(frozen=True, slots=True)
class SecFactAdmissionRequest:
    """One explicit metric/period request; fiscal scope is never inferred from XBRL duration."""

    metric: FinancialMetric
    period: FinancialPeriod
    expected_currency: CurrencyCode | None = None


@dataclass(frozen=True, slots=True)
class SecAdmittedFactBundle:
    """Canonical source-to-evidence-to-claim-to-financial-fact handoff for Underwriting."""

    candidate_id: str
    mapping_version: str
    reconciliation: SecCandidateReconciliation
    evidence: EvidenceItem
    claim: Claim
    financial_fact: FinancialFact


@dataclass(frozen=True, slots=True)
class SecFactAdmissionResult:
    """Explicit admission result that preserves ambiguity and conflict instead of guessing."""

    status: SecFactAdmissionStatus
    metric: FinancialMetric
    period: FinancialPeriod
    considered_candidate_ids: tuple[str, ...]
    reasons: tuple[str, ...]
    bundle: SecAdmittedFactBundle | None = None


class AdmitSecReportedFact:
    """Admit only one exact, standard-taxonomy, consolidated, reconciled SEC fact."""

    def __init__(
        self,
        *,
        repository: SourceDocumentRepository,
        reconciler: SecFactReconciler,
    ) -> None:
        self._repository = repository
        self._reconciler = reconciler

    @staticmethod
    def _candidate_matches_period(candidate: SecXbrlCandidate, period: FinancialPeriod) -> bool:
        if period.kind is FinancialPeriodKind.INSTANT:
            return (
                candidate.period_kind is SecXbrlPeriodKind.INSTANT
                and candidate.period_start is None
                and candidate.period_end == period.end_date
            )
        return (
            candidate.period_kind is SecXbrlPeriodKind.DURATION
            and candidate.period_start == period.start_date
            and candidate.period_end == period.end_date
        )

    @staticmethod
    def _parse_decimal(candidate: SecXbrlCandidate) -> Decimal:
        if not candidate.is_numeric or candidate.is_nil:
            raise ValueError("candidate is not a non-nil numeric fact")
        try:
            value = Decimal(candidate.raw_value.strip())
        except (InvalidOperation, ValueError) as error:
            raise ValueError("candidate raw value is not a finite decimal") from error
        if not value.is_finite():
            raise ValueError("candidate raw value is not a finite decimal")
        return value

    @staticmethod
    def _currency(candidate: SecXbrlCandidate) -> str:
        if candidate.unit_denominator or len(candidate.unit_numerator) != 1:
            raise ValueError("monetary candidate requires one non-divided ISO currency measure")
        match = _ISO_CURRENCY_MEASURE.fullmatch(candidate.unit_numerator[0])
        if match is None:
            raise ValueError("monetary candidate unit is not an ISO currency measure")
        return match.group(1)

    @staticmethod
    def _require_shares(candidate: SecXbrlCandidate) -> None:
        if candidate.unit_denominator or tuple(candidate.unit_numerator) not in {
            (measure,) for measure in _SHARES_MEASURES
        }:
            raise ValueError("share candidate unit is not xbrli:shares")

    @staticmethod
    def _validate_metric_value(metric: FinancialMetric, value: Decimal) -> None:
        if metric in _STRICTLY_POSITIVE_ADMISSION_METRICS and value <= 0:
            raise ValueError(f"{metric.value} must be greater than zero")
        if metric in _NON_NEGATIVE_ADMISSION_METRICS and value < 0:
            raise ValueError(f"{metric.value} cannot be negative")

    @classmethod
    def _normalize_value(
        cls,
        *,
        candidate: SecXbrlCandidate,
        rule: SecCanonicalMetricRule,
        expected_currency: str | None,
    ) -> tuple[Decimal, str | None]:
        raw_value = cls._parse_decimal(candidate)
        cls._validate_metric_value(rule.metric, raw_value)
        if rule.unit is FinancialUnit.MONEY_MILLIONS:
            currency = cls._currency(candidate)
            if expected_currency is not None and currency != expected_currency:
                raise ValueError(
                    f"candidate currency {currency} does not match expected {expected_currency}"
                )
            return raw_value / _MILLION, currency
        if expected_currency is not None:
            raise ValueError("share metrics cannot declare expected_currency")
        cls._require_shares(candidate)
        return raw_value / _MILLION, None

    @staticmethod
    def _reconciliation_is_admissible(
        reconciliation: SecCandidateReconciliation,
        *,
        candidate: SecXbrlCandidate,
        raw_value: Decimal,
    ) -> tuple[bool, tuple[str, ...]]:
        reasons: list[str] = []
        if reconciliation.candidate_id != candidate.candidate_id:
            reasons.append("reconciliation_candidate_mismatch")
        if reconciliation.reconciliation_version != _RECONCILIATION_VERSION:
            reasons.append("unsupported_reconciliation_version")
        if not reconciliation.statement_present:
            reasons.append("candidate_not_presented_on_reconciled_statement")
        if not reconciliation.statement_role_uri.strip():
            reasons.append("missing_statement_role")
        if not reconciliation.statement_locator.strip():
            reasons.append("missing_statement_locator")
        if not reconciliation.reconciler_name.strip() or not reconciliation.reconciler_version.strip():
            reasons.append("missing_reconciler_identity")
        if not reconciliation.inspector_name.strip() or not reconciliation.inspector_version.strip():
            reasons.append("missing_statement_inspector_identity")
        if not reconciliation.calculation_detail.strip():
            reasons.append("missing_calculation_detail")
        if reconciliation.statement_value != raw_value:
            reasons.append("statement_value_conflict")
        if reconciliation.calculation_status not in {
            SecCalculationStatus.CONSISTENT,
            SecCalculationStatus.NOT_APPLICABLE,
        }:
            reasons.append(f"calculation_{reconciliation.calculation_status.value}")
        return (not reasons, tuple(reasons))

    @staticmethod
    def _lineage_hash(
        *,
        candidate: SecXbrlCandidate,
        reconciliation: SecCandidateReconciliation,
        metric: FinancialMetric,
        period: FinancialPeriod,
        normalized_value: Decimal,
        currency: str | None,
    ) -> str:
        payload = {
            "candidate_id": candidate.candidate_id,
            "mapping_version": _MAPPING_VERSION,
            "reconciliation_version": reconciliation.reconciliation_version,
            "reconciler_name": reconciliation.reconciler_name,
            "reconciler_version": reconciliation.reconciler_version,
            "inspector_name": reconciliation.inspector_name,
            "inspector_version": reconciliation.inspector_version,
            "statement_role_uri": reconciliation.statement_role_uri,
            "statement_locator": reconciliation.statement_locator,
            "calculation_status": reconciliation.calculation_status.value,
            "metric": metric.value,
            "period": {
                "kind": period.kind.value,
                "start_date": period.start_date.isoformat() if period.start_date else None,
                "end_date": period.end_date.isoformat(),
                "duration_scope": period.duration_scope.value if period.duration_scope else None,
            },
            "normalized_value": str(normalized_value),
            "currency": currency,
        }
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        return sha256(canonical).hexdigest()

    def execute(
        self,
        *,
        candidate_set: SecXbrlCandidateSet,
        request: SecFactAdmissionRequest,
    ) -> SecFactAdmissionResult:
        """Map and reconcile one requested metric without heuristics or hidden period inference."""

        rule = _RULES.get(request.metric)
        if rule is None:
            return SecFactAdmissionResult(
                status=SecFactAdmissionStatus.UNSUPPORTED,
                metric=request.metric,
                period=request.period,
                considered_candidate_ids=(),
                reasons=("metric_not_in_sec_canonical_mapping_v1",),
            )
        if request.period.kind is not rule.period_kind:
            return SecFactAdmissionResult(
                status=SecFactAdmissionStatus.CONFLICT,
                metric=request.metric,
                period=request.period,
                considered_candidate_ids=(),
                reasons=("requested_period_kind_conflicts_with_metric",),
            )
        if candidate_set.authority is not SecXbrlAuthority.SHADOW_ONLY:
            raise ValueError("Chapter 11C requires a shadow-only candidate set")
        if candidate_set.extraction_version != _SUPPORTED_EXTRACTION_VERSION:
            raise ValueError("Chapter 11C received an unsupported extraction version")
        validate_sec_xbrl_candidate_set_integrity(candidate_set)

        document = load_verified_source_document(
            self._repository,
            candidate_set.source_document_id,
        )
        if document.document_id != candidate_set.source_document_id:
            raise ValueError("candidate set source document identity drifted")
        if document.content_hash != candidate_set.source_content_hash:
            raise ValueError("candidate set source hash does not match verified evidence")
        if document.provider_version != candidate_set.accession:
            raise ValueError("candidate set accession does not match verified evidence")

        mapped = tuple(
            candidate
            for candidate in candidate_set.candidates
            if _US_GAAP_NAMESPACE.fullmatch(candidate.concept_namespace)
            and candidate.concept_name in rule.concept_names
            and self._candidate_matches_period(candidate, request.period)
            and not candidate.dimensions
        )
        if not mapped:
            return SecFactAdmissionResult(
                status=SecFactAdmissionStatus.MISSING,
                metric=request.metric,
                period=request.period,
                considered_candidate_ids=(),
                reasons=("no_exact_consolidated_standard_taxonomy_candidate",),
            )

        normalized: list[tuple[SecXbrlCandidate, Decimal, str | None, Decimal]] = []
        conflicts: list[str] = []
        for candidate in mapped:
            try:
                raw_value = self._parse_decimal(candidate)
                value, currency = self._normalize_value(
                    candidate=candidate,
                    rule=rule,
                    expected_currency=request.expected_currency,
                )
            except ValueError as error:
                conflicts.append(f"{candidate.candidate_id}:{error}")
                continue
            normalized.append((candidate, value, currency, raw_value))

        considered = tuple(candidate.candidate_id for candidate in mapped)
        if conflicts:
            return SecFactAdmissionResult(
                status=SecFactAdmissionStatus.CONFLICT,
                metric=request.metric,
                period=request.period,
                considered_candidate_ids=considered,
                reasons=tuple(sorted(conflicts)),
            )
        if len(normalized) != 1:
            return SecFactAdmissionResult(
                status=SecFactAdmissionStatus.AMBIGUOUS,
                metric=request.metric,
                period=request.period,
                considered_candidate_ids=considered,
                reasons=("multiple_exact_candidates_require_explicit_mapping_revision",),
            )

        candidate, value, currency, raw_value = normalized[0]
        reconciliation = self._reconciler.reconcile(
            candidate=candidate,
            candidate_set=candidate_set,
        )
        admissible, reconciliation_reasons = self._reconciliation_is_admissible(
            reconciliation,
            candidate=candidate,
            raw_value=raw_value,
        )
        if not admissible:
            return SecFactAdmissionResult(
                status=SecFactAdmissionStatus.RECONCILIATION_FAILED,
                metric=request.metric,
                period=request.period,
                considered_candidate_ids=(candidate.candidate_id,),
                reasons=reconciliation_reasons,
            )

        lineage_hash = self._lineage_hash(
            candidate=candidate,
            reconciliation=reconciliation,
            metric=request.metric,
            period=request.period,
            normalized_value=value,
            currency=currency,
        )
        evidence_id = uuid5(
            NAMESPACE_URL,
            f"asymmetric-insight-engine:sec-evidence:{lineage_hash}",
        )
        claim_id = uuid5(
            NAMESPACE_URL,
            f"asymmetric-insight-engine:sec-claim:{lineage_hash}",
        )
        source_locator = f"{candidate.source_locator}|statement:{reconciliation.statement_locator}"
        extraction_method = (
            f"{candidate.extraction_method}@{candidate.extraction_version};"
            f"{_MAPPING_VERSION};{reconciliation.reconciler_name}@"
            f"{reconciliation.reconciler_version};{reconciliation.inspector_name}@"
            f"{reconciliation.inspector_version};{reconciliation.reconciliation_version}"
        )
        evidence = EvidenceItem(
            evidence_id=evidence_id,
            title=f"SEC reported {request.metric.value} from accession {candidate.accession}",
            source_uri=document.source_uri,
            source_type=document.source_type,
            effective_at=document.effective_at,
            available_at=document.available_at,
            recorded_at=document.recorded_at,
            content_hash=lineage_hash,
            quality=DataQuality(
                coverage=1.0,
                source_reliability=1.0,
                point_in_time_integrity=1.0,
            ),
            source_document_id=document.document_id,
            source_locator=source_locator,
            extraction_method=extraction_method,
        )
        unit_text = currency if currency is not None else "shares"
        claim = Claim(
            claim_id=claim_id,
            text=(
                f"SEC accession {candidate.accession} reports {request.metric.value} as "
                f"{value} million {unit_text} for the explicitly reconciled period ending "
                f"{request.period.end_date.isoformat()}."
            ),
            claim_type=ClaimType.OBSERVATION,
            evidence_ids=(evidence.evidence_id,),
            confidence=Confidence(
                score=1.0,
                rationale=(
                    "Deterministic transcription from one exact standard-taxonomy candidate that "
                    "passed statement and calculation reconciliation; not a probabilistic forecast."
                ),
                calibration_status=ConfidenceCalibrationStatus.UNCALIBRATED,
            ),
            invalidation_condition=(
                "Invalidate if source bytes, extraction version, mapping version, statement "
                "reconciliation, unit, or accession identity changes."
            ),
        )
        financial_fact = FinancialFact(
            fact_id=f"sec.{request.metric.value}.{lineage_hash[:16]}",
            metric=request.metric,
            value=value,
            unit=rule.unit,
            currency=currency,
            period=request.period,
            basis=FinancialFactBasis.REPORTED,
            claim_ids=(claim.claim_id,),
        )
        return SecFactAdmissionResult(
            status=SecFactAdmissionStatus.ADMITTED,
            metric=request.metric,
            period=request.period,
            considered_candidate_ids=(candidate.candidate_id,),
            reasons=(),
            bundle=SecAdmittedFactBundle(
                candidate_id=candidate.candidate_id,
                mapping_version=_MAPPING_VERSION,
                reconciliation=reconciliation,
                evidence=evidence,
                claim=claim,
                financial_fact=financial_fact,
            ),
        )
