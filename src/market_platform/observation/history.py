"""Historical observation construction from canonical price prefixes."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from datetime import UTC, datetime
from numbers import Real

import pandas as pd

from market_platform.data.historical import HistoricalPricePrefix, HistoricalPriceSeries
from market_platform.observation.builder import build_market_observation
from market_platform.observation.fingerprint import (
    HistoricalObservationFingerprintPrecompute,
    _hash_historical_observation_fingerprint_bytes,
    _historical_observation_fingerprint_bytes,
    _historical_observation_fingerprint_row,
)
from market_platform.observation.models import (
    MarketObservation,
    ObservationIdentity,
    ObservationProvenance,
    PriceFacts,
)
from market_platform.signals.models import MarketSignalSnapshot
from market_platform.structure.models import PriceStructureSnapshot


def build_historical_market_observation(
    prices: pd.DataFrame,
    *,
    symbol: str,
    interval: str,
    as_of: datetime,
    provider: str,
    signal_snapshot: MarketSignalSnapshot,
    structure_snapshot: PriceStructureSnapshot,
) -> MarketObservation:
    """Build an observation from a raw historical price DataFrame."""

    normalized_as_of = _normalize_timestamp(as_of, "as_of")
    normalized_symbol, normalized_interval, normalized_provider = (
        _normalize_observation_metadata(
            symbol=symbol,
            interval=interval,
            provider=provider,
        )
    )
    series = HistoricalPriceSeries(
        prices,
    )
    if series.symbol != normalized_symbol:
        raise ValueError("price prefix symbol must match symbol")
    if series.provider != normalized_provider:
        raise ValueError("price prefix provider must match provider")
    if series.as_of > normalized_as_of:
        raise ValueError("price prefix must not contain timestamps later than as_of")
    return build_historical_market_observation_from_prefix(
        series.full_prefix(),
        symbol=normalized_symbol,
        interval=normalized_interval,
        as_of=normalized_as_of,
        provider=normalized_provider,
        signal_snapshot=signal_snapshot,
        structure_snapshot=structure_snapshot,
    )


def build_historical_market_observation_from_prefix(
    prefix: HistoricalPricePrefix,
    *,
    symbol: str,
    interval: str,
    as_of: datetime,
    provider: str,
    signal_snapshot: MarketSignalSnapshot,
    structure_snapshot: PriceStructureSnapshot,
    fingerprint_precompute: HistoricalObservationFingerprintPrecompute | None = None,
) -> MarketObservation:
    """Build an observation from an already validated historical prefix."""

    if not isinstance(prefix, HistoricalPricePrefix):
        raise TypeError("prefix must be a HistoricalPricePrefix")
    normalized_as_of = _normalize_timestamp(as_of, "as_of")
    normalized_symbol, normalized_interval, normalized_provider = (
        _normalize_observation_metadata(
            symbol=symbol,
            interval=interval,
            provider=provider,
        )
    )
    if prefix.symbol != normalized_symbol:
        raise ValueError("historical prefix symbol must match symbol")
    if prefix.provider != normalized_provider:
        raise ValueError("historical prefix provider must match provider")
    if prefix.as_of > normalized_as_of:
        raise ValueError("as_of must not be earlier than historical prefix endpoint")
    if not isinstance(signal_snapshot, MarketSignalSnapshot):
        raise TypeError("signal_snapshot must be a MarketSignalSnapshot")
    if not isinstance(structure_snapshot, PriceStructureSnapshot):
        raise TypeError("structure_snapshot must be a PriceStructureSnapshot")
    if signal_snapshot.symbol != normalized_symbol:
        raise ValueError("signal_snapshot symbol must match historical prefix")
    if fingerprint_precompute is not None and not isinstance(
        fingerprint_precompute,
        HistoricalObservationFingerprintPrecompute,
    ):
        raise TypeError(
            "fingerprint_precompute must be a "
            "HistoricalObservationFingerprintPrecompute or None"
        )

    return _construct_historical_observation(
        identity=_build_observation_identity(
            symbol=normalized_symbol,
            interval=normalized_interval,
            as_of=normalized_as_of,
            prefix=prefix,
        ),
        provenance=_build_observation_provenance(
            prefix=prefix,
            symbol=normalized_symbol,
            interval=normalized_interval,
            as_of=normalized_as_of,
            provider=normalized_provider,
            fingerprint_precompute=fingerprint_precompute,
        ),
        price_facts=_build_price_facts(prefix),
        signal_snapshot=signal_snapshot,
        structure_snapshot=structure_snapshot,
    )


def _normalize_observation_metadata(
    *,
    symbol: str,
    interval: str,
    provider: str,
) -> tuple[str, str, str]:
    return (
        _normalize_required_text(symbol, "symbol").upper(),
        _normalize_required_text(interval, "interval"),
        _normalize_required_text(provider, "provider"),
    )


def _build_observation_identity(
    *,
    symbol: str,
    interval: str,
    as_of: datetime,
    prefix: HistoricalPricePrefix,
) -> ObservationIdentity:
    return ObservationIdentity(
        symbol=symbol,
        interval=interval,
        as_of=as_of,
        window_start=prefix.window_start,
        window_end=prefix.as_of,
    )


def _build_price_facts(prefix: HistoricalPricePrefix) -> PriceFacts:
    return PriceFacts(
        latest_price=_normalize_positive_price(prefix.latest_close),
        observed_at=prefix.as_of,
    )


def _build_observation_provenance(
    *,
    prefix: HistoricalPricePrefix,
    symbol: str,
    interval: str,
    as_of: datetime,
    provider: str,
    fingerprint_precompute: HistoricalObservationFingerprintPrecompute | None = None,
) -> ObservationProvenance:
    input_fingerprint = (
        _historical_observation_fingerprint(
            prefix=prefix,
            symbol=symbol,
            interval=interval,
            as_of=as_of,
            provider=provider,
        )
        if fingerprint_precompute is None
        else fingerprint_precompute.fingerprint_for_validated_prefix(
            prefix,
            symbol=symbol,
            interval=interval,
            provider=provider,
            as_of=as_of,
        )
    )
    return ObservationProvenance(
        provider=provider,
        methodology="historical_replay_observation",
        methodology_version="1.0.0",
        parameters={"interval": interval},
        input_fingerprint=input_fingerprint,
    )


def _construct_historical_observation(
    *,
    identity: ObservationIdentity,
    provenance: ObservationProvenance,
    price_facts: PriceFacts,
    signal_snapshot: MarketSignalSnapshot,
    structure_snapshot: PriceStructureSnapshot,
) -> MarketObservation:
    return build_market_observation(
        identity,
        provenance,
        price_facts=price_facts,
        signal_snapshot=signal_snapshot,
        structure_snapshot=structure_snapshot,
    )


def _historical_observation_fingerprint(
    *,
    prefix: HistoricalPricePrefix,
    symbol: str,
    interval: str,
    as_of: datetime,
    provider: str,
) -> str:
    canonical = _historical_observation_fingerprint_bytes(
        prefix=prefix,
        symbol=symbol,
        interval=interval,
        as_of=as_of,
        provider=provider,
    )
    return _hash_historical_observation_fingerprint_bytes(canonical)


def _historical_observation_fingerprint_payload(
    *,
    prefix: HistoricalPricePrefix,
    symbol: str,
    interval: str,
    as_of: datetime,
    provider: str,
) -> dict[str, object]:
    return {
        "as_of": as_of.isoformat(),
        "interval": interval,
        "provider": provider,
        "rows": _historical_observation_fingerprint_rows(prefix),
        "symbol": symbol,
    }


def _historical_observation_fingerprint_rows(
    prefix: HistoricalPricePrefix,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in prefix.iter_rows():
        rows.append(_historical_observation_fingerprint_row(row))
    return rows


def _canonicalize_historical_observation_fingerprint_payload(
    payload: Mapping[str, object],
) -> str:
    return json.dumps(payload, allow_nan=False, separators=(",", ":"), sort_keys=True)


def _hash_historical_observation_fingerprint(canonical: str) -> str:
    return _hash_historical_observation_fingerprint_bytes(canonical.encode("utf-8"))


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


def _normalize_positive_price(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError("latest close must be numeric")
    numeric = float(value)
    if not math.isfinite(numeric) or numeric <= 0.0:
        raise ValueError("latest close must be a positive finite number")
    return numeric


__all__ = [
    "build_historical_market_observation",
    "build_historical_market_observation_from_prefix",
]
