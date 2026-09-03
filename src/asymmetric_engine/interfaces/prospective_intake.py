"""Typed prospective intake for canonical Causal Analysis and Underwriting product records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict

from asymmetric_engine.application.causal_analysis import BuildCausalAnalysis
from asymmetric_engine.application.underwriting import BuildOpportunityState
from asymmetric_engine.domain.causal import CausalAnalysis, CausalAnalysisDraft
from asymmetric_engine.domain.opportunity import OpportunityState, UnderwritingDraft

INTAKE_CONTRACT_VERSION: Literal["aie-intake-v1"] = "aie-intake-v1"


class _IntakeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    contract_version: Literal["aie-intake-v1"] = INTAKE_CONTRACT_VERSION


class IntakeResponse[T](_IntakeModel):
    """Versioned response carrying an exact canonical owner result."""

    operation: str
    result: T


class BuildCausalAnalysisRequest(_IntakeModel):
    operation: Literal["build_causal_analysis"] = "build_causal_analysis"
    draft: CausalAnalysisDraft


class BuildOpportunityStateRequest(_IntakeModel):
    operation: Literal["build_opportunity_state"] = "build_opportunity_state"
    draft: UnderwritingDraft


@dataclass(frozen=True)
class AieIntakeServices:
    """Canonical upstream application services injected by the product composition root."""

    causal_analysis: BuildCausalAnalysis
    opportunity_state: BuildOpportunityState


class AieProspectiveIntake:
    """Expose upstream canonical builders without duplicating analytical logic."""

    def __init__(self, services: AieIntakeServices) -> None:
        self._services = services

    def build_causal_analysis(
        self,
        request: BuildCausalAnalysisRequest,
    ) -> IntakeResponse[CausalAnalysis]:
        result = self._services.causal_analysis.execute(request.draft)
        return IntakeResponse[CausalAnalysis](operation=request.operation, result=result)

    def build_opportunity_state(
        self,
        request: BuildOpportunityStateRequest,
    ) -> IntakeResponse[OpportunityState]:
        result = self._services.opportunity_state.execute(request.draft)
        return IntakeResponse[OpportunityState](operation=request.operation, result=result)


__all__ = [
    "INTAKE_CONTRACT_VERSION",
    "AieIntakeServices",
    "AieProspectiveIntake",
    "BuildCausalAnalysisRequest",
    "BuildOpportunityStateRequest",
    "IntakeResponse",
]
