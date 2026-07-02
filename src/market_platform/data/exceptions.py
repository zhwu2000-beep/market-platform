"""Provider-facing exceptions used by the data access layer."""


class DataProviderError(Exception):
    """Base exception for normalized data provider failures."""


class AuthenticationError(DataProviderError):
    """Raised when provider credentials are missing, invalid, or rejected."""


class RateLimitError(DataProviderError):
    """Raised when a provider rate limit prevents the request."""


class NetworkError(DataProviderError):
    """Raised when a network failure prevents provider communication."""
