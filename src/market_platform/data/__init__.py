"""Data access package."""

from market_platform.data.exceptions import (
    AuthenticationError,
    ConfigurationError,
    DataProviderError,
    NetworkError,
    ProviderNotFoundError,
    RateLimitError,
)
from market_platform.data.http import HTTPClient, HttpClientConfig, create_http_client
from market_platform.data.models import (
    HEALTH_CHECK_COLUMNS,
    PRICE_COLUMNS,
    UTC_TIMEZONE,
    normalize_health_check_frame,
    normalize_price_frame,
)
from market_platform.data.provider import DataProvider, normalize_date_like
from market_platform.data.registry import DataProviderRegistry, ProviderRegistry

__all__ = [
    "HEALTH_CHECK_COLUMNS",
    "PRICE_COLUMNS",
    "UTC_TIMEZONE",
    "AuthenticationError",
    "ConfigurationError",
    "DataProvider",
    "DataProviderError",
    "DataProviderRegistry",
    "HTTPClient",
    "HttpClientConfig",
    "NetworkError",
    "ProviderNotFoundError",
    "ProviderRegistry",
    "RateLimitError",
    "create_http_client",
    "normalize_date_like",
    "normalize_health_check_frame",
    "normalize_price_frame",
]
