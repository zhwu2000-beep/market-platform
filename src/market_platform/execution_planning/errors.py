"""Narrow errors for deterministic execution planning."""


class ExecutionPlanningDomainError(Exception):
    """Base error for the execution-planning domain."""


class ExecutionPlanningValidationError(ExecutionPlanningDomainError, ValueError):
    """Raised when direct execution-planning input is malformed."""


class ExecutionPlanningCorrespondenceError(ExecutionPlanningDomainError, RuntimeError):
    """Raised when retained domain state is not canonical."""


class ExecutionPlanningUnavailableError(ExecutionPlanningDomainError, RuntimeError):
    """Raised when canonical evidence cannot produce a v0.60 translation."""


__all__ = [
    "ExecutionPlanningCorrespondenceError",
    "ExecutionPlanningDomainError",
    "ExecutionPlanningUnavailableError",
    "ExecutionPlanningValidationError",
]
