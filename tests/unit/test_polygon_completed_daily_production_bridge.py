from __future__ import annotations

import inspect
import math
import struct
from dataclasses import FrozenInstanceError, fields, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, localcontext

import pandas as pd
import pytest
from test_polygon_completed_daily_production_qualification import _ready
from test_polygon_completed_daily_production_validation import _Clock

import market_platform.evidence as evidence
from market_platform._fingerprint import canonical_fingerprint, canonical_float
from market_platform.application import polygon_completed_daily_production_bridge as b
from market_platform.application import (
    polygon_completed_daily_production_qualification as q,
)


@pytest.fixture(scope="module")
def authentic():
    service, request = _ready()
    return service, service.qualify(request)


def _request(qualified):
    return b.PolygonCompletedDailyBridgeRequest(
        qualified.construction_result.artifact.reference(),
        qualified.construction_result.receipt.execution_id,
        qualified.execution_id,
        qualified.fingerprint,
    )


def _service(authentic, clock=None):
    source, qualified = authentic
    instant = qualified.available_at + timedelta(days=2)
    return b.PolygonCompletedDailyProductionBridgeApplicationService(
        source, execution_clock=clock or (lambda: instant)
    )


def _refuse(service, request, reason=None):
    with pytest.raises(b.PolygonCompletedDailyBridgeRefused) as caught:
        service.bridge(request)
    if reason is not None:
        assert caught.value.reason is reason
    assert service._history._state == (1, ())
    assert service._history._pending is None
    return caught.value


def _clone(value, **changes):
    copied = object.__new__(type(value))
    for field in fields(value):
        object.__setattr__(copied, field.name, getattr(value, field.name))
    for name, item in changes.items():
        object.__setattr__(copied, name, item)
    return copied


def _changed_qualification(qualified, **changes):
    result = _clone(qualified, **changes)
    object.__setattr__(result, "fingerprint", canonical_fingerprint(result._payload()))
    return result


def test_authentic_bridge_envelope_and_replay(authentic):
    service = _service(authentic)
    qualified = authentic[1]
    result = service.bridge(_request(qualified))
    projection = result.to_dict()
    assert result.qualification is qualified
    assert result.source_row_count == result.target_row_count == 2
    assert result.target_row_date_fingerprint == qualified.original_row_date_fingerprint
    assert [
        row[1].date().isoformat() for row in result.completed_prices.iter_rows()
    ] == ["2026-08-27", "2026-08-28"]
    assert (
        result.execution_started_at > qualified.available_at > qualified.knowledge_as_of
    )
    assert (
        projection["qualification_knowledge_as_of"]
        == qualified.knowledge_as_of.isoformat()
    )
    assert projection["analysis_as_of"] == qualified.analysis_as_of.isoformat()
    assert projection["qualification_fingerprint"] == qualified.fingerprint
    assert (
        projection["construction_receipt"]
        == qualified.construction_result.receipt.to_dict()
    )
    assert projection["transformation"] == q._PROFILE.transformation.to_dict()
    for name in ("consumer", "use", "analysis_profile"):
        assert projection[name] == getattr(q._PROFILE, name).to_dict()
    assert (
        len(
            {
                projection["source_material_fingerprint"],
                projection["source_row_date_fingerprint"],
                result.dataset_fingerprint,
                result.no_drop_proof_fingerprint,
                result.fingerprint,
                projection["legacy_dataset_content_fingerprint"],
            }
        )
        == 6
    )
    with pytest.raises(FrozenInstanceError):
        result.available_at = qualified.knowledge_as_of
    with pytest.raises(TypeError):
        b.PolygonCompletedDailyBridgeResult()
    material = qualified.construction_result.material
    assert material.rows[0].open == "100"
    frame = result.completed_prices.to_dataframe()
    for name in b._FIELDS:
        assert str(frame[name].dtype) == "float64"
        assert type(frame[name].iloc[0]).__name__ == "float64"
    assert str(frame.timestamp.dtype) == "datetime64[ns, UTC]"


@pytest.mark.parametrize(
    "field",
    [
        "artifact_reference",
        "construction_execution_id",
        "qualification_execution_id",
        "qualification_fingerprint",
    ],
)
def test_wrong_exact_reference_refused(authentic, field):
    request = _request(authentic[1])
    value = getattr(request, field)
    if field == "artifact_reference":
        value = replace(value, artifact_id=value.artifact_id + ".wrong")
    elif field == "qualification_fingerprint":
        value = "sha256:" + "0" * 64
    else:
        value = value.split(":")[0] + ":" + "0" * 32
    _refuse(_service(authentic), replace(request, **{field: value}))


def test_no_bearer_qualification_or_import_authority(authentic):
    service = _service(authentic)
    for value in (authentic[1], _clone(authentic[1]), object(), {}):
        with pytest.raises(TypeError):
            service.bridge(value)
    with pytest.raises(TypeError):
        q.PolygonCompletedDailyQualifiedUse()
    assert {field.name for field in fields(b.PolygonCompletedDailyBridgeRequest)} == {
        "artifact_reference",
        "construction_execution_id",
        "qualification_execution_id",
        "qualification_fingerprint",
    }
    for owner in (service, service._history):
        assert not any(
            hasattr(owner, name)
            for name in ("append", "import_result", "mint", "register")
        )
    with pytest.raises(TypeError):
        b.PolygonCompletedDailyProductionBridgeApplicationService(object())


@pytest.mark.parametrize(
    "field,value",
    [
        ("all_row_mapping_covered", False),
        ("whole_material_completed", False),
        ("original_row_count", 1),
        ("original_ordered_dates", ("2026-08-28", "2026-08-27")),
        ("original_row_date_fingerprint", "sha256:" + "0" * 64),
        ("mapping_context_fingerprint", "sha256:" + "0" * 64),
    ],
)
def test_coherent_wrong_qualification_facts_refused(
    authentic, monkeypatch, field, value
):
    source, qualified = authentic
    changed = _changed_qualification(qualified, **{field: value})
    monkeypatch.setattr(source._history, "_state", (2, (changed,)))
    _refuse(_service(authentic), _request(changed))


@pytest.mark.parametrize(
    "field", ["consumer", "use", "analysis_profile", "transformation"]
)
def test_wrong_closed_profile_member_refused(authentic, monkeypatch, field):
    source, qualified = authentic
    member = getattr(qualified.production_profile, field)
    changed_member = replace(member, definition_version="9.0.0")
    profile = replace(qualified.production_profile, **{field: changed_member})
    changed = _changed_qualification(qualified, production_profile=profile)
    monkeypatch.setattr(source._history, "_state", (2, (changed,)))
    _refuse(_service(authentic), _request(changed))


def test_canonical_false_cannot_bridge(authentic, monkeypatch):
    source, qualified = authentic
    monkeypatch.setattr(
        type(qualified.canonical_state), "is_consumable", property(lambda _: False)
    )
    # The qualification payload has a constant requirement, not a bearer boolean.
    _refuse(_service(authentic), _request(qualified))


@pytest.mark.parametrize(
    "kind", ["pruned", "namespace", "fingerprint", "duplicate", "construction_pruned"]
)
def test_corrupt_or_incomplete_history_refused(authentic, monkeypatch, kind):
    source, qualified = authentic
    if kind == "pruned":
        monkeypatch.setattr(source._history, "_state", (2, ()))
    elif kind == "construction_pruned":
        store = (
            source._validity_service._admission_service._construction_service._history
        )
        monkeypatch.setattr(store, "_state", (store._state[0], ()))
    else:
        changed = _clone(qualified)
        if kind == "namespace":
            changed = _changed_qualification(qualified, history_namespace_id="wrong")
        elif kind == "fingerprint":
            object.__setattr__(changed, "fingerprint", "sha256:" + "0" * 64)
        monkeypatch.setattr(
            source._history,
            "_state",
            (3, (qualified, changed)) if kind == "duplicate" else (2, (changed,)),
        )
    _refuse(_service(authentic), _request(qualified))


@pytest.mark.parametrize("field", b._FIELDS)
def test_final_numeric_mutation_detected_against_original(
    authentic, monkeypatch, field
):
    original_prepare = b._prepare
    index = b._FIELDS.index(field)

    def mutate(qualified, expected):
        first = expected[0]
        values = list(first.values)
        values[index] += 0.125
        return original_prepare(
            qualified, (replace(first, values=tuple(values)), *expected[1:])
        )

    monkeypatch.setattr(b, "_prepare", mutate)
    _refuse(
        _service(authentic),
        _request(authentic[1]),
        b.PolygonCompletedDailyBridgeRefusalReason.CORRESPONDENCE_FAILED,
    )


@pytest.mark.parametrize(
    "kind",
    ["omission", "insertion", "date_shift", "filter", "collapse", "subject", "reorder"],
)
def test_final_row_mutations_publish_nothing(authentic, monkeypatch, kind):
    original_prepare = b._prepare

    def mutate(qualified, expected):
        if kind in ("omission", "collapse"):
            return original_prepare(qualified, expected[:1])
        if kind == "insertion":
            extra = replace(
                expected[0],
                session_date="2026-08-26",
                timestamp=datetime(2026, 8, 26, tzinfo=UTC),
            )
            return original_prepare(qualified, (extra, *expected))
        if kind == "date_shift":
            return original_prepare(
                qualified,
                (
                    replace(expected[0], timestamp=datetime(2026, 8, 26, tzinfo=UTC)),
                    expected[1],
                ),
            )
        if kind == "filter":
            local_date = qualified.analysis_as_of.astimezone(q._NY).date()
            return original_prepare(
                qualified,
                (
                    expected[0],
                    replace(
                        expected[1],
                        timestamp=datetime.combine(
                            local_date, datetime.min.time(), UTC
                        ),
                    ),
                ),
            )
        result = original_prepare(qualified, expected)
        if kind == "reorder":
            # Corrupt final storage, not factory input that the legacy path sorts.
            result._prices._frame = result._prices._frame.iloc[::-1].reset_index(
                drop=True
            )
        else:
            result._prices._frame["symbol"] = "MSFT"
        return result

    monkeypatch.setattr(b, "_prepare", mutate)
    _refuse(_service(authentic), _request(authentic[1]))


def test_final_public_row_reorder_detected(authentic, monkeypatch):
    original = b.CompletedDailyPriceSeries.iter_rows
    monkeypatch.setattr(
        b.CompletedDailyPriceSeries,
        "iter_rows",
        lambda self: iter(reversed(tuple(original(self)))),
    )
    _refuse(_service(authentic), _request(authentic[1]))


def test_source_to_intermediate_omission_cannot_move_proof_baseline(
    authentic, monkeypatch
):
    original = b._convert_material
    monkeypatch.setattr(b, "_convert_material", lambda material: original(material)[1:])
    _refuse(_service(authentic), _request(authentic[1]))


@pytest.mark.parametrize(
    "label", ["1677-09-22", "2262-04-11", "2026-03-08", "2026-11-01"]
)
def test_project_native_date_conversion(label):
    from test_daily_research_evidence import make_prices, prepare

    timestamp = b._session_timestamp(label)
    assert timestamp == datetime.fromisoformat(label).replace(tzinfo=UTC)
    result = prepare(make_prices([label]), timestamp + timedelta(days=1, hours=12))
    assert tuple(result.iter_rows())[0][1] == timestamp
    assert str(result.to_dataframe().timestamp.dtype) == "datetime64[ns, UTC]"


@pytest.mark.parametrize(
    "label",
    [
        "1677-09-21",
        "2262-04-12",
        "NaT",
        "2026-1-01",
        "2026-01-01T00:00:00",
        "2026-02-30",
    ],
)
def test_unsupported_dates_refused_without_coercion(label):
    with pytest.raises(ValueError):
        b._session_timestamp(label)


@pytest.mark.parametrize(
    "source,field",
    [
        ("100.125", "open"),
        ("0", "volume"),
        ("0.125", "volume"),
        (format(Decimal.from_float(float.fromhex("0x1.0p-1022")), "f"), "low"),
        (
            format(Decimal.from_float(float.fromhex("0x1.fffffffffffffp+1023")), "f"),
            "high",
        ),
    ],
)
def test_exact_deterministic_binary64_conversion(source, field):
    with localcontext() as context:
        context.prec = 2
        context.rounding = "ROUND_UP"
        first = b._convert_numeric(source, field)
    second = b._convert_numeric(source, field)
    assert (
        b._binary64(first)
        == b._binary64(second)
        == struct.pack(">d", float(Decimal(source))).hex()
    )
    assert math.isfinite(first)
    if source == "0":
        assert math.copysign(1, first) == 1


@pytest.mark.parametrize(
    "source",
    [
        "1" + "0" * 309,
        "0." + "0" * 400 + "1",
        format(Decimal.from_float(float.fromhex("0x0.0000000000001p-1022")), "f"),
        "NaN",
        "Infinity",
        "-Infinity",
        "1.00",
        "1e2",
    ],
)
def test_unsafe_binary64_refused_no_repair(source):
    with pytest.raises((ValueError, ArithmeticError)):
        b._convert_numeric(source, "volume")


@pytest.mark.parametrize("field", ["open", "high", "low", "close", "volume"])
@pytest.mark.parametrize(
    "source,endpoint_hex,below",
    [
        ("2.2250738585072013e-308", "0x1.0000000000000p-1022", True),
        ("1.7976931348623158e308", "0x1.fffffffffffffp+1023", False),
    ],
)
def test_exact_source_range_refuses_inward_rounding(field, source, endpoint_hex, below):
    with localcontext() as context:
        context.prec = 2
        context.rounding = "ROUND_UP"
        decimal = Decimal(source)
        endpoint = float.fromhex(endpoint_hex)
        exact_endpoint = Decimal.from_float(endpoint)
        assert decimal < exact_endpoint if below else decimal > exact_endpoint
        assert float(decimal) == endpoint
        assert math.isfinite(endpoint)
        assert 0 < (int(b._binary64(endpoint), 16) >> 52) & 0x7FF < 0x7FF
        canonical = b._canonical_numeric_text(decimal, field)
        assert len(canonical) <= 1024
        with pytest.raises(ValueError, match="exact source.*range"):
            b._convert_numeric(canonical, field)


@pytest.mark.parametrize("field", ["open", "high", "low", "close", "volume"])
@pytest.mark.parametrize(
    "source,endpoint_hex",
    [
        (None, "0x1.0000000000000p-1022"),
        (None, "0x1.fffffffffffffp+1023"),
        ("2.2250738585072014e-308", "0x1.0000000000000p-1022"),
        ("1.7976931348623157e308", "0x1.fffffffffffffp+1023"),
    ],
)
def test_exact_source_range_accepts_endpoints_and_inside(field, source, endpoint_hex):
    with localcontext() as context:
        context.prec = 2
        context.rounding = "ROUND_UP"
        minimum = Decimal.from_float(float.fromhex("0x1.0000000000000p-1022"))
        maximum = Decimal.from_float(float.fromhex("0x1.fffffffffffffp+1023"))
        endpoint = float.fromhex(endpoint_hex)
        decimal = Decimal.from_float(endpoint) if source is None else Decimal(source)
        assert minimum <= decimal <= maximum
        if source is not None:
            assert minimum < decimal < maximum
            assert decimal != Decimal.from_float(endpoint)
        canonical = b._canonical_numeric_text(decimal, field)
        converted = b._convert_numeric(canonical, field)
        assert b._binary64(converted) == b._binary64(endpoint)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_target_projection_refused(value):
    with pytest.raises(ValueError):
        b._binary64(value)


def test_zero_projection_matches_repository_identity():
    assert canonical_float(-0.0) == canonical_float(0.0)
    assert b._binary64(-0.0) == b._binary64(0.0) == "0000000000000000"
    assert b._binary64(1.0) == "3ff0000000000000"


@pytest.mark.parametrize(
    "mutation", ["number", "order", "timestamp", "version", "identity"]
)
def test_dataset_identity_binds_representation(authentic, monkeypatch, mutation):
    material = authentic[1].construction_result.material
    rows = [
        {
            "timestamp": "2026-08-27T00:00:00+00:00",
            "ohlcv_binary64": [b._binary64(100.0)] * 5,
        },
        {
            "timestamp": "2026-08-28T00:00:00+00:00",
            "ohlcv_binary64": [b._binary64(101.0)] * 5,
        },
    ]
    before = canonical_fingerprint(b._dataset_payload(material, rows))
    if mutation == "number":
        rows[0] = {**rows[0], "ohlcv_binary64": [b._binary64(100.00000000000001)] * 5}
    elif mutation == "order":
        rows.reverse()
    elif mutation == "timestamp":
        rows[0] = {**rows[0], "timestamp": "2026-08-26T00:00:00+00:00"}
    else:
        field = "definition_version" if mutation == "version" else "definition_id"
        monkeypatch.setattr(
            b, "_TRANSFORMATION", replace(b._TRANSFORMATION, **{field: "different"})
        )
    assert canonical_fingerprint(b._dataset_payload(material, rows)) != before


def test_repeated_occurrences_same_dataset_and_proof(authentic):
    service = _service(authentic)
    request = _request(authentic[1])
    first = service.bridge(request)
    second = service.bridge(request)
    assert first.dataset_fingerprint == second.dataset_fingerprint
    assert first.no_drop_proof_fingerprint == second.no_drop_proof_fingerprint
    assert first.fingerprint != second.fingerprint
    assert first.execution_id != second.execution_id
    assert (first.history_sequence, second.history_sequence) == (1, 2)
    assert (
        service.get_bridge_history_as_of(
            request.artifact_reference,
            knowledge_as_of=first.available_at - timedelta(microseconds=1),
        )
        == ()
    )
    history = service.get_bridge_history_as_of(
        request.artifact_reference, knowledge_as_of=second.available_at
    )
    assert tuple(item.to_dict() for item in history) == (
        first.to_dict(),
        second.to_dict(),
    )


@pytest.mark.parametrize("phase", ["conversion", "proof", "stage", "final"])
def test_failed_execution_has_no_publication(authentic, monkeypatch, phase):
    service = _service(authentic)

    def fail(*args, **kwargs):
        raise ValueError("injected failure")

    if phase == "conversion":
        monkeypatch.setattr(b, "_convert_numeric", fail)
    elif phase == "proof":
        monkeypatch.setattr(b, "_prove", fail)
    else:
        original = service._history._stage_publication

        def stage(result):
            original(result)
            assert service._history._state == (1, ())
            assert service._history._pending is result
            assert service._history._lock.locked()
            if phase == "stage":
                raise ValueError("stage failure")
            object.__setattr__(result, "dataset_fingerprint", "sha256:" + "0" * 64)

        monkeypatch.setattr(service._history, "_stage_publication", stage)
    _refuse(service, _request(authentic[1]))


@pytest.mark.parametrize("phase", ["start", "completion", "availability"])
def test_backward_clock_fails_closed(authentic, phase):
    qualified = authentic[1]
    instant = qualified.available_at + timedelta(seconds=10)
    ticks = [instant, instant, instant]
    if phase == "start":
        ticks[0] = qualified.available_at - timedelta(microseconds=1)
    else:
        ticks[1 if phase == "completion" else 2] -= timedelta(seconds=1)
    _refuse(_service(authentic, _Clock(*ticks)), _request(qualified))


def test_availability_sample_is_lock_held_and_staging_hidden(authentic):
    ticks = []
    qualified = authentic[1]

    def clock():
        ticks.append(len(ticks))
        if len(ticks) == 3:
            assert service._history._lock.locked()
            assert service._history._pending is not None
            assert service._history._state == (1, ())
        return qualified.available_at + timedelta(seconds=10 + len(ticks))

    service = _service(authentic, clock)
    result = service.bridge(_request(qualified))
    assert len(ticks) == 3
    assert (
        result.execution_started_at
        < result.execution_completed_at
        < result.available_at
    )
    assert service._history._pending is None


def test_no_governance_qualification_provider_or_analyzer_execution(
    authentic, monkeypatch
):
    source, qualified = authentic

    def forbidden(*args, **kwargs):
        raise AssertionError("out-of-scope execution")

    admission = source._validity_service._admission_service
    for owner, names in (
        (source, ("qualify",)),
        (q, ("_qualify_material",)),
        (q.evaluation, ("evaluate_evidence_admission_as_of",)),
        (admission, ("issue_admission",)),
        (source._validity_service, ("issue_initial_active",)),
        (admission._validation_service, ("execute_profile",)),
        (admission._freshness_service, ("execute_task", "execute_admission")),
    ):
        for name in names:
            monkeypatch.setattr(
                owner if inspect.ismodule(owner) else type(owner), name, forbidden
            )
    from market_platform.data.providers.polygon import PolygonProvider
    from market_platform.research import technical_analysis

    monkeypatch.setattr(PolygonProvider, "get_completed_daily_acquisition", forbidden)
    monkeypatch.setattr(
        technical_analysis, "analyze_daily_technical_snapshot", forbidden
    )
    result = _service(authentic).bridge(_request(qualified))
    assert not any(
        hasattr(result, name)
        for name in ("technical_snapshot", "is_consumable", "strategy")
    )
    assert len(evidence.__all__) == len(set(evidence.__all__)) == 69
    assert q._PROFILE.fingerprint == q._PROFILE_FINGERPRINT
    assert (
        q._PROFILE.construction_authorization.fingerprint
        == "sha256:e9d8057dde8e20c5fb297ea08be7bcc723131cea42fab0e8a528f5b40c343387"
    )
    assert (
        q._PROFILE.analysis_profile.get("profile_fingerprint")
        == q._ANALYSIS_FINGERPRINT
    )
    assert "analyze_daily_technical_snapshot" not in inspect.getsource(b)


@pytest.mark.parametrize(
    "labels", [(date(2026, 8, 28),), (date(2026, 8, 20), date(2026, 8, 28))]
)
def test_one_row_and_sparse_authentic_whole_material(monkeypatch, labels):
    import test_polygon_completed_daily_production_admission_validity as setup
    from test_polygon_completed_daily_production_validation import _construction, _row

    def construct():
        return _construction(
            tuple(_row(label, volume="0.125") for label in labels),
            requested_from=labels[0],
            requested_to=labels[-1],
        )

    monkeypatch.setattr(setup, "_construction", construct)
    source, request = _ready()
    qualified = source.qualify(request)
    result = _service((source, qualified)).bridge(_request(qualified))
    assert result.source_row_count == result.target_row_count == len(labels)
    assert tuple(row[1].date() for row in result.completed_prices.iter_rows()) == labels
    assert all(row[6] == 0.125 for row in result.completed_prices.iter_rows())


def _custom_authentic(monkeypatch, label, volume="0"):
    import test_polygon_completed_daily_production_admission_validity as setup
    from test_polygon_completed_daily_production_validation import (
        _construction,
        _mapping,
        _row,
    )

    def construct():
        return _construction(
            (_row(label, volume=volume),),
            requested_from=label,
            requested_to=label,
            mapping=_mapping(valid_from=datetime(1600, 1, 1, tzinfo=UTC)),
        )

    monkeypatch.setattr(setup, "_construction", construct)
    source, request = _ready()
    return source, source.qualify(request)


@pytest.mark.parametrize(
    "label,accepted",
    [
        ("1677-09-22", True),
        ("2262-04-11", True),
        ("1677-09-21", False),
        ("2262-04-12", False),
    ],
)
def test_authentic_bridge_approved_date_boundaries(monkeypatch, label, accepted):
    authentic = _custom_authentic(monkeypatch, date.fromisoformat(label))
    service = _service(authentic)
    if not accepted:
        _refuse(
            service,
            _request(authentic[1]),
            b.PolygonCompletedDailyBridgeRefusalReason.REPRESENTATION_UNSUPPORTED,
        )
    else:
        result = service.bridge(_request(authentic[1]))
        row = next(result.completed_prices.iter_rows())
        assert row[1] == b._session_timestamp(label)
        assert row[6] == 0.0 and math.copysign(1.0, row[6]) == 1.0
        assert result.source_row_count == result.target_row_count == 1


@pytest.mark.parametrize(
    "volume",
    [
        "1" + "0" * 309,
        "0." + "0" * 400 + "1",
        "2.2250738585072008E-308",
    ],
)
def test_authentic_qualified_but_unrepresentable_material_refuses(monkeypatch, volume):
    authentic = _custom_authentic(monkeypatch, date(2026, 8, 28), volume)
    assert authentic[1].canonical_state.is_consumable
    _refuse(
        _service(authentic),
        _request(authentic[1]),
        b.PolygonCompletedDailyBridgeRefusalReason.REPRESENTATION_UNSUPPORTED,
    )


@pytest.mark.parametrize(
    "volume", ["2.2250738585072013e-308", "1.7976931348623158e308"]
)
def test_authentic_exact_source_range_refusal_publishes_nothing(monkeypatch, volume):
    canonical = b._canonical_numeric_text(Decimal(volume), "volume")
    assert len(canonical) <= 1024
    authentic = _custom_authentic(monkeypatch, date(2026, 8, 28), canonical)
    qualified = authentic[1]
    assert qualified.construction_result.material.rows[0].volume == canonical
    assert qualified.canonical_state.is_consumable is True
    _refuse(
        _service(authentic),
        _request(qualified),
        b.PolygonCompletedDailyBridgeRefusalReason.REPRESENTATION_UNSUPPORTED,
    )


@pytest.mark.parametrize("field", ["volume", "timestamp"])
def test_final_negative_zero_or_nat_refuses(authentic, monkeypatch, field):
    original = b._prepare

    def mutate(qualified, expected):
        result = original(qualified, expected)
        result._prices._frame.loc[0, field] = -0.0 if field == "volume" else pd.NaT
        return result

    monkeypatch.setattr(b, "_prepare", mutate)
    _refuse(_service(authentic), _request(authentic[1]))


def test_staging_cannot_change_qualification_facts(authentic, monkeypatch):
    service = _service(authentic)
    original = service._history._stage_publication

    def stage(result):
        original(result)
        changed = _changed_qualification(
            result.qualification, all_row_mapping_covered=False
        )
        object.__setattr__(result, "qualification", changed)

    monkeypatch.setattr(service._history, "_stage_publication", stage)
    _refuse(service, _request(authentic[1]))


def test_corrupt_bridge_history_and_backward_prior_availability(authentic, monkeypatch):
    service = _service(authentic)
    request = _request(authentic[1])
    result = service.bridge(request)
    service._clock = lambda: result.available_at - timedelta(microseconds=1)
    with pytest.raises(b.PolygonCompletedDailyBridgeRefused):
        service.bridge(request)
    sequence, entries = service._history._state
    assert sequence == 2 and len(entries) == 1
    assert entries[0].to_dict() == result.to_dict()
    monkeypatch.setattr(service._history, "_state", (2, ()))
    with pytest.raises(ValueError, match="incomplete"):
        service.get_bridge_history_as_of(
            request.artifact_reference, knowledge_as_of=result.available_at
        )


def test_intermediate_reordering_cannot_be_silently_normalized(authentic, monkeypatch):
    original = b._convert_material
    monkeypatch.setattr(
        b, "_convert_material", lambda material: original(material)[::-1]
    )
    _refuse(_service(authentic), _request(authentic[1]))


def test_decimal_rounding_ties_to_even_and_no_tolerance():
    lower = 1.0
    upper = math.nextafter(lower, math.inf)
    with localcontext() as context:
        context.prec = 100
        midpoint = (Decimal.from_float(lower) + Decimal.from_float(upper)) / 2
    assert b._binary64(
        b._convert_numeric(format(midpoint, "f"), "open")
    ) == b._binary64(lower)
    assert b._binary64(lower) != b._binary64(upper)


@pytest.mark.parametrize("surface", ["bridge", "history"])
@pytest.mark.parametrize(
    "column,value",
    [
        ("open", 7.0),
        ("timestamp", pd.Timestamp("2026-08-26", tz=UTC)),
        ("symbol", "MSFT"),
        ("provider", "other"),
    ],
)
def test_public_mutation_cannot_change_authoritative_history(
    authentic, surface, column, value
):
    service = _service(authentic)
    request = _request(authentic[1])
    returned = service.bridge(request)
    state = service._history._state
    retained = state[1][0]
    before = retained.to_dict()
    frame = retained.completed_prices._prices._frame.copy(deep=True)
    if surface == "history":
        returned = service.get_bridge_history_as_of(
            request.artifact_reference, knowledge_as_of=retained.available_at
        )[0]
    assert returned is not retained
    assert returned.completed_prices is not retained.completed_prices
    assert returned.completed_prices._prices is not retained.completed_prices._prices
    assert returned.completed_prices._prices._frame is not (
        retained.completed_prices._prices._frame
    )
    assert returned.to_dict() == before

    returned.completed_prices._prices._frame.loc[0, column] = value

    assert service._history._state is state
    pd.testing.assert_frame_equal(retained.completed_prices._prices._frame, frame)
    assert retained.to_dict() == before
    service._history._validate()
    later = service.get_bridge_history_as_of(
        request.artifact_reference, knowledge_as_of=retained.available_at
    )[0]
    assert later.to_dict() == before
    pd.testing.assert_frame_equal(later.completed_prices.to_dataframe(), frame)


def test_defensive_history_copies_preserve_identity_and_do_not_alias(authentic):
    service = _service(authentic)
    request = _request(authentic[1])
    returned = service.bridge(request)
    retained = service._history._state[1][0]
    first = service.get_bridge_history_as_of(
        request.artifact_reference, knowledge_as_of=retained.available_at
    )[0]
    second = service.get_bridge_history_as_of(
        request.artifact_reference, knowledge_as_of=retained.available_at
    )[0]
    copies = (returned, first, second, retained)
    assert len({id(item) for item in copies}) == 4
    assert len({id(item.completed_prices) for item in copies}) == 4
    assert len({id(item.completed_prices._prices._frame) for item in copies}) == 4
    for item in copies:
        assert item.qualification is retained.qualification
        assert item.to_dict() == retained.to_dict()
        assert item.source_row_count == retained.source_row_count
        assert item.target_row_count == retained.target_row_count
        assert tuple(item.completed_prices.iter_rows()) == tuple(
            retained.completed_prices.iter_rows()
        )
        assert tuple(
            b._binary64(value)
            for row in item.completed_prices.iter_rows()
            for value in row[2:7]
        ) == tuple(
            b._binary64(value)
            for row in retained.completed_prices.iter_rows()
            for value in row[2:7]
        )
    before = second.to_dict()
    first.completed_prices._prices._frame.loc[0, "volume"] = 123.0
    assert second.to_dict() == before
    assert returned.to_dict() == before
    assert retained.to_dict() == before
    assert service._history._state[0] == 2


def test_public_copy_failure_cannot_publish_partial_success(authentic, monkeypatch):
    service = _service(authentic)

    def fail_copy(value):
        assert service._history._lock.locked()
        assert service._history._state == (1, ())
        raise ValueError("defensive carrier copy failed")

    monkeypatch.setattr(b, "deepcopy", fail_copy)
    _refuse(
        service,
        _request(authentic[1]),
        b.PolygonCompletedDailyBridgeRefusalReason.PUBLICATION_FAILED,
    )
