"""Build deterministic descriptive Portfolio Exposure from a verified factual state."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import ROUND_HALF_EVEN, Decimal
from hashlib import sha256
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from asymmetric_engine.application.portfolio_state import BuildPortfolioState
from asymmetric_engine.domain.financial import MonetaryAmount, canonical_decimal
from asymmetric_engine.domain.portfolio.exposure import (
    CategoryExposure,
    CompanyExposure,
    CompanyExposureProfile,
    CurrencyExposureBook,
    DriverExposure,
    ETFConstituentSnapshot,
    ExposureScenario,
    ExposureSnapshot,
    GeographyClassification,
    HHIBounds,
    HypotheticalPosition,
    InstrumentExposure,
    PortfolioExposure,
    PortfolioExposureInput,
    PortfolioStateReference,
    SectorClassification,
    UnresolvedExposure,
)
from asymmetric_engine.domain.portfolio.models import (
    Instrument,
    InstrumentType,
    PortfolioState,
)

_RATIO_QUANTUM = Decimal("0.000000000001")


class PortfolioExposureIntegrityError(ValueError):
    """A serialized exposure no longer matches its canonical inputs and derivation."""


@dataclass
class _CompanyAccumulator:
    direct: Decimal = Decimal(0)
    indirect: Decimal = Decimal(0)
    direct_instrument_ids: set[str] = field(default_factory=set)
    indirect_instrument_ids: set[str] = field(default_factory=set)


@dataclass
class _CategoryAccumulator:
    label: str
    value: Decimal = Decimal(0)
    company_subject_ids: set[str] = field(default_factory=set)


class BuildPortfolioExposure:
    """Derive one-level exposure without fit, scoring, sizing, or allocation authority."""

    def __init__(self, *, state_builder: BuildPortfolioState | None = None) -> None:
        self._state_builder = state_builder or BuildPortfolioState()

    def execute(
        self,
        portfolio_state: PortfolioState,
        exposure_input: PortfolioExposureInput,
    ) -> PortfolioExposure:
        """Return the same exposure state for the same verified state and semantic input."""

        verified_state = self._state_builder.verify(portfolio_state)
        canonical_input = self._canonicalize_input(exposure_input)
        self._validate_state_inputs(verified_state, canonical_input)
        state_reference = PortfolioStateReference(
            portfolio_state_id=verified_state.portfolio_state_id,
            portfolio_id=verified_state.portfolio_id,
            input_fingerprint=verified_state.input_fingerprint,
            knowledge_boundary=verified_state.knowledge_boundary,
        )
        canonical_json = json.dumps(
            {
                "portfolio_state": state_reference.model_dump(mode="json"),
                "exposure_input": canonical_input.model_dump(mode="json"),
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        fingerprint = sha256(canonical_json).hexdigest()
        before = self._build_snapshot(
            verified_state,
            canonical_input,
            scenario=ExposureScenario.CURRENT,
            hypothetical=None,
        )
        hypothetical = canonical_input.hypothetical_position
        after = (
            self._build_snapshot(
                verified_state,
                canonical_input,
                scenario=ExposureScenario.HYPOTHETICAL_AFTER,
                hypothetical=hypothetical,
            )
            if hypothetical is not None
            else None
        )
        return PortfolioExposure.model_validate(
            {
                "exposure_id": uuid5(
                    NAMESPACE_URL,
                    f"asymmetric-insight-engine:portfolio-exposure:{fingerprint}",
                ),
                "portfolio_state": state_reference,
                "input_fingerprint": fingerprint,
                **canonical_input.model_dump(mode="python"),
                "before": before,
                "after": after,
            }
        )

    def verify(
        self,
        portfolio_state: PortfolioState,
        exposure: PortfolioExposure,
    ) -> PortfolioExposure:
        """Rebuild an exposure state and reject altered inputs, metrics, or identity."""

        input_values = {
            field_name: getattr(exposure, field_name)
            for field_name in (
                "knowledge_boundary",
                "method_version",
                "top_company_count",
                "evidence_items",
                "claims",
                "etf_snapshots",
                "company_profiles",
                "hypothetical_position",
                "missing_data",
                "conflicts",
                "assumptions",
            )
        }
        rebuilt = self.execute(
            portfolio_state,
            PortfolioExposureInput.model_validate(input_values),
        )
        if rebuilt != exposure:
            raise PortfolioExposureIntegrityError(
                "Portfolio Exposure identity or metrics do not match canonical replay"
            )
        return exposure

    @staticmethod
    def _canonicalize_input(exposure_input: PortfolioExposureInput) -> PortfolioExposureInput:
        values: dict[str, Any] = exposure_input.model_dump(mode="python")
        values["evidence_items"] = tuple(
            sorted(
                (
                    item.model_copy(
                        update={
                            "quality": item.quality.model_copy(
                                update={
                                    "missing_fields": tuple(sorted(item.quality.missing_fields)),
                                    "conflicts": tuple(sorted(item.quality.conflicts)),
                                }
                            )
                        }
                    )
                    for item in exposure_input.evidence_items
                ),
                key=lambda item: str(item.evidence_id),
            )
        )
        values["claims"] = tuple(
            sorted(
                (
                    item.model_copy(update={"evidence_ids": tuple(sorted(item.evidence_ids))})
                    for item in exposure_input.claims
                ),
                key=lambda item: str(item.claim_id),
            )
        )
        values["etf_snapshots"] = tuple(
            sorted(
                (
                    item.model_copy(
                        update={
                            "constituents": tuple(
                                sorted(
                                    item.constituents,
                                    key=lambda constituent: constituent.company_subject_id,
                                )
                            )
                        }
                    )
                    for item in exposure_input.etf_snapshots
                ),
                key=lambda item: item.etf_instrument_id,
            )
        )
        values["company_profiles"] = tuple(
            sorted(
                (
                    BuildPortfolioExposure._canonicalize_profile(item)
                    for item in exposure_input.company_profiles
                ),
                key=lambda item: item.company_subject_id,
            )
        )
        for field_name in ("missing_data", "conflicts", "assumptions"):
            values[field_name] = tuple(sorted(getattr(exposure_input, field_name)))
        return PortfolioExposureInput.model_validate(values)

    @staticmethod
    def _canonicalize_profile(profile: CompanyExposureProfile) -> CompanyExposureProfile:
        sector = (
            profile.sector.model_copy(update={"claim_ids": tuple(sorted(profile.sector.claim_ids))})
            if profile.sector is not None
            else None
        )
        geography = (
            profile.geography.model_copy(
                update={"claim_ids": tuple(sorted(profile.geography.claim_ids))}
            )
            if profile.geography is not None
            else None
        )
        drivers = tuple(
            sorted(
                (
                    item.model_copy(update={"claim_ids": tuple(sorted(item.claim_ids))})
                    for item in profile.economic_drivers
                ),
                key=lambda item: item.driver_id,
            )
        )
        return profile.model_copy(
            update={
                "sector": sector,
                "geography": geography,
                "economic_drivers": drivers,
                "missing_dimensions": tuple(
                    sorted(profile.missing_dimensions, key=lambda item: item.value)
                ),
            }
        )

    @staticmethod
    def _validate_state_inputs(
        portfolio_state: PortfolioState,
        exposure_input: PortfolioExposureInput,
    ) -> None:
        if exposure_input.knowledge_boundary != portfolio_state.knowledge_boundary:
            raise ValueError("Portfolio Exposure must use the Portfolio State knowledge boundary")
        instruments = {item.instrument_id: item for item in portfolio_state.instruments}
        snapshots = {item.etf_instrument_id: item for item in exposure_input.etf_snapshots}
        required_etf_ids: set[str] = set()
        required_company_ids: set[str] = set()

        for position in portfolio_state.positions:
            BuildPortfolioExposure._collect_required_inputs(
                instruments[position.instrument_id],
                snapshots,
                required_etf_ids,
                required_company_ids,
            )

        hypothetical = exposure_input.hypothetical_position
        if hypothetical is not None:
            instrument = instruments.get(hypothetical.instrument_id)
            if instrument is None:
                raise ValueError("hypothetical position references an unknown canonical instrument")
            if not portfolio_state.is_in_investable_universe(instrument.instrument_id):
                raise ValueError("hypothetical position instrument is not eligible for new capital")
            if hypothetical.amount.currency != instrument.native_currency:
                raise ValueError("hypothetical amount must use the instrument native currency")
            BuildPortfolioExposure._collect_required_inputs(
                instrument,
                snapshots,
                required_etf_ids,
                required_company_ids,
            )

        if set(snapshots) != required_etf_ids:
            raise ValueError("ETF snapshots must exactly cover held and hypothetical equity ETFs")
        for instrument_id in snapshots:
            if instruments[instrument_id].instrument_type is not InstrumentType.EQUITY_ETF:
                raise ValueError("constituent snapshots may reference only equity ETFs")
            required_company_ids.update(
                item.company_subject_id for item in snapshots[instrument_id].constituents
            )
        profiles = {item.company_subject_id: item for item in exposure_input.company_profiles}
        if set(profiles) != required_company_ids:
            raise ValueError(
                "company profiles must exactly cover every resolved direct and indirect company"
            )
        BuildPortfolioExposure._validate_classification_labels(exposure_input.company_profiles)

    @staticmethod
    def _collect_required_inputs(
        instrument: Instrument,
        snapshots: dict[str, ETFConstituentSnapshot],
        required_etf_ids: set[str],
        required_company_ids: set[str],
    ) -> None:
        if instrument.instrument_type is InstrumentType.LISTED_EQUITY:
            if instrument.company_subject_id is None:
                raise ValueError("listed equity requires a canonical company subject")
            required_company_ids.add(instrument.company_subject_id)
        elif instrument.instrument_type is InstrumentType.EQUITY_ETF:
            required_etf_ids.add(instrument.instrument_id)
            if instrument.instrument_id not in snapshots:
                raise ValueError("every analyzed equity ETF requires a constituent snapshot")

    @staticmethod
    def _validate_classification_labels(
        profiles: tuple[CompanyExposureProfile, ...],
    ) -> None:
        labels: dict[tuple[str, str], str] = {}

        def register(kind: str, item_id: str, label: str) -> None:
            key = (kind, item_id)
            prior = labels.get(key)
            if prior is not None and prior != label:
                raise ValueError(f"conflicting labels for {kind} {item_id}")
            labels[key] = label

        for profile in profiles:
            if profile.sector is not None:
                register("sector", profile.sector.sector_id, profile.sector.label)
            if profile.geography is not None:
                register("geography", profile.geography.country_code, profile.geography.label)
            for driver in profile.economic_drivers:
                register("driver", driver.driver_id, driver.label)

    def _build_snapshot(
        self,
        portfolio_state: PortfolioState,
        exposure_input: PortfolioExposureInput,
        *,
        scenario: ExposureScenario,
        hypothetical: HypotheticalPosition | None,
    ) -> ExposureSnapshot:
        instruments = {item.instrument_id: item for item in portfolio_state.instruments}
        snapshots = {item.etf_instrument_id: item for item in exposure_input.etf_snapshots}
        profiles = {item.company_subject_id: item for item in exposure_input.company_profiles}
        instrument_values: dict[tuple[str, str], Decimal] = {}
        company_values: dict[tuple[str, str], _CompanyAccumulator] = {}
        unresolved_values: dict[str, Decimal] = {}
        unresolved_reasons: dict[str, set[str]] = {}

        for position in portfolio_state.positions:
            self._add_instrument_value(
                instrument=instruments[position.instrument_id],
                amount=position.current_value,
                snapshots=snapshots,
                instrument_values=instrument_values,
                company_values=company_values,
                unresolved_values=unresolved_values,
                unresolved_reasons=unresolved_reasons,
            )
        if hypothetical is not None:
            self._add_instrument_value(
                instrument=instruments[hypothetical.instrument_id],
                amount=hypothetical.amount,
                snapshots=snapshots,
                instrument_values=instrument_values,
                company_values=company_values,
                unresolved_values=unresolved_values,
                unresolved_reasons=unresolved_reasons,
            )

        currency_books = tuple(
            self._build_currency_book(
                currency,
                instrument_values,
                company_values,
                unresolved_values,
                unresolved_reasons,
                profiles,
                exposure_input.top_company_count,
            )
            for currency in sorted({key[0] for key in instrument_values})
        )
        return ExposureSnapshot(scenario=scenario, currency_books=currency_books)

    @staticmethod
    def _add_instrument_value(
        *,
        instrument: Instrument,
        amount: MonetaryAmount,
        snapshots: dict[str, ETFConstituentSnapshot],
        instrument_values: dict[tuple[str, str], Decimal],
        company_values: dict[tuple[str, str], _CompanyAccumulator],
        unresolved_values: dict[str, Decimal],
        unresolved_reasons: dict[str, set[str]],
    ) -> None:
        currency = amount.currency
        instrument_key = (currency, instrument.instrument_id)
        instrument_values[instrument_key] = canonical_decimal(
            instrument_values.get(instrument_key, Decimal(0)) + amount.amount
        )
        if instrument.instrument_type is InstrumentType.LISTED_EQUITY:
            company_id = instrument.company_subject_id
            if company_id is None:
                raise ValueError("listed equity requires a canonical company subject")
            accumulator = company_values.setdefault(
                (currency, company_id),
                _CompanyAccumulator(),
            )
            accumulator.direct = canonical_decimal(accumulator.direct + amount.amount)
            accumulator.direct_instrument_ids.add(instrument.instrument_id)
            return
        if instrument.instrument_type is InstrumentType.EQUITY_ETF:
            snapshot = snapshots[instrument.instrument_id]
            for constituent in snapshot.constituents:
                accumulator = company_values.setdefault(
                    (currency, constituent.company_subject_id),
                    _CompanyAccumulator(),
                )
                constituent_value = canonical_decimal(amount.amount * constituent.weight)
                accumulator.indirect = canonical_decimal(accumulator.indirect + constituent_value)
                accumulator.indirect_instrument_ids.add(instrument.instrument_id)
            residual_value = canonical_decimal(amount.amount * snapshot.unresolved_weight)
            if residual_value > 0:
                unresolved_values[currency] = canonical_decimal(
                    unresolved_values.get(currency, Decimal(0)) + residual_value
                )
                unresolved_reasons.setdefault(currency, set()).add(
                    f"{instrument.instrument_id}: {snapshot.unresolved_reason}"
                )
            return
        unresolved_values[currency] = canonical_decimal(
            unresolved_values.get(currency, Decimal(0)) + amount.amount
        )
        unresolved_reasons.setdefault(currency, set()).add(
            f"{instrument.instrument_id}: no admitted one-level company look-through"
        )

    def _build_currency_book(
        self,
        currency: str,
        instrument_values: dict[tuple[str, str], Decimal],
        company_values: dict[tuple[str, str], _CompanyAccumulator],
        unresolved_values: dict[str, Decimal],
        unresolved_reasons: dict[str, set[str]],
        profiles: dict[str, CompanyExposureProfile],
        top_company_count: int,
    ) -> CurrencyExposureBook:
        currency_instruments = {
            instrument_id: value
            for (item_currency, instrument_id), value in instrument_values.items()
            if item_currency == currency
        }
        gross = canonical_decimal(sum(currency_instruments.values(), Decimal(0)))
        instrument_exposures = tuple(
            InstrumentExposure(
                instrument_id=instrument_id,
                value=MonetaryAmount(amount=value, currency=currency),
                weight=self._ratio(value, gross),
            )
            for instrument_id, value in sorted(currency_instruments.items())
        )
        company_exposures = tuple(
            self._company_exposure(
                currency,
                company_id,
                accumulator,
                gross,
                profiles[company_id],
            )
            for (item_currency, company_id), accumulator in sorted(company_values.items())
            if item_currency == currency
        )
        unresolved_value = canonical_decimal(unresolved_values.get(currency, Decimal(0)))
        unresolved = UnresolvedExposure(
            value=MonetaryAmount(amount=unresolved_value, currency=currency),
            weight=self._ratio(unresolved_value, gross),
            reasons=tuple(sorted(unresolved_reasons.get(currency, set()))),
        )
        sector_exposures = self._category_exposures(
            currency,
            gross,
            company_exposures,
            profiles,
            unresolved_value,
            dimension="sector",
        )
        geography_exposures = self._category_exposures(
            currency,
            gross,
            company_exposures,
            profiles,
            unresolved_value,
            dimension="geography",
        )
        driver_exposures = self._driver_exposures(
            currency,
            gross,
            company_exposures,
            profiles,
            unresolved_value,
        )
        ranked_companies = sorted(
            company_exposures,
            key=lambda item: (-item.total_value.amount, item.company_subject_id),
        )
        known_hhi = sum(
            ((item.total_value.amount / gross) ** 2 for item in company_exposures),
            Decimal(0),
        )
        unresolved_ratio = unresolved_value / gross
        return CurrencyExposureBook(
            currency=currency,
            gross_position_value=MonetaryAmount(amount=gross, currency=currency),
            instrument_exposures=instrument_exposures,
            company_exposures=company_exposures,
            unresolved_exposure=unresolved,
            sector_exposures=sector_exposures,
            geography_exposures=geography_exposures,
            economic_driver_exposures=driver_exposures,
            top_company_subject_ids=tuple(
                item.company_subject_id for item in ranked_companies[:top_company_count]
            ),
            top_company_count=top_company_count,
            company_hhi=HHIBounds(
                lower_bound=self._quantize_ratio(known_hhi),
                upper_bound=self._quantize_ratio(known_hhi + unresolved_ratio**2),
            ),
        )

    def _company_exposure(
        self,
        currency: str,
        company_id: str,
        accumulator: _CompanyAccumulator,
        gross: Decimal,
        profile: CompanyExposureProfile,
    ) -> CompanyExposure:
        total = canonical_decimal(accumulator.direct + accumulator.indirect)
        return CompanyExposure(
            company_subject_id=company_id,
            direct_value=MonetaryAmount(amount=accumulator.direct, currency=currency),
            indirect_value=MonetaryAmount(amount=accumulator.indirect, currency=currency),
            total_value=MonetaryAmount(amount=total, currency=currency),
            weight=self._ratio(total, gross),
            direct_instrument_ids=tuple(sorted(accumulator.direct_instrument_ids)),
            indirect_instrument_ids=tuple(sorted(accumulator.indirect_instrument_ids)),
            sector_id=profile.sector.sector_id if profile.sector is not None else None,
            geography_code=(
                profile.geography.country_code if profile.geography is not None else None
            ),
            economic_driver_ids=tuple(item.driver_id for item in profile.economic_drivers),
        )

    def _category_exposures(
        self,
        currency: str,
        gross: Decimal,
        company_exposures: tuple[CompanyExposure, ...],
        profiles: dict[str, CompanyExposureProfile],
        unresolved_value: Decimal,
        *,
        dimension: str,
    ) -> tuple[CategoryExposure, ...]:
        categories: dict[str, _CategoryAccumulator] = {}
        unknown_id = f"{dimension}:unknown"
        unknown_label = f"Unknown {dimension}"
        for company in company_exposures:
            profile = profiles[company.company_subject_id]
            classification: SectorClassification | GeographyClassification | None
            if dimension == "sector":
                classification = profile.sector
                category_id = classification.sector_id if classification is not None else unknown_id
            else:
                classification = profile.geography
                category_id = (
                    f"geography:{classification.country_code.lower()}"
                    if classification is not None
                    else unknown_id
                )
            label = classification.label if classification is not None else unknown_label
            accumulator = categories.setdefault(category_id, _CategoryAccumulator(label=label))
            accumulator.value = canonical_decimal(accumulator.value + company.total_value.amount)
            accumulator.company_subject_ids.add(company.company_subject_id)
        if unresolved_value > 0:
            accumulator = categories.setdefault(
                unknown_id,
                _CategoryAccumulator(label=unknown_label),
            )
            accumulator.value = canonical_decimal(accumulator.value + unresolved_value)
        return tuple(
            CategoryExposure(
                category_id=category_id,
                label=accumulator.label,
                value=MonetaryAmount(amount=accumulator.value, currency=currency),
                weight=self._ratio(accumulator.value, gross),
                company_subject_ids=tuple(sorted(accumulator.company_subject_ids)),
                is_unknown=category_id == unknown_id,
            )
            for category_id, accumulator in sorted(categories.items())
        )

    def _driver_exposures(
        self,
        currency: str,
        gross: Decimal,
        company_exposures: tuple[CompanyExposure, ...],
        profiles: dict[str, CompanyExposureProfile],
        unresolved_value: Decimal,
    ) -> tuple[DriverExposure, ...]:
        drivers: dict[str, _CategoryAccumulator] = {}
        unknown_id = "driver:unknown"
        for company in company_exposures:
            profile = profiles[company.company_subject_id]
            company_drivers = profile.economic_drivers
            if not company_drivers:
                company_drivers = ()
                accumulator = drivers.setdefault(
                    unknown_id,
                    _CategoryAccumulator(label="Unknown economic driver"),
                )
                accumulator.value = canonical_decimal(
                    accumulator.value + company.total_value.amount
                )
                accumulator.company_subject_ids.add(company.company_subject_id)
            for driver in company_drivers:
                accumulator = drivers.setdefault(
                    driver.driver_id,
                    _CategoryAccumulator(label=driver.label),
                )
                accumulator.value = canonical_decimal(
                    accumulator.value + company.total_value.amount
                )
                accumulator.company_subject_ids.add(company.company_subject_id)
        if unresolved_value > 0:
            accumulator = drivers.setdefault(
                unknown_id,
                _CategoryAccumulator(label="Unknown economic driver"),
            )
            accumulator.value = canonical_decimal(accumulator.value + unresolved_value)
        return tuple(
            DriverExposure(
                driver_id=driver_id,
                label=accumulator.label,
                value=MonetaryAmount(amount=accumulator.value, currency=currency),
                weight=self._ratio(accumulator.value, gross),
                company_subject_ids=tuple(sorted(accumulator.company_subject_ids)),
                is_unknown=driver_id == unknown_id,
            )
            for driver_id, accumulator in sorted(drivers.items())
        )

    @staticmethod
    def _ratio(numerator: Decimal, denominator: Decimal) -> Decimal:
        if denominator <= 0:
            raise ValueError("exposure ratio requires positive gross value")
        return BuildPortfolioExposure._quantize_ratio(numerator / denominator)

    @staticmethod
    def _quantize_ratio(value: Decimal) -> Decimal:
        return canonical_decimal(value.quantize(_RATIO_QUANTUM, rounding=ROUND_HALF_EVEN))
