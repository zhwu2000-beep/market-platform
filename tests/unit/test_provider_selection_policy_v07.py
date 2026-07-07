from __future__ import annotations

import asyncio
from datetime import date, datetime

import pandas as pd
import pytest

from market_platform.data.capabilities import DataCapability
from market_platform.data.exceptions import DataProviderError
from market_platform.data.models import PRICE_COLUMNS
from market_platform.data.provider import DataProvider
from market_platform.data.selection import ProviderCandidate, ProviderSelectionPolicy
from market_platform.data.service import MarketDataService


class _StaticProvider(DataProvider):
    def __init__(self, name: str, frame: pd.DataFrame | None = None) -> None:
        self.name = name
        self._frame = pd.DataFrame(columns=PRICE_COLUMNS) if frame is None else frame

    async def get_daily_prices(
        self,
        symbol: str,
        start: date,
        end: date,
    ) -> pd.DataFrame:
        return self._frame

    async def get_intraday_prices(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "1min",
    ) -> pd.DataFrame:
        return self._frame

    async def get_latest_price(self, symbol: str) -> pd.DataFrame:
        return self._frame

    async def health_check(self) -> pd.DataFrame:
        return self._frame


def test_selector_respects_configured_provider_order() -> None:
    policy = ProviderSelectionPolicy(
        candidates=[
            ProviderCandidate(
                name="polygon",
                provider=_StaticProvider("polygon"),
                priority=1,
            ),
            ProviderCandidate(
                name="twelvedata",
                provider=_StaticProvider("twelvedata"),
                priority=100,
            ),
        ],
        provider_order=["twelvedata", "polygon"],
    )

    ordered = policy.ordered_providers()

    assert [candidate.name for candidate in ordered] == ["twelvedata", "polygon"]


def test_selector_filters_providers_by_requested_capability() -> None:
    policy = ProviderSelectionPolicy(
        candidates=[
            ProviderCandidate(
                name="twelvedata",
                provider=_StaticProvider("twelvedata"),
                priority=1,
                capabilities=frozenset({DataCapability.DAILY_PRICES}),
            ),
            ProviderCandidate(
                name="polygon",
                provider=_StaticProvider("polygon"),
                priority=2,
                capabilities=frozenset(
                    {
                        DataCapability.DAILY_PRICES,
                        DataCapability.LATEST_PRICE,
                    }
                ),
            ),
        ],
        provider_order=["twelvedata", "polygon"],
    )

    ordered = policy.ordered_providers(DataCapability.LATEST_PRICE)

    assert [candidate.name for candidate in ordered] == ["polygon"]


def test_no_supported_provider_triggers_no_provider_available_behavior() -> None:
    policy = ProviderSelectionPolicy(
        candidates=[
            ProviderCandidate(
                name="polygon",
                provider=_StaticProvider("polygon"),
                priority=1,
                capabilities=frozenset[DataCapability](),
            ),
            ProviderCandidate(
                name="twelvedata",
                provider=_StaticProvider("twelvedata"),
                priority=2,
                capabilities=frozenset[DataCapability](),
            ),
        ]
    )
    service = MarketDataService(policy)

    with pytest.raises(DataProviderError, match="no providers available"):
        asyncio.run(service.get_daily_prices("MSFT", "2026-01-01", "2026-01-02"))
