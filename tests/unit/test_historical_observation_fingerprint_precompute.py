from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

import market_platform.observation.fingerprint as observation_fingerprint
import market_platform.observation.history as observation_history
import market_platform.replay.service as replay_service
from market_platform.data import HistoricalPricePrefix, HistoricalPriceSeries
from market_platform.observation import (
    HistoricalObservationFingerprintPrecompute,
    build_historical_market_observation,
    build_historical_market_observation_from_prefix,
    prepare_historical_observation_fingerprints,
)
from market_platform.replay import (
    HistoricalReplayArtifact,
    HistoricalReplayExperimentSpecification,
    HistoricalReplayService,
    HistoricalReplaySpecification,
    SoftwareRevision,
    create_historical_replay_experiment,
    save_historical_replay_artifact,
)
from market_platform.signals import calculate_market_signals
from market_platform.state import BaselineMarketStateModel
from market_platform.strategy import (
    BaselineTrendRegimeStrategy,
    create_strategy_collection,
)
from market_platform.structure import PriceStructureService

_START = datetime(2026, 1, 1, tzinfo=UTC)
_SOFTWARE = SoftwareRevision("v0.52-test", False)
_COMPARISON_SOFTWARE = SoftwareRevision("v0.52-comparison-test", False)
_ONE_ROW_CANONICAL = (
    b'{"as_of":"2026-01-01T00:00:00+00:00","interval":"1day",'
    b'"provider":"test-provider","rows":[{"close":"100.5","high":"101.0",'
    b'"low":"99.0","open":"100.0","provider":"test-provider","symbol":"MSFT",'
    b'"timestamp":"2026-01-01T00:00:00+00:00","volume":"1000000.0"}],'
    b'"symbol":"MSFT"}'
)
_ONE_ROW_FINGERPRINT = (
    "sha256:959968129fb6261b44a3a44d2cb19e9c9bbad52a8eb5a14322c4cd979407e1b4"
)
_SIGNED_UNICODE_CANONICAL = (
    b'{"as_of":"2026-01-01T16:00:00+00:00","interval":"4h",'
    b'"provider":"\\u63d0\\u4f9b\\u8005","rows":[{"close":"1.5","high":"2.0",'
    b'"low":"0.5","open":"1.0","provider":"\\u63d0\\u4f9b\\u8005",'
    b'"symbol":"\\u00c5BC","timestamp":"2025-12-31T16:00:00+00:00",'
    b'"volume":"-0.0"},{"close":"2.5","high":"3.0","low":"1.5",'
    b'"open":"2.0","provider":"\\u63d0\\u4f9b\\u8005","symbol":"\\u00c5BC",'
    b'"timestamp":"2026-01-01T16:00:00+00:00",'
    b'"volume":"9007199254740992.0"}],"symbol":"\\u00c5BC"}'
)
_SIGNED_UNICODE_FINGERPRINT = (
    "sha256:e0d81e55efe498607c3ceaf01338acebd2be5e4108b4d51d34ea8c5f1ea2e440"
)


def _prices(
    count: int = 12,
    *,
    provider: str = "test-provider",
    first_volume: float = 1_000_000.0,
) -> pd.DataFrame:
    closes = [100.0 + index * 0.5 for index in range(count)]
    volumes = [1_000_000.0] * count
    volumes[0] = first_volume
    return pd.DataFrame(
        {
            "symbol": ["MSFT"] * count,
            "timestamp": [_START + timedelta(days=index) for index in range(count)],
            "open": closes,
            "high": [close + 1.0 for close in closes],
            "low": [close - 1.0 for close in closes],
            "close": closes,
            "volume": volumes,
            "provider": [provider] * count,
        }
    )


def _one_row_series(*, volume: float = 1_000_000.0) -> HistoricalPriceSeries:
    return HistoricalPriceSeries(
        pd.DataFrame(
            {
                "symbol": ["MSFT"],
                "timestamp": [_START],
                "open": [100.0],
                "high": [101.0],
                "low": [99.0],
                "close": [100.5],
                "volume": [volume],
                "provider": ["test-provider"],
            }
        )
    )


def _signed_unicode_series() -> HistoricalPriceSeries:
    offset = timezone(timedelta(hours=8))
    return HistoricalPriceSeries(
        pd.DataFrame(
            {
                "symbol": ["ÅBC", "ÅBC"],
                "timestamp": [
                    datetime(2026, 1, 1, tzinfo=offset),
                    datetime(2026, 1, 2, tzinfo=offset),
                ],
                "open": [1.0, 2.0],
                "high": [2.0, 3.0],
                "low": [0.5, 1.5],
                "close": [1.5, 2.5],
                "volume": [-0.0, 9_007_199_254_740_992],
                "provider": ["提供者", "提供者"],
            }
        )
    )


def _fallback_fingerprint(
    series: HistoricalPriceSeries,
    position: int,
    *,
    interval: str = "1day",
) -> str:
    prefix = series.prefix_at(position)
    return observation_history._historical_observation_fingerprint(
        prefix=prefix,
        symbol=series.symbol,
        interval=interval,
        as_of=prefix.as_of,
        provider=series.provider,
    )


def _snapshots(series: HistoricalPriceSeries):
    frame = series.to_dataframe()
    return (
        calculate_market_signals(frame),
        PriceStructureService().analyze(frame, as_of=series.as_of),
    )


def _specification(count: int = 12) -> HistoricalReplaySpecification:
    return HistoricalReplaySpecification(
        symbol="MSFT",
        interval="1day",
        context_start=_START,
        evaluation_start=_START + timedelta(days=4),
        evaluation_end=_START + timedelta(days=count - 1),
    )


def _run_execution(
    prices: pd.DataFrame,
    *,
    fallback: bool,
    monkeypatch: pytest.MonkeyPatch,
):
    original = observation_history.build_historical_market_observation_from_prefix
    with monkeypatch.context() as context:
        if fallback:

            def fallback_builder(
                prefix: HistoricalPricePrefix,
                **kwargs: object,
            ):
                kwargs.pop("fingerprint_precompute", None)
                return original(prefix, **kwargs)  # type: ignore[arg-type]

            context.setattr(
                replay_service,
                "build_historical_market_observation_from_prefix",
                fallback_builder,
            )
        return HistoricalReplayService().run_execution(
            prices,
            _specification(len(prices)),
            strategies=create_strategy_collection(
                [BaselineTrendRegimeStrategy()]
            ),
            state_model=BaselineMarketStateModel(),
            software_revision=_SOFTWARE,
        )


def test_exact_legacy_one_row_bytes_and_digest_are_frozen() -> None:
    series = _one_row_series()
    prefix = series.full_prefix()

    canonical = observation_fingerprint._historical_observation_fingerprint_bytes(
        prefix=prefix,
        symbol=series.symbol,
        interval="1day",
        as_of=prefix.as_of,
        provider=series.provider,
    )

    assert canonical == _ONE_ROW_CANONICAL
    assert (
        observation_fingerprint._hash_historical_observation_fingerprint_bytes(
            canonical
        )
        == _ONE_ROW_FINGERPRINT
    )
    assert _fallback_fingerprint(series, 0) == _ONE_ROW_FINGERPRINT


def test_unicode_offset_large_volume_and_signed_zero_legacy_bytes_are_frozen() -> None:
    series = _signed_unicode_series()
    prefix = series.full_prefix()
    canonical = observation_fingerprint._historical_observation_fingerprint_bytes(
        prefix=prefix,
        symbol=series.symbol,
        interval="4h",
        as_of=prefix.as_of,
        provider=series.provider,
    )
    precompute = prepare_historical_observation_fingerprints(
        series,
        (1,),
        interval="4h",
    )

    assert canonical == _SIGNED_UNICODE_CANONICAL
    assert _fallback_fingerprint(series, 1, interval="4h") == (
        _SIGNED_UNICODE_FINGERPRINT
    )
    assert precompute.fingerprint_for_validated_prefix(
        prefix,
        symbol=series.symbol,
        interval="4h",
        provider=series.provider,
        as_of=prefix.as_of,
    ) == _SIGNED_UNICODE_FINGERPRINT


def test_signed_zero_remains_distinct_in_observation_identity() -> None:
    positive = _one_row_series(volume=0.0)
    negative = _one_row_series(volume=-0.0)

    assert _fallback_fingerprint(positive, 0) != _fallback_fingerprint(negative, 0)
    assert b'"volume":"0.0"' in (
        observation_fingerprint._historical_observation_fingerprint_bytes(
            prefix=positive.full_prefix(),
            symbol=positive.symbol,
            interval="1day",
            as_of=positive.as_of,
            provider=positive.provider,
        )
    )
    assert b'"volume":"-0.0"' in (
        observation_fingerprint._historical_observation_fingerprint_bytes(
            prefix=negative.full_prefix(),
            symbol=negative.symbol,
            interval="1day",
            as_of=negative.as_of,
            provider=negative.provider,
        )
    )


def test_fragment_bytes_equal_legacy_full_json_for_every_prefix() -> None:
    series = HistoricalPriceSeries(_prices(8))
    for position in range(len(series)):
        prefix = series.prefix_at(position)
        payload = observation_history._historical_observation_fingerprint_payload(
            prefix=prefix,
            symbol=series.symbol,
            interval="1day",
            as_of=prefix.as_of,
            provider=series.provider,
        )
        legacy = (
            observation_history
            ._canonicalize_historical_observation_fingerprint_payload(
                payload
            )
            .encode("utf-8")
        )
        fragmented = (
            observation_fingerprint._historical_observation_fingerprint_bytes(
                prefix=prefix,
                symbol=series.symbol,
                interval="1day",
                as_of=prefix.as_of,
                provider=series.provider,
            )
        )
        assert fragmented == legacy


def test_mapping_order_is_neutral_but_row_order_participates() -> None:
    first = {
        "symbol": "MSFT",
        "timestamp": _START.isoformat(),
        "open": "1.0",
        "high": "2.0",
        "low": "0.5",
        "close": "1.5",
        "volume": "10.0",
        "provider": "provider",
    }
    reversed_mapping = dict(reversed(tuple(first.items())))
    first_bytes = observation_fingerprint._canonical_json_bytes(first)
    second_bytes = observation_fingerprint._canonical_json_bytes(reversed_mapping)
    header, suffix = (
        observation_fingerprint
        ._historical_observation_fingerprint_envelope_bytes(
            symbol="MSFT",
            interval="1day",
            as_of=_START + timedelta(days=1),
            provider="provider",
        )
    )
    other = dict(first)
    other["timestamp"] = (_START + timedelta(days=1)).isoformat()
    other_bytes = observation_fingerprint._canonical_json_bytes(other)

    assert first_bytes == second_bytes
    assert header + first_bytes + b"," + other_bytes + suffix != (
        header + other_bytes + b"," + first_bytes + suffix
    )


@pytest.mark.parametrize("positions", [(), (1, 1), (2, 1)])
def test_precompute_rejects_empty_duplicate_or_unordered_positions(
    positions: tuple[int, ...],
) -> None:
    with pytest.raises(ValueError):
        prepare_historical_observation_fingerprints(
            HistoricalPriceSeries(_prices(4)),
            positions,
            interval="1day",
        )


@pytest.mark.parametrize("positions", [(True,), (-1,), (4,)])
def test_precompute_rejects_invalid_positions(positions: tuple[object, ...]) -> None:
    with pytest.raises((TypeError, IndexError)):
        prepare_historical_observation_fingerprints(
            HistoricalPriceSeries(_prices(4)),
            positions,  # type: ignore[arg-type]
            interval="1day",
        )


def test_noncontiguous_precompute_matches_fallback_and_is_immutable() -> None:
    series = HistoricalPriceSeries(_prices(10))
    positions = (0, 3, 9)
    precompute = prepare_historical_observation_fingerprints(
        series,
        positions,
        interval="1day",
    )

    assert isinstance(precompute, HistoricalObservationFingerprintPrecompute)
    assert precompute.evaluation_positions == positions
    assert precompute.source_row_count == 10
    assert "_source=" not in repr(precompute)
    for position in positions:
        prefix = series.prefix_at(position)
        actual = precompute.fingerprint_for_validated_prefix(
            prefix,
            symbol=series.symbol,
            interval="1day",
            provider=series.provider,
            as_of=prefix.as_of,
        )
        assert actual == _fallback_fingerprint(series, position)
        assert actual == precompute.fingerprint_for_validated_prefix(
            prefix,
            symbol=series.symbol,
            interval="1day",
            provider=series.provider,
            as_of=prefix.as_of,
        )
    with pytest.raises(FrozenInstanceError):
        precompute.interval = "other"  # type: ignore[misc]


def test_precompute_requires_the_validated_public_factory() -> None:
    with pytest.raises(
        TypeError,
        match="prepare_historical_observation_fingerprints",
    ):
        HistoricalObservationFingerprintPrecompute()

    series = HistoricalPriceSeries(_prices(4))
    precompute = prepare_historical_observation_fingerprints(
        series,
        (3,),
        interval="1day",
    )
    prefix = series.full_prefix()

    assert isinstance(precompute, HistoricalObservationFingerprintPrecompute)
    assert repr(precompute)
    assert precompute.fingerprint_for_validated_prefix(
        prefix,
        symbol=series.symbol,
        interval="1day",
        provider=series.provider,
        as_of=prefix.as_of,
    ) == _fallback_fingerprint(series, 3)


def test_precompute_rejects_wrong_source_and_binding_facts() -> None:
    series = HistoricalPriceSeries(_prices(5))
    equivalent_but_distinct = HistoricalPriceSeries(_prices(5))
    precompute = prepare_historical_observation_fingerprints(
        series,
        (2, 4),
        interval="1day",
    )
    prefix = series.prefix_at(2)
    kwargs = {
        "symbol": series.symbol,
        "interval": "1day",
        "provider": series.provider,
        "as_of": prefix.as_of,
    }

    with pytest.raises(ValueError, match="historical series"):
        precompute.fingerprint_for_validated_prefix(
            equivalent_but_distinct.prefix_at(2),
            **kwargs,
        )
    with pytest.raises(ValueError, match="symbol"):
        precompute.fingerprint_for_validated_prefix(
            prefix,
            **{**kwargs, "symbol": "AAPL"},
        )
    with pytest.raises(ValueError, match="interval"):
        precompute.fingerprint_for_validated_prefix(
            prefix,
            **{**kwargs, "interval": "4h"},
        )
    with pytest.raises(ValueError, match="provider"):
        precompute.fingerprint_for_validated_prefix(
            prefix,
            **{**kwargs, "provider": "other"},
        )
    with pytest.raises(ValueError, match="not prepared"):
        precompute.fingerprint_for_validated_prefix(
            series.prefix_at(3),
            **{**kwargs, "as_of": series.timestamp_at(3)},
        )
    with pytest.raises(ValueError, match="observation as_of"):
        precompute.fingerprint_for_validated_prefix(
            prefix,
            **{**kwargs, "as_of": prefix.as_of + timedelta(seconds=1)},
        )


def test_precompute_rejects_corrupted_prefix_length_and_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    series = HistoricalPriceSeries(_prices(5))
    precompute = prepare_historical_observation_fingerprints(
        series,
        (2,),
        interval="1day",
    )
    prefix = series.prefix_at(2)
    kwargs = {
        "symbol": series.symbol,
        "interval": "1day",
        "provider": series.provider,
        "as_of": prefix.as_of,
    }
    object.__setattr__(prefix, "_stop", 2)
    with pytest.raises(ValueError, match="prefix length"):
        precompute.fingerprint_for_validated_prefix(prefix, **kwargs)

    valid_prefix = series.prefix_at(2)
    with monkeypatch.context() as context:
        context.setattr(
            HistoricalPricePrefix,
            "as_of",
            property(lambda _prefix: _START + timedelta(days=4)),
        )
        with pytest.raises(ValueError, match="prefix endpoint"):
            precompute.fingerprint_for_validated_prefix(
                valid_prefix,
                **kwargs,
            )


def test_bound_builder_matches_raw_and_fallback_observations() -> None:
    prices = _prices(8)
    series = HistoricalPriceSeries(prices)
    prefix = series.full_prefix()
    signal_snapshot, structure_snapshot = _snapshots(series)
    precompute = prepare_historical_observation_fingerprints(
        series,
        (7,),
        interval="1day",
    )
    kwargs = {
        "symbol": series.symbol,
        "interval": "1day",
        "as_of": prefix.as_of,
        "provider": series.provider,
        "signal_snapshot": signal_snapshot,
        "structure_snapshot": structure_snapshot,
    }

    fallback = build_historical_market_observation_from_prefix(prefix, **kwargs)
    optimized = build_historical_market_observation_from_prefix(
        prefix,
        **kwargs,
        fingerprint_precompute=precompute,
    )
    raw = build_historical_market_observation(prices, **kwargs)

    assert optimized == fallback == raw
    assert optimized.to_dict() == fallback.to_dict() == raw.to_dict()


def test_optimized_replay_projects_and_encodes_each_required_row_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    counts = {
        "prepare": 0,
        "row_projection": 0,
        "row_encoding": 0,
        "digest": 0,
        "lookup": 0,
        "fallback": 0,
        "prefix_traversal": 0,
    }
    original_prepare = replay_service.prepare_historical_observation_fingerprints
    original_projection = (
        observation_fingerprint._historical_observation_fingerprint_row
    )
    original_encoding = (
        observation_fingerprint._encode_historical_observation_fingerprint_row
    )
    original_digest = (
        observation_fingerprint._hash_historical_observation_fingerprint_parts
    )
    original_lookup = (
        HistoricalObservationFingerprintPrecompute
        .fingerprint_for_validated_prefix
    )
    original_fallback = observation_history._historical_observation_fingerprint
    original_traversal = HistoricalPricePrefix.iter_rows

    def prepare(*args: object, **kwargs: object):
        counts["prepare"] += 1
        return original_prepare(*args, **kwargs)  # type: ignore[arg-type]

    def project(row: object):
        counts["row_projection"] += 1
        return original_projection(row)  # type: ignore[arg-type]

    def encode(row: object):
        counts["row_encoding"] += 1
        return original_encoding(row)  # type: ignore[arg-type]

    def digest(*parts: bytes | memoryview):
        counts["digest"] += 1
        return original_digest(*parts)

    def lookup(
        self: HistoricalObservationFingerprintPrecompute,
        *args: object,
        **kwargs: object,
    ):
        counts["lookup"] += 1
        return original_lookup(self, *args, **kwargs)  # type: ignore[arg-type]

    def fallback(*args: object, **kwargs: object):
        counts["fallback"] += 1
        return original_fallback(*args, **kwargs)  # type: ignore[arg-type]

    def traversal(prefix: HistoricalPricePrefix):
        counts["prefix_traversal"] += 1
        return original_traversal(prefix)

    monkeypatch.setattr(
        replay_service,
        "prepare_historical_observation_fingerprints",
        prepare,
    )
    monkeypatch.setattr(
        observation_fingerprint,
        "_historical_observation_fingerprint_row",
        project,
    )
    monkeypatch.setattr(
        observation_fingerprint,
        "_encode_historical_observation_fingerprint_row",
        encode,
    )
    monkeypatch.setattr(
        observation_fingerprint,
        "_hash_historical_observation_fingerprint_parts",
        digest,
    )
    monkeypatch.setattr(
        HistoricalObservationFingerprintPrecompute,
        "fingerprint_for_validated_prefix",
        lookup,
    )
    monkeypatch.setattr(
        observation_history,
        "_historical_observation_fingerprint",
        fallback,
    )
    monkeypatch.setattr(HistoricalPricePrefix, "iter_rows", traversal)

    result = HistoricalReplayService().run(
        _prices(20),
        symbol="MSFT",
        interval="1day",
        strategies=create_strategy_collection([BaselineTrendRegimeStrategy()]),
        state_model=BaselineMarketStateModel(),
    )

    assert result.step_count == 20
    assert counts == {
        "prepare": 1,
        "row_projection": 20,
        "row_encoding": 20,
        "digest": 20,
        "lookup": 20,
        "fallback": 0,
        "prefix_traversal": 0,
    }


def test_context_rows_are_encoded_once_before_later_evaluation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    encoded = 0
    original = observation_fingerprint._encode_historical_observation_fingerprint_row

    def recording(row: object):
        nonlocal encoded
        encoded += 1
        return original(row)  # type: ignore[arg-type]

    monkeypatch.setattr(
        observation_fingerprint,
        "_encode_historical_observation_fingerprint_row",
        recording,
    )
    result = HistoricalReplayService().run_with_specification(
        _prices(60),
        HistoricalReplaySpecification(
            symbol="MSFT",
            interval="1day",
            context_start=_START,
            evaluation_start=_START + timedelta(days=50),
            evaluation_end=_START + timedelta(days=52),
        ),
        strategies=create_strategy_collection([BaselineTrendRegimeStrategy()]),
        state_model=BaselineMarketStateModel(),
    )

    assert result.step_count == 3
    assert encoded == 53


def test_replay_execution_artifact_bytes_and_experiment_are_fallback_identical(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    baseline_prices = _prices(12, provider="provider-a")
    candidate_prices = _prices(12, provider="provider-b")
    optimized_baseline = _run_execution(
        baseline_prices,
        fallback=False,
        monkeypatch=monkeypatch,
    )
    optimized_candidate = _run_execution(
        candidate_prices,
        fallback=False,
        monkeypatch=monkeypatch,
    )
    fallback_baseline = _run_execution(
        baseline_prices,
        fallback=True,
        monkeypatch=monkeypatch,
    )
    fallback_candidate = _run_execution(
        candidate_prices,
        fallback=True,
        monkeypatch=monkeypatch,
    )

    assert optimized_baseline == fallback_baseline
    assert optimized_candidate == fallback_candidate
    assert optimized_baseline.result.to_dict() == fallback_baseline.result.to_dict()
    assert optimized_baseline.run_fingerprint == fallback_baseline.run_fingerprint

    optimized_artifact = HistoricalReplayArtifact.from_execution(
        optimized_baseline
    )
    fallback_artifact = HistoricalReplayArtifact.from_execution(fallback_baseline)
    assert optimized_artifact == fallback_artifact
    assert optimized_artifact.to_dict() == fallback_artifact.to_dict()
    optimized_path = save_historical_replay_artifact(
        tmp_path / "optimized.json",
        optimized_artifact,
    )
    fallback_path = save_historical_replay_artifact(
        tmp_path / "fallback.json",
        fallback_artifact,
    )
    assert optimized_path.read_bytes() == fallback_path.read_bytes()

    optimized_experiment = create_historical_replay_experiment(
        HistoricalReplayExperimentSpecification(
            baseline=optimized_artifact,
            candidates=(
                HistoricalReplayArtifact.from_execution(optimized_candidate),
            ),
            software_revision=_COMPARISON_SOFTWARE,
        )
    )
    fallback_experiment = create_historical_replay_experiment(
        HistoricalReplayExperimentSpecification(
            baseline=fallback_artifact,
            candidates=(
                HistoricalReplayArtifact.from_execution(fallback_candidate),
            ),
            software_revision=_COMPARISON_SOFTWARE,
        )
    )
    assert optimized_experiment == fallback_experiment
    assert (
        optimized_experiment.specification.experiment_fingerprint
        == fallback_experiment.specification.experiment_fingerprint
    )
    assert tuple(
        comparison.comparison_fingerprint
        for comparison in optimized_experiment.comparisons
    ) == tuple(
        comparison.comparison_fingerprint
        for comparison in fallback_experiment.comparisons
    )


def test_precompute_is_not_json_serializable_and_does_not_expose_source() -> None:
    precompute = prepare_historical_observation_fingerprints(
        HistoricalPriceSeries(_prices(3)),
        (0, 2),
        interval="1day",
    )

    with pytest.raises(TypeError):
        json.dumps(precompute)
    assert "HistoricalPriceSeries" not in repr(precompute)
    assert "object at 0x" not in repr(precompute)
