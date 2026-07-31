"""Focused tests for exact immutable trading-state snapshots."""

from __future__ import annotations

import json
from collections import deque
from collections.abc import Callable, Iterator, Sequence
from dataclasses import fields
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from decimal import Decimal, localcontext
from typing import overload

import pytest

import market_platform.trading_state._canonical as state_canonical
import market_platform.trading_state.snapshots as state_snapshots
from market_platform._fingerprint import canonical_fingerprint
from market_platform.instruments import CanonicalInstrumentId
from market_platform.trading import TradingInstrumentIdentity
from market_platform.trading_state import (
    ACCOUNT_CASH_SNAPSHOT_SCHEMA_VERSION,
    MARKET_QUOTE_COLLECTION_SNAPSHOT_SCHEMA_VERSION,
    OPEN_ORDER_EXPOSURE_SNAPSHOT_SCHEMA_VERSION,
    POSITION_COLLECTION_SNAPSHOT_SCHEMA_VERSION,
    STATE_SNAPSHOT_SOURCE_SCHEMA_VERSION,
    TRADING_ACCOUNT_IDENTITY_SCHEMA_VERSION,
    AccountCashSnapshot,
    CashBalance,
    MarketQuote,
    MarketQuoteCollectionSnapshot,
    OpenOrderExposure,
    OpenOrderExposureSnapshot,
    PositionCollectionSnapshot,
    PositionRecord,
    SnapshotFreshness,
    SnapshotSkew,
    StateSnapshotSourceIdentity,
    TradingAccountIdentity,
    TradingEnvironment,
    TradingStateCorrespondenceError,
    TradingStateDuplicateError,
    TradingStateValidationError,
    evaluate_snapshot_freshness,
    evaluate_snapshot_skew,
)

_AS_OF = datetime(2026, 7, 31, 12, 0, 0, 123456, tzinfo=UTC)
_CONFIGURATION_FINGERPRINT = "sha256:" + ("1" * 64)


def _source(
    source_id: str = "broker.state",
    version: str = "1",
    configuration: str | None = _CONFIGURATION_FINGERPRINT,
) -> StateSnapshotSourceIdentity:
    return StateSnapshotSourceIdentity(source_id, version, configuration)


def _account(
    namespace: str = "interactive_brokers",
    account_id: str = "paper-U1234567",
    environment: TradingEnvironment = TradingEnvironment.PAPER,
    currency: str = "USD",
) -> TradingAccountIdentity:
    return TradingAccountIdentity(
        institution_namespace=namespace,
        account_id=account_id,
        environment=environment,
        base_currency=currency,
    )


def _instrument(value: str = "us_equity_apple") -> CanonicalInstrumentId:
    return CanonicalInstrumentId(value)


def _cash_snapshot(
    balances: object = (),
    *,
    account: TradingAccountIdentity | None = None,
    source: StateSnapshotSourceIdentity | None = None,
    as_of: datetime = _AS_OF,
) -> AccountCashSnapshot:
    return AccountCashSnapshot(
        account=account or _account(),
        source=source or _source(),
        as_of=as_of,
        balances=balances,  # type: ignore[arg-type]
    )


def _position_snapshot(records: object = ()) -> PositionCollectionSnapshot:
    return PositionCollectionSnapshot(
        account=_account(),
        source=_source(),
        as_of=_AS_OF,
        positions=records,  # type: ignore[arg-type]
    )


def _order_snapshot(records: object = ()) -> OpenOrderExposureSnapshot:
    return OpenOrderExposureSnapshot(
        account=_account(),
        source=_source(),
        as_of=_AS_OF,
        exposures=records,  # type: ignore[arg-type]
    )


def _quote_snapshot(records: object = ()) -> MarketQuoteCollectionSnapshot:
    return MarketQuoteCollectionSnapshot(
        source=_source(),
        as_of=_AS_OF,
        quotes=records,  # type: ignore[arg-type]
    )


def _assert_json_safe(value: object) -> None:
    encoded = json.dumps(value, allow_nan=False, sort_keys=True)
    assert json.loads(encoded) == value


def test_exact_public_schema_inventory() -> None:
    assert STATE_SNAPSHOT_SOURCE_SCHEMA_VERSION == "state_snapshot_source/v1"
    assert TRADING_ACCOUNT_IDENTITY_SCHEMA_VERSION == "trading_account_identity/v1"
    assert ACCOUNT_CASH_SNAPSHOT_SCHEMA_VERSION == "account_cash_snapshot/v1"
    assert POSITION_COLLECTION_SNAPSHOT_SCHEMA_VERSION == (
        "position_collection_snapshot/v1"
    )
    assert OPEN_ORDER_EXPOSURE_SNAPSHOT_SCHEMA_VERSION == (
        "open_order_exposure_snapshot/v1"
    )
    assert MARKET_QUOTE_COLLECTION_SNAPSHOT_SCHEMA_VERSION == (
        "market_quote_collection_snapshot/v1"
    )


def test_only_snapshot_and_identity_models_have_fingerprints() -> None:
    for model_type in (
        CashBalance,
        PositionRecord,
        OpenOrderExposure,
        MarketQuote,
    ):
        assert "fingerprint" not in {item.name for item in fields(model_type)}
        assert "schema_version" not in {item.name for item in fields(model_type)}
    assert not hasattr(SnapshotFreshness.FRESH, "fingerprint")
    assert not hasattr(SnapshotSkew.COHERENT, "fingerprint")


@pytest.mark.parametrize("field_name", ["source_id", "source_version"])
@pytest.mark.parametrize("value", ["", " bad", "bad ", "bad value", "bad\x7f", "全角"])
def test_source_identity_rejects_invalid_passive_text(
    field_name: str,
    value: str,
) -> None:
    kwargs = {"source_id": "source", "source_version": "1"}
    kwargs[field_name] = value
    with pytest.raises(TradingStateValidationError):
        StateSnapshotSourceIdentity(**kwargs)


def test_source_identity_limits_and_fingerprint_significance() -> None:
    assert len(StateSnapshotSourceIdentity("a" * 128, "v" * 64).source_id) == 128
    with pytest.raises(TradingStateValidationError):
        StateSnapshotSourceIdentity("a" * 129, "1")
    with pytest.raises(TradingStateValidationError):
        StateSnapshotSourceIdentity("a", "v" * 65)
    baseline = _source()
    assert baseline == _source()
    assert baseline.fingerprint != _source(source_id="other").fingerprint
    assert baseline.fingerprint != _source(version="2").fingerprint
    assert baseline.fingerprint != _source(configuration=None).fingerprint
    _assert_json_safe(baseline.to_dict())


@pytest.mark.parametrize(
    "configuration",
    ["sha256:" + ("A" * 64), "sha1:" + ("1" * 64), "sha256:1", "bad"],
)
def test_source_identity_rejects_malformed_configuration_fingerprint(
    configuration: str,
) -> None:
    with pytest.raises(TradingStateValidationError):
        _source(configuration=configuration)


def test_account_environment_is_exactly_paper_and_live() -> None:
    assert {item.value for item in TradingEnvironment} == {"paper", "live"}
    assert _account(environment=TradingEnvironment.LIVE).environment is (
        TradingEnvironment.LIVE
    )
    with pytest.raises(TypeError):
        _account(environment="paper")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "namespace",
    ["Interactive_Brokers", "1broker", ".broker", "broker/name", "broker:name"],
)
def test_account_rejects_invalid_institution_namespace(namespace: str) -> None:
    with pytest.raises(TradingStateValidationError):
        _account(namespace=namespace)


def test_account_fields_are_bounded_exact_and_fingerprint_significant() -> None:
    account = _account(account_id="Acct:#1/Primary", currency="HKD")
    assert account.account_id == "Acct:#1/Primary"
    assert account.to_dict()["account_id"] == "Acct:#1/Primary"
    _assert_json_safe(account.to_dict())
    with pytest.raises(TradingStateValidationError):
        _account(account_id="a" * 129)
    for currency in ("usd", "US", "USDD", "ＵＳＤ"):
        with pytest.raises(TradingStateValidationError):
            _account(currency=currency)
    assert account.fingerprint != _account(currency="USD").fingerprint
    assert account.fingerprint != _account(account_id="other").fingerprint
    assert account.fingerprint != _account(namespace="tiger").fingerprint
    assert (
        account.fingerprint
        != _account(
            environment=TradingEnvironment.LIVE,
            currency="HKD",
        ).fingerprint
    )


class _DecimalSubclass(Decimal):
    pass


@pytest.mark.parametrize(
    "value",
    [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")],
)
def test_decimal_requires_finite_exact_values(value: Decimal) -> None:
    with pytest.raises(TradingStateValidationError):
        CashBalance("USD", value)
    with pytest.raises(TypeError):
        CashBalance("USD", _DecimalSubclass("1"))


@pytest.mark.parametrize(
    "value", [Decimal("-0"), Decimal("-0.0"), Decimal("-0E+1000000")]
)
def test_every_record_rejects_negative_zero(value: Decimal) -> None:
    with pytest.raises(TradingStateValidationError):
        CashBalance("USD", value)
    with pytest.raises(TradingStateValidationError):
        PositionRecord(_instrument(), value)
    with pytest.raises(TradingStateValidationError):
        OpenOrderExposure("order-1", _instrument(), value)
    with pytest.raises(TradingStateValidationError):
        MarketQuote(_instrument(), last=value)


@pytest.mark.parametrize(
    "value",
    [Decimal("0"), Decimal("0.0"), Decimal("0E+1000000"), Decimal("0E-1000000")],
)
def test_cash_positive_zero_canonicalizes_without_exponent_allocation(
    value: Decimal,
) -> None:
    balance = CashBalance("USD", value)
    assert balance.amount.as_tuple() == Decimal("0").as_tuple()
    assert balance.to_dict()["amount"] == "0"


@pytest.mark.parametrize(
    "value",
    [
        Decimal("1E+1000000"),
        Decimal("1E-1000000"),
        Decimal("-9.99E+1000000"),
        Decimal("9.99E-1000000"),
    ],
)
def test_huge_decimal_exponents_reject_before_formatting(
    monkeypatch: pytest.MonkeyPatch,
    value: Decimal,
) -> None:
    def fail_format(_: Decimal) -> str:
        raise AssertionError("fixed-point formatting must not run")

    monkeypatch.setattr(state_canonical, "_fixed_point_decimal_text", fail_format)
    with pytest.raises(TradingStateValidationError):
        CashBalance("USD", value)


def test_decimal_limits_and_sign_projection_are_exact() -> None:
    assert CashBalance("USD", Decimal("9" * 128)).to_dict()["amount"] == "9" * 128
    with pytest.raises(TradingStateValidationError, match="digit maximum 128"):
        CashBalance("USD", Decimal("9" * 129))
    fractional_64 = Decimal("0." + ("0" * 63) + "1")
    assert CashBalance("USD", fractional_64).amount == fractional_64
    with pytest.raises(
        TradingStateValidationError, match="fractional digit maximum 64"
    ):
        CashBalance("USD", Decimal("0." + ("0" * 64) + "1"))
    assert state_canonical._project_canonical_decimal_size(Decimal("-1")) == (1, 0, 2)


def test_decimal_normalization_is_exact_and_context_independent() -> None:
    with localcontext() as context:
        context.prec = 2
        context.Emax = 2
        context.Emin = -2
        first = CashBalance("USD", Decimal("0001.2500"))
    second = CashBalance("USD", Decimal("1.25"))
    assert first.amount.as_tuple() == second.amount.as_tuple()
    assert first.to_dict() == second.to_dict() == {"currency": "USD", "amount": "1.25"}


def test_record_sign_policies_are_exact() -> None:
    assert CashBalance("USD", Decimal("-25.50")).to_dict()["amount"] == "-25.5"
    assert CashBalance("USD", Decimal("0")).amount == 0
    assert PositionRecord(_instrument(), Decimal("1.5")).quantity > 0
    assert PositionRecord(_instrument(), Decimal("-1.5")).quantity < 0
    assert OpenOrderExposure("buy", _instrument(), Decimal("1")).remaining_quantity > 0
    assert (
        OpenOrderExposure("sell", _instrument(), Decimal("-1")).remaining_quantity < 0
    )
    with pytest.raises(TradingStateValidationError, match="nonzero"):
        PositionRecord(_instrument(), Decimal("0"))
    with pytest.raises(TradingStateValidationError, match="nonzero"):
        OpenOrderExposure("zero", _instrument(), Decimal("0"))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"bid": Decimal("1")},
        {"ask": Decimal("2")},
        {"last": Decimal("3")},
        {"bid": Decimal("1"), "ask": Decimal("2")},
        {"bid": Decimal("1"), "ask": Decimal("2"), "last": Decimal("9")},
    ],
)
def test_market_quote_accepts_approved_partial_price_sets(
    kwargs: dict[str, Decimal],
) -> None:
    quote = MarketQuote(_instrument(), **kwargs)
    _assert_json_safe(quote.to_dict())


def test_market_quote_rejects_missing_nonpositive_or_crossed_prices() -> None:
    with pytest.raises(TradingStateValidationError, match="requires"):
        MarketQuote(_instrument())
    for value in (Decimal("0"), Decimal("-1")):
        with pytest.raises(TradingStateValidationError, match="positive"):
            MarketQuote(_instrument(), last=value)
    with pytest.raises(TradingStateValidationError, match="bid"):
        MarketQuote(_instrument(), bid=Decimal("2"), ask=Decimal("1"))
    assert MarketQuote(_instrument(), bid=Decimal("1"), ask=Decimal("1")).bid == 1


def test_cash_snapshot_sorts_rejects_duplicates_and_is_order_neutral() -> None:
    usd = CashBalance("USD", Decimal("10"))
    eur = CashBalance("EUR", Decimal("-2"))
    first = _cash_snapshot([usd, eur])
    second = _cash_snapshot((eur, usd))
    assert [item.currency for item in first.balances] == ["EUR", "USD"]
    assert first == second
    assert first.fingerprint == second.fingerprint
    with pytest.raises(TradingStateDuplicateError, match="currency USD"):
        _cash_snapshot([usd, CashBalance("USD", Decimal("11"))])


def test_position_snapshot_sorts_rejects_duplicates_and_is_order_neutral() -> None:
    apple = PositionRecord(_instrument("apple"), Decimal("2"))
    microsoft = PositionRecord(_instrument("microsoft"), Decimal("-3"))
    first = _position_snapshot([microsoft, apple])
    second = _position_snapshot((apple, microsoft))
    assert [item.instrument_id.instrument_id for item in first.positions] == [
        "apple",
        "microsoft",
    ]
    assert first.fingerprint == second.fingerprint
    with pytest.raises(TradingStateDuplicateError, match="instrument_id apple"):
        _position_snapshot([apple, PositionRecord(_instrument("apple"), Decimal("5"))])


def test_order_snapshot_sorts_allows_same_instrument_and_rejects_order_id() -> None:
    second = OpenOrderExposure("order-2", _instrument(), Decimal("2"))
    first = OpenOrderExposure("order-1", _instrument(), Decimal("1"))
    snapshot = _order_snapshot([second, first])
    assert [item.external_order_id for item in snapshot.exposures] == [
        "order-1",
        "order-2",
    ]
    assert snapshot.fingerprint == _order_snapshot((first, second)).fingerprint
    with pytest.raises(TradingStateDuplicateError, match="external_order_id"):
        _order_snapshot(
            [first, OpenOrderExposure("order-1", _instrument("other"), Decimal("1"))]
        )


def test_quote_snapshot_sorts_rejects_duplicates_and_has_no_account() -> None:
    apple = MarketQuote(_instrument("apple"), last=Decimal("100"))
    microsoft = MarketQuote(_instrument("microsoft"), bid=Decimal("200"))
    snapshot = _quote_snapshot([microsoft, apple])
    assert [item.instrument_id.instrument_id for item in snapshot.quotes] == [
        "apple",
        "microsoft",
    ]
    assert "account" not in snapshot.to_dict()
    assert snapshot.fingerprint == _quote_snapshot((apple, microsoft)).fingerprint
    with pytest.raises(TradingStateDuplicateError, match="instrument_id apple"):
        _quote_snapshot([apple, MarketQuote(_instrument("apple"), ask=Decimal("101"))])


@pytest.mark.parametrize(
    "factory,field_name",
    [
        (_cash_snapshot, "balances"),
        (_position_snapshot, "positions"),
        (_order_snapshot, "exposures"),
        (_quote_snapshot, "quotes"),
    ],
)
def test_all_snapshot_collections_accept_exact_empty_list_and_tuple(
    factory: Callable[[object], object],
    field_name: str,
) -> None:
    containers: tuple[object, ...] = ([], ())
    for value in containers:
        snapshot = factory(value)
        assert getattr(snapshot, field_name) == ()


class _HostileList(list[object]):
    def __iter__(self) -> Iterator[object]:
        raise AssertionError("list subclass iteration must not execute")


class _HostileTuple(tuple[object, ...]):
    def __iter__(self) -> Iterator[object]:
        raise AssertionError("tuple subclass iteration must not execute")


class _HostileSequence(Sequence[object]):
    def __len__(self) -> int:
        return 1

    @overload
    def __getitem__(self, index: int) -> object: ...

    @overload
    def __getitem__(self, index: slice) -> Sequence[object]: ...

    def __getitem__(self, index: int | slice) -> object | Sequence[object]:
        if isinstance(index, slice):
            return ()
        if index == 0:
            return CashBalance("USD", Decimal("1"))
        raise IndexError(index)

    def __iter__(self) -> Iterator[object]:
        raise AssertionError("custom sequence iteration must not execute")


@pytest.mark.parametrize(
    "value",
    [
        _HostileList(),
        _HostileTuple(),
        _HostileSequence(),
        iter(()),
        (item for item in tuple[object, ...]()),
        set(),
        frozenset(),
        {},
        "records",
        b"records",
        bytearray(b"records"),
        range(0),
        deque(),
    ],
)
@pytest.mark.parametrize(
    "factory",
    [_cash_snapshot, _position_snapshot, _order_snapshot, _quote_snapshot],
)
def test_snapshot_collections_reject_nonexact_containers_before_iteration(
    factory: Callable[[object], object],
    value: object,
) -> None:
    with pytest.raises(TypeError, match="exact built-in list or tuple"):
        factory(value)


def test_collection_caps_are_checked_before_record_iteration() -> None:
    with pytest.raises(TradingStateValidationError, match="maximum 32.*observed 33"):
        _cash_snapshot([object()] * 33)
    for factory in (_position_snapshot, _order_snapshot, _quote_snapshot):
        with pytest.raises(
            TradingStateValidationError,
            match="maximum 10000.*observed 10001",
        ):
            factory([object()] * 10_001)


def test_cash_exact_maximum_is_accepted() -> None:
    currencies = [
        chr(65 + first) + chr(65 + second) + chr(65 + third)
        for first in range(26)
        for second in range(26)
        for third in range(26)
    ][:32]
    snapshot = _cash_snapshot(
        [
            CashBalance(currency, Decimal(index))
            for index, currency in enumerate(currencies)
        ]
    )
    assert len(snapshot.balances) == 32


def test_position_exact_maximum_is_accepted() -> None:
    records = [
        PositionRecord(_instrument(f"instrument-{index:05d}"), Decimal("1"))
        for index in range(10_000)
    ]
    assert len(_position_snapshot(records).positions) == 10_000


def test_open_order_exact_maximum_is_accepted() -> None:
    records = [
        OpenOrderExposure(
            f"order-{index:05d}",
            _instrument(f"instrument-{index:05d}"),
            Decimal("1"),
        )
        for index in range(10_000)
    ]
    assert len(_order_snapshot(records).exposures) == 10_000


def test_market_quote_exact_maximum_is_accepted() -> None:
    records = [
        MarketQuote(
            _instrument(f"instrument-{index:05d}"),
            last=Decimal("1"),
        )
        for index in range(10_000)
    ]
    assert len(_quote_snapshot(records).quotes) == 10_000


def test_snapshots_physically_store_canonical_utc_and_microseconds() -> None:
    offset = timezone(timedelta(hours=8))
    local = datetime(2026, 7, 31, 20, 0, 0, 123456, tzinfo=offset)
    snapshots = (
        _cash_snapshot(as_of=local),
        PositionCollectionSnapshot(_account(), _source(), local, ()),
        OpenOrderExposureSnapshot(_account(), _source(), local, ()),
        MarketQuoteCollectionSnapshot(_source(), local, ()),
    )
    for snapshot in snapshots:
        assert snapshot.as_of == _AS_OF
        assert snapshot.as_of.tzinfo is UTC
        assert snapshot.to_dict()["as_of"] == "2026-07-31T12:00:00.123456+00:00"


class _UndefinedOffset(tzinfo):
    def utcoffset(self, dt: datetime | None) -> None:
        return None

    def dst(self, dt: datetime | None) -> None:
        return None

    def tzname(self, dt: datetime | None) -> None:
        return None


@pytest.mark.parametrize(
    "value",
    [datetime(2026, 7, 31), datetime(2026, 7, 31, tzinfo=_UndefinedOffset())],
)
def test_snapshots_reject_naive_or_undefined_offset_time(value: datetime) -> None:
    with pytest.raises(TradingStateValidationError):
        _cash_snapshot(as_of=value)


def test_snapshot_fingerprints_cover_source_account_time_and_records() -> None:
    baseline = _cash_snapshot([CashBalance("USD", Decimal("1"))])
    changes = (
        _cash_snapshot([CashBalance("USD", Decimal("2"))]),
        _cash_snapshot([CashBalance("EUR", Decimal("1"))]),
        _cash_snapshot(
            [CashBalance("USD", Decimal("1"))], account=_account(account_id="other")
        ),
        _cash_snapshot(
            [CashBalance("USD", Decimal("1"))], source=_source(source_id="other")
        ),
        _cash_snapshot(
            [CashBalance("USD", Decimal("1"))], as_of=_AS_OF + timedelta(microseconds=1)
        ),
    )
    assert all(item.fingerprint != baseline.fingerprint for item in changes)
    assert baseline == _cash_snapshot([CashBalance("USD", Decimal("1"))])
    _assert_json_safe(baseline.to_dict())


def test_every_snapshot_projection_is_recursively_json_safe() -> None:
    snapshots = (
        _cash_snapshot([CashBalance("USD", Decimal("-1.25"))]),
        _position_snapshot([PositionRecord(_instrument(), Decimal("1.5"))]),
        _order_snapshot([OpenOrderExposure("order/1", _instrument(), Decimal("-2"))]),
        _quote_snapshot(
            [MarketQuote(_instrument(), bid=Decimal("1"), ask=Decimal("2"))]
        ),
    )
    for snapshot in snapshots:
        _assert_json_safe(snapshot.to_dict())
        assert snapshot.fingerprint.startswith("sha256:")


def test_fabricated_source_and_account_state_is_rejected_by_snapshots() -> None:
    source = _source()
    object.__setattr__(source, "source_id", " invalid")
    object.__setattr__(
        source,
        "fingerprint",
        canonical_fingerprint(source._fingerprint_payload()),
    )
    with pytest.raises(TradingStateCorrespondenceError, match="source"):
        _cash_snapshot(source=source)

    account = _account()
    object.__setattr__(account, "institution_namespace", "INVALID")
    object.__setattr__(
        account,
        "fingerprint",
        canonical_fingerprint(account._fingerprint_payload()),
    )
    with pytest.raises(TradingStateCorrespondenceError, match="account"):
        _cash_snapshot(account=account)


def test_fabricated_instrument_id_is_rejected_through_nested_record() -> None:
    instrument = _instrument()
    object.__setattr__(instrument, "instrument_id", "bad/id")
    with pytest.raises(TradingStateCorrespondenceError, match="instrument_id"):
        PositionRecord(instrument, Decimal("1"))


@pytest.mark.parametrize(
    "factory,record,field_name",
    [
        (
            _cash_snapshot,
            CashBalance("USD", Decimal("100")),
            "amount",
        ),
        (
            _position_snapshot,
            PositionRecord(_instrument(), Decimal("100")),
            "quantity",
        ),
        (
            _order_snapshot,
            OpenOrderExposure("order", _instrument(), Decimal("100")),
            "remaining_quantity",
        ),
        (
            _quote_snapshot,
            MarketQuote(_instrument(), last=Decimal("100")),
            "last",
        ),
    ],
)
def test_snapshot_rejects_numerically_equal_noncanonical_decimal_state(
    factory: Callable[[object], object],
    record: object,
    field_name: str,
) -> None:
    object.__setattr__(record, field_name, Decimal("100.0"))
    with pytest.raises(TradingStateCorrespondenceError):
        factory([record])


def test_snapshot_validate_rejects_fabricated_timestamp_order_and_fingerprint() -> None:
    snapshot = _cash_snapshot(
        [CashBalance("USD", Decimal("1")), CashBalance("EUR", Decimal("2"))]
    )
    offset_time = _AS_OF.astimezone(timezone(timedelta(hours=8)))
    object.__setattr__(snapshot, "as_of", offset_time)
    with pytest.raises(TradingStateCorrespondenceError, match="UTC"):
        snapshot.to_dict()

    snapshot = _cash_snapshot(
        [CashBalance("USD", Decimal("1")), CashBalance("EUR", Decimal("2"))]
    )
    object.__setattr__(snapshot, "balances", tuple(reversed(snapshot.balances)))
    with pytest.raises(TradingStateCorrespondenceError, match="ordering"):
        snapshot.to_dict()

    snapshot = _cash_snapshot()
    object.__setattr__(snapshot, "fingerprint", "sha256:" + ("0" * 64))
    with pytest.raises(TradingStateCorrespondenceError, match="fingerprint"):
        snapshot.to_dict()


def test_snapshot_fingerprint_cannot_be_supplied() -> None:
    for model_type in (
        AccountCashSnapshot,
        PositionCollectionSnapshot,
        OpenOrderExposureSnapshot,
        MarketQuoteCollectionSnapshot,
    ):
        fingerprint_field = next(
            item for item in fields(model_type) if item.name == "fingerprint"
        )
        assert not fingerprint_field.init


@pytest.mark.parametrize(
    "age,expected",
    [
        (timedelta(0), SnapshotFreshness.FRESH),
        (timedelta(seconds=5), SnapshotFreshness.FRESH),
        (timedelta(seconds=5, microseconds=1), SnapshotFreshness.STALE),
    ],
)
def test_freshness_boundaries_are_exact(
    age: timedelta,
    expected: SnapshotFreshness,
) -> None:
    assert (
        evaluate_snapshot_freshness(
            _AS_OF,
            _AS_OF + age,
            timedelta(seconds=5),
        )
        is expected
    )


def test_freshness_future_offsets_and_invalid_duration() -> None:
    assert (
        evaluate_snapshot_freshness(
            _AS_OF + timedelta(microseconds=1),
            _AS_OF,
            timedelta(days=1),
        )
        is SnapshotFreshness.FUTURE_DATED
    )
    offset = timezone(timedelta(hours=8))
    assert (
        evaluate_snapshot_freshness(
            _AS_OF.astimezone(offset),
            _AS_OF,
            timedelta(0),
        )
        is SnapshotFreshness.FRESH
    )
    with pytest.raises(TradingStateValidationError, match="nonnegative"):
        evaluate_snapshot_freshness(_AS_OF, _AS_OF, timedelta(microseconds=-1))
    with pytest.raises(TypeError):
        evaluate_snapshot_freshness(_AS_OF, _AS_OF, 1)  # type: ignore[arg-type]


def test_skew_boundaries_singleton_and_order_neutrality() -> None:
    assert evaluate_snapshot_skew([_AS_OF], timedelta(0)) is SnapshotSkew.COHERENT
    later = _AS_OF + timedelta(seconds=5)
    for values in ([_AS_OF, later], (later, _AS_OF)):
        assert evaluate_snapshot_skew(values, timedelta(seconds=5)) is (
            SnapshotSkew.COHERENT
        )
        assert (
            evaluate_snapshot_skew(
                values,
                timedelta(seconds=5) - timedelta(microseconds=1),
            )
            is SnapshotSkew.EXCESSIVE_SKEW
        )


def test_skew_limits_offsets_and_invalid_inputs() -> None:
    offset = timezone(timedelta(hours=-5))
    assert (
        evaluate_snapshot_skew(
            [_AS_OF, _AS_OF.astimezone(offset)],
            timedelta(0),
        )
        is SnapshotSkew.COHERENT
    )
    assert evaluate_snapshot_skew([_AS_OF] * 32, timedelta(0)) is SnapshotSkew.COHERENT
    with pytest.raises(TradingStateValidationError, match="at least 1"):
        evaluate_snapshot_skew([], timedelta(0))
    with pytest.raises(TradingStateValidationError, match="maximum 32"):
        evaluate_snapshot_skew([_AS_OF] * 33, timedelta(0))
    with pytest.raises(TradingStateValidationError, match="nonnegative"):
        evaluate_snapshot_skew([_AS_OF], timedelta(microseconds=-1))


@pytest.mark.parametrize(
    "value",
    [
        _HostileList([_AS_OF]),
        _HostileTuple((_AS_OF,)),
        _HostileSequence(),
        iter((_AS_OF,)),
        (_AS_OF for _ in range(1)),
        {_AS_OF},
        {"time": _AS_OF},
        "time",
        b"time",
    ],
)
def test_skew_rejects_nonexact_containers_before_iteration(value: object) -> None:
    with pytest.raises(TypeError, match="exact built-in list or tuple"):
        evaluate_snapshot_skew(value, timedelta(0))  # type: ignore[arg-type]


def test_temporal_helpers_reject_naive_undefined_and_datetime_subclasses() -> None:
    class _DatetimeSubclass(datetime):
        pass

    invalid = (
        datetime(2026, 7, 31),
        datetime(2026, 7, 31, tzinfo=_UndefinedOffset()),
        _DatetimeSubclass(2026, 7, 31, tzinfo=UTC),
    )
    for value in invalid:
        with pytest.raises((TypeError, TradingStateValidationError)):
            evaluate_snapshot_freshness(value, _AS_OF, timedelta(0))
        with pytest.raises((TypeError, TradingStateValidationError)):
            evaluate_snapshot_skew([value], timedelta(0))


def test_released_trading_instrument_identity_fingerprint_is_unchanged() -> None:
    assert TradingInstrumentIdentity("AAPL", "NASDAQ").instrument_fingerprint == (
        "sha256:dc586683e7966f5f6a9060934d37a28a594fe22b6cd42f40b5f5228e13cba433"
    )


def test_package_has_no_bundle_atomicity_or_external_effect_surface() -> None:
    import market_platform.trading_state as trading_state

    assert not hasattr(trading_state, "TradingStateSnapshotBundle")
    for model_type in (
        AccountCashSnapshot,
        PositionCollectionSnapshot,
        OpenOrderExposureSnapshot,
        MarketQuoteCollectionSnapshot,
    ):
        names = {item.name for item in fields(model_type)}
        assert "is_atomic" not in names
        assert "captured_at" not in names
        assert "received_at" not in names
        assert "generated_at" not in names


def test_source_and_order_strings_remain_passive() -> None:
    source = _source("https://provider.example/path?key=value")
    exposure = OpenOrderExposure(
        "order:/path\\name?x=1",
        _instrument(),
        Decimal("1"),
    )
    assert source.source_id == "https://provider.example/path?key=value"
    assert exposure.external_order_id == "order:/path\\name?x=1"


def test_snapshot_revalidation_does_not_mask_unexpected_type_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = _cash_snapshot()

    def fail_normalization(_: object) -> tuple[CashBalance, ...]:
        raise TypeError("unexpected internal failure")

    monkeypatch.setattr(state_snapshots, "_normalize_balances", fail_normalization)
    with pytest.raises(TypeError, match="unexpected internal failure"):
        snapshot.to_dict()
