from __future__ import annotations

import ast
import inspect
import json
import subprocess
from contextlib import ExitStack
from copy import copy
from dataclasses import FrozenInstanceError, fields, is_dataclass
from datetime import UTC, datetime, timedelta, timezone
from enum import Enum, IntEnum, StrEnum
from itertools import product
from pathlib import Path
from threading import Lock
from types import SimpleNamespace

import pytest

from market_platform._fingerprint import canonical_fingerprint
from market_platform.application import (
    polygon_completed_daily_production_assessment as assessment,
)
from market_platform.application import (
    polygon_completed_daily_production_interpretation as interpretation,
)
from market_platform.application import (
    polygon_completed_daily_production_qualification as qualification,
)
from market_platform.application import (
    polygon_completed_daily_production_strategy as app,
)
from market_platform.application import (
    polygon_completed_daily_production_technical as technical,
)
from market_platform.instruments.identity import CanonicalInstrumentId
from market_platform.research import governed_daily_technical_strategy as domain

Result = app.PolygonCompletedDailyStrategyResult
Service = app.PolygonCompletedDailyProductionStrategyApplicationService
Publisher = assessment.PolygonCompletedDailyProductionAssessmentApplicationService
Refused = app.PolygonCompletedDailyStrategyRefused
R = app.PolygonCompletedDailyStrategyRefusalReason
TIME = datetime(2026, 1, 2, tzinfo=UTC)
FP = "sha256:" + "a" * 64
PREFIX = "polygon_completed_daily_strategy"
NAMESPACE = PREFIX + "_history:" + "1" * 32
RESULT_FIELDS = (
    "strategy",
    "assessment_available_at",
    "execution_id",
    "history_namespace_id",
    "history_sequence",
    "execution_started_at",
    "execution_completed_at",
    "available_at",
    "fingerprint",
)
TIME_FIELDS = (
    "assessment_available_at",
    "execution_started_at",
    "execution_completed_at",
    "available_at",
)
CONSTANTS = {
    "schema_version": "polygon_completed_daily_strategy_result/v1",
    "operation": (
        "production.polygon_completed_daily.daily_technical_strategy.application"
    ),
    "operation_version": "1.0.0",
    "executor": (
        "market_platform.application/polygon_completed_daily_production_strategy/v1"
    ),
}


class String(str):
    pass


class Integer(int):
    pass


class Float(float):
    pass


class Bytes(bytes):
    pass


class TextEnum(StrEnum):
    TEMPORAL = "temporal_failure"


class NumberEnum(IntEnum):
    ONE = 1


def content():
    # Retained structural value only; no source authentication or derivation.
    return domain.GovernedDailyTechnicalStrategy(
        source_assessment_occurrence=domain.PolygonCompletedDailyStrategyRequest(
            artifact_reference=app.GovernedTechnicalArtifactReference(
                artifact_id="test:detached",
                artifact_version="1.0.0",
                artifact_fingerprint=FP,
                information_class="source_observation",
                authority="external_origin",
            ),
            assessment_history_namespace_id="polygon_completed_daily_assessment_history:"
            + "2" * 32,
            assessment_history_sequence=1,
            assessment_execution_id="polygon_completed_daily_assessment:" + "3" * 32,
            assessment_fingerprint=FP,
        ),
        source_assessment_content_fingerprint="sha256:" + "b" * 64,
        source_interpretation_content_fingerprint="sha256:" + "c" * 64,
        canonical_instrument_id=CanonicalInstrumentId("us-aapl"),
        analysis_as_of=TIME,
        strategy_policy_identity=domain.GovernedDailyTechnicalStrategyPolicyIdentity(),
        mode="no_active_strategy",
        rule_code="caution_no_active_strategy",
    )


def result(**changes):
    values = (
        dict(
            strategy=content(),
            assessment_available_at=TIME,
            execution_id=PREFIX + ":" + "4" * 32,
            history_namespace_id=NAMESPACE,
            history_sequence=1,
            execution_started_at=TIME,
            execution_completed_at=TIME,
            available_at=TIME,
        )
        | changes
    )
    value = object.__new__(Result)
    for key, item in values.items():
        object.__setattr__(value, key, item)
    object.__setattr__(value, "fingerprint", canonical_fingerprint(value._payload()))
    return value


def refingerprint(projection):
    projection["fingerprint"] = canonical_fingerprint(
        {key: value for key, value in projection.items() if key != "fingerprint"}
    )


def graph(value):
    yield value
    if is_dataclass(value):
        for field in fields(value):
            yield from graph(getattr(value, field.name))
    elif type(value) is dict:
        for key, item in value.items():
            yield from graph(key)
            yield from graph(item)
    elif type(value) in (tuple, list):
        for item in value:
            yield from graph(item)
    elif isinstance(value, BaseException):
        yield from graph(value.args)
        yield from graph(vars(value))


def mutable_ids(value):
    return {
        id(item)
        for item in graph(value)
        if is_dataclass(item) or type(item) in (dict, list)
    }


def forbidden(*args, **kwargs):
    pytest.fail("deferred workflow called")


def test_refusal_contract():
    reasons = {
        name: value for name, value in vars(R).items() if not name.startswith("_")
    }
    assert reasons == {
        "ASSESSMENT_UNAVAILABLE": "assessment_occurrence_unavailable",
        "HISTORY_INVALID": "history_incomplete_or_corrupt",
        "SOURCE_MISMATCH": "source_lineage_mismatch",
        "SEMANTIC_FAILED": "semantic_execution_or_correspondence_failed",
        "TEMPORAL_FAILURE": "temporal_failure",
        "PUBLICATION_FAILED": "strategy_publication_or_copy_failed",
    }
    assert not issubclass(R, Enum)
    for reason in reasons.values():
        error = Refused(reason, "exact message")
        assert type(reason) is type(error.reason) is str
        assert error.args == ("exact message",)
        assert all(not isinstance(item, Enum) for item in graph(error))


@pytest.mark.parametrize(
    "reason", ["invented", String("temporal_failure"), TextEnum.TEMPORAL, 1, None]
)
def test_refusal_rejects_reason(reason):
    with pytest.raises((TypeError, ValueError)):
        Refused(reason, "message")


@pytest.mark.parametrize("message", [String("message"), TextEnum.TEMPORAL, 1, None])
def test_refusal_rejects_message(message):
    with pytest.raises(TypeError):
        Refused(R.TEMPORAL_FAILURE, message)


def test_result_contract():
    with pytest.raises(TypeError, match="trusted execution"):
        Result()
    with pytest.raises(TypeError):
        Result(
            **{field.name: getattr(result(), field.name) for field in fields(Result)}
        )
    assert tuple(field.name for field in fields(Result)) == RESULT_FIELDS
    value = result()
    with pytest.raises(FrozenInstanceError):
        value.history_sequence = 2
    assert not hasattr(value, "__dict__")
    projection = value.to_dict()
    assert set(projection) == set(RESULT_FIELDS) | set(CONSTANTS)
    assert {key: projection[key] for key in CONSTANTS} == CONSTANTS
    assert value.fingerprint == canonical_fingerprint(value._payload())
    assert value.strategy.fingerprint != value.fingerprint
    assert value.strategy.fingerprint == canonical_fingerprint(
        value.strategy._fingerprint_payload()
    )


@pytest.mark.parametrize(
    "field,prefix",
    [("execution_id", PREFIX), ("history_namespace_id", PREFIX + "_history")],
)
@pytest.mark.parametrize("suffix", ["a" * 32, "0" * 32, "abcdef0123456789" * 2])
def test_valid_id_grammar(field, prefix, suffix):
    result(**{field: prefix + ":" + suffix}).to_dict()


@pytest.mark.parametrize("field", ["execution_id", "history_namespace_id"])
@pytest.mark.parametrize(
    "attack", ["upper", "short", "long", "prefix", "newline", "subclass", "nonstring"]
)
def test_invalid_id_grammar(field, attack):
    value = getattr(result(), field)
    value = {
        "upper": value[:-32] + "A" * 32,
        "short": value[:-1],
        "long": value + "0",
        "prefix": "wrong:" + "a" * 32,
        "newline": value + "\n",
        "subclass": String(value),
        "nonstring": 1,
    }[attack]
    item = result()
    object.__setattr__(item, field, value)
    with pytest.raises(ValueError):
        item.to_dict()


@pytest.mark.parametrize(
    "sequence", [0, -1, True, False, 1.0, Integer(1), NumberEnum.ONE, "1", None]
)
def test_invalid_sequence(sequence):
    with pytest.raises(ValueError):
        result(history_sequence=sequence).to_dict()


@pytest.mark.parametrize("field", TIME_FIELDS)
@pytest.mark.parametrize(
    "instant",
    [
        TIME.replace(tzinfo=None),
        TIME.astimezone(timezone(timedelta(hours=1))),
        TIME.replace(tzinfo=timezone(timedelta(0), "other")),
        "2026-01-02T00:00:00+00:00",
        type("DateSubclass", (datetime,), {})(2026, 1, 2, tzinfo=UTC),
    ],
)
def test_noncanonical_timestamp_objects(field, instant):
    value = result()
    object.__setattr__(value, field, instant)
    with pytest.raises(ValueError, match="canonical UTC"):
        value.to_dict()


@pytest.mark.parametrize("gaps", list(product((0, 1), repeat=3)))
def test_all_chronology_equality_boundaries(gaps):
    instants = [TIME]
    for gap in gaps:
        instants.append(instants[-1] + timedelta(seconds=gap))
    value = result(**dict(zip(TIME_FIELDS, instants, strict=True)))
    fact = app._encode_result(value)
    assert app._encode_result(app._reconstruct_result(fact)) == fact


@pytest.mark.parametrize("offsets", [(1, 0, 2, 3), (0, 2, 1, 3), (0, 1, 3, 2)])
def test_invalid_chronology(offsets):
    values = {
        key: TIME + timedelta(seconds=n)
        for key, n in zip(TIME_FIELDS, offsets, strict=True)
    }
    with pytest.raises(ValueError, match="chronology"):
        result(**values).to_dict()


@pytest.mark.parametrize("field", ["strategy", "fingerprint"])
def test_typed_result_rejects_wrong_content_or_hash(field):
    value = result()
    object.__setattr__(value, field, object() if field == "strategy" else FP)
    with pytest.raises(ValueError):
        value.to_dict()


def test_canonical_round_trip_and_fresh_graphs():
    retained = result()
    fact = app._encode_result(retained)
    assert type(fact) is bytes
    expected = retained.to_dict()
    assert fact == json.dumps(
        expected,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    assert app._decode_result(fact) == expected
    values = [
        retained,
        app._reconstruct_result(fact),
        app._reconstruct_result(fact),
        app._public_result_copy(retained),
    ]
    for index, value in enumerate(values):
        assert app._encode_result(value) == fact
        assert all(not isinstance(item, Enum) for item in graph(value))
        assert mutable_ids(value) == app._graph_ids(value)
        for other in values[:index]:
            assert not mutable_ids(value) & mutable_ids(other)
    assert (
        app._canonical_bytes({"z": "中文", "a": [True, None, 1, 1.5]})
        == '{"a":[true,null,1,1.5],"z":"中文"}'.encode()
    )


@pytest.mark.parametrize(
    "carrier", [bytearray, memoryview, Bytes, lambda b: b.decode()]
)
def test_mutable_or_subclass_byte_carriers(carrier):
    with pytest.raises(TypeError):
        app._reconstruct_result(carrier(app._encode_result(result())))


@pytest.mark.parametrize(
    "value",
    [
        String("x"),
        Integer(1),
        Float(1.0),
        TextEnum.TEMPORAL,
        NumberEnum.ONE,
        (1,),
        object(),
        {1: "x"},
        {String("x"): 1},
        type("Dict", (dict,), {})(),
        type("List", (list,), {})(),
    ],
)
def test_exact_json_scalar_container_types(value):
    with pytest.raises(TypeError):
        app._canonical_bytes({"nested": [value]})


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), -0.0])
def test_nonfinite_and_negative_zero(value):
    with pytest.raises(ValueError):
        app._canonical_bytes({"nested": [value]})


@pytest.mark.parametrize(
    "attack",
    [
        "whitespace",
        "duplicate",
        "unsorted",
        "nan",
        "inf",
        "negative_zero",
        "array_root",
        "invalid_utf8",
    ],
)
def test_invalid_byte_encodings(attack):
    fact = app._encode_result(result())
    supplied = {
        "whitespace": b" " + fact,
        "duplicate": b'{"history_sequence":1,' + fact[1:],
        "unsorted": json.dumps(result().to_dict(), separators=(",", ":")).encode(),
        "nan": fact.replace(b'"history_sequence":1', b'"history_sequence":NaN'),
        "inf": fact.replace(b'"history_sequence":1', b'"history_sequence":1e999'),
        "negative_zero": fact.replace(
            b'"history_sequence":1', b'"history_sequence":-0.0'
        ),
        "array_root": b"[]",
        "invalid_utf8": b"\xff",
    }[attack]
    with pytest.raises((TypeError, ValueError)):
        app._reconstruct_result(supplied)


PATHS = (
    (),
    ("strategy",),
    ("strategy", "source_assessment_occurrence"),
    ("strategy", "source_assessment_occurrence", "artifact_reference"),
    ("strategy", "canonical_instrument_id"),
    ("strategy", "strategy_policy_identity"),
    ("strategy", "strategy_policy_identity", "configuration"),
)


def at(value, path):
    for key in path:
        value = value[key]
    return value


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("attack", ["extra", "missing"])
def test_complete_nested_keys(path, attack):
    projection = result().to_dict()
    nested = at(projection, path)
    if attack == "extra":
        nested["extra"] = None
    elif nested:
        del nested[next(iter(nested))]
    else:
        del at(projection, path[:-1])[path[-1]]
    if "schema_version" in projection:
        refingerprint(projection)
    with pytest.raises((TypeError, ValueError, KeyError)):
        app._reconstruct_result(app._canonical_bytes(projection))


@pytest.mark.parametrize(
    "path,key",
    [
        *(((), key) for key in CONSTANTS),
        (("strategy",), "schema_version"),
        (("strategy",), "fingerprint"),
        (("strategy", "strategy_policy_identity"), "schema_version"),
        (("strategy", "strategy_policy_identity"), "fingerprint"),
        (
            ("strategy", "source_assessment_occurrence", "artifact_reference"),
            "schema_version",
        ),
        (
            ("strategy", "source_assessment_occurrence", "artifact_reference"),
            "fingerprint",
        ),
        ((), "fingerprint"),
    ],
)
def test_schema_and_hash_corruption_with_coherent_envelope(path, key):
    projection = result().to_dict()
    at(projection, path)[key] = FP if "fingerprint" in key else "wrong"
    if (path, key) != ((), "fingerprint"):
        refingerprint(projection)
    with pytest.raises(ValueError):
        app._reconstruct_result(app._canonical_bytes(projection))


@pytest.mark.parametrize(
    "path,key",
    [*(((), key) for key in TIME_FIELDS), (("strategy",), "analysis_as_of")],
)
@pytest.mark.parametrize(
    "stamp",
    [
        "2026-01-02T00:00:00Z",
        "2026-01-02 00:00:00+00:00",
        "2026-01-02T00:00:00.000000+00:00",
        "2026-01-02T00:00:00",
        "2026-01-02T01:00:00+01:00",
        1,
    ],
)
def test_invalid_serialized_timestamp(path, key, stamp):
    projection = result().to_dict()
    at(projection, path)[key] = stamp
    refingerprint(projection)
    with pytest.raises((TypeError, ValueError)):
        app._reconstruct_result(app._canonical_bytes(projection))


def test_mutation_and_coherent_refingerprinting_do_not_change_bytes():
    fact = app._encode_result(result())
    expected = app._decode_result(fact)
    one, two = app._reconstruct_result(fact), app._reconstruct_result(fact)
    content_value = one.strategy
    artifact = content_value.source_assessment_occurrence.artifact_reference
    object.__setattr__(artifact, "artifact_id", "test:changed")
    object.__setattr__(
        artifact, "fingerprint", canonical_fingerprint(artifact._fingerprint_payload())
    )
    object.__setattr__(content_value.canonical_instrument_id, "instrument_id", "other")
    object.__setattr__(content_value, "rule_code", "mixed_no_active_strategy")
    object.__setattr__(
        content_value,
        "fingerprint",
        canonical_fingerprint(content_value._fingerprint_payload()),
    )
    object.__setattr__(one, "fingerprint", canonical_fingerprint(one._payload()))
    assert app._encode_result(one) != fact
    content_value.strategy_policy_identity.configuration["corrupt"] = True
    assert fact == app._canonical_bytes(expected)
    assert two.to_dict() == expected
    assert app._reconstruct_result(fact).to_dict() == expected
    projection = two.to_dict()
    projection["strategy"]["strategy_policy_identity"]["configuration"]["bad"] = True
    assert two.to_dict() == expected


def test_copy_check_rejects_nested_alias_or_changed_copy(monkeypatch):
    retained = result()
    shallow = copy(retained)
    with pytest.raises(ValueError, match="aliases"):
        app._check_copy(shallow, retained, retained.to_dict())
    monkeypatch.setattr(app, "_reconstruct_result", lambda fact: shallow)
    with pytest.raises(ValueError):
        app._public_result_copy(retained)


def history(*, later=0):
    owner = app._StrategyHistory()
    entries = tuple(
        app._encode_result(
            result(
                history_namespace_id=owner._namespace_id,
                history_sequence=n,
                execution_id=PREFIX + ":" + f"{n:032x}",
                available_at=TIME + timedelta(seconds=later * (n - 1)),
            )
        )
        for n in (1, 2)
    )
    owner._state = (3, entries)
    return owner


def test_initial_history_and_pending_have_no_authority():
    owner = app._StrategyHistory()
    assert owner._state == (1, ())
    assert type(owner._state) is tuple and type(owner._state[0]) is int
    assert type(owner._state[1]) is tuple
    assert owner._pending is None
    owner._pending = result()
    original = owner._state
    owner._validate()
    assert owner._state is original
    assert owner._state[1] == ()


@pytest.mark.parametrize("later", [0, 1])
def test_valid_history(later):
    owner = history(later=later)
    original = owner._state
    owner._validate()
    assert owner._state is original


@pytest.mark.parametrize(
    "state",
    [
        None,
        [],
        (),
        (1,),
        (1, (), None),
        [1, ()],
        (True, ()),
        (0, ()),
        (Integer(1), ()),
        (2, ()),
        (1, []),
        (2, (b"bad",)),
        (2, (bytearray(b"bad"),)),
        type("Tuple", (tuple,), {})((1, ())),
    ],
)
def test_invalid_history_state_shape(state):
    owner = app._StrategyHistory()
    owner._state = state
    with pytest.raises((TypeError, ValueError)):
        owner._validate()
    assert owner._state is state


@pytest.mark.parametrize(
    "attack",
    [
        "missing",
        "reordered",
        "duplicate_id",
        "namespace",
        "decreasing",
        "nested",
        "bool_sequence",
        "bytes_subclass",
    ],
)
def test_invalid_committed_inventory(attack):
    owner = history()
    first, second = owner._state[1]
    data = app._decode_result(second)
    if attack == "missing":
        entries = (second,)
    elif attack == "reordered":
        entries = (second, first)
    elif attack == "bytes_subclass":
        entries = (Bytes(first), second)
    else:
        if attack == "duplicate_id":
            data["execution_id"] = app._decode_result(first)["execution_id"]
        elif attack == "namespace":
            data["history_namespace_id"] = NAMESPACE
        elif attack == "decreasing":
            earlier = app._decode_result(first)
            earlier["available_at"] = (TIME + timedelta(seconds=1)).isoformat()
            refingerprint(earlier)
            first = app._canonical_bytes(earlier)
        elif attack == "nested":
            data["strategy"]["rule_code"] = "corrupt"
        else:
            data["history_sequence"] = True
        refingerprint(data)
        entries = (first, app._canonical_bytes(data))
    owner._state = (len(entries) + 1, entries)
    original = owner._state
    with pytest.raises((TypeError, ValueError)):
        owner._validate()
    assert owner._state is original


def publisher():
    """Inert roots exercising the released upstream lock composition methods."""

    def store():
        return SimpleNamespace(_lock=Lock())

    admission = SimpleNamespace(
        _construction_service=SimpleNamespace(_history=store()),
        _validation_service=SimpleNamespace(_history=store()),
        _freshness_service=SimpleNamespace(_history=store()),
        _history=store(),
    )
    validity = SimpleNamespace(_admission_service=admission, _history=store())
    qualified = object.__new__(
        qualification.PolygonCompletedDailyProductionQualificationApplicationService
    )
    qualified._validity_service = validity
    qualified._history = store()
    bridge = SimpleNamespace(_qualification_service=qualified, _history=store())
    tech = object.__new__(
        technical.PolygonCompletedDailyProductionTechnicalApplicationService
    )
    tech._bridge_service = bridge
    tech_owner = store()
    tech._PolygonCompletedDailyProductionTechnicalApplicationService__committed = (
        SimpleNamespace(owner=tech_owner)
    )
    tech._history = store()  # This replaceable view must never choose the lock.
    source = object.__new__(
        interpretation.PolygonCompletedDailyProductionInterpretationApplicationService
    )
    source._technical_service = tech
    source._history_owner = source._history = interpretation._InterpretationHistory()
    source._namespace = source._history_owner._namespace_id
    source._committed = source._history_owner._state
    value = Publisher(source)
    locks = [
        admission._construction_service._history._lock,
        admission._validation_service._history._lock,
        admission._freshness_service._history._lock,
        admission._history._lock,
        validity._history._lock,
        qualified._history._lock,
        bridge._history._lock,
        tech_owner._lock,
        source._history_owner._lock,
        value._history_owner._lock,
    ]
    return value, locks


class RecordingStack(ExitStack):
    def __init__(self):
        super().__init__()
        self.locks = []

    def enter_context(self, lock):
        assert lock.acquire(blocking=False), "recursive lock acquisition"
        self.locks.append(lock)
        self.callback(lock.release)


def test_exact_exports_and_no_public_workflows():
    assert app.__all__ == [
        "PolygonCompletedDailyStrategyRefusalReason",
        "PolygonCompletedDailyStrategyRefused",
        "PolygonCompletedDailyStrategyResult",
        "PolygonCompletedDailyProductionStrategyApplicationService",
    ]
    assert not [
        name
        for name, value in inspect.getmembers(Service)
        if not name.startswith("_") and callable(value)
    ]
    service = Service(publisher()[0])
    for name in ("execute", "get_result_history_as_of", "_publish", "_history"):
        assert not hasattr(service, name)
    assert tuple(field.name for field in fields(Result)) == RESULT_FIELDS


def test_constructor_exact_signature():
    signature = inspect.signature(Service)
    assert list(signature.parameters) == ["assessment_service", "execution_clock"]
    source, clock = signature.parameters.values()
    assert source.kind is clock.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert source.default is inspect.Parameter.empty
    assert clock.default is None
    assert source.annotation == (
        "assessment.PolygonCompletedDailyProductionAssessmentApplicationService"
    )
    assert clock.annotation == "Callable[[], datetime] | None"
    supplied, _ = publisher()
    assert Service(supplied, forbidden)._clock is forbidden
    assert (
        Service(assessment_service=supplied, execution_clock=forbidden)._clock
        is forbidden
    )
    with pytest.raises(TypeError):
        Service(supplied, interpretation_service=supplied._interpretation_service)


@pytest.mark.parametrize(
    "source",
    [
        None,
        object(),
        SimpleNamespace(),
        object.__new__(type("Subclass", (Publisher,), {})),
    ],
)
def test_constructor_exact_assessment_type(source):
    with pytest.raises(TypeError, match="exact trusted Assessment"):
        Service(source)


@pytest.mark.parametrize("clock", [False, 1, TIME, object()])
def test_constructor_clock_callability(clock):
    with pytest.raises(TypeError, match="callable"):
        Service(publisher()[0], clock)


def forbid_work(monkeypatch, source):
    for name in (
        "execute",
        "get_result_history_as_of",
        "_authenticate_assessment_occurrence",
        "_authenticate_assessment_inventory",
        "_revalidate_assessment_inventory",
    ):
        monkeypatch.setattr(source, name, forbidden)
    for name in (
        "execute",
        "get_result_history_as_of",
        "_authenticate_interpretation_occurrence",
    ):
        monkeypatch.setattr(source._interpretation_service, name, forbidden)
    for name in (
        "derive_governed_daily_technical_strategy",
        "validate_governed_daily_technical_strategy",
    ):
        monkeypatch.setattr(domain, name, forbidden)
    monkeypatch.setattr(domain.GovernedDailyTechnicalStrategy, "_validate", forbidden)
    monkeypatch.setattr(app, "_reconstruct_result", forbidden)
    monkeypatch.setattr(app._StrategyHistory, "_validate", forbidden)
    monkeypatch.setattr(app.a, "_utc_now", forbidden)


def test_constructor_is_lazy_and_pins_one_original_owner(monkeypatch):
    source, _ = publisher()
    forbid_work(monkeypatch, source)
    monkeypatch.setattr(source, "_lock_inputs", forbidden)
    created = []
    original = app._StrategyHistory.__init__

    def initialize(owner):
        created.append(owner)
        original(owner)

    monkeypatch.setattr(app._StrategyHistory, "__init__", initialize)
    service = Service(source)
    assert created == [service._history_owner]
    assert service._assessment_service is source
    assert service._namespace is service._history_owner._namespace_id
    assert service._committed is service._history_owner._state
    assert service._committed == (1, ())
    assert service._clock is forbidden
    assert service._history_owner._pending is None
    assert not hasattr(service, "_history")
    for name, replacement in (
        ("_history_owner", object()),
        ("_assessment_service", object()),
        ("_namespace", "other"),
    ):
        with pytest.raises(AttributeError):
            setattr(service, name, replacement)


def test_eleven_locks_once_final_without_work(monkeypatch):
    source, upstream = publisher()
    forbid_work(monkeypatch, source)
    service = Service(source, forbidden)
    calls = []
    original = source._lock_inputs

    def compose(stack):
        calls.append(source)
        return original(stack)

    monkeypatch.setattr(source, "_lock_inputs", compose)
    expected = [*upstream, service._history_owner._lock]
    state = service._committed
    with RecordingStack() as stack:
        service._lock_inputs(stack)
        assert stack.locks == expected
        assert len(stack.locks) == len(set(stack.locks)) == 11
        assert all(lock.locked() for lock in expected)
        service._check_locked_roots()
    assert calls == [source]
    assert not any(lock.locked() for lock in expected)
    assert service._committed is state is service._history_owner._state
    assert service._history_owner._pending is None


@pytest.mark.parametrize("restore", [False, True])
def test_read_only_views_cannot_redirect_lock_selection(monkeypatch, restore):
    source, upstream = publisher()
    replacement, replacement_locks = publisher()
    service = Service(source)
    owner = service._history_owner
    other_owner = app._StrategyHistory()
    monkeypatch.setattr(replacement, "_lock_inputs", forbidden)
    # Descriptor-backed views ignore same-named instance dictionary substitutions.
    vars(service)["_assessment_service"] = replacement
    vars(service)["_history_owner"] = other_owner
    assert service._assessment_service is source
    assert service._history_owner is owner
    with RecordingStack() as stack:
        service._lock_inputs(stack)
        if restore:
            vars(service).pop("_assessment_service")
            vars(service).pop("_history_owner")
        service._check_locked_roots()
        assert stack.locks == [*upstream, owner._lock]
        assert not any(lock.locked() for lock in replacement_locks)
        assert not other_owner._lock.locked()


@pytest.mark.parametrize(
    "attack",
    [
        "owner",
        "namespace",
        "owner_namespace",
        "lock",
        "assessment_publisher",
        "assessment_owner",
        "assessment_namespace",
        "assessment_owner_namespace",
        "assessment_lock",
        "assessment_root",
        "interpretation_publisher",
        "interpretation_owner",
        "interpretation_namespace",
        "interpretation_lock",
    ],
)
def test_root_replacement_cannot_select_locks(attack):
    source, upstream = publisher()
    service = Service(source)
    state = service._committed
    owner = service._history_owner
    root_prefix = "_PolygonCompletedDailyProductionStrategyApplicationService__"
    source_prefix = "_PolygonCompletedDailyProductionAssessmentApplicationService__"
    interpretation_source = source._interpretation_service
    changes = {
        "owner": (service, root_prefix + "history_owner", app._StrategyHistory()),
        "namespace": (
            service,
            root_prefix + "namespace",
            (service._namespace + " ")[:-1],
        ),
        "owner_namespace": (owner, "_namespace_id", (service._namespace + " ")[:-1]),
        "lock": (owner, "_lock", Lock()),
        "assessment_publisher": (
            service,
            root_prefix + "assessment_service",
            publisher()[0],
        ),
        "assessment_owner": (
            source,
            source_prefix + "history_owner",
            assessment._AssessmentHistory(),
        ),
        "assessment_namespace": (
            source,
            source_prefix + "namespace",
            (source._namespace + " ")[:-1],
        ),
        "assessment_owner_namespace": (
            source._history_owner,
            "_namespace_id",
            (source._namespace + " ")[:-1],
        ),
        "assessment_lock": (source._history_owner, "_lock", Lock()),
        "assessment_root": (
            source,
            source_prefix + "consumption_roots",
            tuple(list(vars(source)[source_prefix + "consumption_roots"])),
        ),
        "interpretation_publisher": (
            source,
            source_prefix + "interpretation_service",
            copy(interpretation_source),
        ),
        "interpretation_owner": (
            interpretation_source,
            "_history_owner",
            interpretation._InterpretationHistory(),
        ),
        "interpretation_namespace": (
            interpretation_source,
            "_namespace",
            (interpretation_source._namespace + " ")[:-1],
        ),
        "interpretation_lock": (interpretation_source._history_owner, "_lock", Lock()),
    }
    target, name, value = changes[attack]
    assert value is not getattr(target, name)
    setattr(target, name, value)
    with RecordingStack() as stack:
        with pytest.raises(ValueError, match="roots"):
            service._lock_inputs(stack)
        assert stack.locks == []
    assert service._committed is state
    assert not any(lock.locked() for lock in upstream)


@pytest.mark.parametrize(
    "attack", ["state", "pending", "assessment_state", "assessment_pending"]
)
def test_state_and_pending_do_not_grant_authority(attack):
    source, _ = publisher()
    service = Service(source)
    owner = service._history_owner
    original = service._committed
    with RecordingStack() as stack:
        service._lock_inputs(stack)
        target = source._history_owner if attack.startswith("assessment_") else owner
        if attack.endswith("state"):
            replacement = tuple(list(target._state))
            assert replacement == target._state and replacement is not target._state
            target._state = replacement
        else:
            target._pending = object()
        with pytest.raises(ValueError):
            service._check_locked_roots()
    assert service._committed is original


@pytest.mark.parametrize("phase", ["before", "during"])
@pytest.mark.parametrize("restore", [False, True])
def test_strategy_root_swap_cannot_redirect_acquisition(monkeypatch, phase, restore):
    source, upstream = publisher()
    service = Service(source)
    original = service._history_owner
    other = app._StrategyHistory()
    key = "_PolygonCompletedDailyProductionStrategyApplicationService__history_owner"
    compose = source._lock_inputs

    def swap(stack):
        setattr(service, key, other)
        compose(stack)
        if restore:
            setattr(service, key, original)

    if phase == "before":
        setattr(service, key, other)
    else:
        monkeypatch.setattr(source, "_lock_inputs", swap)
    with RecordingStack() as stack:
        if phase == "during" and restore:
            # The replacement was never selected: only the original pinned lock ran.
            service._lock_inputs(stack)
            assert stack.locks == [*upstream, original._lock]
        else:
            with pytest.raises(ValueError):
                service._lock_inputs(stack)
        assert other._lock not in stack.locks
        assert not other._lock.locked()


@pytest.mark.parametrize(
    "attack", ["assessment_owner", "interpretation_publisher", "interpretation_owner"]
)
def test_upstream_lock_selection_swap_back_fails(monkeypatch, attack):
    source, _ = publisher()
    service = Service(source)
    prefix = "_PolygonCompletedDailyProductionAssessmentApplicationService__"
    source_publisher = source._interpretation_service
    if attack == "assessment_owner":
        target, name, replacement = (
            source,
            prefix + "history_owner",
            assessment._AssessmentHistory(),
        )
    elif attack == "interpretation_publisher":
        target, name, replacement = (
            source,
            prefix + "interpretation_service",
            copy(source_publisher),
        )
    else:
        target, name, replacement = (
            source_publisher,
            "_history_owner",
            interpretation._InterpretationHistory(),
        )
    original = getattr(target, name)
    compose = source._lock_inputs

    def swap(stack):
        setattr(target, name, replacement)
        try:
            return compose(stack)
        finally:
            setattr(target, name, original)

    monkeypatch.setattr(source, "_lock_inputs", swap)
    with RecordingStack() as stack:
        with pytest.raises(assessment._AssessmentHistoryInvalid):
            service._lock_inputs(stack)
        assert getattr(target, name) is original
        with pytest.raises(assessment._AssessmentHistoryInvalid):
            service._check_locked_roots()


def test_history_original_namespace_identity_even_when_empty():
    owner = app._StrategyHistory()
    original = owner._namespace_id
    owner._namespace_id = (original + " ")[:-1]
    assert owner._namespace_id == original and owner._namespace_id is not original
    with pytest.raises(ValueError, match="original"):
        owner._validate()


def test_constructor_and_lock_ast_are_foundation_only():
    tree = ast.parse(inspect.getsource(app))
    service = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == Service.__name__
    )
    assert all(
        node.name.startswith("_")
        for node in service.body
        if isinstance(node, ast.FunctionDef)
    )
    forbidden_names = {
        "execute",
        "get_result_history_as_of",
        "_publish",
        "_stage_publication",
        "derive_governed_daily_technical_strategy",
        "validate_governed_daily_technical_strategy",
        "_authenticate_assessment_occurrence",
        "_authenticate_assessment_inventory",
        "_revalidate_assessment_inventory",
        "_observe_technical_history",
    }
    assert not [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.Attribute))
        and getattr(node, "name", getattr(node, "attr", None)) in forbidden_names
    ]
    # Constructor has no execution, provider, bridge, qualification or domain calls.
    constructor = next(
        node
        for node in service.body
        if isinstance(node, ast.FunctionDef) and node.name == "__init__"
    )
    calls = [node.func for node in ast.walk(constructor) if isinstance(node, ast.Call)]
    assert all(isinstance(node, ast.Name) for node in calls)
    assert {node.id for node in calls} == {
        "type",
        "TypeError",
        "callable",
        "_StrategyHistory",
        "vars",
        "_StrategyRoot",
    }


def test_slice_file_scope():
    root = Path(__file__).resolve().parents[2]
    allowed = {
        "src/market_platform/application/polygon_completed_daily_production_strategy.py",
        "tests/unit/test_polygon_completed_daily_production_strategy.py",
    }
    tracked = subprocess.check_output(
        [
            "git",
            "diff",
            "--name-only",
            "3793ec32923ee872a4f619c48965bffdb56f68a9",
        ],
        cwd=root,
        text=True,
    ).splitlines()
    untracked = subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard"], cwd=root, text=True
    ).splitlines()
    assert set(tracked + untracked) == allowed


@pytest.mark.parametrize(
    "path,key,value",
    [
        (("source_assessment_occurrence",), "assessment_history_namespace_id", "wrong"),
        (("source_assessment_occurrence",), "assessment_history_sequence", True),
        (("source_assessment_occurrence",), "assessment_execution_id", "wrong"),
        (("source_assessment_occurrence",), "assessment_fingerprint", "wrong"),
        (("source_assessment_occurrence", "artifact_reference"), "authority", "wrong"),
        (("canonical_instrument_id",), "instrument_id", ""),
        ((), "source_assessment_content_fingerprint", "wrong"),
        ((), "source_interpretation_content_fingerprint", "wrong"),
        ((), "mode", "wrong"),
        ((), "rule_code", "aligned_positive_continuation"),
        (("strategy_policy_identity",), "policy_kind", "wrong"),
        (("strategy_policy_identity",), "policy_id", "wrong"),
        (("strategy_policy_identity",), "behavioral_revision", "2.0.0"),
        (("strategy_policy_identity",), "configuration_schema", "wrong"),
        (("strategy_policy_identity",), "configuration", []),
        (("strategy_policy_identity",), "configuration", {"extra": True}),
    ],
)
def test_complete_nested_validation_despite_coherent_fingerprints(path, key, value):
    projection = result().to_dict()
    strategy = projection["strategy"]
    at(strategy, path)[key] = value
    if path and path[-1] in ("artifact_reference", "strategy_policy_identity"):
        refingerprint(at(strategy, path))
    refingerprint(strategy)
    refingerprint(projection)
    with pytest.raises((TypeError, ValueError)):
        app._reconstruct_result(app._canonical_bytes(projection))


@pytest.mark.parametrize(
    "field",
    [
        "strategy",
        "source_assessment_occurrence",
        "artifact_reference",
        "canonical_instrument_id",
        "strategy_policy_identity",
    ],
)
def test_result_rejects_nested_wrapper_subclasses(field):
    value = result()
    strategy = value.strategy
    parent = {
        "strategy": value,
        "source_assessment_occurrence": strategy,
        "artifact_reference": strategy.source_assessment_occurrence,
        "canonical_instrument_id": strategy,
        "strategy_policy_identity": strategy,
    }[field]
    original = getattr(parent, field)
    subclass = object.__new__(type("Subclass", (type(original),), {}))
    for item in fields(original):
        object.__setattr__(subclass, item.name, getattr(original, item.name))
    object.__setattr__(parent, field, subclass)
    with pytest.raises((TypeError, ValueError)):
        value.to_dict()


def test_public_graphs_and_projections_are_enum_free_and_disjoint():
    retained = result()
    owner = app._StrategyHistory()
    fact = app._encode_result(result(history_namespace_id=owner._namespace_id))
    owner._state = (2, (fact,))  # Test-only structural fixture, never publication.
    reconstructed = app._reconstruct_result(fact)
    public = app._public_result_copy(reconstructed)
    values = [
        retained,
        reconstructed,
        public,
        retained.to_dict(),
        reconstructed.to_dict(),
        public.to_dict(),
        retained.strategy.strategy_policy_identity.configuration,
        public.strategy.strategy_policy_identity.configuration,
        Refused(R.HISTORY_INVALID, "diagnostic"),
    ]
    for index, value in enumerate(values):
        assert all(not isinstance(item, Enum) for item in graph(value))
        for previous in values[:index]:
            assert not mutable_ids(value) & mutable_ids(previous)
    original = owner._state
    object.__setattr__(
        public.strategy.strategy_policy_identity, "policy_kind", "changed"
    )
    object.__setattr__(
        reconstructed.strategy.source_assessment_occurrence,
        "assessment_history_sequence",
        999,
    )
    assert owner._state is original
    owner._validate()
    assert app._encode_result(app._reconstruct_result(owner._state[1][0])) == fact


@pytest.mark.parametrize("target", ["publisher", "owner"])
def test_replacement_class_views_do_not_choose_locks(monkeypatch, target):
    source, upstream = publisher()
    service = Service(source)
    owner = service._history_owner
    replacement, replacement_locks = publisher()
    other_owner = app._StrategyHistory()
    name = "_assessment_service" if target == "publisher" else "_history_owner"
    value = replacement if target == "publisher" else other_owner
    monkeypatch.setattr(Service, name, property(lambda self: value))
    with RecordingStack() as stack:
        service._lock_inputs(stack)
        assert stack.locks == [*upstream, owner._lock]
        assert not any(lock.locked() for lock in replacement_locks)
        assert not other_owner._lock.locked()


@pytest.mark.parametrize(
    "accessor", ["_history_owner", "_namespace", "_interpretation_service"]
)
@pytest.mark.parametrize("view", ["replacement", "raising"])
def test_assessment_accessor_replacement_preserves_original_root(
    monkeypatch, accessor, view
):
    source, upstream = publisher()
    replacement, replacement_locks = publisher()
    roots_key = (
        "_PolygonCompletedDailyProductionAssessmentApplicationService"
        "__consumption_roots"
    )
    original_roots = vars(source)[roots_key]
    replacement_value = getattr(replacement, accessor)
    accessor_calls, compositions, checks = [], [], []
    compose = source._lock_inputs
    check = source._check_consumption_roots

    def read_view(instance):
        accessor_calls.append(instance)
        if view == "raising":
            pytest.fail("Assessment authority must not dispatch its read accessor")
        return replacement_value

    def compose_once(stack):
        compositions.append(source)
        return compose(stack)

    def check_selected_chain(state, interpretation_state):
        checks.append(source)
        assert stack.locks == expected
        check(state, interpretation_state)

    monkeypatch.setattr(Publisher, accessor, property(read_view))
    monkeypatch.setattr(source, "_lock_inputs", compose_once)
    monkeypatch.setattr(source, "_check_consumption_roots", check_selected_chain)
    service = Service(source, forbidden)
    root = vars(service)[
        "_PolygonCompletedDailyProductionStrategyApplicationService__root"
    ]
    assert root.publisher is source
    assert root.assessment_roots is original_roots
    assert root.assessment_owner is original_roots[0]
    assert root.assessment_namespace is original_roots[1]
    assert root.assessment_lock is original_roots[0]._lock
    assert root.interpretation_lock is original_roots[3]._lock
    assert all(value is not replacement_value for value in original_roots)
    assert vars(source)[roots_key] is original_roots
    expected = [*upstream, service._history_owner._lock]
    with RecordingStack() as stack:
        service._lock_inputs(stack)
        assert stack.locks == expected
        assert len(stack.locks) == len(set(stack.locks)) == 11
        assert all(lock.locked() for lock in expected)
        assert not any(lock.locked() for lock in replacement_locks)
    assert compositions == checks == [source]
    assert accessor_calls == []
    assert not any(lock.locked() for lock in expected)


@pytest.mark.parametrize(
    "field",
    ["history_owner", "namespace", "interpretation_service", "consumption_roots"],
)
def test_assessment_private_root_mismatch_cannot_be_hidden_by_accessors(
    monkeypatch, field
):
    source, _ = publisher()
    replacement, _ = publisher()
    prefix = "_PolygonCompletedDailyProductionAssessmentApplicationService__"
    original_roots = vars(source)[prefix + "consumption_roots"]
    service = Service(source)
    # Compatibility views continue to report the original values after private drift.
    for name, value in zip(
        ("_history_owner", "_namespace", "_interpretation_service"),
        original_roots[:3],
        strict=True,
    ):
        monkeypatch.setattr(Publisher, name, property(lambda self, value=value: value))
    replacement_value = (
        tuple(list(original_roots))
        if field == "consumption_roots"
        else vars(replacement)[prefix + field]
    )
    assert replacement_value is not vars(source)[prefix + field]
    vars(source)[prefix + field] = replacement_value
    with RecordingStack() as stack:
        with pytest.raises(ValueError, match="roots"):
            service._lock_inputs(stack)
        assert stack.locks == []
    assert vars(source)[prefix + field] is replacement_value


def test_pending_before_wait_is_checked_only_after_acquisition(monkeypatch):
    source, _ = publisher()
    service = Service(source)
    owner = service._history_owner
    owner._pending = object()
    compose = source._lock_inputs

    def finish_prior_work(stack):
        # Models pending cleanup before this caller obtains the shared chain.
        owner._pending = None
        compose(stack)

    monkeypatch.setattr(source, "_lock_inputs", finish_prior_work)
    with RecordingStack() as stack:
        service._lock_inputs(stack)
        service._check_locked_roots()
    assert owner._state is service._committed
