"""Canonical cross-domain point-in-time knowledge semantics."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict


class KnowledgeMode(StrEnum):
    """Knowledge boundary used to evaluate point-in-time records."""

    HISTORICAL_RECONSTRUCTION = "historical_reconstruction"
    LIVE_SYSTEM_REPLAY = "live_system_replay"


class KnowledgeExclusionReason(StrEnum):
    """Why a record is outside a decision-time knowledge boundary."""

    SOURCE_NOT_AVAILABLE = "source_not_available"
    RECORD_NOT_INGESTED = "record_not_ingested"


class KnowledgeBoundary(BaseModel):
    """One canonical decision-time boundary shared by every bounded context."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    as_of: AwareDatetime
    knowledge_mode: KnowledgeMode

    def exclusion_reason(
        self,
        *,
        available_at: datetime,
        recorded_at: datetime,
    ) -> KnowledgeExclusionReason | None:
        """Classify a record without silently interchanging reconstruction and replay."""

        for name, value in (("available_at", available_at), ("recorded_at", recorded_at)):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware")
        if recorded_at < available_at:
            raise ValueError("recorded_at must be greater than or equal to available_at")
        if available_at > self.as_of:
            return KnowledgeExclusionReason.SOURCE_NOT_AVAILABLE
        if self.knowledge_mode is KnowledgeMode.LIVE_SYSTEM_REPLAY and recorded_at > self.as_of:
            return KnowledgeExclusionReason.RECORD_NOT_INGESTED
        return None

    def includes(self, *, available_at: datetime, recorded_at: datetime) -> bool:
        """Return whether a record belongs to this knowledge boundary."""

        return self.exclusion_reason(available_at=available_at, recorded_at=recorded_at) is None
