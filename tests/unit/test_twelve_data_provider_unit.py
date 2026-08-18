from __future__ import annotations

import asyncio
import json
import math
from datetime import UTC, date, datetime
from numbers import Real

import httpx
import pandas as pd
import pytest

import market_platform.data.providers.twelvedata as twelvedata_module
from market_platform.data.exceptions import ConfigurationError, DataProviderError
from market_platform.data.http import HTTPClient
from market_platform.data.providers.twelvedata import (
    TWELVE_DATA_BASE_URL,
    TwelveDataProvider,
)

_INVALID_NUMERIC_VALUES: tuple[object, ...] = (
    "not-a-number",
    [],
    {},
    True,
    "NaN",
    "Infinity",
    "-Infinity",
    float("nan"),
    float("inf"),
    float("-inf"),
)


def _provider_returning(payload: object) -> TwelveDataProvider:
    return TwelveDataProvider(
        api_key="test-key",
        http_client=HTTPClient(
            client=httpx.Client(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(
                        200,
                        text=json.dumps(payload),
                        headers={"content-type": "application/json"},
                    )
                )
            )
        ),
    )


def _assert_finite_numeric_values(
    frame: pd.DataFrame,
    fields: tuple[str, ...],
) -> None:
    for field in fields:
        values = frame[field].dropna().tolist()
        assert values
        assert all(
            isinstance(value, Real) and not isinstance(value, bool)
            for value in values
        )
        assert all(math.isfinite(float(value)) for value in values)


def test_twelve_data_provider_name() -> None:
    assert TwelveDataProvider.name == "twelvedata"


def test_twelve_data_provider_can_be_constructed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TWELVE_DATA_API_KEY", raising=False)

    provider = TwelveDataProvider()

    assert provider.base_url == TWELVE_DATA_BASE_URL
    assert provider.api_key == ""


def test_twelve_data_provider_uses_injected_http_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TWELVE_DATA_API_KEY", raising=False)
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={}))
    client = HTTPClient(client=httpx.Client(transport=transport))

    provider = TwelveDataProvider(http_client=client)

    assert provider.http_client is client


def test_twelve_data_provider_health_check_requires_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TWELVE_DATA_API_KEY", raising=False)
    provider = TwelveDataProvider(
        http_client=HTTPClient(
            client=httpx.Client(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, json={"status": "ok"})
                )
            )
        )
    )

    with pytest.raises(
        ConfigurationError,
        match="TWELVE_DATA_API_KEY is not configured",
    ):
        asyncio.run(provider.health_check())


def test_twelve_data_provider_health_check_is_normalized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "test-key")
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["apiKey"] = request.url.params["apikey"]
        return httpx.Response(200, json={"status": "ok", "message": "connected"})

    provider = TwelveDataProvider(
        http_client=HTTPClient(
            client=httpx.Client(transport=httpx.MockTransport(handler))
        )
    )

    frame = asyncio.run(provider.health_check())

    assert "/quote" in captured["url"]
    assert captured["apiKey"] == "test-key"
    assert list(frame.columns) == ["provider", "status", "message"]
    assert frame.at[0, "provider"] == "twelvedata"
    assert frame.at[0, "status"] == "ok"
    assert frame.at[0, "message"] == "connected"


def test_twelve_data_provider_health_check_rejects_malformed_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "test-key")
    provider = TwelveDataProvider(
        http_client=HTTPClient(
            client=httpx.Client(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, json=[])
                )
            )
        )
    )

    with pytest.raises(DataProviderError, match="must be an object"):
        asyncio.run(provider.health_check())


def test_twelve_data_provider_latest_price_requires_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TWELVE_DATA_API_KEY", raising=False)
    provider = TwelveDataProvider(
        http_client=HTTPClient(
            client=httpx.Client(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(
                        200,
                        json={"price": "100.5", "datetime": "2026-01-01T00:00:00Z"},
                    )
                )
            )
        )
    )

    with pytest.raises(
        ConfigurationError,
        match="TWELVE_DATA_API_KEY is not configured",
    ):
        asyncio.run(provider.get_latest_price("MSFT"))


def test_twelve_data_provider_latest_price_is_normalized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "test-key")
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["symbol"] = request.url.params["symbol"]
        captured["apiKey"] = request.url.params["apikey"]
        return httpx.Response(
            200,
            json={
                "status": "ok",
                "price": "100.5",
                "datetime": "2026-01-01T09:30:00-05:00",
            },
        )

    provider = TwelveDataProvider(
        http_client=HTTPClient(
            client=httpx.Client(transport=httpx.MockTransport(handler))
        )
    )

    frame = asyncio.run(provider.get_latest_price("msft"))

    assert "/price" in captured["url"]
    assert captured["symbol"] == "MSFT"
    assert captured["apiKey"] == "test-key"
    assert list(frame.columns) == ["symbol", "timestamp", "price", "provider"]
    assert list(frame["symbol"]) == ["MSFT"]
    assert list(frame["provider"]) == ["twelvedata"]
    assert list(frame["timestamp"]) == [pd.Timestamp("2026-01-01T14:30:00Z")]
    assert frame.at[0, "price"] == 100.5
    _assert_finite_numeric_values(frame, ("price",))


def test_twelve_data_provider_latest_price_defaults_to_fetch_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "test-key")

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz: object | None = None) -> datetime:
            return datetime(2026, 1, 1, 14, 30, tzinfo=UTC)

    monkeypatch.setattr(twelvedata_module, "datetime", FixedDatetime)

    provider = TwelveDataProvider(
        http_client=HTTPClient(
            client=httpx.Client(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(
                        200,
                        json={
                            "status": "ok",
                            "price": "100.5",
                        },
                    )
                )
            )
        )
    )

    frame = asyncio.run(provider.get_latest_price("MSFT"))

    assert list(frame["timestamp"]) == [pd.Timestamp("2026-01-01T14:30:00Z")]


@pytest.mark.parametrize("price_value", [100.5, 100])
def test_twelve_data_provider_latest_price_accepts_numeric_vendor_value(
    price_value: float | int,
) -> None:
    provider = _provider_returning(
        {
            "status": "ok",
            "price": price_value,
            "datetime": "2026-01-01T09:30:00Z",
        }
    )

    frame = asyncio.run(provider.get_latest_price("MSFT"))

    assert frame.at[0, "price"] == float(price_value)
    _assert_finite_numeric_values(frame, ("price",))


@pytest.mark.parametrize("price_value", _INVALID_NUMERIC_VALUES)
def test_twelve_data_provider_latest_price_rejects_invalid_numeric_value(
    price_value: object,
) -> None:
    provider = _provider_returning(
        {
            "status": "ok",
            "price": price_value,
            "datetime": "2026-01-01T09:30:00Z",
        }
    )

    with pytest.raises(
        DataProviderError,
        match="Twelve Data latest price must be a finite numeric value",
    ):
        asyncio.run(provider.get_latest_price("MSFT"))


def test_twelve_data_provider_intraday_prices_are_normalized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "test-key")
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["symbol"] = request.url.params["symbol"]
        captured["interval"] = request.url.params["interval"]
        captured["start_date"] = request.url.params["start_date"]
        captured["end_date"] = request.url.params["end_date"]
        captured["apiKey"] = request.url.params["apikey"]
        return httpx.Response(
            200,
            json={
                "status": "ok",
                "values": [
                    {
                        "datetime": "2026-01-01T09:31:00-05:00",
                        "open": "2.0",
                        "high": "3.0",
                        "low": "1.5",
                        "close": "2.5",
                        "volume": "200",
                    },
                    {
                        "datetime": "2026-01-01T09:30:00-05:00",
                        "open": "1.0",
                        "high": "2.0",
                        "low": "0.5",
                        "close": "1.5",
                        "volume": "100",
                    },
                ],
            },
        )

    provider = TwelveDataProvider(
        http_client=HTTPClient(
            client=httpx.Client(transport=httpx.MockTransport(handler))
        )
    )

    frame = asyncio.run(
        provider.get_intraday_prices(
            "msft",
            datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
            datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
            interval="5min",
        )
    )

    assert "/time_series" in captured["url"]
    assert captured["symbol"] == "MSFT"
    assert captured["interval"] == "5min"
    assert captured["start_date"] == "2026-01-01T09:00:00+00:00"
    assert captured["end_date"] == "2026-01-01T10:00:00+00:00"
    assert captured["apiKey"] == "test-key"
    assert list(frame.columns) == [
        "symbol",
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "provider",
    ]
    assert list(frame["symbol"]) == ["MSFT", "MSFT"]
    assert list(frame["provider"]) == ["twelvedata", "twelvedata"]
    assert list(frame["timestamp"]) == [
        pd.Timestamp("2026-01-01T14:30:00Z"),
        pd.Timestamp("2026-01-01T14:31:00Z"),
    ]
    _assert_finite_numeric_values(
        frame,
        ("open", "high", "low", "close", "volume"),
    )


@pytest.mark.parametrize("interval", ["1min", "5min", "15min", "30min", "1h"])
def test_twelve_data_provider_intraday_prices_accepts_supported_intervals(
    monkeypatch: pytest.MonkeyPatch,
    interval: str,
) -> None:
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "test-key")
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["interval"] = request.url.params["interval"]
        return httpx.Response(200, json={"status": "ok", "values": []})

    provider = TwelveDataProvider(
        http_client=HTTPClient(
            client=httpx.Client(transport=httpx.MockTransport(handler))
        )
    )

    frame = asyncio.run(
        provider.get_intraday_prices(
            "MSFT",
            datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
            datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
            interval=interval,
        )
    )

    assert captured["interval"] == interval
    assert list(frame.columns) == [
        "symbol",
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "provider",
    ]
    assert frame.empty


def test_twelve_data_provider_intraday_prices_rejects_unsupported_interval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "test-key")
    provider = TwelveDataProvider(
        http_client=HTTPClient(
            client=httpx.Client(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, json={"status": "ok"})
                )
            )
        )
    )

    with pytest.raises(ValueError, match="Unsupported interval"):
        asyncio.run(
            provider.get_intraday_prices(
                "MSFT",
                datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
                datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
                interval="2min",
            )
        )


def test_twelve_data_provider_intraday_prices_returns_empty_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "test-key")
    provider = TwelveDataProvider(
        http_client=HTTPClient(
            client=httpx.Client(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(
                        200,
                        json={"status": "ok", "values": []},
                    )
                )
            )
        )
    )

    frame = asyncio.run(
        provider.get_intraday_prices(
            "MSFT",
            datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
            datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
            interval="1min",
        )
    )

    assert list(frame.columns) == [
        "symbol",
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "provider",
    ]
    assert frame.empty


def test_twelve_data_provider_intraday_prices_rejects_malformed_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "test-key")
    provider = TwelveDataProvider(
        http_client=HTTPClient(
            client=httpx.Client(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(
                        200,
                        json={"status": "ok", "values": "bad"},
                    )
                )
            )
        )
    )

    with pytest.raises(DataProviderError, match="must be a list"):
        asyncio.run(
            provider.get_intraday_prices(
                "MSFT",
                datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
                datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
                interval="1min",
            )
        )


def test_twelve_data_provider_intraday_prices_rejects_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "test-key")
    provider = TwelveDataProvider(
        http_client=HTTPClient(
            client=httpx.Client(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(
                        200,
                        json={"status": "error", "message": "bad request"},
                    )
                )
            )
        )
    )

    with pytest.raises(DataProviderError, match="bad request"):
        asyncio.run(
            provider.get_intraday_prices(
                "MSFT",
                datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
                datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
                interval="1min",
            )
        )


def test_twelve_data_provider_intraday_prices_rejects_missing_volume(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "test-key")
    provider = TwelveDataProvider(
        http_client=HTTPClient(
            client=httpx.Client(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(
                        200,
                        json={
                            "status": "ok",
                            "values": [
                                {
                                    "datetime": "2026-01-01T09:30:00-05:00",
                                    "open": "1.0",
                                    "high": "2.0",
                                    "low": "0.5",
                                    "close": "1.5",
                                }
                            ],
                        },
                    )
                )
            )
        )
    )

    frame = asyncio.run(
        provider.get_intraday_prices(
            "MSFT",
            datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
            datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
            interval="1min",
        )
    )

    assert pd.isna(frame.at[0, "volume"])
    assert pd.api.types.is_numeric_dtype(frame["volume"].dtype)


def test_twelve_data_provider_daily_prices_are_normalized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "test-key")
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["apiKey"] = request.url.params["apikey"]
        return httpx.Response(
            200,
            json={
                "status": "ok",
                "values": [
                    {
                        "datetime": "2026-01-02",
                        "open": "2.0",
                        "high": "3.0",
                        "low": "1.5",
                        "close": "2.5",
                        "volume": "200",
                    },
                    {
                        "datetime": "2026-01-01",
                        "open": "1.0",
                        "high": "2.0",
                        "low": "0.5",
                        "close": "1.5",
                        "volume": "100",
                    },
                ],
            },
        )

    provider = TwelveDataProvider(
        http_client=HTTPClient(
            client=httpx.Client(transport=httpx.MockTransport(handler))
        )
    )

    frame = asyncio.run(
        provider.get_daily_prices("msft", date(2026, 1, 1), "2026-01-02")
    )

    assert "/time_series" in captured["url"]
    assert captured["apiKey"] == "test-key"
    assert list(frame.columns) == [
        "symbol",
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "provider",
    ]
    assert list(frame["symbol"]) == ["MSFT", "MSFT"]
    assert list(frame["provider"]) == ["twelvedata", "twelvedata"]
    assert list(frame["timestamp"]) == [
        pd.Timestamp("2026-01-01T00:00:00Z"),
        pd.Timestamp("2026-01-02T00:00:00Z"),
    ]
    _assert_finite_numeric_values(
        frame,
        ("open", "high", "low", "close", "volume"),
    )


def test_twelve_data_provider_daily_prices_requires_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TWELVE_DATA_API_KEY", raising=False)
    provider = TwelveDataProvider(
        http_client=HTTPClient(
            client=httpx.Client(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(
                        200,
                        json={"status": "ok", "values": []},
                    )
                )
            )
        )
    )

    with pytest.raises(
        ConfigurationError,
        match="TWELVE_DATA_API_KEY is not configured",
    ):
        asyncio.run(
            provider.get_daily_prices(
                "MSFT",
                date(2026, 1, 1),
                date(2026, 1, 2),
            )
        )


def test_twelve_data_provider_daily_prices_accepts_numeric_vendor_values() -> None:
    provider = _provider_returning(
        {
            "status": "ok",
            "values": [
                {
                    "datetime": "2026-01-01",
                    "open": 1,
                    "high": 2.0,
                    "low": 0.5,
                    "close": 1.5,
                    "volume": 100,
                }
            ],
        }
    )

    frame = asyncio.run(
        provider.get_daily_prices("MSFT", date(2026, 1, 1), date(2026, 1, 1))
    )

    _assert_finite_numeric_values(
        frame,
        ("open", "high", "low", "close", "volume"),
    )


@pytest.mark.parametrize("price_value", _INVALID_NUMERIC_VALUES)
def test_twelve_data_provider_daily_prices_rejects_invalid_price_value(
    price_value: object,
) -> None:
    provider = _provider_returning(
        {
            "status": "ok",
            "values": [
                {
                    "datetime": "2026-01-01",
                    "open": price_value,
                    "high": "2.0",
                    "low": "0.5",
                    "close": "1.5",
                    "volume": "100",
                }
            ],
        }
    )

    with pytest.raises(
        DataProviderError,
        match="Twelve Data open must be a finite numeric value",
    ):
        asyncio.run(
            provider.get_daily_prices(
                "MSFT",
                date(2026, 1, 1),
                date(2026, 1, 1),
            )
        )


@pytest.mark.parametrize("volume_value", _INVALID_NUMERIC_VALUES)
def test_twelve_data_provider_daily_prices_rejects_invalid_volume_value(
    volume_value: object,
) -> None:
    provider = _provider_returning(
        {
            "status": "ok",
            "values": [
                {
                    "datetime": "2026-01-01",
                    "open": "1.0",
                    "high": "2.0",
                    "low": "0.5",
                    "close": "1.5",
                    "volume": volume_value,
                }
            ],
        }
    )

    with pytest.raises(
        DataProviderError,
        match="Twelve Data volume must be a finite numeric value",
    ):
        asyncio.run(
            provider.get_daily_prices(
                "MSFT",
                date(2026, 1, 1),
                date(2026, 1, 1),
            )
        )


def test_twelve_data_provider_daily_prices_returns_empty_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "test-key")
    provider = TwelveDataProvider(
        http_client=HTTPClient(
            client=httpx.Client(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(
                        200,
                        json={"status": "ok", "values": []},
                    )
                )
            )
        )
    )

    frame = asyncio.run(
        provider.get_daily_prices("MSFT", date(2026, 1, 1), date(2026, 1, 2))
    )

    assert list(frame.columns) == [
        "symbol",
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "provider",
    ]
    assert frame.empty


def test_twelve_data_provider_daily_prices_rejects_malformed_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "test-key")
    provider = TwelveDataProvider(
        http_client=HTTPClient(
            client=httpx.Client(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(
                        200,
                        json={"status": "ok", "values": "bad"},
                    )
                )
            )
        )
    )

    with pytest.raises(DataProviderError, match="must be a list"):
        asyncio.run(
            provider.get_daily_prices(
                "MSFT",
                date(2026, 1, 1),
                date(2026, 1, 2),
            )
        )


def test_twelve_data_provider_daily_prices_rejects_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "test-key")
    provider = TwelveDataProvider(
        http_client=HTTPClient(
            client=httpx.Client(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(
                        200,
                        json={"status": "error", "message": "bad request"},
                    )
                )
            )
        )
    )

    with pytest.raises(DataProviderError, match="bad request"):
        asyncio.run(
            provider.get_daily_prices(
                "MSFT",
                date(2026, 1, 1),
                date(2026, 1, 2),
            )
        )


def test_twelve_data_provider_daily_prices_handles_blank_volume(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "test-key")
    provider = TwelveDataProvider(
        http_client=HTTPClient(
            client=httpx.Client(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(
                        200,
                        json={
                            "status": "ok",
                            "values": [
                                {
                                    "datetime": "2026-01-01",
                                    "open": "1.0",
                                    "high": "2.0",
                                    "low": "0.5",
                                    "close": "1.5",
                                    "volume": "",
                                }
                            ],
                        },
                    )
                )
            )
        )
    )

    frame = asyncio.run(
        provider.get_daily_prices("MSFT", date(2026, 1, 1), date(2026, 1, 1))
    )

    assert pd.isna(frame.at[0, "volume"])
    assert pd.api.types.is_numeric_dtype(frame["volume"].dtype)


def test_twelve_data_provider_daily_prices_handles_missing_volume(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "test-key")
    provider = TwelveDataProvider(
        http_client=HTTPClient(
            client=httpx.Client(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(
                        200,
                        json={
                            "status": "ok",
                            "values": [
                                {
                                    "datetime": "2026-01-01",
                                    "open": "1.0",
                                    "high": "2.0",
                                    "low": "0.5",
                                    "close": "1.5",
                                }
                            ],
                        },
                    )
                )
            )
        )
    )

    frame = asyncio.run(
        provider.get_daily_prices("MSFT", date(2026, 1, 1), date(2026, 1, 1))
    )

    assert pd.isna(frame.at[0, "volume"])
    assert pd.api.types.is_numeric_dtype(frame["volume"].dtype)
