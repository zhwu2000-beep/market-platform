"""Benchmark historical replay production timing and attribution."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
import platform
import statistics
import sys
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter_ns
from typing import Any, cast

import pandas as pd

import market_platform.replay.service as replay_service
from market_platform.observation.models import MarketObservation
from market_platform.replay import (
    HistoricalReplayResult,
    HistoricalReplayService,
    summarize_historical_replay,
)
from market_platform.signals.models import MarketSignalSnapshot
from market_platform.state import BaselineMarketStateModel
from market_platform.state.models import MarketState
from market_platform.state.protocol import MarketStateModel
from market_platform.strategy import (
    BaselineTrendRegimeStrategy,
    BaselineVolatilityRegimeStrategy,
    Strategy,
    StrategyCollection,
    StrategyRunner,
    create_strategy_collection,
)
from market_platform.strategy.models import StrategyRunResult
from market_platform.structure import PriceStructureService
from market_platform.structure.models import (
    PriceStructureConfig,
    PriceStructureSnapshot,
)

SCHEMA_VERSION = "1.0.0"
_PRECOMPUTE_ATTR = "precompute_market_signal_snapshots"
_OBSERVATION_ATTR = "build_historical_market_observation"
DEFAULT_BARS = (100, 300, 500)
DEFAULT_RUNS = 3
DEFAULT_WARMUPS = 1
DEFAULT_SEED = 43
SYMBOL = "MSFT"
INTERVAL = "1day"
PROVIDER = "benchmark-provider"

SEGMENT_NAMES = (
    "price_normalization",
    "provider_extraction",
    "replay_position_selection",
    "signal_precompute",
    "strategy_identity_construction",
    "prefix_slicing_copy",
    "structure_analysis",
    "observation_construction",
    "state_evaluation",
    "strategy_runner_evaluation",
)

SERIALIZATION_ITEMS = (
    "result_to_dict",
    "result_json_dumps",
    "summary_build",
    "summary_to_dict",
    "summary_json_dumps",
)


def _median(values: Sequence[int]) -> int:
    if not values:
        return 0
    return int(statistics.median(values))


@dataclass(slots=True)
class TimingRecorder:
    """Collect cumulative segment timings for one instrumented replay run."""

    durations_ns: dict[str, list[int]] = field(default_factory=dict)
    structure_snapshots: list[PriceStructureSnapshot] = field(default_factory=list)

    @contextmanager
    def measure(self, segment: str) -> Iterator[None]:
        start = perf_counter_ns()
        try:
            yield
        finally:
            self.durations_ns.setdefault(segment, []).append(
                perf_counter_ns() - start
            )

    def total_ns(self, segment: str) -> int:
        return sum(self.durations_ns.get(segment, ()))

    def call_count(self, segment: str) -> int:
        return len(self.durations_ns.get(segment, ()))


@dataclass(frozen=True, slots=True)
class SegmentAggregate:
    name: str
    total_samples_ns: tuple[int, ...]
    median_total_ns: int
    call_count: int
    median_per_call_ns: int
    production_share: float
    instrumented_share: float

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "total_samples_ns": list(self.total_samples_ns),
            "median_total_ns": self.median_total_ns,
            "call_count": self.call_count,
            "median_per_call_ns": self.median_per_call_ns,
            "production_share": self.production_share,
            "instrumented_share": self.instrumented_share,
        }


@dataclass(frozen=True, slots=True)
class BenchmarkScenarioResult:
    bars: int
    step_count: int
    strategy_count: int
    production_samples_ns: tuple[int, ...]
    production_median_ns: int
    instrumented_samples_ns: tuple[int, ...]
    instrumented_median_ns: int
    overhead_ratio: float
    segments: tuple[SegmentAggregate, ...]
    residual_samples_ns: tuple[int, ...]
    residual_median_ns: int
    residual_production_share: float
    residual_instrumented_share: float
    serialization: dict[str, dict[str, object]]
    result_fingerprint: str
    stable_output_confirmed: bool
    structure_workload: Mapping[str, object]
    call_counts: dict[str, int]
    decision_inputs: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "bars": self.bars,
            "step_count": self.step_count,
            "strategy_count": self.strategy_count,
            "production_run": {
                "samples_ns": list(self.production_samples_ns),
                "median_ns": self.production_median_ns,
            },
            "instrumented_run": {
                "samples_ns": list(self.instrumented_samples_ns),
                "median_ns": self.instrumented_median_ns,
                "overhead_ratio": self.overhead_ratio,
            },
            "segments": [segment.to_dict() for segment in self.segments],
            "residual": {
                "samples_ns": list(self.residual_samples_ns),
                "median_ns": self.residual_median_ns,
                "production_share": self.residual_production_share,
                "instrumented_share": self.residual_instrumented_share,
                "meaning": (
                    "instrumented orchestration/model/residual after "
                    "measured segments"
                ),
            },
            "serialization": self.serialization,
            "result_fingerprint": self.result_fingerprint,
            "stable_output_confirmed": self.stable_output_confirmed,
            "structure_workload": dict(self.structure_workload),
            "call_counts": dict(self.call_counts),
            "decision_inputs": dict(self.decision_inputs),
        }


class TimedPriceStructureService:
    def __init__(self, inner: PriceStructureService, recorder: TimingRecorder) -> None:
        self._inner = inner
        self._recorder = recorder

    def analyze(
        self,
        prices: pd.DataFrame,
        *,
        config: PriceStructureConfig | None = None,
        current_price: float | None = None,
        as_of: datetime | None = None,
    ) -> PriceStructureSnapshot:
        with self._recorder.measure("structure_analysis"):
            snapshot = self._inner.analyze(
                prices,
                config=config,
                current_price=current_price,
                as_of=as_of,
            )
        self._recorder.structure_snapshots.append(snapshot)
        return snapshot


class TimedMarketStateModel:
    def __init__(self, inner: MarketStateModel, recorder: TimingRecorder) -> None:
        self._inner = inner
        self._recorder = recorder

    @property
    def model_id(self) -> str:
        return self._inner.model_id

    @property
    def model_version(self) -> str:
        return self._inner.model_version

    def evaluate(self, observation: MarketObservation) -> MarketState:
        with self._recorder.measure("state_evaluation"):
            return self._inner.evaluate(observation)


class TimedStrategyRunner:
    def __init__(self, inner: StrategyRunner, recorder: TimingRecorder) -> None:
        self._inner = inner
        self._recorder = recorder

    def evaluate(
        self,
        strategies: Sequence[Strategy],
        *,
        observation: MarketObservation,
        state: MarketState,
    ) -> StrategyRunResult:
        with self._recorder.measure("strategy_runner_evaluation"):
            return self._inner.evaluate(
                strategies,
                observation=observation,
                state=state,
            )


@contextmanager
def _patched_attribute(
    target: object,
    name: str,
    replacement: object,
) -> Iterator[None]:
    original = getattr(target, name)
    setattr(target, name, replacement)
    try:
        yield
    finally:
        setattr(target, name, original)


@contextmanager
def _instrument_replay_bindings(recorder: TimingRecorder) -> Iterator[None]:
    original_normalize = cast(Any, replay_service._normalize_replay_prices)
    original_provider = cast(Any, replay_service._single_provider)
    original_positions = cast(Any, replay_service._replay_positions)
    original_precompute = getattr(replay_service, _PRECOMPUTE_ATTR)
    original_identities = cast(Any, replay_service._strategy_identities)
    original_prefix = cast(Any, replay_service._copy_replay_prefix)
    original_observation = getattr(replay_service, _OBSERVATION_ATTR)


    def timed_normalize(prices: pd.DataFrame, symbol: str) -> pd.DataFrame:
        with recorder.measure("price_normalization"):
            return cast(pd.DataFrame, original_normalize(prices, symbol))

    def timed_provider(prices: pd.DataFrame) -> str:
        with recorder.measure("provider_extraction"):
            return cast(str, original_provider(prices))

    def timed_positions(
        prices: pd.DataFrame,
        *,
        start: datetime | None,
        end: datetime | None,
    ) -> tuple[int, ...]:
        with recorder.measure("replay_position_selection"):
            return cast(
                tuple[int, ...],
                original_positions(prices, start=start, end=end),
            )

    def timed_precompute(prices: pd.DataFrame) -> tuple[MarketSignalSnapshot, ...]:
        with recorder.measure("signal_precompute"):
            return cast(tuple[MarketSignalSnapshot, ...], original_precompute(prices))

    def timed_identities(strategies: StrategyCollection) -> object:
        with recorder.measure("strategy_identity_construction"):
            return original_identities(strategies)

    def timed_prefix(prices: pd.DataFrame, position: int) -> pd.DataFrame:
        with recorder.measure("prefix_slicing_copy"):
            return cast(pd.DataFrame, original_prefix(prices, position))

    def timed_observation(*args: object, **kwargs: object) -> MarketObservation:
        with recorder.measure("observation_construction"):
            return cast(MarketObservation, original_observation(*args, **kwargs))

    patches = (
        ("_normalize_replay_prices", timed_normalize),
        ("_single_provider", timed_provider),
        ("_replay_positions", timed_positions),
        (_PRECOMPUTE_ATTR, timed_precompute),
        ("_strategy_identities", timed_identities),
        ("_copy_replay_prefix", timed_prefix),
        (_OBSERVATION_ATTR, timed_observation),
    )
    with ExitStack() as stack:
        for name, replacement in patches:
            stack.enter_context(_patched_attribute(replay_service, name, replacement))
        yield


def build_price_frame(bars: int, *, seed: int = DEFAULT_SEED) -> pd.DataFrame:
    if bars <= 0:
        raise ValueError("bars must be positive")
    start = datetime(2026, 1, 1, tzinfo=UTC)
    rows: list[dict[str, object]] = []
    phase = (seed % 29) / 10.0
    for index in range(bars):
        trend = index * 0.08
        cycle = 3.8 * math.sin((index + phase) / 5.0)
        faster = 1.4 * math.sin((index + seed) / 2.0)
        close = 100.0 + trend + cycle + faster
        open_price = close - 0.25 * math.sin((index + seed) / 3.0)
        high = max(open_price, close) + 1.0 + (index % 5) * 0.04
        low = min(open_price, close) - 1.0 - (index % 7) * 0.03
        rows.append(
            {
                "symbol": SYMBOL,
                "timestamp": start + timedelta(days=index),
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "volume": 1_000_000.0 + float((index * 997 + seed) % 10_000),
                "provider": PROVIDER,
            }
        )
    return pd.DataFrame(rows)


def build_benchmark_frames(
    bars: Sequence[int],
    *,
    seed: int = DEFAULT_SEED,
) -> dict[int, pd.DataFrame]:
    _validate_bars(bars)
    max_frame = build_price_frame(max(bars), seed=seed)
    return {
        bar_count: _copy_benchmark_prefix(max_frame, bar_count)
        for bar_count in bars
    }


def _copy_benchmark_prefix(prices: pd.DataFrame, bars: int) -> pd.DataFrame:
    if bars <= 0:
        raise ValueError("bars must be positive")
    if bars > len(prices):
        raise ValueError("bars must not exceed generated frame length")
    return prices.iloc[:bars].copy(deep=True)


def _validate_bars(bars: Sequence[int]) -> None:
    if not bars:
        raise ValueError("at least one bars value is required")
    if any(value <= 0 for value in bars):
        raise ValueError("bars values must be positive")


def _collect_before_timing() -> None:
    gc.collect()


def default_strategies() -> StrategyCollection:
    return create_strategy_collection(
        (BaselineTrendRegimeStrategy(), BaselineVolatilityRegimeStrategy())
    )


def _run_replay(
    prices: pd.DataFrame,
    *,
    strategies: StrategyCollection | None = None,
    state_model: MarketStateModel | None = None,
    price_structure_service: (
        PriceStructureService | TimedPriceStructureService | None
    ) = None,
    strategy_runner: StrategyRunner | TimedStrategyRunner | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> HistoricalReplayResult:
    service = HistoricalReplayService(
        price_structure_service=cast(
            PriceStructureService | None,
            price_structure_service,
        ),
        strategy_runner=cast(StrategyRunner | None, strategy_runner),
    )
    return service.run(
        prices,
        symbol=SYMBOL,
        interval=INTERVAL,
        strategies=default_strategies() if strategies is None else strategies,
        state_model=BaselineMarketStateModel() if state_model is None else state_model,
        start=start,
        end=end,
    )


def _time_call[ResultT](call: Callable[[], ResultT]) -> tuple[ResultT, int]:
    start = perf_counter_ns()
    result = call()
    return result, perf_counter_ns() - start


def run_production_samples(
    prices: pd.DataFrame,
    *,
    runs: int,
    warmups: int,
    start: datetime | None = None,
    end: datetime | None = None,
) -> tuple[HistoricalReplayResult, tuple[int, ...]]:
    for _ in range(warmups):
        _collect_before_timing()
        _run_replay(prices, start=start, end=end)
    samples: list[int] = []
    result: HistoricalReplayResult | None = None
    for _ in range(runs):
        _collect_before_timing()
        result, elapsed_ns = _time_call(
            lambda: _run_replay(prices, start=start, end=end)
        )
        samples.append(elapsed_ns)
    if result is None:
        raise ValueError("runs must be positive")
    return result, tuple(samples)


def run_instrumented_samples(
    prices: pd.DataFrame,
    *,
    runs: int,
    warmups: int,
    strategies: StrategyCollection | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> tuple[HistoricalReplayResult, tuple[int, ...], tuple[TimingRecorder, ...]]:
    for _ in range(warmups):
        _collect_before_timing()
        _run_instrumented_replay(
            prices,
            strategies=strategies,
            start=start,
            end=end,
        )
    samples: list[int] = []
    recorders: list[TimingRecorder] = []
    result: HistoricalReplayResult | None = None
    for _ in range(runs):
        _collect_before_timing()
        recorder = TimingRecorder()

        def replay_once(
            active_recorder: TimingRecorder = recorder,
        ) -> HistoricalReplayResult:
            return _run_instrumented_replay(
                prices,
                recorder=active_recorder,
                strategies=strategies,
                start=start,
                end=end,
            )

        result, elapsed_ns = _time_call(replay_once)
        samples.append(elapsed_ns)
        recorders.append(recorder)
    if result is None:
        raise ValueError("runs must be positive")
    return result, tuple(samples), tuple(recorders)


def _run_instrumented_replay(
    prices: pd.DataFrame,
    *,
    recorder: TimingRecorder | None = None,
    strategies: StrategyCollection | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> HistoricalReplayResult:
    active_recorder = TimingRecorder() if recorder is None else recorder
    structure = TimedPriceStructureService(PriceStructureService(), active_recorder)
    state_model = TimedMarketStateModel(BaselineMarketStateModel(), active_recorder)
    runner = TimedStrategyRunner(StrategyRunner(), active_recorder)
    with _instrument_replay_bindings(active_recorder):
        return _run_replay(
            prices,
            strategies=strategies,
            state_model=state_model,
            price_structure_service=structure,
            strategy_runner=runner,
            start=start,
            end=end,
        )


def measure_serialization(
    result: HistoricalReplayResult,
    *,
    runs: int,
) -> dict[str, dict[str, object]]:
    if runs <= 0:
        raise ValueError("runs must be positive")
    result_dict = result.to_dict()
    result_json = json.dumps(result_dict, ensure_ascii=False, sort_keys=True)
    summary = summarize_historical_replay(result)
    summary_dict = summary.to_dict()
    summary_json = json.dumps(summary_dict, ensure_ascii=False, sort_keys=True)
    samples: dict[str, list[int]] = {name: [] for name in SERIALIZATION_ITEMS}
    stable = True
    for _ in range(runs):
        _collect_before_timing()
        produced_result_dict, elapsed = _time_call(result.to_dict)
        samples["result_to_dict"].append(elapsed)
        stable = stable and produced_result_dict == result_dict

        _collect_before_timing()
        produced_result_json, elapsed = _time_call(
            lambda: json.dumps(result_dict, ensure_ascii=False, sort_keys=True)
        )
        samples["result_json_dumps"].append(elapsed)
        stable = stable and produced_result_json == result_json

        _collect_before_timing()
        produced_summary, elapsed = _time_call(
            lambda: summarize_historical_replay(result)
        )
        samples["summary_build"].append(elapsed)
        stable = stable and produced_summary.to_dict() == summary_dict

        _collect_before_timing()
        produced_summary_dict, elapsed = _time_call(summary.to_dict)
        samples["summary_to_dict"].append(elapsed)
        stable = stable and produced_summary_dict == summary_dict

        _collect_before_timing()
        produced_summary_json, elapsed = _time_call(
            lambda: json.dumps(summary_dict, ensure_ascii=False, sort_keys=True)
        )
        samples["summary_json_dumps"].append(elapsed)
        stable = stable and produced_summary_json == summary_json

    return {
        name: {
            "samples_ns": values,
            "median_ns": _median(values),
            "stable_output_confirmed": stable,
        }
        for name, values in samples.items()
    }


def result_fingerprint(result: HistoricalReplayResult) -> str:
    payload = json.dumps(
        result.to_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def run_scenario(
    bars: int,
    *,
    runs: int,
    warmups: int,
    seed: int,
    prices: pd.DataFrame | None = None,
    start_position: int | None = None,
    end_position: int | None = None,
) -> BenchmarkScenarioResult:
    scenario_prices = build_price_frame(bars, seed=seed) if prices is None else prices
    start, end = _positions_to_timestamps(
        scenario_prices,
        start_position,
        end_position,
    )
    production_result, production_samples = run_production_samples(
        scenario_prices,
        runs=runs,
        warmups=warmups,
        start=start,
        end=end,
    )
    instrumented_result, instrumented_samples, recorders = run_instrumented_samples(
        scenario_prices,
        runs=runs,
        warmups=warmups,
        start=start,
        end=end,
    )
    production_dict = production_result.to_dict()
    instrumented_dict = instrumented_result.to_dict()
    if production_dict != instrumented_dict:
        raise AssertionError("instrumented replay output diverged from production")

    production_median = _median(production_samples)
    instrumented_median = _median(instrumented_samples)
    segments = _aggregate_segments(
        recorders,
        production_median_ns=production_median,
        instrumented_median_ns=instrumented_median,
    )
    residual_samples = tuple(
        max(0, total - sum(recorder.total_ns(segment) for segment in SEGMENT_NAMES))
        for total, recorder in zip(instrumented_samples, recorders, strict=True)
    )
    residual_median = _median(residual_samples)
    serialization = measure_serialization(production_result, runs=runs)
    call_counts = _call_counts(recorders, production_result)
    structure_share = _segment_share(segments, "structure_analysis")
    prefix_share = _segment_share(segments, "prefix_slicing_copy")
    observation_share = _segment_share(segments, "observation_construction")
    overhead_ratio = (
        instrumented_median / production_median if production_median else 0.0
    )
    decision_inputs: dict[str, object] = {
        "structure_production_share": structure_share,
        "prefix_copy_production_share": prefix_share,
        "observation_production_share": observation_share,
        "instrumentation_overhead_ratio": overhead_ratio,
        "step_count": production_result.step_count,
        "strategy_count": len(production_result.strategies),
    }
    stable_serialization = all(
        bool(item["stable_output_confirmed"]) for item in serialization.values()
    )
    return BenchmarkScenarioResult(
        bars=bars,
        step_count=production_result.step_count,
        strategy_count=len(production_result.strategies),
        production_samples_ns=production_samples,
        production_median_ns=production_median,
        instrumented_samples_ns=instrumented_samples,
        instrumented_median_ns=instrumented_median,
        overhead_ratio=overhead_ratio,
        segments=segments,
        residual_samples_ns=residual_samples,
        residual_median_ns=residual_median,
        residual_production_share=_share(residual_median, production_median),
        residual_instrumented_share=_share(residual_median, instrumented_median),
        serialization=serialization,
        result_fingerprint=result_fingerprint(production_result),
        stable_output_confirmed=stable_serialization,
        structure_workload=_structure_workload_stats(recorders),
        call_counts=call_counts,
        decision_inputs=decision_inputs,
    )


def run_benchmark(
    *,
    bars: Sequence[int],
    runs: int,
    warmups: int,
    seed: int,
    start_position: int | None = None,
    end_position: int | None = None,
    include_generated_at: bool = True,
) -> dict[str, object]:
    _validate_benchmark_args(bars=bars, runs=runs, warmups=warmups)
    scenario_frames = build_benchmark_frames(bars, seed=seed)
    scenarios = tuple(
        run_scenario(
            bar_count,
            runs=runs,
            warmups=warmups,
            seed=seed,
            prices=scenario_frames[bar_count],
            start_position=start_position,
            end_position=end_position,
        )
        for bar_count in bars
    )
    strategies = default_strategies().strategies
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "environment": _environment(),
        "configuration": {
            "bars": list(bars),
            "runs": runs,
            "warmups": warmups,
            "seed": seed,
            "data_generation": (
                "single max-bars deterministic frame; each scenario uses a "
                "deep-copied prefix"
            ),
            "gc_policy": "gc.collect() before every warm-up and measured timing",
            "strategy_ids_versions": [
                {
                    "strategy_id": strategy.strategy_id,
                    "strategy_version": strategy.strategy_version,
                }
                for strategy in strategies
            ],
            "start_position": start_position,
            "end_position": end_position,
        },
        "scenarios": [scenario.to_dict() for scenario in scenarios],
        "decision_inputs": _overall_decision_inputs(scenarios),
    }
    payload["generated_at"] = (
        datetime.now(UTC).isoformat() if include_generated_at else None
    )
    return payload


def _aggregate_segments(
    recorders: Sequence[TimingRecorder],
    *,
    production_median_ns: int,
    instrumented_median_ns: int,
) -> tuple[SegmentAggregate, ...]:
    aggregates: list[SegmentAggregate] = []
    for name in SEGMENT_NAMES:
        total_samples = tuple(recorder.total_ns(name) for recorder in recorders)
        call_counts = [recorder.call_count(name) for recorder in recorders]
        median_total = _median(total_samples)
        median_call_count = int(statistics.median(call_counts)) if call_counts else 0
        median_per_call = median_total // median_call_count if median_call_count else 0
        aggregates.append(
            SegmentAggregate(
                name=name,
                total_samples_ns=total_samples,
                median_total_ns=median_total,
                call_count=median_call_count,
                median_per_call_ns=median_per_call,
                production_share=_share(median_total, production_median_ns),
                instrumented_share=_share(median_total, instrumented_median_ns),
            )
        )
    return tuple(aggregates)


def _structure_workload_stats(
    recorders: Sequence[TimingRecorder],
) -> dict[str, object]:
    snapshots = recorders[0].structure_snapshots if recorders else []
    status_counts: dict[str, int] = {}
    total_candidate_count = 0
    total_observed_zone_count = 0
    total_independent_zone_touches = 0
    for snapshot in snapshots:
        status = snapshot.status.value
        status_counts[status] = status_counts.get(status, 0) + 1
        total_candidate_count += len(snapshot.candidates)
        total_observed_zone_count += len(snapshot.observed_zones)
        total_independent_zone_touches += sum(
            observed.observation.touch_count
            for observed in snapshot.observed_zones
        )
    final_snapshot = snapshots[-1] if snapshots else None
    return {
        "source": (
            "first measured instrumented run PriceStructureSnapshot returns; "
            "no extra structure analysis executed"
        ),
        "step_count": len(snapshots),
        "structure_available_step_count": status_counts.get("ok", 0),
        "status_counts": status_counts,
        "total_candidate_count": total_candidate_count,
        "final_candidate_count": (
            len(final_snapshot.candidates) if final_snapshot is not None else 0
        ),
        "total_observed_zone_count": total_observed_zone_count,
        "final_observed_zone_count": (
            len(final_snapshot.observed_zones) if final_snapshot is not None else 0
        ),
        "total_independent_zone_touches": total_independent_zone_touches,
    }


def _call_counts(
    recorders: Sequence[TimingRecorder],
    result: HistoricalReplayResult,
) -> dict[str, int]:
    counts = {
        name: int(
            statistics.median(
                [recorder.call_count(name) for recorder in recorders]
            )
        )
        for name in SEGMENT_NAMES
    }
    counts["strategy_evaluations"] = result.step_count * len(result.strategies)
    return counts


def _segment_share(segments: Sequence[SegmentAggregate], name: str) -> float:
    for segment in segments:
        if segment.name == name:
            return segment.production_share
    return 0.0


def _share(part: int, whole: int) -> float:
    if whole <= 0:
        return 0.0
    return part / whole


def _positions_to_timestamps(
    prices: pd.DataFrame,
    start_position: int | None,
    end_position: int | None,
) -> tuple[datetime | None, datetime | None]:
    if start_position is None and end_position is None:
        return None, None
    max_position = len(prices) - 1
    if start_position is not None and not 0 <= start_position <= max_position:
        raise ValueError("start_position must be within generated bars")
    if end_position is not None and not 0 <= end_position <= max_position:
        raise ValueError("end_position must be within generated bars")
    if (
        start_position is not None
        and end_position is not None
        and start_position > end_position
    ):
        raise ValueError("start_position must be earlier than or equal to end_position")
    start = None
    end = None
    if start_position is not None:
        start_timestamp = cast(pd.Timestamp, prices.iloc[start_position]["timestamp"])
        start = start_timestamp.to_pydatetime()
    if end_position is not None:
        end_timestamp = cast(pd.Timestamp, prices.iloc[end_position]["timestamp"])
        end = end_timestamp.to_pydatetime()
    return start, end


def _environment() -> dict[str, str]:
    return {
        "python_version": sys.version.split()[0],
        "pandas_version": pd.__version__,
        "platform": platform.platform(),
    }


def _overall_decision_inputs(
    scenarios: Sequence[BenchmarkScenarioResult],
) -> dict[str, object]:
    largest = max(scenarios, key=lambda scenario: scenario.bars)
    first = min(scenarios, key=lambda scenario: scenario.bars)
    growth_ratio = (
        largest.production_median_ns / first.production_median_ns
        if first.production_median_ns
        else 0.0
    )
    return {
        "largest_bars": largest.bars,
        "largest_structure_production_share": largest.decision_inputs[
            "structure_production_share"
        ],
        "largest_observation_production_share": largest.decision_inputs[
            "observation_production_share"
        ],
        "largest_prefix_copy_production_share": largest.decision_inputs[
            "prefix_copy_production_share"
        ],
        "production_growth_ratio_first_to_largest": growth_ratio,
        "decision_note": (
            "Use these inputs with implementation risk before deciding on "
            "Price Structure Replay Precompute."
        ),
    }


def _validate_benchmark_args(
    *,
    bars: Sequence[int],
    runs: int,
    warmups: int,
) -> None:
    _validate_bars(bars)
    if runs <= 0:
        raise ValueError("runs must be positive")
    if warmups < 0:
        raise ValueError("warmups must not be negative")


def render_table(payload: Mapping[str, object]) -> str:
    scenarios = cast(list[dict[str, object]], payload["scenarios"])
    lines = [
        "Historical Replay Performance Attribution",
        "",
        (
            "bars steps prod_ms instr_ms overhead structure% observation% "
            "prefix% residual%"
        ),
    ]
    for scenario in scenarios:
        production = cast(dict[str, object], scenario["production_run"])
        instrumented = cast(dict[str, object], scenario["instrumented_run"])
        residual = cast(dict[str, object], scenario["residual"])
        decision_inputs = cast(dict[str, object], scenario["decision_inputs"])
        lines.append(
            "{bars:>4} {steps:>5} {prod:>7.2f} {instr:>8.2f} "
            "{overhead:>8.2f} {structure:>10.1%} {observation:>12.1%} "
            "{prefix:>7.1%} {residual:>9.1%}".format(
                bars=scenario["bars"],
                steps=scenario["step_count"],
                prod=_ns_to_ms(cast(int, production["median_ns"])),
                instr=_ns_to_ms(cast(int, instrumented["median_ns"])),
                overhead=cast(float, instrumented["overhead_ratio"]),
                structure=cast(float, decision_inputs["structure_production_share"]),
                observation=cast(
                    float,
                    decision_inputs["observation_production_share"],
                ),
                prefix=cast(float, decision_inputs["prefix_copy_production_share"]),
                residual=cast(float, residual["production_share"]),
            )
        )
        lines.append(
            "  segments: name calls median_total_ms "
            "median_per_call_us prod_share instr_share"
        )
        for segment in cast(list[dict[str, object]], scenario["segments"]):
            lines.append(
                "    {name} {calls:>5} {total:>15.3f} {per_call:>18.3f} "
                "{prod_share:>9.1%} {instr_share:>11.1%}".format(
                    name=segment["name"],
                    calls=segment["call_count"],
                    total=_ns_to_ms(cast(int, segment["median_total_ns"])),
                    per_call=_ns_to_us(cast(int, segment["median_per_call_ns"])),
                    prod_share=cast(float, segment["production_share"]),
                    instr_share=cast(float, segment["instrumented_share"]),
                )
            )
        workload = cast(dict[str, object], scenario["structure_workload"])
        lines.append(
            "  structure workload: available_steps={available} "
            "final_candidates={candidates} final_zones={zones} "
            "total_touches={touches}".format(
                available=workload["structure_available_step_count"],
                candidates=workload["final_candidate_count"],
                zones=workload["final_observed_zone_count"],
                touches=workload["total_independent_zone_touches"],
            )
        )
        serialization = cast(dict[str, dict[str, object]], scenario["serialization"])
        lines.append("  serialization: name median_ms")
        for name in SERIALIZATION_ITEMS:
            lines.append(
                "    {name} {median:>10.3f}".format(
                    name=name,
                    median=_ns_to_ms(cast(int, serialization[name]["median_ns"])),
                )
            )
    return "\n".join(lines) + "\n"


def _ns_to_ms(value: int) -> float:
    return value / 1_000_000.0


def _ns_to_us(value: int) -> float:
    return value / 1_000.0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark historical replay timing and attribution."
    )
    parser.add_argument("--bars", nargs="+", type=int, default=list(DEFAULT_BARS))
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    parser.add_argument("--warmups", type=int, default=DEFAULT_WARMUPS)
    parser.add_argument("--format", choices=("table", "json"), default="table")
    parser.add_argument("--output", default=None)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--start-position", type=int, default=None)
    parser.add_argument("--end-position", type=int, default=None)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        payload = run_benchmark(
            bars=tuple(args.bars),
            runs=args.runs,
            warmups=args.warmups,
            seed=args.seed,
            start_position=args.start_position,
            end_position=args.end_position,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.format == "json":
        rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    else:
        rendered = render_table(payload)

    if args.output is not None:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(rendered, encoding="utf-8")
        return 0
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
