from __future__ import annotations

import asyncio
import inspect
import json
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any

import pandas as pd
import pytest

import market_platform.research.workflow as research_workflow
from market_platform.research import (
    DefaultResearchWorkflow,
    InterpretedSignal,
    InterpretedSignalState,
    PositionContext,
    ResearchAnalysis,
    ResearchCompositeAssessment,
    ResearchRequest,
    ResearchResult,
    ResearchSignalComponent,
    ResearchStatus,
    ResearchWorkflow,
    SignalRole,
    VolatilityAssessment,
    VolatilityState,
)
from market_platform.research.interpretation import calculate_research_composite_signal
from market_platform.signals.models import MarketSignal, MarketSignalSnapshot

_REQUEST_AS_OF = datetime(2026, 1, 5, 1, 0, tzinfo=timezone(timedelta(hours=14)))
_CLOCK_NOW = datetime(2026, 1, 10, 12, 0, tzinfo=UTC)
_SNAPSHOT_TIMESTAMP = datetime(2026, 1, 10, 12, 0, tzinfo=UTC)


class FakeMarketDataService:
    def __init__(self, frame: pd.DataFrame) -> None:
        self.frame = frame
        self.calls: list[dict[str, object]] = []

    async def get_daily_prices(
        self,
        symbol: str,
        start: date,
        end: date,
        provider: str | None = None,
    ) -> pd.DataFrame:
        self.calls.append(
            {
                "symbol": symbol,
                "start": start,
                "end": end,
                "provider": provider,
            }
        )
        return self.frame


class _FakeWorkflow:
    async def run(
        self,
        request: ResearchRequest,
        position: PositionContext | None = None,
    ) -> ResearchResult:
        del position
        return ResearchResult(
            request=request,
            status=ResearchStatus.OK,
            model_version="v1",
        )


def _request(*, as_of: datetime | None = _REQUEST_AS_OF) -> ResearchRequest:
    return ResearchRequest(
        symbol="  msft  ",
        horizon_days=20,
        provider="polygon",
        as_of=as_of,
    )


def _prices_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["MSFT", "MSFT"],
            "timestamp": [
                datetime(2026, 1, 8, 0, 0, tzinfo=UTC),
                datetime(2026, 1, 9, 0, 0, tzinfo=UTC),
            ],
            "close": [100.0, 101.0],
        }
    )


def _raw_snapshot() -> MarketSignalSnapshot:
    return MarketSignalSnapshot(
        symbol="MSFT",
        timestamp=_SNAPSHOT_TIMESTAMP,
        signals=(
            MarketSignal(
                symbol="MSFT",
                name="trend",
                value=0.05,
                timestamp=_SNAPSHOT_TIMESTAMP,
                parameters={"source": "trend"},
            ),
            MarketSignal(
                symbol="MSFT",
                name="momentum",
                value=0.10,
                timestamp=_SNAPSHOT_TIMESTAMP,
                parameters={"source": "momentum"},
            ),
            MarketSignal(
                symbol="MSFT",
                name="realized_volatility",
                value=0.10,
                timestamp=_SNAPSHOT_TIMESTAMP,
                parameters={"source": "volatility"},
            ),
            MarketSignal(
                symbol="MSFT",
                name="current_drawdown",
                value=-0.10,
                timestamp=_SNAPSHOT_TIMESTAMP,
                parameters={"source": "drawdown"},
            ),
            MarketSignal(
                symbol="MSFT",
                name="distance_from_moving_average",
                value=0.05,
                timestamp=_SNAPSHOT_TIMESTAMP,
                parameters={"source": "distance"},
            ),
        ),
    )


def _interpreted_signal(
    name: str,
    score: float | None,
    *,
    role: SignalRole = SignalRole.DIRECTIONAL,
) -> InterpretedSignal:
    state = (
        InterpretedSignalState.UNAVAILABLE
        if score is None
        else InterpretedSignalState.POSITIVE
    )
    scale = {
        "trend": 0.10,
        "momentum": 0.20,
        "current_drawdown": 0.20,
        "distance_from_moving_average": 0.10,
    }.get(name, 0.10)
    return InterpretedSignal(
        symbol="MSFT",
        timestamp=_SNAPSHOT_TIMESTAMP,
        name=name,
        raw_value=score,
        score=score,
        state=state,
        role=role,
        methodology="baseline_uncalibrated_directional_rescaling_v1",
        parameters={
            "signal_name": name,
            "role": role.value,
            "methodology": "baseline_uncalibrated_directional_rescaling_v1",
            "scale": scale,
            "formula": "clamp(raw_value / scale, -1.0, 1.0)",
            "source_parameters": {"source": name},
        },
    )


def _volatility_assessment(
    state: VolatilityState = VolatilityState.NORMAL,
) -> VolatilityAssessment:
    raw_value = None if state is VolatilityState.UNAVAILABLE else 0.2
    return VolatilityAssessment(
        symbol="MSFT",
        timestamp=_SNAPSHOT_TIMESTAMP,
        raw_value=raw_value,
        state=state,
        methodology="baseline_realized_volatility_thresholds_v1",
        parameters={"low_threshold": 0.15, "high_threshold": 0.30},
    )


def _run_workflow(
    workflow: DefaultResearchWorkflow,
    request: ResearchRequest,
    position: PositionContext | None = None,
) -> ResearchResult:
    return asyncio.run(workflow.run(request, position=position))


def _install_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    *,
    directional_scores: tuple[float | None, ...],
    volatility_state: VolatilityState = VolatilityState.NORMAL,
) -> dict[str, object]:
    captured: dict[str, object] = {}

    def fake_calculate_market_signals(prices: pd.DataFrame) -> MarketSignalSnapshot:
        captured["prices_frame"] = prices
        return _raw_snapshot()

    def fake_interpret_directional_signals(
        signals: Any,
        rules: Any = None,
    ) -> tuple[InterpretedSignal, ...]:
        del rules
        selected = list(signals)
        captured["directional_inputs"] = selected
        return tuple(
            _interpreted_signal(signal.name, score)
            for signal, score in zip(selected, directional_scores, strict=True)
        )

    def fake_interpret_realized_volatility(
        signal: MarketSignal,
        **kwargs: Any,
    ) -> VolatilityAssessment:
        del signal, kwargs
        captured["volatility_signal"] = True
        return _volatility_assessment(volatility_state)

    real_calculate_research_composite_signal = calculate_research_composite_signal

    def spy_calculate_research_composite_signal(
        interpreted_signals: Any,
        weights: dict[str, float] | None = None,
    ) -> MarketSignal:
        selected = list(interpreted_signals)
        captured["composite_inputs"] = selected
        captured["composite_weights"] = None if weights is None else dict(weights)
        return real_calculate_research_composite_signal(selected, weights=weights)

    monkeypatch.setattr(
        research_workflow, "calculate_market_signals", fake_calculate_market_signals
    )
    monkeypatch.setattr(
        research_workflow,
        "interpret_directional_signals",
        fake_interpret_directional_signals,
    )
    monkeypatch.setattr(
        research_workflow,
        "interpret_realized_volatility",
        fake_interpret_realized_volatility,
    )
    monkeypatch.setattr(
        research_workflow,
        "calculate_research_composite_signal",
        spy_calculate_research_composite_signal,
    )
    return captured


def test_workflow_protocol_is_async_and_runtime_checkable() -> None:
    assert inspect.iscoroutinefunction(DefaultResearchWorkflow.run)
    assert isinstance(_FakeWorkflow(), ResearchWorkflow)


def test_workflow_uses_request_window_and_preserves_input_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame = _prices_frame()
    original = frame.copy(deep=True)
    service = FakeMarketDataService(frame)
    workflow = DefaultResearchWorkflow(service, lookback_calendar_days=30)
    captured = _install_pipeline(monkeypatch, directional_scores=(0.5, 0.5, 0.5, 0.5))

    monkeypatch.setattr(research_workflow, "_current_utc", lambda: _CLOCK_NOW)

    result = _run_workflow(workflow, _request(as_of=None))

    assert service.calls == [
        {
            "symbol": "MSFT",
            "start": date(2025, 12, 11),
            "end": date(2026, 1, 10),
            "provider": "polygon",
        }
    ]
    assert frame.equals(original)
    assert captured["prices_frame"] is frame
    assert result.request.symbol == "MSFT"


def test_workflow_uses_explicit_as_of_in_utc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame = _prices_frame()
    service = FakeMarketDataService(frame)
    workflow = DefaultResearchWorkflow(service, lookback_calendar_days=20)
    _install_pipeline(monkeypatch, directional_scores=(0.7, 0.7, 0.7, 0.7))

    _run_workflow(workflow, _request())

    assert service.calls[0]["start"] == date(2025, 12, 15)
    assert service.calls[0]["end"] == date(2026, 1, 4)


@pytest.mark.parametrize(
    ("score", "expected_direction", "expected_strength"),
    [
        (-0.9, "bearish", "strong"),
        (-0.3, "bearish", "moderate"),
        (0.0, "neutral", "neutral"),
        (0.3, "bullish", "moderate"),
        (0.9, "bullish", "strong"),
    ],
)
def test_workflow_maps_classification_to_market_view(
    monkeypatch: pytest.MonkeyPatch,
    score: float,
    expected_direction: str,
    expected_strength: str,
) -> None:
    frame = _prices_frame()
    service = FakeMarketDataService(frame)
    workflow = DefaultResearchWorkflow(service)
    _install_pipeline(monkeypatch, directional_scores=(score, score, score, score))

    result = _run_workflow(workflow, _request())

    assert result.market_view is not None
    assert result.market_view.direction == expected_direction
    assert result.market_view.strength == expected_strength


def test_workflow_produces_analysis_and_preserves_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame = _prices_frame()
    service = FakeMarketDataService(frame)
    workflow = DefaultResearchWorkflow(service)
    _install_pipeline(monkeypatch, directional_scores=(0.5, 0.5, 0.5, 0.5))

    result = _run_workflow(workflow, _request())

    assert isinstance(result.analysis, ResearchAnalysis)
    assert isinstance(result.analysis.composite, ResearchCompositeAssessment)
    assert [component.name for component in result.analysis.components] == [
        "trend",
        "momentum",
        "realized_volatility",
        "current_drawdown",
        "distance_from_moving_average",
    ]
    assert isinstance(result.analysis.components[0], ResearchSignalComponent)
    assert result.analysis.components[2].role == "volatility"
    assert result.analysis.components[2].score is None
    assert result.analysis.components[0].parameters["scale"] == pytest.approx(0.10)
    assert (
        result.analysis.components[0].parameters["formula"]
        == "clamp(raw_value / scale, -1.0, 1.0)"
    )
    assert result.analysis.volatility_state == VolatilityState.NORMAL.value
    assert result.analysis.volatility_value == pytest.approx(0.2)


def test_workflow_excludes_volatility_from_directional_composite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame = _prices_frame()
    service = FakeMarketDataService(frame)
    workflow = DefaultResearchWorkflow(service)
    captured = _install_pipeline(monkeypatch, directional_scores=(0.5, 0.5, 0.5, 0.5))

    _run_workflow(workflow, _request())

    composite_inputs = captured["composite_inputs"]
    assert all(signal.role is SignalRole.DIRECTIONAL for signal in composite_inputs)
    assert all(signal.name != "realized_volatility" for signal in composite_inputs)


def test_workflow_status_and_warnings_for_missing_directional_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame = _prices_frame()
    service = FakeMarketDataService(frame)
    workflow = DefaultResearchWorkflow(service)
    _install_pipeline(monkeypatch, directional_scores=(0.5, None, 0.5, 0.5))

    result = _run_workflow(workflow, _request())

    assert result.status is ResearchStatus.DEGRADED
    assert [warning.code for warning in result.warnings] == [
        "missing_directional_signals"
    ]
    assert "momentum" in result.warnings[0].message
    assert result.market_view is not None
    assert result.market_view.direction == "bullish"


def test_workflow_marks_composite_unavailable_when_all_directional_scores_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame = _prices_frame()
    service = FakeMarketDataService(frame)
    workflow = DefaultResearchWorkflow(service)
    _install_pipeline(monkeypatch, directional_scores=(None, None, None, None))

    result = _run_workflow(workflow, _request())

    assert result.status is ResearchStatus.DEGRADED
    assert result.market_view is not None
    assert result.market_view.direction is None
    assert result.market_view.strength is None
    assert result.analysis is not None
    assert result.analysis.composite.score is None
    assert result.analysis.composite.classification is None
    assert [warning.code for warning in result.warnings] == [
        "missing_directional_signals",
        "composite_unavailable",
    ]


def test_workflow_custom_weights_are_copied_and_used(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame = _prices_frame()
    service = FakeMarketDataService(frame)
    weights = {
        "trend": 2.0,
        "momentum": 1.0,
        "current_drawdown": 1.0,
        "distance_from_moving_average": 1.0,
    }
    workflow = DefaultResearchWorkflow(service, composite_weights=weights)
    captured = _install_pipeline(monkeypatch, directional_scores=(0.5, 0.5, 0.5, 0.5))
    weights["trend"] = 10.0

    _run_workflow(workflow, _request())

    assert captured["composite_weights"] == {
        "trend": 2.0,
        "momentum": 1.0,
        "current_drawdown": 1.0,
        "distance_from_moving_average": 1.0,
    }


def test_workflow_position_argument_is_accepted_but_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame = _prices_frame()
    service = FakeMarketDataService(frame)
    workflow = DefaultResearchWorkflow(service)
    _install_pipeline(monkeypatch, directional_scores=(0.5, 0.5, 0.5, 0.5))
    position = PositionContext(shares=10, average_cost=100.0)

    with_position = _run_workflow(workflow, _request(), position=position)
    without_position = _run_workflow(workflow, _request())

    assert with_position == without_position


def test_workflow_summary_uses_request_context_wording(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame = _prices_frame()
    service = FakeMarketDataService(frame)
    workflow = DefaultResearchWorkflow(service)
    _install_pipeline(monkeypatch, directional_scores=(0.5, 0.5, 0.5, 0.5))

    result = _run_workflow(workflow, _request())

    assert (
        result.summary
        == "MSFT's current composite signal is classified as bullish; the "
        "requested research horizon is 20 days."
    )
    assert "forecast" not in result.summary.lower()


def _bad_composite(
    *,
    parameters: dict[str, object],
    value: float | None = 0.25,
) -> MarketSignal:
    return MarketSignal(
        symbol="MSFT",
        name="composite_score",
        value=value,
        timestamp=_SNAPSHOT_TIMESTAMP,
        parameters=parameters,
    )


@pytest.mark.parametrize(
    ("field_name", "bad_value", "expected_message"),
    [
        ("included_signals", "trend", "must be a list or tuple"),
        ("missing_signals", b"trend", "must be a list or tuple"),
        ("included_signals", ["trend", ""], "must not be empty"),
        ("missing_signals", iter(["trend"]), "must be a list or tuple"),
    ],
)
def test_workflow_rejects_malformed_string_sequence_metadata(
    monkeypatch: pytest.MonkeyPatch,
    field_name: str,
    bad_value: object,
    expected_message: str,
) -> None:
    _install_pipeline(monkeypatch, directional_scores=(0.5, 0.5, 0.5, 0.5))

    def fake_calculate_research_composite_signal(
        interpreted_signals: Any,
        weights: dict[str, float] | None = None,
    ) -> MarketSignal:
        del interpreted_signals, weights
        parameters = {
            "missing_policy": "exclude",
            "configured_weights": {"trend": 1.0},
            "normalized_weights": {"trend": 1.0},
            "component_contributions": {"trend": 0.25},
            "included_signals": ["trend"],
            "missing_signals": [],
        }
        parameters[field_name] = bad_value
        return _bad_composite(parameters=parameters)

    monkeypatch.setattr(
        research_workflow,
        "calculate_research_composite_signal",
        fake_calculate_research_composite_signal,
    )

    workflow = DefaultResearchWorkflow(FakeMarketDataService(_prices_frame()))
    with pytest.raises((TypeError, ValueError), match=expected_message):
        _run_workflow(workflow, _request())


@pytest.mark.parametrize(
    ("field_name", "bad_value", "expected_message"),
    [
        ("configured_weights", {"trend": True}, "must be numeric"),
        ("normalized_weights", {"trend": float("inf")}, "must be finite"),
        ("component_contributions", {"trend": True}, "must be numeric"),
        ("component_contributions", {"trend": float("nan")}, "must be finite"),
        ("configured_weights", {"trend": -1.0}, "must not contain negative values"),
        ("normalized_weights", {"trend": -1.0}, "must not contain negative values"),
    ],
)
def test_workflow_rejects_malformed_numeric_metadata(
    monkeypatch: pytest.MonkeyPatch,
    field_name: str,
    bad_value: object,
    expected_message: str,
) -> None:
    _install_pipeline(monkeypatch, directional_scores=(0.5, 0.5, 0.5, 0.5))

    def fake_calculate_research_composite_signal(
        interpreted_signals: Any,
        weights: dict[str, float] | None = None,
    ) -> MarketSignal:
        del interpreted_signals, weights
        parameters = {
            "missing_policy": "exclude",
            "configured_weights": {"trend": 1.0},
            "normalized_weights": {"trend": 1.0},
            "component_contributions": {"trend": 0.25},
            "included_signals": ["trend"],
            "missing_signals": [],
        }
        parameters[field_name] = bad_value
        return _bad_composite(parameters=parameters)

    monkeypatch.setattr(
        research_workflow,
        "calculate_research_composite_signal",
        fake_calculate_research_composite_signal,
    )

    workflow = DefaultResearchWorkflow(FakeMarketDataService(_prices_frame()))
    with pytest.raises((TypeError, ValueError), match=expected_message):
        _run_workflow(workflow, _request())


def test_workflow_unknown_directional_scale_fails_fast() -> None:
    with pytest.raises(ValueError, match="Unknown directional signal"):
        research_workflow._directional_scale("mystery")


def test_workflow_propagates_provider_exceptions() -> None:
    class ExplodingService:
        async def get_daily_prices(
            self,
            symbol: str,
            start: date,
            end: date,
            provider: str | None = None,
        ) -> pd.DataFrame:
            raise RuntimeError("boom")

    workflow = DefaultResearchWorkflow(ExplodingService())

    with pytest.raises(RuntimeError, match="boom"):
        _run_workflow(workflow, _request())


def test_workflow_propagates_empty_price_data_errors() -> None:
    class EmptyFrameService:
        async def get_daily_prices(
            self,
            symbol: str,
            start: date,
            end: date,
            provider: str | None = None,
        ) -> pd.DataFrame:
            return pd.DataFrame(columns=["symbol", "timestamp", "close"])

    workflow = DefaultResearchWorkflow(EmptyFrameService())

    with pytest.raises(ValueError):
        _run_workflow(workflow, _request())


@pytest.mark.parametrize(
    ("lookback_calendar_days", "expected_exception"),
    [
        (0, ValueError),
        (-1, ValueError),
        (True, TypeError),
        (1.5, TypeError),
    ],
)
def test_workflow_constructor_validates_lookback_days(
    lookback_calendar_days: object,
    expected_exception: type[Exception],
) -> None:
    with pytest.raises(expected_exception):
        DefaultResearchWorkflow(object(), lookback_calendar_days=lookback_calendar_days)  # type: ignore[arg-type]


def test_workflow_constructor_validates_model_version() -> None:
    with pytest.raises(ValueError, match="model_version"):
        DefaultResearchWorkflow(object(), model_version="   ")  # type: ignore[arg-type]


def test_workflow_serialization_is_json_compatible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame = _prices_frame()
    service = FakeMarketDataService(frame)
    workflow = DefaultResearchWorkflow(service)
    _install_pipeline(monkeypatch, directional_scores=(0.5, 0.5, 0.5, 0.5))

    result = _run_workflow(workflow, _request())
    payload = result.to_dict()

    json.dumps(payload)
    assert (
        payload["analysis"]["composite"]["methodology"]
        == "baseline_uncalibrated_composite_v1"
    )
    assert payload["analysis"]["components"][0]["parameters"]["scale"] == pytest.approx(
        0.10
    )


def test_public_exports_include_workflow_and_analysis_models() -> None:
    assert DefaultResearchWorkflow is not None
    assert ResearchAnalysis is not None
    assert ResearchCompositeAssessment is not None
    assert ResearchSignalComponent is not None
