from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

import market_platform.research.workflow as research_workflow
from market_platform.research.models import MarketView, ResearchRequest
from market_platform.research.modes import ResearchInterpretationMode
from market_platform.research.workflow import DefaultResearchWorkflow
from market_platform.signals.models import MarketSignal, MarketSignalSnapshot
from market_platform.state import BaselineMarketStateModel
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
_DIRECTIONAL_SCALES = {
    "trend": 0.10,
    "momentum": 0.20,
    "current_drawdown": 0.20,
    "distance_from_moving_average": 0.10,
}


class FakeMarketDataService:
    def __init__(self, prices: pd.DataFrame) -> None:
        self.prices = prices
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
        return self.prices.copy(deep=True)


class FakeStructureService:
    def __init__(self, snapshot: PriceStructureSnapshot) -> None:
        self.snapshot = snapshot
        self.inputs: list[pd.DataFrame] = []

    def analyze(self, prices: pd.DataFrame, **kwargs: object) -> PriceStructureSnapshot:
        del kwargs
        self.inputs.append(prices.copy(deep=True))
        return self.snapshot


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


def _signal_snapshot(
    *,
    trend: float | None,
    momentum: float | None,
    drawdown: float | None,
    distance: float | None,
    volatility: float | None,
    omit_momentum: bool = False,
) -> MarketSignalSnapshot:
    scores = {
        "trend": trend,
        "momentum": momentum,
        "current_drawdown": drawdown,
        "distance_from_moving_average": distance,
    }
    signals = [
        MarketSignal(
            symbol="MSFT",
            name=name,
            value=(score * _DIRECTIONAL_SCALES[name] if score is not None else None),
            timestamp=_FACTS_AS_OF,
            parameters={"scale_source": name},
        )
        for name, score in scores.items()
        if not (omit_momentum and name == "momentum")
    ]
    signals.append(
        MarketSignal(
            symbol="MSFT",
            name="realized_volatility",
            value=volatility,
            timestamp=_FACTS_AS_OF,
            parameters={"window": 20},
        )
    )
    return MarketSignalSnapshot(
        symbol="MSFT",
        timestamp=_FACTS_AS_OF,
        signals=tuple(signals),
    )


def _structure_snapshot(
    status: PriceStructureStatus = PriceStructureStatus.OK,
) -> PriceStructureSnapshot:
    if status is PriceStructureStatus.OK:
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
    return PriceStructureSnapshot(
        status=status,
        as_of=_FACTS_AS_OF,
        current_price=102.0,
    )


def _request() -> ResearchRequest:
    return ResearchRequest(
        symbol="MSFT",
        horizon_days=20,
        provider="test-provider",
        as_of=_AS_OF,
    )


def _run(workflow: DefaultResearchWorkflow) -> MarketView:
    result = asyncio.run(workflow.run(_request()))
    assert result.market_view is not None
    return result.market_view


def _run_pair(
    monkeypatch: pytest.MonkeyPatch,
    *,
    signals: MarketSignalSnapshot,
    structure: PriceStructureSnapshot | None = None,
) -> tuple[MarketView, MarketView, pd.DataFrame]:
    prices = _prices()
    monkeypatch.setattr(
        research_workflow,
        "calculate_market_signals",
        lambda frame: signals,
    )
    structure_service = FakeStructureService(structure or _structure_snapshot())
    data_service = FakeMarketDataService(prices)
    legacy = DefaultResearchWorkflow(
        data_service,
        price_structure_service=structure_service,  # type: ignore[arg-type]
        interpretation_mode=ResearchInterpretationMode.LEGACY,
    )
    state = DefaultResearchWorkflow(
        data_service,
        price_structure_service=structure_service,  # type: ignore[arg-type]
        interpretation_mode=ResearchInterpretationMode.STATE,
        state_model=BaselineMarketStateModel(),
    )
    return _run(legacy), _run(state), prices


@pytest.mark.parametrize(
    ("score", "direction", "strength", "component_state"),
    [
        (0.80, "bullish", "strong", "strongly_positive"),
        (0.40, "bullish", "moderate", "positive"),
        (0.00, "neutral", "neutral", "neutral"),
        (-0.40, "bearish", "moderate", "negative"),
        (-0.80, "bearish", "strong", "strongly_negative"),
    ],
)
def test_aligned_directional_regimes_have_strict_view_parity(
    monkeypatch: pytest.MonkeyPatch,
    score: float,
    direction: str,
    strength: str,
    component_state: str,
) -> None:
    snapshot = _signal_snapshot(
        trend=score,
        momentum=score,
        drawdown=score,
        distance=score,
        volatility=0.20,
    )

    legacy, state, _ = _run_pair(monkeypatch, signals=snapshot)

    assert legacy.direction == state.direction == direction
    assert legacy.strength == state.strength == strength
    assert legacy.trend_state == state.trend_state == component_state
    assert legacy.momentum_state == state.momentum_state == component_state
    assert legacy.volatility_state == state.volatility_state == "normal"


def test_trend_momentum_divergence_preserves_composite_parity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = _signal_snapshot(
        trend=0.80,
        momentum=-0.80,
        drawdown=0.80,
        distance=0.80,
        volatility=0.20,
    )

    legacy, state, _ = _run_pair(monkeypatch, signals=snapshot)

    assert legacy.direction == state.direction
    assert legacy.strength == state.strength
    assert legacy.trend_state == state.trend_state == "strongly_positive"
    assert legacy.momentum_state == state.momentum_state == "strongly_negative"


@pytest.mark.parametrize(
    ("volatility", "expected"),
    [(0.10, "low"), (0.20, "normal"), (0.35, "high")],
)
def test_volatility_regimes_have_parity(
    monkeypatch: pytest.MonkeyPatch,
    volatility: float,
    expected: str,
) -> None:
    snapshot = _signal_snapshot(
        trend=0.0,
        momentum=0.0,
        drawdown=0.0,
        distance=0.0,
        volatility=volatility,
    )

    legacy, state, _ = _run_pair(monkeypatch, signals=snapshot)

    assert legacy.volatility_state == state.volatility_state == expected


def test_missing_volatility_has_unavailable_view_parity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = _signal_snapshot(
        trend=0.0,
        momentum=0.0,
        drawdown=0.0,
        distance=0.0,
        volatility=None,
    )

    legacy, state, _ = _run_pair(monkeypatch, signals=snapshot)

    assert legacy.volatility_state == state.volatility_state == "unavailable"


def test_missing_signal_has_unavailable_component_and_view_parity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = _signal_snapshot(
        trend=0.40,
        momentum=None,
        drawdown=0.40,
        distance=0.40,
        volatility=0.20,
        omit_momentum=True,
    )

    legacy, state, _ = _run_pair(monkeypatch, signals=snapshot)

    assert legacy.direction == state.direction == "bullish"
    assert legacy.strength == state.strength == "moderate"
    assert legacy.trend_state == state.trend_state == "positive"
    assert legacy.momentum_state == state.momentum_state is None


def test_structure_non_ok_does_not_create_structure_interpretation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = _signal_snapshot(
        trend=0.0,
        momentum=0.0,
        drawdown=0.0,
        distance=0.0,
        volatility=0.20,
    )

    legacy, state, _ = _run_pair(
        monkeypatch,
        signals=snapshot,
        structure=_structure_snapshot(PriceStructureStatus.NO_PIVOTS),
    )

    assert legacy.price_structure is None
    assert state.price_structure is None
    assert legacy.confidence is state.confidence is None


def test_available_structure_is_an_intentional_state_view_enrichment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = _signal_snapshot(
        trend=0.0,
        momentum=0.0,
        drawdown=0.0,
        distance=0.0,
        volatility=0.20,
    )

    legacy, state, _ = _run_pair(monkeypatch, signals=snapshot)

    assert legacy.price_structure is None
    assert state.price_structure == "available"


def test_both_paths_are_deterministic_and_preserve_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = _signal_snapshot(
        trend=0.40,
        momentum=0.40,
        drawdown=0.40,
        distance=0.40,
        volatility=0.20,
    )
    signal_parameters = [
        dict(signal.parameters) for signal in snapshot.signals
    ]

    first_legacy, first_state, prices = _run_pair(
        monkeypatch,
        signals=snapshot,
    )
    prices_before = prices.copy(deep=True)
    second_legacy, second_state, _ = _run_pair(
        monkeypatch,
        signals=snapshot,
    )

    assert first_legacy == second_legacy
    assert first_state == second_state
    assert_frame_equal(prices, prices_before)
    assert [signal.parameters for signal in snapshot.signals] == signal_parameters
    assert snapshot.timestamp == _FACTS_AS_OF
