"""Synchronous single-symbol Polygon Radar composition, without trade authority."""

import asyncio
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from market_platform.application.instrument_mapping_codec import (
    load_trusted_instrument_mapping_registry,
)
from market_platform.config import get_settings
from market_platform.data.http import create_http_client
from market_platform.data.providers.polygon import (
    PolygonCompletedDailyAcquisition,
    PolygonProvider,
)
from market_platform.instruments.identity import CanonicalInstrument
from market_platform.logging import get_logger
from market_platform.radar.application import (
    RadarApplicationResult,
    RadarApplicationService,
)
from market_platform.radar.calendar import ExchangeCalendarsSessionCalendar
from market_platform.radar.checkpoint_store import RadarCheckpointFileStore
from market_platform.radar.core import RadarProfile
from market_platform.radar.current_content import bind_completed_daily_current_content
from market_platform.radar.ema_relation import (
    EMA8_EMA20_RELATION_KEY,
    RadarEma8Ema20RelationGate,
)
from market_platform.radar.resolver import RadarGateFactoryBinding, RadarGateResolver
from market_platform.radar.trigger import (
    SESSION_CONTENT_TRIGGER_KEY,
    RadarSessionContentTriggerGate,
)
from market_platform.trading import TradingInstrumentIdentity


class RadarSingleSymbolError(RuntimeError):
    """Invalid synchronous runtime or ambiguous production selection."""


@dataclass(frozen=True, slots=True)
class RadarSingleSymbolResponse:
    canonical_instrument: CanonicalInstrument
    application: RadarApplicationResult

    def __post_init__(self) -> None:
        if type(self.canonical_instrument) is not CanonicalInstrument:
            raise TypeError("canonical_instrument must be a CanonicalInstrument")
        if type(self.application) is not RadarApplicationResult:
            raise TypeError("application must be a RadarApplicationResult")
        instrument = self.canonical_instrument.instrument_id
        if instrument != self.application.pipeline_result.instrument:
            raise ValueError("canonical instrument must match pipeline instrument")
        checkpoint = self.application.saved_checkpoint
        if checkpoint is not None and checkpoint.instrument != instrument:
            raise ValueError(
                "saved checkpoint instrument must match canonical instrument"
            )

    def to_dict(self) -> dict[str, object]:
        """Project passive identities and actual results, never exception text."""
        pipeline = self.application.pipeline_result
        terminating = pipeline.terminating_occurrence
        failure = pipeline.failure
        checkpoint = self.application.saved_checkpoint
        return {
            "canonical_instrument": self.canonical_instrument.to_dict(),
            "application": {
                "pipeline": {
                    "profile": pipeline.profile.to_dict(),
                    "instrument": pipeline.instrument.to_dict(),
                    "as_of": pipeline.as_of.isoformat(),
                    "outcome": pipeline.outcome.value,
                    "executed_results": [
                        {
                            "occurrence": result.occurrence.to_dict(),
                            "disposition": result.disposition.value,
                            "reason_code": result.reason_code,
                        }
                        for result in pipeline.executed_results
                    ],
                    "terminating_occurrence": (
                        None if terminating is None else terminating.to_dict()
                    ),
                    "failure": None
                    if failure is None
                    else {
                        "occurrence": failure.occurrence.to_dict(),
                        "category": failure.category.value,
                    },
                },
                "checkpoint_advancement": self.application.advancement.value,
                "saved_checkpoint": None
                if checkpoint is None
                else checkpoint.to_dict(),
            },
        }


def _completion_clock() -> datetime:
    return datetime.now(UTC)


def run_single_symbol_radar(
    *,
    symbol: str,
    as_of: datetime,
    profile: RadarProfile,
    instrument_mappings_path: Path,
    checkpoint_root: Path,
) -> RadarSingleSymbolResponse:
    """Execute one explicit Profile; caller prevents overlapping instrument runs."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise RadarSingleSymbolError(
            "Single-symbol Radar requires a thread without a running asyncio event loop"
        )
    if not isinstance(as_of, datetime):
        raise TypeError("as_of must be a datetime")
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    if not instrument_mappings_path.is_absolute():
        raise RadarSingleSymbolError("trusted mapping path must be absolute")
    registry = load_trusted_instrument_mapping_registry(instrument_mappings_path)
    selector = TradingInstrumentIdentity(symbol, "NASDAQ").symbol
    matches = [
        item
        for item in registry.instruments
        if item.trading_identity.symbol == selector
    ]
    if not matches:
        raise RadarSingleSymbolError("Canonical trading symbol was not found")
    if len(matches) != 1:
        raise RadarSingleSymbolError("Canonical trading symbol is ambiguous")
    instrument = matches[0]
    if instrument.trading_identity.venue != "NASDAQ":
        raise RadarSingleSymbolError("Single-symbol Radar requires NASDAQ")
    mappings = registry.mappings
    identities = {
        mapping.external_identity
        for mapping in mappings
        if mapping.canonical_instrument.instrument_id == instrument.instrument_id
        and mapping.external_identity.namespace == "polygon"
    }
    if not identities:
        raise RadarSingleSymbolError("Trusted Polygon identity was not found")
    if len(identities) != 1:
        raise RadarSingleSymbolError("Trusted Polygon identity is ambiguous")
    external_identity = next(iter(identities))
    calendar = ExchangeCalendarsSessionCalendar()
    checkpoint_store = RadarCheckpointFileStore(checkpoint_root)
    resolver = RadarGateResolver(
        (
            RadarGateFactoryBinding(
                SESSION_CONTENT_TRIGGER_KEY,
                lambda occurrence: RadarSessionContentTriggerGate(occurrence, calendar),
            ),
            RadarGateFactoryBinding(
                EMA8_EMA20_RELATION_KEY, RadarEma8Ema20RelationGate
            ),
        )
    )
    settings = get_settings()
    client = create_http_client()
    try:
        provider = PolygonProvider(http_client=client, api_key=settings.polygon_api_key)

        def acquire(
            ticker: str, start: date, end: date
        ) -> PolygonCompletedDailyAcquisition:
            return asyncio.run(
                provider.get_completed_daily_acquisition(ticker, start, end)
            )

        loaders = bind_completed_daily_current_content(
            instrument=instrument.instrument_id,
            as_of=as_of,
            calendar=calendar,
            external_identity=external_identity,
            mappings=mappings,
            acquire_completed_daily=acquire,
        )
        service = RadarApplicationService(resolver, checkpoint_store, _completion_clock)
        result = service.evaluate(profile, instrument.instrument_id, as_of, loaders)
        return RadarSingleSymbolResponse(instrument, result)
    finally:
        try:
            client.close()
        except Exception:
            # Best-effort cleanup must preserve the completed result/original error.
            get_logger(__name__).warning("Radar owned HTTP client cleanup failed")
