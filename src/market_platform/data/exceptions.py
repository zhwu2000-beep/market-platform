"""Provider-facing exceptions used by the data access layer."""


class DataProviderError(Exception):
    """Base exception for normalized data provider failures."""


class ConfigurationError(DataProviderError):
    """Raised when a provider or data-layer configuration is missing."""


class ProviderNotFoundError(DataProviderError):
    """Raised when a requested provider is not registered."""


class AuthenticationError(DataProviderError):
    """Raised when provider credentials are missing, invalid, or rejected."""


class RateLimitError(DataProviderError):
    """Raised when a provider rate limit prevents the request."""


class NetworkError(DataProviderError):
    """Raised when a network failure prevents provider communication."""
