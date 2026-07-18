"""Immutable strategy configuration and deterministic identity."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType


@dataclass(frozen=True, slots=True)
class StrategyConfiguration:
    """Immutable identity and deeply frozen parameters for a strategy instance."""

    strategy_id: str
    strategy_version: str
    parameters: Mapping[str, object]
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        strategy_id = _normalize_required_text(self.strategy_id, "strategy_id")
        strategy_version = _normalize_required_text(
            self.strategy_version,
            "strategy_version",
        )
        parameters = _freeze_mapping(self.parameters)
        object.__setattr__(self, "strategy_id", strategy_id)
        object.__setattr__(self, "strategy_version", strategy_version)
        object.__setattr__(self, "parameters", parameters)
        object.__setattr__(
            self,
            "fingerprint",
            _configuration_fingerprint(
                strategy_id,
                strategy_version,
                parameters,
            ),
        )

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible configuration representation."""

        return {
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "parameters": _serialize_mapping(self.parameters),
            "fingerprint": self.fingerprint,
        }


def _configuration_fingerprint(
    strategy_id: str,
    strategy_version: str,
    parameters: Mapping[str, object],
) -> str:
    payload = {
        "parameters": _canonical_value(parameters),
        "strategy_id": strategy_id,
        "strategy_version": strategy_version,
    }
    canonical_json = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    digest = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _normalize_required_text(value: object, field_name: str) -> str:
    if isinstance(value, bool) or not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text


def _freeze_mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError("parameters must be a mapping")
    frozen: dict[str, object] = {}
    for raw_key, item in value.items():
        key = _normalize_required_text(raw_key, "parameters key")
        if key in frozen:
            raise ValueError("parameters keys must be unique after normalization")
        frozen[key] = _freeze_value(item)
    return MappingProxyType(frozen)


def _freeze_value(value: object) -> object:
    if isinstance(value, Mapping):
        return _freeze_mapping(value)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze_value(item) for item in value)
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("parameters numeric values must be finite")
        return value
    raise TypeError("parameters values must be JSON-compatible")


def _canonical_value(value: object) -> object:
    if isinstance(value, Mapping):
        return [
            "mapping",
            [
                [key, _canonical_value(value[key])]
                for key in sorted(value)
            ],
        ]
    if isinstance(value, tuple):
        return ["tuple", [_canonical_value(item) for item in value]]
    if isinstance(value, frozenset):
        items = [_canonical_value(item) for item in value]
        return ["set", sorted(items, key=_canonical_json)]
    if value is None:
        return ["none", None]
    if isinstance(value, bool):
        return ["bool", value]
    if isinstance(value, int):
        return ["int", value]
    if isinstance(value, float):
        return ["float", value]
    if isinstance(value, str):
        return ["str", value]
    raise TypeError("canonical value must be deeply frozen")


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _serialize_mapping(value: Mapping[str, object]) -> dict[str, object]:
    return {key: _serialize_value(value[key]) for key in sorted(value)}


def _serialize_value(value: object) -> object:
    if isinstance(value, Mapping):
        return _serialize_mapping(value)
    if isinstance(value, tuple):
        return [_serialize_value(item) for item in value]
    if isinstance(value, frozenset):
        items = [_serialize_value(item) for item in value]
        return sorted(items, key=_canonical_json)
    return value


__all__ = ["StrategyConfiguration"]
