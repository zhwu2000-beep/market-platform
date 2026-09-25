"""FAST PURE / LOCAL APPLICATION composition tests; no live transport."""

import asyncio
import inspect
import json
from copy import deepcopy
from dataclasses import FrozenInstanceError, fields, replace
from datetime import UTC, datetime, time, timedelta, timezone, tzinfo
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from zoneinfo import ZoneInfo

import pytest

from market_platform.application import radar_single_symbol as subject
from market_platform.data.exceptions import (
    AuthenticationError,
    ConfigurationError,
    DataProviderError,
    NetworkError,
    RateLimitError,
)
from market_platform.data.providers.polygon import (
    PolygonCompletedDailyAcquisition,
    PolygonCompletedDailyAggregate,
)
from market_platform.instruments.identity import CanonicalInstrumentId
from market_platform.radar.application import RadarCheckpointAdvancementError
from market_platform.radar.calendar import CalendarCoverageError
from market_platform.radar.checkpoint_store import RadarCheckpointStoreError
from market_platform.radar.core import (
    RadarGateIdentity,
    RadarGateOccurrence,
    RadarProfile,
)
from market_platform.radar.resolver import RadarResolutionError

AS_OF = datetime(2026, 9, 24, tzinfo=UTC)
COMPLETED = AS_OF + timedelta(minutes=1)


def acceptance_profile(relations=("ABOVE", "EQUAL", "BELOW")):
    def occurrence(name, key, configuration):
        return RadarGateOccurrence(
            name,
            RadarGateIdentity(
                key.gate_id,
                key.behavioral_revision,
                key.configuration_schema,
                configuration,
            ),
        )

    return RadarProfile(
        "acceptance",
        "1",
        "test/v1",
        (
            occurrence("trigger", subject.SESSION_CONTENT_TRIGGER_KEY, {}),
            occurrence(
                "ema",
                subject.EMA8_EMA20_RELATION_KEY,
                {"accepted_relations": list(relations)},
            ),
        ),
    )


def document():
    return {
        "schema_version": "trusted_instrument_mapping_document/v1",
        "source": {
            "source_id": "fixture",
            "source_version": "1",
            "configuration_fingerprint": None,
        },
        "instruments": [
            {
                "instrument_id": "security.canonical",
                "trading_identity": {"symbol": "CANON", "venue": "NASDAQ"},
                "asset_class": "equity",
                "trading_currency": "USD",
            }
        ],
        "mappings": [
            {
                "external_identity": {
                    "namespace": "polygon",
                    "external_symbol": "ALIAS",
                    "external_venue": "NASDAQ",
                },
                "canonical_instrument_id": "security.canonical",
                "valid_from": "2000-01-01",
                "expires_at": None,
            }
        ],
    }


@pytest.fixture(scope="module")
def calendar():
    return subject.ExchangeCalendarsSessionCalendar()


@pytest.fixture
def runtime(tmp_path, monkeypatch, calendar):
    path = tmp_path / "mapping.json"
    path.write_text(json.dumps(document()), encoding="utf-8")
    root = tmp_path / "checkpoints"
    root.mkdir()
    latest = calendar.latest_completed_session(AS_OF)
    start = latest
    for _ in range(249):
        start = calendar.previous_session(start)
    sessions = calendar.sessions_in_range(start, latest)
    acquisition = PolygonCompletedDailyAcquisition(
        requested_ticker="ALIAS",
        requested_from=start.isoformat(),
        requested_to=latest.isoformat(),
        response_ticker_is_present=True,
        response_ticker="ALIAS",
        response_adjusted_is_present=True,
        response_adjusted=True,
        request_id_is_present=False,
        request_id=None,
        query_count_is_present=False,
        query_count=None,
        results_count_is_present=True,
        results_count=250,
        count_is_present=True,
        count=250,
        next_url_is_present=False,
        next_page_reference=None,
        results_is_present=True,
        rows=tuple(
            PolygonCompletedDailyAggregate(
                int(
                    datetime.combine(
                        label, time(), ZoneInfo("America/New_York")
                    ).timestamp()
                    * 1000
                ),
                100,
                400,
                1,
                100 + index,
                1000,
            )
            for index, label in enumerate(sessions)
        ),
        response_received_at=AS_OF,
    )
    provider = Mock()
    provider.get_completed_daily_acquisition = AsyncMock(return_value=acquisition)
    client = Mock()
    factories = {}
    for name, value in (
        ("get_settings", SimpleNamespace(polygon_api_key="secret-fixture")),
        ("create_http_client", client),
        ("PolygonProvider", provider),
        ("ExchangeCalendarsSessionCalendar", calendar),
        ("_completion_clock", COMPLETED),
    ):
        factories[name] = Mock(return_value=value)
        monkeypatch.setattr(subject, name, factories[name])
    kwargs = dict(
        symbol="CANON",
        as_of=AS_OF,
        profile=acceptance_profile(),
        instrument_mappings_path=path,
        checkpoint_root=root,
    )
    return SimpleNamespace(
        kwargs=kwargs,
        provider=provider,
        client=client,
        factories=factories,
        calendar=calendar,
        sessions=sessions,
    )


def run(runtime, **changes):
    return subject.run_single_symbol_radar(**(runtime.kwargs | changes))


def test_acceptance_repeat_and_projection(runtime):
    first = run(runtime, as_of=AS_OF.astimezone(timezone(timedelta(hours=8))))
    app = first.application
    assert app.pipeline_result.profile is runtime.kwargs["profile"]
    assert app.pipeline_result.instrument.instrument_id == "security.canonical"
    assert app.pipeline_result.as_of == AS_OF
    assert app.pipeline_result.outcome == "SELECTED"
    assert [r.disposition for r in app.pipeline_result.executed_results] == [
        "PASS",
        "PASS",
    ]
    assert app.pipeline_result.executed_results[0].reason_code == "BASELINE_REQUIRED"
    assert "ABOVE" in app.pipeline_result.executed_results[1].reason_code
    assert app.advancement == "SAVED"
    assert app.saved_checkpoint.observed_at == COMPLETED
    runtime.provider.get_completed_daily_acquisition.assert_awaited_once_with(
        "ALIAS",
        runtime.sessions[0],
        runtime.sessions[-1],
    )
    runtime.client.close.assert_called_once_with()
    runtime.factories["PolygonProvider"].assert_called_once_with(
        http_client=runtime.client,
        api_key="secret-fixture",
    )
    projection = first.to_dict()
    assert projection == first.to_dict()
    assert "secret-fixture" not in json.dumps(projection)
    assert projection["canonical_instrument"] == first.canonical_instrument.to_dict()
    assert (
        projection["application"]["saved_checkpoint"] == app.saved_checkpoint.to_dict()
    )
    assert (
        projection["application"]["pipeline"]["profile"]
        == runtime.kwargs["profile"].to_dict()
    )
    assert projection["application"]["pipeline"]["terminating_occurrence"] is None
    with pytest.raises(FrozenInstanceError):
        first.application = None
    second = run(runtime)
    pipeline = second.to_dict()["application"]["pipeline"]
    assert pipeline["outcome"] == "FILTERED"
    assert len(pipeline["executed_results"]) == 1
    assert pipeline["executed_results"][0]["reason_code"] == "UNCHANGED"
    assert (
        pipeline["terminating_occurrence"]
        == runtime.kwargs["profile"].gates[0].to_dict()
    )
    assert second.application.advancement == "NOT_ADVANCED"
    assert second.application.saved_checkpoint is None
    assert runtime.provider.get_completed_daily_acquisition.await_count == 2
    assert runtime.client.close.call_count == 2


@pytest.mark.parametrize("field", ["canonical_instrument", "application"])
@pytest.mark.parametrize("kind", ["none", "duck", "subclass"])
def test_response_rejects_wrong_runtime_types(runtime, field, kind):
    response = run(runtime)
    value = getattr(response, field)
    attributes = {
        item.name: getattr(value, item.name) for item in fields(value) if item.init
    }
    invalid = None
    if kind == "duck":
        invalid = SimpleNamespace(**attributes)
    elif kind == "subclass":
        invalid = type("Subclass", (type(value),), {})(**attributes)
    with pytest.raises(TypeError, match=field):
        replace(response, **{field: invalid})


def test_response_rejects_pipeline_identity_mismatch_before_projection(runtime):
    response = run(runtime)
    other = replace(
        response.canonical_instrument,
        instrument_id=CanonicalInstrumentId("security.other"),
    )
    with pytest.raises(ValueError, match="canonical instrument must match pipeline"):
        subject.RadarSingleSymbolResponse(other, response.application).to_dict()


def test_response_rejects_checkpoint_identity_mismatch_before_projection(runtime):
    response = run(runtime)
    checkpoint = replace(
        response.application.saved_checkpoint,
        instrument=CanonicalInstrumentId("security.other"),
    )
    application = replace(response.application, saved_checkpoint=checkpoint)
    with pytest.raises(ValueError, match="saved checkpoint instrument must match"):
        subject.RadarSingleSymbolResponse(
            response.canonical_instrument, application
        ).to_dict()


def test_active_loop_rejected_first(runtime, monkeypatch, recwarn):
    spies = []
    for name in (
        "load_trusted_instrument_mapping_registry",
        "RadarCheckpointFileStore",
        "RadarGateResolver",
        "bind_completed_daily_current_content",
    ):
        spy = Mock(side_effect=AssertionError("side effect"))
        monkeypatch.setattr(subject, name, spy)
        spies.append(spy)

    async def invoke():
        with pytest.raises(
            subject.RadarSingleSymbolError, match="running asyncio event loop"
        ):
            run(runtime, as_of=datetime(2026, 1, 1))

    asyncio.run(invoke())
    for spy in [*spies, *runtime.factories.values()]:
        spy.assert_not_called()
    runtime.provider.get_completed_daily_acquisition.assert_not_called()
    assert not recwarn


class NoOffset(tzinfo):
    def utcoffset(self, dt):
        return None


@pytest.mark.parametrize(
    "as_of", [datetime(2026, 1, 1), datetime(2026, 1, 1, tzinfo=NoOffset()), None]
)
def test_invalid_as_of_before_side_effects(runtime, monkeypatch, as_of):
    loader = Mock()
    monkeypatch.setattr(subject, "load_trusted_instrument_mapping_registry", loader)
    with pytest.raises((TypeError, ValueError), match="as_of"):
        run(runtime, as_of=as_of)
    loader.assert_not_called()
    for factory in runtime.factories.values():
        factory.assert_not_called()


def test_mapping_exact_path_and_shared_wiring(runtime, monkeypatch):
    original = subject.load_trusted_instrument_mapping_registry
    registry = original(runtime.kwargs["instrument_mappings_path"])
    loader = Mock(return_value=registry)
    binder = Mock(wraps=subject.bind_completed_daily_current_content)
    trigger = Mock(wraps=subject.RadarSessionContentTriggerGate)
    ema = Mock(wraps=subject.RadarEma8Ema20RelationGate)
    monkeypatch.setattr(subject, "load_trusted_instrument_mapping_registry", loader)
    monkeypatch.setattr(subject, "bind_completed_daily_current_content", binder)
    monkeypatch.setattr(subject, "RadarSessionContentTriggerGate", trigger)
    monkeypatch.setattr(subject, "RadarEma8Ema20RelationGate", ema)
    run(runtime)
    loader.assert_called_once_with(runtime.kwargs["instrument_mappings_path"])
    assert binder.call_args.kwargs["mappings"] is registry.mappings
    assert (
        binder.call_args.kwargs["external_identity"]
        is registry.mappings[0].external_identity
    )
    assert binder.call_args.kwargs["calendar"] is runtime.calendar
    assert trigger.call_args.args == (
        runtime.kwargs["profile"].gates[0],
        runtime.calendar,
    )
    ema.assert_called_once_with(runtime.kwargs["profile"].gates[1])
    runtime.factories["ExchangeCalendarsSessionCalendar"].assert_called_once_with()


@pytest.mark.parametrize("missing", [False, True])
def test_mapping_load_errors_propagate(runtime, missing):
    path = runtime.kwargs["instrument_mappings_path"]
    if missing:
        path.unlink()
    else:
        path.write_text("{malformed", encoding="utf-8")
    with pytest.raises(OSError if missing else ValueError):
        run(runtime)
    runtime.factories["create_http_client"].assert_not_called()


@pytest.mark.parametrize(
    "kind,message",
    [
        ("absent", "symbol was not found"),
        ("ambiguous", "symbol is ambiguous"),
        ("venue", "requires NASDAQ"),
        ("no_alias", "identity was not found"),
        ("two_aliases", "identity is ambiguous"),
    ],
)
def test_selection_errors(runtime, kind, message):
    doc = document()
    if kind == "absent":
        runtime.kwargs["symbol"] = "ALIAS"
    elif kind == "ambiguous":
        other = deepcopy(doc["instruments"][0])
        other["instrument_id"] = "other"
        doc["instruments"].append(other)
    elif kind == "venue":
        doc["instruments"][0]["trading_identity"]["venue"] = "NYSE"
    elif kind == "no_alias":
        other = deepcopy(doc["instruments"][0])
        other["instrument_id"] = "other"
        other["trading_identity"]["symbol"] = "OTHER"
        doc["instruments"].append(other)
        doc["mappings"][0]["canonical_instrument_id"] = "other"
    else:
        other = deepcopy(doc["mappings"][0])
        other["external_identity"]["external_symbol"] = "OLD"
        doc["mappings"].append(other)
    runtime.kwargs["instrument_mappings_path"].write_text(
        json.dumps(doc), encoding="utf-8"
    )
    with pytest.raises(subject.RadarSingleSymbolError, match=message):
        run(runtime)
    runtime.factories["create_http_client"].assert_not_called()


def test_existing_symbol_normalization(runtime):
    assert (
        run(runtime, symbol=" canon ").application.pipeline_result.outcome == "SELECTED"
    )


def test_full_conflicting_history_reaches_pipeline(runtime, monkeypatch):
    doc = document()
    other = deepcopy(doc["instruments"][0])
    other["instrument_id"] = "other"
    other["trading_identity"]["symbol"] = "OTHER"
    doc["instruments"].append(other)
    conflict = deepcopy(doc["mappings"][0])
    conflict["canonical_instrument_id"] = "other"
    doc["mappings"].append(conflict)
    runtime.kwargs["instrument_mappings_path"].write_text(
        json.dumps(doc), encoding="utf-8"
    )
    binder = Mock(wraps=subject.bind_completed_daily_current_content)
    monkeypatch.setattr(subject, "bind_completed_daily_current_content", binder)
    assert run(runtime).application.pipeline_result.outcome == "FAILED"
    assert len(binder.call_args.kwargs["mappings"]) == 2
    runtime.client.close.assert_called_once()


def test_same_identity_multiple_history_rows_is_not_selection_ambiguity(runtime):
    doc = document()
    historic = deepcopy(doc["mappings"][0])
    historic["valid_from"] = "1990-01-01"
    historic["expires_at"] = "2000-01-01"
    doc["mappings"].append(historic)
    runtime.kwargs["instrument_mappings_path"].write_text(
        json.dumps(doc), encoding="utf-8"
    )
    assert run(runtime).application.pipeline_result.outcome == "SELECTED"


@pytest.mark.parametrize(
    "error",
    [
        NetworkError,
        RateLimitError,
        DataProviderError,
        AuthenticationError,
        ConfigurationError,
    ],
)
def test_provider_errors(runtime, error):
    runtime.provider.get_completed_daily_acquisition.side_effect = error(
        "raw-secret-error"
    )
    response = run(runtime)
    pipeline = response.application.pipeline_result
    if error in (NetworkError, RateLimitError):
        assert pipeline.outcome == "ATTENTION"
        assert pipeline.executed_results[0].reason_code == "CURRENT_CONTENT_UNAVAILABLE"
    else:
        assert pipeline.outcome == "FAILED"
        assert pipeline.failure.occurrence == runtime.kwargs["profile"].gates[0]
        assert pipeline.failure.category == "GATE_EXCEPTION"
        assert response.to_dict()["application"]["pipeline"]["executed_results"] == []
        assert response.to_dict()["application"]["pipeline"]["failure"] == {
            "occurrence": pipeline.failure.occurrence.to_dict(),
            "category": "GATE_EXCEPTION",
        }
    assert response.application.advancement == "NOT_ADVANCED"
    assert "raw-secret-error" not in json.dumps(response.to_dict())
    runtime.client.close.assert_called_once()


def test_malformed_prior_avoids_acquisition(runtime):
    run(runtime)
    next(runtime.kwargs["checkpoint_root"].glob("*.json")).write_text(
        "{bad", encoding="utf-8"
    )
    runtime.provider.get_completed_daily_acquisition.reset_mock()
    runtime.client.reset_mock()
    result = run(runtime).application
    assert result.pipeline_result.outcome == "FAILED"
    assert (
        result.pipeline_result.failure.occurrence == runtime.kwargs["profile"].gates[0]
    )
    assert result.advancement == "NOT_ADVANCED"
    runtime.provider.get_completed_daily_acquisition.assert_not_called()
    runtime.client.close.assert_called_once()


def test_unavailable_root_is_lazy_and_not_created(runtime):
    root = runtime.kwargs["checkpoint_root"] / "unprovisioned"
    result = run(runtime, checkpoint_root=root).application
    assert (
        result.pipeline_result.executed_results[0].reason_code
        == "PRIOR_STATE_UNAVAILABLE"
    )
    assert result.pipeline_result.outcome == "ATTENTION"
    assert result.advancement == "NOT_ADVANCED"
    assert not root.exists()
    runtime.provider.get_completed_daily_acquisition.assert_not_called()
    runtime.client.close.assert_called_once()


def test_save_failure_retains_completed_result(runtime, monkeypatch):
    monkeypatch.setattr(
        subject.RadarCheckpointFileStore, "save", Mock(side_effect=OSError("save"))
    )
    with pytest.raises(RadarCheckpointAdvancementError) as exc:
        run(runtime)
    assert exc.value.pipeline_result.outcome == "SELECTED"
    assert len(exc.value.pipeline_result.executed_results) == 2
    runtime.client.close.assert_called_once()


def test_unsupported_profile_and_no_default(runtime):
    assert (
        inspect.signature(subject.run_single_symbol_radar).parameters["profile"].default
        is inspect.Parameter.empty
    )
    profile = runtime.kwargs["profile"]
    unknown = replace(
        profile.gates[1], gate_identity=RadarGateIdentity("unknown", "1", "v1")
    )
    with pytest.raises(RadarResolutionError, match="UNSUPPORTED_IMPLEMENTATION"):
        run(runtime, profile=replace(profile, gates=(profile.gates[0], unknown)))
    runtime.provider.get_completed_daily_acquisition.assert_not_called()
    runtime.client.close.assert_called_once()


def test_caller_relation_configuration_preserved(runtime):
    response = run(runtime, profile=acceptance_profile(("BELOW",)))
    assert response.application.pipeline_result.outcome == "FILTERED"
    assert (
        response.application.pipeline_result.executed_results[1].disposition == "DROP"
    )
    assert response.application.advancement == "SAVED"


@pytest.mark.parametrize(
    "name",
    [
        "PolygonProvider",
        "bind_completed_daily_current_content",
        "RadarApplicationService",
    ],
)
def test_cleanup_after_owned_composition_failure(runtime, monkeypatch, name):
    error = ValueError("construction")
    monkeypatch.setattr(subject, name, Mock(side_effect=error))
    with pytest.raises(ValueError) as exc:
        run(runtime)
    assert exc.value is error
    runtime.client.close.assert_called_once()


def test_cleanup_failure_preserves_result_and_original_exception(runtime, monkeypatch):
    logger = Mock()
    monkeypatch.setattr(subject, "get_logger", Mock(return_value=logger))
    runtime.client.close.side_effect = RuntimeError("secret cleanup")
    assert run(runtime).application.pipeline_result.outcome == "SELECTED"
    error = ValueError("original")
    runtime.factories["PolygonProvider"].side_effect = error
    with pytest.raises(ValueError) as exc:
        run(runtime)
    assert exc.value is error
    assert runtime.client.close.call_count == 2
    assert "secret cleanup" not in str(logger.mock_calls)


@pytest.mark.parametrize("field", ["instrument_mappings_path", "checkpoint_root"])
def test_relative_paths_rejected(runtime, field):
    with pytest.raises(
        (subject.RadarSingleSymbolError, RadarCheckpointStoreError), match="absolute"
    ):
        run(runtime, **{field: Path("relative")})
    runtime.factories["create_http_client"].assert_not_called()
    runtime.client.close.assert_not_called()


def test_calendar_construction_failure_preserved(runtime):
    error = CalendarCoverageError("coverage")
    runtime.factories["ExchangeCalendarsSessionCalendar"].side_effect = error
    with pytest.raises(CalendarCoverageError) as exc:
        run(runtime)
    assert exc.value is error
    runtime.factories["create_http_client"].assert_not_called()
    runtime.client.close.assert_not_called()


def test_real_provider_missing_credentials_is_lazy(runtime, monkeypatch):
    from market_platform.data.providers.polygon import PolygonProvider

    runtime.factories["get_settings"].return_value.polygon_api_key = ""
    monkeypatch.setattr(subject, "PolygonProvider", PolygonProvider)
    response = run(runtime)
    assert response.application.pipeline_result.outcome == "FAILED"
    runtime.client.get_exact_json.assert_not_called()
    runtime.client.close.assert_called_once()


def test_composition_does_not_acquire_and_passes_exact_loader_bundle(
    runtime, monkeypatch
):
    original = subject.RadarApplicationService
    binder = Mock(wraps=subject.bind_completed_daily_current_content)
    bundles = []

    def bind(**kwargs):
        loaders = binder(**kwargs)
        bundles.append(loaders)
        runtime.provider.get_completed_daily_acquisition.assert_not_called()
        return loaders

    def service(resolver, store, clock):
        runtime.provider.get_completed_daily_acquisition.assert_not_called()
        real = original(resolver, store, clock)

        def evaluate(profile, instrument, as_of, loaders):
            assert loaders is bundles[-1]
            assert len(loaders) == 2  # Prior observation remains Application-owned.
            runtime.provider.get_completed_daily_acquisition.assert_not_called()
            return real.evaluate(profile, instrument, as_of, loaders)

        return SimpleNamespace(evaluate=evaluate)

    monkeypatch.setattr(subject, "bind_completed_daily_current_content", bind)
    monkeypatch.setattr(subject, "RadarApplicationService", service)
    run(runtime)
    runtime.provider.get_completed_daily_acquisition.reset_mock()
    run(runtime)
    assert bundles[0] is not bundles[1]


def test_owned_wrapper_does_not_close_borrowed_transport(runtime):
    from market_platform.data.http import HTTPClient

    borrowed_transport = Mock()
    owned_wrapper = HTTPClient(client=borrowed_transport)
    runtime.factories["create_http_client"].return_value = owned_wrapper
    run(runtime)
    borrowed_transport.close.assert_not_called()
    runtime.client.close.assert_not_called()


def test_calendar_execution_failure_stays_pipeline_failure(runtime, monkeypatch):
    calendar = Mock(wraps=runtime.calendar)
    calendar.latest_completed_session.side_effect = CalendarCoverageError("coverage")
    runtime.factories["ExchangeCalendarsSessionCalendar"].return_value = calendar
    result = run(runtime).application
    assert result.pipeline_result.outcome == "FAILED"
    assert result.advancement == "NOT_ADVANCED"
    runtime.provider.get_completed_daily_acquisition.assert_not_called()
    runtime.client.close.assert_called_once()


def test_production_completion_clock_is_utc_wall_time():
    before = datetime.now(UTC)
    observed = subject._completion_clock()
    after = datetime.now(UTC)
    assert observed.tzinfo is UTC
    assert before <= observed <= after
