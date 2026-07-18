from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

import pytest

from market_platform.replay import (
    HistoricalReplayResult,
    HistoricalReplayStep,
    ReplayStrategyIdentity,
)
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
from market_platform.strategy import StrategyRunResult

_AS_OF = datetime(2026, 1, 1, tzinfo=UTC)
_FINGERPRINT = "sha256:observation"


def _state(as_of: datetime = _AS_OF) -> MarketState:
    return MarketState(
        symbol="MSFT",
        interval="1day",
        as_of=as_of,
        provenance=StateModelProvenance(
            model_id="state-model",
            model_version="1.0.0",
            parameters={},
            observation_fingerprint=_FINGERPRINT,
        ),
        directional_regime=DirectionalRegime.UP,
        trend_regime=TrendRegime.UP,
        momentum_regime=MomentumRegime.POSITIVE,
        volatility_regime=VolatilityRegime.NORMAL,
        structure_state=StructureState.AVAILABLE,
        quality=StateQuality.COMPLETE,
    )


def _strategy_result(as_of: datetime = _AS_OF) -> StrategyRunResult:
    return StrategyRunResult(
        symbol="MSFT",
        interval="1day",
        as_of=as_of,
        observation_fingerprint=_FINGERPRINT,
        state_model_id="state-model",
        state_model_version="1.0.0",
        evaluations=(),
    )


def _step(as_of: datetime = _AS_OF) -> HistoricalReplayStep:
    return HistoricalReplayStep(
        symbol="MSFT",
        interval="1day",
        as_of=as_of,
        observation_fingerprint=_FINGERPRINT,
        state=_state(as_of),
        strategy_result=_strategy_result(as_of),
    )


def test_replay_strategy_identity_is_immutable_and_serializable() -> None:
    identity = ReplayStrategyIdentity(" trend ", " 1.0.0 ", " sha256:cfg ")

    assert identity.to_dict() == {
        "strategy_id": "trend",
        "strategy_version": "1.0.0",
        "configuration_fingerprint": "sha256:cfg",
    }
    with pytest.raises(FrozenInstanceError):
        identity.strategy_id = "other"  # type: ignore[misc]


def test_replay_step_validates_identity() -> None:
    with pytest.raises(ValueError, match="fingerprint"):
        HistoricalReplayStep(
            symbol="MSFT",
            interval="1day",
            as_of=_AS_OF,
            observation_fingerprint="sha256:other",
            state=_state(),
            strategy_result=_strategy_result(),
        )


def test_replay_result_validates_order_and_state_model_identity() -> None:
    with pytest.raises(ValueError, match="strictly ordered"):
        HistoricalReplayResult(
            symbol="MSFT",
            interval="1day",
            start_as_of=_AS_OF,
            end_as_of=_AS_OF,
            steps=[_step(_AS_OF), _step(_AS_OF)],
            state_model_id="state-model",
            state_model_version="1.0.0",
            strategies=(),
        )


def test_replay_result_to_dict_and_step_count() -> None:
    result = HistoricalReplayResult(
        symbol="MSFT",
        interval="1day",
        start_as_of=_AS_OF,
        end_as_of=_AS_OF + timedelta(days=1),
        steps=[_step(_AS_OF), _step(_AS_OF + timedelta(days=1))],
        state_model_id="state-model",
        state_model_version="1.0.0",
        strategies=[],
    )

    payload = result.to_dict()
    assert result.step_count == 2
    assert payload["steps"][0]["strategy_result"]["evaluations"] == []
    assert payload["strategies"] == []
    assert not hasattr(result, "strategy_collection")
