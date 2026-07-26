"""Canonical validated historical price inputs."""

from __future__ import annotations

import math
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime

import pandas as pd

from market_platform._fingerprint import canonical_fingerprint, canonical_float
from market_platform.data.models import PRICE_COLUMNS

HistoricalPriceRow = tuple[
    str,
    datetime,
    float,
    float,
    float,
    float,
    float,
    str,
]


class HistoricalPriceSeries:
    """Defensively owned, replay-grade historical OHLCV series."""

    __slots__ = ("_content_fingerprint", "_frame", "_provider", "_symbol")

    def __init__(
        self,
        prices: pd.DataFrame,
        *,
        symbol: str | None = None,
        provider: str | None = None,
    ) -> None:
        expected_symbol = _normalize_optional_text(symbol, "symbol", uppercase=True)
        expected_provider = _normalize_optional_text(provider, "provider")
        frame = _normalize_historical_prices(
            prices,
            expected_symbol=expected_symbol,
            expected_provider=expected_provider,
        )
        self._frame = frame
        self._symbol = str(frame.iloc[0]["symbol"])
        self._provider = str(frame.iloc[0]["provider"])
        self._content_fingerprint: str | None = None

    @property
    def symbol(self) -> str:
        """Return the single normalized series symbol."""

        return self._symbol

    @property
    def provider(self) -> str:
        """Return the single normalized series provider."""

        return self._provider

    @property
    def content_fingerprint(self) -> str:
        """Return the provider-independent identity of the canonical rows."""

        fingerprint = self._content_fingerprint
        if fingerprint is None:
            fingerprint = _historical_price_content_fingerprint(self)
            self._content_fingerprint = fingerprint
        return fingerprint

    @property
    def as_of(self) -> datetime:
        """Return the final timestamp in the series."""

        return self.timestamp_at(len(self) - 1)

    def __len__(self) -> int:
        return len(self._frame)

    def timestamp_at(self, position: int) -> datetime:
        """Return the UTC timestamp at a full-frame position."""

        normalized_position = _normalize_position(position, len(self))
        return _to_datetime(self._frame.iloc[normalized_position]["timestamp"])

    def prefix_at(self, position: int) -> HistoricalPricePrefix:
        """Return the nonempty prefix ending at the inclusive position."""

        return HistoricalPricePrefix(self, position)

    def full_prefix(self) -> HistoricalPricePrefix:
        """Return a prefix containing the complete series."""

        return self.prefix_at(len(self) - 1)

    def to_dataframe(self) -> pd.DataFrame:
        """Materialize an isolated compatibility DataFrame."""

        return self._frame.copy(deep=True)

    def _iter_rows(self, stop: int) -> Iterator[HistoricalPriceRow]:
        for row in self._frame.iloc[:stop].itertuples(index=False, name=None):
            yield (
                str(row[0]),
                _to_datetime(row[1]),
                float(row[2]),
                float(row[3]),
                float(row[4]),
                float(row[5]),
                float(row[6]),
                str(row[7]),
            )

    def _materialize_prefix(self, stop: int) -> pd.DataFrame:
        return self._frame.iloc[:stop].copy(deep=True)


def _historical_price_content_fingerprint(series: HistoricalPriceSeries) -> str:
    rows: list[dict[str, str]] = []
    for symbol, timestamp, open_, high, low, close, volume, _provider in (
        series._iter_rows(len(series))
    ):
        rows.append(
            {
                "symbol": symbol,
                "timestamp": timestamp.isoformat(),
                "open": canonical_float(open_),
                "high": canonical_float(high),
                "low": canonical_float(low),
                "close": canonical_float(close),
                "volume": canonical_float(volume),
            }
        )
    return canonical_fingerprint(
        {
            "schema_version": "historical_price_series_content/v1",
            "symbol": series.symbol,
            "rows": rows,
        }
    )


@dataclass(frozen=True, slots=True, init=False)
class HistoricalPricePrefix:
    """Immutable positional prefix of a validated historical series."""

    _series: HistoricalPriceSeries
    _position: int
    _stop: int

    def __init__(self, series: HistoricalPriceSeries, position: int) -> None:
        if not isinstance(series, HistoricalPriceSeries):
            raise TypeError("series must be a HistoricalPriceSeries")
        normalized_position = _normalize_position(position, len(series))
        object.__setattr__(self, "_series", series)
        object.__setattr__(self, "_position", normalized_position)
        object.__setattr__(self, "_stop", normalized_position + 1)

    @property
    def symbol(self) -> str:
        """Return the owning series symbol."""

        return self._series.symbol

    @property
    def provider(self) -> str:
        """Return the owning series provider."""

        return self._series.provider

    @property
    def position(self) -> int:
        """Return the inclusive final full-frame position."""

        return self._position

    @property
    def as_of(self) -> datetime:
        """Return the timestamp of the final included row."""

        return self._series.timestamp_at(self._position)

    @property
    def window_start(self) -> datetime:
        """Return the timestamp of the first included row."""

        return self._series.timestamp_at(0)

    @property
    def latest_close(self) -> float:
        """Return the close from the final included row."""

        rows = self._series._frame
        return float(rows.iloc[self._position]["close"])

    def __len__(self) -> int:
        return self._stop

    def iter_rows(self) -> Iterator[HistoricalPriceRow]:
        """Iterate normalized rows deterministically as immutable tuples."""

        return self._series._iter_rows(self._stop)

    def to_dataframe(self) -> pd.DataFrame:
        """Materialize an isolated DataFrame for legacy/custom consumers."""

        return self._series._materialize_prefix(self._stop)


def _normalize_historical_prices(
    prices: pd.DataFrame,
    *,
    expected_symbol: str | None,
    expected_provider: str | None,
) -> pd.DataFrame:
    if not isinstance(prices, pd.DataFrame):
        raise TypeError("prices must be a pandas DataFrame")
    if prices.empty:
        raise ValueError("prices must not be empty")
    missing = [column for column in PRICE_COLUMNS if column not in prices.columns]
    if missing:
        raise ValueError("prices missing required columns: " + ", ".join(missing))

    normalized = prices.loc[:, PRICE_COLUMNS].copy()
    normalized["symbol"] = _normalize_text_series(
        normalized["symbol"],
        "symbol",
        uppercase=True,
    )
    normalized["provider"] = _normalize_text_series(
        normalized["provider"],
        "provider",
    )
    symbols = set(normalized["symbol"].astype("string"))
    if expected_symbol is None:
        if len(symbols) != 1:
            raise ValueError("prices must contain exactly one symbol")
    elif symbols != {expected_symbol}:
        raise ValueError("prices must contain exactly one matching symbol")
    providers = set(normalized["provider"].astype("string"))
    if len(providers) != 1:
        raise ValueError("prices must contain exactly one provider")
    if expected_provider is not None and providers != {expected_provider}:
        raise ValueError("prices must contain exactly one matching provider")

    normalized["timestamp"] = _normalize_aware_timestamp_series(
        normalized["timestamp"]
    )
    for column in ("open", "high", "low", "close", "volume"):
        normalized[column] = _normalize_numeric_series(normalized[column], column)
    if (normalized["high"] < normalized["low"]).any():
        raise ValueError("high must be greater than or equal to low")
    if (normalized[["open", "high", "low", "close"]] <= 0.0).any().any():
        raise ValueError("OHLC prices must be positive")
    if (normalized["volume"] < 0.0).any():
        raise ValueError("volume must not be negative")
    normalized = normalized.sort_values("timestamp", kind="stable", ignore_index=True)
    if normalized["timestamp"].duplicated().any():
        raise ValueError("prices must not contain duplicate timestamps")
    return normalized


def _normalize_optional_text(
    value: str | None,
    field_name: str,
    *,
    uppercase: bool = False,
) -> str | None:
    if value is None:
        return None
    return _normalize_required_text(value, field_name, uppercase=uppercase)


def _normalize_required_text(
    value: object,
    field_name: str,
    *,
    uppercase: bool = False,
) -> str:
    if isinstance(value, bool) or not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text.upper() if uppercase else text


def _normalize_text_series(
    series: pd.Series,
    field_name: str,
    *,
    uppercase: bool = False,
) -> pd.Series:
    if series.isna().any():
        raise ValueError(f"{field_name} must not contain missing values")
    normalized = series.map(
        lambda item: _normalize_required_text(
            item,
            field_name,
            uppercase=uppercase,
        )
    )
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


def _normalize_position(value: object, length: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("position must be an integer")
    if value < 0 or value >= length:
        raise IndexError("position must reference an existing historical row")
    return value


def _to_datetime(value: object) -> datetime:
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime().astimezone(UTC)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        return value.astimezone(UTC)
    raise TypeError("timestamp must be a datetime")


__all__ = ["HistoricalPricePrefix", "HistoricalPriceSeries"]
