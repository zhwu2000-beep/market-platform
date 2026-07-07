"""Factories for wiring market data services."""

from __future__ import annotations

from collections.abc import Sequence

from market_platform.config import get_settings
from market_platform.data.capabilities import parse_provider_order
from market_platform.data.registry import create_default_registry
from market_platform.data.selection import ProviderCandidate, ProviderSelectionPolicy
from market_platform.data.service import MarketDataService


def create_default_market_data_service(
    *,
    provider_order: Sequence[str] | None = None,
    fallback_on_auth_error: bool = False,
) -> MarketDataService:
    """Create the default market data service with registered providers."""

    settings = get_settings()
    registry = create_default_registry()

    resolved_provider_order = (
        parse_provider_order(settings.data_provider_order)
        if provider_order is None
        else provider_order
    )

    provider_kwargs = {
        "polygon": {"api_key": settings.polygon_api_key},
        "twelvedata": {"api_key": settings.twelve_data_api_key},
    }

    candidates = [
        ProviderCandidate(
            name=name,
            provider=registry.create(name, **provider_kwargs.get(name, {})),
        )
        for name in registry.names()
    ]
    policy = ProviderSelectionPolicy(
        candidates=candidates,
        provider_order=resolved_provider_order,
    )
    return MarketDataService(
        policy,
        fallback_on_auth_error=fallback_on_auth_error,
    )