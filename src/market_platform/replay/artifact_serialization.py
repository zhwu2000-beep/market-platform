"""Strict v1 serialization for historical replay artifacts."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from market_platform._fingerprint import canonical_fingerprint, canonical_float
from market_platform.replay.artifact import (
    ARTIFACT_SCHEMA_VERSION,
    INTEGRITY_ALGORITHM,
    INTEGRITY_SCHEMA_VERSION,
    HistoricalReplayArtifactError,
    HistoricalReplayArtifactIntegrityError,
)
from market_platform.replay.models import (
    HistoricalReplayResult,
    HistoricalReplayStep,
    ReplayStrategyIdentity,
)
from market_platform.replay.provenance import (
    HistoricalReplayExecution,
    HistoricalReplayRunProvenance,
    ReplaySignalDerivationIdentity,
    ReplayStructureDerivationIdentity,
    SoftwareRevision,
)
from market_platform.replay.specification import HistoricalReplaySpecification
from market_platform.state import (
    DirectionalRegime,
    MarketState,
    MomentumRegime,
    StateClassificationThresholdEvidence,
    StateCompositeEvidence,
    StateEvaluationEvidence,
    StateModelProvenance,
    StateQuality,
    StateSignalEvidence,
    StateVolatilityEvidence,
    StructureState,
    TrendRegime,
    VolatilityRegime,
)
from market_platform.strategy import (
    StrategyEvaluation,
    StrategyEvaluationStatus,
    StrategyEvidence,
    StrategyEvidenceSource,
    StrategyEvidenceValue,
    StrategyProvenance,
    StrategyRunResult,
)

if TYPE_CHECKING:
    from market_platform.replay.artifact import HistoricalReplayArtifact

RESULT_SCHEMA_VERSION = "historical_replay_result/v1"
_PROVENANCE_SCHEMA_VERSION = "1.0.0"
_RUN_FINGERPRINT_SCHEMA_VERSION = "historical_replay_run/v1"
_FINGERPRINT_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


def serialize_historical_replay_result(
    result: HistoricalReplayResult,
) -> dict[str, object]:
    """Return the strict, typed v1 result payload."""

    if not isinstance(result, HistoricalReplayResult):
        raise TypeError("result must be a HistoricalReplayResult")
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "content": {
            "symbol": result.symbol,
            "interval": result.interval,
            "start_as_of": _optional_timestamp_to_text(result.start_as_of),
            "end_as_of": _optional_timestamp_to_text(result.end_as_of),
            "state_model_id": result.state_model_id,
            "state_model_version": result.state_model_version,
            "strategies": [
                _strategy_identity_to_dict(strategy)
                for strategy in result.strategies
            ],
            "steps": [_step_to_dict(step) for step in result.steps],
        },
    }


def deserialize_historical_replay_result(
    payload: object,
) -> HistoricalReplayResult:
    """Strictly reconstruct a replay result from its typed v1 payload."""

    outer = _object(payload, "result", {"schema_version", "content"})
    _expect_schema(
        outer["schema_version"],
        RESULT_SCHEMA_VERSION,
        "result schema",
    )
    content = _object(
        outer["content"],
        "result.content",
        {
            "symbol",
            "interval",
            "start_as_of",
            "end_as_of",
            "state_model_id",
            "state_model_version",
            "strategies",
            "steps",
        },
    )
    return HistoricalReplayResult(
        symbol=_string(content["symbol"], "result.content.symbol"),
        interval=_string(content["interval"], "result.content.interval"),
        start_as_of=_optional_timestamp(
            content["start_as_of"],
            "result.content.start_as_of",
        ),
        end_as_of=_optional_timestamp(
            content["end_as_of"],
            "result.content.end_as_of",
        ),
        state_model_id=_string(
            content["state_model_id"],
            "result.content.state_model_id",
        ),
        state_model_version=_string(
            content["state_model_version"],
            "result.content.state_model_version",
        ),
        strategies=tuple(
            _strategy_identity_from_dict(value, f"result.strategies[{index}]")
            for index, value in enumerate(
                _list(content["strategies"], "result.content.strategies")
            )
        ),
        steps=tuple(
            _step_from_dict(value, f"result.steps[{index}]")
            for index, value in enumerate(
                _list(content["steps"], "result.content.steps")
            )
        ),
    )


def historical_replay_result_fingerprint(
    result: HistoricalReplayResult,
) -> str:
    """Return the stable production identity of complete Replay result content."""

    return _result_payload_fingerprint(serialize_historical_replay_result(result))


def _result_payload_fingerprint(payload: Mapping[str, object]) -> str:
    return canonical_fingerprint(payload)


def historical_replay_artifact_integrity_checksum(
    execution: HistoricalReplayExecution,
    result_fingerprint: str,
) -> str:
    """Return the semantic checksum for an execution and result identity."""

    if not isinstance(execution, HistoricalReplayExecution):
        raise TypeError("execution must be a HistoricalReplayExecution")
    _fingerprint(result_fingerprint, "result_fingerprint")
    return _checksum_from_parts(
        execution={
            "provenance": _canonical_json_value(execution.provenance.to_dict()),
            "run_fingerprint": execution.run_fingerprint,
        },
        result=serialize_historical_replay_result(execution.result),
        result_fingerprint=result_fingerprint,
    )


def artifact_to_dict(artifact: HistoricalReplayArtifact) -> dict[str, object]:
    """Return the complete canonical artifact envelope."""

    execution = {
        "provenance": _canonical_json_value(
            artifact.execution.provenance.to_dict()
        ),
        "run_fingerprint": artifact.execution.run_fingerprint,
    }
    result = serialize_historical_replay_result(artifact.execution.result)
    return {
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "execution": execution,
        "result": result,
        "result_fingerprint": artifact.result_fingerprint,
        "integrity": {
            "schema_version": INTEGRITY_SCHEMA_VERSION,
            "algorithm": INTEGRITY_ALGORITHM,
            "checksum": artifact.integrity_checksum,
        },
    }


def artifact_from_dict(payload: Mapping[str, object]) -> HistoricalReplayArtifact:
    """Strictly reconstruct and verify a v1 historical replay artifact."""

    from market_platform.replay.artifact import HistoricalReplayArtifact

    try:
        root = _object(
            payload,
            "artifact",
            {
                "artifact_schema_version",
                "execution",
                "result",
                "result_fingerprint",
                "integrity",
            },
        )
        _expect_schema(
            root["artifact_schema_version"],
            ARTIFACT_SCHEMA_VERSION,
            "artifact schema",
        )
        execution_payload = _object(
            root["execution"],
            "artifact.execution",
            {"provenance", "run_fingerprint"},
        )
        result_payload = _object(
            root["result"],
            "artifact.result",
            {"schema_version", "content"},
        )
        _expect_schema(
            result_payload["schema_version"],
            RESULT_SCHEMA_VERSION,
            "result schema",
        )
        provenance_payload = _object(
            execution_payload["provenance"],
            "artifact.execution.provenance",
            {
                "schema_version",
                "specification",
                "fingerprint_schema_version",
                "specification_fingerprint",
                "dataset_content_fingerprint",
                "provider",
                "actual_context",
                "actual_evaluation",
                "signal_derivation",
                "structure_derivation",
                "state_model",
                "strategies",
                "software_revision",
                "run_fingerprint",
            },
        )
        _expect_schema(
            provenance_payload["schema_version"],
            _PROVENANCE_SCHEMA_VERSION,
            "provenance schema",
        )
        _expect_schema(
            provenance_payload["fingerprint_schema_version"],
            _RUN_FINGERPRINT_SCHEMA_VERSION,
            "run fingerprint schema",
        )
        integrity = _object(
            root["integrity"],
            "artifact.integrity",
            {"schema_version", "algorithm", "checksum"},
        )
        _expect_schema(
            integrity["schema_version"],
            INTEGRITY_SCHEMA_VERSION,
            "integrity schema",
        )
        if (
            _string(integrity["algorithm"], "artifact.integrity.algorithm")
            != INTEGRITY_ALGORITHM
        ):
            raise HistoricalReplayArtifactError(
                "artifact integrity algorithm must be sha256"
            )
        stored_checksum = _fingerprint(
            integrity["checksum"],
            "artifact.integrity.checksum",
        )
        stored_result_fingerprint = _fingerprint(
            root["result_fingerprint"],
            "artifact.result_fingerprint",
        )
        stored_run_fingerprint = _fingerprint(
            execution_payload["run_fingerprint"],
            "artifact.execution.run_fingerprint",
        )
        computed_checksum = _checksum_from_parts(
            execution=execution_payload,
            result=root["result"],
            result_fingerprint=stored_result_fingerprint,
        )
        if stored_checksum != computed_checksum:
            raise HistoricalReplayArtifactIntegrityError(
                "artifact integrity checksum does not match payload"
            )

        provenance = _provenance_from_dict(execution_payload["provenance"])
        if stored_run_fingerprint != provenance.run_fingerprint:
            raise HistoricalReplayArtifactIntegrityError(
                "artifact run fingerprint does not match provenance"
            )
        computed_result_fingerprint = _result_payload_fingerprint(result_payload)
        if stored_result_fingerprint != computed_result_fingerprint:
            raise HistoricalReplayArtifactIntegrityError(
                "artifact result fingerprint does not match result"
            )
        result = deserialize_historical_replay_result(root["result"])
        try:
            execution = HistoricalReplayExecution(
                result=result,
                provenance=provenance,
            )
        except (TypeError, ValueError) as exc:
            raise HistoricalReplayArtifactIntegrityError(
                "artifact execution is inconsistent with provenance"
            ) from exc
        artifact = HistoricalReplayArtifact.from_execution(execution)
        if artifact.integrity_checksum != stored_checksum:
            raise HistoricalReplayArtifactIntegrityError(
                "artifact checksum changed after reconstruction"
            )
        return artifact
    except HistoricalReplayArtifactError:
        raise
    except (TypeError, ValueError) as exc:
        raise HistoricalReplayArtifactError(
            "invalid historical replay artifact"
        ) from exc


def _checksum_from_parts(
    *,
    execution: object,
    result: object,
    result_fingerprint: str,
) -> str:
    return canonical_fingerprint(
        {
            "schema_version": INTEGRITY_SCHEMA_VERSION,
            "artifact": {
                "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
                "execution": _canonical_json_value(execution),
                "result": _canonical_json_value(result),
                "result_fingerprint": result_fingerprint,
                "integrity": {
                    "schema_version": INTEGRITY_SCHEMA_VERSION,
                    "algorithm": INTEGRITY_ALGORITHM,
                },
            },
        }
    )


def _step_to_dict(step: HistoricalReplayStep) -> dict[str, object]:
    return {
        "symbol": step.symbol,
        "interval": step.interval,
        "as_of": step.as_of.isoformat(),
        "observation_fingerprint": step.observation_fingerprint,
        "state": _canonical_json_value(step.state.to_dict()),
        "strategy_result": _strategy_run_result_to_dict(step.strategy_result),
    }


def _step_from_dict(payload: object, path: str) -> HistoricalReplayStep:
    value = _object(
        payload,
        path,
        {
            "symbol",
            "interval",
            "as_of",
            "observation_fingerprint",
            "state",
            "strategy_result",
        },
    )
    return HistoricalReplayStep(
        symbol=_string(value["symbol"], f"{path}.symbol"),
        interval=_string(value["interval"], f"{path}.interval"),
        as_of=_timestamp(value["as_of"], f"{path}.as_of"),
        observation_fingerprint=_string(
            value["observation_fingerprint"],
            f"{path}.observation_fingerprint",
        ),
        state=_market_state_from_dict(value["state"], f"{path}.state"),
        strategy_result=_strategy_run_result_from_dict(
            value["strategy_result"],
            f"{path}.strategy_result",
        ),
    )


def _strategy_identity_to_dict(
    identity: ReplayStrategyIdentity,
) -> dict[str, object]:
    return _canonical_json_mapping(identity.to_dict())


def _strategy_identity_from_dict(
    payload: object,
    path: str,
) -> ReplayStrategyIdentity:
    value = _object(
        payload,
        path,
        {
            "strategy_id",
            "strategy_version",
            "configuration_fingerprint",
        },
    )
    return ReplayStrategyIdentity(
        strategy_id=_string(value["strategy_id"], f"{path}.strategy_id"),
        strategy_version=_string(
            value["strategy_version"],
            f"{path}.strategy_version",
        ),
        configuration_fingerprint=_optional_string(
            value["configuration_fingerprint"],
            f"{path}.configuration_fingerprint",
        ),
    )


def _market_state_from_dict(payload: object, path: str) -> MarketState:
    value = _object(
        payload,
        path,
        {
            "symbol",
            "interval",
            "as_of",
            "provenance",
            "directional_regime",
            "trend_regime",
            "momentum_regime",
            "volatility_regime",
            "structure_state",
            "quality",
            "missing_inputs",
            "evaluation_evidence",
        },
    )
    evidence_payload = value["evaluation_evidence"]
    return MarketState(
        symbol=_string(value["symbol"], f"{path}.symbol"),
        interval=_string(value["interval"], f"{path}.interval"),
        as_of=_timestamp(value["as_of"], f"{path}.as_of"),
        provenance=_state_provenance_from_dict(
            value["provenance"],
            f"{path}.provenance",
        ),
        directional_regime=DirectionalRegime(
            _string(value["directional_regime"], f"{path}.directional_regime")
        ),
        trend_regime=TrendRegime(
            _string(value["trend_regime"], f"{path}.trend_regime")
        ),
        momentum_regime=MomentumRegime(
            _string(value["momentum_regime"], f"{path}.momentum_regime")
        ),
        volatility_regime=VolatilityRegime(
            _string(value["volatility_regime"], f"{path}.volatility_regime")
        ),
        structure_state=StructureState(
            _string(value["structure_state"], f"{path}.structure_state")
        ),
        quality=StateQuality(_string(value["quality"], f"{path}.quality")),
        missing_inputs=tuple(
            _string(item, f"{path}.missing_inputs[{index}]")
            for index, item in enumerate(
                _list(value["missing_inputs"], f"{path}.missing_inputs")
            )
        ),
        evaluation_evidence=(
            None
            if evidence_payload is None
            else _state_evaluation_evidence_from_dict(
                evidence_payload,
                f"{path}.evaluation_evidence",
            )
        ),
    )


def _state_provenance_from_dict(payload: object, path: str) -> StateModelProvenance:
    value = _object(
        payload,
        path,
        {
            "model_id",
            "model_version",
            "parameters",
            "observation_fingerprint",
        },
    )
    return StateModelProvenance(
        model_id=_string(value["model_id"], f"{path}.model_id"),
        model_version=_string(value["model_version"], f"{path}.model_version"),
        parameters=_json_mapping(value["parameters"], f"{path}.parameters"),
        observation_fingerprint=_optional_string(
            value["observation_fingerprint"],
            f"{path}.observation_fingerprint",
        ),
    )


def _state_evaluation_evidence_from_dict(
    payload: object,
    path: str,
) -> StateEvaluationEvidence:
    value = _object(
        payload,
        path,
        {"directional_components", "composite", "volatility"},
    )
    return StateEvaluationEvidence(
        directional_components=tuple(
            _state_signal_evidence_from_dict(item, f"{path}.components[{index}]")
            for index, item in enumerate(
                _list(
                    value["directional_components"],
                    f"{path}.directional_components",
                )
            )
        ),
        composite=_state_composite_evidence_from_dict(
            value["composite"],
            f"{path}.composite",
        ),
        volatility=_state_volatility_evidence_from_dict(
            value["volatility"],
            f"{path}.volatility",
        ),
    )


def _state_signal_evidence_from_dict(
    payload: object,
    path: str,
) -> StateSignalEvidence:
    value = _object(
        payload,
        path,
        {
            "name",
            "raw_value",
            "normalized_score",
            "normalization_scale",
            "configured_weight",
            "normalized_weight",
            "weighted_contribution",
            "interpreted_state",
            "methodology",
            "source_parameters",
        },
    )
    return StateSignalEvidence(
        name=_string(value["name"], f"{path}.name"),
        raw_value=_optional_number(value["raw_value"], f"{path}.raw_value"),
        normalized_score=_optional_number(
            value["normalized_score"],
            f"{path}.normalized_score",
        ),
        normalization_scale=_number(
            value["normalization_scale"],
            f"{path}.normalization_scale",
        ),
        configured_weight=_number(
            value["configured_weight"],
            f"{path}.configured_weight",
        ),
        normalized_weight=_optional_number(
            value["normalized_weight"],
            f"{path}.normalized_weight",
        ),
        weighted_contribution=_optional_number(
            value["weighted_contribution"],
            f"{path}.weighted_contribution",
        ),
        interpreted_state=_string(
            value["interpreted_state"],
            f"{path}.interpreted_state",
        ),
        methodology=_string(value["methodology"], f"{path}.methodology"),
        source_parameters=_json_mapping(
            value["source_parameters"],
            f"{path}.source_parameters",
        ),
    )


def _state_composite_evidence_from_dict(
    payload: object,
    path: str,
) -> StateCompositeEvidence:
    value = _object(
        payload,
        path,
        {
            "score",
            "classification",
            "methodology",
            "formula",
            "thresholds",
            "component_order",
            "included_signals",
            "missing_signals",
        },
    )
    thresholds_payload = _object(
        value["thresholds"],
        f"{path}.thresholds",
        {"strong_bearish", "bearish", "bullish", "strong_bullish"},
    )
    return StateCompositeEvidence(
        score=_optional_number(value["score"], f"{path}.score"),
        classification=_optional_string(
            value["classification"],
            f"{path}.classification",
        ),
        methodology=_string(value["methodology"], f"{path}.methodology"),
        formula=_string(value["formula"], f"{path}.formula"),
        thresholds=StateClassificationThresholdEvidence(
            strong_bearish=_number(
                thresholds_payload["strong_bearish"],
                f"{path}.thresholds.strong_bearish",
            ),
            bearish=_number(
                thresholds_payload["bearish"],
                f"{path}.thresholds.bearish",
            ),
            bullish=_number(
                thresholds_payload["bullish"],
                f"{path}.thresholds.bullish",
            ),
            strong_bullish=_number(
                thresholds_payload["strong_bullish"],
                f"{path}.thresholds.strong_bullish",
            ),
        ),
        component_order=_string_tuple(
            value["component_order"],
            f"{path}.component_order",
        ),
        included_signals=_string_tuple(
            value["included_signals"],
            f"{path}.included_signals",
        ),
        missing_signals=_string_tuple(
            value["missing_signals"],
            f"{path}.missing_signals",
        ),
    )


def _state_volatility_evidence_from_dict(
    payload: object,
    path: str,
) -> StateVolatilityEvidence:
    value = _object(
        payload,
        path,
        {"raw_value", "low_threshold", "high_threshold", "regime", "methodology"},
    )
    return StateVolatilityEvidence(
        raw_value=_optional_number(value["raw_value"], f"{path}.raw_value"),
        low_threshold=_number(
            value["low_threshold"],
            f"{path}.low_threshold",
        ),
        high_threshold=_number(
            value["high_threshold"],
            f"{path}.high_threshold",
        ),
        regime=VolatilityRegime(_string(value["regime"], f"{path}.regime")),
        methodology=_string(value["methodology"], f"{path}.methodology"),
    )


def _strategy_run_result_to_dict(
    result: StrategyRunResult,
) -> dict[str, object]:
    return {
        "symbol": result.symbol,
        "interval": result.interval,
        "as_of": result.as_of.isoformat(),
        "observation_fingerprint": result.observation_fingerprint,
        "state_model_id": result.state_model_id,
        "state_model_version": result.state_model_version,
        "evaluations": [
            _strategy_evaluation_to_dict(evaluation)
            for evaluation in result.evaluations
        ],
    }


def _strategy_run_result_from_dict(
    payload: object,
    path: str,
) -> StrategyRunResult:
    value = _object(
        payload,
        path,
        {
            "symbol",
            "interval",
            "as_of",
            "observation_fingerprint",
            "state_model_id",
            "state_model_version",
            "evaluations",
        },
    )
    return StrategyRunResult(
        symbol=_string(value["symbol"], f"{path}.symbol"),
        interval=_string(value["interval"], f"{path}.interval"),
        as_of=_timestamp(value["as_of"], f"{path}.as_of"),
        observation_fingerprint=_string(
            value["observation_fingerprint"],
            f"{path}.observation_fingerprint",
        ),
        state_model_id=_string(
            value["state_model_id"],
            f"{path}.state_model_id",
        ),
        state_model_version=_string(
            value["state_model_version"],
            f"{path}.state_model_version",
        ),
        evaluations=tuple(
            _strategy_evaluation_from_dict(item, f"{path}.evaluations[{index}]")
            for index, item in enumerate(
                _list(value["evaluations"], f"{path}.evaluations")
            )
        ),
    )


def _strategy_evaluation_to_dict(
    evaluation: StrategyEvaluation,
) -> dict[str, object]:
    return {
        "symbol": evaluation.symbol,
        "interval": evaluation.interval,
        "as_of": evaluation.as_of.isoformat(),
        "provenance": _canonical_json_value(evaluation.provenance.to_dict()),
        "status": evaluation.status.value,
        "rationale": evaluation.rationale,
        "required_inputs": list(evaluation.required_inputs),
        "missing_inputs": list(evaluation.missing_inputs),
        "evidence": [_strategy_evidence_to_dict(item) for item in evaluation.evidence],
    }


def _strategy_evaluation_from_dict(
    payload: object,
    path: str,
) -> StrategyEvaluation:
    value = _object(
        payload,
        path,
        {
            "symbol",
            "interval",
            "as_of",
            "provenance",
            "status",
            "rationale",
            "required_inputs",
            "missing_inputs",
            "evidence",
        },
    )
    return StrategyEvaluation(
        symbol=_string(value["symbol"], f"{path}.symbol"),
        interval=_string(value["interval"], f"{path}.interval"),
        as_of=_timestamp(value["as_of"], f"{path}.as_of"),
        provenance=_strategy_provenance_from_dict(
            value["provenance"],
            f"{path}.provenance",
        ),
        status=StrategyEvaluationStatus(
            _string(value["status"], f"{path}.status")
        ),
        rationale=_string(value["rationale"], f"{path}.rationale"),
        required_inputs=_string_tuple(
            value["required_inputs"],
            f"{path}.required_inputs",
        ),
        missing_inputs=_string_tuple(
            value["missing_inputs"],
            f"{path}.missing_inputs",
        ),
        evidence=tuple(
            _strategy_evidence_from_dict(item, f"{path}.evidence[{index}]")
            for index, item in enumerate(
                _list(value["evidence"], f"{path}.evidence")
            )
        ),
    )


def _strategy_provenance_from_dict(
    payload: object,
    path: str,
) -> StrategyProvenance:
    value = _object(
        payload,
        path,
        {
            "strategy_id",
            "strategy_version",
            "parameters",
            "observation_fingerprint",
            "state_model_id",
            "state_model_version",
            "configuration_fingerprint",
        },
    )
    return StrategyProvenance(
        strategy_id=_string(value["strategy_id"], f"{path}.strategy_id"),
        strategy_version=_string(
            value["strategy_version"],
            f"{path}.strategy_version",
        ),
        parameters=_json_mapping(value["parameters"], f"{path}.parameters"),
        observation_fingerprint=_optional_string(
            value["observation_fingerprint"],
            f"{path}.observation_fingerprint",
        ),
        state_model_id=_optional_string(
            value["state_model_id"],
            f"{path}.state_model_id",
        ),
        state_model_version=_optional_string(
            value["state_model_version"],
            f"{path}.state_model_version",
        ),
        configuration_fingerprint=_optional_string(
            value["configuration_fingerprint"],
            f"{path}.configuration_fingerprint",
        ),
    )


def _strategy_evidence_to_dict(evidence: StrategyEvidence) -> dict[str, object]:
    return {
        "source": evidence.source.value,
        "field": evidence.field,
        "observed_value": _typed_evidence_value_to_dict(evidence.observed_value),
        "rationale": evidence.rationale,
        "observed_at": _optional_timestamp_to_text(evidence.observed_at),
    }


def _strategy_evidence_from_dict(payload: object, path: str) -> StrategyEvidence:
    value = _object(
        payload,
        path,
        {"source", "field", "observed_value", "rationale", "observed_at"},
    )
    return StrategyEvidence(
        source=StrategyEvidenceSource(
            _string(value["source"], f"{path}.source")
        ),
        field=_string(value["field"], f"{path}.field"),
        observed_value=_typed_evidence_value_from_dict(
            value["observed_value"],
            f"{path}.observed_value",
        ),
        rationale=_string(value["rationale"], f"{path}.rationale"),
        observed_at=_optional_timestamp(
            value["observed_at"],
            f"{path}.observed_at",
        ),
    )


def _typed_evidence_value_to_dict(value: object) -> dict[str, object]:
    if value is None:
        return {"type": "null", "value": None}
    if isinstance(value, bool):
        return {"type": "boolean", "value": value}
    if isinstance(value, str):
        return {"type": "string", "value": value}
    if isinstance(value, int):
        return {"type": "integer", "value": value}
    if isinstance(value, float):
        return {"type": "float", "value": canonical_float(value)}
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("strategy evidence datetime must be timezone-aware")
        return {
            "type": "datetime",
            "value": value.astimezone(UTC).isoformat(),
        }
    raise TypeError("unsupported StrategyEvidence observed_value")


def _typed_evidence_value_from_dict(
    payload: object,
    path: str,
) -> StrategyEvidenceValue:
    value = _object(payload, path, {"type", "value"})
    value_type = _string(value["type"], f"{path}.type")
    raw = value["value"]
    if value_type == "null":
        if raw is not None:
            raise HistoricalReplayArtifactError(f"{path}.value must be null")
        return None
    if value_type == "boolean":
        return _boolean(raw, f"{path}.value")
    if value_type == "string":
        return _string(raw, f"{path}.value", allow_empty=True)
    if value_type == "integer":
        return _integer(raw, f"{path}.value")
    if value_type == "float":
        text = _string(raw, f"{path}.value")
        try:
            numeric = float(text)
        except ValueError as exc:
            raise HistoricalReplayArtifactError(
                f"{path}.value must be a canonical finite float"
            ) from exc
        if canonical_float(numeric) != text:
            raise HistoricalReplayArtifactError(
                f"{path}.value must be a canonical finite float"
            )
        return numeric
    if value_type == "datetime":
        return _timestamp(raw, f"{path}.value")
    raise HistoricalReplayArtifactError(
        f"{path}.type contains unsupported evidence type {value_type!r}"
    )


def _provenance_from_dict(payload: object) -> HistoricalReplayRunProvenance:
    value = _object(
        payload,
        "artifact.execution.provenance",
        {
            "schema_version",
            "specification",
            "fingerprint_schema_version",
            "specification_fingerprint",
            "dataset_content_fingerprint",
            "provider",
            "actual_context",
            "actual_evaluation",
            "signal_derivation",
            "structure_derivation",
            "state_model",
            "strategies",
            "software_revision",
            "run_fingerprint",
        },
    )
    _expect_schema(
        value["schema_version"],
        _PROVENANCE_SCHEMA_VERSION,
        "provenance schema",
    )
    _expect_schema(
        value["fingerprint_schema_version"],
        _RUN_FINGERPRINT_SCHEMA_VERSION,
        "run fingerprint schema",
    )
    specification = _specification_from_dict(value["specification"])
    specification_fingerprint = _fingerprint(
        value["specification_fingerprint"],
        "provenance.specification_fingerprint",
    )
    if specification_fingerprint != specification.fingerprint:
        raise HistoricalReplayArtifactIntegrityError(
            "stored specification fingerprint does not match specification"
        )
    context = _object(
        value["actual_context"],
        "provenance.actual_context",
        {"start", "end", "row_count"},
    )
    evaluation = _object(
        value["actual_evaluation"],
        "provenance.actual_evaluation",
        {"start", "end", "step_count"},
    )
    state_model = _object(
        value["state_model"],
        "provenance.state_model",
        {"model_id", "model_version", "configuration_fingerprint"},
    )
    signal = _derivation_identity_payload(
        value["signal_derivation"],
        "provenance.signal_derivation",
    )
    structure = _derivation_identity_payload(
        value["structure_derivation"],
        "provenance.structure_derivation",
    )
    software = _object(
        value["software_revision"],
        "provenance.software_revision",
        {"revision", "dirty"},
    )
    stored_run_fingerprint = _fingerprint(
        value["run_fingerprint"],
        "provenance.run_fingerprint",
    )
    provenance = HistoricalReplayRunProvenance(
        specification=specification,
        specification_fingerprint=specification_fingerprint,
        dataset_content_fingerprint=_fingerprint(
            value["dataset_content_fingerprint"],
            "provenance.dataset_content_fingerprint",
        ),
        provider=_string(value["provider"], "provenance.provider"),
        context_start=_timestamp(context["start"], "provenance.context_start"),
        context_end=_timestamp(context["end"], "provenance.context_end"),
        context_row_count=_positive_integer(
            context["row_count"],
            "provenance.context_row_count",
        ),
        evaluation_start=_timestamp(
            evaluation["start"],
            "provenance.evaluation_start",
        ),
        evaluation_end=_timestamp(
            evaluation["end"],
            "provenance.evaluation_end",
        ),
        evaluation_step_count=_positive_integer(
            evaluation["step_count"],
            "provenance.evaluation_step_count",
        ),
        signal_derivation=ReplaySignalDerivationIdentity(**signal),
        structure_derivation=ReplayStructureDerivationIdentity(**structure),
        state_model_id=_string(
            state_model["model_id"],
            "provenance.state_model.model_id",
        ),
        state_model_version=_string(
            state_model["model_version"],
            "provenance.state_model.model_version",
        ),
        state_model_configuration_fingerprint=_optional_fingerprint(
            state_model["configuration_fingerprint"],
            "provenance.state_model.configuration_fingerprint",
        ),
        strategies=tuple(
            _strategy_identity_from_dict(item, f"provenance.strategies[{index}]")
            for index, item in enumerate(
                _list(value["strategies"], "provenance.strategies")
            )
        ),
        software_revision=SoftwareRevision(
            revision=_string(
                software["revision"],
                "provenance.software_revision.revision",
            ),
            dirty=_boolean(
                software["dirty"],
                "provenance.software_revision.dirty",
            ),
        ),
    )
    if provenance.run_fingerprint != stored_run_fingerprint:
        raise HistoricalReplayArtifactIntegrityError(
            "stored provenance run fingerprint does not match reconstructed provenance"
        )
    return provenance


def _specification_from_dict(payload: object) -> HistoricalReplaySpecification:
    value = _object(
        payload,
        "provenance.specification",
        {
            "symbol",
            "interval",
            "context_start",
            "evaluation_start",
            "evaluation_end",
        },
    )
    return HistoricalReplaySpecification(
        symbol=_string(value["symbol"], "specification.symbol"),
        interval=_string(value["interval"], "specification.interval"),
        context_start=_timestamp(
            value["context_start"],
            "specification.context_start",
        ),
        evaluation_start=_timestamp(
            value["evaluation_start"],
            "specification.evaluation_start",
        ),
        evaluation_end=_timestamp(
            value["evaluation_end"],
            "specification.evaluation_end",
        ),
    )


def _derivation_identity_payload(payload: object, path: str) -> dict[str, str]:
    value = _object(
        payload,
        path,
        {"methodology", "version", "configuration_fingerprint"},
    )
    return {
        "methodology": _string(value["methodology"], f"{path}.methodology"),
        "version": _string(value["version"], f"{path}.version"),
        "configuration_fingerprint": _fingerprint(
            value["configuration_fingerprint"],
            f"{path}.configuration_fingerprint",
        ),
    }


def _object(
    value: object,
    path: str,
    expected_keys: set[str],
) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise HistoricalReplayArtifactError(f"{path} must be an object")
    actual_keys = set(value.keys())
    if any(not isinstance(key, str) for key in actual_keys):
        raise HistoricalReplayArtifactError(f"{path} keys must be strings")
    missing = expected_keys - actual_keys
    unknown = actual_keys - expected_keys
    if missing:
        raise HistoricalReplayArtifactError(
            f"{path} missing required fields: {', '.join(sorted(missing))}"
        )
    if unknown:
        raise HistoricalReplayArtifactError(
            f"{path} contains unknown fields: {', '.join(sorted(unknown))}"
        )
    return value


def _list(value: object, path: str) -> list[object]:
    if not isinstance(value, list):
        raise HistoricalReplayArtifactError(f"{path} must be a list")
    return value


def _string(value: object, path: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise HistoricalReplayArtifactError(f"{path} must be a string")
    if not allow_empty and not value:
        raise HistoricalReplayArtifactError(f"{path} must not be empty")
    return value


def _optional_string(value: object, path: str) -> str | None:
    if value is None:
        return None
    return _string(value, path)


def _boolean(value: object, path: str) -> bool:
    if not isinstance(value, bool):
        raise HistoricalReplayArtifactError(f"{path} must be a boolean")
    return value


def _integer(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise HistoricalReplayArtifactError(f"{path} must be an integer")
    return value


def _positive_integer(value: object, path: str) -> int:
    integer = _integer(value, path)
    if integer <= 0:
        raise HistoricalReplayArtifactError(f"{path} must be greater than zero")
    return integer


def _number(value: object, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HistoricalReplayArtifactError(f"{path} must be numeric")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise HistoricalReplayArtifactError(f"{path} must be finite")
    return numeric


def _optional_number(value: object, path: str) -> float | None:
    if value is None:
        return None
    return _number(value, path)


def _timestamp(value: object, path: str) -> datetime:
    text = _string(value, path)
    try:
        timestamp = datetime.fromisoformat(text)
    except ValueError as exc:
        raise HistoricalReplayArtifactError(
            f"{path} must be an ISO-8601 datetime"
        ) from exc
    if timestamp.tzinfo is None:
        raise HistoricalReplayArtifactError(f"{path} must be timezone-aware")
    return timestamp.astimezone(UTC)


def _optional_timestamp(value: object, path: str) -> datetime | None:
    if value is None:
        return None
    return _timestamp(value, path)


def _optional_timestamp_to_text(value: datetime | None) -> str | None:
    return None if value is None else value.astimezone(UTC).isoformat()


def _string_tuple(value: object, path: str) -> tuple[str, ...]:
    return tuple(
        _string(item, f"{path}[{index}]")
        for index, item in enumerate(_list(value, path))
    )


def _fingerprint(value: object, path: str) -> str:
    text = _string(value, path)
    if _FINGERPRINT_PATTERN.fullmatch(text) is None:
        raise HistoricalReplayArtifactError(
            f"{path} must be a lowercase sha256 fingerprint"
        )
    return text


def _optional_fingerprint(value: object, path: str) -> str | None:
    if value is None:
        return None
    return _fingerprint(value, path)


def _expect_schema(value: object, expected: str, field_name: str) -> None:
    actual = _string(value, field_name)
    if actual != expected:
        raise HistoricalReplayArtifactError(
            f"unsupported {field_name}: {actual!r}"
        )


def _json_mapping(value: object, path: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise HistoricalReplayArtifactError(f"{path} must be an object")
    return {
        _string(key, f"{path} key"): _canonical_json_value(item)
        for key, item in value.items()
    }


def _canonical_json_mapping(value: Mapping[str, object]) -> dict[str, object]:
    normalized = _canonical_json_value(value)
    if not isinstance(normalized, dict):  # pragma: no cover - defensive
        raise TypeError("canonical mapping did not produce a dictionary")
    return normalized


def _canonical_json_value(value: object) -> object:
    if isinstance(value, Mapping):
        normalized: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise TypeError("JSON mapping keys must be nonempty strings")
            normalized[key] = _canonical_json_value(item)
        return normalized
    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        return [_canonical_json_value(item) for item in value]
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return float(canonical_float(value))
    raise TypeError("artifact values must be JSON-compatible")


__all__ = [
    "RESULT_SCHEMA_VERSION",
    "deserialize_historical_replay_result",
    "historical_replay_result_fingerprint",
    "serialize_historical_replay_result",
]
