"""Transport-neutral facade for historical Replay research."""

from __future__ import annotations

from market_platform.application.errors import (
    HistoricalSourceValidationError,
    ResolverIdentityMismatchError,
)
from market_platform.application.historical_replay_research import (
    HistoricalReplayResearchApplicationRequest,
    HistoricalReplayResearchApplicationResponse,
    HistoricalReplayResearchMemberRequest,
    HistoricalReplayResearchStateModelRequest,
    HistoricalReplayResearchStrategyRequest,
    _historical_price_series_from_request,
)
from market_platform.application.historical_replay_research_resolvers import (
    HistoricalReplayResearchStateModelResolver,
    HistoricalReplayResearchStrategyResolver,
)
from market_platform.data import HistoricalPriceSeries
from market_platform.research import (
    HistoricalReplayResearchMemberSpecification,
    HistoricalReplayResearchStateModelInstance,
    HistoricalReplayResearchWorkflowService,
    HistoricalReplayResearchWorkflowSpecification,
)
from market_platform.strategy import (
    Strategy,
    StrategyInstance,
    create_strategy_collection,
    get_strategy_provenance,
)


class HistoricalReplayResearchApplicationService:
    """Resolve external intent and invoke the canonical v0.53 workflow once."""

    __slots__ = (
        "_state_model_resolver",
        "_strategy_resolver",
        "_workflow_service",
    )

    def __init__(
        self,
        workflow_service: HistoricalReplayResearchWorkflowService,
        strategy_resolver: HistoricalReplayResearchStrategyResolver,
        state_model_resolver: HistoricalReplayResearchStateModelResolver,
    ) -> None:
        if not isinstance(
            workflow_service,
            HistoricalReplayResearchWorkflowService,
        ):
            raise TypeError(
                "workflow_service must be a "
                "HistoricalReplayResearchWorkflowService"
            )
        if not isinstance(
            strategy_resolver,
            HistoricalReplayResearchStrategyResolver,
        ):
            raise TypeError(
                "strategy_resolver must implement "
                "HistoricalReplayResearchStrategyResolver"
            )
        if not isinstance(
            state_model_resolver,
            HistoricalReplayResearchStateModelResolver,
        ):
            raise TypeError(
                "state_model_resolver must implement "
                "HistoricalReplayResearchStateModelResolver"
            )
        self._workflow_service = workflow_service
        self._strategy_resolver = strategy_resolver
        self._state_model_resolver = state_model_resolver

    def execute(
        self,
        request: HistoricalReplayResearchApplicationRequest,
    ) -> HistoricalReplayResearchApplicationResponse:
        """Execute one normalized application request."""

        if not isinstance(request, HistoricalReplayResearchApplicationRequest):
            raise TypeError(
                "request must be a HistoricalReplayResearchApplicationRequest"
            )
        source = self._source(request)
        baseline = self._member(request.baseline)
        candidates = tuple(self._member(member) for member in request.candidates)
        workflow_specification = (
            HistoricalReplayResearchWorkflowSpecification(
                source=source,
                baseline=baseline,
                candidates=candidates,
                replay_software_revision=request.replay_software_revision,
                comparison_software_revision=(
                    request.comparison_software_revision
                ),
                workflow_software_revision=request.workflow_software_revision,
            )
        )
        result = self._workflow_service.run(workflow_specification)
        return HistoricalReplayResearchApplicationResponse._create(
            request,
            workflow_specification,
            result,
        )

    def _source(
        self,
        request: HistoricalReplayResearchApplicationRequest,
    ) -> HistoricalPriceSeries:
        try:
            return _historical_price_series_from_request(request)
        except (TypeError, ValueError) as exc:
            raise HistoricalSourceValidationError(
                "inline historical source failed canonical validation"
            ) from exc

    def _member(
        self,
        request: HistoricalReplayResearchMemberRequest,
    ) -> HistoricalReplayResearchMemberSpecification:
        strategies = tuple(
            self._strategy(strategy) for strategy in request.strategies
        )
        state_model = self._state_model(request.state_model)
        return HistoricalReplayResearchMemberSpecification(
            replay_specification=request.replay_specification,
            strategies=create_strategy_collection(strategies),
            state_model=state_model,
            structure_derivation=request.structure_derivation,
        )

    def _strategy(
        self,
        request: HistoricalReplayResearchStrategyRequest,
    ) -> Strategy:
        strategy = self._strategy_resolver.resolve(request)
        if not isinstance(strategy, Strategy) or not isinstance(
            strategy,
            StrategyInstance,
        ):
            raise ResolverIdentityMismatchError(
                "resolved strategy must implement Strategy and StrategyInstance"
            )
        provenance = get_strategy_provenance(strategy)
        if (
            provenance.strategy_id != request.strategy_id
            or provenance.strategy_version != request.strategy_version
            or provenance.configuration_fingerprint
            != request.configuration_fingerprint
        ):
            raise ResolverIdentityMismatchError(
                "resolved strategy identity does not match the request"
            )
        return strategy

    def _state_model(
        self,
        request: HistoricalReplayResearchStateModelRequest,
    ) -> HistoricalReplayResearchStateModelInstance:
        state_model = self._state_model_resolver.resolve(request)
        if not isinstance(
            state_model,
            HistoricalReplayResearchStateModelInstance,
        ):
            raise ResolverIdentityMismatchError(
                "resolved state model must implement "
                "HistoricalReplayResearchStateModelInstance"
            )
        if (
            state_model.model_id != request.model_id
            or state_model.model_version != request.model_version
            or state_model.configuration_fingerprint
            != request.expected_configuration_fingerprint
        ):
            raise ResolverIdentityMismatchError(
                "resolved state-model identity does not match the request"
            )
        return state_model


__all__ = ["HistoricalReplayResearchApplicationService"]
