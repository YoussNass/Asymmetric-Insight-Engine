"""Infrastructure clock tests."""

from asymmetric_engine.infrastructure.clock import SystemClock


def test_system_clock_returns_an_aware_timestamp() -> None:
    value = SystemClock().now()

    assert value.tzinfo is not None
    assert value.utcoffset() is not None
