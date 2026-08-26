"""Deterministic Chapter 5 fixtures with official identities and synthetic excerpts."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from hashlib import sha256
from uuid import NAMESPACE_URL, UUID, uuid5

from asymmetric_engine.application.causal_analysis import BuildCausalAnalysis
from asymmetric_engine.domain.causal import CausalAnalysis
from asymmetric_engine.domain.evidence import (
    AvailabilityBasis,
    Claim,
    ClaimType,
    Confidence,
    ConfidenceCalibrationStatus,
    DataQuality,
    EvidenceItem,
    SourceDocument,
    SourceDocumentDraft,
    SourceType,
)
from asymmetric_engine.domain.opportunity import (
    Catalyst,
    DerivedFinancialFact,
    DerivedMetric,
    DimensionOutcome,
    EligibilityGate,
    EligibilityGateKind,
    FinancialFact,
    FinancialFactBasis,
    FinancialFormula,
    FinancialMetric,
    FinancialPeriod,
    FinancialPeriodKind,
    FinancialUnit,
    GateResult,
    OpportunityStatus,
    PayoffProfile,
    RiskKind,
    ScenarioKind,
    UnderwritingDimension,
    UnderwritingDimensionKind,
    UnderwritingDraft,
    UnderwritingRisk,
    ValuationScenario,
)
from asymmetric_engine.infrastructure.providers.sec_edgar import SecEdgarProvider
from tests.causal_factories import make_causal_draft, make_reference_sources
from tests.memory_repository import MemorySourceRepository

MICRON_2025_REFERENCE = "0000723125/0000723125-25-000028"
UNDERWRITING_RECORDED_AT = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)
REFERENCE_PRICE_EFFECTIVE_AT = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)

MICRON_2025_CONTENT = b"""<SEC-DOCUMENT>
<ACCESSION-NUMBER>0000723125-25-000028
<CONFORMED-SUBMISSION-TYPE>10-K
<CONFORMED-PERIOD-OF-REPORT>20250828
<FILER><COMPANY-DATA>
<COMPANY-CONFORMED-NAME>MICRON TECHNOLOGY INC
<CENTRAL-INDEX-KEY>0000723125
</COMPANY-DATA></FILER>
<DOCUMENT>
AIE SYNTHETIC TEST FIXTURE, NOT AN SEC FILING COPY.
Fiscal 2025 revenue was $37,378 million versus $25,111 million in 2024; gross profit was
$14,873 million, operating income was $9,770 million, and net income was $8,539 million.
Operating cash flow was $17,525 million and capital expenditures were $15,857 million.
Cash and marketable investments were $11,936 million; current and long-term debt totaled
$14,577 million. Diluted weighted-average shares were 1,125 million versus 1,118 million.
Stock-based compensation expense was $975 million. Data-center revenue and margin improvement
were supported by AI demand and a richer HBM mix. Capital intensity, customer concentration,
cyclicality, qualification, and production-ramp execution remain material risks.
</DOCUMENT>
</SEC-DOCUMENT>"""

MARKET_PRICE_CONTENT = b"""AIE SYNTHETIC MARKET-DATA FIXTURE, NOT A REAL QUOTE.
MU illustrative reference price: USD 100.00 at 2026-08-25T12:00:00Z.
This value exists only to verify per-share scenario arithmetic and is not investment evidence.
"""

INCOME_EVIDENCE_ID = UUID("41000000-0000-4000-8000-000000000001")
CASH_FLOW_EVIDENCE_ID = UUID("41000000-0000-4000-8000-000000000002")
BALANCE_EVIDENCE_ID = UUID("41000000-0000-4000-8000-000000000003")
PER_SHARE_EVIDENCE_ID = UUID("41000000-0000-4000-8000-000000000004")
VALUE_CAPTURE_EVIDENCE_ID = UUID("41000000-0000-4000-8000-000000000005")
RISK_EVIDENCE_ID = UUID("41000000-0000-4000-8000-000000000006")
PRICE_EVIDENCE_ID = UUID("41000000-0000-4000-8000-000000000007")

INCOME_CLAIM_ID = UUID("51000000-0000-4000-8000-000000000001")
CASH_FLOW_CLAIM_ID = UUID("51000000-0000-4000-8000-000000000002")
BALANCE_CLAIM_ID = UUID("51000000-0000-4000-8000-000000000003")
PER_SHARE_CLAIM_ID = UUID("51000000-0000-4000-8000-000000000004")
VALUE_CAPTURE_CLAIM_ID = UUID("51000000-0000-4000-8000-000000000005")
CAPITAL_RISK_CLAIM_ID = UUID("51000000-0000-4000-8000-000000000006")
PRICE_CLAIM_ID = UUID("51000000-0000-4000-8000-000000000007")
NORMALIZATION_CLAIM_ID = UUID("51000000-0000-4000-8000-000000000008")
VALUATION_ASSUMPTION_CLAIM_ID = UUID("51000000-0000-4000-8000-000000000009")
CATALYST_CLAIM_ID = UUID("51000000-0000-4000-8000-000000000010")


def _source_document(draft: SourceDocumentDraft) -> SourceDocument:
    identity = json.dumps(
        (draft.provider, draft.provider_record_id, draft.provider_version),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return SourceDocument(
        document_id=uuid5(NAMESPACE_URL, identity),
        provider=draft.provider,
        provider_record_id=draft.provider_record_id,
        provider_version=draft.provider_version,
        subject_id=draft.subject_id,
        title=draft.title,
        source_uri=draft.source_uri,
        source_type=draft.source_type,
        effective_at=draft.effective_at,
        availability_basis=draft.availability_basis,
        available_at=UNDERWRITING_RECORDED_AT,
        recorded_at=UNDERWRITING_RECORDED_AT,
        media_type=draft.media_type,
        content_hash=sha256(draft.content).hexdigest(),
        content_size_bytes=len(draft.content),
    )


def make_underwriting_sources() -> tuple[tuple[SourceDocument, SourceDocument], dict[UUID, bytes]]:
    sec_draft = SecEdgarProvider(lambda _: MICRON_2025_CONTENT).fetch(MICRON_2025_REFERENCE)
    filing = _source_document(sec_draft)
    market_identity = json.dumps(
        ("synthetic-market-data", "MU", "2026-08-25T12:00:00Z"),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    market = SourceDocument(
        document_id=uuid5(NAMESPACE_URL, market_identity),
        provider="synthetic-market-data",
        provider_record_id="MU",
        provider_version="2026-08-25T12:00:00Z",
        subject_id="company:sec-cik-0000723125",
        title="Illustrative MU reference price fixture",
        source_uri="https://example.test/market-data/MU/2026-08-25T12:00:00Z",
        source_type=SourceType.MARKET_DATA,
        effective_at=REFERENCE_PRICE_EFFECTIVE_AT,
        availability_basis=AvailabilityBasis.PROVIDER_ASSERTED,
        available_at=UNDERWRITING_RECORDED_AT,
        recorded_at=UNDERWRITING_RECORDED_AT,
        media_type="text/plain",
        content_hash=sha256(MARKET_PRICE_CONTENT).hexdigest(),
        content_size_bytes=len(MARKET_PRICE_CONTENT),
    )
    return (filing, market), {
        filing.document_id: MICRON_2025_CONTENT,
        market.document_id: MARKET_PRICE_CONTENT,
    }


def _evidence(
    *,
    evidence_id: UUID,
    document: SourceDocument,
    title: str,
    locator: str,
) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=evidence_id,
        title=title,
        source_uri=document.source_uri,
        source_type=document.source_type,
        effective_at=document.effective_at,
        available_at=document.available_at,
        recorded_at=document.recorded_at,
        content_hash=document.content_hash,
        quality=DataQuality(
            coverage=0.75,
            source_reliability=0.9,
            point_in_time_integrity=1.0,
            missing_fields=("Independent normalization review",),
        ),
        source_document_id=document.document_id,
        source_locator=locator,
        extraction_method="deterministic manual fixture extraction",
    )


def _confidence(score: float, rationale: str) -> Confidence:
    return Confidence(
        score=score,
        rationale=rationale,
        calibration_status=ConfidenceCalibrationStatus.UNCALIBRATED,
        method_version="manual-underwriting-v1",
    )


def _claim(
    *,
    claim_id: UUID,
    text: str,
    claim_type: ClaimType,
    evidence_ids: tuple[UUID, ...],
    invalidation: str,
    score: float,
) -> Claim:
    return Claim(
        claim_id=claim_id,
        text=text,
        claim_type=claim_type,
        evidence_ids=evidence_ids,
        confidence=_confidence(
            score,
            "Manual reference-case annotation; it is not an empirical probability or gate.",
        ),
        invalidation_condition=invalidation,
    )


def _duration(start: date, end: date) -> FinancialPeriod:
    return FinancialPeriod(kind=FinancialPeriodKind.DURATION, start_date=start, end_date=end)


def _instant(end: date) -> FinancialPeriod:
    return FinancialPeriod(kind=FinancialPeriodKind.INSTANT, end_date=end)


def _reported_fact(
    *,
    fact_id: str,
    metric: FinancialMetric,
    value: str,
    unit: FinancialUnit,
    period: FinancialPeriod,
    claim_id: UUID,
) -> FinancialFact:
    return FinancialFact(
        fact_id=fact_id,
        metric=metric,
        value=Decimal(value),
        unit=unit,
        period=period,
        basis=FinancialFactBasis.REPORTED,
        claim_ids=(claim_id,),
    )


def _scenario(
    *,
    kind: ScenarioKind,
    enterprise_value: str,
    net_debt: str,
    diluted_shares: str,
    assumption: str,
) -> ValuationScenario:
    enterprise_value_decimal = Decimal(enterprise_value)
    net_debt_decimal = Decimal(net_debt)
    shares_decimal = Decimal(diluted_shares)
    reference_price = Decimal("100")
    equity_value = enterprise_value_decimal - net_debt_decimal
    value_per_share = equity_value / shares_decimal
    scenario_return = value_per_share / reference_price - Decimal(1)
    return ValuationScenario(
        kind=kind,
        method="illustrative enterprise-value bridge",
        method_version="illustrative-ev-bridge-v1",
        enterprise_value_usd_millions=enterprise_value_decimal,
        net_debt_usd_millions=net_debt_decimal,
        equity_value_usd_millions=equity_value,
        diluted_shares_millions=shares_decimal,
        value_per_share_usd=value_per_share,
        reference_price_usd=reference_price,
        return_from_reference=scenario_return,
        supporting_fact_ids=(
            "derived:free-cash-flow",
            "derived:net-debt",
            "reported:diluted-shares-2025",
            "reported:reference-price",
            "reported:revenue-2025",
        ),
        assumption_claim_ids=(VALUATION_ASSUMPTION_CLAIM_ID,),
        rationale=(
            "The scenario exposes enterprise value, debt, dilution, and per-share arithmetic; "
            "the illustrative enterprise value is not a price target."
        ),
        assumptions=(assumption,),
        invalidation_conditions=(
            "The operating and capital assumptions no longer support the stated enterprise value.",
        ),
    )


def make_underwriting_draft(
    *,
    causal_analysis: CausalAnalysis,
    documents: tuple[SourceDocument, SourceDocument] | None = None,
    status: OpportunityStatus = OpportunityStatus.READY_FOR_PORTFOLIO_REVIEW,
) -> UnderwritingDraft:
    if documents is None:
        documents, _ = make_underwriting_sources()
    filing = next(document for document in documents if document.source_type is SourceType.FILING)
    market = next(
        document for document in documents if document.source_type is SourceType.MARKET_DATA
    )
    evidence = (
        _evidence(
            evidence_id=INCOME_EVIDENCE_ID,
            document=filing,
            title="Fiscal 2025 income statement facts",
            locator="synthetic fixture: revenue through net-income sentences",
        ),
        _evidence(
            evidence_id=CASH_FLOW_EVIDENCE_ID,
            document=filing,
            title="Fiscal 2025 operating cash flow and capital expenditures",
            locator="synthetic fixture: cash-flow sentence",
        ),
        _evidence(
            evidence_id=BALANCE_EVIDENCE_ID,
            document=filing,
            title="Fiscal 2025 cash, investments, and debt",
            locator="synthetic fixture: balance-sheet sentence",
        ),
        _evidence(
            evidence_id=PER_SHARE_EVIDENCE_ID,
            document=filing,
            title="Diluted shares and stock-based compensation",
            locator="synthetic fixture: per-share sentence",
        ),
        _evidence(
            evidence_id=VALUE_CAPTURE_EVIDENCE_ID,
            document=filing,
            title="Issuer-reported AI and HBM value-capture indicators",
            locator="synthetic fixture: data-centre and HBM sentence",
        ),
        _evidence(
            evidence_id=RISK_EVIDENCE_ID,
            document=filing,
            title="Issuer-disclosed capital, concentration, cycle, and execution risks",
            locator="synthetic fixture: risk sentence",
        ),
        _evidence(
            evidence_id=PRICE_EVIDENCE_ID,
            document=market,
            title="Illustrative per-share reference price",
            locator="line 2",
        ),
    )
    claims = (
        _claim(
            claim_id=INCOME_CLAIM_ID,
            text="Micron reported fiscal 2025 revenue, profit, and operating-income figures.",
            claim_type=ClaimType.OBSERVATION,
            evidence_ids=(INCOME_EVIDENCE_ID,),
            invalidation="The filing is amended or the extracted units are shown to be wrong.",
            score=0.95,
        ),
        _claim(
            claim_id=CASH_FLOW_CLAIM_ID,
            text="Micron reported operating cash flow and gross capital expenditures for 2025.",
            claim_type=ClaimType.OBSERVATION,
            evidence_ids=(CASH_FLOW_EVIDENCE_ID,),
            invalidation="The cash-flow statement is amended or the capex convention changes.",
            score=0.95,
        ),
        _claim(
            claim_id=BALANCE_CLAIM_ID,
            text="Reported cash and investments were below reported current plus long-term debt.",
            claim_type=ClaimType.OBSERVATION,
            evidence_ids=(BALANCE_EVIDENCE_ID,),
            invalidation="The balance-sheet extraction or debt perimeter is corrected.",
            score=0.9,
        ),
        _claim(
            claim_id=PER_SHARE_CLAIM_ID,
            text="Diluted shares increased and stock-based compensation remained material.",
            claim_type=ClaimType.OBSERVATION,
            evidence_ids=(PER_SHARE_EVIDENCE_ID,),
            invalidation="The share-count or compensation disclosure is restated.",
            score=0.9,
        ),
        _claim(
            claim_id=VALUE_CAPTURE_CLAIM_ID,
            text="The filing links data-centre improvement to AI demand and a richer HBM mix.",
            claim_type=ClaimType.INFERENCE,
            evidence_ids=(VALUE_CAPTURE_EVIDENCE_ID,),
            invalidation=(
                "HBM mix fails to improve sustainable margins or competitive value capture."
            ),
            score=0.65,
        ),
        _claim(
            claim_id=CAPITAL_RISK_CLAIM_ID,
            text=(
                "Capital intensity, concentration, cyclicality, qualification, and ramp remain "
                "risks."
            ),
            claim_type=ClaimType.QUALITATIVE_JUDGEMENT,
            evidence_ids=(RISK_EVIDENCE_ID,),
            invalidation="Independent evidence demonstrates that these risks are immaterial.",
            score=0.7,
        ),
        _claim(
            claim_id=PRICE_CLAIM_ID,
            text="The contract fixture declares an illustrative USD 100 reference price.",
            claim_type=ClaimType.OBSERVATION,
            evidence_ids=(PRICE_EVIDENCE_ID,),
            invalidation="The fixture price or its timestamp changes.",
            score=1.0,
        ),
        _claim(
            claim_id=NORMALIZATION_CLAIM_ID,
            text="Illustrative normalized NOPAT and invested capital isolate the formula boundary.",
            claim_type=ClaimType.INFERENCE,
            evidence_ids=(INCOME_EVIDENCE_ID, BALANCE_EVIDENCE_ID),
            invalidation="A reviewed normalization method replaces the illustrative assumptions.",
            score=0.4,
        ),
        _claim(
            claim_id=VALUATION_ASSUMPTION_CLAIM_ID,
            text=(
                "Bear, base, and bull enterprise values are uncalibrated contract-test assumptions."
            ),
            claim_type=ClaimType.HYPOTHESIS,
            evidence_ids=(INCOME_EVIDENCE_ID, CASH_FLOW_EVIDENCE_ID, PRICE_EVIDENCE_ID),
            invalidation="A calibrated valuation model supersedes the illustrative scenario set.",
            score=0.3,
        ),
        _claim(
            claim_id=CATALYST_CLAIM_ID,
            text=(
                "Future HBM qualification and ramp disclosures can resolve value-capture "
                "uncertainty."
            ),
            claim_type=ClaimType.HYPOTHESIS,
            evidence_ids=(VALUE_CAPTURE_EVIDENCE_ID, RISK_EVIDENCE_ID),
            invalidation=(
                "The product cycle ends without an observable qualification or ramp event."
            ),
            score=0.55,
        ),
    )

    fy2024 = _duration(date(2023, 9, 1), date(2024, 8, 29))
    fy2025 = _duration(date(2024, 8, 30), date(2025, 8, 28))
    financial_facts = (
        _reported_fact(
            fact_id="reported:revenue-2024",
            metric=FinancialMetric.REVENUE,
            value="25111",
            unit=FinancialUnit.USD_MILLIONS,
            period=fy2024,
            claim_id=INCOME_CLAIM_ID,
        ),
        _reported_fact(
            fact_id="reported:revenue-2025",
            metric=FinancialMetric.REVENUE,
            value="37378",
            unit=FinancialUnit.USD_MILLIONS,
            period=fy2025,
            claim_id=INCOME_CLAIM_ID,
        ),
        _reported_fact(
            fact_id="reported:gross-profit-2025",
            metric=FinancialMetric.GROSS_PROFIT,
            value="14873",
            unit=FinancialUnit.USD_MILLIONS,
            period=fy2025,
            claim_id=INCOME_CLAIM_ID,
        ),
        _reported_fact(
            fact_id="reported:operating-income-2025",
            metric=FinancialMetric.OPERATING_INCOME,
            value="9770",
            unit=FinancialUnit.USD_MILLIONS,
            period=fy2025,
            claim_id=INCOME_CLAIM_ID,
        ),
        _reported_fact(
            fact_id="reported:net-income-2025",
            metric=FinancialMetric.NET_INCOME,
            value="8539",
            unit=FinancialUnit.USD_MILLIONS,
            period=fy2025,
            claim_id=INCOME_CLAIM_ID,
        ),
        _reported_fact(
            fact_id="reported:operating-cash-flow-2025",
            metric=FinancialMetric.OPERATING_CASH_FLOW,
            value="17525",
            unit=FinancialUnit.USD_MILLIONS,
            period=fy2025,
            claim_id=CASH_FLOW_CLAIM_ID,
        ),
        _reported_fact(
            fact_id="reported:capital-expenditures-2025",
            metric=FinancialMetric.CAPITAL_EXPENDITURES,
            value="15857",
            unit=FinancialUnit.USD_MILLIONS,
            period=fy2025,
            claim_id=CASH_FLOW_CLAIM_ID,
        ),
        _reported_fact(
            fact_id="reported:cash-and-investments-2025",
            metric=FinancialMetric.CASH_AND_INVESTMENTS,
            value="11936",
            unit=FinancialUnit.USD_MILLIONS,
            period=_instant(date(2025, 8, 28)),
            claim_id=BALANCE_CLAIM_ID,
        ),
        _reported_fact(
            fact_id="reported:total-debt-2025",
            metric=FinancialMetric.TOTAL_DEBT,
            value="14577",
            unit=FinancialUnit.USD_MILLIONS,
            period=_instant(date(2025, 8, 28)),
            claim_id=BALANCE_CLAIM_ID,
        ),
        _reported_fact(
            fact_id="reported:diluted-shares-2024",
            metric=FinancialMetric.DILUTED_SHARES,
            value="1118",
            unit=FinancialUnit.SHARES_MILLIONS,
            period=fy2024,
            claim_id=PER_SHARE_CLAIM_ID,
        ),
        _reported_fact(
            fact_id="reported:diluted-shares-2025",
            metric=FinancialMetric.DILUTED_SHARES,
            value="1125",
            unit=FinancialUnit.SHARES_MILLIONS,
            period=fy2025,
            claim_id=PER_SHARE_CLAIM_ID,
        ),
        _reported_fact(
            fact_id="reported:share-based-compensation-2025",
            metric=FinancialMetric.SHARE_BASED_COMPENSATION,
            value="975",
            unit=FinancialUnit.USD_MILLIONS,
            period=fy2025,
            claim_id=PER_SHARE_CLAIM_ID,
        ),
        FinancialFact(
            fact_id="adjusted:normalized-nopat-2025",
            metric=FinancialMetric.NORMALIZED_NOPAT,
            value=Decimal("8636.68"),
            unit=FinancialUnit.USD_MILLIONS,
            period=fy2025,
            basis=FinancialFactBasis.ANALYST_ADJUSTED,
            claim_ids=(NORMALIZATION_CLAIM_ID,),
            normalization_note="Illustrative operating income after an assumed 11.6% tax rate.",
        ),
        FinancialFact(
            fact_id="adjusted:average-invested-capital-2025",
            metric=FinancialMetric.AVERAGE_INVESTED_CAPITAL,
            value=Decimal("50000"),
            unit=FinancialUnit.USD_MILLIONS,
            period=fy2025,
            basis=FinancialFactBasis.ANALYST_ADJUSTED,
            claim_ids=(NORMALIZATION_CLAIM_ID,),
            normalization_note="Illustrative average capital base for formula verification only.",
        ),
        _reported_fact(
            fact_id="reported:reference-price",
            metric=FinancialMetric.REFERENCE_SHARE_PRICE,
            value="100",
            unit=FinancialUnit.USD_PER_SHARE,
            period=_instant(date(2026, 8, 25)),
            claim_id=PRICE_CLAIM_ID,
        ),
    )
    facts = {fact.fact_id: fact for fact in financial_facts}
    derived_facts = (
        DerivedFinancialFact(
            fact_id="derived:revenue-growth",
            metric=DerivedMetric.REVENUE_GROWTH,
            value=(facts["reported:revenue-2025"].value - facts["reported:revenue-2024"].value)
            / facts["reported:revenue-2024"].value,
            unit=FinancialUnit.RATIO,
            formula=FinancialFormula.CURRENT_MINUS_PRIOR_OVER_PRIOR,
            input_fact_ids=("reported:revenue-2024", "reported:revenue-2025"),
            calculation_version="fundamental-formulas-v1",
        ),
        DerivedFinancialFact(
            fact_id="derived:gross-margin",
            metric=DerivedMetric.GROSS_MARGIN,
            value=facts["reported:gross-profit-2025"].value / facts["reported:revenue-2025"].value,
            unit=FinancialUnit.RATIO,
            formula=FinancialFormula.GROSS_PROFIT_OVER_REVENUE,
            input_fact_ids=("reported:revenue-2025", "reported:gross-profit-2025"),
            calculation_version="fundamental-formulas-v1",
        ),
        DerivedFinancialFact(
            fact_id="derived:free-cash-flow",
            metric=DerivedMetric.FREE_CASH_FLOW,
            value=facts["reported:operating-cash-flow-2025"].value
            - facts["reported:capital-expenditures-2025"].value,
            unit=FinancialUnit.USD_MILLIONS,
            formula=FinancialFormula.OPERATING_CASH_FLOW_MINUS_CAPEX,
            input_fact_ids=(
                "reported:operating-cash-flow-2025",
                "reported:capital-expenditures-2025",
            ),
            calculation_version="fundamental-formulas-v1",
        ),
        DerivedFinancialFact(
            fact_id="derived:net-debt",
            metric=DerivedMetric.NET_DEBT,
            value=facts["reported:total-debt-2025"].value
            - facts["reported:cash-and-investments-2025"].value,
            unit=FinancialUnit.USD_MILLIONS,
            formula=FinancialFormula.DEBT_MINUS_CASH,
            input_fact_ids=("reported:total-debt-2025", "reported:cash-and-investments-2025"),
            calculation_version="fundamental-formulas-v1",
        ),
        DerivedFinancialFact(
            fact_id="derived:diluted-share-growth",
            metric=DerivedMetric.DILUTED_SHARE_GROWTH,
            value=(
                facts["reported:diluted-shares-2025"].value
                - facts["reported:diluted-shares-2024"].value
            )
            / facts["reported:diluted-shares-2024"].value,
            unit=FinancialUnit.RATIO,
            formula=FinancialFormula.CURRENT_MINUS_PRIOR_OVER_PRIOR,
            input_fact_ids=(
                "reported:diluted-shares-2024",
                "reported:diluted-shares-2025",
            ),
            calculation_version="fundamental-formulas-v1",
        ),
        DerivedFinancialFact(
            fact_id="derived:return-on-invested-capital",
            metric=DerivedMetric.RETURN_ON_INVESTED_CAPITAL,
            value=facts["adjusted:normalized-nopat-2025"].value
            / facts["adjusted:average-invested-capital-2025"].value,
            unit=FinancialUnit.RATIO,
            formula=FinancialFormula.NOPAT_OVER_AVERAGE_INVESTED_CAPITAL,
            input_fact_ids=(
                "adjusted:normalized-nopat-2025",
                "adjusted:average-invested-capital-2025",
            ),
            calculation_version="fundamental-formulas-v1",
        ),
    )
    dimensions = (
        UnderwritingDimension(
            kind=UnderwritingDimensionKind.REVENUE_AND_MARGINS,
            outcome=DimensionOutcome.SUPPORTIVE,
            rationale="Reported revenue and gross profit improved strongly from the prior year.",
            claim_ids=(INCOME_CLAIM_ID, VALUE_CAPTURE_CLAIM_ID),
            fact_ids=(
                "reported:revenue-2024",
                "reported:revenue-2025",
                "reported:gross-profit-2025",
                "derived:revenue-growth",
                "derived:gross-margin",
            ),
            invalidation_conditions=(
                "A restatement removes the reported revenue or gross-profit improvement.",
            ),
        ),
        UnderwritingDimension(
            kind=UnderwritingDimensionKind.CASH_GENERATION_AND_EARNINGS_QUALITY,
            outcome=DimensionOutcome.MIXED,
            rationale=(
                "Cash generation recovered, but gross capex absorbs most operating cash flow."
            ),
            claim_ids=(INCOME_CLAIM_ID, CASH_FLOW_CLAIM_ID, PER_SHARE_CLAIM_ID),
            fact_ids=(
                "reported:operating-income-2025",
                "reported:net-income-2025",
                "reported:operating-cash-flow-2025",
                "reported:capital-expenditures-2025",
                "reported:share-based-compensation-2025",
                "derived:free-cash-flow",
            ),
        ),
        UnderwritingDimension(
            kind=UnderwritingDimensionKind.RETURNS_ON_INVESTED_CAPITAL,
            outcome=DimensionOutcome.MIXED,
            rationale="Illustrative ROIC is positive but depends on unreviewed normalization.",
            claim_ids=(NORMALIZATION_CLAIM_ID,),
            fact_ids=(
                "adjusted:normalized-nopat-2025",
                "adjusted:average-invested-capital-2025",
                "derived:return-on-invested-capital",
            ),
            missing_data=("Independent review of normalized NOPAT and invested capital",),
        ),
        UnderwritingDimension(
            kind=UnderwritingDimensionKind.BALANCE_SHEET_AND_CAPITAL_NEEDS,
            outcome=DimensionOutcome.MIXED,
            rationale="Liquidity is substantial, while debt and fabrication capex remain material.",
            claim_ids=(BALANCE_CLAIM_ID, CASH_FLOW_CLAIM_ID, CAPITAL_RISK_CLAIM_ID),
            fact_ids=(
                "reported:cash-and-investments-2025",
                "reported:total-debt-2025",
                "reported:capital-expenditures-2025",
                "derived:net-debt",
            ),
        ),
        UnderwritingDimension(
            kind=UnderwritingDimensionKind.DILUTION_AND_PER_SHARE_ECONOMICS,
            outcome=DimensionOutcome.MIXED,
            rationale=(
                "Diluted shares rose and compensation must remain visible in per-share cases."
            ),
            claim_ids=(PER_SHARE_CLAIM_ID,),
            fact_ids=(
                "reported:diluted-shares-2024",
                "reported:diluted-shares-2025",
                "reported:share-based-compensation-2025",
                "derived:diluted-share-growth",
            ),
        ),
        UnderwritingDimension(
            kind=UnderwritingDimensionKind.VALUE_CAPTURE_AND_COMPETITION,
            outcome=DimensionOutcome.MIXED,
            rationale=(
                "HBM mix supports value capture, but durability and competitive share are "
                "unresolved."
            ),
            claim_ids=(VALUE_CAPTURE_CLAIM_ID, CAPITAL_RISK_CLAIM_ID),
            fact_ids=("reported:revenue-2025", "derived:gross-margin"),
            missing_data=("Independent HBM share and unit-economics evidence",),
            conflicts=(
                "Issuer evidence supports HBM progress but does not independently establish "
                "durable competitive share.",
            ),
        ),
        UnderwritingDimension(
            kind=UnderwritingDimensionKind.OPERATING_EXECUTION,
            outcome=DimensionOutcome.MIXED,
            rationale=(
                "The opportunity depends on qualification, capacity, and production-ramp delivery."
            ),
            claim_ids=(VALUE_CAPTURE_CLAIM_ID, CAPITAL_RISK_CLAIM_ID, CATALYST_CLAIM_ID),
            fact_ids=("reported:capital-expenditures-2025",),
        ),
        UnderwritingDimension(
            kind=UnderwritingDimensionKind.VALUATION_AND_ASYMMETRY,
            outcome=DimensionOutcome.MIXED,
            rationale="Per-share scenarios are transparent but deliberately uncalibrated.",
            claim_ids=(PRICE_CLAIM_ID, VALUATION_ASSUMPTION_CLAIM_ID),
            fact_ids=(
                "reported:reference-price",
                "reported:diluted-shares-2025",
                "derived:net-debt",
            ),
            missing_data=("Calibrated valuation method and scenario probabilities",),
            assumptions=(
                "Enterprise values are illustrative scenario inputs, not inferred price targets.",
                "Scenario labels do not imply probabilities.",
            ),
            invalidation_conditions=(
                "A reviewed valuation method supersedes the illustrative scenario bridge.",
            ),
        ),
    )
    gates = (
        EligibilityGate(
            kind=EligibilityGateKind.CAUSAL_HANDOFF,
            result=GateResult.PASS,
            rationale="The input causal analysis is content-addressed and ready for underwriting.",
            method_version="underwriting-gates-v1",
        ),
        EligibilityGate(
            kind=EligibilityGateKind.SURVIVABILITY,
            result=GateResult.PASS,
            rationale="Reported liquidity and cash generation permit a bounded resilience review.",
            method_version="underwriting-gates-v1",
            claim_ids=(BALANCE_CLAIM_ID, CASH_FLOW_CLAIM_ID),
        ),
        EligibilityGate(
            kind=EligibilityGateKind.ECONOMIC_VALUE_CAPTURE,
            result=GateResult.PASS,
            rationale=(
                "Issuer evidence supports an HBM value-capture hypothesis for scenario testing."
            ),
            method_version="underwriting-gates-v1",
            claim_ids=(VALUE_CAPTURE_CLAIM_ID,),
        ),
        EligibilityGate(
            kind=EligibilityGateKind.PER_SHARE_INTEGRITY,
            result=GateResult.PASS,
            rationale="Diluted shares and stock compensation are explicit in the assessment.",
            method_version="underwriting-gates-v1",
            claim_ids=(PER_SHARE_CLAIM_ID,),
        ),
        EligibilityGate(
            kind=EligibilityGateKind.VALUATION_COMPLETENESS,
            result=GateResult.PASS,
            rationale="All three cases expose the enterprise-to-equity and per-share bridge.",
            method_version="underwriting-gates-v1",
            claim_ids=(PRICE_CLAIM_ID, VALUATION_ASSUMPTION_CLAIM_ID),
        ),
        EligibilityGate(
            kind=EligibilityGateKind.FALSIFIABILITY,
            result=GateResult.PASS,
            rationale="Risks, catalysts, assumptions, and invalidation conditions are explicit.",
            method_version="underwriting-gates-v1",
            claim_ids=(CAPITAL_RISK_CLAIM_ID, CATALYST_CLAIM_ID),
        ),
    )
    scenarios = (
        _scenario(
            kind=ScenarioKind.BEAR,
            enterprise_value="80000",
            net_debt="3000",
            diluted_shares="1140",
            assumption="HBM value capture fades while capital intensity and dilution rise.",
        ),
        _scenario(
            kind=ScenarioKind.BASE,
            enterprise_value="125000",
            net_debt="2500",
            diluted_shares="1130",
            assumption="HBM mix persists without assuming a permanent scarcity premium.",
        ),
        _scenario(
            kind=ScenarioKind.BULL,
            enterprise_value="220000",
            net_debt="2000",
            diluted_shares="1125",
            assumption="Qualification, share, pricing, and operating leverage outperform.",
        ),
    )
    by_kind = {scenario.kind: scenario for scenario in scenarios}
    bear = by_kind[ScenarioKind.BEAR].return_from_reference
    base = by_kind[ScenarioKind.BASE].return_from_reference
    bull = by_kind[ScenarioKind.BULL].return_from_reference
    payoff = PayoffProfile(
        bear_return=bear,
        base_return=base,
        bull_return=bull,
        upside_to_downside_ratio=bull / abs(bear),
        method_version="probability-free-payoff-v1",
        rationale=(
            "The ratio compares explicit bull upside with bear downside and assigns no scenario "
            "probabilities."
        ),
    )
    return UnderwritingDraft(
        case_id="ai-hbm-micron-underwriting",
        candidate_id="company:sec-cik-0000723125",
        causal_analysis=causal_analysis,
        knowledge_boundary=causal_analysis.knowledge_boundary,
        method_version="investment-underwriting-v1",
        status=status,
        readiness_rationale=(
            "All standalone dimensions, eligibility gates, scenario arithmetic, risks, catalysts, "
            "and invalidations are explicit; Portfolio may review the unchanged state."
        ),
        thesis_summary=(
            "Micron may capture part of rising HBM economics, but the standalone case remains "
            "conditional on cycle durability, execution, capital intensity, and per-share value."
        ),
        source_document_ids=tuple(document.document_id for document in documents),
        evidence=evidence,
        claims=claims,
        financial_facts=financial_facts,
        derived_facts=derived_facts,
        dimensions=dimensions,
        eligibility_gates=gates,
        valuation_scenarios=scenarios,
        payoff_profile=payoff,
        catalysts=(
            Catalyst(
                catalyst_id="catalyst:hbm-qualification-and-ramp",
                description="Observable HBM qualification, shipment, and margin-ramp disclosures.",
                window_start=date(2026, 9, 1),
                window_end=date(2027, 8, 31),
                claim_ids=(CATALYST_CLAIM_ID,),
                monitoring_condition=(
                    "Review each filing for HBM qualification, mix, and margin data."
                ),
            ),
        ),
        risks=(
            UnderwritingRisk(
                risk_id="risk:memory-cycle-reversal",
                kind=RiskKind.DEMAND,
                description="A memory-cycle reversal can erase pricing and operating leverage.",
                claim_ids=(CAPITAL_RISK_CLAIM_ID,),
                monitoring_condition=(
                    "Track demand, inventory, pricing, and customer concentration."
                ),
                invalidation_condition="Sustained oversupply breaks the HBM value-capture case.",
            ),
            UnderwritingRisk(
                risk_id="risk:hbm-ramp-execution",
                kind=RiskKind.OPERATING_EXECUTION,
                description="Qualification or ramp delays can prevent economic capture.",
                claim_ids=(CAPITAL_RISK_CLAIM_ID, CATALYST_CLAIM_ID),
                monitoring_condition=(
                    "Track qualification, yield, shipment, and capacity milestones."
                ),
                invalidation_condition="Material qualification failure or persistent ramp delay.",
            ),
            UnderwritingRisk(
                risk_id="risk:valuation-assumption",
                kind=RiskKind.VALUATION,
                description="Illustrative enterprise values are not calibrated price targets.",
                claim_ids=(VALUATION_ASSUMPTION_CLAIM_ID,),
                monitoring_condition=(
                    "Replace fixtures with a reviewed, versioned valuation method."
                ),
                invalidation_condition="The selected valuation method fails out-of-sample review.",
            ),
        ),
        invalidation_conditions=(
            "The causal HBM beneficiary path is invalidated.",
            "Micron cannot convert HBM demand into durable per-share cash economics.",
            "Capital needs or dilution eliminate the modeled equity-value bridge.",
        ),
        missing_data=(
            "Independent HBM market-share and unit-economics evidence",
            "Calibrated valuation method and scenario probabilities",
            "Reviewed NOPAT and invested-capital normalization",
        ),
        assumptions=(
            "The reference price and enterprise values are synthetic contract fixtures.",
            "Scenario labels do not imply probabilities or portfolio actions.",
        ),
    )


def make_underwriting_context() -> tuple[MemorySourceRepository, UnderwritingDraft]:
    """Build a complete in-memory causal-to-underwriting test context."""

    causal_documents, causal_contents = make_reference_sources()
    repository = MemorySourceRepository(
        documents={document.document_id: document for document in causal_documents},
        contents=dict(causal_contents),
    )
    causal_analysis = BuildCausalAnalysis(repository).execute(
        make_causal_draft(documents=causal_documents)
    )
    underwriting_documents, underwriting_contents = make_underwriting_sources()
    for document in underwriting_documents:
        repository.append(document, underwriting_contents[document.document_id])
    return repository, make_underwriting_draft(
        causal_analysis=causal_analysis,
        documents=underwriting_documents,
    )
