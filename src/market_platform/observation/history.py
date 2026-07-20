"""Historical observation construction from point-in-time price prefixes."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from datetime import UTC, datetime
from numbers import Real

import pandas as pd

from market_platform.observation.builder import build_market_observation
from market_platform.observation.models import (
    MarketObservation,
    ObservationIdentity,
    ObservationProvenance,
    PriceFacts,
)
from market_platform.signals.models import MarketSignalSnapshot
from market_platform.structure.models import PriceStructureSnapshot

_PRICE_COLUMNS = (
    "symbol",
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "provider",
)


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
    """Build an observation from prices available no later than as_of."""

    normalized_as_of = _normalize_timestamp(as_of, "as_of")
    normalized = _normalize_price_prefix(prices, normalized_as_of)
    normalized_symbol, normalized_interval, normalized_provider = (
        _normalize_observation_metadata(
            symbol=symbol,
            interval=interval,
            provider=provider,
        )
    )
    if not isinstance(signal_snapshot, MarketSignalSnapshot):
        raise TypeError("signal_snapshot must be a MarketSignalSnapshot")
    if not isinstance(structure_snapshot, PriceStructureSnapshot):
        raise TypeError("structure_snapshot must be a PriceStructureSnapshot")

    symbols = set(normalized["symbol"].astype("string"))
    if symbols != {normalized_symbol}:
        raise ValueError("price prefix symbol must match symbol")
    providers = set(normalized["provider"].astype("string"))
    if providers != {normalized_provider}:
        raise ValueError("price prefix provider must match provider")

    return _construct_historical_observation(
        identity=_build_observation_identity(
            symbol=normalized_symbol,
            interval=normalized_interval,
            as_of=normalized_as_of,
            prices=normalized,
        ),
        provenance=_build_observation_provenance(
            prices=normalized,
            symbol=normalized_symbol,
            interval=normalized_interval,
            as_of=normalized_as_of,
            provider=normalized_provider,
        ),
        price_facts=_build_price_facts(normalized),
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
    prices: pd.DataFrame,
) -> ObservationIdentity:
    return ObservationIdentity(
        symbol=symbol,
        interval=interval,
        as_of=as_of,
        window_start=_to_datetime(prices.iloc[0]["timestamp"]),
        window_end=_to_datetime(prices.iloc[-1]["timestamp"]),
    )


def _build_price_facts(prices: pd.DataFrame) -> PriceFacts:
    window_end = _to_datetime(prices.iloc[-1]["timestamp"])
    latest_price = _normalize_positive_price(prices.iloc[-1]["close"])
    return PriceFacts(latest_price=latest_price, observed_at=window_end)


def _build_observation_provenance(
    *,
    prices: pd.DataFrame,
    symbol: str,
    interval: str,
    as_of: datetime,
    provider: str,
) -> ObservationProvenance:
    return ObservationProvenance(
        provider=provider,
        methodology="historical_replay_observation",
        methodology_version="1.0.0",
        parameters={"interval": interval},
        input_fingerprint=_historical_observation_fingerprint(
            prices=prices,
            symbol=symbol,
            interval=interval,
            as_of=as_of,
            provider=provider,
        ),
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


def _normalize_price_prefix(prices: pd.DataFrame, as_of: datetime) -> pd.DataFrame:
    if not isinstance(prices, pd.DataFrame):
        raise TypeError("prices must be a pandas DataFrame")
    if prices.empty:
        raise ValueError("price prefix must not be empty")
    missing = [column for column in _PRICE_COLUMNS if column not in prices.columns]
    if missing:
        raise ValueError("price prefix missing required columns: " + ", ".join(missing))

    normalized = prices.loc[:, list(_PRICE_COLUMNS)].copy()
    normalized["symbol"] = _normalize_text_series(normalized["symbol"], "symbol")
    normalized["provider"] = _normalize_text_series(normalized["provider"], "provider")
    normalized["timestamp"] = _normalize_aware_timestamp_series(normalized["timestamp"])
    if (normalized["timestamp"] > pd.Timestamp(as_of)).any():
        raise ValueError("price prefix must not contain timestamps later than as_of")
    for column in ("open", "high", "low", "close", "volume"):
        normalized[column] = _normalize_numeric_series(normalized[column], column)
    if (normalized["high"] < normalized["low"]).any():
        raise ValueError("high must be greater than or equal to low")
    normalized = normalized.sort_values("timestamp", kind="stable", ignore_index=True)
    if normalized["timestamp"].duplicated().any():
        raise ValueError("price prefix must not contain duplicate timestamps")
    return normalized


def _historical_observation_fingerprint(
    *,
    prices: pd.DataFrame,
    symbol: str,
    interval: str,
    as_of: datetime,
    provider: str,
) -> str:
    payload = _historical_observation_fingerprint_payload(
        prices=prices,
        symbol=symbol,
        interval=interval,
        as_of=as_of,
        provider=provider,
    )
    canonical = _canonicalize_historical_observation_fingerprint_payload(payload)
    return _hash_historical_observation_fingerprint(canonical)


def _historical_observation_fingerprint_payload(
    *,
    prices: pd.DataFrame,
    symbol: str,
    interval: str,
    as_of: datetime,
    provider: str,
) -> dict[str, object]:
    return {
        "as_of": as_of.isoformat(),
        "interval": interval,
        "provider": provider,
        "rows": _historical_observation_fingerprint_rows(prices),
        "symbol": symbol,
    }


def _historical_observation_fingerprint_rows(
    prices: pd.DataFrame,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in prices.itertuples(index=False):
        rows.append(
            {
                "symbol": str(row.symbol),
                "timestamp": _to_datetime(row.timestamp).isoformat(),
                "open": _fingerprint_number(row.open),
                "high": _fingerprint_number(row.high),
                "low": _fingerprint_number(row.low),
                "close": _fingerprint_number(row.close),
                "volume": _fingerprint_number(row.volume),
                "provider": str(row.provider),
            }
        )
    return rows


def _canonicalize_historical_observation_fingerprint_payload(
    payload: Mapping[str, object],
) -> str:
    return json.dumps(payload, allow_nan=False, separators=(",", ":"), sort_keys=True)


def _hash_historical_observation_fingerprint(canonical: str) -> str:
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _normalize_required_text(value: object, field_name: str) -> str:
    if isinstance(value, bool) or not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text


def _normalize_text_series(series: pd.Series, field_name: str) -> pd.Series:
    if series.isna().any():
        raise ValueError(f"{field_name} must not contain missing values")
    normalized = series.map(lambda item: _normalize_required_text(item, field_name))
    if field_name == "symbol":
        normalized = normalized.map(str.upper)
    return normalized.astype("string")


def _normalize_aware_timestamp_series(series: pd.Series) -> pd.Series:
    values: list[pd.Timestamp] = []
    for item in series:
        timestamp = pd.Timestamp(item)
        if pd.isna(timestamp):
            raise ValueError("timestamp must not contain missing values")
        if timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        values.append(timestamp.tz_convert(UTC))
    return pd.Series(values, index=series.index, dtype="datetime64[ns, UTC]")


def _normalize_numeric_series(series: pd.Series, field_name: str) -> pd.Series:
    if series.map(lambda value: isinstance(value, bool)).any():
        raise TypeError(f"{field_name} must be numeric")
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.isna().any():
        raise ValueError(f"{field_name} must not contain invalid values")
    if not numeric.map(math.isfinite).all():
        raise ValueError(f"{field_name} must be finite")
    return numeric.astype(float)


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


def _fingerprint_number(value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError("fingerprint value must be numeric")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError("fingerprint value must be finite")
    return repr(numeric)


def _to_datetime(value: object) -> datetime:
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime().astimezone(UTC)
    if isinstance(value, datetime):
        return _normalize_timestamp(value, "timestamp")
    raise TypeError("timestamp must be a datetime")


__all__ = ["build_historical_market_observation"]
