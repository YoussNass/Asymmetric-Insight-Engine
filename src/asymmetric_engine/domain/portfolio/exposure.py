"""Descriptive, point-in-time Portfolio Exposure contracts for Chapter 6B."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from asymmetric_engine.domain.evidence.models import (
    Claim,
    ClaimType,
    ContentHash,
    EvidenceItem,
    NonEmptyString,
)
from asymmetric_engine.domain.evidence.source_documents import SubjectId
from asymmetric_engine.domain.financial import CurrencyCode, MonetaryAmount, canonical_decimal
from asymmetric_engine.domain.portfolio.models import CountryCode, PortfolioObjectId
from asymmetric_engine.domain.temporal import KnowledgeBoundary, KnowledgeMode

PORTFOLIO_EXPOSURE_METHOD_VERSION = "portfolio-exposure-v1"

ExposureRatio = Annotated[
    Decimal,
    Field(ge=0, le=1, allow_inf_nan=False),
]


def _normalize_ratio(value: Decimal) -> Decimal:
    return canonical_decimal(value)


def _reject_duplicates[T](values: tuple[T, ...], message: str) -> tuple[T, ...]:
    if len(values) != len(set(values)):
        raise ValueError(message)
    return values


class ExposureScenario(StrEnum):
    """The factual current view or a supplied, non-authoritative hypothetical view."""

    CURRENT = "current"
    HYPOTHETICAL_AFTER = "hypothetical_after"


class ClassificationDimension(StrEnum):
    """Descriptive company dimensions that may remain explicitly unknown."""

    SECTOR = "sector"
    GEOGRAPHY = "geography"
    ECONOMIC_DRIVERS = "economic_drivers"


class ETFConstituent(BaseModel):
    """One resolved company inside a one-level ETF holdings snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    company_subject_id: SubjectId
    weight: ExposureRatio

    @field_validator("weight")
    @classmethod
    def normalize_weight(cls, value: Decimal) -> Decimal:
        value = _normalize_ratio(value)
        if value == 0:
            raise ValueError("ETF constituent weight must be greater than zero")
        return value


class ETFConstituentSnapshot(BaseModel):
    """Point-in-time, one-level ETF containment with an explicit unresolved residual."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    snapshot_id: PortfolioObjectId
    etf_instrument_id: PortfolioObjectId
    holdings_date: date
    evidence_id: UUID
    constituents: tuple[ETFConstituent, ...] = Field(min_length=1)
    unresolved_weight: ExposureRatio
    unresolved_reason: NonEmptyString | None = None

    @field_validator("unresolved_weight")
    @classmethod
    def normalize_unresolved_weight(cls, value: Decimal) -> Decimal:
        return _normalize_ratio(value)

    @model_validator(mode="after")
    def validate_snapshot(self) -> Self:
        company_ids = tuple(item.company_subject_id for item in self.constituents)
        _reject_duplicates(company_ids, "duplicate ETF constituent companies are not allowed")
        resolved_weight = sum((item.weight for item in self.constituents), Decimal(0))
        if canonical_decimal(resolved_weight + self.unresolved_weight) != Decimal(1):
            raise ValueError("ETF constituent weights plus unresolved_weight must equal one")
        if self.unresolved_weight > 0 and self.unresolved_reason is None:
            raise ValueError("a positive ETF residual requires unresolved_reason")
        if self.unresolved_weight == 0 and self.unresolved_reason is not None:
            raise ValueError("a fully resolved ETF snapshot cannot declare unresolved_reason")
        return self

    @property
    def coverage(self) -> Decimal:
        return canonical_decimal(Decimal(1) - self.unresolved_weight)


class SectorClassification(BaseModel):
    """Evidence-backed descriptive sector label; it is not causal proof."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    sector_id: PortfolioObjectId
    label: NonEmptyString
    claim_ids: tuple[UUID, ...] = Field(min_length=1)

    @field_validator("claim_ids")
    @classmethod
    def reject_duplicate_claims(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        return _reject_duplicates(
            value,
            "duplicate sector classification claim_ids are not allowed",
        )

    @field_validator("sector_id")
    @classmethod
    def reserve_unknown_sector(cls, value: str) -> str:
        if value == "sector:unknown":
            raise ValueError("sector:unknown is reserved for missing classification")
        return value


class GeographyClassification(BaseModel):
    """Evidence-backed primary economic geography; it is not an issuer domicile proxy."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    country_code: CountryCode
    label: NonEmptyString
    claim_ids: tuple[UUID, ...] = Field(min_length=1)

    @field_validator("claim_ids")
    @classmethod
    def reject_duplicate_claims(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        return _reject_duplicates(
            value,
            "duplicate geography classification claim_ids are not allowed",
        )


class EconomicDriverTag(BaseModel):
    """An overlapping economic-driver tag backed by interpretive claims."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    driver_id: PortfolioObjectId
    label: NonEmptyString
    claim_ids: tuple[UUID, ...] = Field(min_length=1)

    @field_validator("claim_ids")
    @classmethod
    def reject_duplicate_claims(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        return _reject_duplicates(
            value,
            "duplicate economic-driver claim_ids are not allowed",
        )

    @field_validator("driver_id")
    @classmethod
    def reserve_unknown_driver(cls, value: str) -> str:
        if value == "driver:unknown":
            raise ValueError("driver:unknown is reserved for missing classification")
        return value


class CompanyExposureProfile(BaseModel):
    """Descriptive company classifications with dimension-level missingness."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    profile_id: PortfolioObjectId
    company_subject_id: SubjectId
    sector: SectorClassification | None = None
    geography: GeographyClassification | None = None
    economic_drivers: tuple[EconomicDriverTag, ...] = ()
    missing_dimensions: tuple[ClassificationDimension, ...] = ()
    missing_reason: NonEmptyString | None = None

    @model_validator(mode="after")
    def validate_missing_dimensions(self) -> Self:
        driver_ids = tuple(item.driver_id for item in self.economic_drivers)
        _reject_duplicates(driver_ids, "duplicate economic-driver tags are not allowed")
        _reject_duplicates(
            self.missing_dimensions,
            "duplicate classification missing dimensions are not allowed",
        )
        expected_missing = {
            dimension
            for dimension, is_missing in (
                (ClassificationDimension.SECTOR, self.sector is None),
                (ClassificationDimension.GEOGRAPHY, self.geography is None),
                (ClassificationDimension.ECONOMIC_DRIVERS, not self.economic_drivers),
            )
            if is_missing
        }
        if set(self.missing_dimensions) != expected_missing:
            raise ValueError("missing_dimensions must exactly identify absent classifications")
        if expected_missing and self.missing_reason is None:
            raise ValueError("missing company classifications require missing_reason")
        if not expected_missing and self.missing_reason is not None:
            raise ValueError("a complete company profile cannot declare missing_reason")
        return self


class HypotheticalPosition(BaseModel):
    """A user-supplied amount for descriptive before/after exposure only."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    hypothetical_id: PortfolioObjectId
    instrument_id: PortfolioObjectId
    amount: MonetaryAmount
    rationale: NonEmptyString

    @model_validator(mode="after")
    def require_positive_amount(self) -> Self:
        if self.amount.amount == 0:
            raise ValueError("hypothetical position amount must be greater than zero")
        return self


class PortfolioExposureInput(BaseModel):
    """Point-in-time analytical inputs kept separate from factual Portfolio State."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    knowledge_boundary: KnowledgeBoundary
    method_version: NonEmptyString = PORTFOLIO_EXPOSURE_METHOD_VERSION
    top_company_count: int = Field(ge=1)
    evidence_items: tuple[EvidenceItem, ...] = ()
    claims: tuple[Claim, ...] = ()
    etf_snapshots: tuple[ETFConstituentSnapshot, ...] = ()
    company_profiles: tuple[CompanyExposureProfile, ...] = ()
    hypothetical_position: HypotheticalPosition | None = None
    missing_data: tuple[NonEmptyString, ...] = ()
    conflicts: tuple[NonEmptyString, ...] = ()
    assumptions: tuple[NonEmptyString, ...] = ()

    @field_validator("method_version")
    @classmethod
    def require_admitted_method(cls, value: str) -> str:
        if value != PORTFOLIO_EXPOSURE_METHOD_VERSION:
            raise ValueError(f"method_version must be {PORTFOLIO_EXPOSURE_METHOD_VERSION!r}")
        return value

    @field_validator("missing_data", "conflicts", "assumptions")
    @classmethod
    def reject_duplicate_disclosures(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _reject_duplicates(value, "duplicate exposure disclosures are not allowed")

    @model_validator(mode="after")
    def validate_provenance(self) -> Self:
        evidence = {item.evidence_id: item for item in self.evidence_items}
        claims = {item.claim_id: item for item in self.claims}
        snapshots = {item.etf_instrument_id: item for item in self.etf_snapshots}
        profiles = {item.company_subject_id: item for item in self.company_profiles}
        if len(evidence) != len(self.evidence_items):
            raise ValueError("duplicate exposure evidence_ids are not allowed")
        if len(claims) != len(self.claims):
            raise ValueError("duplicate exposure claim_ids are not allowed")
        if len(snapshots) != len(self.etf_snapshots):
            raise ValueError("only one constituent snapshot per ETF is allowed")
        if len({item.snapshot_id for item in self.etf_snapshots}) != len(self.etf_snapshots):
            raise ValueError("duplicate ETF snapshot_ids are not allowed")
        if len(profiles) != len(self.company_profiles):
            raise ValueError("only one exposure profile per company is allowed")
        if len({item.profile_id for item in self.company_profiles}) != len(self.company_profiles):
            raise ValueError("duplicate company exposure profile_ids are not allowed")

        for item in self.evidence_items:
            if item.effective_at > self.knowledge_boundary.as_of:
                raise ValueError(f"exposure evidence {item.evidence_id} is not effective by T0")
            exclusion = item.knowledge_exclusion_reason(self.knowledge_boundary)
            if exclusion is not None:
                raise ValueError(
                    f"exposure evidence {item.evidence_id} is outside the knowledge boundary: "
                    f"{exclusion.value}"
                )

        claim_evidence_ids: set[UUID] = set()
        for claim in self.claims:
            unknown_evidence = set(claim.evidence_ids).difference(evidence)
            if unknown_evidence:
                raise ValueError(f"exposure claim {claim.claim_id} references unknown evidence")
            claim_evidence_ids.update(claim.evidence_ids)

        snapshot_evidence_ids: set[UUID] = set()
        for snapshot in self.etf_snapshots:
            snapshot_evidence = evidence.get(snapshot.evidence_id)
            if snapshot_evidence is None:
                raise ValueError(f"ETF snapshot {snapshot.snapshot_id} references unknown evidence")
            if snapshot_evidence.effective_at.date() != snapshot.holdings_date:
                raise ValueError("ETF holdings_date must match its evidence effective date")
            if snapshot.holdings_date > self.knowledge_boundary.as_of.date():
                raise ValueError("ETF holdings_date cannot be after the knowledge boundary")
            snapshot_evidence_ids.add(snapshot.evidence_id)

        if snapshot_evidence_ids.intersection(claim_evidence_ids):
            raise ValueError(
                "instrument containment and economic classification require separate evidence"
            )

        used_claim_ids: set[UUID] = set()
        interpretive_types = {
            ClaimType.INFERENCE,
            ClaimType.HYPOTHESIS,
            ClaimType.QUALITATIVE_JUDGEMENT,
        }
        for profile in self.company_profiles:
            classification_claim_ids: set[UUID] = set()
            if profile.sector is not None:
                classification_claim_ids.update(profile.sector.claim_ids)
            if profile.geography is not None:
                classification_claim_ids.update(profile.geography.claim_ids)
            for claim_id in classification_claim_ids:
                if claim_id not in claims:
                    raise ValueError("company classification references an unknown claim")
            used_claim_ids.update(classification_claim_ids)
            for driver in profile.economic_drivers:
                for claim_id in driver.claim_ids:
                    driver_claim = claims.get(claim_id)
                    if driver_claim is None:
                        raise ValueError("economic-driver tag references an unknown claim")
                    if driver_claim.claim_type not in interpretive_types:
                        raise ValueError(
                            "economic-driver tags require inference, hypothesis, or judgement"
                        )
                    used_claim_ids.add(claim_id)

        if used_claim_ids != set(claims):
            raise ValueError("every exposure claim must support a company classification")
        used_evidence_ids = claim_evidence_ids | snapshot_evidence_ids
        if used_evidence_ids != set(evidence):
            raise ValueError("every exposure evidence item must support a claim or ETF snapshot")
        return self

    @property
    def as_of(self) -> datetime:
        return self.knowledge_boundary.as_of

    @property
    def knowledge_mode(self) -> KnowledgeMode:
        return self.knowledge_boundary.knowledge_mode


class PortfolioStateReference(BaseModel):
    """Immutable reference to the verified factual state; the payload is not copied."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    portfolio_state_id: UUID
    portfolio_id: PortfolioObjectId
    input_fingerprint: ContentHash
    knowledge_boundary: KnowledgeBoundary


class InstrumentExposure(BaseModel):
    """Instrument value and weight inside one native-currency book."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    instrument_id: PortfolioObjectId
    value: MonetaryAmount
    weight: ExposureRatio

    @field_validator("weight")
    @classmethod
    def normalize_weight(cls, value: Decimal) -> Decimal:
        return _normalize_ratio(value)


class CompanyExposure(BaseModel):
    """Resolved company exposure split between direct equity and ETF look-through."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    company_subject_id: SubjectId
    direct_value: MonetaryAmount
    indirect_value: MonetaryAmount
    total_value: MonetaryAmount
    weight: ExposureRatio
    direct_instrument_ids: tuple[PortfolioObjectId, ...] = ()
    indirect_instrument_ids: tuple[PortfolioObjectId, ...] = ()
    sector_id: PortfolioObjectId | None = None
    geography_code: CountryCode | None = None
    economic_driver_ids: tuple[PortfolioObjectId, ...] = ()

    @field_validator("weight")
    @classmethod
    def normalize_weight(cls, value: Decimal) -> Decimal:
        return _normalize_ratio(value)

    @model_validator(mode="after")
    def validate_values(self) -> Self:
        currencies = {
            self.direct_value.currency,
            self.indirect_value.currency,
            self.total_value.currency,
        }
        if len(currencies) != 1:
            raise ValueError("company exposure values must use one native currency")
        if canonical_decimal(self.direct_value.amount + self.indirect_value.amount) != (
            self.total_value.amount
        ):
            raise ValueError("company total exposure must equal direct plus indirect value")
        _reject_duplicates(
            self.direct_instrument_ids,
            "duplicate direct source instruments are not allowed",
        )
        _reject_duplicates(
            self.indirect_instrument_ids,
            "duplicate indirect source instruments are not allowed",
        )
        _reject_duplicates(
            self.economic_driver_ids,
            "duplicate company economic-driver ids are not allowed",
        )
        return self


class CategoryExposure(BaseModel):
    """Additive sector or geography exposure, including an explicit unknown bucket."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    category_id: PortfolioObjectId
    label: NonEmptyString
    value: MonetaryAmount
    weight: ExposureRatio
    company_subject_ids: tuple[SubjectId, ...] = ()
    is_unknown: bool = False

    @field_validator("weight")
    @classmethod
    def normalize_weight(cls, value: Decimal) -> Decimal:
        return _normalize_ratio(value)


class DriverExposure(BaseModel):
    """Non-additive exposure tagged to an economic driver."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    driver_id: PortfolioObjectId
    label: NonEmptyString
    value: MonetaryAmount
    weight: ExposureRatio
    company_subject_ids: tuple[SubjectId, ...] = ()
    is_unknown: bool = False

    @field_validator("weight")
    @classmethod
    def normalize_weight(cls, value: Decimal) -> Decimal:
        return _normalize_ratio(value)


class UnresolvedExposure(BaseModel):
    """Value that cannot be assigned to an underlying company at T0."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    value: MonetaryAmount
    weight: ExposureRatio
    reasons: tuple[NonEmptyString, ...] = ()

    @field_validator("weight")
    @classmethod
    def normalize_weight(cls, value: Decimal) -> Decimal:
        return _normalize_ratio(value)

    @model_validator(mode="after")
    def validate_reasons(self) -> Self:
        _reject_duplicates(self.reasons, "duplicate unresolved exposure reasons are not allowed")
        if self.value.amount > 0 and not self.reasons:
            raise ValueError("positive unresolved exposure requires at least one reason")
        if self.value.amount == 0 and self.reasons:
            raise ValueError("zero unresolved exposure cannot declare reasons")
        return self


class HHIBounds(BaseModel):
    """Company-concentration bounds when residual company identity is unknown."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    lower_bound: ExposureRatio
    upper_bound: ExposureRatio

    @field_validator("lower_bound", "upper_bound")
    @classmethod
    def normalize_bounds(cls, value: Decimal) -> Decimal:
        return _normalize_ratio(value)

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        if self.lower_bound > self.upper_bound:
            raise ValueError("HHI lower_bound cannot exceed upper_bound")
        return self


class CurrencyExposureBook(BaseModel):
    """A complete descriptive exposure view for one unconverted currency book."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    currency: CurrencyCode
    gross_position_value: MonetaryAmount
    instrument_exposures: tuple[InstrumentExposure, ...]
    company_exposures: tuple[CompanyExposure, ...]
    unresolved_exposure: UnresolvedExposure
    sector_exposures: tuple[CategoryExposure, ...]
    geography_exposures: tuple[CategoryExposure, ...]
    economic_driver_exposures: tuple[DriverExposure, ...]
    economic_driver_exposures_are_non_additive: bool = True
    top_company_subject_ids: tuple[SubjectId, ...]
    top_company_count: int = Field(ge=1)
    company_hhi: HHIBounds

    @model_validator(mode="after")
    def validate_book(self) -> Self:
        if self.gross_position_value.currency != self.currency:
            raise ValueError("gross position value must match the currency book")
        if self.gross_position_value.amount == 0:
            raise ValueError("a currency exposure book requires positive gross value")
        monetary_groups = (
            self.instrument_exposures,
            self.sector_exposures,
            self.geography_exposures,
            self.economic_driver_exposures,
        )
        for group in monetary_groups:
            if any(item.value.currency != self.currency for item in group):
                raise ValueError("all exposure values must match the currency book")
        for company in self.company_exposures:
            if any(
                value.currency != self.currency
                for value in (
                    company.direct_value,
                    company.indirect_value,
                    company.total_value,
                )
            ):
                raise ValueError("all company exposure values must match the currency book")
        if self.unresolved_exposure.value.currency != self.currency:
            raise ValueError("unresolved exposure must match the currency book")
        instrument_total = sum(
            (item.value.amount for item in self.instrument_exposures), Decimal(0)
        )
        company_total = sum(
            (item.total_value.amount for item in self.company_exposures),
            Decimal(0),
        )
        if canonical_decimal(instrument_total) != self.gross_position_value.amount:
            raise ValueError("instrument exposures must reconcile to gross position value")
        if canonical_decimal(company_total + self.unresolved_exposure.value.amount) != (
            self.gross_position_value.amount
        ):
            raise ValueError("company exposure plus unresolved value must reconcile to gross value")
        for group, name in (
            (self.sector_exposures, "sector"),
            (self.geography_exposures, "geography"),
        ):
            total = sum((item.value.amount for item in group), Decimal(0))
            if canonical_decimal(total) != self.gross_position_value.amount:
                raise ValueError(f"{name} exposures must reconcile to gross position value")
        if not self.economic_driver_exposures_are_non_additive:
            raise ValueError("economic-driver exposures must remain explicitly non-additive")
        if len(self.top_company_subject_ids) > self.top_company_count:
            raise ValueError("top company list exceeds top_company_count")
        known_companies = {item.company_subject_id for item in self.company_exposures}
        if not set(self.top_company_subject_ids).issubset(known_companies):
            raise ValueError("top company list references an unknown company exposure")
        return self


class ExposureSnapshot(BaseModel):
    """Current or hypothetical-after exposure, grouped without implicit FX."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    scenario: ExposureScenario
    currency_books: tuple[CurrencyExposureBook, ...] = ()

    @model_validator(mode="after")
    def reject_duplicate_currency_books(self) -> Self:
        currencies = tuple(item.currency for item in self.currency_books)
        _reject_duplicates(currencies, "duplicate currency exposure books are not allowed")
        return self


class PortfolioExposure(BaseModel):
    """Content-addressed descriptive exposure derived from one verified Portfolio State."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    exposure_id: UUID
    portfolio_state: PortfolioStateReference
    input_fingerprint: ContentHash
    knowledge_boundary: KnowledgeBoundary
    method_version: NonEmptyString
    top_company_count: int = Field(ge=1)
    evidence_items: tuple[EvidenceItem, ...] = ()
    claims: tuple[Claim, ...] = ()
    etf_snapshots: tuple[ETFConstituentSnapshot, ...] = ()
    company_profiles: tuple[CompanyExposureProfile, ...] = ()
    hypothetical_position: HypotheticalPosition | None = None
    missing_data: tuple[NonEmptyString, ...] = ()
    conflicts: tuple[NonEmptyString, ...] = ()
    assumptions: tuple[NonEmptyString, ...] = ()
    before: ExposureSnapshot
    after: ExposureSnapshot | None = None

    @model_validator(mode="after")
    def validate_envelope(self) -> Self:
        if self.method_version != PORTFOLIO_EXPOSURE_METHOD_VERSION:
            raise ValueError("Portfolio Exposure uses an unrecognized method version")
        if self.portfolio_state.knowledge_boundary != self.knowledge_boundary:
            raise ValueError("Portfolio Exposure must preserve the Portfolio State boundary")
        if self.before.scenario is not ExposureScenario.CURRENT:
            raise ValueError("before exposure must use the current scenario")
        if self.hypothetical_position is None:
            if self.after is not None:
                raise ValueError("after exposure requires a hypothetical position")
        elif self.after is None or self.after.scenario is not ExposureScenario.HYPOTHETICAL_AFTER:
            raise ValueError("a hypothetical position requires an after exposure snapshot")
        return self

    @property
    def as_of(self) -> datetime:
        return self.knowledge_boundary.as_of

    @property
    def knowledge_mode(self) -> KnowledgeMode:
        return self.knowledge_boundary.knowledge_mode
