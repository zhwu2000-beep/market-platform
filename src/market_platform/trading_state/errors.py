"""Narrow errors for immutable trading-state snapshots."""


class TradingStateDomainError(Exception):
    """Base error for the trading-state snapshot domain."""


class TradingStateValidationError(TradingStateDomainError, ValueError):
    """Raised when direct trading-state domain input is malformed."""


class TradingStateDuplicateError(TradingStateValidationError):
    """Raised when a snapshot repeats one semantic record key."""


class TradingStateCorrespondenceError(TradingStateDomainError, RuntimeError):
    """Raised when retained nested snapshot state is impossible."""


__all__ = [
    "TradingStateCorrespondenceError",
    "TradingStateDomainError",
    "TradingStateDuplicateError",
    "TradingStateValidationError",
]
