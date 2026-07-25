"""Historical point-in-time replay service."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from market_platform.data.historical import HistoricalPriceSeries
from market_platform.observation.history import (
    build_historical_market_observation_from_prefix,
)
from market_platform.replay.models import (
    HistoricalReplayResult,
    HistoricalReplayStep,
    ReplayStrategyIdentity,
)
from market_platform.replay.specification import HistoricalReplaySpecification
from market_platform.signals.service import precompute_market_signal_snapshots
from market_platform.state.models import MarketState
from market_platform.state.protocol import MarketStateModel
from market_platform.strategy.collection import StrategyCollection
from market_platform.strategy.instance import StrategyInstance, get_strategy_provenance
from market_platform.strategy.runner import StrategyRunner
from market_platform.structure.models import PriceStructureSnapshot
from market_platform.structure.precompute import precompute_price_structure_snapshots
from market_platform.structure.service import PriceStructureService


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

        _validate_execution_inputs(strategies, state_model)
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

        series = _build_historical_price_series(prices, normalized_symbol)
        return self._run_canonical_series(
            series,
            interval=normalized_interval,
            strategies=strategies,
            state_model=state_model,
            start=normalized_start,
            end=normalized_end,
        )

    def run_with_specification(
        self,
        prices: pd.DataFrame,
        specification: HistoricalReplaySpecification,
        *,
        strategies: StrategyCollection,
        state_model: MarketStateModel,
    ) -> HistoricalReplayResult:
        """Replay retained context within an explicit evaluation window."""

        if not isinstance(specification, HistoricalReplaySpecification):
            raise TypeError(
                "specification must be a HistoricalReplaySpecification"
            )
        _validate_execution_inputs(strategies, state_model)
        context_prices = _filter_specification_context(prices, specification)
        if not prices.empty and context_prices.empty:
            raise ValueError("no replay timestamps found in requested range")
        series = _build_historical_price_series(
            context_prices,
            specification.symbol,
        )
        return self._run_canonical_series(
            series,
            interval=specification.interval,
            strategies=strategies,
            state_model=state_model,
            start=specification.evaluation_start,
            end=specification.evaluation_end,
        )

    def _run_canonical_series(
        self,
        series: HistoricalPriceSeries,
        *,
        interval: str,
        strategies: StrategyCollection,
        state_model: MarketStateModel,
        start: datetime | None,
        end: datetime | None,
    ) -> HistoricalReplayResult:
        replay_positions = _replay_positions(series, start=start, end=end)
        if not replay_positions:
            raise ValueError("no replay timestamps found in requested range")

        full_prices = series.to_dataframe()
        signal_snapshots = precompute_market_signal_snapshots(full_prices)
        structure_snapshots = _precompute_default_structure_snapshots(
            self._price_structure_service,
            full_prices,
        )
        strategy_identities = _strategy_identities(strategies)
        steps: list[HistoricalReplayStep] = []
        for position in replay_positions:
            prefix = series.prefix_at(position)
            as_of = prefix.as_of
            signal_snapshot = signal_snapshots[position]
            structure_snapshot = (
                structure_snapshots[position]
                if structure_snapshots is not None
                else self._price_structure_service.analyze(
                    prefix.to_dataframe(),
                    as_of=as_of,
                )
            )
            observation = build_historical_market_observation_from_prefix(
                prefix,
                symbol=series.symbol,
                interval=interval,
                as_of=as_of,
                provider=series.provider,
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
                    symbol=series.symbol,
                    interval=interval,
                    as_of=as_of,
                    observation_fingerprint=observation.provenance.input_fingerprint,
                    state=state,
                    strategy_result=strategy_result,
                )
            )

        step_tuple = tuple(steps)
        return HistoricalReplayResult(
            symbol=series.symbol,
            interval=interval,
            start_as_of=step_tuple[0].as_of,
            end_as_of=step_tuple[-1].as_of,
            steps=step_tuple,
            state_model_id=state_model.model_id,
            state_model_version=state_model.model_version,
            strategies=strategy_identities,
        )


def _validate_execution_inputs(
    strategies: StrategyCollection,
    state_model: MarketStateModel,
) -> None:
    if not isinstance(strategies, StrategyCollection):
        raise TypeError("strategies must be a StrategyCollection")
    if not isinstance(state_model, MarketStateModel):
        raise TypeError("state_model must implement MarketStateModel")


def _filter_specification_context(
    prices: pd.DataFrame,
    specification: HistoricalReplaySpecification,
) -> pd.DataFrame:
    if not isinstance(prices, pd.DataFrame):
        raise TypeError("prices must be a pandas DataFrame")
    if "timestamp" not in prices.columns:
        return prices.copy(deep=True)

    retained = prices.copy(deep=True)
    timestamps: list[pd.Timestamp] = []
    for value in retained["timestamp"]:
        timestamp = pd.Timestamp(value)
        if pd.isna(timestamp):
            raise ValueError("timestamp values must not be missing")
        if timestamp.tzinfo is None:
            raise ValueError("timestamp values must be timezone-aware")
        timestamps.append(timestamp.tz_convert(UTC))
    retained["timestamp"] = pd.Series(
        timestamps,
        index=retained.index,
        dtype="datetime64[ns, UTC]",
    )
    mask = (retained["timestamp"] >= specification.context_start) & (
        retained["timestamp"] <= specification.evaluation_end
    )
    return retained.loc[mask].copy(deep=True).reset_index(drop=True)


def _build_historical_price_series(
    prices: pd.DataFrame,
    symbol: str,
) -> HistoricalPriceSeries:
    return HistoricalPriceSeries(prices, symbol=symbol)


def _precompute_default_structure_snapshots(
    service: PriceStructureService,
    prices: pd.DataFrame,
) -> tuple[PriceStructureSnapshot, ...] | None:
    if not service._uses_default_components():
        return None
    return precompute_price_structure_snapshots(prices)


def _replay_positions(
    series: HistoricalPriceSeries,
    *,
    start: datetime | None,
    end: datetime | None,
) -> tuple[int, ...]:
    positions: list[int] = []
    for position in range(len(series)):
        as_of = series.timestamp_at(position)
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


def _normalize_symbol(value: object) -> str:
    return _normalize_required_text(value, "symbol").upper()


def _normalize_required_text(value: object, field_name: str) -> str:
    if isinstance(value, bool) or not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text


def _normalize_optional_timestamp(value: object, field_name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime or None")
    if value.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


__all__ = ["HistoricalReplayService"]
