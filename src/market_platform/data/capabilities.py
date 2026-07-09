"""Provider capability definitions and provider order parsing."""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from market_platform.config import get_settings
from market_platform.data.exceptions import ConfigurationError


class DataCapability(StrEnum):
    """Capabilities that a data provider may support."""

    DAILY_PRICES = "daily_prices"
    INTRADAY_PRICES = "intraday_prices"
    LATEST_PRICE = "latest_price"
    HEALTH_CHECK = "health_check"


PROVIDER_NAME_ALIASES: dict[str, str] = {
    "polygon": "polygon",
    "twelve_data": "twelvedata",
    "twelvedata": "twelvedata",
}

DEFAULT_PROVIDER_CAPABILITIES: dict[str, frozenset[DataCapability]] = {
    "polygon": frozenset(
        {
            DataCapability.DAILY_PRICES,
            DataCapability.LATEST_PRICE,
            DataCapability.HEALTH_CHECK,
        }
    ),
    "twelvedata": frozenset(
        {
            DataCapability.DAILY_PRICES,
            DataCapability.LATEST_PRICE,
            DataCapability.INTRADAY_PRICES,
            DataCapability.HEALTH_CHECK,
        }
    ),
}


def normalize_provider_name(name: str) -> str:
    """Return a canonical provider name."""

    normalized_name = name.strip().lower()
    if not normalized_name:
        raise ValueError("Provider name cannot be empty")
    return PROVIDER_NAME_ALIASES.get(normalized_name, normalized_name)


def get_provider_capabilities(name: str) -> frozenset[DataCapability]:
    """Return the supported capabilities for a known provider."""

    canonical_name = normalize_provider_name(name)
    try:
        return DEFAULT_PROVIDER_CAPABILITIES[canonical_name]
    except KeyError as exc:
        raise ConfigurationError(f"Unknown provider: {canonical_name}") from exc


def provider_supports_capability(
    name: str,
    capability: DataCapability,
) -> bool:
    """Return whether a provider supports a capability.

    Unknown provider names are treated as capability-neutral so fake providers
    used in tests and future custom providers can participate in selection.
    """

    canonical_name = normalize_provider_name(name)
    supported_capabilities = DEFAULT_PROVIDER_CAPABILITIES.get(canonical_name)
    if supported_capabilities is None:
        return True
    return capability in supported_capabilities


def parse_provider_order(raw_order: str | None) -> list[str]:
    """Parse and normalize the configured provider order."""

    if raw_order is None or not raw_order.strip():
        return []

    ordered_names: list[str] = []
    seen: set[str] = set()
    for raw_name in raw_order.split(","):
        canonical_name = normalize_provider_name(raw_name)
        if canonical_name not in DEFAULT_PROVIDER_CAPABILITIES:
            raise ConfigurationError(
                "Unknown provider in MARKET_PLATFORM_DATA_PROVIDER_ORDER: "
                f"{canonical_name}"
            )
        if canonical_name in seen:
            continue
        seen.add(canonical_name)
        ordered_names.append(canonical_name)
    return ordered_names


def get_configured_provider_order() -> list[str]:
    """Return the configured provider order from application settings."""

    settings = get_settings()
    return parse_provider_order(settings.data_provider_order)


def normalize_provider_order(provider_order: Sequence[str]) -> list[str]:
    """Normalize an explicit provider order sequence."""

    return parse_provider_order(",".join(provider_order))
