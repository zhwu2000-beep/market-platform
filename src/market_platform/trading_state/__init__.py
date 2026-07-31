"""Immutable exact trading-state snapshot foundations."""

from market_platform.trading_state.errors import (
    TradingStateCorrespondenceError,
    TradingStateDomainError,
    TradingStateDuplicateError,
    TradingStateValidationError,
)
from market_platform.trading_state.identity import (
    STATE_SNAPSHOT_SOURCE_SCHEMA_VERSION,
    TRADING_ACCOUNT_IDENTITY_SCHEMA_VERSION,
    StateSnapshotSourceIdentity,
    TradingAccountIdentity,
    TradingEnvironment,
)
from market_platform.trading_state.records import (
    CashBalance,
    MarketQuote,
    OpenOrderExposure,
    PositionRecord,
)
from market_platform.trading_state.snapshots import (
    ACCOUNT_CASH_SNAPSHOT_SCHEMA_VERSION,
    MARKET_QUOTE_COLLECTION_SNAPSHOT_SCHEMA_VERSION,
    OPEN_ORDER_EXPOSURE_SNAPSHOT_SCHEMA_VERSION,
    POSITION_COLLECTION_SNAPSHOT_SCHEMA_VERSION,
    AccountCashSnapshot,
    MarketQuoteCollectionSnapshot,
    OpenOrderExposureSnapshot,
    PositionCollectionSnapshot,
)
from market_platform.trading_state.temporal import (
    SnapshotFreshness,
    SnapshotSkew,
    evaluate_snapshot_freshness,
    evaluate_snapshot_skew,
)

__all__ = [
    "ACCOUNT_CASH_SNAPSHOT_SCHEMA_VERSION",
    "MARKET_QUOTE_COLLECTION_SNAPSHOT_SCHEMA_VERSION",
    "OPEN_ORDER_EXPOSURE_SNAPSHOT_SCHEMA_VERSION",
    "POSITION_COLLECTION_SNAPSHOT_SCHEMA_VERSION",
    "STATE_SNAPSHOT_SOURCE_SCHEMA_VERSION",
    "TRADING_ACCOUNT_IDENTITY_SCHEMA_VERSION",
    "AccountCashSnapshot",
    "CashBalance",
    "MarketQuote",
    "MarketQuoteCollectionSnapshot",
    "OpenOrderExposure",
    "OpenOrderExposureSnapshot",
    "PositionCollectionSnapshot",
    "PositionRecord",
    "SnapshotFreshness",
    "SnapshotSkew",
    "StateSnapshotSourceIdentity",
    "TradingAccountIdentity",
    "TradingEnvironment",
    "TradingStateCorrespondenceError",
    "TradingStateDomainError",
    "TradingStateDuplicateError",
    "TradingStateValidationError",
    "evaluate_snapshot_freshness",
    "evaluate_snapshot_skew",
]
