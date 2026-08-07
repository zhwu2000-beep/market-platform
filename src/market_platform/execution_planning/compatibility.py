"""Offline structural compatibility for broker-neutral order specifications.

Results cover only the bounded dimensions declared by a capability profile.
COMPATIBLE is not complete broker executability, authorization, routing
approval, submission readiness, live broker acceptance, account eligibility,
or market-open eligibility. Quantity, lot, tick, collar and band rules,
product/account restrictions, and asset/currency/venue matrices are deferred.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import cast

from market_platform._fingerprint import canonical_fingerprint
from market_platform.execution_planning._canonical import (
    required_fingerprint,
    required_retained_attribute,
)
from market_platform.execution_planning.capability import (
    BrokerExecutionCapabilityProfile,
)
from market_platform.execution_planning.errors import (
    ExecutionPlanningCorrespondenceError,
    ExecutionPlanningValidationError,
)
from market_platform.execution_planning.order_specification import (
    BrokerNeutralOrderSpecification,
)

BROKER_EXECUTION_STRUCTURAL_COMPATIBILITY_RESULT_SCHEMA = (
    "broker_execution_structural_compatibility_result/v1"
)


class BrokerExecutionStructuralCompatibilityOutcome(StrEnum):
    """Canonical outcome of bounded structural capability evaluation."""

    COMPATIBLE = "compatible"
    INCOMPATIBLE = "incompatible"


class BrokerExecutionStructuralCompatibilityReason(StrEnum):
    """Stable machine-readable reason for structural incompatibility."""

    UNSUPPORTED_ASSET_CLASS = "unsupported_asset_class"
    UNSUPPORTED_TRADING_CURRENCY = "unsupported_trading_currency"
    UNSUPPORTED_VENUE = "unsupported_venue"
    UNSUPPORTED_ORDER_STYLE = "unsupported_order_style"
    UNSUPPORTED_TIME_IN_FORCE = "unsupported_time_in_force"
    UNSUPPORTED_SESSION_PARTICIPATION = "unsupported_session_participation"
    UNSUPPORTED_ORDER_COMBINATION = "unsupported_order_combination"


_REASON_RANK = {
    BrokerExecutionStructuralCompatibilityReason.UNSUPPORTED_ASSET_CLASS: 0,
    BrokerExecutionStructuralCompatibilityReason.UNSUPPORTED_TRADING_CURRENCY: 1,
    BrokerExecutionStructuralCompatibilityReason.UNSUPPORTED_VENUE: 2,
    BrokerExecutionStructuralCompatibilityReason.UNSUPPORTED_ORDER_STYLE: 3,
    BrokerExecutionStructuralCompatibilityReason.UNSUPPORTED_TIME_IN_FORCE: 4,
    BrokerExecutionStructuralCompatibilityReason.UNSUPPORTED_SESSION_PARTICIPATION: 5,
    BrokerExecutionStructuralCompatibilityReason.UNSUPPORTED_ORDER_COMBINATION: 6,
}
_RESULT_CREATION_SEAL = object()


@dataclass(frozen=True, slots=True, init=False)
class BrokerExecutionStructuralCompatibilityResult:
    """Value-semantic evidence for bounded structural compatibility only.

    A COMPATIBLE outcome covers only capability-profile dimensions; it is not
    complete broker executability or evidence of authorization, routing,
    submission readiness, live acceptance, account eligibility, or market-open
    eligibility.
    """

    capability_profile_fingerprint: str
    order_specification_fingerprint: str
    outcome: BrokerExecutionStructuralCompatibilityOutcome
    rejection_reasons: tuple[BrokerExecutionStructuralCompatibilityReason, ...]
    schema_version: str = field(init=False)
    fingerprint: str = field(init=False)

    def __init__(self) -> None:
        raise TypeError(
            "BrokerExecutionStructuralCompatibilityResult must be created by "
            "evaluate_broker_execution_structural_compatibility()"
        )

    @classmethod
    def _create(
        cls,
        *,
        capability_profile_fingerprint: str,
        order_specification_fingerprint: str,
        outcome: BrokerExecutionStructuralCompatibilityOutcome,
        rejection_reasons: tuple[BrokerExecutionStructuralCompatibilityReason, ...],
        creation_seal: object,
    ) -> BrokerExecutionStructuralCompatibilityResult:
        if creation_seal is not _RESULT_CREATION_SEAL:
            raise TypeError("structural compatibility result is evaluator-owned")
        _validate_result_values(
            capability_profile_fingerprint=capability_profile_fingerprint,
            order_specification_fingerprint=order_specification_fingerprint,
            outcome=outcome,
            rejection_reasons=rejection_reasons,
            retained=False,
        )
        result = object.__new__(cls)
        for name, value in (
            ("capability_profile_fingerprint", capability_profile_fingerprint),
            ("order_specification_fingerprint", order_specification_fingerprint),
            ("outcome", outcome),
            ("rejection_reasons", rejection_reasons),
            ("schema_version", BROKER_EXECUTION_STRUCTURAL_COMPATIBILITY_RESULT_SCHEMA),
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
        return {
            "schema_version": self.schema_version,
            "capability_profile_fingerprint": self.capability_profile_fingerprint,
            "order_specification_fingerprint": self.order_specification_fingerprint,
            "outcome": self.outcome.value,
            "rejection_reasons": [reason.value for reason in self.rejection_reasons],
        }

    def _validate(self) -> None:
        retained = {
            name: required_retained_attribute(
                self, name, "broker execution structural compatibility result"
            )
            for name in (
                "capability_profile_fingerprint",
                "order_specification_fingerprint",
                "outcome",
                "rejection_reasons",
                "schema_version",
                "fingerprint",
            )
        }
        _validate_result_values(
            capability_profile_fingerprint=retained["capability_profile_fingerprint"],
            order_specification_fingerprint=retained["order_specification_fingerprint"],
            outcome=retained["outcome"],
            rejection_reasons=retained["rejection_reasons"],
            retained=True,
        )
        schema = retained["schema_version"]
        if (
            type(schema) is not str
            or schema != BROKER_EXECUTION_STRUCTURAL_COMPATIBILITY_RESULT_SCHEMA
        ):
            raise ExecutionPlanningCorrespondenceError(
                "structural compatibility result schema_version is invalid"
            )
        expected = canonical_fingerprint(
            {
                "schema_version": schema,
                "capability_profile_fingerprint": retained[
                    "capability_profile_fingerprint"
                ],
                "order_specification_fingerprint": retained[
                    "order_specification_fingerprint"
                ],
                "outcome": cast(
                    BrokerExecutionStructuralCompatibilityOutcome, retained["outcome"]
                ).value,
                "rejection_reasons": [
                    reason.value
                    for reason in cast(
                        tuple[BrokerExecutionStructuralCompatibilityReason, ...],
                        retained["rejection_reasons"],
                    )
                ],
            }
        )
        fingerprint = retained["fingerprint"]
        if type(fingerprint) is not str or fingerprint != expected:
            raise ExecutionPlanningCorrespondenceError(
                "structural compatibility result fingerprint does not match content"
            )

    def to_dict(self) -> dict[str, object]:
        """Return the canonical JSON-safe structural compatibility result."""

        self._validate()
        return {**self._fingerprint_payload(), "fingerprint": self.fingerprint}


def evaluate_broker_execution_structural_compatibility(
    *,
    specification: BrokerNeutralOrderSpecification,
    capability_profile: BrokerExecutionCapabilityProfile,
) -> BrokerExecutionStructuralCompatibilityResult:
    """Evaluate only the bounded structural dimensions declared by a profile.

    Independent asset, currency, and venue domains are treated as structurally
    composable. Quantity, lot, tick, collar/band, product/account, and
    cross-domain matrix restrictions remain outside this result, so COMPATIBLE
    does not mean complete broker executability.
    """

    if type(specification) is not BrokerNeutralOrderSpecification:
        raise ExecutionPlanningValidationError(
            "specification must be an exact BrokerNeutralOrderSpecification"
        )
    if type(capability_profile) is not BrokerExecutionCapabilityProfile:
        raise ExecutionPlanningValidationError(
            "capability_profile must be an exact BrokerExecutionCapabilityProfile"
        )
    specification._validate()
    capability_profile._validate()

    instrument = specification.canonical_instrument
    style = specification.order_style_choice.style
    tif = specification.time_in_force_choice.time_in_force
    session = specification.session_participation_choice.session_participation
    combinations = capability_profile.supported_order_combinations

    reasons: list[BrokerExecutionStructuralCompatibilityReason] = []
    if instrument.asset_class not in capability_profile.supported_asset_classes:
        reasons.append(
            BrokerExecutionStructuralCompatibilityReason.UNSUPPORTED_ASSET_CLASS
        )
    if (
        instrument.trading_currency
        not in capability_profile.supported_trading_currencies
    ):
        reasons.append(
            BrokerExecutionStructuralCompatibilityReason.UNSUPPORTED_TRADING_CURRENCY
        )
    if instrument.trading_identity.venue not in capability_profile.supported_venues:
        reasons.append(BrokerExecutionStructuralCompatibilityReason.UNSUPPORTED_VENUE)

    style_supported = any(combination[0] is style for combination in combinations)
    tif_supported = any(combination[1] is tif for combination in combinations)
    session_supported = any(combination[2] is session for combination in combinations)
    if not style_supported:
        reasons.append(
            BrokerExecutionStructuralCompatibilityReason.UNSUPPORTED_ORDER_STYLE
        )
    if not tif_supported:
        reasons.append(
            BrokerExecutionStructuralCompatibilityReason.UNSUPPORTED_TIME_IN_FORCE
        )
    if not session_supported:
        reasons.append(
            BrokerExecutionStructuralCompatibilityReason.UNSUPPORTED_SESSION_PARTICIPATION
        )
    if (
        style_supported
        and tif_supported
        and session_supported
        and not any(
            combination[0] is style
            and combination[1] is tif
            and combination[2] is session
            for combination in combinations
        )
    ):
        reasons.append(
            BrokerExecutionStructuralCompatibilityReason.UNSUPPORTED_ORDER_COMBINATION
        )

    reason_tuple = tuple(reasons)
    outcome = (
        BrokerExecutionStructuralCompatibilityOutcome.COMPATIBLE
        if not reason_tuple
        else BrokerExecutionStructuralCompatibilityOutcome.INCOMPATIBLE
    )
    return BrokerExecutionStructuralCompatibilityResult._create(
        capability_profile_fingerprint=capability_profile.fingerprint,
        order_specification_fingerprint=specification.fingerprint,
        outcome=outcome,
        rejection_reasons=reason_tuple,
        creation_seal=_RESULT_CREATION_SEAL,
    )


def _validate_result_values(
    *,
    capability_profile_fingerprint: object,
    order_specification_fingerprint: object,
    outcome: object,
    rejection_reasons: object,
    retained: bool,
) -> None:
    for value, name in (
        (capability_profile_fingerprint, "capability_profile_fingerprint"),
        (order_specification_fingerprint, "order_specification_fingerprint"),
    ):
        try:
            required_fingerprint(value, name)
        except ExecutionPlanningValidationError as error:
            if retained:
                raise ExecutionPlanningCorrespondenceError(
                    f"structural compatibility result {name} is invalid"
                ) from error
            raise
    if type(outcome) is not BrokerExecutionStructuralCompatibilityOutcome:
        _raise_invalid("structural compatibility outcome is invalid", retained)
    if type(rejection_reasons) is not tuple:
        _raise_invalid("rejection_reasons must be an exact tuple", retained)
    reasons = cast(tuple[object, ...], rejection_reasons)
    ranks: list[int] = []
    for reason in reasons:
        if (
            type(reason) is not BrokerExecutionStructuralCompatibilityReason
            or reason not in _REASON_RANK
        ):
            _raise_invalid("rejection_reasons contains an invalid v1 reason", retained)
        ranks.append(
            _REASON_RANK[cast(BrokerExecutionStructuralCompatibilityReason, reason)]
        )
    if any(left >= right for left, right in zip(ranks, ranks[1:], strict=False)):
        _raise_invalid(
            "rejection_reasons must use canonical order without duplicates", retained
        )
    if outcome is BrokerExecutionStructuralCompatibilityOutcome.COMPATIBLE and reasons:
        _raise_invalid("compatible result must have no rejection reasons", retained)
    if (
        outcome is BrokerExecutionStructuralCompatibilityOutcome.INCOMPATIBLE
        and not reasons
    ):
        _raise_invalid("incompatible result must have rejection reasons", retained)


def _raise_invalid(message: str, retained: bool) -> None:
    if retained:
        raise ExecutionPlanningCorrespondenceError(message)
    raise ExecutionPlanningValidationError(message)


__all__ = [
    "BROKER_EXECUTION_STRUCTURAL_COMPATIBILITY_RESULT_SCHEMA",
    "BrokerExecutionStructuralCompatibilityOutcome",
    "BrokerExecutionStructuralCompatibilityReason",
    "BrokerExecutionStructuralCompatibilityResult",
    "evaluate_broker_execution_structural_compatibility",
]
