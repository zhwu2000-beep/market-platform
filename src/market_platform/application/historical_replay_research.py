"""Immutable transport-neutral historical Replay research models."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import MappingProxyType

import pandas as pd

from market_platform._fingerprint import canonical_fingerprint
from market_platform.application.errors import (
    HistoricalReplayResearchApplicationRequestError,
)
from market_platform.data import HistoricalPriceSeries
from market_platform.replay import (
    HistoricalReplaySpecification,
    ReplayStructureDerivationIdentity,
    SoftwareRevision,
)
from market_platform.research import (
    HistoricalReplayResearchMemberSpecification,
    HistoricalReplayResearchWorkflowResult,
    HistoricalReplayResearchWorkflowSpecification,
    HistoricalReplayResearchWorkflowStatus,
)
from market_platform.research.historical_replay_workflow import (
    HISTORICAL_REPLAY_RESEARCH_MEMBER_SCHEMA_VERSION,
    HISTORICAL_REPLAY_RESEARCH_WORKFLOW_POLICY_VERSION,
    HISTORICAL_REPLAY_RESEARCH_WORKFLOW_SCHEMA_VERSION,
)
from market_platform.strategy import StrategyConfiguration

HISTORICAL_REPLAY_RESEARCH_APPLICATION_REQUEST_SCHEMA_VERSION = (
    "historical_replay_research_application_request/v1"
)
HISTORICAL_REPLAY_RESEARCH_APPLICATION_RESPONSE_SCHEMA_VERSION = (
    "historical_replay_research_application_response/v1"
)

_FINGERPRINT_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class HistoricalReplayResearchPriceRowRequest:
    """One normalized inline OHLCV row."""

    timestamp: datetime
    open: int | float
    high: int | float
    low: int | float
    close: int | float
    volume: int | float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "timestamp",
            _aware_utc_timestamp(self.timestamp, "timestamp"),
        )
        for name in ("open", "high", "low", "close", "volume"):
            object.__setattr__(
                self,
                name,
                _finite_number(getattr(self, name), name),
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }


@dataclass(frozen=True, slots=True)
class HistoricalReplayResearchInlineSourceRequest:
    """Canonical inline historical source intent."""

    symbol: str
    interval: str
    provider: str
    rows: tuple[HistoricalReplayResearchPriceRowRequest, ...] = field(repr=False)

    def __post_init__(self) -> None:
        symbol = _required_text(self.symbol, "symbol").upper()
        interval = _required_text(self.interval, "interval")
        provider = _required_text(self.provider, "provider")
        if not isinstance(self.rows, tuple):
            raise TypeError("rows must be a tuple")
        if not self.rows:
            raise ValueError("rows must not be empty")
        for row in self.rows:
            if not isinstance(row, HistoricalReplayResearchPriceRowRequest):
                raise TypeError(
                    "rows elements must be HistoricalReplayResearchPriceRowRequest"
                )
        timestamps = tuple(row.timestamp for row in self.rows)
        if any(
            timestamps[index] <= timestamps[index - 1]
            for index in range(1, len(timestamps))
        ):
            raise ValueError(
                "rows timestamps must be strictly increasing after UTC normalization"
            )
        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "interval", interval)
        object.__setattr__(self, "provider", provider)

    @property
    def row_count(self) -> int:
        return len(self.rows)

    def to_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "interval": self.interval,
            "provider": self.provider,
            "rows": [row.to_dict() for row in self.rows],
        }


@dataclass(frozen=True, slots=True)
class HistoricalReplayResearchStrategyRequest:
    """Serializable request for one configured strategy instance."""

    strategy_id: str
    strategy_version: str
    configuration: Mapping[str, object] = field(hash=False, repr=False)
    configuration_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        configuration = _freeze_passive_json_mapping(
            self.configuration,
            "configuration",
        )
        normalized = StrategyConfiguration(
            strategy_id=self.strategy_id,
            strategy_version=self.strategy_version,
            parameters=configuration,
        )
        object.__setattr__(self, "strategy_id", normalized.strategy_id)
        object.__setattr__(self, "strategy_version", normalized.strategy_version)
        object.__setattr__(self, "configuration", normalized.parameters)
        object.__setattr__(
            self,
            "configuration_fingerprint",
            normalized.fingerprint,
        )

    def to_dict(self) -> dict[str, object]:
        configuration = StrategyConfiguration(
            self.strategy_id,
            self.strategy_version,
            self.configuration,
        )
        return {
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "configuration": configuration.to_dict()["parameters"],
        }


@dataclass(frozen=True, slots=True)
class HistoricalReplayResearchStateModelRequest:
    """Serializable request for one state-model instance."""

    model_id: str
    model_version: str
    configuration: Mapping[str, object] = field(hash=False, repr=False)
    expected_configuration_fingerprint: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "model_id", _required_text(self.model_id, "model_id"))
        object.__setattr__(
            self,
            "model_version",
            _required_text(self.model_version, "model_version"),
        )
        object.__setattr__(
            self,
            "configuration",
            _freeze_passive_json_mapping(self.configuration, "configuration"),
        )
        object.__setattr__(
            self,
            "expected_configuration_fingerprint",
            _optional_fingerprint(
                self.expected_configuration_fingerprint,
                "expected_configuration_fingerprint",
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "model_id": self.model_id,
            "model_version": self.model_version,
            "configuration": _json_mapping(self.configuration),
            "expected_configuration_fingerprint": (
                self.expected_configuration_fingerprint
            ),
        }


@dataclass(frozen=True, slots=True)
class HistoricalReplayResearchMemberRequest:
    """Serializable application intent for one Replay member."""

    replay_specification: HistoricalReplaySpecification
    strategies: tuple[HistoricalReplayResearchStrategyRequest, ...] = field(repr=False)
    state_model: HistoricalReplayResearchStateModelRequest
    structure_derivation: ReplayStructureDerivationIdentity

    def __post_init__(self) -> None:
        if not isinstance(self.replay_specification, HistoricalReplaySpecification):
            raise TypeError(
                "replay_specification must be a HistoricalReplaySpecification"
            )
        if not isinstance(self.strategies, tuple):
            raise TypeError("strategies must be a tuple")
        for strategy in self.strategies:
            if not isinstance(strategy, HistoricalReplayResearchStrategyRequest):
                raise TypeError(
                    "strategies elements must be "
                    "HistoricalReplayResearchStrategyRequest"
                )
        if not isinstance(
            self.state_model,
            HistoricalReplayResearchStateModelRequest,
        ):
            raise TypeError(
                "state_model must be a HistoricalReplayResearchStateModelRequest"
            )
        if not isinstance(
            self.structure_derivation,
            ReplayStructureDerivationIdentity,
        ):
            raise TypeError(
                "structure_derivation must be a ReplayStructureDerivationIdentity"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "replay_specification": self.replay_specification.to_dict(),
            "strategies": [strategy.to_dict() for strategy in self.strategies],
            "state_model": self.state_model.to_dict(),
            "structure_derivation": self.structure_derivation.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class HistoricalReplayResearchApplicationRequest:
    """Complete normalized external intent for one historical workflow."""

    source: HistoricalReplayResearchInlineSourceRequest = field(repr=False)
    baseline: HistoricalReplayResearchMemberRequest = field(repr=False)
    candidates: tuple[HistoricalReplayResearchMemberRequest, ...] = field(repr=False)
    replay_software_revision: SoftwareRevision
    comparison_software_revision: SoftwareRevision
    workflow_software_revision: SoftwareRevision
    schema_version: str = field(
        init=False,
        default=HISTORICAL_REPLAY_RESEARCH_APPLICATION_REQUEST_SCHEMA_VERSION,
    )
    request_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.source, HistoricalReplayResearchInlineSourceRequest):
            raise TypeError(
                "source must be a HistoricalReplayResearchInlineSourceRequest"
            )
        if not isinstance(self.baseline, HistoricalReplayResearchMemberRequest):
            raise TypeError(
                "baseline must be a HistoricalReplayResearchMemberRequest"
            )
        if not isinstance(self.candidates, tuple):
            raise TypeError("candidates must be a tuple")
        for candidate in self.candidates:
            if not isinstance(candidate, HistoricalReplayResearchMemberRequest):
                raise TypeError(
                    "candidates elements must be "
                    "HistoricalReplayResearchMemberRequest"
                )
        for name, revision in (
            ("replay_software_revision", self.replay_software_revision),
            ("comparison_software_revision", self.comparison_software_revision),
            ("workflow_software_revision", self.workflow_software_revision),
        ):
            if not isinstance(revision, SoftwareRevision):
                raise TypeError(f"{name} must be a SoftwareRevision")
        for member in (self.baseline, *self.candidates):
            specification = member.replay_specification
            if specification.symbol != self.source.symbol:
                raise ValueError(
                    "member Replay specifications must match the source symbol"
                )
            if specification.interval != self.source.interval:
                raise ValueError(
                    "member Replay specifications must match the source interval"
                )
        object.__setattr__(
            self,
            "request_fingerprint",
            canonical_fingerprint(self._fingerprint_payload()),
        )

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, object],
    ) -> HistoricalReplayResearchApplicationRequest:
        """Strictly decode one application request dictionary."""

        from market_platform.application.historical_replay_research_codec import (
            decode_historical_replay_research_application_request,
        )

        return decode_historical_replay_research_application_request(payload)

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "schema_version": (
                HISTORICAL_REPLAY_RESEARCH_APPLICATION_REQUEST_SCHEMA_VERSION
            ),
            "source": {
                **self.source.to_dict(),
                "row_count": self.source.row_count,
            },
            "baseline": self.baseline.to_dict(),
            "candidates": [
                {
                    "candidate_index": index,
                    "member": candidate.to_dict(),
                }
                for index, candidate in enumerate(self.candidates)
            ],
            "replay_software_revision": self.replay_software_revision.to_dict(),
            "comparison_software_revision": (
                self.comparison_software_revision.to_dict()
            ),
            "workflow_software_revision": self.workflow_software_revision.to_dict(),
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "source": self.source.to_dict(),
            "baseline": self.baseline.to_dict(),
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "replay_software_revision": self.replay_software_revision.to_dict(),
            "comparison_software_revision": (
                self.comparison_software_revision.to_dict()
            ),
            "workflow_software_revision": self.workflow_software_revision.to_dict(),
        }


@dataclass(frozen=True, slots=True, init=False)
class HistoricalReplayResearchApplicationResponse:
    """Bounded application response retaining the complete domain result."""

    application_request_fingerprint: str
    workflow_result: HistoricalReplayResearchWorkflowResult = field(repr=False)
    schema_version: str

    def __init__(self) -> None:
        raise TypeError(
            "HistoricalReplayResearchApplicationResponse is created by "
            "HistoricalReplayResearchApplicationService.execute()"
        )

    @classmethod
    def _create(
        cls,
        request: HistoricalReplayResearchApplicationRequest,
        workflow_specification: HistoricalReplayResearchWorkflowSpecification,
        workflow_result: HistoricalReplayResearchWorkflowResult,
    ) -> HistoricalReplayResearchApplicationResponse:
        if not isinstance(request, HistoricalReplayResearchApplicationRequest):
            raise TypeError(
                "request must be a HistoricalReplayResearchApplicationRequest"
            )
        if not isinstance(
            workflow_specification,
            HistoricalReplayResearchWorkflowSpecification,
        ):
            raise TypeError(
                "workflow_specification must be a "
                "HistoricalReplayResearchWorkflowSpecification"
            )
        if not isinstance(
            workflow_result,
            HistoricalReplayResearchWorkflowResult,
        ):
            raise TypeError(
                "workflow_result must be a HistoricalReplayResearchWorkflowResult"
            )
        if workflow_result.specification is not workflow_specification:
            raise ValueError(
                "workflow result must own the exact executed specification"
            )
        _validate_request_matches_resolved_workflow_specification(
            request,
            workflow_specification,
        )
        instance = cls.__new__(cls)
        object.__setattr__(
            instance,
            "application_request_fingerprint",
            request.request_fingerprint,
        )
        object.__setattr__(instance, "workflow_result", workflow_result)
        object.__setattr__(
            instance,
            "schema_version",
            HISTORICAL_REPLAY_RESEARCH_APPLICATION_RESPONSE_SCHEMA_VERSION,
        )
        return instance

    @property
    def workflow_specification_fingerprint(self) -> str:
        return (
            self.workflow_result.specification.workflow_specification_fingerprint
        )

    @property
    def workflow_result_fingerprint(self) -> str:
        return self.workflow_result.workflow_result_fingerprint

    @property
    def status(self) -> HistoricalReplayResearchWorkflowStatus:
        return self.workflow_result.status

    def to_dict(self) -> dict[str, object]:
        result = self.workflow_result
        baseline_artifact = result.baseline_artifact
        baseline_status = (
            "succeeded" if baseline_artifact is not None else "failed"
        )
        experiment = result.experiment
        experiment_summary: dict[str, object] | None = None
        if experiment is not None:
            experiment_summary = {
                "experiment_fingerprint": experiment.experiment_fingerprint,
                "comparisons": [
                    {
                        "candidate_index": comparison.candidate_index,
                        "comparison_fingerprint": (
                            comparison.comparison_fingerprint
                        ),
                        "compatible": comparison.compatibility.compatible,
                        "reasons": [
                            reason.value
                            for reason in comparison.compatibility.reasons
                        ],
                    }
                    for comparison in experiment.comparisons
                ],
            }
        return {
            "schema_version": self.schema_version,
            "application_request_fingerprint": (
                self.application_request_fingerprint
            ),
            "workflow_specification_fingerprint": (
                self.workflow_specification_fingerprint
            ),
            "workflow_result_fingerprint": self.workflow_result_fingerprint,
            "workflow_status": result.status.value,
            "steps": [step.to_dict() for step in result.steps],
            "baseline": {
                "status": baseline_status,
                "member_specification_fingerprint": (
                    result.specification.baseline.member_fingerprint
                ),
                "run_fingerprint": (
                    baseline_artifact.execution.run_fingerprint
                    if baseline_artifact is not None
                    else None
                ),
                "result_fingerprint": (
                    baseline_artifact.result_fingerprint
                    if baseline_artifact is not None
                    else None
                ),
                "failure_code": (
                    result.baseline_failure_code.value
                    if result.baseline_failure_code is not None
                    else None
                ),
            },
            "candidates": [
                {
                    "candidate_index": candidate.candidate_index,
                    "status": candidate.replay_status.value,
                    "member_specification_fingerprint": (
                        candidate.member_specification_fingerprint
                    ),
                    "run_fingerprint": (
                        candidate.artifact.execution.run_fingerprint
                        if candidate.artifact is not None
                        else None
                    ),
                    "result_fingerprint": (
                        candidate.artifact.result_fingerprint
                        if candidate.artifact is not None
                        else None
                    ),
                    "failure_code": (
                        candidate.failure_code.value
                        if candidate.failure_code is not None
                        else None
                    ),
                    "skip_reason": (
                        candidate.skip_reason.value
                        if candidate.skip_reason is not None
                        else None
                    ),
                }
                for candidate in result.candidates
            ],
            "experiment": experiment_summary,
        }


def _required_text(value: object, field_name: str) -> str:
    if isinstance(value, bool) or not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text


def _aware_utc_timestamp(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _finite_number(value: object, field_name: str) -> int | float:
    if type(value) is int:
        return value
    if type(value) is not float:
        raise TypeError(f"{field_name} must be an int or float")
    if not math.isfinite(value):
        raise ValueError(f"{field_name} must be finite")
    return value


def _optional_fingerprint(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or _FINGERPRINT_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a sha256 fingerprint or None")
    return value


def _freeze_passive_json_mapping(
    value: object,
    field_name: str,
) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise HistoricalReplayResearchApplicationRequestError(
            f"{field_name} must be a mapping"
        )
    frozen: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip():
            raise HistoricalReplayResearchApplicationRequestError(
                f"{field_name} keys must be nonempty strings"
            )
        normalized_key = key.strip()
        if normalized_key in frozen:
            raise HistoricalReplayResearchApplicationRequestError(
                f"{field_name} keys must be unique after normalization"
            )
        frozen[normalized_key] = _freeze_passive_json_value(
            item,
            f"{field_name}.{normalized_key}",
        )
    return MappingProxyType(frozen)


def _freeze_passive_json_value(value: object, field_name: str) -> object:
    if isinstance(value, Mapping):
        return _freeze_passive_json_mapping(value, field_name)
    if isinstance(value, (list, tuple)):
        return tuple(
            _freeze_passive_json_value(item, f"{field_name}[{index}]")
            for index, item in enumerate(value)
        )
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise HistoricalReplayResearchApplicationRequestError(
                f"{field_name} numeric values must be finite"
            )
        return value
    raise HistoricalReplayResearchApplicationRequestError(
        f"{field_name} values must be passive JSON-safe data"
    )


def _json_mapping(value: Mapping[str, object]) -> dict[str, object]:
    return {key: _json_value(value[key]) for key in sorted(value)}


def _json_value(value: object) -> object:
    if isinstance(value, Mapping):
        return _json_mapping(value)
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    return value


def _historical_price_series_from_request(
    request: HistoricalReplayResearchApplicationRequest,
) -> HistoricalPriceSeries:
    source = request.source
    return HistoricalPriceSeries(
        pd.DataFrame(
            [
                {
                    "symbol": source.symbol,
                    "timestamp": row.timestamp,
                    "open": row.open,
                    "high": row.high,
                    "low": row.low,
                    "close": row.close,
                    "volume": row.volume,
                    "provider": source.provider,
                }
                for row in source.rows
            ]
        ),
        symbol=source.symbol,
        provider=source.provider,
    )


def _validate_request_matches_resolved_workflow_specification(
    request: HistoricalReplayResearchApplicationRequest,
    specification: HistoricalReplayResearchWorkflowSpecification,
) -> None:
    expected_source = _historical_price_series_from_request(request)
    if (
        specification.schema_version
        != HISTORICAL_REPLAY_RESEARCH_WORKFLOW_SCHEMA_VERSION
        or specification.policy_version
        != HISTORICAL_REPLAY_RESEARCH_WORKFLOW_POLICY_VERSION
        or specification.source_symbol != request.source.symbol
        or specification.source_interval != request.source.interval
        or specification.source_provider != request.source.provider
        or specification.source_row_count != request.source.row_count
        or specification.source_content_fingerprint
        != expected_source.content_fingerprint
        or not specification.source.to_dataframe().equals(
            expected_source.to_dataframe()
        )
        or specification.replay_software_revision
        != request.replay_software_revision
        or specification.comparison_software_revision
        != request.comparison_software_revision
        or specification.workflow_software_revision
        != request.workflow_software_revision
    ):
        raise ValueError("workflow specification does not match request")

    requested_members = (request.baseline, *request.candidates)
    resolved_members = (specification.baseline, *specification.candidates)
    if len(requested_members) != len(resolved_members):
        raise ValueError("workflow specification does not match request")
    for requested, resolved in zip(
        requested_members,
        resolved_members,
        strict=True,
    ):
        if _requested_member_projection(requested) != (
            _resolved_member_projection(resolved)
        ):
            raise ValueError("workflow specification does not match request")


def _requested_member_projection(
    member: HistoricalReplayResearchMemberRequest,
) -> dict[str, object]:
    return {
        "schema_version": HISTORICAL_REPLAY_RESEARCH_MEMBER_SCHEMA_VERSION,
        "replay_specification": member.replay_specification.to_dict(),
        "state_model": {
            "model_id": member.state_model.model_id,
            "model_version": member.state_model.model_version,
            "configuration_fingerprint": (
                member.state_model.expected_configuration_fingerprint
            ),
        },
        "structure_derivation": member.structure_derivation.to_dict(),
        "strategies": [
            {
                "strategy_id": strategy.strategy_id,
                "strategy_version": strategy.strategy_version,
                "configuration_fingerprint": strategy.configuration_fingerprint,
            }
            for strategy in member.strategies
        ],
    }


def _resolved_member_projection(
    member: HistoricalReplayResearchMemberSpecification,
) -> dict[str, object]:
    return {
        "schema_version": member.schema_version,
        "replay_specification": member.replay_specification.to_dict(),
        "state_model": {
            "model_id": member.state_model_id,
            "model_version": member.state_model_version,
            "configuration_fingerprint": (
                member.state_model_configuration_fingerprint
            ),
        },
        "structure_derivation": member.structure_derivation.to_dict(),
        "strategies": [
            identity.to_dict() for identity in member.strategy_identities
        ],
    }


__all__ = [
    "HISTORICAL_REPLAY_RESEARCH_APPLICATION_REQUEST_SCHEMA_VERSION",
    "HISTORICAL_REPLAY_RESEARCH_APPLICATION_RESPONSE_SCHEMA_VERSION",
    "HistoricalReplayResearchApplicationRequest",
    "HistoricalReplayResearchApplicationResponse",
    "HistoricalReplayResearchInlineSourceRequest",
    "HistoricalReplayResearchMemberRequest",
    "HistoricalReplayResearchPriceRowRequest",
    "HistoricalReplayResearchStateModelRequest",
    "HistoricalReplayResearchStrategyRequest",
]
