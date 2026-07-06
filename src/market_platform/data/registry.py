"""Lightweight provider registry."""

from collections.abc import Callable
from typing import Any

from market_platform.data.exceptions import ProviderNotFoundError
from market_platform.data.provider import DataProvider

ProviderFactory = Callable[..., DataProvider]


class ProviderRegistry:
    """Registry of provider factories keyed by normalized provider name."""

    def __init__(self) -> None:
        self._factories: dict[str, ProviderFactory] = {}

    def register(
        self,
        name: str,
        factory: ProviderFactory,
        *,
        overwrite: bool = False,
    ) -> None:
        """Register a provider factory under a normalized name."""

        normalized_name = self._normalize_name(name)
        if not overwrite and normalized_name in self._factories:
            raise ValueError(f"Provider already registered: {normalized_name}")
        self._factories[normalized_name] = factory

    def create(self, name: str, **kwargs: Any) -> DataProvider:
        """Create a provider instance from a registered factory."""

        normalized_name = self._normalize_name(name)
        try:
            factory = self._factories[normalized_name]
        except KeyError as exc:
            raise ProviderNotFoundError(
                f"Unknown provider: {normalized_name}"
            ) from exc
        return factory(**kwargs)

    def names(self) -> list[str]:
        """Return registered provider names."""

        return sorted(self._factories)

    def __contains__(self, name: str) -> bool:
        """Return whether a normalized provider name is registered."""

        try:
            normalized_name = self._normalize_name(name)
        except ValueError:
            return False
        return normalized_name in self._factories

    def _normalize_name(self, name: str) -> str:
        normalized_name = name.strip().lower()
        if not normalized_name:
            raise ValueError("Provider name cannot be empty")
        return normalized_name


DataProviderRegistry = ProviderRegistry


def create_default_registry() -> ProviderRegistry:
    """Create the default provider registry."""

    from market_platform.data.providers.polygon import PolygonProvider
    from market_platform.data.providers.twelvedata import TwelveDataProvider

    registry = ProviderRegistry()
    registry.register("polygon", PolygonProvider)
    registry.register("twelvedata", TwelveDataProvider)
    return registry


_DEFAULT_REGISTRY = create_default_registry()


def get_provider(name: str, **kwargs: Any) -> DataProvider:
    """Create a provider from the default registry."""

    return _DEFAULT_REGISTRY.create(name, **kwargs)
