"""Canonical validated historical price inputs."""

from __future__ import annotations

import math
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd
from pandas._libs.internals import BlockPlacement  # type: ignore[import-not-found]
from pandas.core.arrays.datetimes import DatetimeArray
from pandas.core.arrays.string_ import StringArray
from pandas.core.internals.blocks import (  # type: ignore[import-not-found]
    DatetimeLikeBlock,
    ExtensionBlock,
    NumpyBlock,
)
from pandas.core.internals.managers import (  # type: ignore[import-not-found]
    BlockManager,
)

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


@dataclass(frozen=True, slots=True)
class _StorageExpectation:
    """Lossless data only; neither possession nor equality grants authority."""

    state: tuple[Any, ...]

    def __reduce__(self) -> Any:
        raise TypeError("storage continuity data is transaction-local")


class _StorageAttachments:
    """Keep original attachments alive, confined to this storage adapter."""

    __slots__ = ("__objects",)

    def __init__(self, objects: tuple[object, ...]) -> None:
        self.__objects = objects

    def __reduce__(self) -> Any:
        raise TypeError("storage attachments are transaction-local")

    def _contains(self, value: object) -> bool:
        return any(value is original for original in self.__objects)

    def _matches(self, objects: tuple[object, ...]) -> bool:
        return len(objects) == len(self.__objects) and all(
            current is original
            for current, original in zip(objects, self.__objects, strict=True)
        )


def _read_storage_continuity(
    series: HistoricalPriceSeries,
    attachments: _StorageAttachments | None = None,
) -> tuple[tuple[Any, ...], tuple[object, ...]]:
    """Bounded reader for the audited pandas 3.0.3 Python-string layout.

    Never extracts columns or invokes lazy manager routing. All content operations
    below operate on exact native storage, after checking the enclosing type.
    """
    if type(series) is not HistoricalPriceSeries:
        raise ValueError("unsupported historical series")
    scalars = (series._symbol, series._provider, series._content_fingerprint)
    if (
        type(scalars[0]) is not str
        or type(scalars[1]) is not str
        or (scalars[2] is not None and type(scalars[2]) is not str)
    ):
        raise ValueError("unsupported historical scalar")
    frame = series._frame
    if type(frame) is not pd.DataFrame:
        raise ValueError("unsupported historical frame")
    manager = object.__getattribute__(frame, "_mgr")
    if type(manager) is not BlockManager:
        raise ValueError("unsupported historical manager")
    axes = manager.axes
    blocks = manager.blocks
    if type(axes) is not list or len(axes) != 2 or type(blocks) is not tuple:
        raise ValueError("unsupported historical layout")
    columns, index = axes
    if type(columns) is not pd.Index or type(index) is not pd.RangeIndex:
        raise ValueError("unsupported historical axes")
    row_range = object.__getattribute__(index, "_range")
    if (
        type(row_range) is not range
        or row_range.start != 0
        or row_range.step != 1
        or row_range.stop <= 0
        or object.__getattribute__(index, "_name") is not None
        or object.__getattribute__(columns, "_name") is not None
    ):
        raise ValueError("unsupported historical index")
    count = row_range.stop
    anchors: list[object] = [
        series,
        frame,
        manager,
        axes,
        blocks,
        columns,
        index,
        row_range,
    ]

    def array(
        value: Any,
        dtype: np.dtype[Any],
        shape: tuple[int, ...],
        *,
        placement: bool = False,
    ) -> Any:
        if type(value) is not np.ndarray:
            raise ValueError("unsupported storage array")
        strides = (
            (dtype.itemsize,)
            if len(shape) == 1
            else (shape[1] * dtype.itemsize, dtype.itemsize)
        )
        if (
            type(value.dtype) is not type(dtype)
            or value.dtype != dtype
            or value.dtype.metadata is not None
            or value.shape != shape
            or not value.flags.c_contiguous
            or not value.flags.aligned
            or value.strides != strides
        ):
            raise ValueError("unsupported storage array layout")
        anchors.extend((value, value.dtype))
        base = value.base
        if base is not None:
            base_dtype = (
                np.dtype("int64") if dtype == np.dtype("datetime64[ns]") else dtype
            )
            if (
                type(base) is not np.ndarray
                or base.base is not None
                or type(base.dtype) is not type(base_dtype)
                or base.dtype != base_dtype
                or base.dtype.metadata is not None
                or not base.flags.c_contiguous
                or not base.flags.aligned
                or base.strides != (base_dtype.itemsize,)
                or (
                    base.size != value.size
                    and not (
                        placement
                        and shape == (1,)
                        and base.shape == (5,)
                        and base_dtype == np.dtype(np.intp)
                    )
                )
            ):
                raise ValueError("unsupported storage backing")
            if not (
                (
                    not placement
                    and len(shape) == 2
                    and shape[0] == 1
                    and base.shape == (count,)
                    and (
                        dtype == np.dtype("float64")
                        or dtype == np.dtype("datetime64[ns]")
                    )
                )
                or (
                    placement
                    and shape == (1,)
                    and base.shape == (5,)
                    and dtype == np.dtype(np.intp)
                )
            ):
                raise ValueError("unsupported audited backing layout")
            anchors.extend((base, base.dtype))
        # Pointer offsets describe attachment/layout, never logical content.
        offset = 0 if base is None else value.ctypes.data - base.ctypes.data
        if base is not None and base.size != value.size:
            # Normalization leaves volume's placement as the final element of
            # the former five-column float block's exact native placement array.
            if offset != 4 * dtype.itemsize or tuple(int(x) for x in base) != (
                2,
                3,
                4,
                5,
                6,
            ):
                raise ValueError("unsupported placement backing span")
        elif offset != 0:
            raise ValueError("unsupported storage offset")
        return (
            dtype.str,
            value.shape,
            value.strides,
            (value.flags.writeable, value.flags.owndata, value.flags.aligned),
            base is None,
            None if base is None else base.shape,
            None if base is None else base.strides,
            None
            if base is None
            else (base.flags.writeable, base.flags.owndata, base.flags.aligned),
            offset,
        )

    def strings(value: Any, length: int, *, axis: bool = False) -> Any:
        if type(value) is not StringArray:
            raise ValueError("unsupported historical string backend")
        dtype = value._dtype
        if type(dtype) is not pd.StringDtype:
            raise ValueError("unsupported historical string dtype")
        if (
            type(object.__getattribute__(dtype, "_storage")) is not str
            or object.__getattribute__(dtype, "_storage") != "python"
        ):
            raise ValueError("unsupported historical string storage")
        missing = np.nan if axis else pd.NA
        if object.__getattribute__(dtype, "_na_value") is not missing:
            raise ValueError("unsupported historical string missing policy")
        anchors.extend((value, dtype))
        backing = value._ndarray
        layout = array(backing, np.dtype(object), (length,))
        values = tuple(backing)
        if any(type(item) is not str for item in values):
            raise ValueError("unsupported historical string value")
        return layout, values

    def stored_dtype(block: Any, kind: str) -> Any:
        # pandas 3.0.3 Block.dtype is cache_readonly: values.dtype is cached in
        # __dict__["_cache"]["dtype"]. Read only stored dictionaries, never dtype.
        # Governed S1 copies/prefixes/row iteration do not populate the retained
        # block's cache (unlike DataFrame.dtypes). Preserve exact absent/present
        # state and, when present, cache/value identity; no rebuilding or repair.
        namespace = object.__getattribute__(block, "__dict__")
        if type(namespace) is not dict or any(type(k) is not str for k in namespace):
            raise ValueError("unsupported historical block dictionary")
        expected = {
            "numeric": ("numpy.float64", "<f8"),
            "timestamp": ("pandas.DatetimeTZDtype", "ns", "UTC"),
            "string": ("pandas.StringDtype", "python", "pd.NA"),
        }[kind]
        if "_cache" not in namespace:
            return expected, "cache_absent", None
        cache = namespace["_cache"]
        # Check keys before lookup: even dict lookup can dispatch to a custom
        # key's equality method on a hash collision with "dtype".
        if type(cache) is not dict or any(type(k) is not str for k in cache):
            raise ValueError("unsupported historical dtype cache")
        anchors.append(cache)
        if "dtype" not in cache:
            return expected, "key_absent", None
        cached = cache["dtype"]
        if kind == "numeric":
            if (
                type(cached) is not type(np.dtype("float64"))
                or cached != np.dtype("float64")
                or cached.metadata is not None
            ):
                raise ValueError("unsupported historical cached numeric dtype")
        elif kind == "timestamp":
            if (
                type(cached) is not pd.DatetimeTZDtype
                or type(object.__getattribute__(cached, "_unit")) is not str
                or object.__getattribute__(cached, "_unit") != "ns"
                or object.__getattribute__(cached, "_tz") is not UTC
            ):
                raise ValueError("unsupported historical cached timestamp dtype")
        elif (
            type(cached) is not pd.StringDtype
            or type(object.__getattribute__(cached, "_storage")) is not str
            or object.__getattribute__(cached, "_storage") != "python"
            or object.__getattribute__(cached, "_na_value") is not pd.NA
        ):
            raise ValueError("unsupported historical cached string dtype")
        # Backing storage and governed placements were independently checked
        # before this call. Exact type/fields now prove the cached logical dtype
        # has this same data-only representation; it is not the authority source.
        anchors.append(cached)
        return expected, "key_present", expected

    column_state = strings(object.__getattribute__(columns, "_data"), 8, axis=True)
    if column_state[1] != tuple(PRICE_COLUMNS):
        raise ValueError("historical column order changed")
    expected_routes: list[tuple[int, int] | None] = [None] * 8
    block_states = []
    for number, block in enumerate(blocks):
        if (
            type(block) is not NumpyBlock
            and type(block) is not DatetimeLikeBlock
            and type(block) is not ExtensionBlock
        ):
            raise ValueError("unsupported historical block")
        if type(block.ndim) is not int or block.ndim != 2:
            raise ValueError("unsupported historical block dimensions")
        placement = block._mgr_locs
        if type(placement) is not BlockPlacement:
            raise ValueError("unsupported historical placement")
        anchors.extend((block, placement))
        # Capture prepares the native placement array once. In the final reader
        # only an original placement is admitted, whose array is already present;
        # no placement or manager routing is materialized in the final comparison.
        if attachments is not None and not attachments._contains(placement):
            raise ValueError("historical placement attachment changed")
        placement_array = placement.as_array
        if type(placement_array) is not np.ndarray:
            raise ValueError("unsupported historical placement storage")
        if placement_array.ndim != 1 or not 0 < placement_array.size <= 8:
            raise ValueError("unsupported historical placement values")
        placement_layout = array(
            placement_array, np.dtype(np.intp), (placement_array.size,), placement=True
        )
        positions = tuple(int(position) for position in placement_array)
        for location, position in enumerate(positions):
            if not 0 <= position < 8 or expected_routes[position] is not None:
                raise ValueError("invalid historical placement coverage")
            expected_routes[position] = (number, location)
        values = block.values
        if type(block) is NumpyBlock:
            kind = "numeric"
            if any(position not in (2, 3, 4, 5, 6) for position in positions):
                raise ValueError("invalid numeric placement")
            layout = array(values, np.dtype("float64"), (len(positions), count))
            if not bool(np.isfinite(values).all()):
                raise ValueError("nonfinite historical storage")
            content = values.tobytes(order="C")
        elif type(block) is DatetimeLikeBlock:
            kind = "timestamp"
            if positions != (1,) or type(values) is not DatetimeArray:
                raise ValueError("unsupported historical timestamp storage")
            if object.__getattribute__(values, "_freq") is not None:
                raise ValueError("unsupported historical timestamp frequency")
            dtype = values._dtype
            if type(dtype) is not pd.DatetimeTZDtype:
                raise ValueError("unsupported historical timestamp dtype")
            if (
                type(object.__getattribute__(dtype, "_unit")) is not str
                or object.__getattribute__(dtype, "_unit") != "ns"
                or object.__getattribute__(dtype, "_tz") is not UTC
            ):
                raise ValueError("unsupported historical timestamp representation")
            anchors.extend((values, dtype))
            backing = values._ndarray
            layout = array(backing, np.dtype("datetime64[ns]"), (1, count))
            if bool(np.isnat(backing).any()):
                raise ValueError("missing historical timestamp")
            content = backing.tobytes(order="C")
        else:
            kind = "string"
            if positions not in ((0,), (7,)):
                raise ValueError("invalid string placement")
            layout, content = strings(values, count)
        block_states.append(
            (positions, placement_layout, layout, content, stored_dtype(block, kind))
        )
    if any(route is None for route in expected_routes):
        raise ValueError("incomplete historical placements")
    # Read STORED slots only. Accessing blknos/blklocs would repair missing routes.
    numbers, locations = manager._blknos, manager._blklocs
    if (numbers is None) != (locations is None):
        raise ValueError("partial historical routing")
    routing = None
    if numbers is not None:
        if (
            type(numbers) is not np.ndarray
            or type(locations) is not np.ndarray
            or numbers.base is not None
            or locations.base is not None
        ):
            raise ValueError("unsupported historical routing backing")
        number_layout = array(numbers, np.dtype(np.intp), (8,))
        location_layout = array(locations, np.dtype(np.intp), (8,))
        routes = tuple((int(numbers[i]), int(locations[i])) for i in range(8))
        if routes != tuple(expected_routes):
            raise ValueError("historical routing disagrees with placements")
        routing = (number_layout, location_layout, routes)
    return (
        (
            scalars,
            (count, 8),
            column_state,
            (0, count, 1),
            tuple(block_states),
            routing,
        ),
        tuple(anchors),
    )


def _capture_storage_continuity(
    series: HistoricalPriceSeries,
) -> tuple[_StorageExpectation, _StorageAttachments]:
    state, anchors = _read_storage_continuity(series)
    return _StorageExpectation(state), _StorageAttachments(anchors)


def _compare_storage_continuity(
    series: HistoricalPriceSeries,
    expectation: _StorageExpectation,
    attachments: _StorageAttachments,
) -> None:
    """Reread CURRENT attached storage without adopting or repairing it."""
    if type(expectation) is not _StorageExpectation or type(attachments) is not (
        _StorageAttachments
    ):
        raise ValueError("original storage capture required")
    state, anchors = _read_storage_continuity(series, attachments)
    if not attachments._matches(anchors) or state != expectation.state:
        raise ValueError("historical storage continuity lost")


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
    for (
        symbol,
        timestamp,
        open_,
        high,
        low,
        close,
        volume,
        _provider,
    ) in series._iter_rows(len(series)):
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

    normalized["timestamp"] = _normalize_aware_timestamp_series(normalized["timestamp"])
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
