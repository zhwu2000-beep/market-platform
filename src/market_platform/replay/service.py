"""Historical point-in-time replay service."""

from __future__ import annotations

import math
from datetime import UTC, datetime

import pandas as pd

from market_platform.observation.history import build_historical_market_observation
from market_platform.replay.models import (
    HistoricalReplayResult,
    HistoricalReplayStep,
    ReplayStrategyIdentity,
)
from market_platform.signals.service import precompute_market_signal_snapshots
from market_platform.state.models import MarketState
from market_platform.state.protocol import MarketStateModel
from market_platform.strategy.collection import StrategyCollection
from market_platform.strategy.instance import StrategyInstance, get_strategy_provenance
from market_platform.strategy.runner import StrategyRunner
from market_platform.structure.models import PriceStructureSnapshot
from market_platform.structure.precompute import precompute_price_structure_snapshots
from market_platform.structure.service import PriceStructureService

_PRICE_COLUMNS = (
    "symbol",
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "provider",
)


class HistoricalReplayService:
    """Replay state and strategy evaluations across historical price bars."""

    def __init__(
        self,
        *,
        price_structure_service: PriceStructureService | None = None,
        strategy_runner: StrategyRunner | None = None,
    ) -> None:
        self._price_structure_service = (
            PriceStructureService()
            if price_structure_service is None
            else price_structure_service
        )
        self._strategy_runner = (
            StrategyRunner() if strategy_runner is None else strategy_runner
        )

    def run(
        self,
        prices: pd.DataFrame,
        *,
        symbol: str,
        interval: str,
        strategies: StrategyCollection,
        state_model: MarketStateModel,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> HistoricalReplayResult:
        """Replay each historical bar in the inclusive start/end range."""

        if not isinstance(strategies, StrategyCollection):
            raise TypeError("strategies must be a StrategyCollection")
        if not isinstance(state_model, MarketStateModel):
            raise TypeError("state_model must implement MarketStateModel")
        normalized_symbol = _normalize_symbol(symbol)
        normalized_interval = _normalize_required_text(interval, "interval")
        normalized_start = _normalize_optional_timestamp(start, "start")
        normalized_end = _normalize_optional_timestamp(end, "end")
        if (
            normalized_start is not None
            and normalized_end is not None
            and normalized_start > normalized_end
        ):
            raise ValueError("start must be earlier than or equal to end")

        normalized = _normalize_replay_prices(prices, normalized_symbol)
        provider = _single_provider(normalized)
        replay_positions = _replay_positions(
            normalized,
            start=normalized_start,
            end=normalized_end,
        )
        if not replay_positions:
            raise ValueError("no replay timestamps found in requested range")

        signal_snapshots = precompute_market_signal_snapshots(normalized)
        structure_snapshots = _precompute_default_structure_snapshots(
            self._price_structure_service,
            normalized,
        )
        strategy_identities = _strategy_identities(strategies)
        steps: list[HistoricalReplayStep] = []
        for position in replay_positions:
            prefix = _copy_replay_prefix(normalized, position)
            as_of = _to_datetime(normalized.iloc[position]["timestamp"])
            signal_snapshot = signal_snapshots[position]
            structure_snapshot = (
                structure_snapshots[position]
                if structure_snapshots is not None
                else self._price_structure_service.analyze(prefix, as_of=as_of)
            )
            observation = build_historical_market_observation(
                prefix,
                symbol=normalized_symbol,
                interval=normalized_interval,
                as_of=as_of,
                provider=provider,
                signal_snapshot=signal_snapshot,
                structure_snapshot=structure_snapshot,
            )
            state = state_model.evaluate(observation)
            _validate_state_model_output(state, state_model)
            strategy_result = self._strategy_runner.evaluate(
                strategies.strategies,
                observation=observation,
                state=state,
            )
            steps.append(
                HistoricalReplayStep(
                    symbol=normalized_symbol,
                    interval=normalized_interval,
                    as_of=as_of,
                    observation_fingerprint=observation.provenance.input_fingerprint,
                    state=state,
                    strategy_result=strategy_result,
                )
            )

        step_tuple = tuple(steps)
        return HistoricalReplayResult(
            symbol=normalized_symbol,
            interval=normalized_interval,
            start_as_of=step_tuple[0].as_of,
            end_as_of=step_tuple[-1].as_of,
            steps=step_tuple,
            state_model_id=state_model.model_id,
            state_model_version=state_model.model_version,
            strategies=strategy_identities,
        )


def _precompute_default_structure_snapshots(
    service: PriceStructureService,
    prices: pd.DataFrame,
) -> tuple[PriceStructureSnapshot, ...] | None:
    if not service._uses_default_components():
        return None
    return precompute_price_structure_snapshots(prices)


def _copy_replay_prefix(prices: pd.DataFrame, position: int) -> pd.DataFrame:
    return prices.iloc[: position + 1].copy(deep=True)


def _normalize_replay_prices(prices: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if not isinstance(prices, pd.DataFrame):
        raise TypeError("prices must be a pandas DataFrame")
    if prices.empty:
        raise ValueError("prices must not be empty")
    missing = [column for column in _PRICE_COLUMNS if column not in prices.columns]
    if missing:
        raise ValueError("prices missing required columns: " + ", ".join(missing))

    normalized = prices.loc[:, list(_PRICE_COLUMNS)].copy()
    normalized["symbol"] = _normalize_text_series(normalized["symbol"], "symbol")
    normalized["provider"] = _normalize_text_series(normalized["provider"], "provider")
    if set(normalized["symbol"].astype("string")) != {symbol}:
        raise ValueError("prices must contain exactly one matching symbol")
    if len(set(normalized["provider"].astype("string"))) != 1:
        raise ValueError("prices must contain exactly one provider")
    normalized["timestamp"] = _normalize_aware_timestamp_series(normalized["timestamp"])
    for column in ("open", "high", "low", "close", "volume"):
        normalized[column] = _normalize_numeric_series(normalized[column], column)
    if (normalized["high"] < normalized["low"]).any():
        raise ValueError("high must be greater than or equal to low")
    if (normalized[["open", "high", "low", "close"]] <= 0.0).any().any():
        raise ValueError("OHLC prices must be positive")
    if (normalized["volume"] < 0.0).any():
        raise ValueError("volume must not be negative")
    normalized = normalized.sort_values("timestamp", kind="stable", ignore_index=True)
    if normalized["timestamp"].duplicated().any():
        raise ValueError("prices must not contain duplicate timestamps")
    return normalized


def _replay_positions(
    prices: pd.DataFrame,
    *,
    start: datetime | None,
    end: datetime | None,
) -> tuple[int, ...]:
    positions: list[int] = []
    for position, timestamp in enumerate(prices["timestamp"]):
        as_of = _to_datetime(timestamp)
        if start is not None and as_of < start:
            continue
        if end is not None and as_of > end:
            continue
        positions.append(position)
    return tuple(positions)


def _strategy_identities(
    strategies: StrategyCollection,
) -> tuple[ReplayStrategyIdentity, ...]:
    identities: list[ReplayStrategyIdentity] = []
    for strategy in strategies.strategies:
        configuration_fingerprint = None
        if isinstance(strategy, StrategyInstance):
            configuration_fingerprint = get_strategy_provenance(
                strategy
            ).configuration_fingerprint
        identities.append(
            ReplayStrategyIdentity(
                strategy_id=strategy.strategy_id,
                strategy_version=strategy.strategy_version,
                configuration_fingerprint=configuration_fingerprint,
            )
        )
    return tuple(identities)


def _validate_state_model_output(
    state: MarketState, state_model: MarketStateModel
) -> None:
    if not isinstance(state, MarketState):
        raise TypeError("state_model must return a MarketState")
    if state.provenance.model_id != state_model.model_id:
        raise ValueError("state model output model_id must match injected state_model")
    if state.provenance.model_version != state_model.model_version:
        raise ValueError(
            "state model output model_version must match injected state_model"
        )


def _single_provider(prices: pd.DataFrame) -> str:
    providers = tuple(str(provider) for provider in prices["provider"].unique())
    if len(providers) != 1:
        raise ValueError("prices must contain exactly one provider")
    return providers[0]


def _normalize_symbol(value: object) -> str:
    return _normalize_required_text(value, "symbol").upper()


def _normalize_required_text(value: object, field_name: str) -> str:
    if isinstance(value, bool) or not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text


def _normalize_text_series(series: pd.Series, field_name: str) -> pd.Series:
    if series.isna().any():
        raise ValueError(f"{field_name} must not contain missing values")
    normalized = series.map(lambda item: _normalize_required_text(item, field_name))
    if field_name == "symbol":
        normalized = normalized.map(str.upper)
    return normalized.astype("string")


def _normalize_aware_timestamp_series(series: pd.Series) -> pd.Series:
    values: list[pd.Timestamp] = []
    for item in series:
        timestamp = pd.Timestamp(item)
        if pd.isna(timestamp):
            raise ValueError("timestamp must not contain missing values")
        if timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        values.append(timestamp.tz_convert(UTC))
    return pd.Series(values, index=series.index, dtype="datetime64[ns, UTC]")


def _normalize_numeric_series(series: pd.Series, field_name: str) -> pd.Series:
    if series.map(lambda value: isinstance(value, bool)).any():
        raise TypeError(f"{field_name} must be numeric")
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.isna().any():
        raise ValueError(f"{field_name} must not contain invalid values")
    if not numeric.map(math.isfinite).all():
        raise ValueError(f"{field_name} must be finite")
    return numeric.astype(float)


def _normalize_optional_timestamp(value: object, field_name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime or None")
    if value.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _to_datetime(value: object) -> datetime:
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime().astimezone(UTC)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        return value.astimezone(UTC)
    raise TypeError("timestamp must be a datetime")


__all__ = ["HistoricalReplayService"]
