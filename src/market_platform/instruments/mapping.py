"""Immutable temporal mappings from external to canonical instruments."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from market_platform._fingerprint import canonical_fingerprint
from market_platform.instruments._canonical import (
    canonical_timestamp,
    require_canonical_timestamp,
    timestamp_text,
)
from market_platform.instruments.errors import InstrumentValidationError
from market_platform.instruments.identity import (
    CanonicalInstrument,
    ExternalInstrumentIdentity,
    InstrumentMappingSourceIdentity,
)

INSTRUMENT_MAPPING_SCHEMA_VERSION = "instrument_mapping/v1"


@dataclass(frozen=True, slots=True)
class InstrumentMapping:
    """One source-attributed, half-open external instrument mapping."""

    external_identity: ExternalInstrumentIdentity
    canonical_instrument: CanonicalInstrument
    source: InstrumentMappingSourceIdentity
    valid_from: datetime
    expires_at: datetime | None = None
    schema_version: str = field(
        init=False,
        default=INSTRUMENT_MAPPING_SCHEMA_VERSION,
    )
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if type(self.external_identity) is not ExternalInstrumentIdentity:
            raise TypeError(
                "external_identity must be an ExternalInstrumentIdentity"
            )
        if type(self.canonical_instrument) is not CanonicalInstrument:
            raise TypeError(
                "canonical_instrument must be a CanonicalInstrument"
            )
        if type(self.source) is not InstrumentMappingSourceIdentity:
            raise TypeError(
                "source must be an InstrumentMappingSourceIdentity"
            )
        self.external_identity._validate()
        self.canonical_instrument._validate()
        self.source._validate()
        valid_from = canonical_timestamp(self.valid_from, "valid_from")
        expires_at = (
            None
            if self.expires_at is None
            else canonical_timestamp(self.expires_at, "expires_at")
        )
        if expires_at is not None and expires_at <= valid_from:
            raise InstrumentValidationError(
                "expires_at must be later than valid_from"
            )
        object.__setattr__(self, "valid_from", valid_from)
        object.__setattr__(self, "expires_at", expires_at)
        object.__setattr__(
            self,
            "fingerprint",
            canonical_fingerprint(self._fingerprint_payload()),
        )

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "external_identity": self.external_identity.to_dict(),
            "canonical_instrument": self.canonical_instrument.to_dict(),
            "source": self.source.to_dict(),
            "valid_from": timestamp_text(self.valid_from),
            "expires_at": (
                None
                if self.expires_at is None
                else timestamp_text(self.expires_at)
            ),
        }

    def _validate(self) -> None:
        if self.schema_version != INSTRUMENT_MAPPING_SCHEMA_VERSION:
            raise InstrumentValidationError(
                "instrument mapping schema_version is invalid"
            )
        if type(self.external_identity) is not ExternalInstrumentIdentity:
            raise InstrumentValidationError(
                "mapping external_identity has invalid type"
            )
        if type(self.canonical_instrument) is not CanonicalInstrument:
            raise InstrumentValidationError(
                "mapping canonical_instrument has invalid type"
            )
        if type(self.source) is not InstrumentMappingSourceIdentity:
            raise InstrumentValidationError("mapping source has invalid type")
        self.external_identity._validate()
        self.canonical_instrument._validate()
        self.source._validate()
        valid_from = require_canonical_timestamp(
            self.valid_from,
            "valid_from",
        )
        expires_at = (
            None
            if self.expires_at is None
            else require_canonical_timestamp(self.expires_at, "expires_at")
        )
        if expires_at is not None and expires_at <= valid_from:
            raise InstrumentValidationError(
                "expires_at must be later than valid_from"
            )
        expected = canonical_fingerprint(self._fingerprint_payload())
        if self.fingerprint != expected:
            raise InstrumentValidationError(
                "instrument mapping fingerprint does not match content"
            )

    def is_active(self, as_of: datetime) -> bool:
        """Return applicability at one explicit caller-supplied instant."""

        self._validate()
        normalized_as_of = canonical_timestamp(as_of, "as_of")
        return self.valid_from <= normalized_as_of and (
            self.expires_at is None or normalized_as_of < self.expires_at
        )

    def to_dict(self) -> dict[str, object]:
        """Return a bounded deterministic JSON-safe mapping."""

        return {
            **self._fingerprint_payload(),
            "fingerprint": self.fingerprint,
        }


__all__ = [
    "INSTRUMENT_MAPPING_SCHEMA_VERSION",
    "InstrumentMapping",
]
