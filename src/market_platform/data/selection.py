"""Provider selection policy primitives."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from market_platform.data.provider import DataProvider


@dataclass(slots=True, frozen=True)
class ProviderCandidate:
    """A provider candidate considered by a selection policy."""

    name: str
    provider: DataProvider
    priority: int = 100
    enabled: bool = True


@dataclass(slots=True)
class ProviderSelectionPolicy:
    """Ordering policy for provider candidates."""

    candidates: Sequence[ProviderCandidate]

    def ordered_providers(self) -> list[ProviderCandidate]:
        """Return enabled providers sorted by priority."""

        enabled_candidates = [
            candidate for candidate in self.candidates if candidate.enabled
        ]
        return sorted(enabled_candidates, key=lambda candidate: candidate.priority)
