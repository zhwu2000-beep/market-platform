from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from market_platform.data import HistoricalPricePrefix, HistoricalPriceSeries

_START = datetime(2026, 1, 1, tzinfo=UTC)


def _prices(count: int = 4) -> pd.DataFrame:
    closes = [100.0 + index for index in range(count)]
    return pd.DataFrame(
        {
            "symbol": [" msft "] * count,
            "timestamp": [_START + timedelta(days=index) for index in range(count)],
            "open": closes,
            "high": [close + 1.0 for close in closes],
            "low": [close - 1.0 for close in closes],
            "close": closes,
            "volume": [1_000_000.0] * count,
            "provider": [" test-provider "] * count,
        }
    )


def test_historical_series_requires_complete_nonempty_frame() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        HistoricalPriceSeries(_prices(0))
    with pytest.raises(ValueError, match="missing required columns: volume"):
        HistoricalPriceSeries(_prices().drop(columns="volume"))


def test_historical_series_requires_single_matching_identity() -> None:
    multiple_symbols = _prices()
    multiple_symbols.loc[1, "symbol"] = "AAPL"
    with pytest.raises(ValueError, match="exactly one symbol"):
        HistoricalPriceSeries(multiple_symbols)
    with pytest.raises(ValueError, match="exactly one matching symbol"):
        HistoricalPriceSeries(_prices(), symbol="AAPL")

    multiple_providers = _prices()
    multiple_providers.loc[1, "provider"] = "other"
    with pytest.raises(ValueError, match="exactly one provider"):
        HistoricalPriceSeries(multiple_providers)
    with pytest.raises(ValueError, match="exactly one matching provider"):
        HistoricalPriceSeries(_prices(), provider="other")


def test_historical_series_rejects_naive_and_converts_aware_timestamps_to_utc() -> None:
    naive = _prices()
    naive["timestamp"] = naive["timestamp"].astype(object)
    naive.loc[0, "timestamp"] = datetime(2026, 1, 1)
    with pytest.raises(ValueError, match="timezone-aware"):
        HistoricalPriceSeries(naive)

    offset = timezone(timedelta(hours=8))
    prices = _prices(2)
    prices["timestamp"] = [
        datetime(2026, 1, 1, 8, tzinfo=offset),
        datetime(2026, 1, 2, 8, tzinfo=offset),
    ]
    series = HistoricalPriceSeries(prices)

    assert series.timestamp_at(0) == datetime(2026, 1, 1, tzinfo=UTC)
    assert series.as_of == datetime(2026, 1, 2, tzinfo=UTC)


def test_historical_series_stably_sorts_without_mutating_input() -> None:
    prices = _prices().iloc[[3, 0, 2, 1]].reset_index(drop=True)
    before = prices.copy(deep=True)

    series = HistoricalPriceSeries(prices)

    assert [row[1] for row in series.full_prefix().iter_rows()] == sorted(
        pd.Timestamp(value).to_pydatetime() for value in prices["timestamp"]
    )
    assert_frame_equal(prices, before)


def test_historical_series_content_fingerprint_is_canonical_and_provider_free() -> None:
    prices = _prices()
    permuted = prices.iloc[[3, 0, 2, 1]].reset_index(drop=True)
    integer_equivalent = prices.copy(deep=True)
    integer_equivalent["volume"] = integer_equivalent["volume"].astype(int)
    other_provider = prices.copy(deep=True)
    other_provider["provider"] = "other-provider"
    offset_equivalent = prices.copy(deep=True)
    offset = timezone(timedelta(hours=8))
    offset_equivalent["timestamp"] = offset_equivalent["timestamp"].map(
        lambda value: value.to_pydatetime().astimezone(offset)
    )

    expected = HistoricalPriceSeries(prices).content_fingerprint

    assert HistoricalPriceSeries(permuted).content_fingerprint == expected
    assert HistoricalPriceSeries(integer_equivalent).content_fingerprint == expected
    assert HistoricalPriceSeries(other_provider).content_fingerprint == expected
    assert HistoricalPriceSeries(offset_equivalent).content_fingerprint == expected


def test_historical_series_content_fingerprint_covers_every_owned_row() -> None:
    prices = _prices()
    series = HistoricalPriceSeries(prices)
    expected = series.content_fingerprint
    changed = prices.copy(deep=True)
    changed.loc[1, "close"] += 0.5
    changed.loc[1, "high"] += 0.5

    prices.loc[1, "close"] = 9_999.0

    assert series.content_fingerprint == expected
    assert HistoricalPriceSeries(changed).content_fingerprint != expected
    assert HistoricalPriceSeries(_prices(3)).content_fingerprint != expected


@pytest.mark.parametrize("column", ["open", "high", "low", "close", "volume"])
def test_historical_series_middle_value_changes_content_fingerprint(
    column: str,
) -> None:
    prices = _prices()
    changed = prices.copy(deep=True)
    changed.loc[1, column] += 0.25
    if column == "low":
        changed.loc[1, "high"] += 0.25

    assert (
        HistoricalPriceSeries(changed).content_fingerprint
        != HistoricalPriceSeries(prices).content_fingerprint
    )


def test_historical_series_symbol_changes_content_fingerprint() -> None:
    changed = _prices()
    changed["symbol"] = "AAPL"

    assert (
        HistoricalPriceSeries(changed).content_fingerprint
        != HistoricalPriceSeries(_prices()).content_fingerprint
    )


def test_historical_series_normalizes_signed_zero_volume_identity() -> None:
    fingerprints: set[str] = set()
    for value in (0, 0.0, -0.0):
        prices = _prices()
        prices.loc[1, "volume"] = value
        fingerprints.add(HistoricalPriceSeries(prices).content_fingerprint)

    changed = _prices()
    changed.loc[1, "volume"] = 1.0

    assert len(fingerprints) == 1
    assert HistoricalPriceSeries(changed).content_fingerprint not in fingerprints


def test_historical_series_rejects_duplicate_timestamps() -> None:
    prices = _prices()
    prices.loc[1, "timestamp"] = prices.loc[0, "timestamp"]

    with pytest.raises(ValueError, match="duplicate timestamps"):
        HistoricalPriceSeries(prices)


@pytest.mark.parametrize("column", ["open", "high", "low", "close", "volume"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_historical_series_rejects_nonfinite_ohlcv(
    column: str,
    value: float,
) -> None:
    prices = _prices()
    prices.loc[1, column] = value

    with pytest.raises(ValueError, match="invalid values|finite"):
        HistoricalPriceSeries(prices)


@pytest.mark.parametrize("column", ["open", "high", "low", "close"])
@pytest.mark.parametrize("value", [0.0, -1.0])
def test_historical_series_rejects_nonpositive_ohlc(
    column: str,
    value: float,
) -> None:
    prices = _prices()
    prices.loc[1, column] = value

    with pytest.raises(
        ValueError,
        match="OHLC prices must be positive|high must be greater",
    ):
        HistoricalPriceSeries(prices)


def test_historical_series_rejects_negative_volume_and_inverted_range() -> None:
    negative_volume = _prices()
    negative_volume.loc[1, "volume"] = -1.0
    with pytest.raises(ValueError, match="volume must not be negative"):
        HistoricalPriceSeries(negative_volume)

    inverted = _prices()
    inverted.loc[1, "high"] = inverted.loc[1, "low"] - 1.0
    with pytest.raises(ValueError, match="high must be greater"):
        HistoricalPriceSeries(inverted)


def test_historical_series_isolated_from_original_and_materialized_frames() -> None:
    prices = _prices()
    series = HistoricalPriceSeries(prices)
    expected = series.to_dataframe()

    prices.loc[0, "close"] = 9_999.0
    materialized = series.to_dataframe()
    materialized.loc[0, "close"] = 8_888.0

    assert_frame_equal(series.to_dataframe(), expected)
    assert series.full_prefix().latest_close == expected.iloc[-1]["close"]


def test_historical_prefix_has_inclusive_positional_semantics() -> None:
    series = HistoricalPriceSeries(_prices())
    prefix = series.prefix_at(1)

    assert isinstance(prefix, HistoricalPricePrefix)
    assert len(prefix) == 2
    assert prefix.position == 1
    assert prefix.symbol == "MSFT"
    assert prefix.provider == "test-provider"
    assert prefix.window_start == _START
    assert prefix.as_of == _START + timedelta(days=1)
    assert [row[1] for row in prefix.iter_rows()] == [
        _START,
        _START + timedelta(days=1),
    ]


@pytest.mark.parametrize("position", [-1, 4])
def test_historical_prefix_rejects_out_of_range_position(position: int) -> None:
    with pytest.raises(IndexError, match="existing historical row"):
        HistoricalPriceSeries(_prices()).prefix_at(position)


def test_historical_prefix_rejects_non_integer_position() -> None:
    with pytest.raises(TypeError, match="position must be an integer"):
        HistoricalPriceSeries(_prices()).prefix_at(True)


def test_historical_prefix_identity_is_immutable() -> None:
    prefix = HistoricalPriceSeries(_prices()).prefix_at(1)

    with pytest.raises(AttributeError):
        prefix._position = 3  # type: ignore[misc]


def test_historical_prefix_materialization_cannot_mutate_owner_or_other_prefixes() -> (
    None
):
    series = HistoricalPriceSeries(_prices())
    early = series.prefix_at(1)
    later = series.prefix_at(3)
    early_rows = tuple(early.iter_rows())
    later_rows = tuple(later.iter_rows())

    materialized = early.to_dataframe()
    materialized.loc[0, "close"] = 7_777.0
    materialized.loc[1, "timestamp"] = _START + timedelta(days=100)

    assert tuple(early.iter_rows()) == early_rows
    assert tuple(later.iter_rows()) == later_rows
    assert len(early_rows) == 2
    assert len(later_rows) == 4


@pytest.mark.parametrize("routing", ["absent", "materialized"])
def test_storage_continuity_unchanged_and_callback_free(monkeypatch, routing):
    from pandas.core.internals.managers import BlockManager

    import market_platform.data.historical as historical

    series = HistoricalPriceSeries(_prices())
    manager = series._frame._mgr
    if routing == "absent":
        manager._blknos = manager._blklocs = None
    before = manager._blknos, manager._blklocs

    def forbidden(*args, **kwargs):
        raise AssertionError("projection or lazy routing invoked")

    monkeypatch.setattr(pd.DataFrame, "__getitem__", forbidden)
    monkeypatch.setattr(BlockManager, "iget", forbidden)
    monkeypatch.setattr(BlockManager, "iget_values", forbidden)
    monkeypatch.setattr(BlockManager, "blknos", property(forbidden))
    monkeypatch.setattr(BlockManager, "blklocs", property(forbidden))
    expectation, attachments = historical._capture_storage_continuity(series)
    historical._compare_storage_continuity(series, expectation, attachments)
    assert manager._blknos is before[0] and manager._blklocs is before[1]


@pytest.mark.parametrize(
    "mutation",
    [
        "numeric",
        "signed_zero",
        "timestamp",
        "timezone",
        "unit",
        "string",
        "dtype",
        "columns",
        "index",
        "frame",
        "manager",
        "backing",
        "column",
        "stale_view",
        "cached_fingerprint",
        "coherent_fingerprint",
        "backend",
        "blknos_inplace",
        "blklocs_inplace",
        "blknos_replace",
        "blklocs_replace",
        "absent_materialized",
        "materialized_absent",
        "out_of_bounds",
        "placement_disagreement",
        "routing_swap",
        "routing_subclass",
    ],
)
def test_storage_continuity_rejects_live_mutation(mutation):
    import numpy as np
    from pandas._libs.internals import BlockPlacement
    from pandas.core.internals.blocks import DatetimeLikeBlock, NumpyBlock

    import market_platform.data.historical as historical

    frame = _prices()
    frame["volume"] = 0.0
    series = HistoricalPriceSeries(frame)
    fingerprint = series.content_fingerprint
    frame = series._frame
    manager = frame._mgr
    numeric = next(
        b for b in manager.blocks if type(b) is NumpyBlock and 6 in b.mgr_locs
    )
    timestamp = next(b for b in manager.blocks if type(b) is DatetimeLikeBlock)
    string = next(b for b in manager.blocks if 0 in b.mgr_locs)
    original_routes = manager._blknos, manager._blklocs
    if mutation == "absent_materialized":
        manager._blknos = manager._blklocs = None
    expectation, attachments = historical._capture_storage_continuity(series)
    old_buffer = numeric.values
    if mutation in ("numeric", "cached_fingerprint", "coherent_fingerprint"):
        numeric.values[0, 0] = 42.0
        if mutation == "coherent_fingerprint":
            series._content_fingerprint = "sha256:" + "a" * 64
        else:
            assert series._content_fingerprint == fingerprint
    elif mutation == "signed_zero":
        numeric.values[0, 0] = -0.0
    elif mutation == "timestamp":
        timestamp.values._ndarray[0, 0] += np.timedelta64(1, "ns")
    elif mutation in ("timezone", "unit"):
        if mutation == "unit":
            timestamp.values._dtype._unit = "us"
        else:
            timestamp.values._dtype._tz = timezone(timedelta(hours=1))
    elif mutation == "string":
        string.values._ndarray[0] = "AAPL"
    elif mutation == "dtype":
        numeric.values.dtype = np.int64
    elif mutation == "columns":
        frame.columns = list(reversed(frame.columns))
    elif mutation == "index":
        frame.index = pd.RangeIndex(1, len(frame) + 1)
    elif mutation == "frame":
        series._frame = frame.copy(deep=True)
    elif mutation == "manager":
        frame._mgr = manager.copy(deep=True)
    elif mutation in ("backing", "stale_view"):
        numeric.values = old_buffer.copy()
        if mutation == "stale_view":
            numeric.values[0, 0] = 42.0
            assert old_buffer[0, 0] == 0.0
    elif mutation == "column":
        frame["volume"] = frame["volume"].copy()
    elif mutation == "backend":
        frame["symbol"] = frame["symbol"].astype(object)
    elif mutation == "blknos_inplace":
        manager._blknos[0] = manager._blknos[1]
    elif mutation == "blklocs_inplace":
        manager._blklocs[0] = 1
    elif mutation == "blknos_replace":
        manager._blknos = manager._blknos.copy()
    elif mutation == "blklocs_replace":
        manager._blklocs = manager._blklocs.copy()
    elif mutation == "absent_materialized":
        manager._blknos, manager._blklocs = original_routes
    elif mutation == "materialized_absent":
        manager._blknos = manager._blklocs = None
    elif mutation == "out_of_bounds":
        manager._blknos[0] = len(manager.blocks)
    elif mutation == "placement_disagreement":
        numeric._mgr_locs = BlockPlacement(slice(2, 3))
    elif mutation == "routing_swap":
        blocks = manager.blocks
        axes = manager.axes
        buffers = tuple(b.values for b in blocks)
        manager._blknos[[2, 3]] = manager._blknos[[3, 2]]
        assert manager.blocks is blocks and manager.axes is axes
        assert all(b.values is v for b, v in zip(blocks, buffers, strict=True))
        assert series._content_fingerprint == fingerprint
    else:

        class Unapproved(np.ndarray):
            def __iter__(self):
                raise AssertionError("unapproved routing dispatched")

        manager._blknos = manager._blknos.view(Unapproved)
    with pytest.raises(ValueError):
        historical._compare_storage_continuity(series, expectation, attachments)


def test_storage_continuity_public_surface_unchanged():
    import ast
    import inspect
    import subprocess

    import market_platform.data.historical as historical

    baseline = ast.parse(
        subprocess.check_output(
            [
                "git",
                "show",
                "97d42bea45cb191cc8bb72008342179852d9182a:"
                "src/market_platform/data/historical.py",
            ]
        ).decode()
    )
    current = ast.parse(inspect.getsource(historical))
    for name in ("HistoricalPriceSeries", "HistoricalPricePrefix"):
        before = next(n for n in baseline.body if getattr(n, "name", None) == name)
        after = next(n for n in current.body if getattr(n, "name", None) == name)
        assert ast.dump(before) == ast.dump(after)
    assert historical.__all__ == ["HistoricalPricePrefix", "HistoricalPriceSeries"]


def test_storage_continuity_expectation_is_data_only():
    import pickle
    from dataclasses import FrozenInstanceError, fields

    import market_platform.data.historical as historical

    series = HistoricalPriceSeries(_prices())
    expectation, attachments = historical._capture_storage_continuity(series)

    def data_only(value):
        if type(value) is tuple:
            for child in value:
                data_only(child)
        else:
            assert type(value) in (str, int, bool, bytes, type(None))

    assert [field.name for field in fields(expectation)] == ["state"]
    data_only(expectation.state)
    with pytest.raises(FrozenInstanceError):
        expectation.state = ()
    for value in (expectation, attachments):
        with pytest.raises(TypeError):
            pickle.dumps(value)


@pytest.mark.parametrize("phase", ["capture", "compare"])
def test_storage_continuity_unapproved_elements_never_dispatch(phase):
    import market_platform.data.historical as historical

    series = HistoricalPriceSeries(_prices())
    block = next(b for b in series._frame._mgr.blocks if 0 in b.mgr_locs)
    expectation, attachments = historical._capture_storage_continuity(series)
    calls = []

    def forbidden(*args):
        calls.append(True)
        raise AssertionError("untrusted string element dispatch")

    class Untrusted:
        __eq__ = __deepcopy__ = __str__ = forbidden

    block.values._ndarray[0] = Untrusted()
    with pytest.raises(ValueError, match="unsupported historical string value"):
        if phase == "capture":
            historical._capture_storage_continuity(series)
        else:
            historical._compare_storage_continuity(series, expectation, attachments)
    assert not calls


def test_storage_continuity_rejects_unapproved_stride_before_capture():
    from pandas.core.internals.blocks import NumpyBlock

    import market_platform.data.historical as historical

    series = HistoricalPriceSeries(_prices())
    block = next(b for b in series._frame._mgr.blocks if type(b) is NumpyBlock)
    block.values.strides = (0, 8)
    with pytest.raises(ValueError):
        historical._capture_storage_continuity(series)


def _storage_without_dtype_cache(series):
    """Identity and content witness independent of pandas logical dtype access."""
    import numpy as np

    frame = series._frame
    manager = frame._mgr
    blocks = []
    for block in manager.blocks:
        values = block.values
        backing = values if type(values) is np.ndarray else values._ndarray
        blocks.append(
            (
                id(block),
                id(block._mgr_locs),
                id(block._mgr_locs.as_array),
                tuple(block._mgr_locs.as_array),
                id(values),
                id(backing),
                id(backing.base),
                id(backing.dtype),
                backing.dtype.str,
                backing.shape,
                backing.strides,
                backing.tobytes(),
            )
        )
    return (
        id(series),
        id(frame),
        id(manager),
        id(manager.blocks),
        tuple(blocks),
        id(manager.axes),
        tuple(id(axis) for axis in manager.axes),
        tuple(frame.columns),
        tuple(frame.index),
        tuple(
            (id(route), None if route is None else route.tobytes())
            for route in (manager._blknos, manager._blklocs)
        ),
        series._content_fingerprint,
    )


@pytest.mark.parametrize("state", ["cache_absent", "key_absent", "key_present"])
def test_storage_continuity_dtype_cache_unchanged_without_materialization(
    monkeypatch, state
):
    from pandas.core.internals.blocks import Block

    import market_platform.data.historical as historical

    series = HistoricalPriceSeries(_prices())
    blocks = series._frame._mgr.blocks
    for block in blocks:
        if state == "cache_absent":
            del block.__dict__["_cache"]
        elif state == "key_absent":
            del block._cache["dtype"]
    # Audited governed operations copy/slice retained blocks; they do not read
    # retained Block.dtype. Exact state continuity (policy A) is therefore safe.
    series.to_dataframe()
    series.full_prefix().to_dataframe()
    tuple(series.full_prefix().iter_rows())
    calls = []

    def forbidden(*args):
        calls.append(True)
        raise AssertionError("lazy Block.dtype invoked")

    monkeypatch.setattr(Block, "dtype", property(forbidden))
    expectation, attachments = historical._capture_storage_continuity(series)
    historical._compare_storage_continuity(series, expectation, attachments)
    assert all(item[-1][1] == state for item in expectation.state[4])
    assert not calls
    for block in blocks:
        namespace = block.__dict__
        assert ("_cache" in namespace) == (state != "cache_absent")
        if state != "cache_absent":
            assert ("dtype" in namespace["_cache"]) == (state == "key_present")


@pytest.mark.parametrize("column", [0, 1, 2])
@pytest.mark.parametrize("mutation", ["value", "equal_object"])
def test_storage_continuity_dtype_cache_only_mutation(column, mutation):
    import numpy as np

    import market_platform.data.historical as historical

    series = HistoricalPriceSeries(_prices())
    _ = series.content_fingerprint
    block = next(b for b in series._frame._mgr.blocks if column in b.mgr_locs)
    original = block._cache["dtype"]
    expectation, attachments = historical._capture_storage_continuity(series)
    before = _storage_without_dtype_cache(series)
    changed = (
        np.dtype("int64")
        if mutation == "value"
        else {
            0: lambda: pd.StringDtype(storage="python", na_value=pd.NA),
            1: lambda: pd.DatetimeTZDtype(unit="ns", tz=UTC),
            2: lambda: np.dtype("float64", copy=True),
        }[column]()
    )
    assert changed is not original
    block._cache["dtype"] = changed
    if column == 2 and mutation == "value":
        assert block.values.dtype == np.dtype("float64")
        assert series._frame.dtypes.iloc[column] == np.dtype("int64")
    with pytest.raises(ValueError):
        historical._compare_storage_continuity(series, expectation, attachments)
    assert _storage_without_dtype_cache(series) == before
    assert block._cache["dtype"] is changed


@pytest.mark.parametrize(
    "transition",
    [
        "cache_add",
        "key_add",
        "cache_delete",
        "key_delete",
        "cache_replace",
        "empty_add",
    ],
)
def test_storage_continuity_dtype_cache_rejects_transitions(transition):
    import market_platform.data.historical as historical

    series = HistoricalPriceSeries(_prices())
    block = series._frame._mgr.blocks[0]
    if transition in ("cache_add", "empty_add"):
        del block.__dict__["_cache"]
    elif transition == "key_add":
        del block._cache["dtype"]
    expectation, attachments = historical._capture_storage_continuity(series)
    if transition in ("cache_add", "key_add"):
        # Public pandas access can materialize the right dtype, but is not an
        # operation on retained blocks in governed S1.
        _ = series._frame.dtypes
    elif transition == "cache_delete":
        del block.__dict__["_cache"]
    elif transition == "key_delete":
        del block._cache["dtype"]
    elif transition == "empty_add":
        block._cache = {}
    else:
        block._cache = dict(block._cache)
    with pytest.raises(ValueError, match="continuity lost"):
        historical._compare_storage_continuity(series, expectation, attachments)


@pytest.mark.parametrize("phase", ["capture", "compare"])
@pytest.mark.parametrize("representation", ["object", "dtype_subclass", "cache", "key"])
def test_storage_continuity_dtype_cache_rejects_before_dispatch(phase, representation):
    import market_platform.data.historical as historical

    series = HistoricalPriceSeries(_prices())
    block = series._frame._mgr.blocks[0]
    expectation, attachments = historical._capture_storage_continuity(series)
    calls = []

    def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError("untrusted dtype cache dispatch")

    class Untrusted:
        __eq__ = __str__ = __iter__ = __array__ = __deepcopy__ = forbidden

        def __hash__(self):
            return hash("dtype")

    class UntrustedDtype(pd.StringDtype):
        __eq__ = forbidden
        storage = property(forbidden)

    class UntrustedCache(dict):
        __getitem__ = __contains__ = __iter__ = get = forbidden

    if representation == "object":
        block._cache["dtype"] = Untrusted()
    elif representation == "dtype_subclass":
        block._cache["dtype"] = object.__new__(UntrustedDtype)
    elif representation == "cache":
        block._cache = UntrustedCache(block._cache)
    else:
        block._cache = {Untrusted(): block.values._dtype}
    with pytest.raises(ValueError, match="unsupported historical"):
        if phase == "capture":
            historical._capture_storage_continuity(series)
        else:
            historical._compare_storage_continuity(series, expectation, attachments)
    assert not calls


@pytest.mark.parametrize("phase", ["capture", "compare"])
@pytest.mark.parametrize(
    "representation,error",
    [
        ("nan", "nonfinite historical storage"),
        ("positive_inf", "nonfinite historical storage"),
        ("negative_inf", "nonfinite historical storage"),
        ("nat", "missing historical timestamp"),
        ("missing_string", "unsupported historical string value"),
        ("extension", "unsupported historical string backend"),
        ("subclass", "unsupported storage array"),
    ],
)
def test_storage_continuity_unsupported_storage_before_dispatch(
    phase, representation, error
):
    import numpy as np
    from pandas.core.internals.blocks import DatetimeLikeBlock, NumpyBlock

    import market_platform.data.historical as historical

    series = HistoricalPriceSeries(_prices())
    blocks = series._frame._mgr.blocks
    numeric = next(b for b in blocks if type(b) is NumpyBlock)
    timestamp = next(b for b in blocks if type(b) is DatetimeLikeBlock)
    string = next(b for b in blocks if 0 in b.mgr_locs)
    expectation, attachments = historical._capture_storage_continuity(series)
    calls = []

    def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError("untrusted storage dispatch")

    class UntrustedExtension(pd.api.extensions.ExtensionArray):
        dtype = property(forbidden)
        __array__ = __iter__ = __eq__ = __getitem__ = __len__ = forbidden
        copy = to_numpy = astype = __deepcopy__ = forbidden

    class UntrustedStorage(np.ndarray):
        dtype = property(forbidden)
        __array__ = __iter__ = __eq__ = __getitem__ = copy = __deepcopy__ = forbidden

    if representation in ("nan", "positive_inf", "negative_inf"):
        numeric.values[0, 0] = {
            "nan": np.nan,
            "positive_inf": np.inf,
            "negative_inf": -np.inf,
        }[representation]
    elif representation == "nat":
        timestamp.values._ndarray[0, 0] = np.datetime64("NaT", "ns")
    elif representation == "missing_string":
        string.values._ndarray[0] = pd.NA
    elif representation == "extension":
        string.values = UntrustedExtension()
    else:
        numeric.values = numeric.values.view(UntrustedStorage)
    with pytest.raises(ValueError, match=error):
        if phase == "capture":
            historical._capture_storage_continuity(series)
        else:
            historical._compare_storage_continuity(series, expectation, attachments)
    assert not calls
