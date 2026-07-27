from __future__ import annotations

import codecs
import copy
import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

import market_platform.replay.artifact_file as artifact_file
import market_platform.replay.artifact_serialization as artifact_serialization
from market_platform.replay import (
    HistoricalReplayArtifact,
    HistoricalReplayArtifactError,
    HistoricalReplayArtifactIntegrityError,
    HistoricalReplayExecution,
    HistoricalReplayResult,
    HistoricalReplayRunProvenance,
    HistoricalReplaySpecification,
    HistoricalReplayStep,
    ReplaySignalDerivationIdentity,
    ReplayStrategyIdentity,
    ReplayStructureDerivationIdentity,
    SoftwareRevision,
    historical_replay_result_fingerprint,
    load_historical_replay_artifact,
    save_historical_replay_artifact,
    verify_historical_replay_artifact,
)
from market_platform.replay.artifact_serialization import (
    deserialize_historical_replay_result,
    serialize_historical_replay_result,
)
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
    StrategyProvenance,
    StrategyRunResult,
)

_AS_OF = datetime(2026, 7, 1, tzinfo=UTC)
_OBSERVATION_FINGERPRINT = "sha256:" + "a" * 64
_DATASET_FINGERPRINT = "sha256:" + "b" * 64
_SIGNAL_FINGERPRINT = "sha256:" + "c" * 64
_STRUCTURE_FINGERPRINT = "sha256:" + "d" * 64
_STATE_FINGERPRINT = "sha256:" + "e" * 64
_STRATEGY_FINGERPRINT = "sha256:" + "f" * 64


def _execution(
    *,
    evidence_values: tuple[object, ...] = ("up",),
    strategies: tuple[ReplayStrategyIdentity, ...] | None = None,
) -> HistoricalReplayExecution:
    identities = (
        (
            ReplayStrategyIdentity(
                "artifact-strategy",
                "1.0.0",
                _STRATEGY_FINGERPRINT,
            ),
        )
        if strategies is None
        else strategies
    )
    state = _state()
    evaluations = tuple(
        StrategyEvaluation(
            symbol="MSFT",
            interval="1day",
            as_of=_AS_OF,
            provenance=StrategyProvenance(
                strategy_id=identity.strategy_id,
                strategy_version=identity.strategy_version,
                parameters={"thresholds": [0.1, 0.2]},
                observation_fingerprint=_OBSERVATION_FINGERPRINT,
                state_model_id="artifact-state-model",
                state_model_version="1.0.0",
                configuration_fingerprint=identity.configuration_fingerprint,
            ),
            status=StrategyEvaluationStatus.APPLICABLE,
            rationale="Artifact test strategy applies.",
            required_inputs=("trend_regime",),
            evidence=tuple(
                StrategyEvidence(
                    source=StrategyEvidenceSource.MARKET_STATE,
                    field=f"evidence_{value_index}",
                    observed_value=value,  # type: ignore[arg-type]
                    rationale="Typed artifact evidence.",
                    observed_at=_AS_OF,
                )
                for value_index, value in enumerate(evidence_values)
            ),
        )
        for identity in identities
    )
    strategy_result = StrategyRunResult(
        symbol="MSFT",
        interval="1day",
        as_of=_AS_OF,
        observation_fingerprint=_OBSERVATION_FINGERPRINT,
        state_model_id="artifact-state-model",
        state_model_version="1.0.0",
        evaluations=evaluations,
    )
    result = HistoricalReplayResult(
        symbol="MSFT",
        interval="1day",
        start_as_of=_AS_OF,
        end_as_of=_AS_OF,
        steps=(
            HistoricalReplayStep(
                symbol="MSFT",
                interval="1day",
                as_of=_AS_OF,
                observation_fingerprint=_OBSERVATION_FINGERPRINT,
                state=state,
                strategy_result=strategy_result,
            ),
        ),
        state_model_id="artifact-state-model",
        state_model_version="1.0.0",
        strategies=identities,
    )
    specification = HistoricalReplaySpecification(
        symbol="MSFT",
        interval="1day",
        context_start=_AS_OF - timedelta(days=10),
        evaluation_start=_AS_OF,
        evaluation_end=_AS_OF,
    )
    provenance = HistoricalReplayRunProvenance(
        specification=specification,
        specification_fingerprint=specification.fingerprint,
        dataset_content_fingerprint=_DATASET_FINGERPRINT,
        provider="artifact-provider",
        context_start=_AS_OF - timedelta(days=10),
        context_end=_AS_OF,
        context_row_count=11,
        evaluation_start=_AS_OF,
        evaluation_end=_AS_OF,
        evaluation_step_count=1,
        signal_derivation=ReplaySignalDerivationIdentity(
            "artifact-signals",
            "1.0.0",
            _SIGNAL_FINGERPRINT,
        ),
        structure_derivation=ReplayStructureDerivationIdentity(
            "artifact-structure",
            "1.0.0",
            _STRUCTURE_FINGERPRINT,
        ),
        state_model_id="artifact-state-model",
        state_model_version="1.0.0",
        state_model_configuration_fingerprint=_STATE_FINGERPRINT,
        strategies=identities,
        software_revision=SoftwareRevision("5d52638", False),
    )
    return HistoricalReplayExecution(result=result, provenance=provenance)


def _state() -> MarketState:
    component = StateSignalEvidence(
        name="trend",
        raw_value=0.5,
        normalized_score=0.5,
        normalization_scale=1.0,
        configured_weight=1.0,
        normalized_weight=1.0,
        weighted_contribution=0.5,
        interpreted_state="up",
        methodology="artifact-test",
        source_parameters={"windows": [5, 20]},
    )
    return MarketState(
        symbol="MSFT",
        interval="1day",
        as_of=_AS_OF,
        provenance=StateModelProvenance(
            model_id="artifact-state-model",
            model_version="1.0.0",
            parameters={"weights": {"trend": 1.0}},
            observation_fingerprint=_OBSERVATION_FINGERPRINT,
        ),
        directional_regime=DirectionalRegime.UP,
        trend_regime=TrendRegime.UP,
        momentum_regime=MomentumRegime.POSITIVE,
        volatility_regime=VolatilityRegime.NORMAL,
        structure_state=StructureState.AVAILABLE,
        quality=StateQuality.COMPLETE,
        evaluation_evidence=StateEvaluationEvidence(
            directional_components=(component,),
            composite=StateCompositeEvidence(
                score=0.5,
                classification="up",
                methodology="artifact-test",
                formula="trend",
                thresholds=StateClassificationThresholdEvidence(
                    strong_bearish=-0.5,
                    bearish=-0.1,
                    bullish=0.1,
                    strong_bullish=0.5,
                ),
                component_order=("trend",),
                included_signals=("trend",),
                missing_signals=(),
            ),
            volatility=StateVolatilityEvidence(
                raw_value=0.2,
                low_threshold=0.1,
                high_threshold=0.3,
                regime=VolatilityRegime.NORMAL,
                methodology="artifact-test",
            ),
        ),
    )


def test_artifact_round_trip_preserves_complete_execution() -> None:
    execution = _execution()
    artifact = HistoricalReplayArtifact.from_execution(execution)

    reconstructed = HistoricalReplayArtifact.from_dict(
        json.loads(json.dumps(artifact.to_dict()))
    )

    assert reconstructed == artifact
    assert reconstructed.execution == execution
    assert reconstructed.execution.result == execution.result
    assert reconstructed.execution.provenance == execution.provenance
    assert reconstructed.result_fingerprint == artifact.result_fingerprint
    assert reconstructed.integrity_checksum == artifact.integrity_checksum
    assert execution.result.to_dict() == reconstructed.execution.result.to_dict()


def test_typed_strategy_evidence_round_trip_preserves_exact_types() -> None:
    visible_time = "2026-07-01T00:00:00+00:00"
    values = (
        visible_time,
        _AS_OF,
        7,
        1.25,
        True,
        None,
        -1.5,
        0.0,
        -0.0,
    )
    artifact = HistoricalReplayArtifact.from_execution(
        _execution(evidence_values=values)
    )

    reconstructed = HistoricalReplayArtifact.from_dict(artifact.to_dict())
    evidence = reconstructed.execution.result.steps[0].strategy_result.evaluations[
        0
    ].evidence
    reconstructed_values = tuple(item.observed_value for item in evidence)

    assert reconstructed_values[:7] == values[:7]
    assert type(reconstructed_values[0]) is str
    assert type(reconstructed_values[1]) is datetime
    assert type(reconstructed_values[2]) is int
    assert type(reconstructed_values[3]) is float
    assert type(reconstructed_values[4]) is bool
    assert reconstructed_values[7:] == (0.0, 0.0)
    assert artifact.to_dict()["result"]["content"]["steps"][0][
        "strategy_result"
    ]["evaluations"][0]["evidence"][-1]["observed_value"] == {
        "type": "float",
        "value": "0.0",
    }


def test_result_fingerprint_is_typed_and_normalizes_signed_zero() -> None:
    iso_text = _AS_OF.isoformat()
    string_result = _execution(evidence_values=(iso_text,)).result
    datetime_result = _execution(evidence_values=(_AS_OF,)).result
    positive_zero = _execution(evidence_values=(0.0,)).result
    negative_zero = _execution(evidence_values=(-0.0,)).result
    nonzero = _execution(evidence_values=(1.0,)).result

    assert historical_replay_result_fingerprint(string_result) != (
        historical_replay_result_fingerprint(datetime_result)
    )
    assert historical_replay_result_fingerprint(positive_zero) == (
        historical_replay_result_fingerprint(negative_zero)
    )
    assert historical_replay_result_fingerprint(positive_zero) != (
        historical_replay_result_fingerprint(nonzero)
    )


@pytest.mark.parametrize(
    "strategies",
    [
        (),
        (
            ReplayStrategyIdentity("duplicate", "1.0.0", _STRATEGY_FINGERPRINT),
            ReplayStrategyIdentity("duplicate", "1.0.0", _STRATEGY_FINGERPRINT),
        ),
    ],
)
def test_artifact_preserves_empty_and_duplicate_ordered_strategies(
    strategies: tuple[ReplayStrategyIdentity, ...],
) -> None:
    execution = _execution(strategies=strategies)
    artifact = HistoricalReplayArtifact.from_execution(execution)

    reconstructed = HistoricalReplayArtifact.from_dict(artifact.to_dict())

    assert reconstructed.execution.result.strategies == strategies
    assert reconstructed.execution.provenance.strategies == strategies


def test_result_codec_rejects_unknown_fields_and_schemas() -> None:
    payload = serialize_historical_replay_result(_execution().result)
    unknown = copy.deepcopy(payload)
    unknown["content"]["unexpected"] = True
    unsupported = copy.deepcopy(payload)
    unsupported["schema_version"] = "historical_replay_result/v2"

    with pytest.raises(HistoricalReplayArtifactError, match="unknown fields"):
        deserialize_historical_replay_result(unknown)
    with pytest.raises(HistoricalReplayArtifactError, match="unsupported"):
        deserialize_historical_replay_result(unsupported)


@pytest.mark.parametrize(
    "mutator",
    [
        lambda payload: payload["result"]["content"].__setitem__("symbol", "AAPL"),
        lambda payload: payload["execution"]["provenance"].__setitem__(
            "provider", "changed"
        ),
        lambda payload: payload["execution"].__setitem__(
            "run_fingerprint", "sha256:" + "1" * 64
        ),
        lambda payload: payload.__setitem__(
            "result_fingerprint", "sha256:" + "2" * 64
        ),
        lambda payload: payload["integrity"].__setitem__(
            "checksum", "sha256:" + "3" * 64
        ),
    ],
)
def test_artifact_detects_semantic_corruption(mutator: object) -> None:
    payload = copy.deepcopy(
        HistoricalReplayArtifact.from_execution(_execution()).to_dict()
    )
    mutator(payload)  # type: ignore[operator]

    with pytest.raises(HistoricalReplayArtifactIntegrityError):
        HistoricalReplayArtifact.from_dict(payload)


@pytest.mark.parametrize(
    "mutator",
    [
        lambda payload: payload["execution"].__setitem__(
            "run_fingerprint", "sha256:" + "1" * 64
        ),
        lambda payload: payload.__setitem__(
            "result_fingerprint", "sha256:" + "2" * 64
        ),
        lambda payload: payload["result"]["content"].__setitem__("symbol", "AAPL"),
        lambda payload: payload["execution"]["provenance"].__setitem__(
            "provider", "changed"
        ),
    ],
)
def test_identity_verification_survives_recomputed_checksum(mutator: object) -> None:
    payload = copy.deepcopy(
        HistoricalReplayArtifact.from_execution(_execution()).to_dict()
    )
    mutator(payload)  # type: ignore[operator]
    _refresh_checksum(payload)

    with pytest.raises(HistoricalReplayArtifactIntegrityError):
        HistoricalReplayArtifact.from_dict(payload)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("artifact_schema_version",), "historical_replay_artifact/v2"),
        (
            ("result", "schema_version"),
            "historical_replay_result/v2",
        ),
        (
            ("integrity", "schema_version"),
            "historical_replay_artifact_integrity/v2",
        ),
    ],
)
def test_artifact_rejects_unknown_schema_before_integrity(
    path: tuple[str, ...],
    value: str,
) -> None:
    payload = copy.deepcopy(
        HistoricalReplayArtifact.from_execution(_execution()).to_dict()
    )
    target = payload
    for segment in path[:-1]:
        target = target[segment]
    target[path[-1]] = value

    with pytest.raises(HistoricalReplayArtifactError, match="unsupported"):
        HistoricalReplayArtifact.from_dict(payload)


@pytest.mark.parametrize(
    "mutator",
    [
        lambda payload: payload["result"]["content"]["steps"][0]["state"].__setitem__(
            "quality", "not-a-quality"
        ),
        lambda payload: payload["result"]["content"]["steps"][0].__setitem__(
            "as_of", "2026-07-01T00:00:00"
        ),
        lambda payload: payload["result"]["content"]["steps"][0][
            "strategy_result"
        ]["evaluations"][0]["evidence"][0]["observed_value"].__setitem__(
            "type", "unsupported"
        ),
    ],
)
def test_recomputed_checksum_does_not_bypass_model_validation(
    mutator: object,
) -> None:
    payload = copy.deepcopy(
        HistoricalReplayArtifact.from_execution(_execution()).to_dict()
    )
    mutator(payload)  # type: ignore[operator]
    _refresh_checksum(payload)

    with pytest.raises(HistoricalReplayArtifactError):
        HistoricalReplayArtifact.from_dict(payload)


def test_artifact_semantic_checksum_ignores_json_formatting(
    tmp_path: Path,
) -> None:
    artifact = HistoricalReplayArtifact.from_execution(_execution())
    payload = artifact.to_dict()
    reversed_payload = dict(reversed(list(payload.items())))
    path = tmp_path / "formatted.json"
    path.write_bytes(
        (json.dumps(reversed_payload, indent=2) + "\r\n").encode("utf-8")
    )

    loaded = load_historical_replay_artifact(path)

    assert loaded == artifact


def test_file_adapter_is_deterministic_atomic_and_refuses_overwrite(
    tmp_path: Path,
) -> None:
    artifact = HistoricalReplayArtifact.from_execution(_execution())
    first = tmp_path / "nested" / "artifact.json"
    second = tmp_path / "second.json"

    assert save_historical_replay_artifact(first, artifact) == first
    save_historical_replay_artifact(second, artifact)
    assert first.read_bytes() == second.read_bytes()
    assert first.read_bytes().endswith(b"\n")
    assert not first.read_bytes().startswith(codecs.BOM_UTF8)
    with pytest.raises(FileExistsError):
        save_historical_replay_artifact(first, artifact)
    save_historical_replay_artifact(first, artifact, overwrite=True)
    assert verify_historical_replay_artifact(first) == artifact


def test_failed_atomic_replace_preserves_target_and_cleans_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = HistoricalReplayArtifact.from_execution(_execution())
    target = tmp_path / "artifact.json"
    target.write_bytes(b"original")

    def fail_replace(source: object, destination: object) -> None:
        raise PermissionError("replace denied")

    monkeypatch.setattr(artifact_file.os, "replace", fail_replace)
    with pytest.raises(PermissionError, match="replace denied"):
        save_historical_replay_artifact(target, artifact, overwrite=True)

    assert target.read_bytes() == b"original"
    assert list(tmp_path.glob(".artifact.json.*.tmp")) == []


def test_failed_temporary_file_flush_cleans_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = HistoricalReplayArtifact.from_execution(_execution())
    target = tmp_path / "artifact.json"

    def fail_fsync(descriptor: int) -> None:
        raise OSError("flush denied")

    monkeypatch.setattr(artifact_file.os, "fsync", fail_fsync)
    with pytest.raises(OSError, match="flush denied"):
        save_historical_replay_artifact(target, artifact)

    assert not target.exists()
    assert list(tmp_path.glob(".artifact.json.*.tmp")) == []


def test_non_overwrite_publication_cannot_replace_competing_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = HistoricalReplayArtifact.from_execution(_execution())
    target = tmp_path / "artifact.json"
    competing_bytes = b"competing artifact"
    real_link = artifact_file.os.link

    def publish_after_competitor(source: object, destination: object) -> None:
        Path(destination).write_bytes(competing_bytes)
        real_link(source, destination)

    monkeypatch.setattr(artifact_file.os, "link", publish_after_competitor)

    with pytest.raises(FileExistsError):
        save_historical_replay_artifact(target, artifact)

    assert target.read_bytes() == competing_bytes
    assert list(tmp_path.glob(".artifact.json.*.tmp")) == []


def test_cleanup_failure_does_not_mask_primary_publication_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = HistoricalReplayArtifact.from_execution(_execution())
    target = tmp_path / "artifact.json"

    def fail_link(source: object, destination: object) -> None:
        raise PermissionError("publication denied")

    def fail_cleanup(path: Path) -> None:
        raise OSError("cleanup denied")

    monkeypatch.setattr(artifact_file.os, "link", fail_link)
    monkeypatch.setattr(artifact_file.Path, "unlink", fail_cleanup)

    with pytest.raises(PermissionError, match="publication denied"):
        save_historical_replay_artifact(target, artifact)


def test_specification_fingerprint_mismatch_is_an_integrity_error() -> None:
    payload = copy.deepcopy(
        HistoricalReplayArtifact.from_execution(_execution()).to_dict()
    )
    payload["execution"]["provenance"]["specification"]["context_start"] = (
        "2026-06-20T00:00:00+00:00"
    )
    _refresh_checksum(payload)

    with pytest.raises(
        HistoricalReplayArtifactIntegrityError,
        match="specification fingerprint",
    ):
        HistoricalReplayArtifact.from_dict(payload)


def test_malformed_specification_remains_an_artifact_error() -> None:
    payload = copy.deepcopy(
        HistoricalReplayArtifact.from_execution(_execution()).to_dict()
    )
    payload["execution"]["provenance"]["specification"]["context_start"] = True
    _refresh_checksum(payload)

    with pytest.raises(HistoricalReplayArtifactError) as exc_info:
        HistoricalReplayArtifact.from_dict(payload)

    assert not isinstance(exc_info.value, HistoricalReplayArtifactIntegrityError)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (codecs.BOM_UTF8 + b"{}", "BOM"),
        (b"\xff", "UTF-8"),
        (b"{", "valid JSON"),
        (b"[]", "root must be an object"),
    ],
)
def test_loader_rejects_invalid_file_content(
    tmp_path: Path,
    content: bytes,
    message: str,
) -> None:
    path = tmp_path / "invalid.json"
    path.write_bytes(content)

    with pytest.raises(HistoricalReplayArtifactError, match=message):
        load_historical_replay_artifact(path)


def test_loader_preserves_native_file_not_found() -> None:
    with pytest.raises(FileNotFoundError):
        load_historical_replay_artifact("missing-replay-artifact.json")


def test_artifact_stores_dataset_identity_but_not_price_rows() -> None:
    artifact = HistoricalReplayArtifact.from_execution(_execution())
    payload = artifact.to_dict()
    serialized = json.dumps(payload)
    provenance = payload["execution"]["provenance"]

    assert provenance["dataset_content_fingerprint"] == _DATASET_FINGERPRINT
    assert provenance["provider"] == "artifact-provider"
    assert '"open"' not in serialized
    assert '"high"' not in serialized
    assert '"low"' not in serialized
    assert '"close"' not in serialized
    assert '"volume"' not in serialized


def test_equivalent_aware_offsets_produce_same_artifact_identity() -> None:
    local_time = _AS_OF.astimezone(timezone(timedelta(hours=8)))

    utc = HistoricalReplayArtifact.from_execution(
        _execution(evidence_values=(_AS_OF,))
    )
    offset = HistoricalReplayArtifact.from_execution(
        _execution(evidence_values=(local_time,))
    )

    assert offset.result_fingerprint == utc.result_fingerprint
    assert offset.integrity_checksum == utc.integrity_checksum


def _refresh_checksum(payload: dict[str, object]) -> None:
    payload["integrity"]["checksum"] = (
        artifact_serialization._checksum_from_parts(  # noqa: SLF001
            execution=payload["execution"],
            result=payload["result"],
            result_fingerprint=payload["result_fingerprint"],
        )
    )
