"""Narrow errors for canonical instrument identity and mapping."""


class InstrumentDomainError(Exception):
    """Base error for the instrument identity and mapping domain."""


class InstrumentValidationError(InstrumentDomainError, ValueError):
    """Raised when an instrument-domain model is malformed."""


class InstrumentMappingError(InstrumentDomainError):
    """Base error for deterministic instrument mapping resolution."""


class InstrumentMappingDuplicateError(InstrumentMappingError):
    """Raised when resolver input repeats a mapping fingerprint."""


class InstrumentMappingNotFoundError(InstrumentMappingError):
    """Raised when no mapping exists for an exact external identity."""


class InstrumentMappingInactiveError(InstrumentMappingError):
    """Raised when matching mappings exist but none apply at the given time."""


class InstrumentMappingAmbiguousError(InstrumentMappingError):
    """Raised when multiple active mappings agree on one canonical result."""


class InstrumentMappingConflictError(InstrumentMappingError):
    """Raised when active mappings disagree on the canonical result."""


class InstrumentResolutionCorrespondenceError(
    InstrumentDomainError,
    RuntimeError,
):
    """Raised when a resolution does not correspond to its retained mapping."""


__all__ = [
    "InstrumentDomainError",
    "InstrumentMappingAmbiguousError",
    "InstrumentMappingConflictError",
    "InstrumentMappingDuplicateError",
    "InstrumentMappingError",
    "InstrumentMappingInactiveError",
    "InstrumentMappingNotFoundError",
    "InstrumentResolutionCorrespondenceError",
    "InstrumentValidationError",
]
