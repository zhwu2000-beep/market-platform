"""Declared structural capabilities for one opaque execution target.

Asset-class, trading-currency, and venue support are independent structural
domains in v1, and values across those domains are treated as structurally
composable. A profile is not proof of live broker capability or acceptance and
does not model asset/venue, currency/venue, or asset/currency/venue matrices,
product-specific restrictions, or account-specific restrictions.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import cast

from market_platform._fingerprint import canonical_fingerprint
from market_platform.execution_planning._canonical import required_retained_attribute
from market_platform.execution_planning.errors import (
    ExecutionPlanningCorrespondenceError,
    ExecutionPlanningValidationError,
)
from market_platform.execution_planning.order_style import OrderStyle
from market_platform.execution_planning.session_participation import (
    SessionParticipation,
)
from market_platform.execution_planning.time_in_force import TimeInForce
from market_platform.instruments import InstrumentAssetClass

BROKER_EXECUTION_CAPABILITY_PROFILE_SCHEMA = "broker_execution_capability_profile/v1"

_PROFILE_CREATION_SEAL = object()
_EXECUTION_TARGET_ID_PATTERN = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", flags=re.ASCII
)
_TRADING_CURRENCY_PATTERN = re.compile(r"[A-Z]{3}", flags=re.ASCII)

# Schema-owned v1 maps: later enum members do not become valid automatically.
_ASSET_CLASS_RANK = {
    InstrumentAssetClass.EQUITY: 0,
    InstrumentAssetClass.ETF: 1,
}
_ORDER_STYLE_RANK = {OrderStyle.MARKET: 0, OrderStyle.LIMIT: 1}
_TIME_IN_FORCE_RANK = {
    TimeInForce.DAY: 0,
    TimeInForce.GTC: 1,
    TimeInForce.IOC: 2,
    TimeInForce.FOK: 3,
}
_SESSION_PARTICIPATION_RANK = {
    SessionParticipation.REGULAR_ONLY: 0,
    SessionParticipation.REGULAR_AND_EXTENDED: 1,
}
_MAX_ORDER_COMBINATIONS = (
    len(_ORDER_STYLE_RANK) * len(_TIME_IN_FORCE_RANK) * len(_SESSION_PARTICIPATION_RANK)
)


@dataclass(frozen=True, slots=True, init=False)
class BrokerExecutionCapabilityProfile:
    """Declare bounded, independent structural support for an execution target.

    V1 treats supported asset classes, trading currencies, and venues as
    structurally composable independent domains. This value is not proof of
    live broker capability or acceptance and does not represent cross-domain,
    product-specific, or account-specific restrictions.
    """

    execution_target_id: str
    supported_asset_classes: tuple[InstrumentAssetClass, ...]
    supported_trading_currencies: tuple[str, ...]
    supported_venues: tuple[str, ...]
    supported_order_combinations: tuple[
        tuple[OrderStyle, TimeInForce, SessionParticipation], ...
    ]
    schema_version: str = field(init=False)
    fingerprint: str = field(init=False)

    def __init__(self) -> None:
        raise TypeError(
            "BrokerExecutionCapabilityProfile must be created by "
            "construct_broker_execution_capability_profile()"
        )

    @classmethod
    def _create(
        cls,
        *,
        execution_target_id: str,
        supported_asset_classes: tuple[InstrumentAssetClass, ...],
        supported_trading_currencies: tuple[str, ...],
        supported_venues: tuple[str, ...],
        supported_order_combinations: tuple[
            tuple[OrderStyle, TimeInForce, SessionParticipation], ...
        ],
        creation_seal: object,
    ) -> BrokerExecutionCapabilityProfile:
        if creation_seal is not _PROFILE_CREATION_SEAL:
            raise TypeError("capability profile construction is factory-owned")
        values = _validate_profile_values(
            execution_target_id=execution_target_id,
            supported_asset_classes=supported_asset_classes,
            supported_trading_currencies=supported_trading_currencies,
            supported_venues=supported_venues,
            supported_order_combinations=supported_order_combinations,
            retained=False,
        )
        result = object.__new__(cls)
        for name, value in (
            ("execution_target_id", values["execution_target_id"]),
            ("supported_asset_classes", values["supported_asset_classes"]),
            ("supported_trading_currencies", values["supported_trading_currencies"]),
            ("supported_venues", values["supported_venues"]),
            ("supported_order_combinations", values["supported_order_combinations"]),
            ("schema_version", BROKER_EXECUTION_CAPABILITY_PROFILE_SCHEMA),
        ):
            object.__setattr__(result, name, value)
        object.__setattr__(
            result,
            "fingerprint",
            canonical_fingerprint(result._fingerprint_payload()),
        )
        result._validate()
        return result

    def _fingerprint_payload(self) -> dict[str, object]:
        return _profile_payload(
            schema_version=self.schema_version,
            execution_target_id=self.execution_target_id,
            supported_asset_classes=self.supported_asset_classes,
            supported_trading_currencies=self.supported_trading_currencies,
            supported_venues=self.supported_venues,
            supported_order_combinations=self.supported_order_combinations,
        )

    def _validate(self) -> None:
        retained = {
            name: required_retained_attribute(
                self, name, "broker execution capability profile"
            )
            for name in (
                "execution_target_id",
                "supported_asset_classes",
                "supported_trading_currencies",
                "supported_venues",
                "supported_order_combinations",
                "schema_version",
                "fingerprint",
            )
        }
        values = _validate_profile_values(
            execution_target_id=retained["execution_target_id"],
            supported_asset_classes=retained["supported_asset_classes"],
            supported_trading_currencies=retained["supported_trading_currencies"],
            supported_venues=retained["supported_venues"],
            supported_order_combinations=retained["supported_order_combinations"],
            retained=True,
        )
        schema = retained["schema_version"]
        if (
            type(schema) is not str
            or schema != BROKER_EXECUTION_CAPABILITY_PROFILE_SCHEMA
        ):
            raise ExecutionPlanningCorrespondenceError(
                "capability profile schema_version is invalid"
            )
        expected = canonical_fingerprint(
            _profile_payload(
                schema_version=schema,
                execution_target_id=cast(str, values["execution_target_id"]),
                supported_asset_classes=cast(
                    tuple[InstrumentAssetClass, ...], values["supported_asset_classes"]
                ),
                supported_trading_currencies=cast(
                    tuple[str, ...], values["supported_trading_currencies"]
                ),
                supported_venues=cast(tuple[str, ...], values["supported_venues"]),
                supported_order_combinations=cast(
                    tuple[tuple[OrderStyle, TimeInForce, SessionParticipation], ...],
                    values["supported_order_combinations"],
                ),
            )
        )
        fingerprint = retained["fingerprint"]
        if type(fingerprint) is not str or fingerprint != expected:
            raise ExecutionPlanningCorrespondenceError(
                "capability profile fingerprint does not match content"
            )

    def to_dict(self) -> dict[str, object]:
        """Return the canonical JSON-safe structural capability projection."""

        self._validate()
        return {**self._fingerprint_payload(), "fingerprint": self.fingerprint}


def construct_broker_execution_capability_profile(
    *,
    execution_target_id: str,
    supported_asset_classes: tuple[InstrumentAssetClass, ...],
    supported_trading_currencies: tuple[str, ...],
    supported_venues: tuple[str, ...],
    supported_order_combinations: tuple[
        tuple[OrderStyle, TimeInForce, SessionParticipation], ...
    ],
) -> BrokerExecutionCapabilityProfile:
    """Construct one offline declaration of structural execution support."""

    return BrokerExecutionCapabilityProfile._create(
        execution_target_id=execution_target_id,
        supported_asset_classes=supported_asset_classes,
        supported_trading_currencies=supported_trading_currencies,
        supported_venues=supported_venues,
        supported_order_combinations=supported_order_combinations,
        creation_seal=_PROFILE_CREATION_SEAL,
    )


def _validate_profile_values(
    *,
    execution_target_id: object,
    supported_asset_classes: object,
    supported_trading_currencies: object,
    supported_venues: object,
    supported_order_combinations: object,
    retained: bool,
) -> dict[str, object]:
    _require_execution_target_id(execution_target_id, retained=retained)
    _require_asset_classes(supported_asset_classes, retained=retained)
    _require_canonical_strings(
        supported_trading_currencies,
        "supported_trading_currencies",
        _require_trading_currency,
        retained=retained,
    )
    _require_canonical_strings(
        supported_venues,
        "supported_venues",
        _require_canonical_venue,
        retained=retained,
    )
    _require_order_combinations(supported_order_combinations, retained=retained)
    return {
        "execution_target_id": execution_target_id,
        "supported_asset_classes": supported_asset_classes,
        "supported_trading_currencies": supported_trading_currencies,
        "supported_venues": supported_venues,
        "supported_order_combinations": supported_order_combinations,
    }


def _require_execution_target_id(value: object, *, retained: bool) -> None:
    if type(value) is not str or _EXECUTION_TARGET_ID_PATTERN.fullmatch(value) is None:
        _raise_invalid(
            "execution_target_id must match [A-Za-z0-9][A-Za-z0-9._-]{0,127}",
            retained=retained,
        )


def _require_asset_classes(value: object, *, retained: bool) -> None:
    if type(value) is not tuple or not value:
        _raise_invalid(
            "supported_asset_classes must be a nonempty exact tuple", retained=retained
        )
    items = cast(tuple[object, ...], value)
    if len(items) > len(_ASSET_CLASS_RANK):
        _raise_invalid(
            "supported_asset_classes exceeds the v1 domain", retained=retained
        )
    ranks: list[int] = []
    for item in items:
        if type(item) is not InstrumentAssetClass or item not in _ASSET_CLASS_RANK:
            _raise_invalid(
                "supported_asset_classes contains an invalid v1 asset class",
                retained=retained,
            )
        ranks.append(_ASSET_CLASS_RANK[cast(InstrumentAssetClass, item)])
    _require_increasing(
        ranks,
        "supported_asset_classes must use canonical order without duplicates",
        retained,
    )


def _require_canonical_strings(
    value: object,
    field_name: str,
    validator: Callable[..., None],
    *,
    retained: bool,
) -> None:
    if type(value) is not tuple or not value:
        _raise_invalid(
            f"{field_name} must be a nonempty exact tuple", retained=retained
        )
    items = cast(tuple[object, ...], value)
    validated: list[str] = []
    for item in items:
        validator(item, retained=retained)
        validated.append(cast(str, item))
    if tuple(validated) != tuple(sorted(validated)) or len(set(validated)) != len(
        validated
    ):
        _raise_invalid(
            f"{field_name} must use canonical order without duplicates",
            retained=retained,
        )


def _require_trading_currency(value: object, *, retained: bool) -> None:
    if type(value) is not str or _TRADING_CURRENCY_PATTERN.fullmatch(value) is None:
        _raise_invalid(
            "trading currency must match exact ASCII [A-Z]{3}", retained=retained
        )


def _require_canonical_venue(value: object, *, retained: bool) -> None:
    if (
        type(value) is not str
        or not value
        or value.strip() != value
        or value.upper() != value
        or any(character.isspace() for character in value)
    ):
        _raise_invalid(
            "venue must be an exact nonempty canonical uppercase value "
            "without whitespace",
            retained=retained,
        )


def _require_order_combinations(value: object, *, retained: bool) -> None:
    if type(value) is not tuple or not value:
        _raise_invalid(
            "supported_order_combinations must be a nonempty exact tuple",
            retained=retained,
        )
    combinations = cast(tuple[object, ...], value)
    if len(combinations) > _MAX_ORDER_COMBINATIONS:
        _raise_invalid(
            "supported_order_combinations exceeds the v1 Cartesian domain",
            retained=retained,
        )
    ranks: list[tuple[int, int, int]] = []
    for combination in combinations:
        if type(combination) is not tuple or len(combination) != 3:
            _raise_invalid(
                "each order combination must be an exact length-three tuple",
                retained=retained,
            )
        style, tif, session = cast(tuple[object, object, object], combination)
        if type(style) is not OrderStyle or style not in _ORDER_STYLE_RANK:
            _raise_invalid(
                "order combination style is invalid for v1", retained=retained
            )
        if type(tif) is not TimeInForce or tif not in _TIME_IN_FORCE_RANK:
            _raise_invalid("order combination TIF is invalid for v1", retained=retained)
        if (
            type(session) is not SessionParticipation
            or session not in _SESSION_PARTICIPATION_RANK
        ):
            _raise_invalid(
                "order combination session is invalid for v1", retained=retained
            )
        ranks.append(
            (
                _ORDER_STYLE_RANK[cast(OrderStyle, style)],
                _TIME_IN_FORCE_RANK[cast(TimeInForce, tif)],
                _SESSION_PARTICIPATION_RANK[cast(SessionParticipation, session)],
            )
        )
    _require_increasing(
        ranks,
        "supported_order_combinations must use canonical order without duplicates",
        retained,
    )


def _require_increasing(
    ranks: list[int] | list[tuple[int, int, int]], message: str, retained: bool
) -> None:
    if ranks != sorted(ranks) or len(set(ranks)) != len(ranks):
        _raise_invalid(message, retained=retained)


def _profile_payload(
    *,
    schema_version: str,
    execution_target_id: str,
    supported_asset_classes: tuple[InstrumentAssetClass, ...],
    supported_trading_currencies: tuple[str, ...],
    supported_venues: tuple[str, ...],
    supported_order_combinations: tuple[
        tuple[OrderStyle, TimeInForce, SessionParticipation], ...
    ],
) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "execution_target_id": execution_target_id,
        "supported_asset_classes": [item.value for item in supported_asset_classes],
        "supported_trading_currencies": list(supported_trading_currencies),
        "supported_venues": list(supported_venues),
        "supported_order_combinations": [
            {
                "order_style": style.value,
                "time_in_force": tif.value,
                "session_participation": session.value,
            }
            for style, tif, session in supported_order_combinations
        ],
    }


def _raise_invalid(message: str, *, retained: bool) -> None:
    if retained:
        raise ExecutionPlanningCorrespondenceError(message)
    raise ExecutionPlanningValidationError(message)


__all__ = [
    "BROKER_EXECUTION_CAPABILITY_PROFILE_SCHEMA",
    "BrokerExecutionCapabilityProfile",
    "construct_broker_execution_capability_profile",
]
