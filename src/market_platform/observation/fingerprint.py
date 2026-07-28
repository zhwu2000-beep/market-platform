"""Exact legacy historical-observation fingerprint preparation."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from numbers import Real
from types import MappingProxyType

from market_platform.data.historical import (
    HistoricalPricePrefix,
    HistoricalPriceRow,
    HistoricalPriceSeries,
)

_JSON_SEPARATORS = (",", ":")


@dataclass(frozen=True, slots=True)
class _PreparedHistoricalObservationFingerprint:
    position: int
    prefix_length: int
    prefix_as_of: datetime
    observation_as_of: datetime
    fingerprint: str


@dataclass(frozen=True, slots=True, init=False)
class HistoricalObservationFingerprintPrecompute:
    """Immutable exact fingerprints bound to one canonical historical series."""

    symbol: str
    interval: str
    provider: str
    source_row_count: int
    source_content_fingerprint: str
    evaluation_positions: tuple[int, ...]
    _entries: tuple[_PreparedHistoricalObservationFingerprint, ...] = field(
        repr=False
    )
    _source: HistoricalPriceSeries = field(repr=False, compare=False)
    _entries_by_position: Mapping[
        int, _PreparedHistoricalObservationFingerprint
    ] = field(repr=False, compare=False)

    def __init__(self) -> None:
        raise TypeError(
            "HistoricalObservationFingerprintPrecompute does not support direct "
            "construction; use prepare_historical_observation_fingerprints()"
        )

    @classmethod
    def _create(
        cls,
        *,
        source: HistoricalPriceSeries,
        interval: str,
        entries: tuple[_PreparedHistoricalObservationFingerprint, ...],
    ) -> HistoricalObservationFingerprintPrecompute:
        instance = cls.__new__(cls)
        object.__setattr__(instance, "symbol", source.symbol)
        object.__setattr__(instance, "interval", interval)
        object.__setattr__(instance, "provider", source.provider)
        object.__setattr__(instance, "source_row_count", len(source))
        object.__setattr__(
            instance,
            "source_content_fingerprint",
            source.content_fingerprint,
        )
        object.__setattr__(
            instance,
            "evaluation_positions",
            tuple(entry.position for entry in entries),
        )
        object.__setattr__(instance, "_entries", entries)
        object.__setattr__(instance, "_source", source)
        object.__setattr__(
            instance,
            "_entries_by_position",
            MappingProxyType({entry.position: entry for entry in entries}),
        )
        return instance

    def fingerprint_for_validated_prefix(
        self,
        prefix: HistoricalPricePrefix,
        *,
        symbol: str,
        interval: str,
        provider: str,
        as_of: datetime,
    ) -> str:
        """Return the prepared fingerprint after validating every binding fact."""

        if not isinstance(prefix, HistoricalPricePrefix):
            raise TypeError("prefix must be a HistoricalPricePrefix")
        if prefix._series is not self._source:
            raise ValueError("fingerprint precompute must match historical series")
        if symbol != self.symbol:
            raise ValueError("fingerprint precompute symbol must match prefix")
        if interval != self.interval:
            raise ValueError("fingerprint precompute interval must match observation")
        if provider != self.provider:
            raise ValueError("fingerprint precompute provider must match prefix")
        try:
            entry = self._entries_by_position[prefix.position]
        except KeyError as error:
            raise ValueError(
                "historical prefix position was not prepared for fingerprinting"
            ) from error
        if len(prefix) != entry.prefix_length:
            raise ValueError("historical prefix length must match prepared fingerprint")
        if prefix.as_of != entry.prefix_as_of:
            raise ValueError(
                "historical prefix endpoint must match prepared fingerprint"
            )
        normalized_as_of = _normalize_timestamp(as_of, "as_of")
        if normalized_as_of != entry.observation_as_of:
            raise ValueError(
                "observation as_of must match prepared fingerprint"
            )
        return entry.fingerprint


def prepare_historical_observation_fingerprints(
    series: HistoricalPriceSeries,
    evaluation_positions: tuple[int, ...],
    *,
    interval: str,
) -> HistoricalObservationFingerprintPrecompute:
    """Prepare exact legacy observation fingerprints for selected positions."""

    if not isinstance(series, HistoricalPriceSeries):
        raise TypeError("series must be a HistoricalPriceSeries")
    normalized_interval = _normalize_required_text(interval, "interval")
    positions = _validate_evaluation_positions(evaluation_positions, len(series))
    maximum_position = positions[-1]

    row_stream = bytearray()
    row_offsets: list[int] = []
    for row_index, row in enumerate(series._iter_rows(maximum_position + 1)):
        if row_index:
            row_stream.extend(b",")
        row_stream.extend(_encode_historical_observation_fingerprint_row(row))
        row_offsets.append(len(row_stream))

    immutable_row_stream = bytes(row_stream)
    row_view = memoryview(immutable_row_stream)
    entries: list[_PreparedHistoricalObservationFingerprint] = []
    try:
        for position in positions:
            as_of = series.timestamp_at(position)
            header, suffix = _historical_observation_fingerprint_envelope_bytes(
                symbol=series.symbol,
                interval=normalized_interval,
                as_of=as_of,
                provider=series.provider,
            )
            fingerprint = _hash_historical_observation_fingerprint_parts(
                header,
                row_view[: row_offsets[position]],
                suffix,
            )
            entries.append(
                _PreparedHistoricalObservationFingerprint(
                    position=position,
                    prefix_length=position + 1,
                    prefix_as_of=as_of,
                    observation_as_of=as_of,
                    fingerprint=fingerprint,
                )
            )
    finally:
        row_view.release()

    return HistoricalObservationFingerprintPrecompute._create(
        source=series,
        interval=normalized_interval,
        entries=tuple(entries),
    )


def _historical_observation_fingerprint_bytes(
    *,
    prefix: HistoricalPricePrefix,
    symbol: str,
    interval: str,
    as_of: datetime,
    provider: str,
) -> bytes:
    header, suffix = _historical_observation_fingerprint_envelope_bytes(
        symbol=symbol,
        interval=interval,
        as_of=as_of,
        provider=provider,
    )
    encoded_rows = tuple(
        _encode_historical_observation_fingerprint_row(row)
        for row in prefix.iter_rows()
    )
    return header + b",".join(encoded_rows) + suffix


def _historical_observation_fingerprint_row(
    row: HistoricalPriceRow,
) -> dict[str, str]:
    symbol, timestamp, open_, high, low, close, volume, provider = row
    return {
        "symbol": symbol,
        "timestamp": timestamp.isoformat(),
        "open": _fingerprint_number(open_),
        "high": _fingerprint_number(high),
        "low": _fingerprint_number(low),
        "close": _fingerprint_number(close),
        "volume": _fingerprint_number(volume),
        "provider": provider,
    }


def _encode_historical_observation_fingerprint_row(
    row: HistoricalPriceRow,
) -> bytes:
    return _canonical_json_bytes(_historical_observation_fingerprint_row(row))


def _historical_observation_fingerprint_envelope_bytes(
    *,
    symbol: str,
    interval: str,
    as_of: datetime,
    provider: str,
) -> tuple[bytes, bytes]:
    header = (
        b'{"as_of":'
        + _json_string_bytes(as_of.isoformat())
        + b',"interval":'
        + _json_string_bytes(interval)
        + b',"provider":'
        + _json_string_bytes(provider)
        + b',"rows":['
    )
    suffix = b'],"symbol":' + _json_string_bytes(symbol) + b"}"
    return header, suffix


def _canonical_json_bytes(value: Mapping[str, object]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        separators=_JSON_SEPARATORS,
        sort_keys=True,
    ).encode("utf-8")


def _json_string_bytes(value: str) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        separators=_JSON_SEPARATORS,
    ).encode("utf-8")


def _hash_historical_observation_fingerprint_bytes(canonical: bytes) -> str:
    return _hash_historical_observation_fingerprint_parts(canonical)


def _hash_historical_observation_fingerprint_parts(
    *parts: bytes | memoryview,
) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part)
    return "sha256:" + digest.hexdigest()


def _validate_evaluation_positions(
    value: object,
    series_length: int,
) -> tuple[int, ...]:
    if not isinstance(value, tuple):
        raise TypeError("evaluation_positions must be a tuple")
    if not value:
        raise ValueError("evaluation_positions must not be empty")
    previous: int | None = None
    for position in value:
        if isinstance(position, bool) or not isinstance(position, int):
            raise TypeError("evaluation positions must be integers")
        if position < 0 or position >= series_length:
            raise IndexError("evaluation position must reference a historical row")
        if previous is not None and position <= previous:
            raise ValueError(
                "evaluation positions must be strictly increasing and unique"
            )
        previous = position
    return value


def _normalize_required_text(value: object, field_name: str) -> str:
    if isinstance(value, bool) or not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text


def _normalize_timestamp(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _fingerprint_number(value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError("fingerprint value must be numeric")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError("fingerprint value must be finite")
    return repr(numeric)


__all__ = [
    "HistoricalObservationFingerprintPrecompute",
    "prepare_historical_observation_fingerprints",
]
