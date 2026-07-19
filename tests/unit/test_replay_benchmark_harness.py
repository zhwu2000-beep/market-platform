from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

import market_platform.replay.service as replay_service
from market_platform.replay import HistoricalReplayService
from market_platform.state import BaselineMarketStateModel
from market_platform.strategy import create_strategy_collection

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "benchmark_replay.py"
_SPEC = importlib.util.spec_from_file_location("benchmark_replay", _SCRIPT_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("benchmark_replay script could not be loaded")
benchmark_replay = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = benchmark_replay
_SPEC.loader.exec_module(benchmark_replay)


def _prices(count: int = 30) -> pd.DataFrame:
    return benchmark_replay.build_price_frame(count, seed=7)


def test_copy_replay_prefix_matches_original_expression_and_deep_copies() -> None:
    prices = _prices(6).iloc[[3, 0, 5, 1, 4, 2]].reset_index(drop=True)
    before = prices.copy(deep=True)

    prefix = replay_service._copy_replay_prefix(prices, 3)
    expected = prices.iloc[:4].copy(deep=True)

    assert_frame_equal(prefix, expected)
    prefix.loc[0, "close"] = 1.0
    assert prices.loc[0, "close"] == before.loc[0, "close"]
    assert_frame_equal(prices, before)
    assert list(prefix["timestamp"]) == list(prices.iloc[:4]["timestamp"])


def test_production_and_instrumented_replay_outputs_match_exactly() -> None:
    prices = _prices(30)

    production = benchmark_replay._run_replay(prices)
    instrumented = benchmark_replay._run_instrumented_replay(prices)

    assert instrumented.to_dict() == production.to_dict()
    assert [step.as_of for step in instrumented.steps] == [
        step.as_of for step in production.steps
    ]
    assert [strategy.strategy_id for strategy in instrumented.strategies] == [
        strategy.strategy_id for strategy in production.strategies
    ]
    assert [step.observation_fingerprint for step in instrumented.steps] == [
        step.observation_fingerprint for step in production.steps
    ]


def test_instrumented_call_counts_for_full_replay() -> None:
    prices = _prices(18)
    result, _samples, recorders = benchmark_replay.run_instrumented_samples(
        prices,
        runs=1,
        warmups=0,
    )

    counts = benchmark_replay._call_counts(recorders, result)

    assert counts["price_normalization"] == 1
    assert counts["provider_extraction"] == 1
    assert counts["replay_position_selection"] == 1
    assert counts["signal_precompute"] == 1
    assert counts["strategy_identity_construction"] == 1
    assert counts["prefix_slicing_copy"] == result.step_count == 18
    assert counts["structure_analysis"] == result.step_count
    assert counts["observation_construction"] == result.step_count
    assert counts["state_evaluation"] == result.step_count
    assert counts["strategy_runner_evaluation"] == result.step_count
    assert counts["strategy_evaluations"] == result.step_count * 2


def test_instrumented_call_counts_for_start_end_subwindow() -> None:
    prices = _prices(20)
    start = datetime(2026, 1, 6, tzinfo=UTC)
    end = start + timedelta(days=2)
    result, _samples, recorders = benchmark_replay.run_instrumented_samples(
        prices,
        runs=1,
        warmups=0,
        start=start,
        end=end,
    )

    counts = benchmark_replay._call_counts(recorders, result)

    assert result.step_count == 3
    assert counts["signal_precompute"] == 1
    assert counts["prefix_slicing_copy"] == 3
    assert counts["structure_analysis"] == 3
    assert counts["observation_construction"] == 3
    assert result.to_dict()["steps"] == HistoricalReplayService().run(
        prices,
        symbol=benchmark_replay.SYMBOL,
        interval=benchmark_replay.INTERVAL,
        strategies=benchmark_replay.default_strategies(),
        state_model=BaselineMarketStateModel(),
        start=start,
        end=end,
    ).to_dict()["steps"]


def test_instrumented_call_counts_for_empty_strategy_collection() -> None:
    prices = _prices(12)
    empty_strategies = create_strategy_collection([])
    result, _samples, recorders = benchmark_replay.run_instrumented_samples(
        prices,
        runs=1,
        warmups=0,
        strategies=empty_strategies,
    )

    counts = benchmark_replay._call_counts(recorders, result)

    assert result.strategies == ()
    assert result.step_count == 12
    assert counts["strategy_runner_evaluation"] == 12
    assert counts["strategy_evaluations"] == 0


def test_signal_precompute_is_patched_at_replay_service_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    original = replay_service.precompute_market_signal_snapshots

    def counting_precompute(prices: pd.DataFrame):
        nonlocal calls
        calls += 1
        return original(prices)

    monkeypatch.setattr(
        replay_service,
        "precompute_market_signal_snapshots",
        counting_precompute,
    )

    benchmark_replay._run_instrumented_replay(_prices(10))

    assert calls == 1


def test_instrumentation_restores_patches_and_does_not_swallow_exceptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_prefix = replay_service._copy_replay_prefix
    original_normalize = replay_service._normalize_replay_prices

    with pytest.raises(
        RuntimeError,
        match="boom",
    ), benchmark_replay._instrument_replay_bindings(
        benchmark_replay.TimingRecorder()
    ):
        assert replay_service._copy_replay_prefix is not original_prefix
        raise RuntimeError("boom")

    assert replay_service._copy_replay_prefix is original_prefix

    def exploding_normalize(prices: pd.DataFrame, symbol: str) -> pd.DataFrame:
        raise ValueError("bad frame")

    monkeypatch.setattr(replay_service, "_normalize_replay_prices", exploding_normalize)
    with pytest.raises(ValueError, match="bad frame"):
        benchmark_replay._run_instrumented_replay(_prices(5))
    assert replay_service._normalize_replay_prices is exploding_normalize
    monkeypatch.setattr(replay_service, "_normalize_replay_prices", original_normalize)


def test_serialization_is_measured_separately_and_stably() -> None:
    result = benchmark_replay._run_replay(_prices(16))

    serialization = benchmark_replay.measure_serialization(result, runs=3)

    assert set(serialization) == set(benchmark_replay.SERIALIZATION_ITEMS)
    for item in serialization.values():
        assert len(item["samples_ns"]) == 3
        assert item["median_ns"] > 0
        assert item["stable_output_confirmed"] is True


def test_run_scenario_reports_required_keys_without_speed_thresholds() -> None:
    scenario = benchmark_replay.run_scenario(
        12,
        runs=1,
        warmups=0,
        seed=11,
    ).to_dict()

    assert scenario["production_run"]["median_ns"] > 0
    assert scenario["instrumented_run"]["median_ns"] > 0
    assert "overhead_ratio" in scenario["instrumented_run"]
    assert "residual" in scenario
    assert "result_fingerprint" in scenario
    assert scenario["stable_output_confirmed"] is True
    assert {segment["name"] for segment in scenario["segments"]} == set(
        benchmark_replay.SEGMENT_NAMES
    )


def test_benchmark_cli_json_output_and_argument_validation(tmp_path: Path) -> None:
    output_path = tmp_path / "benchmark.json"

    exit_code = benchmark_replay.main(
        [
            "--bars",
            "8",
            "--runs",
            "1",
            "--warmups",
            "0",
            "--format",
            "json",
            "--output",
            str(output_path),
        ]
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["schema_version"] == benchmark_replay.SCHEMA_VERSION
    assert payload["configuration"]["bars"] == [8]
    assert payload["configuration"]["gc_policy"]
    assert payload["configuration"]["data_generation"]
    scenario = payload["scenarios"][0]
    assert scenario["step_count"] == 8
    assert isinstance(scenario["production_run"]["median_ns"], int)
    assert isinstance(scenario["production_run"]["samples_ns"][0], int)
    assert isinstance(scenario["instrumented_run"]["median_ns"], int)
    assert "structure_workload" in scenario
    assert benchmark_replay.main(["--bars", "0"]) == 2


def test_benchmark_frames_use_same_max_frame_prefixes() -> None:
    frames = benchmark_replay.build_benchmark_frames((100, 300, 500), seed=17)
    max_frame = benchmark_replay.build_price_frame(500, seed=17)

    assert_frame_equal(frames[100], max_frame.iloc[:100].copy(deep=True))
    assert_frame_equal(frames[300], max_frame.iloc[:300].copy(deep=True))
    assert_frame_equal(frames[500], max_frame.copy(deep=True))
    assert_frame_equal(
        benchmark_replay.build_price_frame(300, seed=17),
        max_frame.iloc[:300].copy(deep=True),
    )


def test_benchmark_price_frame_seed_controls_all_data() -> None:
    first = benchmark_replay.build_price_frame(24, seed=19)
    second = benchmark_replay.build_price_frame(24, seed=19)
    different = benchmark_replay.build_price_frame(24, seed=20)

    assert_frame_equal(first, second)
    assert not first.equals(different)


def test_benchmark_collects_gc_before_each_timing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fake_collect() -> int:
        nonlocal calls
        calls += 1
        return 0

    monkeypatch.setattr(benchmark_replay.gc, "collect", fake_collect)
    prices = _prices(8)

    benchmark_replay.run_production_samples(prices, runs=2, warmups=1)
    assert calls == 3

    benchmark_replay.run_instrumented_samples(prices, runs=2, warmups=1)
    assert calls == 6

    result = benchmark_replay._run_replay(prices)
    benchmark_replay.measure_serialization(result, runs=2)
    assert calls == 16


def test_run_benchmark_generates_one_max_frame_outside_scenario_timing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[int, int]] = []
    original = benchmark_replay.build_price_frame

    def counting_build_price_frame(
        bars: int,
        *,
        seed: int = benchmark_replay.DEFAULT_SEED,
    ) -> pd.DataFrame:
        calls.append((bars, seed))
        return original(bars, seed=seed)

    monkeypatch.setattr(
        benchmark_replay,
        "build_price_frame",
        counting_build_price_frame,
    )

    payload = benchmark_replay.run_benchmark(
        bars=(8, 12),
        runs=1,
        warmups=0,
        seed=23,
        include_generated_at=False,
    )

    assert calls == [(12, 23)]
    assert payload["configuration"]["data_generation"]
    assert payload["configuration"]["gc_policy"]


def test_segment_totals_are_not_double_counted() -> None:
    _result, samples, recorders = benchmark_replay.run_instrumented_samples(
        _prices(10),
        runs=1,
        warmups=0,
    )

    measured_total = sum(
        recorders[0].total_ns(segment)
        for segment in benchmark_replay.SEGMENT_NAMES
    )

    assert measured_total <= samples[0]


def test_scenario_reports_structure_workload_from_instrumented_snapshots() -> None:
    scenario = benchmark_replay.run_scenario(
        18,
        runs=1,
        warmups=0,
        seed=29,
    ).to_dict()
    workload = scenario["structure_workload"]

    assert workload["step_count"] == scenario["step_count"]
    assert workload["source"]
    assert "status_counts" in workload
    assert "final_candidate_count" in workload
    assert "final_observed_zone_count" in workload
    assert "total_independent_zone_touches" in workload

def test_benchmark_harness_does_not_copy_production_replay_loop() -> None:
    source = Path("scripts/benchmark_replay.py").read_text(encoding="utf-8")

    assert "for position in replay_positions" not in source
    assert "HistoricalReplayService(" in source
    assert ".run(" in source
