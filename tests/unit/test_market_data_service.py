from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime

import pandas as pd
import pytest

from market_platform.data.capabilities import DataCapability
from market_platform.data.comparison import compare_daily_prices
from market_platform.data.exceptions import (
    AuthenticationError,
    ConfigurationError,
    DataProviderError,
    NetworkError,
    RateLimitError,
)
from market_platform.data.models import PRICE_COLUMNS
from market_platform.data.provider import DataProvider
from market_platform.data.selection import ProviderCandidate, ProviderSelectionPolicy
from market_platform.data.service import MarketDataService


def _daily_frame(*, symbol: str, provider: str, close: float) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": [symbol],
            "timestamp": [pd.Timestamp("2026-01-01", tz=UTC)],
            "open": [close - 1.0],
            "high": [close + 1.0],
            "low": [close - 2.0],
            "close": [close],
            "volume": [100],
            "provider": [provider],
        }
    )


def _latest_frame(*, symbol: str, provider: str, price: float) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": [symbol],
            "timestamp": [pd.Timestamp("2026-01-01", tz=UTC)],
            "price": [price],
            "provider": [provider],
        }
    )


def _intraday_frame(*, symbol: str, provider: str, close: float) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": [symbol],
            "timestamp": [pd.Timestamp("2026-01-01T09:30:00Z")],
            "open": [close - 1.0],
            "high": [close + 1.0],
            "low": [close - 2.0],
            "close": [close],
            "volume": [100],
            "provider": [provider],
        }
    )


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=PRICE_COLUMNS)


class _FakeProvider(DataProvider):
    def __init__(
        self,
        *,
        name: str,
        frame: pd.DataFrame | None = None,
        error: Exception | None = None,
    ) -> None:
        self.name = name
        self._frame = _empty_frame() if frame is None else frame
        self._error = error
        self.calls: list[object] = []

    async def get_daily_prices(
        self,
        symbol: str,
        start: date,
        end: date,
    ) -> pd.DataFrame:
        self.calls.append((symbol, start, end))
        if self._error is not None:
            raise self._error
        return self._frame

    async def get_intraday_prices(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "1min",
    ) -> pd.DataFrame:
        self.calls.append(("intraday", symbol, start, end, interval))
        if self._error is not None:
            raise self._error
        return self._frame

    async def get_latest_price(self, symbol: str) -> pd.DataFrame:
        self.calls.append(("latest", symbol))
        if self._error is not None:
            raise self._error
        return self._frame

    async def health_check(self) -> pd.DataFrame:
        raise NotImplementedError


def test_priority_ordering() -> None:
    policy = ProviderSelectionPolicy(
        candidates=[
            ProviderCandidate(
                name="slow", provider=_FakeProvider(name="slow"), priority=20
            ),
            ProviderCandidate(
                name="fast", provider=_FakeProvider(name="fast"), priority=10
            ),
            ProviderCandidate(
                name="disabled",
                provider=_FakeProvider(name="disabled"),
                priority=5,
                enabled=False,
            ),
        ]
    )

    ordered = policy.ordered_providers()

    assert [candidate.name for candidate in ordered] == ["fast", "slow"]


def test_disabled_providers_are_skipped() -> None:
    policy = ProviderSelectionPolicy(
        candidates=[
            ProviderCandidate(
                name="disabled",
                provider=_FakeProvider(name="disabled"),
                priority=1,
                enabled=False,
            ),
            ProviderCandidate(
                name="enabled",
                provider=_FakeProvider(name="enabled"),
                priority=2,
            ),
        ]
    )

    assert [candidate.name for candidate in policy.ordered_providers()] == ["enabled"]


def test_first_successful_provider_is_returned_without_calling_later_providers() -> (
    None
):
    first_frame = _daily_frame(symbol="MSFT", provider="polygon", close=10.0)
    first = _FakeProvider(name="polygon", frame=first_frame)
    second = _FakeProvider(
        name="twelvedata",
        error=RuntimeError("should not be called"),
    )
    service = MarketDataService(
        ProviderSelectionPolicy(
            candidates=[
                ProviderCandidate(name="polygon", provider=first, priority=1),
                ProviderCandidate(name="twelvedata", provider=second, priority=2),
            ]
        )
    )

    frame = asyncio.run(service.get_daily_prices("MSFT", "2026-01-01", "2026-01-02"))

    assert frame.equals(first_frame)
    assert len(first.calls) == 1
    assert second.calls == []


def test_first_successful_latest_price_provider_is_returned() -> None:
    first_frame = _latest_frame(symbol="MSFT", provider="polygon", price=10.0)
    first = _FakeProvider(name="polygon", frame=first_frame)
    second = _FakeProvider(
        name="twelvedata",
        error=RuntimeError("should not be called"),
    )
    service = MarketDataService(
        ProviderSelectionPolicy(
            candidates=[
                ProviderCandidate(name="polygon", provider=first, priority=1),
                ProviderCandidate(name="twelvedata", provider=second, priority=2),
            ]
        )
    )

    frame = asyncio.run(service.get_latest_price("MSFT"))

    assert frame.equals(first_frame)
    assert len(first.calls) == 1
    assert second.calls == []


def test_first_successful_intraday_provider_is_returned() -> None:
    first_frame = _intraday_frame(symbol="MSFT", provider="twelvedata", close=10.0)
    first = _FakeProvider(name="twelvedata", frame=first_frame)
    second = _FakeProvider(
        name="archive",
        error=RuntimeError("should not be called"),
    )
    service = MarketDataService(
        ProviderSelectionPolicy(
            candidates=[
                ProviderCandidate(name="twelvedata", provider=first, priority=1),
                ProviderCandidate(name="archive", provider=second, priority=2),
            ]
        )
    )

    frame = asyncio.run(service.get_intraday_prices("MSFT"))

    assert frame.equals(first_frame)
    assert len(first.calls) == 1
    assert second.calls == []
    call_name, call_symbol, start, end, interval = first.calls[0]
    assert call_name == "intraday"
    assert call_symbol == "MSFT"
    assert start.tzinfo is not None
    assert end.tzinfo is not None
    assert interval == "1min"


def test_fallback_after_network_error() -> None:
    first = _FakeProvider(name="polygon", error=NetworkError("offline"))
    second_frame = _daily_frame(symbol="MSFT", provider="twelvedata", close=11.0)
    second = _FakeProvider(name="twelvedata", frame=second_frame)
    service = MarketDataService(
        ProviderSelectionPolicy(
            candidates=[
                ProviderCandidate(name="polygon", provider=first, priority=1),
                ProviderCandidate(name="twelvedata", provider=second, priority=2),
            ]
        )
    )

    frame = asyncio.run(service.get_daily_prices("MSFT", "2026-01-01", "2026-01-02"))

    assert frame.equals(second_frame)
    assert len(first.calls) == 1
    assert len(second.calls) == 1


def test_fallback_after_network_error_for_latest_price() -> None:
    first = _FakeProvider(name="polygon", error=NetworkError("offline"))
    second_frame = _latest_frame(symbol="MSFT", provider="polygon", price=11.0)
    second = _FakeProvider(name="polygon", frame=second_frame)
    service = MarketDataService(
        ProviderSelectionPolicy(
            candidates=[
                ProviderCandidate(name="polygon", provider=first, priority=1),
                ProviderCandidate(name="archive", provider=second, priority=2),
            ]
        )
    )

    frame = asyncio.run(service.get_latest_price("MSFT"))

    assert frame.equals(second_frame)
    assert len(first.calls) == 1
    assert len(second.calls) == 1


def test_fallback_after_network_error_for_intraday() -> None:
    first = _FakeProvider(name="twelvedata", error=NetworkError("offline"))
    second_frame = _intraday_frame(symbol="MSFT", provider="twelvedata", close=11.0)
    second = _FakeProvider(name="twelvedata", frame=second_frame)
    service = MarketDataService(
        ProviderSelectionPolicy(
            candidates=[
                ProviderCandidate(name="twelvedata", provider=first, priority=1),
                ProviderCandidate(name="archive", provider=second, priority=2),
            ]
        )
    )

    frame = asyncio.run(service.get_intraday_prices("MSFT"))

    assert frame.equals(second_frame)
    assert len(first.calls) == 1
    assert len(second.calls) == 1


def test_fallback_after_rate_limit_error() -> None:
    first = _FakeProvider(name="polygon", error=RateLimitError("slow down"))
    second_frame = _daily_frame(symbol="MSFT", provider="twelvedata", close=11.0)
    second = _FakeProvider(name="twelvedata", frame=second_frame)
    service = MarketDataService(
        ProviderSelectionPolicy(
            candidates=[
                ProviderCandidate(name="polygon", provider=first, priority=1),
                ProviderCandidate(name="twelvedata", provider=second, priority=2),
            ]
        )
    )

    frame = asyncio.run(service.get_daily_prices("MSFT", "2026-01-01", "2026-01-02"))

    assert frame.equals(second_frame)
    assert len(first.calls) == 1
    assert len(second.calls) == 1


def test_fallback_after_data_provider_error() -> None:
    first = _FakeProvider(name="polygon", error=DataProviderError("bad payload"))
    second_frame = _daily_frame(symbol="MSFT", provider="twelvedata", close=11.0)
    second = _FakeProvider(name="twelvedata", frame=second_frame)
    service = MarketDataService(
        ProviderSelectionPolicy(
            candidates=[
                ProviderCandidate(name="polygon", provider=first, priority=1),
                ProviderCandidate(name="twelvedata", provider=second, priority=2),
            ]
        )
    )

    frame = asyncio.run(service.get_daily_prices("MSFT", "2026-01-01", "2026-01-02"))

    assert frame.equals(second_frame)
    assert len(first.calls) == 1
    assert len(second.calls) == 1


def test_fallback_after_empty_dataframe() -> None:
    first = _FakeProvider(name="polygon", frame=_empty_frame())
    second_frame = _daily_frame(symbol="MSFT", provider="twelvedata", close=11.0)
    second = _FakeProvider(name="twelvedata", frame=second_frame)
    service = MarketDataService(
        ProviderSelectionPolicy(
            candidates=[
                ProviderCandidate(name="polygon", provider=first, priority=1),
                ProviderCandidate(name="twelvedata", provider=second, priority=2),
            ]
        )
    )

    frame = asyncio.run(service.get_daily_prices("MSFT", "2026-01-01", "2026-01-02"))

    assert frame.equals(second_frame)
    assert len(first.calls) == 1
    assert len(second.calls) == 1


def test_incapable_provider_is_skipped() -> None:
    first = _FakeProvider(name="legacy")
    second_frame = _daily_frame(symbol="MSFT", provider="twelvedata", close=11.0)
    second = _FakeProvider(name="twelvedata", frame=second_frame)
    service = MarketDataService(
        ProviderSelectionPolicy(
            candidates=[
                ProviderCandidate(
                    name="legacy",
                    provider=first,
                    priority=1,
                    capabilities=frozenset[DataCapability](),
                ),
                ProviderCandidate(
                    name="twelvedata",
                    provider=second,
                    priority=2,
                ),
            ]
        )
    )

    frame = asyncio.run(service.get_daily_prices("MSFT", "2026-01-01", "2026-01-02"))

    assert frame.equals(second_frame)
    assert len(first.calls) == 0
    assert len(second.calls) == 1


def test_explicit_provider_selection_uses_only_requested_provider() -> None:
    first = _FakeProvider(
        name="polygon",
        frame=_daily_frame(symbol="MSFT", provider="polygon", close=10.0),
    )
    second = _FakeProvider(
        name="twelvedata",
        frame=_daily_frame(symbol="MSFT", provider="twelvedata", close=11.0),
    )
    service = MarketDataService(
        ProviderSelectionPolicy(
            candidates=[
                ProviderCandidate(name="polygon", provider=first, priority=1),
                ProviderCandidate(name="twelvedata", provider=second, priority=2),
            ],
            provider_order=["twelvedata", "polygon"],
        )
    )

    frame = asyncio.run(
        service.get_daily_prices(
            "MSFT",
            "2026-01-01",
            "2026-01-02",
            provider="polygon",
        )
    )

    assert list(frame["provider"]) == ["polygon"]
    assert len(first.calls) == 1
    assert second.calls == []


def test_explicit_intraday_provider_selection_uses_only_requested_provider() -> None:
    first = _FakeProvider(
        name="twelvedata",
        frame=_intraday_frame(symbol="MSFT", provider="twelvedata", close=10.0),
    )
    second = _FakeProvider(
        name="archive",
        frame=_intraday_frame(symbol="MSFT", provider="archive", close=11.0),
    )
    service = MarketDataService(
        ProviderSelectionPolicy(
            candidates=[
                ProviderCandidate(name="twelvedata", provider=first, priority=1),
                ProviderCandidate(name="archive", provider=second, priority=2),
            ],
            provider_order=["archive", "twelvedata"],
        )
    )

    frame = asyncio.run(
        service.get_intraday_prices(
            "MSFT",
            provider="twelve_data",
        )
    )

    assert list(frame["provider"]) == ["twelvedata"]
    assert len(first.calls) == 1
    assert second.calls == []


def test_explicit_latest_provider_selection_uses_only_requested_provider() -> None:
    first = _FakeProvider(
        name="polygon",
        frame=_latest_frame(symbol="MSFT", provider="polygon", price=10.0),
    )
    second = _FakeProvider(
        name="twelvedata",
        frame=_latest_frame(symbol="MSFT", provider="twelvedata", price=11.0),
    )
    service = MarketDataService(
        ProviderSelectionPolicy(
            candidates=[
                ProviderCandidate(name="polygon", provider=first, priority=1),
                ProviderCandidate(name="twelvedata", provider=second, priority=2),
            ],
            provider_order=["twelvedata", "polygon"],
        )
    )

    frame = asyncio.run(
        service.get_latest_price(
            "MSFT",
            provider="polygon",
        )
    )

    assert list(frame["provider"]) == ["polygon"]
    assert len(first.calls) == 1
    assert second.calls == []


def test_explicit_intraday_incapable_provider_raises_clear_error() -> None:
    first = _FakeProvider(name="legacy")
    service = MarketDataService(
        ProviderSelectionPolicy(
            candidates=[
                ProviderCandidate(
                    name="legacy",
                    provider=first,
                    priority=1,
                    capabilities=frozenset[DataCapability](),
                ),
            ]
        )
    )

    with pytest.raises(ConfigurationError, match="does not support intraday_prices"):
        asyncio.run(
            service.get_intraday_prices(
                "MSFT",
                provider="legacy",
            )
        )

    assert first.calls == []


def test_explicit_incapable_provider_raises_clear_error() -> None:
    first = _FakeProvider(name="legacy")
    service = MarketDataService(
        ProviderSelectionPolicy(
            candidates=[
                ProviderCandidate(
                    name="legacy",
                    provider=first,
                    priority=1,
                    capabilities=frozenset[DataCapability](),
                ),
            ]
        )
    )

    with pytest.raises(ConfigurationError, match="does not support daily_prices"):
        asyncio.run(
            service.get_daily_prices(
                "MSFT",
                "2026-01-01",
                "2026-01-02",
                provider="legacy",
            )
        )

    assert first.calls == []


def test_explicit_latest_incapable_provider_raises_clear_error() -> None:
    first = _FakeProvider(name="legacy")
    service = MarketDataService(
        ProviderSelectionPolicy(
            candidates=[
                ProviderCandidate(
                    name="legacy",
                    provider=first,
                    priority=1,
                    capabilities=frozenset[DataCapability](),
                ),
            ]
        )
    )

    with pytest.raises(ConfigurationError, match="does not support latest_price"):
        asyncio.run(
            service.get_latest_price(
                "MSFT",
                provider="legacy",
            )
        )

    assert first.calls == []


def test_no_intraday_capable_provider_available_raises_clear_error() -> None:
    first = _FakeProvider(name="legacy")
    second = _FakeProvider(name="archive")
    service = MarketDataService(
        ProviderSelectionPolicy(
            candidates=[
                ProviderCandidate(
                    name="legacy",
                    provider=first,
                    priority=1,
                    capabilities=frozenset[DataCapability](),
                ),
                ProviderCandidate(
                    name="archive",
                    provider=second,
                    priority=2,
                    capabilities=frozenset[DataCapability](),
                ),
            ]
        )
    )

    with pytest.raises(
        DataProviderError,
        match="no provider succeeded for intraday prices",
    ):
        asyncio.run(service.get_intraday_prices("MSFT"))

    assert first.calls == []
    assert second.calls == []


def test_no_capable_provider_available_raises_clear_error() -> None:
    first = _FakeProvider(name="legacy")
    second = _FakeProvider(name="archive")
    service = MarketDataService(
        ProviderSelectionPolicy(
            candidates=[
                ProviderCandidate(
                    name="legacy",
                    provider=first,
                    priority=1,
                    capabilities=frozenset[DataCapability](),
                ),
                ProviderCandidate(
                    name="archive",
                    provider=second,
                    priority=2,
                    capabilities=frozenset[DataCapability](),
                ),
            ]
        )
    )

    with pytest.raises(DataProviderError, match="no providers available"):
        asyncio.run(service.get_daily_prices("MSFT", "2026-01-01", "2026-01-02"))

    assert first.calls == []
    assert second.calls == []


def test_no_latest_capable_provider_available_raises_clear_error() -> None:
    first = _FakeProvider(name="legacy")
    second = _FakeProvider(name="archive")
    service = MarketDataService(
        ProviderSelectionPolicy(
            candidates=[
                ProviderCandidate(
                    name="legacy",
                    provider=first,
                    priority=1,
                    capabilities=frozenset[DataCapability](),
                ),
                ProviderCandidate(
                    name="archive",
                    provider=second,
                    priority=2,
                    capabilities=frozenset[DataCapability](),
                ),
            ]
        )
    )

    with pytest.raises(DataProviderError, match="no providers available"):
        asyncio.run(service.get_latest_price("MSFT"))

    assert first.calls == []
    assert second.calls == []


def test_authentication_error_does_not_fallback_by_default() -> None:
    first = _FakeProvider(name="polygon", error=AuthenticationError("bad key"))
    second = _FakeProvider(
        name="twelvedata",
        frame=_daily_frame(symbol="MSFT", provider="twelvedata", close=11.0),
    )
    service = MarketDataService(
        ProviderSelectionPolicy(
            candidates=[
                ProviderCandidate(name="polygon", provider=first, priority=1),
                ProviderCandidate(name="twelvedata", provider=second, priority=2),
            ]
        )
    )

    with pytest.raises(AuthenticationError, match="bad key"):
        asyncio.run(service.get_daily_prices("MSFT", "2026-01-01", "2026-01-02"))

    assert len(first.calls) == 1
    assert second.calls == []


def test_authentication_error_can_fallback_when_enabled() -> None:
    first = _FakeProvider(name="polygon", error=AuthenticationError("bad key"))
    second_frame = _daily_frame(symbol="MSFT", provider="twelvedata", close=11.0)
    second = _FakeProvider(name="twelvedata", frame=second_frame)
    service = MarketDataService(
        ProviderSelectionPolicy(
            candidates=[
                ProviderCandidate(name="polygon", provider=first, priority=1),
                ProviderCandidate(name="twelvedata", provider=second, priority=2),
            ]
        ),
        fallback_on_auth_error=True,
    )

    frame = asyncio.run(service.get_daily_prices("MSFT", "2026-01-01", "2026-01-02"))

    assert frame.equals(second_frame)
    assert len(first.calls) == 1
    assert len(second.calls) == 1


def test_all_providers_failing_raises_data_provider_error_with_attempt_details() -> (
    None
):
    first = _FakeProvider(name="polygon", error=NetworkError("offline"))
    second = _FakeProvider(name="twelvedata", frame=_empty_frame())
    service = MarketDataService(
        ProviderSelectionPolicy(
            candidates=[
                ProviderCandidate(name="polygon", provider=first, priority=1),
                ProviderCandidate(name="twelvedata", provider=second, priority=2),
            ]
        )
    )

    with pytest.raises(DataProviderError) as excinfo:
        asyncio.run(service.get_daily_prices("MSFT", "2026-01-01", "2026-01-02"))

    message = str(excinfo.value)
    assert "polygon" in message
    assert "twelvedata" in message
    assert "network error" in message
    assert "empty response" in message


def test_compare_daily_prices_is_still_available_for_normalized_frames() -> None:
    left = _daily_frame(symbol="MSFT", provider="polygon", close=10.0)
    right = _daily_frame(symbol="MSFT", provider="twelvedata", close=9.0)

    frame = compare_daily_prices(left, right)

    assert list(frame["match_status"]) == ["matched"]
