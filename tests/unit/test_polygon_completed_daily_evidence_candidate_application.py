from __future__ import annotations

import ast
import asyncio
import inspect
from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

import market_platform.application.polygon_completed_daily_evidence_candidate as app
import market_platform.data.factory as data_factory
from market_platform.application import (
    PolygonCompletedDailyAcquirer,
    PolygonCompletedDailyEvidenceCandidateApplicationRequest,
    PolygonCompletedDailyEvidenceCandidateApplicationService,
)
from market_platform.data import DataProviderError
from market_platform.data.providers.polygon import (
    PolygonCompletedDailyAcquisition,
    PolygonProvider,
)
from market_platform.instruments import (
    CanonicalInstrument,
    CanonicalInstrumentId,
    ExternalInstrumentIdentity,
    InstrumentAssetClass,
    InstrumentMapping,
    InstrumentMappingAmbiguousError,
    InstrumentMappingConflictError,
    InstrumentMappingDuplicateError,
    InstrumentMappingInactiveError,
    InstrumentMappingNotFoundError,
    InstrumentMappingSourceIdentity,
)
from market_platform.trading import TradingInstrumentIdentity

_QUERY = datetime(2026, 8, 24, 10, tzinfo=UTC)
_RECEIVED = datetime(2026, 8, 24, 12, tzinfo=UTC)
_CREATED = datetime(2026, 8, 24, 13, tzinfo=UTC)


def _external(symbol: str = "AAPL") -> ExternalInstrumentIdentity:
    return ExternalInstrumentIdentity("polygon", symbol, "NASDAQ")


def _canonical(
    symbol: str = "AAPL", *, instrument_id: str | None = None
) -> CanonicalInstrument:
    return CanonicalInstrument(
        CanonicalInstrumentId(instrument_id or f"us_equity.{symbol}"),
        TradingInstrumentIdentity(symbol, "NASDAQ"),
        InstrumentAssetClass.EQUITY,
        "USD",
    )


def _mapping(
    *,
    external: ExternalInstrumentIdentity | None = None,
    canonical: CanonicalInstrument | None = None,
    source_id: str = "operator_registry",
    valid_from: datetime = datetime(2020, 1, 1, tzinfo=UTC),
    expires_at: datetime | None = None,
) -> InstrumentMapping:
    return InstrumentMapping(
        external or _external(),
        canonical or _canonical(),
        InstrumentMappingSourceIdentity(source_id, "1.0.0"),
        valid_from,
        expires_at,
    )


def _acquisition() -> PolygonCompletedDailyAcquisition:
    return PolygonCompletedDailyAcquisition(
        requested_ticker="AAPL",
        requested_from="2026-08-20",
        requested_to="2026-08-24",
        response_ticker_is_present=True,
        response_ticker="AAPL",
        response_adjusted_is_present=True,
        response_adjusted=True,
        request_id_is_present=True,
        request_id="request-123",
        query_count_is_present=True,
        query_count=0,
        results_count_is_present=True,
        results_count=0,
        count_is_present=True,
        count=0,
        next_url_is_present=False,
        next_page_reference=None,
        results_is_present=True,
        rows=(),
        response_received_at=_RECEIVED,
    )


def _request(
    *,
    external: ExternalInstrumentIdentity | None = None,
    mappings: tuple[InstrumentMapping, ...] | None = None,
    query_as_of: datetime = _QUERY,
) -> PolygonCompletedDailyEvidenceCandidateApplicationRequest:
    return PolygonCompletedDailyEvidenceCandidateApplicationRequest(
        external_identity=external or _external(),
        mappings=(_mapping(),) if mappings is None else mappings,
        requested_from=date(2026, 8, 20),
        requested_to=date(2026, 8, 24),
        query_as_of=query_as_of,
    )


class _Acquirer:
    def __init__(
        self,
        result: PolygonCompletedDailyAcquisition | None = None,
        failure: Exception | None = None,
        events: list[str] | None = None,
    ) -> None:
        self.result = result or _acquisition()
        self.failure = failure
        self.calls: list[tuple[str, date, date]] = []
        self.events = [] if events is None else events

    async def get_completed_daily_acquisition(
        self, ticker: str, start: date, end: date
    ) -> PolygonCompletedDailyAcquisition:
        self.calls.append((ticker, start, end))
        self.events.append("acquire")
        if self.failure is not None:
            raise self.failure
        return self.result


def test_request_is_frozen_slotted_exact_and_normalizes_query_time() -> None:
    external = _external()
    mappings = (_mapping(),)
    request = _request(
        external=external,
        mappings=mappings,
        query_as_of=datetime(2026, 8, 24, 18, tzinfo=timezone(timedelta(hours=8))),
    )

    assert request.external_identity is external
    assert request.mappings is mappings
    assert request.mappings[0] is mappings[0]
    assert request.query_as_of == _QUERY
    assert request.query_as_of.tzinfo is UTC
    assert not hasattr(request, "__dict__")
    with pytest.raises(FrozenInstanceError):
        request.requested_from = date(2026, 8, 19)  # type: ignore[misc]


@pytest.mark.parametrize(
    ("changes", "error"),
    (
        (
            {
                "requested_from": date(2026, 8, 25),
                "requested_to": date(2026, 8, 24),
            },
            ValueError,
        ),
        ({"query_as_of": datetime(2026, 8, 24, 10)}, ValueError),
        ({"requested_from": datetime(2026, 8, 20, tzinfo=UTC)}, TypeError),
        ({"mappings": [_mapping()]}, TypeError),
    ),
)
def test_request_rejects_invalid_exact_inputs(
    changes: dict[str, object], error: type[Exception]
) -> None:
    values: dict[str, object] = {
        "external_identity": _external(),
        "mappings": (_mapping(),),
        "requested_from": date(2026, 8, 20),
        "requested_to": date(2026, 8, 24),
        "query_as_of": _QUERY,
    }
    values.update(changes)
    with pytest.raises(error):
        PolygonCompletedDailyEvidenceCandidateApplicationRequest(  # type: ignore[arg-type]
            **values
        )


@pytest.mark.parametrize(
    ("mappings", "error"),
    (
        ((_mapping(external=_external("MSFT")),), InstrumentMappingNotFoundError),
        (
            (_mapping(expires_at=datetime(2025, 1, 1, tzinfo=UTC)),),
            InstrumentMappingInactiveError,
        ),
        (
            (
                _mapping(source_id="registry_a"),
                _mapping(source_id="registry_b"),
            ),
            InstrumentMappingAmbiguousError,
        ),
        (
            (
                _mapping(source_id="registry_a"),
                _mapping(
                    canonical=_canonical(instrument_id="us_equity.aapl_alt"),
                    source_id="registry_b",
                ),
            ),
            InstrumentMappingConflictError,
        ),
        ((lambda item: (item, item))(_mapping()), InstrumentMappingDuplicateError),
    ),
)
def test_mapping_preflight_failures_stop_before_provider_clock_and_ingress(
    mappings: tuple[InstrumentMapping, ...],
    error: type[Exception],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    acquirer = _Acquirer()
    clock_calls: list[str] = []
    ingress_calls: list[str] = []
    monkeypatch.setattr(
        app,
        "create_polygon_completed_daily_ohlcv_evidence",
        lambda **kwargs: ingress_calls.append("ingress"),
    )
    service = PolygonCompletedDailyEvidenceCandidateApplicationService(
        acquirer,
        lambda: clock_calls.append("clock") or _CREATED,
    )

    with pytest.raises(error):
        asyncio.run(service.execute(_request(mappings=mappings)))

    assert acquirer.calls == []
    assert clock_calls == []
    assert ingress_calls == []


def test_exact_order_and_values_flow_to_ingress_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    acquirer = _Acquirer(events=events)
    request = _request()
    expected_result = object()
    ingress_calls: list[dict[str, object]] = []
    original_resolve = app.resolve_instrument_mapping

    def resolve(*args: object, **kwargs: object) -> object:
        events.append("preflight")
        return original_resolve(*args, **kwargs)  # type: ignore[arg-type]

    def clock() -> datetime:
        events.append("clock")
        return _CREATED

    def ingress(**kwargs: object) -> object:
        events.append("ingress")
        ingress_calls.append(kwargs)
        return expected_result

    monkeypatch.setattr(app, "resolve_instrument_mapping", resolve)
    monkeypatch.setattr(app, "create_polygon_completed_daily_ohlcv_evidence", ingress)

    result = asyncio.run(
        PolygonCompletedDailyEvidenceCandidateApplicationService(
            acquirer, clock
        ).execute(request)
    )

    assert result is expected_result
    assert events == ["preflight", "acquire", "clock", "ingress"]
    assert acquirer.calls == [("AAPL", date(2026, 8, 20), date(2026, 8, 24))]
    assert ingress_calls == [
        {
            "acquisition": acquirer.result,
            "external_identity": request.external_identity,
            "mappings": request.mappings,
            "query_as_of": request.query_as_of,
            "artifact_created_at": _CREATED,
        }
    ]


def test_provider_failure_stops_clock_and_ingress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    acquirer = _Acquirer(failure=DataProviderError("controlled"))
    clock_calls: list[str] = []
    ingress_calls: list[str] = []
    monkeypatch.setattr(
        app,
        "create_polygon_completed_daily_ohlcv_evidence",
        lambda **kwargs: ingress_calls.append("ingress"),
    )
    service = PolygonCompletedDailyEvidenceCandidateApplicationService(
        acquirer,
        lambda: clock_calls.append("clock") or _CREATED,
    )

    with pytest.raises(DataProviderError, match="controlled"):
        asyncio.run(service.execute(_request()))

    assert len(acquirer.calls) == 1
    assert clock_calls == []
    assert ingress_calls == []


def test_retained_request_validation_failure_stops_all_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _request()
    object.__setattr__(request, "requested_from", date(2026, 8, 25))
    acquirer = _Acquirer()
    clock_calls: list[str] = []
    ingress_calls: list[str] = []
    monkeypatch.setattr(
        app,
        "create_polygon_completed_daily_ohlcv_evidence",
        lambda **kwargs: ingress_calls.append("ingress"),
    )
    service = PolygonCompletedDailyEvidenceCandidateApplicationService(
        acquirer,
        lambda: clock_calls.append("clock") or _CREATED,
    )

    with pytest.raises(ValueError, match="requested_from"):
        asyncio.run(service.execute(request))

    assert acquirer.calls == []
    assert clock_calls == []
    assert ingress_calls == []


def test_ingress_failure_propagates_after_one_acquisition_and_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    acquirer = _Acquirer()
    clock_calls: list[str] = []
    ingress_calls: list[str] = []

    def fail_ingress(**kwargs: object) -> object:
        ingress_calls.append("ingress")
        raise ValueError("controlled ingress failure")

    monkeypatch.setattr(
        app, "create_polygon_completed_daily_ohlcv_evidence", fail_ingress
    )
    service = PolygonCompletedDailyEvidenceCandidateApplicationService(
        acquirer,
        lambda: clock_calls.append("clock") or _CREATED,
    )

    with pytest.raises(ValueError, match="controlled ingress failure"):
        asyncio.run(service.execute(_request()))

    assert len(acquirer.calls) == 1
    assert clock_calls == ["clock"]
    assert ingress_calls == ["ingress"]


def test_narrow_protocol_and_service_have_no_selection_or_fallback_surface() -> None:
    assert isinstance(_Acquirer(), PolygonCompletedDailyAcquirer)
    parameters = inspect.signature(
        PolygonCompletedDailyAcquirer.get_completed_daily_acquisition
    ).parameters
    assert tuple(parameters) == ("self", "ticker", "start", "end")
    service_parameters = inspect.signature(
        PolygonCompletedDailyEvidenceCandidateApplicationService
    ).parameters
    assert tuple(service_parameters) == ("acquirer", "creation_clock")


def test_application_module_has_no_later_lifecycle_or_research_dependencies() -> None:
    path = Path(app.__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    imported_modules.update(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    forbidden_modules = {
        "market_platform.evidence.admission",
        "market_platform.evidence.evaluation",
        "market_platform.evidence.temporal",
        "market_platform.evidence.validation",
        "market_platform.research",
        "market_platform.agent_exposure",
    }
    assert imported_modules.isdisjoint(forbidden_modules)
    imported_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    forbidden_names = {
        "CompletedDailyPriceSeries",
        "evaluate_evidence_admission_as_of",
        "create_evidence_validation_record",
        "create_evidence_admission_record",
    }
    assert forbidden_names.isdisjoint(imported_names | called_names)


def test_create_polygon_provider_wires_settings_and_standard_http_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = object()
    registry_calls: list[str] = []
    monkeypatch.setattr(
        data_factory,
        "get_settings",
        lambda: SimpleNamespace(polygon_api_key="configured-key"),
    )
    monkeypatch.setattr(data_factory, "create_http_client", lambda: client)
    monkeypatch.setattr(
        data_factory,
        "create_default_registry",
        lambda: registry_calls.append("registry"),
    )

    provider = data_factory.create_polygon_provider()

    assert type(provider) is PolygonProvider
    assert provider.api_key == "configured-key"
    assert provider.http_client is client
    assert registry_calls == []
    assert (
        tuple(inspect.signature(data_factory.create_polygon_provider).parameters) == ()
    )


def test_application_package_exports_only_the_narrow_new_surface() -> None:
    import market_platform.application as application

    expected = {
        "PolygonCompletedDailyAcquirer",
        "PolygonCompletedDailyEvidenceCandidateApplicationRequest",
        "PolygonCompletedDailyEvidenceCandidateApplicationService",
    }
    assert expected <= set(application.__all__)
    assert "PolygonCompletedDailyOhlcvEvidenceIngressResult" not in application.__all__
    assert cast(object, application.PolygonCompletedDailyAcquirer) is (
        PolygonCompletedDailyAcquirer
    )
