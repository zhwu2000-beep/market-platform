"""Pure order-neutral instrument mapping resolution."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from market_platform.instruments._canonical import (
    canonical_timestamp,
    require_canonical_timestamp,
    timestamp_text,
)
from market_platform.instruments.errors import (
    InstrumentMappingAmbiguousError,
    InstrumentMappingConflictError,
    InstrumentMappingDuplicateError,
    InstrumentMappingInactiveError,
    InstrumentMappingNotFoundError,
    InstrumentResolutionCorrespondenceError,
    InstrumentValidationError,
)
from market_platform.instruments.identity import ExternalInstrumentIdentity
from market_platform.instruments.mapping import InstrumentMapping

INSTRUMENT_RESOLUTION_SCHEMA_VERSION = "instrument_resolution/v1"


@dataclass(frozen=True, slots=True, init=False)
class InstrumentResolution:
    """Bounded evidence of one exact active instrument mapping."""

    external_identity: ExternalInstrumentIdentity = field(repr=False)
    mapping: InstrumentMapping = field(repr=False)
    resolved_as_of: datetime
    schema_version: str

    def __init__(self) -> None:
        raise TypeError(
            "InstrumentResolution must be created by "
            "resolve_instrument_mapping()"
        )

    @classmethod
    def _create(
        cls,
        *,
        external_identity: ExternalInstrumentIdentity,
        mapping: InstrumentMapping,
        resolved_as_of: datetime,
    ) -> InstrumentResolution:
        resolution = object.__new__(cls)
        object.__setattr__(resolution, "external_identity", external_identity)
        object.__setattr__(resolution, "mapping", mapping)
        object.__setattr__(resolution, "resolved_as_of", resolved_as_of)
        object.__setattr__(
            resolution,
            "schema_version",
            INSTRUMENT_RESOLUTION_SCHEMA_VERSION,
        )
        resolution._validate()
        return resolution

    def _validate(self) -> None:
        if self.schema_version != INSTRUMENT_RESOLUTION_SCHEMA_VERSION:
            raise InstrumentResolutionCorrespondenceError(
                "instrument resolution schema_version is invalid"
            )
        if type(self.external_identity) is not ExternalInstrumentIdentity:
            raise InstrumentResolutionCorrespondenceError(
                "resolution external_identity has invalid type"
            )
        if type(self.mapping) is not InstrumentMapping:
            raise InstrumentResolutionCorrespondenceError(
                "resolution mapping has invalid type"
            )
        if not isinstance(self.resolved_as_of, datetime):
            raise InstrumentResolutionCorrespondenceError(
                "resolution resolved_as_of has invalid type"
            )
        try:
            self.external_identity._validate()
            self.mapping._validate()
            resolved_as_of = require_canonical_timestamp(
                self.resolved_as_of,
                "resolved_as_of",
            )
        except InstrumentValidationError as error:
            raise InstrumentResolutionCorrespondenceError(
                "resolution retains invalid canonical state"
            ) from error
        if (
            self.mapping.external_identity != self.external_identity
            or self.mapping.external_identity.fingerprint
            != self.external_identity.fingerprint
        ):
            raise InstrumentResolutionCorrespondenceError(
                "resolution external identity does not match mapping"
            )
        if not self.mapping.is_active(resolved_as_of):
            raise InstrumentResolutionCorrespondenceError(
                "resolution mapping is inactive at resolved_as_of"
            )

    def to_dict(self) -> dict[str, object]:
        """Return bounded deterministic JSON-safe resolution evidence."""

        return {
            "schema_version": self.schema_version,
            "external_identity": self.external_identity.to_dict(),
            "mapping": self.mapping.to_dict(),
            "resolved_as_of": timestamp_text(self.resolved_as_of),
        }


def resolve_instrument_mapping(
    external_identity: ExternalInstrumentIdentity,
    mappings: list[InstrumentMapping] | tuple[InstrumentMapping, ...],
    as_of: datetime,
) -> InstrumentResolution:
    """Resolve exactly one active mapping without fallback or external effects."""

    if type(external_identity) is not ExternalInstrumentIdentity:
        raise TypeError(
            "external_identity must be an ExternalInstrumentIdentity"
        )
    if type(mappings) not in (list, tuple):
        raise TypeError("mappings must be an exact built-in list or tuple")
    external_identity._validate()
    resolved_as_of = canonical_timestamp(as_of, "as_of")
    records = tuple(mappings)
    for record in records:
        if type(record) is not InstrumentMapping:
            raise TypeError("every mapping must be an InstrumentMapping")
        record._validate()

    ordered = tuple(sorted(records, key=lambda record: record.fingerprint))
    _reject_duplicate_fingerprints(ordered)
    matching = tuple(
        record
        for record in ordered
        if record.external_identity == external_identity
        and record.external_identity.fingerprint
        == external_identity.fingerprint
    )
    if not matching:
        raise InstrumentMappingNotFoundError(
            "no mapping exists for external identity "
            f"{external_identity.fingerprint}"
        )
    active = tuple(
        record for record in matching if record.is_active(resolved_as_of)
    )
    if not active:
        raise InstrumentMappingInactiveError(
            "mapping records exist but are inactive for external identity "
            f"{external_identity.fingerprint} at "
            f"{timestamp_text(resolved_as_of)}"
        )
    if len(active) > 1:
        canonical_results = {
            (
                record.canonical_instrument.instrument_id.instrument_id,
                record.canonical_instrument.fingerprint,
            )
            for record in active
        }
        if len(canonical_results) == 1:
            raise InstrumentMappingAmbiguousError(
                f"{len(active)} active mappings agree for external identity "
                f"{external_identity.fingerprint}"
            )
        raise InstrumentMappingConflictError(
            f"{len(active)} active mappings conflict for external identity "
            f"{external_identity.fingerprint}"
        )
    return InstrumentResolution._create(
        external_identity=external_identity,
        mapping=active[0],
        resolved_as_of=resolved_as_of,
    )


def _reject_duplicate_fingerprints(
    mappings: tuple[InstrumentMapping, ...],
) -> None:
    previous: str | None = None
    for mapping in mappings:
        if mapping.fingerprint == previous:
            raise InstrumentMappingDuplicateError(
                "resolver input repeats mapping fingerprint "
                f"{mapping.fingerprint}"
            )
        previous = mapping.fingerprint


__all__ = [
    "INSTRUMENT_RESOLUTION_SCHEMA_VERSION",
    "InstrumentResolution",
    "resolve_instrument_mapping",
]
