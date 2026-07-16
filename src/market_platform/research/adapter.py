"""Adapters from market state domain models to research DTOs."""

from __future__ import annotations

from market_platform.observation.models import MarketObservation
from market_platform.research.models import (
    MarketView,
    PriceContext,
    PriceLevel,
    ResearchAnalysis,
    ResearchCompositeAssessment,
    ResearchSignalComponent,
    ResearchStructureAssessment,
)
from market_platform.research.price_context import build_price_context
from market_platform.research.target_framework import build_structural_target_levels
from market_platform.signals.models import MarketSignal
from market_platform.state.models import (
    DirectionalRegime,
    MarketState,
    MomentumRegime,
    StateSignalEvidence,
    StructureState,
    TrendRegime,
    VolatilityRegime,
)
from market_platform.structure.models import ObservedPriceZone

_DIRECTIONAL_VIEW_MAP: dict[
    DirectionalRegime,
    tuple[str | None, str | None],
] = {
    DirectionalRegime.STRONG_UP: ("bullish", "strong"),
    DirectionalRegime.UP: ("bullish", "moderate"),
    DirectionalRegime.NEUTRAL: ("neutral", "neutral"),
    DirectionalRegime.DOWN: ("bearish", "moderate"),
    DirectionalRegime.STRONG_DOWN: ("bearish", "strong"),
    DirectionalRegime.UNAVAILABLE: (None, None),
    DirectionalRegime.INDETERMINATE: (None, None),
}

_TREND_VIEW_MAP: dict[TrendRegime, str | None] = {
    TrendRegime.STRONG_UP: "strongly_positive",
    TrendRegime.UP: "positive",
    TrendRegime.NEUTRAL: "neutral",
    TrendRegime.DOWN: "negative",
    TrendRegime.STRONG_DOWN: "strongly_negative",
    TrendRegime.UNAVAILABLE: None,
    TrendRegime.INDETERMINATE: "indeterminate",
}

_MOMENTUM_VIEW_MAP: dict[MomentumRegime, str | None] = {
    MomentumRegime.STRONG_POSITIVE: "strongly_positive",
    MomentumRegime.POSITIVE: "positive",
    MomentumRegime.NEUTRAL: "neutral",
    MomentumRegime.NEGATIVE: "negative",
    MomentumRegime.STRONG_NEGATIVE: "strongly_negative",
    MomentumRegime.UNAVAILABLE: None,
    MomentumRegime.INDETERMINATE: "indeterminate",
}

_VOLATILITY_VIEW_MAP: dict[VolatilityRegime, str] = {
    VolatilityRegime.LOW: "low",
    VolatilityRegime.NORMAL: "normal",
    VolatilityRegime.HIGH: "high",
    VolatilityRegime.UNAVAILABLE: "unavailable",
    VolatilityRegime.INDETERMINATE: "indeterminate",
}

_STRUCTURE_VIEW_MAP: dict[StructureState, str | None] = {
    StructureState.AVAILABLE: "available",
    StructureState.OBSERVED: "observed",
    StructureState.INSUFFICIENT: "insufficient",
    StructureState.UNAVAILABLE: None,
    StructureState.INDETERMINATE: "indeterminate",
}
_DIRECTIONAL_SIGNAL_NAMES = {
    "trend",
    "momentum",
    "current_drawdown",
    "distance_from_moving_average",
}
_STATE_COMPONENT_METHODOLOGY = "market_state_evidence_projection_v1"
_RAW_COMPONENT_METHODOLOGY = "market_observation_raw_signal_v1"
_STATE_COMPOSITE_METHODOLOGY = "market_state_composite_unavailable_v1"


def adapt_market_state_to_view(state: MarketState) -> MarketView:
    """Project an evaluated market state into the existing research DTO."""

    if not isinstance(state, MarketState):
        raise TypeError("state must be a MarketState")

    direction, strength = _DIRECTIONAL_VIEW_MAP[state.directional_regime]
    return MarketView(
        direction=direction,
        strength=strength,
        trend_state=_TREND_VIEW_MAP[state.trend_regime],
        momentum_state=_MOMENTUM_VIEW_MAP[state.momentum_regime],
        volatility_state=_VOLATILITY_VIEW_MAP[state.volatility_regime],
        price_structure=_STRUCTURE_VIEW_MAP[state.structure_state],
        confidence=None,
    )


def adapt_market_state_to_analysis(
    state: MarketState,
    observation: MarketObservation,
) -> ResearchAnalysis:
    """Project state and its source facts into an evidence-only analysis DTO."""

    if not isinstance(state, MarketState):
        raise TypeError("state must be a MarketState")
    if not isinstance(observation, MarketObservation):
        raise TypeError("observation must be a MarketObservation")
    if state.symbol != observation.identity.symbol:
        raise ValueError("state and observation symbols must match")
    if state.as_of != observation.identity.as_of:
        raise ValueError("state and observation as_of values must match")

    signals = (
        observation.signal_facts.signals
        if observation.signal_facts is not None
        else ()
    )
    components = tuple(
        _adapt_signal_component(
            signal,
            state,
            _directional_evidence_by_name(state).get(signal.name),
        )
        for signal in signals
    )
    volatility_state, volatility_value = _analysis_volatility(
        state,
        signals,
    )
    price_context = _adapt_price_context(observation)
    return ResearchAnalysis(
        symbol=state.symbol,
        timestamp=(
            observation.signal_facts.as_of
            if observation.signal_facts is not None
            else state.as_of
        ),
        components=components,
        volatility_state=volatility_state,
        volatility_value=volatility_value,
        composite=_adapt_composite_assessment(state),
        structure=_adapt_structure_assessment(observation),
        price_context=price_context,
        structural_target_levels=build_structural_target_levels(price_context),
    )


def _adapt_signal_component(
    signal: MarketSignal,
    state: MarketState,
    evidence: StateSignalEvidence | None,
) -> ResearchSignalComponent:
    if evidence is not None:
        thresholds = state.evaluation_evidence
        assert thresholds is not None
        classification_thresholds = thresholds.composite.thresholds
        return ResearchSignalComponent(
            name=signal.name,
            raw_value=evidence.raw_value,
            score=evidence.normalized_score,
            state=evidence.interpreted_state,
            role="directional",
            methodology=evidence.methodology,
            parameters={
                "signal_name": evidence.name,
                "role": "directional",
                "methodology": evidence.methodology,
                "scale": evidence.normalization_scale,
                "formula": "clamp(raw_value / scale, -1.0, 1.0)",
                "configured_weight": evidence.configured_weight,
                "normalized_weight": evidence.normalized_weight,
                "weighted_contribution": evidence.weighted_contribution,
                "classification_thresholds": (
                    classification_thresholds.to_dict()
                ),
                "source_parameters": dict(evidence.source_parameters),
            },
        )
    if (
        signal.name == "realized_volatility"
        and state.evaluation_evidence is not None
    ):
        volatility = state.evaluation_evidence.volatility
        return ResearchSignalComponent(
            name=signal.name,
            raw_value=volatility.raw_value,
            score=None,
            state=_VOLATILITY_VIEW_MAP[volatility.regime],
            role="volatility",
            methodology=volatility.methodology,
            parameters={
                "low_threshold": volatility.low_threshold,
                "high_threshold": volatility.high_threshold,
                "source_parameters": dict(signal.parameters),
            },
        )
    interpreted_state = _signal_state(signal, state)
    methodology = (
        _STATE_COMPONENT_METHODOLOGY
        if signal.name in {"trend", "momentum", "realized_volatility"}
        else _RAW_COMPONENT_METHODOLOGY
    )
    role = (
        "volatility"
        if signal.name == "realized_volatility"
        else "directional"
        if signal.name in _DIRECTIONAL_SIGNAL_NAMES
        else "observed"
    )
    return ResearchSignalComponent(
        name=signal.name,
        raw_value=signal.value,
        score=None,
        state=interpreted_state,
        role=role,
        methodology=methodology,
        parameters={
            "source": "market_observation",
            "source_parameters": dict(signal.parameters),
            "state_model_id": state.provenance.model_id,
            "state_model_version": state.provenance.model_version,
        },
    )


def _directional_evidence_by_name(
    state: MarketState,
) -> dict[str, StateSignalEvidence]:
    if state.evaluation_evidence is None:
        return {}
    return {
        evidence.name: evidence
        for evidence in state.evaluation_evidence.directional_components
    }


def _adapt_composite_assessment(
    state: MarketState,
) -> ResearchCompositeAssessment:
    evaluation = state.evaluation_evidence
    if evaluation is None:
        return ResearchCompositeAssessment(
            score=None,
            classification=None,
            included_signals=(),
            missing_signals=(),
            configured_weights={},
            normalized_weights={},
            component_contributions={},
            methodology=_STATE_COMPOSITE_METHODOLOGY,
        )
    components = evaluation.directional_components
    return ResearchCompositeAssessment(
        score=evaluation.composite.score,
        classification=evaluation.composite.classification,
        included_signals=evaluation.composite.included_signals,
        missing_signals=evaluation.composite.missing_signals,
        configured_weights={
            component.name: component.configured_weight
            for component in components
        },
        normalized_weights={
            component.name: component.normalized_weight
            for component in components
            if component.normalized_weight is not None
        },
        component_contributions={
            component.name: component.weighted_contribution
            for component in components
            if component.weighted_contribution is not None
        },
        methodology=evaluation.composite.methodology,
    )


def _signal_state(signal: MarketSignal, state: MarketState) -> str:
    if signal.name == "trend":
        return _TREND_VIEW_MAP[state.trend_regime] or "unavailable"
    if signal.name == "momentum":
        return _MOMENTUM_VIEW_MAP[state.momentum_regime] or "unavailable"
    if signal.name == "realized_volatility":
        return _VOLATILITY_VIEW_MAP[state.volatility_regime]
    return "observed" if signal.value is not None else "unavailable"


def _analysis_volatility(
    state: MarketState,
    signals: tuple[MarketSignal, ...],
) -> tuple[str | None, float | None]:
    if state.evaluation_evidence is not None:
        volatility = state.evaluation_evidence.volatility
        state_value = _VOLATILITY_VIEW_MAP[volatility.regime]
        if state_value not in {"low", "normal", "high", "unavailable"}:
            return None, None
        return (
            state_value,
            None if state_value == "unavailable" else volatility.raw_value,
        )
    volatility_state = _VOLATILITY_VIEW_MAP[state.volatility_regime]
    if volatility_state not in {"low", "normal", "high", "unavailable"}:
        return None, None
    if volatility_state == "unavailable":
        return volatility_state, None
    volatility_signal = next(
        (
            signal
            for signal in signals
            if signal.name == "realized_volatility"
        ),
        None,
    )
    if volatility_signal is None or volatility_signal.value is None:
        return None, None
    return (
        volatility_state,
        volatility_signal.value,
    )


def _adapt_structure_assessment(
    observation: MarketObservation,
) -> ResearchStructureAssessment | None:
    facts = observation.structure_facts
    if facts is None:
        return None
    return ResearchStructureAssessment(
        status=facts.status.value,
        as_of=facts.as_of,
        current_price=facts.current_price,
        atr=facts.atr,
        candidate_count=len(facts.confirmed_pivots),
        zone_count=len(facts.available_zones),
    )


def _adapt_price_context(
    observation: MarketObservation,
) -> PriceContext | None:
    facts = observation.structure_facts
    if (
        facts is None
        or facts.status.value != "ok"
        or facts.current_price is None
    ):
        return None
    return build_price_context(
        facts.current_price,
        _adapt_price_levels(facts.current_price, facts.available_zones),
    )


def _adapt_price_levels(
    current_price: float,
    available_zones: tuple[ObservedPriceZone, ...],
) -> tuple[PriceLevel, ...]:
    lower_zones = sorted(
        (
            observed
            for observed in available_zones
            if observed.zone.upper_bound < current_price
        ),
        key=lambda observed: (
            current_price - observed.zone.upper_bound,
            -observed.zone.midpoint,
            observed.zone.lower_bound,
        ),
    )
    containing_zones = tuple(
        observed
        for observed in available_zones
        if observed.zone.lower_bound <= current_price <= observed.zone.upper_bound
    )
    upper_zones = sorted(
        (
            observed
            for observed in available_zones
            if observed.zone.lower_bound > current_price
        ),
        key=lambda observed: (
            observed.zone.lower_bound - current_price,
            observed.zone.midpoint,
            observed.zone.upper_bound,
        ),
    )
    return tuple(
        [
            _price_level(observed, "support")
            for observed in lower_zones
        ]
        + [
            _price_level(observed, "current_zone")
            for observed in containing_zones
        ]
        + [
            _price_level(observed, "resistance")
            for observed in upper_zones
        ]
    )


def _price_level(observed: ObservedPriceZone, level_type: str) -> PriceLevel:
    zone = observed.zone
    return PriceLevel(
        lower=zone.lower_bound,
        upper=zone.upper_bound,
        level_type=level_type,
        strength=None,
        sources=zone.source_methods,
    )


__all__ = [
    "adapt_market_state_to_analysis",
    "adapt_market_state_to_view",
]
