"""Provider registry for selecting data sources by name."""

from market_platform.data.provider import DataProvider


class DataProviderRegistry:
    """In-memory registry of available data providers."""

    def __init__(self) -> None:
        self._providers: dict[str, DataProvider] = {}

    def register(self, provider: DataProvider) -> None:
        """Register a provider implementation."""

        self._providers[provider.name] = provider

    def get(self, name: str) -> DataProvider:
        """Return a provider by name."""

        try:
            return self._providers[name]
        except KeyError as exc:
            raise KeyError(f"Unknown data provider: {name}") from exc

    def names(self) -> list[str]:
        """Return registered provider names."""

        return sorted(self._providers)
