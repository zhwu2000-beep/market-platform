from __future__ import annotations

import ast
import inspect
import json
import subprocess
import sys
import tomllib
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from copy import copy
from dataclasses import FrozenInstanceError, fields, is_dataclass, replace
from datetime import UTC, datetime, timedelta, timezone
from enum import Enum, IntEnum, StrEnum
from itertools import product
from pathlib import Path
from threading import Event, Lock
from types import SimpleNamespace

import pytest
from test_polygon_completed_daily_production_interpretation import (
    _interpretation_selectors,
    bridge_fixture,  # noqa: F401
)
from test_polygon_completed_daily_production_interpretation import (
    _request as interpretation_request,
)
from test_polygon_completed_daily_production_interpretation import (
    _service as interpretation_service,
)
from test_polygon_completed_daily_production_interpretation import (
    authentic as interpretation_authentic,  # noqa: F401
)

from market_platform._fingerprint import canonical_fingerprint
from market_platform.application import (
    polygon_completed_daily_production_assessment as app,
)
from market_platform.application import (
    polygon_completed_daily_production_interpretation as i,
)
from market_platform.application import (
    polygon_completed_daily_production_qualification as q,
)
from market_platform.application import (
    polygon_completed_daily_production_technical as t,
)
from market_platform.evidence import __all__ as evidence_exports
from market_platform.instruments.identity import CanonicalInstrumentId
from market_platform.research import governed_daily_technical_assessment as domain
from market_platform.trading.instrument import TradingInstrumentIdentity

Result = app.PolygonCompletedDailyAssessmentResult
Service = app.PolygonCompletedDailyProductionAssessmentApplicationService
Publisher = i.PolygonCompletedDailyProductionInterpretationApplicationService
Refused = app.PolygonCompletedDailyAssessmentRefused
R = app.PolygonCompletedDailyAssessmentRefusalReason
TIME = datetime(2026, 1, 2, tzinfo=UTC)
FP = "sha256:" + "a" * 64
PREFIX = "polygon_completed_daily_assessment"
NAMESPACE = PREFIX + "_history:" + "1" * 32
RESULT_FIELDS = (
    "assessment",
    "interpretation_available_at",
    "execution_id",
    "history_namespace_id",
    "history_sequence",
    "execution_started_at",
    "execution_completed_at",
    "available_at",
    "fingerprint",
)
TIME_FIELDS = (
    "interpretation_available_at",
    "execution_started_at",
    "execution_completed_at",
    "available_at",
)
CONSTANTS = {
    "schema_version": "polygon_completed_daily_assessment_result/v1",
    "operation": (
        "production.polygon_completed_daily.daily_technical_assessment.application"
    ),
    "operation_version": "1.0.0",
    "executor": (
        "market_platform.application/polygon_completed_daily_production_assessment/v1"
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
    # Structural retained-value fixture, with no semantic execution or source claim.
    return domain.GovernedDailyTechnicalAssessment(
        source_interpretation_occurrence=domain.PolygonCompletedDailyAssessmentRequest(
            artifact_reference=domain.GovernedTechnicalArtifactReference(
                artifact_id="test:detached",
                artifact_version="1.0.0",
                artifact_fingerprint=FP,
                information_class="source_observation",
                authority="external_origin",
            ),
            interpretation_history_namespace_id=(
                "polygon_completed_daily_interpretation_history:" + "2" * 32
            ),
            interpretation_history_sequence=1,
            interpretation_execution_id="polygon_completed_daily_interpretation:"
            + "3" * 32,
            interpretation_fingerprint=FP,
        ),
        source_interpretation_content_fingerprint="sha256:" + "b" * 64,
        canonical_instrument_id=CanonicalInstrumentId("us-aapl"),
        source_trading_identity=TradingInstrumentIdentity("AAPL", "NASDAQ"),
        analysis_as_of=TIME,
        assessment_policy_identity=domain.GovernedDailyTechnicalAssessmentPolicyIdentity(),
        source_quality="degraded",
        source_warnings=("insufficient_profile_history", "stale_evidence"),
        outcome="caution",
        findings=(
            domain.GovernedDailyTechnicalAssessmentFinding(
                "caution", "rsi_elevated", ("rsi_at_or_above_elevated",)
            ),
            domain.GovernedDailyTechnicalAssessmentFinding(
                "caution", "source_quality_degraded", ()
            ),
        ),
    )


def result(**changes):
    values = (
        dict(
            assessment=content(),
            interpretation_available_at=TIME,
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
        "INTERPRETATION_UNAVAILABLE": "interpretation_occurrence_unavailable",
        "HISTORY_INVALID": "history_incomplete_or_corrupt",
        "SOURCE_MISMATCH": "source_lineage_mismatch",
        "SEMANTIC_FAILED": "semantic_execution_or_correspondence_failed",
        "TEMPORAL_FAILURE": "temporal_failure",
        "PUBLICATION_FAILED": "assessment_publication_or_copy_failed",
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
    assert value.assessment.fingerprint != value.fingerprint
    assert value.assessment.fingerprint == canonical_fingerprint(
        value.assessment._fingerprint_payload()
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


@pytest.mark.parametrize("field", ["assessment", "fingerprint"])
def test_typed_result_rejects_wrong_content_or_hash(field):
    value = result()
    object.__setattr__(value, field, object() if field == "assessment" else FP)
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
    ("assessment",),
    ("assessment", "source_interpretation_occurrence"),
    ("assessment", "source_interpretation_occurrence", "artifact_reference"),
    ("assessment", "canonical_instrument_id"),
    ("assessment", "source_trading_identity"),
    ("assessment", "assessment_policy_identity"),
    ("assessment", "assessment_policy_identity", "configuration"),
    ("assessment", "findings", 0),
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
        (("assessment",), "schema_version"),
        (("assessment",), "fingerprint"),
        (("assessment", "assessment_policy_identity"), "schema_version"),
        (("assessment", "assessment_policy_identity"), "fingerprint"),
        (
            ("assessment", "source_interpretation_occurrence", "artifact_reference"),
            "schema_version",
        ),
        (
            ("assessment", "source_interpretation_occurrence", "artifact_reference"),
            "fingerprint",
        ),
        (("assessment", "source_trading_identity"), "schema_version"),
        (("assessment", "source_trading_identity"), "instrument_fingerprint"),
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
    [*(((), key) for key in TIME_FIELDS), (("assessment",), "analysis_as_of")],
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


def test_order_and_empty_container_types_are_not_coerced():
    for key, replacement in [
        ("findings", list(reversed(result().to_dict()["assessment"]["findings"]))),
        ("source_warnings", []),
        ("findings", {}),
        ("source_warnings", ""),
    ]:
        projection = result().to_dict()
        projection["assessment"][key] = replacement
        refingerprint(projection)
        with pytest.raises((TypeError, ValueError)):
            app._reconstruct_result(app._canonical_bytes(projection))


def test_mutation_and_coherent_refingerprinting_do_not_change_bytes():
    fact = app._encode_result(result())
    expected = app._decode_result(fact)
    one, two = app._reconstruct_result(fact), app._reconstruct_result(fact)
    content_value = one.assessment
    artifact = content_value.source_interpretation_occurrence.artifact_reference
    object.__setattr__(artifact, "artifact_id", "test:changed")
    object.__setattr__(
        artifact, "fingerprint", canonical_fingerprint(artifact._fingerprint_payload())
    )
    object.__setattr__(content_value.canonical_instrument_id, "instrument_id", "other")
    object.__setattr__(content_value, "outcome", "mixed")
    object.__setattr__(
        content_value,
        "fingerprint",
        canonical_fingerprint(content_value._fingerprint_payload()),
    )
    object.__setattr__(one, "fingerprint", canonical_fingerprint(one._payload()))
    assert app._encode_result(one) != fact
    content_value.assessment_policy_identity.configuration["corrupt"] = True
    object.__setattr__(content_value.findings[0], "code", "corrupt")
    object.__setattr__(content_value.source_trading_identity, "symbol", "OTHER")
    assert fact == app._canonical_bytes(expected)
    assert two.to_dict() == expected
    assert app._reconstruct_result(fact).to_dict() == expected
    projection = two.to_dict()
    projection["assessment"]["assessment_policy_identity"]["configuration"]["bad"] = (
        True
    )
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
    owner = app._AssessmentHistory()
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
    owner = app._AssessmentHistory()
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
    owner = app._AssessmentHistory()
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
            data["assessment"]["findings"][0]["code"] = "corrupt"
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
    # Inert exact publisher: constructor must not observe any upstream attributes.
    return object.__new__(Publisher)


def test_constructor_and_pinned_authority(monkeypatch):
    source = publisher()
    for name in (
        "_lock_inputs",
        "_authenticate_interpretation_occurrence",
        "execute",
        "get_result_history_as_of",
    ):
        monkeypatch.setattr(Publisher, name, forbidden)
    service = Service(source)
    owner = service._history_owner
    assert type(owner) is app._AssessmentHistory
    assert service._interpretation_service is source
    assert service._namespace == owner._namespace_id
    assert service._committed is owner._state
    assert not hasattr(service, "_history")
    assert service._clock is app.a._utc_now
    assert list(inspect.signature(Service).parameters) == [
        "interpretation_service",
        "execution_clock",
    ]
    service._check_history()
    with pytest.raises(AttributeError):
        service._history_owner = app._AssessmentHistory()
    with pytest.raises(AttributeError):
        service._namespace = NAMESPACE
    assert service._history_owner is owner
    assert owner._pending is None


@pytest.mark.parametrize(
    "source",
    [
        None,
        object(),
        SimpleNamespace(),
        object.__new__(type("Subclass", (Publisher,), {})),
    ],
)
def test_constructor_rejects_untrusted_publisher(source):
    with pytest.raises(TypeError, match="exact trusted"):
        Service(source)


def test_equal_distinct_state_is_not_commitment():
    service = Service(publisher())
    original = service._committed
    replacement = tuple(list(original))
    assert replacement == original and replacement is not original
    service._history_owner._state = replacement
    with pytest.raises(ValueError, match="commitment"):
        service._check_history()
    assert service._committed is original
    assert service._history_owner._state is replacement


@pytest.mark.parametrize("namespace", [NAMESPACE, "bad", String(NAMESPACE)])
def test_original_namespace_required_even_when_empty(namespace):
    service = Service(publisher())
    original = service._committed
    service._history_owner._namespace_id = namespace
    with pytest.raises(ValueError):
        service._check_history()
    assert service._committed is original


def test_structural_validation_is_called_without_adoption(monkeypatch):
    service = Service(publisher())
    before = service._committed
    calls = []

    def validate(owner):
        calls.append(owner)
        raise ValueError("corrupt inventory")

    monkeypatch.setattr(app._AssessmentHistory, "_validate", validate)
    with pytest.raises(ValueError, match="corrupt inventory"):
        service._check_history()
    assert calls == [service._history_owner]
    assert service._committed is before is service._history_owner._state


def test_exact_ten_lock_chain_composed_once_without_work(monkeypatch):
    def store():
        return SimpleNamespace(_lock=Lock())

    admission = SimpleNamespace(
        _construction_service=SimpleNamespace(_history=store()),
        _validation_service=SimpleNamespace(_history=store()),
        _freshness_service=SimpleNamespace(_history=store()),
        _history=store(),
    )
    validity = SimpleNamespace(_admission_service=admission, _history=store())
    qualification = object.__new__(
        q.PolygonCompletedDailyProductionQualificationApplicationService
    )
    qualification._validity_service = validity
    qualification._history = store()
    bridge = SimpleNamespace(_qualification_service=qualification, _history=store())
    technical = object.__new__(
        t.PolygonCompletedDailyProductionTechnicalApplicationService
    )
    technical._bridge_service = bridge
    technical_owner = store()
    technical._PolygonCompletedDailyProductionTechnicalApplicationService__committed = (
        SimpleNamespace(owner=technical_owner)
    )
    technical._history = store()  # A replacement view must not select its lock.
    source = publisher()
    source._technical_service = technical
    source._history_owner = i._InterpretationHistory()
    source._history = i._InterpretationHistory()
    service = Service(source)
    owner = service._history_owner
    expected = [
        admission._construction_service._history._lock,
        admission._validation_service._history._lock,
        admission._freshness_service._history._lock,
        admission._history._lock,
        validity._history._lock,
        qualification._history._lock,
        bridge._history._lock,
        technical_owner._lock,
        source._history_owner._lock,
        owner._lock,
    ]
    calls = []
    original = source._lock_inputs

    def compose(stack):
        calls.append(1)
        original(stack)

    monkeypatch.setattr(source, "_lock_inputs", compose)
    monkeypatch.setattr(source, "_authenticate_interpretation_occurrence", forbidden)
    monkeypatch.setattr(source, "get_result_history_as_of", forbidden)
    monkeypatch.setattr(service, "_check_history", forbidden)
    monkeypatch.setattr(app, "_reconstruct_result", forbidden)
    locks = []
    service._lock_inputs(SimpleNamespace(enter_context=locks.append))
    assert calls == [1]
    assert locks == expected
    assert len({id(lock) for lock in locks}) == 10
    assert not any(lock.locked() for lock in locks)

    # Exercise actual acquisition nonblockingly, so an accidental recursion fails.
    class NonrecursiveStack(ExitStack):
        def enter_context(self, lock):
            assert lock.acquire(blocking=False), "recursive acquisition"
            self.callback(lock.release)

    with NonrecursiveStack() as stack:
        service._lock_inputs(stack)
        assert all(lock.locked() for lock in expected)
    assert calls == [1, 1]
    assert not any(lock.locked() for lock in expected)
    assert owner._state is service._committed and owner._state == (1, ())


def test_exact_exports_and_public_workflows():
    assert app.__all__ == [
        "PolygonCompletedDailyAssessmentRefusalReason",
        "PolygonCompletedDailyAssessmentRefused",
        "PolygonCompletedDailyAssessmentResult",
        "PolygonCompletedDailyProductionAssessmentApplicationService",
    ]
    assert [
        name
        for name, member in inspect.getmembers(Service, callable)
        if not name.startswith("_")
    ] == ["execute", "get_result_history_as_of"]
    assert list(inspect.signature(Service.execute).parameters) == ["self", "request"]
    tree = ast.parse(inspect.getsource(app))
    called = {
        node.func.id if isinstance(node.func, ast.Name) else node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, (ast.Name, ast.Attribute))
    }
    assert not called & {
        "_semantic_view",
        "_derive_assessment",
        "execute",
        "get_result_history_as_of",
        "_utc_now",
        "now",
    }
    assert {
        "_authenticate_interpretation_occurrence",
        "assess_governed_daily_technical_interpretation",
        "validate_governed_daily_technical_assessment",
    } <= called


def test_frozen_checkpoint_files_unchanged():
    root = Path(__file__).resolve().parents[2]
    checkpoint = "4201d2d851b061808a1712aaa573f272632865c5"
    # The original d3ada18 check was a per-slice changed-file restriction, not
    # permanent ownership of the repository. ADR0042 explicitly preserves these
    # three historical documents; public code is protected by contract/AST tests.
    for path in (
        "docs/adr/0040_governed_daily_technical_interpretation.md",
        "docs/adr/0041_publication_time_technical_issuance_authority_and_governed_interpretation_value_isolation.md",
        "docs/handoffs/v0.80.0-governed-daily-technical-interpretation-handoff.md",
    ):
        historical = subprocess.check_output(
            ["git", "show", f"{checkpoint}:{path}"],
            cwd=root,
            text=True,
            encoding="utf-8",
        )
        assert (root / path).read_text(encoding="utf-8") == historical
    assert (
        tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
        == "0.1.0"
    )
    assert len(evidence_exports) == len(set(evidence_exports)) == 69
    assert evidence_exports == sorted(evidence_exports)


@pytest.fixture(scope="module")
def preparation_publisher(interpretation_authentic):  # noqa: F811
    service = interpretation_service(interpretation_authentic)
    request = interpretation_request(interpretation_authentic[1])
    return service, service.execute(request), service.execute(request)


def assessment_request(source, **changes):
    return domain.PolygonCompletedDailyAssessmentRequest(
        **_interpretation_selectors(source, **changes)
    )


def assert_unprepared_authority(service, owner, state, namespace):
    assert service._history_owner is owner
    assert service._namespace == owner._namespace_id == namespace
    assert service._committed is owner._state is state
    assert owner._pending is None
    assert state == (1, ())


def prepare_refusal(service, request, started, reason):
    owner, state, namespace = (
        service._history_owner,
        service._committed,
        service._namespace,
    )
    with pytest.raises(Refused) as caught:
        service._prepare_assessment(request, started)
    assert caught.value.reason == reason
    assert_unprepared_authority(service, owner, state, namespace)


@pytest.mark.parametrize("offset", [0, 1])
def test_preparation_authentic_preexisting_source(
    preparation_publisher, monkeypatch, offset
):
    publisher, first, second = preparation_publisher
    service = Service(publisher)  # Both source publications predate construction.
    owner, state, namespace = (
        service._history_owner,
        service._committed,
        service._namespace,
    )
    source_state = publisher._committed
    request = assessment_request(first)
    started = first.available_at + timedelta(seconds=offset)
    for name in (
        "uuid4",
        "_encode_result",
        "_public_result_copy",
        "_reconstruct_result",
    ):
        monkeypatch.setattr(app, name, forbidden)
    prepared = service._prepare_assessment(request, started)
    assert type(prepared) is app._PreparedAssessment
    assert tuple(field.name for field in fields(prepared)) == (
        "request",
        "source_projection",
        "assessment",
        "interpretation_available_at",
        "started",
    )
    assert not hasattr(prepared, "__dict__")
    with pytest.raises(FrozenInstanceError):
        prepared.started = TIME
    assert prepared.request == request and prepared.request is not request
    assert prepared.request.artifact_reference is not request.artifact_reference
    assert prepared.source_projection == first.to_dict()
    assert prepared.source_projection != second.to_dict()  # No latest substitution.
    assert prepared.interpretation_available_at == first.available_at
    assert prepared.started == started
    content = prepared.assessment
    assert content.source_interpretation_occurrence == request
    assert (
        content.source_interpretation_occurrence.interpretation_fingerprint
        == first.fingerprint
    )
    assert (
        content.source_interpretation_content_fingerprint
        == first.interpretation.fingerprint
    )
    assert first.fingerprint != first.interpretation.fingerprint
    for name in (
        "canonical_instrument_id",
        "source_trading_identity",
        "analysis_as_of",
        "source_quality",
        "source_warnings",
    ):
        assert getattr(content, name) == getattr(first.interpretation, name)
    domain.validate_governed_daily_technical_assessment(
        content=content,
        interpretation=first.interpretation,
        source_interpretation_occurrence=request,
    )
    assert all(not isinstance(item, Enum) for item in graph(prepared))
    assert_unprepared_authority(service, owner, state, namespace)
    assert publisher._committed is source_state is publisher._history_owner._state
    assert publisher._history_owner._pending is None
    repeated = service._prepare_assessment(request, started)
    assert repeated.assessment.to_dict() == content.to_dict()
    prepared.source_projection["interpretation"]["source_quality"] = "changed"
    assert repeated.source_projection == first.to_dict()
    assert not mutable_ids(prepared) & mutable_ids(repeated)
    assert_unprepared_authority(service, owner, state, namespace)


def test_preparation_later_publication_and_initially_empty(interpretation_authentic):  # noqa: F811
    publisher = interpretation_service(interpretation_authentic)
    service = Service(publisher)
    request = interpretation_request(interpretation_authentic[1])
    unavailable = content().source_interpretation_occurrence
    prepare_refusal(
        service,
        unavailable,
        interpretation_authentic[1].available_at,
        R.INTERPRETATION_UNAVAILABLE,
    )
    first = publisher.execute(request)
    assert (
        service._prepare_assessment(
            assessment_request(first), first.available_at
        ).source_projection
        == first.to_dict()
    )
    publisher._clock = lambda: first.available_at + timedelta(seconds=1)
    second = publisher.execute(request)
    prepared = service._prepare_assessment(
        assessment_request(second), second.available_at
    )
    assert prepared.source_projection == second.to_dict()
    assert (
        service._prepare_assessment(
            assessment_request(first), first.available_at
        ).source_projection
        == first.to_dict()
    )


def test_preparation_equal_content_distinct_publications(preparation_publisher):
    publisher, first, second = preparation_publisher
    service = Service(publisher)
    one = service._prepare_assessment(assessment_request(first), first.available_at)
    two = service._prepare_assessment(assessment_request(second), second.available_at)
    assert first.interpretation.to_dict() == second.interpretation.to_dict()
    assert (
        one.assessment.source_interpretation_content_fingerprint
        == two.assessment.source_interpretation_content_fingerprint
    )
    assert one.assessment.fingerprint != two.assessment.fingerprint
    assert (
        one.request.interpretation_fingerprint != two.request.interpretation_fingerprint
    )
    assert service._committed == (1, ())


@pytest.mark.parametrize("kind", ["object", "mapping", "namespace", "subclass"])
def test_preparation_exact_request_type(preparation_publisher, monkeypatch, kind):
    publisher, first, _ = preparation_publisher
    service = Service(publisher)
    request = assessment_request(first)
    supplied = {
        "object": object(),
        "mapping": request.to_dict(),
        "namespace": SimpleNamespace(**_interpretation_selectors(first)),
        "subclass": type("RequestSubclass", (type(request),), {})(
            **_interpretation_selectors(first)
        ),
    }[kind]
    monkeypatch.setattr(service, "_lock_inputs", forbidden)
    with pytest.raises(TypeError, match="exact Assessment"):
        service._prepare_assessment(supplied, first.available_at)


@pytest.mark.parametrize(
    "selector",
    [field.name for field in fields(domain.PolygonCompletedDailyAssessmentRequest)],
)
def test_preparation_missing_exact_selector(
    preparation_publisher, monkeypatch, selector
):
    publisher, first, _ = preparation_publisher
    service = Service(publisher)
    selectors = _interpretation_selectors(first)
    value = selectors[selector]
    if selector == "artifact_reference":
        value = replace(value, artifact_version="9.0.0")
    elif selector == "interpretation_history_sequence":
        value += 10
    elif selector == "interpretation_fingerprint":
        value = first.interpretation.fingerprint
    else:
        value = value[:-32] + "f" * 32
    monkeypatch.setattr(
        domain, "assess_governed_daily_technical_interpretation", forbidden
    )
    prepare_refusal(
        service,
        assessment_request(first, **{selector: value}),
        first.available_at,
        R.INTERPRETATION_UNAVAILABLE,
    )


def test_preparation_source_unavailable_by_start(preparation_publisher, monkeypatch):
    publisher, first, _ = preparation_publisher
    service = Service(publisher)
    monkeypatch.setattr(
        domain, "assess_governed_daily_technical_interpretation", forbidden
    )
    prepare_refusal(
        service,
        assessment_request(first),
        first.available_at - timedelta(microseconds=1),
        R.INTERPRETATION_UNAVAILABLE,
    )


@pytest.mark.parametrize(
    "started",
    [
        TIME.replace(tzinfo=None),
        TIME.astimezone(timezone(timedelta(hours=8))),
        TIME.replace(tzinfo=timezone(timedelta(0), "other")),
        TIME.isoformat(),
        type("DateSubclass", (datetime,), {})(2026, 1, 2, tzinfo=UTC),
        None,
    ],
)
def test_preparation_canonical_start(preparation_publisher, monkeypatch, started):
    publisher, first, _ = preparation_publisher
    service = Service(publisher)
    monkeypatch.setattr(service, "_lock_inputs", forbidden)
    prepare_refusal(service, assessment_request(first), started, R.TEMPORAL_FAILURE)


def test_preparation_detaches_before_lock_and_semantic_work(
    preparation_publisher, monkeypatch
):
    publisher, first, _ = preparation_publisher
    service = Service(publisher)
    request = assessment_request(first)
    expected = request.to_dict()
    original = service._lock_inputs

    def lock_inputs(stack):
        object.__setattr__(request, "interpretation_history_sequence", 999)
        object.__setattr__(request.artifact_reference, "artifact_version", "changed")
        return original(stack)

    monkeypatch.setattr(service, "_lock_inputs", lock_inputs)
    prepared = service._prepare_assessment(request, first.available_at)
    assert prepared.request.to_dict() == expected
    assert prepared.assessment.source_interpretation_occurrence.to_dict() == expected


def test_preparation_order_selectors_and_complete_locks(
    preparation_publisher, monkeypatch
):
    publisher, first, _ = preparation_publisher
    service = Service(publisher)
    technical = publisher._technical_service
    bridge = technical._bridge_service
    qualified = bridge._qualification_service
    validity = qualified._validity_service
    admission = validity._admission_service
    locks = [
        admission._construction_service._history._lock,
        admission._validation_service._history._lock,
        admission._freshness_service._history._lock,
        admission._history._lock,
        validity._history._lock,
        qualified._history._lock,
        bridge._history._lock,
        technical._history._lock,
        publisher._history_owner._lock,
        service._history_owner._lock,
    ]
    entries, events, compositions, sources = [], [], [], []
    original_locks = publisher._lock_inputs
    original_assessment_locks = service._lock_inputs
    authenticate = publisher._authenticate_interpretation_occurrence
    assess = domain.assess_governed_daily_technical_interpretation
    validate = domain.validate_governed_daily_technical_assessment
    request = assessment_request(first)

    class NonrecursiveStack(ExitStack):
        def enter_context(self, lock):
            assert lock.acquire(blocking=False), "recursive input lock acquisition"
            entries.append(lock)
            self.callback(lock.release)

    def locked():
        assert entries == locks
        assert all(lock.locked() for lock in locks)

    def compose(stack):
        compositions.append("interpretation")
        original_locks(stack)

    def assessment_locks(stack):
        compositions.append("assessment")
        return original_assessment_locks(stack)

    def authentication(**selectors):
        locked()
        events.append("authenticate")
        assert set(selectors) == set(_interpretation_selectors(first))
        assert selectors == _interpretation_selectors(first)
        assert selectors["artifact_reference"] is not request.artifact_reference
        source = authenticate(**selectors)  # Real Slice 2 publisher authority.
        sources.append(source)
        return source

    def assessment(**kwargs):
        locked()
        events.append("assess")
        assert set(kwargs) == {"interpretation", "source_interpretation_occurrence"}
        assert kwargs["interpretation"] is sources[0].interpretation
        assert kwargs["source_interpretation_occurrence"] == request
        assert kwargs["source_interpretation_occurrence"] is not request
        return assess(**kwargs)

    def validation(**kwargs):
        locked()
        events.append("validate")
        assert set(kwargs) == {
            "content",
            "interpretation",
            "source_interpretation_occurrence",
        }
        return validate(**kwargs)

    monkeypatch.setattr(app, "ExitStack", NonrecursiveStack)
    monkeypatch.setattr(service, "_lock_inputs", assessment_locks)
    monkeypatch.setattr(publisher, "_lock_inputs", compose)
    monkeypatch.setattr(
        publisher, "_authenticate_interpretation_occurrence", authentication
    )
    monkeypatch.setattr(
        domain, "assess_governed_daily_technical_interpretation", assessment
    )
    monkeypatch.setattr(
        domain, "validate_governed_daily_technical_assessment", validation
    )
    service._prepare_assessment(request, first.available_at)
    assert events == ["authenticate", "assess", "validate", "validate", "authenticate"]
    assert compositions == ["assessment", "interpretation"]
    assert sources[0] is not sources[1]
    assert sources[0].to_dict() == sources[1].to_dict()
    assert entries == locks and len({id(lock) for lock in locks}) == 10
    assert not any(lock.locked() for lock in locks)


@pytest.mark.parametrize(
    "change",
    ["outcome", "findings", "source_quality", "source_fingerprint", "occurrence"],
)
def test_preparation_independent_validation_rejects_coherent_entry_result(
    preparation_publisher, monkeypatch, change
):
    publisher, first, second = preparation_publisher
    service = Service(publisher)
    assess = domain.assess_governed_daily_technical_interpretation

    def altered(**kwargs):
        content = assess(**kwargs)
        changes = {
            "outcome": {
                "outcome": "mixed" if content.outcome != "mixed" else "aligned"
            },
            "findings": {
                "findings": ()
                if content.findings
                else (
                    domain.GovernedDailyTechnicalAssessmentFinding(
                        "caution", "source_quality_degraded", ()
                    ),
                )
            },
            "source_quality": {
                "source_quality": "complete"
                if content.source_quality == "degraded"
                else "degraded"
            },
            "source_fingerprint": {
                "source_interpretation_content_fingerprint": first.fingerprint
            },
            "occurrence": {
                "source_interpretation_occurrence": assessment_request(second)
            },
        }
        value = replace(content, **changes[change])
        value.to_dict()  # Internally coherent content still requires correspondence.
        return value

    monkeypatch.setattr(
        domain, "assess_governed_daily_technical_interpretation", altered
    )
    prepare_refusal(
        service, assessment_request(first), first.available_at, R.SEMANTIC_FAILED
    )


@pytest.mark.parametrize(
    "boundary",
    [
        "assess_governed_daily_technical_interpretation",
        "validate_governed_daily_technical_assessment",
    ],
)
def test_preparation_semantic_exception(preparation_publisher, monkeypatch, boundary):
    publisher, first, _ = preparation_publisher
    service = Service(publisher)

    def failed(**kwargs):
        raise RuntimeError("semantic boundary failed")

    monkeypatch.setattr(domain, boundary, failed)
    prepare_refusal(
        service, assessment_request(first), first.available_at, R.SEMANTIC_FAILED
    )


@pytest.mark.parametrize("change", ["other_occurrence", "projection", "missing"])
def test_preparation_source_reauthentication_change(
    preparation_publisher, monkeypatch, change
):
    publisher, first, second = preparation_publisher
    service = Service(publisher)
    authenticate = publisher._authenticate_interpretation_occurrence
    calls = []

    def changed(**selectors):
        calls.append(selectors)
        source = authenticate(**selectors)
        if len(calls) == 2:
            if change == "missing":
                raise ValueError("source support no longer available")
            if change == "other_occurrence":
                return authenticate(**_interpretation_selectors(second))
            object.__setattr__(
                source, "available_at", source.available_at + timedelta(seconds=1)
            )
            object.__setattr__(
                source, "fingerprint", canonical_fingerprint(source._payload())
            )
        return source

    monkeypatch.setattr(publisher, "_authenticate_interpretation_occurrence", changed)
    prepare_refusal(
        service, assessment_request(first), first.available_at, R.SOURCE_MISMATCH
    )
    assert len(calls) == 2 and calls[0] == calls[1]


@pytest.mark.parametrize("change", ["request", "nested_request", "source", "content"])
def test_preparation_persistent_semantic_input_or_output_change(
    preparation_publisher, monkeypatch, change
):
    publisher, first, _ = preparation_publisher
    service = Service(publisher)
    validate = domain.validate_governed_daily_technical_assessment
    calls = []

    def changed(**kwargs):
        validate(**kwargs)
        calls.append(1)
        if len(calls) != 2:  # Alter after the independent application validation.
            return
        if change == "request":
            object.__setattr__(
                kwargs["source_interpretation_occurrence"],
                "interpretation_history_sequence",
                999,
            )
        elif change == "nested_request":
            ref = kwargs["source_interpretation_occurrence"].artifact_reference
            object.__setattr__(ref, "artifact_version", "9.0.0")
            object.__setattr__(
                ref, "fingerprint", canonical_fingerprint(ref._fingerprint_payload())
            )
        else:
            value = (
                kwargs["interpretation"] if change == "source" else kwargs["content"]
            )
            object.__setattr__(
                value,
                "source_quality",
                "complete" if value.source_quality == "degraded" else "degraded",
            )
            object.__setattr__(
                value,
                "fingerprint",
                canonical_fingerprint(value._fingerprint_payload()),
            )

    monkeypatch.setattr(domain, "validate_governed_daily_technical_assessment", changed)
    prepare_refusal(
        service,
        assessment_request(first),
        first.available_at,
        R.SEMANTIC_FAILED if change == "content" else R.SOURCE_MISMATCH,
    )
    assert calls == [1, 1]


@pytest.mark.parametrize("phase", ["before", "semantic", "reauthentication"])
@pytest.mark.parametrize(
    "change",
    [
        "owner",
        "namespace",
        "owner_namespace",
        "committed",
        "owner_state",
        "both_states",
        "pending",
    ],
)
def test_preparation_authority_change_refused(
    preparation_publisher, monkeypatch, phase, change
):
    publisher, first, _ = preparation_publisher
    service = Service(publisher)
    owner, state, namespace = (
        service._history_owner,
        service._committed,
        service._namespace,
    )

    def alter():
        if change == "owner":
            replacement = app._AssessmentHistory()
            replacement._namespace_id = namespace
            replacement._state = state
            monkeypatch.setattr(
                service,
                "_PolygonCompletedDailyProductionAssessmentApplicationService__history_owner",
                replacement,
            )
        elif change == "namespace":
            monkeypatch.setattr(
                service,
                "_PolygonCompletedDailyProductionAssessmentApplicationService__namespace",
                NAMESPACE,
            )
        elif change == "owner_namespace":
            monkeypatch.setattr(owner, "_namespace_id", NAMESPACE)
        elif change == "pending":
            monkeypatch.setattr(owner, "_pending", result())
        else:
            replacement = tuple(list(state))
            if change in ("committed", "both_states"):
                monkeypatch.setattr(service, "_committed", replacement)
            if change in ("owner_state", "both_states"):
                monkeypatch.setattr(owner, "_state", replacement)

    if phase == "before":
        # Capture originals at workflow entry, then alter at the lock boundary.
        original = service._lock_inputs

        def locked(stack):
            publisher = original(stack)
            alter()
            return publisher

        monkeypatch.setattr(service, "_lock_inputs", locked)
    elif phase == "semantic":
        original = domain.assess_governed_daily_technical_interpretation

        def assess(**kwargs):
            value = original(**kwargs)
            alter()
            return value

        monkeypatch.setattr(
            domain, "assess_governed_daily_technical_interpretation", assess
        )
    else:
        original = publisher._authenticate_interpretation_occurrence
        calls = []

        def authenticate(**kwargs):
            value = original(**kwargs)
            calls.append(1)
            if len(calls) == 2:
                alter()
            return value

        monkeypatch.setattr(
            publisher, "_authenticate_interpretation_occurrence", authenticate
        )
    with pytest.raises(Refused) as caught:
        service._prepare_assessment(assessment_request(first), first.available_at)
    assert caught.value.reason == R.HISTORY_INVALID
    assert state == (1, ())  # No repair, adoption or publication of changed state.
    if change not in ("committed", "both_states"):
        assert service._committed is state
    if change not in ("owner_state", "both_states"):
        assert owner._state is state
    if change != "pending":
        assert owner._pending is None


@pytest.mark.parametrize(
    "selector",
    [field.name for field in fields(domain.PolygonCompletedDailyAssessmentRequest)],
)
def test_preparation_checks_returned_source_selectors(
    preparation_publisher, monkeypatch, selector
):
    publisher, first, _ = preparation_publisher
    service = Service(publisher)
    value = _interpretation_selectors(first)[selector]
    if selector == "artifact_reference":
        value = replace(value, artifact_version="9.0.0")
    elif selector == "interpretation_history_sequence":
        value += 1
    elif selector == "interpretation_fingerprint":
        value = first.interpretation.fingerprint
    else:
        value = value[:-32] + "f" * 32
    authenticate = publisher._authenticate_interpretation_occurrence
    monkeypatch.setattr(
        publisher,
        "_authenticate_interpretation_occurrence",
        lambda **kwargs: authenticate(**_interpretation_selectors(first)),
    )
    monkeypatch.setattr(
        domain, "assess_governed_daily_technical_interpretation", forbidden
    )
    prepare_refusal(
        service,
        assessment_request(first, **{selector: value}),
        first.available_at,
        R.SOURCE_MISMATCH,
    )


@pytest.mark.parametrize("workflow", ["prepare", "execute", "history"])
def test_preparation_no_upstream_execution_or_legacy_assessment(
    preparation_publisher, monkeypatch, workflow
):
    from market_platform.application import (
        polygon_completed_daily_production_bridge as b,
    )
    from market_platform.data.providers.polygon import PolygonProvider
    from market_platform.research import daily_technical_assessment as classic
    from market_platform.research import daily_technical_interpretation as legacy
    from market_platform.research import (
        governed_daily_technical_interpretation as governed,
    )
    from market_platform.research.classic_daily_technical import (
        ClassicDailyTechnicalAssessmentPolicy,
    )

    publisher, first, _ = preparation_publisher
    service = Service(publisher, execution_clock=lambda: first.available_at)
    if workflow == "history":
        service.execute(assessment_request(first))
    technical = publisher._technical_service
    bridge = technical._bridge_service
    qualified = bridge._qualification_service
    validity = qualified._validity_service
    admission = validity._admission_service
    for owner, names in (
        (
            Publisher,
            (
                "execute",
                "get_result_history_as_of",
                "_check_history",
                "_observe_technical_history",
                "_publish",
            ),
        ),
        (i, ("_check_content",)),
        (
            governed,
            (
                "interpret_governed_daily_technical_snapshot",
                "validate_governed_daily_technical_interpretation",
                "classic_states",
                "build_classic_comparison_evidence",
            ),
        ),
        (legacy, ("classic_states", "build_classic_comparison_evidence")),
        (classic, ("assess_daily_technical_interpretation",)),
        (ClassicDailyTechnicalAssessmentPolicy, ("assess",)),
        (t.technical, ("analyze_daily_technical_snapshot",)),
        (type(technical), ("execute", "get_result_history_as_of")),
        (type(bridge), ("bridge", "get_bridge_history_as_of")),
        (b, ("_convert_material", "_prepare", "prepare_completed_daily_price_series")),
        (type(qualified), ("qualify",)),
        (b.q, ("_qualify_material",)),
        (b.q.evaluation, ("evaluate_evidence_admission_as_of",)),
        (type(admission), ("issue_admission",)),
        (type(validity), ("issue_initial_active",)),
        (type(admission._validation_service), ("execute_profile",)),
        (type(admission._freshness_service), ("execute_task", "execute_admission")),
        (PolygonProvider, ("get_daily_prices", "get_completed_daily_acquisition")),
        (app.a, ("_utc_now",)),
    ):
        for name in names:
            monkeypatch.setattr(owner, name, forbidden)
    owner = service._history_owner
    state, namespace = service._committed, service._namespace
    if workflow == "execute":
        assert service.execute(assessment_request(first)).history_sequence == 1
        return
    if workflow == "history":
        monkeypatch.setattr(
            domain, "assess_governed_daily_technical_interpretation", forbidden
        )
        monkeypatch.setattr(app, "uuid4", forbidden)
        monkeypatch.setattr(service, "_clock", forbidden)
        assert (
            len(
                service.get_result_history_as_of(
                    assessment_request(first).artifact_reference,
                    knowledge_as_of=first.available_at,
                )
            )
            == 1
        )
        assert service._history_owner is owner
        assert service._namespace is owner._namespace_id is namespace
        assert service._committed is owner._state is state
        assert owner._pending is None
        return
    for name in (
        "uuid4",
        "_encode_result",
        "_public_result_copy",
        "_reconstruct_result",
    ):
        monkeypatch.setattr(app, name, forbidden)
    prepared = service._prepare_assessment(
        assessment_request(first), first.available_at
    )
    assert prepared.source_projection == first.to_dict()
    assert list(inspect.signature(service._prepare_assessment).parameters) == [
        "request",
        "started",
    ]
    assert_unprepared_authority(service, owner, state, namespace)


def test_preparation_lost_retained_source_support(preparation_publisher, monkeypatch):
    publisher, first, _ = preparation_publisher
    service = Service(publisher)
    assess = domain.assess_governed_daily_technical_interpretation

    def lost(**kwargs):
        value = assess(**kwargs)
        monkeypatch.setattr(publisher._technical_service._history, "_state", (1, ()))
        return value

    monkeypatch.setattr(domain, "assess_governed_daily_technical_interpretation", lost)
    prepare_refusal(
        service, assessment_request(first), first.available_at, R.HISTORY_INVALID
    )


def test_preparation_requires_idle_structurally_valid_assessment_history(
    preparation_publisher, monkeypatch
):
    publisher, first, _ = preparation_publisher
    service = Service(publisher)
    owner = service._history_owner
    owner._pending = result()
    monkeypatch.setattr(publisher, "_authenticate_interpretation_occurrence", forbidden)
    with pytest.raises(Refused) as caught:
        service._prepare_assessment(assessment_request(first), first.available_at)
    assert caught.value.reason == R.HISTORY_INVALID
    assert (
        owner._pending is not None
    )  # Preparation cannot clear another operation's state.
    owner._pending = None
    owner._state = tuple(list(service._committed))
    with pytest.raises(Refused) as caught:
        service._prepare_assessment(assessment_request(first), first.available_at)
    assert caught.value.reason == R.HISTORY_INVALID


@pytest.mark.parametrize(
    "change,expected",
    [
        ("selector", R.INTERPRETATION_UNAVAILABLE),
        ("owner", R.HISTORY_INVALID),
        ("commitment", R.HISTORY_INVALID),
        ("inventory", R.HISTORY_INVALID),
        ("technical", R.HISTORY_INVALID),
        ("bridge", R.HISTORY_INVALID),
        ("qualification", R.HISTORY_INVALID),
        ("lineage", R.SOURCE_MISMATCH),
    ],
)
def test_preparation_private_failure_categories_before_first_authentication(
    preparation_publisher, monkeypatch, change, expected
):
    from test_polygon_completed_daily_production_interpretation import (
        _private_authentication_failure_case,
    )

    publisher, first, _ = preparation_publisher
    service = Service(publisher)
    selectors = _private_authentication_failure_case(
        publisher, first, monkeypatch, change
    )
    monkeypatch.setattr(
        domain, "assess_governed_daily_technical_interpretation", forbidden
    )
    prepare_refusal(
        service,
        domain.PolygonCompletedDailyAssessmentRequest(**selectors),
        first.available_at,
        expected,
    )


def test_preparation_empty_valid_publisher_category(preparation_publisher):
    original, first, _ = preparation_publisher
    publisher = Publisher(
        original._technical_service, execution_clock=lambda: first.available_at
    )
    assert publisher._committed == (1, ())
    request = assessment_request(
        first, interpretation_history_namespace_id=publisher._namespace
    )
    prepare_refusal(
        Service(publisher), request, first.available_at, R.INTERPRETATION_UNAVAILABLE
    )


@pytest.mark.parametrize("phase", [1, 2])
@pytest.mark.parametrize(
    "category,expected",
    [
        (i._InterpretationOccurrenceUnavailable, R.INTERPRETATION_UNAVAILABLE),
        (i._InterpretationHistoryInvalid, R.HISTORY_INVALID),
        (i._InterpretationSourceMismatch, R.SOURCE_MISMATCH),
    ],
)
def test_preparation_maps_structured_failures_at_both_authentications(
    preparation_publisher, monkeypatch, phase, category, expected
):
    publisher, first, _ = preparation_publisher
    service = Service(publisher)
    fact = i._encode_result(first)
    calls = []

    def authenticate(**selectors):
        calls.append(selectors)
        if len(calls) == phase:
            raise category("same message for every category")
        return i._reconstruct_result(fact)

    monkeypatch.setattr(
        publisher, "_authenticate_interpretation_occurrence", authenticate
    )
    prepare_refusal(service, assessment_request(first), first.available_at, expected)
    assert len(calls) == phase


def _locking_publisher():
    publisher = object.__new__(Publisher)
    locks = [Lock() for _ in range(8)]
    publisher._history_owner = i._InterpretationHistory()

    def technical_locks(stack):
        for lock in locks:
            stack.enter_context(lock)

    publisher._technical_service = SimpleNamespace(_lock_inputs=technical_locks)
    return publisher, [*locks, publisher._history_owner._lock]


@pytest.mark.parametrize("phase", ["before", "locking", "semantic"])
@pytest.mark.parametrize("restore", [False, True])
def test_preparation_pinned_publisher_read_surface_cannot_redirect_locks(
    preparation_publisher, monkeypatch, phase, restore
):
    _, first, _ = preparation_publisher
    original, original_locks = _locking_publisher()
    replacement, replacement_locks = _locking_publisher()
    service = Service(original)
    expected = [*original_locks, service._history_owner._lock]
    entries, compositions, authentications = [], [], []
    fact = i._encode_result(first)
    compose = original._lock_inputs
    assess = domain.assess_governed_daily_technical_interpretation

    class RecordingStack(ExitStack):
        def enter_context(self, lock):
            assert lock.acquire(blocking=False), "recursive lock acquisition"
            entries.append(lock)
            self.callback(lock.release)

    def replace_surface():
        with pytest.raises(AttributeError):
            service._interpretation_service = replacement
        # A data descriptor must also ignore a same-named instance dictionary entry.
        vars(service)["_interpretation_service"] = replacement
        assert service._interpretation_service is original
        if restore:
            vars(service).pop("_interpretation_service")

    def lock_inputs(stack):
        compositions.append(original)
        if phase == "locking":
            replace_surface()
        compose(stack)

    def authenticate(**selectors):
        assert entries == expected
        assert all(lock.locked() for lock in original_locks)
        assert expected[-1].locked()
        assert not any(lock.locked() for lock in replacement_locks)
        authentications.append(original)
        return i._reconstruct_result(fact)

    def assessment(**kwargs):
        if phase == "semantic":
            replace_surface()
        return assess(**kwargs)

    monkeypatch.setattr(app, "ExitStack", RecordingStack)
    monkeypatch.setattr(original, "_lock_inputs", lock_inputs)
    monkeypatch.setattr(
        original, "_authenticate_interpretation_occurrence", authenticate
    )
    monkeypatch.setattr(replacement, "_lock_inputs", forbidden)
    monkeypatch.setattr(
        replacement, "_authenticate_interpretation_occurrence", forbidden
    )
    monkeypatch.setattr(
        domain, "assess_governed_daily_technical_interpretation", assessment
    )
    if phase == "before":
        replace_surface()
    prepared = service._prepare_assessment(
        assessment_request(first), first.available_at
    )
    assert prepared.source_projection == first.to_dict()
    assert entries == expected and len(entries) == 10
    assert compositions == [original]
    assert authentications == [original, original]
    assert not any(lock.locked() for lock in expected + replacement_locks)


@pytest.mark.parametrize("restore", [False, True])
@pytest.mark.parametrize(
    "phase",
    [
        "selection",
        "locking",
        "first_authentication",
        "semantic",
        "second_authentication",
    ],
)
def test_preparation_publisher_root_rechecked_against_acquired_chain(
    preparation_publisher, monkeypatch, phase, restore
):
    _, first, _ = preparation_publisher
    original, original_locks = _locking_publisher()
    replacement, replacement_locks = _locking_publisher()
    service = Service(original)
    root = (
        "_PolygonCompletedDailyProductionAssessmentApplicationService"
        "__interpretation_service"
    )
    entries, calls = [], []
    fact = i._encode_result(first)
    compose = original._lock_inputs
    assessment_locks = service._lock_inputs
    assess = domain.assess_governed_daily_technical_interpretation

    class RecordingStack(ExitStack):
        def enter_context(self, lock):
            assert lock.acquire(blocking=False), "recursive lock acquisition"
            entries.append(lock)
            self.callback(lock.release)

    def change_root():
        monkeypatch.setattr(service, root, replacement)
        if restore:
            monkeypatch.setattr(service, root, original)

    def select(stack):
        # Simulate a lock-selection wrapper choosing another root then restoring it.
        monkeypatch.setattr(service, root, replacement)
        selected = assessment_locks(stack)
        monkeypatch.setattr(service, root, original)
        return selected

    def locking(stack):
        monkeypatch.setattr(service, root, replacement)
        compose(stack)
        if restore:
            monkeypatch.setattr(service, root, original)

    def authenticate(**selectors):
        calls.append(original)
        assert entries == [*original_locks, service._history_owner._lock]
        assert all(lock.locked() for lock in entries)
        assert not any(lock.locked() for lock in replacement_locks)
        if phase == (
            "first_authentication" if len(calls) == 1 else "second_authentication"
        ):
            change_root()
        return i._reconstruct_result(fact)

    def assessment(**kwargs):
        value = assess(**kwargs)
        if phase == "semantic":
            change_root()
        return value

    monkeypatch.setattr(app, "ExitStack", RecordingStack)
    monkeypatch.setattr(
        original, "_authenticate_interpretation_occurrence", authenticate
    )
    monkeypatch.setattr(
        replacement, "_authenticate_interpretation_occurrence", forbidden
    )
    monkeypatch.setattr(
        domain, "assess_governed_daily_technical_interpretation", assessment
    )
    if phase == "selection":
        monkeypatch.setattr(service, "_lock_inputs", select)
    elif phase == "locking":
        monkeypatch.setattr(original, "_lock_inputs", locking)
    if restore and phase != "selection":
        service._prepare_assessment(assessment_request(first), first.available_at)
        assert calls == [original, original]
    else:
        prepare_refusal(
            service, assessment_request(first), first.available_at, R.HISTORY_INVALID
        )
        if phase in ("selection", "locking"):
            assert not calls
    assert len(entries) == 10 and entries[-1] is service._history_owner._lock
    assert not any(
        lock.locked() for lock in original_locks + replacement_locks + entries
    )


def execution_service(preparation_publisher, clock=None):
    publisher, source, _ = preparation_publisher
    return Service(publisher, execution_clock=clock or (lambda: source.available_at))


def execution_refusal(service, request, reason):
    owner, state = service._history_owner, service._committed
    inventory = tuple(state[1])
    with pytest.raises(Refused) as caught:
        service.execute(request)
    assert caught.value.reason == reason
    assert service._committed is owner._state is state
    assert state[1] == inventory
    assert all(type(fact) is bytes for fact in state[1])
    assert owner._pending is None


@pytest.fixture
def publication_case(preparation_publisher, monkeypatch):
    # Real source publication, mocked authentication boundary for seam matrices.
    publisher, source, _ = preparation_publisher
    fact = i._encode_result(source)

    def authenticate(**selectors):
        assert selectors == _interpretation_selectors(source)
        return i._reconstruct_result(fact)

    monkeypatch.setattr(
        publisher, "_authenticate_interpretation_occurrence", authenticate
    )
    service = execution_service(preparation_publisher)
    return service, assessment_request(source), source


def test_execute_authentic_repeated_occurrences_and_public_mutation(
    preparation_publisher,
):
    service = execution_service(preparation_publisher)
    source = preparation_publisher[1]
    request = assessment_request(source)
    first = service.execute(request)
    first_fact = service._committed[1][0]
    expected = first.assessment.to_dict()
    second = service.execute(request)
    assert [first.history_sequence, second.history_sequence] == [1, 2]
    assert first.execution_id != second.execution_id
    assert first.fingerprint != second.fingerprint
    assert first.assessment.to_dict() == second.assessment.to_dict() == expected
    assert app._encode_result(first) == first_fact
    assert type(first_fact) is bytes
    assert not mutable_ids(first) & mutable_ids(second)
    object.__setattr__(first.assessment, "outcome", "mixed")
    object.__setattr__(
        first.assessment,
        "fingerprint",
        canonical_fingerprint(first.assessment._fingerprint_payload()),
    )
    object.__setattr__(first, "fingerprint", canonical_fingerprint(first._payload()))
    first.assessment.assessment_policy_identity.configuration["changed"] = True
    third = service.execute(request)
    assert third.history_sequence == 3
    assert third.assessment.to_dict() == expected
    assert second.assessment.to_dict() == expected
    assert service._committed[1][0] == first_fact
    assert app._reconstruct_result(first_fact).assessment.to_dict() == expected
    assert service._history_owner._state is service._committed
    assert service._history_owner._pending is None


@pytest.mark.parametrize("gaps", list(product((0, 1), repeat=3)))
def test_execute_chronology_and_all_equal_boundaries(publication_case, gaps):
    service, request, source = publication_case
    instants = [source.available_at]
    for gap in gaps:
        instants.append(instants[-1] + timedelta(seconds=gap))
    ticks = iter(instants[1:])
    service._clock = lambda: next(ticks)
    value = service.execute(request)
    assert [getattr(value, name) for name in TIME_FIELDS] == instants
    assert value.interpretation_available_at <= value.execution_started_at
    assert (
        value.execution_started_at <= value.execution_completed_at <= value.available_at
    )


@pytest.mark.parametrize("clock", [0, False, "clock", object(), TIME])
def test_execute_constructor_rejects_noncallable_clock(clock):
    with pytest.raises(TypeError, match="clock must be callable"):
        Service(publisher(), execution_clock=clock)


def test_execute_constructor_clock_is_lazy_dependency(monkeypatch):
    def clock():
        forbidden()

    source = publisher()
    service = Service(source, execution_clock=clock)
    assert service._clock is clock
    assert service._interpretation_service is source
    monkeypatch.setattr(app.a, "_utc_now", clock)
    assert Service(source)._clock is clock
    assert Service(source, execution_clock=None)._clock is clock
    assert inspect.signature(Service).parameters["execution_clock"].default is None


@pytest.mark.parametrize("kind", ["none", "object", "interpretation", "subclass"])
def test_execute_exact_request_before_clock(publication_case, monkeypatch, kind):
    service, request, source = publication_case
    supplied = {
        "none": None,
        "object": object(),
        "interpretation": source.source_technical_occurrence,
        "subclass": object.__new__(type("Request", (type(request),), {})),
    }[kind]
    monkeypatch.setattr(service, "_clock", forbidden)
    monkeypatch.setattr(service, "_lock_inputs", forbidden)
    with pytest.raises(TypeError, match="exact Assessment"):
        service.execute(supplied)


def test_execute_detaches_before_start_clock(publication_case):
    service, request, source = publication_case
    expected = request.to_dict()
    calls = []

    def clock():
        if not calls:
            object.__setattr__(request, "interpretation_execution_id", "invalid")
            object.__setattr__(
                request.artifact_reference, "artifact_version", "changed"
            )
        calls.append(1)
        return source.available_at

    service._clock = clock
    value = service.execute(request)
    assert value.assessment.source_interpretation_occurrence.to_dict() == expected
    assert len(calls) == 3


@pytest.mark.parametrize("phase", [0, 1, 2])
@pytest.mark.parametrize("invalid", [None, TIME.replace(tzinfo=None), "raise"])
def test_execute_clock_failure_is_atomic_and_sequence_reused(
    publication_case, phase, invalid
):
    service, request, source = publication_case
    service.execute(request)
    calls = []

    def clock():
        calls.append(1)
        if len(calls) == phase + 1:
            if invalid == "raise":
                raise RuntimeError("clock failed")
            return invalid
        return source.available_at

    service._clock = clock
    execution_refusal(service, request, R.TEMPORAL_FAILURE)
    assert len(calls) == phase + 1
    service._clock = lambda: source.available_at
    assert service.execute(request).history_sequence == 2


@pytest.mark.parametrize("phase", ["completion", "publication", "previous"])
def test_execute_backward_clocks_reuse_sequence(publication_case, phase):
    service, request, source = publication_case
    instant = source.available_at
    service._clock = lambda: instant + timedelta(seconds=5)
    service.execute(request)
    offsets = {
        "completion": (2, 1, 6),
        "publication": (1, 2, 1),
        "previous": (0, 0, 4),
    }[phase]
    ticks = iter(instant + timedelta(seconds=n) for n in offsets)
    service._clock = lambda: next(ticks)
    execution_refusal(service, request, R.TEMPORAL_FAILURE)
    service._clock = lambda: instant + timedelta(seconds=5)
    assert service.execute(request).history_sequence == 2  # Prior R equality allowed.


def test_execute_clock_normalizes_to_canonical_utc(publication_case):
    service, request, source = publication_case
    service._clock = lambda: source.available_at.astimezone(
        timezone(timedelta(hours=8))
    )
    value = service.execute(request)
    assert all(getattr(value, name).tzinfo is UTC for name in TIME_FIELDS)


def test_execute_complete_lock_order_and_publication_seams(
    preparation_publisher, monkeypatch
):
    publisher, source, _ = preparation_publisher
    service = execution_service(preparation_publisher)
    technical = publisher._technical_service
    bridge = technical._bridge_service
    qualified = bridge._qualification_service
    validity = qualified._validity_service
    admission = validity._admission_service
    locks = [
        admission._construction_service._history._lock,
        admission._validation_service._history._lock,
        admission._freshness_service._history._lock,
        admission._history._lock,
        validity._history._lock,
        qualified._history._lock,
        bridge._history._lock,
        technical._history._lock,
        publisher._history_owner._lock,
        service._history_owner._lock,
    ]
    entries, events, compositions, graphs = [], [], [], []
    state = service._committed
    owner = service._history_owner

    class NonrecursiveStack(ExitStack):
        def enter_context(self, lock):
            assert lock.acquire(blocking=False), "recursive input lock acquisition"
            entries.append(lock)
            self.callback(lock.release)

    def locked():
        assert entries == locks
        assert all(lock.locked() for lock in locks)
        assert service._committed is owner._state is state

    def wrap(target, name, label):
        original = getattr(target, name)

        def call(*args, **kwargs):
            locked()
            events.append(label)
            value = original(*args, **kwargs)
            if label in ("copy", "decode"):
                graphs.append(value)
            return value

        monkeypatch.setattr(target, name, call)

    compose = publisher._lock_inputs

    def compose_once(stack):
        compositions.append(publisher)
        compose(stack)

    ticks = []

    def clock():
        ticks.append(1)
        if len(ticks) > 1:
            locked()
        else:
            assert not entries
        events.append(("start", "completion", "availability")[len(ticks) - 1])
        return source.available_at

    stage = owner._stage_publication

    def staging(value):
        locked()
        assert value.history_namespace_id == service._namespace == owner._namespace_id
        assert value.history_sequence == state[0]
        stage(value)
        owner._validate()
        assert service._committed is owner._state is state and state == (1, ())
        assert owner._pending is value
        graphs.append(value)
        events.append("stage")

    monkeypatch.setattr(app, "ExitStack", NonrecursiveStack)
    monkeypatch.setattr(publisher, "_lock_inputs", compose_once)
    monkeypatch.setattr(service, "_prepare_assessment", forbidden)
    monkeypatch.setattr(service, "_clock", clock)
    monkeypatch.setattr(owner, "_stage_publication", staging)
    wrap(publisher, "_authenticate_interpretation_occurrence", "authenticate")
    wrap(domain, "assess_governed_daily_technical_interpretation", "assess")
    wrap(domain, "validate_governed_daily_technical_assessment", "validate")
    wrap(app, "uuid4", "id")
    wrap(app, "_encode_result", "encode")
    wrap(app, "_reconstruct_result", "decode")
    wrap(app, "_public_result_copy", "copy")
    wrap(app, "_graph_ids", "graph")
    wrap(Result, "to_dict", "projection")
    wrap(service, "_check_authority", "authority")
    wrap(service, "_check_history", "history")
    value = service.execute(assessment_request(source))
    assert entries == locks and len(entries) == len(set(entries)) == 10
    assert compositions == [publisher]
    assert not any(lock.locked() for lock in locks)
    assert events.count("assess") == 1
    assert events.count("validate") == 2  # Domain self-check + independent app check.
    assert events.count("authenticate") == 5
    assert events.index("completion") < events.index("id") < events.index("stage")
    assert events.index("stage") < events.index("availability") < events.index("copy")
    assert (
        max(n for n, event in enumerate(events) if event == "encode") < len(events) - 1
    )
    assert events[-1] == "authenticate"
    assert all(
        index < len(events) - 1
        for index, event in enumerate(events)
        if event in ("graph", "projection", "authority", "history", "validate")
    )
    assert owner._pending is None
    for other in graphs:
        if other is not value:
            assert not mutable_ids(value) & mutable_ids(other)
    assert all(not isinstance(item, Enum) for item in graph(value))


@pytest.mark.parametrize(
    "phase", ["completion", "stage", "availability", "copy", "final", "seal"]
)
@pytest.mark.parametrize(
    "change",
    [
        "owner",
        "namespace",
        "owner_namespace",
        "committed",
        "owner_state",
        "both_states",
        "pending",
        "publisher",
    ],
)
def test_execute_authority_replacement_refused_without_adoption(
    publication_case, monkeypatch, phase, change
):
    service, request, source = publication_case
    service.execute(request)
    owner, state, namespace = (
        service._history_owner,
        service._committed,
        service._namespace,
    )
    inventory = tuple(state[1])
    root = "_PolygonCompletedDailyProductionAssessmentApplicationService"
    replacement_owner = app._AssessmentHistory()
    replacement_owner._namespace_id = namespace
    replacement_owner._state = state
    sentinel = result()
    replacement_owner._pending = sentinel
    replacement_state = tuple(list(state))
    publisher = service._interpretation_service
    calls = []

    def alter():
        calls.append(1)
        if change == "owner":
            monkeypatch.setattr(service, root + "__history_owner", replacement_owner)
        elif change == "namespace":
            monkeypatch.setattr(service, root + "__namespace", NAMESPACE)
        elif change == "owner_namespace":
            monkeypatch.setattr(owner, "_namespace_id", NAMESPACE)
        elif change == "pending":
            monkeypatch.setattr(owner, "_pending", result())
        elif change == "publisher":
            monkeypatch.setattr(
                service, root + "__interpretation_service", object.__new__(Publisher)
            )
        else:
            if change in ("committed", "both_states"):
                monkeypatch.setattr(service, "_committed", replacement_state)
            if change in ("owner_state", "both_states"):
                monkeypatch.setattr(owner, "_state", replacement_state)

    with monkeypatch.context() as seam:
        # Use a separate patch scope for the callback while retaining deliberate
        # authority corruption until explicitly asserting that it was not repaired.
        if phase in ("completion", "availability"):
            ticks = []

            def clock():
                ticks.append(1)
                if len(ticks) == (2 if phase == "completion" else 3):
                    alter()
                return source.available_at

            seam.setattr(service, "_clock", clock)
        elif phase == "stage":
            original = owner._stage_publication

            def stage(value):
                original(value)
                alter()

            seam.setattr(owner, "_stage_publication", stage)
        elif phase == "copy":
            original = app._public_result_copy

            def copied(value):
                returned = original(value)
                alter()
                return returned

            seam.setattr(app, "_public_result_copy", copied)
        else:
            original = publisher._authenticate_interpretation_occurrence
            authentications = []

            def authenticate(**selectors):
                returned = original(**selectors)
                authentications.append(1)
                if len(authentications) == (5 if phase == "seal" else 4):
                    alter()
                return returned

            seam.setattr(
                publisher, "_authenticate_interpretation_occurrence", authenticate
            )
        with pytest.raises(Refused) as caught:
            service.execute(request)
        assert caught.value.reason == R.HISTORY_INVALID
    assert calls == [1]
    assert service._committed is (
        replacement_state if change in ("committed", "both_states") else state
    )
    assert owner._state is (
        replacement_state if change in ("owner_state", "both_states") else state
    )
    assert service._committed[1] == owner._state[1] == inventory
    assert owner._pending is None
    assert replacement_owner._pending is sentinel
    # Test-controlled restoration permits reuse; the application must not repair.
    monkeypatch.setattr(service, root + "__history_owner", owner)
    monkeypatch.setattr(service, root + "__namespace", namespace)
    monkeypatch.setattr(service, root + "__interpretation_service", publisher)
    monkeypatch.setattr(service, "_committed", state)
    monkeypatch.setattr(owner, "_state", state)
    monkeypatch.setattr(owner, "_namespace_id", namespace)
    assert service.execute(request).history_sequence == 2
    assert service._committed[1][:-1] == inventory


@pytest.mark.parametrize(
    "seam,reason",
    [
        ("source", R.INTERPRETATION_UNAVAILABLE),
        ("semantic", R.SEMANTIC_FAILED),
        ("validator", R.SEMANTIC_FAILED),
        ("id", R.PUBLICATION_FAILED),
        ("stage", R.PUBLICATION_FAILED),
        ("stage_validation", R.PUBLICATION_FAILED),
        ("copy", R.PUBLICATION_FAILED),
        ("deepcopy", R.PUBLICATION_FAILED),
        ("encode", R.PUBLICATION_FAILED),
        ("decode", R.PUBLICATION_FAILED),
        ("reconstruct", R.PUBLICATION_FAILED),
        ("canonical", R.PUBLICATION_FAILED),
        ("final_history", R.HISTORY_INVALID),
    ],
)
def test_execute_failed_seams_preserve_bytes_and_reuse_sequence(
    publication_case, monkeypatch, seam, reason
):
    service, request, _ = publication_case
    service.execute(request)
    owner = service._history_owner
    inventory = service._committed[1]
    calls = []

    def failed(*args, **kwargs):
        calls.append(seam)
        raise RuntimeError("same failure text")

    with monkeypatch.context() as patch:
        if seam == "source":

            def unavailable(**selectors):
                calls.append(seam)
                raise i._InterpretationOccurrenceUnavailable("same failure text")

            patch.setattr(
                service._interpretation_service,
                "_authenticate_interpretation_occurrence",
                unavailable,
            )
        elif seam in ("semantic", "validator"):
            patch.setattr(
                domain,
                "assess_governed_daily_technical_interpretation"
                if seam == "semantic"
                else "validate_governed_daily_technical_assessment",
                failed,
            )
        elif seam == "id":
            patch.setattr(app, "uuid4", failed)
        elif seam == "stage":
            original = owner._stage_publication

            def stage(value):
                original(value)
                failed()

            patch.setattr(owner, "_stage_publication", stage)
        elif seam == "stage_validation":
            original = Result.to_dict

            def validate(value):
                if value is owner._pending:
                    failed()
                return original(value)

            patch.setattr(Result, "to_dict", validate)
        elif seam == "final_history":
            original = owner._validate

            def validate_history():
                if owner._pending is not None:
                    failed()
                original()

            patch.setattr(owner, "_validate", validate_history)
        else:
            name = {
                "copy": "_public_result_copy",
                "deepcopy": "deepcopy",
                "encode": "_encode_result",
                "decode": "_decode_result",
                "reconstruct": "_reconstruct_result",
                "canonical": "_canonical_bytes",
            }[seam]
            original = getattr(app, name)

            def publication_only(*args, **kwargs):
                if owner._pending is not None:
                    failed()
                return original(*args, **kwargs)

            patch.setattr(app, name, publication_only)
        execution_refusal(service, request, reason)
    assert calls == [seam]
    assert service.execute(request).history_sequence == 2
    assert service._committed[1][:-1] == inventory


@pytest.mark.parametrize("phase", [3, 4, 5])
@pytest.mark.parametrize(
    "category,reason",
    [
        (i._InterpretationOccurrenceUnavailable, R.INTERPRETATION_UNAVAILABLE),
        (i._InterpretationHistoryInvalid, R.HISTORY_INVALID),
        (i._InterpretationSourceMismatch, R.SOURCE_MISMATCH),
    ],
)
def test_execute_publication_authentication_categories(
    publication_case, monkeypatch, phase, category, reason
):
    service, request, _ = publication_case
    service.execute(request)
    publisher = service._interpretation_service
    original = publisher._authenticate_interpretation_occurrence
    calls = []

    def authenticate(**selectors):
        calls.append(1)
        if len(calls) == phase:
            raise category("identical message for all categories")
        return original(**selectors)

    with monkeypatch.context() as patch:
        patch.setattr(
            publisher, "_authenticate_interpretation_occurrence", authenticate
        )
        execution_refusal(service, request, reason)
    assert len(calls) == phase
    assert service.execute(request).history_sequence == 2


@pytest.mark.parametrize(
    "seam", ["completion", "stage", "availability", "copy", "final"]
)
@pytest.mark.parametrize(
    "change,reason",
    [
        ("source", R.SOURCE_MISMATCH),
        ("request", R.SOURCE_MISMATCH),
        ("prepared_source", R.SOURCE_MISMATCH),
        ("assessment", R.SEMANTIC_FAILED),
    ],
)
def test_execute_final_correspondence_is_complete(
    publication_case, monkeypatch, seam, change, reason
):
    service, request, source = publication_case
    service.execute(request)
    publisher = service._interpretation_service
    original_prepare = service._prepare_assessment_locked
    original_authenticate = publisher._authenticate_interpretation_occurrence
    prepared_values = []
    changed = []
    calls = []

    def prepare(*args):
        value = original_prepare(*args)
        prepared_values.append(value)
        return value

    def alter():
        changed.append(1)
        prepared = prepared_values[0]
        if change == "request":
            object.__setattr__(prepared.request, "interpretation_fingerprint", FP)
        elif change == "prepared_source":
            prepared.source_projection["execution_id"] = "changed"
        elif change == "assessment":
            object.__setattr__(prepared.assessment, "outcome", "mixed")
            object.__setattr__(
                prepared.assessment,
                "fingerprint",
                canonical_fingerprint(prepared.assessment._fingerprint_payload()),
            )

    def authenticate(**selectors):
        calls.append(1)
        value = original_authenticate(**selectors)
        if seam == "final" and len(calls) == 4:
            alter()
        if changed and change == "source":
            # Coherent full-envelope change, despite the exact requested selectors.
            object.__setattr__(
                value,
                "execution_id",
                "polygon_completed_daily_interpretation:" + "f" * 32,
            )
            object.__setattr__(
                value, "fingerprint", canonical_fingerprint(value._payload())
            )
        return value

    with monkeypatch.context() as patch:
        patch.setattr(service, "_prepare_assessment_locked", prepare)
        patch.setattr(
            publisher, "_authenticate_interpretation_occurrence", authenticate
        )
        if seam in ("completion", "availability"):
            ticks = []

            def clock():
                ticks.append(1)
                if len(ticks) == (2 if seam == "completion" else 3):
                    alter()
                return source.available_at

            patch.setattr(service, "_clock", clock)
        elif seam == "stage":
            original = service._history_owner._stage_publication

            def stage(value):
                original(value)
                alter()

            patch.setattr(service._history_owner, "_stage_publication", stage)
        elif seam == "copy":
            original = app._public_result_copy

            def copied(value):
                public = original(value)
                alter()
                return public

            patch.setattr(app, "_public_result_copy", copied)
        execution_refusal(service, request, reason)
    assert changed == [1]
    assert service.execute(request).history_sequence == 2


@pytest.mark.parametrize("kind", ["alias", "nested_alias", "changed", "wrong_type"])
def test_execute_public_copy_must_be_disjoint_and_exact(
    publication_case, monkeypatch, kind
):
    service, request, _ = publication_case
    service.execute(request)
    original = app._public_result_copy

    def copied(value):
        public = original(value)
        if kind == "alias":
            return value
        if kind == "nested_alias":
            object.__setattr__(
                public.assessment,
                "canonical_instrument_id",
                value.assessment.canonical_instrument_id,
            )
        elif kind == "changed":
            object.__setattr__(public, "execution_id", PREFIX + ":" + "f" * 32)
            object.__setattr__(
                public, "fingerprint", canonical_fingerprint(public._payload())
            )
        else:
            return object()
        return public

    with monkeypatch.context() as patch:
        patch.setattr(app, "_public_result_copy", copied)
        execution_refusal(service, request, R.PUBLICATION_FAILED)
    assert service.execute(request).history_sequence == 2


@pytest.mark.parametrize(
    "field",
    ["assessment", "history_sequence", "history_namespace_id", "execution_started_at"],
)
def test_execute_coherent_stage_changes_refused(publication_case, monkeypatch, field):
    service, request, _ = publication_case
    service.execute(request)
    owner = service._history_owner
    original = owner._stage_publication

    def stage(value):
        original(value)
        changes = {
            "assessment": content(),
            "history_sequence": 9,
            "history_namespace_id": NAMESPACE,
            "execution_started_at": value.execution_completed_at - timedelta(seconds=1),
        }
        object.__setattr__(value, field, changes[field])
        object.__setattr__(
            value, "fingerprint", canonical_fingerprint(value._payload())
        )

    with monkeypatch.context() as patch:
        patch.setattr(owner, "_stage_publication", stage)
        execution_refusal(service, request, R.PUBLICATION_FAILED)
    assert service.execute(request).history_sequence == 2


def test_execute_duplicate_id_does_not_retry(publication_case, monkeypatch):
    service, request, _ = publication_case
    first = service.execute(request)
    calls = []

    def duplicate():
        calls.append(1)
        return SimpleNamespace(hex=first.execution_id.split(":")[1])

    with monkeypatch.context() as patch:
        patch.setattr(app, "uuid4", duplicate)
        execution_refusal(service, request, R.PUBLICATION_FAILED)
    assert calls == [1]
    assert service.execute(request).history_sequence == 2


@pytest.mark.parametrize("failure", ["source", "semantic", "validator", "completion"])
def test_execute_does_not_allocate_id_before_successful_completion(
    publication_case, monkeypatch, failure
):
    service, request, source = publication_case
    monkeypatch.setattr(app, "uuid4", forbidden)

    def failed(*args, **kwargs):
        raise ValueError("failed before ID allocation")

    if failure == "source":

        def unavailable(**selectors):
            raise i._InterpretationOccurrenceUnavailable("missing")

        monkeypatch.setattr(
            service._interpretation_service,
            "_authenticate_interpretation_occurrence",
            unavailable,
        )
        reason = R.INTERPRETATION_UNAVAILABLE
    elif failure in ("semantic", "validator"):
        monkeypatch.setattr(
            domain,
            "assess_governed_daily_technical_interpretation"
            if failure == "semantic"
            else "validate_governed_daily_technical_assessment",
            failed,
        )
        reason = R.SEMANTIC_FAILED
    else:
        ticks = iter([source.available_at, source.available_at - timedelta(seconds=1)])
        service._clock = lambda: next(ticks)
        reason = R.TEMPORAL_FAILURE
    execution_refusal(service, request, reason)


@pytest.mark.parametrize("restore", [False, True])
@pytest.mark.parametrize("phase", ["completion", "stage", "availability", "copy"])
def test_execute_publisher_root_swap_never_redirects_acquired_locks(
    publication_case, monkeypatch, phase, restore
):
    service, request, source = publication_case
    publisher = service._interpretation_service
    replacement, replacement_locks = _locking_publisher()
    root = (
        "_PolygonCompletedDailyProductionAssessmentApplicationService"
        "__interpretation_service"
    )
    original_authenticate = publisher._authenticate_interpretation_occurrence
    calls, changes = [], []

    def alter():
        changes.append(1)
        monkeypatch.setattr(service, root, replacement)
        if restore:
            monkeypatch.setattr(service, root, publisher)

    def authenticate(**selectors):
        calls.append(publisher)
        assert publisher._history_owner._lock.locked()
        assert service._history_owner._lock.locked()
        assert not any(lock.locked() for lock in replacement_locks)
        return original_authenticate(**selectors)

    monkeypatch.setattr(replacement, "_lock_inputs", forbidden)
    monkeypatch.setattr(
        replacement, "_authenticate_interpretation_occurrence", forbidden
    )
    monkeypatch.setattr(
        publisher, "_authenticate_interpretation_occurrence", authenticate
    )
    if phase in ("completion", "availability"):
        ticks = []

        def clock():
            ticks.append(1)
            if len(ticks) == (2 if phase == "completion" else 3):
                alter()
            return source.available_at

        monkeypatch.setattr(service, "_clock", clock)
    elif phase == "stage":
        original = service._history_owner._stage_publication

        def stage(value):
            original(value)
            alter()

        monkeypatch.setattr(service._history_owner, "_stage_publication", stage)
    else:
        original = app._public_result_copy

        def copied(value):
            public = original(value)
            alter()
            return public

        monkeypatch.setattr(app, "_public_result_copy", copied)
    if restore:
        assert service.execute(request).history_sequence == 1
        assert calls == [publisher] * 5
    else:
        execution_refusal(service, request, R.HISTORY_INVALID)
    assert changes == [1]
    assert all(item is publisher for item in calls)
    assert not any(lock.locked() for lock in replacement_locks)


def test_execute_three_concurrent_authentic_occurrences(preparation_publisher):
    service = execution_service(preparation_publisher)
    request = assessment_request(preparation_publisher[1])
    owner = service._history_owner
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(service.execute, request) for _ in range(3)]
        results = [future.result(timeout=600) for future in futures]
    assert sorted(item.history_sequence for item in results) == [1, 2, 3]
    assert len({item.execution_id for item in results}) == 3
    assert len({item.fingerprint for item in results}) == 3
    assert service._history_owner is owner
    assert service._committed is owner._state
    assert owner._state[0] == 4
    assert owner._pending is None
    assert [
        app._reconstruct_result(fact).history_sequence for fact in owner._state[1]
    ] == [1, 2, 3]


def test_stage_requires_exact_completely_valid_result():
    owner = app._AssessmentHistory()
    for supplied in (object(), object.__new__(type("ResultSubclass", (Result,), {}))):
        with pytest.raises(TypeError):
            owner._stage_publication(supplied)
        assert owner._pending is None
    invalid = result()
    object.__setattr__(invalid, "fingerprint", FP)
    with pytest.raises(ValueError):
        owner._stage_publication(invalid)
    assert owner._pending is None
    assert owner._state == (1, ())


@pytest.mark.parametrize("phase", ["selection", "upstream_locking"])
@pytest.mark.parametrize("restore", [False, True])
def test_execute_lock_selection_cannot_adopt_replacement_owner_or_publisher(
    publication_case, monkeypatch, phase, restore
):
    service, request, _ = publication_case
    original = service._interpretation_service
    owner, state = service._history_owner, service._committed
    replacement, replacement_locks = _locking_publisher()
    replacement_owner = app._AssessmentHistory()
    root = "_PolygonCompletedDailyProductionAssessmentApplicationService"
    entries = []

    class NonrecursiveStack(ExitStack):
        def enter_context(self, lock):
            assert lock.acquire(blocking=False)
            entries.append(lock)
            self.callback(lock.release)

    monkeypatch.setattr(app, "ExitStack", NonrecursiveStack)
    monkeypatch.setattr(
        replacement, "_authenticate_interpretation_occurrence", forbidden
    )
    if phase == "selection":
        acquire = service._lock_inputs

        def selected(stack):
            monkeypatch.setattr(service, root + "__interpretation_service", replacement)
            publisher = acquire(stack)
            if restore:
                monkeypatch.setattr(
                    service, root + "__interpretation_service", original
                )
            return publisher

        monkeypatch.setattr(service, "_lock_inputs", selected)
    else:
        acquire = original._lock_inputs

        def upstream(stack):
            monkeypatch.setattr(service, root + "__history_owner", replacement_owner)
            acquire(stack)
            if restore:
                monkeypatch.setattr(service, root + "__history_owner", owner)

        monkeypatch.setattr(original, "_lock_inputs", upstream)
    if phase == "upstream_locking" and restore:
        assert service.execute(request).history_sequence == 1
    else:
        with pytest.raises(Refused) as caught:
            service.execute(request)
        assert caught.value.reason == R.HISTORY_INVALID
        assert service._committed is owner._state is state
        assert owner._pending is None
    assert len(entries) == 10
    assert entries[-1] is owner._lock
    assert replacement_owner._lock not in entries
    assert not any(lock.locked() for lock in entries + replacement_locks)


def test_execute_source_unavailable_by_start_does_not_allocate_id(
    publication_case, monkeypatch
):
    service, request, source = publication_case
    monkeypatch.setattr(app, "uuid4", forbidden)
    service._clock = lambda: source.available_at - timedelta(microseconds=1)
    execution_refusal(service, request, R.INTERPRETATION_UNAVAILABLE)


@pytest.mark.parametrize(
    "seam", ["id", "stage", "copy", "encode", "decode", "final_history"]
)
def test_execute_source_reauthenticated_after_each_publication_seam(
    publication_case, monkeypatch, seam
):
    service, request, _ = publication_case
    service.execute(request)
    publisher = service._interpretation_service
    original_authenticate = publisher._authenticate_interpretation_occurrence
    changed = []
    checks = []

    def authenticate(**selectors):
        checks.append(1)
        if changed:
            raise i._InterpretationHistoryInvalid("original source support lost")
        return original_authenticate(**selectors)

    owner = service._history_owner
    target, name = {
        "id": (app, "uuid4"),
        "stage": (owner, "_stage_publication"),
        "copy": (app, "_public_result_copy"),
        "encode": (app, "_encode_result"),
        "decode": (app, "_reconstruct_result"),
        "final_history": (owner, "_validate"),
    }[seam]
    original = getattr(target, name)

    def mutate(*args, **kwargs):
        value = original(*args, **kwargs)
        if seam == "id" or owner._pending is not None:
            changed.append(1)
        return value

    with monkeypatch.context() as patch:
        patch.setattr(
            publisher, "_authenticate_interpretation_occurrence", authenticate
        )
        patch.setattr(target, name, mutate)
        execution_refusal(service, request, R.HISTORY_INVALID)
    assert changed and len(checks) == (5 if seam == "final_history" else 4)
    assert service.execute(request).history_sequence == 2


def test_execute_prepared_snapshot_copy_failure_is_publication_failure(
    publication_case, monkeypatch
):
    service, request, _ = publication_case
    service.execute(request)
    prepared = []
    prepare = service._prepare_assessment_locked
    copied = app.deepcopy

    def prepare_once(*args):
        value = prepare(*args)
        prepared.append(value)
        return value

    def fail_snapshot(value):
        if prepared:
            raise RuntimeError("snapshot copy failed")
        return copied(value)

    with monkeypatch.context() as patch:
        patch.setattr(service, "_prepare_assessment_locked", prepare_once)
        patch.setattr(app, "deepcopy", fail_snapshot)
        execution_refusal(service, request, R.PUBLICATION_FAILED)
    assert len(prepared) == 1
    assert service.execute(request).history_sequence == 2


@pytest.mark.parametrize("phase", ["stage", "availability", "copy"])
def test_execute_original_pending_cleanup_survives_replacement_and_exception(
    publication_case, monkeypatch, phase
):
    service, request, source = publication_case
    service.execute(request)
    owner, state = service._history_owner, service._committed
    replacement = app._AssessmentHistory()
    replacement._pending = sentinel = result()
    root = "_PolygonCompletedDailyProductionAssessmentApplicationService__history_owner"

    def fail():
        assert owner._pending is not None
        monkeypatch.setattr(service, root, replacement)
        raise RuntimeError("callback failed after replacing owner")

    with monkeypatch.context() as patch:
        if phase == "stage":
            original = owner._stage_publication

            def stage(value):
                original(value)
                fail()

            patch.setattr(owner, "_stage_publication", stage)
        elif phase == "availability":
            ticks = []

            def clock():
                ticks.append(1)
                if len(ticks) == 3:
                    fail()
                return source.available_at

            patch.setattr(service, "_clock", clock)
        else:
            patch.setattr(app, "_public_result_copy", lambda value: fail())
        with pytest.raises(Refused):
            service.execute(request)
    assert service._committed is owner._state is state
    assert owner._pending is None
    assert replacement._pending is sentinel
    monkeypatch.setattr(service, root, owner)
    assert service.execute(request).history_sequence == 2


def test_execute_final_source_seal_follows_last_graph_validation(
    preparation_publisher, monkeypatch
):
    publisher, source, _ = preparation_publisher
    service = execution_service(preparation_publisher)
    request = assessment_request(source)
    service.execute(request)
    owner, state = service._history_owner, service._committed
    inventory = state[1]
    technical_history = publisher._technical_service._history
    support_state = technical_history._state
    authenticate = publisher._authenticate_interpretation_occurrence
    graph_ids = app._graph_ids
    events, authentications, invalidations = [], [], []

    def authenticated(**selectors):
        assert selectors == _interpretation_selectors(source)
        assert service._history_owner is owner
        assert service._committed is owner._state is state
        assert owner._lock.locked() and publisher._history_owner._lock.locked()
        if len(authentications) >= 3:
            assert owner._pending is not None
        authentications.append(1)
        events.append("authenticate")
        return authenticate(**selectors)

    with monkeypatch.context() as patch:

        def validated_graph(value):
            identities = graph_ids(value)
            if len(authentications) == 4:
                events.append("final_graph_validation")
                if not invalidations:
                    assert service._committed is owner._state is state
                    assert owner._pending is not None
                    # Remove original retained technical support after the fourth
                    # real authentication, without changing Assessment authority.
                    patch.setattr(technical_history, "_state", (1, ()))
                    invalidations.append(1)
            return identities

        patch.setattr(
            publisher, "_authenticate_interpretation_occurrence", authenticated
        )
        patch.setattr(app, "_graph_ids", validated_graph)
        with pytest.raises(Refused) as caught:
            service.execute(request)
        assert caught.value.reason == R.HISTORY_INVALID
        assert invalidations == [1]
        assert len(authentications) == 5
        assert events[-1] == "authenticate"
        assert (
            max(
                index
                for index, event in enumerate(events)
                if event == "final_graph_validation"
            )
            < len(events) - 1
        )
        assert service._committed is owner._state is state
        assert state[1] == inventory
        assert owner._pending is None
    assert technical_history._state is support_state
    retried = service.execute(request)
    assert retried.history_sequence == state[0] == 2
    assert service._committed[1][:-1] == inventory
    assert owner._pending is None


@pytest.mark.parametrize(
    "change", ["type", "namespace", "sequence", "execution_id", "fingerprint"]
)
def test_execute_final_source_seal_rejects_wrong_occurrence(
    publication_case, monkeypatch, change
):
    service, request, _ = publication_case
    service.execute(request)
    publisher = service._interpretation_service
    authenticate = publisher._authenticate_interpretation_occurrence
    calls = []

    def authenticated(**selectors):
        value = authenticate(**selectors)
        calls.append(1)
        if len(calls) == 5:
            if change == "type":
                return object()
            field, replacement = {
                "namespace": ("history_namespace_id", "changed"),
                "sequence": ("history_sequence", True),
                "execution_id": ("execution_id", "changed"),
                "fingerprint": ("fingerprint", FP),
            }[change]
            object.__setattr__(value, field, replacement)
        return value

    with monkeypatch.context() as patch:
        patch.setattr(
            publisher, "_authenticate_interpretation_occurrence", authenticated
        )
        execution_refusal(service, request, R.SOURCE_MISMATCH)
    assert len(calls) == 5
    assert service.execute(request).history_sequence == 2


def test_execute_final_source_seal_detects_removed_assessment_root(
    publication_case, monkeypatch
):
    service, request, _ = publication_case
    service.execute(request)
    owner, state = service._history_owner, service._committed
    publisher = service._interpretation_service
    authenticate = publisher._authenticate_interpretation_occurrence
    calls = []

    with monkeypatch.context() as patch:

        def authenticated(**selectors):
            value = authenticate(**selectors)
            calls.append(1)
            if len(calls) == 5:
                patch.delattr(service, "_committed")
            return value

        patch.setattr(
            publisher, "_authenticate_interpretation_occurrence", authenticated
        )
        with pytest.raises(Refused) as caught:
            service.execute(request)
        assert caught.value.reason == R.HISTORY_INVALID
        assert not hasattr(service, "_committed")  # No repair of the removed root.
        assert owner._state is state
        assert owner._pending is None
        assert len(calls) == 5
    assert service._committed is state
    assert service.execute(request).history_sequence == 2
    assert service._committed[1][:-1] == state[1]


def read_history(service, request, cutoff):
    return service.get_result_history_as_of(
        request.artifact_reference, knowledge_as_of=cutoff
    )


def history_refusal(service, request, cutoff, reason):
    owner, state = service._history_owner, service._committed
    pending, namespace = owner._pending, service._namespace
    publisher = service._interpretation_service
    with pytest.raises(Refused) as caught:
        read_history(service, request, cutoff)
    assert caught.value.reason == reason
    assert service._committed is state
    assert service._history_owner is owner
    assert owner._pending is pending
    assert service._namespace is namespace
    assert service._interpretation_service is publisher


def test_history_signature_and_slice_5_execute_ast_checkpoint():
    signature = inspect.signature(Service.get_result_history_as_of)
    assert list(signature.parameters) == [
        "self",
        "artifact_reference",
        "knowledge_as_of",
    ]
    assert signature.parameters["artifact_reference"].annotation == (
        "GovernedTechnicalArtifactReference"
    )
    assert (
        signature.parameters["knowledge_as_of"].kind is inspect.Parameter.KEYWORD_ONLY
    )
    assert signature.parameters["knowledge_as_of"].annotation == "datetime"
    assert (
        signature.return_annotation
        == "tuple[PolygonCompletedDailyAssessmentResult, ...]"
    )
    _assert_assessment_checkpoint(
        _assessment_checkpoint(), ast.parse(inspect.getsource(app))
    )


def test_history_empty_no_clock_id_stage_or_observation(
    preparation_publisher, monkeypatch
):
    service = execution_service(preparation_publisher)
    owner, state, namespace = (
        service._history_owner,
        service._committed,
        service._namespace,
    )
    publisher = service._interpretation_service
    observed, retention = publisher._observed, publisher._retention
    for target, name in (
        (service, "_clock"),
        (app, "uuid4"),
        (owner, "_stage_publication"),
        (publisher, "_observe_technical_history"),
        (publisher, "_authenticate_interpretation_occurrence"),
    ):
        monkeypatch.setattr(target, name, forbidden)
    assert (
        read_history(service, assessment_request(preparation_publisher[1]), TIME) == ()
    )
    assert_unprepared_authority(service, owner, state, namespace)
    assert publisher._observed is observed and publisher._retention is retention
    assert state[1] == ()


def test_history_inclusive_availability_and_all_occurrences(publication_case):
    service, request, source = publication_case
    start = source.available_at
    times = iter(start + timedelta(seconds=n) for n in (1, 2, 3, 4, 5, 6, 7, 8, 9))
    service._clock = lambda: next(times)
    published = [service.execute(request) for _ in range(3)]
    for index, item in enumerate(published):
        assert [
            v.history_sequence
            for v in read_history(
                service, request, item.available_at - timedelta(microseconds=1)
            )
        ] == list(range(1, index + 1))
        values = read_history(service, request, item.available_at)
        assert type(values) is tuple
        assert [v.history_sequence for v in values] == list(range(1, index + 2))
        assert [app._encode_result(v) for v in values] == list(
            service._committed[1][: index + 1]
        )
    assert len(read_history(service, request, start + timedelta(days=1))) == 3


def test_history_filters_complete_artifact_projection(publication_case, monkeypatch):
    service, request, source = publication_case
    # Mock the private boundary with two distinct, complete source projections.
    other = i._reconstruct_result(i._encode_result(source))
    reference = replace(request.artifact_reference, artifact_version="other")
    object.__setattr__(
        other,
        "interpretation",
        replace(
            other.interpretation,
            source_technical_occurrence=replace(
                other.source_technical_occurrence, artifact_reference=reference
            ),
        ),
    )
    object.__setattr__(other, "fingerprint", canonical_fingerprint(other._payload()))
    source_facts = {
        value.fingerprint: i._encode_result(value) for value in (source, other)
    }

    def authenticate(**selectors):
        value = i._reconstruct_result(
            source_facts[selectors["interpretation_fingerprint"]]
        )
        assert selectors == _interpretation_selectors(value)
        return value

    monkeypatch.setattr(
        service._interpretation_service,
        "_authenticate_interpretation_occurrence",
        authenticate,
    )
    other_request = assessment_request(other)
    for selected in (request, other_request, request):
        service.execute(selected)
    assert [
        v.history_sequence for v in read_history(service, request, source.available_at)
    ] == [1, 3]
    assert [
        v.history_sequence
        for v in read_history(service, other_request, source.available_at)
    ] == [2]
    missing = replace(
        request, artifact_reference=replace(reference, artifact_version="missing")
    )
    assert read_history(service, missing, source.available_at) == ()


@pytest.mark.parametrize(
    "kind",
    ["object", "mapping", "fingerprint", "request", "source", "result", "subclass"],
)
def test_history_requires_exact_artifact_type(publication_case, monkeypatch, kind):
    service, request, source = publication_case
    value = service.execute(request)
    supplied = {
        "object": object(),
        "mapping": request.artifact_reference.to_dict(),
        "fingerprint": request.artifact_reference.fingerprint,
        "request": request,
        "source": source,
        "result": value,
        "subclass": object.__new__(
            type("ReferenceSubclass", (app.GovernedTechnicalArtifactReference,), {})
        ),
    }[kind]
    monkeypatch.setattr(service, "_lock_inputs", forbidden)
    with pytest.raises(TypeError):
        service.get_result_history_as_of(supplied, knowledge_as_of=source.available_at)


@pytest.mark.parametrize(
    "field,value",
    [
        ("fingerprint", FP),
        ("schema_version", "invalid"),
        ("authority", String("external_origin")),
    ],
)
def test_history_validates_original_artifact_projection(publication_case, field, value):
    service, request, source = publication_case
    reference = replace(request.artifact_reference)
    object.__setattr__(reference, field, value)
    with pytest.raises((TypeError, ValueError)):
        service.get_result_history_as_of(reference, knowledge_as_of=source.available_at)


def test_history_detaches_before_projection_timestamp_and_lock(
    publication_case, monkeypatch
):
    service, request, source = publication_case
    service.execute(request)
    reference = replace(request.artifact_reference)
    project = app.GovernedTechnicalArtifactReference.to_dict
    timestamp = app.a._timestamp
    calls = []

    def projection(value):
        if not calls:
            assert value is not reference
            object.__setattr__(reference, "artifact_version", "mutated")
            calls.append("detached")
        return project(value)

    def normalize(value):
        assert calls == ["detached"]
        cutoff = timestamp(value)
        assert cutoff.tzinfo is UTC
        calls.append(cutoff)
        return cutoff

    monkeypatch.setattr(app.GovernedTechnicalArtifactReference, "to_dict", projection)
    monkeypatch.setattr(app.a, "_timestamp", normalize)
    offset_cutoff = source.available_at.astimezone(timezone(timedelta(hours=8)))
    assert (
        len(service.get_result_history_as_of(reference, knowledge_as_of=offset_cutoff))
        == 1
    )
    assert calls == ["detached", source.available_at]


@pytest.mark.parametrize(
    "cutoff", [None, "2026-01-02", 1, datetime(2026, 1, 2), object()]
)
def test_history_invalid_cutoff_is_temporal_failure(
    publication_case, monkeypatch, cutoff
):
    service, request, _ = publication_case
    monkeypatch.setattr(service, "_lock_inputs", forbidden)
    history_refusal(service, request, cutoff, R.TEMPORAL_FAILURE)


@pytest.mark.parametrize("attack", ["pending", "state", "namespace", "owner"])
def test_history_requires_idle_original_authority(
    publication_case, monkeypatch, attack
):
    service, request, source = publication_case
    value = service.execute(request)
    owner, state = service._history_owner, service._committed
    if attack == "pending":
        monkeypatch.setattr(owner, "_pending", value)
    elif attack == "state":
        replacement = (state[0], state[1])
        assert replacement == state and replacement is not state
        monkeypatch.setattr(owner, "_state", replacement)
    elif attack == "namespace":
        monkeypatch.setattr(owner, "_namespace_id", PREFIX + "_history:" + "0" * 32)
    else:
        replacement = app._AssessmentHistory()
        monkeypatch.setattr(
            service,
            "_PolygonCompletedDailyProductionAssessmentApplicationService__history_owner",
            replacement,
        )
    history_refusal(service, request, source.available_at, R.HISTORY_INVALID)
    assert service._committed is state


@pytest.mark.parametrize(
    "error,reason",
    [
        (i._InterpretationOccurrenceUnavailable, R.HISTORY_INVALID),
        (i._InterpretationHistoryInvalid, R.HISTORY_INVALID),
        (i._InterpretationSourceMismatch, R.SOURCE_MISMATCH),
    ],
)
@pytest.mark.parametrize("phase", [1, 2, 3])
def test_history_retained_private_failures_never_become_selection_unavailable(
    publication_case, monkeypatch, error, reason, phase
):
    service, request, source = publication_case
    service.execute(request)
    authenticate = (
        service._interpretation_service._authenticate_interpretation_occurrence
    )
    calls = []

    def failed(**selectors):
        calls.append(selectors)
        if len(calls) == phase:
            raise error("identical message for every structured category")
        return authenticate(**selectors)

    monkeypatch.setattr(
        service._interpretation_service,
        "_authenticate_interpretation_occurrence",
        failed,
    )
    history_refusal(service, request, source.available_at, reason)
    assert len(calls) == phase


@pytest.mark.parametrize("attack", ["bytes", "semantic", "unsupported"])
@pytest.mark.parametrize("invisible", ["future", "artifact"])
def test_history_authenticates_complete_inventory_before_filtering(
    publication_case, monkeypatch, attack, invisible
):
    service, request, source = publication_case
    service.execute(request)
    service._clock = lambda: source.available_at + timedelta(days=1)
    service.execute(request)
    state = service._committed
    if attack in ("bytes", "semantic"):
        projection = app._decode_result(state[1][1])
        if attack == "bytes":
            projection["fingerprint"] = FP
        else:
            projection["assessment"]["outcome"] = (
                "aligned"
                if projection["assessment"]["outcome"] != "aligned"
                else "mixed"
            )
            refingerprint(projection["assessment"])
            refingerprint(projection)
        changed = (3, (state[1][0], app._canonical_bytes(projection)))
        monkeypatch.setattr(service, "_committed", changed)
        monkeypatch.setattr(service._history_owner, "_state", changed)
    else:
        authenticate = (
            service._interpretation_service._authenticate_interpretation_occurrence
        )
        calls = []

        def unsupported(**selectors):
            calls.append(1)
            if len(calls) == 2:
                raise i._InterpretationOccurrenceUnavailable("lost exact source")
            return authenticate(**selectors)

        monkeypatch.setattr(
            service._interpretation_service,
            "_authenticate_interpretation_occurrence",
            unsupported,
        )
    monkeypatch.setattr(app, "_public_result_copy", forbidden)
    selected = (
        request
        if invisible == "future"
        else replace(
            request,
            artifact_reference=replace(
                request.artifact_reference, artifact_version="absent"
            ),
        )
    )
    history_refusal(service, selected, source.available_at, R.HISTORY_INVALID)


def test_history_public_graph_mutation_isolation(publication_case, monkeypatch):
    service, request, source = publication_case
    service.execute(request)
    service.execute(request)
    owner, state, namespace = (
        service._history_owner,
        service._committed,
        service._namespace,
    )
    observed, retention = (
        service._interpretation_service._observed,
        service._interpretation_service._retention,
    )
    reconstructions, validations = [], []
    reconstruct = app._reconstruct_result
    validate = domain.validate_governed_daily_technical_assessment

    def reconstructed(fact):
        value = reconstruct(fact)
        reconstructions.append(value)
        return value

    def validated(**kwargs):
        validations.append(kwargs["content"].to_dict())
        return validate(**kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(app, "_reconstruct_result", reconstructed)
        patch.setattr(domain, "validate_governed_daily_technical_assessment", validated)
        patch.setattr(
            domain, "assess_governed_daily_technical_interpretation", forbidden
        )
        patch.setattr(service, "_clock", forbidden)
        patch.setattr(app, "uuid4", forbidden)
        first = read_history(service, request, source.available_at)
        second = read_history(service, request, source.available_at)
    assert len(validations) == 8  # Two occurrences, two complete passes, two reads.
    graphs = [mutable_ids(value) for value in reconstructions]
    for index, graph_ids in enumerate(graphs):
        assert all(not graph_ids & other for other in graphs[:index])
    assert not mutable_ids(first) & mutable_ids(second)
    assert tuple(app._encode_result(value) for value in first) == state[1]
    expected = second[0].assessment.to_dict()
    first[0].assessment.assessment_policy_identity.configuration["changed"] = True
    object.__setattr__(first[1].assessment, "outcome", "mutated")
    third = read_history(service, request, source.available_at)
    assert tuple(app._encode_result(value) for value in third) == state[1]
    assert service._history_owner is owner
    assert service._namespace is owner._namespace_id is namespace
    assert service._committed is owner._state is state
    assert owner._pending is None
    assert service._interpretation_service._observed is observed
    assert service._interpretation_service._retention is retention
    later = service.execute(request)
    assert later.history_sequence == 3 and later.assessment.to_dict() == expected
    assert service._committed[1][:-1] == state[1]


@pytest.mark.parametrize(
    "seam", ["copy", "reconstruct", "encode", "projection", "graph", "alias", "changed"]
)
def test_history_public_copy_failures_preserve_authority(
    publication_case, monkeypatch, seam
):
    service, request, source = publication_case
    service.execute(request)
    original = app._public_result_copy

    def failed(*args, **kwargs):
        raise ValueError("public reconstruction seam failed")

    def copied(item):
        if seam == "copy":
            raise RuntimeError("copy failed")
        if seam == "alias":
            return item
        if seam == "changed":
            value = original(item)
            object.__setattr__(value, "history_sequence", 99)
            return value
        target, name = {
            "reconstruct": (app, "_reconstruct_result"),
            "encode": (app, "_encode_result"),
            "projection": (Result, "to_dict"),
            "graph": (app, "_graph_ids"),
        }[seam]
        monkeypatch.setattr(target, name, failed)
        return original(item)

    monkeypatch.setattr(app, "_public_result_copy", copied)
    history_refusal(service, request, source.available_at, R.PUBLICATION_FAILED)
    assert service._history_owner._state is service._committed


def assessment_locks(service):
    publisher = service._interpretation_service
    technical = publisher._technical_service
    bridge = technical._bridge_service
    qualified = bridge._qualification_service
    validity = qualified._validity_service
    admission = validity._admission_service
    return [
        admission._construction_service._history._lock,
        admission._validation_service._history._lock,
        admission._freshness_service._history._lock,
        admission._history._lock,
        validity._history._lock,
        qualified._history._lock,
        bridge._history._lock,
        technical._history._lock,
        publisher._history_owner._lock,
        service._history_owner._lock,
    ]


def test_history_ten_locks_once_pinned_publisher_and_final_seal(
    publication_case, monkeypatch
):
    service, request, source = publication_case
    service.execute(request)
    service.execute(request)
    publisher = service._interpretation_service
    locks = assessment_locks(service)
    entries, events, compositions, authenticated = [], [], [], []
    state = service._committed

    class NonrecursiveStack(ExitStack):
        def enter_context(self, lock):
            assert lock.acquire(blocking=False), "recursive lock acquisition"
            entries.append(lock)
            self.callback(lock.release)

    compose = publisher._lock_inputs
    authenticate = publisher._authenticate_interpretation_occurrence

    def composed(stack):
        compositions.append(publisher)
        compose(stack)

    def authentication(**selectors):
        assert entries == locks and all(lock.locked() for lock in locks)
        assert service._committed is service._history_owner._state is state
        assert service._history_owner._pending is None
        assert selectors == _interpretation_selectors(source)
        authenticated.append(selectors)
        value = authenticate(**selectors)
        events.append("authentication_return")
        return value

    def wrap(target, name):
        original = getattr(target, name)

        def call(*args, **kwargs):
            events.append(name)
            return original(*args, **kwargs)

        monkeypatch.setattr(target, name, call)

    monkeypatch.setattr(app, "ExitStack", NonrecursiveStack)
    monkeypatch.setattr(publisher, "_lock_inputs", composed)
    monkeypatch.setattr(
        publisher, "_authenticate_interpretation_occurrence", authentication
    )
    # The compatibility read surface cannot choose a different publisher.
    monkeypatch.setattr(
        Service, "_interpretation_service", property(lambda self: object())
    )
    for target, name in (
        (app, "_encode_result"),
        (app, "_decode_result"),
        (app, "_reconstruct_result"),
        (app, "_public_result_copy"),
        (app, "_check_copy"),
        (app, "_graph_ids"),
        (Result, "to_dict"),
        (service, "_check_history"),
        (service, "_check_authority"),
        (domain, "validate_governed_daily_technical_assessment"),
        (i, "_encode_result"),
    ):
        wrap(target, name)
    assert len(read_history(service, request, source.available_at)) == 2
    assert entries == locks and len(set(entries)) == 10
    assert entries[-1] is service._history_owner._lock
    assert compositions == [publisher]
    assert len(authenticated) == 6  # Complete initial, post-copy, final seal passes.
    assert events[-1] == "authentication_return"
    assert not any(lock.locked() for lock in locks)
    # There is no dispatch to a local validation seam after the final seal loop.
    tree = ast.parse(inspect.getsource(app))
    method = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "get_result_history_as_of"
    )
    body = next(node for node in ast.walk(method) if isinstance(node, ast.With)).body
    assert isinstance(body[-3], ast.For)
    assert isinstance(body[-2], ast.If) and isinstance(body[-1], ast.Return)
    assert all(
        isinstance(node.func, ast.Attribute) and node.func.attr == "__getattribute__"
        for node in ast.walk(body[-2].test)
        if isinstance(node, ast.Call)
    )
    assert isinstance(body[-1].value, ast.Name)


@pytest.mark.parametrize(
    "root", ["owner", "publisher", "namespace", "owner_namespace", "state", "pending"]
)
@pytest.mark.parametrize("phase", ["locking", "seal"])
def test_history_rejects_authority_replacement_without_repair(
    publication_case, monkeypatch, root, phase
):
    service, request, source = publication_case
    service.execute(request)
    owner, state = service._history_owner, service._committed
    publisher = service._interpretation_service
    prefix = "_PolygonCompletedDailyProductionAssessmentApplicationService__"
    target, name, replacement = {
        "owner": (service, prefix + "history_owner", app._AssessmentHistory()),
        "publisher": (service, prefix + "interpretation_service", object()),
        "namespace": (service, prefix + "namespace", PREFIX + "_history:" + "f" * 32),
        "owner_namespace": (owner, "_namespace_id", PREFIX + "_history:" + "f" * 32),
        "state": (owner, "_state", (state[0], state[1])),
        "pending": (owner, "_pending", app._reconstruct_result(state[1][0])),
    }[root]
    lock_inputs = service._lock_inputs
    authenticate = publisher._authenticate_interpretation_occurrence
    calls = []

    def locking(stack):
        value = lock_inputs(stack)
        monkeypatch.setattr(target, name, replacement)
        return value

    def authenticated(**selectors):
        value = authenticate(**selectors)
        calls.append(1)
        if len(calls) == 3:
            monkeypatch.setattr(target, name, replacement)
        return value

    if phase == "locking":
        monkeypatch.setattr(service, "_lock_inputs", locking)
    else:
        monkeypatch.setattr(
            publisher, "_authenticate_interpretation_occurrence", authenticated
        )
    with pytest.raises(Refused) as caught:
        read_history(service, request, source.available_at)
    assert caught.value.reason == R.HISTORY_INVALID
    assert getattr(target, name) is replacement
    assert service._committed is state
    assert not owner._lock.locked()
    if root != "state":
        assert owner._state is state
    if root != "pending":
        assert owner._pending is None


@pytest.mark.parametrize(
    "seam", ["copy", "graph", "projection", "codec", "domain", "history"]
)
def test_history_final_seal_catches_real_support_loss_after_fallible_work(
    publication_case, monkeypatch, seam
):
    service, request, source = publication_case
    service.execute(request)
    publisher = service._interpretation_service
    technical_history = publisher._technical_service._history
    owner, state = service._history_owner, service._committed
    authenticate = Publisher._authenticate_interpretation_occurrence.__get__(publisher)
    calls, invalidations = [], []
    target, name = {
        "copy": (app, "_public_result_copy"),
        "graph": (app, "_graph_ids"),
        "projection": (Result, "to_dict"),
        "codec": (app, "_encode_result"),
        "domain": (domain, "validate_governed_daily_technical_assessment"),
        "history": (service, "_check_history"),
    }[seam]
    original = getattr(target, name)

    def authenticated(**selectors):
        calls.append(1)
        return authenticate(**selectors)

    def changed(*args, **kwargs):
        value = original(*args, **kwargs)
        # Late projection/codec/domain seams occur after the second authentication.
        threshold = 2 if seam in ("projection", "codec", "domain") else 1
        if len(calls) >= threshold and not invalidations:
            monkeypatch.setattr(technical_history, "_state", (1, ()))
            invalidations.append(1)
        return value

    monkeypatch.setattr(
        publisher, "_authenticate_interpretation_occurrence", authenticated
    )
    monkeypatch.setattr(target, name, changed)
    history_refusal(service, request, source.available_at, R.HISTORY_INVALID)
    assert invalidations == [1]
    assert len(calls) == (3 if seam in ("projection", "codec", "domain") else 2)
    assert service._committed is owner._state is state


@pytest.mark.parametrize(
    "change", ["type", "namespace", "sequence", "execution_id", "fingerprint"]
)
def test_history_final_seal_rejects_wrong_occurrence(
    publication_case, monkeypatch, change
):
    service, request, source = publication_case
    service.execute(request)
    publisher = service._interpretation_service
    authenticate = publisher._authenticate_interpretation_occurrence
    calls = []

    def authenticated(**selectors):
        value = authenticate(**selectors)
        calls.append(1)
        if len(calls) == 3:
            if change == "type":
                return object()
            field, replacement = {
                "namespace": ("history_namespace_id", "wrong"),
                "sequence": ("history_sequence", True),
                "execution_id": ("execution_id", "wrong"),
                "fingerprint": ("fingerprint", FP),
            }[change]
            object.__setattr__(value, field, replacement)
        return value

    monkeypatch.setattr(
        publisher, "_authenticate_interpretation_occurrence", authenticated
    )
    history_refusal(service, request, source.available_at, R.SOURCE_MISMATCH)
    assert len(calls) == 3


@pytest.mark.parametrize("first_operation", ["read", "execute"])
def test_history_and_execute_serialize_on_original_owner(
    publication_case, monkeypatch, first_operation
):
    service, request, source = publication_case
    service.execute(request)
    owner, state = service._history_owner, service._committed
    locks = assessment_locks(service)
    second_operation = "execute" if first_operation == "read" else "read"
    owner_attempted, second_attempted, in_work, release_work = (
        Event() for _ in range(4)
    )
    attempted = {"read": [], "execute": []}
    acquired = {"read": [], "execute": []}
    stage, public_copy = owner._stage_publication, app._public_result_copy

    def pause():
        assert owner._lock.locked()
        assert service._committed is owner._state is state
        in_work.set()
        assert release_work.wait(30)

    def staged(value):
        stage(value)
        if first_operation == "execute":
            pause()

    def copied(value):
        if first_operation == "read" and not in_work.is_set():
            assert owner._pending is None
            pause()
        return public_copy(value)

    def run(operation):
        previous = sys.getprofile()

        def observe(frame, event, call):
            if event not in ("c_call", "c_return"):
                return
            lock = getattr(call, "__self__", None)
            if getattr(call, "__name__", None) != "__enter__" or not any(
                lock is candidate for candidate in locks
            ):
                return
            if event == "c_call":
                attempted[operation].append(lock)
                if lock is owner._lock and operation == first_operation:
                    owner_attempted.set()
                if lock is locks[0] and operation == second_operation:
                    second_attempted.set()
            else:
                acquired[operation].append(lock)

        sys.setprofile(observe)
        try:
            return (
                read_history(service, request, source.available_at)
                if operation == "read"
                else service.execute(request)
            )
        finally:
            sys.setprofile(previous)

    monkeypatch.setattr(owner, "_stage_publication", staged)
    monkeypatch.setattr(app, "_public_result_copy", copied)
    owner._lock.acquire()
    with ThreadPoolExecutor(max_workers=2) as pool:
        try:
            first = pool.submit(run, first_operation)
            assert owner_attempted.wait(30)
            assert attempted[first_operation] == locks
            assert acquired[first_operation] == locks[:-1]
            second = pool.submit(run, second_operation)
            assert second_attempted.wait(30)
            assert acquired[second_operation] == []
        finally:
            owner._lock.release()
        try:
            assert in_work.wait(30)
            assert service._committed is owner._state is state
            assert (
                owner._pending is not None
                if first_operation == "execute"
                else owner._pending is None
            )
            assert not first.done() and not second.done()
        finally:
            release_work.set()
        values = {
            first_operation: first.result(timeout=60),
            second_operation: second.result(timeout=60),
        }
    assert [item.history_sequence for item in values["read"]] == (
        [1] if first_operation == "read" else [1, 2]
    )
    assert values["execute"].history_sequence == 2
    assert attempted == acquired == {"read": locks, "execute": locks}
    assert service._history_owner is owner and service._committed is owner._state
    assert owner._pending is None and service._committed[1][:-1] == state[1]


def test_history_reauthenticates_invisible_source_after_copy(
    preparation_publisher, monkeypatch
):
    publisher, first, second = preparation_publisher
    source_facts = {
        item.fingerprint: i._encode_result(item) for item in (first, second)
    }
    calls, copied = [], []

    def authenticate(**selectors):
        fingerprint = selectors["interpretation_fingerprint"]
        calls.append(fingerprint)
        if copied and fingerprint == second.fingerprint:
            raise i._InterpretationOccurrenceUnavailable("nonvisible source lost")
        value = i._reconstruct_result(source_facts[fingerprint])
        assert selectors == _interpretation_selectors(value)
        return value

    monkeypatch.setattr(
        publisher, "_authenticate_interpretation_occurrence", authenticate
    )
    service = Service(publisher, execution_clock=lambda: second.available_at)
    request = assessment_request(first)
    visible = service.execute(request)
    service._clock = lambda: second.available_at + timedelta(days=1)
    service.execute(assessment_request(second))
    calls.clear()
    original = app._public_result_copy

    def public_copy(item):
        value = original(item)
        copied.append(item.history_sequence)
        return value

    monkeypatch.setattr(app, "_public_result_copy", public_copy)
    history_refusal(service, request, visible.available_at, R.HISTORY_INVALID)
    assert copied == [1]
    assert calls == [first.fingerprint, second.fingerprint] * 2


def test_history_rejects_alias_between_public_results(publication_case, monkeypatch):
    service, request, source = publication_case
    service.execute(request)
    service.execute(request)
    original = app._public_result_copy
    public_values = []

    def public_copy(item):
        value = original(item)
        if public_values:
            object.__setattr__(
                value.assessment,
                "assessment_policy_identity",
                public_values[0].assessment.assessment_policy_identity,
            )
        public_values.append(value)
        return value

    monkeypatch.setattr(app, "_public_result_copy", public_copy)
    history_refusal(service, request, source.available_at, R.PUBLICATION_FAILED)
    assert len(public_values) == 2


@pytest.mark.parametrize(
    "field",
    [
        "source_interpretation_content_fingerprint",
        "canonical_instrument_id",
        "source_trading_identity",
        "analysis_as_of",
        "source_quality",
        "source_warnings",
        "assessment_policy_identity",
        "findings",
        "outcome",
    ],
)
def test_history_independent_retained_content_correspondence(
    publication_case, monkeypatch, field
):
    service, request, source = publication_case
    service.execute(request)
    projection = app._decode_result(service._committed[1][0])
    content = projection["assessment"]
    replacements = {
        "source_interpretation_content_fingerprint": FP,
        "canonical_instrument_id": {
            **content["canonical_instrument_id"],
            "instrument_id": "other",
        },
        "source_trading_identity": {
            **content["source_trading_identity"],
            "symbol": "OTHER",
        },
        "analysis_as_of": (
            source.interpretation.analysis_as_of - timedelta(days=1)
        ).isoformat(),
        "source_quality": "degraded"
        if content["source_quality"] == "complete"
        else "complete",
        "source_warnings": [] if content["source_warnings"] else ["stale_evidence"],
        "assessment_policy_identity": {
            **content["assessment_policy_identity"],
            "behavioral_revision": "other",
        },
        "findings": []
        if content["findings"]
        else [
            {
                "kind": "caution",
                "code": "source_quality_degraded",
                "comparison_evidence_ids": [],
            }
        ],
        "outcome": "mixed" if content["outcome"] != "mixed" else "aligned",
    }
    content[field] = replacements[field]
    refingerprint(content)
    refingerprint(projection)
    changed = (2, (app._canonical_bytes(projection),))
    monkeypatch.setattr(service, "_committed", changed)
    monkeypatch.setattr(service._history_owner, "_state", changed)
    history_refusal(service, request, source.available_at, R.HISTORY_INVALID)


@pytest.mark.parametrize("root", ["namespace", "owner_namespace"])
def test_history_does_not_adopt_equal_namespace_replacement(
    publication_case, monkeypatch, root
):
    service, request, source = publication_case
    service.execute(request)
    original = app._public_result_copy
    namespace = service._namespace
    replacement = namespace.encode().decode()
    assert replacement == namespace and replacement is not namespace

    def copied(item):
        value = original(item)
        target, name = (
            (
                service,
                "_PolygonCompletedDailyProductionAssessmentApplicationService__namespace",
            )
            if root == "namespace"
            else (service._history_owner, "_namespace_id")
        )
        monkeypatch.setattr(target, name, replacement)
        return value

    monkeypatch.setattr(app, "_public_result_copy", copied)
    with pytest.raises(Refused) as caught:
        read_history(service, request, source.available_at)
    assert caught.value.reason == R.HISTORY_INVALID
    assert service._committed is service._history_owner._state


def test_history_requires_exact_retained_source_availability(
    publication_case, monkeypatch
):
    service, request, source = publication_case
    service.execute(request)
    projection = app._decode_result(service._committed[1][0])
    projection["interpretation_available_at"] = (
        source.available_at - timedelta(microseconds=1)
    ).isoformat()
    refingerprint(projection)
    fact = app._canonical_bytes(projection)
    app._reconstruct_result(fact)  # Valid envelope, incorrect source correspondence.
    state = (2, (fact,))
    monkeypatch.setattr(service, "_committed", state)
    monkeypatch.setattr(service._history_owner, "_state", state)
    history_refusal(service, request, source.available_at, R.SOURCE_MISMATCH)


# Exact additive allowances; all other released nodes remain AST-identical.
_PRIVATE_TOP_LEVEL = {
    "_AssessmentOccurrenceUnavailable",
    "_AssessmentHistoryInvalid",
    "_AssessmentSourceMismatch",
    "_AssessmentPair",
    "_check_assessment_pair",
}
_PRIVATE_METHODS = {
    "_check_consumption_roots",
    "_authenticate_consumption_source",
    "_consume_assessments",
    "_authenticate_assessment_occurrence",
    "_authenticate_assessment_inventory",
    "_revalidate_assessment_inventory",
}
_PRIVATE_IMPORT = (
    "from market_platform.research.governed_daily_technical_strategy "
    "import PolygonCompletedDailyStrategyRequest as _StrategyRequest"
)
_PRIVATE_INITIALIZATION = """
self.__consumption_roots = (
    self.__history_owner, self.__namespace, interpretation_service,
    vars(interpretation_service).get("_history_owner"),
    vars(interpretation_service).get("_namespace"),
)
self.__consumption_locks: tuple[object, ...] | None = None
"""
_PRIVATE_LOCK_CAPTURE = """
consumption_locks = (
    publisher, owner, vars(publisher).get("_history_owner"),
)
self.__consumption_locks = consumption_locks
"""


def _assessment_checkpoint():
    return ast.parse(
        subprocess.check_output(
            [
                "git",
                "show",
                "0f6d58f671e38e733332999de37323f1f98c38e9:"
                "src/market_platform/application/polygon_completed_daily_production_assessment.py",
            ],
            cwd=Path(__file__).resolve().parents[2],
            text=True,
        )
    )


def _assert_assessment_checkpoint(before, after):
    from copy import deepcopy

    after = deepcopy(after)
    extra_import = ast.dump(ast.parse(_PRIVATE_IMPORT).body[0])
    baseline_names = {node.name for node in before.body if hasattr(node, "name")}
    retained = []
    added = set()
    for node in after.body:
        if ast.dump(node) == extra_import:
            assert extra_import not in added
            added.add(extra_import)
        elif hasattr(node, "name") and node.name not in baseline_names:
            assert node.name in _PRIVATE_TOP_LEVEL
            assert node.name.startswith("_") and node.name not in added
            added.add(node.name)
        else:
            retained.append(node)
    after.body = retained
    assert len(before.body) == len(after.body)
    for old, new in zip(before.body, after.body, strict=True):
        if isinstance(old, ast.ClassDef) and old.name == Service.__name__:
            old_names = {node.name for node in old.body if hasattr(node, "name")}
            members = []
            added_methods = set()
            for node in new.body:
                if hasattr(node, "name") and node.name not in old_names:
                    assert node.name in _PRIVATE_METHODS
                    assert node.name.startswith("_") and node.name not in added_methods
                    added_methods.add(node.name)
                    continue
                if isinstance(node, ast.FunctionDef):
                    permitted = {
                        "__init__": _PRIVATE_INITIALIZATION,
                        "_lock_inputs": _PRIVATE_LOCK_CAPTURE,
                    }.get(node.name)
                    if permitted:
                        original = next(
                            n for n in old.body if getattr(n, "name", None) == node.name
                        )
                        augmented = deepcopy(original)
                        additions = ast.parse(permitted).body
                        if node.name == "__init__":
                            augmented.body.extend(additions)
                        else:
                            augmented.body[2:2] = additions[:1]
                            augmented.body[-1:-1] = additions[1:]
                        assert ast.dump(node) in (
                            ast.dump(original),
                            ast.dump(augmented),
                        )
                        node = original
                members.append(node)
            new.body = members
        assert ast.dump(old) == ast.dump(new)


@pytest.mark.parametrize(
    "attack",
    [
        "export",
        "execute",
        "history",
        "result",
        "refusal",
        "constant",
        "public",
        "private",
        "method",
        "constructor",
    ],
)
def test_slice2_checkpoint_rejects_unauthorized_changes(attack):
    baseline = _assessment_checkpoint()
    changed = ast.parse(inspect.getsource(app))
    service = next(
        n
        for n in changed.body
        if isinstance(n, ast.ClassDef) and n.name == Service.__name__
    )
    if attack == "export":
        node = next(
            n
            for n in changed.body
            if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "__all__" for t in n.targets)
        )
        node.value.elts.append(ast.Constant("NewPublic"))
    elif attack in ("execute", "history", "constructor"):
        name = {
            "execute": "execute",
            "history": "get_result_history_as_of",
            "constructor": "__init__",
        }[attack]
        node = next(
            n for n in service.body if isinstance(n, ast.FunctionDef) and n.name == name
        )
        node.args.args.append(ast.arg(arg="new_parameter"))
    elif attack in ("result", "refusal"):
        name = Result.__name__ if attack == "result" else Refused.__name__
        node = next(
            n for n in changed.body if isinstance(n, ast.ClassDef) and n.name == name
        )
        node.body.append(ast.parse("new_field = 1").body[0])
    elif attack == "constant":
        node = next(
            n
            for n in changed.body
            if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "_SCHEMA" for t in n.targets)
        )
        node.value = ast.Constant("changed")
    elif attack == "method":
        service.body.append(ast.parse("def new_public(self): pass").body[0])
    else:
        changed.body.append(
            ast.parse(
                "class "
                + ("NewPublic" if attack == "public" else "_UnapprovedPrivate")
                + ": pass"
            ).body[0]
        )
    with pytest.raises(AssertionError):
        _assert_assessment_checkpoint(baseline, changed)


def test_slice2_checkpoint_accepts_only_named_private_additions():
    baseline = _assessment_checkpoint()
    current = ast.parse(inspect.getsource(app))
    _assert_assessment_checkpoint(baseline, current)
    before = {n.name for n in baseline.body if hasattr(n, "name")}
    after = {n.name for n in current.body if hasattr(n, "name")}
    assert after - before == _PRIVATE_TOP_LEVEL
    assert all(name.startswith("_") for name in _PRIVATE_TOP_LEVEL | _PRIVATE_METHODS)
    assert set(app.__all__).isdisjoint(_PRIVATE_TOP_LEVEL | _PRIVATE_METHODS)


def _strategy_request(value, **changes):
    return app._StrategyRequest(
        **(
            dict(
                artifact_reference=value.assessment.source_interpretation_occurrence.artifact_reference,
                assessment_history_namespace_id=value.history_namespace_id,
                assessment_history_sequence=value.history_sequence,
                assessment_execution_id=value.execution_id,
                assessment_fingerprint=value.fingerprint,
            )
            | changes
        )
    )


@pytest.fixture
def consumption_case(monkeypatch):
    # Mock only the released Interpretation authentication/locking boundary.
    # Assessment publications are issued through unchanged public execute.
    from test_governed_daily_technical_assessment import source

    publisher = object.__new__(Publisher)
    owner = i._InterpretationHistory()
    publisher._history_owner = publisher._history = owner
    publisher._namespace = owner._namespace_id
    values = []
    content = source(
        truths=("rsi_at_or_above_elevated",),
        source_quality="degraded",
        source_warnings=("insufficient_profile_history", "stale_evidence"),
    )
    for sequence in (1, 2):
        value = object.__new__(i.PolygonCompletedDailyInterpretationResult)
        for name, field_value in dict(
            interpretation=replace(content),
            technical_available_at=TIME,
            execution_id="polygon_completed_daily_interpretation:" + f"{sequence:032x}",
            history_namespace_id=owner._namespace_id,
            history_sequence=sequence,
            execution_started_at=TIME,
            execution_completed_at=TIME,
            available_at=TIME,
        ).items():
            object.__setattr__(value, name, field_value)
        object.__setattr__(
            value, "fingerprint", canonical_fingerprint(value._payload())
        )
        values.append(value)
    owner._state = publisher._committed = (
        3,
        tuple(i._encode_result(v) for v in values),
    )
    locks = [*(Lock() for _ in range(8)), owner._lock]
    calls = []

    def lock_inputs(stack):
        for lock in locks:
            stack.enter_context(lock)

    def authenticate(**selectors):
        assert all(lock.locked() for lock in locks)
        calls.append(selectors)
        owner._validate()
        if owner._state is not publisher._committed:
            raise i._InterpretationHistoryInvalid("support")
        for fact in publisher._committed[1]:
            value = i._reconstruct_result(fact)
            if selectors == _interpretation_selectors(value):
                return value
        raise i._InterpretationOccurrenceUnavailable("support")

    monkeypatch.setattr(publisher, "_lock_inputs", lock_inputs)
    monkeypatch.setattr(
        publisher, "_authenticate_interpretation_occurrence", authenticate
    )
    service = Service(publisher, execution_clock=lambda: TIME)
    first = service.execute(assessment_request(values[0]))
    second = service.execute(assessment_request(values[1]))
    calls.clear()
    return service, first, second, values, calls


def _consume(service, value, **changes):
    with ExitStack() as stack:
        service._lock_inputs(stack)
        return service._authenticate_assessment_occurrence(
            _strategy_request(value, **changes)
        )


def _capture(service):
    with ExitStack() as stack:
        service._lock_inputs(stack)
        return service._authenticate_assessment_inventory()


def _recheck(service, expected):
    with ExitStack() as stack:
        service._lock_inputs(stack)
        service._revalidate_assessment_inventory(expected)


def _install_assessment_projection(service, index, projection):
    # Deliberately corrupt BOTH commitments to reach deeper validation checks;
    # ordinary single-root replacement tests below preserve the independent pin.
    refingerprint(projection["assessment"])
    refingerprint(projection)
    facts = list(service._committed[1])
    facts[index] = app._canonical_bytes(projection)
    service._history_owner._state = service._committed = (len(facts) + 1, tuple(facts))


def test_slice2_private_types_pair_and_exact_bound_source(consumption_case):
    service, first, second, sources, calls = consumption_case
    for name in (
        "_AssessmentOccurrenceUnavailable",
        "_AssessmentHistoryInvalid",
        "_AssessmentSourceMismatch",
    ):
        assert issubclass(getattr(app, name), ValueError)
        assert name not in app.__all__
    before = service._committed
    pair = _consume(service, first)
    assert type(pair) is app._AssessmentPair
    assert tuple(f.name for f in fields(pair)) == (
        "assessment",
        "interpretation",
        "assessment_fact",
        "interpretation_fact",
    )
    assert pair.assessment.to_dict() == first.to_dict()
    assert pair.interpretation.to_dict() == sources[0].to_dict()
    assert pair.interpretation.fingerprint != sources[1].fingerprint
    assert type(pair.assessment_fact) is type(pair.interpretation_fact) is bytes
    assert pair.assessment_fact == before[1][0]
    assert pair.interpretation_fact == service._interpretation_service._committed[1][0]
    assert calls == [_interpretation_selectors(source) for source in sources] * 2
    other = _consume(service, second)
    repeated = _consume(service, first)
    assert not mutable_ids(pair) & (
        mutable_ids(other) | mutable_ids(repeated) | mutable_ids(first)
    )
    assert not mutable_ids(pair.assessment) & mutable_ids(pair.interpretation)
    assert all(not isinstance(v, Enum) for v in graph(pair))
    assert service._committed is service._history_owner._state is before
    with pytest.raises(TypeError):
        service._authenticate_assessment_occurrence(
            _strategy_request(first), interpretation=sources[1]
        )
    with pytest.raises(TypeError):
        service._authenticate_assessment_occurrence(pair)
    object.__setattr__(pair.assessment.assessment, "outcome", "mixed")
    object.__setattr__(
        pair.interpretation.interpretation.canonical_instrument_id,
        "instrument_id",
        "changed",
    )
    assert _consume(service, first).assessment.to_dict() == first.to_dict()


@pytest.mark.parametrize("selector", [f.name for f in fields(app._StrategyRequest)])
def test_slice2_all_five_selectors_and_envelope_required(consumption_case, selector):
    service, first, _, sources, calls = consumption_case
    request = _strategy_request(first)
    value = getattr(request, selector)
    if selector == "artifact_reference":
        value = replace(value, authority="platform_origin")
    elif selector == "assessment_history_sequence":
        value += 1
    elif selector == "assessment_fingerprint":
        value = first.assessment.fingerprint
    else:
        value = value[:-32] + "f" * 32
    with pytest.raises(app._AssessmentOccurrenceUnavailable):
        _consume(service, first, **{selector: value})
    assert calls == [_interpretation_selectors(source) for source in sources] * 2


@pytest.mark.parametrize(
    "failure,expected",
    [
        (i._InterpretationOccurrenceUnavailable, app._AssessmentHistoryInvalid),
        (i._InterpretationHistoryInvalid, app._AssessmentHistoryInvalid),
        (i._InterpretationSourceMismatch, app._AssessmentSourceMismatch),
    ],
)
@pytest.mark.parametrize("phase", [1, 2, 3, 4])
def test_slice2_structured_failures_without_message_parsing(
    consumption_case, monkeypatch, failure, expected, phase
):
    service, first, _, _, _ = consumption_case
    publisher = service._interpretation_service
    authenticate = publisher._authenticate_interpretation_occurrence
    count = 0

    class OpaqueFailure(failure):
        def __str__(self):
            return "identical diagnostic for every category"

    def failing(**selectors):
        nonlocal count
        count += 1
        if count == phase:
            raise OpaqueFailure()
        return authenticate(**selectors)

    monkeypatch.setattr(publisher, "_authenticate_interpretation_occurrence", failing)
    with pytest.raises(expected) as caught:
        _consume(service, first, assessment_history_sequence=99)
    assert isinstance(caught.value.__cause__, OpaqueFailure)


@pytest.mark.parametrize(
    "field",
    [
        "source_interpretation_content_fingerprint",
        "canonical_instrument_id",
        "source_trading_identity",
        "analysis_as_of",
        "source_quality",
        "source_warnings",
        "interpretation_available_at",
        "findings",
    ],
)
def test_slice2_nonsemantic_pair_correspondence(consumption_case, field):
    service, first, _, _, _ = consumption_case
    projection = app._decode_result(service._committed[1][1])
    content = projection["assessment"]
    replacements = {
        "source_interpretation_content_fingerprint": FP,
        "canonical_instrument_id": CanonicalInstrumentId("other").to_dict(),
        "source_trading_identity": TradingInstrumentIdentity(
            "MSFT", "NASDAQ"
        ).to_dict(),
        "analysis_as_of": (TIME - timedelta(days=1)).isoformat(),
        "source_quality": "complete",
        "source_warnings": ["stale_evidence"],
        "findings": [
            domain.GovernedDailyTechnicalAssessmentFinding(
                "caution", "rsi_depressed", ("rsi_at_or_below_depressed",)
            ).to_dict()
        ],
    }
    if field == "interpretation_available_at":
        projection[field] = (TIME - timedelta(seconds=1)).isoformat()
    else:
        content[field] = replacements[field]
    _install_assessment_projection(service, 1, projection)
    with pytest.raises(app._AssessmentSourceMismatch):
        _consume(service, first)


@pytest.mark.parametrize(
    "field",
    [
        "artifact_reference",
        "interpretation_history_namespace_id",
        "interpretation_history_sequence",
        "interpretation_execution_id",
        "interpretation_fingerprint",
    ],
)
def test_slice2_authenticated_source_selectors_must_match(
    consumption_case, monkeypatch, field
):
    service, first, _, sources, _ = consumption_case
    source = i._reconstruct_result(i._encode_result(sources[0]))
    item = app._reconstruct_result(app._encode_result(first))
    request = item.assessment.source_interpretation_occurrence
    value = getattr(request, field)
    if field == "artifact_reference":
        value = replace(value, artifact_version="other")
    elif field == "interpretation_history_sequence":
        value += 9
    elif field == "interpretation_fingerprint":
        value = FP
    else:
        value = value[:-32] + "f" * 32
    changed = replace(
        item.assessment,
        source_interpretation_occurrence=replace(request, **{field: value}),
    )
    object.__setattr__(item, "assessment", changed)
    object.__setattr__(item, "fingerprint", canonical_fingerprint(item._payload()))
    with pytest.raises(app._AssessmentSourceMismatch):
        app._check_assessment_pair(item, source)


@pytest.mark.parametrize(
    "attack",
    [
        "bytes",
        "bytes_subclass",
        "content_hash",
        "envelope_hash",
        "duplicate_id",
        "sequence",
        "reorder",
        "count",
        "warnings_order",
        "finding_shape",
        "policy",
        "chronology",
        "availability_order",
    ],
)
def test_slice2_complete_inventory_before_selection(consumption_case, attack):
    service, first, second, _, calls = consumption_case
    facts = list(service._committed[1])
    projection = app._decode_result(facts[1])
    if attack == "bytes":
        facts[1] = b"corrupt"
    elif attack == "bytes_subclass":
        facts[1] = Bytes(facts[1])
    elif attack == "reorder":
        facts.reverse()
    elif attack == "count":
        pass
    else:
        if attack == "content_hash":
            projection["assessment"]["fingerprint"] = FP
        elif attack == "envelope_hash":
            projection["fingerprint"] = FP
        elif attack == "duplicate_id":
            projection["execution_id"] = first.execution_id
        elif attack == "sequence":
            projection["history_sequence"] = 9
        elif attack == "warnings_order":
            projection["assessment"]["source_warnings"].reverse()
            refingerprint(projection["assessment"])
        elif attack == "finding_shape":
            projection["assessment"]["findings"].reverse()
            refingerprint(projection["assessment"])
        elif attack == "policy":
            projection["assessment"]["assessment_policy_identity"]["policy_id"] = (
                "changed"
            )
            refingerprint(projection["assessment"])
        elif attack == "chronology":
            projection["execution_started_at"] = (
                TIME - timedelta(seconds=1)
            ).isoformat()
        elif attack == "availability_order":
            previous = app._decode_result(facts[0])
            previous["available_at"] = (TIME + timedelta(seconds=1)).isoformat()
            refingerprint(previous)
            facts[0] = app._canonical_bytes(previous)
        if attack != "envelope_hash":
            refingerprint(projection)
        facts[1] = app._canonical_bytes(projection)
    state = (4 if attack == "count" else 3, tuple(facts))
    service._committed = service._history_owner._state = state
    with pytest.raises(app._AssessmentHistoryInvalid):
        _consume(service, first, assessment_history_sequence=99)
    assert calls == []
    assert service._committed is service._history_owner._state is state


@pytest.mark.parametrize(
    "attack",
    [
        "owner",
        "state",
        "rollback",
        "truncation",
        "reorder",
        "namespace",
        "namespace_equal",
        "commitment",
        "pending",
        "publisher",
        "interpretation_owner",
        "interpretation_namespace",
    ],
)
@pytest.mark.parametrize("empty", [False, True])
def test_slice2_original_roots_even_when_empty(
    consumption_case, monkeypatch, attack, empty
):
    service, first, _, _, _ = consumption_case
    if empty:
        service = Service(service._interpretation_service)
    owner, state = service._history_owner, service._committed
    prefix = "_PolygonCompletedDailyProductionAssessmentApplicationService__"
    publisher = service._interpretation_service
    if attack == "owner":
        replacement = app._AssessmentHistory()
        replacement._state = state
        replacement._namespace_id = owner._namespace_id
        monkeypatch.setattr(service, prefix + "history_owner", replacement)
    elif attack == "state":
        owner._state = tuple(list(state))
    elif attack == "rollback":
        owner._state = (1, ())
    elif attack == "truncation":
        owner._state = (state[0], state[1][:-1])
    elif attack == "reorder":
        owner._state = (state[0], tuple(reversed(state[1])))
    elif attack == "namespace":
        owner._namespace_id = NAMESPACE
    elif attack == "namespace_equal":
        owner._namespace_id = owner._namespace_id.encode().decode()
    elif attack == "commitment":
        service._committed = tuple(list(state))
    elif attack == "pending":
        owner._pending = first
    elif attack == "publisher":
        other = copy(publisher)
        monkeypatch.setattr(service, prefix + "interpretation_service", other)
    elif attack == "interpretation_owner":
        other = copy(publisher._history_owner)
        monkeypatch.setattr(publisher, "_history_owner", other)
        monkeypatch.setattr(publisher, "_history", other)
    else:
        monkeypatch.setattr(
            publisher, "_namespace", publisher._namespace.encode().decode()
        )
    with pytest.raises(app._AssessmentHistoryInvalid):
        _consume(service, first)


def test_slice2_valid_empty_inventory_and_revalidation(consumption_case):
    service, first, _, _, _ = consumption_case
    service = Service(service._interpretation_service)
    state = service._committed
    assert _capture(service) == ()
    _recheck(service, ())
    with pytest.raises(app._AssessmentOccurrenceUnavailable):
        _consume(service, first)
    assert service._committed is state


def test_slice2_lock_selection_swap_back_rejected(consumption_case, monkeypatch):
    service, first, _, _, _ = consumption_case
    original = service._interpretation_service
    replacement = copy(original)
    name = (
        "_PolygonCompletedDailyProductionAssessmentApplicationService"
        "__interpretation_service"
    )
    with ExitStack() as stack:
        monkeypatch.setattr(service, name, replacement)
        service._lock_inputs(stack)
        monkeypatch.setattr(service, name, original)
        with pytest.raises(app._AssessmentHistoryInvalid):
            service._authenticate_assessment_occurrence(_strategy_request(first))


@pytest.mark.parametrize(
    "change", ["pair", "fact", "inventory", "support", "root", "copy"]
)
def test_slice2_expected_inventory_is_not_authority(
    consumption_case, monkeypatch, change
):
    from copy import deepcopy

    service, first, _, _, _ = consumption_case
    captured = _capture(service)
    _recheck(service, captured)
    expected = deepcopy(captured)
    if change == "pair":
        object.__setattr__(
            expected[0].assessment, "execution_id", PREFIX + ":" + "f" * 32
        )
    elif change == "fact":
        object.__setattr__(
            expected[0], "interpretation_fact", expected[1].interpretation_fact
        )
    elif change == "inventory":
        expected = expected[:1]
    elif change in ("support", "copy"):
        publisher = service._interpretation_service
        monkeypatch.setattr(publisher, "_committed", (1, ()))
        monkeypatch.setattr(publisher._history_owner, "_state", publisher._committed)
    else:
        monkeypatch.setattr(
            service._history_owner, "_state", tuple(list(service._committed))
        )
    with pytest.raises((app._AssessmentHistoryInvalid, app._AssessmentSourceMismatch)):
        _recheck(service, expected)
    if change == "copy":
        with pytest.raises(app._AssessmentHistoryInvalid):
            _consume(service, first)


def test_slice2_no_semantics_public_calls_or_recursive_locks(
    consumption_case, monkeypatch
):
    service, first, _, _, _ = consumption_case
    with ExitStack() as stack:
        service._lock_inputs(stack)
        for target, names in (
            (
                service,
                (
                    "execute",
                    "get_result_history_as_of",
                    "_lock_inputs",
                    "_authenticate_history_locked",
                    "_prepare_assessment_locked",
                ),
            ),
            (
                service._interpretation_service,
                ("execute", "get_result_history_as_of", "_lock_inputs"),
            ),
            (
                domain,
                (
                    "assess_governed_daily_technical_interpretation",
                    "validate_governed_daily_technical_assessment",
                    "_derive_assessment",
                    "build_classic_assessment_findings",
                    "classic_assessment_outcome",
                ),
            ),
            (
                domain.classic,
                ("build_classic_assessment_findings", "classic_assessment_outcome"),
            ),
            (
                i.domain,
                (
                    "interpret_governed_daily_technical_snapshot",
                    "validate_governed_daily_technical_interpretation",
                    "classic_states",
                    "build_classic_comparison_evidence",
                ),
            ),
            (i.domain.classic, ("classic_states", "build_classic_comparison_evidence")),
        ):
            for name in names:
                monkeypatch.setattr(target, name, forbidden)
        pair = service._authenticate_assessment_occurrence(_strategy_request(first))
        captured = service._authenticate_assessment_inventory()
        service._revalidate_assessment_inventory(captured)
        assert pair.assessment.fingerprint == first.fingerprint


def test_slice2_final_support_seal_after_all_local_work(consumption_case, monkeypatch):
    service, first, _, sources, _ = consumption_case
    events = []
    final_events = [("support_return", _interpretation_selectors(s)) for s in sources]
    publisher = service._interpretation_service
    authenticate = publisher._authenticate_interpretation_occurrence
    in_source = False

    def authentication(**selectors):
        nonlocal in_source
        in_source = True
        try:
            value = authenticate(**selectors)
        finally:
            in_source = False
        events.append(("support_return", selectors))
        return value

    monkeypatch.setattr(
        publisher, "_authenticate_interpretation_occurrence", authentication
    )
    for target, name in (
        (app, "_encode_result"),
        (app, "_decode_result"),
        (app, "_reconstruct_result"),
        (app, "_graph_ids"),
        (app, "_check_assessment_pair"),
        (app, "deepcopy"),
        (i, "_encode_result"),
        (app._AssessmentHistory, "_validate"),
        (Result, "to_dict"),
        (i.PolygonCompletedDailyInterpretationResult, "to_dict"),
        (domain.PolygonCompletedDailyAssessmentRequest, "to_dict"),
        (app._StrategyRequest, "to_dict"),
        (domain.GovernedDailyTechnicalAssessment, "_validate"),
    ):
        original = getattr(target, name)

        def wrap(*args, _original=original, _name=name, **kwargs):
            value = _original(*args, **kwargs)
            if not in_source:
                events.append(_name)
            return value

        monkeypatch.setattr(target, name, wrap)
    _consume(service, first)
    assert events[-2:] == final_events
    events.clear()
    captured = _capture(service)
    assert events[-2:] == final_events
    events.clear()
    _recheck(service, captured)
    assert events[-2:] == final_events


@pytest.mark.parametrize(
    "seam", ["_graph_ids", "_check_assessment_pair", "_encode_result"]
)
def test_slice2_late_support_loss_detected(consumption_case, monkeypatch, seam):
    service, first, _, _, _ = consumption_case
    publisher = service._interpretation_service
    original = getattr(app, seam)

    def remove(*args, **kwargs):
        value = original(*args, **kwargs)
        publisher._committed = publisher._history_owner._state = (1, ())
        return value

    monkeypatch.setattr(app, seam, remove)
    with pytest.raises(app._AssessmentHistoryInvalid):
        _consume(service, first)


def test_slice2_authentic_preexisting_support_and_forbidden_execution(
    preparation_publisher, monkeypatch
):
    publisher, source, other_source = preparation_publisher
    service = execution_service(preparation_publisher)
    first = service.execute(assessment_request(source))
    service.execute(assessment_request(other_source))
    technical = publisher._technical_service
    bridge = technical._bridge_service
    qualification = bridge._qualification_service
    from market_platform.data.providers.polygon import PolygonProvider

    for target, names in (
        (service, ("execute", "get_result_history_as_of")),
        (
            publisher,
            (
                "execute",
                "get_result_history_as_of",
                "_check_history",
                "_observe_technical_history",
            ),
        ),
        (technical, ("execute", "get_result_history_as_of")),
        (bridge, ("bridge", "get_bridge_history_as_of")),
        (qualification, ("qualify",)),
        (t.technical, ("analyze_daily_technical_snapshot",)),
        (PolygonProvider, ("get_daily_prices", "get_completed_daily_acquisition")),
    ):
        for name in names:
            monkeypatch.setattr(target, name, forbidden)
    for target, names in (
        (
            domain,
            (
                "assess_governed_daily_technical_interpretation",
                "validate_governed_daily_technical_assessment",
                "_derive_assessment",
            ),
        ),
        (
            i.domain,
            (
                "interpret_governed_daily_technical_snapshot",
                "validate_governed_daily_technical_interpretation",
                "classic_states",
                "build_classic_comparison_evidence",
            ),
        ),
        (i.domain.classic, ("classic_states", "build_classic_comparison_evidence")),
    ):
        for name in names:
            monkeypatch.setattr(target, name, forbidden)
    pair = _consume(service, first)
    assert pair.interpretation.to_dict() == source.to_dict()
    expected = _capture(service)
    _recheck(service, expected)
    authenticate = publisher._authenticate_interpretation_occurrence
    calls = []

    def lose_support_after_first_final_check(**selectors):
        calls.append(selectors)
        value = authenticate(**selectors)
        if len(calls) == 3:
            # First final pair authenticated successfully. Only now remove its
            # original technical support; the later trusted call must reject it.
            monkeypatch.setattr(technical._history, "_state", (1, ()))
        return value

    monkeypatch.setattr(
        publisher,
        "_authenticate_interpretation_occurrence",
        lose_support_after_first_final_check,
    )
    with pytest.raises(app._AssessmentHistoryInvalid):
        _recheck(service, expected)
    assert calls == [_interpretation_selectors(s) for s in (source, other_source)] * 2


@pytest.mark.parametrize("mode", ["selection", "revalidation"])
def test_slice2_final_check_covers_earlier_source_after_later_pair_work(
    consumption_case, monkeypatch, mode
):
    service, first, _, sources, _ = consumption_case
    expected = _capture(service)
    publisher = service._interpretation_service
    authenticate = publisher._authenticate_interpretation_occurrence
    check_pair = app._check_assessment_pair
    lost = False
    calls = []

    def support(**selectors):
        calls.append(selectors)
        # The released contract authenticates ALL support at each pair check.
        if lost:
            raise i._InterpretationHistoryInvalid("earlier source support lost")
        return authenticate(**selectors)

    def pair_work(item, source):
        nonlocal lost
        check_pair(item, source)
        if item.history_sequence == 2:
            lost = True

    monkeypatch.setattr(publisher, "_authenticate_interpretation_occurrence", support)
    monkeypatch.setattr(app, "_check_assessment_pair", pair_work)
    with pytest.raises(app._AssessmentHistoryInvalid):
        if mode == "selection":
            _consume(service, first)
        else:
            _recheck(service, expected)
    bound = [_interpretation_selectors(source) for source in sources]
    assert calls == [*bound, bound[0]]


def test_slice2_wrong_authenticated_bound_occurrence_is_source_mismatch(
    consumption_case, monkeypatch
):
    service, first, _, sources, _ = consumption_case
    publisher = service._interpretation_service
    fact = i._encode_result(sources[1])
    monkeypatch.setattr(
        publisher,
        "_authenticate_interpretation_occurrence",
        lambda **kwargs: i._reconstruct_result(fact),
    )
    with pytest.raises(app._AssessmentSourceMismatch):
        _consume(service, first)


def test_slice2_availability_after_original_start_rejected(consumption_case):
    service, first, _, sources, _ = consumption_case
    item = app._reconstruct_result(app._encode_result(first))
    source = i._reconstruct_result(i._encode_result(sources[0]))
    object.__setattr__(source, "available_at", TIME + timedelta(seconds=1))
    object.__setattr__(source, "fingerprint", canonical_fingerprint(source._payload()))
    # Other retained correspondence is made exact, leaving source availability
    # later than the original Assessment execution start.
    content = replace(
        item.assessment, source_interpretation_occurrence=assessment_request(source)
    )
    object.__setattr__(item, "assessment", content)
    object.__setattr__(item, "fingerprint", canonical_fingerprint(item._payload()))
    with pytest.raises(app._AssessmentSourceMismatch):
        app._check_assessment_pair(item, source)


@pytest.mark.parametrize(
    "attack", ["satisfied", "operator", "operand", "order", "policy"]
)
def test_slice2_interpretation_structural_facts_rejected(
    consumption_case, monkeypatch, attack
):
    service, first, _, sources, _ = consumption_case
    publisher = service._interpretation_service
    projection = sources[0].to_dict()
    comparison = projection["interpretation"]["comparison_evidence"][0]
    if attack == "satisfied":
        comparison["satisfied"] = not comparison["satisfied"]
    elif attack == "operator":
        comparison["operator"] = "unknown"
    elif attack == "operand":
        comparison["left_operand"]["value"] = True
    elif attack == "order":
        projection["interpretation"]["comparison_evidence"].append(comparison.copy())
    else:
        projection["interpretation"]["interpretation_policy_identity"]["policy_id"] = (
            "changed"
        )
    refingerprint(projection)
    state = (3, (i._canonical_bytes(projection), publisher._committed[1][1]))
    monkeypatch.setattr(publisher, "_committed", state)
    monkeypatch.setattr(publisher._history_owner, "_state", state)
    with pytest.raises(app._AssessmentHistoryInvalid):
        _consume(service, first)


def test_slice2_semantic_decision_lookup_does_not_rederive(consumption_case):
    service, first, _, _, _ = consumption_case
    projection = first.to_dict()
    projection["assessment"]["outcome"] = "aligned"
    _install_assessment_projection(service, 0, projection)
    altered = app._reconstruct_result(service._committed[1][0])
    # Deliberately coherent, structurally valid retained semantics. Private lookup
    # authenticates membership/correspondence; public history still revalidates it.
    assert _consume(service, altered).assessment.assessment.outcome == "aligned"
    with pytest.raises(Refused) as caught:
        read_history(service, assessment_request(consumption_case[3][0]), TIME)
    assert caught.value.reason == R.HISTORY_INVALID


def test_slice2_private_seam_call_inventory_has_no_execution_or_locking():
    tree = ast.parse(inspect.getsource(app))
    nodes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in _PRIVATE_METHODS | {"_check_assessment_pair"}
    ]
    called = {
        node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
        for definition in nodes
        for node in ast.walk(definition)
        if isinstance(node, ast.Call)
        and isinstance(node.func, (ast.Name, ast.Attribute))
    }
    assert not called & {
        "execute",
        "get_result_history_as_of",
        "_lock_inputs",
        "enter_context",
        "acquire",
        "Lock",
        "_derive_assessment",
        "assess_governed_daily_technical_interpretation",
        "validate_governed_daily_technical_assessment",
        "interpret_governed_daily_technical_snapshot",
        "validate_governed_daily_technical_interpretation",
        "classic_states",
        "build_classic_comparison_evidence",
        "_semantic_view",
    }
    assert not any(
        "StrategyResult" in node.name or "StrategyApplication" in node.name
        for node in tree.body
        if hasattr(node, "name")
    )


def test_slice2_waiting_reader_does_not_replace_held_lock_capture(
    consumption_case, monkeypatch
):
    service, first, _, _, _ = consumption_case
    publisher = service._interpretation_service
    locking = publisher._lock_inputs
    waiting = Event()

    def signal_then_lock(stack):
        waiting.set()
        locking(stack)

    with ThreadPoolExecutor(max_workers=1) as pool:
        with ExitStack() as stack:
            service._lock_inputs(stack)
            captured = service._authenticate_assessment_inventory()
            monkeypatch.setattr(publisher, "_lock_inputs", signal_then_lock)
            future = pool.submit(_capture, service)
            assert waiting.wait(5)
            assert not future.done()
            service._revalidate_assessment_inventory(captured)
        assert future.result(timeout=10)[0].assessment.fingerprint == first.fingerprint


def test_slice2_interpretation_lock_replacement_swap_back_rejected(
    consumption_case, monkeypatch
):
    service, first, _, _, _ = consumption_case
    publisher = service._interpretation_service
    original_owner = publisher._history_owner
    replacement = i._InterpretationHistory()
    replacement._state = original_owner._state
    replacement._namespace_id = original_owner._namespace_id
    lock_inputs = publisher._lock_inputs

    def substitute_lock(stack):
        class SubstituteStack:
            def enter_context(self, lock):
                return stack.enter_context(
                    replacement._lock if lock is original_owner._lock else lock
                )

        monkeypatch.setattr(publisher, "_history_owner", replacement)
        lock_inputs(SubstituteStack())
        monkeypatch.setattr(publisher, "_history_owner", original_owner)

    monkeypatch.setattr(publisher, "_lock_inputs", substitute_lock)
    with pytest.raises(app._AssessmentHistoryInvalid):
        _consume(service, first)


@pytest.mark.parametrize("expected", [None, [], object()])
def test_slice2_revalidation_requires_explicit_complete_expectations(
    consumption_case, expected
):
    service, _, _, _, calls = consumption_case
    with pytest.raises(TypeError):
        _recheck(service, expected)
    assert calls == []


@pytest.mark.parametrize("mode", ["selection", "revalidation"])
def test_slice2_final_seal_later_pair_detects_earlier_support_loss(
    consumption_case, monkeypatch, mode
):
    service, first, _, sources, _ = consumption_case
    expected = _capture(service)
    bound = [_interpretation_selectors(source) for source in sources]
    publisher = service._interpretation_service
    authenticate = publisher._authenticate_interpretation_occurrence
    support = {1, 2}
    calls = []

    def complete_support(**selectors):
        calls.append(selectors)
        # Model the released complete-support contract, not selected support.
        if support != {1, 2}:
            assert selectors == bound[1]
            assert selectors["interpretation_history_sequence"] in support
            raise i._InterpretationHistoryInvalid("earlier required support lost")
        value = authenticate(**selectors)
        if len(calls) == 3:
            assert selectors == bound[0]
            support.remove(1)
        return value

    monkeypatch.setattr(
        publisher, "_authenticate_interpretation_occurrence", complete_support
    )
    with pytest.raises(app._AssessmentHistoryInvalid):
        if mode == "selection":
            _consume(service, first)
        else:
            _recheck(service, expected)
    assert calls == bound * 2


@pytest.mark.parametrize("phase", [3, 4])
@pytest.mark.parametrize(
    "field", ["history_namespace_id", "history_sequence", "execution_id", "fingerprint"]
)
def test_slice2_final_seal_checks_each_bound_occurrence(
    consumption_case, monkeypatch, phase, field
):
    service, _, second, sources, _ = consumption_case
    bound = [_interpretation_selectors(source) for source in sources] * 2
    publisher = service._interpretation_service
    authenticate = publisher._authenticate_interpretation_occurrence
    calls = []

    def changed(**selectors):
        calls.append(selectors)
        value = authenticate(**selectors)
        if len(calls) == phase:
            object.__setattr__(
                value, field, 99 if field == "history_sequence" else "changed"
            )
        return value

    monkeypatch.setattr(publisher, "_authenticate_interpretation_occurrence", changed)
    with pytest.raises(app._AssessmentSourceMismatch):
        _consume(service, second)
    assert calls == bound[:phase]


def test_slice2_final_seal_has_only_authentication_and_direct_checks():
    tree = ast.parse(inspect.getsource(app))
    method = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_consume_assessments"
    )
    body = method.body[1].body
    seal_index = next(
        index
        for index, node in enumerate(body)
        if isinstance(node, ast.For)
        and isinstance(node.iter, ast.Name)
        and node.iter.id == "seal_expectations"
    )
    seal = body[seal_index]
    assert [type(node) for node in seal.body] == [ast.Assign, ast.If]
    assert {
        node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
        for node in ast.walk(seal)
        if isinstance(node, ast.Call)
    } == {"_authenticate_consumption_source", "type", "_AssessmentSourceMismatch"}
    tail = body[seal_index + 1 :]
    assert [type(node) for node in tail] == [ast.If, ast.If, ast.Return]
    for statement in tail:
        for node in ast.walk(statement):
            if isinstance(node, ast.Call):
                assert isinstance(node.func, ast.Name)
                assert node.func.id in {
                    "_AssessmentHistoryInvalid",
                    "_AssessmentOccurrenceUnavailable",
                }
            assert not isinstance(
                node,
                (
                    ast.List,
                    ast.Dict,
                    ast.Set,
                    ast.Tuple,
                    ast.ListComp,
                    ast.SetComp,
                    ast.DictComp,
                    ast.GeneratorExp,
                ),
            )


@pytest.mark.parametrize(
    "path,owned",
    [
        ("docs/adr/0040_governed_daily_technical_interpretation.md", True),
        (
            "docs/adr/0041_publication_time_technical_issuance_authority_and_governed_interpretation_value_isolation.md",
            True,
        ),
        (
            "docs/handoffs/v0.80.0-governed-daily-technical-interpretation-handoff.md",
            True,
        ),
        ("README.md", False),
    ],
)
def test_slice2_historical_checkpoint_has_explicit_owned_scope(
    monkeypatch, path, owned
):
    root = Path(__file__).resolve().parents[2]
    checkpoint = "4201d2d851b061808a1712aaa573f272632865c5"
    # The unrelated control really existed at the historical checkpoint.
    subprocess.check_output(["git", "cat-file", "-e", f"{checkpoint}:{path}"], cwd=root)
    read = Path.read_text
    run = subprocess.check_output
    commands = []

    def changed(file, *args, **kwargs):
        value = read(file, *args, **kwargs)
        return value + "\nchanged\n" if file == root / path else value

    def bounded(command, **kwargs):
        commands.append(command)
        assert command[:2] == ["git", "show"]
        assert len(command) == 3
        assert command[2] in {
            checkpoint + ":docs/adr/0040_governed_daily_technical_interpretation.md",
            checkpoint
            + (
                ":docs/adr/0041_publication_time_technical_issuance_"
                "authority_and_governed_interpretation_value_isolation.md"
            ),
            checkpoint
            + (
                ":docs/handoffs/v0.80.0-governed-daily-technical-"
                "interpretation-handoff.md"
            ),
        }
        return run(command, **kwargs)

    monkeypatch.setattr(Path, "read_text", changed)
    monkeypatch.setattr(subprocess, "check_output", bounded)
    if owned:
        with pytest.raises(AssertionError):
            test_frozen_checkpoint_files_unchanged()
    else:
        test_frozen_checkpoint_files_unchanged()
        assert len(commands) == 3
    assert commands
