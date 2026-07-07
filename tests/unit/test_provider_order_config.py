from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime

import pandas as pd
import pytest

from market_platform.config import get_settings
from market_platform.data.exceptions import ConfigurationError
from market_platform.data.provider import DataProvider
from market_platform.data.selection import ProviderCandidate, ProviderSelectionPolicy


class _NamedProvider(DataProvider):
    def __init__(self, name: str) -> None:
        self.name = name

    async def get_daily_prices(
        self,
        symbol: str,
        start: date,
        end: date,
    ) -> pd.DataFrame:
        return pd.DataFrame()

    async def get_intraday_prices(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "1min",
    ) -> pd.DataFrame:
        return pd.DataFrame()

    async def get_latest_price(self, symbol: str) -> pd.DataFrame:
        return pd.DataFrame()

    async def health_check(self) -> pd.DataFrame:
        return pd.DataFrame()


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _policy() -> ProviderSelectionPolicy:
    return ProviderSelectionPolicy(
        candidates=[
            ProviderCandidate(
                name="polygon",
                provider=_NamedProvider("polygon"),
                priority=20,
            ),
            ProviderCandidate(
                name="twelvedata",
                provider=_NamedProvider("twelvedata"),
                priority=10,
            ),
        ]
    )


def test_missing_env_var_uses_default_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MARKET_PLATFORM_DATA_PROVIDER_ORDER", raising=False)

    ordered = _policy().ordered_providers()

    assert [candidate.name for candidate in ordered] == ["twelvedata", "polygon"]


def test_provider_order_env_var_parses_correctly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "MARKET_PLATFORM_DATA_PROVIDER_ORDER",
        "polygon,twelve_data",
    )

    ordered = _policy().ordered_providers()

    assert [candidate.name for candidate in ordered] == ["polygon", "twelvedata"]


def test_provider_order_env_var_handles_whitespace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "MARKET_PLATFORM_DATA_PROVIDER_ORDER",
        "  twelvedata ,  polygon  ",
    )

    ordered = _policy().ordered_providers()

    assert [candidate.name for candidate in ordered] == ["twelvedata", "polygon"]


def test_provider_order_env_var_deduplicates_repeated_providers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "MARKET_PLATFORM_DATA_PROVIDER_ORDER",
        "polygon, twelve_data, polygon",
    )

    ordered = _policy().ordered_providers()

    assert [candidate.name for candidate in ordered] == ["polygon", "twelvedata"]


def test_unknown_provider_in_order_raises_clear_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "MARKET_PLATFORM_DATA_PROVIDER_ORDER",
        "polygon,unknown",
    )

    with pytest.raises(ConfigurationError, match="Unknown provider"):
        _policy().ordered_providers()
