"""Research workflow interface."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from market_platform.research.models import (
    PositionContext,
    ResearchRequest,
    ResearchResult,
)


@runtime_checkable
class ResearchWorkflow(Protocol):
    """Protocol for research workflow implementations."""

    def run(
        self,
        request: ResearchRequest,
        position: PositionContext | None = None,
    ) -> ResearchResult:
        """Run the workflow for a request and optional position context."""
        ...
