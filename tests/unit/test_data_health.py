from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd
import pytest

from market_platform.config import Settings
from market_platform.data.exceptions import ConfigurationError, NetworkError
from market_platform.data.health import build_provider_health_report
from market_platform.data.provider import DataProvider
from market_platform.data.registry import ProviderRegistry


@dataclass
class _FakeProvider(DataProvider):
    name: str
    health_result: object
    health_exc: Exception | None = None
    calls: list[str] | None = None

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

    async def health_check(self) -> object:
        if self.calls is not None:
            self.calls.append(self.name)
        if self.health_exc is not None:
            raise self.health_exc
        return self.health_result


def _registry(*providers: _FakeProvider) -> ProviderRegistry:
    registry = ProviderRegistry()
    for provider in providers:
        registry.register(
            provider.name,
            lambda provider=provider, **kwargs: provider,
        )
    return registry


def _settings(order: str) -> Settings:
    return Settings.model_construct(
        data_provider_order=order,
        polygon_api_key="",
        twelve_data_api_key="",
    )


def test_build_provider_health_report_all_healthy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    polygon = _FakeProvider(
        name="polygon",
        health_result=pd.DataFrame(
            [{"provider": "polygon", "status": "ok", "message": "connected"}]
        ),
    )
    twelve_data = _FakeProvider(
        name="twelvedata",
        health_result={"status": "ok", "message": "connected"},
    )
    monkeypatch.setattr(
        "market_platform.data.health.create_default_registry",
        lambda: _registry(polygon, twelve_data),
    )
    settings = _settings("polygon,twelve_data")
    monkeypatch.setattr("market_platform.data.health.get_settings", lambda: settings)

    report = build_provider_health_report()

    assert report.status == "ok"
    assert [result.provider for result in report.providers] == [
        "polygon",
        "twelvedata",
    ]
    assert all(result.healthy is True for result in report.providers)
    assert all((result.latency_ms or 0) >= 0 for result in report.providers)


def test_build_provider_health_report_mixed_is_degraded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    polygon = _FakeProvider(name="polygon", health_result=True)
    twelve_data = _FakeProvider(name="twelvedata", health_result=False)
    monkeypatch.setattr(
        "market_platform.data.health.create_default_registry",
        lambda: _registry(polygon, twelve_data),
    )
    settings = _settings("polygon,twelve_data")
    monkeypatch.setattr("market_platform.data.health.get_settings", lambda: settings)

    report = build_provider_health_report()

    assert report.status == "degraded"
    assert [result.healthy for result in report.providers] == [True, False]


def test_build_provider_health_report_all_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    polygon = _FakeProvider(name="polygon", health_result=False)
    twelve_data = _FakeProvider(
        name="twelvedata",
        health_result={"status": "error", "message": "down"},
    )
    monkeypatch.setattr(
        "market_platform.data.health.create_default_registry",
        lambda: _registry(polygon, twelve_data),
    )
    settings = _settings("polygon,twelve_data")
    monkeypatch.setattr("market_platform.data.health.get_settings", lambda: settings)

    report = build_provider_health_report()

    assert report.status == "failed"
    assert all(result.healthy is False for result in report.providers)


def test_build_provider_health_report_explicit_provider_only_checks_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    polygon = _FakeProvider(
        name="polygon",
        health_result=True,
        calls=calls,
    )
    twelve_data = _FakeProvider(
        name="twelvedata",
        health_result=True,
        calls=calls,
    )
    monkeypatch.setattr(
        "market_platform.data.health.create_default_registry",
        lambda: _registry(polygon, twelve_data),
    )
    settings = _settings("")
    monkeypatch.setattr("market_platform.data.health.get_settings", lambda: settings)

    report = build_provider_health_report("twelve_data")

    assert report.status == "ok"
    assert [result.provider for result in report.providers] == ["twelvedata"]
    assert calls == ["twelvedata"]


def test_build_provider_health_report_captures_provider_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    polygon = _FakeProvider(
        name="polygon",
        health_result=True,
        health_exc=NetworkError("network down"),
    )
    monkeypatch.setattr(
        "market_platform.data.health.create_default_registry",
        lambda: _registry(polygon),
    )
    settings = _settings("polygon")
    monkeypatch.setattr("market_platform.data.health.get_settings", lambda: settings)

    report = build_provider_health_report()

    result = report.providers[0]
    assert report.status == "failed"
    assert result.healthy is False
    assert result.error_type == "NetworkError"
    assert result.error_message == "network down"


def test_build_provider_health_report_unknown_provider_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "market_platform.data.health.create_default_registry",
        lambda: _registry(),
    )
    settings = _settings("")
    monkeypatch.setattr("market_platform.data.health.get_settings", lambda: settings)

    with pytest.raises(ConfigurationError, match="Unknown provider"):
        build_provider_health_report("missing")
