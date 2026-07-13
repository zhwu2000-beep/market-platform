from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import market_platform.research.interpretation as research_interpretation
from market_platform.research import (
    DIRECTIONAL_CURRENT_DRAWDOWN_SCALE,
    DIRECTIONAL_DISTANCE_FROM_MOVING_AVERAGE_SCALE,
    DIRECTIONAL_MOMENTUM_SCALE,
    DIRECTIONAL_TREND_SCALE,
    InterpretedSignal,
    InterpretedSignalState,
    SignalInterpretationRule,
    SignalRole,
    VolatilityAssessment,
    VolatilityState,
    calculate_research_composite_signal,
    interpret_directional_signals,
    interpret_market_signal,
    interpret_realized_volatility,
)
from market_platform.signals.models import MarketSignal

_TIMESTAMP_UTC = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
_TIMESTAMP_OFFSET = datetime(2026, 1, 1, 4, 0, tzinfo=timezone(timedelta(hours=4)))


def _raw_signal(
    name: str,
    value: float | None,
    *,
    symbol: str = "  msft  ",
    timestamp: datetime = _TIMESTAMP_OFFSET,
    parameters: dict[str, object] | None = None,
) -> MarketSignal:
    return MarketSignal(
        symbol=symbol,
        name=name,
        value=value,
        timestamp=timestamp,
        parameters=parameters or {"source": "test"},
    )


def _directional_scale_for_name(name: str) -> float:
    if name == "trend":
        return DIRECTIONAL_TREND_SCALE
    if name == "momentum":
        return DIRECTIONAL_MOMENTUM_SCALE
    if name == "current_drawdown":
        return DIRECTIONAL_CURRENT_DRAWDOWN_SCALE
    if name == "distance_from_moving_average":
        return DIRECTIONAL_DISTANCE_FROM_MOVING_AVERAGE_SCALE
    return DIRECTIONAL_TREND_SCALE


def _directional_rule(
    name: str = "trend",
    *,
    scale: float | None = None,
    methodology: str = "baseline_uncalibrated_directional_rescaling_v1",
) -> SignalInterpretationRule:
    return SignalInterpretationRule(
        signal_name=name,
        role=SignalRole.DIRECTIONAL,
        methodology=methodology,
        scale=_directional_scale_for_name(name) if scale is None else scale,
    )


def _interpreted_signal(
    name: str,
    score: float | None,
    *,
    raw_value: float | None = None,
    symbol: str = "msft",
    timestamp: datetime = _TIMESTAMP_UTC,
    methodology: str = "baseline_uncalibrated_directional_rescaling_v1",
    parameters: dict[str, object] | None = None,
) -> InterpretedSignal:
    state = (
        InterpretedSignalState.UNAVAILABLE
        if raw_value is None or score is None
        else InterpretedSignalState.POSITIVE
    )
    source_parameters = parameters or {"source": "test"}
    scale = _directional_scale_for_name(name)
    return InterpretedSignal(
        symbol=symbol,
        timestamp=timestamp,
        name=name,
        raw_value=raw_value,
        score=score,
        state=state,
        role=SignalRole.DIRECTIONAL,
        methodology=methodology,
        parameters={
            "signal_name": name,
            "role": SignalRole.DIRECTIONAL.value,
            "methodology": methodology,
            "scale": scale,
            "formula": "clamp(raw_value / scale, -1.0, 1.0)",
            "source_parameters": dict(source_parameters),
        },
    )


def test_default_directional_scales_are_exact() -> None:
    assert DIRECTIONAL_TREND_SCALE == 0.10
    assert DIRECTIONAL_MOMENTUM_SCALE == 0.20
    assert DIRECTIONAL_CURRENT_DRAWDOWN_SCALE == 0.20
    assert DIRECTIONAL_DISTANCE_FROM_MOVING_AVERAGE_SCALE == 0.10


@pytest.mark.parametrize(
    ("signal_name", "raw_value", "expected_score"),
    [
        ("trend", 0.05, 0.5),
        ("momentum", 0.10, 0.5),
        ("current_drawdown", -0.10, -0.5),
        ("distance_from_moving_average", 0.05, 0.5),
    ],
)
def test_directional_interpretation_realistic_scale_examples(
    signal_name: str,
    raw_value: float,
    expected_score: float,
) -> None:
    result = interpret_market_signal(
        _raw_signal(signal_name, raw_value),
        _directional_rule(signal_name),
    )

    assert result.score == pytest.approx(expected_score)
    expected_states = {
        "trend": InterpretedSignalState.POSITIVE,
        "momentum": InterpretedSignalState.POSITIVE,
        "current_drawdown": InterpretedSignalState.NEGATIVE,
        "distance_from_moving_average": InterpretedSignalState.POSITIVE,
    }
    assert result.state is expected_states[signal_name]


@pytest.mark.parametrize(
    ("signal_name", "raw_value", "expected_state"),
    [
        ("trend", -0.60, InterpretedSignalState.STRONGLY_NEGATIVE),
        ("trend", -0.20, InterpretedSignalState.NEGATIVE),
        ("trend", 0.0, InterpretedSignalState.NEUTRAL),
        ("trend", 0.199999, InterpretedSignalState.NEUTRAL),
        ("trend", 0.20, InterpretedSignalState.POSITIVE),
        ("trend", 0.60, InterpretedSignalState.STRONGLY_POSITIVE),
    ],
)
def test_directional_interpretation_boundary_behavior(
    signal_name: str,
    raw_value: float,
    expected_state: InterpretedSignalState,
) -> None:
    result = interpret_market_signal(
        _raw_signal(signal_name, raw_value),
        _directional_rule(signal_name, scale=1.0),
    )

    assert result.state is expected_state


def test_directional_interpretation_handles_missing_raw_value() -> None:
    result = interpret_market_signal(_raw_signal("trend", None), _directional_rule())

    assert result.raw_value is None
    assert result.score is None
    assert result.state is InterpretedSignalState.UNAVAILABLE


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), True])
def test_directional_interpretation_rejects_non_finite_and_bool_values(
    value: object,
) -> None:
    with pytest.raises((TypeError, ValueError)):
        interpret_market_signal(_raw_signal("trend", value), _directional_rule())  # type: ignore[arg-type]


def test_directional_interpretation_rejects_rule_name_mismatch() -> None:
    with pytest.raises(ValueError, match="rule.signal_name"):
        interpret_market_signal(
            _raw_signal("trend", 0.1),
            _directional_rule("momentum"),
        )


def test_directional_interpretation_parameters_include_metadata(
    ) -> None:
    parameters = {"source": "test", "nested": {"keep": True}}
    result = interpret_market_signal(
        _raw_signal("trend", 0.05, parameters=parameters),
        _directional_rule(),
    )

    assert result.parameters["scale"] == pytest.approx(0.10)
    assert result.parameters["formula"] == "clamp(raw_value / scale, -1.0, 1.0)"
    assert result.parameters["source_parameters"] == {
        "source": "test",
        "nested": {"keep": True},
    }
    assert result.parameters["source_parameters"] is not parameters


def test_interpreted_signal_normalizes_timezone_and_copies_parameters() -> None:
    parameters = {"source": "test", "nested": {"keep": True}}
    result = interpret_market_signal(
        _raw_signal("trend", 0.05, parameters=parameters),
        _directional_rule(),
    )
    parameters["source"] = "changed"

    assert result.timestamp == _TIMESTAMP_UTC
    assert result.timestamp.tzinfo is UTC
    assert result.parameters["source_parameters"] == {
        "source": "test",
        "nested": {"keep": True},
    }
    assert result.parameters["source_parameters"] is not parameters


@pytest.mark.parametrize(
    ("raw_value", "expected_state"),
    [
        (0.149, VolatilityState.LOW),
        (0.15, VolatilityState.NORMAL),
        (0.299, VolatilityState.NORMAL),
        (0.30, VolatilityState.HIGH),
    ],
)
def test_realized_volatility_state_boundaries(
    raw_value: float,
    expected_state: VolatilityState,
) -> None:
    result = interpret_realized_volatility(
        _raw_signal("realized_volatility", raw_value)
    )

    assert isinstance(result, VolatilityAssessment)
    assert result.raw_value == pytest.approx(raw_value)
    assert result.state is expected_state
    assert result.parameters["low_threshold"] == pytest.approx(0.15)
    assert result.parameters["high_threshold"] == pytest.approx(0.30)


def test_realized_volatility_handles_missing_value() -> None:
    result = interpret_realized_volatility(_raw_signal("realized_volatility", None))

    assert result.raw_value is None
    assert result.state is VolatilityState.UNAVAILABLE


@pytest.mark.parametrize(
    ("low_threshold", "high_threshold", "expected_message"),
    [
        (True, 0.30, "low_threshold"),
        (0.15, False, "high_threshold"),
        (float("nan"), 0.30, "finite"),
        (0.15, float("inf"), "finite"),
        (-0.1, 0.30, "must not be negative"),
        (0.30, 0.15, "less than high_threshold"),
    ],
)
def test_realized_volatility_rejects_invalid_thresholds(
    low_threshold: object,
    high_threshold: object,
    expected_message: str,
) -> None:
    with pytest.raises((TypeError, ValueError), match=expected_message):
        interpret_realized_volatility(  # type: ignore[arg-type]
            _raw_signal("realized_volatility", 0.2),
            low_threshold=low_threshold,
            high_threshold=high_threshold,
        )


def test_directly_constructed_negative_volatility_assessment_is_rejected() -> None:
    with pytest.raises(ValueError, match="must not be negative"):
        VolatilityAssessment(
            symbol="msft",
            timestamp=_TIMESTAMP_UTC,
            raw_value=-0.1,
            state=VolatilityState.LOW,
            methodology="baseline_realized_volatility_thresholds_v1",
            parameters={"source": "test"},
        )


def test_interpreted_signal_rejects_non_directional_roles() -> None:
    with pytest.raises(ValueError, match="SignalRole.DIRECTIONAL"):
        InterpretedSignal(
            symbol="msft",
            timestamp=_TIMESTAMP_UTC,
            name="trend",
            raw_value=0.1,
            score=0.1,
            state=InterpretedSignalState.POSITIVE,
            role=SignalRole.VOLATILITY,
            methodology="baseline_uncalibrated_directional_rescaling_v1",
            parameters={},
        )

    with pytest.raises(ValueError, match="SignalRole.DIRECTIONAL"):
        InterpretedSignal(
            symbol="msft",
            timestamp=_TIMESTAMP_UTC,
            name="trend",
            raw_value=0.1,
            score=0.1,
            state=InterpretedSignalState.POSITIVE,
            role=SignalRole.CONTEXTUAL,
            methodology="baseline_uncalibrated_directional_rescaling_v1",
            parameters={},
        )


@pytest.mark.parametrize(
    ("input_factory", "expected_names"),
    [
        (
            lambda: [
                _raw_signal("trend", 0.5),
                _raw_signal("context", 0.0),
                _raw_signal("momentum", -0.4),
            ],
            ("trend", "momentum"),
        ),
        (
            lambda: (
                _raw_signal("trend", 0.5),
                _raw_signal("context", 0.0),
                _raw_signal("momentum", -0.4),
            ),
            ("trend", "momentum"),
        ),
        (
            lambda: iter(
                [
                    _raw_signal("trend", 0.5),
                    _raw_signal("context", 0.0),
                    _raw_signal("momentum", -0.4),
                ]
            ),
            ("trend", "momentum"),
        ),
    ],
)
def test_directional_batch_preserves_order_and_ignores_unknown_signals(
    input_factory: object,
    expected_names: tuple[str, ...],
) -> None:
    interpreted = interpret_directional_signals(input_factory())  # type: ignore[misc]

    assert tuple(signal.name for signal in interpreted) == expected_names
    assert [signal.state for signal in interpreted] == [
        InterpretedSignalState.STRONGLY_POSITIVE,
        InterpretedSignalState.STRONGLY_NEGATIVE,
    ]


def test_directional_batch_rejects_duplicate_signal_names() -> None:
    signals = [_raw_signal("trend", 0.5), _raw_signal("trend", -0.2)]

    with pytest.raises(ValueError, match="unique"):
        interpret_directional_signals(signals)


@pytest.mark.parametrize(
    ("second_signal", "expected_message"),
    [
        (_raw_signal("momentum", 0.1, symbol="aapl"), "same symbol"),
        (
            _raw_signal(
                "momentum",
                0.1,
                timestamp=datetime(2026, 1, 1, 1, 0, tzinfo=UTC),
            ),
            "same timestamp",
        ),
    ],
)
def test_directional_batch_rejects_mismatched_symbol_or_timestamp(
    second_signal: MarketSignal,
    expected_message: str,
) -> None:
    with pytest.raises(ValueError, match=expected_message):
        interpret_directional_signals([_raw_signal("trend", 0.5), second_signal])


def test_directional_batch_rejects_invalid_custom_rule_mappings() -> None:
    valid_rule = _directional_rule()

    with pytest.raises(TypeError, match="Mapping"):
        interpret_directional_signals(
            [_raw_signal("trend", 0.5)],
            rules=[("trend", valid_rule)],  # type: ignore[arg-type]
        )

    with pytest.raises(TypeError, match="SignalInterpretationRule instances"):
        interpret_directional_signals(
            [_raw_signal("trend", 0.5)],
            rules={"trend": "bad"},  # type: ignore[arg-type]
        )

    with pytest.raises(ValueError, match="Mapping key must match rule.signal_name"):
        interpret_directional_signals(
            [_raw_signal("trend", 0.5)],
            rules={"momentum": valid_rule},
        )

    with pytest.raises(ValueError, match="SignalRole.DIRECTIONAL"):
        interpret_directional_signals(
            [_raw_signal("trend", 0.5)],
            rules={
                "trend": SignalInterpretationRule(
                    signal_name="trend",
                    role=SignalRole.CONTEXTUAL,
                    methodology="baseline_uncalibrated_directional_rescaling_v1",
                    scale=None,
                )
            },
        )


def test_custom_directional_rules_do_not_mutate_input_mapping() -> None:
    rules = {"trend": _directional_rule()}
    original = deepcopy(rules)

    interpret_directional_signals([_raw_signal("trend", 0.5)], rules=rules)

    assert rules == original


def test_default_directional_rules_are_not_mutated() -> None:
    before = research_interpretation._default_directional_rules()
    interpret_directional_signals(
        [
            _raw_signal("trend", 0.5),
            _raw_signal("momentum", -0.4),
            _raw_signal("current_drawdown", -0.1),
            _raw_signal("distance_from_moving_average", 0.2),
        ]
    )
    after = research_interpretation._default_directional_rules()

    assert before == after


def test_research_composite_uses_only_directional_signals_and_preserves_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_calculate_composite_signal(
        signals: object,
        weights: object,
        *,
        missing_policy: str = "exclude",
    ) -> MarketSignal:
        signal_list = list(signals)  # type: ignore[arg-type]
        captured["signals"] = signal_list
        captured["weights"] = dict(weights)  # type: ignore[arg-type]
        captured["missing_policy"] = missing_policy
        first = signal_list[0]
        return MarketSignal(
            symbol=first.symbol,
            name="composite_score",
            value=0.1,
            timestamp=first.timestamp,
            parameters={"stub": True},
        )

    monkeypatch.setattr(
        research_interpretation,
        "calculate_composite_signal",
        fake_calculate_composite_signal,
    )

    trend = _interpreted_signal("trend", 0.4, raw_value=0.4)
    momentum = _interpreted_signal("momentum", -0.2, raw_value=-0.2)
    volatility = SimpleNamespace(role=SignalRole.VOLATILITY)

    result = calculate_research_composite_signal([trend, volatility, momentum])

    assert result.name == "composite_score"
    assert result.symbol == "MSFT"
    assert result.value == pytest.approx(0.1)
    assert captured["missing_policy"] == "exclude"
    component_signals = captured["signals"]
    assert [signal.name for signal in component_signals] == ["trend", "momentum"]
    assert component_signals[0].parameters["scale"] == pytest.approx(0.10)
    assert component_signals[0].parameters["methodology"] == (
        "baseline_uncalibrated_directional_rescaling_v1"
    )
    assert component_signals[0].parameters["source_parameters"] == {"source": "test"}
    assert result.parameters == {"stub": True}


def test_research_composite_excludes_missing_scores_and_renormalizes_weights() -> None:
    trend = _interpreted_signal("trend", 0.4, raw_value=0.4)
    momentum = _interpreted_signal("momentum", None, raw_value=None)
    distance = _interpreted_signal("distance_from_moving_average", -0.2, raw_value=-0.2)

    result = calculate_research_composite_signal([trend, momentum, distance])

    assert result.value == pytest.approx(0.1)
    assert result.parameters["missing_signals"] == ["momentum"]
    assert result.parameters["normalized_weights"] == {
        "trend": pytest.approx(0.5),
        "distance_from_moving_average": pytest.approx(0.5),
    }


def test_research_composite_returns_none_when_all_scores_missing() -> None:
    result = calculate_research_composite_signal(
        [
            _interpreted_signal("trend", None, raw_value=None),
            _interpreted_signal("momentum", None, raw_value=None),
        ]
    )

    assert result.value is None
    assert result.parameters["missing_signals"] == ["trend", "momentum"]


def test_research_composite_supports_custom_weights() -> None:
    result = calculate_research_composite_signal(
        [
            _interpreted_signal("trend", 0.4, raw_value=0.4),
            _interpreted_signal("momentum", -0.2, raw_value=-0.2),
        ],
        weights={"trend": 2.0, "momentum": 1.0},
    )

    assert result.value == pytest.approx(0.2)
    assert result.parameters["configured_weights"] == {"trend": 2.0, "momentum": 1.0}
    assert result.parameters["normalized_weights"] == {
        "trend": pytest.approx(2.0 / 3.0),
        "momentum": pytest.approx(1.0 / 3.0),
    }


def test_research_composite_does_not_mutate_inputs() -> None:
    signals = [
        _interpreted_signal("trend", 0.4, raw_value=0.4),
        _interpreted_signal("momentum", -0.2, raw_value=-0.2),
    ]
    weights = {"trend": 2.0, "momentum": 1.0}
    original_signals = deepcopy(signals)
    original_weights = deepcopy(weights)

    calculate_research_composite_signal(signals, weights=weights)

    assert signals == original_signals
    assert weights == original_weights


@pytest.mark.parametrize(
    "model_factory",
    [
        lambda: _interpreted_signal("trend", 0.4, raw_value=0.4),
        lambda: VolatilityAssessment(
            symbol="msft",
            timestamp=_TIMESTAMP_UTC,
            raw_value=0.2,
            state=VolatilityState.NORMAL,
            methodology="baseline_realized_volatility_thresholds_v1",
            parameters={"source": "test"},
        ),
    ],
)
def test_json_serialization_is_predictable(model_factory: object) -> None:
    model = model_factory()  # type: ignore[misc]

    json.dumps(model.to_dict())


def test_package_level_imports_are_available() -> None:
    assert SignalRole.DIRECTIONAL.value == "directional"
    assert InterpretedSignalState.UNAVAILABLE.value == "unavailable"
    assert VolatilityState.HIGH.value == "high"
    assert isinstance(
        interpret_market_signal(
            _raw_signal("trend", 0.4),
            _directional_rule(),
        ),
        InterpretedSignal,
    )