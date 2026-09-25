"""Sequential caller-owned Radar orchestration, without investment authority."""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from market_platform.application.radar_single_symbol import (
    RadarSingleSymbolResponse,
    run_single_symbol_radar,
)
from market_platform.radar.application import RadarCheckpointAdvancementError
from market_platform.radar.core import RadarProfile
from market_platform.radar.pipeline import RadarPipelineResult
from market_platform.trading import TradingInstrumentIdentity


def _utc_as_of(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("as_of must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    utc = value.astimezone(UTC)
    return datetime(
        utc.year,
        utc.month,
        utc.day,
        utc.hour,
        utc.minute,
        utc.second,
        utc.microsecond,
        tzinfo=UTC,
    )


def _symbol(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("symbol must be a string")
    return TradingInstrumentIdentity(value, "NASDAQ").symbol


class RadarBatchFailureCategory(StrEnum):
    EXECUTION_ERROR = "EXECUTION_ERROR"
    CHECKPOINT_SAVE_FAILED = "CHECKPOINT_SAVE_FAILED"


@dataclass(frozen=True, slots=True)
class RadarBatchFailure:
    category: RadarBatchFailureCategory
    pipeline_result: RadarPipelineResult | None = None

    def __post_init__(self) -> None:
        if type(self.category) is not RadarBatchFailureCategory:
            raise TypeError("category must be RadarBatchFailureCategory")
        if (
            self.pipeline_result is not None
            and type(self.pipeline_result) is not RadarPipelineResult
        ):
            raise TypeError("pipeline_result must be a RadarPipelineResult or None")
        if self.category is RadarBatchFailureCategory.EXECUTION_ERROR:
            if self.pipeline_result is not None:
                raise ValueError("EXECUTION_ERROR forbids a Pipeline result")
        elif self.pipeline_result is None:
            raise ValueError("CHECKPOINT_SAVE_FAILED requires a Pipeline result")

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {"category": self.category.value}
        if self.pipeline_result is not None:
            result["pipeline"] = _pipeline_projection(self.pipeline_result)
        return result


@dataclass(frozen=True, slots=True)
class RadarBatchItemResult:
    symbol: str
    response: RadarSingleSymbolResponse | None = None
    failure: RadarBatchFailure | None = None

    def __post_init__(self) -> None:
        if type(self.symbol) is not str:
            raise TypeError("item symbol must be a string")
        if _symbol(self.symbol) != self.symbol:
            raise ValueError("item symbol must be normalized")
        if (
            self.response is not None
            and type(self.response) is not RadarSingleSymbolResponse
        ):
            raise TypeError("response must be a RadarSingleSymbolResponse or None")
        if self.failure is not None and type(self.failure) is not RadarBatchFailure:
            raise TypeError("failure must be a RadarBatchFailure or None")
        if (self.response is None) == (self.failure is None):
            raise ValueError("item requires exactly one response or failure")
        if (
            self.response is not None
            and self.symbol
            != self.response.canonical_instrument.trading_identity.symbol
        ):
            raise ValueError("item symbol must match canonical response symbol")

    def to_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "response": None if self.response is None else self.response.to_dict(),
            "failure": None if self.failure is None else self.failure.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class RadarBatchResponse:
    profile: RadarProfile
    as_of: datetime
    items: tuple[RadarBatchItemResult, ...]

    def __post_init__(self) -> None:
        if type(self.profile) is not RadarProfile:
            raise TypeError("profile must be a RadarProfile")
        object.__setattr__(self, "as_of", _utc_as_of(self.as_of))
        if type(self.items) not in (tuple, list):
            raise TypeError("items must be a tuple or list")
        items = tuple(self.items)
        if not items:
            raise ValueError("items must not be empty")
        if any(type(item) is not RadarBatchItemResult for item in items):
            raise TypeError("items must contain RadarBatchItemResult values")
        if len({item.symbol for item in items}) != len(items):
            raise ValueError("items must not repeat symbols")
        for item in items:
            pipeline = None
            if item.response is not None:
                pipeline = item.response.application.pipeline_result
            elif item.failure is not None:
                pipeline = item.failure.pipeline_result
            if pipeline is not None:
                if pipeline.profile != self.profile:
                    raise ValueError("item Pipeline Profile must match batch Profile")
                if pipeline.as_of != self.as_of:
                    raise ValueError("item Pipeline as_of must match batch as_of")
        object.__setattr__(self, "items", items)

    def to_dict(self) -> dict[str, object]:
        return {
            "profile": self.profile.to_dict(),
            "as_of": self.as_of.isoformat(),
            "items": [item.to_dict() for item in self.items],
        }


def _pipeline_projection(pipeline: RadarPipelineResult) -> dict[str, object]:
    terminating = pipeline.terminating_occurrence
    failure = pipeline.failure
    return {
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
        "terminating_occurrence": None
        if terminating is None
        else terminating.to_dict(),
        "failure": None
        if failure is None
        else {
            "occurrence": failure.occurrence.to_dict(),
            "category": failure.category.value,
        },
    }


def run_radar_batch(
    *,
    symbols: tuple[str, ...] | list[str],
    as_of: datetime,
    profile: RadarProfile,
    instrument_mappings_path: Path,
    checkpoint_root: Path,
) -> RadarBatchResponse:
    """Run in caller order; caller prevents overlapping instrument evaluations."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise RuntimeError(
            "Radar batch requires a thread without a running asyncio event loop"
        )
    _utc_as_of(as_of)
    if type(profile) is not RadarProfile:
        raise TypeError("profile must be a RadarProfile")
    if type(symbols) not in (tuple, list):
        raise TypeError("symbols must be a tuple or list")
    snapshot = tuple(symbols)
    if not snapshot:
        raise ValueError("symbols must not be empty")
    normalized = tuple(_symbol(symbol) for symbol in snapshot)
    if len(set(normalized)) != len(normalized):
        raise ValueError("symbols must not repeat after normalization")
    for name, path in (
        ("instrument_mappings_path", instrument_mappings_path),
        ("checkpoint_root", checkpoint_root),
    ):
        if not isinstance(path, Path):
            raise TypeError(f"{name} must be a Path")
        if not path.is_absolute():
            raise ValueError(f"{name} must be absolute")
    items = []
    for symbol in normalized:
        try:
            response = run_single_symbol_radar(
                symbol=symbol,
                as_of=as_of,
                profile=profile,
                instrument_mappings_path=instrument_mappings_path,
                checkpoint_root=checkpoint_root,
            )
        except RadarCheckpointAdvancementError as error:
            item = RadarBatchItemResult(
                symbol,
                failure=RadarBatchFailure(
                    RadarBatchFailureCategory.CHECKPOINT_SAVE_FAILED,
                    error.pipeline_result,
                ),
            )
        except Exception:
            item = RadarBatchItemResult(
                symbol,
                failure=RadarBatchFailure(
                    RadarBatchFailureCategory.EXECUTION_ERROR,
                ),
            )
        else:
            item = RadarBatchItemResult(symbol, response=response)
        items.append(item)
    return RadarBatchResponse(profile, as_of, tuple(items))
