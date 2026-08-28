"""Unit tests for Chapter 6B descriptive Portfolio Exposure."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from asymmetric_engine.application.portfolio_exposure import (
    BuildPortfolioExposure,
    PortfolioExposureIntegrityError,
)
from asymmetric_engine.application.portfolio_state import BuildPortfolioState
from asymmetric_engine.domain.evidence import ClaimType
from asymmetric_engine.domain.financial import MonetaryAmount
from asymmetric_engine.domain.portfolio import (
    ClassificationDimension,
    CompanyExposureProfile,
    CurrencyExposureBook,
    EconomicDriverTag,
    ExposureScenario,
    HypotheticalPosition,
    InstrumentType,
    PortfolioExposure,
    PortfolioExposureInput,
    PortfolioState,
    SectorClassification,
)
from asymmetric_engine.domain.temporal import KnowledgeBoundary
from tests.exposure_factories import (
    CONSUMER_CLASSIFICATION_EVIDENCE_ID,
    CONSUMER_COMPANY_ID,
    CONSUMER_DRIVER_CLAIM_ID,
    CORE_SNAPSHOT_EVIDENCE_ID,
    INDUSTRIAL_COMPANY_ID,
    MICRON_CLASSIFICATION_CLAIM_ID,
    MICRON_CLASSIFICATION_EVIDENCE_ID,
    MICRON_COMPANY_ID,
    MICRON_DRIVER_CLAIM_ID,
    THEMATIC_SNAPSHOT_EVIDENCE_ID,
    build_reference_exposure,
    make_exposure_input,
    rebuild_exposure_input,
)
from tests.portfolio_factories import make_portfolio_draft, rebuild_portfolio_draft


def _portfolio_state() -> PortfolioState:
    return BuildPortfolioState().execute(make_portfolio_draft())


def _book(
    exposure: PortfolioExposure,
    *,
    scenario: str,
    currency: str,
) -> CurrencyExposureBook:
    snapshot = exposure.before if scenario == "before" else exposure.after
    assert snapshot is not None
    return next(item for item in snapshot.currency_books if item.currency == currency)


def _without_hypothetical() -> PortfolioExposureInput:
    exposure_input = make_exposure_input()
    retained_company_ids = {MICRON_COMPANY_ID, INDUSTRIAL_COMPANY_ID}
    retained_profiles = tuple(
        item
        for item in exposure_input.company_profiles
        if item.company_subject_id in retained_company_ids
    )
    retained_claim_ids = {
        claim_id
        for profile in retained_profiles
        for claim_id in (
            *(profile.sector.claim_ids if profile.sector is not None else ()),
            *(profile.geography.claim_ids if profile.geography is not None else ()),
            *(claim_id for driver in profile.economic_drivers for claim_id in driver.claim_ids),
        )
    }
    retained_claims = tuple(
        item for item in exposure_input.claims if item.claim_id in retained_claim_ids
    )
    retained_evidence_ids = {
        THEMATIC_SNAPSHOT_EVIDENCE_ID,
        *(evidence_id for claim in retained_claims for evidence_id in claim.evidence_ids),
    }
    return rebuild_exposure_input(
        exposure_input,
        evidence_items=tuple(
            item
            for item in exposure_input.evidence_items
            if item.evidence_id in retained_evidence_ids
        ),
        claims=retained_claims,
        etf_snapshots=(exposure_input.etf_snapshots[0],),
        company_profiles=retained_profiles,
        hypothetical_position=None,
    )


def test_reference_exposure_keeps_currencies_and_direct_indirect_routes_separate() -> None:
    exposure = build_reference_exposure()
    eur_before = _book(exposure, scenario="before", currency="EUR")
    usd_before = _book(exposure, scenario="before", currency="USD")

    assert [item.currency for item in exposure.before.currency_books] == ["EUR", "USD"]
    assert not hasattr(exposure.before, "total_portfolio_value")
    assert eur_before.gross_position_value.amount == Decimal("200")
    assert usd_before.gross_position_value.amount == Decimal("1100")
    eur_micron = next(
        item
        for item in eur_before.company_exposures
        if item.company_subject_id == MICRON_COMPANY_ID
    )
    usd_micron = next(
        item
        for item in usd_before.company_exposures
        if item.company_subject_id == MICRON_COMPANY_ID
    )
    assert eur_micron.direct_value.amount == 0
    assert eur_micron.indirect_value.amount == Decimal("120")
    assert usd_micron.direct_value.amount == Decimal("1100")
    assert usd_micron.indirect_value.amount == 0


def test_reference_exposure_preserves_residual_as_hhi_bounds_and_unknown_buckets() -> None:
    exposure = build_reference_exposure()
    eur_before = _book(exposure, scenario="before", currency="EUR")

    assert eur_before.unresolved_exposure.value.amount == Decimal("20")
    assert eur_before.unresolved_exposure.weight == Decimal("0.1")
    assert eur_before.company_hhi.lower_bound == Decimal("0.45")
    assert eur_before.company_hhi.upper_bound == Decimal("0.46")
    assert eur_before.top_company_subject_ids == (MICRON_COMPANY_ID, INDUSTRIAL_COMPANY_ID)
    assert next(item for item in eur_before.sector_exposures if item.is_unknown).weight == (
        Decimal("0.1")
    )
    assert next(
        item for item in eur_before.economic_driver_exposures if item.is_unknown
    ).weight == Decimal("0.1")
    assert eur_before.economic_driver_exposures_are_non_additive


def test_supplied_amount_builds_before_after_without_selecting_or_sizing_it() -> None:
    exposure = build_reference_exposure()
    eur_after = _book(exposure, scenario="after", currency="EUR")

    assert exposure.after is not None
    assert exposure.after.scenario is ExposureScenario.HYPOTHETICAL_AFTER
    assert eur_after.gross_position_value.amount == Decimal("700")
    assert eur_after.unresolved_exposure.value.amount == Decimal("70")
    assert eur_after.company_hhi.lower_bound == Decimal("0.278571428571")
    assert eur_after.company_hhi.upper_bound == Decimal("0.288571428571")
    assert eur_after.top_company_subject_ids == (
        INDUSTRIAL_COMPANY_ID,
        CONSUMER_COMPANY_ID,
        MICRON_COMPANY_ID,
    )
    assert {item.instrument_id: item.value.amount for item in eur_after.instrument_exposures} == {
        "instrument:core-equity-etf": Decimal("500"),
        "instrument:thematic-etf": Decimal("200"),
    }
    assert not hasattr(exposure, "allocation")
    assert not hasattr(exposure, "score")


def test_input_order_does_not_change_content_address() -> None:
    state = _portfolio_state()
    exposure_input = make_exposure_input()
    reordered = rebuild_exposure_input(
        exposure_input,
        evidence_items=tuple(reversed(exposure_input.evidence_items)),
        claims=tuple(reversed(exposure_input.claims)),
        etf_snapshots=tuple(reversed(exposure_input.etf_snapshots)),
        company_profiles=tuple(reversed(exposure_input.company_profiles)),
        missing_data=tuple(reversed(exposure_input.missing_data)),
        assumptions=tuple(reversed(exposure_input.assumptions)),
    )
    builder = BuildPortfolioExposure()

    assert builder.execute(state, reordered) == builder.execute(state, exposure_input)


def test_round_trip_and_integrity_replay_reject_tampered_metrics() -> None:
    state = _portfolio_state()
    builder = BuildPortfolioExposure()
    exposure = builder.execute(state, make_exposure_input())
    restored = PortfolioExposure.model_validate_json(exposure.model_dump_json())

    assert restored == exposure
    assert builder.verify(state, restored) is restored
    values = restored.model_dump(mode="python")
    before = restored.before.model_dump(mode="python")
    eur_book = restored.before.currency_books[0].model_dump(mode="python")
    eur_book["company_hhi"] = {"lower_bound": Decimal("0"), "upper_bound": Decimal("0")}
    before["currency_books"] = (eur_book, *restored.before.currency_books[1:])
    values["before"] = before
    tampered = PortfolioExposure.model_validate(values)

    with pytest.raises(PortfolioExposureIntegrityError, match="canonical replay"):
        builder.verify(state, tampered)


def test_current_only_exposure_has_no_after_state_or_unused_etf_inputs() -> None:
    state = _portfolio_state()
    exposure = BuildPortfolioExposure().execute(state, _without_hypothetical())

    assert exposure.after is None
    assert exposure.hypothetical_position is None
    assert [item.etf_instrument_id for item in exposure.etf_snapshots] == [
        "instrument:thematic-etf"
    ]


def test_missing_classifications_remain_unknown_instead_of_zero() -> None:
    state = _portfolio_state()
    exposure_input = make_exposure_input()
    micron_profile = exposure_input.company_profiles[0]
    unknown_micron = CompanyExposureProfile(
        profile_id=micron_profile.profile_id,
        company_subject_id=micron_profile.company_subject_id,
        missing_dimensions=tuple(ClassificationDimension),
        missing_reason="No admissible Micron classification is available at T0.",
    )
    removed_claim_ids = {MICRON_CLASSIFICATION_CLAIM_ID, MICRON_DRIVER_CLAIM_ID}
    changed_input = rebuild_exposure_input(
        exposure_input,
        evidence_items=tuple(
            item
            for item in exposure_input.evidence_items
            if item.evidence_id != MICRON_CLASSIFICATION_EVIDENCE_ID
        ),
        claims=tuple(
            item for item in exposure_input.claims if item.claim_id not in removed_claim_ids
        ),
        company_profiles=(unknown_micron, *exposure_input.company_profiles[1:]),
    )
    exposure = BuildPortfolioExposure().execute(state, changed_input)
    usd_book = _book(exposure, scenario="before", currency="USD")

    assert usd_book.sector_exposures[0].is_unknown
    assert usd_book.sector_exposures[0].weight == Decimal(1)
    assert usd_book.geography_exposures[0].is_unknown
    assert usd_book.economic_driver_exposures[0].is_unknown


def test_unsupported_legacy_instrument_value_remains_fully_unresolved() -> None:
    draft = make_portfolio_draft()
    instruments = list(draft.instruments)
    instruments[2] = instruments[2].model_copy(
        update={"instrument_type": InstrumentType.OTHER, "etf_profile": None}
    )
    state = BuildPortfolioState().execute(
        rebuild_portfolio_draft(draft, instruments=tuple(instruments))
    )
    exposure_input = make_exposure_input()
    micron_claim_ids = {MICRON_CLASSIFICATION_CLAIM_ID, MICRON_DRIVER_CLAIM_ID}
    direct_only_input = rebuild_exposure_input(
        exposure_input,
        evidence_items=tuple(
            item
            for item in exposure_input.evidence_items
            if item.evidence_id == MICRON_CLASSIFICATION_EVIDENCE_ID
        ),
        claims=tuple(item for item in exposure_input.claims if item.claim_id in micron_claim_ids),
        etf_snapshots=(),
        company_profiles=(exposure_input.company_profiles[0],),
        hypothetical_position=None,
    )
    exposure = BuildPortfolioExposure().execute(state, direct_only_input)
    eur_book = _book(exposure, scenario="before", currency="EUR")

    assert eur_book.company_exposures == ()
    assert eur_book.unresolved_exposure.value.amount == Decimal("200")
    assert eur_book.unresolved_exposure.weight == Decimal(1)
    assert "no admitted one-level" in eur_book.unresolved_exposure.reasons[0]
    assert eur_book.company_hhi.lower_bound == 0
    assert eur_book.company_hhi.upper_bound == 1


@pytest.mark.parametrize(
    ("weight", "residual", "reason", "message"),
    [
        (Decimal("0.7"), Decimal("0.1"), "Residual", "must equal one"),
        (Decimal("0.6"), Decimal("0.1"), None, "requires unresolved_reason"),
        (Decimal("0.6"), Decimal("0"), "Residual", "must equal one"),
    ],
)
def test_etf_snapshot_rejects_incoherent_coverage(
    weight: Decimal,
    residual: Decimal,
    reason: str | None,
    message: str,
) -> None:
    snapshot = make_exposure_input().etf_snapshots[0]
    values = snapshot.model_dump(mode="python")
    constituents = list(snapshot.constituents)
    constituents[0] = constituents[0].model_copy(update={"weight": weight})
    values.update(
        constituents=tuple(constituents),
        unresolved_weight=residual,
        unresolved_reason=reason,
    )

    with pytest.raises(ValidationError, match=message):
        type(snapshot).model_validate(values)


def test_company_profile_requires_exact_missing_dimensions_and_reason() -> None:
    profile = make_exposure_input().company_profiles[0]
    values = profile.model_dump(mode="python")
    values["sector"] = None

    with pytest.raises(ValidationError, match="exactly identify"):
        CompanyExposureProfile.model_validate(values)

    values["missing_dimensions"] = (ClassificationDimension.SECTOR,)
    with pytest.raises(ValidationError, match="require missing_reason"):
        CompanyExposureProfile.model_validate(values)

    values["missing_reason"] = "Sector classification is unavailable."
    assert CompanyExposureProfile.model_validate(values).sector is None


def test_unknown_bucket_ids_and_duplicate_source_ids_are_reserved() -> None:
    exposure_input = make_exposure_input()
    with pytest.raises(ValidationError, match="reserved"):
        SectorClassification(
            sector_id="sector:unknown",
            label="Not actually known",
            claim_ids=(CONSUMER_DRIVER_CLAIM_ID,),
        )
    with pytest.raises(ValidationError, match="reserved"):
        EconomicDriverTag(
            driver_id="driver:unknown",
            label="Not actually known",
            claim_ids=(CONSUMER_DRIVER_CLAIM_ID,),
        )
    duplicate_snapshot_id = exposure_input.etf_snapshots[1].model_copy(
        update={"snapshot_id": exposure_input.etf_snapshots[0].snapshot_id}
    )
    with pytest.raises(ValidationError, match="duplicate ETF snapshot_ids"):
        rebuild_exposure_input(
            exposure_input,
            etf_snapshots=(exposure_input.etf_snapshots[0], duplicate_snapshot_id),
        )
    duplicate_profile_id = exposure_input.company_profiles[1].model_copy(
        update={"profile_id": exposure_input.company_profiles[0].profile_id}
    )
    with pytest.raises(ValidationError, match="duplicate company exposure profile_ids"):
        rebuild_exposure_input(
            exposure_input,
            company_profiles=(
                exposure_input.company_profiles[0],
                duplicate_profile_id,
                exposure_input.company_profiles[2],
            ),
        )


def test_exposure_input_rejects_future_or_repurposed_provenance() -> None:
    exposure_input = make_exposure_input()
    future = exposure_input.evidence_items[0].model_copy(
        update={
            "effective_at": exposure_input.as_of + timedelta(days=1),
            "available_at": exposure_input.as_of + timedelta(days=1),
            "recorded_at": exposure_input.as_of + timedelta(days=1),
        }
    )
    with pytest.raises(ValidationError, match="not effective by T0"):
        rebuild_exposure_input(
            exposure_input,
            evidence_items=(future, *exposure_input.evidence_items[1:]),
        )

    classification_evidence = next(
        item
        for item in exposure_input.evidence_items
        if item.evidence_id == CONSUMER_CLASSIFICATION_EVIDENCE_ID
    )
    reused_snapshot = exposure_input.etf_snapshots[0].model_copy(
        update={
            "evidence_id": CONSUMER_CLASSIFICATION_EVIDENCE_ID,
            "holdings_date": classification_evidence.effective_at.date(),
        }
    )
    with pytest.raises(ValidationError, match="separate evidence"):
        rebuild_exposure_input(
            exposure_input,
            etf_snapshots=(reused_snapshot, exposure_input.etf_snapshots[1]),
        )


def test_economic_driver_requires_interpretive_claim_and_all_inputs_must_be_used() -> None:
    exposure_input = make_exposure_input()
    driver_claim = next(
        item for item in exposure_input.claims if item.claim_id == CONSUMER_DRIVER_CLAIM_ID
    )
    observational = driver_claim.model_copy(update={"claim_type": ClaimType.OBSERVATION})
    claims = tuple(
        observational if item.claim_id == observational.claim_id else item
        for item in exposure_input.claims
    )
    with pytest.raises(ValidationError, match="require inference"):
        rebuild_exposure_input(exposure_input, claims=claims)

    with pytest.raises(ValidationError, match="every exposure claim"):
        rebuild_exposure_input(
            exposure_input,
            company_profiles=exposure_input.company_profiles[:-1],
        )


def test_builder_rejects_missing_or_extra_state_inputs() -> None:
    state = _portfolio_state()
    exposure_input = make_exposure_input()
    builder = BuildPortfolioExposure()

    with pytest.raises(ValueError, match="every analyzed equity ETF"):
        builder.execute(
            state,
            rebuild_exposure_input(
                exposure_input,
                etf_snapshots=(exposure_input.etf_snapshots[0],),
                evidence_items=tuple(
                    item
                    for item in exposure_input.evidence_items
                    if item.evidence_id != CORE_SNAPSHOT_EVIDENCE_ID
                ),
            ),
        )
    orphan_profile = CompanyExposureProfile(
        profile_id="profile:orphan",
        company_subject_id="company:orphan",
        missing_dimensions=tuple(ClassificationDimension),
        missing_reason="No classification evidence exists for this unused profile.",
    )
    with pytest.raises(ValueError, match="company profiles must exactly cover"):
        builder.execute(
            state,
            rebuild_exposure_input(
                exposure_input,
                company_profiles=(*exposure_input.company_profiles, orphan_profile),
            ),
        )


def test_builder_rejects_ineligible_unknown_or_wrong_currency_hypothetical() -> None:
    state = _portfolio_state()
    exposure_input = make_exposure_input()
    builder = BuildPortfolioExposure()

    ineligible = exposure_input.hypothetical_position
    assert ineligible is not None
    current_only_input = _without_hypothetical()
    with pytest.raises(ValueError, match="not eligible"):
        builder.execute(
            state,
            rebuild_exposure_input(
                current_only_input,
                hypothetical_position=ineligible.model_copy(
                    update={"instrument_id": "instrument:thematic-etf"}
                ),
            ),
        )
    with pytest.raises(ValueError, match="unknown canonical instrument"):
        builder.execute(
            state,
            rebuild_exposure_input(
                exposure_input,
                hypothetical_position=ineligible.model_copy(
                    update={"instrument_id": "instrument:unknown"}
                ),
            ),
        )
    with pytest.raises(ValueError, match="native currency"):
        builder.execute(
            state,
            rebuild_exposure_input(
                exposure_input,
                hypothetical_position=ineligible.model_copy(
                    update={"amount": MonetaryAmount(amount=Decimal("500"), currency="USD")}
                ),
            ),
        )


def test_builder_rejects_a_different_temporal_boundary() -> None:
    state = _portfolio_state()
    exposure_input = make_exposure_input()
    changed_boundary = KnowledgeBoundary(
        as_of=exposure_input.as_of - timedelta(hours=1),
        knowledge_mode=exposure_input.knowledge_mode,
    )
    values = exposure_input.model_dump(mode="python")
    values["knowledge_boundary"] = changed_boundary
    earlier_input = PortfolioExposureInput.model_validate(values)

    with pytest.raises(ValueError, match="Portfolio State knowledge boundary"):
        BuildPortfolioExposure().execute(state, earlier_input)


def test_hypothetical_and_output_envelopes_reject_incoherent_shape() -> None:
    with pytest.raises(ValidationError, match="greater than zero"):
        HypotheticalPosition(
            hypothetical_id="hypothetical:zero",
            instrument_id="instrument:core-equity-etf",
            amount=MonetaryAmount(amount=Decimal(0), currency="EUR"),
            rationale="Invalid zero amount.",
        )

    exposure = build_reference_exposure()
    values = exposure.model_dump(mode="python")
    values["hypothetical_position"] = None
    with pytest.raises(ValidationError, match="after exposure requires"):
        PortfolioExposure.model_validate(values)
    values = exposure.model_dump(mode="python")
    before = exposure.before.model_copy(update={"scenario": ExposureScenario.HYPOTHETICAL_AFTER})
    values["before"] = before
    with pytest.raises(ValidationError, match="before exposure"):
        PortfolioExposure.model_validate(values)
