"""Deterministic Chapter 6B Portfolio Exposure fixtures."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from hashlib import sha256
from uuid import UUID

from asymmetric_engine.application.portfolio_exposure import BuildPortfolioExposure
from asymmetric_engine.application.portfolio_state import BuildPortfolioState
from asymmetric_engine.domain.evidence import (
    Claim,
    ClaimType,
    Confidence,
    DataQuality,
    EvidenceItem,
    SourceType,
)
from asymmetric_engine.domain.financial import MonetaryAmount
from asymmetric_engine.domain.portfolio import (
    CompanyExposureProfile,
    EconomicDriverTag,
    ETFConstituent,
    ETFConstituentSnapshot,
    GeographyClassification,
    HypotheticalPosition,
    PortfolioExposure,
    PortfolioExposureInput,
    SectorClassification,
)
from tests.portfolio_factories import AS_OF, make_portfolio_draft

MICRON_COMPANY_ID = "company:sec-cik-0000723125"
INDUSTRIAL_COMPANY_ID = "company:global-industrials"
CONSUMER_COMPANY_ID = "company:consumer-platform"

THEMATIC_SNAPSHOT_EVIDENCE_ID = UUID("71000000-0000-4000-8000-000000000001")
CORE_SNAPSHOT_EVIDENCE_ID = UUID("71000000-0000-4000-8000-000000000002")
MICRON_CLASSIFICATION_EVIDENCE_ID = UUID("71000000-0000-4000-8000-000000000003")
INDUSTRIAL_CLASSIFICATION_EVIDENCE_ID = UUID("71000000-0000-4000-8000-000000000004")
CONSUMER_CLASSIFICATION_EVIDENCE_ID = UUID("71000000-0000-4000-8000-000000000005")

MICRON_CLASSIFICATION_CLAIM_ID = UUID("72000000-0000-4000-8000-000000000001")
MICRON_DRIVER_CLAIM_ID = UUID("72000000-0000-4000-8000-000000000002")
INDUSTRIAL_CLASSIFICATION_CLAIM_ID = UUID("72000000-0000-4000-8000-000000000003")
INDUSTRIAL_DRIVER_CLAIM_ID = UUID("72000000-0000-4000-8000-000000000004")
CONSUMER_CLASSIFICATION_CLAIM_ID = UUID("72000000-0000-4000-8000-000000000005")
CONSUMER_DRIVER_CLAIM_ID = UUID("72000000-0000-4000-8000-000000000006")


def make_exposure_evidence(
    evidence_id: UUID,
    *,
    offset_days: int,
    coverage: float,
) -> EvidenceItem:
    effective_at = AS_OF - timedelta(days=offset_days)
    return EvidenceItem(
        evidence_id=evidence_id,
        title=f"Synthetic exposure evidence {evidence_id}",
        source_uri=f"fixture://portfolio-exposure/{evidence_id}",
        source_type=SourceType.RESEARCH,
        effective_at=effective_at,
        available_at=effective_at,
        recorded_at=effective_at,
        content_hash=sha256(str(evidence_id).encode()).hexdigest(),
        quality=DataQuality(
            coverage=coverage,
            source_reliability=1.0,
            point_in_time_integrity=1.0,
        ),
    )


def make_claim(
    claim_id: UUID,
    evidence_id: UUID,
    *,
    claim_type: ClaimType,
    text: str,
) -> Claim:
    return Claim(
        claim_id=claim_id,
        text=text,
        claim_type=claim_type,
        evidence_ids=(evidence_id,),
        confidence=Confidence(
            score=0.7,
            rationale="Synthetic uncalibrated annotation retained for uncertainty disclosure.",
        ),
        invalidation_condition="The referenced classification evidence is superseded.",
    )


def make_exposure_input() -> PortfolioExposureInput:
    evidence_items = (
        make_exposure_evidence(
            THEMATIC_SNAPSHOT_EVIDENCE_ID,
            offset_days=1,
            coverage=0.9,
        ),
        make_exposure_evidence(
            CORE_SNAPSHOT_EVIDENCE_ID,
            offset_days=2,
            coverage=0.9,
        ),
        make_exposure_evidence(
            MICRON_CLASSIFICATION_EVIDENCE_ID,
            offset_days=7,
            coverage=1.0,
        ),
        make_exposure_evidence(
            INDUSTRIAL_CLASSIFICATION_EVIDENCE_ID,
            offset_days=7,
            coverage=1.0,
        ),
        make_exposure_evidence(
            CONSUMER_CLASSIFICATION_EVIDENCE_ID,
            offset_days=7,
            coverage=1.0,
        ),
    )
    claims = (
        make_claim(
            MICRON_CLASSIFICATION_CLAIM_ID,
            MICRON_CLASSIFICATION_EVIDENCE_ID,
            claim_type=ClaimType.OBSERVATION,
            text="Micron is classified in information technology with primary US exposure.",
        ),
        make_claim(
            MICRON_DRIVER_CLAIM_ID,
            MICRON_CLASSIFICATION_EVIDENCE_ID,
            claim_type=ClaimType.INFERENCE,
            text="Memory demand and AI infrastructure are material economic-driver tags.",
        ),
        make_claim(
            INDUSTRIAL_CLASSIFICATION_CLAIM_ID,
            INDUSTRIAL_CLASSIFICATION_EVIDENCE_ID,
            claim_type=ClaimType.OBSERVATION,
            text="The industrial reference is classified in Industrials with German exposure.",
        ),
        make_claim(
            INDUSTRIAL_DRIVER_CLAIM_ID,
            INDUSTRIAL_CLASSIFICATION_EVIDENCE_ID,
            claim_type=ClaimType.QUALITATIVE_JUDGEMENT,
            text="Capital spending is a material economic-driver tag.",
        ),
        make_claim(
            CONSUMER_CLASSIFICATION_CLAIM_ID,
            CONSUMER_CLASSIFICATION_EVIDENCE_ID,
            claim_type=ClaimType.OBSERVATION,
            text="The consumer reference has US consumer-discretionary exposure.",
        ),
        make_claim(
            CONSUMER_DRIVER_CLAIM_ID,
            CONSUMER_CLASSIFICATION_EVIDENCE_ID,
            claim_type=ClaimType.INFERENCE,
            text="Consumer demand is a material economic-driver tag.",
        ),
    )
    etf_snapshots = (
        ETFConstituentSnapshot(
            snapshot_id="snapshot:thematic-etf:2026-08-26",
            etf_instrument_id="instrument:thematic-etf",
            holdings_date=(AS_OF - timedelta(days=1)).date(),
            evidence_id=THEMATIC_SNAPSHOT_EVIDENCE_ID,
            constituents=(
                ETFConstituent(
                    company_subject_id=MICRON_COMPANY_ID,
                    weight=Decimal("0.6"),
                ),
                ETFConstituent(
                    company_subject_id=INDUSTRIAL_COMPANY_ID,
                    weight=Decimal("0.3"),
                ),
            ),
            unresolved_weight=Decimal("0.1"),
            unresolved_reason="The fixture source resolves ninety percent of fund weight.",
        ),
        ETFConstituentSnapshot(
            snapshot_id="snapshot:core-etf:2026-08-25",
            etf_instrument_id="instrument:core-equity-etf",
            holdings_date=(AS_OF - timedelta(days=2)).date(),
            evidence_id=CORE_SNAPSHOT_EVIDENCE_ID,
            constituents=(
                ETFConstituent(
                    company_subject_id=MICRON_COMPANY_ID,
                    weight=Decimal("0.1"),
                ),
                ETFConstituent(
                    company_subject_id=INDUSTRIAL_COMPANY_ID,
                    weight=Decimal("0.4"),
                ),
                ETFConstituent(
                    company_subject_id=CONSUMER_COMPANY_ID,
                    weight=Decimal("0.4"),
                ),
            ),
            unresolved_weight=Decimal("0.1"),
            unresolved_reason="The fixture source resolves ninety percent of fund weight.",
        ),
    )
    company_profiles = (
        CompanyExposureProfile(
            profile_id="profile:micron",
            company_subject_id=MICRON_COMPANY_ID,
            sector=SectorClassification(
                sector_id="sector:information-technology",
                label="Information Technology",
                claim_ids=(MICRON_CLASSIFICATION_CLAIM_ID,),
            ),
            geography=GeographyClassification(
                country_code="US",
                label="United States",
                claim_ids=(MICRON_CLASSIFICATION_CLAIM_ID,),
            ),
            economic_drivers=(
                EconomicDriverTag(
                    driver_id="driver:memory-demand",
                    label="Memory demand",
                    claim_ids=(MICRON_DRIVER_CLAIM_ID,),
                ),
                EconomicDriverTag(
                    driver_id="driver:ai-infrastructure",
                    label="AI infrastructure",
                    claim_ids=(MICRON_DRIVER_CLAIM_ID,),
                ),
            ),
        ),
        CompanyExposureProfile(
            profile_id="profile:global-industrials",
            company_subject_id=INDUSTRIAL_COMPANY_ID,
            sector=SectorClassification(
                sector_id="sector:industrials",
                label="Industrials",
                claim_ids=(INDUSTRIAL_CLASSIFICATION_CLAIM_ID,),
            ),
            geography=GeographyClassification(
                country_code="DE",
                label="Germany",
                claim_ids=(INDUSTRIAL_CLASSIFICATION_CLAIM_ID,),
            ),
            economic_drivers=(
                EconomicDriverTag(
                    driver_id="driver:capital-spending",
                    label="Capital spending",
                    claim_ids=(INDUSTRIAL_DRIVER_CLAIM_ID,),
                ),
            ),
        ),
        CompanyExposureProfile(
            profile_id="profile:consumer-platform",
            company_subject_id=CONSUMER_COMPANY_ID,
            sector=SectorClassification(
                sector_id="sector:consumer-discretionary",
                label="Consumer Discretionary",
                claim_ids=(CONSUMER_CLASSIFICATION_CLAIM_ID,),
            ),
            geography=GeographyClassification(
                country_code="US",
                label="United States",
                claim_ids=(CONSUMER_CLASSIFICATION_CLAIM_ID,),
            ),
            economic_drivers=(
                EconomicDriverTag(
                    driver_id="driver:consumer-demand",
                    label="Consumer demand",
                    claim_ids=(CONSUMER_DRIVER_CLAIM_ID,),
                ),
            ),
        ),
    )
    return PortfolioExposureInput(
        knowledge_boundary=make_portfolio_draft().knowledge_boundary,
        top_company_count=3,
        evidence_items=evidence_items,
        claims=claims,
        etf_snapshots=etf_snapshots,
        company_profiles=company_profiles,
        hypothetical_position=HypotheticalPosition(
            hypothetical_id="hypothetical:core-etf:eur-500",
            instrument_id="instrument:core-equity-etf",
            amount=MonetaryAmount(amount=Decimal("500"), currency="EUR"),
            rationale="Measure exposure for an explicit supplied amount; do not recommend it.",
        ),
        missing_data=("Ten percent of each synthetic ETF snapshot remains unresolved.",),
        assumptions=("Economic-driver tags overlap, are non-additive, and are not causal edges.",),
    )


def build_reference_exposure() -> PortfolioExposure:
    portfolio_state = BuildPortfolioState().execute(make_portfolio_draft())
    return BuildPortfolioExposure().execute(portfolio_state, make_exposure_input())


def rebuild_exposure_input(
    exposure_input: PortfolioExposureInput,
    **overrides: object,
) -> PortfolioExposureInput:
    values = exposure_input.model_dump(mode="python")
    values.update(overrides)
    return PortfolioExposureInput.model_validate(values)
