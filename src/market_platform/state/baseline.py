"""Deterministic baseline market state model."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from numbers import Real

from market_platform.observation.models import MarketObservation
from market_platform.signals.classification import (
    SignalClassificationLevel,
    SignalClassificationThresholds,
    classify_composite_signal,
)
from market_platform.signals.composite import calculate_composite_signal
from market_platform.signals.models import MarketSignal
from market_platform.state.models import (
    DirectionalRegime,
    MarketState,
    MomentumRegime,
    StateModelProvenance,
    StateQuality,
    StructureState,
    TrendRegime,
    VolatilityRegime,
)

_MODEL_ID = "baseline_rule_state_model"
_MODEL_VERSION = "1.0.0"
_RULES_VERSION = "baseline_state_rules_v1"
_TREND_SCALE = 0.10
_MOMENTUM_SCALE = 0.20
_CURRENT_DRAWDOWN_SCALE = 0.20
_DISTANCE_FROM_MOVING_AVERAGE_SCALE = 0.10
_DIRECTIONAL_SCALES = {
    "trend": _TREND_SCALE,
    "momentum": _MOMENTUM_SCALE,
    "current_drawdown": _CURRENT_DRAWDOWN_SCALE,
    "distance_from_moving_average": _DISTANCE_FROM_MOVING_AVERAGE_SCALE,
}
_DIRECTIONAL_WEIGHTS = dict.fromkeys(_DIRECTIONAL_SCALES, 1.0)
_VOLATILITY_LOW_THRESHOLD = 0.15
_VOLATILITY_HIGH_THRESHOLD = 0.30
_REFERENCE_TIMESTAMP = datetime(1970, 1, 1, tzinfo=UTC)

_DIRECTIONAL_LEVEL_MAP = {
    SignalClassificationLevel.STRONG_BEARISH: DirectionalRegime.STRONG_DOWN,
    SignalClassificationLevel.BEARISH: DirectionalRegime.DOWN,
    SignalClassificationLevel.NEUTRAL: DirectionalRegime.NEUTRAL,
    SignalClassificationLevel.BULLISH: DirectionalRegime.UP,
    SignalClassificationLevel.STRONG_BULLISH: DirectionalRegime.STRONG_UP,
}
_TREND_LEVEL_MAP = {
    SignalClassificationLevel.STRONG_BEARISH: TrendRegime.STRONG_DOWN,
    SignalClassificationLevel.BEARISH: TrendRegime.DOWN,
    SignalClassificationLevel.NEUTRAL: TrendRegime.NEUTRAL,
    SignalClassificationLevel.BULLISH: TrendRegime.UP,
    SignalClassificationLevel.STRONG_BULLISH: TrendRegime.STRONG_UP,
}
_MOMENTUM_LEVEL_MAP = {
    SignalClassificationLevel.STRONG_BEARISH: MomentumRegime.STRONG_NEGATIVE,
    SignalClassificationLevel.BEARISH: MomentumRegime.NEGATIVE,
    SignalClassificationLevel.NEUTRAL: MomentumRegime.NEUTRAL,
    SignalClassificationLevel.BULLISH: MomentumRegime.POSITIVE,
    SignalClassificationLevel.STRONG_BULLISH: MomentumRegime.STRONG_POSITIVE,
}


class BaselineMarketStateModel:
    """Evaluate observations with transparent, versioned baseline rules."""

    __slots__ = ()

    @property
    def model_id(self) -> str:
        """Return the stable baseline model identity."""

        return _MODEL_ID

    @property
    def model_version(self) -> str:
        """Return the baseline rules version."""

        return _MODEL_VERSION

    def evaluate(self, observation: MarketObservation) -> MarketState:
        """Return state derived only from the supplied point-in-time facts."""

        if not isinstance(observation, MarketObservation):
            raise TypeError("observation must be a MarketObservation")

        signals = (
            {signal.name: signal for signal in observation.signal_facts.signals}
            if observation.signal_facts is not None
            else {}
        )
        trend_score, trend_valid = _scaled_signal_score(
            signals.get("trend"),
            _TREND_SCALE,
        )
        momentum_score, momentum_valid = _scaled_signal_score(
            signals.get("momentum"),
            _MOMENTUM_SCALE,
        )
        current_drawdown_score, current_drawdown_valid = _scaled_signal_score(
            signals.get("current_drawdown"),
            _CURRENT_DRAWDOWN_SCALE,
        )
        distance_score, distance_valid = _scaled_signal_score(
            signals.get("distance_from_moving_average"),
            _DISTANCE_FROM_MOVING_AVERAGE_SCALE,
        )

        trend_regime = _trend_regime(trend_score, trend_valid)
        momentum_regime = _momentum_regime(momentum_score, momentum_valid)
        directional_regime = _directional_regime(
            observation,
            trend_score=trend_score,
            trend_valid=trend_valid,
            momentum_score=momentum_score,
            momentum_valid=momentum_valid,
            current_drawdown_score=current_drawdown_score,
            current_drawdown_valid=current_drawdown_valid,
            distance_score=distance_score,
            distance_valid=distance_valid,
        )
        volatility_regime, volatility_valid = _volatility_regime(
            signals.get("realized_volatility")
        )
        structure_available = (
            observation.structure_facts is not None
            and observation.structure_facts.status.value == "ok"
        )
        structure_state = (
            StructureState.AVAILABLE
            if structure_available
            else StructureState.UNAVAILABLE
        )
        missing_inputs = _missing_inputs(
            has_signal_facts=observation.signal_facts is not None,
            trend_valid=trend_valid,
            momentum_valid=momentum_valid,
            current_drawdown_valid=current_drawdown_valid,
            distance_valid=distance_valid,
            volatility_valid=volatility_valid,
            has_available_structure_facts=structure_available,
        )
        quality = _state_quality(
            directional_regime=directional_regime,
            trend_regime=trend_regime,
            momentum_regime=momentum_regime,
            volatility_regime=volatility_regime,
            structure_state=structure_state,
            missing_inputs=missing_inputs,
        )

        return MarketState(
            symbol=observation.identity.symbol,
            interval=observation.identity.interval,
            as_of=observation.identity.as_of,
            provenance=StateModelProvenance(
                model_id=self.model_id,
                model_version=self.model_version,
                parameters=_model_parameters(),
                observation_fingerprint=(
                    observation.provenance.input_fingerprint
                ),
            ),
            directional_regime=directional_regime,
            trend_regime=trend_regime,
            momentum_regime=momentum_regime,
            volatility_regime=volatility_regime,
            structure_state=structure_state,
            quality=quality,
            missing_inputs=missing_inputs,
        )


def _scaled_signal_score(
    signal: MarketSignal | None,
    scale: float,
) -> tuple[float | None, bool]:
    if signal is None or signal.value is None:
        return None, False
    value = signal.value
    if isinstance(value, bool) or not isinstance(value, Real):
        return None, False
    numeric = float(value)
    if not math.isfinite(numeric):
        return None, False
    return max(-1.0, min(1.0, numeric / scale)), True


def _trend_regime(score: float | None, valid: bool) -> TrendRegime:
    if not valid or score is None:
        return TrendRegime.UNAVAILABLE
    return _TREND_LEVEL_MAP[_classification_level(score)]


def _momentum_regime(score: float | None, valid: bool) -> MomentumRegime:
    if not valid or score is None:
        return MomentumRegime.UNAVAILABLE
    return _MOMENTUM_LEVEL_MAP[_classification_level(score)]


def _directional_regime(
    observation: MarketObservation,
    *,
    trend_score: float | None,
    trend_valid: bool,
    momentum_score: float | None,
    momentum_valid: bool,
    current_drawdown_score: float | None,
    current_drawdown_valid: bool,
    distance_score: float | None,
    distance_valid: bool,
) -> DirectionalRegime:
    if not any(
        (
            trend_valid,
            momentum_valid,
            current_drawdown_valid,
            distance_valid,
        )
    ):
        return DirectionalRegime.UNAVAILABLE

    scores = {
        "trend": trend_score,
        "momentum": momentum_score,
        "current_drawdown": current_drawdown_score,
        "distance_from_moving_average": distance_score,
    }
    components = tuple(
        MarketSignal(
            symbol=observation.identity.symbol,
            name=name,
            value=score,
            timestamp=observation.identity.as_of,
            parameters={"scale": _DIRECTIONAL_SCALES[name]},
        )
        for name, score in scores.items()
    )
    composite = calculate_composite_signal(
        components,
        _DIRECTIONAL_WEIGHTS,
        missing_policy="exclude",
    )
    if composite.value is None:
        return DirectionalRegime.UNAVAILABLE
    classification = classify_composite_signal(composite)
    return _DIRECTIONAL_LEVEL_MAP[classification.level]


def _volatility_regime(
    signal: MarketSignal | None,
) -> tuple[VolatilityRegime, bool]:
    if signal is None or signal.value is None:
        return VolatilityRegime.UNAVAILABLE, False
    value = signal.value
    if isinstance(value, bool) or not isinstance(value, Real):
        return VolatilityRegime.INDETERMINATE, False
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0.0:
        return VolatilityRegime.INDETERMINATE, False
    if numeric < _VOLATILITY_LOW_THRESHOLD:
        return VolatilityRegime.LOW, True
    if numeric < _VOLATILITY_HIGH_THRESHOLD:
        return VolatilityRegime.NORMAL, True
    return VolatilityRegime.HIGH, True


def _classification_level(score: float) -> SignalClassificationLevel:
    signal = MarketSignal(
        symbol="STATE",
        name="composite_score",
        value=score,
        timestamp=_REFERENCE_TIMESTAMP,
        parameters={},
    )
    return classify_composite_signal(signal).level


def _missing_inputs(
    *,
    has_signal_facts: bool,
    trend_valid: bool,
    momentum_valid: bool,
    current_drawdown_valid: bool,
    distance_valid: bool,
    volatility_valid: bool,
    has_available_structure_facts: bool,
) -> tuple[str, ...]:
    if not has_signal_facts:
        missing = ["signal_facts"]
    else:
        missing = []
        if not trend_valid:
            missing.append("trend")
        if not momentum_valid:
            missing.append("momentum")
        if not current_drawdown_valid:
            missing.append("current_drawdown")
        if not distance_valid:
            missing.append("distance_from_moving_average")
        if not volatility_valid:
            missing.append("realized_volatility")
    if not has_available_structure_facts:
        missing.append("structure_facts")
    return tuple(missing)


def _state_quality(
    *,
    directional_regime: DirectionalRegime,
    trend_regime: TrendRegime,
    momentum_regime: MomentumRegime,
    volatility_regime: VolatilityRegime,
    structure_state: StructureState,
    missing_inputs: tuple[str, ...],
) -> StateQuality:
    regimes = (
        directional_regime,
        trend_regime,
        momentum_regime,
        volatility_regime,
        structure_state,
    )
    if not missing_inputs:
        return StateQuality.COMPLETE
    if all(regime.value == "unavailable" for regime in regimes):
        return StateQuality.UNAVAILABLE
    return StateQuality.DEGRADED


def _model_parameters() -> dict[str, object]:
    thresholds = SignalClassificationThresholds()
    return {
        "rules_version": _RULES_VERSION,
        "directional_components": list(_DIRECTIONAL_SCALES),
        "directional_scales": dict(_DIRECTIONAL_SCALES),
        "directional_weights": dict(_DIRECTIONAL_WEIGHTS),
        "classification_thresholds": {
            "strong_down": thresholds.strong_bearish,
            "down": thresholds.bearish,
            "up": thresholds.bullish,
            "strong_up": thresholds.strong_bullish,
        },
        "volatility_thresholds": {
            "low": _VOLATILITY_LOW_THRESHOLD,
            "high": _VOLATILITY_HIGH_THRESHOLD,
        },
        "structure_rule": "status_ok",
    }
