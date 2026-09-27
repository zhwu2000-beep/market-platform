"""Deterministic single-instrument execution; SELECTED grants no authority."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from market_platform.instruments.identity import CanonicalInstrumentId
from market_platform.radar.context import RadarEvaluationContext
from market_platform.radar.core import (
    RadarGate,
    RadarGateDisposition,
    RadarGateIdentity,
    RadarGateOccurrence,
    RadarGateResult,
    RadarPipelineOutcome,
    RadarProfile,
)


class RadarPipelineError(Exception):
    """Invalid Pipeline wiring, never a filtering or investment outcome."""


class RadarPipelineFailureCategory(StrEnum):
    """Stable execution reasons, independent of exception text."""

    GATE_EXCEPTION = "GATE_EXCEPTION"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
    INVALID_RESULT = "INVALID_RESULT"


@dataclass(frozen=True, slots=True)
class RadarPipelineFailure:
    """Failure location without a synthetic Gate result or live exception."""

    occurrence: RadarGateOccurrence
    category: RadarPipelineFailureCategory

    def __post_init__(self) -> None:
        if type(self.occurrence) is not RadarGateOccurrence:
            raise TypeError("occurrence must be a RadarGateOccurrence")
        if type(self.category) is not RadarPipelineFailureCategory:
            raise TypeError("category must be a RadarPipelineFailureCategory")


@dataclass(frozen=True, slots=True)
class RadarPipelineResult:
    """Actual completed prefix and input correspondence, not input equivalence.

    Outcome and termination are derived to prevent contradictory audit fields.
    The as-of instant is detached into UTC; no result fingerprint is implied.
    """

    profile: RadarProfile
    instrument: CanonicalInstrumentId
    as_of: datetime
    executed_results: tuple[RadarGateResult, ...]
    failure: RadarPipelineFailure | None = None

    def __post_init__(self) -> None:
        if type(self.profile) is not RadarProfile:
            raise TypeError("profile must be a RadarProfile")
        if type(self.instrument) is not CanonicalInstrumentId:
            raise TypeError("instrument must be a CanonicalInstrumentId")
        if not isinstance(self.as_of, datetime):
            raise TypeError("as_of must be a datetime")
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        # Rebuild a plain datetime so a caller-owned tzinfo/subclass is not retained.
        utc = self.as_of.astimezone(UTC)
        object.__setattr__(
            self,
            "as_of",
            datetime(
                utc.year,
                utc.month,
                utc.day,
                utc.hour,
                utc.minute,
                utc.second,
                utc.microsecond,
                tzinfo=UTC,
            ),
        )
        if type(self.executed_results) not in (tuple, list):
            raise TypeError("executed_results must be an ordered tuple or list")
        results = tuple(self.executed_results)
        object.__setattr__(self, "executed_results", results)
        if any(type(result) is not RadarGateResult for result in results):
            raise TypeError("executed_results must contain RadarGateResult values")
        if (
            tuple(result.occurrence for result in results)
            != self.profile.gates[: len(results)]
        ):
            raise ValueError("executed_results must match the exact Profile prefix")
        if any(r.disposition is not RadarGateDisposition.PASS for r in results[:-1]):
            raise ValueError("results must stop at the first terminating Gate")
        if self.failure is not None:
            if type(self.failure) is not RadarPipelineFailure:
                raise TypeError("failure must be a RadarPipelineFailure or None")
            if (
                len(results) >= len(self.profile.gates)
                or self.failure.occurrence != self.profile.gates[len(results)]
                or any(r.disposition is not RadarGateDisposition.PASS for r in results)
            ):
                raise ValueError("failure must identify the next occurrence after PASS")
        elif not results or (
            results[-1].disposition is RadarGateDisposition.PASS
            and len(results) != len(self.profile.gates)
        ):
            raise ValueError("successful traversal must complete the Profile")

    @property
    def outcome(self) -> RadarPipelineOutcome:
        if self.failure is not None:
            return RadarPipelineOutcome.FAILED
        return {
            RadarGateDisposition.PASS: RadarPipelineOutcome.SELECTED,
            RadarGateDisposition.DROP: RadarPipelineOutcome.FILTERED,
            RadarGateDisposition.ATTENTION: RadarPipelineOutcome.ATTENTION,
        }[self.executed_results[-1].disposition]

    @property
    def terminating_occurrence(self) -> RadarGateOccurrence | None:
        if self.failure is not None:
            return self.failure.occurrence
        if self.outcome is RadarPipelineOutcome.SELECTED:
            return None
        return self.executed_results[-1].occurrence


class RadarPipeline:
    """Caller-resolved evaluators, copied and validated before any invocation.

    Profile order alone determines execution order. Mutable evaluator identity
    is rechecked around each invocation; subsequent drift is execution failure.
    Gates must obey the context's read-only fact contract. No retries occur.
    """

    __slots__ = ("_profile", "_gates")

    def __init__(
        self,
        profile: RadarProfile,
        resolved_gates: Mapping[str, RadarGate[RadarEvaluationContext]],
    ) -> None:
        if type(profile) is not RadarProfile:
            raise TypeError("profile must be a RadarProfile")
        if not isinstance(resolved_gates, Mapping):
            raise TypeError("resolved_gates must be a mapping")
        gates = dict(resolved_gates)
        if set(gates) != {occurrence.occurrence_id for occurrence in profile.gates}:
            raise RadarPipelineError("resolved bindings must exactly match the Profile")
        for occurrence in profile.gates:
            gate = gates[occurrence.occurrence_id]
            try:
                valid = callable(getattr(gate, "evaluate", None)) and _matches_identity(
                    gate, occurrence
                )
            except Exception as exc:
                raise RadarPipelineError(
                    "cannot inspect resolved Gate contract"
                ) from exc
            if not valid:
                raise RadarPipelineError("resolved Gate contract/identity mismatch")
        self._profile = profile
        self._gates = gates

    def evaluate(self, context: RadarEvaluationContext) -> RadarPipelineResult:
        """Execute one context, retaining only valid, actually returned results."""
        if type(context) is not RadarEvaluationContext:
            raise TypeError("context must be a RadarEvaluationContext")
        results: list[RadarGateResult] = []
        failure = None
        for occurrence in self._profile.gates:
            gate = self._gates[occurrence.occurrence_id]
            category = RadarPipelineFailureCategory.IDENTITY_MISMATCH
            try:
                if not _matches_identity(gate, occurrence):
                    raise RadarPipelineError("Gate identity drifted before evaluation")
                category = RadarPipelineFailureCategory.GATE_EXCEPTION
                result = gate.evaluate(context)
                category = RadarPipelineFailureCategory.IDENTITY_MISMATCH
                if not _matches_identity(gate, occurrence):
                    raise RadarPipelineError("Gate identity drifted during evaluation")
                category = RadarPipelineFailureCategory.INVALID_RESULT
                if (
                    type(result) is not RadarGateResult
                    or result.occurrence != occurrence
                ):
                    raise RadarPipelineError("Gate returned a noncorresponding result")
            except Exception:
                failure = RadarPipelineFailure(occurrence, category)
                break
            results.append(result)
            if result.disposition is not RadarGateDisposition.PASS:
                break
        return RadarPipelineResult(
            self._profile, context.instrument, context.as_of, tuple(results), failure
        )


def _matches_identity(
    gate: RadarGate[RadarEvaluationContext], occurrence: RadarGateOccurrence
) -> bool:
    identity = gate.identity
    return type(identity) is RadarGateIdentity and identity == occurrence.gate_identity
