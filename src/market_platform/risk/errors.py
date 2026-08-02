"""Narrow errors for structural risk evaluation."""


class RiskDomainError(Exception):
    """Base error for the structural risk domain."""


class RiskValidationError(RiskDomainError, ValueError):
    """Raised when direct structural risk input is malformed."""


class RiskCorrespondenceError(RiskDomainError, RuntimeError):
    """Raised when retained structural risk state is not canonical."""


__all__ = [
    "RiskCorrespondenceError",
    "RiskDomainError",
    "RiskValidationError",
]
