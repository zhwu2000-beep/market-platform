"""Focused tests for the Daily Technical Strategy Agent exposure facade."""

from __future__ import annotations

import ast
import asyncio
import inspect
from pathlib import Path
from typing import cast
from unittest.mock import patch

import pytest

from market_platform.agent_exposure import (
    DailyTechnicalStrategyAgentExposureFacade,
    DailyTechnicalStrategyAgentResponseProjection,
)
from market_platform.application import (
    DailyTechnicalStrategyApplicationRequest,
    DailyTechnicalStrategyApplicationResponse,
    DailyTechnicalStrategyApplicationService,
)


class _RecordingApplicationService:
    def __init__(
        self,
        *,
        response: DailyTechnicalStrategyApplicationResponse | None = None,
        error: BaseException | None = None,
    ) -> None:
        self.response = response
        self.error = error
        self.requests: list[DailyTechnicalStrategyApplicationRequest] = []

    async def execute(
        self,
        request: DailyTechnicalStrategyApplicationRequest,
    ) -> DailyTechnicalStrategyApplicationResponse:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


def _facade(
    service: _RecordingApplicationService,
) -> DailyTechnicalStrategyAgentExposureFacade:
    return DailyTechnicalStrategyAgentExposureFacade(
        cast(DailyTechnicalStrategyApplicationService, service)
    )


def test_facade_delegates_once_and_returns_projection() -> None:
    request = cast(DailyTechnicalStrategyApplicationRequest, object())
    response = cast(DailyTechnicalStrategyApplicationResponse, object())
    projection = cast(DailyTechnicalStrategyAgentResponseProjection, object())
    service = _RecordingApplicationService(response=response)

    with patch.object(
        DailyTechnicalStrategyAgentResponseProjection,
        "from_application_response",
        return_value=projection,
    ) as projection_factory:
        actual = asyncio.run(_facade(service).execute(request))

    assert actual is projection
    assert service.requests == [request]
    projection_factory.assert_called_once_with(response)


def test_facade_preserves_application_exception_identity() -> None:
    request = cast(DailyTechnicalStrategyApplicationRequest, object())
    error = RuntimeError("application failure")
    service = _RecordingApplicationService(error=error)

    with patch.object(
        DailyTechnicalStrategyAgentResponseProjection,
        "from_application_response",
    ) as projection_factory, pytest.raises(RuntimeError) as caught:
        asyncio.run(_facade(service).execute(request))

    assert caught.value is error
    assert service.requests == [request]
    projection_factory.assert_not_called()


def test_facade_preserves_projection_exception_identity() -> None:
    request = cast(DailyTechnicalStrategyApplicationRequest, object())
    response = cast(DailyTechnicalStrategyApplicationResponse, object())
    error = ValueError("projection failure")
    service = _RecordingApplicationService(response=response)

    with patch.object(
        DailyTechnicalStrategyAgentResponseProjection,
        "from_application_response",
        side_effect=error,
    ) as projection_factory, pytest.raises(ValueError) as caught:
        asyncio.run(_facade(service).execute(request))

    assert caught.value is error
    assert service.requests == [request]
    projection_factory.assert_called_once_with(response)


def test_facade_operation_remains_async_and_capability_specific() -> None:
    assert inspect.iscoroutinefunction(
        DailyTechnicalStrategyAgentExposureFacade.execute
    )
    public_operations = {
        name
        for name, value in DailyTechnicalStrategyAgentExposureFacade.__dict__.items()
        if not name.startswith("_") and callable(value)
    }
    assert public_operations == {"execute"}
    assert DailyTechnicalStrategyAgentExposureFacade.__slots__ == (
        "_application_service",
    )


def test_facade_imports_only_application_boundary_and_response_projection() -> None:
    source_path = Path(inspect.getfile(DailyTechnicalStrategyAgentExposureFacade))
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    market_platform_imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module is not None
        and node.module.startswith("market_platform")
    }

    assert market_platform_imports == {
        "market_platform.agent_exposure.daily_technical_strategy_response",
        "market_platform.application.daily_technical_strategy",
        "market_platform.application.daily_technical_strategy_service",
    }
