from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from market_platform.structure import (
    ObservedPriceZone,
    PriceLevelCandidate,
    PriceLevelKind,
    PriceStructureConfig,
    PriceStructureService,
    PriceStructureStatus,
    PriceZoneObservation,
    create_price_zone,
)


def _timestamps(count: int) -> list[datetime]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return [start + timedelta(days=index) for index in range(count)]


def _price_frame(
    *,
    highs: list[float],
    lows: list[float],
    closes: list[float],
    timestamps: list[datetime] | None = None,
) -> pd.DataFrame:
    count = len(highs)
    return pd.DataFrame(
        {
            "timestamp": timestamps or _timestamps(count),
            "high": highs,
            "low": lows,
            "close": closes,
        }
    )


def _oscillating_frame() -> pd.DataFrame:
    return _price_frame(
        highs=[10.0, 12.0, 10.0, 13.0, 10.0, 14.0, 10.0, 13.0, 10.0],
        lows=[9.0, 8.0, 9.0, 7.0, 9.0, 6.0, 9.0, 7.0, 9.0],
        closes=[9.5, 10.0, 9.5, 10.0, 9.5, 10.0, 9.5, 10.0, 9.5],
    )


def _stage_four_config() -> PriceStructureConfig:
    return PriceStructureConfig(
        pivot_window=1,
        atr_period=3,
        zone_atr_multiplier=0.25,
    )


def test_analyze_completes_full_pipeline() -> None:
    snapshot = PriceStructureService().analyze(
        _oscillating_frame(),
        config=_stage_four_config(),
    )

    assert snapshot.status is PriceStructureStatus.OK
    assert snapshot.as_of == datetime(2026, 1, 9, tzinfo=UTC)
    assert snapshot.current_price == 9.5
    assert snapshot.atr is not None
    assert snapshot.atr > 0.0
    assert snapshot.candidates
    assert snapshot.observed_zones
    assert all(
        isinstance(observed, ObservedPriceZone)
        and isinstance(observed.observation, PriceZoneObservation)
        for observed in snapshot.observed_zones
    )


def test_analyze_uses_explicit_current_price() -> None:
    snapshot = PriceStructureService().analyze(
        _oscillating_frame(),
        config=_stage_four_config(),
        current_price=11.25,
    )

    assert snapshot.current_price == 11.25
    assert snapshot.as_of == datetime(2026, 1, 9, tzinfo=UTC)


def test_analyze_uses_close_at_latest_timestamp_by_default() -> None:
    prices = _oscillating_frame()
    prices.loc[8, "close"] = 12.5
    shuffled = prices.iloc[[8, 2, 6, 0, 7, 1, 5, 3, 4]].reset_index(drop=True)

    snapshot = PriceStructureService().analyze(
        shuffled,
        config=_stage_four_config(),
    )

    assert snapshot.as_of == datetime(2026, 1, 9, tzinfo=UTC)
    assert snapshot.current_price == 12.5


def test_analyze_empty_frame_returns_insufficient_data() -> None:
    prices = pd.DataFrame(columns=["timestamp", "high", "low", "close"])

    snapshot = PriceStructureService().analyze(prices)

    assert snapshot.status is PriceStructureStatus.INSUFFICIENT_DATA
    assert snapshot.as_of is None
    assert snapshot.current_price is None
    assert snapshot.candidates == ()
    assert snapshot.observed_zones == ()


def test_analyze_returns_insufficient_data_when_pivot_window_needs_more_bars() -> None:
    prices = _price_frame(
        highs=[10.0, 12.0, 10.0, 11.0],
        lows=[9.0, 8.0, 9.0, 8.5],
        closes=[9.5, 10.0, 9.5, 10.0],
    )

    snapshot = PriceStructureService().analyze(
        prices,
        config=PriceStructureConfig(
            pivot_window=2,
            atr_period=1,
            zone_atr_multiplier=0.25,
        ),
    )

    assert snapshot.status is PriceStructureStatus.INSUFFICIENT_DATA


def test_analyze_returns_insufficient_data_when_atr_period_needs_more_bars() -> None:
    prices = _price_frame(
        highs=[10.0, 12.0, 10.0, 13.0, 10.0],
        lows=[9.0, 8.0, 9.0, 7.0, 9.0],
        closes=[9.5, 10.0, 9.5, 10.0, 9.5],
    )

    snapshot = PriceStructureService().analyze(
        prices,
        config=PriceStructureConfig(
            pivot_window=1,
            atr_period=6,
            zone_atr_multiplier=0.25,
        ),
    )

    assert snapshot.status is PriceStructureStatus.INSUFFICIENT_DATA


def test_analyze_returns_no_pivots_for_sufficient_monotonic_data() -> None:
    prices = _price_frame(
        highs=[10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0],
        lows=[9.0, 10.0, 11.0, 12.0, 13.0, 14.0, 15.0],
        closes=[9.5, 10.5, 11.5, 12.5, 13.5, 14.5, 15.5],
    )

    snapshot = PriceStructureService().analyze(
        prices,
        config=_stage_four_config(),
    )

    assert snapshot.status is PriceStructureStatus.NO_PIVOTS
    assert snapshot.atr is None
    assert snapshot.candidates == ()


@pytest.mark.parametrize(("atr_value", "expected_atr"), [(None, None), (0.0, 0.0)])
def test_analyze_returns_volatility_unavailable_for_unusable_atr(
    atr_value: float | None,
    expected_atr: float | None,
) -> None:
    def calculate_unavailable_atr(
        prices: pd.DataFrame,
        *,
        period: int,
    ) -> float | None:
        del prices, period
        return atr_value

    service = PriceStructureService(atr_calculator=calculate_unavailable_atr)

    snapshot = service.analyze(
        _oscillating_frame(),
        config=_stage_four_config(),
    )

    assert snapshot.status is PriceStructureStatus.VOLATILITY_UNAVAILABLE
    assert snapshot.atr == expected_atr
    assert snapshot.candidates
    assert snapshot.observed_zones == ()


def test_analyze_passes_config_to_each_pipeline_stage() -> None:
    calls: dict[str, float | int] = {}
    timestamp = datetime(2026, 1, 2, tzinfo=UTC)
    candidate = PriceLevelCandidate(
        price=100.0,
        kind=PriceLevelKind.SWING_HIGH,
        observed_at=timestamp,
    )

    def detect_highs(
        prices: pd.DataFrame,
        *,
        window: int,
    ) -> tuple[PriceLevelCandidate, ...]:
        del prices
        calls["high_window"] = window
        return (candidate,)

    def detect_lows(
        prices: pd.DataFrame,
        *,
        window: int,
    ) -> tuple[PriceLevelCandidate, ...]:
        del prices
        calls["low_window"] = window
        return ()

    def calculate_test_atr(
        prices: pd.DataFrame,
        *,
        period: int,
    ) -> float | None:
        del prices
        calls["atr_period"] = period
        return 2.0

    def cluster_test_levels(
        candidates: tuple[PriceLevelCandidate, ...],
        *,
        atr: float,
        atr_multiplier: float,
    ) -> tuple:
        calls["candidate_count"] = len(candidates)
        calls["atr"] = atr
        calls["atr_multiplier"] = atr_multiplier
        return (create_price_zone(candidates),)

    config = PriceStructureConfig(
        pivot_window=2,
        atr_period=5,
        zone_atr_multiplier=0.75,
    )
    service = PriceStructureService(
        swing_high_detector=detect_highs,
        swing_low_detector=detect_lows,
        atr_calculator=calculate_test_atr,
        zone_clusterer=cluster_test_levels,
    )

    snapshot = service.analyze(
        _oscillating_frame(),
        config=config,
        current_price=100.0,
    )

    assert snapshot.status is PriceStructureStatus.OK
    assert calls == {
        "high_window": 2,
        "low_window": 2,
        "atr_period": 5,
        "candidate_count": 1,
        "atr": 2.0,
        "atr_multiplier": 0.75,
    }


def test_analyze_snapshot_classifies_injected_zones() -> None:
    timestamps = _timestamps(3)
    candidates = tuple(
        PriceLevelCandidate(
            price=price,
            kind=PriceLevelKind.SWING_HIGH,
            observed_at=timestamp,
        )
        for price, timestamp in zip((90.0, 100.0, 110.0), timestamps, strict=True)
    )

    def detect_levels(
        prices: pd.DataFrame,
        *,
        window: int,
    ) -> tuple[PriceLevelCandidate, ...]:
        del prices, window
        return candidates

    def cluster_individual_levels(
        values: tuple[PriceLevelCandidate, ...],
        *,
        atr: float,
        atr_multiplier: float,
    ) -> tuple:
        del atr, atr_multiplier
        return tuple(create_price_zone((candidate,)) for candidate in values)

    service = PriceStructureService(
        swing_high_detector=detect_levels,
        swing_low_detector=lambda prices, *, window: (),
        atr_calculator=lambda prices, *, period: 1.0,
        zone_clusterer=cluster_individual_levels,
    )

    snapshot = service.analyze(
        _oscillating_frame(),
        config=_stage_four_config(),
        current_price=100.0,
    )

    assert [observed.zone.midpoint for observed in snapshot.lower_zones] == [90.0]
    assert [observed.zone.midpoint for observed in snapshot.containing_zones] == [
        100.0
    ]
    assert [observed.zone.midpoint for observed in snapshot.upper_zones] == [110.0]


def test_analyze_is_independent_of_input_row_order() -> None:
    prices = _oscillating_frame()
    shuffled = prices.iloc[[5, 1, 8, 3, 0, 7, 2, 6, 4]].reset_index(drop=True)
    service = PriceStructureService()

    ordered_snapshot = service.analyze(prices, config=_stage_four_config())
    shuffled_snapshot = service.analyze(shuffled, config=_stage_four_config())

    assert shuffled_snapshot == ordered_snapshot


def test_analyze_does_not_mutate_input_frame() -> None:
    prices = _oscillating_frame().iloc[::-1].reset_index(drop=True)
    original = prices.copy(deep=True)

    PriceStructureService().analyze(prices, config=_stage_four_config())

    pd.testing.assert_frame_equal(prices, original)


def test_analyze_is_deterministic_for_same_input() -> None:
    prices = _oscillating_frame()
    service = PriceStructureService()

    first = service.analyze(prices, config=_stage_four_config())
    second = service.analyze(prices, config=_stage_four_config())

    assert first == second


@pytest.mark.parametrize("missing_column", ["timestamp", "high", "low", "close"])
def test_analyze_rejects_missing_required_columns(missing_column: str) -> None:
    prices = _oscillating_frame().drop(columns=missing_column)

    with pytest.raises(ValueError, match=f"missing required columns: {missing_column}"):
        PriceStructureService().analyze(prices, config=_stage_four_config())


def test_analyze_rejects_duplicate_timestamps() -> None:
    prices = _oscillating_frame()
    prices.loc[1, "timestamp"] = prices.loc[0, "timestamp"]

    with pytest.raises(ValueError, match="must not contain duplicate timestamps"):
        PriceStructureService().analyze(prices, config=_stage_four_config())


def test_analyze_rejects_high_below_low() -> None:
    prices = _oscillating_frame()
    prices.loc[0, ["high", "low"]] = [8.0, 9.0]

    with pytest.raises(ValueError, match="high must be greater than or equal to low"):
        PriceStructureService().analyze(prices, config=_stage_four_config())


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("high", float("nan"), "invalid high values"),
        ("low", float("inf"), "non-finite low values"),
        ("close", float("-inf"), "non-finite close values"),
    ],
)
def test_analyze_rejects_invalid_numeric_values(
    column: str,
    value: float,
    message: str,
) -> None:
    prices = _oscillating_frame()
    prices.loc[0, column] = value

    with pytest.raises(ValueError, match=message):
        PriceStructureService().analyze(prices, config=_stage_four_config())


@pytest.mark.parametrize("column", ["high", "low", "close"])
def test_analyze_rejects_bool_prices_before_pipeline_execution(column: str) -> None:
    prices = _oscillating_frame()
    prices[column] = prices[column].astype(object)
    prices.loc[0, column] = True

    with pytest.raises(TypeError, match=f"{column} must be numeric"):
        PriceStructureService().analyze(prices, config=_stage_four_config())


def test_analyze_rejects_invalid_timestamps() -> None:
    prices = _oscillating_frame()
    prices.loc[0, "timestamp"] = pd.NaT

    with pytest.raises(ValueError, match="invalid timestamp values"):
        PriceStructureService().analyze(prices, config=_stage_four_config())


@pytest.mark.parametrize(
    "current_price",
    [True, 0.0, -1.0, float("nan"), float("inf"), "100"],
)
def test_analyze_rejects_invalid_current_price(current_price: object) -> None:
    with pytest.raises((TypeError, ValueError), match="current_price"):
        PriceStructureService().analyze(
            _oscillating_frame(),
            config=_stage_four_config(),
            current_price=current_price,  # type: ignore[arg-type]
        )
