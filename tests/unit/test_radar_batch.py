"""Sequential Radar contracts and mocked production composition; no network."""

import asyncio
import json
from dataclasses import FrozenInstanceError, fields, replace
from datetime import UTC, datetime, time, timedelta, timezone, tzinfo
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from zoneinfo import ZoneInfo

import pytest

from market_platform.application import radar_batch as subject
from market_platform.application import radar_single_symbol as single
from market_platform.data.providers.polygon import (
    PolygonCompletedDailyAcquisition,
    PolygonCompletedDailyAggregate,
)
from market_platform.instruments.identity import (
    CanonicalInstrument,
    CanonicalInstrumentId,
    InstrumentAssetClass,
)
from market_platform.radar.application import (
    RadarApplicationResult,
    RadarCheckpointAdvancement,
    RadarCheckpointAdvancementError,
)
from market_platform.radar.checkpoint_store import RadarCheckpointFileStore
from market_platform.radar.core import (
    RadarGateDisposition,
    RadarGateIdentity,
    RadarGateOccurrence,
    RadarGateResult,
    RadarProfile,
)
from market_platform.radar.pipeline import (
    RadarPipelineFailure,
    RadarPipelineFailureCategory,
    RadarPipelineResult,
)
from market_platform.trading import TradingInstrumentIdentity

AS_OF = datetime(2026, 9, 24, tzinfo=UTC)


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


PROFILE = RadarProfile(
    "batch-test",
    "1",
    "test/v1",
    (
        occurrence("trigger", single.SESSION_CONTENT_TRIGGER_KEY, {}),
        occurrence(
            "ema",
            single.EMA8_EMA20_RELATION_KEY,
            {"accepted_relations": ["ABOVE", "EQUAL", "BELOW"]},
        ),
    ),
)


def response(symbol="NVDA", outcome="SELECTED", *, profile=PROFILE, as_of=AS_OF):
    canonical = CanonicalInstrument(
        CanonicalInstrumentId(f"security.{symbol}"),
        TradingInstrumentIdentity(symbol, "NASDAQ"),
        InstrumentAssetClass.EQUITY,
        "USD",
    )
    failure = None
    if outcome == "FAILED":
        results = ()
        failure = RadarPipelineFailure(
            profile.gates[0], RadarPipelineFailureCategory.GATE_EXCEPTION
        )
    elif outcome == "SELECTED":
        results = tuple(
            RadarGateResult(gate, RadarGateDisposition.PASS, "PASSED")
            for gate in profile.gates
        )
    else:
        disposition = (
            RadarGateDisposition.DROP
            if outcome == "FILTERED"
            else RadarGateDisposition.ATTENTION
        )
        results = (RadarGateResult(profile.gates[0], disposition, "BOUNDED_REASON"),)
    pipeline = RadarPipelineResult(
        profile, canonical.instrument_id, as_of, results, failure
    )
    return single.RadarSingleSymbolResponse(
        canonical,
        RadarApplicationResult(
            pipeline,
            RadarCheckpointAdvancement.NOT_ADVANCED,
        ),
    )


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    runner = Mock(
        side_effect=lambda **kwargs: response(
            kwargs["symbol"],
            profile=kwargs["profile"],
            as_of=kwargs["as_of"],
        )
    )
    monkeypatch.setattr(subject, "run_single_symbol_radar", runner)
    return SimpleNamespace(
        runner=runner,
        kwargs=dict(
            symbols=("NVDA", "MSFT"),
            as_of=AS_OF,
            profile=PROFILE,
            instrument_mappings_path=tmp_path / "mapping.json",
            checkpoint_root=tmp_path / "not-created",
        ),
    )


def run(runtime, **changes):
    return subject.run_radar_batch(**(runtime.kwargs | changes))


@pytest.mark.parametrize("symbols", [(" msft ", "nvda"), [" msft ", "nvda"]])
def test_order_normalization_and_exact_forwarding(runtime, symbols):
    as_of = AS_OF.astimezone(timezone(timedelta(hours=8)))
    originals = [response("MSFT"), response("NVDA")]

    def invoke(**kwargs):
        if isinstance(symbols, list):
            symbols[:] = ["CHANGED"]
        return originals[runtime.runner.call_count - 1]

    runtime.runner.side_effect = invoke
    result = run(runtime, symbols=symbols, as_of=as_of)
    assert tuple(item.symbol for item in result.items) == ("MSFT", "NVDA")
    assert type(result.items) is tuple
    assert [item.response for item in result.items] == originals
    assert all(
        item.response is original
        for item, original in zip(result.items, originals, strict=True)
    )
    assert runtime.runner.call_count == 2
    for call, symbol in zip(
        runtime.runner.call_args_list, ("MSFT", "NVDA"), strict=True
    ):
        assert call.kwargs["symbol"] == symbol
        assert call.kwargs["profile"] is PROFILE
        assert call.kwargs["as_of"] is as_of
        for name in ("instrument_mappings_path", "checkpoint_root"):
            assert call.kwargs[name] is runtime.kwargs[name]
    assert not runtime.kwargs["checkpoint_root"].exists()
    assert result.as_of.tzinfo is UTC
    assert result.to_dict() == result.to_dict()
    assert set(result.to_dict()) == {"profile", "as_of", "items"}
    assert json.loads(json.dumps(result.to_dict())) == result.to_dict()


class NoOffset(tzinfo):
    def utcoffset(self, dt):
        return None


@pytest.mark.parametrize(
    "changes,error",
    [
        ({"symbols": ()}, ValueError),
        ({"symbols": []}, ValueError),
        ({"symbols": "NVDA"}, TypeError),
        ({"symbols": {"NVDA"}}, TypeError),
        ({"symbols": iter(["NVDA"])}, TypeError),
        ({"symbols": ("NVDA", 4)}, TypeError),
        ({"symbols": ("NVDA", " nvda ")}, ValueError),
        ({"symbols": ("NVDA", " ")}, ValueError),
        ({"symbols": ("NVDA", "NASDAQ:MSFT")}, ValueError),
        ({"as_of": None}, TypeError),
        ({"as_of": datetime(2026, 1, 1)}, ValueError),
        ({"as_of": datetime(2026, 1, 1, tzinfo=NoOffset())}, ValueError),
        ({"profile": None}, TypeError),
        ({"instrument_mappings_path": Path("relative")}, ValueError),
        ({"checkpoint_root": Path("relative")}, ValueError),
        ({"checkpoint_root": "absolute-looking"}, TypeError),
    ],
)
def test_prevalidation_before_any_runner_call(runtime, changes, error):
    with pytest.raises(error):
        run(runtime, **changes)
    runtime.runner.assert_not_called()


def test_active_loop_rejected_before_even_invalid_inputs(runtime):
    async def invoke():
        with pytest.raises(RuntimeError, match="running asyncio event loop"):
            run(runtime, symbols=None, as_of=None)

    asyncio.run(invoke())
    runtime.runner.assert_not_called()


@pytest.mark.parametrize("outcome", ["SELECTED", "FILTERED", "ATTENTION", "FAILED"])
def test_actual_responses_preserved(runtime, outcome):
    actual = response(outcome=outcome)
    runtime.runner.side_effect = None
    runtime.runner.return_value = actual
    result = run(runtime, symbols=("NVDA",))
    assert result.items[0].response is actual
    assert result.items[0].failure is None
    assert result.to_dict()["items"][0]["response"] == actual.to_dict()
    assert actual.application.pipeline_result.outcome == outcome


def test_middle_exception_is_bounded_and_later_symbol_runs(runtime):
    first, last = response("NVDA"), response("MU")
    runtime.runner.side_effect = [first, ValueError("fake-api-secret"), last]
    result = run(runtime, symbols=("NVDA", "MSFT", "MU"))
    assert result.items[0].response is first
    assert result.items[2].response is last
    assert runtime.runner.call_count == 3
    assert result.items[1].response is None
    assert result.items[1].failure.pipeline_result is None
    projection = result.to_dict()
    assert projection["items"][1] == {
        "symbol": "MSFT",
        "response": None,
        "failure": {"category": "EXECUTION_ERROR"},
    }
    assert "fake-api-secret" not in json.dumps(projection)


def test_checkpoint_failure_retains_only_actual_pipeline_and_continues(runtime):
    actual = response("NVDA")
    pipeline = actual.application.pipeline_result
    pipeline = replace(
        pipeline,
        executed_results=tuple(
            replace(result, detail="fake-provider-secret")
            for result in pipeline.executed_results
        ),
    )
    error = RadarCheckpointAdvancementError(pipeline)
    error.__cause__ = OSError("fake-api-secret")
    last = response("MSFT")
    runtime.runner.side_effect = [error, last]
    result = run(runtime)
    item = result.items[0]
    assert item.response is None
    assert (
        item.failure.category
        is subject.RadarBatchFailureCategory.CHECKPOINT_SAVE_FAILED
    )
    assert item.failure.pipeline_result is pipeline
    assert result.items[1].response is last
    assert runtime.runner.call_count == 2
    projected = item.failure.to_dict()
    assert set(projected) == {"category", "pipeline"}
    assert projected["pipeline"] == actual.to_dict()["application"]["pipeline"]
    assert set(projected["pipeline"]) == {
        "profile",
        "instrument",
        "as_of",
        "outcome",
        "executed_results",
        "terminating_occurrence",
        "failure",
    }
    for gate in projected["pipeline"]["executed_results"]:
        assert set(gate) == {"occurrence", "disposition", "reason_code"}
    assert "fake-" not in json.dumps(result.to_dict())


@pytest.mark.parametrize(
    "error", [KeyboardInterrupt, SystemExit, asyncio.CancelledError]
)
def test_base_exception_propagates(runtime, error):
    runtime.runner.side_effect = error()
    with pytest.raises(error):
        run(runtime)
    assert runtime.runner.call_count == 1


def execution_failure():
    return subject.RadarBatchFailure(subject.RadarBatchFailureCategory.EXECUTION_ERROR)


@pytest.mark.parametrize(
    "category,payload,error",
    [
        ("EXECUTION_ERROR", None, TypeError),
        (
            subject.RadarBatchFailureCategory.EXECUTION_ERROR,
            response().application.pipeline_result,
            ValueError,
        ),
        (subject.RadarBatchFailureCategory.CHECKPOINT_SAVE_FAILED, None, ValueError),
        (subject.RadarBatchFailureCategory.CHECKPOINT_SAVE_FAILED, object(), TypeError),
    ],
)
def test_failure_invariants(category, payload, error):
    with pytest.raises(error):
        subject.RadarBatchFailure(category, payload)


@pytest.mark.parametrize(
    "symbol,normal,failure,error",
    [
        ("NVDA", None, None, ValueError),
        ("NVDA", response(), execution_failure(), ValueError),
        ("NVDA", object(), None, TypeError),
        ("NVDA", None, object(), TypeError),
        ("MSFT", response(), None, ValueError),
        (" nvda ", response(), None, ValueError),
        (4, None, execution_failure(), TypeError),
    ],
)
def test_item_invariants(symbol, normal, failure, error):
    with pytest.raises(error):
        subject.RadarBatchItemResult(symbol, normal, failure)


@pytest.mark.parametrize("kind", ["normal", "checkpoint"])
@pytest.mark.parametrize("field", ["profile", "as_of"])
def test_batch_correspondence(kind, field):
    actual = response()
    if kind == "normal":
        item = subject.RadarBatchItemResult("NVDA", response=actual)
    else:
        item = subject.RadarBatchItemResult(
            "NVDA",
            failure=subject.RadarBatchFailure(
                subject.RadarBatchFailureCategory.CHECKPOINT_SAVE_FAILED,
                actual.application.pipeline_result,
            ),
        )
    changes = (
        {"profile": replace(PROFILE, profile_id="other")}
        if field == "profile"
        else {"as_of": AS_OF + timedelta(seconds=1)}
    )
    with pytest.raises(ValueError, match="must match batch"):
        subject.RadarBatchResponse(
            **(dict(profile=PROFILE, as_of=AS_OF, items=(item,)) | changes)
        )


@pytest.mark.parametrize(
    "changes,error",
    [
        ({"profile": None}, TypeError),
        ({"as_of": None}, TypeError),
        ({"as_of": datetime(2026, 1, 1)}, ValueError),
        ({"items": ()}, ValueError),
        ({"items": "NVDA"}, TypeError),
        ({"items": (object(),)}, TypeError),
    ],
)
def test_batch_structural_invariants(changes, error):
    with pytest.raises(error):
        subject.RadarBatchResponse(
            **(
                dict(
                    profile=PROFILE,
                    as_of=AS_OF,
                    items=(
                        subject.RadarBatchItemResult(
                            "NVDA", failure=execution_failure()
                        ),
                    ),
                )
                | changes
            )
        )


def test_batch_items_snapshot_duplicates_and_frozen_values():
    failure = execution_failure()
    item = subject.RadarBatchItemResult("NVDA", failure=failure)
    items = [item]
    result = subject.RadarBatchResponse(PROFILE, AS_OF, items)
    items.clear()
    assert result.items == (item,)
    with pytest.raises(ValueError, match="repeat"):
        subject.RadarBatchResponse(PROFILE, AS_OF, (item, item))
    for value in (failure, item, result):
        field = fields(value)[0].name
        with pytest.raises(FrozenInstanceError):
            setattr(value, field, None)
        assert not hasattr(value, "__dict__")


def subclass(value):
    return type("Subclass", (type(value),), {})(
        **{
            field.name: getattr(value, field.name)
            for field in fields(value)
            if field.init
        }
    )


def test_exact_runtime_types_reject_subclasses(runtime):
    actual = response()
    with pytest.raises(TypeError):
        subject.RadarBatchItemResult(
            type("StringSubclass", (str,), {})("NVDA"), response=actual
        )
    with pytest.raises(TypeError):
        run(runtime, profile=subclass(PROFILE))
    runtime.runner.assert_not_called()
    with pytest.raises(TypeError):
        subject.RadarBatchFailure(
            subject.RadarBatchFailureCategory.CHECKPOINT_SAVE_FAILED,
            subclass(actual.application.pipeline_result),
        )
    with pytest.raises(TypeError):
        subject.RadarBatchItemResult("NVDA", response=subclass(actual))
    with pytest.raises(TypeError):
        subject.RadarBatchItemResult("NVDA", failure=subclass(execution_failure()))
    item = subject.RadarBatchItemResult("NVDA", response=actual)
    with pytest.raises(TypeError):
        subject.RadarBatchResponse(PROFILE, AS_OF, (subclass(item),))
    with pytest.raises(TypeError):
        subject.RadarBatchResponse(subclass(PROFILE), AS_OF, (item,))
    for container in (
        type("ListSubclass", (list,), {})(["NVDA"]),
        type("TupleSubclass", (tuple,), {})(["NVDA"]),
    ):
        with pytest.raises(TypeError):
            run(runtime, symbols=container)


def test_two_symbol_production_checkpoint_isolation(tmp_path, monkeypatch):
    symbols = ("NVDA", "MSFT")
    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text(
        json.dumps(
            {
                "schema_version": "trusted_instrument_mapping_document/v1",
                "source": {
                    "source_id": "fixture",
                    "source_version": "1",
                    "configuration_fingerprint": None,
                },
                "instruments": [
                    {
                        "instrument_id": f"security.{symbol}",
                        "trading_identity": {"symbol": symbol, "venue": "NASDAQ"},
                        "asset_class": "equity",
                        "trading_currency": "USD",
                    }
                    for symbol in symbols
                ],
                "mappings": [
                    {
                        "external_identity": {
                            "namespace": "polygon",
                            "external_symbol": symbol,
                            "external_venue": "NASDAQ",
                        },
                        "canonical_instrument_id": f"security.{symbol}",
                        "valid_from": "2000-01-01",
                        "expires_at": None,
                    }
                    for symbol in symbols
                ],
            }
        ),
        encoding="utf-8",
    )
    root = tmp_path / "checkpoints"
    root.mkdir()
    calendar = single.ExchangeCalendarsSessionCalendar()
    end = calendar.latest_completed_session(AS_OF)
    start = end
    for _ in range(249):
        start = calendar.previous_session(start)
    sessions = calendar.sessions_in_range(start, end)

    async def acquire(ticker, requested_start, requested_end):
        assert (requested_start, requested_end) == (start, end)
        return PolygonCompletedDailyAcquisition(
            requested_ticker=ticker,
            requested_from=start.isoformat(),
            requested_to=end.isoformat(),
            response_ticker_is_present=True,
            response_ticker=ticker,
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
                    500,
                    1,
                    100 + index + symbols.index(ticker),
                    1000,
                )
                for index, label in enumerate(sessions)
            ),
            response_received_at=AS_OF,
        )

    providers, clients = [], []

    def provider_factory(**kwargs):
        provider = Mock(get_completed_daily_acquisition=AsyncMock(side_effect=acquire))
        providers.append(provider)
        return provider

    def client_factory():
        client = Mock()
        clients.append(client)
        return client

    monkeypatch.setattr(single, "PolygonProvider", provider_factory)
    monkeypatch.setattr(single, "create_http_client", client_factory)
    monkeypatch.setattr(
        single, "get_settings", lambda: SimpleNamespace(polygon_api_key="fake-secret")
    )
    kwargs = dict(
        symbols=symbols,
        as_of=AS_OF,
        profile=PROFILE,
        instrument_mappings_path=mapping_path,
        checkpoint_root=root,
    )
    first = subject.run_radar_batch(**kwargs)
    assert [
        item.response.application.pipeline_result.outcome for item in first.items
    ] == ["SELECTED"] * 2
    assert [item.response.application.advancement for item in first.items] == [
        "SAVED"
    ] * 2
    store = RadarCheckpointFileStore(root)
    checkpoints = [
        store.lookup(CanonicalInstrumentId(f"security.{symbol}")).checkpoint
        for symbol in symbols
    ]
    assert checkpoints[0].instrument != checkpoints[1].instrument
    assert (
        checkpoints[0].normalized_market_content_identity
        != checkpoints[1].normalized_market_content_identity
    )
    before = {path.name: path.read_bytes() for path in root.iterdir()}
    assert len(before) == 2
    second = subject.run_radar_batch(**kwargs)
    for item in second.items:
        app = item.response.application
        assert app.pipeline_result.outcome == "FILTERED"
        assert len(app.pipeline_result.executed_results) == 1
        assert app.pipeline_result.executed_results[0].reason_code == "UNCHANGED"
        assert app.advancement == "NOT_ADVANCED"
        assert app.saved_checkpoint is None
    assert before == {path.name: path.read_bytes() for path in root.iterdir()}
    assert len(providers) == len(clients) == 4
    for index, provider in enumerate(providers):
        provider.get_completed_daily_acquisition.assert_awaited_once_with(
            symbols[index % 2], start, end
        )
    for client in clients:
        client.close.assert_called_once_with()
    assert "fake-secret" not in json.dumps(first.to_dict())
