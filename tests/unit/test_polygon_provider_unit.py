from __future__ import annotations

import ast
import asyncio
import json
from dataclasses import FrozenInstanceError, fields, replace
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from importlib.util import resolve_name
from inspect import signature
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from typing import cast

import httpx
import pandas as pd
import pytest

from market_platform.data.exceptions import ConfigurationError, DataProviderError
from market_platform.data.http import ExactJsonResult, HTTPClient
from market_platform.data.providers.polygon import (
    POLYGON_BASE_URL,
    PolygonCompletedDailyAcquisition,
    PolygonCompletedDailyAggregate,
    PolygonProvider,
)


def test_polygon_provider_can_be_constructed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("POLYGON_API_KEY", raising=False)

    provider = PolygonProvider()

    assert provider.base_url == POLYGON_BASE_URL
    assert provider.api_key == ""


def test_polygon_provider_uses_injected_http_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("POLYGON_API_KEY", raising=False)
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={}))
    client = HTTPClient(client=httpx.Client(transport=transport))

    provider = PolygonProvider(http_client=client)

    assert provider.http_client is client


def test_polygon_provider_allows_missing_api_key_on_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = PolygonProvider()

    assert provider.api_key == ""


def test_polygon_provider_daily_prices_are_normalized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POLYGON_API_KEY", "test-key")
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["apiKey"] = request.url.params["apiKey"]
        return httpx.Response(
            200,
            json={
                "adjusted": True,
                "results": [
                    {
                        "t": int(
                            pd.Timestamp("2026-01-02T05:00:00Z").timestamp() * 1000
                        ),
                        "o": 2.0,
                        "h": 3.0,
                        "l": 1.5,
                        "c": 2.5,
                        "v": 200,
                    },
                    {
                        "t": int(
                            pd.Timestamp("2026-01-01T05:00:00Z").timestamp() * 1000
                        ),
                        "o": 1.0,
                        "h": 2.0,
                        "l": 0.5,
                        "c": 1.5,
                        "v": 100,
                    },
                ],
            },
        )

    provider = PolygonProvider(
        http_client=HTTPClient(
            client=httpx.Client(transport=httpx.MockTransport(handler))
        )
    )

    frame = asyncio.run(
        provider.get_daily_prices("msft", date(2026, 1, 1), "2026-01-02")
    )

    assert "/v2/aggs/ticker/MSFT/range/1/day/2026-01-01/2026-01-02" in captured["url"]
    assert captured["apiKey"] == "test-key"
    assert "adjusted=true" in captured["url"]
    assert "sort=asc" in captured["url"]
    assert "limit=50000" in captured["url"]
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
    assert frame["timestamp"].dt.tz is not None
    assert list(frame["timestamp"]) == [
        pd.Timestamp("2026-01-01T00:00:00Z"),
        pd.Timestamp("2026-01-02T00:00:00Z"),
    ]
    assert list(frame["symbol"]) == ["MSFT", "MSFT"]
    assert list(frame["provider"]) == ["polygon", "polygon"]


@pytest.mark.parametrize("adjusted", [None, False, 1, "true"])
def test_polygon_daily_prices_require_exact_adjusted_proof(
    monkeypatch: pytest.MonkeyPatch,
    adjusted: object,
) -> None:
    monkeypatch.setenv("POLYGON_API_KEY", "test-key")
    payload: dict[str, object] = {"results": []}
    if adjusted is not None:
        payload["adjusted"] = adjusted
    provider = PolygonProvider(
        http_client=HTTPClient(
            client=httpx.Client(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, json=payload)
                )
            )
        )
    )

    with pytest.raises(DataProviderError, match="exact boolean true"):
        asyncio.run(provider.get_daily_prices("msft", date(2026, 1, 1), "2026-01-02"))


@pytest.mark.parametrize(
    ("raw_timestamp", "expected"),
    [
        ("2026-03-09T04:00:00Z", "2026-03-09T00:00:00Z"),
        ("2026-11-02T05:00:00Z", "2026-11-02T00:00:00Z"),
        ("2026-01-02T01:00:00Z", "2026-01-01T00:00:00Z"),
    ],
)
def test_polygon_daily_timestamp_uses_new_york_session_date(
    monkeypatch: pytest.MonkeyPatch,
    raw_timestamp: str,
    expected: str,
) -> None:
    monkeypatch.setenv("POLYGON_API_KEY", "test-key")
    raw_ms = int(pd.Timestamp(raw_timestamp).timestamp() * 1000)
    provider = PolygonProvider(
        http_client=HTTPClient(
            client=httpx.Client(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(
                        200,
                        json={
                            "adjusted": True,
                            "results": [
                                {
                                    "t": raw_ms,
                                    "o": 1.0,
                                    "h": 2.0,
                                    "l": 0.5,
                                    "c": 1.5,
                                    "v": 100,
                                }
                            ],
                        },
                    )
                )
            )
        )
    )

    frame = asyncio.run(
        provider.get_daily_prices("msft", date(2026, 1, 1), "2026-11-02")
    )

    assert frame.at[0, "timestamp"] == pd.Timestamp(expected)
    assert frame.at[0, "provider"] == "polygon"


def test_polygon_daily_prices_reject_malformed_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POLYGON_API_KEY", "test-key")
    provider = PolygonProvider(
        http_client=HTTPClient(
            client=httpx.Client(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(
                        200, json={"adjusted": True, "results": [{"t": 1}]}
                    )
                )
            )
        )
    )

    with pytest.raises(DataProviderError, match="missing field"):
        asyncio.run(provider.get_daily_prices("msft", date(2026, 1, 1), "2026-01-02"))


def test_polygon_provider_daily_prices_requires_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("POLYGON_API_KEY", raising=False)
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"results": []})
    )
    provider = PolygonProvider(
        http_client=HTTPClient(client=httpx.Client(transport=transport))
    )

    with pytest.raises(ConfigurationError, match="POLYGON_API_KEY is not configured"):
        asyncio.run(provider.get_daily_prices("msft", date(2026, 1, 1), "2026-01-02"))


def test_polygon_provider_health_check_is_normalized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POLYGON_API_KEY", "test-key")
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["apiKey"] = request.url.params["apiKey"]
        return httpx.Response(200, json={"status": "OK", "message": "connected"})

    provider = PolygonProvider(
        http_client=HTTPClient(
            client=httpx.Client(transport=httpx.MockTransport(handler))
        )
    )

    frame = asyncio.run(provider.health_check())

    assert "/v1/marketstatus/now" in captured["url"]
    assert captured["apiKey"] == "test-key"
    assert list(frame.columns) == ["provider", "status", "message"]
    assert frame.at[0, "provider"] == "polygon"
    assert frame.at[0, "status"] == "OK"
    assert frame.at[0, "message"] == "connected"


def test_polygon_provider_latest_price_is_normalized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POLYGON_API_KEY", "test-key")
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["apiKey"] = request.url.params["apiKey"]
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "t": 1767312000000,
                        "c": 123.45,
                    }
                ]
            },
        )

    provider = PolygonProvider(
        http_client=HTTPClient(
            client=httpx.Client(transport=httpx.MockTransport(handler))
        )
    )

    frame = asyncio.run(provider.get_latest_price("msft"))

    assert "/v2/aggs/ticker/MSFT/prev" in captured["url"]
    assert captured["apiKey"] == "test-key"
    assert list(frame.columns) == ["symbol", "timestamp", "price", "provider"]
    assert frame.at[0, "symbol"] == "MSFT"
    assert frame.at[0, "provider"] == "polygon"
    assert frame.at[0, "price"] == 123.45
    assert frame["timestamp"].dt.tz is not None


def test_polygon_provider_latest_price_requires_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("POLYGON_API_KEY", raising=False)
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"results": []})
    )
    provider = PolygonProvider(
        http_client=HTTPClient(client=httpx.Client(transport=transport))
    )

    with pytest.raises(ConfigurationError, match="POLYGON_API_KEY is not configured"):
        asyncio.run(provider.get_latest_price("msft"))


def test_polygon_provider_latest_price_rejects_empty_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POLYGON_API_KEY", "test-key")
    provider = PolygonProvider(
        http_client=HTTPClient(
            client=httpx.Client(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, json={"results": []})
                )
            )
        )
    )

    with pytest.raises(DataProviderError, match="no results"):
        asyncio.run(provider.get_latest_price("msft"))


def test_polygon_provider_latest_price_rejects_missing_price_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POLYGON_API_KEY", "test-key")
    provider = PolygonProvider(
        http_client=HTTPClient(
            client=httpx.Client(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(
                        200,
                        json={"results": [{"t": 1767312000000}]},
                    )
                )
            )
        )
    )

    with pytest.raises(DataProviderError, match="missing field"):
        asyncio.run(provider.get_latest_price("msft"))


@pytest.mark.parametrize(
    ("interval", "expected_path"),
    [
        ("1min", "/v2/aggs/ticker/MSFT/range/1/minute/"),
        ("1hour", "/v2/aggs/ticker/MSFT/range/1/hour/"),
    ],
)
def test_polygon_provider_intraday_prices_are_normalized(
    monkeypatch: pytest.MonkeyPatch,
    interval: str,
    expected_path: str,
) -> None:
    monkeypatch.setenv("POLYGON_API_KEY", "test-key")
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["apiKey"] = request.url.params["apiKey"]
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "t": 1767225600000,
                        "o": 1.0,
                        "h": 2.0,
                        "l": 0.5,
                        "c": 1.5,
                        "v": 100,
                    },
                    {
                        "t": 1767312000000,
                        "o": 2.0,
                        "h": 3.0,
                        "l": 1.5,
                        "c": 2.5,
                        "v": 200,
                    },
                ]
            },
        )

    provider = PolygonProvider(
        http_client=HTTPClient(
            client=httpx.Client(transport=httpx.MockTransport(handler))
        )
    )

    frame = asyncio.run(
        provider.get_intraday_prices(
            "msft",
            datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
            datetime(2026, 1, 2, 0, 0, tzinfo=UTC),
            interval=interval,
        )
    )

    assert expected_path in captured["url"]
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
    assert list(frame["timestamp"]) == [
        pd.Timestamp("2026-01-01T00:00:00Z"),
        pd.Timestamp("2026-01-02T00:00:00Z"),
    ]
    assert list(frame["symbol"]) == ["MSFT", "MSFT"]
    assert list(frame["provider"]) == ["polygon", "polygon"]
    assert frame["timestamp"].dt.tz is not None


def test_polygon_provider_intraday_prices_unsupported_interval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POLYGON_API_KEY", "test-key")
    provider = PolygonProvider(
        http_client=HTTPClient(
            client=httpx.Client(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, json={})
                )
            )
        )
    )

    with pytest.raises(ValueError, match="Unsupported interval"):
        asyncio.run(
            provider.get_intraday_prices(
                "msft",
                datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
                datetime(2026, 1, 2, 0, 0, tzinfo=UTC),
                interval="2min",
            )
        )


def test_polygon_provider_intraday_prices_requires_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("POLYGON_API_KEY", raising=False)
    provider = PolygonProvider(
        http_client=HTTPClient(
            client=httpx.Client(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, json={"results": []})
                )
            )
        )
    )

    with pytest.raises(ConfigurationError, match="POLYGON_API_KEY is not configured"):
        asyncio.run(
            provider.get_intraday_prices(
                "msft",
                datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
                datetime(2026, 1, 2, 0, 0, tzinfo=UTC),
            )
        )


def test_polygon_provider_intraday_prices_returns_empty_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POLYGON_API_KEY", "test-key")
    provider = PolygonProvider(
        http_client=HTTPClient(
            client=httpx.Client(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, json={"results": []})
                )
            )
        )
    )

    frame = asyncio.run(
        provider.get_intraday_prices(
            "msft",
            datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
            datetime(2026, 1, 2, 0, 0, tzinfo=UTC),
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


def test_polygon_provider_intraday_prices_rejects_malformed_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POLYGON_API_KEY", "test-key")
    provider = PolygonProvider(
        http_client=HTTPClient(
            client=httpx.Client(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, json={"results": "bad"})
                )
            )
        )
    )

    with pytest.raises(DataProviderError, match="must be a list"):
        asyncio.run(
            provider.get_intraday_prices(
                "msft",
                datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
                datetime(2026, 1, 2, 0, 0, tzinfo=UTC),
            )
        )


def _daily_provider_with_value(field: str, value: object) -> PolygonProvider:
    row: dict[str, object] = {
        "t": 1,
        "o": 1.0,
        "h": 2.0,
        "l": 0.5,
        "c": 1.5,
        "v": 100,
    }
    row[field] = value
    return PolygonProvider(
        api_key="test-key",
        http_client=HTTPClient(
            client=httpx.Client(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(
                        200,
                        json={"adjusted": True, "results": [row]},
                    )
                )
            )
        ),
    )


@pytest.mark.parametrize("timestamp", ["bad", True, float("nan"), float("inf")])
def test_polygon_daily_prices_wrap_malformed_timestamp(
    timestamp: object,
) -> None:
    provider = _daily_provider_with_value("t", timestamp)
    with pytest.raises(DataProviderError, match="malformed"):
        provider._daily_payload_to_frame(
            "MSFT",
            {
                "adjusted": True,
                "results": [
                    {
                        "t": timestamp,
                        "o": 1.0,
                        "h": 2.0,
                        "l": 0.5,
                        "c": 1.5,
                        "v": 100,
                    }
                ],
            },
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("o", "bad"),
        ("h", True),
        ("l", float("nan")),
        ("c", float("inf")),
        ("v", "bad"),
    ],
)
def test_polygon_daily_prices_wrap_malformed_ohlcv(
    field: str,
    value: object,
) -> None:
    provider = _daily_provider_with_value(field, value)
    with pytest.raises(DataProviderError, match="malformed"):
        row = {
            "t": 1,
            "o": 1.0,
            "h": 2.0,
            "l": 0.5,
            "c": 1.5,
            "v": 100,
        }
        row[field] = value
        provider._daily_payload_to_frame(
            "MSFT",
            {
                "adjusted": True,
                "results": [row],
            },
        )


def test_polygon_completed_daily_acquisition_preserves_governed_transport_facts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received_at = datetime(2026, 9, 3, 1, 2, 3, tzinfo=UTC)
    clock_calls = 0
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            content=(
                b'{"ticker":"AAPL","adjusted":true,"request_id":"request-123",'
                b'"queryCount":1,"resultsCount":1,"count":1,'
                b'"next_url":"https://api.massive.com/v2/aggs/ticker/MSFT/'
                b"range/1/day/2026-01-02/2026-01-31?cursor=next"
                b'&apiKey=response-secret","results":[{'
                b'"t":1767312000000,'
                b'"o":12345678901234567890.12345678901234567890123456789,'
                b'"h":125.5,"l":120,"c":124.2500,"v":100.125}]}'
            ),
        )

    def response_clock() -> datetime:
        nonlocal clock_calls
        clock_calls += 1
        return received_at

    client = HTTPClient(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        response_clock=response_clock,
    )
    monkeypatch.setattr(
        client,
        "get",
        lambda *args, **kwargs: pytest.fail("standard JSON path was used"),
    )
    provider = PolygonProvider(
        http_client=client,
        api_key="request-secret",
        base_url="https://api.massive.com",
    )

    result = asyncio.run(
        provider.get_completed_daily_acquisition(
            "MSFT",
            date(2026, 1, 1),
            "2026-01-31",
        )
    )

    assert type(result) is PolygonCompletedDailyAcquisition
    assert len(requests) == 1
    request = requests[0]
    assert request.url.scheme == "https"
    assert request.url.host == "api.polygon.io"
    assert request.url.path == (
        "/v2/aggs/ticker/MSFT/range/1/day/2026-01-01/2026-01-31"
    )
    assert dict(request.url.params) == {
        "adjusted": "true",
        "sort": "asc",
        "limit": "50000",
        "apiKey": "request-secret",
    }
    assert result.requested_ticker == "MSFT"
    assert result.request_base_url == POLYGON_BASE_URL
    assert result.resolved_route == request.url.path
    assert result.requested_from == "2026-01-01"
    assert result.requested_to == "2026-01-31"
    assert result.multiplier == 1
    assert result.timespan == "day"
    assert result.adjusted is True
    assert result.sort == "asc"
    assert result.limit == 50000
    assert result.response_ticker_is_present is True
    assert result.response_ticker == "AAPL"
    assert result.response_adjusted_is_present is True
    assert result.response_adjusted is True
    assert result.request_id_is_present is True
    assert result.request_id == "request-123"
    assert result.query_count_is_present is True
    assert result.query_count == 1
    assert result.results_count_is_present is True
    assert result.results_count == 1
    assert result.count_is_present is True
    assert result.count == 1
    assert result.next_url_is_present is True
    assert result.next_page_reference == (
        "https://api.massive.com/v2/aggs/ticker/MSFT/range/1/day/"
        "2026-01-02/2026-01-31?cursor=next"
    )
    assert result.additional_page_indicated is True
    assert result.results_is_present is True
    assert result.response_received_at is received_at
    assert clock_calls == 1

    assert len(result.rows) == 1
    row = result.rows[0]
    assert type(row) is PolygonCompletedDailyAggregate
    assert type(row.timestamp) is int
    assert row.timestamp == 1767312000000
    assert row.open == Decimal("12345678901234567890.12345678901234567890123456789")
    assert type(row.open) is Decimal
    assert row.high == Decimal("125.5")
    assert type(row.low) is int
    assert row.close == Decimal("124.2500")
    assert row.volume == Decimal("100.125")
    assert type(row.volume) is Decimal
    assert "request-secret" not in repr(result)
    assert "response-secret" not in repr(result)
    assert {field.name for field in fields(result)}.isdisjoint(
        {"api_key", "response", "client", "http_client", "next_url"}
    )
    with pytest.raises(FrozenInstanceError):
        result.requested_ticker = "CHANGED"
    with pytest.raises(FrozenInstanceError):
        row.open = Decimal("0")


def test_polygon_completed_daily_profile_cannot_be_selected_by_callers() -> None:
    parameters = signature(PolygonProvider.get_completed_daily_acquisition).parameters

    assert set(parameters) == {"self", "ticker", "start", "end"}


def test_polygon_completed_daily_preserves_absent_metadata_without_synthesis() -> None:
    provider, requests = _completed_daily_provider(b"{}")

    result = asyncio.run(
        provider.get_completed_daily_acquisition(
            "case.sensitive",
            "2026-01-01",
            "2026-01-02",
        )
    )

    assert len(requests) == 1
    assert requests[0].url.path == (
        "/v2/aggs/ticker/case.sensitive/range/1/day/2026-01-01/2026-01-02"
    )
    assert result.requested_ticker == "case.sensitive"
    assert result.response_ticker_is_present is False
    assert result.response_ticker is None
    assert result.response_adjusted_is_present is False
    assert result.response_adjusted is None
    assert result.request_id_is_present is False
    assert result.request_id is None
    assert result.query_count_is_present is False
    assert result.query_count is None
    assert result.results_count_is_present is False
    assert result.results_count is None
    assert result.count_is_present is False
    assert result.count is None
    assert result.next_url_is_present is False
    assert result.next_page_reference is None
    assert result.additional_page_indicated is False
    assert result.results_is_present is False
    assert result.rows == ()


def test_polygon_completed_daily_distinguishes_null_from_absent_metadata() -> None:
    provider, _ = _completed_daily_provider(
        b'{"ticker":null,"adjusted":null,"request_id":null,'
        b'"queryCount":null,"resultsCount":null,"count":null,'
        b'"next_url":null,"results":[]}'
    )

    result = asyncio.run(
        provider.get_completed_daily_acquisition(
            "MSFT",
            "2026-01-01",
            "2026-01-02",
        )
    )

    assert result.response_ticker_is_present is True
    assert result.response_ticker is None
    assert result.response_adjusted_is_present is True
    assert result.response_adjusted is None
    assert result.request_id_is_present is True
    assert result.request_id is None
    assert result.query_count_is_present is True
    assert result.query_count is None
    assert result.results_count_is_present is True
    assert result.results_count is None
    assert result.count_is_present is True
    assert result.count is None
    assert result.next_url_is_present is True
    assert result.next_page_reference is None
    assert result.additional_page_indicated is False
    assert result.results_is_present is True
    assert result.rows == ()


@pytest.mark.parametrize(
    ("body", "message"),
    (
        (b"[]", "response must be an object"),
        (b'{"results":{}}', "results must be an array"),
        (b'{"results":null}', "results must be an array"),
        (b'{"results":[1]}', "aggregate must be an object"),
    ),
)
def test_polygon_completed_daily_rejects_wrong_response_structure(
    body: bytes,
    message: str,
) -> None:
    provider, _ = _completed_daily_provider(body)

    with pytest.raises(DataProviderError, match=message):
        asyncio.run(
            provider.get_completed_daily_acquisition(
                "MSFT",
                "2026-01-01",
                "2026-01-02",
            )
        )


@pytest.mark.parametrize("missing", ("t", "o", "h", "l", "c", "v"))
def test_polygon_completed_daily_rejects_missing_aggregate_fields(
    missing: str,
) -> None:
    row = {"t": 1, "o": 2, "h": 3, "l": 1, "c": 2, "v": 100}
    del row[missing]
    provider, _ = _completed_daily_provider(json.dumps({"results": [row]}).encode())

    with pytest.raises(DataProviderError, match=f"missing field: {missing}"):
        asyncio.run(
            provider.get_completed_daily_acquisition(
                "MSFT",
                "2026-01-01",
                "2026-01-02",
            )
        )


@pytest.mark.parametrize("field", ("t", "o", "h", "l", "c", "v"))
def test_polygon_completed_daily_rejects_boolean_aggregate_numbers(
    field: str,
) -> None:
    row = {"t": 1, "o": 2, "h": 3, "l": 1, "c": 2, "v": 100}
    row[field] = True
    provider, _ = _completed_daily_provider(json.dumps({"results": [row]}).encode())

    with pytest.raises(DataProviderError, match="must be an exact JSON number"):
        asyncio.run(
            provider.get_completed_daily_acquisition(
                "MSFT",
                "2026-01-01",
                "2026-01-02",
            )
        )


@pytest.mark.parametrize(
    ("body", "message"),
    (
        (b'{"ticker":1}', "ticker must be a string or null"),
        (b'{"request_id":true}', "request_id must be a string or null"),
        (b'{"queryCount":true}', "queryCount must be an integer or null"),
        (b'{"resultsCount":1.5}', "resultsCount must be an integer or null"),
        (b'{"count":"1"}', "count must be an integer or null"),
        (b'{"adjusted":1}', "adjusted must be a boolean or null"),
        (b'{"next_url":1}', "next_url must be a string or null"),
    ),
)
def test_polygon_completed_daily_rejects_malformed_metadata(
    body: bytes,
    message: str,
) -> None:
    provider, _ = _completed_daily_provider(body)

    with pytest.raises(DataProviderError, match=message):
        asyncio.run(
            provider.get_completed_daily_acquisition(
                "MSFT",
                "2026-01-01",
                "2026-01-02",
            )
        )


def test_polygon_daily_research_path_remains_float_dataframe_based() -> None:
    provider = PolygonProvider(
        api_key="test-key",
        http_client=HTTPClient(
            client=httpx.Client(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(
                        200,
                        content=(
                            b'{"adjusted":true,"results":[{"t":1767312000000,'
                            b'"o":1.25,"h":2.5,"l":1.0,"c":2.0,"v":100.5}]}'
                        ),
                    )
                )
            )
        ),
    )

    frame = asyncio.run(provider.get_daily_prices("msft", "2026-01-01", "2026-01-02"))

    assert list(frame["symbol"]) == ["MSFT"]
    assert all(
        not isinstance(value, Decimal)
        for field in ("open", "high", "low", "close", "volume")
        for value in frame[field]
    )
    assert str(frame["open"].dtype) == "float64"


@pytest.mark.parametrize("ticker", ("BRK.B", "brk.b", "A1"))
def test_polygon_completed_daily_accepts_stock_ticker_punctuation_and_case(
    ticker: str,
) -> None:
    provider, requests = _completed_daily_provider(b"{}")

    result = asyncio.run(
        provider.get_completed_daily_acquisition(
            ticker,
            date(2026, 1, 1),
            date(2026, 1, 2),
        )
    )

    assert len(requests) == 1
    assert result.requested_ticker == ticker
    assert result.resolved_route == requests[0].url.path
    assert requests[0].url.path == (
        f"/v2/aggs/ticker/{ticker}/range/1/day/2026-01-01/2026-01-02"
    )


@pytest.mark.parametrize(
    "ticker",
    (
        "",
        "../details",
        "A/B",
        "A\\B",
        "A?query=true",
        "A#fragment",
        "A%2FB",
        ".",
        "..",
        " AAPL",
        "AAPL ",
        "AA PL",
        "AA\nPL",
        "BRK-B",
    ),
)
def test_polygon_completed_daily_rejects_route_controlling_tickers(
    ticker: str,
) -> None:
    provider, requests = _completed_daily_provider(b"{}")

    with pytest.raises(DataProviderError, match="valid U.S. stock ticker"):
        asyncio.run(
            provider.get_completed_daily_acquisition(
                ticker,
                date(2026, 1, 1),
                date(2026, 1, 2),
            )
        )

    assert requests == []


def test_polygon_completed_daily_serializes_semantic_dates_canonically() -> None:
    provider, requests = _completed_daily_provider(b"{}")

    result = asyncio.run(
        provider.get_completed_daily_acquisition(
            "BRK.B",
            date(2026, 2, 3),
            date(2026, 11, 12),
        )
    )

    assert result.requested_from == "2026-02-03"
    assert result.requested_to == "2026-11-12"
    assert result.resolved_route == requests[0].url.path
    assert requests[0].url.path == (
        "/v2/aggs/ticker/BRK.B/range/1/day/2026-02-03/2026-11-12"
    )


@pytest.mark.parametrize(
    "value",
    (
        "",
        "2026-1-01",
        "20260101",
        "2026-02-30",
        "2026-01-01T00:00:00",
        "../2026-01-01",
        "2026-01-01?query=true",
        "2026-01-01#fragment",
        " 2026-01-01",
        "2026-01-01 ",
        "2026-01-01%2F..",
        datetime(2026, 1, 1, tzinfo=UTC),
        20260101,
    ),
)
@pytest.mark.parametrize("field", ("start", "end"))
def test_polygon_completed_daily_rejects_noncanonical_date_inputs(
    field: str,
    value: object,
) -> None:
    provider, requests = _completed_daily_provider(b"{}")
    start: object = value if field == "start" else date(2026, 1, 1)
    end: object = value if field == "end" else date(2026, 1, 2)

    with pytest.raises(DataProviderError, match="YYYY-MM-DD"):
        asyncio.run(
            provider.get_completed_daily_acquisition(
                "MSFT",
                cast(date | str, start),
                cast(date | str, end),
            )
        )

    assert requests == []


@pytest.mark.parametrize(
    ("start", "end"),
    (
        (date(2026, 1, 3), date(2026, 1, 2)),
        ("2026-01-03", "2026-01-02"),
    ),
)
def test_polygon_completed_daily_rejects_reversed_bounds_before_exact_transport(
    monkeypatch: pytest.MonkeyPatch,
    start: date | str,
    end: date | str,
) -> None:
    provider, requests = _completed_daily_provider(b"{}")
    exact_transport_calls = 0

    def get_exact_json(*args: object, **kwargs: object) -> ExactJsonResult:
        nonlocal exact_transport_calls
        exact_transport_calls += 1
        return cast(
            ExactJsonResult,
            SimpleNamespace(
                value=MappingProxyType({}),
                response_received_at=datetime(2026, 9, 3, tzinfo=UTC),
            ),
        )

    monkeypatch.setattr(provider.http_client, "get_exact_json", get_exact_json)

    with pytest.raises(
        DataProviderError, match="start date must not be after end date"
    ):
        asyncio.run(provider.get_completed_daily_acquisition("MSFT", start, end))

    assert exact_transport_calls == 0
    assert requests == []


@pytest.mark.parametrize(
    "bound",
    (date(2026, 1, 2), "2026-01-02"),
)
def test_polygon_completed_daily_accepts_equal_bounds(bound: date | str) -> None:
    provider, requests = _completed_daily_provider(b"{}")

    result = asyncio.run(provider.get_completed_daily_acquisition("MSFT", bound, bound))

    assert len(requests) == 1
    assert result.requested_from == "2026-01-02"
    assert result.requested_to == "2026-01-02"
    assert result.resolved_route == requests[0].url.path


@pytest.mark.parametrize("field", ("o", "v"))
@pytest.mark.parametrize("value", (1.25, True, "1.25", None))
def test_polygon_completed_daily_public_method_rejects_inexact_numeric_values(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: object,
) -> None:
    row: dict[str, object] = {
        "t": 1,
        "o": 2,
        "h": 3,
        "l": 1,
        "c": 2,
        "v": 100,
    }
    row[field] = value
    exact_result = cast(
        ExactJsonResult,
        SimpleNamespace(
            value=MappingProxyType({"results": (MappingProxyType(row),)}),
            response_received_at=datetime(2026, 9, 3, tzinfo=UTC),
        ),
    )
    provider, _ = _completed_daily_provider(b"{}")
    monkeypatch.setattr(
        provider.http_client,
        "get_exact_json",
        lambda *args, **kwargs: exact_result,
    )

    with pytest.raises(DataProviderError, match="must be an exact JSON number"):
        asyncio.run(
            provider.get_completed_daily_acquisition(
                "MSFT",
                date(2026, 1, 1),
                date(2026, 1, 2),
            )
        )


def test_polygon_completed_daily_sanitizes_pagination_reference_credentials() -> None:
    secret_values = tuple(f"secret-{index}" for index in range(1, 15))
    credential_parameters = (
        "apiKey",
        "APIKEY",
        "api_key",
        "api-key",
        "x-api-key",
        "x_api_key",
        "api_token",
        "api-token",
        "access_token",
        "client_secret",
        "client-secret",
        "authorization",
        "token",
        "key",
    )
    secret_query = "&".join(
        f"{name}={secret}"
        for name, secret in zip(
            credential_parameters,
            secret_values,
            strict=True,
        )
    )
    body = (
        '{"next_url":"https://api.massive.com/v2/aggs?'
        f"{secret_query}&cursor=next&order=asc#fragment-secret"
        '"}'
    ).encode()
    provider, requests = _completed_daily_provider(body)

    result = asyncio.run(
        provider.get_completed_daily_acquisition(
            "MSFT",
            date(2026, 1, 1),
            date(2026, 1, 2),
        )
    )

    assert len(requests) == 1
    assert result.next_url_is_present is True
    assert result.next_page_reference == (
        "https://api.massive.com/v2/aggs?cursor=next&order=asc"
    )
    assert result.additional_page_indicated is True
    rendered = repr(result)
    assert "fragment-secret" not in rendered
    assert all(secret not in rendered for secret in secret_values)


def test_polygon_completed_daily_rejects_pagination_userinfo_without_echoing_it() -> (
    None
):
    provider, requests = _completed_daily_provider(
        b'{"next_url":"https://credential-user:password-secret@'
        b'api.massive.com/v2/aggs?cursor=next"}'
    )

    with pytest.raises(
        DataProviderError, match="must not contain user information"
    ) as exc:
        asyncio.run(
            provider.get_completed_daily_acquisition(
                "MSFT",
                date(2026, 1, 1),
                date(2026, 1, 2),
            )
        )

    assert len(requests) == 1
    assert "credential-user" not in str(exc.value)
    assert "password-secret" not in str(exc.value)


def test_polygon_completed_daily_public_constructors_accept_valid_shape() -> None:
    aggregate = _valid_completed_daily_aggregate()
    acquisition = _valid_completed_daily_acquisition(rows=(aggregate,))

    assert acquisition.requested_ticker == "BRK.B"
    assert acquisition.request_base_url == POLYGON_BASE_URL
    assert acquisition.resolved_route == (
        "/v2/aggs/ticker/BRK.B/range/1/day/2026-01-01/2026-01-02"
    )
    assert acquisition.multiplier == 1
    assert acquisition.timespan == "day"
    assert acquisition.adjusted is True
    assert acquisition.sort == "asc"
    assert acquisition.limit == 50000
    assert acquisition.rows == (aggregate,)


@pytest.mark.parametrize("field", ("open", "volume"))
@pytest.mark.parametrize(
    "value",
    (1.25, True, "1.25", None, Decimal("NaN"), Decimal("Infinity")),
)
def test_polygon_completed_daily_aggregate_constructor_rejects_invalid_numeric_values(
    field: str,
    value: object,
) -> None:
    values: dict[str, object] = {
        "timestamp": 1,
        "open": Decimal("1.25"),
        "high": 2,
        "low": 1,
        "close": Decimal("1.5"),
        "volume": Decimal("100.125"),
    }
    values[field] = value

    with pytest.raises(DataProviderError, match="JSON number"):
        PolygonCompletedDailyAggregate(**values)  # type: ignore[arg-type]


def test_polygon_completed_daily_acquisition_constructor_rejects_mutable_rows() -> None:
    aggregate = _valid_completed_daily_aggregate()

    with pytest.raises(DataProviderError, match="rows must be a tuple"):
        _valid_completed_daily_acquisition(
            rows=cast(tuple[PolygonCompletedDailyAggregate, ...], [aggregate])
        )


def test_polygon_completed_daily_acquisition_constructor_rejects_invalid_row_type() -> (
    None
):
    with pytest.raises(DataProviderError, match="exact aggregate values"):
        _valid_completed_daily_acquisition(
            rows=cast(tuple[PolygonCompletedDailyAggregate, ...], ("not-a-row",))
        )


@pytest.mark.parametrize(
    ("changes", "message"),
    (
        (
            {
                "response_ticker_is_present": False,
                "response_ticker": "MSFT",
            },
            "absent response_ticker must be null",
        ),
        (
            {
                "request_id_is_present": 1,
            },
            "request_id_is_present must be a boolean",
        ),
        (
            {
                "results_is_present": False,
                "rows": (
                    PolygonCompletedDailyAggregate(
                        timestamp=1,
                        open=1,
                        high=1,
                        low=1,
                        close=1,
                        volume=1,
                    ),
                ),
            },
            "absent results cannot contain rows",
        ),
    ),
)
def test_polygon_completed_daily_acquisition_constructor_rejects_contradictions(
    changes: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(DataProviderError, match=message):
        _valid_completed_daily_acquisition(**changes)


@pytest.mark.parametrize(
    ("changes", "message"),
    (
        ({"requested_ticker": "../details"}, "valid U.S. stock ticker"),
        ({"requested_from": "2026-02-30"}, "YYYY-MM-DD"),
        (
            {"response_received_at": datetime(2026, 9, 3)},
            "timezone-aware",
        ),
        (
            {
                "response_received_at": datetime(
                    2026,
                    9,
                    3,
                    tzinfo=timezone(timedelta(hours=8)),
                )
            },
            "must be UTC",
        ),
        (
            {
                "next_url_is_present": True,
                "next_page_reference": (
                    "https://api.massive.com/v2/aggs?api-key=secret"
                ),
            },
            "must be sanitized",
        ),
    ),
)
def test_polygon_completed_daily_acquisition_constructor_rejects_invalid_facts(
    changes: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(DataProviderError, match=message):
        _valid_completed_daily_acquisition(**changes)


def test_polygon_completed_daily_acquisition_constructor_rejects_reversed_bounds() -> (
    None
):
    with pytest.raises(
        DataProviderError, match="start date must not be after end date"
    ):
        _valid_completed_daily_acquisition(
            requested_from="2026-01-03",
            requested_to="2026-01-02",
        )


def test_polygon_completed_daily_acquisition_constructor_accepts_equal_bounds() -> None:
    acquisition = _valid_completed_daily_acquisition(
        requested_from="2026-01-02",
        requested_to="2026-01-02",
    )

    assert acquisition.requested_from == acquisition.requested_to == "2026-01-02"


def test_polygon_completed_daily_fixed_profile_is_not_constructor_selectable() -> None:
    parameters = signature(PolygonCompletedDailyAcquisition).parameters
    fixed_facts = {
        "request_base_url",
        "resolved_route",
        "multiplier",
        "timespan",
        "adjusted",
        "sort",
        "limit",
    }

    assert fixed_facts.isdisjoint(parameters)
    acquisition = _valid_completed_daily_acquisition()
    for field_name, value in (
        ("request_base_url", "https://api.massive.com"),
        ("adjusted", False),
        ("limit", 100),
    ):
        with pytest.raises(TypeError, match="init=False"):
            replace(acquisition, **{field_name: value})


_POLYGON_PROVIDER_MODULE = "market_platform.data.providers.polygon"
_EVIDENCE_MODULE = "market_platform.evidence"


def _resolved_import_targets(source: str, *, module_name: str) -> set[str]:
    package = module_name.rpartition(".")[0]
    imports: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level:
            imported_from = resolve_name(
                f"{'.' * node.level}{node.module or ''}",
                package,
            )
        elif node.module is not None:
            imported_from = node.module
        else:
            continue
        imports.add(imported_from)
        imports.update(
            f"{imported_from}.{alias.name}" for alias in node.names if alias.name != "*"
        )
    return imports


def _imports_evidence_dependency(source: str) -> bool:
    return any(
        imported == _EVIDENCE_MODULE or imported.startswith(f"{_EVIDENCE_MODULE}.")
        for imported in _resolved_import_targets(
            source,
            module_name=_POLYGON_PROVIDER_MODULE,
        )
    )


@pytest.mark.parametrize(
    "source",
    (
        "import market_platform.evidence",
        "import market_platform.evidence.foo",
        "from market_platform import evidence",
        "from market_platform.evidence import EvidenceArtifact",
        "from market_platform.evidence.foo import Bar",
        "from ... import evidence",
        "from ...evidence import EvidenceArtifact",
        "from ...evidence.foo import Bar",
    ),
)
def test_evidence_dependency_detector_rejects_forbidden_imports(source: str) -> None:
    assert _imports_evidence_dependency(source) is True


def test_evidence_dependency_detector_allows_unrelated_relative_import() -> None:
    assert _imports_evidence_dependency("from ..models import Evidence") is False


def test_polygon_provider_source_has_no_evidence_dependency() -> None:
    source_path = Path("src/market_platform/data/providers/polygon.py")
    source = source_path.read_text(encoding="utf-8")

    assert _imports_evidence_dependency(source) is False


def _completed_daily_provider(
    body: bytes,
) -> tuple[PolygonProvider, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=body)

    return (
        PolygonProvider(
            api_key="test-key",
            http_client=HTTPClient(
                client=httpx.Client(transport=httpx.MockTransport(handler)),
                response_clock=lambda: datetime(2026, 9, 3, tzinfo=UTC),
            ),
        ),
        requests,
    )


def _valid_completed_daily_aggregate() -> PolygonCompletedDailyAggregate:
    return PolygonCompletedDailyAggregate(
        timestamp=1767312000000,
        open=Decimal("1.25"),
        high=2,
        low=1,
        close=Decimal("1.5"),
        volume=Decimal("100.125"),
    )


def _valid_completed_daily_acquisition(
    **changes: object,
) -> PolygonCompletedDailyAcquisition:
    values: dict[str, object] = {
        "requested_ticker": "BRK.B",
        "requested_from": "2026-01-01",
        "requested_to": "2026-01-02",
        "response_ticker_is_present": True,
        "response_ticker": "BRK.B",
        "response_adjusted_is_present": True,
        "response_adjusted": True,
        "request_id_is_present": True,
        "request_id": "request-123",
        "query_count_is_present": True,
        "query_count": 1,
        "results_count_is_present": True,
        "results_count": 1,
        "count_is_present": True,
        "count": 1,
        "next_url_is_present": False,
        "next_page_reference": None,
        "results_is_present": True,
        "rows": (),
        "response_received_at": datetime(2026, 9, 3, tzinfo=UTC),
    }
    values.update(changes)
    return PolygonCompletedDailyAcquisition(**values)  # type: ignore[arg-type]
