"""Strict trusted local instrument-mapping document codec."""

from __future__ import annotations

import json
import os
import re
import stat
from datetime import UTC, date, datetime
from pathlib import Path

from market_platform.instruments import (
    CanonicalInstrument,
    CanonicalInstrumentId,
    ExternalInstrumentIdentity,
    InstrumentAssetClass,
    InstrumentMapping,
    InstrumentMappingSourceIdentity,
)
from market_platform.research.daily_instrument_integrity import (
    _REGISTRY_SEAL,
    TrustedInstrumentMappingRegistry,
)
from market_platform.trading import TradingInstrumentIdentity

_DOCUMENT_SCHEMA = "trusted_instrument_mapping_document/v1"
_MAX_BYTES = 1_048_576
_MAX_STRING = 256
_MAX_DEPTH = 4
_DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", re.ASCII)
_FINGERPRINT_PATTERN = re.compile(r"sha256:[0-9a-f]{64}", re.ASCII)
_REPARSE_POINT = 0x400


def load_trusted_instrument_mapping_registry(
    path: object,
) -> TrustedInstrumentMappingRegistry:
    """Load one bounded strict-JSON trusted mapping document."""
    if type(path) is not str and not isinstance(path, Path):
        raise TypeError("path must be an exact str or Path")
    supplied = str(path)
    try:
        info = os.lstat(supplied)
    except OSError as exc:
        raise OSError("trusted mapping path is not an existing regular file") from exc
    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISREG(info.st_mode)
        or getattr(info, "st_file_attributes", 0) & _REPARSE_POINT
    ):
        raise OSError("trusted mapping path must be a regular non-reparse file")
    if info.st_size > _MAX_BYTES:
        raise ValueError("trusted mapping document exceeds maximum file size")
    with open(supplied, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(opened.st_mode)
            or getattr(opened, "st_file_attributes", 0) & _REPARSE_POINT
        ):
            raise OSError("trusted mapping path must be a regular non-reparse file")
        raw = stream.read(_MAX_BYTES + 1)
        after = os.fstat(stream.fileno())
    if len(raw) > _MAX_BYTES or after.st_size > _MAX_BYTES:
        raise ValueError("trusted mapping document exceeds maximum file size")
    if not raw:
        raise ValueError("trusted mapping document must not be empty")
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError("trusted mapping document must not contain a UTF-8 BOM")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError("trusted mapping document is not valid UTF-8") from exc
    try:
        document = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError("trusted mapping document is not valid strict JSON") from exc
    _validate_json(document, 1)
    return _decode(document)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value: str) -> object:
    raise ValueError(f"non-finite JSON number {value}")


def _validate_json(value: object, depth: int) -> None:
    if depth > _MAX_DEPTH:
        raise ValueError("trusted mapping document exceeds maximum container depth")
    if type(value) is str:
        if len(value) > _MAX_STRING:
            raise ValueError("trusted mapping document string exceeds maximum length")
        return
    if value is None or type(value) in (bool, int, float):
        return
    if type(value) is list:
        for item in value:
            _validate_json(item, depth + 1 if type(item) in (list, dict) else depth)
        return
    if type(value) is dict:
        for key, item in value.items():
            if len(key) > _MAX_STRING:
                raise ValueError(
                    "trusted mapping document string exceeds maximum length"
                )
            _validate_json(item, depth + 1 if type(item) in (list, dict) else depth)
        return
    raise ValueError("trusted mapping document contains unsupported JSON")


def _object(value: object, fields: tuple[str, ...], name: str) -> dict[str, object]:
    if type(value) is not dict:
        raise ValueError(f"{name} must be an exact JSON object")
    if set(value) != set(fields):
        detail = "missing fields" if set(fields) - set(value) else "unknown fields"
        raise ValueError(f"{name} has {detail}")
    return value


def _text(
    value: object,
    name: str,
    *,
    uppercase: bool = False,
    exact: str | None = None,
) -> str:
    if type(value) is not str:
        raise ValueError(f"{name} must be a string")
    if not value or value != value.strip() or any(char.isspace() for char in value):
        raise ValueError(f"{name} must be nonempty canonical text")
    if uppercase and value != value.upper():
        raise ValueError(f"{name} must be uppercase")
    if exact is not None and value != exact:
        raise ValueError(f"{name} must equal {exact}")
    return value


def _date(value: object, name: str) -> datetime:
    if type(value) is not str or _DATE_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{name} must be YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{name} is not a real Gregorian date") from exc
    return datetime(parsed.year, parsed.month, parsed.day, tzinfo=UTC)


def _decode(value: object) -> TrustedInstrumentMappingRegistry:
    root = _object(
        value,
        ("schema_version", "source", "instruments", "mappings"),
        "document",
    )
    _text(root["schema_version"], "schema_version", exact=_DOCUMENT_SCHEMA)
    raw_source = _object(
        root["source"],
        ("source_id", "source_version", "configuration_fingerprint"),
        "source",
    )
    configuration = raw_source["configuration_fingerprint"]
    if configuration is not None and (
        type(configuration) is not str
        or _FINGERPRINT_PATTERN.fullmatch(configuration) is None
    ):
        raise ValueError("configuration_fingerprint is not canonical")
    source = InstrumentMappingSourceIdentity(
        _text(raw_source["source_id"], "source_id"),
        _text(raw_source["source_version"], "source_version"),
        configuration,
    )
    raw_instruments = root["instruments"]
    raw_mappings = root["mappings"]
    if type(raw_instruments) is not list or not 1 <= len(raw_instruments) <= 1024:
        raise ValueError("instruments must contain 1 to 1024 records")
    if type(raw_mappings) is not list or not 1 <= len(raw_mappings) <= 4096:
        raise ValueError("mappings must contain 1 to 4096 records")
    instruments: list[CanonicalInstrument] = []
    by_id: dict[str, CanonicalInstrument] = {}
    for raw in raw_instruments:
        item = _object(
            raw,
            ("instrument_id", "trading_identity", "asset_class", "trading_currency"),
            "instrument",
        )
        identity = _object(
            item["trading_identity"], ("symbol", "venue"), "trading_identity"
        )
        instrument_id = _text(item["instrument_id"], "instrument_id")
        if instrument_id in by_id:
            raise ValueError("instrument IDs must be unique")
        asset_class = _text(item["asset_class"], "asset_class")
        if asset_class not in {"equity", "etf"}:
            raise ValueError("asset_class must be equity or etf")
        instrument = CanonicalInstrument(
            CanonicalInstrumentId(instrument_id),
            TradingInstrumentIdentity(
                _text(identity["symbol"], "symbol", uppercase=True),
                _text(identity["venue"], "venue", uppercase=True),
            ),
            InstrumentAssetClass(asset_class),
            _text(item["trading_currency"], "trading_currency", uppercase=True),
        )
        instruments.append(instrument)
        by_id[instrument_id] = instrument
    mappings: list[InstrumentMapping] = []
    semantic: set[tuple[object, ...]] = set()
    fingerprints: set[str] = set()
    for raw in raw_mappings:
        item = _object(
            raw,
            (
                "external_identity",
                "canonical_instrument_id",
                "valid_from",
                "expires_at",
            ),
            "mapping",
        )
        identity = _object(
            item["external_identity"],
            ("namespace", "external_symbol", "external_venue"),
            "external_identity",
        )
        namespace = _text(identity["namespace"], "namespace", exact="polygon")
        symbol = _text(identity["external_symbol"], "external_symbol", uppercase=True)
        venue = _text(identity["external_venue"], "external_venue", uppercase=True)
        canonical_id = _text(item["canonical_instrument_id"], "canonical_instrument_id")
        if canonical_id not in by_id:
            raise ValueError("mapping canonical ID does not resolve an instrument")
        valid_from = _date(item["valid_from"], "valid_from")
        expires_at = (
            None
            if item["expires_at"] is None
            else _date(item["expires_at"], "expires_at")
        )
        key = (namespace, symbol, venue, canonical_id, valid_from, expires_at)
        if key in semantic:
            raise ValueError("duplicate semantic mapping")
        semantic.add(key)
        mapping = InstrumentMapping(
            ExternalInstrumentIdentity(namespace, symbol, venue),
            by_id[canonical_id],
            source,
            valid_from,
            expires_at,
        )
        if mapping.fingerprint in fingerprints:
            raise ValueError("duplicate mapping fingerprint")
        fingerprints.add(mapping.fingerprint)
        mappings.append(mapping)
    return TrustedInstrumentMappingRegistry._create(
        source=source,
        instruments=tuple(instruments),
        mappings=tuple(mappings),
        seal=_REGISTRY_SEAL,
    )


__all__ = ["load_trusted_instrument_mapping_registry"]
