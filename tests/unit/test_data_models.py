from datetime import UTC, datetime
from decimal import Decimal

from market_platform.data.models import OHLCVBar


def test_ohlcv_bar_model() -> None:
    bar = OHLCVBar(
        symbol="MSFT",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        open=Decimal("1"),
        high=Decimal("2"),
        low=Decimal("0.5"),
        close=Decimal("1.5"),
        volume=Decimal("1000"),
        source="test",
    )

    assert bar.symbol == "MSFT"
    assert bar.close == Decimal("1.5")
