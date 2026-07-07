"""Provider selection policy primitives."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from market_platform.data.capabilities import (
    DataCapability,
    get_configured_provider_order,
    normalize_provider_name,
    normalize_provider_order,
    provider_supports_capability,
)
from market_platform.data.provider import DataProvider


@dataclass(slots=True, frozen=True)
class ProviderCandidate:
    """A provider candidate considered by a selection policy."""

    name: str
    provider: DataProvider
    priority: int = 100
    enabled: bool = True
    capabilities: frozenset[DataCapability] | None = None


@dataclass(slots=True)
class ProviderSelectionPolicy:
    """Ordering policy for provider candidates."""

    candidates: Sequence[ProviderCandidate]
    provider_order: Sequence[str] | None = None

    def ordered_providers(
        self,
        capability: DataCapability | None = None,
    ) -> list[ProviderCandidate]:
        """Return enabled providers sorted by configured order and priority."""

        configured_order = self._configured_provider_order()
        order_index = {
            provider_name: index for index, provider_name in enumerate(configured_order)
        }
        ranked_candidates: list[tuple[int, int, int, ProviderCandidate]] = []
        for index, candidate in enumerate(self.candidates):
            if not candidate.enabled:
                continue
            if capability is not None and not _candidate_supports_capability(
                candidate,
                capability,
            ):
                continue

            canonical_name = normalize_provider_name(candidate.name)
            configured_rank = order_index.get(canonical_name, len(order_index))
            ranked_candidates.append(
                (configured_rank, candidate.priority, index, candidate)
            )

        ranked_candidates.sort()
        return [candidate for _, _, _, candidate in ranked_candidates]

    def _configured_provider_order(self) -> list[str]:
        if self.provider_order is None:
            return get_configured_provider_order()
        return normalize_provider_order(self.provider_order)


def _candidate_supports_capability(
    candidate: ProviderCandidate,
    capability: DataCapability,
) -> bool:
    if candidate.capabilities is not None:
        return capability in candidate.capabilities
    return provider_supports_capability(candidate.name, capability)
