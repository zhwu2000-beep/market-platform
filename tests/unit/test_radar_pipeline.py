"""FAST PURE / LOCAL APPLICATION tests with real contexts and tiny fake Gates."""

from collections.abc import Callable
from dataclasses import FrozenInstanceError, fields, replace
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from unittest.mock import Mock

import pytest

from market_platform.instruments.identity import CanonicalInstrumentId
from market_platform.radar.context import RadarEvaluationContext, RadarFactKey
from market_platform.radar.core import (
    RadarGateDisposition,
    RadarGateIdentity,
    RadarGateOccurrence,
    RadarGateResult,
    RadarPipelineOutcome,
    RadarProfile,
)
from market_platform.radar.pipeline import (
    RadarPipeline,
    RadarPipelineError,
    RadarPipelineFailure,
    RadarPipelineFailureCategory,
    RadarPipelineResult,
)

INSTRUMENT = CanonicalInstrumentId("sample")
AS_OF = datetime(2026, 9, 24, tzinfo=timezone(timedelta(hours=8)))
PASS = RadarGateDisposition.PASS
DROP = RadarGateDisposition.DROP
ATTENTION = RadarGateDisposition.ATTENTION


class FakeGate:
    def __init__(self, occurrence: RadarGateOccurrence, calls: list[str]) -> None:
        self.identity = occurrence.gate_identity
        self.occurrence = occurrence
        self.calls = calls
        self.result = RadarGateResult(occurrence, PASS, "passed")
        self.action: Callable[[RadarEvaluationContext], None] = lambda ctx: None

    def evaluate(self, context: RadarEvaluationContext) -> RadarGateResult:
        self.calls.append(self.occurrence.occurrence_id)
        self.action(context)
        return self.result


def setup() -> tuple[RadarProfile, dict[str, FakeGate], list[str]]:
    # Repeated definitions remain distinct occurrences; names are not sort order.
    identity = RadarGateIdentity("fake", "1", "test/v1", {"nested": [1]})
    profile = RadarProfile(
        "test",
        "1",
        "test/v1",
        tuple(RadarGateOccurrence(name, identity) for name in ("z", "a", "m")),
    )
    calls: list[str] = []
    gates = {step.occurrence_id: FakeGate(step, calls) for step in profile.gates}
    return profile, gates, calls


def context() -> RadarEvaluationContext:
    return RadarEvaluationContext(INSTRUMENT, AS_OF, {})


@pytest.mark.parametrize("reverse", [False, True])
def test_selected_in_exact_profile_order(reverse: bool) -> None:
    profile, gates, calls = setup()
    bindings = dict(reversed(tuple(gates.items()))) if reverse else gates
    result = RadarPipeline(profile, bindings).evaluate(context())
    assert calls == ["z", "a", "m"]
    assert result.outcome is RadarPipelineOutcome.SELECTED
    assert result.profile is profile
    assert result.instrument is INSTRUMENT
    assert result.as_of == AS_OF
    assert result.as_of.tzinfo is UTC
    assert result.terminating_occurrence is None
    assert result.failure is None
    assert all(
        actual is gate.result
        for actual, gate in zip(result.executed_results, gates.values(), strict=True)
    )


@pytest.mark.parametrize(
    "disposition,outcome",
    [
        (DROP, RadarPipelineOutcome.FILTERED),
        (ATTENTION, RadarPipelineOutcome.ATTENTION),
    ],
)
def test_terminating_result_retained(
    disposition: RadarGateDisposition, outcome: RadarPipelineOutcome
) -> None:
    profile, gates, calls = setup()
    gates["a"].result = RadarGateResult(profile.gates[1], disposition, "stop")
    result = RadarPipeline(profile, gates).evaluate(context())
    assert calls == ["z", "a"]
    assert result.outcome is outcome
    assert result.executed_results == (gates["z"].result, gates["a"].result)
    assert result.executed_results[-1] is gates["a"].result
    assert result.terminating_occurrence is profile.gates[1]
    assert result.failure is None


@pytest.mark.parametrize(
    "exception", [RuntimeError("private detail"), ValueError("bad")]
)
def test_ordinary_failure_keeps_only_successful_prefix(exception: Exception) -> None:
    profile, gates, calls = setup()
    gates["a"].action = Mock(side_effect=exception)
    result = RadarPipeline(profile, gates).evaluate(context())
    assert calls == ["z", "a"]
    gates["a"].action.assert_called_once()
    assert result.outcome is RadarPipelineOutcome.FAILED
    assert result.executed_results == (gates["z"].result,)
    assert result.terminating_occurrence is profile.gates[1]
    assert result.failure == RadarPipelineFailure(
        profile.gates[1], RadarPipelineFailureCategory.GATE_EXCEPTION
    )
    assert str(exception) not in repr(result)


@pytest.mark.parametrize(
    "exception", [KeyboardInterrupt(), SystemExit(), BaseException()]
)
def test_process_control_propagates(exception: BaseException) -> None:
    profile, gates, calls = setup()
    gates["a"].action = Mock(side_effect=exception)
    with pytest.raises(type(exception)) as caught:
        RadarPipeline(profile, gates).evaluate(context())
    assert caught.value is exception
    assert calls == ["z", "a"]


@pytest.mark.parametrize("disposition", [PASS, DROP, ATTENTION])
def test_real_lazy_fact_cost_avoidance(disposition: RadarGateDisposition) -> None:
    profile, gates, calls = setup()
    a, b, unused = (RadarFactKey(name, int) for name in ("a", "b", "unused"))
    events: list[str] = []

    def load_a() -> int:
        events.append("load_a")
        return 1

    def load_b() -> int:
        events.append("load_b")
        return 2

    loader_a, loader_b, loader_unused = (
        Mock(side_effect=load_a),
        Mock(side_effect=load_b),
        Mock(),
    )
    ctx = RadarEvaluationContext(
        INSTRUMENT,
        AS_OF,
        {
            a: loader_a,
            b: loader_b,
            unused: loader_unused,
        },
    )

    def request_a(ctx: RadarEvaluationContext) -> None:
        events.append("gate_a")
        assert ctx.get_fact(a) == ctx.get_fact(a) == 1

    def request_b(ctx: RadarEvaluationContext) -> None:
        events.append("gate_b")
        assert ctx.get_fact(b) == 2

    gates["z"].action = request_a
    gates["z"].result = RadarGateResult(profile.gates[0], disposition, "decision")
    gates["a"].action = request_b
    gates["m"].action = lambda ctx: ctx.get_fact(a) and None
    pipeline = RadarPipeline(profile, gates)
    assert events == []
    result = pipeline.evaluate(ctx)
    loader_a.assert_called_once_with()
    loader_unused.assert_not_called()
    if disposition is PASS:
        assert result.outcome is RadarPipelineOutcome.SELECTED
        loader_b.assert_called_once_with()
        assert events == ["gate_a", "load_a", "gate_b", "load_b"]
        assert calls == ["z", "a", "m"]
    else:
        loader_b.assert_not_called()
        assert events == ["gate_a", "load_a"]
        assert calls == ["z"]


@pytest.mark.parametrize(
    "defect",
    ["missing", "extra", "identity", "not_callable", "absent", "wrong_identity_type"],
)
def test_invalid_wiring_rejected_before_any_execution(defect: str) -> None:
    profile, gates, calls = setup()
    bindings: dict[str, Any] = dict(gates)
    if defect == "missing":
        del bindings["m"]
    elif defect == "extra":
        bindings["extra"] = gates["m"]
    elif defect == "identity":
        gates["m"].identity = RadarGateIdentity("other", "1", "test/v1")
    elif defect == "not_callable":
        bindings["m"].evaluate = None
    elif defect == "wrong_identity_type":
        bindings["m"].identity = "fake"
    else:
        bindings["m"] = object()
    with pytest.raises(RadarPipelineError):
        RadarPipeline(profile, bindings)
    assert calls == []


def test_mapping_is_detached() -> None:
    profile, gates, calls = setup()
    supplied = dict(gates)
    pipeline = RadarPipeline(profile, supplied)
    supplied.clear()
    supplied["extra"] = gates["m"]
    assert pipeline.evaluate(context()).outcome is RadarPipelineOutcome.SELECTED
    assert calls == ["z", "a", "m"]


@pytest.mark.parametrize("defect", ["previous", "later", "definition", "not_result"])
def test_result_correspondence_failure(defect: str) -> None:
    profile, gates, calls = setup()
    wrong: Any
    if defect == "not_result":
        wrong = None
    else:
        occurrence = {
            "previous": profile.gates[0],
            "later": profile.gates[2],
            "definition": RadarGateOccurrence(
                "a", RadarGateIdentity("other", "1", "v1")
            ),
        }[defect]
        wrong = RadarGateResult(occurrence, DROP, "wrong")
    gates["a"].result = wrong
    result = RadarPipeline(profile, gates).evaluate(context())
    assert result.outcome is RadarPipelineOutcome.FAILED
    assert result.failure == RadarPipelineFailure(
        profile.gates[1], RadarPipelineFailureCategory.INVALID_RESULT
    )
    assert result.executed_results == (gates["z"].result,)
    assert calls == ["z", "a"]


@pytest.mark.parametrize("when", ["before_run", "before_step", "during_step"])
def test_identity_drift_fails(when: str) -> None:
    profile, gates, calls = setup()
    pipeline = RadarPipeline(profile, gates)

    def drift(ctx: RadarEvaluationContext) -> None:
        gates["a"].identity = RadarGateIdentity("changed", "2", "v1")

    if when == "before_run":
        drift(context())
    else:
        gates["z" if when == "before_step" else "a"].action = drift
    result = pipeline.evaluate(context())
    assert result.outcome is RadarPipelineOutcome.FAILED
    assert result.failure == RadarPipelineFailure(
        profile.gates[1], RadarPipelineFailureCategory.IDENTITY_MISMATCH
    )
    assert result.executed_results == (gates["z"].result,)
    assert calls == (["z", "a"] if when == "during_step" else ["z"])


def test_result_deep_immutability_and_narrow_surface() -> None:
    profile, gates, _ = setup()
    result = RadarPipeline(profile, gates).evaluate(context())
    supplied: Any = list(result.executed_results)
    detached = replace(result, executed_results=supplied)
    supplied.clear()
    assert detached.executed_results == result.executed_results
    for obj, name, value in (
        (result, "profile", None),
        (result, "executed_results", ()),
        (profile, "gates", ()),
        (result.executed_results[0], "disposition", DROP),
        (result.instrument, "instrument_id", "other"),
    ):
        with pytest.raises(FrozenInstanceError):
            setattr(obj, name, value)
    with pytest.raises(AttributeError):
        result.outcome = RadarPipelineOutcome.FAILED  # type: ignore[misc]
    with pytest.raises(TypeError):
        profile.gates[0].gate_identity.configuration["nested"] = ()  # type: ignore[index]
    assert profile.gates[0].gate_identity.configuration["nested"] == (1,)
    assert type(result.executed_results) is tuple
    assert {field.name for field in fields(result)} == {
        "profile",
        "instrument",
        "as_of",
        "executed_results",
        "failure",
    }
    assert {name for name in dir(result) if not name.startswith("_")} == {
        "profile",
        "instrument",
        "as_of",
        "executed_results",
        "failure",
        "outcome",
        "terminating_occurrence",
    }


@pytest.mark.parametrize(
    "defect",
    [
        "empty",
        "partial",
        "reordered",
        "past_drop",
        "failure_after_drop",
        "wrong_failure",
        "failure_after_complete",
    ],
)
def test_result_rejects_contradictory_audit_records(defect: str) -> None:
    profile, gates, _ = setup()
    results = [gate.result for gate in gates.values()]
    failure = None
    if defect in ("empty", "partial"):
        results = results[: 0 if defect == "empty" else 1]
    elif defect == "reordered":
        results.reverse()
    elif defect in ("past_drop", "failure_after_drop"):
        results[0] = replace(results[0], disposition=DROP)
        if defect == "failure_after_drop":
            results = results[:1]
            failure = RadarPipelineFailure(
                profile.gates[1], RadarPipelineFailureCategory.GATE_EXCEPTION
            )
    else:
        failure = RadarPipelineFailure(
            profile.gates[0], RadarPipelineFailureCategory.GATE_EXCEPTION
        )
        if defect == "wrong_failure":
            results = results[:1]
    with pytest.raises(ValueError):
        RadarPipelineResult(profile, INSTRUMENT, AS_OF, tuple(results), failure)


@pytest.mark.parametrize("position", [0, 2])
def test_failure_at_prefix_boundaries(position: int) -> None:
    profile, gates, calls = setup()
    step = profile.gates[position]
    gates[step.occurrence_id].action = Mock(side_effect=RuntimeError())
    result = RadarPipeline(profile, gates).evaluate(context())
    assert result.outcome is RadarPipelineOutcome.FAILED
    assert result.terminating_occurrence is step
    assert (
        tuple(r.occurrence for r in result.executed_results) == profile.gates[:position]
    )
    assert calls == [s.occurrence_id for s in profile.gates[: position + 1]]
    assert result.failure is not None
    with pytest.raises(FrozenInstanceError):
        result.failure.category = RadarPipelineFailureCategory.INVALID_RESULT  # type: ignore[misc]


@pytest.mark.parametrize("disposition", [DROP, ATTENTION])
def test_identity_drift_overrides_returned_termination(
    disposition: RadarGateDisposition,
) -> None:
    profile, gates, calls = setup()
    gates["a"].result = RadarGateResult(profile.gates[1], disposition, "stop")

    def drift(ctx: RadarEvaluationContext) -> None:
        gates["a"].identity = RadarGateIdentity("changed", "1", "v1")

    gates["a"].action = drift
    result = RadarPipeline(profile, gates).evaluate(context())
    assert result.outcome is RadarPipelineOutcome.FAILED
    assert result.executed_results == (gates["z"].result,)
    assert calls == ["z", "a"]


def test_identity_access_exception_is_owned_wiring_error() -> None:
    profile, gates, calls = setup()

    class BrokenIdentity:
        @property
        def identity(self) -> RadarGateIdentity:
            raise RuntimeError("cannot read identity")

        def evaluate(self, ctx: RadarEvaluationContext) -> RadarGateResult:
            pytest.fail("invalid wiring must not execute")

    bindings: dict[str, Any] = dict(gates)
    bindings["m"] = BrokenIdentity()
    with pytest.raises(RadarPipelineError, match="cannot inspect"):
        RadarPipeline(profile, bindings)
    assert calls == []
