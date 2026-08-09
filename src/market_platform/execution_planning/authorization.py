"""Deterministic submission-bound authorization without broker effects."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, fields
from datetime import UTC, datetime
from typing import cast

from market_platform._fingerprint import canonical_fingerprint
from market_platform.execution_planning._canonical import (
    canonical_plan_time,
    required_fingerprint,
    required_retained_attribute,
    timestamp_text,
)
from market_platform.execution_planning.compatibility import (
    BrokerExecutionStructuralCompatibilityOutcome,
    BrokerExecutionStructuralCompatibilityResult,
)
from market_platform.execution_planning.errors import (
    ExecutionPlanningCorrespondenceError,
    ExecutionPlanningValidationError,
)
from market_platform.execution_planning.native_order_mapping import (
    BrokerNativeOrderMapping,
)
from market_platform.execution_planning.order_specification import (
    BrokerNeutralOrderSpecification,
)
from market_platform.execution_planning.translation import PositionTargetTranslation
from market_platform.risk import (
    RiskDecision,
    RiskDecisionOutcome,
    RiskDomainError,
    RiskEvaluationContext,
    evaluate_structural_risk,
)

BROKER_NEUTRAL_EXECUTION_AUTHORIZATION_POLICY_IDENTITY_SCHEMA = (
    "broker_neutral_execution_authorization_policy_identity/v1"
)
BROKER_NEUTRAL_EXECUTION_AUTHORIZATION_SCHEMA = (
    "broker_neutral_execution_authorization/v1"
)
_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", flags=re.ASCII)
_VERSION_MAXIMUM = 64
_POLICY_SEAL = object()
_AUTHORIZATION_SEAL = object()


@dataclass(frozen=True, slots=True, init=False)
class BrokerNeutralExecutionAuthorizationPolicyIdentity:
    """Immutable declared identity of the platform authorization rule set.

    This records provenance, not behavioral policy or code authenticity. The
    v1 evaluator owns the fixed authorization rules.
    """

    policy_id: str
    policy_version: str
    schema_version: str = field(init=False)
    fingerprint: str = field(init=False)

    def __init__(self) -> None:
        raise TypeError(
            "BrokerNeutralExecutionAuthorizationPolicyIdentity must be created "
            "by construct_broker_neutral_execution_authorization_policy_identity()"
        )

    @classmethod
    def _create(
        cls, *, policy_id: str, policy_version: str, creation_seal: object
    ) -> BrokerNeutralExecutionAuthorizationPolicyIdentity:
        if creation_seal is not _POLICY_SEAL:
            raise TypeError("authorization policy identity construction is private")
        policy_id = _opaque_id(policy_id, "policy_id", retained=False)
        policy_version = _visible_ascii(
            policy_version, "policy_version", retained=False
        )
        result = object.__new__(cls)
        object.__setattr__(result, "policy_id", policy_id)
        object.__setattr__(result, "policy_version", policy_version)
        object.__setattr__(
            result,
            "schema_version",
            BROKER_NEUTRAL_EXECUTION_AUTHORIZATION_POLICY_IDENTITY_SCHEMA,
        )
        object.__setattr__(
            result, "fingerprint", canonical_fingerprint(result._fingerprint_payload())
        )
        result._validate()
        return result

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
        }

    def _validate(self) -> None:
        retained = _retained(
            self,
            "authorization policy identity",
            ("policy_id", "policy_version", "schema_version", "fingerprint"),
        )
        policy_id = _opaque_id(retained["policy_id"], "policy_id", retained=True)
        policy_version = _visible_ascii(
            retained["policy_version"], "policy_version", retained=True
        )
        schema = retained["schema_version"]
        if (
            type(schema) is not str
            or schema != BROKER_NEUTRAL_EXECUTION_AUTHORIZATION_POLICY_IDENTITY_SCHEMA
        ):
            raise ExecutionPlanningCorrespondenceError(
                "authorization policy identity schema_version is invalid"
            )
        expected = canonical_fingerprint(
            {
                "schema_version": schema,
                "policy_id": policy_id,
                "policy_version": policy_version,
            }
        )
        if (
            type(retained["fingerprint"]) is not str
            or retained["fingerprint"] != expected
        ):
            raise ExecutionPlanningCorrespondenceError(
                "authorization policy identity fingerprint does not match content"
            )

    def to_dict(self) -> dict[str, object]:
        """Return the canonical JSON-safe policy-identity projection."""
        self._validate()
        return {**self._fingerprint_payload(), "fingerprint": self.fingerprint}


def construct_broker_neutral_execution_authorization_policy_identity(
    *, policy_id: str, policy_version: str
) -> BrokerNeutralExecutionAuthorizationPolicyIdentity:
    """Construct one declared platform authorization rule-set identity."""
    return BrokerNeutralExecutionAuthorizationPolicyIdentity._create(
        policy_id=policy_id, policy_version=policy_version, creation_seal=_POLICY_SEAL
    )


@dataclass(frozen=True, slots=True, init=False)
class BrokerNeutralExecutionAuthorization:
    """Self-contained permission for one exact broker-native mapping.

    This success-only value binds evidence but retains no upstream source. It
    is not broker acceptance, submission, or indefinite authority.
    """

    authorization_policy_id: str
    authorization_policy_version: str
    authorization_policy_identity_fingerprint: str
    risk_context_fingerprint: str
    risk_decision_fingerprint: str
    position_target_translation_fingerprint: str
    order_specification_fingerprint: str
    structural_compatibility_result_fingerprint: str
    broker_native_order_mapping_fingerprint: str
    execution_target_id: str
    account_fingerprint: str
    evidence_as_of: datetime
    authorization_as_of: datetime
    schema_version: str = field(init=False)
    fingerprint: str = field(init=False)

    def __init__(self) -> None:
        raise TypeError(
            "BrokerNeutralExecutionAuthorization must be created by "
            "authorize_broker_neutral_execution()"
        )

    @classmethod
    def _create(
        cls, *, creation_seal: object, **inputs: object
    ) -> BrokerNeutralExecutionAuthorization:
        if creation_seal is not _AUTHORIZATION_SEAL:
            raise TypeError("broker-neutral execution authorization is evaluator-owned")
        values = _validate_authorization_values(retained=False, **inputs)
        result = object.__new__(cls)
        for name, value in values.items():
            object.__setattr__(result, name, value)
        object.__setattr__(
            result, "schema_version", BROKER_NEUTRAL_EXECUTION_AUTHORIZATION_SCHEMA
        )
        object.__setattr__(
            result, "fingerprint", canonical_fingerprint(result._fingerprint_payload())
        )
        result._validate()
        return result

    def _fingerprint_payload(self) -> dict[str, object]:
        return _authorization_payload(
            schema_version=self.schema_version,
            **{
                name: object.__getattribute__(self, name)
                for name in _AUTHORIZATION_FIELDS
            },
        )

    def _validate(self) -> None:
        retained = _retained(
            self,
            "broker-neutral execution authorization",
            (*_AUTHORIZATION_FIELDS, "schema_version", "fingerprint"),
        )
        values = _validate_authorization_values(
            retained=True, **{name: retained[name] for name in _AUTHORIZATION_FIELDS}
        )
        schema = retained["schema_version"]
        if (
            type(schema) is not str
            or schema != BROKER_NEUTRAL_EXECUTION_AUTHORIZATION_SCHEMA
        ):
            raise ExecutionPlanningCorrespondenceError(
                "broker-neutral execution authorization schema_version is invalid"
            )
        expected = canonical_fingerprint(
            _authorization_payload(schema_version=schema, **values)
        )
        if (
            type(retained["fingerprint"]) is not str
            or retained["fingerprint"] != expected
        ):
            raise ExecutionPlanningCorrespondenceError(
                "broker-neutral execution authorization fingerprint does not "
                "match content"
            )

    def to_dict(self) -> dict[str, object]:
        """Return the deterministic submission-bound permission projection."""
        self._validate()
        return {**self._fingerprint_payload(), "fingerprint": self.fingerprint}


_AUTHORIZATION_FIELDS = (
    "authorization_policy_id",
    "authorization_policy_version",
    "authorization_policy_identity_fingerprint",
    "risk_context_fingerprint",
    "risk_decision_fingerprint",
    "position_target_translation_fingerprint",
    "order_specification_fingerprint",
    "structural_compatibility_result_fingerprint",
    "broker_native_order_mapping_fingerprint",
    "execution_target_id",
    "account_fingerprint",
    "evidence_as_of",
    "authorization_as_of",
)


def authorize_broker_neutral_execution(
    *,
    risk_context: RiskEvaluationContext,
    risk_decision: RiskDecision,
    position_target_translation: PositionTargetTranslation,
    specification: BrokerNeutralOrderSpecification,
    compatibility_result: BrokerExecutionStructuralCompatibilityResult,
    native_order_mapping: BrokerNativeOrderMapping,
    authorization_policy_identity: BrokerNeutralExecutionAuthorizationPolicyIdentity,
    authorization_as_of: datetime,
) -> BrokerNeutralExecutionAuthorization:
    """Authorize one exact mapping for a later, separate submission boundary.

    Structural risk is replayed exactly once to validate supplied evidence. No
    authorization-specific risk rule or broker-native token meaning is added.
    """
    sources: dict[str, object] = {
        "risk_context": risk_context,
        "risk_decision": risk_decision,
        "position_target_translation": position_target_translation,
        "specification": specification,
        "compatibility_result": compatibility_result,
        "native_order_mapping": native_order_mapping,
        "authorization_policy_identity": authorization_policy_identity,
    }
    _validate_source_types(sources)
    _validate_source_state(
        risk_context=risk_context,
        risk_decision=risk_decision,
        position_target_translation=position_target_translation,
        specification=specification,
        compatibility_result=compatibility_result,
        native_order_mapping=native_order_mapping,
        authorization_policy_identity=authorization_policy_identity,
    )
    try:
        replayed = evaluate_structural_risk(risk_context)
        replayed_projection = replayed.to_dict()
        supplied_projection = risk_decision.to_dict()
    except RiskDomainError as error:
        raise ExecutionPlanningCorrespondenceError(
            "authorization risk evidence cannot be replayed canonically"
        ) from error
    if replayed_projection != supplied_projection:
        raise ExecutionPlanningValidationError(
            "risk decision does not correspond to replayed risk context"
        )
    if (
        risk_decision.outcome is not RiskDecisionOutcome.APPROVED
        or risk_decision.findings != ()
        or risk_decision.common_account_fingerprint is None
    ):
        raise ExecutionPlanningValidationError(
            "authorization requires an exact approved structural risk decision"
        )
    _require_translation_correspondence(
        risk_context, risk_decision, position_target_translation
    )
    _require_specification_correspondence(position_target_translation, specification)
    _require_compatibility_correspondence(specification, compatibility_result)
    _require_mapping_correspondence(
        specification, compatibility_result, native_order_mapping
    )
    evidence_as_of = risk_context.evaluation_as_of
    authorization_time = _canonical_public_time(authorization_as_of)
    if authorization_time < evidence_as_of:
        raise ExecutionPlanningValidationError(
            "authorization_as_of must not precede evidence_as_of"
        )
    return BrokerNeutralExecutionAuthorization._create(
        authorization_policy_id=authorization_policy_identity.policy_id,
        authorization_policy_version=authorization_policy_identity.policy_version,
        authorization_policy_identity_fingerprint=authorization_policy_identity.fingerprint,
        risk_context_fingerprint=risk_context.fingerprint,
        risk_decision_fingerprint=risk_decision.fingerprint,
        position_target_translation_fingerprint=position_target_translation.fingerprint,
        order_specification_fingerprint=specification.fingerprint,
        structural_compatibility_result_fingerprint=compatibility_result.fingerprint,
        broker_native_order_mapping_fingerprint=native_order_mapping.fingerprint,
        execution_target_id=native_order_mapping.execution_target_id,
        account_fingerprint=risk_decision.common_account_fingerprint,
        evidence_as_of=evidence_as_of,
        authorization_as_of=authorization_time,
        creation_seal=_AUTHORIZATION_SEAL,
    )


def _validate_source_types(sources: dict[str, object]) -> None:
    expected = {
        "risk_context": RiskEvaluationContext,
        "risk_decision": RiskDecision,
        "position_target_translation": PositionTargetTranslation,
        "specification": BrokerNeutralOrderSpecification,
        "compatibility_result": BrokerExecutionStructuralCompatibilityResult,
        "native_order_mapping": BrokerNativeOrderMapping,
        "authorization_policy_identity": (
            BrokerNeutralExecutionAuthorizationPolicyIdentity
        ),
    }
    for name, source in sources.items():
        if type(source) is not expected[name]:
            raise ExecutionPlanningValidationError(
                f"{name} must have exact runtime type {expected[name].__name__}"
            )


def _validate_source_state(
    *,
    risk_context: RiskEvaluationContext,
    risk_decision: RiskDecision,
    position_target_translation: PositionTargetTranslation,
    specification: BrokerNeutralOrderSpecification,
    compatibility_result: BrokerExecutionStructuralCompatibilityResult,
    native_order_mapping: BrokerNativeOrderMapping,
    authorization_policy_identity: BrokerNeutralExecutionAuthorizationPolicyIdentity,
) -> None:
    for source, subject in (
        (risk_context, "authorization risk context"),
        (risk_decision, "authorization risk decision"),
    ):
        for retained_field in fields(source):
            required_retained_attribute(source, retained_field.name, subject)
    try:
        risk_context._validate()
        risk_decision._validate()
    except RiskDomainError as error:
        raise ExecutionPlanningCorrespondenceError(
            "authorization risk source retains noncanonical state"
        ) from error
    position_target_translation._validate()
    specification._validate()
    compatibility_result._validate()
    native_order_mapping._validate()
    authorization_policy_identity._validate()


def _require_translation_correspondence(
    context: RiskEvaluationContext,
    decision: RiskDecision,
    translation: PositionTargetTranslation,
) -> None:
    if (
        translation.risk_context_fingerprint != context.fingerprint
        or translation.risk_decision_fingerprint != decision.fingerprint
        or translation.order_intent_fingerprint
        != context.order_intent.intent_fingerprint
        or translation.account_fingerprint != decision.common_account_fingerprint
        or translation.position_snapshot_fingerprint
        != decision.position_snapshot_fingerprint
        or translation.open_order_snapshot_fingerprint
        != decision.open_order_snapshot_fingerprint
        or translation.plan_as_of != context.evaluation_as_of
        or translation.plan_as_of != decision.evaluation_as_of
    ):
        raise ExecutionPlanningValidationError(
            "position translation does not correspond to risk evidence"
        )


def _require_specification_correspondence(
    translation: PositionTargetTranslation,
    specification: BrokerNeutralOrderSpecification,
) -> None:
    instruction = specification.instruction
    if (
        instruction.source_translation_fingerprint != translation.fingerprint
        or instruction.account_fingerprint != translation.account_fingerprint
        or instruction.plan_as_of != translation.plan_as_of
        or instruction.canonical_instrument_fingerprint
        != translation.canonical_instrument_fingerprint
        or instruction.canonical_instrument_id.to_dict()
        != translation.canonical_instrument_id.to_dict()
    ):
        raise ExecutionPlanningValidationError(
            "order specification does not correspond to position translation"
        )


def _require_compatibility_correspondence(
    specification: BrokerNeutralOrderSpecification,
    result: BrokerExecutionStructuralCompatibilityResult,
) -> None:
    if (
        result.outcome is not BrokerExecutionStructuralCompatibilityOutcome.COMPATIBLE
        or result.rejection_reasons != ()
    ):
        raise ExecutionPlanningValidationError(
            "authorization requires an exact compatible structural result"
        )
    if result.order_specification_fingerprint != specification.fingerprint:
        raise ExecutionPlanningValidationError(
            "compatibility result does not correspond to specification"
        )


def _require_mapping_correspondence(
    specification: BrokerNeutralOrderSpecification,
    compatibility: BrokerExecutionStructuralCompatibilityResult,
    mapping: BrokerNativeOrderMapping,
) -> None:
    if (
        mapping.order_specification_fingerprint != specification.fingerprint
        or mapping.structural_compatibility_result_fingerprint
        != compatibility.fingerprint
        or mapping.capability_profile_fingerprint
        != compatibility.capability_profile_fingerprint
    ):
        raise ExecutionPlanningValidationError(
            "broker-native mapping does not correspond to authorization evidence"
        )


def _validate_authorization_values(
    *, retained: bool, **inputs: object
) -> dict[str, object]:
    policy_id = _opaque_id(
        inputs["authorization_policy_id"], "authorization_policy_id", retained=retained
    )
    policy_version = _visible_ascii(
        inputs["authorization_policy_version"],
        "authorization_policy_version",
        retained=retained,
    )
    fingerprint_names = _AUTHORIZATION_FIELDS[2:9] + ("account_fingerprint",)
    fingerprints: dict[str, str] = {}
    try:
        for name in fingerprint_names:
            fingerprints[name] = required_fingerprint(inputs[name], name)
    except ExecutionPlanningValidationError as error:
        if retained:
            raise ExecutionPlanningCorrespondenceError(
                "authorization retains malformed fingerprint evidence"
            ) from error
        raise
    target = _opaque_id(
        inputs["execution_target_id"], "execution_target_id", retained=retained
    )
    try:
        evidence_time = canonical_plan_time(inputs["evidence_as_of"], "evidence_as_of")
        authorization_time = canonical_plan_time(
            inputs["authorization_as_of"], "authorization_as_of"
        )
    except ExecutionPlanningValidationError as error:
        if retained:
            raise ExecutionPlanningCorrespondenceError(
                "authorization retains noncanonical datetime state"
            ) from error
        raise
    error_type = (
        ExecutionPlanningCorrespondenceError
        if retained
        else ExecutionPlanningValidationError
    )
    if authorization_time < evidence_time:
        raise error_type("authorization_as_of must not precede evidence_as_of")
    identity = construct_broker_neutral_execution_authorization_policy_identity(
        policy_id=policy_id, policy_version=policy_version
    )
    if (
        fingerprints["authorization_policy_identity_fingerprint"]
        != identity.fingerprint
    ):
        raise error_type("authorization policy identity fields do not correspond")
    return {
        "authorization_policy_id": policy_id,
        "authorization_policy_version": policy_version,
        **fingerprints,
        "execution_target_id": target,
        "evidence_as_of": evidence_time,
        "authorization_as_of": authorization_time,
    }


def _authorization_payload(
    *, schema_version: str, **values: object
) -> dict[str, object]:
    projected = {name: values[name] for name in _AUTHORIZATION_FIELDS}
    projected["evidence_as_of"] = timestamp_text(
        cast(datetime, values["evidence_as_of"])
    )
    projected["authorization_as_of"] = timestamp_text(
        cast(datetime, values["authorization_as_of"])
    )
    return {"schema_version": schema_version, **projected}


def _retained(value: object, subject: str, names: tuple[str, ...]) -> dict[str, object]:
    return {name: required_retained_attribute(value, name, subject) for name in names}


def _opaque_id(value: object, field_name: str, *, retained: bool) -> str:
    if type(value) is str and _ID_PATTERN.fullmatch(value) is not None:
        return value
    error_type = (
        ExecutionPlanningCorrespondenceError
        if retained
        else ExecutionPlanningValidationError
    )
    raise error_type(f"{field_name} must match [A-Za-z0-9][A-Za-z0-9._-]{{0,127}}")


def _visible_ascii(value: object, field_name: str, *, retained: bool) -> str:
    valid = (
        type(value) is str
        and 1 <= len(value) <= _VERSION_MAXIMUM
        and all(0x21 <= ord(character) <= 0x7E for character in value)
    )
    if valid:
        return cast(str, value)
    error_type = (
        ExecutionPlanningCorrespondenceError
        if retained
        else ExecutionPlanningValidationError
    )
    raise error_type(
        f"{field_name} must contain 1-{_VERSION_MAXIMUM} visible ASCII characters"
    )


def _canonical_public_time(value: object) -> datetime:
    if type(value) is not datetime:
        raise ExecutionPlanningValidationError(
            "authorization_as_of must be an exact datetime"
        )
    timestamp = value
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ExecutionPlanningValidationError(
            "authorization_as_of must be timezone-aware"
        )
    return timestamp.astimezone(UTC)


__all__ = [
    "BROKER_NEUTRAL_EXECUTION_AUTHORIZATION_POLICY_IDENTITY_SCHEMA",
    "BrokerNeutralExecutionAuthorizationPolicyIdentity",
    "construct_broker_neutral_execution_authorization_policy_identity",
    "BROKER_NEUTRAL_EXECUTION_AUTHORIZATION_SCHEMA",
    "BrokerNeutralExecutionAuthorization",
    "authorize_broker_neutral_execution",
]
