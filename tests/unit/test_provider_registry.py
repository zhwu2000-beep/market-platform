from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import pytest

from market_platform.data.exceptions import ProviderNotFoundError
from market_platform.data.provider import DataProvider
from market_platform.data.providers.polygon import PolygonProvider
from market_platform.data.providers.twelvedata import TwelveDataProvider
from market_platform.data.registry import (
    ProviderRegistry,
    create_default_registry,
    get_provider,
)


class FakeProvider(DataProvider):
    name = "fake"

    def __init__(self, label: str = "default") -> None:
        self.label = label

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


def test_can_register_and_create_a_provider() -> None:
    registry = ProviderRegistry()
    registry.register("fake", lambda **kwargs: FakeProvider(**kwargs))

    provider = registry.create("fake", label="custom")

    assert isinstance(provider, FakeProvider)
    assert provider.label == "custom"


def test_provider_names_are_normalized() -> None:
    registry = ProviderRegistry()
    registry.register("  FaKe  ", lambda **kwargs: FakeProvider(**kwargs))

    assert "fake" in registry
    assert "  fAkE  " in registry
    assert registry.create("FAKE").label == "default"


def test_names_returns_registered_provider_names() -> None:
    registry = ProviderRegistry()
    registry.register("beta", lambda **kwargs: FakeProvider(**kwargs))
    registry.register("alpha", lambda **kwargs: FakeProvider(**kwargs))

    assert registry.names() == ["alpha", "beta"]


def test_duplicate_registration_raises_value_error() -> None:
    registry = ProviderRegistry()
    registry.register("fake", lambda **kwargs: FakeProvider(**kwargs))

    with pytest.raises(ValueError, match="already registered"):
        registry.register(" fake ", lambda **kwargs: FakeProvider(**kwargs))


def test_duplicate_registration_with_overwrite_succeeds() -> None:
    registry = ProviderRegistry()
    registry.register("fake", lambda **kwargs: FakeProvider(label="first"))
    registry.register(
        "FAKE",
        lambda **kwargs: FakeProvider(label="second"),
        overwrite=True,
    )

    provider = registry.create("fake")

    assert provider.label == "second"


def test_unknown_provider_raises_provider_not_found_error() -> None:
    registry = ProviderRegistry()

    with pytest.raises(ProviderNotFoundError, match="Unknown provider"):
        registry.create("missing")


def test_empty_provider_name_raises_value_error() -> None:
    registry = ProviderRegistry()

    with pytest.raises(ValueError, match="cannot be empty"):
        registry.register("   ", lambda **kwargs: FakeProvider(**kwargs))

    with pytest.raises(ValueError, match="cannot be empty"):
        registry.create("   ")


def test_contains_works_with_normalized_names() -> None:
    registry = ProviderRegistry()
    registry.register("fake", lambda **kwargs: FakeProvider(**kwargs))

    assert "fake" in registry
    assert " FAKE " in registry
    assert "missing" not in registry


def test_create_default_registry_includes_polygon(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("POLYGON_API_KEY", raising=False)
    monkeypatch.delenv("TWELVE_DATA_API_KEY", raising=False)

    registry = create_default_registry()

    assert "polygon" in registry.names()
    assert "twelvedata" in registry.names()


def test_get_provider_returns_polygon_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("POLYGON_API_KEY", raising=False)

    provider = get_provider("polygon")

    assert isinstance(provider, PolygonProvider)


def test_get_provider_normalizes_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("POLYGON_API_KEY", raising=False)

    provider = get_provider(" POLYGON ")

    assert isinstance(provider, PolygonProvider)


def test_get_provider_returns_twelve_data_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TWELVE_DATA_API_KEY", raising=False)

    provider = get_provider("twelvedata")

    assert isinstance(provider, TwelveDataProvider)


def test_get_provider_normalizes_twelve_data_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TWELVE_DATA_API_KEY", raising=False)

    provider = get_provider(" TWELVEDATA ")

    assert isinstance(provider, TwelveDataProvider)


def test_get_provider_twelve_data_is_lazy_about_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TWELVE_DATA_API_KEY", raising=False)

    provider = get_provider("twelvedata")

    assert isinstance(provider, TwelveDataProvider)
    assert provider.api_key == ""


def test_get_provider_unknown_raises_provider_not_found_error() -> None:
    with pytest.raises(ProviderNotFoundError, match="Unknown provider"):
        get_provider("unknown")


def test_create_default_registry_is_lazy_about_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("POLYGON_API_KEY", raising=False)

    registry = create_default_registry()

    assert "polygon" in registry
