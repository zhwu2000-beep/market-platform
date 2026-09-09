from __future__ import annotations

import inspect
import tomllib
from copy import deepcopy
from dataclasses import FrozenInstanceError, fields, replace
from datetime import date, timedelta
from pathlib import Path

import pytest
from test_polygon_completed_daily_production_bridge import _request as bridge_request
from test_polygon_completed_daily_production_qualification import _ready
from test_polygon_completed_daily_production_validation import _Clock

import market_platform.evidence as evidence
from market_platform._fingerprint import canonical_fingerprint
from market_platform.application import polygon_completed_daily_production_bridge as b
from market_platform.application import (
    polygon_completed_daily_production_technical as t,
)
from market_platform.research import technical_analysis as technical

R = t.PolygonCompletedDailyTechnicalRefusalReason


@pytest.fixture(scope="module")
def authentic():
    source, request = _ready()
    qualified = source.qualify(request)
    instant = qualified.available_at + timedelta(days=2)
    service = b.PolygonCompletedDailyProductionBridgeApplicationService(
        source, execution_clock=lambda: instant
    )
    service.bridge(bridge_request(qualified))
    return service, service._history._state[1][0]


def _request(bridge):
    return t.PolygonCompletedDailyTechnicalRequest(
        bridge.qualification.construction_result.artifact.reference(),
        bridge.history_namespace_id,
        bridge.history_sequence,
        bridge.execution_id,
        bridge.fingerprint,
    )


def _service(authentic, clock=None):
    source, bridge = authentic
    start = bridge.available_at + timedelta(days=1)
    return t.PolygonCompletedDailyProductionTechnicalApplicationService(
        source,
        execution_clock=clock
        or _Clock(start, start + timedelta(seconds=1), start + timedelta(seconds=2)),
    )


def _refuse(service, request, reason=None):
    with pytest.raises(t.PolygonCompletedDailyTechnicalRefused) as caught:
        service.execute(request)
    if reason is not None:
        assert caught.value.reason is reason
    assert service._history._state == (1, ())
    assert service._history._pending is None
    return caught.value


def _forbidden(*args, **kwargs):
    raise AssertionError("out-of-scope execution")


def test_authentic_execution_exact_handoff_and_envelope(authentic, monkeypatch):
    service = _service(authentic)
    bridge = authentic[1]
    original = technical.analyze_daily_technical_snapshot
    calls = []
    before = bridge.to_dict()
    rows = tuple(bridge.completed_prices.iter_rows())

    def analyze(*, completed_prices, profile):
        assert completed_prices is bridge.completed_prices
        assert tuple(completed_prices.iter_rows()) == rows
        assert profile.to_dict() == t._fixed_profile().to_dict()
        calls.append(completed_prices)
        return original(completed_prices=completed_prices, profile=profile)

    monkeypatch.setattr(technical, "analyze_daily_technical_snapshot", analyze)
    result = service.execute(_request(bridge))
    assert calls == [bridge.completed_prices]
    assert bridge.to_dict() == before
    assert result.snapshot.evidence == bridge.completed_prices.evidence
    assert result.snapshot.profile.fingerprint == t._ANALYSIS_FINGERPRINT
    assert result.analysis_as_of == bridge.qualification.analysis_as_of
    assert result.source.bridge_reference == _request(bridge)
    assert result.source.construction_execution_id == (
        bridge.qualification.construction_result.receipt.execution_id
    )
    assert result.source.qualification_execution_id == bridge.qualification.execution_id
    assert result.source.dataset_fingerprint == bridge.dataset_fingerprint
    assert result.source.no_drop_proof_fingerprint == bridge.no_drop_proof_fingerprint
    assert result.source.row_date_fingerprint == bridge.target_row_date_fingerprint
    assert result.source.dataset_fingerprint != (
        result.snapshot.evidence.dataset_content_fingerprint
    )
    assert result.source.bridge_available_at == bridge.available_at
    assert result.source.qualification_knowledge_as_of < bridge.available_at
    assert (
        bridge.available_at
        < result.execution_started_at
        < result.execution_completed_at
        < result.available_at
    )
    payload = result.to_dict()
    assert payload["operation"] == (
        "production.polygon_completed_daily.daily_technical.application"
    )
    assert payload["operation_version"] == "1.0.0"
    assert payload["analyzer"] == (
        "market_platform.research.technical_analysis.analyze_daily_technical_snapshot"
    )
    assert payload["transformation"]["fingerprint"] == t._TRANSFORMATION_FINGERPRINT
    assert result.fingerprint == canonical_fingerprint(result._payload())
    assert result.snapshot.fingerprint != result.fingerprint
    assert result.snapshot.quality is technical.TechnicalAnalysisQuality.DEGRADED
    assert not any(
        hasattr(result, name)
        for name in (
            "bridge",
            "completed_prices",
            "research",
            "integrity",
            "interpretation",
            "assessment",
            "strategy",
            "trading_signal",
            "order_intent",
            "is_consumable",
        )
    )


@pytest.mark.parametrize("kind", ["bridge", "lookalike", "prices", "snapshot", "hash"])
def test_no_bearer_inputs(authentic, kind):
    bridge = authentic[1]
    inputs = {
        "bridge": bridge,
        "lookalike": deepcopy(bridge),
        "prices": bridge.completed_prices,
        "snapshot": technical.analyze_daily_technical_snapshot(
            completed_prices=bridge.completed_prices, profile=t._fixed_profile()
        ),
        "hash": bridge.fingerprint,
    }
    service = _service(authentic)
    with pytest.raises(TypeError):
        service.execute(inputs[kind])
    assert service._history._state == (1, ())


@pytest.mark.parametrize(
    "field,value",
    [
        ("bridge_execution_id", "polygon_completed_daily_bridge:" + "0" * 32),
        ("bridge_fingerprint", "sha256:" + "0" * 64),
        (
            "bridge_history_namespace_id",
            "polygon_completed_daily_bridge_history:" + "0" * 32,
        ),
        ("bridge_history_sequence", 2),
    ],
)
def test_wrong_exact_bridge_reference(authentic, monkeypatch, field, value):
    monkeypatch.setattr(technical, "analyze_daily_technical_snapshot", _forbidden)
    request = replace(_request(authentic[1]), **{field: value})
    _refuse(_service(authentic), request, R.BRIDGE_UNAVAILABLE)


def test_wrong_artifact_lineage(authentic, monkeypatch):
    monkeypatch.setattr(technical, "analyze_daily_technical_snapshot", _forbidden)
    request = _request(authentic[1])
    artifact = replace(
        request.artifact_reference, artifact_fingerprint="sha256:" + "0" * 64
    )
    _refuse(
        _service(authentic),
        replace(request, artifact_reference=artifact),
        R.BRIDGE_UNAVAILABLE,
    )


@pytest.mark.parametrize(
    "kind",
    [
        "missing",
        "sequence",
        "duplicate",
        "namespace",
        "fingerprint",
        "rows",
        "qualification",
        "construction",
        "coherent_clone",
    ],
)
def test_corrupt_upstream_history_refuses_before_analyzer(authentic, monkeypatch, kind):
    source, bridge = authentic
    request = _request(bridge)
    monkeypatch.setattr(technical, "analyze_daily_technical_snapshot", _forbidden)
    if kind == "missing":
        monkeypatch.setattr(source._history, "_state", (2, ()))
    elif kind == "sequence":
        monkeypatch.setattr(source._history, "_state", (4, (bridge,)))
    elif kind == "duplicate":
        monkeypatch.setattr(source._history, "_state", (3, (bridge, bridge)))
    elif kind == "namespace":
        monkeypatch.setattr(source._history, "_namespace_id", "wrong")
    elif kind in ("fingerprint", "rows"):
        bad = deepcopy(bridge)
        if kind == "fingerprint":
            object.__setattr__(bad, "fingerprint", "sha256:" + "0" * 64)
        else:
            bad.completed_prices._prices._frame.loc[0, "volume"] = 999
        monkeypatch.setattr(source._history, "_state", (2, (bad,)))
    elif kind == "qualification":
        monkeypatch.setattr(source._qualification_service._history, "_state", (1, ()))
    elif kind == "coherent_clone":
        monkeypatch.setattr(source._history, "_state", (2, (deepcopy(bridge),)))
    else:
        admission = source._qualification_service._validity_service._admission_service
        construction = admission._construction_service
        monkeypatch.setattr(construction._history, "_state", (1, ()))
    _refuse(_service(authentic), request, R.HISTORY_INVALID)


def test_bridge_unavailable_at_start(authentic, monkeypatch):
    monkeypatch.setattr(technical, "analyze_daily_technical_snapshot", _forbidden)
    service = _service(
        authentic, lambda: authentic[1].available_at - timedelta(microseconds=1)
    )
    _refuse(service, _request(authentic[1]), R.BRIDGE_UNAVAILABLE)


def test_closed_input_and_execution_surfaces(authentic):
    assert [f.name for f in fields(t.PolygonCompletedDailyTechnicalRequest)] == [
        "artifact_reference",
        "bridge_history_namespace_id",
        "bridge_history_sequence",
        "bridge_execution_id",
        "bridge_fingerprint",
    ]
    service = _service(authentic)
    for keyword in ("analyzer", "profile", "snapshot", "completed_prices", "history"):
        with pytest.raises(TypeError):
            t.PolygonCompletedDailyProductionTechnicalApplicationService(
                authentic[0], **{keyword: object()}
            )
        with pytest.raises(TypeError):
            service.execute(_request(authentic[1]), **{keyword: object()})
    with pytest.raises(TypeError):
        t.PolygonCompletedDailyTechnicalResult()
    with pytest.raises(TypeError):
        t.PolygonCompletedDailyProductionTechnicalApplicationService(object())
    assert {
        name
        for name, member in inspect.getmembers(type(service), callable)
        if not name.startswith("_")
    } == {"execute", "get_result_history_as_of"}


@pytest.mark.parametrize(
    "field,value",
    [
        ("profile_id", "alternate"),
        ("profile_version", "2.0.0"),
        ("fingerprint", "sha256:" + "0" * 64),
    ],
)
def test_wrong_fixed_profile_refuses_before_analysis(
    authentic, monkeypatch, field, value
):
    bad = technical.construct_daily_technical_analysis_profile()
    object.__setattr__(bad, field, value)
    monkeypatch.setattr(
        technical, "construct_daily_technical_analysis_profile", lambda: bad
    )
    monkeypatch.setattr(technical, "analyze_daily_technical_snapshot", _forbidden)
    _refuse(_service(authentic), _request(authentic[1]), R.PROFILE_MISMATCH)


def _refingerprint_snapshot(snapshot):
    object.__setattr__(
        snapshot, "fingerprint", canonical_fingerprint(snapshot._fingerprint_payload())
    )


@pytest.mark.parametrize(
    "field",
    [
        "analysis_as_of",
        "provider",
        "instrument",
        "bar_count",
        "dataset_content_fingerprint",
        "fingerprint",
        "profile",
        "indicator",
        "evidence",
        "type",
    ],
)
def test_snapshot_correspondence_failures_publish_nothing(
    authentic, monkeypatch, field
):
    original = technical.analyze_daily_technical_snapshot

    def changed(**kwargs):
        result = original(**kwargs)
        item = result.evidence
        if field == "type":
            return object()
        if field == "profile":
            object.__setattr__(result.profile, "profile_version", "2.0.0")
        elif field == "fingerprint":
            object.__setattr__(result, "fingerprint", "sha256:" + "0" * 64)
        elif field == "indicator":
            object.__setattr__(result, "current_drawdown", 0.5)
            _refingerprint_snapshot(result)
        else:
            if field == "evidence":
                from test_daily_technical_analysis import snapshot

                object.__setattr__(result, "evidence", snapshot(1).evidence)
            elif field == "analysis_as_of":
                object.__setattr__(
                    item, field, item.analysis_as_of + timedelta(seconds=1)
                )
            elif field == "provider":
                object.__setattr__(item, field, "rewritten")
            elif field == "instrument":
                object.__setattr__(
                    item, field, replace(item.instrument, symbol="OTHER")
                )
            elif field == "bar_count":
                object.__setattr__(item, field, item.bar_count + 1)
            else:
                object.__setattr__(item, field, "sha256:" + "0" * 64)
            object.__setattr__(
                item, "fingerprint", canonical_fingerprint(item._fingerprint_payload())
            )
            _refingerprint_snapshot(result)
        return result

    monkeypatch.setattr(technical, "analyze_daily_technical_snapshot", changed)
    _refuse(_service(authentic), _request(authentic[1]), R.CORRESPONDENCE_FAILED)


def test_all_forbidden_paths_remain_unused(authentic, monkeypatch):
    from market_platform.application.daily_technical_strategy_service import (
        DailyTechnicalStrategyApplicationService,
    )
    from market_platform.data.providers.polygon import PolygonProvider
    from market_platform.research import (
        daily_analysis,
        daily_evidence,
        daily_instrument_integrity,
        daily_technical_assessment,
        daily_technical_interpretation,
        daily_technical_strategy,
    )

    source, bridge = authentic
    qualification = source._qualification_service
    admission = qualification._validity_service._admission_service
    for owner, names in (
        (daily_analysis.DailyTechnicalResearchWorkflow, ("run",)),
        (
            daily_instrument_integrity.IntegrityCheckedDailyTechnicalResearchWorkflow,
            ("run",),
        ),
        (
            daily_analysis,
            ("_acquire_polygon_daily_prices", "prepare_completed_daily_price_series"),
        ),
        (
            daily_instrument_integrity,
            (
                "_acquire_polygon_daily_prices",
                "_prepare",
                "_preflight_daily_instrument_resolution",
            ),
        ),
        (daily_evidence, ("prepare_completed_daily_price_series",)),
        (b, ("_convert_material", "_prepare", "prepare_completed_daily_price_series")),
        (type(source), ("bridge",)),
        (PolygonProvider, ("get_daily_prices", "get_completed_daily_acquisition")),
        (type(qualification), ("qualify",)),
        (b.q, ("_qualify_material",)),
        (b.q.evaluation, ("evaluate_evidence_admission_as_of",)),
        (type(admission), ("issue_admission",)),
        (type(qualification._validity_service), ("issue_initial_active",)),
        (type(admission._validation_service), ("execute_profile",)),
        (type(admission._freshness_service), ("execute_task", "execute_admission")),
        (DailyTechnicalStrategyApplicationService, ("execute",)),
        (daily_technical_interpretation, ("interpret_daily_technical_research",)),
        (daily_technical_assessment, ("assess_daily_technical_interpretation",)),
        (daily_technical_strategy, ("derive_daily_technical_strategy",)),
        (daily_analysis.DailyTechnicalResearchResult, ("_create",)),
        (
            daily_instrument_integrity.IntegrityCheckedDailyTechnicalResearchResult,
            ("_create",),
        ),
    ):
        for name in names:
            monkeypatch.setattr(owner, name, _forbidden)
    result = _service(authentic).execute(_request(bridge))
    assert result.snapshot.evidence == bridge.completed_prices.evidence


def test_replay_determinism_occurrences_and_visibility(authentic):
    bridge = authentic[1]
    start = bridge.available_at
    service = _service(
        authentic, _Clock(*(start + timedelta(seconds=i) for i in range(6)))
    )
    request = _request(bridge)
    first = service.execute(request)
    second = service.execute(request)
    assert first.snapshot == second.snapshot
    assert first.snapshot.fingerprint == second.snapshot.fingerprint
    assert first.execution_id != second.execution_id
    assert first.fingerprint != second.fingerprint
    assert (first.history_sequence, second.history_sequence) == (1, 2)
    assert first.execution_started_at != second.execution_started_at
    assert (
        first.analysis_as_of
        == second.analysis_as_of
        == bridge.qualification.analysis_as_of
    )
    assert first.analysis_as_of < first.available_at
    for cutoff, expected in (
        (bridge.qualification.knowledge_as_of, ()),
        (bridge.available_at, ()),
        (first.available_at - timedelta(microseconds=1), ()),
        (first.available_at, (first,)),
        (second.available_at, (first, second)),
    ):
        assert (
            service.get_result_history_as_of(
                request.artifact_reference, knowledge_as_of=cutoff
            )
            == expected
        )


@pytest.mark.parametrize("phase", ["completion", "publication", "prior_publication"])
def test_backward_clock_refuses(authentic, phase):
    bridge = authentic[1]
    start = bridge.available_at + timedelta(days=2)
    values = (
        (start, start - timedelta(seconds=1))
        if phase == "completion"
        else (start, start, start - timedelta(seconds=1))
    )
    service = _service(authentic, _Clock(*values))
    if phase == "prior_publication":
        service = _service(authentic, lambda: start + timedelta(days=1))
        first = service.execute(_request(bridge))
        service._clock = lambda: start
        with pytest.raises(t.PolygonCompletedDailyTechnicalRefused) as caught:
            service.execute(_request(bridge))
        assert caught.value.reason is R.TEMPORAL_FAILURE
        assert service._history._state == (2, (first,))
    else:
        _refuse(service, _request(bridge), R.TEMPORAL_FAILURE)


@pytest.mark.parametrize("phase", ["analysis", "arithmetic", "stage", "public_copy"])
def test_fallible_work_never_publishes(authentic, monkeypatch, phase):
    service = _service(authentic)

    def fail(*args, **kwargs):
        if phase == "arithmetic":
            raise OverflowError("derived arithmetic overflow")
        raise RuntimeError("failure before publication")

    if phase in ("analysis", "arithmetic"):
        monkeypatch.setattr(technical, "analyze_daily_technical_snapshot", fail)
        reason = R.ANALYSIS_FAILED
    elif phase == "stage":
        monkeypatch.setattr(service._history, "_stage_publication", fail)
        reason = R.PUBLICATION_FAILED
    else:
        monkeypatch.setattr(t, "_public_result_copy", fail)
        reason = R.PUBLICATION_FAILED
    _refuse(service, _request(authentic[1]), reason)


def test_final_availability_lock_held_and_staging_hidden(authentic):
    bridge = authentic[1]
    start = bridge.available_at + timedelta(days=1)
    ticks = []

    def clock():
        index = len(ticks)
        ticks.append(index)
        if index == 2:
            assert service._history._lock.locked()
            assert authentic[0]._history._lock.locked()
            assert service._history._state == (1, ())
            assert service._history._pending is not None
        return start + timedelta(seconds=index)

    service = _service(authentic, clock)
    result = service.execute(_request(bridge))
    assert ticks == [0, 1, 2]
    assert result.available_at == start + timedelta(seconds=2)
    assert service._history._pending is None


def test_public_graphs_never_alias_trusted_history(authentic):
    service = _service(authentic)
    request = _request(authentic[1])
    returned = service.execute(request)
    retained = service._history._state[1][0]
    one = service.get_result_history_as_of(
        request.artifact_reference, knowledge_as_of=returned.available_at
    )[0]
    two = service.get_result_history_as_of(
        request.artifact_reference, knowledge_as_of=returned.available_at
    )[0]
    copies = (returned, retained, one, two)
    for path in (
        lambda x: x,
        lambda x: x.snapshot,
        lambda x: x.snapshot.evidence,
        lambda x: x.snapshot.evidence.instrument,
        lambda x: x.source,
        lambda x: x.source.bridge_reference.artifact_reference,
    ):
        assert len({id(path(x)) for x in copies}) == 4
    expected = retained.to_dict()
    with pytest.raises(FrozenInstanceError):
        returned.snapshot.latest_close = 0.0
    object.__setattr__(returned.snapshot.evidence, "provider", "rewritten")
    object.__setattr__(one.snapshot.profile, "profile_version", "other")
    object.__setattr__(one.source.evidence.instrument, "symbol", "OTHER")
    projection = two.to_dict()
    projection["snapshot"]["warnings"].append("invented")
    assert retained.to_dict() == two.to_dict() == expected
    assert (
        service.get_result_history_as_of(
            request.artifact_reference, knowledge_as_of=two.available_at
        )[0].to_dict()
        == expected
    )


@pytest.mark.parametrize("count", [1, 2, 250])
def test_authentic_one_bar_sparse_and_complete_history(monkeypatch, count):
    import test_polygon_completed_daily_production_admission_validity as setup
    from test_polygon_completed_daily_production_validation import _construction, _row

    latest = date(2026, 8, 28)
    labels = (
        (date(2026, 8, 20), latest)
        if count == 2
        else tuple(latest - timedelta(days=i) for i in reversed(range(count)))
    )
    monkeypatch.setattr(
        setup,
        "_construction",
        lambda: _construction(
            tuple(_row(label) for label in labels),
            requested_from=labels[0],
            requested_to=labels[-1],
        ),
    )
    source, request = _ready()
    qualified = source.qualify(request)
    instant = qualified.available_at + timedelta(days=2)
    bridge_service = b.PolygonCompletedDailyProductionBridgeApplicationService(
        source, execution_clock=lambda: instant
    )
    bridge_service.bridge(bridge_request(qualified))
    bridge = bridge_service._history._state[1][0]
    result = _service((bridge_service, bridge)).execute(_request(bridge))
    assert result.snapshot.evidence.bar_count == count
    assert result.snapshot.quality is (
        technical.TechnicalAnalysisQuality.COMPLETE
        if count == 250
        else technical.TechnicalAnalysisQuality.DEGRADED
    )
    assert len(result.snapshot.unavailable) == (0 if count == 250 else 10)
    assert tuple(row[1].date() for row in bridge.completed_prices.iter_rows()) == labels
    assert qualified.canonical_state.is_consumable is True


def test_real_derived_overflow_on_authentic_binary64_input(monkeypatch):
    import test_polygon_completed_daily_production_admission_validity as setup
    from test_polygon_completed_daily_production_validation import _construction, _row

    labels = tuple(date(2026, 8, 21) + timedelta(days=i) for i in range(8))
    monkeypatch.setattr(
        setup,
        "_construction",
        lambda: _construction(
            tuple(
                _row(
                    label, open_value="1e308", high="1e308", low="1e308", close="1e308"
                )
                for label in labels
            ),
            requested_from=labels[0],
            requested_to=labels[-1],
        ),
    )
    source, request = _ready()
    qualified = source.qualify(request)
    bridge_service = b.PolygonCompletedDailyProductionBridgeApplicationService(
        source, execution_clock=lambda: qualified.available_at + timedelta(days=1)
    )
    bridge_service.bridge(bridge_request(qualified))
    bridge = bridge_service._history._state[1][0]
    before = bridge.to_dict()
    _refuse(_service((bridge_service, bridge)), _request(bridge), R.ANALYSIS_FAILED)
    assert bridge.to_dict() == before


@pytest.mark.parametrize(
    "field",
    [
        "dataset_fingerprint",
        "qualification_fingerprint",
        "snapshot",
        "execution_started_at",
        "execution_id",
        "history_sequence",
        "history_namespace_id",
    ],
)
def test_coherent_staging_rewrite_cannot_change_analysis(authentic, monkeypatch, field):
    service = _service(authentic)
    original = service._history._stage_publication

    def stage(result):
        original(result)
        if field == "snapshot":
            object.__setattr__(result.snapshot, "latest_close", 102.0)
            _refingerprint_snapshot(result.snapshot)
        elif field in ("dataset_fingerprint", "qualification_fingerprint"):
            object.__setattr__(result.source, field, "sha256:" + "0" * 64)
        else:
            value = {
                "execution_started_at": result.execution_started_at
                - timedelta(seconds=1),
                "execution_id": "polygon_completed_daily_technical:" + "0" * 32,
                "history_sequence": 7,
                "history_namespace_id": "polygon_completed_daily_technical_history:"
                + "0" * 32,
            }[field]
            object.__setattr__(result, field, value)
        object.__setattr__(
            result, "fingerprint", canonical_fingerprint(result._payload())
        )
        result.to_dict()

    monkeypatch.setattr(service._history, "_stage_publication", stage)
    _refuse(service, _request(authentic[1]), R.PUBLICATION_FAILED)


@pytest.mark.parametrize(
    "kind", ["missing", "fingerprint", "namespace", "sequence", "duplicate"]
)
def test_own_history_corruption_refuses(authentic, monkeypatch, kind):
    service = _service(authentic, lambda: authentic[1].available_at)
    request = _request(authentic[1])
    result = service.execute(request)
    if kind == "missing":
        state = (2, ())
    elif kind == "duplicate":
        state = (3, (result, result))
    else:
        field, value = {
            "fingerprint": ("fingerprint", "sha256:" + "0" * 64),
            "namespace": (
                "history_namespace_id",
                "polygon_completed_daily_technical_history:" + "0" * 32,
            ),
            "sequence": ("history_sequence", 2),
        }[kind]
        object.__setattr__(result, field, value)
        if kind != "fingerprint":
            object.__setattr__(
                result, "fingerprint", canonical_fingerprint(result._payload())
            )
        state = (2, (result,))
    monkeypatch.setattr(service._history, "_state", state)
    monkeypatch.setattr(technical, "analyze_daily_technical_snapshot", _forbidden)
    with pytest.raises(t.PolygonCompletedDailyTechnicalRefused) as caught:
        service.execute(request)
    assert caught.value.reason is R.HISTORY_INVALID
    assert service._history._state == state
    with pytest.raises(t.PolygonCompletedDailyTechnicalRefused):
        service.get_result_history_as_of(
            request.artifact_reference, knowledge_as_of=result.available_at
        )


def test_lost_upstream_history_cannot_back_result_claim(authentic, monkeypatch):
    service = _service(authentic)
    result = service.execute(_request(authentic[1]))
    monkeypatch.setattr(authentic[0]._history, "_state", (1, ()))
    with pytest.raises(t.PolygonCompletedDailyTechnicalRefused) as caught:
        service.get_result_history_as_of(
            result.source.bridge_reference.artifact_reference,
            knowledge_as_of=result.available_at,
        )
    assert caught.value.reason is R.HISTORY_INVALID


def test_execution_id_collision_cannot_publish(authentic, monkeypatch):
    from uuid import UUID

    service = _service(authentic, lambda: authentic[1].available_at)
    request = _request(authentic[1])
    first = service.execute(request)
    duplicate = UUID(hex=first.execution_id.split(":")[1])
    monkeypatch.setattr(t, "uuid4", lambda: duplicate)
    with pytest.raises(t.PolygonCompletedDailyTechnicalRefused) as caught:
        service.execute(request)
    assert caught.value.reason is R.PUBLICATION_FAILED
    assert service._history._state == (2, (first,))
    assert service._history._pending is None


@pytest.mark.parametrize("state", [(True, ()), (1, [])])
def test_noncanonical_history_shape_fails_before_analysis(
    authentic, monkeypatch, state
):
    service = _service(authentic)
    monkeypatch.setattr(service._history, "_state", state)
    monkeypatch.setattr(technical, "analyze_daily_technical_snapshot", _forbidden)
    with pytest.raises(t.PolygonCompletedDailyTechnicalRefused) as caught:
        service.execute(_request(authentic[1]))
    assert caught.value.reason is R.HISTORY_INVALID
    assert service._history._state == state


@pytest.mark.parametrize("mutation", ["subset", "reorder", "numeric"])
def test_analyzer_cannot_change_retained_representation(
    authentic, monkeypatch, mutation
):
    original = technical.analyze_daily_technical_snapshot
    bridge = authentic[1]

    def analyze(**kwargs):
        result = original(**kwargs)
        frame = bridge.completed_prices._prices.to_dataframe()
        if mutation == "subset":
            frame = frame.iloc[:1].copy()
        elif mutation == "reorder":
            frame = frame.iloc[::-1].reset_index(drop=True)
        else:
            frame.loc[0, "volume"] = 42.0
        monkeypatch.setattr(bridge.completed_prices._prices, "_frame", frame)
        return result

    monkeypatch.setattr(technical, "analyze_daily_technical_snapshot", analyze)
    _refuse(_service(authentic), _request(bridge), R.CORRESPONDENCE_FAILED)


@pytest.mark.parametrize(
    "field,value",
    [
        ("bridge_history_sequence", True),
        ("bridge_history_sequence", 0),
        ("bridge_execution_id", "wrong"),
        ("bridge_history_namespace_id", "wrong"),
        ("bridge_fingerprint", "wrong"),
    ],
)
def test_malformed_requests_rejected(authentic, field, value):
    with pytest.raises((TypeError, ValueError)):
        replace(_request(authentic[1]), **{field: value})


def test_stale_warning_is_descriptive_correspondence_not_authority():
    # Approved production freshness currently excludes >7-day inputs. Test the
    # unchanged snapshot boundary without inventing an authentic stale bridge.
    from test_daily_technical_analysis import snapshot

    stale = snapshot(250, lag_days=8)
    t._check_snapshot(stale, stale.evidence, t._fixed_profile())
    assert stale.warnings == (technical.TechnicalAnalysisWarning.STALE_EVIDENCE,)
    assert stale.quality is technical.TechnicalAnalysisQuality.COMPLETE
    source = inspect.getsource(t)
    assert ".warnings" not in source
    assert ".quality" not in source
    assert "STALE_EVIDENCE" not in source


def test_frozen_boundaries_and_no_downstream_output():
    from test_evidence_public_api import EXPECTED_PUBLIC_API

    assert tuple(evidence.__all__) == EXPECTED_PUBLIC_API
    assert len(evidence.__all__) == len(set(evidence.__all__)) == 69
    profile = b.q._approved_profile()
    assert profile.fingerprint == t._PROFILE_FINGERPRINT
    assert (
        profile.construction_authorization.fingerprint == t._AUTHORIZATION_FINGERPRINT
    )
    assert t._fixed_profile().fingerprint == t._ANALYSIS_FINGERPRINT
    assert profile.transformation.fingerprint == t._TRANSFORMATION_FINGERPRINT
    root = Path(__file__).resolve().parents[2]
    assert (
        tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
        == "0.1.0"
    )
    assert [item.name for item in fields(t.PolygonCompletedDailyTechnicalResult)] == [
        "source",
        "snapshot",
        "execution_id",
        "history_namespace_id",
        "history_sequence",
        "execution_started_at",
        "execution_completed_at",
        "available_at",
        "fingerprint",
    ]
