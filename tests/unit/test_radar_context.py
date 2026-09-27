"""FAST PURE context tests; no calendar, provider or governed setup."""

from collections.abc import Callable
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from typing import Any
from unittest.mock import Mock

import pytest

from market_platform.instruments.identity import CanonicalInstrumentId
from market_platform.radar.context import (
    RadarContextError,
    RadarEvaluationContext,
    RadarFactKey,
)

INSTRUMENT = CanonicalInstrumentId("sample")
AS_OF = datetime(2026, 9, 24, tzinfo=timezone(timedelta(hours=8)))


def context(
    loaders: dict[RadarFactKey[object], Callable[[], object]],
) -> RadarEvaluationContext:
    return RadarEvaluationContext(INSTRUMENT, AS_OF, loaders)


def test_identity_and_no_public_write_surface() -> None:
    ctx = context({})
    assert ctx.instrument is INSTRUMENT
    assert ctx.as_of is AS_OF
    assert {name for name in dir(ctx) if not name.startswith("_")} == {
        "instrument",
        "as_of",
        "get_fact",
    }
    for name, value in (("instrument", INSTRUMENT), ("as_of", AS_OF)):
        with pytest.raises(AttributeError):
            setattr(ctx, name, value)


class NoOffset(tzinfo):
    def utcoffset(self, dt: datetime | None) -> None:
        return None


@pytest.mark.parametrize(
    "as_of", [datetime(2026, 9, 24), datetime(2026, 9, 24, tzinfo=NoOffset())]
)
def test_naive_timestamp_rejected(as_of: datetime) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        RadarEvaluationContext(INSTRUMENT, as_of, {})


@pytest.mark.parametrize(
    "instrument,as_of,loaders",
    [
        ("sample", AS_OF, {}),
        (INSTRUMENT, "2026-09-24", {}),
        (INSTRUMENT, AS_OF, []),
        (INSTRUMENT, AS_OF, {"a": lambda: 1}),
        (INSTRUMENT, AS_OF, {RadarFactKey("a", int): 1}),
    ],
)
def test_wrong_context_inputs(instrument: Any, as_of: Any, loaders: Any) -> None:
    with pytest.raises(TypeError):
        RadarEvaluationContext(instrument, as_of, loaders)


def test_key_immutable_and_reconstructible() -> None:
    key = RadarFactKey("a", int)
    assert key == RadarFactKey("a", int)
    assert hash(key) == hash(RadarFactKey("a", int))
    for name, value in (("fact_id", "b"), ("value_type", str)):
        with pytest.raises(FrozenInstanceError):
            setattr(key, name, value)


@pytest.mark.parametrize("identifier", ["", " ", "\n"])
def test_empty_key_rejected(identifier: str) -> None:
    with pytest.raises(ValueError, match="empty"):
        RadarFactKey(identifier, int)


@pytest.mark.parametrize(
    "identifier,value_type",
    [(1, int), ("a", list[int]), ("a", int | str), ("a", Any), ("a", "int")],
)
def test_invalid_key_types(identifier: Any, value_type: Any) -> None:
    with pytest.raises(TypeError):
        RadarFactKey(identifier, value_type)


def test_lazy_resolution_and_execution_local_success() -> None:
    a, b = RadarFactKey("a", object), RadarFactKey("b", str)
    value = object()
    loader_a, loader_b = Mock(return_value=value), Mock(return_value="b")
    wiring = {a: loader_a, b: loader_b}
    ctx = context(wiring)
    loader_a.assert_not_called()
    loader_b.assert_not_called()
    assert ctx.get_fact(a) is value
    assert ctx.get_fact(RadarFactKey("a", object)) is value
    loader_a.assert_called_once_with()
    loader_b.assert_not_called()
    assert ctx.get_fact(b) == "b"
    assert ctx.get_fact(b) == "b"
    loader_b.assert_called_once_with()
    other = context(wiring)
    assert other.get_fact(a) is value
    assert loader_a.call_count == 2


def test_failure_retained_without_disposition_or_retry() -> None:
    key = RadarFactKey("a", int)
    failure = RuntimeError("fake acquisition failure")
    loader = Mock(side_effect=failure)
    ctx = context({key: loader})
    for _ in range(2):
        with pytest.raises(RuntimeError) as caught:
            ctx.get_fact(key)
        assert caught.value is failure
    loader.assert_called_once_with()
    with pytest.raises(RuntimeError):
        context({key: loader}).get_fact(key)
    assert loader.call_count == 2


def test_unknown_and_incompatible_lookup_are_owned_errors() -> None:
    loader = Mock(return_value=1)
    ctx = context({RadarFactKey("a", int): loader})
    for key in (RadarFactKey("missing", int), RadarFactKey("a", str)):
        with pytest.raises(RadarContextError, match="Unconfigured"):
            ctx.get_fact(key)
    loader.assert_not_called()
    with pytest.raises(TypeError, match="RadarFactKey"):
        ctx.get_fact("a")  # type: ignore[arg-type]


def test_registry_detached_before_first_resolution() -> None:
    a, b = RadarFactKey("a", int), RadarFactKey("b", int)
    original = Mock(return_value=1)
    replacement = Mock(return_value=2)
    wiring = {a: original}
    ctx = context(wiring)
    wiring[a] = replacement
    wiring[b] = replacement
    assert ctx.get_fact(a) == 1
    with pytest.raises(RadarContextError):
        ctx.get_fact(b)
    replacement.assert_not_called()
    wiring.clear()
    assert ctx.get_fact(a) == 1
    original.assert_called_once_with()


@pytest.mark.parametrize(
    "value_type,value", [(int, 1), (bool, True), (str, "x"), (type(None), None)]
)
def test_exact_values_accepted(value_type: Any, value: object) -> None:
    key = RadarFactKey("a", value_type)
    loader = Mock(return_value=value)
    ctx = context({key: loader})
    assert ctx.get_fact(key) is value
    assert ctx.get_fact(key) is value
    loader.assert_called_once_with()


class IntSubclass(int):
    pass


@pytest.mark.parametrize(
    "value_type,value",
    [(int, True), (bool, 1), (int, "1"), (int, IntSubclass(1)), (object, 1)],
)
def test_incompatible_values_fail_once(value_type: Any, value: object) -> None:
    key = RadarFactKey("a", value_type)
    loader = Mock(return_value=value)
    ctx = context({key: loader})
    failures = []
    for _ in range(2):
        with pytest.raises(RadarContextError, match="exact type") as caught:
            ctx.get_fact(key)
        failures.append(caught.value)
    assert failures[0] is failures[1]
    loader.assert_called_once_with()


@pytest.mark.parametrize("reverse", [False, True])
def test_conflicting_registration_rejected_in_either_order(reverse: bool) -> None:
    loader = Mock()
    keys = [RadarFactKey("a", int), RadarFactKey("a", str)]
    if reverse:
        keys.reverse()
    with pytest.raises(RadarContextError, match="Conflicting"):
        context(dict.fromkeys(keys, loader))
    loader.assert_not_called()


def test_values_retained_by_reference_without_deep_freezing() -> None:
    key = RadarFactKey("a", list)
    value = [object()]
    ctx = context({key: lambda: value})
    assert ctx.get_fact(key) is value
    assert ctx.get_fact(key) is value


def test_recursive_resolution_does_not_reinvoke_loader() -> None:
    key = RadarFactKey("a", int)
    loader = Mock(side_effect=lambda: ctx.get_fact(key))
    ctx = context({key: loader})
    for _ in range(2):
        with pytest.raises(RadarContextError, match="Recursive"):
            ctx.get_fact(key)
    loader.assert_called_once_with()


def test_utc_timestamp_accepted() -> None:
    as_of = AS_OF.astimezone(UTC)
    assert RadarEvaluationContext(INSTRUMENT, as_of, {}).as_of is as_of
