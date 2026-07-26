from __future__ import annotations

import pytest

from market_platform._fingerprint import canonical_fingerprint, canonical_float


def test_canonical_fingerprint_is_order_independent_and_versioned() -> None:
    left = {"schema_version": "test/v1", "nested": {"b": 2, "a": [1, 2]}}
    right = {"nested": {"a": [1, 2], "b": 2}, "schema_version": "test/v1"}

    assert canonical_fingerprint(left) == canonical_fingerprint(right)
    assert canonical_fingerprint(left).startswith("sha256:")


def test_canonical_fingerprint_rejects_unversioned_or_unsupported_values() -> None:
    with pytest.raises(ValueError, match="schema_version"):
        canonical_fingerprint({"value": 1})
    with pytest.raises(TypeError, match="canonical values"):
        canonical_fingerprint({"schema_version": "test/v1", "value": {1, 2}})
    with pytest.raises(ValueError, match="finite"):
        canonical_fingerprint(
            {"schema_version": "test/v1", "value": float("nan")}
        )


@pytest.mark.parametrize("value", [0, 0.0, -0.0])
def test_canonical_float_normalizes_all_zero_values(value: float) -> None:
    assert canonical_float(value) == "0.0"


@pytest.mark.parametrize("value", [True, False])
def test_canonical_float_rejects_booleans(value: bool) -> None:
    with pytest.raises(TypeError, match="must not be a bool"):
        canonical_float(value)


def test_canonical_float_preserves_nonzero_value_identity() -> None:
    assert canonical_float(1.5) == repr(1.5)
    assert canonical_float(-1.5) == repr(-1.5)
    assert canonical_float(1.5) != canonical_float(-1.5)
    assert canonical_float(1.5) != canonical_float(2.5)


@pytest.mark.parametrize(
    "value",
    [float("nan"), float("inf"), float("-inf")],
)
def test_canonical_float_rejects_nonfinite_values(value: float) -> None:
    with pytest.raises(ValueError, match="must be finite"):
        canonical_float(value)
