"""Passive nested records retained by trading-state snapshots."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from market_platform.instruments import (
    CanonicalInstrumentId,
    InstrumentValidationError,
)
from market_platform.trading_state._canonical import (
    canonical_decimal,
    require_canonical_decimal,
    require_pattern_text,
    require_visible_ascii,
)
from market_platform.trading_state.errors import (
    TradingStateCorrespondenceError,
    TradingStateValidationError,
)

_CURRENCY_PATTERN = re.compile(r"[A-Z]{3}", flags=re.ASCII)


@dataclass(frozen=True, slots=True)
class CashBalance:
    """One exact signed cash balance in one currency."""

    currency: str
    amount: Decimal

    def __post_init__(self) -> None:
        currency = require_pattern_text(
            self.currency,
            "currency",
            _CURRENCY_PATTERN,
            "[A-Z]{3}",
        )
        amount, _ = canonical_decimal(
            self.amount,
            "amount",
            allow_negative=True,
            allow_zero=True,
        )
        object.__setattr__(self, "currency", currency)
        object.__setattr__(self, "amount", amount)

    def to_dict(self) -> dict[str, object]:
        """Return the bounded nested cash projection."""

        _, text = require_canonical_decimal(
            self.amount,
            "amount",
            allow_negative=True,
            allow_zero=True,
        )
        return {"currency": self.currency, "amount": text}


@dataclass(frozen=True, slots=True)
class PositionRecord:
    """One exact nonzero signed position keyed by stable instrument ID."""

    instrument_id: CanonicalInstrumentId
    quantity: Decimal

    def __post_init__(self) -> None:
        if type(self.instrument_id) is not CanonicalInstrumentId:
            raise TypeError("instrument_id must be a CanonicalInstrumentId")
        require_instrument_id_correspondence(self.instrument_id)
        quantity, _ = canonical_decimal(
            self.quantity,
            "quantity",
            allow_negative=True,
            allow_zero=False,
        )
        object.__setattr__(self, "quantity", quantity)

    def to_dict(self) -> dict[str, object]:
        """Return the bounded nested position projection."""

        _, text = require_canonical_decimal(
            self.quantity,
            "quantity",
            allow_negative=True,
            allow_zero=False,
        )
        return {
            "instrument_id": self.instrument_id.to_dict(),
            "quantity": text,
        }


@dataclass(frozen=True, slots=True)
class OpenOrderExposure:
    """One exact nonzero pending buy or sell exposure."""

    external_order_id: str
    instrument_id: CanonicalInstrumentId
    remaining_quantity: Decimal

    def __post_init__(self) -> None:
        order_id = require_visible_ascii(
            self.external_order_id,
            "external_order_id",
            128,
        )
        if type(self.instrument_id) is not CanonicalInstrumentId:
            raise TypeError("instrument_id must be a CanonicalInstrumentId")
        require_instrument_id_correspondence(self.instrument_id)
        quantity, _ = canonical_decimal(
            self.remaining_quantity,
            "remaining_quantity",
            allow_negative=True,
            allow_zero=False,
        )
        object.__setattr__(self, "external_order_id", order_id)
        object.__setattr__(self, "remaining_quantity", quantity)

    def to_dict(self) -> dict[str, object]:
        """Return the bounded nested open-order exposure projection."""

        _, text = require_canonical_decimal(
            self.remaining_quantity,
            "remaining_quantity",
            allow_negative=True,
            allow_zero=False,
        )
        return {
            "external_order_id": self.external_order_id,
            "instrument_id": self.instrument_id.to_dict(),
            "remaining_quantity": text,
        }


@dataclass(frozen=True, slots=True)
class MarketQuote:
    """One partial or complete exact market quote."""

    instrument_id: CanonicalInstrumentId
    bid: Decimal | None = None
    ask: Decimal | None = None
    last: Decimal | None = None

    def __post_init__(self) -> None:
        if type(self.instrument_id) is not CanonicalInstrumentId:
            raise TypeError("instrument_id must be a CanonicalInstrumentId")
        require_instrument_id_correspondence(self.instrument_id)
        bid = _optional_price(self.bid, "bid")
        ask = _optional_price(self.ask, "ask")
        last = _optional_price(self.last, "last")
        if bid is None and ask is None and last is None:
            raise TradingStateValidationError("market quote requires bid, ask, or last")
        if bid is not None and ask is not None and bid > ask:
            raise TradingStateValidationError("market quote bid must not exceed ask")
        object.__setattr__(self, "bid", bid)
        object.__setattr__(self, "ask", ask)
        object.__setattr__(self, "last", last)

    def to_dict(self) -> dict[str, object]:
        """Return the bounded nested market-quote projection."""

        return {
            "instrument_id": self.instrument_id.to_dict(),
            "bid": _optional_price_text(self.bid, "bid"),
            "ask": _optional_price_text(self.ask, "ask"),
            "last": _optional_price_text(self.last, "last"),
        }


def require_instrument_id_correspondence(
    instrument_id: object,
) -> CanonicalInstrumentId:
    """Require exact public-constructor canonical instrument ID state."""

    if type(instrument_id) is not CanonicalInstrumentId:
        raise TradingStateCorrespondenceError("instrument_id has invalid runtime type")
    try:
        reconstructed = CanonicalInstrumentId(instrument_id.instrument_id)
    except (TypeError, InstrumentValidationError) as error:
        raise TradingStateCorrespondenceError(
            "instrument_id cannot be reconstructed canonically"
        ) from error
    if (
        instrument_id.instrument_id != reconstructed.instrument_id
        or instrument_id.to_dict() != reconstructed.to_dict()
    ):
        raise TradingStateCorrespondenceError(
            "instrument_id does not match canonical reconstructed state"
        )
    return instrument_id


def require_cash_balance_correspondence(value: object) -> CashBalance:
    """Require exact public-constructor cash balance state."""

    if type(value) is not CashBalance:
        raise TradingStateCorrespondenceError("cash balance has invalid runtime type")
    try:
        reconstructed = CashBalance(value.currency, value.amount)
    except (TypeError, TradingStateValidationError) as error:
        raise TradingStateCorrespondenceError(
            "cash balance cannot be reconstructed canonically"
        ) from error
    if (
        value.currency != reconstructed.currency
        or value.amount.as_tuple() != reconstructed.amount.as_tuple()
        or value.to_dict() != reconstructed.to_dict()
    ):
        raise TradingStateCorrespondenceError(
            "cash balance does not match canonical reconstructed state"
        )
    return value


def require_position_correspondence(value: object) -> PositionRecord:
    """Require exact public-constructor position record state."""

    if type(value) is not PositionRecord:
        raise TradingStateCorrespondenceError("position has invalid runtime type")
    try:
        reconstructed = PositionRecord(value.instrument_id, value.quantity)
    except (
        TypeError,
        TradingStateValidationError,
        TradingStateCorrespondenceError,
    ) as error:
        raise TradingStateCorrespondenceError(
            "position cannot be reconstructed canonically"
        ) from error
    if (
        value.instrument_id.to_dict() != reconstructed.instrument_id.to_dict()
        or value.quantity.as_tuple() != reconstructed.quantity.as_tuple()
        or value.to_dict() != reconstructed.to_dict()
    ):
        raise TradingStateCorrespondenceError(
            "position does not match canonical reconstructed state"
        )
    return value


def require_open_order_correspondence(
    value: object,
) -> OpenOrderExposure:
    """Require exact public-constructor open-order exposure state."""

    if type(value) is not OpenOrderExposure:
        raise TradingStateCorrespondenceError(
            "open-order exposure has invalid runtime type"
        )
    try:
        reconstructed = OpenOrderExposure(
            value.external_order_id,
            value.instrument_id,
            value.remaining_quantity,
        )
    except (
        TypeError,
        TradingStateValidationError,
        TradingStateCorrespondenceError,
    ) as error:
        raise TradingStateCorrespondenceError(
            "open-order exposure cannot be reconstructed canonically"
        ) from error
    if (
        value.external_order_id != reconstructed.external_order_id
        or value.instrument_id.to_dict() != reconstructed.instrument_id.to_dict()
        or value.remaining_quantity.as_tuple()
        != reconstructed.remaining_quantity.as_tuple()
        or value.to_dict() != reconstructed.to_dict()
    ):
        raise TradingStateCorrespondenceError(
            "open-order exposure does not match canonical reconstructed state"
        )
    return value


def require_market_quote_correspondence(value: object) -> MarketQuote:
    """Require exact public-constructor market quote state."""

    if type(value) is not MarketQuote:
        raise TradingStateCorrespondenceError("market quote has invalid runtime type")
    try:
        reconstructed = MarketQuote(
            instrument_id=value.instrument_id,
            bid=value.bid,
            ask=value.ask,
            last=value.last,
        )
    except (
        TypeError,
        TradingStateValidationError,
        TradingStateCorrespondenceError,
    ) as error:
        raise TradingStateCorrespondenceError(
            "market quote cannot be reconstructed canonically"
        ) from error
    if (
        value.instrument_id.to_dict() != reconstructed.instrument_id.to_dict()
        or not _optional_decimal_tuple_equal(value.bid, reconstructed.bid)
        or not _optional_decimal_tuple_equal(value.ask, reconstructed.ask)
        or not _optional_decimal_tuple_equal(value.last, reconstructed.last)
        or value.to_dict() != reconstructed.to_dict()
    ):
        raise TradingStateCorrespondenceError(
            "market quote does not match canonical reconstructed state"
        )
    return value


def _optional_price(value: object, field_name: str) -> Decimal | None:
    if value is None:
        return None
    canonical, _ = canonical_decimal(
        value,
        field_name,
        allow_negative=False,
        allow_zero=False,
    )
    return canonical


def _optional_price_text(
    value: Decimal | None,
    field_name: str,
) -> str | None:
    if value is None:
        return None
    _, text = require_canonical_decimal(
        value,
        field_name,
        allow_negative=False,
        allow_zero=False,
    )
    return text


def _optional_decimal_tuple_equal(
    left: Decimal | None,
    right: Decimal | None,
) -> bool:
    if left is None or right is None:
        return left is right
    return left.as_tuple() == right.as_tuple()


__all__ = [
    "CashBalance",
    "MarketQuote",
    "OpenOrderExposure",
    "PositionRecord",
]
