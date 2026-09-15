from __future__ import annotations

import ast
import inspect
import json
import subprocess
import tomllib
from contextlib import ExitStack
from copy import copy
from dataclasses import FrozenInstanceError, fields, is_dataclass, replace
from datetime import UTC, datetime, timedelta, timezone
from enum import Enum, IntEnum, StrEnum
from itertools import product
from pathlib import Path
from threading import Lock
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
    assert not hasattr(service, "_clock")
    assert len(inspect.signature(Service).parameters) == 1
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


def test_exact_exports_and_no_publication_workflow():
    assert app.__all__ == [
        "PolygonCompletedDailyAssessmentRefusalReason",
        "PolygonCompletedDailyAssessmentRefused",
        "PolygonCompletedDailyAssessmentResult",
        "PolygonCompletedDailyProductionAssessmentApplicationService",
    ]
    assert not [
        name
        for name, member in inspect.getmembers(Service, callable)
        if not name.startswith("_")
    ]
    assert not any(
        hasattr(Service, name)
        for name in ("execute", "get_result_history_as_of", "_publish")
    )
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
    # Compare every tracked file with the authorized checkpoint, including Slice 2.
    changed = subprocess.check_output(
        [
            "git",
            "diff",
            "--name-only",
            "d3ada182be5ff925685879a0c7ef24bf6d8d71d1",
            "--",
        ],
        cwd=root,
        text=True,
    )
    allowed = {
        "src/market_platform/application/polygon_completed_daily_production_assessment.py",
        "tests/unit/test_polygon_completed_daily_production_assessment.py",
        "src/market_platform/application/polygon_completed_daily_production_interpretation.py",
        "tests/unit/test_polygon_completed_daily_production_interpretation.py",
    }
    assert set(changed.splitlines()) <= allowed
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


def test_preparation_no_upstream_execution_or_legacy_assessment(
    preparation_publisher, monkeypatch
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
    service = Service(publisher)
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
        (
            app,
            ("uuid4", "_encode_result", "_public_result_copy", "_reconstruct_result"),
        ),
        (app.a, ("_utc_now",)),
    ):
        for name in names:
            monkeypatch.setattr(owner, name, forbidden)
    owner = service._history_owner
    state, namespace = service._committed, service._namespace
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
