"""Explicit caller-authored limit-price choices."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Never, cast

from market_platform._fingerprint import canonical_fingerprint

from ._canonical import required_retained_attribute
from .errors import (
    ExecutionPlanningCorrespondenceError,
    ExecutionPlanningValidationError,
)

LIMIT_PRICE_CHOICE_SCHEMA = "limit_price_choice/v1"

_MAX_FIXED_POINT_CHARACTERS = 256
_MAX_DIGIT_CHARACTERS = 128
_MAX_FRACTIONAL_DIGITS = 64
_TRADING_CURRENCY_PATTERN = re.compile(r"[A-Z]{3}", flags=re.ASCII)


@dataclass(frozen=True, slots=True)
class LimitPriceChoice:
    """A canonical explicit limit price and trading-currency choice."""

    limit_price: Decimal
    trading_currency: str
    schema_version: str = field(init=False)
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        canonical_price, price_text = _canonical_price(self.limit_price, retained=False)
        canonical_currency = _canonical_currency(self.trading_currency, retained=False)
        object.__setattr__(self, "limit_price", canonical_price)
        object.__setattr__(self, "trading_currency", canonical_currency)
        object.__setattr__(self, "schema_version", LIMIT_PRICE_CHOICE_SCHEMA)
        object.__setattr__(
            self,
            "fingerprint",
            _fingerprint(price_text=price_text, trading_currency=canonical_currency),
        )
        self._validate()

    def to_dict(self) -> dict[str, object]:
        """Return the bounded canonical public projection."""

        retained, price_text = self._validate()
        return {
            "schema_version": retained["schema_version"],
            "limit_price": price_text,
            "trading_currency": retained["trading_currency"],
            "fingerprint": retained["fingerprint"],
        }

    def _validate(self) -> tuple[dict[str, object], str]:
        retained = {
            name: required_retained_attribute(self, name, "limit price choice")
            for name in (
                "limit_price",
                "trading_currency",
                "schema_version",
                "fingerprint",
            )
        }

        retained_price = retained["limit_price"]
        canonical_price, price_text = _canonical_price(retained_price, retained=True)
        if cast(Decimal, retained_price).as_tuple() != canonical_price.as_tuple():
            raise ExecutionPlanningCorrespondenceError(
                "retained limit price must already be canonical"
            )

        trading_currency = _canonical_currency(
            retained["trading_currency"], retained=True
        )
        schema_version = retained["schema_version"]
        if (
            type(schema_version) is not str
            or schema_version != LIMIT_PRICE_CHOICE_SCHEMA
        ):
            raise ExecutionPlanningCorrespondenceError(
                "retained limit price choice schema is not canonical"
            )
        expected_fingerprint = _fingerprint(
            price_text=price_text, trading_currency=trading_currency
        )
        fingerprint = retained["fingerprint"]
        if type(fingerprint) is not str or fingerprint != expected_fingerprint:
            raise ExecutionPlanningCorrespondenceError(
                "retained limit price choice fingerprint is not canonical"
            )
        return retained, price_text


def _canonical_price(value: object, *, retained: bool) -> tuple[Decimal, str]:
    if type(value) is not Decimal:
        _raise_price_error("limit price must be an exact Decimal", retained=retained)
    price = value
    if not price.is_finite():
        _raise_price_error("limit price must be finite", retained=retained)
    if price.is_zero() or price.is_signed():
        _raise_price_error("limit price must be strictly positive", retained=retained)

    digit_characters, fractional_digits, fixed_point_characters = _project_price_size(
        price
    )
    if digit_characters > _MAX_DIGIT_CHARACTERS:
        _raise_price_error(
            "limit price exceeds the digit-character bound", retained=retained
        )
    if fractional_digits > _MAX_FRACTIONAL_DIGITS:
        _raise_price_error(
            "limit price exceeds the fractional-digit bound", retained=retained
        )
    if fixed_point_characters > _MAX_FIXED_POINT_CHARACTERS:
        _raise_price_error(
            "limit price exceeds the fixed-point bound", retained=retained
        )

    text = format(price, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    canonical = Decimal(text)
    return canonical, text


def _project_price_size(value: Decimal) -> tuple[int, int, int]:
    decimal_tuple = value.as_tuple()
    digits = decimal_tuple.digits
    exponent = decimal_tuple.exponent
    if not isinstance(exponent, int):
        raise AssertionError("finite Decimal must have an integer exponent")

    trailing_zero_count = 0
    for digit in reversed(digits):
        if digit != 0:
            break
        trailing_zero_count += 1
    canonical_digit_count = len(digits) - trailing_zero_count
    canonical_exponent = exponent + trailing_zero_count
    if canonical_exponent >= 0:
        output_digit_count = canonical_digit_count + canonical_exponent
        return output_digit_count, 0, output_digit_count

    fractional_digit_count = -canonical_exponent
    decimal_position = canonical_digit_count + canonical_exponent
    integer_digit_count = max(decimal_position, 1)
    output_digit_count = integer_digit_count + fractional_digit_count
    return output_digit_count, fractional_digit_count, output_digit_count + 1


def _canonical_currency(value: object, *, retained: bool) -> str:
    if (
        type(value) is not str
        or _TRADING_CURRENCY_PATTERN.fullmatch(value) is None
    ):
        _raise_currency_error(
            "trading currency must be an exact uppercase three-letter ASCII string",
            retained=retained,
        )
    return value


def _fingerprint(*, price_text: str, trading_currency: str) -> str:
    return canonical_fingerprint(
        {
            "schema_version": LIMIT_PRICE_CHOICE_SCHEMA,
            "limit_price": price_text,
            "trading_currency": trading_currency,
        }
    )


def _raise_price_error(message: str, *, retained: bool) -> Never:
    if retained:
        raise ExecutionPlanningCorrespondenceError(message)
    raise ExecutionPlanningValidationError(message)


def _raise_currency_error(message: str, *, retained: bool) -> Never:
    if retained:
        raise ExecutionPlanningCorrespondenceError(message)
    raise ExecutionPlanningValidationError(message)


__all__ = ["LIMIT_PRICE_CHOICE_SCHEMA", "LimitPriceChoice"]
