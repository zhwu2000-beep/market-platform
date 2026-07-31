"""Stable instrument identities and pure temporal mapping resolution."""

from market_platform.instruments.errors import (
    InstrumentDomainError,
    InstrumentMappingAmbiguousError,
    InstrumentMappingConflictError,
    InstrumentMappingDuplicateError,
    InstrumentMappingError,
    InstrumentMappingInactiveError,
    InstrumentMappingNotFoundError,
    InstrumentResolutionCorrespondenceError,
    InstrumentValidationError,
)
from market_platform.instruments.identity import (
    CANONICAL_INSTRUMENT_SCHEMA_VERSION,
    EXTERNAL_INSTRUMENT_IDENTITY_SCHEMA_VERSION,
    INSTRUMENT_MAPPING_SOURCE_SCHEMA_VERSION,
    CanonicalInstrument,
    CanonicalInstrumentId,
    ExternalInstrumentIdentity,
    InstrumentAssetClass,
    InstrumentMappingSourceIdentity,
)
from market_platform.instruments.mapping import (
    INSTRUMENT_MAPPING_SCHEMA_VERSION,
    InstrumentMapping,
)
from market_platform.instruments.resolver import (
    INSTRUMENT_RESOLUTION_SCHEMA_VERSION,
    InstrumentResolution,
    resolve_instrument_mapping,
)

__all__ = [
    "CANONICAL_INSTRUMENT_SCHEMA_VERSION",
    "EXTERNAL_INSTRUMENT_IDENTITY_SCHEMA_VERSION",
    "INSTRUMENT_MAPPING_SCHEMA_VERSION",
    "INSTRUMENT_MAPPING_SOURCE_SCHEMA_VERSION",
    "INSTRUMENT_RESOLUTION_SCHEMA_VERSION",
    "CanonicalInstrument",
    "CanonicalInstrumentId",
    "ExternalInstrumentIdentity",
    "InstrumentAssetClass",
    "InstrumentDomainError",
    "InstrumentMapping",
    "InstrumentMappingAmbiguousError",
    "InstrumentMappingConflictError",
    "InstrumentMappingDuplicateError",
    "InstrumentMappingError",
    "InstrumentMappingInactiveError",
    "InstrumentMappingNotFoundError",
    "InstrumentMappingSourceIdentity",
    "InstrumentResolution",
    "InstrumentResolutionCorrespondenceError",
    "InstrumentValidationError",
    "resolve_instrument_mapping",
]
