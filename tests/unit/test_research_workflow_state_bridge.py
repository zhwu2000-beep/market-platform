from __future__ import annotations

import asyncio
import math
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest

import market_platform.research.workflow as research_workflow
from market_platform.observation import MarketObservation
from market_platform.research.adapter import adapt_market_state_to_view
from market_platform.research.models import MarketView, ResearchRequest, ResearchResult
from market_platform.research.workflow import DefaultResearchWorkflow
from market_platform.state import (
    DirectionalRegime,
    MarketState,
    MomentumRegime,
    StateModelProvenance,
    StateQuality,
    StructureState,
    TrendRegime,
    VolatilityRegime,
)

_AS_OF = datetime(2026, 7, 16, 23, 0, tzinfo=UTC)


class FakeMarketDataService:
    def __init__(self, prices: pd.DataFrame) -> None:
        self._prices = prices

    async def get_daily_prices(
        self,
        symbol: str,
        start: date,
        end: date,
        provider: str | None = None,
    ) -> pd.DataFrame:
        del symbol, start, end, provider
        return self._prices.copy(deep=True)


class FakeStateModel:
    def __init__(self) -> None:
        self.observations: list[MarketObservation] = []
        self.before_evaluation: list[dict[str, object]] = []
        self.states: list[MarketState] = []

    @property
    def model_id(self) -> str:
        return "fake-bridge-state-model"

    @property
    def model_version(self) -> str:
        return "1.0.0"

    def evaluate(self, observation: MarketObservation) -> MarketState:
        self.observations.append(observation)
        self.before_evaluation.append(observation.to_dict())
        state = MarketState(
            symbol=observation.identity.symbol,
            interval=observation.identity.interval,
            as_of=observation.identity.as_of,
            provenance=StateModelProvenance(
                model_id=self.model_id,
                model_version=self.model_version,
                parameters={"source": "fake"},
                observation_fingerprint=(
                    observation.provenance.input_fingerprint
                ),
            ),
            directional_regime=DirectionalRegime.STRONG_DOWN,
            trend_regime=TrendRegime.DOWN,
            momentum_regime=MomentumRegime.STRONG_NEGATIVE,
            volatility_regime=VolatilityRegime.HIGH,
            structure_state=StructureState.AVAILABLE,
            quality=StateQuality.COMPLETE,
        )
        self.states.append(state)
        return state


def _prices() -> pd.DataFrame:
    timestamps = pd.date_range(
        end=datetime(2026, 7, 16, tzinfo=UTC),
        periods=90,
        freq="D",
    )
    closes = [
        100.0 + index * 0.05 + math.sin(index / 3.0) * 3.0
        for index in range(len(timestamps))
    ]
    return pd.DataFrame(
        {
            "symbol": ["MSFT"] * len(timestamps),
            "timestamp": timestamps,
            "open": closes,
            "high": [close + 1.0 for close in closes],
            "low": [close - 1.0 for close in closes],
            "close": closes,
            "volume": [1_000_000] * len(timestamps),
        }
    )


def _run(workflow: DefaultResearchWorkflow) -> ResearchResult:
    request = ResearchRequest(
        symbol="MSFT",
        horizon_days=20,
        provider="test-provider",
        as_of=_AS_OF,
    )
    return asyncio.run(workflow.run(request))


def test_default_workflow_behavior_is_unchanged_with_explicit_none() -> None:
    implicit = DefaultResearchWorkflow(FakeMarketDataService(_prices()))
    explicit = DefaultResearchWorkflow(
        FakeMarketDataService(_prices()),
        state_model=None,
    )

    assert _run(implicit).to_dict() == _run(explicit).to_dict()


def test_default_path_does_not_call_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_called(state: MarketState) -> MarketView:
        del state
        raise AssertionError("adapter must not run without a state model")

    monkeypatch.setattr(
        research_workflow,
        "adapt_market_state_to_view",
        fail_if_called,
    )

    assert _run(
        DefaultResearchWorkflow(FakeMarketDataService(_prices()))
    ).market_view is not None


def test_injected_model_uses_adapter_and_controls_market_view(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = FakeStateModel()
    adapted: list[MarketState] = []

    def spy_adapter(state: MarketState) -> MarketView:
        adapted.append(state)
        return adapt_market_state_to_view(state)

    monkeypatch.setattr(
        research_workflow,
        "adapt_market_state_to_view",
        spy_adapter,
    )
    result = _run(
        DefaultResearchWorkflow(
            FakeMarketDataService(_prices()),
            state_model=model,
        )
    )

    assert adapted == model.states
    assert result.market_view == MarketView(
        direction="bearish",
        strength="strong",
        trend_state="negative",
        momentum_state="strongly_negative",
        volatility_state="high",
        price_structure="available",
        confidence=None,
    )


def test_bridge_observation_is_point_in_time_and_not_modified() -> None:
    model = FakeStateModel()

    _run(
        DefaultResearchWorkflow(
            FakeMarketDataService(_prices()),
            state_model=model,
        )
    )

    observation = model.observations[0]
    assert observation.to_dict() == model.before_evaluation[0]
    assert observation.identity.symbol == "MSFT"
    assert observation.identity.interval == "1day"
    assert observation.identity.as_of == _AS_OF
    assert observation.price_facts is not None
    assert observation.signal_facts is not None
    assert observation.structure_facts is not None
    assert observation.provenance.methodology == (
        "research_workflow_state_bridge"
    )
    assert observation.provenance.input_fingerprint.startswith("sha256:")


def test_bridge_preserves_research_result_and_market_view_schema() -> None:
    payload = _run(
        DefaultResearchWorkflow(
            FakeMarketDataService(_prices()),
            state_model=FakeStateModel(),
        )
    ).to_dict()

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


def test_state_model_package_does_not_depend_on_research_workflow() -> None:
    state_package = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "market_platform"
        / "state"
    )
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(state_package.glob("*.py"))
    )

    assert "market_platform.research.workflow" not in source
