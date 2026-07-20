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
import market_platform.structure.precompute as structure_precompute
import market_platform.structure.service as structure_service
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
    assert counts["structure_precompute"] == 1
    assert counts["structure_analysis"] == 0
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
    assert counts["structure_precompute"] == 1
    assert counts["structure_analysis"] == 0
    assert counts["observation_construction"] == 3
    assert (
        result.to_dict()["steps"]
        == HistoricalReplayService()
        .run(
            prices,
            symbol=benchmark_replay.SYMBOL,
            interval=benchmark_replay.INTERVAL,
            strategies=benchmark_replay.default_strategies(),
            state_model=BaselineMarketStateModel(),
            start=start,
            end=end,
        )
        .to_dict()["steps"]
    )


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
    assert counts["structure_precompute"] == 1
    assert counts["structure_analysis"] == 0
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
    original_structure_precompute = replay_service.precompute_price_structure_snapshots
    original_structure_frame = structure_precompute._normalize_price_frame
    original_observe_zone = structure_service._observe_zone
    original_touch_build = structure_precompute._build_touch_observation_series
    original_touch_lookup = structure_precompute._touch_observation_at_position
    original_normalize = replay_service._normalize_replay_prices

    with (
        pytest.raises(
            RuntimeError,
            match="boom",
        ),
        benchmark_replay._instrument_replay_bindings(benchmark_replay.TimingRecorder()),
    ):
        assert replay_service._copy_replay_prefix is not original_prefix
        raise RuntimeError("boom")

    assert replay_service._copy_replay_prefix is original_prefix
    assert (
        replay_service.precompute_price_structure_snapshots
        is original_structure_precompute
    )
    assert structure_precompute._normalize_price_frame is original_structure_frame
    assert structure_service._observe_zone is original_observe_zone
    assert structure_precompute._build_touch_observation_series is original_touch_build
    assert structure_precompute._touch_observation_at_position is original_touch_lookup

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
    assert {
        segment["name"] for segment in scenario["structure_internal_segments"]
    } == set(benchmark_replay.STRUCTURE_INTERNAL_SEGMENT_NAMES) | {
        "structure_precompute_residual"
    }


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
    assert "structure_internal_segments" in scenario
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
        recorders[0].total_ns(segment) for segment in benchmark_replay.SEGMENT_NAMES
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
    assert "touch_state_builds" in workload
    assert "touch_state_lookups" in workload
    assert "logical_prefix_rows_avoided" in workload


def test_touch_optimization_workload_metrics_are_consistent() -> None:
    scenario = benchmark_replay.run_scenario(
        30,
        runs=1,
        warmups=0,
        seed=31,
    ).to_dict()
    workload = scenario["structure_workload"]
    logical_calls = workload["logical_observer_calls"]
    builds = workload["touch_state_builds"]
    physical_rows = workload["physical_vector_rows_processed"]
    logical_rows = workload["logical_prefix_rows"]

    assert workload["touch_state_lookups"] == logical_calls
    assert workload["unique_touch_keys"] == builds
    assert builds <= logical_calls
    assert workload["fallback_public_observer_calls"] == 0
    assert physical_rows == builds * scenario["bars"]
    assert workload["logical_prefix_rows_avoided"] == max(
        0,
        logical_rows - physical_rows,
    )
    expected_reuse = 0.0 if logical_calls == 0 else 1 - builds / logical_calls
    assert workload["touch_key_reuse_ratio"] == pytest.approx(expected_reuse)
    assert workload["touch_state_array_bytes"] >= 0


def test_structure_internal_attribution_records_real_call_counts() -> None:
    result, _samples, recorders = benchmark_replay.run_instrumented_samples(
        _prices(30),
        runs=1,
        warmups=0,
    )
    recorder = recorders[0]
    internal = benchmark_replay._aggregate_structure_internal_segments(recorders)
    internal_by_name = {segment.name: segment for segment in internal}

    assert recorder.call_count("structure_frame_preparation") == 1
    assert recorder.call_count("structure_pivot_high_detection") == 1
    assert recorder.call_count("structure_pivot_low_detection") == 1
    assert recorder.call_count("structure_atr_series") == 1
    assert recorder.call_count("structure_candidate_visibility") <= result.step_count
    assert (
        recorder.call_count("structure_clustering_and_zone_construction")
        == result.step_count - 13
    )
    logical_touch_observations = sum(
        len(snapshot.observed_zones) for snapshot in recorder.structure_snapshots
    )
    assert (
        recorder.call_count("structure_touch_state_lookup")
        == logical_touch_observations
    )
    assert (
        recorder.call_count("structure_touch_state_build") <= logical_touch_observations
    )
    assert recorder.call_count("structure_fallback_public_observer") == 0
    assert len(set(recorder.structure_touch_keys)) == recorder.call_count(
        "structure_touch_state_build"
    )
    assert (
        sum(recorder.structure_touch_logical_prefix_rows) >= logical_touch_observations
    )
    assert sum(recorder.structure_touch_physical_rows) >= recorder.call_count(
        "structure_touch_state_build"
    )
    assert sum(recorder.structure_touch_array_bytes) >= 0
    assert internal_by_name["structure_precompute_residual"].median_total_ns >= 0


def test_structure_internal_segments_are_not_counted_in_replay_residual() -> None:
    _result, samples, recorders = benchmark_replay.run_instrumented_samples(
        _prices(18),
        runs=1,
        warmups=0,
    )
    top_level_total = sum(
        recorders[0].total_ns(segment) for segment in benchmark_replay.SEGMENT_NAMES
    )
    with_internal_total = top_level_total + sum(
        recorders[0].total_ns(segment)
        for segment in benchmark_replay.STRUCTURE_INTERNAL_SEGMENT_NAMES
    )

    assert top_level_total <= samples[0]
    assert with_internal_total > top_level_total


def test_benchmark_harness_does_not_copy_production_replay_loop() -> None:
    source = Path("scripts/benchmark_replay.py").read_text(encoding="utf-8")

    assert "for position in replay_positions" not in source
    assert "HistoricalReplayService(" in source
    assert ".run(" in source


def test_observation_internal_attribution_metrics_are_consistent() -> None:
    result, _samples, recorders = benchmark_replay.run_instrumented_samples(
        _prices(20),
        runs=1,
        warmups=0,
    )
    recorder = recorders[0]
    scenario = benchmark_replay.run_scenario(
        20,
        runs=1,
        warmups=0,
        seed=7,
    ).to_dict()

    assert recorder.call_count("observation_prefix_preparation") == result.step_count
    assert recorder.call_count("observation_metadata") == result.step_count
    assert recorder.call_count("observation_identity") == result.step_count
    assert recorder.call_count("observation_price_facts") == result.step_count
    assert recorder.call_count("observation_fingerprint_rows") == result.step_count
    assert recorder.call_count("observation_fingerprint_canonical_json") == (
        result.step_count
    )
    assert recorder.call_count("observation_fingerprint_hash") == result.step_count
    assert recorder.call_count("observation_provenance") == result.step_count
    assert recorder.call_count("observation_signal_facts") == result.step_count
    assert recorder.call_count("observation_structure_facts") == result.step_count
    assert recorder.call_count("observation_model_construction") == result.step_count
    assert sum(recorder.observation_prefix_lengths) == sum(
        range(1, result.step_count + 1)
    )
    assert sum(recorder.observation_fingerprint_rows) == sum(
        range(1, result.step_count + 1)
    )
    assert sum(recorder.observation_signal_counts) == result.step_count * 5

    observation_attribution = scenario["observation_attribution"]
    assert {segment["name"] for segment in scenario["observation_segments"]} == set(
        benchmark_replay.OBSERVATION_INTERNAL_SEGMENT_NAMES
    )
    assert observation_attribution["residual"]["median_ns"] >= 0
    for segment in observation_attribution["segments"]:
        assert segment["median_total_ns"] >= 0
        assert segment["median_per_call_ns"] >= 0
        assert segment["timing_mode"] == "exclusive"
    assert scenario["observation_workload"]["builder_calls"] == scenario["step_count"]
    assert (
        scenario["fingerprint_workload"]["fingerprint_calls"] == scenario["step_count"]
    )
    assert scenario["fingerprint_workload"]["canonicalized_row_count"] == sum(
        range(1, scenario["step_count"] + 1)
    )
    assert (
        scenario["canonicalization_workload"]["canonicalization_calls"]
        == (scenario["step_count"])
    )
    assert (
        scenario["canonicalization_workload"]["canonicalized_chars"]
        == scenario["fingerprint_workload"]["hash_input_bytes"]
    )


def test_observation_instrumentation_restores_private_helper_patches() -> None:
    original_prefix = benchmark_replay.observation_history._normalize_price_prefix
    original_rows = (
        benchmark_replay.observation_history._historical_observation_fingerprint_rows
    )
    original_signal = benchmark_replay.observation_builder.build_signal_facts
    original_structure = benchmark_replay.observation_builder.build_structure_facts

    with (
        pytest.raises(
            RuntimeError,
            match="boom",
        ),
        benchmark_replay._instrument_replay_bindings(benchmark_replay.TimingRecorder()),
    ):
        assert benchmark_replay.observation_history._normalize_price_prefix is not (
            original_prefix
        )
        assert benchmark_replay.observation_builder.build_signal_facts is not (
            original_signal
        )
        raise RuntimeError("boom")

    assert (
        benchmark_replay.observation_history._normalize_price_prefix is original_prefix
    )
    assert (
        benchmark_replay.observation_history._historical_observation_fingerprint_rows
        is original_rows
    )
    assert benchmark_replay.observation_builder.build_signal_facts is original_signal
    assert (
        benchmark_replay.observation_builder.build_structure_facts is original_structure
    )


def test_instrumented_observations_match_normal_observations_exactly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prices = _prices(24)
    normal_observations = []
    instrumented_observations = []
    original = replay_service.build_historical_market_observation

    def recording_normal(*args, **kwargs):
        observation = original(*args, **kwargs)
        normal_observations.append(observation)
        return observation

    monkeypatch.setattr(
        replay_service,
        "build_historical_market_observation",
        recording_normal,
    )
    normal_result = benchmark_replay._run_replay(prices)

    def recording_instrumented(*args, **kwargs):
        observation = original(*args, **kwargs)
        instrumented_observations.append(observation)
        return observation

    monkeypatch.setattr(
        replay_service,
        "build_historical_market_observation",
        recording_instrumented,
    )
    instrumented_result = benchmark_replay._run_instrumented_replay(prices)

    assert instrumented_result.to_dict() == normal_result.to_dict()
    assert len(instrumented_observations) == len(normal_observations) == 24
    for instrumented, normal in zip(
        instrumented_observations,
        normal_observations,
        strict=True,
    ):
        assert instrumented == normal
        assert instrumented.to_dict() == normal.to_dict()
        assert json.dumps(instrumented.to_dict(), sort_keys=True) == json.dumps(
            normal.to_dict(),
            sort_keys=True,
        )
        assert (
            instrumented.provenance.input_fingerprint
            == normal.provenance.input_fingerprint
        )
        assert instrumented.provenance == normal.provenance
