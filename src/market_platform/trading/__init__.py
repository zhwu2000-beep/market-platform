"""Deterministic trading-signal and pre-risk Order Intent domain."""

from market_platform.trading.instrument import (
    TRADING_INSTRUMENT_IDENTITY_SCHEMA_VERSION,
    TradingInstrumentIdentity,
)
from market_platform.trading.order_intent import (
    ORDER_INTENT_SCHEMA_VERSION,
    OrderIntent,
    TradingSignalExpiredError,
    TradingSignalNotYetValidError,
    TradingSignalTemporalError,
    create_order_intent_from_signal,
)
from market_platform.trading.policy import (
    EXACT_TARGET_POSITION_INTENT_POLICY_SCHEMA_VERSION,
    ExactTargetPositionIntentPolicy,
)
from market_platform.trading.signal import (
    TRADING_SIGNAL_SCHEMA_VERSION,
    TRADING_SIGNAL_SOURCE_SCHEMA_VERSION,
    TradingSignal,
    TradingSignalEventConsistency,
    TradingSignalSourceIdentity,
    TradingSignalTemporalStatus,
    TradingTargetPosition,
    compare_trading_signal_event_consistency,
    evaluate_trading_signal_temporal_status,
)

__all__ = [
    "EXACT_TARGET_POSITION_INTENT_POLICY_SCHEMA_VERSION",
    "ORDER_INTENT_SCHEMA_VERSION",
    "TRADING_INSTRUMENT_IDENTITY_SCHEMA_VERSION",
    "TRADING_SIGNAL_SCHEMA_VERSION",
    "TRADING_SIGNAL_SOURCE_SCHEMA_VERSION",
    "ExactTargetPositionIntentPolicy",
    "OrderIntent",
    "TradingInstrumentIdentity",
    "TradingSignal",
    "TradingSignalEventConsistency",
    "TradingSignalExpiredError",
    "TradingSignalNotYetValidError",
    "TradingSignalSourceIdentity",
    "TradingSignalTemporalError",
    "TradingSignalTemporalStatus",
    "TradingTargetPosition",
    "compare_trading_signal_event_consistency",
    "create_order_intent_from_signal",
    "evaluate_trading_signal_temporal_status",
]
