from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from decimal import Decimal, localcontext

import pytest

from market_platform.signals.models import MarketSignal
from market_platform.trading import (
    EXACT_TARGET_POSITION_INTENT_POLICY_SCHEMA_VERSION,
    ORDER_INTENT_SCHEMA_VERSION,
    TRADING_INSTRUMENT_IDENTITY_SCHEMA_VERSION,
    TRADING_SIGNAL_SCHEMA_VERSION,
    TRADING_SIGNAL_SOURCE_SCHEMA_VERSION,
    ExactTargetPositionIntentPolicy,
    OrderIntent,
    TradingInstrumentIdentity,
    TradingSignal,
    TradingSignalEventConsistency,
    TradingSignalExpiredError,
    TradingSignalNotYetValidError,
    TradingSignalSourceIdentity,
    TradingSignalTemporalStatus,
    TradingTargetPosition,
    compare_trading_signal_event_consistency,
    create_order_intent_from_signal,
    evaluate_trading_signal_temporal_status,
)

_START = datetime(2026, 7, 29, 14, 30, tzinfo=UTC)
_CONFIGURATION_FINGERPRINT = "sha256:" + ("a" * 64)


class _NoOffsetTimezone(tzinfo):
    def utcoffset(self, dt: datetime | None) -> None:
        return None

    def dst(self, dt: datetime | None) -> None:
        return None

    def tzname(self, dt: datetime | None) -> str:
        return "NO_OFFSET"


def _source(
    *,
    source_id: str = "trend-system",
    source_version: str = "1.0.0",
    configuration_fingerprint: str | None = _CONFIGURATION_FINGERPRINT,
) -> TradingSignalSourceIdentity:
    return TradingSignalSourceIdentity(
        source_id=source_id,
        source_version=source_version,
        configuration_fingerprint=configuration_fingerprint,
    )


def _instrument(
    *,
    symbol: str = "AAPL",
    venue: str = "NASDAQ",
) -> TradingInstrumentIdentity:
    return TradingInstrumentIdentity(symbol=symbol, venue=venue)


def _signal(
    *,
    source: TradingSignalSourceIdentity | None = None,
    source_event_id: str = "event-001",
    instrument: TradingInstrumentIdentity | None = None,
    timeframe: str | None = "5min",
    target_position: TradingTargetPosition = TradingTargetPosition.LONG,
    target_units: Decimal = Decimal("100"),
    generated_at: datetime = _START,
    valid_from: datetime = _START,
    expires_at: datetime = _START + timedelta(minutes=5),
) -> TradingSignal:
    return TradingSignal(
        source=source or _source(),
        source_event_id=source_event_id,
        instrument=instrument or _instrument(),
        timeframe=timeframe,
        target_position=target_position,
        target_units=target_units,
        generated_at=generated_at,
        valid_from=valid_from,
        expires_at=expires_at,
    )


def test_public_schemas_are_exact() -> None:
    assert (
        TRADING_INSTRUMENT_IDENTITY_SCHEMA_VERSION == "trading_instrument_identity/v1"
    )
    assert TRADING_SIGNAL_SOURCE_SCHEMA_VERSION == "trading_signal_source/v1"
    assert TRADING_SIGNAL_SCHEMA_VERSION == "trading_signal/v1"
    assert (
        EXACT_TARGET_POSITION_INTENT_POLICY_SCHEMA_VERSION
        == "exact_target_position_intent_policy/v1"
    )
    assert ORDER_INTENT_SCHEMA_VERSION == "order_intent/v1"


@pytest.mark.parametrize("symbol", ["BRK.B", "BTC-USDT", "BTC/USDT", "ES1!"])
def test_instrument_normalizes_identity_and_allows_common_punctuation(
    symbol: str,
) -> None:
    instrument = TradingInstrumentIdentity(
        symbol=f" {symbol.lower()} ",
        venue=" nasdaq ",
    )

    assert instrument.symbol == symbol
    assert instrument.venue == "NASDAQ"
    assert instrument == TradingInstrumentIdentity(symbol=symbol, venue="NASDAQ")
    assert instrument.to_dict()["schema_version"] == ("trading_instrument_identity/v1")


@pytest.mark.parametrize(
    ("symbol", "venue", "error"),
    [
        (" ", "NASDAQ", "symbol must not be empty"),
        ("AAPL", " ", "venue must not be empty"),
        ("NASDAQ:AAPL", "NASDAQ", "provide venue separately"),
        ("BINANCE:BTCUSDT", "BINANCE", "provide venue separately"),
    ],
)
def test_instrument_rejects_empty_and_external_qualified_symbols(
    symbol: str,
    venue: str,
    error: str,
) -> None:
    with pytest.raises(ValueError, match=error):
        TradingInstrumentIdentity(symbol=symbol, venue=venue)


def test_instrument_projection_is_deterministic_and_json_safe() -> None:
    instrument = _instrument()

    assert instrument.instrument_fingerprint.startswith("sha256:")
    assert instrument.to_dict() == instrument.to_dict()
    json.dumps(instrument.to_dict(), allow_nan=False)
    assert "tradingview" not in json.dumps(instrument.to_dict()).lower()


def test_source_identity_is_deterministic_and_configuration_sensitive() -> None:
    source = _source()
    repeated = _source()
    changed = _source(configuration_fingerprint="sha256:" + ("b" * 64))

    assert source == repeated
    assert source.source_fingerprint == repeated.source_fingerprint
    assert source.source_fingerprint != changed.source_fingerprint
    json.dumps(source.to_dict(), allow_nan=False)


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"source_id": ""}, "source_id must not be empty"),
        ({"source_id": " source "}, "surrounding whitespace"),
        ({"source_version": " "}, "source_version must not be empty"),
        ({"source_version": " 1.0.0"}, "surrounding whitespace"),
        ({"configuration_fingerprint": "bad"}, "sha256 fingerprint"),
    ],
)
def test_source_identity_rejects_invalid_values(
    kwargs: dict[str, object],
    error: str,
) -> None:
    values: dict[str, object] = {
        "source_id": "source",
        "source_version": "1.0.0",
        "configuration_fingerprint": None,
    }
    values.update(kwargs)
    with pytest.raises((TypeError, ValueError), match=error):
        TradingSignalSourceIdentity(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "value",
    [
        1,
        1.0,
        "1",
        True,
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
        Decimal("-1"),
        Decimal("-0"),
        Decimal("-0.0"),
        Decimal("-0E+5"),
        Decimal("-0E-5"),
    ],
)
def test_target_units_require_finite_nonnegative_decimal(value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        _signal(target_units=value)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "value",
    [
        Decimal("1"),
        Decimal("1.0"),
        Decimal("1.00"),
        Decimal("1E+0"),
    ],
)
def test_decimal_trailing_zero_forms_have_one_identity(value: Decimal) -> None:
    signal = _signal(target_units=value)

    assert signal.target_units == Decimal("1")
    assert signal.to_dict()["target_units"] == "1"
    assert (
        signal.signal_fingerprint
        == _signal(
            target_units=Decimal("1"),
        ).signal_fingerprint
    )


@pytest.mark.parametrize(
    ("value", "canonical"),
    [
        (Decimal("0"), "0"),
        (Decimal("0.0"), "0"),
        (Decimal("0E+100"), "0"),
        (Decimal("1.2500"), "1.25"),
        (Decimal("1000"), "1000"),
        (Decimal("1E+3"), "1000"),
    ],
)
def test_decimal_projection_is_fixed_point(value: Decimal, canonical: str) -> None:
    position = (
        TradingTargetPosition.FLAT if value.is_zero() else TradingTargetPosition.LONG
    )
    signal = _signal(target_position=position, target_units=value)

    assert signal.to_dict()["target_units"] == canonical


@pytest.mark.parametrize(
    ("value", "canonical"),
    [
        (Decimal("1E-30"), "0.000000000000000000000000000001"),
        (Decimal("1E+30"), "1000000000000000000000000000000"),
        (
            Decimal("123456789012345678901234567890.0000"),
            "123456789012345678901234567890",
        ),
        (
            Decimal("0.0000000000000000000000000000012300"),
            "0.00000000000000000000000000000123",
        ),
    ],
)
def test_decimal_extreme_finite_values_project_exactly(
    value: Decimal,
    canonical: str,
) -> None:
    signal = _signal(target_units=value)

    assert signal.to_dict()["target_units"] == canonical
    assert "E" not in canonical


@pytest.mark.parametrize(
    "value",
    [
        Decimal("123456789.123456789"),
        Decimal("1.2300"),
        Decimal("1E+20"),
        Decimal("1E-20"),
    ],
)
def test_decimal_identity_is_independent_of_context_precision(
    value: Decimal,
) -> None:
    expected = _signal(target_units=value)

    with localcontext() as context:
        context.prec = 2
        actual = _signal(target_units=value)

    assert actual.target_units == expected.target_units
    assert actual.to_dict()["target_units"] == expected.to_dict()["target_units"]
    assert actual.signal_fingerprint == expected.signal_fingerprint


@pytest.mark.parametrize(
    ("position", "units", "accepted"),
    [
        (TradingTargetPosition.LONG, Decimal("1"), True),
        (TradingTargetPosition.SHORT, Decimal("1"), True),
        (TradingTargetPosition.FLAT, Decimal("0"), True),
        (TradingTargetPosition.LONG, Decimal("0"), False),
        (TradingTargetPosition.SHORT, Decimal("0"), False),
        (TradingTargetPosition.FLAT, Decimal("1"), False),
    ],
)
def test_target_position_quantity_invariants(
    position: TradingTargetPosition,
    units: Decimal,
    accepted: bool,
) -> None:
    if accepted:
        assert _signal(target_position=position, target_units=units).target_units == (
            units
        )
    else:
        with pytest.raises(ValueError):
            _signal(target_position=position, target_units=units)


def test_signal_requires_opaque_event_id_and_preserves_case() -> None:
    signal = _signal(source_event_id="Alert-ABC")

    assert signal.source_event_id == "Alert-ABC"
    with pytest.raises(ValueError, match="surrounding whitespace"):
        _signal(source_event_id=" Alert-ABC ")
    with pytest.raises(ValueError, match="must not be empty"):
        _signal(source_event_id="")


def test_signal_normalizes_timestamps_to_utc_and_optional_timeframe() -> None:
    offset = timezone(timedelta(hours=8))
    signal = _signal(
        timeframe=" 5min ",
        generated_at=_START.astimezone(offset),
        valid_from=_START.astimezone(offset),
        expires_at=(_START + timedelta(minutes=5)).astimezone(offset),
    )

    assert signal.timeframe == "5min"
    assert signal.generated_at == _START
    assert signal.generated_at.tzinfo is UTC
    assert signal.signal_fingerprint == _signal().signal_fingerprint
    assert _signal(timeframe=None).timeframe is None


@pytest.mark.parametrize(
    "field_name",
    ["generated_at", "valid_from", "expires_at"],
)
def test_signal_rejects_naive_timestamps(field_name: str) -> None:
    kwargs = {field_name: _START.replace(tzinfo=None)}

    with pytest.raises(ValueError, match="timezone-aware"):
        _signal(**kwargs)  # type: ignore[arg-type]


def test_timezone_without_utc_offset_is_rejected_everywhere() -> None:
    no_offset = _START.replace(tzinfo=_NoOffsetTimezone())

    with pytest.raises(ValueError, match="timezone-aware"):
        _signal(generated_at=no_offset)

    signal = _signal()
    with pytest.raises(ValueError, match="timezone-aware"):
        evaluate_trading_signal_temporal_status(signal, no_offset)
    with pytest.raises(ValueError, match="timezone-aware"):
        create_order_intent_from_signal(
            signal,
            ExactTargetPositionIntentPolicy(),
            no_offset,
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        OrderIntent._create(
            source_signal=signal,
            policy=ExactTargetPositionIntentPolicy(),
            decision_as_of=no_offset,
        )


def test_signal_timestamp_window_invariants() -> None:
    with pytest.raises(ValueError, match="generated_at"):
        _signal(generated_at=_START + timedelta(seconds=1))
    with pytest.raises(ValueError, match="valid_from"):
        _signal(expires_at=_START)
    with pytest.raises(ValueError, match="valid_from"):
        _signal(expires_at=_START - timedelta(seconds=1))


def test_signal_fingerprint_covers_content_but_idempotency_does_not() -> None:
    baseline = _signal()
    changed_target = _signal(target_units=Decimal("101"))
    changed_direction = _signal(
        target_position=TradingTargetPosition.SHORT,
    )
    changed_instrument = _signal(instrument=_instrument(symbol="MSFT"))
    changed_timeframe = _signal(timeframe="1day")
    changed_generated = _signal(generated_at=_START - timedelta(seconds=1))
    changed_expiry = _signal(expires_at=_START + timedelta(minutes=6))

    for changed in (
        changed_target,
        changed_direction,
        changed_instrument,
        changed_timeframe,
        changed_generated,
        changed_expiry,
    ):
        assert changed.idempotency_key == baseline.idempotency_key
        assert changed.signal_fingerprint != baseline.signal_fingerprint

    changed_event = _signal(source_event_id="event-002")
    assert changed_event.idempotency_key != baseline.idempotency_key
    assert changed_event.signal_fingerprint != baseline.signal_fingerprint


def test_signal_source_change_changes_both_identities() -> None:
    baseline = _signal()
    changed = _signal(source=_source(source_id="other-source"))

    assert changed.idempotency_key != baseline.idempotency_key
    assert changed.signal_fingerprint != baseline.signal_fingerprint


def test_signal_is_frozen_bounded_and_json_safe() -> None:
    signal = _signal(source_event_id="sensitive-event-value")

    with pytest.raises(FrozenInstanceError):
        signal.timeframe = "1day"  # type: ignore[misc]
    assert "object at 0x" not in repr(signal)
    assert "raw_payload" not in repr(signal)
    assert "sensitive-event-value" not in repr(signal)
    serialized = json.dumps(signal.to_dict(), allow_nan=False)
    for forbidden in ("credential", "account", "broker", "risk", "tradingview"):
        assert forbidden not in serialized.lower()


def test_signal_runtime_checks_domain_types_and_required_expiry() -> None:
    with pytest.raises(TypeError, match="source"):
        _signal(source="source")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="instrument"):
        _signal(instrument="instrument")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="target_position"):
        _signal(target_position="long")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="timeframe must not be empty"):
        _signal(timeframe=" ")
    with pytest.raises(TypeError, match="expires_at"):
        _signal(expires_at=None)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("as_of", "expected"),
    [
        (
            _START - timedelta(microseconds=1),
            TradingSignalTemporalStatus.NOT_YET_VALID,
        ),
        (_START, TradingSignalTemporalStatus.ACTIVE),
        (
            _START + timedelta(minutes=5) - timedelta(microseconds=1),
            TradingSignalTemporalStatus.ACTIVE,
        ),
        (_START + timedelta(minutes=5), TradingSignalTemporalStatus.EXPIRED),
        (
            _START + timedelta(minutes=5, microseconds=1),
            TradingSignalTemporalStatus.EXPIRED,
        ),
    ],
)
def test_temporal_status_uses_half_open_interval(
    as_of: datetime,
    expected: TradingSignalTemporalStatus,
) -> None:
    assert evaluate_trading_signal_temporal_status(_signal(), as_of) is expected


def test_temporal_status_normalizes_offset_and_rejects_naive_as_of() -> None:
    signal = _signal()
    offset_as_of = _START.astimezone(timezone(timedelta(hours=-5)))

    assert (
        evaluate_trading_signal_temporal_status(signal, offset_as_of)
        is TradingSignalTemporalStatus.ACTIVE
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        evaluate_trading_signal_temporal_status(
            signal,
            _START.replace(tzinfo=None),
        )


def test_event_consistency_identical_conflicting_and_unrelated() -> None:
    baseline = _signal()

    assert (
        compare_trading_signal_event_consistency(baseline, _signal())
        is TradingSignalEventConsistency.IDENTICAL
    )
    assert (
        compare_trading_signal_event_consistency(
            baseline,
            _signal(target_position=TradingTargetPosition.SHORT),
        )
        is TradingSignalEventConsistency.CONFLICTING_CONTENT
    )
    assert (
        compare_trading_signal_event_consistency(
            baseline,
            _signal(source_event_id="event-002"),
        )
        is TradingSignalEventConsistency.UNRELATED
    )
    assert (
        compare_trading_signal_event_consistency(
            baseline,
            _signal(source=_source(source_id="other-source")),
        )
        is TradingSignalEventConsistency.UNRELATED
    )


@pytest.mark.parametrize(
    ("other", "expected"),
    [
        (_signal(), TradingSignalEventConsistency.IDENTICAL),
        (
            _signal(target_position=TradingTargetPosition.SHORT),
            TradingSignalEventConsistency.CONFLICTING_CONTENT,
        ),
        (
            _signal(source_event_id="event-002"),
            TradingSignalEventConsistency.UNRELATED,
        ),
    ],
)
def test_event_consistency_is_symmetric(
    other: TradingSignal,
    expected: TradingSignalEventConsistency,
) -> None:
    baseline = _signal()

    assert compare_trading_signal_event_consistency(baseline, other) is expected
    assert compare_trading_signal_event_consistency(other, baseline) is expected


def test_policy_has_one_fixed_deterministic_identity() -> None:
    policy = ExactTargetPositionIntentPolicy()

    assert policy == ExactTargetPositionIntentPolicy()
    assert policy.methodology == "exact_target_position"
    assert policy.version == "1.0.0"
    assert policy.policy_fingerprint.startswith("sha256:")
    assert policy.to_dict() == ExactTargetPositionIntentPolicy().to_dict()
    json.dumps(policy.to_dict(), allow_nan=False)
    with pytest.raises(TypeError):
        ExactTargetPositionIntentPolicy(configuration={})  # type: ignore[call-arg]


def test_active_signal_creates_exact_pre_risk_intent() -> None:
    signal = _signal()
    policy = ExactTargetPositionIntentPolicy()
    intent = create_order_intent_from_signal(signal, policy, _START)

    assert intent.source_signal is signal
    assert intent.policy is policy
    assert intent.source_signal_fingerprint == signal.signal_fingerprint
    assert intent.source_idempotency_key == signal.idempotency_key
    assert intent.instrument is signal.instrument
    assert intent.target_position is signal.target_position
    assert intent.target_units is signal.target_units
    assert intent.policy_fingerprint == policy.policy_fingerprint
    assert intent.decision_as_of == _START
    assert intent.valid_from == _START
    assert intent.expires_at == signal.expires_at
    assert intent.intent_fingerprint.startswith("sha256:")


def test_order_intent_normalizes_as_of_and_identity_is_time_sensitive() -> None:
    signal = _signal()
    policy = ExactTargetPositionIntentPolicy()
    offset = timezone(timedelta(hours=8))
    first = create_order_intent_from_signal(
        signal,
        policy,
        _START.astimezone(offset),
    )
    equivalent = create_order_intent_from_signal(signal, policy, _START)
    later = create_order_intent_from_signal(
        signal,
        policy,
        _START + timedelta(seconds=1),
    )

    assert first == equivalent
    assert first.decision_as_of.tzinfo is UTC
    assert first.valid_from.tzinfo is UTC
    assert first.expires_at.tzinfo is UTC
    assert first.intent_fingerprint == equivalent.intent_fingerprint
    assert first.intent_fingerprint != later.intent_fingerprint


def test_private_order_intent_creation_stores_only_canonical_utc() -> None:
    signal = _signal()
    offset_as_of = _START.astimezone(timezone(timedelta(hours=8)))

    intent = OrderIntent._create(
        source_signal=signal,
        policy=ExactTargetPositionIntentPolicy(),
        decision_as_of=offset_as_of,
    )

    assert intent.decision_as_of == _START
    assert intent.valid_from == _START
    assert intent.expires_at is signal.expires_at
    assert intent.decision_as_of.tzinfo is UTC
    assert intent.valid_from.tzinfo is UTC
    assert intent.expires_at.tzinfo is UTC
    assert intent.to_dict()["decision_as_of"] == intent.decision_as_of.isoformat()
    assert intent.to_dict()["valid_from"] == intent.valid_from.isoformat()
    assert intent.to_dict()["expires_at"] == intent.expires_at.isoformat()


@pytest.mark.parametrize(
    "field_name",
    ["decision_as_of", "valid_from", "expires_at"],
)
def test_order_intent_validation_rejects_noncanonical_offset_state(
    field_name: str,
) -> None:
    intent = create_order_intent_from_signal(
        _signal(),
        ExactTargetPositionIntentPolicy(),
        _START,
    )
    offset = timezone(timedelta(hours=8))
    object.__setattr__(
        intent, field_name, getattr(intent, field_name).astimezone(offset)
    )

    with pytest.raises(ValueError, match="canonical UTC"):
        intent._validate()


def test_order_intent_rejects_inactive_signal() -> None:
    signal = _signal(valid_from=_START + timedelta(minutes=1))
    policy = ExactTargetPositionIntentPolicy()

    with pytest.raises(TradingSignalNotYetValidError, match="not yet valid"):
        create_order_intent_from_signal(signal, policy, _START)
    with pytest.raises(TradingSignalExpiredError, match="expired"):
        create_order_intent_from_signal(
            signal,
            policy,
            signal.expires_at,
        )


def test_order_intent_direct_construction_is_guarded() -> None:
    with pytest.raises(TypeError, match="create_order_intent_from_signal"):
        OrderIntent()


def test_order_intent_private_factory_revalidates_temporal_correspondence() -> None:
    signal = _signal()
    policy = ExactTargetPositionIntentPolicy()

    with pytest.raises(TradingSignalNotYetValidError, match="not yet valid"):
        OrderIntent._create(
            source_signal=signal,
            policy=policy,
            decision_as_of=_START - timedelta(microseconds=1),
        )
    with pytest.raises(TradingSignalExpiredError, match="expired"):
        OrderIntent._create(
            source_signal=signal,
            policy=policy,
            decision_as_of=signal.expires_at,
        )


@pytest.mark.parametrize(
    "source_signal",
    [
        None,
        object(),
        MarketSignal(
            symbol="AAPL",
            name="trend",
            value=1.0,
            timestamp=_START,
            parameters={},
        ),
    ],
)
def test_private_order_intent_factory_rejects_wrong_source_type(
    source_signal: object,
) -> None:
    with pytest.raises(TypeError, match="source_signal"):
        OrderIntent._create(
            source_signal=source_signal,  # type: ignore[arg-type]
            policy=ExactTargetPositionIntentPolicy(),
            decision_as_of=_START,
        )


@pytest.mark.parametrize("policy", [None, object(), ExactTargetPositionIntentPolicy])
def test_private_order_intent_factory_rejects_wrong_policy_type(
    policy: object,
) -> None:
    with pytest.raises(TypeError, match="policy"):
        OrderIntent._create(
            source_signal=_signal(),
            policy=policy,  # type: ignore[arg-type]
            decision_as_of=_START,
        )


@pytest.mark.parametrize(
    "decision_as_of",
    ["2026-07-29T14:30:00Z", 1, _START.replace(tzinfo=None)],
)
def test_private_order_intent_factory_rejects_invalid_decision_time(
    decision_as_of: object,
) -> None:
    with pytest.raises((TypeError, ValueError), match="decision_as_of"):
        OrderIntent._create(
            source_signal=_signal(),
            policy=ExactTargetPositionIntentPolicy(),
            decision_as_of=decision_as_of,  # type: ignore[arg-type]
        )


def test_order_intent_rejects_mutated_or_fabricated_identity() -> None:
    intent = create_order_intent_from_signal(
        _signal(),
        ExactTargetPositionIntentPolicy(),
        _START,
    )
    object.__setattr__(intent, "intent_fingerprint", "sha256:" + ("0" * 64))

    with pytest.raises(ValueError, match="intent_fingerprint"):
        intent._validate()

    other = create_order_intent_from_signal(
        _signal(source_event_id="other-event"),
        ExactTargetPositionIntentPolicy(),
        _START,
    )
    object.__setattr__(other, "expires_at", other.expires_at + timedelta(seconds=1))
    with pytest.raises(ValueError, match="source signal expiry"):
        other._validate()

    swapped_source = create_order_intent_from_signal(
        _signal(),
        ExactTargetPositionIntentPolicy(),
        _START,
    )
    object.__setattr__(
        swapped_source,
        "source_signal",
        _signal(source_event_id="other-event"),
    )
    with pytest.raises(ValueError, match="intent_fingerprint"):
        swapped_source._validate()

    mismatched_policy = create_order_intent_from_signal(
        _signal(),
        ExactTargetPositionIntentPolicy(),
        _START,
    )
    object.__setattr__(
        mismatched_policy.policy,
        "policy_fingerprint",
        "sha256:" + ("f" * 64),
    )
    with pytest.raises(ValueError, match="intent_fingerprint"):
        mismatched_policy._validate()


def test_order_intent_is_frozen_bounded_and_json_safe() -> None:
    intent = create_order_intent_from_signal(
        _signal(),
        ExactTargetPositionIntentPolicy(),
        _START,
    )

    with pytest.raises(FrozenInstanceError):
        intent.expires_at = _START  # type: ignore[misc]
    assert "TradingSignal(" not in repr(intent)
    assert "object at 0x" not in repr(intent)
    payload = intent.to_dict()
    serialized = json.dumps(payload, allow_nan=False)
    assert "source_signal" not in payload
    for forbidden in (
        "status",
        "approved",
        "rejected",
        "filled",
        "cancelled",
        "submitted",
        "account",
        "broker",
        "risk",
        "order_type",
        "time_in_force",
        "price",
    ):
        assert forbidden not in serialized.lower()


def test_order_intent_has_no_lifecycle_or_execution_fields() -> None:
    field_names = {item.name for item in fields(OrderIntent)}

    assert field_names.isdisjoint(
        {
            "status",
            "approved",
            "rejected",
            "filled",
            "cancelled",
            "submitted",
            "account",
            "broker",
            "order_type",
            "time_in_force",
            "fill",
            "price",
        }
    )


@pytest.mark.parametrize(
    ("function", "args"),
    [
        (evaluate_trading_signal_temporal_status, ("bad", _START)),
        (compare_trading_signal_event_consistency, ("bad", _signal())),
        (compare_trading_signal_event_consistency, (_signal(), "bad")),
        (
            create_order_intent_from_signal,
            ("bad", ExactTargetPositionIntentPolicy(), _START),
        ),
        (create_order_intent_from_signal, (_signal(), "bad", _START)),
    ],
)
def test_public_operations_runtime_check_types(
    function: object,
    args: tuple[object, ...],
) -> None:
    with pytest.raises(TypeError):
        function(*args)  # type: ignore[operator]


@pytest.mark.parametrize(
    "signal",
    [
        None,
        object(),
        MarketSignal(
            symbol="AAPL",
            name="trend",
            value=1.0,
            timestamp=_START,
            parameters={},
        ),
    ],
)
def test_public_order_intent_factory_rejects_wrong_signal_type(
    signal: object,
) -> None:
    with pytest.raises(TypeError, match="signal"):
        create_order_intent_from_signal(
            signal,  # type: ignore[arg-type]
            ExactTargetPositionIntentPolicy(),
            _START,
        )


@pytest.mark.parametrize("policy", [None, object(), ExactTargetPositionIntentPolicy])
def test_public_order_intent_factory_rejects_wrong_policy_type(
    policy: object,
) -> None:
    with pytest.raises(TypeError, match="policy"):
        create_order_intent_from_signal(
            _signal(),
            policy,  # type: ignore[arg-type]
            _START,
        )


@pytest.mark.parametrize(
    "as_of",
    ["2026-07-29T14:30:00Z", 1, _START.replace(tzinfo=None)],
)
def test_public_order_intent_factory_rejects_invalid_as_of(as_of: object) -> None:
    with pytest.raises((TypeError, ValueError), match="as_of"):
        create_order_intent_from_signal(
            _signal(),
            ExactTargetPositionIntentPolicy(),
            as_of,  # type: ignore[arg-type]
        )
