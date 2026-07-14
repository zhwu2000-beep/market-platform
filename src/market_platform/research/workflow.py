"""Research workflow interface and default implementation."""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from numbers import Real
from typing import Protocol, runtime_checkable

from market_platform.data.service import MarketDataService
from market_platform.research.interpretation import (
    DIRECTIONAL_CURRENT_DRAWDOWN_SCALE,
    DIRECTIONAL_DISTANCE_FROM_MOVING_AVERAGE_SCALE,
    DIRECTIONAL_MOMENTUM_SCALE,
    DIRECTIONAL_TREND_SCALE,
    InterpretedSignal,
    InterpretedSignalState,
    SignalRole,
    VolatilityAssessment,
    calculate_research_composite_signal,
    interpret_directional_signals,
    interpret_realized_volatility,
)
from market_platform.research.models import (
    MarketView,
    PositionContext,
    PriceContext,
    PriceLevel,
    ResearchAnalysis,
    ResearchCompositeAssessment,
    ResearchRequest,
    ResearchResult,
    ResearchSignalComponent,
    ResearchStatus,
    ResearchStructureAssessment,
    ResearchWarning,
)
from market_platform.research.price_context import build_price_context
from market_platform.signals import (
    calculate_market_signals,
    classify_composite_signal,
)
from market_platform.signals.classification import SignalClassification
from market_platform.signals.models import MarketSignal, MarketSignalSnapshot
from market_platform.structure.models import (
    PriceStructureSnapshot,
    PriceStructureStatus,
)
from market_platform.structure.service import PriceStructureService

_DIRECTIONAL_SIGNAL_NAMES = (
    "trend",
    "momentum",
    "current_drawdown",
    "distance_from_moving_average",
)
_DIRECTIONAL_METHODOLOGY = "baseline_uncalibrated_directional_rescaling_v1"
_COMPOSITE_METHODOLOGY = "baseline_uncalibrated_composite_v1"


@runtime_checkable
class ResearchWorkflow(Protocol):
    """Protocol for research workflow implementations."""

    async def run(
        self,
        request: ResearchRequest,
        position: PositionContext | None = None,
    ) -> ResearchResult:
        """Run the workflow for a request and optional position context."""
        ...


class DefaultResearchWorkflow:
    """Concrete end-to-end research workflow implementation."""

    def __init__(
        self,
        market_data_service: MarketDataService,
        lookback_calendar_days: int = 120,
        composite_weights: Mapping[str, float] | None = None,
        model_version: str = "research-workflow-v1",
        price_structure_service: PriceStructureService | None = None,
    ) -> None:
        if isinstance(lookback_calendar_days, bool) or not isinstance(
            lookback_calendar_days,
            int,
        ):
            raise TypeError("lookback_calendar_days must be an integer")
        if lookback_calendar_days <= 0:
            raise ValueError("lookback_calendar_days must be positive")
        self._market_data_service = market_data_service
        self._lookback_calendar_days = lookback_calendar_days
        self._composite_weights = (
            None if composite_weights is None else dict(composite_weights)
        )
        self._model_version = _normalize_required_text(model_version, "model_version")
        self._price_structure_service = (
            PriceStructureService()
            if price_structure_service is None
            else price_structure_service
        )

    async def run(
        self,
        request: ResearchRequest,
        position: PositionContext | None = None,
    ) -> ResearchResult:
        del position
        as_of = _resolve_as_of(request)
        end_date = as_of.date()
        start_date = end_date - timedelta(days=self._lookback_calendar_days)

        prices = await self._market_data_service.get_daily_prices(
            symbol=request.symbol,
            start=start_date,
            end=end_date,
            provider=request.provider,
        )
        signals_snapshot = calculate_market_signals(prices)
        structure_snapshot = self._price_structure_service.analyze(prices)
        structure_assessment = _build_structure_assessment(structure_snapshot)
        price_levels = _build_price_levels(structure_snapshot)
        current_price = structure_snapshot.current_price
        price_context = (
            build_price_context(current_price, price_levels)
            if structure_snapshot.status is PriceStructureStatus.OK
            and current_price is not None
            else None
        )

        directional_raw = [
            signal
            for signal in signals_snapshot.signals
            if signal.name in _DIRECTIONAL_SIGNAL_NAMES
        ]
        interpreted_directional = interpret_directional_signals(directional_raw)
        directional_by_name = {
            signal.name: signal for signal in interpreted_directional
        }

        volatility_signal = next(
            (
                signal
                for signal in signals_snapshot.signals
                if signal.name == "realized_volatility"
            ),
            None,
        )
        volatility_assessment = (
            interpret_realized_volatility(volatility_signal)
            if volatility_signal is not None
            else None
        )

        missing_directional_names = [
            name
            for name in _DIRECTIONAL_SIGNAL_NAMES
            if name not in directional_by_name
            or directional_by_name[name].score is None
        ]
        composite_inputs = list(interpreted_directional)
        for name in _DIRECTIONAL_SIGNAL_NAMES:
            if name in directional_by_name:
                continue
            composite_inputs.append(
                _build_unavailable_directional_signal(
                    symbol=signals_snapshot.symbol,
                    timestamp=signals_snapshot.timestamp,
                    name=name,
                )
            )

        composite_weights = _resolve_composite_weights(
            self._composite_weights,
            composite_inputs,
        )
        composite = calculate_research_composite_signal(
            composite_inputs,
            weights=composite_weights,
        )
        classification = (
            classify_composite_signal(composite)
            if composite.value is not None
            else None
        )

        analysis = _build_research_analysis(
            signals_snapshot=signals_snapshot,
            interpreted_directional=interpreted_directional,
            volatility_assessment=volatility_assessment,
            composite=composite,
            classification=classification,
            structure_assessment=structure_assessment,
            price_context=price_context,
        )
        market_view = _build_market_view(
            analysis=analysis,
            classification=classification,
        )
        warnings = _build_warnings(
            missing_directional_names=missing_directional_names,
            composite_value=composite.value,
            structure_status=structure_snapshot.status,
        )
        status = _resolve_status(
            missing_directional_names=missing_directional_names,
            composite_value=composite.value,
            structure_status=structure_snapshot.status,
        )
        summary = _build_summary(
            symbol=request.symbol,
            horizon_days=request.horizon_days,
            market_view=market_view,
            classification=classification,
        )

        return ResearchResult(
            request=request,
            status=status,
            market_view=market_view,
            price_levels=price_levels,
            warnings=warnings,
            summary=summary,
            model_version=self._model_version,
            analysis=analysis,
        )


def _resolve_as_of(request: ResearchRequest) -> datetime:
    if request.as_of is None:
        return _current_utc()
    return request.as_of.astimezone(UTC)


def _current_utc() -> datetime:
    return datetime.now(UTC)


def _resolve_composite_weights(
    composite_weights: Mapping[str, float] | None,
    composite_inputs: list[InterpretedSignal],
) -> dict[str, float]:
    if composite_weights is not None:
        return dict(composite_weights)
    return {
        signal.name: 1.0
        for signal in composite_inputs
        if signal.name in _DIRECTIONAL_SIGNAL_NAMES
    }


def _build_unavailable_directional_signal(
    *,
    symbol: str,
    timestamp: datetime,
    name: str,
) -> InterpretedSignal:
    scale = _directional_scale(name)
    return InterpretedSignal(
        symbol=symbol,
        timestamp=timestamp,
        name=name,
        raw_value=None,
        score=None,
        state=InterpretedSignalState.UNAVAILABLE,
        role=SignalRole.DIRECTIONAL,
        methodology=_DIRECTIONAL_METHODOLOGY,
        parameters={
            "signal_name": name,
            "role": SignalRole.DIRECTIONAL.value,
            "methodology": _DIRECTIONAL_METHODOLOGY,
            "scale": scale,
            "formula": "clamp(raw_value / scale, -1.0, 1.0)",
            "source_parameters": {},
        },
    )


def _build_research_analysis(
    *,
    signals_snapshot: MarketSignalSnapshot,
    interpreted_directional: tuple[InterpretedSignal, ...],
    volatility_assessment: VolatilityAssessment | None,
    composite: MarketSignal,
    classification: SignalClassification | None,
    structure_assessment: ResearchStructureAssessment,
    price_context: PriceContext | None,
) -> ResearchAnalysis:
    directional_by_name = {signal.name: signal for signal in interpreted_directional}
    components: list[ResearchSignalComponent] = []
    for signal in signals_snapshot.signals:
        if signal.name in directional_by_name:
            interpreted = directional_by_name[signal.name]
            components.append(
                ResearchSignalComponent(
                    name=interpreted.name,
                    raw_value=interpreted.raw_value,
                    score=interpreted.score,
                    state=interpreted.state.value,
                    role=interpreted.role.value,
                    methodology=interpreted.methodology,
                    parameters=interpreted.parameters,
                )
            )
            continue
        if signal.name == "realized_volatility" and volatility_assessment is not None:
            components.append(
                ResearchSignalComponent(
                    name="realized_volatility",
                    raw_value=volatility_assessment.raw_value,
                    score=None,
                    state=volatility_assessment.state.value,
                    role=SignalRole.VOLATILITY.value,
                    methodology=volatility_assessment.methodology,
                    parameters=volatility_assessment.parameters,
                )
            )
    composite_assessment = ResearchCompositeAssessment(
        score=composite.value,
        classification=(
            classification.level.value if classification is not None else None
        ),
        included_signals=_extract_string_sequence_metadata(
            composite.parameters,
            "included_signals",
        ),
        missing_signals=_extract_string_sequence_metadata(
            composite.parameters,
            "missing_signals",
        ),
        configured_weights=_extract_numeric_mapping_metadata(
            composite.parameters,
            "configured_weights",
            non_negative=True,
        ),
        normalized_weights=_extract_numeric_mapping_metadata(
            composite.parameters,
            "normalized_weights",
            non_negative=True,
        ),
        component_contributions=_extract_numeric_mapping_metadata(
            composite.parameters,
            "component_contributions",
            non_negative=False,
        ),
        methodology=_COMPOSITE_METHODOLOGY,
    )
    return ResearchAnalysis(
        symbol=signals_snapshot.symbol,
        timestamp=signals_snapshot.timestamp,
        components=tuple(components),
        volatility_state=(
            volatility_assessment.state.value
            if volatility_assessment is not None
            else None
        ),
        volatility_value=(
            volatility_assessment.raw_value
            if volatility_assessment is not None
            else None
        ),
        composite=composite_assessment,
        structure=structure_assessment,
        price_context=price_context,
    )


def _build_structure_assessment(
    snapshot: PriceStructureSnapshot,
) -> ResearchStructureAssessment:
    if not isinstance(snapshot, PriceStructureSnapshot):
        raise TypeError("snapshot must be a PriceStructureSnapshot")
    return ResearchStructureAssessment(
        status=snapshot.status.value,
        as_of=snapshot.as_of,
        current_price=snapshot.current_price,
        atr=snapshot.atr,
        candidate_count=len(snapshot.candidates),
        zone_count=len(snapshot.observed_zones),
    )


def _build_price_levels(
    snapshot: PriceStructureSnapshot,
) -> tuple[PriceLevel, ...]:
    if not isinstance(snapshot, PriceStructureSnapshot):
        raise TypeError("snapshot must be a PriceStructureSnapshot")
    if snapshot.status is not PriceStructureStatus.OK:
        return ()

    levels: list[PriceLevel] = []
    for observed_zone in snapshot.lower_zones:
        zone = observed_zone.zone
        levels.append(
            PriceLevel(
                lower=zone.lower_bound,
                upper=zone.upper_bound,
                level_type="support",
                strength=None,
                sources=zone.source_methods,
            )
        )
    for observed_zone in snapshot.containing_zones:
        zone = observed_zone.zone
        levels.append(
            PriceLevel(
                lower=zone.lower_bound,
                upper=zone.upper_bound,
                level_type="current_zone",
                strength=None,
                sources=zone.source_methods,
            )
        )
    for observed_zone in snapshot.upper_zones:
        zone = observed_zone.zone
        levels.append(
            PriceLevel(
                lower=zone.lower_bound,
                upper=zone.upper_bound,
                level_type="resistance",
                strength=None,
                sources=zone.source_methods,
            )
        )
    return tuple(levels)


def _build_market_view(
    *,
    analysis: ResearchAnalysis,
    classification: SignalClassification | None,
) -> MarketView:
    direction: str | None = None
    strength: str | None = None
    if classification is not None:
        direction, strength = _map_classification_level(classification.level.value)
    trend_state = _component_state(analysis.components, "trend")
    momentum_state = _component_state(analysis.components, "momentum")
    return MarketView(
        direction=direction,
        strength=strength,
        trend_state=trend_state,
        momentum_state=momentum_state,
        volatility_state=analysis.volatility_state,
        price_structure=None,
        confidence=None,
    )


def _build_warnings(
    *,
    missing_directional_names: list[str],
    composite_value: float | None,
    structure_status: PriceStructureStatus,
) -> tuple[ResearchWarning, ...]:
    warnings: list[ResearchWarning] = []
    if missing_directional_names:
        warnings.append(
            ResearchWarning(
                code="missing_directional_signals",
                message="Missing directional signals: "
                + ", ".join(missing_directional_names),
            )
        )
    if composite_value is None:
        warnings.append(
            ResearchWarning(
                code="composite_unavailable",
                message=(
                    "Composite unavailable due to insufficient directional signal data."
                ),
            )
        )
    if structure_status is PriceStructureStatus.INSUFFICIENT_DATA:
        warnings.append(
            ResearchWarning(
                code="price_structure_insufficient_data",
                message="Price structure unavailable due to insufficient data.",
            )
        )
    elif structure_status is PriceStructureStatus.NO_PIVOTS:
        warnings.append(
            ResearchWarning(
                code="price_structure_no_pivots",
                message="Price structure unavailable because no pivots were detected.",
            )
        )
    elif structure_status is PriceStructureStatus.VOLATILITY_UNAVAILABLE:
        warnings.append(
            ResearchWarning(
                code="price_structure_volatility_unavailable",
                message=(
                    "Price structure unavailable because volatility could not "
                    "be calculated."
                ),
            )
        )
    return tuple(warnings)


def _resolve_status(
    *,
    missing_directional_names: list[str],
    composite_value: float | None,
    structure_status: PriceStructureStatus,
) -> ResearchStatus:
    if (
        composite_value is None
        or missing_directional_names
        or structure_status is not PriceStructureStatus.OK
    ):
        return ResearchStatus.DEGRADED
    return ResearchStatus.OK


def _build_summary(
    *,
    symbol: str,
    horizon_days: int,
    market_view: MarketView,
    classification: SignalClassification | None,
) -> str:
    if classification is None or market_view.direction is None:
        return (
            f"{symbol} has insufficient directional signal data for a composite "
            f"classification."
        )
    return (
        f"{symbol}'s current composite signal is classified as "
        f"{market_view.direction}; the requested research horizon is "
        f"{horizon_days} days."
    )


def _extract_string_sequence_metadata(
    parameters: Mapping[str, object],
    field_name: str,
) -> tuple[str, ...]:
    value = _require_metadata_value(parameters, field_name)
    container = _normalize_sequence_metadata(value, field_name)
    normalized = tuple(_normalize_metadata_text(item, field_name) for item in container)
    return normalized


def _extract_numeric_mapping_metadata(
    parameters: Mapping[str, object],
    field_name: str,
    *,
    non_negative: bool,
) -> dict[str, float]:
    value = _require_metadata_value(parameters, field_name)
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")

    normalized: dict[str, float] = {}
    for key, raw_value in value.items():
        normalized_key = _normalize_metadata_text(key, field_name)
        if normalized_key in normalized:
            raise ValueError(f"{field_name} keys must be unique")
        numeric_value = _normalize_metadata_number(raw_value, field_name)
        if non_negative and numeric_value < 0.0:
            raise ValueError(f"{field_name} must not contain negative values")
        normalized[normalized_key] = numeric_value
    return dict(normalized)


def _require_metadata_value(
    parameters: Mapping[str, object],
    field_name: str,
) -> object:
    if field_name not in parameters:
        raise ValueError(f"{field_name} metadata is required")
    return parameters[field_name]


def _normalize_sequence_metadata(
    value: object,
    field_name: str,
) -> tuple[object, ...]:
    if isinstance(value, (str, bytes, bytearray, dict)):
        raise TypeError(f"{field_name} must be a list or tuple")
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    raise TypeError(f"{field_name} must be a list or tuple")


def _normalize_metadata_text(value: object, field_name: str) -> str:
    if isinstance(value, bool) or not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text


def _normalize_metadata_number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{field_name} must be numeric")
    numeric_value = float(value)
    if not math.isfinite(numeric_value):
        raise ValueError(f"{field_name} must be finite")
    return numeric_value


def _component_state(
    components: tuple[ResearchSignalComponent, ...], name: str
) -> str | None:
    for component in components:
        if component.name == name:
            return component.state
    return None


def _map_classification_level(level: str) -> tuple[str, str]:
    if level in {"strong_bearish", "bearish"}:
        return "bearish", ("strong" if level == "strong_bearish" else "moderate")
    if level == "neutral":
        return "neutral", "neutral"
    if level in {"bullish", "strong_bullish"}:
        return "bullish", ("strong" if level == "strong_bullish" else "moderate")
    raise ValueError(f"Unsupported classification level: {level}")


def _directional_scale(name: str) -> float:
    if name == "trend":
        return DIRECTIONAL_TREND_SCALE
    if name == "momentum":
        return DIRECTIONAL_MOMENTUM_SCALE
    if name == "current_drawdown":
        return DIRECTIONAL_CURRENT_DRAWDOWN_SCALE
    if name == "distance_from_moving_average":
        return DIRECTIONAL_DISTANCE_FROM_MOVING_AVERAGE_SCALE
    raise ValueError(f"Unknown directional signal: {name}")


def _normalize_required_text(value: object, field_name: str) -> str:
    if isinstance(value, bool) or not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text
