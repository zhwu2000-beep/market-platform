"""Narrow canonical fingerprint support for versioned platform identities."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence


def canonical_fingerprint(payload: Mapping[str, object]) -> str:
    """Return a versioned compact-JSON SHA-256 fingerprint."""

    schema_version = payload.get("schema_version")
    if not isinstance(schema_version, str) or not schema_version.strip():
        raise ValueError("fingerprint payload must contain a schema_version")
    canonical_json = json.dumps(
        _canonical_value(payload),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    digest = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def canonical_float(value: float) -> str:
    """Return the locale-independent representation of a canonical float."""

    if isinstance(value, bool):
        raise TypeError("canonical float must not be a bool")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError("canonical float must be finite")
    if numeric == 0.0:
        return "0.0"
    return repr(numeric)


def _canonical_value(value: object) -> object:
    if isinstance(value, Mapping):
        normalized: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise TypeError("canonical mapping keys must be nonempty strings")
            normalized[key] = _canonical_value(item)
        return normalized
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        return [_canonical_value(item) for item in value]
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("canonical numeric values must be finite")
        return value
    raise TypeError(
        "canonical values must be JSON scalars, mappings, lists, or tuples"
    )


__all__ = ["canonical_fingerprint", "canonical_float"]
