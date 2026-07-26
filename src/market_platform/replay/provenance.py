"""Immutable replay execution identities and provenance."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

from market_platform._fingerprint import canonical_fingerprint
from market_platform.replay.models import HistoricalReplayResult, ReplayStrategyIdentity
from market_platform.replay.specification import HistoricalReplaySpecification
from market_platform.signals.service import (
    DEFAULT_ANNUALIZATION_FACTOR,
    DEFAULT_DISTANCE_FROM_MA_WINDOW,
    DEFAULT_MOMENTUM_WINDOW,
    DEFAULT_REALIZED_VOLATILITY_WINDOW,
    DEFAULT_TREND_LONG_WINDOW,
    DEFAULT_TREND_SHORT_WINDOW,
)
from market_platform.structure.models import PriceStructureConfig

_FINGERPRINT_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_PROVENANCE_SCHEMA_VERSION = "1.0.0"
_RUN_FINGERPRINT_SCHEMA_VERSION = "historical_replay_run/v1"


@dataclass(frozen=True, slots=True)
class ReplaySignalDerivationIdentity:
    """Stable identity for the signal derivation used by replay."""

    methodology: str
    version: str
    configuration_fingerprint: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "methodology",
            _normalize_required_text(self.methodology, "methodology"),
        )
        object.__setattr__(
            self,
            "version",
            _normalize_required_text(self.version, "version"),
        )
        object.__setattr__(
            self,
            "configuration_fingerprint",
            _normalize_fingerprint(
                self.configuration_fingerprint,
                "configuration_fingerprint",
            ),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "methodology": self.methodology,
            "version": self.version,
            "configuration_fingerprint": self.configuration_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class ReplayStructureDerivationIdentity:
    """Stable identity for the price-structure derivation used by replay."""

    methodology: str
    version: str
    configuration_fingerprint: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "methodology",
            _normalize_required_text(self.methodology, "methodology"),
        )
        object.__setattr__(
            self,
            "version",
            _normalize_required_text(self.version, "version"),
        )
        object.__setattr__(
            self,
            "configuration_fingerprint",
            _normalize_fingerprint(
                self.configuration_fingerprint,
                "configuration_fingerprint",
            ),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "methodology": self.methodology,
            "version": self.version,
            "configuration_fingerprint": self.configuration_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class SoftwareRevision:
    """Caller-supplied identity of the software that executed replay."""

    revision: str
    dirty: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "revision",
            _normalize_required_text(self.revision, "revision"),
        )
        if not isinstance(self.dirty, bool):
            raise TypeError("dirty must be a bool")

    def to_dict(self) -> dict[str, object]:
        return {"revision": self.revision, "dirty": self.dirty}


def default_replay_signal_derivation_identity() -> ReplaySignalDerivationIdentity:
    """Return the identity of the built-in replay signal derivation."""

    configuration_fingerprint = canonical_fingerprint(
        {
            "schema_version": "default_replay_signals_configuration/v1",
            "trend_short_window": DEFAULT_TREND_SHORT_WINDOW,
            "trend_long_window": DEFAULT_TREND_LONG_WINDOW,
            "momentum_window": DEFAULT_MOMENTUM_WINDOW,
            "realized_volatility_window": DEFAULT_REALIZED_VOLATILITY_WINDOW,
            "annualization_factor": DEFAULT_ANNUALIZATION_FACTOR,
            "realized_volatility_return_type": "log",
            "current_drawdown_reference": "highest_close_to_latest_timestamp",
            "distance_from_moving_average_window": DEFAULT_DISTANCE_FROM_MA_WINDOW,
        }
    )
    return ReplaySignalDerivationIdentity(
        methodology="default_market_signal_snapshots",
        version="1.0.0",
        configuration_fingerprint=configuration_fingerprint,
    )


def default_replay_structure_derivation_identity(
    config: PriceStructureConfig | None = None,
) -> ReplayStructureDerivationIdentity:
    """Return the identity of the built-in replay structure derivation."""

    effective = PriceStructureConfig() if config is None else config
    if not isinstance(effective, PriceStructureConfig):
        raise TypeError("config must be a PriceStructureConfig or None")
    configuration_fingerprint = canonical_fingerprint(
        {
            "schema_version": "default_replay_structure_configuration/v1",
            "pivot_window": effective.pivot_window,
            "atr_period": effective.atr_period,
            "zone_atr_multiplier": effective.zone_atr_multiplier,
        }
    )
    return ReplayStructureDerivationIdentity(
        methodology="default_price_structure_snapshots",
        version="1.0.0",
        configuration_fingerprint=configuration_fingerprint,
    )


@dataclass(frozen=True, slots=True)
class HistoricalReplayRunProvenance:
    """Canonical requested and resolved facts for one replay execution."""

    specification: HistoricalReplaySpecification
    specification_fingerprint: str
    dataset_content_fingerprint: str
    provider: str
    context_start: datetime
    context_end: datetime
    context_row_count: int
    evaluation_start: datetime
    evaluation_end: datetime
    evaluation_step_count: int
    signal_derivation: ReplaySignalDerivationIdentity
    structure_derivation: ReplayStructureDerivationIdentity
    state_model_id: str
    state_model_version: str
    state_model_configuration_fingerprint: str | None
    strategies: tuple[ReplayStrategyIdentity, ...]
    software_revision: SoftwareRevision
    schema_version: str = field(init=False, default=_PROVENANCE_SCHEMA_VERSION)
    run_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.specification, HistoricalReplaySpecification):
            raise TypeError("specification must be a HistoricalReplaySpecification")
        specification_fingerprint = _normalize_fingerprint(
            self.specification_fingerprint,
            "specification_fingerprint",
        )
        if specification_fingerprint != self.specification.fingerprint:
            raise ValueError("specification_fingerprint must match specification")
        object.__setattr__(
            self,
            "specification_fingerprint",
            specification_fingerprint,
        )
        object.__setattr__(
            self,
            "dataset_content_fingerprint",
            _normalize_fingerprint(
                self.dataset_content_fingerprint,
                "dataset_content_fingerprint",
            ),
        )
        object.__setattr__(
            self,
            "provider",
            _normalize_required_text(self.provider, "provider"),
        )
        context_start = _normalize_timestamp(self.context_start, "context_start")
        context_end = _normalize_timestamp(self.context_end, "context_end")
        evaluation_start = _normalize_timestamp(
            self.evaluation_start,
            "evaluation_start",
        )
        evaluation_end = _normalize_timestamp(self.evaluation_end, "evaluation_end")
        if context_start > context_end:
            raise ValueError("context_start must not be later than context_end")
        if evaluation_start > evaluation_end:
            raise ValueError("evaluation_start must not be later than evaluation_end")
        if evaluation_start < context_start or evaluation_end > context_end:
            raise ValueError("actual evaluation must lie inside actual context")
        object.__setattr__(self, "context_start", context_start)
        object.__setattr__(self, "context_end", context_end)
        object.__setattr__(self, "evaluation_start", evaluation_start)
        object.__setattr__(self, "evaluation_end", evaluation_end)
        object.__setattr__(
            self,
            "context_row_count",
            _normalize_positive_int(self.context_row_count, "context_row_count"),
        )
        object.__setattr__(
            self,
            "evaluation_step_count",
            _normalize_positive_int(
                self.evaluation_step_count,
                "evaluation_step_count",
            ),
        )
        if not isinstance(self.signal_derivation, ReplaySignalDerivationIdentity):
            raise TypeError(
                "signal_derivation must be a ReplaySignalDerivationIdentity"
            )
        if not isinstance(
            self.structure_derivation,
            ReplayStructureDerivationIdentity,
        ):
            raise TypeError(
                "structure_derivation must be a ReplayStructureDerivationIdentity"
            )
        object.__setattr__(
            self,
            "state_model_id",
            _normalize_required_text(self.state_model_id, "state_model_id"),
        )
        object.__setattr__(
            self,
            "state_model_version",
            _normalize_required_text(
                self.state_model_version,
                "state_model_version",
            ),
        )
        if self.state_model_configuration_fingerprint is not None:
            object.__setattr__(
                self,
                "state_model_configuration_fingerprint",
                _normalize_fingerprint(
                    self.state_model_configuration_fingerprint,
                    "state_model_configuration_fingerprint",
                ),
            )
        object.__setattr__(self, "strategies", _normalize_strategies(self.strategies))
        if not isinstance(self.software_revision, SoftwareRevision):
            raise TypeError("software_revision must be a SoftwareRevision")
        object.__setattr__(
            self,
            "run_fingerprint",
            canonical_fingerprint(self._fingerprint_payload()),
        )

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "schema_version": _RUN_FINGERPRINT_SCHEMA_VERSION,
            "specification_fingerprint": self.specification_fingerprint,
            "dataset_content_fingerprint": self.dataset_content_fingerprint,
            "provider": self.provider,
            "actual_context": {
                "start": self.context_start.isoformat(),
                "end": self.context_end.isoformat(),
                "row_count": self.context_row_count,
            },
            "actual_evaluation": {
                "start": self.evaluation_start.isoformat(),
                "end": self.evaluation_end.isoformat(),
                "step_count": self.evaluation_step_count,
            },
            "signal_derivation": self.signal_derivation.to_dict(),
            "structure_derivation": self.structure_derivation.to_dict(),
            "state_model": {
                "model_id": self.state_model_id,
                "model_version": self.state_model_version,
                "configuration_fingerprint": (
                    self.state_model_configuration_fingerprint
                ),
            },
            "strategies": [strategy.to_dict() for strategy in self.strategies],
            "software_revision": self.software_revision.to_dict(),
        }

    def to_dict(self) -> dict[str, object]:
        """Return a deterministic JSON-compatible provenance representation."""

        payload = self._fingerprint_payload()
        payload["fingerprint_schema_version"] = payload.pop("schema_version")
        return {
            "schema_version": self.schema_version,
            "specification": self.specification.to_dict(),
            **payload,
            "run_fingerprint": self.run_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class HistoricalReplayExecution:
    """Replay result plus its deterministic execution provenance."""

    result: HistoricalReplayResult
    provenance: HistoricalReplayRunProvenance
    run_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.result, HistoricalReplayResult):
            raise TypeError("result must be a HistoricalReplayResult")
        if not isinstance(self.provenance, HistoricalReplayRunProvenance):
            raise TypeError("provenance must be a HistoricalReplayRunProvenance")
        specification = self.provenance.specification
        if self.result.symbol != specification.symbol:
            raise ValueError("result symbol must match provenance specification")
        if self.result.interval != specification.interval:
            raise ValueError("result interval must match provenance specification")
        if self.result.start_as_of != self.provenance.evaluation_start:
            raise ValueError("result start must match provenance evaluation start")
        if self.result.end_as_of != self.provenance.evaluation_end:
            raise ValueError("result end must match provenance evaluation end")
        if self.result.step_count != self.provenance.evaluation_step_count:
            raise ValueError("result step count must match provenance")
        if self.result.state_model_id != self.provenance.state_model_id:
            raise ValueError("result state model id must match provenance")
        if self.result.state_model_version != self.provenance.state_model_version:
            raise ValueError("result state model version must match provenance")
        if self.result.strategies != self.provenance.strategies:
            raise ValueError("result strategies must match provenance")
        object.__setattr__(
            self,
            "run_fingerprint",
            self.provenance.run_fingerprint,
        )


def _normalize_required_text(value: object, field_name: str) -> str:
    if isinstance(value, bool) or not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _normalize_fingerprint(value: object, field_name: str) -> str:
    normalized = _normalize_required_text(value, field_name)
    if _FINGERPRINT_PATTERN.fullmatch(normalized) is None:
        raise ValueError(f"{field_name} must be a sha256 fingerprint")
    return normalized


def _normalize_timestamp(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _normalize_positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an int")
    if value <= 0:
        raise ValueError(f"{field_name} must be greater than 0")
    return value


def _normalize_strategies(value: object) -> tuple[ReplayStrategyIdentity, ...]:
    if isinstance(value, tuple):
        strategies = value
    elif isinstance(value, list):
        strategies = tuple(value)
    else:
        raise TypeError("strategies must be a tuple or list")
    for strategy in strategies:
        if not isinstance(strategy, ReplayStrategyIdentity):
            raise TypeError("strategies elements must be ReplayStrategyIdentity")
    return strategies


__all__ = [
    "HistoricalReplayExecution",
    "HistoricalReplayRunProvenance",
    "ReplaySignalDerivationIdentity",
    "ReplayStructureDerivationIdentity",
    "SoftwareRevision",
    "default_replay_signal_derivation_identity",
    "default_replay_structure_derivation_identity",
]
