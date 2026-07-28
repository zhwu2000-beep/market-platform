from __future__ import annotations

import copy
import json
from collections.abc import Callable
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from types import MappingProxyType
from typing import NoReturn

import pandas as pd
import pytest

from market_platform.application import (
    BuiltInHistoricalReplayResearchStateModelResolver,
    BuiltInHistoricalReplayResearchStrategyResolver,
    HistoricalReplayResearchApplicationRequest,
    HistoricalReplayResearchApplicationRequestError,
    HistoricalReplayResearchApplicationResponse,
    HistoricalReplayResearchApplicationService,
    HistoricalReplayResearchInlineSourceRequest,
    HistoricalReplayResearchMemberRequest,
    HistoricalReplayResearchPriceRowRequest,
    HistoricalReplayResearchStateModelRequest,
    HistoricalReplayResearchStrategyRequest,
    HistoricalSourceValidationError,
    ResolverIdentityMismatchError,
    StateModelResolutionError,
    StrategyResolutionError,
    UnsupportedApplicationSchemaError,
)
from market_platform.application import (
    historical_replay_research_resolvers as resolver_module,
)
from market_platform.data import HistoricalPriceSeries
from market_platform.observation import MarketObservation
from market_platform.replay import (
    HistoricalReplayService,
    HistoricalReplaySpecification,
    SoftwareRevision,
    default_replay_structure_derivation_identity,
)
from market_platform.research import (
    HistoricalReplayResearchWorkflowService,
    HistoricalReplayResearchWorkflowStatus,
)
from market_platform.state import BaselineMarketStateModel, MarketState
from market_platform.strategy import (
    BaselineTrendRegimeStrategy,
    BaselineVolatilityRegimeStrategy,
    StrategyConfiguration,
    StrategyEvaluation,
    StrategyRunnerError,
)

_START = datetime(2026, 1, 1, tzinfo=UTC)


def _parameters(
    strategy: BaselineTrendRegimeStrategy
    | BaselineVolatilityRegimeStrategy,
) -> dict[str, object]:
    configuration = strategy.configuration.to_dict()["parameters"]
    assert isinstance(configuration, dict)
    return configuration


def _strategy_request(
    strategy: BaselineTrendRegimeStrategy
    | BaselineVolatilityRegimeStrategy,
) -> HistoricalReplayResearchStrategyRequest:
    return HistoricalReplayResearchStrategyRequest(
        strategy_id=strategy.strategy_id,
        strategy_version=strategy.strategy_version,
        configuration=_parameters(strategy),
    )


def _member(
    *,
    evaluation_start: datetime = _START + timedelta(days=50),
    reverse: bool = False,
) -> HistoricalReplayResearchMemberRequest:
    strategies = [
        _strategy_request(BaselineTrendRegimeStrategy()),
        _strategy_request(BaselineVolatilityRegimeStrategy()),
    ]
    if reverse:
        strategies.reverse()
    state_model = BaselineMarketStateModel()
    return HistoricalReplayResearchMemberRequest(
        replay_specification=HistoricalReplaySpecification(
            symbol="MSFT",
            interval="1day",
            context_start=_START,
            evaluation_start=evaluation_start,
            evaluation_end=evaluation_start + timedelta(days=2),
        ),
        strategies=tuple(strategies),
        state_model=HistoricalReplayResearchStateModelRequest(
            model_id=state_model.model_id,
            model_version=state_model.model_version,
            configuration={},
            expected_configuration_fingerprint=None,
        ),
        structure_derivation=default_replay_structure_derivation_identity(),
    )


def _request(
    *,
    candidates: tuple[HistoricalReplayResearchMemberRequest, ...] = (),
    provider: str = "application-provider",
) -> HistoricalReplayResearchApplicationRequest:
    rows = tuple(
        HistoricalReplayResearchPriceRowRequest(
            timestamp=_START + timedelta(days=index),
            open=100.0 + index,
            high=101.0 + index,
            low=99.0 + index,
            close=100.5 + index,
            volume=-0.0 if index == 0 else 1_000_000.0,
        )
        for index in range(60)
    )
    return HistoricalReplayResearchApplicationRequest(
        source=HistoricalReplayResearchInlineSourceRequest(
            symbol="MSFT",
            interval="1day",
            provider=provider,
            rows=rows,
        ),
        baseline=_member(),
        candidates=candidates,
        replay_software_revision=SoftwareRevision("replay", False),
        comparison_software_revision=SoftwareRevision("comparison", True),
        workflow_software_revision=SoftwareRevision("workflow", False),
    )


def _application_service(
    replay_service: HistoricalReplayService | None = None,
) -> HistoricalReplayResearchApplicationService:
    return HistoricalReplayResearchApplicationService(
        HistoricalReplayResearchWorkflowService(
            HistoricalReplayService()
            if replay_service is None
            else replay_service
        ),
        BuiltInHistoricalReplayResearchStrategyResolver(),
        BuiltInHistoricalReplayResearchStateModelResolver(),
    )


def test_request_codec_round_trip_is_strict_and_canonical() -> None:
    request = _request(candidates=(_member(reverse=True), _member()))
    payload = request.to_dict()

    reconstructed = HistoricalReplayResearchApplicationRequest.from_dict(payload)

    assert reconstructed == request
    assert reconstructed.to_dict() == payload
    assert reconstructed.request_fingerprint == request.request_fingerprint
    assert json.loads(json.dumps(payload)) == payload
    assert request.source.row_count == 60
    assert request.source.rows[0].volume == 0.0
    assert str(request.source.rows[0].volume).startswith("-")


@pytest.mark.parametrize(
    ("mutate", "error", "match"),
    [
        (
            lambda payload: payload.update({"unexpected": True}),
            HistoricalReplayResearchApplicationRequestError,
            "unknown fields",
        ),
        (
            lambda payload: payload.pop("baseline"),
            HistoricalReplayResearchApplicationRequestError,
            "missing fields",
        ),
        (
            lambda payload: payload.update(
                {"schema_version": "historical_replay_research_application_request/v2"}
            ),
            UnsupportedApplicationSchemaError,
            "unsupported",
        ),
        (
            lambda payload: payload["source"]["rows"][0].update(
                {"extra": 1}
            ),
            HistoricalReplayResearchApplicationRequestError,
            "unknown fields",
        ),
        (
            lambda payload: payload["source"]["rows"][0].update(
                {"volume": True}
            ),
            HistoricalReplayResearchApplicationRequestError,
            "number",
        ),
        (
            lambda payload: payload["source"]["rows"][0].update(
                {"close": float("nan")}
            ),
            HistoricalReplayResearchApplicationRequestError,
            "finite",
        ),
        (
            lambda payload: payload["source"]["rows"][0].update(
                {"timestamp": "2026-01-01T00:00:00"}
            ),
            HistoricalReplayResearchApplicationRequestError,
            "timezone-aware",
        ),
    ],
)
def test_request_codec_rejects_malformed_payloads(
    mutate: Callable[[dict[str, object]], object],
    error: type[Exception],
    match: str,
) -> None:
    payload = copy.deepcopy(_request().to_dict())
    mutate(payload)
    with pytest.raises(error, match=match):
        HistoricalReplayResearchApplicationRequest.from_dict(payload)


def test_timestamp_offsets_normalize_and_duplicate_instants_fail() -> None:
    payload = _request().to_dict()
    source = payload["source"]
    assert isinstance(source, dict)
    rows = source["rows"]
    assert isinstance(rows, list)
    first = rows[0]
    second = rows[1]
    assert isinstance(first, dict)
    assert isinstance(second, dict)
    first["timestamp"] = "2026-01-01T08:00:00+08:00"
    normalized = HistoricalReplayResearchApplicationRequest.from_dict(payload)
    assert normalized.source.rows[0].timestamp == _START
    second["timestamp"] = "2026-01-01T08:00:00+08:00"
    with pytest.raises(
        HistoricalReplayResearchApplicationRequestError,
        match="strictly increasing",
    ):
        HistoricalReplayResearchApplicationRequest.from_dict(payload)


def test_request_identity_is_mapping_neutral_and_order_sensitive() -> None:
    left = _request(candidates=(_member(), _member(reverse=True)))
    payload = left.to_dict()
    baseline = payload["baseline"]
    assert isinstance(baseline, dict)
    strategies = baseline["strategies"]
    assert isinstance(strategies, list)
    first = strategies[0]
    assert isinstance(first, dict)
    configuration = first["configuration"]
    assert isinstance(configuration, dict)
    first["configuration"] = dict(reversed(tuple(configuration.items())))
    reordered_mapping = HistoricalReplayResearchApplicationRequest.from_dict(payload)
    right = _request(candidates=(_member(reverse=True), _member()))

    assert reordered_mapping.request_fingerprint == left.request_fingerprint
    assert right.request_fingerprint != left.request_fingerprint


def test_builtin_resolvers_are_fresh_and_validate_requests() -> None:
    strategy_request = _strategy_request(BaselineTrendRegimeStrategy())
    strategy_resolver = BuiltInHistoricalReplayResearchStrategyResolver()
    first_strategy = strategy_resolver.resolve(strategy_request)
    second_strategy = strategy_resolver.resolve(strategy_request)
    state_request = _member().state_model
    state_resolver = BuiltInHistoricalReplayResearchStateModelResolver()
    first_state = state_resolver.resolve(state_request)
    second_state = state_resolver.resolve(state_request)

    assert first_strategy is not second_strategy
    assert first_strategy.configuration == second_strategy.configuration
    assert first_state is not second_state
    with pytest.raises(FrozenInstanceError):
        strategy_resolver._factories = {}  # type: ignore[misc,assignment]
    with pytest.raises(FrozenInstanceError):
        state_resolver._factories = {}  # type: ignore[misc,assignment]
    with pytest.raises(StrategyResolutionError, match="unknown"):
        strategy_resolver.resolve(
            HistoricalReplayResearchStrategyRequest(
                "unknown",
                "1.0.0",
                {},
            )
        )
    with pytest.raises(StateModelResolutionError, match="empty configuration"):
        state_resolver.resolve(
            HistoricalReplayResearchStateModelRequest(
                state_request.model_id,
                state_request.model_version,
                {"unexpected": True},
                None,
            )
        )


class _WrongStrategyResolver:
    def resolve(
        self,
        request: HistoricalReplayResearchStrategyRequest,
    ) -> BaselineTrendRegimeStrategy:
        del request
        return BaselineTrendRegimeStrategy()


class _WrongStateResolver:
    class _WrongState(BaselineMarketStateModel):
        @property
        def model_id(self) -> str:
            return "wrong"

    def resolve(
        self,
        request: HistoricalReplayResearchStateModelRequest,
    ) -> _WrongState:
        del request
        return self._WrongState()


class _BroadOnlyStrategy:
    _delegate = BaselineTrendRegimeStrategy()

    @property
    def strategy_id(self) -> str:
        return self._delegate.strategy_id

    @property
    def strategy_version(self) -> str:
        return self._delegate.strategy_version

    def evaluate(
        self,
        state: MarketState,
        observation: MarketObservation,
    ) -> StrategyEvaluation:
        return self._delegate.evaluate(state, observation)


class _BroadStrategyResolver:
    def resolve(self, request: HistoricalReplayResearchStrategyRequest):  # type: ignore[no-untyped-def]
        del request
        return _BroadOnlyStrategy()


class _BroadOnlyStateModel:
    _delegate = BaselineMarketStateModel()

    @property
    def model_id(self) -> str:
        return self._delegate.model_id

    @property
    def model_version(self) -> str:
        return self._delegate.model_version

    def evaluate(self, observation: MarketObservation) -> MarketState:
        return self._delegate.evaluate(observation)


class _BroadStateResolver:
    def resolve(self, request: HistoricalReplayResearchStateModelRequest):  # type: ignore[no-untyped-def]
        del request
        return _BroadOnlyStateModel()


def test_application_rejects_resolver_identity_mismatch() -> None:
    workflow = HistoricalReplayResearchWorkflowService(HistoricalReplayService())
    with pytest.raises(ResolverIdentityMismatchError, match="strategy identity"):
        HistoricalReplayResearchApplicationService(
            workflow,
            _WrongStrategyResolver(),
            BuiltInHistoricalReplayResearchStateModelResolver(),
        ).execute(_request())


def test_application_rejects_broad_only_executables() -> None:
    workflow = HistoricalReplayResearchWorkflowService(HistoricalReplayService())
    with pytest.raises(ResolverIdentityMismatchError, match="StrategyInstance"):
        HistoricalReplayResearchApplicationService(
            workflow,
            _BroadStrategyResolver(),
            BuiltInHistoricalReplayResearchStateModelResolver(),
        ).execute(_request())
    with pytest.raises(
        ResolverIdentityMismatchError,
        match="StateModelInstance",
    ):
        HistoricalReplayResearchApplicationService(
            workflow,
            BuiltInHistoricalReplayResearchStrategyResolver(),
            _BroadStateResolver(),
        ).execute(_request())
    with pytest.raises(ResolverIdentityMismatchError, match="state-model identity"):
        HistoricalReplayResearchApplicationService(
            workflow,
            BuiltInHistoricalReplayResearchStrategyResolver(),
            _WrongStateResolver(),
        ).execute(_request())


def test_application_source_uses_canonical_domain_validation() -> None:
    request = _request()
    invalid_row = HistoricalReplayResearchPriceRowRequest(
        timestamp=request.source.rows[0].timestamp,
        open=-1.0,
        high=1.0,
        low=0.5,
        close=0.75,
        volume=1.0,
    )
    invalid = HistoricalReplayResearchApplicationRequest(
        source=HistoricalReplayResearchInlineSourceRequest(
            symbol=request.source.symbol,
            interval=request.source.interval,
            provider=request.source.provider,
            rows=(invalid_row, *request.source.rows[1:]),
        ),
        baseline=request.baseline,
        candidates=(),
        replay_software_revision=request.replay_software_revision,
        comparison_software_revision=request.comparison_software_revision,
        workflow_software_revision=request.workflow_software_revision,
    )
    with pytest.raises(HistoricalSourceValidationError) as raised:
        _application_service().execute(invalid)
    assert isinstance(raised.value.__cause__, ValueError)


def test_application_source_matches_direct_historical_series() -> None:
    request = _request()
    direct = HistoricalPriceSeries(
        pd.DataFrame(
            [
                {
                    "symbol": request.source.symbol,
                    "timestamp": row.timestamp,
                    "open": row.open,
                    "high": row.high,
                    "low": row.low,
                    "close": row.close,
                    "volume": row.volume,
                    "provider": request.source.provider,
                }
                for row in request.source.rows
            ]
        ),
        symbol=request.source.symbol,
        provider=request.source.provider,
    )
    actual = _application_service().execute(request).workflow_result.specification

    assert actual.source.symbol == direct.symbol
    assert actual.source.provider == direct.provider
    assert actual.source_interval == request.source.interval
    assert actual.source.to_dataframe().equals(direct.to_dataframe())
    assert actual.source.content_fingerprint == direct.content_fingerprint


def test_application_executes_exact_workflow_and_bounds_response() -> None:
    request = _request(candidates=(_member(reverse=True), _member()))
    response = _application_service().execute(request)
    payload = response.to_dict()

    assert response.status is HistoricalReplayResearchWorkflowStatus.SUCCEEDED
    assert response.application_request_fingerprint == request.request_fingerprint
    assert response.workflow_specification_fingerprint != request.request_fingerprint
    assert response.workflow_result_fingerprint == (
        response.workflow_result.workflow_result_fingerprint
    )
    assert payload["schema_version"] == (
        "historical_replay_research_application_response/v1"
    )
    candidates = payload["candidates"]
    assert isinstance(candidates, list)
    assert all(isinstance(item, dict) for item in candidates)
    assert [item["candidate_index"] for item in candidates] == [0, 1]
    assert all("status" in item and "replay_status" not in item for item in candidates)
    experiment = payload["experiment"]
    assert isinstance(experiment, dict)
    comparisons = experiment["comparisons"]
    assert isinstance(comparisons, list)
    assert all(isinstance(item, dict) for item in comparisons)
    assert [item["candidate_index"] for item in comparisons] == [0, 1]
    rendered = json.dumps(payload)
    for forbidden in (
        "integrity_checksum",
        "artifact_schema_version",
        "observation_fingerprint",
        "source_row_count",
        "application_response_fingerprint",
    ):
        assert forbidden not in rendered


class _CountingWorkflowService(HistoricalReplayResearchWorkflowService):
    def __init__(self) -> None:
        super().__init__(HistoricalReplayService())
        self.calls = 0

    def run(self, specification):  # type: ignore[no-untyped-def]
        self.calls += 1
        return super().run(specification)


def test_application_calls_workflow_once() -> None:
    workflow = _CountingWorkflowService()
    response = HistoricalReplayResearchApplicationService(
        workflow,
        BuiltInHistoricalReplayResearchStrategyResolver(),
        BuiltInHistoricalReplayResearchStateModelResolver(),
    ).execute(_request(candidates=(_member(),)))

    assert workflow.calls == 1
    assert response.workflow_result.specification.replay_software_revision == (
        SoftwareRevision("replay", False)
    )
    assert response.workflow_result.specification.comparison_software_revision == (
        SoftwareRevision("comparison", True)
    )
    assert response.workflow_result.specification.workflow_software_revision == (
        SoftwareRevision("workflow", False)
    )


class _FailingReplayService(HistoricalReplayService):
    def __init__(self, failures: set[int], failure: BaseException) -> None:
        super().__init__()
        self.failures = failures
        self.failure = failure
        self.calls = 0

    def run_execution(self, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        index = self.calls
        self.calls += 1
        if index in self.failures:
            raise self.failure
        return super().run_execution(*args, **kwargs)  # type: ignore[arg-type]


def test_strategy_runner_error_remains_a_workflow_outcome() -> None:
    replay = _FailingReplayService({1}, StrategyRunnerError("captured"))
    response = _application_service(replay).execute(
        _request(candidates=(_member(), _member(reverse=True)))
    )

    assert (
        response.status
        is HistoricalReplayResearchWorkflowStatus.PARTIALLY_SUCCEEDED
    )
    assert replay.calls == 3


def test_baseline_failure_and_incompatible_experiment_remain_domain_outcomes() -> None:
    failed_replay = _FailingReplayService({0}, StrategyRunnerError("captured"))
    failed = _application_service(failed_replay).execute(
        _request(candidates=(_member(),))
    )
    incompatible = _application_service().execute(
        _request(
            candidates=(
                _member(evaluation_start=_START + timedelta(days=51)),
            )
        )
    )

    assert failed.status is HistoricalReplayResearchWorkflowStatus.FAILED
    assert failed_replay.calls == 1
    assert incompatible.status is HistoricalReplayResearchWorkflowStatus.SUCCEEDED
    assert incompatible.workflow_result.experiment is not None
    comparison = incompatible.workflow_result.experiment.comparisons[0]
    assert not comparison.compatibility.compatible


@pytest.mark.parametrize(
    "failure",
    [
        ValueError("domain"),
        RuntimeError("programming"),
        AssertionError("invariant"),
        KeyboardInterrupt(),
        SystemExit(),
    ],
)
def test_workflow_and_control_flow_errors_propagate(
    failure: BaseException,
) -> None:
    with pytest.raises(type(failure)):
        _application_service(_FailingReplayService({0}, failure)).execute(
            _request()
        )


def test_response_direct_construction_is_forbidden() -> None:
    with pytest.raises(TypeError, match="ApplicationService.execute"):
        HistoricalReplayResearchApplicationResponse()


def test_response_factory_requires_exact_executed_specification() -> None:
    request = _request()
    first = _application_service().execute(request)
    second = _application_service().execute(request)

    with pytest.raises(ValueError, match="exact executed specification"):
        HistoricalReplayResearchApplicationResponse._create(
            request,
            first.workflow_result.specification,
            second.workflow_result,
        )


class _PassiveConfigEnum(StrEnum):
    VALUE = "value"


@pytest.mark.parametrize(
    "invalid",
    [
        {1, 2},
        {"nested": {1, 2}},
        frozenset({1, 2}),
        b"bytes",
        datetime(2026, 1, 1, tzinfo=UTC),
        _PassiveConfigEnum.VALUE,
        lambda: None,
        object(),
        {1: "non-string-key"},
        {"nested": float("nan")},
        {"nested": float("inf")},
    ],
)
def test_strategy_direct_constructor_rejects_non_json_configuration(
    invalid: object,
) -> None:
    configuration = invalid if isinstance(invalid, dict) else {"value": invalid}
    with pytest.raises(
        HistoricalReplayResearchApplicationRequestError,
        match="configuration",
    ):
        HistoricalReplayResearchStrategyRequest("strategy", "1", configuration)


def test_direct_configuration_models_reject_non_mapping_and_runtime_values() -> None:
    state = _member().state_model
    with pytest.raises(HistoricalReplayResearchApplicationRequestError):
        HistoricalReplayResearchStrategyRequest("strategy", "1", {1, 2})  # type: ignore[arg-type]
    with pytest.raises(HistoricalReplayResearchApplicationRequestError):
        HistoricalReplayResearchStateModelRequest(
            state.model_id,
            state.model_version,
            {"runtime": object()},
            None,
        )


def test_passive_configuration_is_shared_immutable_and_codec_equivalent() -> None:
    mutable = {
        "nested": {
            "sequence": [None, True, "value", 7, 1.5],
        }
    }
    direct = HistoricalReplayResearchStrategyRequest("strategy", "1", mutable)
    mutable["nested"]["sequence"].append("changed")

    assert direct.to_dict()["configuration"] == {
        "nested": {"sequence": [None, True, "value", 7, 1.5]}
    }
    assert isinstance(direct.configuration["nested"], MappingProxyType)
    payload = _request().to_dict()
    baseline = payload["baseline"]
    assert isinstance(baseline, dict)
    strategies = baseline["strategies"]
    assert isinstance(strategies, list)
    strategies[0] = direct.to_dict()
    decoded = HistoricalReplayResearchApplicationRequest.from_dict(payload)
    assert decoded.baseline.strategies[0] == direct


def _request_with_first_number(
    value: int | float,
) -> HistoricalReplayResearchApplicationRequest:
    request = _request()
    first = request.source.rows[0]
    row = replace(
        first,
        open=value,
        high=value,
        low=value,
        close=value,
        volume=value,
    )
    return replace(
        request,
        source=replace(request.source, rows=(row, *request.source.rows[1:])),
    )


def test_numeric_types_and_large_integers_are_identity_significant() -> None:
    large = _request_with_first_number(9_007_199_254_740_993)
    nearby = _request_with_first_number(9_007_199_254_740_992)
    integer = _request_with_first_number(100)
    floating = _request_with_first_number(100.0)
    positive_zero = _request_with_first_number(0.0)
    negative_zero = _request_with_first_number(-0.0)

    decoded = HistoricalReplayResearchApplicationRequest.from_dict(large.to_dict())
    assert decoded.source.rows[0].open == 9_007_199_254_740_993
    assert type(decoded.source.rows[0].open) is int
    assert large.request_fingerprint != nearby.request_fingerprint
    assert integer.request_fingerprint != floating.request_fingerprint
    assert positive_zero.request_fingerprint != negative_zero.request_fingerprint
    assert str(negative_zero.source.rows[0].open).startswith("-")


def test_distinct_numeric_requests_may_resolve_to_equal_workflow_intent() -> None:
    integer = _request_with_first_number(100)
    floating = _request_with_first_number(100.0)
    integer_response = _application_service().execute(integer)
    floating_response = _application_service().execute(floating)

    assert integer.request_fingerprint != floating.request_fingerprint
    assert (
        integer_response.workflow_specification_fingerprint
        == floating_response.workflow_specification_fingerprint
    )
    assert (
        integer_response.application_request_fingerprint
        == integer.request_fingerprint
    )
    assert (
        floating_response.application_request_fingerprint
        == floating.request_fingerprint
    )


def _changed_trend_request() -> HistoricalReplayResearchStrategyRequest:
    strategy = BaselineTrendRegimeStrategy()
    parameters = _parameters(strategy)
    parameters["required_trend_regimes"] = ["up"]
    return HistoricalReplayResearchStrategyRequest(
        strategy.strategy_id,
        strategy.strategy_version,
        parameters,
    )


def _response_mismatch_requests() -> tuple[
    HistoricalReplayResearchApplicationRequest,
    ...,
]:
    request = _request(candidates=(_member(), _member(reverse=True)))
    source_row = replace(request.source.rows[0], close=100.25)
    source_changed = replace(
        request,
        source=replace(
            request.source,
            rows=(source_row, *request.source.rows[1:]),
        ),
    )
    strategy_changed = replace(
        request,
        baseline=replace(
            request.baseline,
            strategies=(
                _changed_trend_request(),
                request.baseline.strategies[1],
            ),
        ),
    )
    state_changed = replace(
        request,
        baseline=replace(
            request.baseline,
            state_model=replace(
                request.baseline.state_model,
                expected_configuration_fingerprint="sha256:" + "1" * 64,
            ),
        ),
    )
    structure_changed = replace(
        request,
        baseline=replace(
            request.baseline,
            structure_derivation=replace(
                request.baseline.structure_derivation,
                methodology="different",
            ),
        ),
    )
    return (
        source_changed,
        replace(request, baseline=_member(reverse=True)),
        strategy_changed,
        state_changed,
        structure_changed,
        replace(
            request,
            baseline=_member(
                evaluation_start=_START + timedelta(days=49)
            ),
        ),
        replace(request, candidates=request.candidates[:1]),
        replace(request, candidates=tuple(reversed(request.candidates))),
        replace(
            request,
            source=replace(request.source, provider="other-provider"),
        ),
        replace(
            request,
            replay_software_revision=replace(
                request.replay_software_revision,
                dirty=True,
            ),
        ),
        replace(
            request,
            comparison_software_revision=replace(
                request.comparison_software_revision,
                dirty=False,
            ),
        ),
        replace(
            request,
            workflow_software_revision=replace(
                request.workflow_software_revision,
                dirty=True,
            ),
        ),
    )


def test_response_rejects_complete_request_to_workflow_mismatches() -> None:
    request = _request(candidates=(_member(), _member(reverse=True)))
    response = _application_service().execute(request)

    for mismatched in _response_mismatch_requests():
        with pytest.raises(ValueError, match="does not match request"):
            HistoricalReplayResearchApplicationResponse._create(
                mismatched,
                response.workflow_result.specification,
                response.workflow_result,
            )


@pytest.mark.parametrize(
    "failure",
    [
        TypeError("factory"),
        ValueError("factory"),
        RuntimeError("factory"),
        AssertionError("factory"),
    ],
)
def test_unexpected_strategy_factory_defects_propagate(
    failure: Exception,
) -> None:
    request = _strategy_request(BaselineTrendRegimeStrategy())
    resolver = BuiltInHistoricalReplayResearchStrategyResolver()
    descriptor = resolver._factories[(request.strategy_id, request.strategy_version)]

    def fail(configuration: StrategyConfiguration) -> NoReturn:
        del configuration
        raise failure

    object.__setattr__(
        resolver,
        "_factories",
        MappingProxyType(
            {
                (request.strategy_id, request.strategy_version): (
                    resolver_module._StrategyFactoryDescriptor(
                        descriptor.validate,
                        fail,
                    )
                )
            }
        ),
    )
    with pytest.raises(type(failure), match="factory"):
        resolver.resolve(request)


def test_expected_builtin_configuration_failure_is_translated() -> None:
    strategy = BaselineTrendRegimeStrategy()
    invalid = HistoricalReplayResearchStrategyRequest(
        strategy.strategy_id,
        strategy.strategy_version,
        {"unexpected": True},
    )
    with pytest.raises(StrategyResolutionError, match="invalid configuration"):
        BuiltInHistoricalReplayResearchStrategyResolver().resolve(invalid)


@pytest.mark.parametrize(
    "failure",
    [
        TypeError("factory"),
        ValueError("factory"),
        RuntimeError("factory"),
        AssertionError("factory"),
    ],
)
def test_unexpected_state_model_factory_defects_propagate(
    failure: Exception,
) -> None:
    request = _member().state_model
    resolver = BuiltInHistoricalReplayResearchStateModelResolver()

    def fail() -> NoReturn:
        raise failure

    object.__setattr__(
        resolver,
        "_factories",
        MappingProxyType({(request.model_id, request.model_version): fail}),
    )
    with pytest.raises(type(failure), match="factory"):
        resolver.resolve(request)


def test_application_request_repr_is_bounded_and_identity_neutral() -> None:
    request = _request(candidates=(_member(),))
    rendered = repr(request)
    reconstructed = HistoricalReplayResearchApplicationRequest.from_dict(
        request.to_dict()
    )

    assert "HistoricalReplayResearchApplicationRequest" in rendered
    assert "1000000.0" not in rendered
    assert "HistoricalReplayResearchPriceRowRequest" not in rendered
    assert " object at 0x" not in rendered
    assert reconstructed == request
    assert reconstructed.request_fingerprint == request.request_fingerprint
