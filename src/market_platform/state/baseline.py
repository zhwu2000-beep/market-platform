"""Deterministic baseline market state model."""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import UTC, datetime
from numbers import Real

from market_platform.observation.models import MarketObservation
from market_platform.signals.classification import (
    SignalClassification,
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
    StateClassificationThresholdEvidence,
    StateCompositeEvidence,
    StateEvaluationEvidence,
    StateModelProvenance,
    StateQuality,
    StateSignalEvidence,
    StateVolatilityEvidence,
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

        scores = {
            "trend": trend_score,
            "momentum": momentum_score,
            "current_drawdown": current_drawdown_score,
            "distance_from_moving_average": distance_score,
        }
        valid_components = {
            "trend": trend_valid,
            "momentum": momentum_valid,
            "current_drawdown": current_drawdown_valid,
            "distance_from_moving_average": distance_valid,
        }
        component_levels = {
            name: (
                _classification_level(score)
                if valid_components[name] and score is not None
                else None
            )
            for name, score in scores.items()
        }
        trend_regime = _trend_regime(component_levels["trend"])
        momentum_regime = _momentum_regime(component_levels["momentum"])
        directional_regime, composite, classification = _directional_evaluation(
            observation,
            scores=scores,
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
        evaluation_evidence = _build_evaluation_evidence(
            signals=signals,
            scores=scores,
            component_levels=component_levels,
            composite=composite,
            classification=classification,
            volatility_regime=volatility_regime,
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
            evaluation_evidence=evaluation_evidence,
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


def _trend_regime(
    level: SignalClassificationLevel | None,
) -> TrendRegime:
    if level is None:
        return TrendRegime.UNAVAILABLE
    return _TREND_LEVEL_MAP[level]


def _momentum_regime(
    level: SignalClassificationLevel | None,
) -> MomentumRegime:
    if level is None:
        return MomentumRegime.UNAVAILABLE
    return _MOMENTUM_LEVEL_MAP[level]


def _directional_evaluation(
    observation: MarketObservation,
    *,
    scores: dict[str, float | None],
) -> tuple[
    DirectionalRegime,
    MarketSignal,
    SignalClassification | None,
]:
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
        return DirectionalRegime.UNAVAILABLE, composite, None
    classification = classify_composite_signal(composite)
    return (
        _DIRECTIONAL_LEVEL_MAP[classification.level],
        composite,
        classification,
    )


def _build_evaluation_evidence(
    *,
    signals: dict[str, MarketSignal],
    scores: dict[str, float | None],
    component_levels: dict[
        str,
        SignalClassificationLevel | None,
    ],
    composite: MarketSignal,
    classification: SignalClassification | None,
    volatility_regime: VolatilityRegime,
) -> StateEvaluationEvidence:
    configured_weights = _numeric_mapping_parameter(
        composite,
        "configured_weights",
    )
    normalized_weights = _numeric_mapping_parameter(
        composite,
        "normalized_weights",
    )
    contributions = _numeric_mapping_parameter(
        composite,
        "component_contributions",
    )
    components = tuple(
        StateSignalEvidence(
            name=name,
            raw_value=_raw_signal_value(signals.get(name)),
            normalized_score=scores[name],
            normalization_scale=_DIRECTIONAL_SCALES[name],
            configured_weight=configured_weights[name],
            normalized_weight=normalized_weights.get(name),
            weighted_contribution=contributions.get(name),
            interpreted_state=_evidence_state(component_levels[name]),
            methodology="baseline_uncalibrated_directional_rescaling_v1",
            source_parameters=(
                signals[name].parameters if name in signals else {}
            ),
        )
        for name in _DIRECTIONAL_SCALES
    )
    thresholds = (
        classification.thresholds
        if classification is not None
        else SignalClassificationThresholds()
    )
    volatility_signal = signals.get("realized_volatility")
    return StateEvaluationEvidence(
        directional_components=components,
        composite=StateCompositeEvidence(
            score=(
                float(composite.value)
                if composite.value is not None
                else None
            ),
            classification=(
                classification.level.value
                if classification is not None
                else None
            ),
            methodology="baseline_uncalibrated_composite_v1",
            formula="sum(normalized_score * normalized_weight)",
            thresholds=StateClassificationThresholdEvidence(
                strong_bearish=thresholds.strong_bearish,
                bearish=thresholds.bearish,
                bullish=thresholds.bullish,
                strong_bullish=thresholds.strong_bullish,
            ),
            component_order=tuple(_DIRECTIONAL_SCALES),
            included_signals=_string_sequence_parameter(
                composite,
                "included_signals",
            ),
            missing_signals=_string_sequence_parameter(
                composite,
                "missing_signals",
            ),
        ),
        volatility=StateVolatilityEvidence(
            raw_value=_raw_signal_value(volatility_signal),
            low_threshold=_VOLATILITY_LOW_THRESHOLD,
            high_threshold=_VOLATILITY_HIGH_THRESHOLD,
            regime=volatility_regime,
            methodology="baseline_realized_volatility_thresholds_v1",
        ),
    )


def _evidence_state(
    level: SignalClassificationLevel | None,
) -> str:
    if level is None:
        return "unavailable"
    return {
        SignalClassificationLevel.STRONG_BEARISH: "strongly_negative",
        SignalClassificationLevel.BEARISH: "negative",
        SignalClassificationLevel.NEUTRAL: "neutral",
        SignalClassificationLevel.BULLISH: "positive",
        SignalClassificationLevel.STRONG_BULLISH: "strongly_positive",
    }[level]


def _raw_signal_value(signal: MarketSignal | None) -> float | None:
    if signal is None or signal.value is None:
        return None
    value = signal.value
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    numeric = float(value)
    return numeric if math.isfinite(numeric) else None


def _numeric_mapping_parameter(
    signal: MarketSignal,
    field_name: str,
) -> dict[str, float]:
    value = signal.parameters.get(field_name)
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    return {str(name): float(number) for name, number in value.items()}


def _string_sequence_parameter(
    signal: MarketSignal,
    field_name: str,
) -> tuple[str, ...]:
    value = signal.parameters.get(field_name)
    if not isinstance(value, (list, tuple)):
        raise TypeError(f"{field_name} must be a list or tuple")
    return tuple(str(item) for item in value)


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
