"""Canonical standalone opportunity state owned by Investment Underwriting."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Self, cast
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from asymmetric_engine.domain.causal import (
    CausalAnalysis,
    CausalNodeKind,
    CausalReadiness,
)
from asymmetric_engine.domain.evidence import (
    Claim,
    ClaimType,
    EvidenceItem,
    SourceDocument,
)
from asymmetric_engine.domain.evidence.models import ContentHash, NonEmptyString
from asymmetric_engine.domain.evidence.source_documents import SubjectId
from asymmetric_engine.domain.temporal import KnowledgeBoundary, KnowledgeMode

UnderwritingObjectId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        pattern=r"^[a-z][a-z0-9_.:-]*$",
    ),
]
ThesisSummary = Annotated[str, StringConstraints(strip_whitespace=True, min_length=20)]

_DECIMAL_TOLERANCE = Decimal("0.000000001")
_OBSERVED_CLAIM_TYPES = {ClaimType.OBSERVATION, ClaimType.STATISTICAL_RESULT}
_INTERPRETIVE_CLAIM_TYPES = {
    ClaimType.INFERENCE,
    ClaimType.HYPOTHESIS,
    ClaimType.QUALITATIVE_JUDGEMENT,
}


def _is_close(actual: Decimal, expected: Decimal) -> bool:
    return abs(actual - expected) <= _DECIMAL_TOLERANCE


def _reject_duplicates(value: tuple[object, ...], *, message: str) -> tuple[object, ...]:
    if len(value) != len(set(value)):
        raise ValueError(message)
    return value


class OpportunityStatus(StrEnum):
    """Standalone research readiness; none of these states allocates capital."""

    INVESTIGATE = "investigate"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    READY_FOR_PORTFOLIO_REVIEW = "ready_for_portfolio_review"
    INVALIDATED = "invalidated"


class FinancialUnit(StrEnum):
    """Explicit units used by the first normalized-facts slice."""

    USD_MILLIONS = "usd_millions"
    SHARES_MILLIONS = "shares_millions"
    USD_PER_SHARE = "usd_per_share"
    RATIO = "ratio"


class FinancialPeriodKind(StrEnum):
    """Whether a fact applies at an instant or over a duration."""

    INSTANT = "instant"
    DURATION = "duration"


class FinancialPeriod(BaseModel):
    """Fiscal period attached to a normalized financial fact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: FinancialPeriodKind
    end_date: date
    start_date: date | None = None

    @model_validator(mode="after")
    def validate_period_shape(self) -> Self:
        if self.kind is FinancialPeriodKind.INSTANT and self.start_date is not None:
            raise ValueError("instant financial periods cannot declare start_date")
        if self.kind is FinancialPeriodKind.DURATION:
            if self.start_date is None:
                raise ValueError("duration financial periods require start_date")
            if self.start_date >= self.end_date:
                raise ValueError("financial period start_date must precede end_date")
        return self


class FinancialMetric(StrEnum):
    """Reported or analyst-adjusted inputs admitted by Chapter 5."""

    REVENUE = "revenue"
    GROSS_PROFIT = "gross_profit"
    OPERATING_INCOME = "operating_income"
    NET_INCOME = "net_income"
    OPERATING_CASH_FLOW = "operating_cash_flow"
    CAPITAL_EXPENDITURES = "capital_expenditures"
    CASH_AND_INVESTMENTS = "cash_and_investments"
    TOTAL_DEBT = "total_debt"
    DILUTED_SHARES = "diluted_shares"
    SHARE_BASED_COMPENSATION = "share_based_compensation"
    NORMALIZED_NOPAT = "normalized_nopat"
    AVERAGE_INVESTED_CAPITAL = "average_invested_capital"
    REFERENCE_SHARE_PRICE = "reference_share_price"


class FinancialFactBasis(StrEnum):
    """Whether a fact is directly reported or explicitly adjusted by the analyst."""

    REPORTED = "reported"
    ANALYST_ADJUSTED = "analyst_adjusted"


_METRIC_UNITS = {
    FinancialMetric.REVENUE: FinancialUnit.USD_MILLIONS,
    FinancialMetric.GROSS_PROFIT: FinancialUnit.USD_MILLIONS,
    FinancialMetric.OPERATING_INCOME: FinancialUnit.USD_MILLIONS,
    FinancialMetric.NET_INCOME: FinancialUnit.USD_MILLIONS,
    FinancialMetric.OPERATING_CASH_FLOW: FinancialUnit.USD_MILLIONS,
    FinancialMetric.CAPITAL_EXPENDITURES: FinancialUnit.USD_MILLIONS,
    FinancialMetric.CASH_AND_INVESTMENTS: FinancialUnit.USD_MILLIONS,
    FinancialMetric.TOTAL_DEBT: FinancialUnit.USD_MILLIONS,
    FinancialMetric.DILUTED_SHARES: FinancialUnit.SHARES_MILLIONS,
    FinancialMetric.SHARE_BASED_COMPENSATION: FinancialUnit.USD_MILLIONS,
    FinancialMetric.NORMALIZED_NOPAT: FinancialUnit.USD_MILLIONS,
    FinancialMetric.AVERAGE_INVESTED_CAPITAL: FinancialUnit.USD_MILLIONS,
    FinancialMetric.REFERENCE_SHARE_PRICE: FinancialUnit.USD_PER_SHARE,
}
_INSTANT_METRICS = {
    FinancialMetric.CASH_AND_INVESTMENTS,
    FinancialMetric.TOTAL_DEBT,
    FinancialMetric.REFERENCE_SHARE_PRICE,
}
_STRICTLY_POSITIVE_METRICS = {
    FinancialMetric.REVENUE,
    FinancialMetric.DILUTED_SHARES,
    FinancialMetric.AVERAGE_INVESTED_CAPITAL,
    FinancialMetric.REFERENCE_SHARE_PRICE,
}
_NON_NEGATIVE_METRICS = {
    FinancialMetric.CAPITAL_EXPENDITURES,
    FinancialMetric.CASH_AND_INVESTMENTS,
    FinancialMetric.TOTAL_DEBT,
    FinancialMetric.SHARE_BASED_COMPENSATION,
}


class FinancialFact(BaseModel):
    """One normalized financial input with claim-level provenance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fact_id: UnderwritingObjectId
    metric: FinancialMetric
    value: Decimal
    unit: FinancialUnit
    period: FinancialPeriod
    basis: FinancialFactBasis
    claim_ids: tuple[UUID, ...] = Field(min_length=1)
    normalization_note: NonEmptyString | None = None

    @field_validator("claim_ids")
    @classmethod
    def reject_duplicate_claims(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        return cast(
            tuple[UUID, ...],
            _reject_duplicates(value, message="duplicate financial fact claim_ids are not allowed"),
        )

    @model_validator(mode="after")
    def validate_metric_semantics(self) -> Self:
        if self.unit is not _METRIC_UNITS[self.metric]:
            raise ValueError(
                f"{self.metric.value} requires unit {_METRIC_UNITS[self.metric].value}"
            )
        expected_kind = (
            FinancialPeriodKind.INSTANT
            if self.metric in _INSTANT_METRICS
            else FinancialPeriodKind.DURATION
        )
        if self.period.kind is not expected_kind:
            raise ValueError(f"{self.metric.value} requires a {expected_kind.value} period")
        if self.metric in _STRICTLY_POSITIVE_METRICS and self.value <= 0:
            raise ValueError(f"{self.metric.value} must be greater than zero")
        if self.metric in _NON_NEGATIVE_METRICS and self.value < 0:
            raise ValueError(f"{self.metric.value} cannot be negative")
        if self.basis is FinancialFactBasis.ANALYST_ADJUSTED and self.normalization_note is None:
            raise ValueError("analyst-adjusted facts require normalization_note")
        if self.basis is FinancialFactBasis.REPORTED and self.normalization_note is not None:
            raise ValueError("reported facts cannot declare an analyst normalization_note")
        return self


class DerivedMetric(StrEnum):
    """Transparent calculations derived from normalized fact inputs."""

    REVENUE_GROWTH = "revenue_growth"
    GROSS_MARGIN = "gross_margin"
    FREE_CASH_FLOW = "free_cash_flow"
    NET_DEBT = "net_debt"
    DILUTED_SHARE_GROWTH = "diluted_share_growth"
    RETURN_ON_INVESTED_CAPITAL = "return_on_invested_capital"


class FinancialFormula(StrEnum):
    """Versioned formula identity, separate from the resulting metric."""

    CURRENT_MINUS_PRIOR_OVER_PRIOR = "current_minus_prior_over_prior"
    GROSS_PROFIT_OVER_REVENUE = "gross_profit_over_revenue"
    OPERATING_CASH_FLOW_MINUS_CAPEX = "operating_cash_flow_minus_capex"
    DEBT_MINUS_CASH = "debt_minus_cash"
    NOPAT_OVER_AVERAGE_INVESTED_CAPITAL = "nopat_over_average_invested_capital"


_DERIVED_UNITS = {
    DerivedMetric.REVENUE_GROWTH: FinancialUnit.RATIO,
    DerivedMetric.GROSS_MARGIN: FinancialUnit.RATIO,
    DerivedMetric.FREE_CASH_FLOW: FinancialUnit.USD_MILLIONS,
    DerivedMetric.NET_DEBT: FinancialUnit.USD_MILLIONS,
    DerivedMetric.DILUTED_SHARE_GROWTH: FinancialUnit.RATIO,
    DerivedMetric.RETURN_ON_INVESTED_CAPITAL: FinancialUnit.RATIO,
}
_DERIVED_FORMULAS = {
    DerivedMetric.REVENUE_GROWTH: FinancialFormula.CURRENT_MINUS_PRIOR_OVER_PRIOR,
    DerivedMetric.GROSS_MARGIN: FinancialFormula.GROSS_PROFIT_OVER_REVENUE,
    DerivedMetric.FREE_CASH_FLOW: FinancialFormula.OPERATING_CASH_FLOW_MINUS_CAPEX,
    DerivedMetric.NET_DEBT: FinancialFormula.DEBT_MINUS_CASH,
    DerivedMetric.DILUTED_SHARE_GROWTH: FinancialFormula.CURRENT_MINUS_PRIOR_OVER_PRIOR,
    DerivedMetric.RETURN_ON_INVESTED_CAPITAL: (
        FinancialFormula.NOPAT_OVER_AVERAGE_INVESTED_CAPITAL
    ),
}


class DerivedFinancialFact(BaseModel):
    """A deterministic value whose ordered inputs and formula remain visible."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fact_id: UnderwritingObjectId
    metric: DerivedMetric
    value: Decimal
    unit: FinancialUnit
    formula: FinancialFormula
    input_fact_ids: tuple[UnderwritingObjectId, UnderwritingObjectId]
    calculation_version: NonEmptyString

    @model_validator(mode="after")
    def validate_formula_identity(self) -> Self:
        if self.unit is not _DERIVED_UNITS[self.metric]:
            raise ValueError(
                f"{self.metric.value} requires unit {_DERIVED_UNITS[self.metric].value}"
            )
        if self.formula is not _DERIVED_FORMULAS[self.metric]:
            raise ValueError(
                f"{self.metric.value} requires formula {_DERIVED_FORMULAS[self.metric].value}"
            )
        if self.input_fact_ids[0] == self.input_fact_ids[1]:
            raise ValueError("a derived fact requires two distinct input facts")
        return self


class UnderwritingDimensionKind(StrEnum):
    """Non-interchangeable dimensions of a standalone company assessment."""

    REVENUE_AND_MARGINS = "revenue_and_margins"
    CASH_GENERATION_AND_EARNINGS_QUALITY = "cash_generation_and_earnings_quality"
    RETURNS_ON_INVESTED_CAPITAL = "returns_on_invested_capital"
    BALANCE_SHEET_AND_CAPITAL_NEEDS = "balance_sheet_and_capital_needs"
    DILUTION_AND_PER_SHARE_ECONOMICS = "dilution_and_per_share_economics"
    VALUE_CAPTURE_AND_COMPETITION = "value_capture_and_competition"
    OPERATING_EXECUTION = "operating_execution"
    VALUATION_AND_ASYMMETRY = "valuation_and_asymmetry"


class DimensionOutcome(StrEnum):
    """Categorical evidence synthesis; deliberately not an ordinal score."""

    SUPPORTIVE = "supportive"
    MIXED = "mixed"
    ADVERSE = "adverse"
    UNKNOWN = "unknown"


class UnderwritingDimension(BaseModel):
    """One explained component of the standalone assessment."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: UnderwritingDimensionKind
    outcome: DimensionOutcome
    rationale: NonEmptyString
    claim_ids: tuple[UUID, ...] = Field(min_length=1)
    fact_ids: tuple[UnderwritingObjectId, ...] = ()
    missing_data: tuple[NonEmptyString, ...] = ()
    conflicts: tuple[NonEmptyString, ...] = ()
    assumptions: tuple[NonEmptyString, ...] = ()
    invalidation_conditions: tuple[NonEmptyString, ...] = ()

    @field_validator(
        "claim_ids",
        "fact_ids",
        "missing_data",
        "conflicts",
        "assumptions",
        "invalidation_conditions",
    )
    @classmethod
    def reject_duplicate_references(cls, value: tuple[object, ...]) -> tuple[object, ...]:
        return _reject_duplicates(value, message="duplicate dimension entries are not allowed")

    @model_validator(mode="after")
    def require_unknown_disclosure(self) -> Self:
        if self.outcome is DimensionOutcome.UNKNOWN and not self.missing_data:
            raise ValueError("unknown dimensions require explicit missing_data")
        return self


class EligibilityGateKind(StrEnum):
    """Fixed eligibility questions that precede any future portfolio comparison."""

    CAUSAL_HANDOFF = "causal_handoff"
    SURVIVABILITY = "survivability"
    ECONOMIC_VALUE_CAPTURE = "economic_value_capture"
    PER_SHARE_INTEGRITY = "per_share_integrity"
    VALUATION_COMPLETENESS = "valuation_completeness"
    FALSIFIABILITY = "falsifiability"


class GateResult(StrEnum):
    """Explicit categorical gate result."""

    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


class EligibilityGate(BaseModel):
    """Versioned, explained gate that cannot become a hidden weighted score."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: EligibilityGateKind
    result: GateResult
    rationale: NonEmptyString
    method_version: NonEmptyString
    claim_ids: tuple[UUID, ...] = ()
    missing_data: tuple[NonEmptyString, ...] = ()

    @field_validator("claim_ids", "missing_data")
    @classmethod
    def reject_duplicate_references(cls, value: tuple[object, ...]) -> tuple[object, ...]:
        return _reject_duplicates(
            value, message="duplicate eligibility-gate entries are not allowed"
        )

    @model_validator(mode="after")
    def require_non_pass_disclosure(self) -> Self:
        if self.result is GateResult.UNKNOWN and not self.missing_data:
            raise ValueError("unknown eligibility gates require explicit missing_data")
        return self


class ScenarioKind(StrEnum):
    """Named scenarios; no probability is implied by their order."""

    BEAR = "bear"
    BASE = "base"
    BULL = "bull"


class ValuationScenario(BaseModel):
    """Transparent enterprise-to-equity bridge and per-share return scenario."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: ScenarioKind
    method: NonEmptyString
    method_version: NonEmptyString
    enterprise_value_usd_millions: Decimal
    net_debt_usd_millions: Decimal
    equity_value_usd_millions: Decimal
    diluted_shares_millions: Decimal
    value_per_share_usd: Decimal
    reference_price_usd: Decimal
    return_from_reference: Decimal
    supporting_fact_ids: tuple[UnderwritingObjectId, ...] = Field(min_length=1)
    assumption_claim_ids: tuple[UUID, ...] = Field(min_length=1)
    rationale: NonEmptyString
    assumptions: tuple[NonEmptyString, ...] = Field(min_length=1)
    invalidation_conditions: tuple[NonEmptyString, ...] = Field(min_length=1)

    @field_validator(
        "supporting_fact_ids", "assumption_claim_ids", "assumptions", "invalidation_conditions"
    )
    @classmethod
    def reject_duplicate_entries(cls, value: tuple[object, ...]) -> tuple[object, ...]:
        return _reject_duplicates(
            value, message="duplicate valuation-scenario entries are not allowed"
        )

    @model_validator(mode="after")
    def validate_per_share_bridge(self) -> Self:
        if self.enterprise_value_usd_millions <= 0:
            raise ValueError("enterprise value must be greater than zero")
        if self.diluted_shares_millions <= 0 or self.reference_price_usd <= 0:
            raise ValueError("diluted shares and reference price must be greater than zero")
        expected_equity = self.enterprise_value_usd_millions - self.net_debt_usd_millions
        if expected_equity < 0:
            raise ValueError("scenario equity value cannot be negative")
        if not _is_close(self.equity_value_usd_millions, expected_equity):
            raise ValueError("equity value must equal enterprise value minus net debt")
        expected_per_share = expected_equity / self.diluted_shares_millions
        if not _is_close(self.value_per_share_usd, expected_per_share):
            raise ValueError("value per share must equal equity value divided by diluted shares")
        expected_return = expected_per_share / self.reference_price_usd - Decimal(1)
        if not _is_close(self.return_from_reference, expected_return):
            raise ValueError("scenario return must be calculated from value per share and price")
        return self


class PayoffProfile(BaseModel):
    """Derived, probability-free summary of the three explicit scenarios."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    bear_return: Decimal
    base_return: Decimal
    bull_return: Decimal
    upside_to_downside_ratio: Decimal | None
    method_version: NonEmptyString
    rationale: NonEmptyString


class Catalyst(BaseModel):
    """Observable event window that may resolve part of the thesis."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    catalyst_id: UnderwritingObjectId
    description: NonEmptyString
    window_start: date
    window_end: date
    claim_ids: tuple[UUID, ...] = Field(min_length=1)
    monitoring_condition: NonEmptyString

    @field_validator("claim_ids")
    @classmethod
    def reject_duplicate_claims(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        return cast(
            tuple[UUID, ...],
            _reject_duplicates(value, message="duplicate catalyst claim_ids are not allowed"),
        )

    @model_validator(mode="after")
    def validate_window(self) -> Self:
        if self.window_start > self.window_end:
            raise ValueError("catalyst window_start cannot follow window_end")
        return self


class RiskKind(StrEnum):
    """Material risk families kept visible instead of absorbed into a score."""

    DEMAND = "demand"
    COMPETITION = "competition"
    OPERATING_EXECUTION = "operating_execution"
    FINANCIAL = "financial"
    DILUTION = "dilution"
    VALUATION = "valuation"
    REGULATORY = "regulatory"
    OTHER = "other"


class UnderwritingRisk(BaseModel):
    """One sourced risk with an observable monitoring and invalidation condition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    risk_id: UnderwritingObjectId
    kind: RiskKind
    description: NonEmptyString
    claim_ids: tuple[UUID, ...] = Field(min_length=1)
    monitoring_condition: NonEmptyString
    invalidation_condition: NonEmptyString

    @field_validator("claim_ids")
    @classmethod
    def reject_duplicate_claims(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        return cast(
            tuple[UUID, ...],
            _reject_duplicates(value, message="duplicate risk claim_ids are not allowed"),
        )


class UnderwritingDraft(BaseModel):
    """Standalone underwriting input before source verification and content addressing."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: UnderwritingObjectId
    candidate_id: SubjectId
    causal_analysis: CausalAnalysis
    knowledge_boundary: KnowledgeBoundary
    method_version: NonEmptyString
    status: OpportunityStatus
    readiness_rationale: NonEmptyString
    thesis_summary: ThesisSummary
    source_document_ids: tuple[UUID, ...] = ()
    evidence: tuple[EvidenceItem, ...] = ()
    claims: tuple[Claim, ...] = ()
    financial_facts: tuple[FinancialFact, ...] = ()
    derived_facts: tuple[DerivedFinancialFact, ...] = ()
    dimensions: tuple[UnderwritingDimension, ...] = ()
    eligibility_gates: tuple[EligibilityGate, ...] = ()
    valuation_scenarios: tuple[ValuationScenario, ...] = ()
    payoff_profile: PayoffProfile | None = None
    catalysts: tuple[Catalyst, ...] = ()
    risks: tuple[UnderwritingRisk, ...] = ()
    invalidation_conditions: tuple[NonEmptyString, ...] = ()
    missing_data: tuple[NonEmptyString, ...] = ()
    conflicts: tuple[NonEmptyString, ...] = ()
    assumptions: tuple[NonEmptyString, ...] = ()
    invalidation_reason: NonEmptyString | None = None

    @field_validator("source_document_ids")
    @classmethod
    def reject_duplicate_source_documents(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        return cast(
            tuple[UUID, ...],
            _reject_duplicates(value, message="duplicate source_document_ids are not allowed"),
        )

    @field_validator("invalidation_conditions", "missing_data", "conflicts", "assumptions")
    @classmethod
    def reject_duplicate_disclosures(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return cast(
            tuple[str, ...],
            _reject_duplicates(value, message="duplicate underwriting disclosures are not allowed"),
        )

    @model_validator(mode="after")
    def validate_underwriting_contract(self) -> Self:
        self._validate_causal_handoff()
        evidence = self._unique_by_id(self.evidence, "evidence_id", "evidence")
        claims = self._unique_by_id(self.claims, "claim_id", "claim")
        facts = self._unique_by_id(self.financial_facts, "fact_id", "financial fact")
        derived = self._unique_by_id(self.derived_facts, "fact_id", "derived fact")
        if set(facts).intersection(derived):
            raise ValueError("financial and derived fact_ids must be unique across the assessment")
        dimensions = self._unique_by_id(self.dimensions, "kind", "underwriting dimension")
        gates = self._unique_by_id(self.eligibility_gates, "kind", "eligibility gate")
        scenarios = self._unique_by_id(self.valuation_scenarios, "kind", "valuation scenario")
        self._unique_by_id(self.catalysts, "catalyst_id", "catalyst")
        self._unique_by_id(self.risks, "risk_id", "risk")

        self._validate_evidence_and_claims(evidence, claims)
        self._validate_financial_facts(facts, derived, claims)
        referenced_claims, referenced_facts = self._validate_analytical_references(
            claims=claims,
            fact_ids=set(facts).union(derived),
        )
        if referenced_claims != set(claims):
            raise ValueError("every underwriting claim must support an analytical component")
        if referenced_facts != set(facts).union(derived):
            raise ValueError("every financial fact must support a dimension or scenario")
        self._validate_scenario_fact_support(
            scenarios=scenarios,
            facts=facts,
            derived=derived,
        )
        self._validate_scenarios_and_payoff(scenarios)
        self._validate_status(dimensions=dimensions, gates=gates, scenarios=scenarios)
        return self

    @staticmethod
    def _unique_by_id(
        values: tuple[BaseModel, ...], attribute: str, label: str
    ) -> dict[object, BaseModel]:
        indexed = {getattr(value, attribute): value for value in values}
        if len(indexed) != len(values):
            raise ValueError(f"duplicate {label} records are not allowed")
        return indexed

    def _validate_causal_handoff(self) -> None:
        if self.causal_analysis.readiness is not CausalReadiness.READY_FOR_UNDERWRITING:
            raise ValueError("underwriting requires a causal analysis ready_for_underwriting")
        if self.knowledge_boundary != self.causal_analysis.knowledge_boundary:
            raise ValueError("underwriting and causal analysis must share the knowledge boundary")
        beneficiary_subjects = {
            node.subject_id
            for node in self.causal_analysis.nodes
            if node.kind is CausalNodeKind.BENEFICIARY
        }
        if self.candidate_id not in beneficiary_subjects:
            raise ValueError("underwriting candidate must be a causal beneficiary subject")

    def _validate_evidence_and_claims(
        self,
        evidence: dict[object, BaseModel],
        claims: dict[object, BaseModel],
    ) -> None:
        source_document_ids = set(self.source_document_ids)
        referenced_evidence: set[UUID] = set()
        for raw_item in evidence.values():
            item = cast(EvidenceItem, raw_item)
            if (
                item.source_document_id is None
                or item.source_locator is None
                or item.extraction_method is None
            ):
                raise ValueError(
                    f"underwriting evidence {item.evidence_id} must link to a source document"
                )
            if item.source_document_id not in source_document_ids:
                raise ValueError(
                    f"underwriting evidence {item.evidence_id} references an undeclared source"
                )
            exclusion = item.knowledge_exclusion_reason(self.knowledge_boundary)
            if exclusion is not None:
                raise ValueError(
                    f"underwriting evidence {item.evidence_id} is outside the knowledge boundary: "
                    f"{exclusion.value}"
                )
        for raw_claim in claims.values():
            claim = cast(Claim, raw_claim)
            unknown_evidence = set(claim.evidence_ids).difference(evidence)
            if unknown_evidence:
                raise ValueError(f"underwriting claim {claim.claim_id} references unknown evidence")
            referenced_evidence.update(claim.evidence_ids)
        if referenced_evidence != set(evidence):
            raise ValueError("every underwriting evidence item must support a claim")
        evidence_source_ids = {
            cast(EvidenceItem, item).source_document_id for item in evidence.values()
        }
        if evidence_source_ids != source_document_ids:
            raise ValueError("every underwriting source document must support evidence")

    def _validate_financial_facts(
        self,
        facts: dict[object, BaseModel],
        derived: dict[object, BaseModel],
        claims: dict[object, BaseModel],
    ) -> None:
        typed_facts = {key: cast(FinancialFact, value) for key, value in facts.items()}
        typed_claims = {key: cast(Claim, value) for key, value in claims.items()}
        for fact in typed_facts.values():
            if fact.period.end_date > self.knowledge_boundary.as_of.date():
                raise ValueError(f"financial fact {fact.fact_id} ends after the as_of boundary")
            unknown_claims = set(fact.claim_ids).difference(typed_claims)
            if unknown_claims:
                raise ValueError(f"financial fact {fact.fact_id} references unknown claims")
            required_types = (
                _OBSERVED_CLAIM_TYPES
                if fact.basis is FinancialFactBasis.REPORTED
                else _INTERPRETIVE_CLAIM_TYPES
            )
            if not any(
                typed_claims[claim_id].claim_type in required_types for claim_id in fact.claim_ids
            ):
                raise ValueError(
                    f"{fact.basis.value} financial fact {fact.fact_id} lacks compatible "
                    "claim support"
                )
        for raw_derived in derived.values():
            self._validate_derived_fact(cast(DerivedFinancialFact, raw_derived), typed_facts)

    @staticmethod
    def _validate_derived_fact(
        derived: DerivedFinancialFact,
        facts: dict[object, FinancialFact],
    ) -> None:
        try:
            left, right = (facts[fact_id] for fact_id in derived.input_fact_ids)
        except KeyError as error:
            raise ValueError(
                f"derived fact {derived.fact_id} references unknown input facts"
            ) from error

        expected_metrics: dict[DerivedMetric, tuple[FinancialMetric, FinancialMetric]] = {
            DerivedMetric.REVENUE_GROWTH: (FinancialMetric.REVENUE, FinancialMetric.REVENUE),
            DerivedMetric.GROSS_MARGIN: (FinancialMetric.REVENUE, FinancialMetric.GROSS_PROFIT),
            DerivedMetric.FREE_CASH_FLOW: (
                FinancialMetric.OPERATING_CASH_FLOW,
                FinancialMetric.CAPITAL_EXPENDITURES,
            ),
            DerivedMetric.NET_DEBT: (
                FinancialMetric.TOTAL_DEBT,
                FinancialMetric.CASH_AND_INVESTMENTS,
            ),
            DerivedMetric.DILUTED_SHARE_GROWTH: (
                FinancialMetric.DILUTED_SHARES,
                FinancialMetric.DILUTED_SHARES,
            ),
            DerivedMetric.RETURN_ON_INVESTED_CAPITAL: (
                FinancialMetric.NORMALIZED_NOPAT,
                FinancialMetric.AVERAGE_INVESTED_CAPITAL,
            ),
        }
        if (left.metric, right.metric) != expected_metrics[derived.metric]:
            raise ValueError(f"derived fact {derived.fact_id} has incompatible input metrics")
        if derived.metric in {
            DerivedMetric.REVENUE_GROWTH,
            DerivedMetric.DILUTED_SHARE_GROWTH,
        }:
            if left.period.end_date >= right.period.end_date:
                raise ValueError(
                    f"derived fact {derived.fact_id} requires prior then current input"
                )
            expected = (right.value - left.value) / abs(left.value)
        elif derived.metric is DerivedMetric.GROSS_MARGIN:
            if left.period != right.period:
                raise ValueError("gross margin requires same-period revenue and gross profit")
            expected = right.value / left.value
        elif derived.metric is DerivedMetric.FREE_CASH_FLOW:
            if left.period != right.period:
                raise ValueError("free cash flow requires same-period cash flow and capex")
            expected = left.value - right.value
        elif derived.metric is DerivedMetric.NET_DEBT:
            if left.period.end_date != right.period.end_date:
                raise ValueError("net debt requires same-date debt and cash")
            expected = left.value - right.value
        else:
            if left.period != right.period:
                raise ValueError("ROIC requires same-period NOPAT and invested capital")
            expected = left.value / right.value
        if not _is_close(derived.value, expected):
            raise ValueError(f"derived fact {derived.fact_id} does not match its declared formula")

    def _validate_analytical_references(
        self,
        *,
        claims: dict[object, BaseModel],
        fact_ids: set[object],
    ) -> tuple[set[UUID], set[str]]:
        known_claims = set(claims)
        referenced_claims: set[UUID] = set()
        referenced_facts: set[str] = set()

        for fact in self.financial_facts:
            referenced_claims.update(fact.claim_ids)
        for component in self.dimensions:
            unknown_claims = set(component.claim_ids).difference(known_claims)
            if unknown_claims:
                raise ValueError("underwriting component references unknown claims")
            referenced_claims.update(component.claim_ids)
            unknown_facts = set(component.fact_ids).difference(fact_ids)
            if unknown_facts:
                raise ValueError("underwriting dimension references unknown financial facts")
            referenced_facts.update(component.fact_ids)
        for gate in self.eligibility_gates:
            unknown_claims = set(gate.claim_ids).difference(known_claims)
            if unknown_claims:
                raise ValueError("underwriting component references unknown claims")
            referenced_claims.update(gate.claim_ids)
        for scenario in self.valuation_scenarios:
            unknown_claims = set(scenario.assumption_claim_ids).difference(known_claims)
            if unknown_claims:
                raise ValueError("valuation scenario references unknown assumption claims")
            if not any(
                cast(Claim, claims[claim_id]).claim_type in _INTERPRETIVE_CLAIM_TYPES
                for claim_id in scenario.assumption_claim_ids
            ):
                raise ValueError("valuation scenarios require inferential assumption claims")
            unknown_facts = set(scenario.supporting_fact_ids).difference(fact_ids)
            if unknown_facts:
                raise ValueError("valuation scenario references unknown financial facts")
            referenced_claims.update(scenario.assumption_claim_ids)
            referenced_facts.update(scenario.supporting_fact_ids)
        for catalyst in self.catalysts:
            unknown_claims = set(catalyst.claim_ids).difference(known_claims)
            if unknown_claims:
                raise ValueError("catalyst or risk references unknown claims")
            referenced_claims.update(catalyst.claim_ids)
        for risk in self.risks:
            unknown_claims = set(risk.claim_ids).difference(known_claims)
            if unknown_claims:
                raise ValueError("catalyst or risk references unknown claims")
            referenced_claims.update(risk.claim_ids)
        for derived in self.derived_facts:
            referenced_facts.update(derived.input_fact_ids)
        return referenced_claims, referenced_facts

    @staticmethod
    def _validate_scenario_fact_support(
        *,
        scenarios: dict[object, BaseModel],
        facts: dict[object, BaseModel],
        derived: dict[object, BaseModel],
    ) -> None:
        typed_facts = {key: cast(FinancialFact, value) for key, value in facts.items()}
        typed_derived = {key: cast(DerivedFinancialFact, value) for key, value in derived.items()}
        for raw_scenario in scenarios.values():
            scenario = cast(ValuationScenario, raw_scenario)
            supported_facts = [
                typed_facts[fact_id]
                for fact_id in scenario.supporting_fact_ids
                if fact_id in typed_facts
            ]
            supported_derived = [
                typed_derived[fact_id]
                for fact_id in scenario.supporting_fact_ids
                if fact_id in typed_derived
            ]
            prices = [
                fact.value
                for fact in supported_facts
                if fact.metric is FinancialMetric.REFERENCE_SHARE_PRICE
            ]
            if scenario.reference_price_usd not in prices:
                raise ValueError("valuation scenario reference price lacks exact fact support")
            if not any(fact.metric is FinancialMetric.DILUTED_SHARES for fact in supported_facts):
                raise ValueError("valuation scenario requires diluted-share fact support")
            if not any(fact.metric is DerivedMetric.NET_DEBT for fact in supported_derived):
                raise ValueError("valuation scenario requires derived net-debt support")

    def _validate_scenarios_and_payoff(
        self,
        scenarios: dict[object, BaseModel],
    ) -> None:
        if not scenarios:
            if self.payoff_profile is not None:
                raise ValueError("payoff_profile requires valuation scenarios")
            return
        if set(scenarios) != set(ScenarioKind):
            raise ValueError("valuation requires exactly bear, base, and bull scenarios")
        typed = {kind: cast(ValuationScenario, value) for kind, value in scenarios.items()}
        bear, base, bull = (typed[kind] for kind in ScenarioKind)
        prices = {scenario.reference_price_usd for scenario in typed.values()}
        if len(prices) != 1:
            raise ValueError("all valuation scenarios must use the same reference price")
        if not (bear.value_per_share_usd < base.value_per_share_usd < bull.value_per_share_usd):
            raise ValueError(
                "scenario values per share must be strictly ordered bear < base < bull"
            )
        if self.payoff_profile is None:
            raise ValueError("valuation scenarios require payoff_profile")
        payoff = self.payoff_profile
        expected_returns = (
            bear.return_from_reference,
            base.return_from_reference,
            bull.return_from_reference,
        )
        actual_returns = (payoff.bear_return, payoff.base_return, payoff.bull_return)
        if not all(
            _is_close(actual, expected)
            for actual, expected in zip(actual_returns, expected_returns, strict=True)
        ):
            raise ValueError("payoff_profile returns must match valuation scenarios")
        expected_ratio = (
            bull.return_from_reference / abs(bear.return_from_reference)
            if bear.return_from_reference < 0 < bull.return_from_reference
            else None
        )
        if expected_ratio is None:
            if payoff.upside_to_downside_ratio is not None:
                raise ValueError("upside/downside ratio is undefined without loss and gain cases")
        elif payoff.upside_to_downside_ratio is None or not _is_close(
            payoff.upside_to_downside_ratio, expected_ratio
        ):
            raise ValueError("upside/downside ratio must match bear and bull scenario returns")

    def _validate_status(
        self,
        *,
        dimensions: dict[object, BaseModel],
        gates: dict[object, BaseModel],
        scenarios: dict[object, BaseModel],
    ) -> None:
        if self.status is OpportunityStatus.READY_FOR_PORTFOLIO_REVIEW:
            if set(dimensions) != set(UnderwritingDimensionKind):
                raise ValueError("portfolio-ready underwriting requires all dimensions")
            if set(gates) != set(EligibilityGateKind):
                raise ValueError("portfolio-ready underwriting requires all eligibility gates")
            if any(
                cast(EligibilityGate, gate).result is not GateResult.PASS for gate in gates.values()
            ):
                raise ValueError(
                    "portfolio-ready underwriting requires every eligibility gate to pass"
                )
            if any(
                cast(UnderwritingDimension, dimension).outcome is DimensionOutcome.UNKNOWN
                for dimension in dimensions.values()
            ):
                raise ValueError("portfolio-ready underwriting cannot contain unknown dimensions")
            if set(scenarios) != set(ScenarioKind):
                raise ValueError("portfolio-ready underwriting requires three valuation scenarios")
            required_collections = (
                self.source_document_ids,
                self.evidence,
                self.claims,
                self.financial_facts,
                self.derived_facts,
                self.catalysts,
                self.risks,
                self.invalidation_conditions,
            )
            if any(not collection for collection in required_collections):
                raise ValueError("portfolio-ready underwriting has incomplete analytical lineage")
        if self.status is OpportunityStatus.INSUFFICIENT_EVIDENCE and not self.missing_data:
            raise ValueError("insufficient_evidence requires explicit missing_data")
        if self.status is OpportunityStatus.INVALIDATED:
            if self.invalidation_reason is None:
                raise ValueError("invalidated underwriting requires invalidation_reason")
        elif self.invalidation_reason is not None:
            raise ValueError("invalidation_reason is allowed only for invalidated underwriting")


class OpportunityState(UnderwritingDraft):
    """Verified, deterministic standalone assessment handed to Portfolio unchanged."""

    opportunity_id: UUID
    input_fingerprint: ContentHash
    source_documents: tuple[SourceDocument, ...] = ()

    @property
    def as_of(self) -> datetime:
        """Compatibility view over the canonical shared boundary."""

        return self.knowledge_boundary.as_of

    @property
    def knowledge_mode(self) -> KnowledgeMode:
        """Compatibility view over the canonical shared boundary."""

        return self.knowledge_boundary.knowledge_mode

    @model_validator(mode="after")
    def validate_verified_sources(self) -> Self:
        documents = {document.document_id: document for document in self.source_documents}
        if len(documents) != len(self.source_documents):
            raise ValueError("duplicate verified source documents are not allowed")
        if set(documents) != set(self.source_document_ids):
            raise ValueError("verified documents must match underwriting source_document_ids")
        for document in self.source_documents:
            exclusion = document.knowledge_exclusion_reason(self.knowledge_boundary)
            if exclusion is not None:
                raise ValueError(
                    f"underwriting source {document.document_id} is outside the knowledge "
                    "boundary: "
                    f"{exclusion.value}"
                )
        for item in self.evidence:
            document = documents[cast(UUID, item.source_document_id)]
            expected = (
                document.source_uri,
                document.source_type,
                document.effective_at,
                document.available_at,
                document.recorded_at,
                document.content_hash,
            )
            actual = (
                item.source_uri,
                item.source_type,
                item.effective_at,
                item.available_at,
                item.recorded_at,
                item.content_hash,
            )
            if actual != expected:
                raise ValueError(
                    f"underwriting evidence {item.evidence_id} provenance does not match source"
                )
        evidence = {item.evidence_id: item for item in self.evidence}
        claims = {claim.claim_id: claim for claim in self.claims}
        for fact in self.financial_facts:
            for claim_id in fact.claim_ids:
                for evidence_id in claims[claim_id].evidence_ids:
                    document_id = cast(UUID, evidence[evidence_id].source_document_id)
                    if documents[document_id].subject_id != self.candidate_id:
                        raise ValueError(
                            f"financial fact {fact.fact_id} lacks direct candidate-subject "
                            "provenance"
                        )
        return self
