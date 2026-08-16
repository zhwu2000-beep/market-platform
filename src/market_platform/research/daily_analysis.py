"""Daily technical research application workflow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from market_platform.data.exceptions import DataProviderError
from market_platform.data.historical import HistoricalPriceSeries
from market_platform.data.providers.polygon import PolygonProvider
from market_platform.data.selection import ProviderCandidate, ProviderSelectionPolicy
from market_platform.data.service import MarketDataService
from market_platform.research.daily_evidence import (
    DailyAnalysisSessionScope,
    PriceAdjustmentPolicy,
    ResearchTimeframe,
    prepare_completed_daily_price_series,
)
from market_platform.research.technical_analysis import (
    DailyTechnicalAnalysisProfile,
    TechnicalAnalysisSnapshot,
    analyze_daily_technical_snapshot,
    construct_daily_technical_analysis_profile,
)
from market_platform.trading.instrument import TradingInstrumentIdentity

_MARKET_TIMEZONE = "America/New_York"
_PROVIDER = "polygon"
_LOOKBACK_CALENDAR_DAYS = 450
_RESULT_SEAL = object()


@dataclass(frozen=True, slots=True)
class DailyTechnicalResearchRequest:
    instrument: TradingInstrumentIdentity
    timeframe: ResearchTimeframe
    provider: str
    analysis_as_of: datetime
    profile: DailyTechnicalAnalysisProfile

    def __post_init__(self) -> None:
        if type(self.instrument) is not TradingInstrumentIdentity:
            raise TypeError("instrument must be an exact TradingInstrumentIdentity")
        instrument = _reconstruct_instrument(self.instrument)
        object.__setattr__(
            self,
            "instrument",
            instrument,
        )
        if type(self.timeframe) is not ResearchTimeframe:
            raise TypeError("timeframe must be an exact ResearchTimeframe")
        if self.timeframe is not ResearchTimeframe.DAILY:
            raise ValueError("timeframe must be 1d")
        if type(self.provider) is not str:
            raise TypeError("provider must be a string")
        provider = self.provider.strip().lower()
        if provider != _PROVIDER:
            raise ValueError("provider must be polygon")
        object.__setattr__(self, "provider", provider)
        if type(self.analysis_as_of) is not datetime:
            raise TypeError("analysis_as_of must be a datetime")
        if (
            self.analysis_as_of.tzinfo is None
            or self.analysis_as_of.utcoffset() is None
        ):
            raise ValueError("analysis_as_of must be timezone-aware")
        object.__setattr__(self, "analysis_as_of", self.analysis_as_of.astimezone(UTC))
        if type(self.profile) is not DailyTechnicalAnalysisProfile:
            raise TypeError("profile must be an exact DailyTechnicalAnalysisProfile")
        fixed_profile = construct_daily_technical_analysis_profile()
        try:
            self.profile._validate()
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError("profile must match the exact fixed v1 profile") from exc
        if self.profile.to_dict() != fixed_profile.to_dict():
            raise ValueError("profile must match the exact fixed v1 profile")
        object.__setattr__(self, "profile", fixed_profile)

    def _validate(self) -> None:
        try:
            reconstructed = DailyTechnicalResearchRequest(
                instrument=self.instrument,
                timeframe=self.timeframe,
                provider=self.provider,
                analysis_as_of=self.analysis_as_of,
                profile=self.profile,
            )
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError(
                "retained daily technical research request is invalid"
            ) from exc
        if reconstructed._projection() != self._projection():
            raise ValueError(
                "retained daily technical research request is not canonical"
            )

    def _projection(self) -> dict[str, object]:
        return {
            "instrument": self.instrument.to_dict(),
            "timeframe": self.timeframe.value,
            "provider": self.provider,
            "analysis_as_of": self.analysis_as_of.isoformat(),
            "profile": self.profile.to_dict(),
        }

    def to_dict(self) -> dict[str, object]:
        self._validate()
        return self._projection()


@dataclass(frozen=True, slots=True, init=False)
class DailyTechnicalResearchResult:
    request: DailyTechnicalResearchRequest
    snapshot: TechnicalAnalysisSnapshot

    def __init__(self) -> None:
        raise TypeError("DailyTechnicalResearchResult is workflow-owned")

    @classmethod
    def _create(
        cls,
        *,
        request: DailyTechnicalResearchRequest,
        snapshot: TechnicalAnalysisSnapshot,
        seal: object,
    ) -> DailyTechnicalResearchResult:
        if seal is not _RESULT_SEAL:
            raise TypeError("daily technical research result construction is private")
        result = object.__new__(cls)
        object.__setattr__(result, "request", request)
        object.__setattr__(result, "snapshot", snapshot)
        result._validate()
        return result

    def _validate(self) -> None:
        try:
            request = self.request
            snapshot = self.snapshot
        except AttributeError as exc:
            raise ValueError("result retained state is incomplete") from exc
        if type(request) is not DailyTechnicalResearchRequest:
            raise ValueError("result request is invalid")
        request._validate()
        if type(snapshot) is not TechnicalAnalysisSnapshot:
            raise ValueError("result snapshot is invalid")
        try:
            snapshot._validate()
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError("result snapshot is invalid") from exc
        evidence = snapshot.evidence
        if request.instrument != evidence.instrument:
            raise ValueError("request instrument does not match snapshot evidence")
        if request.timeframe is not evidence.timeframe:
            raise ValueError("request timeframe does not match snapshot evidence")
        if request.analysis_as_of != evidence.analysis_as_of:
            raise ValueError("request analysis_as_of does not match snapshot evidence")
        if request.profile.to_dict() != snapshot.profile.to_dict():
            raise ValueError("request profile does not match snapshot profile")
        if request.provider != evidence.provider or evidence.provider != _PROVIDER:
            raise ValueError("request provider does not match snapshot evidence")
        if evidence.adjustment_policy is not PriceAdjustmentPolicy.ADJUSTED:
            raise ValueError("snapshot evidence must use adjusted prices")

    def to_dict(self) -> dict[str, object]:
        self._validate()
        return {
            "request": self.request.to_dict(),
            "snapshot": self.snapshot.to_dict(),
        }


class DailyTechnicalResearchWorkflow:
    def __init__(self, market_data_service: MarketDataService) -> None:
        if type(market_data_service) is not MarketDataService:
            raise TypeError("market_data_service must be an exact MarketDataService")
        self._market_data_service = market_data_service

    async def run(
        self,
        request: DailyTechnicalResearchRequest,
    ) -> DailyTechnicalResearchResult:
        if type(request) is not DailyTechnicalResearchRequest:
            raise TypeError("request must be an exact DailyTechnicalResearchRequest")
        request._validate()
        prices = await _acquire_polygon_daily_prices(self._market_data_service, request)
        completed = prepare_completed_daily_price_series(
            prices=prices,
            instrument=request.instrument,
            timeframe=ResearchTimeframe.DAILY,
            session_scope=DailyAnalysisSessionScope.PROVIDER_DAILY_AGGREGATE,
            market_timezone=_MARKET_TIMEZONE,
            adjustment_policy=PriceAdjustmentPolicy.ADJUSTED,
            analysis_as_of=request.analysis_as_of,
        )
        snapshot = analyze_daily_technical_snapshot(
            completed_prices=completed,
            profile=request.profile,
        )
        return DailyTechnicalResearchResult._create(
            request=request,
            snapshot=snapshot,
            seal=_RESULT_SEAL,
        )


__all__ = [
    "DailyTechnicalResearchRequest",
    "DailyTechnicalResearchResult",
    "DailyTechnicalResearchWorkflow",
]


def _reconstruct_instrument(
    instrument: TradingInstrumentIdentity,
) -> TradingInstrumentIdentity:
    try:
        symbol = instrument.symbol
        venue = instrument.venue
        schema_version = instrument.schema_version
        fingerprint = instrument.instrument_fingerprint
        projection = instrument.to_dict()
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("instrument retained state is invalid") from exc
    if not all(
        type(value) is str for value in (symbol, venue, schema_version, fingerprint)
    ):
        raise ValueError("instrument retained state is invalid")
    try:
        reconstructed = TradingInstrumentIdentity(symbol, venue)
    except (TypeError, ValueError) as exc:
        raise ValueError("instrument retained state is invalid") from exc
    if projection != reconstructed.to_dict():
        raise ValueError("instrument does not match canonical reconstruction")
    return reconstructed


def _require_production_polygon_route(service: MarketDataService) -> None:
    if type(service) is not MarketDataService:
        raise DataProviderError(
            "adjusted research requires the production market data service"
        )
    try:
        policy = service._policy
        candidates = policy.candidates
    except AttributeError as exc:
        raise DataProviderError("production Polygon route cannot be attested") from exc
    if type(policy) is not ProviderSelectionPolicy:
        raise DataProviderError("production Polygon route cannot be attested")
    matches = [candidate for candidate in candidates if candidate.name == _PROVIDER]
    if len(matches) != 1 or type(matches[0]) is not ProviderCandidate:
        raise DataProviderError("production Polygon route cannot be attested")
    candidate = matches[0]
    if not candidate.enabled or type(candidate.provider) is not PolygonProvider:
        raise DataProviderError(
            "adjusted research requires the production PolygonProvider"
        )
    service_method = getattr(service.get_daily_prices, "__func__", None)
    provider_method = getattr(candidate.provider.get_daily_prices, "__func__", None)
    if service_method is not MarketDataService.get_daily_prices:
        raise DataProviderError(
            "production market data acquisition method cannot be attested"
        )
    if provider_method is not PolygonProvider.get_daily_prices:
        raise DataProviderError(
            "production Polygon acquisition method cannot be attested"
        )


async def _acquire_polygon_daily_prices(
    service: MarketDataService,
    request: DailyTechnicalResearchRequest,
) -> HistoricalPriceSeries:
    _require_production_polygon_route(service)
    end_date = request.analysis_as_of.astimezone(ZoneInfo(_MARKET_TIMEZONE)).date()
    start_date = end_date - timedelta(days=_LOOKBACK_CALENDAR_DAYS)
    frame = await service.get_daily_prices(
        symbol=request.instrument.symbol,
        start=start_date,
        end=end_date,
        provider=_PROVIDER,
    )
    if "provider" not in frame.columns or not all(
        type(value) is str and value == _PROVIDER for value in frame["provider"]
    ):
        raise DataProviderError("daily price provider identity must be polygon")
    try:
        return HistoricalPriceSeries(
            frame, symbol=request.instrument.symbol, provider=_PROVIDER
        )
    except (TypeError, ValueError) as exc:
        raise DataProviderError("Polygon daily price rows are invalid") from exc
