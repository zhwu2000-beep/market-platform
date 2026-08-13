from __future__ import annotations

import asyncio
from dataclasses import fields
from datetime import UTC, date, datetime, timedelta, tzinfo
from typing import cast
from zoneinfo import ZoneInfo

import httpx
import pandas as pd
import pytest

from market_platform.data.capabilities import DataCapability
from market_platform.data.exceptions import ConfigurationError, DataProviderError
from market_platform.data.http import HTTPClient
from market_platform.data.provider import DataProvider
from market_platform.data.providers.polygon import PolygonProvider
from market_platform.data.selection import ProviderCandidate, ProviderSelectionPolicy
from market_platform.data.service import MarketDataService
from market_platform.research import (
    DailyTechnicalResearchRequest,
    DailyTechnicalResearchResult,
    DailyTechnicalResearchWorkflow,
    PriceAdjustmentPolicy,
    ResearchTimeframe,
    TechnicalAnalysisQuality,
    construct_daily_technical_analysis_profile,
)
from market_platform.trading.instrument import TradingInstrumentIdentity


class DailyProvider(DataProvider):
    name = "polygon"

    def __init__(
        self,
        frame: pd.DataFrame,
        error: Exception | None = None,
    ) -> None:
        self.frame = frame
        self.error = error
        self.calls: list[tuple[str, date, date]] = []

    async def get_daily_prices(
        self, symbol: str, start: date | str, end: date | str
    ) -> pd.DataFrame:
        assert isinstance(start, date)
        assert isinstance(end, date)
        self.calls.append((symbol, start, end))
        if self.error is not None:
            raise self.error
        return self.frame.copy(deep=True)

    async def get_intraday_prices(
        self,
        symbol: str,
        start: datetime | date | str,
        end: datetime | date | str,
        interval: str = "1min",
    ) -> pd.DataFrame:
        raise AssertionError("intraday prices must not be requested")

    async def get_latest_price(self, symbol: str) -> pd.DataFrame:
        raise AssertionError("latest price must not be requested")

    async def health_check(self) -> pd.DataFrame:
        raise AssertionError("health check must not be requested")


def _frame(
    count: int,
    *,
    end: date = date(2026, 8, 11),
    provider: str = "polygon",
) -> pd.DataFrame:
    dates = pd.bdate_range(end=end, periods=count, tz=UTC)
    rows = []
    for index, timestamp in enumerate(dates):
        close = 100.0 + index * 0.25
        rows.append(
            {
                "symbol": "NVDA",
                "timestamp": timestamp,
                "open": close - 0.5,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 1_000_000.0 + index,
                "provider": provider,
            }
        )
    return pd.DataFrame(rows)


def _polygon_provider(
    frame: pd.DataFrame,
    error: Exception | None = None,
) -> PolygonProvider:
    calls: list[tuple[str, date, date]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        start = date.fromisoformat(request.url.path.split("/")[-2])
        end = date.fromisoformat(request.url.path.split("/")[-1])
        calls.append(("NVDA", start, end))
        if error is not None:
            raise error
        results = [
            {
                "t": int((row.timestamp + pd.Timedelta(hours=12)).timestamp() * 1000),
                "o": row.open,
                "h": row.high,
                "l": row.low,
                "c": row.close,
                "v": row.volume,
            }
            for row in frame.itertuples()
        ]
        return httpx.Response(200, json={"adjusted": True, "results": results})

    provider = PolygonProvider(
        api_key="test-key",
        http_client=HTTPClient(
            client=httpx.Client(transport=httpx.MockTransport(handler))
        ),
    )
    provider.calls = calls
    return provider


def _service(provider: DataProvider, *others: DataProvider) -> MarketDataService:
    candidates = [
        ProviderCandidate(
            name=provider.name,
            provider=provider,
            capabilities=frozenset({DataCapability.DAILY_PRICES}),
        ),
        *[
            ProviderCandidate(
                name=item.name,
                provider=item,
                capabilities=frozenset({DataCapability.DAILY_PRICES}),
            )
            for item in others
        ],
    ]
    return MarketDataService(
        ProviderSelectionPolicy(candidates, ["twelvedata", "polygon"])
    )


def _request(as_of: datetime | None = None) -> DailyTechnicalResearchRequest:
    return DailyTechnicalResearchRequest(
        instrument=TradingInstrumentIdentity("NVDA", "NASDAQ"),
        timeframe=ResearchTimeframe.DAILY,
        provider=" Polygon ",
        analysis_as_of=as_of or datetime(2026, 8, 12, 16, tzinfo=UTC),
        profile=construct_daily_technical_analysis_profile(),
    )


def _run(
    count: int,
    *,
    as_of: datetime | None = None,
    provider_name: str = "polygon",
) -> DailyTechnicalResearchResult:
    frame = _frame(count, provider=provider_name)
    provider: DataProvider = (
        _polygon_provider(frame) if provider_name == "polygon" else DailyProvider(frame)
    )
    return asyncio.run(
        DailyTechnicalResearchWorkflow(_service(provider)).run(_request(as_of))
    )


def test_request_fields_and_projection_are_exact_and_ordered() -> None:
    request = _request(datetime(2026, 8, 13, 0, 30, tzinfo=ZoneInfo("Asia/Shanghai")))

    assert [field.name for field in fields(request)] == [
        "instrument",
        "timeframe",
        "provider",
        "analysis_as_of",
        "profile",
    ]
    assert list(request.to_dict()) == [
        "instrument",
        "timeframe",
        "provider",
        "analysis_as_of",
        "profile",
    ]
    assert request.provider == "polygon"
    assert request.analysis_as_of == datetime(2026, 8, 12, 16, 30, tzinfo=UTC)


def test_request_defensively_reconstructs_instrument() -> None:
    instrument = TradingInstrumentIdentity("NVDA", "NASDAQ")
    request = DailyTechnicalResearchRequest(
        instrument,
        ResearchTimeframe.DAILY,
        "polygon",
        datetime.now(UTC),
        construct_daily_technical_analysis_profile(),
    )
    assert request.instrument == instrument
    assert request.instrument is not instrument


@pytest.mark.parametrize("provider", ["twelvedata", "", "poly"])
def test_request_rejects_other_provider(provider: str) -> None:
    with pytest.raises(ValueError, match="polygon"):
        DailyTechnicalResearchRequest(
            TradingInstrumentIdentity("NVDA", "NASDAQ"),
            ResearchTimeframe.DAILY,
            provider,
            datetime.now(UTC),
            construct_daily_technical_analysis_profile(),
        )


def test_request_requires_exact_daily_timeframe() -> None:
    with pytest.raises(TypeError, match="ResearchTimeframe"):
        DailyTechnicalResearchRequest(
            TradingInstrumentIdentity("NVDA", "NASDAQ"),
            cast(ResearchTimeframe, "1d"),
            "polygon",
            datetime.now(UTC),
            construct_daily_technical_analysis_profile(),
        )


def test_request_requires_aware_analysis_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        DailyTechnicalResearchRequest(
            TradingInstrumentIdentity("NVDA", "NASDAQ"),
            ResearchTimeframe.DAILY,
            "polygon",
            datetime(2026, 8, 12),
            construct_daily_technical_analysis_profile(),
        )


def test_request_rejects_tampered_fixed_profile() -> None:
    profile = construct_daily_technical_analysis_profile()
    object.__setattr__(profile, "minimum_bar_count", 1)
    with pytest.raises(ValueError, match="fixed v1"):
        DailyTechnicalResearchRequest(
            TradingInstrumentIdentity("NVDA", "NASDAQ"),
            ResearchTimeframe.DAILY,
            "polygon",
            datetime.now(UTC),
            profile,
        )


def test_result_direct_construction_is_prohibited_and_projection_is_exact() -> None:
    with pytest.raises(TypeError, match="workflow-owned"):
        DailyTechnicalResearchResult()
    result = _run(260)
    assert list(result.to_dict()) == ["request", "snapshot"]
    assert result.to_dict()["snapshot"] == result.snapshot.to_dict()
    assert not hasattr(result, "market_data_service")
    assert not hasattr(result, "provider")
    assert not hasattr(result, "frame")
    assert not hasattr(result, "prices")
    assert not hasattr(result, "completed_prices")


@pytest.mark.parametrize(
    ("path", "value", "match"),
    [
        ("instrument", TradingInstrumentIdentity("AAPL", "NASDAQ"), "instrument"),
        ("timeframe", cast(ResearchTimeframe, "bad"), "request"),
        ("analysis_as_of", datetime(2020, 1, 1, tzinfo=UTC), "analysis_as_of"),
        ("provider", "twelvedata", "request"),
    ],
)
def test_result_rejects_correspondence_tampering(
    path: str, value: object, match: str
) -> None:
    result = _run(40)
    object.__setattr__(result.request, path, value)
    with pytest.raises(ValueError, match=match):
        result.to_dict()


def test_result_requires_adjusted_evidence_and_matching_profile() -> None:
    result = _run(40)
    object.__setattr__(
        result.snapshot.evidence,
        "adjustment_policy",
        PriceAdjustmentPolicy.PROVIDER_DEFAULT,
    )
    with pytest.raises(ValueError, match="snapshot"):
        result.to_dict()


def test_workflow_uses_exact_new_york_450_day_polygon_window() -> None:
    as_of = datetime(2026, 8, 13, 2, 0, tzinfo=UTC)
    provider = _polygon_provider(_frame(40))
    result = asyncio.run(
        DailyTechnicalResearchWorkflow(_service(provider)).run(_request(as_of))
    )
    end = as_of.astimezone(ZoneInfo("America/New_York")).date()
    assert provider.calls == [("NVDA", end - timedelta(days=450), end)]
    assert result.snapshot.evidence.provider == "polygon"
    assert result.snapshot.evidence.adjustment_policy is PriceAdjustmentPolicy.ADJUSTED


def test_workflow_explicit_polygon_route_prevents_fallback() -> None:
    polygon = _polygon_provider(_frame(40), DataProviderError("polygon failed"))
    twelve = DailyProvider(_frame(40))
    twelve.name = "twelvedata"
    with pytest.raises(DataProviderError, match="polygon failed"):
        asyncio.run(
            DailyTechnicalResearchWorkflow(_service(polygon, twelve)).run(_request())
        )
    assert polygon.calls
    assert twelve.calls == []


@pytest.mark.parametrize(
    ("count", "quality"),
    [
        (260, TechnicalAnalysisQuality.COMPLETE),
        (200, TechnicalAnalysisQuality.DEGRADED),
        (100, TechnicalAnalysisQuality.DEGRADED),
        (20, TechnicalAnalysisQuality.DEGRADED),
    ],
)
def test_workflow_preserves_complete_and_partial_history_semantics(
    count: int, quality: TechnicalAnalysisQuality
) -> None:
    result = _run(count)
    assert result.snapshot.quality is quality
    assert result.snapshot.evidence.bar_count == count
    assert result.snapshot.evidence.latest_completed_bar_session_date < (
        result.snapshot.evidence.cutoff_session_date
    )
    assert result.to_dict() == result.to_dict()


def test_workflow_rejects_empty_provider_data() -> None:
    provider = _polygon_provider(_frame(1).iloc[0:0])
    with pytest.raises(DataProviderError, match="empty response"):
        asyncio.run(DailyTechnicalResearchWorkflow(_service(provider)).run(_request()))


def test_workflow_propagates_zero_admitted_evidence() -> None:
    current = date(2026, 8, 12)
    provider = _polygon_provider(_frame(1, end=current))
    with pytest.raises(ValueError, match="at least one row"):
        asyncio.run(DailyTechnicalResearchWorkflow(_service(provider)).run(_request()))


def test_workflow_rejects_provider_mismatch() -> None:
    with pytest.raises(DataProviderError, match="production PolygonProvider"):
        _run(20, provider_name="twelvedata")


@pytest.mark.parametrize(
    "error", [ConfigurationError("missing"), DataProviderError("bad provider")]
)
def test_workflow_preserves_provider_and_configuration_failures(
    error: Exception,
) -> None:
    provider = _polygon_provider(_frame(20), error)
    with pytest.raises(DataProviderError, match=str(error)):
        asyncio.run(DailyTechnicalResearchWorkflow(_service(provider)).run(_request()))


class _NaiveOffset(tzinfo):
    def utcoffset(self, dt: datetime | None) -> None:
        return None

    def dst(self, dt: datetime | None) -> None:
        return None


def test_request_rejects_semantically_naive_tzinfo() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _request(datetime(2026, 8, 12, tzinfo=_NaiveOffset()))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider", "twelvedata"),
        ("instrument", TradingInstrumentIdentity("NVDA", "NASDAQ")),
        ("analysis_as_of", datetime(2026, 8, 12)),
        ("profile", object()),
        ("timeframe", "bad"),
    ],
)
def test_corrupted_request_fails_before_provider_io(field: str, value: object) -> None:
    request = _request()
    object.__setattr__(request, field, value)
    if field == "instrument":
        object.__setattr__(value, "symbol", "AAPL")
    provider = _polygon_provider(_frame(20))
    with pytest.raises(ValueError, match="retained"):
        asyncio.run(DailyTechnicalResearchWorkflow(_service(provider)).run(request))
    assert provider.calls == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("symbol", "AAPL"),
        ("venue", "NYSE"),
        ("instrument_fingerprint", "sha256:" + "0" * 64),
    ],
)
def test_request_rejects_forged_instrument(field: str, value: str) -> None:
    instrument = TradingInstrumentIdentity("NVDA", "NASDAQ")
    object.__setattr__(instrument, field, value)
    with pytest.raises(ValueError, match="instrument"):
        DailyTechnicalResearchRequest(
            instrument,
            ResearchTimeframe.DAILY,
            "polygon",
            datetime.now(UTC),
            construct_daily_technical_analysis_profile(),
        )


@pytest.mark.parametrize("field", ["request", "snapshot"])
def test_result_missing_retained_field_is_value_error(field: str) -> None:
    result = _run(20)
    object.__delattr__(result, field)
    with pytest.raises(ValueError, match="retained state"):
        result.to_dict()


def test_fake_provider_named_polygon_cannot_attest_adjusted_evidence() -> None:
    fake = DailyProvider(_frame(20))
    with pytest.raises(DataProviderError, match="production PolygonProvider"):
        asyncio.run(DailyTechnicalResearchWorkflow(_service(fake)).run(_request()))
    assert fake.calls == []


def test_polygon_provider_subclass_cannot_bypass_attestation() -> None:
    class _PolygonSubclass(PolygonProvider):
        pass

    real = _polygon_provider(_frame(20))
    provider = _PolygonSubclass(
        api_key="test-key",
        http_client=real.http_client,
    )
    with pytest.raises(DataProviderError, match="production PolygonProvider"):
        asyncio.run(DailyTechnicalResearchWorkflow(_service(provider)).run(_request()))


def test_market_data_service_subclass_cannot_bypass_attestation() -> None:
    class _ServiceSubclass(MarketDataService):
        pass

    provider = _polygon_provider(_frame(20))
    service = _ServiceSubclass(_service(provider)._policy)
    with pytest.raises(TypeError, match="exact MarketDataService"):
        DailyTechnicalResearchWorkflow(service)
