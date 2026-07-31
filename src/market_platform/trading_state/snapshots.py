"""Immutable source-attributed trading-state collection snapshots."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, cast

from market_platform._fingerprint import canonical_fingerprint
from market_platform.trading_state._canonical import (
    canonical_timestamp,
    require_canonical_timestamp,
    require_exact_container,
    timestamp_text,
)
from market_platform.trading_state.errors import (
    TradingStateCorrespondenceError,
    TradingStateDuplicateError,
    TradingStateValidationError,
)
from market_platform.trading_state.identity import (
    StateSnapshotSourceIdentity,
    TradingAccountIdentity,
    require_account_correspondence,
    require_source_correspondence,
)
from market_platform.trading_state.records import (
    CashBalance,
    MarketQuote,
    OpenOrderExposure,
    PositionRecord,
    require_cash_balance_correspondence,
    require_market_quote_correspondence,
    require_open_order_correspondence,
    require_position_correspondence,
)

ACCOUNT_CASH_SNAPSHOT_SCHEMA_VERSION = "account_cash_snapshot/v1"
POSITION_COLLECTION_SNAPSHOT_SCHEMA_VERSION = "position_collection_snapshot/v1"
OPEN_ORDER_EXPOSURE_SNAPSHOT_SCHEMA_VERSION = "open_order_exposure_snapshot/v1"
MARKET_QUOTE_COLLECTION_SNAPSHOT_SCHEMA_VERSION = "market_quote_collection_snapshot/v1"

_CASH_BALANCE_LIMIT = 32
_POSITION_LIMIT = 10_000
_OPEN_ORDER_EXPOSURE_LIMIT = 10_000
_MARKET_QUOTE_LIMIT = 10_000


class _Projectable(Protocol):
    def to_dict(self) -> dict[str, object]:
        """Return a deterministic projection."""


@dataclass(frozen=True, slots=True)
class AccountCashSnapshot:
    """Exact source-reported cash balances for one account."""

    account: TradingAccountIdentity
    source: StateSnapshotSourceIdentity
    as_of: datetime
    balances: list[CashBalance] | tuple[CashBalance, ...]
    schema_version: str = field(
        init=False,
        default=ACCOUNT_CASH_SNAPSHOT_SCHEMA_VERSION,
    )
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        _require_identity_types(self.account, self.source)
        require_account_correspondence(self.account)
        require_source_correspondence(self.source)
        as_of = canonical_timestamp(self.as_of, "as_of")
        balances = _normalize_balances(self.balances)
        object.__setattr__(self, "as_of", as_of)
        object.__setattr__(self, "balances", balances)
        object.__setattr__(
            self,
            "fingerprint",
            canonical_fingerprint(self._fingerprint_payload()),
        )

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "account": self.account.to_dict(),
            "source": self.source.to_dict(),
            "as_of": timestamp_text(self.as_of),
            "balances": [balance.to_dict() for balance in self.balances],
        }

    def _validate(self) -> None:
        _validate_snapshot_header(
            self.schema_version,
            ACCOUNT_CASH_SNAPSHOT_SCHEMA_VERSION,
            self.account,
            self.source,
            self.as_of,
        )
        canonical = _corresponding_records(
            self.balances,
            CashBalance,
            _normalize_balances,
            "balances",
        )
        _require_record_projection_order(self.balances, canonical, "balances")
        _require_snapshot_fingerprint(self, self._fingerprint_payload())

    def to_dict(self) -> dict[str, object]:
        """Return the bounded deterministic JSON-safe cash snapshot."""

        self._validate()
        return {
            **self._fingerprint_payload(),
            "fingerprint": self.fingerprint,
        }


@dataclass(frozen=True, slots=True)
class PositionCollectionSnapshot:
    """Exact source-reported nonzero positions for one account."""

    account: TradingAccountIdentity
    source: StateSnapshotSourceIdentity
    as_of: datetime
    positions: list[PositionRecord] | tuple[PositionRecord, ...]
    schema_version: str = field(
        init=False,
        default=POSITION_COLLECTION_SNAPSHOT_SCHEMA_VERSION,
    )
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        _require_identity_types(self.account, self.source)
        require_account_correspondence(self.account)
        require_source_correspondence(self.source)
        as_of = canonical_timestamp(self.as_of, "as_of")
        positions = _normalize_positions(self.positions)
        object.__setattr__(self, "as_of", as_of)
        object.__setattr__(self, "positions", positions)
        object.__setattr__(
            self,
            "fingerprint",
            canonical_fingerprint(self._fingerprint_payload()),
        )

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "account": self.account.to_dict(),
            "source": self.source.to_dict(),
            "as_of": timestamp_text(self.as_of),
            "positions": [position.to_dict() for position in self.positions],
        }

    def _validate(self) -> None:
        _validate_snapshot_header(
            self.schema_version,
            POSITION_COLLECTION_SNAPSHOT_SCHEMA_VERSION,
            self.account,
            self.source,
            self.as_of,
        )
        canonical = _corresponding_records(
            self.positions,
            PositionRecord,
            _normalize_positions,
            "positions",
        )
        _require_record_projection_order(
            self.positions,
            canonical,
            "positions",
        )
        _require_snapshot_fingerprint(self, self._fingerprint_payload())

    def to_dict(self) -> dict[str, object]:
        """Return the bounded deterministic JSON-safe position snapshot."""

        self._validate()
        return {
            **self._fingerprint_payload(),
            "fingerprint": self.fingerprint,
        }


@dataclass(frozen=True, slots=True)
class OpenOrderExposureSnapshot:
    """Exact source-reported pending order exposure for one account."""

    account: TradingAccountIdentity
    source: StateSnapshotSourceIdentity
    as_of: datetime
    exposures: list[OpenOrderExposure] | tuple[OpenOrderExposure, ...]
    schema_version: str = field(
        init=False,
        default=OPEN_ORDER_EXPOSURE_SNAPSHOT_SCHEMA_VERSION,
    )
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        _require_identity_types(self.account, self.source)
        require_account_correspondence(self.account)
        require_source_correspondence(self.source)
        as_of = canonical_timestamp(self.as_of, "as_of")
        exposures = _normalize_exposures(self.exposures)
        object.__setattr__(self, "as_of", as_of)
        object.__setattr__(self, "exposures", exposures)
        object.__setattr__(
            self,
            "fingerprint",
            canonical_fingerprint(self._fingerprint_payload()),
        )

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "account": self.account.to_dict(),
            "source": self.source.to_dict(),
            "as_of": timestamp_text(self.as_of),
            "exposures": [exposure.to_dict() for exposure in self.exposures],
        }

    def _validate(self) -> None:
        _validate_snapshot_header(
            self.schema_version,
            OPEN_ORDER_EXPOSURE_SNAPSHOT_SCHEMA_VERSION,
            self.account,
            self.source,
            self.as_of,
        )
        canonical = _corresponding_records(
            self.exposures,
            OpenOrderExposure,
            _normalize_exposures,
            "exposures",
        )
        _require_record_projection_order(
            self.exposures,
            canonical,
            "exposures",
        )
        _require_snapshot_fingerprint(self, self._fingerprint_payload())

    def to_dict(self) -> dict[str, object]:
        """Return the bounded deterministic JSON-safe exposure snapshot."""

        self._validate()
        return {
            **self._fingerprint_payload(),
            "fingerprint": self.fingerprint,
        }


@dataclass(frozen=True, slots=True)
class MarketQuoteCollectionSnapshot:
    """Exact source-reported quotes independent of any account."""

    source: StateSnapshotSourceIdentity
    as_of: datetime
    quotes: list[MarketQuote] | tuple[MarketQuote, ...]
    schema_version: str = field(
        init=False,
        default=MARKET_QUOTE_COLLECTION_SNAPSHOT_SCHEMA_VERSION,
    )
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if type(self.source) is not StateSnapshotSourceIdentity:
            raise TypeError("source must be a StateSnapshotSourceIdentity")
        require_source_correspondence(self.source)
        as_of = canonical_timestamp(self.as_of, "as_of")
        quotes = _normalize_quotes(self.quotes)
        object.__setattr__(self, "as_of", as_of)
        object.__setattr__(self, "quotes", quotes)
        object.__setattr__(
            self,
            "fingerprint",
            canonical_fingerprint(self._fingerprint_payload()),
        )

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "source": self.source.to_dict(),
            "as_of": timestamp_text(self.as_of),
            "quotes": [quote.to_dict() for quote in self.quotes],
        }

    def _validate(self) -> None:
        if self.schema_version != MARKET_QUOTE_COLLECTION_SNAPSHOT_SCHEMA_VERSION:
            raise TradingStateCorrespondenceError(
                "market quote snapshot schema_version is invalid"
            )
        require_source_correspondence(self.source)
        _require_snapshot_timestamp(self.as_of)
        canonical = _corresponding_records(
            self.quotes,
            MarketQuote,
            _normalize_quotes,
            "quotes",
        )
        _require_record_projection_order(self.quotes, canonical, "quotes")
        _require_snapshot_fingerprint(self, self._fingerprint_payload())

    def to_dict(self) -> dict[str, object]:
        """Return the bounded deterministic JSON-safe quote snapshot."""

        self._validate()
        return {
            **self._fingerprint_payload(),
            "fingerprint": self.fingerprint,
        }


def _require_identity_types(
    account: object,
    source: object,
) -> None:
    if type(account) is not TradingAccountIdentity:
        raise TypeError("account must be a TradingAccountIdentity")
    if type(source) is not StateSnapshotSourceIdentity:
        raise TypeError("source must be a StateSnapshotSourceIdentity")


def _validate_snapshot_header(
    schema_version: object,
    expected_schema: str,
    account: object,
    source: object,
    as_of: object,
) -> None:
    if schema_version != expected_schema:
        raise TradingStateCorrespondenceError("snapshot schema_version is invalid")
    require_account_correspondence(account)
    require_source_correspondence(source)
    _require_snapshot_timestamp(as_of)


def _require_snapshot_timestamp(value: object) -> datetime:
    try:
        return require_canonical_timestamp(value, "as_of")
    except (TypeError, TradingStateValidationError) as error:
        raise TradingStateCorrespondenceError(
            "snapshot as_of must retain canonical UTC state"
        ) from error


def _normalize_balances(
    value: object,
) -> tuple[CashBalance, ...]:
    records = require_exact_container(
        value,
        "balances",
        _CASH_BALANCE_LIMIT,
    )
    validated: list[CashBalance] = []
    for record in records:
        if type(record) is not CashBalance:
            raise TypeError("every balance must be a CashBalance")
        validated.append(require_cash_balance_correspondence(record))
    ordered = tuple(sorted(validated, key=lambda record: record.currency))
    _reject_duplicate_keys(
        ordered,
        lambda record: record.currency,
        "balances",
        "currency",
    )
    return ordered


def _normalize_positions(
    value: object,
) -> tuple[PositionRecord, ...]:
    records = require_exact_container(value, "positions", _POSITION_LIMIT)
    validated: list[PositionRecord] = []
    for record in records:
        if type(record) is not PositionRecord:
            raise TypeError("every position must be a PositionRecord")
        validated.append(require_position_correspondence(record))
    ordered = tuple(
        sorted(
            validated,
            key=lambda record: record.instrument_id.instrument_id,
        )
    )
    _reject_duplicate_keys(
        ordered,
        lambda record: record.instrument_id.instrument_id,
        "positions",
        "instrument_id",
    )
    return ordered


def _normalize_exposures(
    value: object,
) -> tuple[OpenOrderExposure, ...]:
    records = require_exact_container(
        value,
        "exposures",
        _OPEN_ORDER_EXPOSURE_LIMIT,
    )
    validated: list[OpenOrderExposure] = []
    for record in records:
        if type(record) is not OpenOrderExposure:
            raise TypeError("every exposure must be an OpenOrderExposure")
        validated.append(require_open_order_correspondence(record))
    ordered = tuple(
        sorted(
            validated,
            key=lambda record: (
                record.external_order_id,
                record.instrument_id.instrument_id,
            ),
        )
    )
    _reject_duplicate_keys(
        ordered,
        lambda record: record.external_order_id,
        "exposures",
        "external_order_id",
    )
    return ordered


def _normalize_quotes(
    value: object,
) -> tuple[MarketQuote, ...]:
    records = require_exact_container(value, "quotes", _MARKET_QUOTE_LIMIT)
    validated: list[MarketQuote] = []
    for record in records:
        if type(record) is not MarketQuote:
            raise TypeError("every quote must be a MarketQuote")
        validated.append(require_market_quote_correspondence(record))
    ordered = tuple(
        sorted(
            validated,
            key=lambda record: record.instrument_id.instrument_id,
        )
    )
    _reject_duplicate_keys(
        ordered,
        lambda record: record.instrument_id.instrument_id,
        "quotes",
        "instrument_id",
    )
    return ordered


def _reject_duplicate_keys[RecordT](
    records: tuple[RecordT, ...],
    key: Callable[[RecordT], str],
    field_name: str,
    key_name: str,
) -> None:
    previous: object = object()
    for record in records:
        current = key(record)
        if current == previous:
            raise TradingStateDuplicateError(
                f"{field_name} contains duplicate {key_name} {current}"
            )
        previous = current


def _corresponding_records[RecordT](
    records: object,
    expected_type: type[RecordT],
    normalize: Callable[[object], tuple[RecordT, ...]],
    field_name: str,
) -> tuple[RecordT, ...]:
    if type(records) is not tuple:
        raise TradingStateCorrespondenceError(
            f"snapshot {field_name} must be physically stored as a tuple"
        )
    retained = cast("tuple[object, ...]", records)
    if any(type(record) is not expected_type for record in retained):
        raise TradingStateCorrespondenceError(
            f"snapshot {field_name} contains an invalid record type"
        )
    try:
        return normalize(records)
    except TradingStateValidationError as error:
        raise TradingStateCorrespondenceError(
            f"snapshot {field_name} state is not canonical"
        ) from error


def _require_record_projection_order[RecordT: _Projectable](
    actual: object,
    expected: tuple[RecordT, ...],
    field_name: str,
) -> None:
    if type(actual) is not tuple:
        raise TradingStateCorrespondenceError(
            f"snapshot {field_name} must be physically stored as a tuple"
        )
    actual_records = cast("tuple[_Projectable, ...]", actual)
    actual_projections = tuple(item.to_dict() for item in actual_records)
    expected_projections = tuple(item.to_dict() for item in expected)
    if actual_projections != expected_projections:
        raise TradingStateCorrespondenceError(
            f"snapshot {field_name} ordering is not canonical"
        )


def _require_snapshot_fingerprint(
    snapshot: object,
    payload: dict[str, object],
) -> None:
    expected = canonical_fingerprint(payload)
    if getattr(snapshot, "fingerprint", None) != expected:
        raise TradingStateCorrespondenceError(
            "snapshot fingerprint does not match content"
        )


__all__ = [
    "ACCOUNT_CASH_SNAPSHOT_SCHEMA_VERSION",
    "MARKET_QUOTE_COLLECTION_SNAPSHOT_SCHEMA_VERSION",
    "OPEN_ORDER_EXPOSURE_SNAPSHOT_SCHEMA_VERSION",
    "POSITION_COLLECTION_SNAPSHOT_SCHEMA_VERSION",
    "AccountCashSnapshot",
    "MarketQuoteCollectionSnapshot",
    "OpenOrderExposureSnapshot",
    "PositionCollectionSnapshot",
]
