from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, date, datetime, timedelta

import pandas as pd
import pytest

import market_platform.research as research
import market_platform.research.technical_analysis as technical_analysis_module
from market_platform._fingerprint import canonical_fingerprint
from market_platform.data.historical import HistoricalPriceSeries
from market_platform.research import (
    DAILY_RESEARCH_EVIDENCE_SCHEMA,
    DAILY_TECHNICAL_ANALYSIS_PROFILE_SCHEMA,
    TECHNICAL_ANALYSIS_SNAPSHOT_SCHEMA,
    DailyAnalysisSessionScope,
    DailyTechnicalAnalysisProfile,
    EmaAlignment,
    PriceAdjustmentPolicy,
    ResearchTimeframe,
    ResearchVolatilityReferences,
    TechnicalAnalysisComponent,
    TechnicalAnalysisQuality,
    TechnicalAnalysisSnapshot,
    TechnicalAnalysisUnavailable,
    TechnicalAnalysisUnavailableReason,
    TechnicalAnalysisWarning,
    TechnicalMomentumState,
    TechnicalTrendState,
    TunnelPosition,
    analyze_daily_technical_snapshot,
    construct_daily_technical_analysis_profile,
    prepare_completed_daily_price_series,
)
from market_platform.research.interpretation import VolatilityState
from market_platform.trading.instrument import TradingInstrumentIdentity

PRIOR_RESEARCH_EXPORTS = [
    "DIRECTIONAL_CURRENT_DRAWDOWN_SCALE",
    "DIRECTIONAL_DISTANCE_FROM_MOVING_AVERAGE_SCALE",
    "DIRECTIONAL_MOMENTUM_SCALE",
    "DIRECTIONAL_TREND_SCALE",
    "InterpretedSignal",
    "InterpretedSignalState",
    "DefaultResearchWorkflow",
    "HistoricalReplayResearchMemberSpecification",
    "HistoricalReplayResearchStateModelInstance",
    "HistoricalReplayResearchWorkflowCandidateResult",
    "HistoricalReplayResearchWorkflowFailureCode",
    "HistoricalReplayResearchWorkflowResult",
    "HistoricalReplayResearchWorkflowService",
    "HistoricalReplayResearchWorkflowSkipReason",
    "HistoricalReplayResearchWorkflowSpecification",
    "HistoricalReplayResearchWorkflowStatus",
    "HistoricalReplayResearchWorkflowStepKind",
    "HistoricalReplayResearchWorkflowStepResult",
    "HistoricalReplayResearchWorkflowStepStatus",
    "MarketView",
    "PositionAction",
    "PositionContext",
    "PriceContext",
    "PriceLevel",
    "PriceTarget",
    "ProbabilityEstimate",
    "ResearchAnalysis",
    "ResearchCompositeAssessment",
    "ResearchRequest",
    "ResearchResult",
    "ResearchInterpretationMode",
    "ResearchSignalComponent",
    "ResearchStatus",
    "ResearchStrategyAssessment",
    "ResearchStructureAssessment",
    "ResearchWarning",
    "ResearchWorkflow",
    "SignalInterpretationRule",
    "SignalRole",
    "StructuralTargetDirection",
    "StructuralTargetLevel",
    "StrategyCandidate",
    "VolatilityAssessment",
    "VolatilityState",
    "build_price_context",
    "build_structural_target_levels",
    "adapt_strategy_run_result",
    "calculate_research_composite_signal",
    "interpret_directional_signals",
    "interpret_market_signal",
    "interpret_realized_volatility",
]
APPENDED_RESEARCH_EXPORTS = [
    "DAILY_RESEARCH_EVIDENCE_SCHEMA",
    "DAILY_TECHNICAL_ANALYSIS_PROFILE_SCHEMA",
    "TECHNICAL_ANALYSIS_SNAPSHOT_SCHEMA",
    "CompletedDailyPriceSeries",
    "DailyAnalysisSessionScope",
    "DailyResearchEvidence",
    "DailyTechnicalAnalysisProfile",
    "EmaAlignment",
    "PriceAdjustmentPolicy",
    "ResearchTimeframe",
    "ResearchVolatilityReferences",
    "TechnicalAnalysisComponent",
    "TechnicalAnalysisQuality",
    "TechnicalAnalysisSnapshot",
    "TechnicalAnalysisUnavailable",
    "TechnicalAnalysisUnavailableReason",
    "TechnicalAnalysisWarning",
    "TechnicalMomentumState",
    "TechnicalTrendState",
    "TunnelPosition",
    "analyze_daily_technical_snapshot",
    "construct_daily_technical_analysis_profile",
    "prepare_completed_daily_price_series",
]
V071_RESEARCH_EXPORTS = [
    "DailyTechnicalResearchRequest",
    "DailyTechnicalResearchResult",
    "DailyTechnicalResearchWorkflow",
]
INSTRUMENT = TradingInstrumentIdentity("AAPL", "NASDAQ")


def completed(
    count: int,
    close_function: Callable[[int], float] = lambda index: 100.0 + index,
    *,
    lag_days: int = 1,
):
    start = date(2024, 1, 1)
    rows = []
    for index in range(count):
        close = float(close_function(index))
        rows.append(
            {
                "symbol": "AAPL",
                "timestamp": datetime.combine(
                    start + timedelta(days=index), datetime.min.time(), UTC
                ),
                "open": close,
                "high": close + 1.0,
                "low": max(close - 1.0, close / 2.0),
                "close": close,
                "volume": 1000.0 + index,
                "provider": "fixture",
            }
        )
    source = HistoricalPriceSeries(pd.DataFrame(rows))
    cutoff = start + timedelta(days=count - 1 + lag_days)
    analysis_as_of = datetime.combine(cutoff, datetime.min.time(), UTC).replace(hour=17)
    return prepare_completed_daily_price_series(
        prices=source,
        instrument=INSTRUMENT,
        timeframe=ResearchTimeframe.DAILY,
        session_scope=DailyAnalysisSessionScope.PROVIDER_DAILY_AGGREGATE,
        market_timezone="America/New_York",
        adjustment_policy=PriceAdjustmentPolicy.ADJUSTED,
        analysis_as_of=analysis_as_of,
    )


def snapshot(
    count: int,
    close_function: Callable[[int], float] = lambda index: 100.0 + index,
    *,
    lag_days: int = 1,
) -> TechnicalAnalysisSnapshot:
    return analyze_daily_technical_snapshot(
        completed_prices=completed(
            count, close_function=close_function, lag_days=lag_days
        ),
        profile=construct_daily_technical_analysis_profile(),
    )


def test_exact_research_exports_and_schema_inventory() -> None:
    assert research.__all__[:51] == PRIOR_RESEARCH_EXPORTS
    assert research.__all__[51:74] == APPENDED_RESEARCH_EXPORTS
    assert research.__all__[74:] == V071_RESEARCH_EXPORTS
    assert len(research.__all__) == 77
    assert [
        DAILY_RESEARCH_EVIDENCE_SCHEMA,
        DAILY_TECHNICAL_ANALYSIS_PROFILE_SCHEMA,
        TECHNICAL_ANALYSIS_SNAPSHOT_SCHEMA,
    ] == [
        "daily_research_evidence/v1",
        "daily_technical_analysis_profile/v1",
        "technical_analysis_snapshot/v1",
    ]


def test_fixed_profile_values_projection_and_fingerprint() -> None:
    profile = construct_daily_technical_analysis_profile()
    assert [field.name for field in fields(DailyTechnicalAnalysisProfile)] == [
        "profile_id",
        "profile_version",
        "ema_fast_period",
        "ema_slow_period",
        "tunnel_fast_period",
        "tunnel_slow_period",
        "macd_fast_period",
        "macd_slow_period",
        "macd_signal_period",
        "rsi_period",
        "atr_period",
        "minimum_bar_count",
        "stale_after_calendar_days",
        "realized_volatility_low_threshold",
        "realized_volatility_high_threshold",
        "rules_version",
        "schema_version",
        "fingerprint",
    ]
    assert (
        profile.profile_id,
        profile.profile_version,
        profile.ema_fast_period,
        profile.ema_slow_period,
        profile.tunnel_fast_period,
        profile.tunnel_slow_period,
        profile.macd_fast_period,
        profile.macd_slow_period,
        profile.macd_signal_period,
        profile.rsi_period,
        profile.atr_period,
        profile.minimum_bar_count,
        profile.stale_after_calendar_days,
        profile.realized_volatility_low_threshold,
        profile.realized_volatility_high_threshold,
        profile.rules_version,
    ) == (
        "daily_technical_analysis_default",
        "1.0.0",
        8,
        20,
        144,
        169,
        12,
        26,
        9,
        14,
        14,
        250,
        7,
        0.15,
        0.30,
        "daily_technical_analysis_rules/v1",
    )
    assert profile.fingerprint == canonical_fingerprint(profile._fingerprint_payload())
    with pytest.raises(TypeError):
        DailyTechnicalAnalysisProfile()
    object.__setattr__(profile, "minimum_bar_count", 251)
    object.__setattr__(
        profile, "fingerprint", canonical_fingerprint(profile._fingerprint_payload())
    )
    with pytest.raises(ValueError, match="fixed v1"):
        profile.to_dict()


def test_state_enum_inventories_are_exact() -> None:
    assert [value.value for value in TechnicalAnalysisQuality] == [
        "complete",
        "degraded",
    ]
    for kind in (TechnicalTrendState, TechnicalMomentumState, EmaAlignment):
        assert [value.value for value in kind] == [
            "bullish",
            "bearish",
            "mixed",
            "unavailable",
        ]
    assert [value.value for value in TunnelPosition] == [
        "above",
        "inside",
        "below",
        "unavailable",
    ]
    assert [value.value for value in TechnicalAnalysisComponent] == [
        "ema_8",
        "ema_20",
        "ema_144",
        "ema_169",
        "macd",
        "rsi_14",
        "wilder_atr_14",
        "atr_percent_14",
        "realized_volatility",
        "distance_from_ema20",
    ]
    assert [value.value for value in TechnicalAnalysisUnavailableReason] == [
        "insufficient_history"
    ]
    assert [value.value for value in TechnicalAnalysisWarning] == [
        "insufficient_profile_history",
        "stale_evidence",
    ]


def test_unavailable_and_reference_value_validation() -> None:
    value = TechnicalAnalysisUnavailable(
        TechnicalAnalysisComponent.EMA_8,
        TechnicalAnalysisUnavailableReason.INSUFFICIENT_HISTORY,
        8,
        7,
    )
    assert [field.name for field in fields(value)] == [
        "component",
        "reason",
        "required_bars",
        "available_bars",
    ]
    with pytest.raises(ValueError):
        TechnicalAnalysisUnavailable(
            TechnicalAnalysisComponent.EMA_8,
            TechnicalAnalysisUnavailableReason.INSUFFICIENT_HISTORY,
            8,
            8,
        )
    references = ResearchVolatilityReferences(
        None, None, None, None, None, None, None, 1.0
    )
    assert [field.name for field in fields(references)] == [
        "atr",
        "one_atr_below",
        "one_atr_above",
        "one_and_half_atr_below",
        "one_and_half_atr_above",
        "two_atr_below",
        "two_atr_above",
        "distance_from_ema20_percent",
    ]
    with pytest.raises(ValueError):
        ResearchVolatilityReferences(None, 1.0, None, None, None, None, None, None)


@pytest.mark.parametrize(
    ("bar_count", "missing"),
    [
        (1, 10),
        (14, 7),
        (15, 6),
        (21, 3),
        (34, 2),
        (169, 0),
        (249, 0),
        (250, 0),
    ],
)
def test_partial_availability_boundaries(bar_count: int, missing: int) -> None:
    result = snapshot(bar_count)
    assert len(result.unavailable) == missing
    assert [item.component for item in result.unavailable] == sorted(
        (item.component for item in result.unavailable),
        key=list(TechnicalAnalysisComponent).index,
    )
    expected_quality = (
        TechnicalAnalysisQuality.COMPLETE
        if bar_count == 250
        else TechnicalAnalysisQuality.DEGRADED
    )
    assert result.quality is expected_quality
    assert (
        TechnicalAnalysisWarning.INSUFFICIENT_PROFILE_HISTORY in result.warnings
    ) is (bar_count < 250)


def test_snapshot_fields_projection_fingerprint_and_immutability() -> None:
    result = snapshot(250)
    assert [field.name for field in fields(result)] == [
        "evidence",
        "profile",
        "latest_close",
        "ema_8",
        "ema_20",
        "ema_144",
        "ema_169",
        "ema_alignment",
        "tunnel_position",
        "macd_line",
        "macd_signal",
        "macd_histogram",
        "rsi_14",
        "wilder_atr_14",
        "atr_percent_14",
        "realized_volatility",
        "current_drawdown",
        "trend_state",
        "momentum_state",
        "volatility_state",
        "volatility_references",
        "quality",
        "unavailable",
        "warnings",
        "schema_version",
        "fingerprint",
    ]
    assert list(result.to_dict()) == [
        "schema_version",
        "evidence",
        "profile",
        "latest_close",
        "ema_8",
        "ema_20",
        "ema_144",
        "ema_169",
        "ema_alignment",
        "tunnel_position",
        "macd_line",
        "macd_signal",
        "macd_histogram",
        "rsi_14",
        "wilder_atr_14",
        "atr_percent_14",
        "realized_volatility",
        "current_drawdown",
        "trend_state",
        "momentum_state",
        "volatility_state",
        "volatility_references",
        "quality",
        "unavailable",
        "warnings",
        "fingerprint",
    ]
    assert result.fingerprint == canonical_fingerprint(result._fingerprint_payload())
    assert result.to_dict()["profile"] == result.profile.to_dict()
    assert (
        result._fingerprint_payload()["profile"]["fingerprint"]
        == result.profile.fingerprint
    )
    assert not hasattr(result, "__dict__")
    with pytest.raises(FrozenInstanceError):
        result.latest_close = 0.0  # type: ignore[misc]
    with pytest.raises(TypeError):
        TechnicalAnalysisSnapshot()


def test_flat_bullish_and_bearish_interpretations() -> None:
    flat = snapshot(250, lambda _: 100.0)
    assert flat.ema_alignment is EmaAlignment.MIXED
    assert flat.tunnel_position is TunnelPosition.INSIDE
    assert flat.trend_state is TechnicalTrendState.MIXED
    assert flat.momentum_state is TechnicalMomentumState.MIXED
    bullish = snapshot(250, lambda index: 100.0 + (index / 10.0) ** 2)
    assert bullish.ema_alignment is EmaAlignment.BULLISH
    assert bullish.tunnel_position is TunnelPosition.ABOVE
    assert bullish.trend_state is TechnicalTrendState.BULLISH
    assert bullish.momentum_state is TechnicalMomentumState.BULLISH
    bearish = snapshot(250, lambda index: 1000.0 - (index / 10.0) ** 2)
    assert bearish.ema_alignment is EmaAlignment.BEARISH
    assert bearish.tunnel_position is TunnelPosition.BELOW
    assert bearish.trend_state is TechnicalTrendState.BEARISH
    assert bearish.momentum_state is TechnicalMomentumState.BEARISH


@pytest.mark.parametrize(
    ("return_size", "state"),
    [
        (0.0, VolatilityState.LOW),
        (0.01, VolatilityState.NORMAL),
        (0.03, VolatilityState.HIGH),
    ],
)
def test_volatility_interpretation_threshold_bands(
    return_size: float, state: VolatilityState
) -> None:
    def close(index: int) -> float:
        return 100.0 * math.exp(return_size if index % 2 else 0.0)

    assert snapshot(250, close).volatility_state is state


def test_research_volatility_reference_arithmetic() -> None:
    result = snapshot(250)
    references = result.volatility_references
    assert references.atr == result.wilder_atr_14
    assert references.one_atr_below == result.latest_close - references.atr
    assert references.one_atr_above == result.latest_close + references.atr
    assert references.one_and_half_atr_below == (
        result.latest_close - 1.5 * references.atr
    )
    assert references.two_atr_above == result.latest_close + 2.0 * references.atr
    assert references.distance_from_ema20_percent == (
        100.0 * (result.latest_close / result.ema_20 - 1.0)
    )


def test_freshness_warning_is_orthogonal_to_complete_quality() -> None:
    result = snapshot(250, lag_days=8)
    assert result.quality is TechnicalAnalysisQuality.COMPLETE
    assert result.warnings == (TechnicalAnalysisWarning.STALE_EVIDENCE,)


def test_deterministic_rebuild_and_bounded_retention() -> None:
    first = snapshot(250)
    second = snapshot(250)
    assert first == second
    assert first.to_dict() == second.to_dict()
    field_names = {field.name for field in fields(first)}
    assert "_prices" not in field_names
    assert "completed_prices" not in field_names
    assert "provider" not in field_names
    assert "frame" not in field_names
    assert not any(
        isinstance(getattr(first, name), pd.DataFrame) for name in field_names
    )


def test_snapshot_rejects_nested_arithmetic_contradiction() -> None:
    result = snapshot(250)
    references = result.volatility_references
    object.__setattr__(references, "one_atr_above", references.one_atr_above + 1.0)
    object.__setattr__(
        result, "fingerprint", canonical_fingerprint(result._fingerprint_payload())
    )
    with pytest.raises(ValueError, match="arithmetic"):
        result.to_dict()


def test_coherent_self_contained_snapshot_rewrite_remains_valid() -> None:
    result = snapshot(250)
    object.__setattr__(result.evidence, "provider", "rewritten")
    object.__setattr__(
        result.evidence,
        "fingerprint",
        canonical_fingerprint(result.evidence._fingerprint_payload()),
    )
    object.__setattr__(
        result, "fingerprint", canonical_fingerprint(result._fingerprint_payload())
    )
    assert result.to_dict()["evidence"]["provider"] == "rewritten"


def test_analyzer_revalidates_carrier_profile_and_argument_types() -> None:
    carrier = completed(250)
    profile = construct_daily_technical_analysis_profile()
    object.__setattr__(carrier.evidence, "bar_count", 249)
    with pytest.raises(ValueError):
        analyze_daily_technical_snapshot(
            completed_prices=carrier,
            profile=profile,
        )
    with pytest.raises(TypeError):
        analyze_daily_technical_snapshot(
            completed_prices=object(),  # type: ignore[arg-type]
            profile=construct_daily_technical_analysis_profile(),
        )


def test_snapshot_has_no_execution_or_signal_artifacts() -> None:
    result = snapshot(250)
    projection = result.to_dict()
    forbidden = {
        "buy",
        "sell",
        "confidence",
        "trading_signal",
        "order_intent",
        "risk_decision",
        "execution",
        "stop_loss",
    }
    assert forbidden.isdisjoint(projection)


class StrSubclass(str):
    pass


def _refingerprint_snapshot(value: TechnicalAnalysisSnapshot) -> None:
    object.__setattr__(
        value, "fingerprint", canonical_fingerprint(value._fingerprint_payload())
    )


def test_analyzer_rejects_deleted_nested_evidence_fingerprint() -> None:
    carrier = completed(250)
    object.__delattr__(carrier.evidence, "fingerprint")
    with pytest.raises(ValueError, match="missing retained field fingerprint"):
        analyze_daily_technical_snapshot(
            completed_prices=carrier,
            profile=construct_daily_technical_analysis_profile(),
        )


def test_snapshot_rejects_refingerprinted_macd_histogram_contradiction() -> None:
    result = snapshot(250)
    assert result.macd_histogram is not None
    object.__setattr__(result, "macd_histogram", result.macd_histogram + 1.0)
    _refingerprint_snapshot(result)
    with pytest.raises(ValueError, match="MACD histogram"):
        result.to_dict()


def test_snapshot_rejects_refingerprinted_atr_percent_contradiction() -> None:
    result = snapshot(250)
    assert result.atr_percent_14 is not None
    object.__setattr__(result, "atr_percent_14", result.atr_percent_14 + 1.0)
    _refingerprint_snapshot(result)
    with pytest.raises(ValueError, match="ATR percent"):
        result.to_dict()


def test_snapshot_rejects_atr_percent_without_atr() -> None:
    result = snapshot(1)
    object.__setattr__(result, "atr_percent_14", 1.0)
    _refingerprint_snapshot(result)
    with pytest.raises(ValueError, match="ATR percent"):
        result.to_dict()


@pytest.mark.parametrize("drawdown", [-1.0, -1.0000001, -2.0])
def test_snapshot_rejects_impossible_current_drawdown(drawdown: float) -> None:
    result = snapshot(250)
    object.__setattr__(result, "current_drawdown", drawdown)
    _refingerprint_snapshot(result)
    with pytest.raises(ValueError, match="drawdown"):
        result.to_dict()


def test_retained_negative_zero_is_rejected() -> None:
    result = snapshot(250)
    object.__setattr__(result, "current_drawdown", -0.0)
    _refingerprint_snapshot(result)
    with pytest.raises(ValueError, match="canonical finite float"):
        result.to_dict()

    result = snapshot(250)
    references = result.volatility_references
    object.__setattr__(references, "distance_from_ema20_percent", -0.0)
    with pytest.raises(ValueError, match="canonical finite float"):
        result.to_dict()


@pytest.mark.parametrize("field_name", ["schema_version", "fingerprint"])
def test_profile_rejects_str_subclass_schema_and_fingerprint(
    field_name: str,
) -> None:
    profile = construct_daily_technical_analysis_profile()
    object.__setattr__(profile, field_name, StrSubclass(getattr(profile, field_name)))
    if field_name == "schema_version":
        object.__setattr__(
            profile,
            "fingerprint",
            canonical_fingerprint(profile._fingerprint_payload()),
        )
    with pytest.raises(ValueError):
        profile.to_dict()


@pytest.mark.parametrize("field_name", ["schema_version", "fingerprint"])
def test_snapshot_rejects_str_subclass_schema_and_fingerprint(
    field_name: str,
) -> None:
    result = snapshot(250)
    object.__setattr__(result, field_name, StrSubclass(getattr(result, field_name)))
    if field_name == "schema_version":
        _refingerprint_snapshot(result)
    with pytest.raises(ValueError):
        result.to_dict()


def test_snapshot_rejects_nested_evidence_str_subclass() -> None:
    result = snapshot(250)
    object.__setattr__(
        result.evidence,
        "fingerprint",
        StrSubclass(result.evidence.fingerprint),
    )
    with pytest.raises(ValueError):
        result.to_dict()


@pytest.mark.parametrize(
    ("bar_count", "expected_components"),
    [
        (1, tuple(TechnicalAnalysisComponent)),
        (
            14,
            (
                TechnicalAnalysisComponent.EMA_20,
                TechnicalAnalysisComponent.EMA_144,
                TechnicalAnalysisComponent.EMA_169,
                TechnicalAnalysisComponent.MACD,
                TechnicalAnalysisComponent.RSI_14,
                TechnicalAnalysisComponent.REALIZED_VOLATILITY,
                TechnicalAnalysisComponent.DISTANCE_FROM_EMA20,
            ),
        ),
        (
            15,
            (
                TechnicalAnalysisComponent.EMA_20,
                TechnicalAnalysisComponent.EMA_144,
                TechnicalAnalysisComponent.EMA_169,
                TechnicalAnalysisComponent.MACD,
                TechnicalAnalysisComponent.REALIZED_VOLATILITY,
                TechnicalAnalysisComponent.DISTANCE_FROM_EMA20,
            ),
        ),
        (
            21,
            (
                TechnicalAnalysisComponent.EMA_144,
                TechnicalAnalysisComponent.EMA_169,
                TechnicalAnalysisComponent.MACD,
            ),
        ),
        (
            34,
            (
                TechnicalAnalysisComponent.EMA_144,
                TechnicalAnalysisComponent.EMA_169,
            ),
        ),
        (169, ()),
        (249, ()),
        (250, ()),
    ],
)
def test_exact_unavailable_component_identities(
    bar_count: int,
    expected_components: tuple[TechnicalAnalysisComponent, ...],
) -> None:
    result = snapshot(bar_count)
    assert tuple(item.component for item in result.unavailable) == expected_components
    assert all(item.available_bars == bar_count for item in result.unavailable)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0.15, VolatilityState.NORMAL),
        (0.30, VolatilityState.HIGH),
    ],
)
def test_exact_volatility_interpretation_boundaries(
    value: float, expected: VolatilityState
) -> None:
    assert technical_analysis_module._volatility_state(value, 0.15, 0.30) is expected
