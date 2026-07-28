"""Strict dictionary codec for historical Replay research requests."""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import datetime

from market_platform.application.errors import (
    HistoricalReplayResearchApplicationRequestError,
    UnsupportedApplicationSchemaError,
)
from market_platform.application.historical_replay_research import (
    HISTORICAL_REPLAY_RESEARCH_APPLICATION_REQUEST_SCHEMA_VERSION,
    HistoricalReplayResearchApplicationRequest,
    HistoricalReplayResearchInlineSourceRequest,
    HistoricalReplayResearchMemberRequest,
    HistoricalReplayResearchPriceRowRequest,
    HistoricalReplayResearchStateModelRequest,
    HistoricalReplayResearchStrategyRequest,
    _freeze_passive_json_mapping,
)
from market_platform.replay import (
    HistoricalReplaySpecification,
    ReplayStructureDerivationIdentity,
    SoftwareRevision,
)


def decode_historical_replay_research_application_request(
    payload: Mapping[str, object],
) -> HistoricalReplayResearchApplicationRequest:
    """Strictly decode one versioned request dictionary."""

    try:
        root = _object(
            payload,
            "request",
            {
                "schema_version",
                "source",
                "baseline",
                "candidates",
                "replay_software_revision",
                "comparison_software_revision",
                "workflow_software_revision",
            },
        )
        schema = _string(root["schema_version"], "request.schema_version")
        if schema != HISTORICAL_REPLAY_RESEARCH_APPLICATION_REQUEST_SCHEMA_VERSION:
            raise UnsupportedApplicationSchemaError(
                f"unsupported application request schema: {schema}"
            )
        return HistoricalReplayResearchApplicationRequest(
            source=_source(root["source"], "request.source"),
            baseline=_member(root["baseline"], "request.baseline"),
            candidates=tuple(
                _member(item, f"request.candidates[{index}]")
                for index, item in enumerate(
                    _array(root["candidates"], "request.candidates")
                )
            ),
            replay_software_revision=_revision(
                root["replay_software_revision"],
                "request.replay_software_revision",
            ),
            comparison_software_revision=_revision(
                root["comparison_software_revision"],
                "request.comparison_software_revision",
            ),
            workflow_software_revision=_revision(
                root["workflow_software_revision"],
                "request.workflow_software_revision",
            ),
        )
    except (
        HistoricalReplayResearchApplicationRequestError,
        UnsupportedApplicationSchemaError,
    ):
        raise
    except (TypeError, ValueError) as exc:
        raise HistoricalReplayResearchApplicationRequestError(str(exc)) from exc


def _source(
    payload: object,
    path: str,
) -> HistoricalReplayResearchInlineSourceRequest:
    value = _object(payload, path, {"symbol", "interval", "provider", "rows"})
    return HistoricalReplayResearchInlineSourceRequest(
        symbol=_string(value["symbol"], f"{path}.symbol"),
        interval=_string(value["interval"], f"{path}.interval"),
        provider=_string(value["provider"], f"{path}.provider"),
        rows=tuple(
            _row(item, f"{path}.rows[{index}]")
            for index, item in enumerate(_array(value["rows"], f"{path}.rows"))
        ),
    )


def _row(
    payload: object,
    path: str,
) -> HistoricalReplayResearchPriceRowRequest:
    value = _object(
        payload,
        path,
        {"timestamp", "open", "high", "low", "close", "volume"},
    )
    return HistoricalReplayResearchPriceRowRequest(
        timestamp=_timestamp(value["timestamp"], f"{path}.timestamp"),
        open=_number(value["open"], f"{path}.open"),
        high=_number(value["high"], f"{path}.high"),
        low=_number(value["low"], f"{path}.low"),
        close=_number(value["close"], f"{path}.close"),
        volume=_number(value["volume"], f"{path}.volume"),
    )


def _member(
    payload: object,
    path: str,
) -> HistoricalReplayResearchMemberRequest:
    value = _object(
        payload,
        path,
        {
            "replay_specification",
            "strategies",
            "state_model",
            "structure_derivation",
        },
    )
    return HistoricalReplayResearchMemberRequest(
        replay_specification=_replay_specification(
            value["replay_specification"],
            f"{path}.replay_specification",
        ),
        strategies=tuple(
            _strategy(item, f"{path}.strategies[{index}]")
            for index, item in enumerate(
                _array(value["strategies"], f"{path}.strategies")
            )
        ),
        state_model=_state_model(
            value["state_model"],
            f"{path}.state_model",
        ),
        structure_derivation=_structure(
            value["structure_derivation"],
            f"{path}.structure_derivation",
        ),
    )


def _replay_specification(
    payload: object,
    path: str,
) -> HistoricalReplaySpecification:
    value = _object(
        payload,
        path,
        {
            "symbol",
            "interval",
            "context_start",
            "evaluation_start",
            "evaluation_end",
        },
    )
    return HistoricalReplaySpecification(
        symbol=_string(value["symbol"], f"{path}.symbol"),
        interval=_string(value["interval"], f"{path}.interval"),
        context_start=_timestamp(value["context_start"], f"{path}.context_start"),
        evaluation_start=_timestamp(
            value["evaluation_start"],
            f"{path}.evaluation_start",
        ),
        evaluation_end=_timestamp(
            value["evaluation_end"],
            f"{path}.evaluation_end",
        ),
    )


def _strategy(
    payload: object,
    path: str,
) -> HistoricalReplayResearchStrategyRequest:
    value = _object(
        payload,
        path,
        {"strategy_id", "strategy_version", "configuration"},
    )
    return HistoricalReplayResearchStrategyRequest(
        strategy_id=_string(value["strategy_id"], f"{path}.strategy_id"),
        strategy_version=_string(
            value["strategy_version"],
            f"{path}.strategy_version",
        ),
        configuration=_json_mapping(
            value["configuration"],
            f"{path}.configuration",
        ),
    )


def _state_model(
    payload: object,
    path: str,
) -> HistoricalReplayResearchStateModelRequest:
    value = _object(
        payload,
        path,
        {
            "model_id",
            "model_version",
            "configuration",
            "expected_configuration_fingerprint",
        },
    )
    fingerprint = value["expected_configuration_fingerprint"]
    if fingerprint is not None:
        fingerprint = _string(
            fingerprint,
            f"{path}.expected_configuration_fingerprint",
        )
    return HistoricalReplayResearchStateModelRequest(
        model_id=_string(value["model_id"], f"{path}.model_id"),
        model_version=_string(value["model_version"], f"{path}.model_version"),
        configuration=_json_mapping(
            value["configuration"],
            f"{path}.configuration",
        ),
        expected_configuration_fingerprint=fingerprint,
    )


def _structure(
    payload: object,
    path: str,
) -> ReplayStructureDerivationIdentity:
    value = _object(
        payload,
        path,
        {"methodology", "version", "configuration_fingerprint"},
    )
    return ReplayStructureDerivationIdentity(
        methodology=_string(value["methodology"], f"{path}.methodology"),
        version=_string(value["version"], f"{path}.version"),
        configuration_fingerprint=_string(
            value["configuration_fingerprint"],
            f"{path}.configuration_fingerprint",
        ),
    )


def _revision(payload: object, path: str) -> SoftwareRevision:
    value = _object(payload, path, {"revision", "dirty"})
    dirty = value["dirty"]
    if not isinstance(dirty, bool):
        raise HistoricalReplayResearchApplicationRequestError(
            f"{path}.dirty must be a bool"
        )
    return SoftwareRevision(
        revision=_string(value["revision"], f"{path}.revision"),
        dirty=dirty,
    )


def _object(
    payload: object,
    path: str,
    expected_keys: set[str],
) -> Mapping[str, object]:
    if not isinstance(payload, Mapping):
        raise HistoricalReplayResearchApplicationRequestError(
            f"{path} must be an object"
        )
    actual_keys = set(payload)
    if any(not isinstance(key, str) for key in actual_keys):
        raise HistoricalReplayResearchApplicationRequestError(
            f"{path} keys must be strings"
        )
    missing = expected_keys - actual_keys
    unknown = actual_keys - expected_keys
    if missing:
        raise HistoricalReplayResearchApplicationRequestError(
            f"{path} missing fields: {', '.join(sorted(missing))}"
        )
    if unknown:
        raise HistoricalReplayResearchApplicationRequestError(
            f"{path} contains unknown fields: {', '.join(sorted(unknown))}"
        )
    return payload


def _array(payload: object, path: str) -> list[object]:
    if not isinstance(payload, list):
        raise HistoricalReplayResearchApplicationRequestError(
            f"{path} must be an array"
        )
    return payload


def _string(payload: object, path: str) -> str:
    if isinstance(payload, bool) or not isinstance(payload, str):
        raise HistoricalReplayResearchApplicationRequestError(
            f"{path} must be a string"
        )
    return payload


def _number(payload: object, path: str) -> int | float:
    if type(payload) is int:
        return payload
    if type(payload) is not float:
        raise HistoricalReplayResearchApplicationRequestError(
            f"{path} must be a number"
        )
    if not math.isfinite(payload):
        raise HistoricalReplayResearchApplicationRequestError(
            f"{path} must be finite"
        )
    return payload


def _timestamp(payload: object, path: str) -> datetime:
    text = _string(payload, path)
    try:
        value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HistoricalReplayResearchApplicationRequestError(
            f"{path} must be an ISO-8601 timestamp"
        ) from exc
    if value.tzinfo is None:
        raise HistoricalReplayResearchApplicationRequestError(
            f"{path} must be timezone-aware"
        )
    return value


def _json_mapping(payload: object, path: str) -> dict[str, object]:
    return dict(_freeze_passive_json_mapping(payload, path))


__all__ = ["decode_historical_replay_research_application_request"]
