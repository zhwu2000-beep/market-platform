"""FAST PURE / LOCAL APPLICATION coverage of approved runtime wiring."""

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from types import SimpleNamespace
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
from market_platform.radar.pipeline import RadarPipeline
from market_platform.radar.resolver import (
    RadarGateFactoryBinding,
    RadarGateImplementationKey,
    RadarGateResolver,
    RadarResolutionCategory,
    RadarResolutionError,
)

IDENTITY = RadarGateIdentity("fake", "1", "test/v1")
KEY = RadarGateImplementationKey("fake", "1", "test/v1")


class FakeGate:
    def __init__(self, occurrence: RadarGateOccurrence) -> None:
        self.identity = occurrence.gate_identity
        self.occurrence = occurrence
        self.calls = 0
        self.disposition = RadarGateDisposition(
            self.identity.configuration.get("disposition", "PASS")
        )

    def evaluate(self, context: RadarEvaluationContext) -> RadarGateResult:
        self.calls += 1
        return RadarGateResult(self.occurrence, self.disposition, "fake_result")


def profile(*identities: RadarGateIdentity) -> RadarProfile:
    return RadarProfile(
        "test",
        "1",
        "test/v1",
        tuple(
            RadarGateOccurrence(name, identity)
            for name, identity in zip(("z", "a", "m"), identities, strict=False)
        ),
    )


def assert_category(
    caught: pytest.ExceptionInfo[RadarResolutionError],
    category: RadarResolutionCategory,
) -> None:
    assert caught.value.category is category
    assert str(caught.value) == category.value


def test_exact_resolution_and_immutable_wiring_values() -> None:
    factory = Mock(side_effect=FakeGate)
    binding = RadarGateFactoryBinding(KEY, factory)
    selected = profile(IDENTITY)
    gate = RadarGateResolver([binding]).resolve_profile(selected)["z"]
    assert gate.identity is IDENTITY
    factory.assert_called_once_with(selected.gates[0])
    assert factory.call_args.args[0] is selected.gates[0]
    assert gate.calls == 0
    for obj, attr in ((KEY, "gate_id"), (binding, "factory")):
        with pytest.raises(FrozenInstanceError):
            setattr(obj, attr, None)


@pytest.mark.parametrize(
    "change",
    [
        {"gate_id": "unknown"},
        {"behavioral_revision": "2"},
        {"configuration_schema": "test/v2"},
    ],
)
def test_unsupported_exact_key_has_no_fallback(change: dict[str, str]) -> None:
    factory = Mock(side_effect=FakeGate)
    resolver = RadarGateResolver([RadarGateFactoryBinding(KEY, factory)])
    with pytest.raises(RadarResolutionError) as caught:
        resolver.resolve_profile(profile(replace(IDENTITY, **change)))
    assert_category(caught, RadarResolutionCategory.UNSUPPORTED_IMPLEMENTATION)
    factory.assert_not_called()


@pytest.mark.parametrize("reverse", [False, True])
def test_duplicate_registration_rejected_in_any_order(reverse: bool) -> None:
    factories = [Mock(), Mock()]
    bindings = [RadarGateFactoryBinding(KEY, factory) for factory in factories]
    if reverse:
        bindings.reverse()
    with pytest.raises(RadarResolutionError) as caught:
        RadarGateResolver(bindings)
    assert_category(caught, RadarResolutionCategory.INVALID_WIRING)
    for factory in factories:
        factory.assert_not_called()


@pytest.mark.parametrize(
    "field", ["gate_id", "behavioral_revision", "configuration_schema"]
)
@pytest.mark.parametrize("value", ["", " ", None, 1])
def test_invalid_key(field: str, value: Any) -> None:
    with pytest.raises(RadarResolutionError) as caught:
        replace(KEY, **{field: value})
    assert_category(caught, RadarResolutionCategory.INVALID_WIRING)


@pytest.mark.parametrize("defect", ["key", "factory", "binding"])
def test_invalid_wiring(defect: str) -> None:
    with pytest.raises(RadarResolutionError) as caught:
        if defect == "key":
            RadarGateFactoryBinding("fake", FakeGate)  # type: ignore[arg-type]
        elif defect == "factory":
            RadarGateFactoryBinding(KEY, "module.Factory")  # type: ignore[arg-type]
        else:
            RadarGateResolver([object()])  # type: ignore[list-item]
    assert_category(caught, RadarResolutionCategory.INVALID_WIRING)


def test_registration_detached_from_caller_collection() -> None:
    factory = Mock(side_effect=FakeGate)
    supplied = [RadarGateFactoryBinding(KEY, factory)]
    resolver = RadarGateResolver(supplied)
    supplied.clear()
    replacement = Mock()
    supplied.append(RadarGateFactoryBinding(KEY, replacement))
    assert resolver.resolve_profile(profile(IDENTITY))["z"].identity == IDENTITY
    factory.assert_called_once()
    replacement.assert_not_called()


@pytest.mark.parametrize(
    "exception", [RuntimeError("private detail"), ValueError("bad config")]
)
def test_factory_failure_is_owned_without_retry(exception: Exception) -> None:
    factory = Mock(side_effect=exception)
    with pytest.raises(RadarResolutionError) as caught:
        RadarGateResolver([RadarGateFactoryBinding(KEY, factory)]).resolve_profile(
            profile(IDENTITY)
        )
    assert_category(caught, RadarResolutionCategory.FACTORY_FAILURE)
    assert caught.value.__cause__ is exception
    assert str(exception) not in str(caught.value)
    factory.assert_called_once()


@pytest.mark.parametrize(
    "exception", [KeyboardInterrupt(), SystemExit(), BaseException()]
)
@pytest.mark.parametrize("phase", ["construction", "inspection"])
def test_base_exception_propagates(exception: BaseException, phase: str) -> None:
    class BrokenIdentity:
        @property
        def identity(self) -> RadarGateIdentity:
            raise exception

    factory = (
        Mock(side_effect=exception)
        if phase == "construction"
        else Mock(return_value=BrokenIdentity())
    )
    with pytest.raises(type(exception)) as caught:
        RadarGateResolver([RadarGateFactoryBinding(KEY, factory)]).resolve_profile(
            profile(IDENTITY)
        )
    assert caught.value is exception
    factory.assert_called_once()


@pytest.mark.parametrize(
    "defect",
    [
        "object",
        "evaluate",
        "identity_type",
        "identity_subclass",
        "gate_id",
        "behavioral_revision",
        "configuration_schema",
        "configuration",
        "inspection",
    ],
)
def test_bad_factory_output(defect: str) -> None:
    class IdentitySubclass(RadarGateIdentity):
        pass

    class BrokenIdentity:
        @property
        def identity(self) -> RadarGateIdentity:
            raise RuntimeError("private inspection detail")

    evaluate = Mock()
    output: Any = SimpleNamespace(identity=IDENTITY, evaluate=evaluate)
    if defect == "object":
        output = object()
    elif defect == "evaluate":
        output.evaluate = None
    elif defect == "identity_type":
        output.identity = "fake"
    elif defect == "identity_subclass":
        output.identity = IdentitySubclass("fake", "1", "test/v1")
    elif defect == "inspection":
        output = BrokenIdentity()
    else:
        value = {"different": True} if defect == "configuration" else "different"
        output.identity = replace(IDENTITY, **{defect: value})
    factory = Mock(return_value=output)
    with pytest.raises(RadarResolutionError) as caught:
        RadarGateResolver([RadarGateFactoryBinding(KEY, factory)]).resolve_profile(
            profile(IDENTITY)
        )
    assert_category(caught, RadarResolutionCategory.EVALUATOR_MISMATCH)
    factory.assert_called_once()
    evaluate.assert_not_called()
    assert IDENTITY.configuration == {}


def test_whole_profile_support_preflight_calls_zero_factories() -> None:
    factory = Mock(side_effect=FakeGate)
    selected = profile(IDENTITY, IDENTITY, replace(IDENTITY, gate_id="unknown"))
    with pytest.raises(RadarResolutionError) as caught:
        RadarGateResolver([RadarGateFactoryBinding(KEY, factory)]).resolve_profile(
            selected
        )
    assert_category(caught, RadarResolutionCategory.UNSUPPORTED_IMPLEMENTATION)
    factory.assert_not_called()


@pytest.mark.parametrize("reverse", [False, True])
def test_revisions_and_schemas_coexist_in_profile_order(reverse: bool) -> None:
    identities = (
        IDENTITY,
        replace(IDENTITY, behavioral_revision="2"),
        replace(IDENTITY, configuration_schema="test/v2"),
    )
    selected = profile(*identities)
    events = []

    def factory(step: RadarGateOccurrence) -> FakeGate:
        events.append(step)
        return FakeGate(step)

    bindings = [
        RadarGateFactoryBinding(
            RadarGateImplementationKey(
                i.gate_id, i.behavioral_revision, i.configuration_schema
            ),
            factory,
        )
        for i in identities
    ]
    if reverse:
        bindings.reverse()
    resolved = RadarGateResolver(bindings).resolve_profile(selected)
    assert list(resolved) == ["z", "a", "m"]
    assert tuple(events) == selected.gates
    assert tuple(g.identity for g in resolved.values()) == identities


@pytest.mark.parametrize(
    "disposition,outcome",
    [
        ("PASS", RadarPipelineOutcome.SELECTED),
        ("DROP", RadarPipelineOutcome.FILTERED),
        ("ATTENTION", RadarPipelineOutcome.ATTENTION),
    ],
)
def test_passive_configuration_repeated_occurrences_and_pipeline(
    disposition: str,
    outcome: RadarPipelineOutcome,
) -> None:
    # Strings resembling code/import selectors remain inert factory input.
    configured = replace(
        IDENTITY,
        configuration={
            "disposition": disposition,
            "inert": "module.Factory; raise RuntimeError()",
            "nested": [1, {"flag": True}],
        },
    )
    selected = profile(IDENTITY, configured, IDENTITY)
    before = selected.to_dict()
    factory = Mock(side_effect=FakeGate)
    loader = Mock(side_effect=AssertionError("must stay lazy"))
    context = RadarEvaluationContext(
        CanonicalInstrumentId("sample"),
        datetime(2026, 9, 24, tzinfo=UTC),
        {RadarFactKey("unused", int): loader},
    )
    resolved = RadarGateResolver(
        [RadarGateFactoryBinding(KEY, factory)]
    ).resolve_profile(selected)
    assert list(resolved) == ["z", "a", "m"]
    assert selected.to_dict() == before
    assert factory.call_count == 3
    assert [call.args[0] for call in factory.call_args_list] == list(selected.gates)
    assert resolved["z"] is not resolved["m"]
    for step, gate in zip(selected.gates, resolved.values(), strict=True):
        assert gate.identity is step.gate_identity
        assert gate.calls == 0
    assert resolved["a"].identity.configuration is configured.configuration
    assert IDENTITY.fingerprint != configured.fingerprint
    loader.assert_not_called()
    result = RadarPipeline(selected, resolved).evaluate(context)
    assert result.outcome is outcome
    count = 3 if disposition == "PASS" else 2
    assert (
        tuple(r.occurrence for r in result.executed_results) == selected.gates[:count]
    )
    assert [gate.calls for gate in resolved.values()] == (
        [1, 1, 1] if count == 3 else [1, 1, 0]
    )
    loader.assert_not_called()
