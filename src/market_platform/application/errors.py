"""Narrow errors for transport-neutral application boundaries."""


class HistoricalReplayResearchApplicationError(Exception):
    """Base error for the historical Replay research application boundary."""


class HistoricalReplayResearchApplicationRequestError(
    HistoricalReplayResearchApplicationError,
    ValueError,
):
    """Raised when a serialized application request is malformed."""


class UnsupportedApplicationSchemaError(
    HistoricalReplayResearchApplicationRequestError
):
    """Raised when an application request schema is unsupported."""


class HistoricalSourceValidationError(HistoricalReplayResearchApplicationError):
    """Raised when inline historical rows cannot form a canonical source."""


class StrategyResolutionError(HistoricalReplayResearchApplicationError):
    """Raised when a requested strategy cannot be resolved."""


class StateModelResolutionError(HistoricalReplayResearchApplicationError):
    """Raised when a requested state model cannot be resolved."""


class ResolverIdentityMismatchError(HistoricalReplayResearchApplicationError):
    """Raised when a resolved executable does not match requested identity."""


class TradingApplicationError(Exception):
    """Base error for the trading-signal application boundary."""


class TradingApplicationRequestError(TradingApplicationError, ValueError):
    """Raised when a trading application request is malformed."""


class UnsupportedTradingApplicationSchemaError(TradingApplicationRequestError):
    """Raised when a trading application request schema is unsupported."""


class TradingApplicationResourceLimitError(TradingApplicationRequestError):
    """Raised when a trading application field exceeds a fixed v1 limit."""


class TradingApplicationCorrespondenceError(
    TradingApplicationError,
    RuntimeError,
):
    """Raised when an application request and domain result do not correspond."""


__all__ = [
    "HistoricalReplayResearchApplicationError",
    "HistoricalReplayResearchApplicationRequestError",
    "HistoricalSourceValidationError",
    "ResolverIdentityMismatchError",
    "StateModelResolutionError",
    "StrategyResolutionError",
    "TradingApplicationCorrespondenceError",
    "TradingApplicationError",
    "TradingApplicationRequestError",
    "TradingApplicationResourceLimitError",
    "UnsupportedApplicationSchemaError",
    "UnsupportedTradingApplicationSchemaError",
]
