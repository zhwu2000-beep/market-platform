"""Mechanical position-target translation without broker authority."""

from market_platform.execution_planning.capability import (
    BROKER_EXECUTION_CAPABILITY_PROFILE_SCHEMA,
    BrokerExecutionCapabilityProfile,
    construct_broker_execution_capability_profile,
)
from market_platform.execution_planning.compatibility import (
    BROKER_EXECUTION_STRUCTURAL_COMPATIBILITY_RESULT_SCHEMA,
    BrokerExecutionStructuralCompatibilityOutcome,
    BrokerExecutionStructuralCompatibilityReason,
    BrokerExecutionStructuralCompatibilityResult,
    evaluate_broker_execution_structural_compatibility,
)
from market_platform.execution_planning.errors import (
    ExecutionPlanningCorrespondenceError,
    ExecutionPlanningDomainError,
    ExecutionPlanningUnavailableError,
    ExecutionPlanningValidationError,
)
from market_platform.execution_planning.instruction import (
    BROKER_NEUTRAL_EXECUTION_INSTRUCTION_SCHEMA,
    BrokerNeutralExecutionInstruction,
    ExecutionInstructionSide,
    derive_broker_neutral_execution_instruction,
)
from market_platform.execution_planning.limit_price import (
    LIMIT_PRICE_CHOICE_SCHEMA,
    LimitPriceChoice,
)
from market_platform.execution_planning.native_order_mapping import (
    BROKER_NATIVE_ORDER_MAPPING_SCHEMA,
    BROKER_NATIVE_ORDER_REPRESENTATION_SCHEMA,
    BrokerNativeOrderMapper,
    BrokerNativeOrderMapping,
    BrokerNativeOrderRepresentation,
    construct_broker_native_order_representation,
    map_broker_native_order,
)
from market_platform.execution_planning.order_specification import (
    BROKER_NEUTRAL_ORDER_SPECIFICATION_SCHEMA,
    BrokerNeutralOrderSpecification,
    construct_broker_neutral_order_specification,
)
from market_platform.execution_planning.order_style import (
    ORDER_STYLE_CHOICE_SCHEMA,
    OrderStyle,
    OrderStyleChoice,
)
from market_platform.execution_planning.session_participation import (
    SESSION_PARTICIPATION_CHOICE_SCHEMA,
    SessionParticipation,
    SessionParticipationChoice,
)
from market_platform.execution_planning.time_in_force import (
    TIME_IN_FORCE_CHOICE_SCHEMA,
    TimeInForce,
    TimeInForceChoice,
)
from market_platform.execution_planning.translation import (
    POSITION_TARGET_TRANSLATION_SCHEMA,
    PositionDeltaAction,
    PositionTargetTranslation,
    translate_position_target,
)

__all__ = [
    "BROKER_NEUTRAL_EXECUTION_INSTRUCTION_SCHEMA",
    "BROKER_NEUTRAL_ORDER_SPECIFICATION_SCHEMA",
    "LIMIT_PRICE_CHOICE_SCHEMA",
    "ORDER_STYLE_CHOICE_SCHEMA",
    "POSITION_TARGET_TRANSLATION_SCHEMA",
    "SESSION_PARTICIPATION_CHOICE_SCHEMA",
    "TIME_IN_FORCE_CHOICE_SCHEMA",
    "BrokerNeutralExecutionInstruction",
    "BrokerNeutralOrderSpecification",
    "ExecutionPlanningCorrespondenceError",
    "ExecutionPlanningDomainError",
    "ExecutionPlanningUnavailableError",
    "ExecutionPlanningValidationError",
    "ExecutionInstructionSide",
    "LimitPriceChoice",
    "OrderStyle",
    "OrderStyleChoice",
    "PositionDeltaAction",
    "PositionTargetTranslation",
    "SessionParticipation",
    "SessionParticipationChoice",
    "TimeInForce",
    "TimeInForceChoice",
    "construct_broker_neutral_order_specification",
    "derive_broker_neutral_execution_instruction",
    "translate_position_target",
    "BROKER_EXECUTION_CAPABILITY_PROFILE_SCHEMA",
    "BrokerExecutionCapabilityProfile",
    "construct_broker_execution_capability_profile",
    "BROKER_EXECUTION_STRUCTURAL_COMPATIBILITY_RESULT_SCHEMA",
    "BrokerExecutionStructuralCompatibilityOutcome",
    "BrokerExecutionStructuralCompatibilityReason",
    "BrokerExecutionStructuralCompatibilityResult",
    "evaluate_broker_execution_structural_compatibility",
    "BROKER_NATIVE_ORDER_REPRESENTATION_SCHEMA",
    "BrokerNativeOrderRepresentation",
    "construct_broker_native_order_representation",
    "BROKER_NATIVE_ORDER_MAPPING_SCHEMA",
    "BrokerNativeOrderMapping",
    "BrokerNativeOrderMapper",
    "map_broker_native_order",
]
