"""Data access package."""

from market_platform.data.comparison import compare_daily_prices
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
    LATEST_PRICE_COLUMNS,
    PRICE_COLUMNS,
    UTC_TIMEZONE,
    normalize_health_check_frame,
    normalize_latest_price_frame,
    normalize_price_frame,
)
from market_platform.data.provider import DataProvider, normalize_date_like
from market_platform.data.registry import (
    DataProviderRegistry,
    ProviderRegistry,
    create_default_registry,
    get_provider,
)

__all__ = [
    "HEALTH_CHECK_COLUMNS",
    "LATEST_PRICE_COLUMNS",
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
    "create_default_registry",
    "create_http_client",
    "compare_daily_prices",
    "get_provider",
    "normalize_date_like",
    "normalize_health_check_frame",
    "normalize_latest_price_frame",
    "normalize_price_frame",
]
