"""Safe executable resolvers for historical Replay research requests."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Protocol, runtime_checkable

from market_platform.application.errors import (
    StateModelResolutionError,
    StrategyResolutionError,
)
from market_platform.application.historical_replay_research import (
    HistoricalReplayResearchStateModelRequest,
    HistoricalReplayResearchStrategyRequest,
)
from market_platform.research import HistoricalReplayResearchStateModelInstance
from market_platform.state import (
    BaselineMarketStateModel,
    MomentumRegime,
    TrendRegime,
    VolatilityRegime,
)
from market_platform.strategy import (
    BaselineTrendRegimeStrategy,
    BaselineVolatilityRegimeStrategy,
    StrategyConfiguration,
    StrategyInstance,
)

StrategyFactory = Callable[[StrategyConfiguration], StrategyInstance]
StrategyConfigurationValidator = Callable[[StrategyConfiguration], None]
StateModelFactory = Callable[[], HistoricalReplayResearchStateModelInstance]


class _BuiltInStrategyConfigurationError(ValueError):
    """Expected invalid allow-listed strategy configuration."""


@dataclass(frozen=True, slots=True)
class _StrategyFactoryDescriptor:
    validate: StrategyConfigurationValidator
    create: StrategyFactory


@runtime_checkable
class HistoricalReplayResearchStrategyResolver(Protocol):
    """Resolve one passive strategy request to a fresh executable instance."""

    def resolve(
        self,
        request: HistoricalReplayResearchStrategyRequest,
    ) -> StrategyInstance:
        """Resolve one strategy request."""
        ...


@runtime_checkable
class HistoricalReplayResearchStateModelResolver(Protocol):
    """Resolve one passive state-model request to a fresh executable instance."""

    def resolve(
        self,
        request: HistoricalReplayResearchStateModelRequest,
    ) -> HistoricalReplayResearchStateModelInstance:
        """Resolve one state-model request."""
        ...


@dataclass(frozen=True, slots=True)
class BuiltInHistoricalReplayResearchStrategyResolver:
    """Immutable allow-list resolver for production baseline strategies."""

    _factories: MappingProxyType[
        tuple[str, str],
        _StrategyFactoryDescriptor,
    ] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        trend = BaselineTrendRegimeStrategy()
        volatility = BaselineVolatilityRegimeStrategy()
        factories = _immutable_factory_mapping(
            (
                (
                    (trend.strategy_id, trend.strategy_version),
                    _StrategyFactoryDescriptor(
                        _validate_trend_configuration,
                        BaselineTrendRegimeStrategy,
                    ),
                ),
                (
                    (volatility.strategy_id, volatility.strategy_version),
                    _StrategyFactoryDescriptor(
                        _validate_volatility_configuration,
                        BaselineVolatilityRegimeStrategy,
                    ),
                ),
            )
        )
        object.__setattr__(self, "_factories", factories)

    def resolve(
        self,
        request: HistoricalReplayResearchStrategyRequest,
    ) -> StrategyInstance:
        if not isinstance(request, HistoricalReplayResearchStrategyRequest):
            raise TypeError(
                "request must be a HistoricalReplayResearchStrategyRequest"
            )
        key = (request.strategy_id, request.strategy_version)
        descriptor = self._factories.get(key)
        if descriptor is None:
            raise StrategyResolutionError(
                "unknown built-in strategy ID/version: "
                f"{request.strategy_id}/{request.strategy_version}"
            )
        configuration = StrategyConfiguration(
            strategy_id=request.strategy_id,
            strategy_version=request.strategy_version,
            parameters=request.configuration,
        )
        try:
            descriptor.validate(configuration)
        except _BuiltInStrategyConfigurationError as exc:
            raise StrategyResolutionError(
                f"invalid configuration for strategy {request.strategy_id}"
            ) from exc
        return descriptor.create(configuration)


@dataclass(frozen=True, slots=True)
class BuiltInHistoricalReplayResearchStateModelResolver:
    """Immutable allow-list resolver for the stateless baseline state model."""

    _factories: MappingProxyType[
        tuple[str, str],
        StateModelFactory,
    ] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        baseline = BaselineMarketStateModel()
        factories = _immutable_factory_mapping(
            (((baseline.model_id, baseline.model_version), BaselineMarketStateModel),)
        )
        object.__setattr__(self, "_factories", factories)

    def resolve(
        self,
        request: HistoricalReplayResearchStateModelRequest,
    ) -> HistoricalReplayResearchStateModelInstance:
        if not isinstance(request, HistoricalReplayResearchStateModelRequest):
            raise TypeError(
                "request must be a HistoricalReplayResearchStateModelRequest"
            )
        key = (request.model_id, request.model_version)
        factory = self._factories.get(key)
        if factory is None:
            raise StateModelResolutionError(
                "unknown built-in state-model ID/version: "
                f"{request.model_id}/{request.model_version}"
            )
        if request.configuration:
            raise StateModelResolutionError(
                "BaselineMarketStateModel requires empty configuration"
            )
        if request.expected_configuration_fingerprint is not None:
            raise StateModelResolutionError(
                "BaselineMarketStateModel requires a null configuration fingerprint"
            )
        return factory()


def _immutable_factory_mapping[FactoryT](
    entries: tuple[tuple[tuple[str, str], FactoryT], ...],
) -> MappingProxyType[tuple[str, str], FactoryT]:
    factories: dict[tuple[str, str], FactoryT] = {}
    for key, factory in entries:
        if key in factories:
            raise ValueError(f"duplicate built-in executable ID/version: {key}")
        factories[key] = factory
    return MappingProxyType(factories)


def _validate_trend_configuration(
    configuration: StrategyConfiguration,
) -> None:
    parameters = configuration.parameters
    _require_exact_keys(
        parameters,
        {"required_trend_regimes", "required_momentum_regimes"},
    )
    _validate_enum_sequence(
        parameters["required_trend_regimes"],
        TrendRegime,
        "required_trend_regimes",
    )
    _validate_enum_sequence(
        parameters["required_momentum_regimes"],
        MomentumRegime,
        "required_momentum_regimes",
    )


def _validate_volatility_configuration(
    configuration: StrategyConfiguration,
) -> None:
    parameters = configuration.parameters
    _require_exact_keys(
        parameters,
        {
            "compatible_volatility_regimes",
            "unavailable_volatility_regimes",
            "indeterminate_policy",
        },
    )
    compatible = _validate_enum_sequence(
        parameters["compatible_volatility_regimes"],
        VolatilityRegime,
        "compatible_volatility_regimes",
    )
    unavailable = _validate_enum_sequence(
        parameters["unavailable_volatility_regimes"],
        VolatilityRegime,
        "unavailable_volatility_regimes",
    )
    if compatible != frozenset(
        (VolatilityRegime.LOW, VolatilityRegime.NORMAL)
    ):
        raise _BuiltInStrategyConfigurationError(
            "compatible_volatility_regimes do not match baseline rules"
        )
    if unavailable != frozenset((VolatilityRegime.UNAVAILABLE,)):
        raise _BuiltInStrategyConfigurationError(
            "unavailable_volatility_regimes do not match baseline rules"
        )
    if parameters["indeterminate_policy"] != "not_applicable":
        raise _BuiltInStrategyConfigurationError(
            "indeterminate_policy does not match baseline rules"
        )


def _require_exact_keys(
    parameters: Mapping[str, object],
    expected: set[str],
) -> None:
    if set(parameters) != expected:
        raise _BuiltInStrategyConfigurationError(
            "configuration keys do not match the built-in strategy schema"
        )


def _validate_enum_sequence[EnumT: StrEnum](
    value: object,
    enum_type: type[EnumT],
    field_name: str,
) -> frozenset[EnumT]:
    if not isinstance(value, tuple) or not value:
        raise _BuiltInStrategyConfigurationError(
            f"{field_name} must be a nonempty sequence"
        )
    try:
        return frozenset(enum_type(item) for item in value)
    except (TypeError, ValueError) as exc:
        raise _BuiltInStrategyConfigurationError(
            f"{field_name} contains an unsupported value"
        ) from exc


__all__ = [
    "BuiltInHistoricalReplayResearchStateModelResolver",
    "BuiltInHistoricalReplayResearchStrategyResolver",
    "HistoricalReplayResearchStateModelResolver",
    "HistoricalReplayResearchStrategyResolver",
]
