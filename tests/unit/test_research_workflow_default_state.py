from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

import market_platform.cli.main as cli_main
import market_platform.research.workflow as research_workflow
from market_platform.observation import MarketObservation
from market_platform.research import (
    DefaultResearchWorkflow,
    ResearchInterpretationMode,
)
from market_platform.research.models import ResearchRequest, ResearchResult
from market_platform.signals.models import MarketSignal, MarketSignalSnapshot
from market_platform.state import BaselineMarketStateModel, MarketState
from market_platform.structure.models import (
    ObservedPriceZone,
    PriceLevelCandidate,
    PriceLevelKind,
    PriceStructureSnapshot,
    PriceStructureStatus,
    PriceZone,
    PriceZoneObservation,
)

_AS_OF = datetime(2026, 7, 16, 23, 0, tzinfo=UTC)
_FACTS_AS_OF = datetime(2026, 7, 16, tzinfo=UTC)


class FakeMarketDataService:
    def __init__(self, prices: pd.DataFrame) -> None:
        self.prices = prices
        self.returned_frames: list[pd.DataFrame] = []
        self.calls = 0

    async def get_daily_prices(
        self,
        symbol: str,
        start: date,
        end: date,
        provider: str | None = None,
    ) -> pd.DataFrame:
        del symbol, start, end, provider
        self.calls += 1
        frame = self.prices.copy(deep=True)
        self.returned_frames.append(frame)
        return frame


class FakeStructureService:
    def __init__(self, snapshot: PriceStructureSnapshot) -> None:
        self.snapshot = snapshot
        self.calls = 0
        self.inputs: list[pd.DataFrame] = []
        self.as_of_values: list[object] = []

    def analyze(
        self,
        prices: pd.DataFrame,
        **kwargs: object,
    ) -> PriceStructureSnapshot:
        self.calls += 1
        self.inputs.append(prices.copy(deep=True))
        self.as_of_values.append(kwargs.get("as_of"))
        return self.snapshot


class RecordingStateModel:
    def __init__(self) -> None:
        self.delegate = BaselineMarketStateModel()
        self.observations: list[MarketObservation] = []
        self.before: list[dict[str, object]] = []
        self.after: list[dict[str, object]] = []

    @property
    def model_id(self) -> str:
        return "recording-state-model"

    @property
    def model_version(self) -> str:
        return "1.0.0"

    def evaluate(self, observation: MarketObservation) -> MarketState:
        self.observations.append(observation)
        self.before.append(observation.to_dict())
        state = self.delegate.evaluate(observation)
        self.after.append(observation.to_dict())
        return state


def _prices() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["MSFT", "MSFT", "MSFT"],
            "timestamp": [
                datetime(2026, 7, 14, tzinfo=UTC),
                datetime(2026, 7, 15, tzinfo=UTC),
                _FACTS_AS_OF,
            ],
            "open": [98.5, 100.5, 101.5],
            "high": [100.0, 102.0, 103.0],
            "low": [98.0, 99.0, 100.0],
            "close": [99.0, 101.0, 102.0],
            "volume": [1_000_000.0, 1_100_000.0, 1_200_000.0],
            "provider": ["test-provider", "test-provider", "test-provider"],
        }
    )


def _prices_with_future() -> pd.DataFrame:
    future = pd.DataFrame(
        {
            "symbol": ["MSFT"],
            "timestamp": [datetime(2026, 7, 17, tzinfo=UTC)],
            "open": [9998.0],
            "high": [10000.0],
            "low": [9990.0],
            "close": [9999.0],
            "volume": [9_999_999.0],
            "provider": ["test-provider"],
        }
    )
    return pd.concat([_prices(), future], ignore_index=True)


def _signals() -> MarketSignalSnapshot:
    values = {
        "trend": 0.04,
        "momentum": 0.08,
        "current_drawdown": 0.08,
        "distance_from_moving_average": 0.04,
        "realized_volatility": 0.20,
    }
    return MarketSignalSnapshot(
        symbol="MSFT",
        timestamp=_FACTS_AS_OF,
        signals=tuple(
            MarketSignal(
                symbol="MSFT",
                name=name,
                value=value,
                timestamp=_FACTS_AS_OF,
                parameters={"source": "default-state-test"},
            )
            for name, value in values.items()
        ),
    )


def _structure_snapshot(
    status: PriceStructureStatus = PriceStructureStatus.OK,
) -> PriceStructureSnapshot:
    if status is not PriceStructureStatus.OK:
        return PriceStructureSnapshot(
            status=status,
            as_of=_FACTS_AS_OF,
            current_price=102.0,
        )
    candidate = PriceLevelCandidate(
        price=100.0,
        kind=PriceLevelKind.SWING_LOW,
        occurred_at=datetime(2026, 7, 14, tzinfo=UTC),
        confirmed_at=datetime(2026, 7, 15, tzinfo=UTC),
    )
    observed_zone = ObservedPriceZone(
        zone=PriceZone(
            lower_bound=99.5,
            upper_bound=100.5,
            midpoint=100.0,
            candidates=(candidate,),
            source_methods=(candidate.source_method,),
        ),
        observation=PriceZoneObservation(
            touch_count=0,
            first_observed_at=None,
            last_observed_at=None,
        ),
    )
    return PriceStructureSnapshot(
        status=status,
        as_of=_FACTS_AS_OF,
        current_price=102.0,
        atr=2.0,
        candidates=(candidate,),
        observed_zones=(observed_zone,),
    )


def _request() -> ResearchRequest:
    return ResearchRequest(
        symbol="MSFT",
        horizon_days=20,
        provider="test-provider",
        as_of=_AS_OF,
    )


def _run(workflow: DefaultResearchWorkflow) -> ResearchResult:
    return asyncio.run(workflow.run(_request()))


def _install_signals(
    monkeypatch: pytest.MonkeyPatch,
    snapshot: MarketSignalSnapshot,
) -> list[pd.DataFrame]:
    inputs: list[pd.DataFrame] = []

    def calculate(prices: pd.DataFrame) -> MarketSignalSnapshot:
        inputs.append(prices.copy(deep=True))
        return snapshot

    monkeypatch.setattr(research_workflow, "calculate_market_signals", calculate)
    return inputs


def _workflow(
    *,
    prices: pd.DataFrame,
    structure: PriceStructureSnapshot,
    interpretation_mode: ResearchInterpretationMode = (
        ResearchInterpretationMode.STATE
    ),
    state_model: RecordingStateModel | BaselineMarketStateModel | None = None,
) -> tuple[DefaultResearchWorkflow, FakeMarketDataService, FakeStructureService]:
    data_service = FakeMarketDataService(prices)
    structure_service = FakeStructureService(structure)
    workflow = DefaultResearchWorkflow(
        data_service,
        price_structure_service=structure_service,  # type: ignore[arg-type]
        interpretation_mode=interpretation_mode,
        state_model=state_model,
    )
    return workflow, data_service, structure_service


def test_default_workflow_instantiates_and_uses_baseline_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_signals(monkeypatch, _signals())
    model = RecordingStateModel()
    adapted: list[tuple[MarketState, MarketObservation]] = []
    real_adapter = research_workflow.adapt_market_state_to_analysis

    def spy_adapter(
        state: MarketState,
        observation: MarketObservation,
    ) -> object:
        adapted.append((state, observation))
        return real_adapter(state, observation)

    monkeypatch.setattr(
        research_workflow,
        "BaselineMarketStateModel",
        lambda: model,
    )
    monkeypatch.setattr(
        research_workflow,
        "adapt_market_state_to_analysis",
        spy_adapter,
    )
    workflow, _, _ = _workflow(
        prices=_prices(),
        structure=_structure_snapshot(),
    )

    result = _run(workflow)

    assert len(model.observations) == 1
    assert len(adapted) == 1
    assert adapted[0][1] is model.observations[0]
    assert result.market_view is not None
    assert result.analysis is not None
    assert result.market_view.direction == "bullish"
    assert result.market_view.price_structure == "available"


def test_default_state_matches_explicit_baseline_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_signals(monkeypatch, _signals())
    default, _, _ = _workflow(
        prices=_prices(),
        structure=_structure_snapshot(),
    )
    explicit, _, _ = _workflow(
        prices=_prices(),
        structure=_structure_snapshot(),
        interpretation_mode=ResearchInterpretationMode.STATE,
        state_model=BaselineMarketStateModel(),
    )

    assert _run(default).to_dict() == _run(explicit).to_dict()


def test_explicit_state_uses_injected_custom_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_signals(monkeypatch, _signals())
    model = RecordingStateModel()
    workflow, _, _ = _workflow(
        prices=_prices(),
        structure=_structure_snapshot(),
        interpretation_mode=ResearchInterpretationMode.STATE,
        state_model=model,
    )

    _run(workflow)

    assert len(model.observations) == 1
    assert model.observations[0].identity.as_of == _AS_OF


def test_state_workflow_ignores_future_rows_for_same_as_of(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signals = _signals()
    base_signal_inputs = _install_signals(monkeypatch, signals)
    base_model = RecordingStateModel()
    base_workflow, _, base_structure_service = _workflow(
        prices=_prices(),
        structure=_structure_snapshot(),
        state_model=base_model,
    )
    base_result = _run(base_workflow)

    future_signal_inputs = _install_signals(monkeypatch, signals)
    future_model = RecordingStateModel()
    future_prices = _prices_with_future()
    original_future_prices = future_prices.copy(deep=True)
    future_workflow, _, future_structure_service = _workflow(
        prices=future_prices,
        structure=_structure_snapshot(),
        state_model=future_model,
    )
    future_result = _run(future_workflow)

    assert base_result.to_dict() == future_result.to_dict()
    assert_frame_equal(future_prices, original_future_prices)
    assert len(base_signal_inputs[0]) == 3
    assert len(future_signal_inputs[0]) == 3
    assert len(future_structure_service.inputs[0]) == 3
    assert future_structure_service.as_of_values == [_AS_OF]
    base_observation = base_model.observations[0]
    future_observation = future_model.observations[0]
    assert base_observation.identity.window_end == _FACTS_AS_OF
    assert future_observation.identity.window_end == _FACTS_AS_OF
    assert future_observation.price_facts.latest_price == 102.0
    assert (
        base_observation.provenance.input_fingerprint
        == future_observation.provenance.input_fingerprint
    )
    assert base_structure_service.as_of_values == [_AS_OF]


def test_state_workflow_keeps_row_at_exact_as_of(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exact_row = pd.DataFrame(
        {
            "symbol": ["MSFT"],
            "timestamp": [_AS_OF],
            "open": [102.5],
            "high": [104.0],
            "low": [102.0],
            "close": [103.5],
            "volume": [1_300_000.0],
            "provider": ["test-provider"],
        }
    )
    prices = pd.concat([_prices(), exact_row], ignore_index=True)
    signal_inputs = _install_signals(monkeypatch, _signals())
    model = RecordingStateModel()
    workflow, _, structure_service = _workflow(
        prices=prices,
        structure=_structure_snapshot(),
        state_model=model,
    )

    _run(workflow)

    observation = model.observations[0]
    assert len(signal_inputs[0]) == 4
    assert len(structure_service.inputs[0]) == 4
    assert structure_service.as_of_values == [_AS_OF]
    assert observation.identity.window_end == _AS_OF
    assert observation.price_facts.latest_price == 103.5


def test_explicit_legacy_preserves_parity_and_state_structure_enrichment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_signals(monkeypatch, _signals())
    state, _, _ = _workflow(
        prices=_prices(),
        structure=_structure_snapshot(),
    )
    legacy, _, _ = _workflow(
        prices=_prices(),
        structure=_structure_snapshot(),
        interpretation_mode=ResearchInterpretationMode.LEGACY,
    )

    state_result = _run(state)
    legacy_result = _run(legacy)
    assert state_result.market_view is not None
    assert legacy_result.market_view is not None
    for field_name in (
        "direction",
        "strength",
        "trend_state",
        "momentum_state",
        "volatility_state",
        "confidence",
    ):
        assert getattr(state_result.market_view, field_name) == getattr(
            legacy_result.market_view,
            field_name,
        )
    assert state_result.market_view.price_structure == "available"
    assert legacy_result.market_view.price_structure is None
    assert state_result.analysis is not None
    assert legacy_result.analysis is not None
    assert state_result.analysis.composite == legacy_result.analysis.composite
    assert [
        component.score for component in state_result.analysis.components
    ] == [
        component.score for component in legacy_result.analysis.components
    ]
    assert state_result.analysis.structure is not None
    assert (
        state_result.analysis.price_context
        == legacy_result.analysis.price_context
    )
    assert (
        state_result.analysis.structural_target_levels
        == legacy_result.analysis.structural_target_levels
    )
    assert state_result.summary == legacy_result.summary
    assert state_result.warnings == legacy_result.warnings
    assert state_result.status is legacy_result.status


def test_legacy_with_custom_state_model_is_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="state_model must be None when interpretation_mode is LEGACY",
    ):
        DefaultResearchWorkflow(
            FakeMarketDataService(_prices()),
            interpretation_mode=ResearchInterpretationMode.LEGACY,
            state_model=RecordingStateModel(),
        )


def test_interpretation_mode_requires_enum_member() -> None:
    with pytest.raises(TypeError, match="ResearchInterpretationMode"):
        DefaultResearchWorkflow(
            FakeMarketDataService(_prices()),
            interpretation_mode="state",  # type: ignore[arg-type]
        )


def test_non_ok_structure_uses_compatible_unavailable_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_signals(monkeypatch, _signals())
    workflow, _, _ = _workflow(
        prices=_prices(),
        structure=_structure_snapshot(PriceStructureStatus.NO_PIVOTS),
    )

    result = _run(workflow)

    assert result.market_view is not None
    assert result.market_view.price_structure is None


def test_default_state_serialization_field_sets_are_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_signals(monkeypatch, _signals())
    workflow, _, _ = _workflow(
        prices=_prices(),
        structure=_structure_snapshot(),
    )

    payload = _run(workflow).to_dict()

    assert set(payload) == {
        "request",
        "status",
        "model_version",
        "market_view",
        "price_targets",
        "probabilities",
        "price_levels",
        "position_actions",
        "strategy_candidates",
        "warnings",
        "summary",
        "analysis",
    }
    assert isinstance(payload["market_view"], dict)
    assert set(payload["market_view"]) == {
        "direction",
        "strength",
        "trend_state",
        "momentum_state",
        "volatility_state",
        "price_structure",
        "confidence",
    }
    assert isinstance(payload["analysis"], dict)
    composite = payload["analysis"]["composite"]
    assert composite["score"] == pytest.approx(0.4)
    assert composite["classification"] == "bullish"
    assert composite["configured_weights"] == {
        "trend": 1.0,
        "momentum": 1.0,
        "current_drawdown": 1.0,
        "distance_from_moving_average": 1.0,
    }
    assert composite["normalized_weights"] == {
        "trend": 0.25,
        "momentum": 0.25,
        "current_drawdown": 0.25,
        "distance_from_moving_average": 0.25,
    }
    assert payload["analysis"]["timestamp"] == _FACTS_AS_OF.isoformat()
    assert len(payload["analysis"]["components"]) == 5
    assert payload["analysis"]["structure"]["status"] == "ok"
    assert payload["analysis"]["price_context"]["current_price"] == 102.0
    assert payload["analysis"]["structural_target_levels"] == [
        {
            "price": 100.5,
            "direction": "downside",
            "distance": 1.5,
            "distance_pct": 1.5 / 102.0,
            "sources": ["swing_pivot"],
        }
    ]


def test_default_state_cli_table_restores_composite_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_signals(monkeypatch, _signals())
    workflow, _, _ = _workflow(
        prices=_prices(),
        structure=_structure_snapshot(),
    )

    rendered = cli_main._render_research_result_table(_run(workflow))

    assert "Composite Score" in rendered
    assert "Classification" in rendered
    assert "0.4" in rendered
    assert "bullish" in rendered


def test_default_state_preserves_inputs_and_is_deterministic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prices = _prices()
    prices_before = prices.copy(deep=True)
    signals = _signals()
    signal_parameters = [dict(signal.parameters) for signal in signals.signals]
    structure = _structure_snapshot()
    signal_inputs = _install_signals(monkeypatch, signals)
    model = RecordingStateModel()
    workflow, data_service, structure_service = _workflow(
        prices=prices,
        structure=structure,
        state_model=model,
    )

    first = _run(workflow)
    second = _run(workflow)

    assert first == second
    assert_frame_equal(prices, prices_before)
    assert data_service.calls == 2
    assert structure_service.calls == 2
    assert len(signal_inputs) == 2
    assert all(
        frame.equals(data_service.returned_frames[index])
        for index, frame in enumerate(signal_inputs)
    )
    assert model.before == model.after
    assert all(
        observation.identity.window_end <= observation.identity.as_of
        for observation in model.observations
    )
    assert [signal.parameters for signal in signals.signals] == signal_parameters
    assert structure == _structure_snapshot()


def test_default_state_does_not_execute_legacy_interpretation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_signals(monkeypatch, _signals())

    def fail(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("legacy interpretation must not run in STATE mode")

    monkeypatch.setattr(research_workflow, "interpret_directional_signals", fail)
    monkeypatch.setattr(research_workflow, "interpret_realized_volatility", fail)
    monkeypatch.setattr(
        research_workflow,
        "calculate_research_composite_signal",
        fail,
    )
    monkeypatch.setattr(research_workflow, "classify_composite_signal", fail)
    workflow, _, _ = _workflow(
        prices=_prices(),
        structure=_structure_snapshot(),
    )

    assert _run(workflow).market_view is not None
