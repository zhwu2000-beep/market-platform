from __future__ import annotations

import ast
import inspect
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from copy import copy, deepcopy
from dataclasses import FrozenInstanceError, fields, is_dataclass
from datetime import UTC, datetime, timedelta, timezone
from enum import Enum, IntEnum, StrEnum
from itertools import product
from pathlib import Path
from threading import Barrier, Event, Lock, local
from types import SimpleNamespace

import pytest
from test_polygon_completed_daily_production_assessment import (
    assessment_request,
    bridge_fixture,  # noqa: F401
    consumption_case,  # noqa: F401
    interpretation_authentic,  # noqa: F401
    preparation_publisher,  # noqa: F401
)

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


def test_exact_exports_and_public_workflows():
    assert app.__all__ == [
        "PolygonCompletedDailyStrategyRefusalReason",
        "PolygonCompletedDailyStrategyRefused",
        "PolygonCompletedDailyStrategyResult",
        "PolygonCompletedDailyProductionStrategyApplicationService",
    ]
    assert [
        name
        for name, value in inspect.getmembers(Service)
        if not name.startswith("_") and callable(value)
    ] == ["execute", "get_result_history_as_of"]
    service = Service(publisher()[0])
    for name in ("_publish", "_history"):
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
        or node.name in ("execute", "get_result_history_as_of")
        for node in service.body
        if isinstance(node, ast.FunctionDef)
    )
    forbidden_names = {
        "_publish",
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


def strategy_request(value, **changes):
    return domain.PolygonCompletedDailyStrategyRequest(
        **{
            "artifact_reference": (
                value.assessment.source_interpretation_occurrence.artifact_reference
            ),
            "assessment_history_namespace_id": value.history_namespace_id,
            "assessment_history_sequence": value.history_sequence,
            "assessment_execution_id": value.execution_id,
            "assessment_fingerprint": value.fingerprint,
        }
        | changes
    )


@pytest.fixture
def execute_case(consumption_case):  # noqa: F811
    source, first, second, _, _ = consumption_case
    return Service(source, lambda: TIME), strategy_request(first), second


@pytest.fixture(scope="module")
def authentic_strategy_sources(preparation_publisher):  # noqa: F811
    upstream, first, second = preparation_publisher
    source = Publisher(upstream, lambda: second.available_at)
    one = source.execute(assessment_request(first))
    two = source.execute(assessment_request(second))
    return source, one, two


@pytest.fixture
def authentic_execute_case(authentic_strategy_sources):
    source, one, two = authentic_strategy_sources
    return Service(source, lambda: two.available_at), strategy_request(one), two


def execute_refusal(service, request, reason):
    owner, state = service._history_owner, service._committed
    with pytest.raises(Refused) as caught:
        service.execute(request)
    assert caught.value.reason == reason
    assert service._committed is state
    assert owner._state is state
    assert owner._pending is None
    return caught.value


@pytest.mark.parametrize("kind", ["none", "mapping", "content", "result", "subclass"])
def test_execute_exact_outer_type_before_clock_or_locks(monkeypatch, kind):
    service = Service(publisher()[0], forbidden)
    monkeypatch.setattr(service, "_lock_inputs", forbidden)
    request = content().source_assessment_occurrence
    supplied = {
        "none": None,
        "mapping": request.to_dict(),
        "content": content(),
        "result": result(),
        "subclass": object.__new__(type("Subclass", (type(request),), {})),
    }[kind]
    monkeypatch.setattr(app, "deepcopy", forbidden)
    with pytest.raises(TypeError):
        service.execute(supplied)


@pytest.mark.parametrize("field", ["fingerprint", "artifact_fingerprint", "authority"])
def test_execute_does_not_repair_input_before_clock(monkeypatch, field):
    service = Service(publisher()[0], forbidden)
    request = content().source_assessment_occurrence
    object.__setattr__(request.artifact_reference, field, "bad")
    monkeypatch.setattr(service, "_lock_inputs", forbidden)
    with pytest.raises((TypeError, ValueError)):
        service.execute(request)


def test_execute_detach_projection_start_and_eleven_lock_order(
    execute_case, monkeypatch
):
    service, request, _ = execute_case
    expected = request.to_dict()
    events, stacks, selected = [], [], []
    project = domain.PolygonCompletedDailyStrategyRequest.to_dict
    reference_project = app.GovernedTechnicalArtifactReference.to_dict
    consume = service._assessment_service._authenticate_assessment_occurrence
    derive = domain.derive_governed_daily_technical_strategy
    validate = domain.validate_governed_daily_technical_strategy

    def projection(value):
        assert value is not request
        assert value.artifact_reference is not request.artifact_reference
        events.append("projection")
        return project(value)

    def reference_projection(value):
        assert value is not request.artifact_reference
        return reference_project(value)

    class Stack(RecordingStack):
        def __init__(self):
            super().__init__()
            stacks.append(self)

    def clock():
        events.append("clock")
        if events.count("clock") == 1:
            assert "projection" in events
            assert not stacks
            object.__setattr__(request, "assessment_history_sequence", 999)
            object.__setattr__(
                request.artifact_reference, "artifact_version", "changed"
            )
        else:
            assert len(stacks[0].locks) == 11
            assert all(lock.locked() for lock in stacks[0].locks)
            assert "derive" in events and "validate" in events
        return TIME

    def occurrence(value):
        assert events.count("clock") == 1
        assert project(value) == expected
        assert len(stacks[0].locks) == len(set(stacks[0].locks)) == 11
        selected.append(value)
        events.append("consume")
        return consume(value)

    def derivation(**kwargs):
        events.append("derive")
        return derive(**kwargs)

    def validation(**kwargs):
        events.append("validate")
        return validate(**kwargs)

    monkeypatch.setattr(
        domain.PolygonCompletedDailyStrategyRequest, "to_dict", projection
    )
    monkeypatch.setattr(
        app.GovernedTechnicalArtifactReference, "to_dict", reference_projection
    )
    monkeypatch.setattr(app, "ExitStack", Stack)
    monkeypatch.setattr(service, "_clock", clock)
    monkeypatch.setattr(
        service._assessment_service, "_authenticate_assessment_occurrence", occurrence
    )
    monkeypatch.setattr(domain, "derive_governed_daily_technical_strategy", derivation)
    monkeypatch.setattr(
        domain, "validate_governed_daily_technical_strategy", validation
    )
    value = service.execute(request)
    assert project(value.strategy.source_assessment_occurrence) == expected
    assert events.count("clock") == 3
    assert events.count("derive") == 1
    assert events.count("validate") == 2
    assert events.index("clock") < events.index("consume") < events.index("derive")
    assert len(stacks) == len(selected) == 1
    assert not any(lock.locked() for lock in stacks[0].locks)


@pytest.mark.parametrize(
    "selector",
    [
        "artifact_reference",
        "assessment_history_namespace_id",
        "assessment_history_sequence",
        "assessment_execution_id",
        "assessment_fingerprint",
    ],
)
def test_execute_all_five_exact_selectors_no_latest(execute_case, selector):
    service, request, other = execute_case
    if selector == "artifact_reference":
        value = deepcopy(request.artifact_reference)
        object.__setattr__(value, "artifact_version", "other")
        object.__setattr__(
            value, "fingerprint", canonical_fingerprint(value._fingerprint_payload())
        )
    elif selector == "assessment_history_sequence":
        value = other.history_sequence
    elif selector == "assessment_history_namespace_id":
        value = "polygon_completed_daily_assessment_history:" + "0" * 32
    elif selector == "assessment_execution_id":
        value = other.execution_id
    else:
        value = (
            other.assessment.fingerprint
        )  # Content never replaces envelope identity.
    object.__setattr__(request, selector, value)
    execute_refusal(service, request, R.ASSESSMENT_UNAVAILABLE)


@pytest.mark.parametrize(
    "failure,reason",
    [
        (assessment._AssessmentOccurrenceUnavailable, R.ASSESSMENT_UNAVAILABLE),
        (assessment._AssessmentHistoryInvalid, R.HISTORY_INVALID),
        (assessment._AssessmentSourceMismatch, R.SOURCE_MISMATCH),
    ],
)
@pytest.mark.parametrize(
    "message", ["same message", "semantic clock missing source history"]
)
def test_execute_private_failure_types_only(
    execute_case, monkeypatch, failure, reason, message
):
    service, request, _ = execute_case

    def failed(value):
        raise failure(message)

    monkeypatch.setattr(
        service._assessment_service, "_authenticate_assessment_occurrence", failed
    )
    execute_refusal(service, request, reason)


@pytest.mark.parametrize(
    "instants,reason",
    [
        ([TIME - timedelta(microseconds=1)], R.ASSESSMENT_UNAVAILABLE),
        ([None], R.TEMPORAL_FAILURE),
        ([TIME, None], R.TEMPORAL_FAILURE),
        ([TIME, TIME - timedelta(microseconds=1)], R.TEMPORAL_FAILURE),
        ([TIME, TIME, None], R.TEMPORAL_FAILURE),
        ([TIME, TIME, TIME - timedelta(microseconds=1)], R.TEMPORAL_FAILURE),
    ],
)
def test_execute_chronology_and_id_order(execute_case, monkeypatch, instants, reason):
    service, request, _ = execute_case
    clock = iter(instants)
    ids = []
    monkeypatch.setattr(service, "_clock", lambda: next(clock))
    monkeypatch.setattr(
        app, "uuid4", lambda: ids.append(1) or SimpleNamespace(hex="e" * 32)
    )
    execute_refusal(service, request, reason)
    assert len(ids) == (1 if len(instants) == 3 else 0)


@pytest.mark.parametrize("boundary", ["derive", "validate"])
def test_execute_semantic_failure_precedes_completion_and_id(
    execute_case, monkeypatch, boundary
):
    service, request, _ = execute_case
    clocks = []
    monkeypatch.setattr(service, "_clock", lambda: clocks.append(1) or TIME)
    monkeypatch.setattr(app, "uuid4", forbidden)

    def failed(**kwargs):
        raise ValueError("same message")

    name = (
        "derive" if boundary == "derive" else "validate"
    ) + "_governed_daily_technical_strategy"
    monkeypatch.setattr(domain, name, failed)
    execute_refusal(service, request, R.SEMANTIC_FAILED)
    assert clocks == [1]


def test_execute_validator_is_independent_of_derivation(execute_case, monkeypatch):
    service, request, _ = execute_case
    derive = domain.derive_governed_daily_technical_strategy
    calls = []

    def once(**kwargs):
        calls.append(1)
        value = derive(**kwargs)
        monkeypatch.setattr(
            domain, "derive_governed_daily_technical_strategy", forbidden
        )
        return value

    monkeypatch.setattr(domain, "derive_governed_daily_technical_strategy", once)
    service.execute(request)
    assert calls == [1]


def test_execute_coherent_wrong_candidate_is_semantic_failure(
    execute_case, monkeypatch
):
    service, request, _ = execute_case
    derive = domain.derive_governed_daily_technical_strategy

    def wrong(**kwargs):
        value = derive(**kwargs)
        object.__setattr__(value, "mode", "positive_directional_continuation")
        object.__setattr__(value, "rule_code", "aligned_positive_continuation")
        object.__setattr__(
            value, "fingerprint", canonical_fingerprint(value._fingerprint_payload())
        )
        return value

    monkeypatch.setattr(domain, "derive_governed_daily_technical_strategy", wrong)
    execute_refusal(service, request, R.SEMANTIC_FAILED)


def test_execute_canonical_fact_equality_isolation_and_occurrences(execute_case):
    service, request, other = execute_case
    one = service.execute(request)
    two = service.execute(request)
    three = service.execute(strategy_request(other))
    assert [one.history_sequence, two.history_sequence, three.history_sequence] == [
        1,
        2,
        3,
    ]
    assert len({v.execution_id for v in (one, two, three)}) == 3
    assert len({v.fingerprint for v in (one, two, three)}) == 3
    assert one.strategy == two.strategy
    assert one.strategy.mode == three.strategy.mode
    assert one.strategy.fingerprint != three.strategy.fingerprint
    assert service._committed is service._history_owner._state
    state = service._committed
    for index, value in enumerate((one, two, three)):
        assert type(state[1][index]) is bytes
        assert app._encode_result(value) == state[1][index]
        assert value.fingerprint == canonical_fingerprint(value._payload())
        assert tuple(getattr(value, field) for field in TIME_FIELDS) == (TIME,) * 4
        assert not any(isinstance(item, Enum) for item in graph(value))
        assert not mutable_ids(value) & mutable_ids(
            app._reconstruct_result(state[1][index])
        )
    assert not mutable_ids(one) & mutable_ids(two)
    object.__setattr__(
        one.strategy.source_assessment_occurrence.artifact_reference,
        "artifact_id",
        "changed",
    )
    assert service._committed is state
    service.execute(request)  # Caller mutation has no authority.


def test_execute_duplicate_id_no_retry_and_failed_sequence_reuse(
    execute_case, monkeypatch
):
    service, request, _ = execute_case
    first = service.execute(request)
    calls = []
    with monkeypatch.context() as patch:
        patch.setattr(
            app,
            "uuid4",
            lambda: (
                calls.append(1) or SimpleNamespace(hex=first.execution_id.split(":")[1])
            ),
        )
        execute_refusal(service, request, R.PUBLICATION_FAILED)
    assert calls == [1]
    assert service.execute(request).history_sequence == 2


def test_execute_nondecreasing_publication_availability(execute_case, monkeypatch):
    service, request, _ = execute_case
    later = TIME + timedelta(seconds=1)
    clock = iter([TIME, TIME, later, TIME, TIME, TIME, TIME, TIME, later])
    monkeypatch.setattr(service, "_clock", lambda: next(clock))
    assert service.execute(request).available_at == later
    execute_refusal(service, request, R.TEMPORAL_FAILURE)
    assert service.execute(request).history_sequence == 2


def test_stage_exact_valid_values_and_no_authority():
    owner = app._StrategyHistory()
    state = owner._state
    for value in (None, content(), object.__new__(type("Child", (Result,), {}))):
        with pytest.raises(TypeError):
            owner._stage_publication(value)
    invalid = result()
    object.__setattr__(invalid, "fingerprint", FP)
    with pytest.raises(ValueError):
        owner._stage_publication(invalid)
    value = result()
    owner._stage_publication(value)
    assert owner._pending is value
    assert owner._state is state == (1, ())


@pytest.mark.parametrize(
    "seam", ["stage", "copy", "encode", "reconstruct", "graph", "uuid"]
)
def test_execute_preparation_failures_atomic_and_reuse_sequence(
    execute_case, monkeypatch, seam
):
    service, request, _ = execute_case
    service.execute(request)
    target, name = {
        "stage": (service._history_owner, "_stage_publication"),
        "copy": (app, "_public_result_copy"),
        "encode": (app, "_encode_result"),
        "reconstruct": (app, "_reconstruct_result"),
        "graph": (app, "_graph_ids"),
        "uuid": (app, "uuid4"),
    }[seam]
    original = getattr(target, name)

    def failed(*args, **kwargs):
        # Prior inventory codecs remain authentic; fail only candidate preparation.
        if (
            seam in ("encode", "reconstruct")
            and service._history_owner._pending is None
        ):
            return original(*args, **kwargs)
        raise ValueError("injected publication failure")

    with monkeypatch.context() as patch:
        patch.setattr(target, name, failed)
        execute_refusal(service, request, R.PUBLICATION_FAILED)
    assert service.execute(request).history_sequence == 2


@pytest.mark.parametrize(
    "attack,reason",
    [
        ("bytes", R.HISTORY_INVALID),
        ("semantic", R.HISTORY_INVALID),
        ("availability", R.SOURCE_MISMATCH),
        ("content_source", R.SOURCE_MISMATCH),
        ("missing_source", R.HISTORY_INVALID),
    ],
)
def test_execute_complete_prior_inventory_before_new_selection(
    execute_case, monkeypatch, attack, reason
):
    service, request, other = execute_case
    service.execute(
        strategy_request(other)
    )  # Prior entry unrelated to the new selector.
    projection = app._decode_result(service._committed[1][0])
    if attack == "bytes":
        fact = b"corrupt"
    else:
        if attack == "semantic":
            projection["strategy"]["mode"] = "positive_directional_continuation"
            projection["strategy"]["rule_code"] = "aligned_positive_continuation"
        elif attack == "availability":
            projection["assessment_available_at"] = (
                TIME - timedelta(seconds=1)
            ).isoformat()
        elif attack == "content_source":
            projection["strategy"]["source_assessment_content_fingerprint"] = FP
        else:
            projection["strategy"]["source_assessment_occurrence"][
                "assessment_execution_id"
            ] = "polygon_completed_daily_assessment:" + "0" * 32
        refingerprint(projection["strategy"])
        refingerprint(projection)
        fact = app._canonical_bytes(projection)
    # Corrupt both independent pins to reach deep committed-fact authentication.
    service._committed = service._history_owner._state = (2, (fact,))
    consume = service._assessment_service._authenticate_assessment_occurrence
    calls = []

    def occurrence(value):
        calls.append(value)
        assert value != request, (
            "new source selected before complete prior authentication"
        )
        return consume(value)

    monkeypatch.setattr(
        service._assessment_service, "_authenticate_assessment_occurrence", occurrence
    )
    monkeypatch.setattr(domain, "derive_governed_daily_technical_strategy", forbidden)
    execute_refusal(service, request, reason)
    assert len(calls) == (0 if attack == "bytes" else 1)


def test_execute_selected_pair_must_match_captured_inventory(execute_case, monkeypatch):
    service, request, _ = execute_case
    capture = service._assessment_service._authenticate_assessment_inventory
    monkeypatch.setattr(
        service._assessment_service,
        "_authenticate_assessment_inventory",
        lambda: capture()[1:],
    )
    execute_refusal(service, request, R.SOURCE_MISMATCH)


@pytest.mark.parametrize("view", ["owner", "publisher", "namespace"])
def test_execute_replaceable_views_never_own_transaction(
    execute_case, monkeypatch, view
):
    service, request, _ = execute_case
    owner = service._history_owner
    replacement = app._StrategyHistory()
    replacement._pending = sentinel = object()
    value = {"owner": replacement, "publisher": publisher()[0], "namespace": NAMESPACE}[
        view
    ]
    name = {
        "owner": "_history_owner",
        "publisher": "_assessment_service",
        "namespace": "_namespace",
    }[view]
    monkeypatch.setattr(Service, name, property(lambda self: value))
    service.execute(request)
    assert owner._state is service._committed
    assert owner._state[0] == 2 and owner._pending is None
    assert replacement._state == (1, ()) and replacement._pending is sentinel


@pytest.mark.parametrize("phase", ["stage", "copy", "seal"])
@pytest.mark.parametrize("raise_error", [False, True])
def test_execute_original_cleanup_survives_owner_replacement(
    execute_case, monkeypatch, phase, raise_error
):
    service, request, _ = execute_case
    service.execute(request)
    owner, state = service._history_owner, service._committed
    replacement = app._StrategyHistory()
    replacement._pending = sentinel = object()
    target, name = {
        "stage": (owner, "_stage_publication"),
        "copy": (app, "_public_result_copy"),
        "seal": (service._assessment_service, "_revalidate_assessment_inventory"),
    }[phase]
    original = getattr(target, name)

    def replace_owner(*args):
        value = original(*args)
        vars(service)[
            "_PolygonCompletedDailyProductionStrategyApplicationService__history_owner"
        ] = replacement
        if raise_error:
            raise ValueError("replacement failure")
        return value

    monkeypatch.setattr(target, name, replace_owner)
    with pytest.raises(Refused):
        service.execute(request)
    assert owner._pending is None
    assert owner._state is service._committed is state
    assert replacement._pending is sentinel
    assert replacement._state == (1, ())


def test_execute_final_seal_complete_inventory_and_preallocated_state(
    execute_case, monkeypatch
):
    service, request, _ = execute_case
    source = service._assessment_service
    state = service._committed
    seal = source._revalidate_assessment_inventory
    seen = []

    def final_seal(expected):
        frame = inspect.currentframe().f_back
        prepared = frame.f_locals
        next_state = prepared["next_state"]
        public = prepared["public"]
        assert service._committed is state
        assert service._history_owner._pending is prepared["staged"]
        assert next_state == (2, (app._encode_result(public),))
        assert len(expected) == 2  # New Strategy consumes only the first Assessment.
        assert tuple(pair.assessment_fact for pair in expected) == source._committed[1]
        seen.append(next_state)
        seal(expected)
        # No local fallible dispatch may follow the complete seal.
        for name in (
            "_encode_result",
            "_reconstruct_result",
            "_public_result_copy",
            "_graph_ids",
            "deepcopy",
            "uuid4",
            "_check_pair",
            "_check_strategy_source",
            "_validate_committed_assessment",
        ):
            monkeypatch.setattr(app, name, forbidden)
        monkeypatch.setattr(Result, "to_dict", forbidden)
        monkeypatch.setattr(app._StrategyHistory, "_validate", forbidden)
        monkeypatch.setattr(service, "_check_transaction", forbidden)
        monkeypatch.setattr(service, "_check_roots", forbidden)
        monkeypatch.setattr(service, "_clock", forbidden)
        monkeypatch.setattr(
            app.assessment_domain,
            "validate_governed_daily_technical_assessment",
            forbidden,
        )
        for name in (
            "derive_governed_daily_technical_strategy",
            "validate_governed_daily_technical_strategy",
        ):
            monkeypatch.setattr(domain, name, forbidden)
        for name in (
            "_authenticate_assessment_inventory",
            "_authenticate_assessment_occurrence",
        ):
            monkeypatch.setattr(source, name, forbidden)

    monkeypatch.setattr(source, "_revalidate_assessment_inventory", final_seal)
    public = service.execute(request)
    assert public.history_sequence == 1
    assert service._committed is service._history_owner._state is seen[0]


@pytest.mark.parametrize(
    "target",
    [
        "namespace",
        "commitment",
        "assessment_root",
        "interpretation_dictionary",
        "interpretation_owner",
        "interpretation_history",
        "interpretation_state",
        "interpretation_owner_state",
        "interpretation_namespace",
        "interpretation_owner_namespace",
        "interpretation_pending",
        "interpretation_lock",
    ],
)
def test_execute_post_seal_direct_root_drift(execute_case, monkeypatch, target):
    service, request, _ = execute_case
    owner, state = service._history_owner, service._committed
    source = service._assessment_service
    upstream = source._interpretation_service
    upstream_owner = upstream._history_owner
    seal = source._revalidate_assessment_inventory
    key = (
        "_PolygonCompletedDailyProductionAssessmentApplicationService"
        "__consumption_roots"
    )
    targets = {
        "namespace": (owner, "_namespace_id", (owner._namespace_id + " ")[:-1]),
        "commitment": (service, "_committed", tuple(list(state))),
        "assessment_root": (source, key, tuple(list(vars(source)[key]))),
        "interpretation_dictionary": (upstream, "__dict__", vars(upstream).copy()),
        "interpretation_owner": (
            upstream,
            "_history_owner",
            interpretation._InterpretationHistory(),
        ),
        "interpretation_history": (
            upstream,
            "_history",
            interpretation._InterpretationHistory(),
        ),
        "interpretation_state": (
            upstream,
            "_committed",
            tuple(list(upstream._committed)),
        ),
        "interpretation_owner_state": (
            upstream_owner,
            "_state",
            tuple(list(upstream_owner._state)),
        ),
        "interpretation_namespace": (
            upstream,
            "_namespace",
            (upstream._namespace + " ")[:-1],
        ),
        "interpretation_owner_namespace": (
            upstream_owner,
            "_namespace_id",
            (upstream_owner._namespace_id + " ")[:-1],
        ),
        "interpretation_pending": (upstream_owner, "_pending", object()),
        "interpretation_lock": (upstream_owner, "_lock", Lock()),
    }
    changed, name, replacement = targets[target]
    assert getattr(changed, name) is not replacement

    def drift(expected):
        seal(expected)
        setattr(changed, name, replacement)

    monkeypatch.setattr(source, "_revalidate_assessment_inventory", drift)
    with pytest.raises(Refused) as caught:
        service.execute(request)
    assert caught.value.reason == R.HISTORY_INVALID
    assert owner._state is state and owner._pending is None
    assert service._committed == state
    if target != "commitment":
        assert service._committed is state
    assert getattr(changed, name) is replacement  # Refusal never repairs drift.


def test_execute_post_seal_authentic_interpretation_commitment_replacement(
    authentic_execute_case, monkeypatch
):
    service, request, _ = authentic_execute_case
    service.execute(request)
    owner, state = service._history_owner, service._committed
    source = service._assessment_service
    source_state = source._committed
    upstream = source._interpretation_service
    interpretation_state = upstream._committed
    replacement = tuple(list(interpretation_state))
    assert (
        replacement == interpretation_state and replacement is not interpretation_state
    )
    seal = source._revalidate_assessment_inventory

    def drift(expected):
        seal(expected)
        monkeypatch.setattr(upstream, "_committed", replacement)

    monkeypatch.setattr(source, "_revalidate_assessment_inventory", drift)
    execute_refusal(service, request, R.HISTORY_INVALID)
    assert service._committed is owner._state is state
    assert owner._pending is None
    assert source._committed is source._history_owner._state is source_state
    assert upstream._committed is replacement  # No publication-side repair.
    assert upstream._history_owner._state is interpretation_state


def test_execute_three_authentic_concurrent_publications(
    preparation_publisher,  # noqa: F811
    monkeypatch,
):
    upstream, first, _ = preparation_publisher
    source = Publisher(upstream, lambda: first.available_at)
    published = source.execute(assessment_request(first))
    service = Service(source, lambda: published.available_at)
    request = strategy_request(published)
    gate = Barrier(3)
    time = service._clock()
    thread_state = local()

    def clock():
        if not getattr(thread_state, "started", False):
            thread_state.started = True
            gate.wait(timeout=20)
        return time

    monkeypatch.setattr(service, "_clock", clock)
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(service.execute, request) for _ in range(3)]
        results = [future.result() for future in futures]
    assert sorted(value.history_sequence for value in results) == [1, 2, 3]
    assert len({value.execution_id for value in results}) == 3
    assert service._committed is service._history_owner._state
    assert service._committed[0] == 4


def test_execute_waiter_captures_state_after_chain_acquisition(
    execute_case, monkeypatch
):
    service, request, _ = execute_case
    stage = service._history_owner._stage_publication
    staged, release, waiting = Event(), Event(), Event()
    calls, attempts = [], []
    acquire = service._lock_inputs

    def locking(stack):
        attempts.append(True)
        if len(attempts) == 2:
            waiting.set()
        acquire(stack)

    def pause(value):
        stage(value)
        calls.append(value)
        if len(calls) == 1:
            staged.set()
            assert release.wait(20)

    monkeypatch.setattr(service._history_owner, "_stage_publication", pause)
    monkeypatch.setattr(service, "_lock_inputs", locking)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(service.execute, request)
        assert staged.wait(20)
        second = pool.submit(service.execute, request)
        assert waiting.wait(20)
        release.set()
        assert first.result(timeout=30).history_sequence == 1
        assert second.result(timeout=30).history_sequence == 2


def test_execute_no_upstream_execution_history_or_interpretation_semantics(
    authentic_execute_case, monkeypatch
):
    service, request, _ = authentic_execute_case
    source = service._assessment_service
    upstream = source._interpretation_service
    tech = upstream._technical_service
    bridge = tech._bridge_service
    from market_platform.data.providers.polygon import PolygonProvider

    for target, names in (
        (source, ("execute", "get_result_history_as_of")),
        (
            upstream,
            (
                "execute",
                "get_result_history_as_of",
                "_check_history",
                "_observe_technical_history",
            ),
        ),
        (tech, ("execute", "get_result_history_as_of")),
        (bridge, ("bridge", "get_bridge_history_as_of")),
        (bridge._qualification_service, ("qualify",)),
        (technical.technical, ("analyze_daily_technical_snapshot",)),
        (PolygonProvider, ("get_daily_prices", "get_completed_daily_acquisition")),
        (assessment.domain, ("assess_governed_daily_technical_interpretation",)),
        (
            interpretation.domain,
            (
                "interpret_governed_daily_technical_snapshot",
                "validate_governed_daily_technical_interpretation",
                "classic_states",
                "build_classic_comparison_evidence",
            ),
        ),
    ):
        for name in names:
            monkeypatch.setattr(target, name, forbidden)
    service.execute(request)
    service.execute(request)


@pytest.mark.parametrize("seam", ["copy", "graph", "validation"])
def test_execute_final_seal_catches_unrelated_real_support_loss(
    authentic_execute_case, monkeypatch, seam
):
    service, request, _ = authentic_execute_case
    service.execute(request)
    upstream = service._assessment_service._interpretation_service
    tech = upstream._technical_service
    target, name = {
        "copy": (app, "_public_result_copy"),
        "graph": (app, "_graph_ids"),
        "validation": (domain, "validate_governed_daily_technical_strategy"),
    }[seam]
    original = getattr(target, name)
    seal = service._assessment_service._revalidate_assessment_inventory
    sealing = []

    def remove(*args, **kwargs):
        value = original(*args, **kwargs)
        if service._history_owner._pending is not None:
            state = tech._history._state
            # Drop the later technical support, unrelated to the selected Assessment.
            monkeypatch.setattr(tech._history, "_state", (state[0] - 1, state[1][:-1]))
        return value

    def final(expected):
        sealing.append(len(expected))
        return seal(expected)

    monkeypatch.setattr(target, name, remove)
    monkeypatch.setattr(
        service._assessment_service, "_revalidate_assessment_inventory", final
    )
    execute_refusal(service, request, R.HISTORY_INVALID)
    # Earlier prior-history rechecks may already detect the loss. On the final
    # domain seam the complete seal itself must reject the unrelated support loss.
    if seam == "validation":
        assert sealing == [2]


def test_execute_no_action_fields_or_downstream_integration():
    tree = ast.parse(inspect.getsource(app))
    names = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    names |= {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert not names & {
        "TradingSignal",
        "OrderIntent",
        "RiskDecision",
        "StrategyCandidate",
        "PositionAction",
        "PriceTarget",
        "ProbabilityEstimate",
        "thesis",
        "recommendation",
        "buy",
        "sell",
        "entry",
        "target",
        "stop",
        "sizing",
        "allocation",
        "execution_authorization",
    }
    assert callable(Service.get_result_history_as_of)
    assert not hasattr(Service, "_publish")


@pytest.mark.parametrize("phase", ["capture", "seal"])
@pytest.mark.parametrize(
    "failure,reason",
    [
        (assessment._AssessmentHistoryInvalid, R.HISTORY_INVALID),
        (assessment._AssessmentSourceMismatch, R.SOURCE_MISMATCH),
    ],
)
def test_execute_complete_inventory_failure_categories(
    execute_case, monkeypatch, phase, failure, reason
):
    service, request, _ = execute_case
    name = (
        "_authenticate_assessment_inventory"
        if phase == "capture"
        else "_revalidate_assessment_inventory"
    )

    def fail(*args):
        raise failure("identical opaque diagnostic")

    monkeypatch.setattr(service._assessment_service, name, fail)
    execute_refusal(service, request, reason)


@pytest.mark.parametrize("attack", ["alias", "changed", "enum"])
def test_execute_public_preparation_rejects_bad_graph(
    execute_case, monkeypatch, attack
):
    service, request, _ = execute_case
    original = app._public_result_copy

    def corrupt(value):
        public = original(value)
        if attack == "alias":
            object.__setattr__(public, "strategy", value.strategy)
        elif attack == "changed":
            object.__setattr__(public, "execution_id", PREFIX + ":" + "0" * 32)
            object.__setattr__(
                public, "fingerprint", canonical_fingerprint(public._payload())
            )
        else:
            object.__setattr__(public, "history_sequence", NumberEnum.ONE)
        return public

    monkeypatch.setattr(app, "_public_result_copy", corrupt)
    execute_refusal(service, request, R.PUBLICATION_FAILED)


def test_execute_staging_cannot_alias_prepared_content(execute_case, monkeypatch):
    service, request, _ = execute_case
    copy_value = app.deepcopy

    def alias(value):
        if type(value) is domain.GovernedDailyTechnicalStrategy:
            return value
        return copy_value(value)

    monkeypatch.setattr(app, "deepcopy", alias)
    execute_refusal(service, request, R.PUBLICATION_FAILED)


def test_execute_final_R_is_fingerprinted(execute_case, monkeypatch):
    service, request, _ = execute_case
    clock = iter([TIME, TIME + timedelta(seconds=1), TIME + timedelta(seconds=2)])
    monkeypatch.setattr(service, "_clock", lambda: next(clock))
    value = service.execute(request)
    assert value.execution_started_at == TIME
    assert value.execution_completed_at == TIME + timedelta(seconds=1)
    assert value.available_at == TIME + timedelta(seconds=2)
    expected = value.to_dict()
    assert value.fingerprint == canonical_fingerprint(value._payload())
    assert service._committed[1] == (app._canonical_bytes(expected),)
    expected["available_at"] = value.execution_completed_at.isoformat()
    refingerprint(expected)
    assert expected["fingerprint"] != value.fingerprint


def test_execute_wrong_authenticated_pair_is_source_mismatch(execute_case, monkeypatch):
    service, request, _ = execute_case
    source = service._assessment_service
    occurrence = source._authenticate_assessment_occurrence
    other = strategy_request(execute_case[2])
    monkeypatch.setattr(
        source, "_authenticate_assessment_occurrence", lambda request: occurrence(other)
    )
    execute_refusal(service, request, R.SOURCE_MISMATCH)


def test_execute_final_seal_catches_earlier_support_loss_after_later_pair_work(
    execute_case, monkeypatch
):
    service, request, _ = execute_case
    source = service._assessment_service
    upstream = source._interpretation_service
    check_pair = assessment._check_assessment_pair
    seal = source._revalidate_assessment_inventory
    authenticate = upstream._authenticate_interpretation_occurrence
    active, lost, selected = [], [], []
    with ExitStack() as stack:
        source._lock_inputs(stack)
        inventory = source._authenticate_assessment_inventory()
    first_execution = inventory[0].interpretation.execution_id

    def pair_work(item, interpretation_value):
        check_pair(item, interpretation_value)
        if active and item.history_sequence == 2:
            lost.append(first_execution)

    def support(**selectors):
        selected.append(selectors["interpretation_execution_id"])
        if lost and selectors["interpretation_execution_id"] == first_execution:
            raise interpretation._InterpretationHistoryInvalid("earlier support lost")
        return authenticate(**selectors)

    def final(expected):
        active.append(True)
        return seal(expected)

    monkeypatch.setattr(assessment, "_check_assessment_pair", pair_work)
    monkeypatch.setattr(upstream, "_authenticate_interpretation_occurrence", support)
    monkeypatch.setattr(source, "_revalidate_assessment_inventory", final)
    execute_refusal(service, request, R.HISTORY_INVALID)
    assert active and lost
    assert selected[-1] == first_execution


def test_execute_final_seal_rechecks_unselected_assessment_after_last_graph_work(
    execute_case, monkeypatch
):
    service, request, other = execute_case
    source = service._assessment_service
    upstream = source._interpretation_service
    authenticate = upstream._authenticate_interpretation_occurrence
    ids = app._graph_ids
    lost, sealed = [], []
    seal = source._revalidate_assessment_inventory
    unselected_id = (
        other.assessment.source_interpretation_occurrence.interpretation_execution_id
    )

    def graph_work(value):
        result = ids(value)
        if service._history_owner._pending is not None:
            lost.append(True)
        return result

    def support(**selectors):
        if lost and selectors["interpretation_execution_id"] == unselected_id:
            raise interpretation._InterpretationHistoryInvalid(
                "unselected support lost"
            )
        return authenticate(**selectors)

    def final(expected):
        sealed.append(expected)
        return seal(expected)

    monkeypatch.setattr(app, "_graph_ids", graph_work)
    monkeypatch.setattr(upstream, "_authenticate_interpretation_occurrence", support)
    monkeypatch.setattr(source, "_revalidate_assessment_inventory", final)
    execute_refusal(service, request, R.HISTORY_INVALID)
    assert len(sealed) == 1 and len(sealed[0]) == 2


@pytest.mark.parametrize("copy_number", [1, 2])
def test_execute_input_copy_failure_is_publication_failure_before_clock(
    monkeypatch, copy_number
):
    service = Service(publisher()[0], forbidden)
    request = content().source_assessment_occurrence
    copy_value = app.deepcopy
    calls = []

    def failed(value):
        calls.append(value)
        if len(calls) == copy_number:
            raise RuntimeError("detachment failed")
        return copy_value(value)

    monkeypatch.setattr(app, "deepcopy", failed)
    monkeypatch.setattr(service, "_lock_inputs", forbidden)
    execute_refusal(service, request, R.PUBLICATION_FAILED)


def corrupt_committed_assessment_semantics(source, index=0):
    projection = json.loads(source._committed[1][index])
    content = projection["assessment"]
    content["outcome"] = "mixed" if content["outcome"] != "mixed" else "caution"
    refingerprint(content)
    refingerprint(projection)
    facts = list(source._committed[1])
    facts[index] = assessment._canonical_bytes(projection)
    # Corrupt both independent commitments to reach the semantic validation stage.
    source._committed = source._history_owner._state = (len(facts) + 1, tuple(facts))
    return assessment._reconstruct_result(facts[index])


def test_execute_invalid_committed_assessment_semantics_is_history_invalid(
    execute_case, monkeypatch
):
    service, _, _ = execute_case
    source = service._assessment_service
    invalid = corrupt_committed_assessment_semantics(source)
    request = strategy_request(invalid)
    source_state = source._committed
    validate = app.assessment_domain.validate_governed_daily_technical_assessment
    checked = []
    clocks = []

    def committed_validation(**kwargs):
        content = kwargs["content"]
        assert content.to_dict() == invalid.assessment.to_dict()
        assert kwargs["source_interpretation_occurrence"] is (
            content.source_interpretation_occurrence
        )
        checked.append(content)
        return validate(**kwargs)

    monkeypatch.setattr(
        app.assessment_domain,
        "validate_governed_daily_technical_assessment",
        committed_validation,
    )
    monkeypatch.setattr(service, "_clock", lambda: clocks.append(1) or TIME)
    monkeypatch.setattr(app, "uuid4", forbidden)
    monkeypatch.setattr(domain, "derive_governed_daily_technical_strategy", forbidden)
    monkeypatch.setattr(domain, "validate_governed_daily_technical_strategy", forbidden)
    failure = execute_refusal(service, request, R.HISTORY_INVALID)
    assert isinstance(failure.__cause__, ValueError)
    assert len(checked) == 1 and clocks == [1]
    assert source._committed is source._history_owner._state is source_state


@pytest.mark.parametrize(
    ("stage", "reason"),
    [("assessment", R.HISTORY_INVALID), ("strategy", R.SEMANTIC_FAILED)],
)
def test_execute_same_diagnostic_classified_by_validation_stage(
    execute_case, monkeypatch, stage, reason
):
    service, request, _ = execute_case
    diagnostic = "identical diagnostic: source history semantic clock"
    validate = app.assessment_domain.validate_governed_daily_technical_assessment
    events = []

    def assessment_validation(**kwargs):
        events.append("assessment")
        if stage == "assessment":
            raise ValueError(diagnostic)
        validate(**kwargs)

    def candidate_validation(**kwargs):
        assert events and events[0] == "assessment"
        events.append("strategy")
        raise ValueError(diagnostic)

    monkeypatch.setattr(
        app.assessment_domain,
        "validate_governed_daily_technical_assessment",
        assessment_validation,
    )
    monkeypatch.setattr(
        domain, "validate_governed_daily_technical_strategy", candidate_validation
    )
    failure = execute_refusal(service, request, reason)
    assert str(failure.__cause__) == diagnostic
    assert events[-1] == stage


def test_execute_prior_strategy_invalid_committed_assessment_is_history_invalid(
    execute_case, monkeypatch
):
    service, request, other = execute_case
    service.execute(request)
    source = service._assessment_service
    invalid = corrupt_committed_assessment_semantics(source)
    projection = app._decode_result(service._committed[1][0])
    content = projection["strategy"]
    content["source_assessment_occurrence"]["assessment_fingerprint"] = (
        invalid.fingerprint
    )
    content["source_assessment_content_fingerprint"] = invalid.assessment.fingerprint
    refingerprint(content)
    refingerprint(projection)
    fact = app._canonical_bytes(projection)
    service._committed = service._history_owner._state = (2, (fact,))
    consume = source._authenticate_assessment_occurrence
    calls = []

    def prior_only(value):
        assert value.to_dict() == strategy_request(invalid).to_dict()
        calls.append(value)
        return consume(value)

    monkeypatch.setattr(source, "_authenticate_assessment_occurrence", prior_only)
    monkeypatch.setattr(source, "_authenticate_assessment_inventory", forbidden)
    monkeypatch.setattr(domain, "derive_governed_daily_technical_strategy", forbidden)
    monkeypatch.setattr(domain, "validate_governed_daily_technical_strategy", forbidden)
    failure = execute_refusal(service, strategy_request(other), R.HISTORY_INVALID)
    assert isinstance(failure.__cause__, ValueError)
    assert len(calls) == 1


@pytest.mark.parametrize("invalid_semantics", [False, True])
def test_private_assessment_authentication_and_seal_do_not_validate_semantics(
    execute_case, monkeypatch, invalid_semantics
):
    service, request, _ = execute_case
    source = service._assessment_service
    if invalid_semantics:
        request = strategy_request(corrupt_committed_assessment_semantics(source))
    state = source._committed
    monkeypatch.setattr(
        app.assessment_domain,
        "validate_governed_daily_technical_assessment",
        forbidden,
    )
    with ExitStack() as stack:
        service._lock_inputs(stack)
        inventory = source._authenticate_assessment_inventory()
        pair = source._authenticate_assessment_occurrence(request)
        assert len(inventory) == 2
        assert pair.assessment_fact == inventory[0].assessment_fact
        assert pair.interpretation_fact == inventory[0].interpretation_fact
        source._revalidate_assessment_inventory(inventory)
    assert source._committed is source._history_owner._state is state
    assert service._committed == (1, ())


def history_read(service, artifact, cutoff=TIME):
    return service.get_result_history_as_of(artifact, knowledge_as_of=cutoff)


def authority_snapshot(service):
    source = service._assessment_service
    upstream = source._interpretation_service
    return tuple(
        (value, value._history_owner, value._committed, value._history_owner._pending)
        for value in (service, source, upstream)
    )


def assert_authority_unchanged(snapshot):
    for service, owner, state, pending in snapshot:
        assert service._committed is owner._state is state
        assert owner._pending is pending


def history_refusal(service, artifact, reason, cutoff=TIME):
    before = authority_snapshot(service)
    with pytest.raises(Refused) as caught:
        history_read(service, artifact, cutoff)
    assert caught.value.reason == reason
    assert_authority_unchanged(before)
    return caught.value


def install_strategy_projection(service, index, projection):
    refingerprint(projection["strategy"])
    refingerprint(projection)
    facts = list(service._committed[1])
    facts[index] = app._canonical_bytes(projection)
    service._committed = service._history_owner._state = (len(facts) + 1, tuple(facts))


def test_history_signature():
    signature = inspect.signature(Service.get_result_history_as_of)
    assert list(signature.parameters) == [
        "self",
        "artifact_reference",
        "knowledge_as_of",
    ]
    artifact = signature.parameters["artifact_reference"]
    cutoff = signature.parameters["knowledge_as_of"]
    assert artifact.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert artifact.annotation == "GovernedTechnicalArtifactReference"
    assert cutoff.kind is inspect.Parameter.KEYWORD_ONLY
    assert cutoff.default is inspect.Parameter.empty
    assert cutoff.annotation == "datetime"
    assert (
        signature.return_annotation == "tuple[PolygonCompletedDailyStrategyResult, ...]"
    )


@pytest.mark.parametrize("kind", ["none", "mapping", "request", "subclass"])
def test_history_exact_outer_type_before_detach_or_locks(
    execute_case, monkeypatch, kind
):
    service, request, _ = execute_case
    artifact = request.artifact_reference
    supplied = {
        "none": None,
        "mapping": artifact.to_dict(),
        "request": request,
        "subclass": object.__new__(type("Child", (type(artifact),), {})),
    }[kind]
    monkeypatch.setattr(app, "deepcopy", forbidden)
    monkeypatch.setattr(service, "_lock_inputs", forbidden)
    monkeypatch.setattr(service, "_clock", forbidden)
    with pytest.raises(TypeError):
        history_read(service, supplied)


@pytest.mark.parametrize("field", ["fingerprint", "artifact_fingerprint", "authority"])
def test_history_detached_invalid_artifact_is_not_repaired(
    execute_case, monkeypatch, field
):
    service, request, _ = execute_case
    artifact = request.artifact_reference
    object.__setattr__(artifact, field, "bad")
    project = type(artifact).to_dict
    seen = []

    def detached(value):
        assert value is not artifact
        seen.append(value)
        return project(value)

    monkeypatch.setattr(type(artifact), "to_dict", detached)
    monkeypatch.setattr(service, "_lock_inputs", forbidden)
    monkeypatch.setattr(app.a, "_timestamp", forbidden)
    with pytest.raises((TypeError, ValueError)):
        history_read(service, artifact)
    assert seen


def test_history_detach_capture_cutoff_then_exact_eleven_locks(
    execute_case, monkeypatch
):
    service, request, _ = execute_case
    service.execute(request)
    artifact = request.artifact_reference
    expected = artifact.to_dict()
    project = type(artifact).to_dict
    normalize = app.a._timestamp
    lock_inputs = service._lock_inputs
    events, stacks, projected = [], [], []

    def projection(value):
        assert value is not artifact
        result = project(value)
        if not projected:
            projected.append(result)
            events.append("projection")
        return result

    def timestamp(value):
        assert events == ["projection"]
        assert not stacks
        events.append("cutoff")
        # Mutate both caller state and the earlier projection after its capture.
        object.__setattr__(artifact, "artifact_version", "caller changed")
        projected[0]["artifact_version"] = "projection changed"
        result = normalize(value)
        assert result.tzinfo is UTC
        return result

    class Stack(RecordingStack):
        def __init__(self):
            super().__init__()
            stacks.append(self)

    def lock_once(stack):
        assert events == ["projection", "cutoff"]
        events.append("locks")
        lock_inputs(stack)
        root = vars(service)[
            "_PolygonCompletedDailyProductionStrategyApplicationService__root"
        ]
        assert len(stack.locks) == len(set(stack.locks)) == 11
        assert stack.locks[-3:] == [
            root.interpretation_lock,
            root.assessment_lock,
            root.lock,
        ]
        assert all(lock.locked() for lock in stack.locks)

    monkeypatch.setattr(type(artifact), "to_dict", projection)
    monkeypatch.setattr(app.a, "_timestamp", timestamp)
    monkeypatch.setattr(service, "_lock_inputs", lock_once)
    monkeypatch.setattr(app, "ExitStack", Stack)
    monkeypatch.setattr(service, "_clock", forbidden)
    monkeypatch.setattr(app, "uuid4", forbidden)
    values = history_read(
        service, artifact, TIME.astimezone(timezone(timedelta(hours=8)))
    )
    assert len(values) == 1
    assert (
        project(values[0].strategy.source_assessment_occurrence.artifact_reference)
        == expected
    )
    assert events == ["projection", "cutoff", "locks"]
    assert len(stacks) == 1 and not any(lock.locked() for lock in stacks[0].locks)


@pytest.mark.parametrize(
    "cutoff",
    [
        None,
        "2026-01-02",
        TIME.replace(tzinfo=None),
        1,
        type("DateSubclass", (datetime,), {})(2026, 1, 2, tzinfo=UTC),
    ],
)
def test_history_invalid_cutoff_is_temporal_before_locks(
    execute_case, monkeypatch, cutoff
):
    service, request, _ = execute_case
    monkeypatch.setattr(service, "_lock_inputs", forbidden)
    monkeypatch.setattr(service, "_clock", forbidden)
    history_refusal(service, request.artifact_reference, R.TEMPORAL_FAILURE, cutoff)


@pytest.mark.parametrize("copy_number", [1, 2])
def test_history_input_copy_failure_before_cutoff(
    execute_case, monkeypatch, copy_number
):
    service, request, _ = execute_case
    original = app.deepcopy
    calls = []

    def fail(value):
        calls.append(value)
        if len(calls) == copy_number:
            raise ValueError("copy failed")
        return original(value)

    monkeypatch.setattr(app, "deepcopy", fail)
    monkeypatch.setattr(app.a, "_timestamp", forbidden)
    monkeypatch.setattr(service, "_lock_inputs", forbidden)
    history_refusal(service, request.artifact_reference, R.PUBLICATION_FAILED)


@pytest.mark.parametrize("empty", [True, False])
def test_history_empty_selection_authenticates_and_seals_complete_inventory(
    execute_case, monkeypatch, empty
):
    service, request, _ = execute_case
    if not empty:
        service.execute(request)
    source = service._assessment_service
    capture = source._authenticate_assessment_inventory
    authenticate = service._authenticate_history_locked
    seal = source._revalidate_assessment_inventory
    events = []

    def capture_all():
        values = capture()
        assert len(values) == 2
        events.append("capture")
        return values

    def complete(*args, **kwargs):
        events.append("strategy")
        return authenticate(*args, **kwargs)

    def final(expected):
        assert len(expected) == 2
        assert tuple(pair.assessment_fact for pair in expected) == source._committed[1]
        events.append("seal")
        return seal(expected)

    monkeypatch.setattr(source, "_authenticate_assessment_inventory", capture_all)
    monkeypatch.setattr(service, "_authenticate_history_locked", complete)
    monkeypatch.setattr(source, "_revalidate_assessment_inventory", final)
    before = authority_snapshot(service)
    values = history_read(
        service, request.artifact_reference, TIME - timedelta(microseconds=1)
    )
    assert type(values) is tuple and values == ()
    assert events == ["capture", "strategy", "seal"]
    assert_authority_unchanged(before)


@pytest.mark.parametrize("invisible", ["unrelated", "future"])
@pytest.mark.parametrize(
    "attack,reason",
    [
        ("bytes", R.HISTORY_INVALID),
        ("semantic", R.HISTORY_INVALID),
        ("availability", R.SOURCE_MISMATCH),
        ("content_source", R.SOURCE_MISMATCH),
    ],
)
def test_history_complete_inventory_corruption_precedes_filtering(
    execute_case, monkeypatch, invisible, attack, reason
):
    service, request, _ = execute_case
    service.execute(request)
    later = TIME + timedelta(seconds=1)
    monkeypatch.setattr(service, "_clock", lambda: later)
    service.execute(request)
    projection = app._decode_result(service._committed[1][1])
    if attack == "semantic":
        projection["strategy"]["mode"] = "positive_directional_continuation"
        projection["strategy"]["rule_code"] = "aligned_positive_continuation"
    elif attack == "availability":
        projection["assessment_available_at"] = (
            TIME - timedelta(seconds=1)
        ).isoformat()
    elif attack == "content_source":
        projection["strategy"]["source_assessment_content_fingerprint"] = FP
    install_strategy_projection(service, 1, projection)
    if attack == "bytes":
        service._committed = service._history_owner._state = (
            3,
            (service._committed[1][0], b"bad"),
        )
    artifact = (
        request.artifact_reference
        if invisible == "future"
        else content().source_assessment_occurrence.artifact_reference
    )
    if invisible == "unrelated":
        object.__setattr__(artifact, "artifact_id", "test:unrelated")
        object.__setattr__(
            artifact,
            "fingerprint",
            canonical_fingerprint(artifact._fingerprint_payload()),
        )
    monkeypatch.setattr(app, "_public_result_copy", forbidden)
    history_refusal(service, artifact, reason)


@pytest.mark.parametrize("stage", ["assessment", "strategy"])
def test_history_same_semantic_diagnostic_is_committed_history_invalid(
    execute_case, monkeypatch, stage
):
    service, request, _ = execute_case
    service.execute(request)
    events = []
    validate = app.assessment_domain.validate_governed_daily_technical_assessment

    def assessment_validation(**kwargs):
        events.append("assessment")
        if stage == "assessment":
            raise ValueError("identical diagnostic")
        validate(**kwargs)

    def strategy_validation(**kwargs):
        assert events == ["assessment"]
        events.append("strategy")
        raise ValueError("identical diagnostic")

    monkeypatch.setattr(
        app.assessment_domain,
        "validate_governed_daily_technical_assessment",
        assessment_validation,
    )
    monkeypatch.setattr(
        domain, "validate_governed_daily_technical_strategy", strategy_validation
    )
    failure = history_refusal(service, request.artifact_reference, R.HISTORY_INVALID)
    assert str(failure.__cause__) == "identical diagnostic"
    assert events[-1] == stage


def test_history_coherent_committed_assessment_semantic_corruption(
    execute_case, monkeypatch
):
    service, request, _ = execute_case
    service.execute(request)
    invalid = corrupt_committed_assessment_semantics(service._assessment_service)
    projection = app._decode_result(service._committed[1][0])
    projection["strategy"]["source_assessment_occurrence"]["assessment_fingerprint"] = (
        invalid.fingerprint
    )
    projection["strategy"]["source_assessment_content_fingerprint"] = (
        invalid.assessment.fingerprint
    )
    install_strategy_projection(service, 0, projection)
    monkeypatch.setattr(domain, "validate_governed_daily_technical_strategy", forbidden)
    history_refusal(service, request.artifact_reference, R.HISTORY_INVALID)


@pytest.mark.parametrize("phase", ["capture", "resolve", "seal"])
@pytest.mark.parametrize(
    "failure,reason",
    [
        (assessment._AssessmentOccurrenceUnavailable, R.HISTORY_INVALID),
        (assessment._AssessmentHistoryInvalid, R.HISTORY_INVALID),
        (assessment._AssessmentSourceMismatch, R.SOURCE_MISMATCH),
    ],
)
def test_history_structured_private_failures_ignore_diagnostic(
    execute_case, monkeypatch, phase, failure, reason
):
    service, request, _ = execute_case
    service.execute(request)
    name = {
        "capture": "_authenticate_assessment_inventory",
        "resolve": "_authenticate_assessment_occurrence",
        "seal": "_revalidate_assessment_inventory",
    }[phase]

    def fail(*args):
        raise failure("identical diagnostic")

    monkeypatch.setattr(service._assessment_service, name, fail)
    error = history_refusal(service, request.artifact_reference, reason)
    assert str(error.__cause__) in (
        "identical diagnostic",
        "committed Strategy source unavailable",
    )


@pytest.mark.parametrize(
    "selector",
    [
        "artifact_reference",
        "assessment_history_namespace_id",
        "assessment_history_sequence",
        "assessment_execution_id",
        "assessment_fingerprint",
    ],
)
def test_history_all_retained_assessment_selectors_authenticate_conjunctively(
    execute_case, selector
):
    service, request, other = execute_case
    service.execute(request)
    projection = app._decode_result(service._committed[1][0])
    occurrence = projection["strategy"]["source_assessment_occurrence"]
    if selector == "artifact_reference":
        occurrence[selector]["artifact_version"] = "other"
        refingerprint(occurrence[selector])
    elif selector == "assessment_history_namespace_id":
        occurrence[selector] = "polygon_completed_daily_assessment_history:" + "0" * 32
    elif selector == "assessment_history_sequence":
        occurrence[selector] = other.history_sequence
    elif selector == "assessment_execution_id":
        occurrence[selector] = other.execution_id
    else:
        occurrence[selector] = other.assessment.fingerprint
    install_strategy_projection(service, 0, projection)
    history_refusal(service, request.artifact_reference, R.HISTORY_INVALID)


@pytest.mark.parametrize("lost", ["assessment", "interpretation"])
def test_history_missing_required_committed_source_is_history_invalid(
    execute_case, lost
):
    service, request, _ = execute_case
    service.execute(request)
    source = service._assessment_service
    target = source if lost == "assessment" else source._interpretation_service
    target._committed = target._history_owner._state = (1, ())
    history_refusal(service, request.artifact_reference, R.HISTORY_INVALID)


@pytest.mark.parametrize("attack", ["omit", "other_pair", "content_fact"])
def test_history_retained_pair_must_be_exactly_in_captured_inventory(
    execute_case, monkeypatch, attack
):
    service, request, other = execute_case
    service.execute(request)
    source = service._assessment_service
    capture = source._authenticate_assessment_inventory
    resolve = source._authenticate_assessment_occurrence

    def inventory():
        pairs = capture()
        if attack == "omit":
            return pairs[1:]
        if attack == "content_fact":
            pair = pairs[0]
            object.__setattr__(
                pair,
                "assessment_fact",
                app._canonical_bytes(pair.assessment.assessment.to_dict()),
            )
        return pairs

    monkeypatch.setattr(source, "_authenticate_assessment_inventory", inventory)
    if attack == "other_pair":
        monkeypatch.setattr(
            source,
            "_authenticate_assessment_occurrence",
            lambda value: resolve(strategy_request(other)),
        )
    history_refusal(service, request.artifact_reference, R.SOURCE_MISMATCH)


@pytest.mark.parametrize(
    "field,value",
    [
        ("artifact_id", "other:id"),
        ("artifact_version", "2.0.0"),
        ("artifact_fingerprint", "sha256:" + "b" * 64),
        ("information_class", "source_assertion"),
        ("authority", "platform_origin"),
    ],
)
def test_history_complete_artifact_projection_required(execute_case, field, value):
    service, request, _ = execute_case
    service.execute(request)
    artifact = deepcopy(request.artifact_reference)
    assert getattr(artifact, field) != value
    object.__setattr__(artifact, field, value)
    object.__setattr__(
        artifact, "fingerprint", canonical_fingerprint(artifact._fingerprint_payload())
    )
    assert history_read(service, artifact) == ()


def test_history_inclusive_cutoff_sequence_order_and_repeated_content(
    execute_case, monkeypatch
):
    service, request, _ = execute_case
    first = service.execute(request)
    second = service.execute(request)
    later = TIME + timedelta(microseconds=1)
    monkeypatch.setattr(service, "_clock", lambda: later)
    third = service.execute(request)
    assert (
        first.strategy.fingerprint
        == second.strategy.fingerprint
        == third.strategy.fingerprint
    )
    for cutoff, expected in [
        (TIME - timedelta(microseconds=1), []),
        (TIME, [first, second]),
        (TIME.astimezone(timezone(timedelta(hours=-5))), [first, second]),
        (later, [first, second, third]),
    ]:
        values = history_read(service, request.artifact_reference, cutoff)
        assert type(values) is tuple
        assert [v.to_dict() for v in values] == [v.to_dict() for v in expected]
        assert [v.history_sequence for v in values] == list(range(1, len(expected) + 1))


def test_history_public_graphs_from_final_bytes_fresh_disjoint_and_mutation_safe(
    execute_case, monkeypatch
):
    service, request, _ = execute_case
    service.execute(request)
    service.execute(request)
    state = service._committed
    captured, retained = [], []
    capture = service._assessment_service._authenticate_assessment_inventory
    copy_result = app._public_result_copy

    def inventory():
        result = capture()
        captured.extend(result)
        return result

    def copying(value):
        retained.append(value)
        return copy_result(value)

    monkeypatch.setattr(
        service._assessment_service, "_authenticate_assessment_inventory", inventory
    )
    monkeypatch.setattr(app, "_public_result_copy", copying)
    one = history_read(service, request.artifact_reference)
    two = history_read(service, request.artifact_reference)
    values = (*one, *two)
    for index, value in enumerate(values):
        assert type(value) is Result
        assert app._encode_result(value) == state[1][value.history_sequence - 1]
        assert not any(isinstance(item, Enum) for item in graph(value))
        assert not mutable_ids(value) & mutable_ids((tuple(captured), tuple(retained)))
        for earlier in values[:index]:
            assert not mutable_ids(value) & mutable_ids(earlier)
    object.__setattr__(
        one[0].strategy.source_assessment_occurrence.artifact_reference,
        "artifact_id",
        "caller:changed",
    )
    object.__setattr__(
        one[1].strategy.canonical_instrument_id, "instrument_id", "changed"
    )
    assert service._committed is state
    assert tuple(app._encode_result(v) for v in two) == state[1]
    assert (
        tuple(
            app._encode_result(v)
            for v in history_read(service, request.artifact_reference)
        )
        == state[1]
    )


@pytest.mark.parametrize(
    "attack",
    ["raise", "alias", "cross_alias", "earlier_mutation", "enum", "other_occurrence"],
)
def test_history_public_preparation_failures_are_atomic(
    execute_case, monkeypatch, attack
):
    service, request, _ = execute_case
    service.execute(request)
    service.execute(request)
    original = app._public_result_copy
    prepared = []

    def corrupt(value):
        if attack == "raise":
            raise RuntimeError("copy failed")
        public = original(value)
        if attack == "alias":
            object.__setattr__(public, "strategy", value.strategy)
        elif attack == "enum":
            object.__setattr__(public, "history_sequence", NumberEnum.ONE)
        elif attack == "other_occurrence":
            public = app._reconstruct_result(service._committed[1][1])
        elif prepared:
            if attack == "cross_alias":
                object.__setattr__(public, "strategy", prepared[0].strategy)
            else:
                object.__setattr__(prepared[0].strategy, "rule_code", "changed")
        prepared.append(public)
        return public

    monkeypatch.setattr(app, "_public_result_copy", corrupt)
    monkeypatch.setattr(
        service._assessment_service, "_revalidate_assessment_inventory", forbidden
    )
    history_refusal(service, request.artifact_reference, R.PUBLICATION_FAILED)


@pytest.mark.parametrize("visible", [False, True])
def test_history_final_complete_seal_after_preparation_and_direct_return(
    execute_case, monkeypatch, visible
):
    service, request, _ = execute_case
    service.execute(request)
    source = service._assessment_service
    before = authority_snapshot(service)
    seal = source._revalidate_assessment_inventory
    calls = []
    cutoff = TIME if visible else TIME - timedelta(microseconds=1)

    def final(expected):
        prepared = inspect.currentframe().f_back.f_locals
        public = prepared["public"]
        assert type(public) is tuple and len(public) == int(visible)
        assert len(expected) == 2
        assert tuple(pair.assessment_fact for pair in expected) == source._committed[1]
        assert not mutable_ids(public) & mutable_ids(expected)
        calls.append(public)
        seal(expected)
        for name in (
            "_encode_result",
            "_decode_result",
            "_canonical_bytes",
            "_check_scalars",
            "_reconstruct_result",
            "_public_result_copy",
            "_check_copy",
            "_graph_ids",
            "deepcopy",
            "uuid4",
            "_check_pair",
            "_check_strategy_source",
            "_validate_committed_assessment",
        ):
            monkeypatch.setattr(app, name, forbidden)
        for cls in (
            Result,
            app.GovernedTechnicalArtifactReference,
            domain.GovernedDailyTechnicalStrategy,
            domain.PolygonCompletedDailyStrategyRequest,
        ):
            monkeypatch.setattr(cls, "to_dict", forbidden)
        for name in (
            "_check_transaction",
            "_check_roots",
            "_authenticate_history_locked",
            "_clock",
        ):
            monkeypatch.setattr(service, name, forbidden)
        monkeypatch.setattr(app._StrategyHistory, "_validate", forbidden)
        monkeypatch.setattr(
            app.assessment_domain,
            "validate_governed_daily_technical_assessment",
            forbidden,
        )
        monkeypatch.setattr(
            domain, "validate_governed_daily_technical_strategy", forbidden
        )
        for name in (
            "_authenticate_assessment_inventory",
            "_authenticate_assessment_occurrence",
            "_revalidate_assessment_inventory",
        ):
            monkeypatch.setattr(source, name, forbidden)
        monkeypatch.setattr(
            source._interpretation_service,
            "_authenticate_interpretation_occurrence",
            forbidden,
        )
        for cls, names in (
            (Service, ("_history_owner", "_namespace", "_assessment_service")),
            (Publisher, ("_history_owner", "_namespace", "_interpretation_service")),
        ):
            for name in names:
                monkeypatch.setattr(cls, name, property(forbidden))

    monkeypatch.setattr(source, "_revalidate_assessment_inventory", final)
    values = history_read(service, request.artifact_reference, cutoff)
    assert len(calls) == 1 and values is calls[0]
    assert_authority_unchanged(before)
    # Assert the successful post-seal path has no calls/allocations beyond direct
    # dictionary identity reads, the drift refusal, and returning the prepared tuple.
    import textwrap

    method = ast.parse(
        textwrap.dedent(inspect.getsource(Service.get_result_history_as_of))
    )
    block = next(node for node in ast.walk(method) if isinstance(node, ast.With))
    index = next(
        index
        for index, node in enumerate(block.body)
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute)
        and node.value.func.attr == "_revalidate_assessment_inventory"
    )
    tail = block.body[index + 1 :]
    assert (
        len(tail) == 2
        and isinstance(tail[0], ast.If)
        and isinstance(tail[1], ast.Return)
    )
    assert isinstance(tail[1].value, ast.Name) and tail[1].value.id == "public"
    for node in ast.walk(tail[0].test):
        assert not isinstance(
            node,
            (ast.List, ast.Tuple, ast.Dict, ast.Set, ast.ListComp, ast.GeneratorExp),
        )
        if isinstance(node, ast.Call):
            assert ast.unparse(node.func) == "object.__getattribute__"


@pytest.mark.parametrize("seam", ["copy", "graph", "domain"])
@pytest.mark.parametrize("lost", ["unselected_assessment", "invisible_strategy"])
def test_history_final_seal_catches_real_invisible_support_loss(
    authentic_execute_case, monkeypatch, seam, lost
):
    service, request, other = authentic_execute_case
    service.execute(request)
    cutoff = other.available_at
    if lost == "invisible_strategy":
        monkeypatch.setattr(
            service, "_clock", lambda: cutoff + timedelta(microseconds=1)
        )
        service.execute(strategy_request(other))
    source = service._assessment_service
    tech = source._interpretation_service._technical_service
    target, name = {
        "copy": (app, "_public_result_copy"),
        "graph": (app, "_graph_ids"),
        "domain": (domain, "validate_governed_daily_technical_strategy"),
    }[seam]
    original = getattr(target, name)
    seal = source._revalidate_assessment_inventory
    lost_support, sealed = [], []

    def late_work(*args, **kwargs):
        result = original(*args, **kwargs)
        # On domain work, wait until the last retained Strategy validation so the
        # final seal, rather than another retained-source lookup, catches loss.
        if not lost_support and (
            seam != "domain"
            or kwargs[
                "content"
            ].source_assessment_occurrence.assessment_history_sequence
            == (2 if lost == "invisible_strategy" else 1)
        ):
            state = tech._history._state
            monkeypatch.setattr(tech._history, "_state", (state[0] - 1, state[1][:-1]))
            lost_support.append(True)
        return result

    def final(expected):
        sealed.append(expected)
        assert len(expected) == 2
        return seal(expected)

    monkeypatch.setattr(target, name, late_work)
    monkeypatch.setattr(source, "_revalidate_assessment_inventory", final)
    history_refusal(service, request.artifact_reference, R.HISTORY_INVALID, cutoff)
    assert lost_support and len(sealed) == 1


@pytest.mark.parametrize(
    "target",
    [
        "root",
        "owner",
        "namespace",
        "commitment",
        "owner_state",
        "pending",
        "assessment_root",
        "assessment_state",
        "interpretation_state",
    ],
)
def test_history_post_seal_direct_drift_refuses_without_repair(
    execute_case, monkeypatch, target
):
    service, request, _ = execute_case
    service.execute(request)
    source = service._assessment_service
    upstream = source._interpretation_service
    owner, state = service._history_owner, service._committed
    seal = source._revalidate_assessment_inventory
    strategy_prefix = "_PolygonCompletedDailyProductionStrategyApplicationService__"
    assessment_prefix = "_PolygonCompletedDailyProductionAssessmentApplicationService__"
    targets = {
        "root": (
            service,
            strategy_prefix + "root",
            copy(vars(service)[strategy_prefix + "root"]),
        ),
        "owner": (service, strategy_prefix + "history_owner", app._StrategyHistory()),
        "namespace": (owner, "_namespace_id", (owner._namespace_id + " ")[:-1]),
        "commitment": (service, "_committed", tuple(list(state))),
        "owner_state": (owner, "_state", tuple(list(state))),
        "pending": (owner, "_pending", object()),
        "assessment_root": (
            source,
            assessment_prefix + "consumption_roots",
            tuple(list(vars(source)[assessment_prefix + "consumption_roots"])),
        ),
        "assessment_state": (source, "_committed", tuple(list(source._committed))),
        "interpretation_state": (
            upstream,
            "_committed",
            tuple(list(upstream._committed)),
        ),
    }
    changed, name, replacement = targets[target]
    assert getattr(changed, name) is not replacement
    after_callback = []

    def drift(expected):
        seal(expected)
        setattr(changed, name, replacement)
        after_callback.append((service._committed, owner._state, owner._pending))

    monkeypatch.setattr(source, "_revalidate_assessment_inventory", drift)
    with pytest.raises(Refused) as caught:
        history_read(service, request.artifact_reference)
    assert caught.value.reason == R.HISTORY_INVALID
    assert (
        getattr(changed, name) is replacement
    )  # Reads do not repair or clean pending.
    assert all(
        current is before
        for current, before in zip(
            (service._committed, owner._state, owner._pending),
            after_callback[0],
            strict=True,
        )
    )


@pytest.mark.parametrize("attack", ["equal_state", "pending", "namespace", "root"])
def test_history_requires_original_idle_authority(execute_case, attack):
    service, request, _ = execute_case
    service.execute(request)
    owner = service._history_owner
    if attack == "equal_state":
        owner._state = tuple(list(owner._state))
    elif attack == "pending":
        owner._pending = object()
    elif attack == "namespace":
        owner._namespace_id = (owner._namespace_id + " ")[:-1]
    else:
        vars(service)[
            "_PolygonCompletedDailyProductionStrategyApplicationService__history_owner"
        ] = app._StrategyHistory()
    state, pending = owner._state, owner._pending
    with pytest.raises(Refused) as caught:
        history_read(service, request.artifact_reference)
    assert caught.value.reason == R.HISTORY_INVALID
    assert owner._state is state and owner._pending is pending


@pytest.mark.parametrize("view", ["owner", "publisher", "namespace"])
def test_history_replaceable_views_do_not_choose_authority(
    execute_case, monkeypatch, view
):
    service, request, _ = execute_case
    issued = service.execute(request)
    before = authority_snapshot(service)
    name = {
        "owner": "_history_owner",
        "publisher": "_assessment_service",
        "namespace": "_namespace",
    }[view]
    monkeypatch.setattr(Service, name, property(forbidden))
    assert (
        history_read(service, request.artifact_reference)[0].to_dict()
        == issued.to_dict()
    )
    assert_authority_unchanged(before)


def test_history_never_executes_upstream_stages_clock_uuid_or_derivation(
    authentic_execute_case, monkeypatch
):
    service, request, other = authentic_execute_case
    service.execute(request)
    source = service._assessment_service
    upstream = source._interpretation_service
    tech = upstream._technical_service
    bridge = tech._bridge_service
    from market_platform.data.providers.polygon import PolygonProvider

    for target, names in (
        (service, ("execute", "_clock")),
        (service._history_owner, ("_stage_publication",)),
        (app, ("uuid4",)),
        (domain, ("derive_governed_daily_technical_strategy",)),
        (source, ("execute", "get_result_history_as_of")),
        (
            upstream,
            (
                "execute",
                "get_result_history_as_of",
                "_check_history",
                "_observe_technical_history",
            ),
        ),
        (tech, ("execute", "get_result_history_as_of")),
        (bridge, ("bridge", "get_bridge_history_as_of")),
        (bridge._qualification_service, ("qualify",)),
        (technical.technical, ("analyze_daily_technical_snapshot",)),
        (PolygonProvider, ("get_daily_prices", "get_completed_daily_acquisition")),
        (assessment.domain, ("assess_governed_daily_technical_interpretation",)),
        (
            interpretation.domain,
            (
                "interpret_governed_daily_technical_snapshot",
                "validate_governed_daily_technical_interpretation",
                "classic_states",
                "build_classic_comparison_evidence",
            ),
        ),
    ):
        for name in names:
            monkeypatch.setattr(target, name, forbidden)
    before = authority_snapshot(service)
    assert (
        len(history_read(service, request.artifact_reference, other.available_at)) == 1
    )
    assert_authority_unchanged(before)


@pytest.mark.parametrize("first", ["reader", "writer"])
def test_history_execute_concurrency_complete_old_or_new_state(
    execute_case, monkeypatch, first
):
    service, request, other = execute_case
    one = service.execute(request)
    old_state = service._committed
    held, release, waiting = Event(), Event(), Event()
    lock_inputs = service._lock_inputs
    seal = service._assessment_service._revalidate_assessment_inventory
    stage = service._history_owner._stage_publication
    attempts = []
    captured = []
    authenticate = service._authenticate_history_locked

    def locking(stack):
        attempts.append(True)
        if len(attempts) == 2:
            waiting.set()
        lock_inputs(stack)

    def capture(root, state, **kwargs):
        if kwargs:  # Only history supplies complete expected inventory facts.
            captured.append(state)
        return authenticate(root, state, **kwargs)

    def pause_stage(value):
        stage(value)
        if first == "writer":
            held.set()
            assert release.wait(20)

    def pause_seal(expected):
        seal(expected)
        if first == "reader" and not held.is_set():
            held.set()
            assert release.wait(20)

    monkeypatch.setattr(service, "_lock_inputs", locking)
    monkeypatch.setattr(service, "_authenticate_history_locked", capture)
    monkeypatch.setattr(service._history_owner, "_stage_publication", pause_stage)
    monkeypatch.setattr(
        service._assessment_service, "_revalidate_assessment_inventory", pause_seal
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        if first == "writer":
            writer = pool.submit(service.execute, request)
        else:
            reader = pool.submit(
                history_read, service, request.artifact_reference, other.available_at
            )
        try:
            assert held.wait(20)
            if first == "writer":
                reader = pool.submit(
                    history_read,
                    service,
                    request.artifact_reference,
                    other.available_at,
                )
            else:
                writer = pool.submit(service.execute, request)
            assert waiting.wait(20)
            assert not (reader if first == "writer" else writer).done()
            assert service._committed is old_state
        finally:
            release.set()
        two = writer.result(timeout=30)
        values = reader.result(timeout=30)
    assert [value.history_sequence for value in values] == (
        [1, 2] if first == "writer" else [1]
    )
    expected = [one, two] if first == "writer" else [one]
    assert [value.to_dict() for value in values] == [
        value.to_dict() for value in expected
    ]
    assert len(captured) == 1
    assert captured[0] is (service._committed if first == "writer" else old_state)
    assert service._committed is service._history_owner._state
    assert service._committed[0] == 3 and service._history_owner._pending is None


def test_history_exact_original_eleven_lock_order_once(monkeypatch):
    source, upstream = publisher()
    service = Service(source, forbidden)
    expected = [*upstream, service._history_owner._lock]
    stacks, seals = [], []

    class Stack(RecordingStack):
        def __init__(self):
            super().__init__()
            stacks.append(self)

    def inventory():
        assert stacks[0].locks == expected
        return ()

    def seal(values):
        assert values == ()
        assert stacks[0].locks == expected
        assert all(lock.locked() for lock in expected)
        seals.append(True)

    monkeypatch.setattr(app, "ExitStack", Stack)
    monkeypatch.setattr(source, "_authenticate_assessment_inventory", inventory)
    monkeypatch.setattr(source, "_revalidate_assessment_inventory", seal)
    artifact = content().source_assessment_occurrence.artifact_reference
    assert history_read(service, artifact) == ()
    assert len(stacks) == 1 and seals == [True]
    assert len(expected) == len(set(expected)) == 11
    assert not any(lock.locked() for lock in expected)


def test_history_later_graph_work_cannot_change_earlier_public_result(
    execute_case, monkeypatch
):
    service, request, _ = execute_case
    service.execute(request)
    service.execute(request)
    original = app._public_result_copy
    graph_ids = app._graph_ids
    prepared = []

    def copying(value):
        public = original(value)
        prepared.append(public)
        return public

    def late_graph(value):
        ids = graph_ids(value)
        if len(prepared) == 2 and value is prepared[1]:
            object.__setattr__(prepared[0].strategy, "rule_code", "changed")
        return ids

    monkeypatch.setattr(app, "_public_result_copy", copying)
    monkeypatch.setattr(app, "_graph_ids", late_graph)
    history_refusal(service, request.artifact_reference, R.PUBLICATION_FAILED)


def test_history_final_seal_catches_unreturned_assessment_loss_after_copy(
    execute_case, monkeypatch
):
    service, request, _ = execute_case
    service.execute(request)
    source = service._assessment_service
    original = app._public_result_copy
    seal = source._revalidate_assessment_inventory
    sealed = []
    original_state = source._committed

    def copying(value):
        public = original(value)
        # Remove an Assessment that has no corresponding Strategy result at all.
        source._committed = source._history_owner._state = (2, original_state[1][:1])
        return public

    def final(expected):
        assert len(expected) == 2
        sealed.append(True)
        return seal(expected)

    monkeypatch.setattr(app, "_public_result_copy", copying)
    monkeypatch.setattr(source, "_revalidate_assessment_inventory", final)
    state = service._committed
    with pytest.raises(Refused) as caught:
        history_read(service, request.artifact_reference)
    assert caught.value.reason == R.HISTORY_INVALID
    assert sealed == [True]
    assert service._committed is service._history_owner._state is state
    assert service._history_owner._pending is None
    assert source._committed is source._history_owner._state
    assert source._committed == (2, original_state[1][:1])  # No read-side repair.
