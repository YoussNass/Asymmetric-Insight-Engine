"""Production clock adapter."""

from datetime import UTC, datetime


class SystemClock:
    """Return real ingestion time at the outer infrastructure boundary."""

    def now(self) -> datetime:
        """Return the current UTC timestamp."""

        return datetime.now(UTC)
