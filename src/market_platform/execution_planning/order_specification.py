"""Factory-owned broker-neutral order specifications."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import NamedTuple, cast
from weakref import ReferenceType, ref

from market_platform._fingerprint import canonical_fingerprint
from market_platform.instruments import (
    CANONICAL_INSTRUMENT_SCHEMA_VERSION,
    CanonicalInstrument,
    CanonicalInstrumentId,
    InstrumentAssetClass,
    InstrumentValidationError,
)
from market_platform.trading import (
    TRADING_INSTRUMENT_IDENTITY_SCHEMA_VERSION,
    TradingInstrumentIdentity,
)

from ._canonical import required_retained_attribute
from .errors import (
    ExecutionPlanningCorrespondenceError,
    ExecutionPlanningValidationError,
)
from .instruction import (
    BROKER_NEUTRAL_EXECUTION_INSTRUCTION_SCHEMA,
    BrokerNeutralExecutionInstruction,
)
from .limit_price import LIMIT_PRICE_CHOICE_SCHEMA, LimitPriceChoice
from .order_style import ORDER_STYLE_CHOICE_SCHEMA, OrderStyle, OrderStyleChoice
from .session_participation import (
    SESSION_PARTICIPATION_CHOICE_SCHEMA,
    SessionParticipationChoice,
)
from .time_in_force import TIME_IN_FORCE_CHOICE_SCHEMA, TimeInForceChoice

BROKER_NEUTRAL_ORDER_SPECIFICATION_SCHEMA = "broker_neutral_order_specification/v1"

_SPECIFICATION_CREATION_SEAL = object()
_ATTESTATION_CREATION_SEAL = object()


@dataclass(frozen=True, slots=True, init=False)
class _OrderSpecificationConstructionAttestation:
    """Per-instance identity anchors for factory-owned retained state."""

    _original_state: tuple[object, ...]
    _original_binding: tuple[object, ...]
    _instruction: BrokerNeutralExecutionInstruction
    _canonical_instrument: CanonicalInstrument
    _order_style_choice: OrderStyleChoice
    _limit_price_choice: LimitPriceChoice | None
    _time_in_force_choice: TimeInForceChoice
    _session_participation_choice: SessionParticipationChoice

    def __init__(self) -> None:
        raise TypeError("order specification construction attestation is private")

    @classmethod
    def _create(
        cls,
        *,
        original_state: tuple[object, ...],
        original_binding: tuple[object, ...],
        instruction: BrokerNeutralExecutionInstruction,
        canonical_instrument: CanonicalInstrument,
        order_style_choice: OrderStyleChoice,
        limit_price_choice: LimitPriceChoice | None,
        time_in_force_choice: TimeInForceChoice,
        session_participation_choice: SessionParticipationChoice,
        creation_seal: object,
    ) -> _OrderSpecificationConstructionAttestation:
        if creation_seal is not _ATTESTATION_CREATION_SEAL:
            raise TypeError("order specification construction attestation is private")
        result = object.__new__(cls)
        for name, value in (
            ("_original_state", original_state),
            ("_original_binding", original_binding),
            ("_instruction", instruction),
            ("_canonical_instrument", canonical_instrument),
            ("_order_style_choice", order_style_choice),
            ("_limit_price_choice", limit_price_choice),
            ("_time_in_force_choice", time_in_force_choice),
            ("_session_participation_choice", session_participation_choice),
        ):
            object.__setattr__(result, name, value)
        return result


class _OrderSpecificationOrigin(NamedTuple):
    """Immutable process-local origin for one exact specification owner."""

    owner_reference: ReferenceType[BrokerNeutralOrderSpecification]
    attestation: _OrderSpecificationConstructionAttestation
    original_state: tuple[object, ...]
    original_binding: tuple[object, ...]
    instruction: BrokerNeutralExecutionInstruction
    canonical_instrument: CanonicalInstrument
    order_style_choice: OrderStyleChoice
    limit_price_choice: LimitPriceChoice | None
    time_in_force_choice: TimeInForceChoice
    session_participation_choice: SessionParticipationChoice


def _origin_registry_accessors() -> tuple[
    Callable[..., None],
    Callable[[BrokerNeutralOrderSpecification], _OrderSpecificationOrigin],
    Callable[[], int],
]:
    origins: dict[int, _OrderSpecificationOrigin] = {}

    def register(
        owner: BrokerNeutralOrderSpecification,
        *,
        attestation: _OrderSpecificationConstructionAttestation,
        original_state: tuple[object, ...],
        original_binding: tuple[object, ...],
        instruction: BrokerNeutralExecutionInstruction,
        canonical_instrument: CanonicalInstrument,
        order_style_choice: OrderStyleChoice,
        limit_price_choice: LimitPriceChoice | None,
        time_in_force_choice: TimeInForceChoice,
        session_participation_choice: SessionParticipationChoice,
    ) -> None:
        owner_key = id(owner)
        existing = origins.get(owner_key)
        if existing is not None:
            existing_owner = existing.owner_reference()
            if existing_owner is not None:
                raise ExecutionPlanningCorrespondenceError(
                    "order specification origin is already registered"
                )
            if origins.get(owner_key) is existing:
                del origins[owner_key]

        def cleanup(
            owner_reference: ReferenceType[BrokerNeutralOrderSpecification],
        ) -> None:
            current = origins.get(owner_key)
            if current is not None and current.owner_reference is owner_reference:
                del origins[owner_key]

        owner_reference = ref(owner, cleanup)
        origins[owner_key] = _OrderSpecificationOrigin(
            owner_reference=owner_reference,
            attestation=attestation,
            original_state=original_state,
            original_binding=original_binding,
            instruction=instruction,
            canonical_instrument=canonical_instrument,
            order_style_choice=order_style_choice,
            limit_price_choice=limit_price_choice,
            time_in_force_choice=time_in_force_choice,
            session_participation_choice=session_participation_choice,
        )

    def get(owner: BrokerNeutralOrderSpecification) -> _OrderSpecificationOrigin:
        origin = origins.get(id(owner))
        if type(origin) is not _OrderSpecificationOrigin:
            raise ExecutionPlanningCorrespondenceError(
                "order specification origin is not registered"
            )
        if origin.owner_reference() is not owner:
            raise ExecutionPlanningCorrespondenceError(
                "order specification origin owner does not correspond"
            )
        return origin

    def count() -> int:
        return len(origins)

    return register, get, count


(
    _register_order_specification_origin,
    _get_order_specification_origin,
    _registered_order_specification_origin_count,
) = _origin_registry_accessors()
del _origin_registry_accessors


@dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
class BrokerNeutralOrderSpecification:
    """One complete canonical order request without execution authority."""

    instruction: BrokerNeutralExecutionInstruction
    canonical_instrument: CanonicalInstrument
    order_style_choice: OrderStyleChoice
    limit_price_choice: LimitPriceChoice | None
    time_in_force_choice: TimeInForceChoice
    session_participation_choice: SessionParticipationChoice
    schema_version: str = field(init=False)
    fingerprint: str = field(init=False)
    _constructor_state: tuple[object, ...] = field(repr=False, compare=False)
    _constructor_binding: tuple[object, ...] = field(repr=False, compare=False)
    _token: object = field(repr=False, compare=False)

    def __init__(self) -> None:
        raise TypeError(
            "BrokerNeutralOrderSpecification must be created by "
            "construct_broker_neutral_order_specification()"
        )

    @classmethod
    def _create(
        cls,
        *,
        instruction: BrokerNeutralExecutionInstruction,
        canonical_instrument: CanonicalInstrument,
        order_style_choice: OrderStyleChoice,
        limit_price_choice: LimitPriceChoice | None,
        time_in_force_choice: TimeInForceChoice,
        session_participation_choice: SessionParticipationChoice,
        creation_seal: object,
    ) -> BrokerNeutralOrderSpecification:
        if creation_seal is not _SPECIFICATION_CREATION_SEAL:
            raise TypeError("order specification construction is factory-owned")

        sources = _validate_factory_sources(
            instruction=instruction,
            canonical_instrument=canonical_instrument,
            order_style_choice=order_style_choice,
            limit_price_choice=limit_price_choice,
            time_in_force_choice=time_in_force_choice,
            session_participation_choice=session_participation_choice,
        )
        state = _constructor_state(sources)
        binding = (
            state,
            instruction,
            canonical_instrument,
            order_style_choice,
            limit_price_choice,
            time_in_force_choice,
            session_participation_choice,
        )
        attestation = _OrderSpecificationConstructionAttestation._create(
            original_state=state,
            original_binding=binding,
            instruction=instruction,
            canonical_instrument=canonical_instrument,
            order_style_choice=order_style_choice,
            limit_price_choice=limit_price_choice,
            time_in_force_choice=time_in_force_choice,
            session_participation_choice=session_participation_choice,
            creation_seal=_ATTESTATION_CREATION_SEAL,
        )
        result = object.__new__(cls)
        for name, value in (
            ("instruction", instruction),
            ("canonical_instrument", canonical_instrument),
            ("order_style_choice", order_style_choice),
            ("limit_price_choice", limit_price_choice),
            ("time_in_force_choice", time_in_force_choice),
            ("session_participation_choice", session_participation_choice),
            ("schema_version", BROKER_NEUTRAL_ORDER_SPECIFICATION_SCHEMA),
            ("_constructor_state", state),
            ("_constructor_binding", binding),
            ("_token", attestation),
        ):
            object.__setattr__(result, name, value)
        object.__setattr__(
            result,
            "fingerprint",
            canonical_fingerprint(_fingerprint_payload(sources)),
        )
        _register_order_specification_origin(
            result,
            attestation=attestation,
            original_state=state,
            original_binding=binding,
            instruction=instruction,
            canonical_instrument=canonical_instrument,
            order_style_choice=order_style_choice,
            limit_price_choice=limit_price_choice,
            time_in_force_choice=time_in_force_choice,
            session_participation_choice=session_participation_choice,
        )
        result._validate()
        return result

    def _validate(self) -> dict[str, object]:
        retained = {
            name: required_retained_attribute(
                self, name, "broker-neutral order specification"
            )
            for name in (
                "instruction",
                "canonical_instrument",
                "order_style_choice",
                "limit_price_choice",
                "time_in_force_choice",
                "session_participation_choice",
                "schema_version",
                "fingerprint",
                "_constructor_state",
                "_constructor_binding",
                "_token",
            )
        }
        origin = _get_order_specification_origin(self)
        if type(origin) is not _OrderSpecificationOrigin:
            raise ExecutionPlanningCorrespondenceError(
                "order specification origin is invalid"
            )
        attestation = retained["_token"]
        if attestation is not origin.attestation:
            raise ExecutionPlanningCorrespondenceError(
                "order specification construction attestation is not original"
            )
        if type(attestation) is not _OrderSpecificationConstructionAttestation:
            raise ExecutionPlanningCorrespondenceError(
                "order specification construction attestation is invalid"
            )
        attested = {
            name: required_retained_attribute(
                attestation,
                name,
                "order specification construction attestation",
            )
            for name in (
                "_original_state",
                "_original_binding",
                "_instruction",
                "_canonical_instrument",
                "_order_style_choice",
                "_limit_price_choice",
                "_time_in_force_choice",
                "_session_participation_choice",
            )
        }
        state = retained["_constructor_state"]
        binding = retained["_constructor_binding"]
        expected_sources = (
            retained["instruction"],
            retained["canonical_instrument"],
            retained["order_style_choice"],
            retained["limit_price_choice"],
            retained["time_in_force_choice"],
            retained["session_participation_choice"],
        )
        origin_sources = (
            origin.instruction,
            origin.canonical_instrument,
            origin.order_style_choice,
            origin.limit_price_choice,
            origin.time_in_force_choice,
            origin.session_participation_choice,
        )
        attested_sources = (
            attested["_instruction"],
            attested["_canonical_instrument"],
            attested["_order_style_choice"],
            attested["_limit_price_choice"],
            attested["_time_in_force_choice"],
            attested["_session_participation_choice"],
        )
        if state is not origin.original_state:
            raise ExecutionPlanningCorrespondenceError(
                "order specification constructor state is not the original "
                "attested object"
            )
        if binding is not origin.original_binding:
            raise ExecutionPlanningCorrespondenceError(
                "order specification constructor binding is not the original "
                "attested object"
            )
        if any(
            retained_source is not origin_source
            for retained_source, origin_source in zip(
                expected_sources, origin_sources, strict=True
            )
        ):
            raise ExecutionPlanningCorrespondenceError(
                "order specification source identity is not original "
                "according to constructor binding"
            )
        if (
            attested["_original_state"] is not origin.original_state
            or attested["_original_binding"] is not origin.original_binding
            or any(
                attested_source is not origin_source
                for attested_source, origin_source in zip(
                    attested_sources, origin_sources, strict=True
                )
            )
        ):
            raise ExecutionPlanningCorrespondenceError(
                "order specification attestation contradicts registered origin"
            )
        _validate_constructor_state_types(
            state,
            price_is_absent=origin.limit_price_choice is None,
        )
        if type(binding) is not tuple or len(cast(tuple[object, ...], binding)) != 7:
            raise ExecutionPlanningCorrespondenceError(
                "order specification constructor binding is invalid"
            )
        bound = cast(tuple[object, ...], binding)
        if bound[0] is not state or any(
            bound[index + 1] is not source
            for index, source in enumerate(origin_sources)
        ):
            raise ExecutionPlanningCorrespondenceError(
                "order specification constructor binding is invalid"
            )

        sources = _validate_retained_sources(retained)
        expected_state = _constructor_state(sources)
        if any(
            cast(tuple[object, ...], state)[index] != expected_state[index]
            for index in range(7)
        ):
            raise ExecutionPlanningCorrespondenceError(
                "order specification contradicts constructor state"
            )

        schema_version = retained["schema_version"]
        if (
            type(schema_version) is not str
            or schema_version != BROKER_NEUTRAL_ORDER_SPECIFICATION_SCHEMA
        ):
            raise ExecutionPlanningCorrespondenceError(
                "order specification schema_version is invalid"
            )
        expected_fingerprint = canonical_fingerprint(_fingerprint_payload(sources))
        fingerprint = retained["fingerprint"]
        if type(fingerprint) is not str or fingerprint != expected_fingerprint:
            raise ExecutionPlanningCorrespondenceError(
                "order specification fingerprint does not match content"
            )
        return sources

    def to_dict(self) -> dict[str, object]:
        """Return the complete bounded nested specification projection."""

        sources = self._validate()
        return {
            "schema_version": self.schema_version,
            "instruction": sources["instruction_projection"],
            "canonical_instrument": sources["canonical_projection"],
            "order_style_choice": sources["style_projection"],
            "limit_price_choice": sources["price_projection"],
            "time_in_force_choice": sources["tif_projection"],
            "session_participation_choice": sources["session_projection"],
            "fingerprint": self.fingerprint,
        }


def construct_broker_neutral_order_specification(
    *,
    instruction: BrokerNeutralExecutionInstruction,
    canonical_instrument: CanonicalInstrument,
    order_style_choice: OrderStyleChoice,
    limit_price_choice: LimitPriceChoice | None,
    time_in_force_choice: TimeInForceChoice,
    session_participation_choice: SessionParticipationChoice,
) -> BrokerNeutralOrderSpecification:
    """Construct one complete canonical but unauthorized order request."""

    return BrokerNeutralOrderSpecification._create(
        instruction=instruction,
        canonical_instrument=canonical_instrument,
        order_style_choice=order_style_choice,
        limit_price_choice=limit_price_choice,
        time_in_force_choice=time_in_force_choice,
        session_participation_choice=session_participation_choice,
        creation_seal=_SPECIFICATION_CREATION_SEAL,
    )


def _validate_factory_sources(
    *,
    instruction: object,
    canonical_instrument: object,
    order_style_choice: object,
    limit_price_choice: object,
    time_in_force_choice: object,
    session_participation_choice: object,
) -> dict[str, object]:
    for value, expected, name in (
        (instruction, BrokerNeutralExecutionInstruction, "instruction"),
        (canonical_instrument, CanonicalInstrument, "canonical_instrument"),
        (order_style_choice, OrderStyleChoice, "order_style_choice"),
        (time_in_force_choice, TimeInForceChoice, "time_in_force_choice"),
        (
            session_participation_choice,
            SessionParticipationChoice,
            "session_participation_choice",
        ),
    ):
        if type(value) is not expected:
            raise ExecutionPlanningValidationError(
                f"{name} must have exact runtime type {expected.__name__}"
            )
    return _validate_sources(
        instruction=cast(BrokerNeutralExecutionInstruction, instruction),
        canonical_instrument=cast(CanonicalInstrument, canonical_instrument),
        order_style_choice=cast(OrderStyleChoice, order_style_choice),
        limit_price_choice=limit_price_choice,
        time_in_force_choice=cast(TimeInForceChoice, time_in_force_choice),
        session_participation_choice=cast(
            SessionParticipationChoice, session_participation_choice
        ),
        retained=False,
    )


def _validate_retained_sources(retained: dict[str, object]) -> dict[str, object]:
    for name, expected in (
        ("instruction", BrokerNeutralExecutionInstruction),
        ("canonical_instrument", CanonicalInstrument),
        ("order_style_choice", OrderStyleChoice),
        ("time_in_force_choice", TimeInForceChoice),
        ("session_participation_choice", SessionParticipationChoice),
    ):
        if type(retained[name]) is not expected:
            raise ExecutionPlanningCorrespondenceError(
                f"order specification retains invalid {name}"
            )
    return _validate_sources(
        instruction=cast(BrokerNeutralExecutionInstruction, retained["instruction"]),
        canonical_instrument=cast(
            CanonicalInstrument, retained["canonical_instrument"]
        ),
        order_style_choice=cast(OrderStyleChoice, retained["order_style_choice"]),
        limit_price_choice=retained["limit_price_choice"],
        time_in_force_choice=cast(TimeInForceChoice, retained["time_in_force_choice"]),
        session_participation_choice=cast(
            SessionParticipationChoice, retained["session_participation_choice"]
        ),
        retained=True,
    )


def _validate_sources(
    *,
    instruction: BrokerNeutralExecutionInstruction,
    canonical_instrument: CanonicalInstrument,
    order_style_choice: OrderStyleChoice,
    limit_price_choice: object,
    time_in_force_choice: TimeInForceChoice,
    session_participation_choice: SessionParticipationChoice,
    retained: bool,
) -> dict[str, object]:
    _require_source_identity(
        instruction,
        BROKER_NEUTRAL_EXECUTION_INSTRUCTION_SCHEMA,
        "instruction",
    )
    instruction_projection = instruction.to_dict()
    reconstructed, canonical_projection = _reconstruct_canonical_instrument(
        canonical_instrument
    )
    _require_source_identity(
        order_style_choice, ORDER_STYLE_CHOICE_SCHEMA, "order_style_choice"
    )
    style_projection = order_style_choice.to_dict()
    _require_source_identity(
        time_in_force_choice, TIME_IN_FORCE_CHOICE_SCHEMA, "time_in_force_choice"
    )
    tif_projection = time_in_force_choice.to_dict()
    _require_source_identity(
        session_participation_choice,
        SESSION_PARTICIPATION_CHOICE_SCHEMA,
        "session_participation_choice",
    )
    session_projection = session_participation_choice.to_dict()

    style = order_style_choice.style
    if style is OrderStyle.MARKET:
        if limit_price_choice is not None:
            _raise_cross_source(
                "MARKET requires explicit limit_price_choice=None", retained=retained
            )
        price = None
        price_projection = None
    elif style is OrderStyle.LIMIT:
        if type(limit_price_choice) is not LimitPriceChoice:
            _raise_cross_source(
                "LIMIT requires an exact LimitPriceChoice", retained=retained
            )
        price = cast(LimitPriceChoice, limit_price_choice)
        _require_source_identity(price, LIMIT_PRICE_CHOICE_SCHEMA, "limit_price_choice")
        price_projection = price.to_dict()
        if type(price.trading_currency) is not str:
            raise ExecutionPlanningCorrespondenceError(
                "limit price retains invalid trading currency"
            )
        if price.trading_currency != reconstructed.trading_currency:
            _raise_cross_source(
                "limit price currency does not match canonical instrument",
                retained=retained,
            )
    else:
        raise ExecutionPlanningCorrespondenceError(
            "order style choice retains unsupported style"
        )

    instruction_id = instruction.canonical_instrument_id.instrument_id
    canonical_id = reconstructed.instrument_id.instrument_id
    if instruction_id != canonical_id:
        _raise_cross_source(
            "instruction and canonical instrument IDs do not correspond",
            retained=retained,
        )
    if instruction.canonical_instrument_fingerprint != reconstructed.fingerprint:
        _raise_cross_source(
            "instruction and canonical instrument fingerprints do not correspond",
            retained=retained,
        )

    return {
        "instruction": instruction,
        "canonical_instrument": canonical_instrument,
        "order_style_choice": order_style_choice,
        "limit_price_choice": price,
        "time_in_force_choice": time_in_force_choice,
        "session_participation_choice": session_participation_choice,
        "instruction_projection": instruction_projection,
        "canonical_projection": canonical_projection,
        "style_projection": style_projection,
        "price_projection": price_projection,
        "tif_projection": tif_projection,
        "session_projection": session_projection,
    }


def _require_source_identity(value: object, schema: str, subject: str) -> None:
    retained_schema = required_retained_attribute(value, "schema_version", subject)
    if type(retained_schema) is not str or retained_schema != schema:
        raise ExecutionPlanningCorrespondenceError(
            f"{subject} schema_version is not canonical"
        )
    fingerprint = required_retained_attribute(value, "fingerprint", subject)
    if type(fingerprint) is not str:
        raise ExecutionPlanningCorrespondenceError(
            f"{subject} fingerprint is not canonical"
        )


def _reconstruct_canonical_instrument(
    value: CanonicalInstrument,
) -> tuple[CanonicalInstrument, dict[str, object]]:
    retained = {
        name: required_retained_attribute(value, name, "canonical instrument")
        for name in (
            "instrument_id",
            "trading_identity",
            "asset_class",
            "trading_currency",
            "schema_version",
            "fingerprint",
        )
    }
    schema = retained["schema_version"]
    fingerprint = retained["fingerprint"]
    currency = retained["trading_currency"]
    if type(schema) is not str or schema != CANONICAL_INSTRUMENT_SCHEMA_VERSION:
        raise ExecutionPlanningCorrespondenceError(
            "canonical instrument schema_version is not canonical"
        )
    if type(fingerprint) is not str:
        raise ExecutionPlanningCorrespondenceError(
            "canonical instrument fingerprint is not canonical"
        )
    if type(currency) is not str:
        raise ExecutionPlanningCorrespondenceError(
            "canonical instrument trading_currency is not canonical"
        )
    instrument_id = retained["instrument_id"]
    if type(instrument_id) is not CanonicalInstrumentId:
        raise ExecutionPlanningCorrespondenceError(
            "canonical instrument ID has invalid runtime type"
        )
    identifier = required_retained_attribute(
        instrument_id, "instrument_id", "canonical instrument ID"
    )
    if type(identifier) is not str:
        raise ExecutionPlanningCorrespondenceError(
            "canonical instrument ID is not canonical"
        )
    identity = retained["trading_identity"]
    if type(identity) is not TradingInstrumentIdentity:
        raise ExecutionPlanningCorrespondenceError(
            "canonical trading identity has invalid runtime type"
        )
    identity_state = {
        name: required_retained_attribute(identity, name, "trading identity")
        for name in (
            "symbol",
            "venue",
            "schema_version",
            "instrument_fingerprint",
        )
    }
    if any(type(identity_state[name]) is not str for name in identity_state):
        raise ExecutionPlanningCorrespondenceError(
            "trading identity retains noncanonical string state"
        )
    if identity_state["schema_version"] != TRADING_INSTRUMENT_IDENTITY_SCHEMA_VERSION:
        raise ExecutionPlanningCorrespondenceError(
            "trading identity schema_version is not canonical"
        )
    asset_class = retained["asset_class"]
    if type(asset_class) is not InstrumentAssetClass:
        raise ExecutionPlanningCorrespondenceError(
            "canonical instrument asset_class has invalid runtime type"
        )
    try:
        reconstructed_id = CanonicalInstrumentId(identifier)
        reconstructed_identity = TradingInstrumentIdentity(
            symbol=cast(str, identity_state["symbol"]),
            venue=cast(str, identity_state["venue"]),
        )
        reconstructed = CanonicalInstrument(
            instrument_id=reconstructed_id,
            trading_identity=reconstructed_identity,
            asset_class=asset_class,
            trading_currency=currency,
        )
    except (TypeError, ValueError, InstrumentValidationError) as error:
        raise ExecutionPlanningCorrespondenceError(
            "canonical instrument cannot be reconstructed"
        ) from error
    if (
        instrument_id.to_dict() != reconstructed_id.to_dict()
        or identity.to_dict() != reconstructed_identity.to_dict()
        or fingerprint != reconstructed.fingerprint
        or value.to_dict() != reconstructed.to_dict()
    ):
        raise ExecutionPlanningCorrespondenceError(
            "canonical instrument does not match canonical reconstruction"
        )
    return reconstructed, reconstructed.to_dict()


def _validate_constructor_state_types(
    state: object,
    *,
    price_is_absent: bool,
) -> None:
    if type(state) is not tuple or len(cast(tuple[object, ...], state)) != 7:
        raise ExecutionPlanningCorrespondenceError(
            "order specification constructor state is invalid"
        )
    retained_state = cast(tuple[object, ...], state)
    for index in (0, 1, 2, 4, 5, 6):
        if type(retained_state[index]) is not str:
            raise ExecutionPlanningCorrespondenceError(
                "order specification constructor state is invalid"
            )
    price_fingerprint = retained_state[3]
    if price_is_absent:
        if price_fingerprint is not None:
            raise ExecutionPlanningCorrespondenceError(
                "order specification constructor state is invalid"
            )
    elif type(price_fingerprint) is not str:
        raise ExecutionPlanningCorrespondenceError(
            "order specification constructor state is invalid"
        )


def _constructor_state(sources: dict[str, object]) -> tuple[object, ...]:
    instruction = cast(BrokerNeutralExecutionInstruction, sources["instruction"])
    canonical = cast(CanonicalInstrument, sources["canonical_instrument"])
    style = cast(OrderStyleChoice, sources["order_style_choice"])
    price = cast(LimitPriceChoice | None, sources["limit_price_choice"])
    tif = cast(TimeInForceChoice, sources["time_in_force_choice"])
    session = cast(SessionParticipationChoice, sources["session_participation_choice"])
    return (
        instruction.fingerprint,
        canonical.fingerprint,
        style.fingerprint,
        None if price is None else price.fingerprint,
        tif.fingerprint,
        session.fingerprint,
        BROKER_NEUTRAL_ORDER_SPECIFICATION_SCHEMA,
    )


def _fingerprint_payload(sources: dict[str, object]) -> dict[str, object]:
    state = _constructor_state(sources)
    return {
        "schema_version": state[6],
        "instruction_fingerprint": state[0],
        "canonical_instrument_fingerprint": state[1],
        "order_style_choice_fingerprint": state[2],
        "limit_price_choice_fingerprint": state[3],
        "time_in_force_choice_fingerprint": state[4],
        "session_participation_choice_fingerprint": state[5],
    }


def _raise_cross_source(message: str, *, retained: bool) -> None:
    if retained:
        raise ExecutionPlanningCorrespondenceError(message)
    raise ExecutionPlanningValidationError(message)


__all__ = [
    "BROKER_NEUTRAL_ORDER_SPECIFICATION_SCHEMA",
    "BrokerNeutralOrderSpecification",
    "construct_broker_neutral_order_specification",
]
