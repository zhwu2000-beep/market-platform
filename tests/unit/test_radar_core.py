"""FAST PURE Radar value contracts; no calendar, provider or governed setup."""

from collections.abc import Mapping
from dataclasses import FrozenInstanceError, fields, replace
from typing import get_protocol_members

import pytest

from market_platform._fingerprint import canonical_fingerprint
from market_platform.radar.core import (
    RADAR_GATE_IDENTITY_SCHEMA,
    RADAR_PROFILE_SCHEMA,
    RadarGate,
    RadarGateDisposition,
    RadarGateIdentity,
    RadarGateOccurrence,
    RadarGateResult,
    RadarPipelineOutcome,
    RadarProfile,
)


def gate(configuration: Mapping[str, object] | None = None) -> RadarGateIdentity:
    return RadarGateIdentity("sample", "1.0.0", "sample/v1", configuration or {})


def profile() -> RadarProfile:
    return RadarProfile(
        "sample",
        "1.0.0",
        "sample_profile/v1",
        (RadarGateOccurrence("first", gate()), RadarGateOccurrence("second", gate())),
    )


def test_enum_separation() -> None:
    assert {item.value for item in RadarGateDisposition} == {
        "PASS",
        "DROP",
        "ATTENTION",
    }
    assert {item.value for item in RadarPipelineOutcome} == {
        "SELECTED",
        "FILTERED",
        "ATTENTION",
        "FAILED",
    }
    assert not hasattr(RadarGateDisposition, "FAILED")
    assert RadarGateDisposition is not RadarPipelineOutcome


def test_gate_reconstruction_and_mapping_order() -> None:
    first = gate({"b": [None, True, 3, 1.5], "a": {"y": 2, "x": "text"}})
    second = gate({"a": {"x": "text", "y": 2}, "b": (None, True, 3, 1.5)})
    assert first == second
    assert first.fingerprint == second.fingerprint
    assert first.to_dict() == second.to_dict()
    assert first.schema_version == RADAR_GATE_IDENTITY_SCHEMA
    assert gate({"zero": -0.0}).fingerprint == gate({"zero": 0.0}).fingerprint


@pytest.mark.parametrize(
    "change",
    [
        {"gate_id": "other"},
        {"behavioral_revision": "2.0.0"},
        {"configuration_schema": "sample/v2"},
        {"configuration": {"threshold": 2}},
    ],
)
def test_gate_identity_changes(change: dict[str, object]) -> None:
    original = gate()
    assert replace(original, **change).fingerprint != original.fingerprint


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_configuration(value: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        gate({"nested": [{"number": value}]})
    with pytest.raises(ValueError, match="finite"):
        replace(profile(), configuration={"number": value})


@pytest.mark.parametrize("value", [lambda: None, object, object(), b"bytes", {1, 2}])
def test_executable_and_non_json_configuration_rejected(value: object) -> None:
    with pytest.raises(TypeError, match="JSON"):
        gate({"nested": [value]})
    with pytest.raises(TypeError, match="JSON"):
        replace(profile(), configuration={"nested": [value]})


def test_strings_are_passive_data() -> None:
    identity = gate({"label": "some.module.Class"})
    assert identity.configuration["label"] == "some.module.Class"
    assert not hasattr(identity, "resolve")


@pytest.mark.parametrize("key", ["", "  ", 1])
def test_invalid_mapping_keys(key: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        gate({key: 1})


def test_cycles_rejected_and_shared_values_allowed() -> None:
    cyclic: list[object] = []
    cyclic.append(cyclic)
    with pytest.raises(ValueError, match="cycles"):
        gate({"cycle": cyclic})
    mapping: dict[str, object] = {}
    mapping["self"] = mapping
    with pytest.raises(ValueError, match="cycles"):
        gate(mapping)
    shared = [1]
    assert gate({"a": shared, "b": shared}) == gate({"a": [1], "b": [1]})


@pytest.mark.parametrize("owner", ["gate", "profile"])
def test_deep_configuration_immutability(owner: str) -> None:
    nested = {"threshold": 3}
    sequence = [nested]
    source = {"items": sequence}
    value = (
        gate(source) if owner == "gate" else replace(profile(), configuration=source)
    )
    before = value.to_dict()
    fingerprint = value.fingerprint
    nested["threshold"] = 99
    sequence.append({"threshold": 4})
    source["other"] = []
    assert value.to_dict() == before
    assert value.fingerprint == fingerprint
    with pytest.raises(TypeError):
        value.configuration["new"] = 1
    with pytest.raises(TypeError):
        value.configuration["items"][0]["threshold"] = 5
    with pytest.raises(TypeError):
        value.configuration["items"][0] = {}
    with pytest.raises(FrozenInstanceError):
        value.configuration = {}
    exported = value.to_dict()
    exported["configuration"]["items"][0]["threshold"] = 100
    assert value.to_dict() == before


def test_occurrences_and_ordered_profile() -> None:
    original = profile()
    reconstructed = profile()
    assert original == reconstructed
    assert original.fingerprint == reconstructed.fingerprint
    assert original.schema_version == RADAR_PROFILE_SCHEMA
    first, second = original.gates
    assert first.gate_identity == second.gate_identity
    assert first != second
    assert first == RadarGateOccurrence("first", gate())
    assert replace(original, gates=(second, first)).fingerprint != original.fingerprint
    changes = (
        replace(first, occurrence_id="renamed"),
        replace(first, gate_identity=gate({"threshold": 1})),
    )
    for changed in changes:
        assert (
            replace(original, gates=(changed, second)).fingerprint
            != original.fingerprint
        )
    serialized = original.to_dict()
    assert [step["occurrence_id"] for step in serialized["gates"]] == [
        "first",
        "second",
    ]
    serialized["gates"][0]["gate_identity"]["configuration"]["new"] = 1
    assert original == reconstructed


@pytest.mark.parametrize(
    "change",
    [
        {"profile_id": "other"},
        {"behavioral_revision": "2.0.0"},
        {"configuration_schema": "profile/v2"},
        {"configuration": {"threshold": 1}},
    ],
)
def test_profile_identity_changes(change: dict[str, object]) -> None:
    original = profile()
    assert replace(original, **change).fingerprint != original.fingerprint


def test_profile_mapping_order_and_fingerprint_correspondence() -> None:
    first = replace(profile(), configuration={"a": 1, "b": [2]})
    second = replace(profile(), configuration={"b": (2,), "a": 1})
    assert first.fingerprint == second.fingerprint
    for value in (first, gate({"a": 1})):
        payload = value.to_dict()
        fingerprint = payload.pop("fingerprint")
        assert canonical_fingerprint(payload) == fingerprint


def test_duplicate_occurrence_rejected_even_with_different_definition() -> None:
    first = profile().gates[0]
    for other in (first, replace(first, gate_identity=gate({"x": 1}))):
        with pytest.raises(ValueError, match="unique"):
            replace(profile(), gates=(first, other))


def test_profile_sequence_detached_and_frozen() -> None:
    source = list(profile().gates)
    value = replace(profile(), gates=source)
    source.reverse()
    source.clear()
    assert value == profile()
    with pytest.raises(FrozenInstanceError):
        value.gates = ()
    with pytest.raises(FrozenInstanceError):
        value.gates[0].occurrence_id = "changed"


@pytest.mark.parametrize(
    "name", ["gate_id", "behavioral_revision", "configuration_schema"]
)
@pytest.mark.parametrize("value", ["", "   ", None])
def test_gate_required_text(name: str, value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        replace(gate(), **{name: value})


@pytest.mark.parametrize(
    "name", ["profile_id", "behavioral_revision", "configuration_schema"]
)
@pytest.mark.parametrize("value", ["", "   ", None])
def test_profile_required_text(name: str, value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        replace(profile(), **{name: value})


@pytest.mark.parametrize("gates", [(), {}, "steps", (gate(),)])
def test_invalid_profile_gates(gates: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        replace(profile(), gates=gates)


def test_invalid_occurrence() -> None:
    with pytest.raises(ValueError):
        RadarGateOccurrence(" ", gate())
    with pytest.raises(TypeError):
        RadarGateOccurrence("step", object())


@pytest.mark.parametrize("disposition", list(RadarGateDisposition))
def test_result_content(disposition: RadarGateDisposition) -> None:
    occurrence = profile().gates[0]
    result = RadarGateResult(occurrence, disposition, "condition_checked", "Diagnostic")
    assert result == RadarGateResult(
        occurrence, disposition, "condition_checked", "Diagnostic"
    )
    assert result.disposition is disposition
    assert result.occurrence.gate_identity == gate()
    assert replace(result, detail="Other diagnostic").reason_code == result.reason_code
    assert {item.name for item in fields(result)} == {
        "occurrence",
        "disposition",
        "reason_code",
        "detail",
    }
    with pytest.raises(FrozenInstanceError):
        result.reason_code = "changed"


@pytest.mark.parametrize(
    "change",
    [
        {"reason_code": ""},
        {"reason_code": "free form message"},
        {"reason_code": "x" * 129},
        {"reason_code": None},
        {"disposition": "PASS"},
        {"disposition": RadarPipelineOutcome.ATTENTION},
        {"occurrence": gate()},
        {"detail": 3},
        {"detail": "x" * 1025},
    ],
)
def test_invalid_result(change: dict[str, object]) -> None:
    result = RadarGateResult(profile().gates[0], RadarGateDisposition.PASS, "checked")
    with pytest.raises((TypeError, ValueError)):
        replace(result, **change)


def test_result_detail_bound() -> None:
    result = RadarGateResult(profile().gates[0], RadarGateDisposition.PASS, "checked")
    assert result.detail is None
    assert len(replace(result, detail="x" * 1024).detail) == 1024


def test_protocol_requires_only_identity_and_evaluation() -> None:
    assert get_protocol_members(RadarGate) == {"identity", "evaluate"}

    class SuppliedFactGate:
        @property
        def identity(self) -> RadarGateIdentity:
            return gate()

        def evaluate(self, context: bool) -> RadarGateResult:
            return RadarGateResult(
                RadarGateOccurrence("step", self.identity),
                RadarGateDisposition.PASS if context else RadarGateDisposition.DROP,
                "supplied_fact",
            )

    evaluator: RadarGate[bool] = SuppliedFactGate()
    assert evaluator.identity == gate()
    assert evaluator.evaluate(True).disposition is RadarGateDisposition.PASS
    assert evaluator.evaluate(False).disposition is RadarGateDisposition.DROP
