from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime, timedelta, timezone
from inspect import signature

import pytest
from evidence_test_support import (
    create_governed_test_artifact as _create_evidence_artifact,
)

from market_platform._fingerprint import canonical_fingerprint
from market_platform.evidence import (
    EVIDENCE_FRESHNESS_EVALUATION_RECORD_SCHEMA_VERSION,
    EVIDENCE_FRESHNESS_RULE_SCHEMA_VERSION,
    EvidenceArtifact,
    EvidenceAuthority,
    EvidenceContractReference,
    EvidenceFreshnessEvaluationRecord,
    EvidenceFreshnessRule,
    EvidenceIdentityReference,
    EvidenceInformationClass,
    EvidenceProvenance,
    EvidenceSourceReference,
    EvidenceSubjectReference,
    EvidenceTemporalIdentity,
    create_evidence_freshness_evaluation_record,
)

_MATERIAL_FINGERPRINT = canonical_fingerprint(
    {"schema_version": "market_quote_material/v1", "price": "650.00"}
)


def _artifact() -> EvidenceArtifact:
    origin = EvidenceSourceReference(
        namespace="external_source",
        source_id="market_data_provider",
        source_version="2026-08",
        authority=EvidenceAuthority.EXTERNAL_ORIGIN,
    )
    return _create_evidence_artifact(
        artifact_id="market.quote.spy.2026-08-25",
        artifact_version="1",
        evidence_type="market_quote",
        subjects=(
            EvidenceSubjectReference(
                namespace="instrument",
                subject_id="SPY",
                subject_version="instrument_identity/v1",
            ),
        ),
        temporal_identity=EvidenceTemporalIdentity(
            observed_at=datetime(2026, 8, 25, 20, tzinfo=UTC),
            published_at=datetime(2026, 8, 25, 20, tzinfo=UTC),
            platform_received_at=datetime(2026, 8, 25, 20, 0, 1, tzinfo=UTC),
            artifact_created_at=datetime(2026, 8, 25, 20, 0, 2, tzinfo=UTC),
        ),
        provenance=EvidenceProvenance(
            origin=origin,
            producer=EvidenceIdentityReference(
                namespace="producer",
                identity_id="market_quote_adapter",
                identity_version="1",
            ),
            source_references=(origin,),
        ),
        governing_contract=EvidenceContractReference(
            namespace="evidence_contract",
            contract_id="market_quote",
            contract_version="1",
            information_class=EvidenceInformationClass.SOURCE_MEASUREMENT,
        ),
        material_schema_version="market_quote_material/v1",
        material_fingerprint=_MATERIAL_FINGERPRINT,
    )


def _rule(**changes: object) -> EvidenceFreshnessRule:
    values: dict[str, object] = {
        "rule_id": "market_quote_max_age",
        "rule_version": "1.0.0",
        "declared_temporal_anchor": "published_at",
        "evaluation_scope": "specialist.market_quote",
    }
    values.update(changes)
    return EvidenceFreshnessRule(**values)  # type: ignore[arg-type]


def _evaluation(**changes: object) -> EvidenceFreshnessEvaluationRecord:
    values: dict[str, object] = {
        "artifact": _artifact(),
        "freshness_rule": _rule(),
        "evaluation_as_of": datetime(2026, 8, 25, 20, 5, tzinfo=UTC),
        "result": True,
        "findings": ("Published value is within the rule window.",),
    }
    values.update(changes)
    return create_evidence_freshness_evaluation_record(  # type: ignore[arg-type]
        **values
    )


def test_freshness_rule_is_frozen_slotted_and_exact() -> None:
    rule = _rule()

    assert tuple(item.name for item in fields(EvidenceFreshnessRule)) == (
        "rule_id",
        "rule_version",
        "declared_temporal_anchor",
        "evaluation_scope",
        "schema_version",
        "fingerprint",
    )
    assert not hasattr(rule, "__dict__")
    with pytest.raises(FrozenInstanceError):
        rule.rule_version = "2"  # type: ignore[misc]


def test_freshness_rule_schema_and_fingerprint_are_fixed_and_deterministic() -> None:
    baseline = _rule()
    projection = baseline.to_dict()
    retained_fingerprint = projection.pop("fingerprint")

    assert baseline.schema_version == EVIDENCE_FRESHNESS_RULE_SCHEMA_VERSION
    assert EVIDENCE_FRESHNESS_RULE_SCHEMA_VERSION == "evidence_freshness_rule/v1"
    assert retained_fingerprint == canonical_fingerprint(projection)
    assert baseline.fingerprint == _rule().fingerprint
    assert _rule(rule_version="2.0.0").fingerprint != baseline.fingerprint
    assert _rule(declared_temporal_anchor="observed_at").fingerprint != (
        baseline.fingerprint
    )
    assert _rule(evaluation_scope="consumer.market_quote").fingerprint != (
        baseline.fingerprint
    )


def test_freshness_evaluation_is_factory_created_frozen_and_exact() -> None:
    with pytest.raises(TypeError, match="factory-created"):
        EvidenceFreshnessEvaluationRecord()

    evaluation = _evaluation()
    assert tuple(item.name for item in fields(EvidenceFreshnessEvaluationRecord)) == (
        "artifact_reference",
        "freshness_rule",
        "evaluation_as_of",
        "evaluated_temporal_values",
        "result",
        "findings",
        "schema_version",
        "fingerprint",
    )
    assert not hasattr(evaluation, "__dict__")
    with pytest.raises(FrozenInstanceError):
        evaluation.result = False  # type: ignore[misc]


def test_freshness_evaluation_fingerprint_is_canonical_and_deterministic() -> None:
    baseline = _evaluation()
    projection = baseline.to_dict()
    retained_fingerprint = projection.pop("fingerprint")

    assert baseline.schema_version == (
        EVIDENCE_FRESHNESS_EVALUATION_RECORD_SCHEMA_VERSION
    )
    assert EVIDENCE_FRESHNESS_EVALUATION_RECORD_SCHEMA_VERSION == (
        "evidence_freshness_evaluation_record/v2"
    )
    assert retained_fingerprint == canonical_fingerprint(projection)
    assert baseline.fingerprint == _evaluation().fingerprint
    assert _evaluation(result=False).fingerprint != baseline.fingerprint
    assert (
        _evaluation(
            evaluation_as_of=datetime(2026, 8, 25, 20, 6, tzinfo=UTC)
        ).fingerprint
        != baseline.fingerprint
    )


def test_temporal_values_and_evaluation_as_of_remain_separate_and_canonical() -> None:
    offset = timezone(timedelta(hours=8))
    evaluation = _evaluation(
        evaluation_as_of=datetime(2026, 8, 26, 4, 5, tzinfo=offset),
    )

    assert evaluation.evaluation_as_of == datetime(2026, 8, 25, 20, 5, tzinfo=UTC)
    assert evaluation.evaluated_temporal_values == (
        ("published_at", datetime(2026, 8, 25, 20, tzinfo=UTC)),
    )
    assert (
        evaluation.evaluation_as_of
        not in dict(evaluation.evaluated_temporal_values).values()
    )


def test_evaluation_binds_exact_rule_identity_and_declared_anchor() -> None:
    rule = _rule()
    evaluation = _evaluation(freshness_rule=rule)

    assert evaluation.freshness_rule == rule
    assert evaluation.freshness_rule is not rule
    assert evaluation.freshness_rule.fingerprint == rule.fingerprint
    assert _evaluation(freshness_rule=_rule(rule_version="2.0.0")).fingerprint != (
        evaluation.fingerprint
    )
    observed = _evaluation(
        freshness_rule=_rule(declared_temporal_anchor="observed_at"),
    )
    assert observed.evaluated_temporal_values == (
        ("observed_at", datetime(2026, 8, 25, 20, tzinfo=UTC)),
    )


def test_evaluation_copies_nested_state_and_rejects_mutable_inputs() -> None:
    artifact = _artifact()
    rule = _rule()
    evaluation = _evaluation(
        artifact=artifact,
        freshness_rule=rule,
    )

    assert evaluation.artifact_reference == artifact.reference()
    object.__setattr__(rule, "rule_version", "tampered")
    assert evaluation.freshness_rule.rule_version == "1.0.0"
    assert type(evaluation.evaluated_temporal_values) is tuple
    assert all(type(item) is tuple for item in evaluation.evaluated_temporal_values)
    assert type(evaluation.findings) is tuple

    parameters = signature(create_evidence_freshness_evaluation_record).parameters
    assert "artifact" in parameters
    assert "artifact_reference" not in parameters
    assert "evaluated_temporal_values" not in parameters
    with pytest.raises(TypeError, match="findings must be an exact tuple"):
        _evaluation(findings=["Fresh at evaluation time."])
    with pytest.raises(TypeError, match="exact bool"):
        _evaluation(result=1)


def test_freshness_is_as_of_and_never_mutates_artifact_truth() -> None:
    artifact = _artifact()
    before = artifact.to_dict()
    earlier = _evaluation(
        artifact=artifact,
        evaluation_as_of=datetime(2026, 8, 25, 20, 5, tzinfo=UTC),
        result=True,
    )
    later = _evaluation(
        artifact=artifact,
        evaluation_as_of=datetime(2026, 8, 26, 20, 5, tzinfo=UTC),
        result=False,
        findings=("Published value exceeds the rule window.",),
    )

    assert earlier.artifact_reference == later.artifact_reference
    assert earlier.result is True
    assert later.result is False
    assert earlier.fingerprint != later.fingerprint
    assert artifact.to_dict() == before
    assert "fresh" not in artifact.__dataclass_fields__
    assert "freshness" not in artifact.__dataclass_fields__


def test_freshness_contract_rejects_tampered_nested_or_own_identity() -> None:
    rule = _rule()
    object.__setattr__(rule, "rule_version", "tampered")
    with pytest.raises(ValueError, match="does not match identity"):
        _evaluation(freshness_rule=rule)

    evaluation = _evaluation()
    object.__setattr__(evaluation, "fingerprint", "sha256:" + ("0" * 64))
    with pytest.raises(ValueError, match="does not match content"):
        evaluation.to_dict()


def test_freshness_contracts_have_no_lifecycle_or_semantic_authority_fields() -> None:
    forbidden = {
        "active",
        "admitted",
        "admission_authority",
        "lifecycle_state",
        "permanent_freshness",
        "market_meaning",
        "confidence",
        "recommendation",
    }

    assert forbidden.isdisjoint(EvidenceFreshnessRule.__dataclass_fields__)
    assert forbidden.isdisjoint(EvidenceFreshnessEvaluationRecord.__dataclass_fields__)
    assert forbidden.isdisjoint(_evaluation().to_dict())


def test_freshness_factory_fails_closed_without_exact_artifact_anchor() -> None:
    artifact = _artifact()

    with pytest.raises(ValueError, match="required effective_until"):
        _evaluation(
            artifact=artifact,
            freshness_rule=_rule(declared_temporal_anchor="effective_until"),
        )
    with pytest.raises(ValueError, match="unsupported"):
        _evaluation(
            artifact=artifact,
            freshness_rule=_rule(declared_temporal_anchor="made_up_time"),
        )


def test_interval_anchor_retains_exact_artifact_interval_semantics() -> None:
    base = _artifact()
    interval_artifact = _create_evidence_artifact(
        artifact_id=base.artifact_id,
        artifact_version="interval",
        evidence_type=base.evidence_type,
        subjects=base.subjects,
        temporal_identity=EvidenceTemporalIdentity(
            observation_period_start=datetime(2026, 8, 25, 19, tzinfo=UTC),
            observation_period_end=datetime(2026, 8, 25, 20, tzinfo=UTC),
            platform_received_at=datetime(2026, 8, 25, 20, 0, 1, tzinfo=UTC),
            artifact_created_at=datetime(2026, 8, 25, 20, 0, 2, tzinfo=UTC),
        ),
        provenance=base.provenance,
        governing_contract=base.governing_contract,
        material_schema_version=base.material_schema_version,
        material_fingerprint=base.material_fingerprint,
    )
    evaluation = _evaluation(
        artifact=interval_artifact,
        freshness_rule=_rule(declared_temporal_anchor="observation_period"),
    )

    assert evaluation.evaluated_temporal_values == (
        ("observation_period_end", datetime(2026, 8, 25, 20, tzinfo=UTC)),
        ("observation_period_start", datetime(2026, 8, 25, 19, tzinfo=UTC)),
    )
