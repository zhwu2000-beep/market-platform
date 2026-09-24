"""Code-owned Gate allow-list resolution; correspondence grants no authority."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import StrEnum

from market_platform.radar.context import RadarEvaluationContext
from market_platform.radar.core import (
    RadarGate,
    RadarGateIdentity,
    RadarGateOccurrence,
    RadarProfile,
)


class RadarResolutionCategory(StrEnum):
    """Configuration/runtime wiring failures, independent of exception text."""

    UNSUPPORTED_IMPLEMENTATION = "UNSUPPORTED_IMPLEMENTATION"
    INVALID_WIRING = "INVALID_WIRING"
    FACTORY_FAILURE = "FACTORY_FAILURE"
    EVALUATOR_MISMATCH = "EVALUATOR_MISMATCH"


class RadarResolutionError(Exception):
    """Resolution failure, never a filtering, refusal or authority decision."""

    def __init__(self, category: RadarResolutionCategory) -> None:
        self.category = category
        super().__init__(category.value)


@dataclass(frozen=True, slots=True)
class RadarGateImplementationKey:
    """Exact implementation contract, excluding instance configuration values."""

    gate_id: str
    behavioral_revision: str
    configuration_schema: str

    def __post_init__(self) -> None:
        for value in (
            self.gate_id,
            self.behavioral_revision,
            self.configuration_schema,
        ):
            if type(value) is not str or not value.strip():
                raise RadarResolutionError(RadarResolutionCategory.INVALID_WIRING)


@dataclass(frozen=True, slots=True)
class RadarGateFactoryBinding:
    """Approved runtime wiring, never passive Profile configuration.

    Factories receive the exact occurrence, including its passive Gate identity,
    so repeated definitions can produce occurrence-specific results. Factories
    must only construct evaluators: no evaluation, fact acquisition or research.
    Callable code is trusted application wiring, not fingerprinted or sandboxed.
    """

    key: RadarGateImplementationKey
    factory: Callable[[RadarGateOccurrence], RadarGate[RadarEvaluationContext]]

    def __post_init__(self) -> None:
        if type(self.key) is not RadarGateImplementationKey or not callable(
            self.factory
        ):
            raise RadarResolutionError(RadarResolutionCategory.INVALID_WIRING)


class RadarGateResolver:
    """Detached allow-list with all-Profile support preflight and no fallback.

    Every occurrence gets one factory call in Profile order after preflight.
    Construction failures are not retried or rolled back. No Gate is executed.
    """

    __slots__ = ("_bindings",)

    def __init__(self, bindings: Iterable[RadarGateFactoryBinding]) -> None:
        detached: dict[RadarGateImplementationKey, RadarGateFactoryBinding] = {}
        for binding in bindings:
            if type(binding) is not RadarGateFactoryBinding or binding.key in detached:
                raise RadarResolutionError(RadarResolutionCategory.INVALID_WIRING)
            detached[binding.key] = binding
        self._bindings = detached

    def resolve_profile(
        self, profile: RadarProfile
    ) -> dict[str, RadarGate[RadarEvaluationContext]]:
        """Return exact occurrence wiring ready for RadarPipeline construction."""
        if type(profile) is not RadarProfile:
            raise TypeError("profile must be a RadarProfile")
        factories = []
        for occurrence in profile.gates:
            identity = occurrence.gate_identity
            key = RadarGateImplementationKey(
                identity.gate_id,
                identity.behavioral_revision,
                identity.configuration_schema,
            )
            if key not in self._bindings:
                raise RadarResolutionError(
                    RadarResolutionCategory.UNSUPPORTED_IMPLEMENTATION
                )
            factories.append(self._bindings[key].factory)

        resolved: dict[str, RadarGate[RadarEvaluationContext]] = {}
        for occurrence, factory in zip(profile.gates, factories, strict=True):
            try:
                gate = factory(occurrence)
            except Exception as exc:
                raise RadarResolutionError(
                    RadarResolutionCategory.FACTORY_FAILURE
                ) from exc
            try:
                identity = gate.identity
                matches = (
                    type(identity) is RadarGateIdentity
                    and identity == occurrence.gate_identity
                    and callable(gate.evaluate)
                )
            except Exception as exc:
                raise RadarResolutionError(
                    RadarResolutionCategory.EVALUATOR_MISMATCH
                ) from exc
            if not matches:
                raise RadarResolutionError(RadarResolutionCategory.EVALUATOR_MISMATCH)
            resolved[occurrence.occurrence_id] = gate
        return resolved
