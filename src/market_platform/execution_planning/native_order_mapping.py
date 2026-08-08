"""Pure broker-native semantic mapping without broker integration.

Native tokens are bounded opaque adapter vocabulary. The platform validates
their shape and all independently reconstructible source correspondence, but
their target meaning remains a mapper-conformance responsibility. Successful
mapping is not authorization, submission, broker acceptance, or proof that a
mapper implementation is correct.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol, cast, runtime_checkable

from market_platform._fingerprint import canonical_fingerprint
from market_platform.execution_planning._canonical import (
    required_fingerprint,
    required_retained_attribute,
)
from market_platform.execution_planning.capability import (
    BrokerExecutionCapabilityProfile,
)
from market_platform.execution_planning.compatibility import (
    BrokerExecutionStructuralCompatibilityOutcome,
    BrokerExecutionStructuralCompatibilityResult,
)
from market_platform.execution_planning.errors import (
    ExecutionPlanningCorrespondenceError,
    ExecutionPlanningValidationError,
)
from market_platform.execution_planning.limit_price import (
    _canonical_currency,
    _canonical_price,
)
from market_platform.execution_planning.order_specification import (
    BrokerNeutralOrderSpecification,
)
from market_platform.execution_planning.order_style import OrderStyle
from market_platform.execution_planning.quantities import (
    DELTA_DIGIT_LIMIT,
    DELTA_FRACTIONAL_DIGIT_LIMIT,
    DELTA_TEXT_LIMIT,
    _canonical_quantity,
)
from market_platform.instruments import (
    ExternalInstrumentIdentity,
    InstrumentMapping,
    InstrumentValidationError,
)

BROKER_NATIVE_ORDER_REPRESENTATION_SCHEMA = "broker_native_order_representation/v1"
BROKER_NATIVE_ORDER_MAPPING_SCHEMA = "broker_native_order_mapping/v1"

_REPRESENTATION_CREATION_SEAL = object()
_MAPPING_CREATION_SEAL = object()
_OPAQUE_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", flags=re.ASCII)
_INSTRUMENT_NAMESPACE_PATTERN = re.compile(r"[a-z][a-z0-9._-]{0,63}", flags=re.ASCII)
_MAPPER_VERSION_MAXIMUM = 64
_NATIVE_TOKEN_MAXIMUM = 128


@dataclass(frozen=True, slots=True, init=False)
class BrokerNativeOrderRepresentation:
    """One bounded adapter-native semantic order representation.

    Native token syntax is validated, but token meaning belongs to mapper
    conformance. This value is neither an SDK object nor proof of broker
    acceptance.
    """

    external_instrument_identity: ExternalInstrumentIdentity
    side_token: str
    quantity: Decimal
    order_type_token: str
    limit_price: Decimal | None
    limit_price_currency: str | None
    time_in_force_token: str
    session_participation_token: str
    schema_version: str = field(init=False)
    fingerprint: str = field(init=False)

    def __init__(self) -> None:
        raise TypeError(
            "BrokerNativeOrderRepresentation must be created by "
            "construct_broker_native_order_representation()"
        )

    @classmethod
    def _create(
        cls,
        *,
        external_instrument_identity: ExternalInstrumentIdentity,
        side_token: str,
        quantity: Decimal,
        order_type_token: str,
        limit_price: Decimal | None,
        limit_price_currency: str | None,
        time_in_force_token: str,
        session_participation_token: str,
        creation_seal: object,
    ) -> BrokerNativeOrderRepresentation:
        if creation_seal is not _REPRESENTATION_CREATION_SEAL:
            raise TypeError("native order representation construction is private")
        values = _validate_representation_values(
            external_instrument_identity=external_instrument_identity,
            side_token=side_token,
            quantity=quantity,
            order_type_token=order_type_token,
            limit_price=limit_price,
            limit_price_currency=limit_price_currency,
            time_in_force_token=time_in_force_token,
            session_participation_token=session_participation_token,
            retained=False,
        )
        result = object.__new__(cls)
        for name in (
            "external_instrument_identity",
            "side_token",
            "quantity",
            "order_type_token",
            "limit_price",
            "limit_price_currency",
            "time_in_force_token",
            "session_participation_token",
        ):
            object.__setattr__(result, name, values[name])
        object.__setattr__(
            result, "schema_version", BROKER_NATIVE_ORDER_REPRESENTATION_SCHEMA
        )
        object.__setattr__(
            result,
            "fingerprint",
            canonical_fingerprint(result._fingerprint_payload()),
        )
        result._validate()
        return result

    def _fingerprint_payload(self) -> dict[str, object]:
        _, quantity_text = _canonical_native_quantity(self.quantity, retained=True)
        _, _, price_text = _canonical_native_price(
            self.limit_price, self.limit_price_currency, retained=True
        )
        return _representation_payload(
            schema_version=self.schema_version,
            external_instrument_identity=self.external_instrument_identity,
            side_token=self.side_token,
            quantity_text=quantity_text,
            order_type_token=self.order_type_token,
            limit_price_text=price_text,
            limit_price_currency=self.limit_price_currency,
            time_in_force_token=self.time_in_force_token,
            session_participation_token=self.session_participation_token,
        )

    def _validate(self) -> None:
        retained = {
            name: required_retained_attribute(
                self, name, "broker-native order representation"
            )
            for name in (
                "external_instrument_identity",
                "side_token",
                "quantity",
                "order_type_token",
                "limit_price",
                "limit_price_currency",
                "time_in_force_token",
                "session_participation_token",
                "schema_version",
                "fingerprint",
            )
        }
        values = _validate_representation_values(
            external_instrument_identity=retained["external_instrument_identity"],
            side_token=retained["side_token"],
            quantity=retained["quantity"],
            order_type_token=retained["order_type_token"],
            limit_price=retained["limit_price"],
            limit_price_currency=retained["limit_price_currency"],
            time_in_force_token=retained["time_in_force_token"],
            session_participation_token=retained["session_participation_token"],
            retained=True,
        )
        schema = retained["schema_version"]
        if (
            type(schema) is not str
            or schema != BROKER_NATIVE_ORDER_REPRESENTATION_SCHEMA
        ):
            raise ExecutionPlanningCorrespondenceError(
                "native order representation schema_version is invalid"
            )
        expected = canonical_fingerprint(
            _representation_payload(
                schema_version=schema,
                external_instrument_identity=cast(
                    ExternalInstrumentIdentity,
                    values["external_instrument_identity"],
                ),
                side_token=cast(str, values["side_token"]),
                quantity_text=cast(str, values["quantity_text"]),
                order_type_token=cast(str, values["order_type_token"]),
                limit_price_text=cast(str | None, values["limit_price_text"]),
                limit_price_currency=cast(str | None, values["limit_price_currency"]),
                time_in_force_token=cast(str, values["time_in_force_token"]),
                session_participation_token=cast(
                    str, values["session_participation_token"]
                ),
            )
        )
        fingerprint = retained["fingerprint"]
        if type(fingerprint) is not str or fingerprint != expected:
            raise ExecutionPlanningCorrespondenceError(
                "native order representation fingerprint does not match content"
            )

    def to_dict(self) -> dict[str, object]:
        """Return the canonical JSON-safe adapter-native representation."""

        self._validate()
        return {**self._fingerprint_payload(), "fingerprint": self.fingerprint}


def construct_broker_native_order_representation(
    *,
    external_instrument_identity: ExternalInstrumentIdentity,
    side_token: str,
    quantity: Decimal,
    order_type_token: str,
    limit_price: Decimal | None,
    limit_price_currency: str | None,
    time_in_force_token: str,
    session_participation_token: str,
) -> BrokerNativeOrderRepresentation:
    """Construct one bounded mapper-owned semantic representation."""

    return BrokerNativeOrderRepresentation._create(
        external_instrument_identity=external_instrument_identity,
        side_token=side_token,
        quantity=quantity,
        order_type_token=order_type_token,
        limit_price=limit_price,
        limit_price_currency=limit_price_currency,
        time_in_force_token=time_in_force_token,
        session_participation_token=session_participation_token,
        creation_seal=_REPRESENTATION_CREATION_SEAL,
    )


@runtime_checkable
class BrokerNativeOrderMapper(Protocol):
    """Replaceable deterministic mapper port without execution side effects.

    Runtime protocol conformance proves member availability only. Platform
    evaluation snapshots and validates every metadata value exactly once;
    mapper provenance does not prove native-token correctness.
    """

    @property
    def execution_target_id(self) -> str:
        """Return the opaque capability-profile target identity."""
        ...

    @property
    def mapper_id(self) -> str:
        """Return the stable mapper identity."""
        ...

    @property
    def mapper_version(self) -> str:
        """Return the bounded declared version of mapping rules."""
        ...

    @property
    def mapping_policy_fingerprint(self) -> str:
        """Return the exact immutable mapping-policy fingerprint."""
        ...

    @property
    def instrument_namespace(self) -> str:
        """Return the exact external-instrument namespace handled."""
        ...

    def map_order(
        self,
        *,
        specification: BrokerNeutralOrderSpecification,
        external_instrument_identity: ExternalInstrumentIdentity,
    ) -> BrokerNativeOrderRepresentation:
        """Map once to bounded adapter-native semantic values."""
        ...


@dataclass(frozen=True, slots=True, init=False)
class BrokerNativeOrderMapping:
    """Self-contained provenance for one broker-native semantic mapping.

    The native_order field is owned nested semantic state. Upstream planning,
    capability, compatibility, instrument-mapping, and mapper objects are not
    retained.
    """

    execution_target_id: str
    mapper_id: str
    mapper_version: str
    mapping_policy_fingerprint: str
    instrument_namespace: str
    order_specification_fingerprint: str
    capability_profile_fingerprint: str
    structural_compatibility_result_fingerprint: str
    instrument_mapping_fingerprint: str
    native_order: BrokerNativeOrderRepresentation
    schema_version: str = field(init=False)
    fingerprint: str = field(init=False)

    def __init__(self) -> None:
        raise TypeError(
            "BrokerNativeOrderMapping must be created by map_broker_native_order()"
        )

    @classmethod
    def _create(
        cls,
        *,
        execution_target_id: str,
        mapper_id: str,
        mapper_version: str,
        mapping_policy_fingerprint: str,
        instrument_namespace: str,
        order_specification_fingerprint: str,
        capability_profile_fingerprint: str,
        structural_compatibility_result_fingerprint: str,
        instrument_mapping_fingerprint: str,
        native_order: BrokerNativeOrderRepresentation,
        creation_seal: object,
    ) -> BrokerNativeOrderMapping:
        if creation_seal is not _MAPPING_CREATION_SEAL:
            raise TypeError("broker-native order mapping construction is private")
        values = _validate_mapping_values(
            execution_target_id=execution_target_id,
            mapper_id=mapper_id,
            mapper_version=mapper_version,
            mapping_policy_fingerprint=mapping_policy_fingerprint,
            instrument_namespace=instrument_namespace,
            order_specification_fingerprint=order_specification_fingerprint,
            capability_profile_fingerprint=capability_profile_fingerprint,
            structural_compatibility_result_fingerprint=(
                structural_compatibility_result_fingerprint
            ),
            instrument_mapping_fingerprint=instrument_mapping_fingerprint,
            native_order=native_order,
            retained=False,
        )
        result = object.__new__(cls)
        for name in (
            "execution_target_id",
            "mapper_id",
            "mapper_version",
            "mapping_policy_fingerprint",
            "instrument_namespace",
            "order_specification_fingerprint",
            "capability_profile_fingerprint",
            "structural_compatibility_result_fingerprint",
            "instrument_mapping_fingerprint",
            "native_order",
        ):
            object.__setattr__(result, name, values[name])
        object.__setattr__(result, "schema_version", BROKER_NATIVE_ORDER_MAPPING_SCHEMA)
        object.__setattr__(
            result,
            "fingerprint",
            canonical_fingerprint(result._fingerprint_payload()),
        )
        result._validate()
        return result

    def _fingerprint_payload(self) -> dict[str, object]:
        return _mapping_payload(
            schema_version=self.schema_version,
            execution_target_id=self.execution_target_id,
            mapper_id=self.mapper_id,
            mapper_version=self.mapper_version,
            mapping_policy_fingerprint=self.mapping_policy_fingerprint,
            instrument_namespace=self.instrument_namespace,
            order_specification_fingerprint=self.order_specification_fingerprint,
            capability_profile_fingerprint=self.capability_profile_fingerprint,
            structural_compatibility_result_fingerprint=(
                self.structural_compatibility_result_fingerprint
            ),
            instrument_mapping_fingerprint=self.instrument_mapping_fingerprint,
            native_order=self.native_order,
        )

    def _validate(self) -> None:
        retained = {
            name: required_retained_attribute(self, name, "broker-native order mapping")
            for name in (
                "execution_target_id",
                "mapper_id",
                "mapper_version",
                "mapping_policy_fingerprint",
                "instrument_namespace",
                "order_specification_fingerprint",
                "capability_profile_fingerprint",
                "structural_compatibility_result_fingerprint",
                "instrument_mapping_fingerprint",
                "native_order",
                "schema_version",
                "fingerprint",
            )
        }
        values = _validate_mapping_values(
            execution_target_id=retained["execution_target_id"],
            mapper_id=retained["mapper_id"],
            mapper_version=retained["mapper_version"],
            mapping_policy_fingerprint=retained["mapping_policy_fingerprint"],
            instrument_namespace=retained["instrument_namespace"],
            order_specification_fingerprint=retained["order_specification_fingerprint"],
            capability_profile_fingerprint=retained["capability_profile_fingerprint"],
            structural_compatibility_result_fingerprint=retained[
                "structural_compatibility_result_fingerprint"
            ],
            instrument_mapping_fingerprint=retained["instrument_mapping_fingerprint"],
            native_order=retained["native_order"],
            retained=True,
        )
        schema = retained["schema_version"]
        if type(schema) is not str or schema != BROKER_NATIVE_ORDER_MAPPING_SCHEMA:
            raise ExecutionPlanningCorrespondenceError(
                "broker-native order mapping schema_version is invalid"
            )
        expected = canonical_fingerprint(
            _mapping_payload(
                schema_version=schema,
                execution_target_id=cast(str, values["execution_target_id"]),
                mapper_id=cast(str, values["mapper_id"]),
                mapper_version=cast(str, values["mapper_version"]),
                mapping_policy_fingerprint=cast(
                    str, values["mapping_policy_fingerprint"]
                ),
                instrument_namespace=cast(str, values["instrument_namespace"]),
                order_specification_fingerprint=cast(
                    str, values["order_specification_fingerprint"]
                ),
                capability_profile_fingerprint=cast(
                    str, values["capability_profile_fingerprint"]
                ),
                structural_compatibility_result_fingerprint=cast(
                    str, values["structural_compatibility_result_fingerprint"]
                ),
                instrument_mapping_fingerprint=cast(
                    str, values["instrument_mapping_fingerprint"]
                ),
                native_order=cast(
                    BrokerNativeOrderRepresentation, values["native_order"]
                ),
            )
        )
        fingerprint = retained["fingerprint"]
        if type(fingerprint) is not str or fingerprint != expected:
            raise ExecutionPlanningCorrespondenceError(
                "broker-native order mapping fingerprint does not match content"
            )

    def to_dict(self) -> dict[str, object]:
        """Return the canonical JSON-safe mapping and complete native child."""

        self._validate()
        return {**self._fingerprint_payload(), "fingerprint": self.fingerprint}


def map_broker_native_order(
    *,
    specification: BrokerNeutralOrderSpecification,
    capability_profile: BrokerExecutionCapabilityProfile,
    compatibility_result: BrokerExecutionStructuralCompatibilityResult,
    instrument_mapping: InstrumentMapping,
    mapper: BrokerNativeOrderMapper,
) -> BrokerNativeOrderMapping:
    """Map one structurally compatible order without authorization or effects.

    The caller supplies one validated instrument relation; this operation does
    no lookup, reverse resolution, routing, authorization, submission, live
    broker interaction, or target-token semantic verification.
    """

    _validate_mapping_source_types(
        specification=specification,
        capability_profile=capability_profile,
        compatibility_result=compatibility_result,
        instrument_mapping=instrument_mapping,
    )
    specification._validate()
    capability_profile._validate()
    compatibility_result._validate()
    _validate_supplied_instrument_mapping(instrument_mapping)

    if (
        compatibility_result.outcome
        is not BrokerExecutionStructuralCompatibilityOutcome.COMPATIBLE
        or compatibility_result.rejection_reasons != ()
    ):
        raise ExecutionPlanningValidationError(
            "mapping requires an exact compatible structural result"
        )
    if (
        compatibility_result.order_specification_fingerprint
        != specification.fingerprint
    ):
        raise ExecutionPlanningValidationError(
            "compatibility result does not correspond to specification"
        )
    if (
        compatibility_result.capability_profile_fingerprint
        != capability_profile.fingerprint
    ):
        raise ExecutionPlanningValidationError(
            "compatibility result does not correspond to capability profile"
        )
    _require_canonical_instrument_correspondence(specification, instrument_mapping)
    if not instrument_mapping.is_active(specification.instruction.plan_as_of):
        raise ExecutionPlanningValidationError(
            "instrument mapping is inactive at instruction plan_as_of"
        )
    external_identity = _reconstruct_external_identity(
        instrument_mapping.external_identity,
        retained_source=True,
    )

    if not isinstance(mapper, BrokerNativeOrderMapper):
        raise ExecutionPlanningValidationError(
            "mapper must satisfy BrokerNativeOrderMapper"
        )

    execution_target_id = mapper.execution_target_id
    mapper_id = mapper.mapper_id
    mapper_version = mapper.mapper_version
    mapping_policy_fingerprint = mapper.mapping_policy_fingerprint
    instrument_namespace = mapper.instrument_namespace

    execution_target_id = _opaque_id(
        execution_target_id, "execution_target_id", retained=False
    )
    mapper_id = _opaque_id(mapper_id, "mapper_id", retained=False)
    mapper_version = _visible_ascii(
        mapper_version,
        "mapper_version",
        _MAPPER_VERSION_MAXIMUM,
        retained=False,
    )
    mapping_policy_fingerprint = required_fingerprint(
        mapping_policy_fingerprint, "mapping_policy_fingerprint"
    )
    instrument_namespace = _instrument_namespace(instrument_namespace, retained=False)
    if execution_target_id != capability_profile.execution_target_id:
        raise ExecutionPlanningValidationError(
            "mapper execution_target_id does not match capability profile"
        )
    if instrument_namespace != external_identity.namespace:
        raise ExecutionPlanningValidationError(
            "mapper instrument_namespace does not match instrument mapping"
        )

    map_order = mapper.map_order
    native_order = map_order(
        specification=specification,
        external_instrument_identity=external_identity,
    )
    if type(native_order) is not BrokerNativeOrderRepresentation:
        raise ExecutionPlanningValidationError(
            "mapper must return an exact BrokerNativeOrderRepresentation"
        )
    try:
        native_order._validate()
    except ExecutionPlanningCorrespondenceError as error:
        raise ExecutionPlanningValidationError(
            "mapper returned a malformed native order representation"
        ) from error
    _require_native_output_correspondence(
        specification=specification,
        external_identity=external_identity,
        native_order=native_order,
    )

    return BrokerNativeOrderMapping._create(
        execution_target_id=execution_target_id,
        mapper_id=mapper_id,
        mapper_version=mapper_version,
        mapping_policy_fingerprint=mapping_policy_fingerprint,
        instrument_namespace=instrument_namespace,
        order_specification_fingerprint=specification.fingerprint,
        capability_profile_fingerprint=capability_profile.fingerprint,
        structural_compatibility_result_fingerprint=compatibility_result.fingerprint,
        instrument_mapping_fingerprint=instrument_mapping.fingerprint,
        native_order=native_order,
        creation_seal=_MAPPING_CREATION_SEAL,
    )


def _validate_representation_values(
    *,
    external_instrument_identity: object,
    side_token: object,
    quantity: object,
    order_type_token: object,
    limit_price: object,
    limit_price_currency: object,
    time_in_force_token: object,
    session_participation_token: object,
    retained: bool,
) -> dict[str, object]:
    if type(external_instrument_identity) is not ExternalInstrumentIdentity:
        _raise_invalid(
            "external_instrument_identity must be exact",
            retained=retained,
        )
    try:
        external_identity = _reconstruct_external_identity(
            cast(ExternalInstrumentIdentity, external_instrument_identity),
            retained_source=retained,
        )
    except InstrumentValidationError as error:
        _raise_invalid(
            "external_instrument_identity is malformed",
            retained=retained,
            cause=error,
        )
    canonical_quantity, quantity_text = _canonical_native_quantity(
        quantity,
        retained=retained,
    )
    canonical_price, currency, price_text = _canonical_native_price(
        limit_price,
        limit_price_currency,
        retained=retained,
    )
    return {
        "external_instrument_identity": external_identity,
        "side_token": _native_token(side_token, "side_token", retained=retained),
        "quantity": canonical_quantity,
        "quantity_text": quantity_text,
        "order_type_token": _native_token(
            order_type_token,
            "order_type_token",
            retained=retained,
        ),
        "limit_price": canonical_price,
        "limit_price_currency": currency,
        "limit_price_text": price_text,
        "time_in_force_token": _native_token(
            time_in_force_token,
            "time_in_force_token",
            retained=retained,
        ),
        "session_participation_token": _native_token(
            session_participation_token,
            "session_participation_token",
            retained=retained,
        ),
    }


def _validate_mapping_values(
    *,
    execution_target_id: object,
    mapper_id: object,
    mapper_version: object,
    mapping_policy_fingerprint: object,
    instrument_namespace: object,
    order_specification_fingerprint: object,
    capability_profile_fingerprint: object,
    structural_compatibility_result_fingerprint: object,
    instrument_mapping_fingerprint: object,
    native_order: object,
    retained: bool,
) -> dict[str, object]:
    values: dict[str, object] = {
        "execution_target_id": _opaque_id(
            execution_target_id,
            "execution_target_id",
            retained=retained,
        ),
        "mapper_id": _opaque_id(mapper_id, "mapper_id", retained=retained),
        "mapper_version": _visible_ascii(
            mapper_version,
            "mapper_version",
            _MAPPER_VERSION_MAXIMUM,
            retained=retained,
        ),
        "instrument_namespace": _instrument_namespace(
            instrument_namespace,
            retained=retained,
        ),
    }
    for name, candidate in (
        ("mapping_policy_fingerprint", mapping_policy_fingerprint),
        ("order_specification_fingerprint", order_specification_fingerprint),
        ("capability_profile_fingerprint", capability_profile_fingerprint),
        (
            "structural_compatibility_result_fingerprint",
            structural_compatibility_result_fingerprint,
        ),
        ("instrument_mapping_fingerprint", instrument_mapping_fingerprint),
    ):
        try:
            values[name] = required_fingerprint(candidate, name)
        except ExecutionPlanningValidationError as error:
            _raise_invalid(
                f"{name} is invalid",
                retained=retained,
                cause=error,
            )
    if type(native_order) is not BrokerNativeOrderRepresentation:
        _raise_invalid("native_order must be exact", retained=retained)
    try:
        cast(BrokerNativeOrderRepresentation, native_order)._validate()
    except ExecutionPlanningCorrespondenceError as error:
        _raise_invalid("native_order is malformed", retained=retained, cause=error)
    if (
        values["instrument_namespace"]
        != cast(
            BrokerNativeOrderRepresentation, native_order
        ).external_instrument_identity.namespace
    ):
        _raise_invalid(
            "instrument_namespace does not match native_order namespace",
            retained=retained,
        )
    values["native_order"] = native_order
    return values


def _validate_mapping_source_types(
    *,
    specification: object,
    capability_profile: object,
    compatibility_result: object,
    instrument_mapping: object,
) -> None:
    for value, expected, name in (
        (specification, BrokerNeutralOrderSpecification, "specification"),
        (capability_profile, BrokerExecutionCapabilityProfile, "capability_profile"),
        (
            compatibility_result,
            BrokerExecutionStructuralCompatibilityResult,
            "compatibility_result",
        ),
        (instrument_mapping, InstrumentMapping, "instrument_mapping"),
    ):
        if type(value) is not expected:
            raise ExecutionPlanningValidationError(
                f"{name} must have exact runtime type {expected.__name__}"
            )


def _validate_supplied_instrument_mapping(mapping: InstrumentMapping) -> None:
    try:
        mapping._validate()
    except InstrumentValidationError as error:
        raise ExecutionPlanningCorrespondenceError(
            "instrument_mapping retained state is malformed"
        ) from error


def _require_canonical_instrument_correspondence(
    specification: BrokerNeutralOrderSpecification,
    mapping: InstrumentMapping,
) -> None:
    canonical = specification.canonical_instrument
    mapped = mapping.canonical_instrument
    if (
        mapped.fingerprint != canonical.fingerprint
        or mapped.to_dict() != canonical.to_dict()
    ):
        raise ExecutionPlanningValidationError(
            "instrument mapping does not correspond to specification instrument"
        )


def _require_native_output_correspondence(
    *,
    specification: BrokerNeutralOrderSpecification,
    external_identity: ExternalInstrumentIdentity,
    native_order: BrokerNativeOrderRepresentation,
) -> None:
    if (
        native_order.external_instrument_identity.to_dict()
        != external_identity.to_dict()
    ):
        raise ExecutionPlanningValidationError(
            "native order external identity does not match instrument mapping"
        )
    _, native_quantity_text = _canonical_native_quantity(
        native_order.quantity,
        retained=True,
    )
    _, source_quantity_text = _canonical_native_quantity(
        specification.instruction.quantity,
        retained=True,
    )
    if native_quantity_text != source_quantity_text:
        raise ExecutionPlanningValidationError(
            "native order quantity does not match specification instruction"
        )

    style = specification.order_style_choice.style
    if style is OrderStyle.MARKET:
        if (
            native_order.limit_price is not None
            or native_order.limit_price_currency is not None
        ):
            raise ExecutionPlanningValidationError(
                "MARKET native order must omit limit price and currency"
            )
        return
    if style is not OrderStyle.LIMIT:
        raise ExecutionPlanningCorrespondenceError(
            "specification order style is outside the validated v1 domain"
        )
    source_price = specification.limit_price_choice
    if source_price is None:
        raise ExecutionPlanningCorrespondenceError(
            "LIMIT specification is missing limit price choice"
        )
    if native_order.limit_price is None or native_order.limit_price_currency is None:
        raise ExecutionPlanningValidationError(
            "LIMIT native order must include limit price and currency"
        )
    _, native_price_text = _canonical_price(native_order.limit_price, retained=True)
    _, source_price_text = _canonical_price(source_price.limit_price, retained=True)
    if native_price_text != source_price_text:
        raise ExecutionPlanningValidationError(
            "native order limit price does not match specification"
        )
    if native_order.limit_price_currency != source_price.trading_currency:
        raise ExecutionPlanningValidationError(
            "native order limit price currency does not match specification"
        )


def _reconstruct_external_identity(
    source: ExternalInstrumentIdentity,
    *,
    retained_source: bool,
) -> ExternalInstrumentIdentity:
    try:
        source._validate()
        reconstructed = ExternalInstrumentIdentity(
            namespace=source.namespace,
            external_symbol=source.external_symbol,
            external_venue=source.external_venue,
        )
        reconstructed._validate()
    except (InstrumentValidationError, TypeError) as error:
        _raise_invalid(
            "external instrument identity is malformed",
            retained=retained_source,
            cause=error,
        )
    if reconstructed.to_dict() != source.to_dict():
        _raise_invalid(
            "external instrument identity reconstruction differs",
            retained=retained_source,
        )
    return reconstructed


def _canonical_native_quantity(
    value: object,
    *,
    retained: bool,
) -> tuple[Decimal, str]:
    try:
        canonical, text = _canonical_quantity(
            value,
            "quantity",
            allow_negative=False,
            digit_limit=DELTA_DIGIT_LIMIT,
            fractional_limit=DELTA_FRACTIONAL_DIGIT_LIMIT,
            text_limit=DELTA_TEXT_LIMIT,
            bounds_error=ExecutionPlanningValidationError,
        )
    except ExecutionPlanningValidationError as error:
        _raise_invalid(str(error), retained=retained, cause=error)
    if canonical.is_zero():
        _raise_invalid("quantity must be strictly positive", retained=retained)
    if retained and cast(Decimal, value).as_tuple() != canonical.as_tuple():
        raise ExecutionPlanningCorrespondenceError(
            "retained quantity must already be canonical"
        )
    return canonical, text


def _canonical_native_price(
    limit_price: object,
    limit_price_currency: object,
    *,
    retained: bool,
) -> tuple[Decimal | None, str | None, str | None]:
    if limit_price is None and limit_price_currency is None:
        return None, None, None
    if limit_price is None or limit_price_currency is None:
        _raise_invalid(
            "limit_price and limit_price_currency must both be present or absent",
            retained=retained,
        )
    try:
        canonical_price, price_text = _canonical_price(
            limit_price,
            retained=retained,
        )
        currency = _canonical_currency(limit_price_currency, retained=retained)
    except ExecutionPlanningValidationError, ExecutionPlanningCorrespondenceError:
        raise
    if retained and cast(Decimal, limit_price).as_tuple() != canonical_price.as_tuple():
        raise ExecutionPlanningCorrespondenceError(
            "retained limit price must already be canonical"
        )
    return canonical_price, currency, price_text


def _opaque_id(value: object, name: str, *, retained: bool) -> str:
    if type(value) is not str or _OPAQUE_ID_PATTERN.fullmatch(value) is None:
        _raise_invalid(
            f"{name} must match [A-Za-z0-9][A-Za-z0-9._-]{{0,127}}",
            retained=retained,
        )
    return cast(str, value)


def _instrument_namespace(value: object, *, retained: bool) -> str:
    if type(value) is not str or _INSTRUMENT_NAMESPACE_PATTERN.fullmatch(value) is None:
        _raise_invalid(
            "instrument_namespace must match [a-z][a-z0-9._-]{0,63}",
            retained=retained,
        )
    return cast(str, value)


def _visible_ascii(
    value: object,
    name: str,
    maximum: int,
    *,
    retained: bool,
) -> str:
    if (
        type(value) is not str
        or not 1 <= len(value) <= maximum
        or any(not 0x21 <= ord(character) <= 0x7E for character in value)
    ):
        _raise_invalid(
            f"{name} must be 1-{maximum} visible ASCII characters",
            retained=retained,
        )
    return cast(str, value)


def _native_token(value: object, name: str, *, retained: bool) -> str:
    return _visible_ascii(
        value,
        name,
        _NATIVE_TOKEN_MAXIMUM,
        retained=retained,
    )


def _representation_payload(
    *,
    schema_version: str,
    external_instrument_identity: ExternalInstrumentIdentity,
    side_token: str,
    quantity_text: str,
    order_type_token: str,
    limit_price_text: str | None,
    limit_price_currency: str | None,
    time_in_force_token: str,
    session_participation_token: str,
) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "external_instrument_identity": external_instrument_identity.to_dict(),
        "side_token": side_token,
        "quantity": quantity_text,
        "order_type_token": order_type_token,
        "limit_price": limit_price_text,
        "limit_price_currency": limit_price_currency,
        "time_in_force_token": time_in_force_token,
        "session_participation_token": session_participation_token,
    }


def _mapping_payload(
    *,
    schema_version: str,
    execution_target_id: str,
    mapper_id: str,
    mapper_version: str,
    mapping_policy_fingerprint: str,
    instrument_namespace: str,
    order_specification_fingerprint: str,
    capability_profile_fingerprint: str,
    structural_compatibility_result_fingerprint: str,
    instrument_mapping_fingerprint: str,
    native_order: BrokerNativeOrderRepresentation,
) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "execution_target_id": execution_target_id,
        "mapper_id": mapper_id,
        "mapper_version": mapper_version,
        "mapping_policy_fingerprint": mapping_policy_fingerprint,
        "instrument_namespace": instrument_namespace,
        "order_specification_fingerprint": order_specification_fingerprint,
        "capability_profile_fingerprint": capability_profile_fingerprint,
        "structural_compatibility_result_fingerprint": (
            structural_compatibility_result_fingerprint
        ),
        "instrument_mapping_fingerprint": instrument_mapping_fingerprint,
        "native_order": native_order.to_dict(),
    }


def _raise_invalid(
    message: str,
    *,
    retained: bool,
    cause: BaseException | None = None,
) -> None:
    error: Exception
    if retained:
        error = ExecutionPlanningCorrespondenceError(message)
    else:
        error = ExecutionPlanningValidationError(message)
    if cause is None:
        raise error
    raise error from cause


__all__ = [
    "BROKER_NATIVE_ORDER_REPRESENTATION_SCHEMA",
    "BrokerNativeOrderRepresentation",
    "construct_broker_native_order_representation",
    "BROKER_NATIVE_ORDER_MAPPING_SCHEMA",
    "BrokerNativeOrderMapping",
    "BrokerNativeOrderMapper",
    "map_broker_native_order",
]
