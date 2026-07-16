"""Adapters from market state domain models to research DTOs."""

from __future__ import annotations

from market_platform.research.models import MarketView
from market_platform.state.models import (
    DirectionalRegime,
    MarketState,
    MomentumRegime,
    StructureState,
    TrendRegime,
    VolatilityRegime,
)

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


__all__ = ["adapt_market_state_to_view"]
