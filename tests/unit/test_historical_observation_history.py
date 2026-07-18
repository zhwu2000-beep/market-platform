from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from market_platform.observation import build_historical_market_observation
from market_platform.signals import calculate_market_signals
from market_platform.structure import PriceStructureService

_AS_OF = datetime(2026, 1, 5, tzinfo=UTC)


def _prices(count: int = 5) -> pd.DataFrame:
    timestamps = [_AS_OF - timedelta(days=count - index - 1) for index in range(count)]
    closes = [100.0 + index for index in range(count)]
    return pd.DataFrame(
        {
            "symbol": ["MSFT"] * count,
            "timestamp": timestamps,
            "open": closes,
            "high": [close + 1.0 for close in closes],
            "low": [close - 1.0 for close in closes],
            "close": closes,
            "volume": [1_000_000.0] * count,
            "provider": ["test-provider"] * count,
        }
    )


def _observation(prices: pd.DataFrame, as_of: datetime = _AS_OF):
    return build_historical_market_observation(
        prices,
        symbol="MSFT",
        interval="1day",
        as_of=as_of,
        provider="test-provider",
        signal_snapshot=calculate_market_signals(prices),
        structure_snapshot=PriceStructureService().analyze(prices, as_of=as_of),
    )


def test_historical_observation_uses_only_current_prefix_for_fingerprint() -> None:
    prefix = _prices(5)
    future = pd.concat(
        [
            prefix,
            pd.DataFrame(
                {
                    "symbol": ["MSFT"],
                    "timestamp": [_AS_OF + timedelta(days=1)],
                    "open": [999.0],
                    "high": [1000.0],
                    "low": [998.0],
                    "close": [999.0],
                    "volume": [1_000_000.0],
                    "provider": ["test-provider"],
                }
            ),
        ],
        ignore_index=True,
    )

    first = _observation(prefix)
    second = _observation(future.iloc[:5].copy())

    assert first.provenance.input_fingerprint == second.provenance.input_fingerprint
    with pytest.raises(ValueError, match="later than as_of"):
        _observation(future)


def test_historical_observation_rejects_naive_prefix_timestamp() -> None:
    prices = _prices()
    prices["timestamp"] = prices["timestamp"].astype(object)
    prices.loc[0, "timestamp"] = datetime(2026, 1, 1)

    with pytest.raises(ValueError, match="timezone-aware"):
        _observation(prices)


def test_historical_observation_is_json_compatible() -> None:
    observation = _observation(_prices())

    payload = observation.to_dict()

    assert payload["identity"]["symbol"] == "MSFT"
    assert payload["provenance"]["input_fingerprint"].startswith("sha256:")
    assert payload["price_facts"]["observed_at"] == _AS_OF.isoformat()
