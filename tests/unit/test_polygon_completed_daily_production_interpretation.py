from __future__ import annotations

import inspect
import subprocess
import tomllib
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from copy import deepcopy
from dataclasses import fields, replace
from datetime import timedelta
from pathlib import Path
from uuid import UUID

import pytest
from test_governed_daily_technical_interpretation import (
    SEMANTIC_MUTATIONS,
    assert_enum_free,
    coherently_wrong_semantics,
    legacy_enum_inventory,
    load_pre_b2,
    pre_b2_domain,  # noqa: F401
    public_graph,
    serialized,
)
from test_polygon_completed_daily_production_technical import (
    _forbidden,
)
from test_polygon_completed_daily_production_technical import (
    _request as technical_request,
)
from test_polygon_completed_daily_production_technical import (
    _service as technical_service,
)
from test_polygon_completed_daily_production_technical import (
    authentic as bridge_fixture,  # noqa: F401
)
from test_polygon_completed_daily_production_validation import _Clock

from market_platform._fingerprint import canonical_fingerprint
from market_platform.application import polygon_completed_daily_production_bridge as b
from market_platform.application import (
    polygon_completed_daily_production_interpretation as app,
)
from market_platform.application import (
    polygon_completed_daily_production_technical as t,
)
from market_platform.research import governed_daily_technical_interpretation as domain

R = app.PolygonCompletedDailyInterpretationRefusalReason
Service = app.PolygonCompletedDailyProductionInterpretationApplicationService
Refused = app.PolygonCompletedDailyInterpretationRefused
Request = domain.PolygonCompletedDailyInterpretationRequest


@pytest.fixture(scope="module")
def authentic(bridge_fixture):  # noqa: F811
    source = technical_service(bridge_fixture)
    source.execute(technical_request(bridge_fixture[1]))
    return source, source._history._state[1][0]


def _request(item):
    return Request(
        artifact_reference=item.source.bridge_reference.artifact_reference,
        technical_history_namespace_id=item.history_namespace_id,
        technical_history_sequence=item.history_sequence,
        technical_execution_id=item.execution_id,
        technical_fingerprint=item.fingerprint,
    )


def _service(authentic, clock=None):
    return Service(
        authentic[0], execution_clock=clock or (lambda: authentic[1].available_at)
    )


def _refuse(service, request, reason=None):
    before = service._history._state
    with pytest.raises(Refused) as caught:
        service.execute(request)
    if reason is not None:
        assert caught.value.reason is reason
    assert service._history._state is before
    assert service._history._pending is None
    return caught.value


def _history(service, request, cutoff):
    return service.get_result_history_as_of(
        request.artifact_reference, knowledge_as_of=cutoff
    )


def _refingerprint(item):
    object.__setattr__(item, "fingerprint", canonical_fingerprint(item._payload()))


@pytest.mark.parametrize("surface", ["execute", "history"])
def test_b2_public_graph_has_zero_enum(authentic, surface):
    service = _service(authentic)
    request = _request(authentic[1])
    result = service.execute(request)
    if surface == "history":
        result = _history(service, request, result.available_at)[0]
    assert_enum_free(result)


def test_b2_committed_application_envelope_parity(
    complete_authentic,
    pre_b2_domain,  # noqa: F811
    monkeypatch,
):
    baseline = load_pre_b2(
        "src/market_platform/application/polygon_completed_daily_production_interpretation.py",
        "_pre_b2_governed_application",
    )
    baseline.domain = pre_b2_domain
    baseline.GovernedDailyTechnicalInterpretation = (
        pre_b2_domain.GovernedDailyTechnicalInterpretation
    )
    baseline.PolygonCompletedDailyInterpretationRequest = (
        pre_b2_domain.PolygonCompletedDailyInterpretationRequest
    )

    def uuid():
        return UUID("12345678123456781234567812345678")

    monkeypatch.setattr(baseline, "uuid4", uuid)
    monkeypatch.setattr(app, "uuid4", uuid)
    source, technical = complete_authentic

    def clock():
        return technical.available_at

    old_service = (
        baseline.PolygonCompletedDailyProductionInterpretationApplicationService(
            source, execution_clock=clock
        )
    )
    old = old_service.execute(baseline._reference(technical))
    new_service = Service(source, execution_clock=clock)
    new = new_service.execute(_request(technical))
    assert serialized(new.to_dict()) == serialized(old.to_dict())
    assert serialized(new._payload()) == serialized(old._payload())
    assert new.fingerprint == old.fingerprint
    assert new.interpretation.fingerprint == old.interpretation.fingerprint
    fact = new_service._history._state[1][0]
    assert type(fact) is bytes
    assert fact == app._canonical_bytes(old.to_dict())
    assert_enum_free(new)
    old_read = old_service.get_result_history_as_of(
        old.source_technical_occurrence.artifact_reference,
        knowledge_as_of=old.available_at,
    )[0]
    from enum import Enum

    assert any(isinstance(item, Enum) for _, item in public_graph(old))
    assert any(isinstance(item, Enum) for _, item in public_graph(old_read))


def test_b2_every_refusal_reason_is_an_exact_string():
    from enum import Enum

    assert not issubclass(R, Enum)
    reasons = {value for name, value in vars(R).items() if name.isupper()}
    assert reasons == {
        "technical_occurrence_unavailable",
        "history_incomplete_or_corrupt",
        "source_lineage_mismatch",
        "semantic_execution_or_correspondence_failed",
        "temporal_failure",
        "interpretation_publication_or_copy_failed",
    }
    for reason in reasons:
        assert type(reason) is str
        error = Refused(reason, "test")
        assert type(error.reason) is str
        assert_enum_free(error.reason)
    with pytest.raises(ValueError):
        Refused("invented", "test")
    with pytest.raises(TypeError):
        Refused(R.TEMPORAL_FAILURE, object())


def test_b2_public_mutations_cannot_rewrite_authority_or_legacy(complete_authentic):
    from market_platform.evidence import EvidenceArtifactReference
    from market_platform.research.daily_technical_interpretation import (
        TechnicalComparisonEvidence,
        TechnicalComparisonOperand,
    )
    from market_platform.research.technical_policy import TechnicalPolicyIdentity

    service = _service(complete_authentic)
    request = _request(complete_authentic[1])
    returned = service.execute(request)
    state = service._history._state
    fact = state[1][0]
    expected = returned.to_dict()
    inventory = legacy_enum_inventory()
    assert type(fact) is bytes
    assert fact == app._canonical_bytes(expected)
    assert service._committed is state
    assert not hasattr(service, "_published")
    assert_enum_free(request)
    forbidden = (
        EvidenceArtifactReference,
        TechnicalPolicyIdentity,
        TechnicalComparisonEvidence,
        TechnicalComparisonOperand,
    )
    assert not any(isinstance(item, forbidden) for _, item in public_graph(returned))

    def mutate(victim, name, value):
        object.__setattr__(victim, name, value)
        assert service._history._state is state
        assert state[1][0] == fact
        assert inventory == legacy_enum_inventory()

    mutations = [
        ("interpretation.trend_direction", "unavailable"),
        ("interpretation.momentum_direction", "unavailable"),
        ("interpretation.volatility_state", "unavailable"),
        ("interpretation.extension_state", "unavailable"),
        ("interpretation.source_quality", "degraded"),
        (
            "interpretation.source_warnings",
            ("insufficient_profile_history", "stale_evidence"),
        ),
        ("interpretation.interpretation_policy_identity.policy_kind", "corrupt"),
        (
            "interpretation.interpretation_policy_identity.configuration.rsi_neutral",
            51.0,
        ),
        (
            "source_technical_occurrence.artifact_reference.information_class",
            "source_measurement",
        ),
        ("source_technical_occurrence.artifact_reference.authority", "platform_origin"),
        ("source_technical_occurrence.artifact_reference.artifact_id", "other"),
    ]
    for path, value in mutations:
        public = _history(service, request, returned.available_at)[0]
        assert_enum_free(public)
        victim = public
        names = path.split(".")
        for name in names[:-1]:
            victim = getattr(victim, name)
        mutate(victim, names[-1], value)
        # Attempt coherent nested, content, and envelope refingerprinting.
        for wrapper, payload in (
            (
                public.source_technical_occurrence.artifact_reference,
                "_fingerprint_payload",
            ),
            (
                public.interpretation.interpretation_policy_identity,
                "_fingerprint_payload",
            ),
            (public.interpretation, "_fingerprint_payload"),
            (public, "_payload"),
        ):
            # Closed validation can reject the coherent rewrite early.
            with suppress(ValueError, TypeError):
                mutate(
                    wrapper,
                    "fingerprint",
                    canonical_fingerprint(getattr(wrapper, payload)()),
                )
        assert service._history._state is state
        assert state[1][0] == fact
        second = _history(service, request, returned.available_at)[0]
        assert_enum_free(second)
        assert second.to_dict() == expected
        assert not app._graph_ids(public) & app._graph_ids(second)
        assert inventory == legacy_enum_inventory()
    # Exercise all 18 comparisons and both operand-source storage paths.
    for index in range(18):
        public = app._reconstruct_result(fact)
        item = public.interpretation.comparison_evidence[index]
        mutate(item, "operator", "less_than_or_equal")
        mutate(item.left_operand, "source", "interpretation_policy_derived")
        mutate(item.right_operand, "source", "technical_analysis_snapshot")
        mutate(item.left_operand, "field", "corrupt")
        mutate(item.right_operand, "value", 123.0)
        mutate(item, "satisfied", not item.satisfied)
        assert state[1][0] == fact
        fresh = app._reconstruct_result(fact)
        assert_enum_free(fresh)
        assert fresh.to_dict() == expected
    assert inventory == legacy_enum_inventory()
    later = service.execute(request)
    assert_enum_free(later)
    assert later.interpretation.to_dict() == returned.interpretation.to_dict()
    assert service._history._state[1][0] == fact
    assert service._history._pending is None


@pytest.mark.parametrize("seam", ["normalize", "encode", "decode", "reconstruct"])
def test_b2_codec_failure_is_atomic_and_reuses_sequence(authentic, seam):
    service = _service(authentic)
    request = _request(authentic[1])
    first = service.execute(request)
    before = service._history._state
    original = domain.interpret_governed_daily_technical_snapshot
    failures = []

    def arm(**kwargs):
        if seam == "normalize":

            def fail_normalization(value):
                failures.append(seam)
                return _forbidden(value)

            armed.setattr(domain, "_scalar_policy", fail_normalization)
        content = original(**kwargs)
        if seam != "normalize":
            name = {
                "encode": "_canonical_bytes",
                "decode": "_decode_result",
                "reconstruct": "_reconstruct_result",
            }[seam]
            boundary = getattr(app, name)

            def fail_new_occurrence(value):
                is_new = (
                    value.get("history_sequence") == 2
                    if type(value) is dict
                    else b'"history_sequence":2' in value
                )
                if is_new:
                    failures.append(seam)
                    return _forbidden(value)
                return boundary(value)

            armed.setattr(app, name, fail_new_occurrence)
        return content

    with pytest.MonkeyPatch.context() as armed:
        armed.setattr(domain, "interpret_governed_daily_technical_snapshot", arm)
        error = _refuse(service, request)
        assert type(error.reason) is str
        assert service._history._state is before
        assert failures == [seam]
    assert (
        _history(service, request, first.available_at)[0].to_dict() == first.to_dict()
    )
    assert service.execute(request).history_sequence == 2


@pytest.fixture(scope="module")
def b2_projection(authentic):
    source = authentic[1]
    instrument, _ = _service(authentic)._authenticate(source)
    content = domain.interpret_governed_daily_technical_snapshot(
        snapshot=source.snapshot,
        source_technical_occurrence=_request(source),
        canonical_instrument=instrument,
        source_governed_dataset_fingerprint=source.source.dataset_fingerprint,
    )
    value = object.__new__(app.PolygonCompletedDailyInterpretationResult)
    for key, item in {
        "interpretation": content,
        "technical_available_at": source.available_at,
        "execution_id": app._PREFIX + ":" + "1" * 32,
        "history_namespace_id": app._PREFIX + "_history:" + "2" * 32,
        "history_sequence": 1,
        "execution_started_at": source.available_at,
        "execution_completed_at": source.available_at,
        "available_at": source.available_at,
    }.items():
        object.__setattr__(value, key, item)
    _refingerprint(value)
    return value.to_dict()


@pytest.mark.parametrize(
    "attack",
    [
        "mutable",
        "duplicate_key",
        "whitespace",
        "extra",
        "int_float",
        "missing",
        "schema",
        "fingerprint",
        "timestamp",
        "nan",
        "negative_zero",
    ],
)
def test_b2_decoder_rejects_noncanonical_complete_projection(b2_projection, attack):
    projection = deepcopy(b2_projection)
    fact = app._canonical_bytes(projection)
    if attack == "mutable":
        supplied = bytearray(fact)
    elif attack == "duplicate_key":
        supplied = b'{"history_sequence":1,' + fact[1:]
    elif attack == "whitespace":
        supplied = b" " + fact
    else:
        if attack == "extra":
            projection["extra"] = None
        elif attack == "missing":
            projection["interpretation"].pop("source_warnings")
        elif attack == "schema":
            projection["interpretation"]["source_technical_occurrence"][
                "artifact_reference"
            ]["schema_version"] = "other/v1"
        elif attack == "fingerprint":
            projection["interpretation"]["fingerprint"] = "sha256:" + "0" * 64
        elif attack == "timestamp":
            projection["available_at"] = projection["available_at"].replace(
                "+00:00", "Z"
            )
        else:
            projection["interpretation"]["interpretation_policy_identity"][
                "configuration"
            ]["rsi_neutral"] = {
                "int_float": 50,
                "nan": float("nan"),
                "negative_zero": -0.0,
            }[attack]
        import json

        supplied = json.dumps(
            projection, sort_keys=True, separators=(",", ":")
        ).encode()
    with pytest.raises((TypeError, ValueError, KeyError)):
        app._reconstruct_result(supplied)


def test_exact_handoff_envelope_and_original_context(authentic, monkeypatch):
    source, technical = authentic
    service = _service(authentic)
    request = _request(technical)
    original = domain.interpret_governed_daily_technical_snapshot
    calls = []
    contexts = []
    resolve = source._resolve
    before = technical.to_dict()
    bridge = source._bridge_service._history._state[1][0]
    material = bridge.qualification.construction_result.material
    instrument = material.mapping_resolution_provenance.mapping.canonical_instrument

    def historical(reference, started):
        contexts.append((reference, started))
        return resolve(reference, started)

    def interpret(**kwargs):
        assert kwargs["snapshot"] is technical.snapshot
        assert kwargs["source_technical_occurrence"] == request
        assert kwargs["source_technical_occurrence"] is not request
        assert kwargs["canonical_instrument"] == instrument
        assert (
            kwargs["source_governed_dataset_fingerprint"] == bridge.dataset_fingerprint
        )
        calls.append(kwargs)
        return original(**kwargs)

    monkeypatch.setattr(source, "_resolve", historical)
    monkeypatch.setattr(
        domain, "interpret_governed_daily_technical_snapshot", interpret
    )
    result = service.execute(request)
    assert len(calls) == 1
    assert contexts and all(
        reference == technical.source.bridge_reference
        and started == technical.execution_started_at
        for reference, started in contexts
    )
    assert technical.to_dict() == before
    assert type(result.interpretation) is domain.GovernedDailyTechnicalInterpretation
    assert result.source_technical_occurrence == request
    assert result.source_content_fingerprint == technical.snapshot.fingerprint
    assert result.technical_available_at == technical.available_at
    assert result.analysis_as_of == technical.analysis_as_of < result.available_at
    assert (
        result.execution_started_at
        == result.execution_completed_at
        == result.available_at
    )
    payload = result.to_dict()
    assert (
        payload["schema_version"] == "polygon_completed_daily_interpretation_result/v1"
    )
    assert payload["operation"] == (
        "production.polygon_completed_daily.daily_technical_interpretation.application"
    )
    assert payload["operation_version"] == "1.0.0"
    assert payload["executor"] == (
        "market_platform.application.polygon_completed_daily_production_interpretation/v1"
    )
    assert canonical_fingerprint(result._payload()) == result.fingerprint
    assert result.fingerprint != result.interpretation.fingerprint
    assert result.interpretation.fingerprint == canonical_fingerprint(
        result.interpretation._fingerprint_payload()
    )


@pytest.mark.parametrize("selector", [field.name for field in fields(Request)])
def test_each_selector_must_match(authentic, monkeypatch, selector):
    request = _request(authentic[1])
    value = getattr(request, selector)
    if selector == "artifact_reference":
        value = replace(value, artifact_fingerprint="sha256:" + "0" * 64)
    elif selector.endswith("sequence"):
        value += 1
    elif selector.endswith("fingerprint"):
        value = "sha256:" + "0" * 64
    else:
        value = value.split(":")[0] + ":" + "0" * 32
    service = _service(authentic)
    monkeypatch.setattr(
        domain, "interpret_governed_daily_technical_snapshot", _forbidden
    )
    _refuse(service, replace(request, **{selector: value}), R.TECHNICAL_UNAVAILABLE)


@pytest.mark.parametrize(
    "kind", ["snapshot", "technical", "content", "fingerprint", "dataset"]
)
def test_no_bearer_authority(authentic, kind):
    service = _service(authentic)
    technical = authentic[1]
    content = service.execute(_request(technical)).interpretation
    supplied = {
        "snapshot": technical.snapshot,
        "technical": technical,
        "content": content,
        "fingerprint": technical.fingerprint,
        "dataset": technical.source.dataset_fingerprint,
    }[kind]
    with pytest.raises(TypeError):
        service.execute(supplied)


@pytest.mark.parametrize(
    "keyword", ["policy", "configuration", "snapshot", "history", "analysis_as_of"]
)
def test_closed_api(authentic, keyword):
    service = _service(authentic)
    with pytest.raises(TypeError):
        service.execute(_request(authentic[1]), **{keyword: object()})
    with pytest.raises(TypeError):
        Service(authentic[0], **{keyword: object()})
    with pytest.raises(TypeError):
        replace(_request(authentic[1]), **{keyword: object()})
    assert {
        name
        for name, member in inspect.getmembers(Service, callable)
        if not name.startswith("_")
    } == {"execute", "get_result_history_as_of"}
    with pytest.raises(TypeError):
        app.PolygonCompletedDailyInterpretationResult()
    with pytest.raises(TypeError):
        Service(object())
    with pytest.raises(TypeError):
        Service(authentic[0], execution_clock=42)


@pytest.mark.parametrize(
    "kind",
    [
        "missing",
        "truncated",
        "duplicate",
        "clone",
        "coherent_clone",
        "namespace",
        "sequence",
        "state_list",
        "entries_list",
        "boolean",
        "history_replaced",
        "bridge",
        "qualification",
        "construction",
    ],
)
def test_upstream_history_corruption_before_semantics(authentic, monkeypatch, kind):
    service = _service(authentic)
    source, item = authentic
    state = source._history._state
    bridge = source._bridge_service
    if kind == "bridge":
        monkeypatch.setattr(bridge._history, "_state", (1, ()))
    elif kind == "qualification":
        monkeypatch.setattr(bridge._qualification_service._history, "_state", (1, ()))
    elif kind == "construction":
        admission = bridge._qualification_service._validity_service._admission_service
        monkeypatch.setattr(admission._construction_service._history, "_state", (1, ()))
    elif kind == "history_replaced":
        new = t._TechnicalHistory()
        new._namespace_id = source._history._namespace_id
        new._state = state
        monkeypatch.setattr(source, "_history", new)
    elif kind == "namespace":
        monkeypatch.setattr(source._history, "_namespace_id", "wrong")
    else:
        clone = deepcopy(item)
        if kind == "coherent_clone":
            object.__setattr__(clone.snapshot, "latest_close", 123.0)
            object.__setattr__(
                clone.snapshot,
                "fingerprint",
                canonical_fingerprint(clone.snapshot._fingerprint_payload()),
            )
            _refingerprint(clone)
            clone.to_dict()
        changed = {
            "missing": (1, ()),
            "truncated": (2, ()),
            "duplicate": (3, (item, item)),
            "clone": (2, (clone,)),
            "coherent_clone": (2, (clone,)),
            "sequence": (3, (item,)),
            "state_list": list(state),
            "entries_list": (2, [item]),
            "boolean": (True, ()),
        }[kind]
        monkeypatch.setattr(source._history, "_state", changed)
    monkeypatch.setattr(
        domain, "interpret_governed_daily_technical_snapshot", _forbidden
    )
    _refuse(service, _request(item), R.HISTORY_INVALID)


@pytest.mark.parametrize(
    "field", ["snapshot", "lineage", "canonical_subject", "trading_identity"]
)
def test_changed_source_refuses(authentic, monkeypatch, field):
    service = _service(authentic)
    item = authentic[1]
    bridge = authentic[0]._bridge_service._history._state[1][0]
    material = bridge.qualification.construction_result.material
    if field == "snapshot":
        monkeypatch.setattr(type(item.snapshot), "to_dict", lambda self: {})
    elif field == "lineage":
        bad = deepcopy(item.source)
        object.__setattr__(bad, "dataset_fingerprint", "sha256:" + "0" * 64)
        monkeypatch.setattr(t, "_source_lineage", lambda bridge: bad)
    else:
        mapping = material.mapping_resolution_provenance.mapping
        if field == "canonical_subject":
            bad = replace(material.canonical_subject, subject_id="OTHER")
            original = material.canonical_subject
            object.__setattr__(material, "canonical_subject", bad)
        else:
            original = mapping.canonical_instrument
            bad = replace(
                original,
                trading_identity=replace(original.trading_identity, symbol="OTHER"),
            )
            object.__setattr__(mapping, "canonical_instrument", bad)
        try:
            _refuse(service, _request(item), R.HISTORY_INVALID)
        finally:
            if field == "canonical_subject":
                object.__setattr__(material, "canonical_subject", original)
            else:
                object.__setattr__(mapping, "canonical_instrument", original)
        return
    _refuse(service, _request(item), R.HISTORY_INVALID)


@pytest.mark.parametrize(
    "phase", ["semantic", "completion", "stage", "copy", "availability"]
)
def test_source_change_at_every_fallible_seam(authentic, monkeypatch, phase):
    service = _service(authentic)
    source, item = authentic
    request = _request(item)

    def corrupt():
        clone = deepcopy(item)
        monkeypatch.setattr(source._history, "_state", (2, (clone,)))

    if phase == "semantic":
        original = domain.interpret_governed_daily_technical_snapshot

        def semantic(**kwargs):
            result = original(**kwargs)
            corrupt()
            return result

        monkeypatch.setattr(
            domain, "interpret_governed_daily_technical_snapshot", semantic
        )
    elif phase == "stage":
        original = service._history._stage_publication

        def stage(result):
            original(result)
            corrupt()

        monkeypatch.setattr(service._history, "_stage_publication", stage)
    elif phase == "copy":
        original = app._public_result_copy

        def copy(result):
            public = original(result)
            corrupt()
            return public

        monkeypatch.setattr(app, "_public_result_copy", copy)
    else:
        ticks = []

        def clock():
            ticks.append(1)
            if len(ticks) == (2 if phase == "completion" else 3):
                corrupt()
            return item.available_at

        service._clock = clock
    _refuse(
        service,
        request,
        R.SOURCE_MISMATCH if phase == "semantic" else R.PUBLICATION_FAILED,
    )


@pytest.mark.parametrize(
    "field",
    [
        "source_technical_occurrence",
        "canonical_instrument_id",
        "source_trading_identity",
        "analysis_as_of",
        "source_technical_analysis_snapshot_fingerprint",
        "source_governed_dataset_fingerprint",
        "source_research_dataset_content_fingerprint",
        "source_quality",
        "source_warnings",
        "type",
    ],
)
def test_semantic_source_correspondence(authentic, monkeypatch, field):
    service = _service(authentic)
    original = domain.interpret_governed_daily_technical_snapshot

    def changed(**kwargs):
        result = original(**kwargs)
        if field == "type":
            return object()
        value = getattr(result, field)
        if field == "source_technical_occurrence":
            value = replace(value, technical_history_sequence=99)
        elif field == "canonical_instrument_id":
            value = replace(value, instrument_id="OTHER")
        elif field == "source_trading_identity":
            value = replace(value, symbol="OTHER")
        elif field == "analysis_as_of":
            value += timedelta(days=1)
        elif field == "source_quality":
            value = "complete"
        elif field == "source_warnings":
            value = ()
        else:
            value = "sha256:" + "0" * 64
        return replace(result, **{field: value})

    monkeypatch.setattr(domain, "interpret_governed_daily_technical_snapshot", changed)
    _refuse(service, _request(authentic[1]), R.SEMANTIC_FAILED)


def test_occurrence_determinism_and_replay_cutoffs(authentic):
    start = authentic[1].available_at
    service = _service(
        authentic, _Clock(*(start + timedelta(seconds=i) for i in range(6)))
    )
    request = _request(authentic[1])
    first, second = service.execute(request), service.execute(request)
    assert first.interpretation == second.interpretation
    assert first.execution_id != second.execution_id
    assert first.fingerprint != second.fingerprint
    assert (first.history_sequence, second.history_sequence) == (1, 2)
    assert first.analysis_as_of == second.analysis_as_of < first.execution_started_at
    assert (
        _history(service, request, first.available_at - timedelta(microseconds=1)) == ()
    )
    assert _history(service, request, first.available_at) == (first,)
    assert _history(service, request, second.available_at) == (first, second)


def test_different_technical_occurrence_changes_content(bridge_fixture):  # noqa: F811
    source = technical_service(bridge_fixture, lambda: bridge_fixture[1].available_at)
    service = Service(source, execution_clock=lambda: bridge_fixture[1].available_at)
    one = source.execute(technical_request(bridge_fixture[1]))
    first = service.execute(_request(one))
    two = source.execute(technical_request(bridge_fixture[1]))
    second = service.execute(_request(two))
    assert one.snapshot.fingerprint == two.snapshot.fingerprint
    assert first.interpretation.fingerprint != second.interpretation.fingerprint


@pytest.mark.parametrize(
    "phase", ["start", "completion", "publication", "prior_publication"]
)
def test_temporal_refusals(authentic, phase):
    start = authentic[1].available_at
    early = start - timedelta(microseconds=1)
    clocks = {
        "start": _Clock(early),
        "completion": _Clock(start, early),
        "publication": _Clock(start, start, early),
        "prior_publication": lambda: start + timedelta(days=1),
    }
    service = _service(authentic, clocks[phase])
    request = _request(authentic[1])
    if phase == "prior_publication":
        service.execute(request)
        service._clock = lambda: start
    _refuse(
        service,
        request,
        R.TECHNICAL_UNAVAILABLE if phase == "start" else R.TEMPORAL_FAILURE,
    )


@pytest.mark.parametrize("phase", ["semantic", "stage", "copy", "stage_validation"])
def test_failure_atomicity_and_sequence_reuse(authentic, monkeypatch, phase):
    service = _service(authentic)
    request = _request(authentic[1])
    with monkeypatch.context() as patch:
        if phase == "semantic":
            patch.setattr(
                domain, "interpret_governed_daily_technical_snapshot", _forbidden
            )
        elif phase == "copy":
            patch.setattr(app, "_public_result_copy", _forbidden)
        elif phase == "stage":
            patch.setattr(service._history, "_stage_publication", _forbidden)
        else:

            def stage(result):
                service._history._pending = result
                object.__setattr__(result, "fingerprint", "sha256:" + "0" * 64)

            patch.setattr(service._history, "_stage_publication", stage)
        _refuse(
            service,
            request,
            R.SEMANTIC_FAILED if phase == "semantic" else R.PUBLICATION_FAILED,
        )
    assert service.execute(request).history_sequence == 1


@pytest.mark.parametrize(
    "field",
    [
        "execution_id",
        "history_namespace_id",
        "history_sequence",
        "execution_started_at",
        "execution_completed_at",
        "available_at",
        "technical_available_at",
        "interpretation",
    ],
)
def test_coherent_stage_rewrite_refused(authentic, monkeypatch, field):
    service = _service(authentic)
    original = service._history._stage_publication

    def stage(result):
        original(result)
        value = getattr(result, field)
        if field == "interpretation":
            value = replace(
                value, source_governed_dataset_fingerprint="sha256:" + "0" * 64
            )
        elif field.endswith("_id"):
            value = value.split(":")[0] + ":" + "0" * 32
        elif field == "history_sequence":
            value = 99
        elif field in ("technical_available_at", "execution_started_at"):
            value -= timedelta(seconds=1)
        else:
            value += timedelta(seconds=1)
        object.__setattr__(result, field, value)
        _refingerprint(result)

    monkeypatch.setattr(service._history, "_stage_publication", stage)
    _refuse(service, _request(authentic[1]), R.PUBLICATION_FAILED)


@pytest.mark.parametrize("kind", ["alias", "nested_alias", "coherent_content"])
def test_public_copy_seam_cannot_publish_bad_graph(authentic, monkeypatch, kind):
    service = _service(authentic)

    def bad_copy(result):
        if kind == "alias":
            return result
        public = deepcopy(result)
        if kind == "nested_alias":
            object.__setattr__(public, "interpretation", result.interpretation)
        else:
            object.__setattr__(
                public,
                "interpretation",
                replace(
                    public.interpretation,
                    source_governed_dataset_fingerprint="sha256:" + "0" * 64,
                ),
            )
            _refingerprint(public)
        return public

    monkeypatch.setattr(app, "_public_result_copy", bad_copy)
    _refuse(service, _request(authentic[1]), R.PUBLICATION_FAILED)


def test_duplicate_execution_id_refuses(authentic, monkeypatch):
    service = _service(authentic)
    request = _request(authentic[1])
    first = service.execute(request)
    monkeypatch.setattr(
        app, "uuid4", lambda: UUID(hex=first.execution_id.split(":")[1])
    )
    _refuse(service, request, R.PUBLICATION_FAILED)
    assert service._history._state[0] == 2


def test_final_clock_under_complete_ordered_locks(authentic, monkeypatch):
    source, technical = authentic
    service = _service(authentic)
    locks = []

    class RecordingStack:
        def enter_context(self, lock):
            locks.append(lock)

    service._lock_inputs(RecordingStack())
    bridge = source._bridge_service
    qualification = bridge._qualification_service
    validity = qualification._validity_service
    admission = validity._admission_service
    assert locks == [
        admission._construction_service._history._lock,
        admission._validation_service._history._lock,
        admission._freshness_service._history._lock,
        admission._history._lock,
        validity._history._lock,
        qualification._history._lock,
        bridge._history._lock,
        source._history._lock,
        service._history._lock,
    ]
    ticks = []
    original = source._lock_inputs
    acquisitions = []

    def lock_inputs(stack):
        acquisitions.append(1)
        original(stack)

    monkeypatch.setattr(source, "_lock_inputs", lock_inputs)

    def clock():
        ticks.append(1)
        if len(ticks) == 3:
            assert all(lock.locked() for lock in locks)
            assert service._history._pending is not None
            assert service._history._state == (1, ())
        return technical.available_at

    service._clock = clock
    service.execute(_request(technical))
    assert len(ticks) == 3 and len(acquisitions) == 1
    assert not any(lock.locked() for lock in locks)


@pytest.mark.parametrize(
    "kind",
    [
        "missing",
        "reset",
        "duplicate",
        "namespace",
        "sequence",
        "fingerprint",
        "availability",
        "state_list",
        "entries_list",
        "boolean",
        "coherent_content",
    ],
)
def test_own_history_corruption(authentic, monkeypatch, kind):
    service = _service(authentic)
    request = _request(authentic[1])
    first = service.execute(request)
    service._clock = lambda: first.available_at + timedelta(seconds=2)
    second = service.execute(request)
    one, two = (app._reconstruct_result(fact) for fact in service._history._state[1])
    if kind == "availability":
        object.__setattr__(
            one, "available_at", second.available_at + timedelta(seconds=1)
        )
        _refingerprint(one)
    if kind == "duplicate":
        object.__setattr__(two, "execution_id", one.execution_id)
        _refingerprint(two)
    if kind in (
        "namespace",
        "sequence",
        "fingerprint",
        "availability",
        "coherent_content",
    ):
        field, value = {
            "namespace": ("history_namespace_id", app._PREFIX + "_history:" + "0" * 32),
            "sequence": ("history_sequence", 7),
            "fingerprint": ("fingerprint", "sha256:" + "0" * 64),
            "availability": ("available_at", second.available_at),
            "coherent_content": (
                "interpretation",
                replace(
                    two.interpretation,
                    source_governed_dataset_fingerprint="sha256:" + "0" * 64,
                ),
            ),
        }[kind]
        object.__setattr__(two, field, value)
        if kind != "fingerprint":
            _refingerprint(two)
        state = (3, (one, two))
    else:
        state = {
            "missing": (3, (one,)),
            "reset": (1, ()),
            "duplicate": (3, (one, two)),
            "state_list": [3, (one, two)],
            "entries_list": (3, [one, two]),
            "boolean": (True, ()),
        }[kind]
    if type(state) is tuple and type(state[1]) is tuple:
        state = (
            state[0],
            tuple(
                app._canonical_bytes(
                    {**item._payload(), "fingerprint": item.fingerprint}
                )
                for item in state[1]
            ),
        )
    monkeypatch.setattr(service._history, "_state", state)
    monkeypatch.setattr(
        domain, "interpret_governed_daily_technical_snapshot", _forbidden
    )
    _refuse(service, request, R.HISTORY_INVALID)
    with pytest.raises(Refused) as caught:
        _history(service, request, second.available_at)
    assert caught.value.reason is R.HISTORY_INVALID


@pytest.mark.parametrize(
    "upstream", ["technical", "bridge", "qualification", "construction"]
)
def test_history_read_reauthenticates_even_before_visibility(
    authentic, monkeypatch, upstream
):
    service = _service(authentic)
    request = _request(authentic[1])
    result = service.execute(request)
    technical = authentic[0]
    bridge = technical._bridge_service
    qualified = bridge._qualification_service
    construction = qualified._validity_service._admission_service._construction_service
    target = {
        "technical": technical,
        "bridge": bridge,
        "qualification": qualified,
        "construction": construction,
    }[upstream]
    monkeypatch.setattr(target._history, "_state", (1, ()))
    for cutoff in (result.available_at, result.analysis_as_of):
        with pytest.raises(Refused) as caught:
            _history(service, request, cutoff)
        assert caught.value.reason is R.HISTORY_INVALID
    _refuse(service, request, R.HISTORY_INVALID)


def test_defensive_graphs_and_coherent_mutation(authentic):
    service = _service(authentic)
    request = _request(authentic[1])
    returned = service.execute(request)
    retained = app._reconstruct_result(service._history._state[1][0])
    one = _history(service, request, returned.available_at)[0]
    two = _history(service, request, returned.available_at)[0]
    copies = (returned, retained, one, two)
    for left_index, left in enumerate(copies):
        for right in copies[left_index + 1 :]:
            assert not app._graph_ids(left) & app._graph_ids(right)
    expected = retained.to_dict()
    changed = replace(
        returned.interpretation,
        source_technical_occurrence=replace(request, technical_history_sequence=99),
        canonical_instrument_id=replace(
            returned.interpretation.canonical_instrument_id, instrument_id="OTHER"
        ),
    )
    object.__setattr__(returned, "interpretation", changed)
    _refingerprint(returned)
    returned.to_dict()
    object.__setattr__(
        one.interpretation.interpretation_policy_identity.configuration,
        "rsi_neutral",
        1.0,
    )
    object.__setattr__(
        one.source_technical_occurrence.artifact_reference, "artifact_id", "rewritten"
    )
    object.__setattr__(one.interpretation.source_trading_identity, "symbol", "OTHER")
    projection = two.to_dict()
    projection["interpretation"]["source_warnings"].append("invented")
    projection["interpretation"]["interpretation_policy_identity"]["configuration"][
        "rsi_neutral"
    ] = 4
    assert retained.to_dict() == two.to_dict() == expected
    assert _history(service, request, two.available_at)[0].to_dict() == expected
    assert service.execute(request).history_sequence == 2


def test_empty_history_and_concurrent_occurrences(authentic):
    service = _service(authentic)
    request = _request(authentic[1])
    assert service._history._state == (1, ())
    assert _history(service, request, authentic[1].available_at) == ()
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = tuple(pool.map(lambda _: service.execute(request), range(3)))
    assert sorted(item.history_sequence for item in results) == [1, 2, 3]
    assert len({item.execution_id for item in results}) == 3
    assert len(_history(service, request, authentic[1].available_at)) == 3


def test_forbidden_execution_paths_and_public_history_apis(authentic, monkeypatch):
    from market_platform.application.daily_technical_strategy_service import (
        DailyTechnicalStrategyApplicationService,
    )
    from market_platform.data.providers.polygon import PolygonProvider
    from market_platform.research import (
        daily_analysis,
        daily_instrument_integrity,
        daily_technical_assessment,
        daily_technical_interpretation,
        daily_technical_strategy,
    )

    source = authentic[0]
    service = _service(authentic)
    bridge = source._bridge_service
    qualified = bridge._qualification_service
    admission = qualified._validity_service._admission_service
    for owner, names in (
        (t.technical, ("analyze_daily_technical_snapshot",)),
        (type(source), ("execute", "get_result_history_as_of")),
        (type(bridge), ("bridge", "get_bridge_history_as_of")),
        (b, ("_convert_material", "_prepare", "prepare_completed_daily_price_series")),
        (type(qualified), ("qualify",)),
        (b.q, ("_qualify_material",)),
        (b.q.evaluation, ("evaluate_evidence_admission_as_of",)),
        (type(admission), ("issue_admission",)),
        (type(qualified._validity_service), ("issue_initial_active",)),
        (type(admission._validation_service), ("execute_profile",)),
        (type(admission._freshness_service), ("execute_task", "execute_admission")),
        (PolygonProvider, ("get_daily_prices", "get_completed_daily_acquisition")),
        (daily_analysis.DailyTechnicalResearchWorkflow, ("run",)),
        (
            daily_instrument_integrity.IntegrityCheckedDailyTechnicalResearchWorkflow,
            ("run",),
        ),
        (daily_technical_interpretation, ("interpret_daily_technical_research",)),
        (daily_technical_assessment, ("assess_daily_technical_interpretation",)),
        (daily_technical_strategy, ("derive_daily_technical_strategy",)),
        (DailyTechnicalStrategyApplicationService, ("execute",)),
    ):
        for name in names:
            monkeypatch.setattr(owner, name, _forbidden)
    result = service.execute(_request(authentic[1]))
    assert _history(service, _request(authentic[1]), result.available_at) == (result,)
    source_code = inspect.getsource(app)
    assert "classic_states(" not in source_code
    assert "build_classic_comparison_evidence(" not in source_code


def test_frozen_files_exports_version_and_output_scope():
    from test_evidence_public_api import EXPECTED_PUBLIC_API

    import market_platform.evidence as evidence

    assert tuple(evidence.__all__) == EXPECTED_PUBLIC_API
    assert len(evidence.__all__) == len(set(evidence.__all__)) == 69
    root = Path(__file__).resolve().parents[2]
    assert (
        tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
        == "0.1.0"
    )
    frozen = [
        "docs/adr/0040_governed_daily_technical_interpretation.md",
        "docs/adr/0041_publication_time_technical_issuance_authority_and_governed_interpretation_value_isolation.md",
        "src/market_platform/research/daily_technical_interpretation.py",
        "src/market_platform/research/daily_technical_assessment.py",
        "src/market_platform/application/polygon_completed_daily_production_bridge.py",
        "src/market_platform/application/polygon_completed_daily_production_technical.py",
        "pyproject.toml",
    ]
    assert (
        subprocess.check_output(["git", "diff", "HEAD", "--", *frozen], cwd=root) == b""
    )
    names = {
        field.name for field in fields(app.PolygonCompletedDailyInterpretationResult)
    }
    assert names == {
        "interpretation",
        "technical_available_at",
        "execution_id",
        "history_namespace_id",
        "history_sequence",
        "execution_started_at",
        "execution_completed_at",
        "available_at",
        "fingerprint",
    }
    assert "integrity" not in inspect.getsource(app)


@pytest.mark.parametrize("timing", ["before_construction", "before_observation"])
@pytest.mark.parametrize("rewrite", [False, True])
def test_b1_first_seen_replacement_refused(bridge_fixture, timing, rewrite):  # noqa: F811
    source = technical_service(bridge_fixture, lambda: bridge_fixture[1].available_at)
    if timing == "before_observation":
        service = Service(
            source, execution_clock=lambda: bridge_fixture[1].available_at
        )
    public = source.execute(technical_request(bridge_fixture[1]))
    if rewrite:
        object.__setattr__(
            public.snapshot, "latest_close", public.snapshot.latest_close + 1
        )
        from test_polygon_completed_daily_production_technical import (
            _refingerprint_snapshot,
        )

        _refingerprint_snapshot(public.snapshot)
        _refingerprint(public)
    public.to_dict()  # Coherent complete projection, never an issuance credential.
    source._history._state = (2, (public,))
    if timing == "before_construction":
        with pytest.raises(app.PolygonCompletedDailyInterpretationRefused):
            Service(source)
    else:
        _refuse(service, _request(public))


def test_b1_authentic_appends_and_consumed_replacement(bridge_fixture):  # noqa: F811
    instant = bridge_fixture[1].available_at
    source = technical_service(bridge_fixture, lambda: instant)
    service = Service(source, execution_clock=lambda: instant)
    one = source.execute(technical_request(bridge_fixture[1]))
    assert service.execute(_request(one)).source_technical_occurrence == _request(one)
    two = source.execute(technical_request(bridge_fixture[1]))
    assert service.execute(_request(two)).source_technical_occurrence == _request(two)
    source._history._state = (3, (one, source._history._state[1][1]))
    # Even discarding downstream observation anchors cannot adopt a replacement.
    service._observed = ()
    service._retention = ()
    _refuse(service, _request(two))


def test_zero_retained_matches(bridge_fixture):  # noqa: F811
    source = technical_service(bridge_fixture)
    service = Service(source, execution_clock=lambda: bridge_fixture[1].available_at)
    reference = bridge_fixture[1].qualification.construction_result.artifact.reference()
    request = Request(
        artifact_reference=reference,
        technical_history_namespace_id=source._history._namespace_id,
        technical_history_sequence=1,
        technical_execution_id="polygon_completed_daily_technical:" + "0" * 32,
        technical_fingerprint="sha256:" + "0" * 64,
    )
    _refuse(service, request, R.TECHNICAL_UNAVAILABLE)


@pytest.mark.parametrize("kind", ["bridge_clone", "bridge_store", "own_store"])
def test_coherent_store_replacements_refused(authentic, monkeypatch, kind):
    from copy import copy

    service = _service(authentic)
    bridge = authentic[0]._bridge_service
    if kind == "bridge_clone":
        # Preserve the authentic qualification pointer; Slice 8's resolver alone
        # cannot distinguish this shallow replacement from the original bridge.
        state = bridge._history._state
        monkeypatch.setattr(bridge._history, "_state", (state[0], (copy(state[1][0]),)))
    else:
        owner = service if kind == "own_store" else bridge
        monkeypatch.setattr(owner, "_history", copy(owner._history))
    _refuse(service, _request(authentic[1]), R.HISTORY_INVALID)


@pytest.mark.parametrize("kind", ["alias", "changed", "lost_provenance"])
def test_history_copy_failure_is_closed(authentic, monkeypatch, kind):
    service = _service(authentic)
    request = _request(authentic[1])
    result = service.execute(request)
    before = service._history._state

    def bad_copy(item):
        if kind == "alias":
            return item
        public = deepcopy(item)
        if kind == "changed":
            object.__setattr__(public, "execution_id", app._PREFIX + ":" + "0" * 32)
            _refingerprint(public)
        else:
            monkeypatch.setattr(authentic[0]._history, "_state", (1, ()))
        return public

    monkeypatch.setattr(app, "_public_result_copy", bad_copy)
    with pytest.raises(Refused):
        _history(service, request, result.available_at)
    assert service._history._state is before
    assert service._history._pending is None


def test_coherent_in_place_source_mutation_during_semantics(authentic, monkeypatch):
    service = _service(authentic)
    item = authentic[1]
    request = _request(item)
    original = domain.interpret_governed_daily_technical_snapshot
    old_close = item.snapshot.latest_close
    old_snapshot_fingerprint = item.snapshot.fingerprint
    old_envelope_fingerprint = item.fingerprint

    def changed(**kwargs):
        result = original(**kwargs)
        object.__setattr__(item.snapshot, "latest_close", old_close + 1.0)
        object.__setattr__(
            item.snapshot,
            "fingerprint",
            canonical_fingerprint(item.snapshot._fingerprint_payload()),
        )
        _refingerprint(item)
        item.to_dict()
        return result

    monkeypatch.setattr(domain, "interpret_governed_daily_technical_snapshot", changed)
    try:
        _refuse(service, request)
    finally:
        object.__setattr__(item.snapshot, "latest_close", old_close)
        object.__setattr__(item.snapshot, "fingerprint", old_snapshot_fingerprint)
        object.__setattr__(item, "fingerprint", old_envelope_fingerprint)


@pytest.fixture(scope="module")
def complete_authentic():
    with pytest.MonkeyPatch.context() as monkeypatch:
        return _complete_authentic(monkeypatch)


def _complete_authentic(monkeypatch):
    from datetime import date

    import test_polygon_completed_daily_production_admission_validity as setup
    from test_polygon_completed_daily_production_bridge import (
        _request as bridge_request,
    )
    from test_polygon_completed_daily_production_qualification import _ready
    from test_polygon_completed_daily_production_validation import _construction, _row

    latest = date(2026, 8, 28)
    labels = tuple(latest - timedelta(days=i) for i in reversed(range(250)))
    monkeypatch.setattr(
        setup,
        "_construction",
        lambda: _construction(
            tuple(_row(label) for label in labels),
            requested_from=labels[0],
            requested_to=labels[-1],
        ),
    )
    qualification, intent = _ready()
    qualified = qualification.qualify(intent)
    instant = qualified.available_at + timedelta(days=1)
    bridge = b.PolygonCompletedDailyProductionBridgeApplicationService(
        qualification, execution_clock=lambda: instant
    )
    bridge.bridge(bridge_request(qualified))
    source = technical_service((bridge, bridge._history._state[1][0]), lambda: instant)
    source.execute(technical_request(bridge._history._state[1][0]))
    return source, source._history._state[1][0]


def test_complete_comparison_operand_isolation(complete_authentic):
    source, technical = complete_authentic
    instant = technical.available_at
    service = Service(source, execution_clock=lambda: instant)
    request = _request(technical)
    returned = service.execute(request)
    retained = app._reconstruct_result(service._history._state[1][0])
    expected = retained.to_dict()
    assert len(returned.interpretation.comparison_evidence) == 18
    assert not app._graph_ids(returned) & app._graph_ids(retained)
    comparison = returned.interpretation.comparison_evidence[0]
    object.__setattr__(comparison.left_operand, "value", 999.0)
    object.__setattr__(comparison, "satisfied", True)
    object.__setattr__(
        returned.interpretation,
        "fingerprint",
        canonical_fingerprint(returned.interpretation._fingerprint_payload()),
    )
    _refingerprint(returned)
    returned.to_dict()
    projection = retained.to_dict()
    projection["interpretation"]["comparison_evidence"][0]["left_operand"]["value"] = -1
    assert retained.to_dict() == expected
    read = _history(service, request, instant)[0]
    assert read.to_dict() == expected
    assert not app._graph_ids(read) & app._graph_ids(retained)


@pytest.mark.parametrize("operation", ["execute", "read"])
def test_final_provenance_seam_cannot_rewrite_public_copy(
    authentic, monkeypatch, operation
):
    service = _service(authentic)
    request = _request(authentic[1])
    result = service.execute(request) if operation == "read" else None
    copied = []
    original_copy = app._public_result_copy
    original_resolve = authentic[0]._resolve

    def copy(item):
        public = original_copy(item)
        copied.append(public)
        return public

    def resolve(reference, started):
        source = original_resolve(reference, started)
        if copied:
            object.__setattr__(copied[0], "execution_id", app._PREFIX + ":" + "0" * 32)
            _refingerprint(copied[0])
        return source

    monkeypatch.setattr(app, "_public_result_copy", copy)
    monkeypatch.setattr(authentic[0], "_resolve", resolve)
    if operation == "execute":
        _refuse(service, request, R.PUBLICATION_FAILED)
    else:
        with pytest.raises(Refused) as caught:
            _history(service, request, result.available_at)
        assert caught.value.reason is R.PUBLICATION_FAILED


def test_coherent_in_place_retained_content_rewrite_refused(authentic):
    service = _service(authentic)
    request = _request(authentic[1])
    result = service.execute(request)
    retained = app._reconstruct_result(service._history._state[1][0])
    object.__setattr__(
        retained,
        "interpretation",
        replace(
            retained.interpretation,
            source_governed_dataset_fingerprint="sha256:" + "0" * 64,
        ),
    )
    _refingerprint(retained)
    retained.to_dict()
    service._history._state = (2, (app._encode_result(retained),))
    _refuse(service, request, R.HISTORY_INVALID)
    with pytest.raises(Refused):
        _history(service, request, result.available_at)


def test_private_projection_copy_precedes_final_authentication(authentic, monkeypatch):
    service = _service(authentic)
    request = _request(authentic[1])
    armed = []
    copied = []
    original_check = app._check_copy
    original_copy = app.deepcopy

    def check(public, retained, expected):
        original_check(public, retained, expected)
        armed.append(True)

    def copy(value):
        if armed and not copied and type(value) is dict:
            copied.append(True)
            monkeypatch.setattr(authentic[0]._history, "_state", (1, ()))
        return original_copy(value)

    monkeypatch.setattr(app, "_check_copy", check)
    monkeypatch.setattr(app, "deepcopy", copy)
    _refuse(service, request, R.PUBLICATION_FAILED)
    assert copied == [True]


@pytest.mark.parametrize("mutation", SEMANTIC_MUTATIONS)
def test_domain_return_requires_independent_semantic_correspondence(
    complete_authentic, monkeypatch, mutation
):
    service = _service(complete_authentic)
    request = _request(complete_authentic[1])
    original = domain.interpret_governed_daily_technical_snapshot
    calls = []

    def wrong(**kwargs):
        calls.append(kwargs)
        authentic = original(**kwargs)
        altered = coherently_wrong_semantics(authentic, mutation)
        assert (
            altered.source_technical_occurrence == authentic.source_technical_occurrence
        )
        assert (
            altered.source_technical_analysis_snapshot_fingerprint
            == authentic.source_technical_analysis_snapshot_fingerprint
        )
        return altered

    monkeypatch.setattr(domain, "interpret_governed_daily_technical_snapshot", wrong)
    _refuse(service, request, R.SEMANTIC_FAILED)
    assert len(calls) == 1


def test_domain_verification_seams_preserve_single_execution(authentic, monkeypatch):
    service = _service(authentic)
    request = _request(authentic[1])
    execute = domain.interpret_governed_daily_technical_snapshot
    validate = domain.validate_governed_daily_technical_interpretation
    executions, verifications = [], []

    def observed_execution(**kwargs):
        executions.append(kwargs)
        return execute(**kwargs)

    def observed_verification(**kwargs):
        assert kwargs["snapshot"] is authentic[1].snapshot
        verifications.append(kwargs)
        return validate(**kwargs)

    monkeypatch.setattr(
        domain, "interpret_governed_daily_technical_snapshot", observed_execution
    )
    monkeypatch.setattr(
        domain,
        "validate_governed_daily_technical_interpretation",
        observed_verification,
    )
    result = service.execute(request)
    assert len(executions) == 1
    assert len(verifications) == 2
    assert (
        verifications[0]["content"]
        == verifications[1]["content"]
        == result.interpretation
    )
    assert _history(service, request, result.available_at) == (result,)
    assert len(executions) == 1
    assert len(verifications) == 4


@pytest.mark.parametrize("phase", ["immediate", "publication", "history"])
def test_validator_failure_is_closed(authentic, monkeypatch, phase):
    service = _service(authentic)
    request = _request(authentic[1])
    result = service.execute(request) if phase == "history" else None
    original = domain.validate_governed_daily_technical_interpretation
    calls = []

    def failed(**kwargs):
        calls.append(1)
        if len(calls) == (2 if phase == "publication" else 1):
            raise ValueError("domain semantic verification failed")
        return original(**kwargs)

    monkeypatch.setattr(
        domain, "validate_governed_daily_technical_interpretation", failed
    )
    if phase == "history":
        with pytest.raises(Refused) as caught:
            _history(service, request, result.available_at)
        assert caught.value.reason is R.HISTORY_INVALID
        assert service._history._state[0] == 2
    else:
        _refuse(
            service,
            request,
            R.SEMANTIC_FAILED if phase == "immediate" else R.PUBLICATION_FAILED,
        )
    assert service._history._pending is None


@pytest.mark.parametrize("phase", ["publication", "history"])
def test_provenance_reauthenticated_after_domain_verification(
    authentic, monkeypatch, phase
):
    service = _service(authentic)
    request = _request(authentic[1])
    result = service.execute(request) if phase == "history" else None
    original = domain.validate_governed_daily_technical_interpretation
    calls = []

    def changed(**kwargs):
        original(**kwargs)
        calls.append(1)
        if len(calls) == (2 if phase == "publication" else 1):
            monkeypatch.setattr(
                authentic[0]._bridge_service._history, "_state", (1, ())
            )

    monkeypatch.setattr(
        domain, "validate_governed_daily_technical_interpretation", changed
    )
    if phase == "publication":
        _refuse(service, request, R.PUBLICATION_FAILED)
    else:
        with pytest.raises(Refused) as caught:
            _history(service, request, result.available_at)
        assert caught.value.reason is R.HISTORY_INVALID
