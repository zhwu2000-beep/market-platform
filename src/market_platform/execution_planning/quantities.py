"""Exact bounded fixed-point arithmetic for position translation."""

from __future__ import annotations

from decimal import Decimal
from typing import cast

from market_platform.execution_planning.errors import (
    ExecutionPlanningCorrespondenceError,
    ExecutionPlanningUnavailableError,
    ExecutionPlanningValidationError,
)

OPERAND_DIGIT_LIMIT = 128
OPERAND_FRACTIONAL_DIGIT_LIMIT = 64
OPERAND_TEXT_LIMIT = 256
DELTA_DIGIT_LIMIT = 129
DELTA_FRACTIONAL_DIGIT_LIMIT = 64
DELTA_TEXT_LIMIT = 258


def canonical_source_quantity(
    value: object,
    field_name: str,
    *,
    allow_negative: bool,
) -> tuple[Decimal, str]:
    """Canonicalize a released operand or report v0.60 resource unavailability."""

    return _canonical_quantity(
        value,
        field_name,
        allow_negative=allow_negative,
        digit_limit=OPERAND_DIGIT_LIMIT,
        fractional_limit=OPERAND_FRACTIONAL_DIGIT_LIMIT,
        text_limit=OPERAND_TEXT_LIMIT,
        bounds_error=ExecutionPlanningUnavailableError,
    )


def require_retained_quantity(
    value: object,
    field_name: str,
    *,
    delta: bool = False,
) -> tuple[Decimal, str]:
    """Require exact canonical quantity state retained by a translation."""

    digit_limit = DELTA_DIGIT_LIMIT if delta else OPERAND_DIGIT_LIMIT
    text_limit = DELTA_TEXT_LIMIT if delta else OPERAND_TEXT_LIMIT
    try:
        canonical, text = _canonical_quantity(
            value,
            field_name,
            allow_negative=True,
            digit_limit=digit_limit,
            fractional_limit=DELTA_FRACTIONAL_DIGIT_LIMIT,
            text_limit=text_limit,
            bounds_error=ExecutionPlanningCorrespondenceError,
        )
    except ExecutionPlanningValidationError as error:
        raise ExecutionPlanningCorrespondenceError(
            f"{field_name} retains invalid canonical state"
        ) from error
    retained = cast(Decimal, value)
    if retained.as_tuple() != canonical.as_tuple():
        raise ExecutionPlanningCorrespondenceError(
            f"{field_name} does not retain canonical Decimal state"
        )
    return canonical, text


def exact_subtract(target: Decimal, current: Decimal) -> tuple[Decimal, str]:
    """Subtract bounded fixed-point operands without ambient Decimal context."""

    target_coefficient, target_scale = _integer_and_scale(target)
    current_coefficient, current_scale = _integer_and_scale(current)
    result_scale = max(target_scale, current_scale)
    result_coefficient = (
        target_coefficient * (10 ** (result_scale - target_scale))
        - current_coefficient * (10 ** (result_scale - current_scale))
    )
    while result_coefficient and result_scale and result_coefficient % 10 == 0:
        result_coefficient //= 10
        result_scale -= 1
    result = _decimal_from_integer_and_scale(result_coefficient, result_scale)
    return _canonical_quantity(
        result,
        "delta_quantity",
        allow_negative=True,
        digit_limit=DELTA_DIGIT_LIMIT,
        fractional_limit=DELTA_FRACTIONAL_DIGIT_LIMIT,
        text_limit=DELTA_TEXT_LIMIT,
        bounds_error=ExecutionPlanningUnavailableError,
    )


def signed_target_quantity(direction: str, magnitude: Decimal) -> Decimal:
    """Apply one released target direction without Decimal arithmetic."""

    if direction == "flat":
        return Decimal("0")
    decimal_tuple = magnitude.as_tuple()
    exponent = decimal_tuple.exponent
    if not isinstance(exponent, int):
        raise ExecutionPlanningCorrespondenceError("target quantity is not finite")
    if direction == "long":
        return Decimal((0, decimal_tuple.digits, exponent))
    if direction == "short":
        return Decimal((1, decimal_tuple.digits, exponent))
    raise ExecutionPlanningCorrespondenceError("target direction is invalid")


def quantity_sign(value: Decimal) -> int:
    """Return -1, 0, or 1 from exact Decimal tuple state."""

    if value.is_zero():
        return 0
    return -1 if value.is_signed() else 1


def _canonical_quantity(
    value: object,
    field_name: str,
    *,
    allow_negative: bool,
    digit_limit: int,
    fractional_limit: int,
    text_limit: int,
    bounds_error: type[Exception],
) -> tuple[Decimal, str]:
    if type(value) is not Decimal:
        raise ExecutionPlanningValidationError(f"{field_name} must be a Decimal")
    decimal_value = value
    if not decimal_value.is_finite():
        raise ExecutionPlanningValidationError(f"{field_name} must be finite")
    if decimal_value.is_zero():
        if decimal_value.is_signed():
            raise ExecutionPlanningValidationError(
                f"{field_name} must not be negative zero"
            )
        return Decimal("0"), "0"
    if decimal_value.is_signed() and not allow_negative:
        raise ExecutionPlanningValidationError(
            f"{field_name} must not be negative"
        )
    digits, fractional, text_length = _project_size(decimal_value)
    if digits > digit_limit:
        raise bounds_error(f"{field_name} exceeds digit maximum {digit_limit}")
    if fractional > fractional_limit:
        raise bounds_error(
            f"{field_name} exceeds fractional digit maximum {fractional_limit}"
        )
    if text_length > text_limit:
        raise bounds_error(f"{field_name} exceeds text maximum {text_limit}")
    text = format(decimal_value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    canonical = Decimal(text)
    return canonical, text


def _project_size(value: Decimal) -> tuple[int, int, int]:
    state = value.as_tuple()
    exponent = state.exponent
    if not isinstance(exponent, int):
        raise ExecutionPlanningValidationError("quantity must be finite")
    trailing = 0
    for digit in reversed(state.digits):
        if digit:
            break
        trailing += 1
    significant = len(state.digits) - trailing
    canonical_exponent = exponent + trailing
    if canonical_exponent >= 0:
        digits = significant + canonical_exponent
        fractional = 0
        text_length = digits
    else:
        fractional = -canonical_exponent
        integer_digits = max(significant + canonical_exponent, 1)
        digits = integer_digits + fractional
        text_length = digits + 1
    if value.is_signed():
        text_length += 1
    return digits, fractional, text_length


def _integer_and_scale(value: Decimal) -> tuple[int, int]:
    state = value.as_tuple()
    exponent = state.exponent
    if not isinstance(exponent, int):
        raise ExecutionPlanningCorrespondenceError("quantity is not finite")
    coefficient = 0
    for digit in state.digits:
        coefficient = coefficient * 10 + digit
    if state.sign:
        coefficient = -coefficient
    if exponent >= 0:
        return coefficient * (10**exponent), 0
    return coefficient, -exponent


def _decimal_from_integer_and_scale(coefficient: int, scale: int) -> Decimal:
    if coefficient == 0:
        return Decimal("0")
    magnitude = abs(coefficient)
    digits = tuple(int(character) for character in str(magnitude))
    return Decimal((1 if coefficient < 0 else 0, digits, -scale))


__all__: list[str] = []
