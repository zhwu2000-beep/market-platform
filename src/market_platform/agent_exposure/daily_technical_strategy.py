"""Explicit Agent exposure facade for Daily Technical Strategy."""

from __future__ import annotations

from market_platform.agent_exposure.daily_technical_strategy_response import (
    DailyTechnicalStrategyAgentResponseProjection,
)
from market_platform.application.daily_technical_strategy import (
    DailyTechnicalStrategyApplicationRequest,
)
from market_platform.application.daily_technical_strategy_service import (
    DailyTechnicalStrategyApplicationService,
)


class DailyTechnicalStrategyAgentExposureFacade:
    """Expose only the Daily Technical Strategy application operation."""

    __slots__ = ("_application_service",)

    def __init__(
        self,
        application_service: DailyTechnicalStrategyApplicationService,
    ) -> None:
        self._application_service = application_service

    async def execute(
        self,
        request: DailyTechnicalStrategyApplicationRequest,
    ) -> DailyTechnicalStrategyAgentResponseProjection:
        """Delegate once and return the bounded Agent response projection."""

        application_response = await self._application_service.execute(request)
        return DailyTechnicalStrategyAgentResponseProjection.from_application_response(
            application_response
        )


__all__ = ["DailyTechnicalStrategyAgentExposureFacade"]
