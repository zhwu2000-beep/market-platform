from __future__ import annotations

import json
from dataclasses import MISSING, FrozenInstanceError, fields
from datetime import UTC, datetime

import pytest

from market_platform.research import (
    MarketView,
    PositionAction,
    PositionContext,
    PriceLevel,
    PriceTarget,
    ProbabilityEstimate,
    ResearchAnalysis,
    ResearchCompositeAssessment,
    ResearchRequest,
    ResearchResult,
    ResearchSignalComponent,
    ResearchStatus,
    ResearchWarning,
    ResearchWorkflow,
    StrategyCandidate,
)

_FIXED_AS_OF = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)


def _request() -> ResearchRequest:
    return ResearchRequest(
        symbol="  msft  ",
        horizon_days=20,
        provider="polygon",
        as_of=_FIXED_AS_OF,
    )


def _price_target() -> PriceTarget:
    return PriceTarget(
        horizon_days=20,
        lower=100.0,
        central=110.0,
        upper=120.0,
        methodology=("trend", "momentum"),
        confidence=0.7,
    )


def _probability() -> ProbabilityEstimate:
    return ProbabilityEstimate(
        event="close_above_target",
        horizon_days=20,
        probability=0.65,
        methodology="historical-frequency",
        sample_size=100,
        model_version="v1",
    )


def _price_level() -> PriceLevel:
    return PriceLevel(
        lower=95.0,
        upper=97.0,
        level_type="support",
        strength=0.4,
        sources=("trend",),
    )


def _position_action() -> PositionAction:
    return PositionAction(
        action_type="hold",
        rationale="maintain exposure",
        trigger_price=105.0,
        invalidation_price=90.0,
    )


def _strategy_candidate() -> StrategyCandidate:
    return StrategyCandidate(
        strategy_type="covered_call",
        objective="generate income",
        rationale="balanced thesis",
        suitability_score=0.6,
        max_profit=5.0,
        max_loss=3.0,
        breakeven=(102.0,),
        entry_conditions=("above support",),
        exit_conditions=("below invalidation",),
        rejection_reasons=("too volatile",),
    )


def _result(**overrides: object) -> ResearchResult:
    payload = {
        "request": _request(),
        "status": ResearchStatus.OK,
        "model_version": "research-v1",
        "market_view": MarketView(
            direction="bullish",
            strength="moderate",
            trend_state="uptrend",
            momentum_state="improving",
            volatility_state="high",
            price_structure="higher_highs",
            confidence=0.8,
        ),
        "price_targets": (_price_target(),),
        "probabilities": (_probability(),),
        "price_levels": (_price_level(),),
        "position_actions": (_position_action(),),
        "strategy_candidates": (_strategy_candidate(),),
        "warnings": (ResearchWarning(code="low_confidence", message="tentative"),),
        "summary": "Research summary",
    }
    payload.update(overrides)
    return ResearchResult(**payload)


def _analysis(
    *,
    volatility_state: str | None,
    volatility_value: float | None,
) -> ResearchAnalysis:
    composite = ResearchCompositeAssessment(
        score=0.25,
        classification="bullish",
        included_signals=("trend",),
        missing_signals=(),
        configured_weights={"trend": 1.0},
        normalized_weights={"trend": 1.0},
        component_contributions={"trend": 0.25},
        methodology="baseline_uncalibrated_composite_v1",
    )
    return ResearchAnalysis(
        symbol="msft",
        timestamp=_FIXED_AS_OF,
        components=(
            ResearchSignalComponent(
                name="trend",
                raw_value=0.05,
                score=0.5,
                state="positive",
                role="directional",
                methodology="baseline_uncalibrated_directional_rescaling_v1",
                parameters={
                    "scale": 0.10,
                    "formula": "clamp(raw_value / scale, -1.0, 1.0)",
                },
            ),
        ),
        volatility_state=volatility_state,
        volatility_value=volatility_value,
        composite=composite,
    )


def test_research_request_normalizes_symbol() -> None:
    request = _request()

    assert request.symbol == "MSFT"
    assert request.horizon_days == 20
    assert request.provider == "polygon"
    assert request.as_of == _FIXED_AS_OF


def test_research_result_defaults_are_empty_tuples() -> None:
    result = ResearchResult(
        request=_request(),
        status=ResearchStatus.DEGRADED,
        model_version="research-v1",
    )

    assert result.market_view is None
    assert result.price_targets == ()
    assert result.probabilities == ()
    assert result.price_levels == ()
    assert result.position_actions == ()
    assert result.strategy_candidates == ()
    assert result.warnings == ()


def test_research_models_are_immutable() -> None:
    request = _request()

    with pytest.raises(FrozenInstanceError):
        request.symbol = "AAPL"  # type: ignore[misc]


def test_markerview_text_is_stripped() -> None:
    view = MarketView(
        direction=" bullish ",
        strength=" moderate ",
        trend_state=" trending ",
        momentum_state=" improving ",
        volatility_state=" high ",
        price_structure=" higher_highs ",
        confidence=0.5,
    )

    assert view.direction == "bullish"
    assert view.strength == "moderate"
    assert view.trend_state == "trending"
    assert view.momentum_state == "improving"
    assert view.volatility_state == "high"
    assert view.price_structure == "higher_highs"


@pytest.mark.parametrize(
    ("volatility_state", "volatility_value", "expected_state", "expected_value"),
    [
        (None, None, None, None),
        ("unavailable", None, "unavailable", None),
        ("low", 0.1, "low", 0.1),
        ("normal", 0.2, "normal", 0.2),
        ("high", 0.3, "high", 0.3),
    ],
)
def test_research_analysis_accepts_valid_volatility_combinations(
    volatility_state: str | None,
    volatility_value: float | None,
    expected_state: str | None,
    expected_value: float | None,
) -> None:
    analysis = _analysis(
        volatility_state=volatility_state,
        volatility_value=volatility_value,
    )

    assert analysis.volatility_state == expected_state
    assert analysis.volatility_value == expected_value


@pytest.mark.parametrize(
    ("volatility_state", "volatility_value", "expected_exception", "expected_message"),
    [
        ("low", None, ValueError, "must be provided"),
        ("normal", None, ValueError, "must be provided"),
        ("high", None, ValueError, "must be provided"),
        ("unavailable", 0.1, ValueError, "must be None"),
        (None, 0.1, ValueError, "must be None"),
        ("mystery", 0.1, ValueError, "one of: low, normal, high, unavailable"),
        ("low", -0.1, ValueError, "must not be negative"),
        ("low", float("inf"), ValueError, "must be finite"),
        ("low", True, TypeError, "must be numeric"),
        (True, 0.1, TypeError, "volatility_state must be a string"),
    ],
)
def test_research_analysis_rejects_invalid_volatility_combinations(
    volatility_state: object,
    volatility_value: object,
    expected_exception: type[Exception],
    expected_message: str,
) -> None:
    with pytest.raises(expected_exception, match=expected_message):
        _analysis(
            volatility_state=volatility_state,  # type: ignore[arg-type]
            volatility_value=volatility_value,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("direction", "   "),
        ("strength", ""),
        ("trend_state", 1),
        ("momentum_state", True),
        ("volatility_state", b"up"),
    ],
)
def test_markerview_rejects_invalid_optional_text(
    field_name: str,
    value: object,
) -> None:
    kwargs = {field_name: value}

    with pytest.raises((TypeError, ValueError)):
        MarketView(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("factory", "expected_message"),
    [
        (
            lambda: ResearchRequest(symbol="", horizon_days=1),
            "symbol must not be empty",
        ),
        (
            lambda: ResearchRequest(symbol="MSFT", horizon_days=0),
            "horizon_days must be positive",
        ),
        (
            lambda: PriceTarget(
                horizon_days=1,
                lower=10.0,
                central=9.0,
                upper=11.0,
                methodology=("model",),
            ),
            "lower <= central <= upper",
        ),
        (
            lambda: PriceLevel(lower=2.0, upper=1.0, level_type="support"),
            "lower <= upper",
        ),
        (
            lambda: ProbabilityEstimate(
                event="event",
                horizon_days=1,
                probability=1.1,
                methodology="model",
            ),
            r"within \[0\.0, 1\.0\]",
        ),
        (
            lambda: ProbabilityEstimate(
                event="event",
                horizon_days=1,
                probability=0.5,
                sample_size=-1,
                methodology="model",
            ),
            "sample_size must not be negative",
        ),
        (
            lambda: PositionContext(shares=-1),
            "shares must not be negative",
        ),
        (
            lambda: PositionContext(shares=1, available_cash=-1.0),
            "available_cash must not be negative",
        ),
        (
            lambda: MarketView(confidence=1.1),
            r"within \[0\.0, 1\.0\]",
        ),
        (
            lambda: PriceTarget(
                horizon_days=1,
                lower=1.0,
                central=1.0,
                upper=1.0,
                methodology=("model",),
                confidence=1.1,
            ),
            r"within \[0\.0, 1\.0\]",
        ),
        (
            lambda: PriceLevel(
                lower=0.0,
                upper=1.0,
                level_type="support",
                strength=1.1,
            ),
            r"within \[0\.0, 1\.0\]",
        ),
        (
            lambda: StrategyCandidate(
                strategy_type="buy",
                objective="test",
                rationale="valid",
                suitability_score=1.1,
            ),
            r"within \[0\.0, 1\.0\]",
        ),
        (
            lambda: StrategyCandidate(
                strategy_type="buy",
                objective="test",
                rationale="valid",
                max_profit=-1.0,
            ),
            "max_profit must not be negative",
        ),
        (
            lambda: StrategyCandidate(
                strategy_type="buy",
                objective="test",
                rationale="valid",
                breakeven=(1.0, -1.0),
            ),
            "breakeven must not be negative",
        ),
        (
            lambda: ResearchResult(
                request=_request(),
                status=ResearchStatus.OK,
                model_version="",
            ),
            "model_version must not be empty",
        ),
        (
            lambda: ResearchWarning(code="", message="x"),
            "code must not be empty",
        ),
        (
            lambda: PositionAction(action_type="", rationale="x"),
            "action_type must not be empty",
        ),
        (
            lambda: ProbabilityEstimate(
                event="event",
                horizon_days=1,
                probability=0.5,
                methodology="",
            ),
            "methodology must not be empty",
        ),
    ],
)
def test_research_validation_boundaries(
    factory: object,
    expected_message: str,
) -> None:
    with pytest.raises((TypeError, ValueError), match=expected_message):
        factory()  # type: ignore[operator]


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("price_targets", "not-a-tuple"),
        ("probabilities", "not-a-tuple"),
        ("price_levels", "not-a-tuple"),
        ("position_actions", "not-a-tuple"),
        ("strategy_candidates", "not-a-tuple"),
        ("warnings", "not-a-tuple"),
    ],
)
def test_research_result_rejects_plain_strings_for_tuple_fields(
    field_name: str,
    value: object,
) -> None:
    kwargs = {field_name: value}

    with pytest.raises(TypeError):
        _result(**kwargs)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("price_targets", ("bad",)),
        ("probabilities", ("bad",)),
        ("price_levels", ("bad",)),
        ("position_actions", ("bad",)),
        ("strategy_candidates", ("bad",)),
        ("warnings", ("bad",)),
    ],
)
def test_research_result_rejects_wrong_element_types_for_tuple_fields(
    field_name: str,
    value: object,
) -> None:
    kwargs = {field_name: value}

    with pytest.raises(TypeError):
        _result(**kwargs)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("price_targets", [_price_target()]),
        ("probabilities", [_probability()]),
        ("price_levels", [_price_level()]),
        ("position_actions", [_position_action()]),
        ("strategy_candidates", [_strategy_candidate()]),
        ("warnings", [ResearchWarning(code="warn", message="note")]),
    ],
)
def test_research_result_normalizes_list_inputs_to_tuples(
    field_name: str,
    value: object,
) -> None:
    result = _result(**{field_name: value})

    field_value = getattr(result, field_name)
    assert isinstance(field_value, tuple)
    assert len(field_value) == 1


def test_research_result_preserves_nested_object_identity() -> None:
    target = _price_target()
    probability = _probability()
    price_level = _price_level()
    action = _position_action()
    candidate = _strategy_candidate()
    warning = ResearchWarning(code="low_confidence", message="tentative")
    market_view = MarketView(direction="bullish", strength="moderate")

    result = _result(
        market_view=market_view,
        price_targets=[target],
        probabilities=[probability],
        price_levels=[price_level],
        position_actions=[action],
        strategy_candidates=[candidate],
        warnings=[warning],
    )

    assert result.market_view is market_view
    assert result.price_targets[0] is target
    assert result.probabilities[0] is probability
    assert result.price_levels[0] is price_level
    assert result.position_actions[0] is action
    assert result.strategy_candidates[0] is candidate
    assert result.warnings[0] is warning


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("market_view", "not-a-view"),
        ("market_view", 1),
    ],
)
def test_research_result_rejects_invalid_market_view_type(
    field_name: str,
    value: object,
) -> None:
    kwargs = {field_name: value}

    with pytest.raises(TypeError, match="market_view must be a MarketView or None"):
        _result(**kwargs)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("willing_to_add", 0),
        ("willing_to_add", 1),
        ("willing_to_be_assigned", 0),
        ("willing_to_be_assigned", 1),
    ],
)
def test_position_context_rejects_non_bool_optional_flags(
    field_name: str,
    value: object,
) -> None:
    kwargs = {field_name: value}

    with pytest.raises(TypeError, match="bool or None"):
        PositionContext(shares=0, **kwargs)  # type: ignore[arg-type]


def test_required_constructor_fields_do_not_expose_empty_defaults() -> None:
    required_fields = {
        "PriceTarget": {"methodology"},
        "ProbabilityEstimate": {"methodology"},
        "StrategyCandidate": {"rationale"},
        "ResearchResult": {"model_version"},
    }

    for model_name, field_names in required_fields.items():
        model_fields = {field.name: field for field in fields(globals()[model_name])}
        for field_name in field_names:
            assert model_fields[field_name].default is MISSING


def test_json_dumps_of_research_result_dict_succeeds() -> None:
    result = _result()

    json.dumps(result.to_dict())


def test_research_result_serialization_is_nested_and_json_compatible() -> None:
    result = _result()
    payload = result.to_dict()

    assert payload["status"] == "ok"
    assert payload["request"]["symbol"] == "MSFT"
    assert payload["request"]["as_of"] == _FIXED_AS_OF.isoformat()
    assert payload["market_view"]["direction"] == "bullish"
    assert payload["market_view"]["confidence"] == 0.8
    assert payload["price_targets"][0]["methodology"] == ["trend", "momentum"]
    assert payload["warnings"][0]["code"] == "low_confidence"
    assert payload["model_version"] == "research-v1"


def test_enum_serialization_uses_enum_values() -> None:
    result = ResearchResult(
        request=_request(),
        status=ResearchStatus.FAILED,
        model_version="v1",
    )

    assert result.to_dict()["status"] == "failed"


def test_bool_is_rejected_for_numeric_and_integer_fields() -> None:
    with pytest.raises(TypeError):
        ResearchRequest(symbol="MSFT", horizon_days=True)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        PositionContext(shares=True)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        PriceTarget(
            horizon_days=1,
            lower=True,  # type: ignore[arg-type]
            central=1.0,
            upper=1.0,
            methodology=("model",),
        )
    with pytest.raises(TypeError):
        ProbabilityEstimate(
            event="event",
            horizon_days=1,
            probability=True,  # type: ignore[arg-type]
            methodology="model",
        )


def test_nan_and_infinities_are_rejected() -> None:
    with pytest.raises(ValueError):
        ProbabilityEstimate(
            event="event",
            horizon_days=1,
            probability=float("nan"),
            methodology="model",
        )
    with pytest.raises(ValueError):
        PriceTarget(
            horizon_days=1,
            lower=float("inf"),
            central=1.0,
            upper=1.0,
            methodology=("model",),
        )
    with pytest.raises(ValueError):
        PriceLevel(
            lower=0.0,
            upper=float("-inf"),
            level_type="support",
        )


def test_package_level_imports_are_available() -> None:
    request = ResearchRequest(symbol="msft", horizon_days=5)

    assert request.symbol == "MSFT"
    assert ResearchStatus.OK.value == "ok"


def test_workflow_protocol_is_importable_and_runtime_checkable() -> None:
    class _Workflow:
        def run(
            self,
            request: ResearchRequest,
            position: PositionContext | None = None,
        ) -> ResearchResult:
            return ResearchResult(
                request=request,
                status=ResearchStatus.OK,
                model_version="v1",
            )

    workflow = _Workflow()

    assert isinstance(workflow, ResearchWorkflow)
