"""Stable canonical and external instrument identities."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

from market_platform._fingerprint import canonical_fingerprint
from market_platform.instruments._canonical import (
    optional_fingerprint,
    require_pattern_text,
    require_visible_ascii,
)
from market_platform.instruments.errors import InstrumentValidationError
from market_platform.trading import (
    TRADING_INSTRUMENT_IDENTITY_SCHEMA_VERSION,
    TradingInstrumentIdentity,
)

CANONICAL_INSTRUMENT_SCHEMA_VERSION = "canonical_instrument/v1"
EXTERNAL_INSTRUMENT_IDENTITY_SCHEMA_VERSION = "external_instrument_identity/v1"
INSTRUMENT_MAPPING_SOURCE_SCHEMA_VERSION = "instrument_mapping_source/v1"

_CANONICAL_ID_PATTERN = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}",
    flags=re.ASCII,
)
_NAMESPACE_PATTERN = re.compile(
    r"[a-z][a-z0-9._-]{0,63}",
    flags=re.ASCII,
)
_CURRENCY_PATTERN = re.compile(r"[A-Z]{3}", flags=re.ASCII)


class InstrumentAssetClass(StrEnum):
    """Asset classes whose identity semantics are complete in schema v1."""

    EQUITY = "equity"
    ETF = "etf"


@dataclass(frozen=True, slots=True)
class CanonicalInstrumentId:
    """Opaque stable registry key independent of mutable descriptors."""

    instrument_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "instrument_id",
            require_pattern_text(
                self.instrument_id,
                "instrument_id",
                _CANONICAL_ID_PATTERN,
                "[A-Za-z0-9][A-Za-z0-9._-]{0,127}",
            ),
        )

    def to_dict(self) -> dict[str, object]:
        """Return the bounded nested identifier projection."""

        return {"instrument_id": self.instrument_id}


@dataclass(frozen=True, slots=True)
class CanonicalInstrument:
    """Versioned descriptor for one stable canonical instrument ID."""

    instrument_id: CanonicalInstrumentId
    trading_identity: TradingInstrumentIdentity
    asset_class: InstrumentAssetClass
    trading_currency: str
    schema_version: str = field(
        init=False,
        default=CANONICAL_INSTRUMENT_SCHEMA_VERSION,
    )
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if type(self.instrument_id) is not CanonicalInstrumentId:
            raise TypeError("instrument_id must be a CanonicalInstrumentId")
        if type(self.trading_identity) is not TradingInstrumentIdentity:
            raise TypeError(
                "trading_identity must be a TradingInstrumentIdentity"
            )
        if type(self.asset_class) is not InstrumentAssetClass:
            raise TypeError("asset_class must be an InstrumentAssetClass")
        currency = require_pattern_text(
            self.trading_currency,
            "trading_currency",
            _CURRENCY_PATTERN,
            "[A-Z]{3}",
        )
        CanonicalInstrumentId(self.instrument_id.instrument_id)
        _validate_trading_identity(self.trading_identity)
        object.__setattr__(self, "trading_currency", currency)
        object.__setattr__(
            self,
            "fingerprint",
            canonical_fingerprint(self._fingerprint_payload()),
        )

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "instrument_id": self.instrument_id.to_dict(),
            "trading_identity": self.trading_identity.to_dict(),
            "asset_class": self.asset_class.value,
            "trading_currency": self.trading_currency,
        }

    def _validate(self) -> None:
        if self.schema_version != CANONICAL_INSTRUMENT_SCHEMA_VERSION:
            raise InstrumentValidationError(
                "canonical instrument schema_version is invalid"
            )
        if type(self.instrument_id) is not CanonicalInstrumentId:
            raise InstrumentValidationError(
                "canonical instrument_id has invalid type"
            )
        if type(self.trading_identity) is not TradingInstrumentIdentity:
            raise InstrumentValidationError(
                "canonical trading_identity has invalid type"
            )
        if type(self.asset_class) is not InstrumentAssetClass:
            raise InstrumentValidationError(
                "canonical asset_class has invalid type"
            )
        CanonicalInstrumentId(self.instrument_id.instrument_id)
        _validate_trading_identity(self.trading_identity)
        require_pattern_text(
            self.trading_currency,
            "trading_currency",
            _CURRENCY_PATTERN,
            "[A-Z]{3}",
        )
        expected = canonical_fingerprint(self._fingerprint_payload())
        if self.fingerprint != expected:
            raise InstrumentValidationError(
                "canonical instrument fingerprint does not match content"
            )

    def to_dict(self) -> dict[str, object]:
        """Return a bounded deterministic JSON-safe descriptor."""

        return {
            **self._fingerprint_payload(),
            "fingerprint": self.fingerprint,
        }


@dataclass(frozen=True, slots=True)
class ExternalInstrumentIdentity:
    """Exact identity in one opaque external namespace."""

    namespace: str
    external_symbol: str
    external_venue: str | None = None
    schema_version: str = field(
        init=False,
        default=EXTERNAL_INSTRUMENT_IDENTITY_SCHEMA_VERSION,
    )
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        namespace = require_pattern_text(
            self.namespace,
            "namespace",
            _NAMESPACE_PATTERN,
            "[a-z][a-z0-9._-]{0,63}",
        )
        symbol = require_visible_ascii(
            self.external_symbol,
            "external_symbol",
            128,
        )
        venue = (
            None
            if self.external_venue is None
            else require_visible_ascii(
                self.external_venue,
                "external_venue",
                64,
            )
        )
        object.__setattr__(self, "namespace", namespace)
        object.__setattr__(self, "external_symbol", symbol)
        object.__setattr__(self, "external_venue", venue)
        object.__setattr__(
            self,
            "fingerprint",
            canonical_fingerprint(self._fingerprint_payload()),
        )

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "namespace": self.namespace,
            "external_symbol": self.external_symbol,
            "external_venue": self.external_venue,
        }

    def _validate(self) -> None:
        if self.schema_version != EXTERNAL_INSTRUMENT_IDENTITY_SCHEMA_VERSION:
            raise InstrumentValidationError(
                "external instrument schema_version is invalid"
            )
        require_pattern_text(
            self.namespace,
            "namespace",
            _NAMESPACE_PATTERN,
            "[a-z][a-z0-9._-]{0,63}",
        )
        require_visible_ascii(self.external_symbol, "external_symbol", 128)
        if self.external_venue is not None:
            require_visible_ascii(self.external_venue, "external_venue", 64)
        expected = canonical_fingerprint(self._fingerprint_payload())
        if self.fingerprint != expected:
            raise InstrumentValidationError(
                "external instrument fingerprint does not match content"
            )

    def to_dict(self) -> dict[str, object]:
        """Return a bounded deterministic JSON-safe external identity."""

        return {
            **self._fingerprint_payload(),
            "fingerprint": self.fingerprint,
        }


@dataclass(frozen=True, slots=True)
class InstrumentMappingSourceIdentity:
    """Versioned provenance identity for instrument mappings."""

    source_id: str
    source_version: str
    configuration_fingerprint: str | None = None
    schema_version: str = field(
        init=False,
        default=INSTRUMENT_MAPPING_SOURCE_SCHEMA_VERSION,
    )
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        source_id = require_visible_ascii(self.source_id, "source_id", 128)
        source_version = require_visible_ascii(
            self.source_version,
            "source_version",
            64,
        )
        configuration = optional_fingerprint(
            self.configuration_fingerprint,
            "configuration_fingerprint",
        )
        object.__setattr__(self, "source_id", source_id)
        object.__setattr__(self, "source_version", source_version)
        object.__setattr__(self, "configuration_fingerprint", configuration)
        object.__setattr__(
            self,
            "fingerprint",
            canonical_fingerprint(self._fingerprint_payload()),
        )

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "source_id": self.source_id,
            "source_version": self.source_version,
            "configuration_fingerprint": self.configuration_fingerprint,
        }

    def _validate(self) -> None:
        if self.schema_version != INSTRUMENT_MAPPING_SOURCE_SCHEMA_VERSION:
            raise InstrumentValidationError(
                "mapping source schema_version is invalid"
            )
        require_visible_ascii(self.source_id, "source_id", 128)
        require_visible_ascii(self.source_version, "source_version", 64)
        optional_fingerprint(
            self.configuration_fingerprint,
            "configuration_fingerprint",
        )
        expected = canonical_fingerprint(self._fingerprint_payload())
        if self.fingerprint != expected:
            raise InstrumentValidationError(
                "mapping source fingerprint does not match content"
            )

    def to_dict(self) -> dict[str, object]:
        """Return a bounded deterministic JSON-safe source identity."""

        return {
            **self._fingerprint_payload(),
            "fingerprint": self.fingerprint,
        }


def _validate_trading_identity(identity: TradingInstrumentIdentity) -> None:
    if type(identity) is not TradingInstrumentIdentity:
        raise InstrumentValidationError(
            "trading identity has invalid runtime type"
        )
    if any(
        character.isspace()
        for text in (identity.symbol, identity.venue)
        for character in text
    ):
        raise InstrumentValidationError("trading identity contains whitespace")
    try:
        reconstructed = TradingInstrumentIdentity(
            symbol=identity.symbol,
            venue=identity.venue,
        )
    except (TypeError, ValueError) as error:
        raise InstrumentValidationError(
            "trading identity cannot be reconstructed canonically"
        ) from error
    if (
        identity.schema_version != TRADING_INSTRUMENT_IDENTITY_SCHEMA_VERSION
        or identity.schema_version != reconstructed.schema_version
        or identity.symbol != reconstructed.symbol
        or identity.venue != reconstructed.venue
        or identity.instrument_fingerprint
        != reconstructed.instrument_fingerprint
        or identity.to_dict() != reconstructed.to_dict()
    ):
        raise InstrumentValidationError(
            "trading identity does not match canonical reconstructed state"
        )


__all__ = [
    "CANONICAL_INSTRUMENT_SCHEMA_VERSION",
    "EXTERNAL_INSTRUMENT_IDENTITY_SCHEMA_VERSION",
    "INSTRUMENT_MAPPING_SOURCE_SCHEMA_VERSION",
    "CanonicalInstrument",
    "CanonicalInstrumentId",
    "ExternalInstrumentIdentity",
    "InstrumentAssetClass",
    "InstrumentMappingSourceIdentity",
]
