from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

import market_platform.application.trading_signal as application_model
import market_platform.application.trading_signal_service as service_module
from market_platform.application import (
    ORDER_INTENT_APPLICATION_REQUEST_SCHEMA_VERSION,
    ORDER_INTENT_APPLICATION_RESPONSE_SCHEMA_VERSION,
    TRADING_SIGNAL_APPLICATION_REQUEST_SCHEMA_VERSION,
    TRADING_SIGNAL_APPLICATION_RESPONSE_SCHEMA_VERSION,
    CreateOrderIntentApplicationResponse,
    CreateOrderIntentApplicationService,
    CreateTradingSignalApplicationResponse,
    CreateTradingSignalApplicationService,
    OrderIntentApplicationRequest,
    TradingApplicationCorrespondenceError,
    TradingApplicationRequestError,
    TradingApplicationResourceLimitError,
    TradingInstrumentApplicationInput,
    TradingSignalApplicationInput,
    TradingSignalApplicationRequest,
    TradingSignalSourceApplicationInput,
    TradingTargetPositionApplicationInput,
    UnsupportedTradingApplicationSchemaError,
    decode_order_intent_application_request,
    decode_trading_signal_application_request,
)
from market_platform.trading import (
    TradingSignalExpiredError,
    TradingSignalNotYetValidError,
    TradingTargetPosition,
)

_START = datetime(2026, 7, 29, 14, 30, tzinfo=UTC)
_CONFIGURATION_FINGERPRINT = "sha256:" + ("a" * 64)


def _signal_input(
    *,
    source_id: str = "strategy.alpha",
    source_version: str = "1.2.3",
    source_event_id: str = "event-0001",
    symbol: str = "aapl",
    venue: str = "nasdaq",
    timeframe: str | None = "1m",
    position: TradingTargetPosition = TradingTargetPosition.LONG,
    units: Decimal = Decimal("100.00"),
    generated_at: datetime = _START,
    valid_from: datetime = _START,
    expires_at: datetime = _START + timedelta(minutes=5),
) -> TradingSignalApplicationInput:
    return TradingSignalApplicationInput(
        source=TradingSignalSourceApplicationInput(
            source_id=source_id,
            source_version=source_version,
            configuration_fingerprint=_CONFIGURATION_FINGERPRINT,
        ),
        source_event_id=source_event_id,
        instrument=TradingInstrumentApplicationInput(symbol=symbol, venue=venue),
        timeframe=timeframe,
        target=TradingTargetPositionApplicationInput(
            position=position,
            units=units,
        ),
        generated_at=generated_at,
        valid_from=valid_from,
        expires_at=expires_at,
    )


def _signal_request(**changes: object) -> TradingSignalApplicationRequest:
    return TradingSignalApplicationRequest(signal=_signal_input(**changes))


def _intent_request(
    *,
    decision_as_of: datetime = _START,
    **changes: object,
) -> OrderIntentApplicationRequest:
    return OrderIntentApplicationRequest(
        signal=_signal_input(**changes),
        decision_as_of=decision_as_of,
    )


def test_public_schemas_are_exact_and_responses_have_no_fingerprint() -> None:
    assert TRADING_SIGNAL_APPLICATION_REQUEST_SCHEMA_VERSION == (
        "trading_signal_application_request/v1"
    )
    assert TRADING_SIGNAL_APPLICATION_RESPONSE_SCHEMA_VERSION == (
        "trading_signal_application_response/v1"
    )
    assert ORDER_INTENT_APPLICATION_REQUEST_SCHEMA_VERSION == (
        "order_intent_application_request/v1"
    )
    assert ORDER_INTENT_APPLICATION_RESPONSE_SCHEMA_VERSION == (
        "order_intent_application_response/v1"
    )
    signal_response = CreateTradingSignalApplicationService().execute(_signal_request())
    intent_response = CreateOrderIntentApplicationService().execute(_intent_request())
    assert not hasattr(signal_response, "response_fingerprint")
    assert not hasattr(intent_response, "response_fingerprint")


@pytest.mark.parametrize(
    ("path", "field"),
    [
        ((), "unexpected"),
        (("signal",), "unexpected"),
        (("signal", "source"), "unexpected"),
        (("signal", "instrument"), "unexpected"),
        (("signal", "target"), "unexpected"),
    ],
)
def test_codec_rejects_unknown_fields_at_every_level(
    path: tuple[str, ...],
    field: str,
) -> None:
    payload = _signal_request().to_dict()
    target: dict[str, object] = payload
    for component in path:
        target = target[component]  # type: ignore[assignment]
    target[field] = "value"
    with pytest.raises(TradingApplicationRequestError, match="unknown fields"):
        decode_trading_signal_application_request(payload)


@pytest.mark.parametrize(
    ("path", "field"),
    [
        ((), "schema_version"),
        ((), "signal"),
        (("signal",), "source_event_id"),
        (("signal", "source"), "source_id"),
        (("signal", "instrument"), "symbol"),
        (("signal", "target"), "units"),
    ],
)
def test_codec_rejects_missing_fields(
    path: tuple[str, ...],
    field: str,
) -> None:
    payload = _signal_request().to_dict()
    target: dict[str, object] = payload
    for component in path:
        target = target[component]  # type: ignore[assignment]
    del target[field]
    with pytest.raises(TradingApplicationRequestError, match="missing fields"):
        decode_trading_signal_application_request(payload)


def test_codecs_reject_wrong_schema_and_non_mapping() -> None:
    payload = _signal_request().to_dict()
    payload["schema_version"] = "unsupported/v1"
    with pytest.raises(UnsupportedTradingApplicationSchemaError):
        decode_trading_signal_application_request(payload)
    with pytest.raises(TradingApplicationRequestError, match="object"):
        decode_trading_signal_application_request([])  # type: ignore[arg-type]
    intent = _intent_request().to_dict()
    intent["schema_version"] = "unsupported/v1"
    with pytest.raises(UnsupportedTradingApplicationSchemaError):
        decode_order_intent_application_request(intent)


def test_request_round_trips_are_canonical_and_json_safe() -> None:
    signal = _signal_request()
    intent = _intent_request()
    assert TradingSignalApplicationRequest.from_dict(signal.to_dict()) == signal
    assert OrderIntentApplicationRequest.from_dict(intent.to_dict()) == intent
    assert decode_trading_signal_application_request(signal.to_dict()) == signal
    assert decode_order_intent_application_request(intent.to_dict()) == intent
    json.dumps(signal.to_dict(), allow_nan=False)
    json.dumps(intent.to_dict(), allow_nan=False)


@pytest.mark.parametrize(
    "invalid",
    ["", " value", "value ", "a b", "a\tb", "a\nb", "a\rb", "a\0b", "é"],
)
def test_visible_ascii_policy_rejects_whitespace_controls_and_unicode(
    invalid: str,
) -> None:
    with pytest.raises(TradingApplicationRequestError):
        TradingSignalSourceApplicationInput(invalid, "1", None)


@pytest.mark.parametrize(
    ("field", "limit"),
    [
        ("source_id", 128),
        ("source_version", 64),
        ("source_event_id", 256),
        ("symbol", 64),
        ("venue", 32),
        ("timeframe", 32),
    ],
)
def test_string_limits_accept_boundary_and_reject_overage(
    field: str,
    limit: int,
) -> None:
    values: dict[str, object] = {
        "source_id": "s",
        "source_version": "v",
        "source_event_id": "e",
        "symbol": "A",
        "venue": "V",
        "timeframe": "1m",
    }
    values[field] = "x" * limit
    _signal_input(**values)
    values[field] = "x" * (limit + 1)
    with pytest.raises(TradingApplicationResourceLimitError, match="observed"):
        _signal_input(**values)


def test_instrument_normalizes_and_rejects_qualified_symbol() -> None:
    instrument = TradingInstrumentApplicationInput("brk.b", "nyse")
    assert instrument.to_dict() == {"symbol": "BRK.B", "venue": "NYSE"}
    with pytest.raises(TradingApplicationRequestError, match="venue prefix"):
        TradingInstrumentApplicationInput("NASDAQ:AAPL", "NASDAQ")


def test_qualified_symbol_is_rejected_before_domain_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_constructor(**kwargs: object) -> object:
        raise AssertionError(f"domain constructor called with {sorted(kwargs)}")

    monkeypatch.setattr(
        application_model,
        "TradingInstrumentIdentity",
        unexpected_constructor,
    )
    with pytest.raises(TradingApplicationRequestError, match="venue prefix"):
        TradingInstrumentApplicationInput("NASDAQ:AAPL", "NASDAQ")


@pytest.mark.parametrize(
    "error_type",
    [TypeError, ValueError, RuntimeError, AssertionError],
)
def test_unexpected_instrument_domain_failures_propagate(
    monkeypatch: pytest.MonkeyPatch,
    error_type: type[Exception],
) -> None:
    request = _signal_request()
    original_constructor = application_model.TradingInstrumentIdentity

    def failing_constructor(**kwargs: object) -> object:
        del kwargs
        raise error_type("injected domain defect")

    monkeypatch.setattr(
        application_model,
        "TradingInstrumentIdentity",
        failing_constructor,
    )
    with pytest.raises(error_type, match="injected domain defect"):
        TradingInstrumentApplicationInput("AAPL", "NASDAQ")

    monkeypatch.setattr(
        application_model,
        "TradingInstrumentIdentity",
        original_constructor,
    )
    monkeypatch.setattr(
        service_module,
        "TradingInstrumentIdentity",
        failing_constructor,
    )
    with pytest.raises(error_type, match="injected domain defect"):
        CreateTradingSignalApplicationService().execute(request)


@pytest.mark.parametrize(
    ("text", "canonical"),
    [
        ("0", "0"),
        ("0.0", "0"),
        ("1", "1"),
        ("1.25", "1.25"),
        ("0001.2500", "1.25"),
    ],
)
def test_decimal_codec_accepts_fixed_point_and_normalizes(
    text: str,
    canonical: str,
) -> None:
    payload = _signal_request(
        position=(
            TradingTargetPosition.FLAT
            if Decimal(text).is_zero()
            else TradingTargetPosition.LONG
        ),
        units=(Decimal("0") if Decimal(text).is_zero() else Decimal("1")),
    ).to_dict()
    signal = payload["signal"]
    assert isinstance(signal, dict)
    target = signal["target"]
    assert isinstance(target, dict)
    target["units"] = text
    decoded = decode_trading_signal_application_request(payload)
    assert decoded.signal.target.to_dict()["units"] == canonical


@pytest.mark.parametrize(
    "invalid",
    [
        1,
        1.0,
        True,
        Decimal("1"),
        "+1",
        "-1",
        "-0",
        "-0.0",
        "1E+3",
        "1e-3",
        " 1",
        "1 ",
        "1,000",
        ".5",
        "1.",
        "",
        "NaN",
        "Infinity",
    ],
)
def test_decimal_codec_rejects_non_fixed_point_values(invalid: object) -> None:
    payload = _signal_request().to_dict()
    signal = payload["signal"]
    assert isinstance(signal, dict)
    target = signal["target"]
    assert isinstance(target, dict)
    target["units"] = invalid
    with pytest.raises(TradingApplicationRequestError):
        decode_trading_signal_application_request(payload)


def test_decimal_resource_limits_are_exact() -> None:
    for accepted in ("9" * 128, "0." + ("0" * 63) + "1"):
        payload = _signal_request().to_dict()
        payload["signal"]["target"]["units"] = accepted  # type: ignore[index]
        decode_trading_signal_application_request(payload)
    for rejected in (
        "9" * 129,
        "0." + ("0" * 64) + "1",
        "0" * 257,
    ):
        payload = _signal_request().to_dict()
        payload["signal"]["target"]["units"] = rejected  # type: ignore[index]
        with pytest.raises(TradingApplicationResourceLimitError):
            decode_trading_signal_application_request(payload)


@pytest.mark.parametrize(
    "value",
    [
        Decimal("1E+1000000"),
        Decimal("1E-1000000"),
        Decimal("9.99E+1000000"),
        Decimal("9.99E-1000000"),
    ],
)
def test_direct_decimal_rejects_projected_oversize_before_formatting(
    monkeypatch: pytest.MonkeyPatch,
    value: Decimal,
) -> None:
    def unexpected_format(candidate: Decimal) -> str:
        raise AssertionError(f"formatted rejected Decimal {candidate.as_tuple()}")

    monkeypatch.setattr(
        application_model,
        "_fixed_point_decimal_text",
        unexpected_format,
    )
    with pytest.raises(TradingApplicationResourceLimitError, match="observed"):
        TradingTargetPositionApplicationInput(TradingTargetPosition.LONG, value)


def test_direct_decimal_projection_boundaries_are_exact() -> None:
    projections = {
        Decimal("9" * 128): (128, 0, 128),
        Decimal("9" * 129): (129, 0, 129),
        Decimal("1E-64"): (65, 64, 66),
        Decimal("1E-65"): (66, 65, 67),
        Decimal("1E-254"): (255, 254, 256),
        Decimal("1E-255"): (256, 255, 257),
    }
    for value, projected in projections.items():
        assert application_model._project_canonical_decimal_size(value) == projected

    accepted_integer = TradingTargetPositionApplicationInput(
        TradingTargetPosition.LONG,
        Decimal("9" * 128),
    )
    accepted_fraction = TradingTargetPositionApplicationInput(
        TradingTargetPosition.LONG,
        Decimal("1E-64"),
    )
    assert accepted_integer.to_dict()["units"] == "9" * 128
    assert accepted_fraction.to_dict()["units"] == "0." + ("0" * 63) + "1"
    for rejected in (Decimal("9" * 129), Decimal("1E-65")):
        with pytest.raises(TradingApplicationResourceLimitError):
            TradingTargetPositionApplicationInput(
                TradingTargetPosition.LONG,
                rejected,
            )


def test_direct_decimal_huge_exponent_zero_is_safe_and_canonical(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_format(candidate: Decimal) -> str:
        raise AssertionError(f"formatted zero Decimal {candidate.as_tuple()}")

    monkeypatch.setattr(
        application_model,
        "_fixed_point_decimal_text",
        unexpected_format,
    )
    for value in (Decimal("0E+1000000"), Decimal("0E-1000000")):
        target = TradingTargetPositionApplicationInput(
            TradingTargetPosition.FLAT,
            value,
        )
        assert target.units.as_tuple() == Decimal("0").as_tuple()
        assert target.to_dict()["units"] == "0"
    for value in (Decimal("-0E+1000000"), Decimal("-0E-1000000")):
        with pytest.raises(TradingApplicationRequestError, match="negative zero"):
            TradingTargetPositionApplicationInput(TradingTargetPosition.FLAT, value)


def test_equivalent_decimal_syntax_has_one_request_identity() -> None:
    payloads = []
    for text in ("1", "1.0", "01.00", "0001.0000"):
        payload = _signal_request(units=Decimal("1")).to_dict()
        payload["signal"]["target"]["units"] = text  # type: ignore[index]
        payloads.append(decode_trading_signal_application_request(payload))
    assert len({request.request_fingerprint for request in payloads}) == 1
    assert {request.to_dict()["signal"]["target"]["units"] for request in payloads} == {
        "1"
    }  # type: ignore[index]


@pytest.mark.parametrize(
    "text",
    [
        "2026-07-29T14:30:00Z",
        "2026-07-29T14:30:00.1Z",
        "2026-07-29T14:30:00.123456+00:00",
        "2026-07-29T22:30:00+08:00",
        "2026-07-29T09:30:00-05:00",
    ],
)
def test_timestamp_codec_accepts_strict_aware_forms(text: str) -> None:
    payload = _signal_request().to_dict()
    payload["signal"]["generated_at"] = text  # type: ignore[index]
    payload["signal"]["valid_from"] = text  # type: ignore[index]
    decoded = decode_trading_signal_application_request(payload)
    assert decoded.signal.generated_at.tzinfo is UTC


@pytest.mark.parametrize(
    "invalid",
    [
        "2026-07-29T14:30:00",
        "2026-07-29 14:30:00Z",
        "2026-07-29T14:30:00z",
        "2026-07-29T14:30:00.1234567Z",
        "2026-07-29T14:30:00UTC",
        "2026-07-29T14:30:00+8:00",
        1,
        datetime(2026, 7, 29, 14, 30),
    ],
)
def test_timestamp_codec_rejects_non_strict_values(invalid: object) -> None:
    payload = _signal_request().to_dict()
    payload["signal"]["generated_at"] = invalid  # type: ignore[index]
    with pytest.raises(TradingApplicationRequestError):
        decode_trading_signal_application_request(payload)


@pytest.mark.parametrize(
    "invalid",
    [
        "2026-07-29T14:30:00+24:00",
        "2026-07-29T14:30:00-24:00",
        "2026-07-29T14:30:00+99:99",
        "2026-07-29T14:30:00-99:99",
        "2026-07-29T14:30:00+12:60",
        "2026-07-29T14:30:00-12:60",
        "2026-07-29T14:30:00+00:60",
        "2026-07-29T14:30:00-00:60",
        "2026-07-29T14:30:00-00:00",
        "2026-07-29T14:30:00.123456-00:00",
    ],
)
def test_timestamp_codec_rejects_invalid_or_unknown_offsets(invalid: str) -> None:
    payload = _signal_request().to_dict()
    payload["signal"]["generated_at"] = invalid  # type: ignore[index]
    with pytest.raises(TradingApplicationRequestError, match="offset|timestamp"):
        decode_trading_signal_application_request(payload)


@pytest.mark.parametrize(
    ("generated_at", "expires_at"),
    [
        ("2026-07-30T14:29:00+23:59", "2026-07-30T14:34:00+23:59"),
        ("2026-07-28T14:31:00-23:59", "2026-07-28T14:36:00-23:59"),
    ],
)
def test_timestamp_codec_accepts_boundary_known_offsets(
    generated_at: str,
    expires_at: str,
) -> None:
    payload = _signal_request().to_dict()
    payload["signal"]["generated_at"] = generated_at  # type: ignore[index]
    payload["signal"]["valid_from"] = generated_at  # type: ignore[index]
    payload["signal"]["expires_at"] = expires_at  # type: ignore[index]
    decoded = decode_trading_signal_application_request(payload)
    assert decoded.signal.generated_at == _START
    assert decoded.signal.expires_at == _START + timedelta(minutes=5)


def test_timestamp_text_limit_precedes_parsing() -> None:
    payload = _signal_request().to_dict()
    payload["signal"]["generated_at"] = "2" * 65  # type: ignore[index]
    with pytest.raises(TradingApplicationResourceLimitError, match="limit 64"):
        decode_trading_signal_application_request(payload)


def test_offset_equivalent_timestamps_have_one_request_identity() -> None:
    utc_payload = _signal_request().to_dict()
    offset_payload = deepcopy(utc_payload)
    offset_payload["signal"]["generated_at"] = "2026-07-29T22:30:00+08:00"  # type: ignore[index]
    offset_payload["signal"]["valid_from"] = "2026-07-29T22:30:00+08:00"  # type: ignore[index]
    offset_payload["signal"]["expires_at"] = "2026-07-29T22:35:00+08:00"  # type: ignore[index]
    left = decode_trading_signal_application_request(utc_payload)
    right = decode_trading_signal_application_request(offset_payload)
    assert left == right
    assert left.request_fingerprint == right.request_fingerprint
    assert right.to_dict()["signal"]["generated_at"].endswith("+00:00")  # type: ignore[index,union-attr]


def test_direct_constructor_and_codec_have_semantic_parity() -> None:
    offset = timezone(timedelta(hours=8))
    direct = _signal_request(
        units=Decimal("1.00"),
        generated_at=_START.astimezone(offset),
        valid_from=_START.astimezone(offset),
        expires_at=(_START + timedelta(minutes=5)).astimezone(offset),
    )
    decoded = decode_trading_signal_application_request(direct.to_dict())
    assert decoded == direct
    assert decoded.request_fingerprint == direct.request_fingerprint
    with pytest.raises(TradingApplicationRequestError, match="Decimal"):
        TradingTargetPositionApplicationInput(TradingTargetPosition.LONG, "1")  # type: ignore[arg-type]
    with pytest.raises(TradingApplicationRequestError, match="timezone-aware"):
        replace(_signal_input(), generated_at=datetime(2026, 7, 29, 14, 30))


def test_signal_service_constructs_exact_domain_signal_and_bounded_response() -> None:
    request = _signal_request()
    response = CreateTradingSignalApplicationService().execute(request)
    assert response.request_fingerprint == request.request_fingerprint
    assert response.signal.source.source_id == request.signal.source.source_id
    assert response.signal.instrument.symbol == request.signal.instrument.symbol
    assert response.signal.target_units == request.signal.target.units
    assert response.signal.generated_at == request.signal.generated_at
    assert request.request_fingerprint not in {
        response.signal.idempotency_key,
        response.signal.signal_fingerprint,
    }
    payload = response.to_dict()
    json.dumps(payload, allow_nan=False)
    assert (
        payload["schema_version"] == TRADING_SIGNAL_APPLICATION_RESPONSE_SCHEMA_VERSION
    )


def test_intent_service_constructs_exact_pre_risk_intent() -> None:
    request = _intent_request(decision_as_of=_START + timedelta(minutes=1))
    response = CreateOrderIntentApplicationService().execute(request)
    intent = response.intent
    assert intent.source_signal.source_event_id == request.signal.source_event_id
    assert intent.decision_as_of == request.decision_as_of
    assert intent.valid_from == request.decision_as_of
    assert intent.expires_at == request.signal.expires_at
    assert intent.target_units == request.signal.target.units
    payload = response.to_dict()
    json.dumps(payload, allow_nan=False)
    assert payload["schema_version"] == ORDER_INTENT_APPLICATION_RESPONSE_SCHEMA_VERSION


def test_intent_service_preserves_temporal_domain_errors() -> None:
    early = _intent_request(decision_as_of=_START - timedelta(microseconds=1))
    expired = _intent_request(decision_as_of=_START + timedelta(minutes=5))
    with pytest.raises(TradingSignalNotYetValidError):
        CreateOrderIntentApplicationService().execute(early)
    with pytest.raises(TradingSignalExpiredError):
        CreateOrderIntentApplicationService().execute(expired)


def test_services_runtime_check_request_types() -> None:
    with pytest.raises(TypeError, match="TradingSignalApplicationRequest"):
        CreateTradingSignalApplicationService().execute(None)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="OrderIntentApplicationRequest"):
        CreateOrderIntentApplicationService().execute(None)  # type: ignore[arg-type]


def test_signal_service_constructs_one_signal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    original_signal = service_module._create_signal

    def signal_wrapper(value: TradingSignalApplicationInput):
        nonlocal calls
        calls += 1
        return original_signal(value)

    monkeypatch.setattr(service_module, "_create_signal", signal_wrapper)
    CreateTradingSignalApplicationService().execute(_signal_request())
    assert calls == 1


def test_intent_service_calls_signal_policy_and_conversion_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    counts = {"signal": 0, "policy": 0, "intent": 0}
    original_signal = service_module._create_signal
    original_policy = service_module.ExactTargetPositionIntentPolicy
    original_intent = service_module.create_order_intent_from_signal

    def signal_wrapper(value: TradingSignalApplicationInput):
        counts["signal"] += 1
        return original_signal(value)

    def policy_wrapper():
        counts["policy"] += 1
        return original_policy()

    def intent_wrapper(*args: object):
        counts["intent"] += 1
        return original_intent(*args)  # type: ignore[arg-type]

    monkeypatch.setattr(service_module, "_create_signal", signal_wrapper)
    monkeypatch.setattr(
        service_module, "ExactTargetPositionIntentPolicy", policy_wrapper
    )
    monkeypatch.setattr(
        service_module, "create_order_intent_from_signal", intent_wrapper
    )
    CreateOrderIntentApplicationService().execute(_intent_request())
    assert counts == {"signal": 1, "policy": 1, "intent": 1}


def test_response_factories_reject_unrelated_domain_objects() -> None:
    request_a = _signal_request(source_event_id="event-a")
    signal_b = (
        CreateTradingSignalApplicationService()
        .execute(_signal_request(source_event_id="event-b"))
        .signal
    )
    with pytest.raises(TradingApplicationCorrespondenceError):
        CreateTradingSignalApplicationResponse._create(request_a, signal_b)

    intent_request_a = _intent_request(source_event_id="event-a")
    intent_b = (
        CreateOrderIntentApplicationService()
        .execute(_intent_request(source_event_id="event-b"))
        .intent
    )
    with pytest.raises(TradingApplicationCorrespondenceError):
        CreateOrderIntentApplicationResponse._create(intent_request_a, intent_b)


def test_response_factory_rejects_fabricated_intent_identity() -> None:
    request = _intent_request()
    intent = CreateOrderIntentApplicationService().execute(request).intent
    object.__setattr__(intent, "intent_fingerprint", "sha256:" + ("0" * 64))
    with pytest.raises(TradingApplicationCorrespondenceError):
        CreateOrderIntentApplicationResponse._create(request, intent)


@pytest.mark.parametrize(
    ("canonical", "fabricated"),
    [
        (Decimal("100"), Decimal("100.0")),
        (Decimal("100"), Decimal("100.00")),
        (Decimal("100"), Decimal("1E+2")),
        (Decimal("1.25"), Decimal("1.250")),
        (Decimal("0"), Decimal("0.0")),
        (Decimal("0"), Decimal("0E+10")),
    ],
)
def test_signal_response_rejects_noncanonical_domain_units(
    canonical: Decimal,
    fabricated: Decimal,
) -> None:
    position = (
        TradingTargetPosition.FLAT
        if canonical.is_zero()
        else TradingTargetPosition.LONG
    )
    request = _signal_request(position=position, units=canonical)
    signal = CreateTradingSignalApplicationService().execute(request).signal
    object.__setattr__(signal, "target_units", fabricated)
    with pytest.raises(TradingApplicationCorrespondenceError, match="canonical"):
        CreateTradingSignalApplicationResponse._create(request, signal)


@pytest.mark.parametrize(
    ("canonical", "fabricated"),
    [
        (Decimal("100"), Decimal("100.0")),
        (Decimal("100"), Decimal("1E+2")),
        (Decimal("1.25"), Decimal("1.250")),
        (Decimal("0"), Decimal("0.0")),
        (Decimal("0"), Decimal("0E+10")),
    ],
)
def test_intent_response_rejects_noncanonical_source_or_intent_units(
    monkeypatch: pytest.MonkeyPatch,
    canonical: Decimal,
    fabricated: Decimal,
) -> None:
    position = (
        TradingTargetPosition.FLAT
        if canonical.is_zero()
        else TradingTargetPosition.LONG
    )

    source_request = _intent_request(position=position, units=canonical)
    source_intent = CreateOrderIntentApplicationService().execute(source_request).intent
    object.__setattr__(source_intent.source_signal, "target_units", fabricated)
    with pytest.raises(TradingApplicationCorrespondenceError, match="canonical"):
        CreateOrderIntentApplicationResponse._create(source_request, source_intent)

    intent_request = _intent_request(position=position, units=canonical)
    intent = CreateOrderIntentApplicationService().execute(intent_request).intent
    monkeypatch.setattr(
        type(intent),
        "target_units",
        property(lambda instance: fabricated),
    )
    with pytest.raises(TradingApplicationCorrespondenceError, match="canonical"):
        CreateOrderIntentApplicationResponse._create(intent_request, intent)


def test_response_factories_reject_fabricated_request_identity_and_state() -> None:
    request = _signal_request()
    signal = CreateTradingSignalApplicationService().execute(request).signal
    object.__setattr__(request, "request_fingerprint", "sha256:" + ("0" * 64))
    with pytest.raises(TradingApplicationCorrespondenceError):
        CreateTradingSignalApplicationResponse._create(request, signal)

    intent_request = _intent_request()
    intent = CreateOrderIntentApplicationService().execute(intent_request).intent
    offset = timezone(timedelta(hours=8))
    object.__setattr__(
        intent_request,
        "decision_as_of",
        intent_request.decision_as_of.astimezone(offset),
    )
    with pytest.raises(TradingApplicationCorrespondenceError):
        CreateOrderIntentApplicationResponse._create(intent_request, intent)


def test_responses_are_factory_only_bounded_and_exclude_forbidden_fields() -> None:
    with pytest.raises(TypeError, match="Service.execute"):
        CreateTradingSignalApplicationResponse()
    with pytest.raises(TypeError, match="Service.execute"):
        CreateOrderIntentApplicationResponse()
    signal_response = CreateTradingSignalApplicationService().execute(_signal_request())
    intent_response = CreateOrderIntentApplicationService().execute(_intent_request())
    assert "source_event_id" not in repr(signal_response)
    assert "source_event_id" not in repr(intent_response)
    rendered = json.dumps(
        {"signal": signal_response.to_dict(), "intent": intent_response.to_dict()}
    ).lower()
    for forbidden in (
        "tradingview",
        "credential",
        "account",
        "risk",
        "broker",
        "response_fingerprint",
        "raw_request",
    ):
        assert forbidden not in rendered


def test_request_shapes_have_no_derived_or_arbitrary_fields() -> None:
    fields = json.dumps(_intent_request().to_dict()).lower()
    for forbidden in (
        "idempotency_key",
        "source_fingerprint",
        "instrument_fingerprint",
        "signal_fingerprint",
        "policy_fingerprint",
        "intent_fingerprint",
        "metadata",
        "price",
    ):
        assert forbidden not in fields
