"""Transport-neutral services for trading-signal application operations."""

from __future__ import annotations

from market_platform.application.trading_signal import (
    CreateOrderIntentApplicationResponse,
    CreateTradingSignalApplicationResponse,
    OrderIntentApplicationRequest,
    TradingSignalApplicationInput,
    TradingSignalApplicationRequest,
)
from market_platform.trading import (
    ExactTargetPositionIntentPolicy,
    TradingInstrumentIdentity,
    TradingSignal,
    TradingSignalSourceIdentity,
    create_order_intent_from_signal,
)


class CreateTradingSignalApplicationService:
    """Create one canonical TradingSignal from normalized application intent."""

    __slots__ = ()

    def execute(
        self,
        request: TradingSignalApplicationRequest,
    ) -> CreateTradingSignalApplicationResponse:
        if not isinstance(request, TradingSignalApplicationRequest):
            raise TypeError("request must be a TradingSignalApplicationRequest")
        signal = _create_signal(request.signal)
        return CreateTradingSignalApplicationResponse._create(request, signal)


class CreateOrderIntentApplicationService:
    """Create one canonical pre-risk OrderIntent from normalized signal intent."""

    __slots__ = ()

    def execute(
        self,
        request: OrderIntentApplicationRequest,
    ) -> CreateOrderIntentApplicationResponse:
        if not isinstance(request, OrderIntentApplicationRequest):
            raise TypeError("request must be an OrderIntentApplicationRequest")
        signal = _create_signal(request.signal)
        policy = ExactTargetPositionIntentPolicy()
        intent = create_order_intent_from_signal(
            signal,
            policy,
            request.decision_as_of,
        )
        return CreateOrderIntentApplicationResponse._create(request, intent)


def _create_signal(request: TradingSignalApplicationInput) -> TradingSignal:
    source = TradingSignalSourceIdentity(
        source_id=request.source.source_id,
        source_version=request.source.source_version,
        configuration_fingerprint=request.source.configuration_fingerprint,
    )
    instrument = TradingInstrumentIdentity(
        symbol=request.instrument.symbol,
        venue=request.instrument.venue,
    )
    return TradingSignal(
        source=source,
        source_event_id=request.source_event_id,
        instrument=instrument,
        timeframe=request.timeframe,
        target_position=request.target.position,
        target_units=request.target.units,
        generated_at=request.generated_at,
        valid_from=request.valid_from,
        expires_at=request.expires_at,
    )


__all__ = [
    "CreateOrderIntentApplicationService",
    "CreateTradingSignalApplicationService",
]
