from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime, timedelta, timezone

import pytest
from evidence_test_support import (
    create_governed_test_artifact as _create_evidence_artifact,
)

from market_platform._fingerprint import canonical_fingerprint
from market_platform.evidence import (
    EVIDENCE_VALIDATION_RECORD_SCHEMA_VERSION,
    EvidenceArtifact,
    EvidenceAuthority,
    EvidenceContractReference,
    EvidenceIdentityReference,
    EvidenceInformationClass,
    EvidenceProvenance,
    EvidenceSourceReference,
    EvidenceSubjectReference,
    EvidenceTemporalIdentity,
    EvidenceValidationConcern,
    EvidenceValidationDisposition,
    EvidenceValidationRecord,
    create_evidence_validation_record,
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


def _validator() -> EvidenceIdentityReference:
    return EvidenceIdentityReference(
        namespace="validator",
        identity_id="evidence_contract_validator",
        identity_version="1.0.0",
    )


def _record(**changes: object) -> EvidenceValidationRecord:
    values: dict[str, object] = {
        "validation_record_id": "validation.market.quote.spy.2026-08-25.schema.1",
        "artifact_reference": _artifact().reference(),
        "concern": EvidenceValidationConcern.SCHEMA,
        "scope": "specialist.market_quote",
        "disposition": EvidenceValidationDisposition.PASSED,
        "validator_identity": _validator(),
        "ruleset_id": "market_quote_evidence_validation",
        "ruleset_version": "1.0.0",
        "recorded_at": datetime(2026, 8, 25, 20, 1, tzinfo=UTC),
        "effective_at": datetime(2026, 8, 25, 20, 0, 30, tzinfo=UTC),
        "findings": ("Required material fields are present.",),
    }
    values.update(changes)
    return create_evidence_validation_record(**values)  # type: ignore[arg-type]


def test_validation_concern_has_exact_bounded_values() -> None:
    assert tuple(EvidenceValidationConcern) == (
        EvidenceValidationConcern.IDENTITY,
        EvidenceValidationConcern.INTEGRITY,
        EvidenceValidationConcern.PROVENANCE,
        EvidenceValidationConcern.AUTHORITY,
        EvidenceValidationConcern.SCHEMA,
        EvidenceValidationConcern.TEMPORAL_COHERENCE,
        EvidenceValidationConcern.FRESHNESS_CONTRACT,
        EvidenceValidationConcern.SOURCE_QUALITY,
    )
    assert tuple(item.value for item in EvidenceValidationConcern) == (
        "identity",
        "integrity",
        "provenance",
        "authority",
        "schema",
        "temporal_coherence",
        "freshness_contract",
        "source_quality",
    )
    for forbidden in (
        "confidence",
        "significance",
        "ranking",
        "recommendation",
        "market_meaning",
        "truth",
    ):
        with pytest.raises(ValueError):
            EvidenceValidationConcern(forbidden)


def test_validation_disposition_has_exact_values() -> None:
    assert tuple(EvidenceValidationDisposition) == (
        EvidenceValidationDisposition.PASSED,
        EvidenceValidationDisposition.REJECTED,
        EvidenceValidationDisposition.UNABLE_TO_VALIDATE,
    )
    assert tuple(item.value for item in EvidenceValidationDisposition) == (
        "PASSED",
        "REJECTED",
        "UNABLE_TO_VALIDATE",
    )
    for invalid in ("passed", "challenged", "ADMITTED", "FRESH"):
        with pytest.raises(ValueError):
            EvidenceValidationDisposition(invalid)


def test_validation_record_is_factory_created_frozen_and_slotted() -> None:
    with pytest.raises(TypeError, match="factory-created"):
        EvidenceValidationRecord()

    record = _record()
    assert not hasattr(record, "__dict__")
    with pytest.raises(FrozenInstanceError):
        record.scope = "other"  # type: ignore[misc]


def test_validation_record_retains_exact_slice_2_fields() -> None:
    assert tuple(item.name for item in fields(EvidenceValidationRecord)) == (
        "validation_record_id",
        "artifact_reference",
        "concern",
        "scope",
        "disposition",
        "validator_identity",
        "validator_capability_identity",
        "ruleset_id",
        "ruleset_version",
        "predecessor_validation_record_reference",
        "recorded_at",
        "effective_at",
        "findings",
        "schema_version",
        "fingerprint",
    )
    schema_field = next(
        item
        for item in fields(EvidenceValidationRecord)
        if item.name == "schema_version"
    )
    fingerprint_field = next(
        item for item in fields(EvidenceValidationRecord) if item.name == "fingerprint"
    )
    assert not schema_field.init
    assert not fingerprint_field.init
    assert EVIDENCE_VALIDATION_RECORD_SCHEMA_VERSION == "evidence_validation_record/v2"


def test_validation_record_copies_and_freezes_nested_state() -> None:
    artifact_reference = _artifact().reference()
    validator = _validator()
    findings = ("Identity correspondence established.",)
    record = _record(
        artifact_reference=artifact_reference,
        validator_identity=validator,
        findings=findings,
    )

    assert record.artifact_reference is not artifact_reference
    assert record.validator_identity is not validator
    assert type(record.findings) is tuple
    object.__setattr__(artifact_reference, "artifact_version", "tampered")
    object.__setattr__(validator, "identity_id", "tampered")
    assert record.artifact_reference.artifact_version == "1"
    assert record.validator_identity.identity_id == "evidence_contract_validator"
    assert record.findings == findings


def test_validation_record_rejects_mutable_or_empty_findings() -> None:
    with pytest.raises(TypeError, match="exact tuple"):
        _record(findings=["Schema passed."])
    with pytest.raises(ValueError, match="at least one"):
        _record(findings=())


def test_validation_record_fingerprint_is_canonical_and_deterministic() -> None:
    baseline = _record()
    projection = baseline.to_dict()
    retained_fingerprint = projection.pop("fingerprint")

    assert baseline.fingerprint == _record().fingerprint
    assert retained_fingerprint == canonical_fingerprint(projection)
    assert _record(scope="specialist.macro").fingerprint != baseline.fingerprint
    assert (
        _record(disposition=EvidenceValidationDisposition.REJECTED).fingerprint
        != baseline.fingerprint
    )
    assert (
        _record(findings=("Required field is absent.",)).fingerprint
        != baseline.fingerprint
    )


def test_validation_preserves_exact_artifact_reference_without_mutation() -> None:
    artifact = _artifact()
    before = artifact.to_dict()
    artifact_reference = artifact.reference()
    record = _record(artifact_reference=artifact_reference)

    assert record.artifact_reference == artifact_reference
    assert record.artifact_reference.artifact_id == artifact.artifact_id
    assert record.artifact_reference.artifact_version == artifact.artifact_version
    assert record.artifact_reference.artifact_fingerprint == artifact.fingerprint
    assert artifact.to_dict() == before


def test_validation_timestamps_remain_separate_and_canonical_utc() -> None:
    offset = timezone(timedelta(hours=8))
    record = _record(
        recorded_at=datetime(2026, 8, 26, 4, 1, tzinfo=offset),
        effective_at=datetime(2026, 8, 26, 4, 0, 30, tzinfo=offset),
    )

    assert record.recorded_at == datetime(2026, 8, 25, 20, 1, tzinfo=UTC)
    assert record.effective_at == datetime(2026, 8, 25, 20, 0, 30, tzinfo=UTC)
    assert record.recorded_at != record.effective_at


def test_validation_record_rejects_fabricated_nested_or_own_identity() -> None:
    artifact_reference = _artifact().reference()
    object.__setattr__(artifact_reference, "artifact_version", "tampered")
    with pytest.raises(ValueError, match="does not match identity"):
        _record(artifact_reference=artifact_reference)

    record = _record()
    object.__setattr__(record, "fingerprint", "sha256:" + ("0" * 64))
    with pytest.raises(ValueError, match="does not match content"):
        record.to_dict()


def test_validation_record_has_no_admission_freshness_or_semantic_state() -> None:
    forbidden = {
        "admission",
        "admission_state",
        "admitted",
        "fresh",
        "freshness",
        "freshness_result",
        "confidence",
        "significance",
        "ranking",
        "interpretation",
        "recommendation",
        "market_meaning",
    }

    assert forbidden.isdisjoint(EvidenceValidationRecord.__dataclass_fields__)
    assert forbidden.isdisjoint(_record().to_dict())
