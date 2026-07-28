"""Application-boundary errors for historical Replay research."""


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


__all__ = [
    "HistoricalReplayResearchApplicationError",
    "HistoricalReplayResearchApplicationRequestError",
    "HistoricalSourceValidationError",
    "ResolverIdentityMismatchError",
    "StateModelResolutionError",
    "StrategyResolutionError",
    "UnsupportedApplicationSchemaError",
]
