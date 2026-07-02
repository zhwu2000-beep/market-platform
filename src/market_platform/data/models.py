"""Internal data models shared across providers and research modules."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Final

import pandas as pd

PRICE_COLUMNS: Final[list[str]] = [
    "symbol",
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "provider",
]
HEALTH_CHECK_COLUMNS: Final[list[str]] = [
    "provider",
    "status",
    "checked_at",
    "latency_ms",
    "message",
]
UTC_TIMEZONE: Final = "UTC"


@dataclass(frozen=True, slots=True)
class OHLCVBar:
    """Normalized open-high-low-close-volume market bar."""

    symbol: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    source: str


def normalize_price_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a price frame with canonical columns and UTC timestamps."""

    missing_columns = set(PRICE_COLUMNS) - set(frame.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"Price frame is missing required columns: {missing}")

    normalized = frame.loc[:, PRICE_COLUMNS].copy()
    normalized["timestamp"] = pd.to_datetime(normalized["timestamp"], utc=True)
    return normalized


def normalize_health_check_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a health check frame with canonical columns and UTC timestamps."""

    missing_columns = set(HEALTH_CHECK_COLUMNS) - set(frame.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"Health check frame is missing required columns: {missing}")

    normalized = frame.loc[:, HEALTH_CHECK_COLUMNS].copy()
    normalized["checked_at"] = pd.to_datetime(normalized["checked_at"], utc=True)
    return normalized
