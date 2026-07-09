"""Local cache helpers for market data command outputs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from market_platform.data.capabilities import normalize_provider_name
from market_platform.data.exceptions import DataProviderError
from market_platform.data.models import (
    LATEST_PRICE_COLUMNS,
    PRICE_COLUMNS,
    normalize_latest_price_frame,
    normalize_price_frame,
)

DEFAULT_MARKET_DATA_CACHE_DIR = Path(".market-platform/cache")
_CACHE_FILE_SUFFIX = ".csv"
_SAFE_COMPONENT_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True, slots=True)
class MarketDataCacheKey:
    """Stable cache key for a market data request."""

    command: str
    symbol: str
    provider: str
    start: str | None = None
    end: str | None = None
    interval: str | None = None
    window: str | None = None

    @classmethod
    def for_daily(
        cls,
        *,
        symbol: str,
        provider: str | None,
        start: str,
        end: str,
    ) -> MarketDataCacheKey:
        return cls(
            command="daily",
            symbol=_normalize_symbol(symbol),
            provider=_normalize_provider(provider),
            start=start,
            end=end,
        )

    @classmethod
    def for_latest(
        cls,
        *,
        symbol: str,
        provider: str | None,
    ) -> MarketDataCacheKey:
        return cls(
            command="latest",
            symbol=_normalize_symbol(symbol),
            provider=_normalize_provider(provider),
        )

    @classmethod
    def for_intraday(
        cls,
        *,
        symbol: str,
        provider: str | None,
        interval: str,
        window: str = "recent-1d",
        start: str | None = None,
        end: str | None = None,
    ) -> MarketDataCacheKey:
        return cls(
            command="intraday",
            symbol=_normalize_symbol(symbol),
            provider=_normalize_provider(provider),
            start=start,
            end=end,
            interval=interval.strip().lower(),
            window=window.strip().lower(),
        )

    def path(self, base_dir: Path = DEFAULT_MARKET_DATA_CACHE_DIR) -> Path:
        """Return the on-disk cache path for this key."""

        parts = [
            _normalize_command(self.command),
            _normalize_provider_component(self.provider),
            _normalize_symbol_component(self.symbol),
        ]
        filename = self._filename()
        return base_dir.joinpath(*parts, filename)

    def _filename(self) -> str:
        if self.command == "latest":
            return f"latest{_CACHE_FILE_SUFFIX}"

        segments: list[str] = []
        if self.start is not None:
            segments.append(_normalize_component(self.start))
        if self.end is not None:
            segments.append(_normalize_component(self.end))
        if self.command == "intraday":
            segments.append(_normalize_component(self.window or "recent-1d"))
            if self.interval is not None:
                segments.append(_normalize_component(self.interval))
        if not segments:
            segments.append("request")
        return "__".join(segments) + _CACHE_FILE_SUFFIX


class MarketDataCache:
    """Read and write cached market data frames on local disk."""

    def __init__(
        self,
        base_dir: Path = DEFAULT_MARKET_DATA_CACHE_DIR,
    ) -> None:
        self._base_dir = base_dir

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    def path_for(self, key: MarketDataCacheKey) -> Path:
        return key.path(self._base_dir)

    def exists(self, key: MarketDataCacheKey) -> bool:
        return self.path_for(key).exists()

    def load(self, key: MarketDataCacheKey) -> pd.DataFrame:
        return self.load_path(self.path_for(key))

    def load_path(self, path: Path) -> pd.DataFrame:
        try:
            frame = pd.read_csv(path)
        except FileNotFoundError as exc:
            raise DataProviderError(f"Cache entry not found: {path}") from exc
        except Exception as exc:
            raise DataProviderError(f"Unable to read cache entry: {path}") from exc

        return self._normalize_loaded_frame(frame, path)

    def save(self, key: MarketDataCacheKey, frame: pd.DataFrame) -> Path:
        path = self.path_for(key)
        self.save_path(path, frame)
        return path

    def save_path(self, path: Path, frame: pd.DataFrame) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        serializable_frame = frame.copy()
        if "timestamp" in serializable_frame.columns:
            serializable_frame["timestamp"] = serializable_frame["timestamp"].map(
                _serialize_timestamp
            )
        serializable_frame.to_csv(path, index=False)

    def _normalize_loaded_frame(self, frame: pd.DataFrame, path: Path) -> pd.DataFrame:
        columns = list(frame.columns)
        if list(columns) == LATEST_PRICE_COLUMNS:
            normalized = normalize_latest_price_frame(frame)
        elif set(PRICE_COLUMNS).issubset(columns):
            normalized = normalize_price_frame(frame)
        else:
            raise DataProviderError(
                "Cache entry has unsupported market data columns: "
                f"{path}"
            )

        if "timestamp" in normalized.columns and not normalized.empty:
            normalized = normalized.sort_values(
                "timestamp",
                ascending=True,
                kind="stable",
            )
        return normalized.reset_index(drop=True)


def _normalize_provider(provider: str | None) -> str:
    if provider is None:
        return "auto"
    return normalize_provider_name(provider)


def _normalize_command(value: str) -> str:
    normalized_value = value.strip().lower()
    return _SAFE_COMPONENT_PATTERN.sub("_", normalized_value) or "unknown"


def _normalize_provider_component(value: str) -> str:
    normalized_value = value.strip().lower()
    normalized_value = _SAFE_COMPONENT_PATTERN.sub("_", normalized_value)
    normalized_value = normalized_value.strip("._-")
    return normalized_value or "auto"


def _normalize_symbol_component(value: str) -> str:
    normalized_value = value.strip().upper()
    normalized_value = _SAFE_COMPONENT_PATTERN.sub("_", normalized_value)
    normalized_value = normalized_value.strip("._-")
    return normalized_value or "UNKNOWN"


def _normalize_component(value: str) -> str:
    normalized_value = value.strip().lower()
    normalized_value = _SAFE_COMPONENT_PATTERN.sub("_", normalized_value)
    normalized_value = normalized_value.strip("._-")
    return normalized_value or "unknown"


def _normalize_symbol(symbol: str) -> str:
    normalized_symbol = symbol.strip().upper()
    if not normalized_symbol:
        raise ValueError("Symbol cannot be empty")
    return normalized_symbol


def _serialize_timestamp(value: object) -> object:
    if value is None or value is pd.NA:
        return ""
    if isinstance(value, pd.Timestamp):
        if value.tzinfo:
            return value.tz_convert("UTC").isoformat()
        return value.isoformat()
    return str(value)
