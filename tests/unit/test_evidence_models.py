from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime, timedelta, timezone

import pytest
from evidence_test_support import (
    create_test_authorization,
    govern_test_authorizations,
)

from market_platform._fingerprint import canonical_fingerprint
from market_platform.evidence import (
    EVIDENCE_ARTIFACT_REFERENCE_SCHEMA_VERSION,
    EVIDENCE_ARTIFACT_SCHEMA_VERSION,
    EVIDENCE_CONTRACT_REFERENCE_SCHEMA_VERSION,
    EVIDENCE_IDENTITY_REFERENCE_SCHEMA_VERSION,
    EVIDENCE_PROVENANCE_SCHEMA_VERSION,
    EVIDENCE_SOURCE_REFERENCE_SCHEMA_VERSION,
    EVIDENCE_SUBJECT_REFERENCE_SCHEMA_VERSION,
    EVIDENCE_TEMPORAL_IDENTITY_SCHEMA_VERSION,
    EvidenceArtifact,
    EvidenceArtifactReference,
    EvidenceAuthority,
    EvidenceContractDefinition,
    EvidenceContractReference,
    EvidenceIdentityReference,
    EvidenceInformationClass,
    EvidenceMaterialSchemaReference,
    EvidenceProvenance,
    EvidenceSourceReference,
    EvidenceSubjectReference,
    EvidenceTemporalIdentity,
)
from market_platform.evidence.models import _create_evidence_artifact

_MATERIAL_FINGERPRINT = canonical_fingerprint(
    {"schema_version": "macro_release_material/v1", "value": "3.1"}
)
_IDENTITY_FINGERPRINT = canonical_fingerprint(
    {"schema_version": "source_identity/v1", "value": "fred"}
)
_PREDECESSOR_FINGERPRINT = canonical_fingerprint(
    {"schema_version": "evidence_artifact/v1", "value": "predecessor"}
)


def _identity(
    identity_id: str,
    *,
    namespace: str = "source",
    version: str = "1.0.0",
    fingerprint: str | None = _IDENTITY_FINGERPRINT,
) -> EvidenceIdentityReference:
    return EvidenceIdentityReference(
        namespace=namespace,
        identity_id=identity_id,
        identity_version=version,
        identity_fingerprint=fingerprint,
    )


def _source(
    source_id: str,
    *,
    namespace: str = "source",
    version: str = "1.0.0",
    fingerprint: str | None = _IDENTITY_FINGERPRINT,
    authority: EvidenceAuthority = EvidenceAuthority.EXTERNAL_ORIGIN,
) -> EvidenceSourceReference:
    return EvidenceSourceReference(
        namespace=namespace,
        source_id=source_id,
        source_version=version,
        authority=authority,
        source_fingerprint=fingerprint,
    )


def _subject(
    subject_id: str,
    *,
    namespace: str = "subject",
    version: str = "1.0.0",
    fingerprint: str | None = None,
) -> EvidenceSubjectReference:
    return EvidenceSubjectReference(
        namespace=namespace,
        subject_id=subject_id,
        subject_version=version,
        subject_fingerprint=fingerprint,
    )


def _contract(
    contract_id: str,
    *,
    namespace: str = "evidence_contract",
    version: str = "1.0.0",
    fingerprint: str | None = None,
    information_class: EvidenceInformationClass = (
        EvidenceInformationClass.SOURCE_MEASUREMENT
    ),
) -> EvidenceContractReference:
    return EvidenceContractReference(
        namespace=namespace,
        contract_id=contract_id,
        contract_version=version,
        information_class=information_class,
        contract_fingerprint=fingerprint,
    )


def _temporal(**changes: object) -> EvidenceTemporalIdentity:
    values: dict[str, object] = {
        "observed_at": datetime(2026, 8, 25, 8, tzinfo=UTC),
        "observation_period_start": None,
        "observation_period_end": None,
        "effective_from": datetime(2026, 8, 25, 9, tzinfo=UTC),
        "effective_until": datetime(2026, 9, 1, 9, tzinfo=UTC),
        "published_at": datetime(2026, 8, 25, 10, tzinfo=UTC),
        "source_revision": "vintage-2026-08-25",
        "platform_received_at": datetime(2026, 8, 25, 10, 1, tzinfo=UTC),
        "artifact_created_at": datetime(2026, 8, 25, 10, 2, tzinfo=UTC),
    }
    values.update(changes)
    return EvidenceTemporalIdentity(**values)  # type: ignore[arg-type]


def _provenance(**changes: object) -> EvidenceProvenance:
    origin = _source("fred", namespace="external_source")
    values: dict[str, object] = {
        "origin": origin,
        "producer": _identity(
            "macro_release_adapter",
            namespace="producer",
            fingerprint=None,
        ),
        "source_references": (
            origin,
            _source(
                "release-series-CPIAUCSL",
                namespace="source_record",
                fingerprint=None,
            ),
        ),
        "transformations": (
            _identity(
                "decimal-normalization",
                namespace="transformation",
                fingerprint=None,
            ),
        ),
        "predecessors": (
            EvidenceArtifactReference(
                artifact_id="macro.cpi.2026-07",
                artifact_version="1",
                artifact_fingerprint=_PREDECESSOR_FINGERPRINT,
                information_class=EvidenceInformationClass.SOURCE_MEASUREMENT,
                authority=EvidenceAuthority.EXTERNAL_ORIGIN,
            ),
        ),
    }
    values.update(changes)
    return EvidenceProvenance(**values)  # type: ignore[arg-type]


def _artifact(**changes: object) -> EvidenceArtifact:
    values: dict[str, object] = {
        "artifact_id": "macro.cpi.2026-08",
        "artifact_version": "1",
        "evidence_type": "macro_release",
        "subjects": (
            _subject(
                "US",
                namespace="economy",
                version="economy_identity/v1",
                fingerprint=None,
            ),
        ),
        "temporal_identity": _temporal(),
        "provenance": _provenance(),
        "governing_contract": _contract(
            "macro_release",
            namespace="evidence_contract",
            version="1.0.0",
            fingerprint=None,
        ),
        "material_schema_version": "macro_release_material/v1",
        "material_fingerprint": _MATERIAL_FINGERPRINT,
    }
    values.update(changes)
    provenance = values.pop("provenance")
    assert isinstance(provenance, EvidenceProvenance)
    evidence_type = values.pop("evidence_type")
    governing_contract = values.pop("governing_contract")
    material_schema_version = values.pop("material_schema_version")
    if not isinstance(evidence_type, str):
        raise TypeError("evidence_type must be a string")
    if not isinstance(governing_contract, EvidenceContractReference):
        raise TypeError("governing_contract must be an EvidenceContractReference")
    if not isinstance(material_schema_version, str):
        raise TypeError("material_schema_version must be a string")
    definition = EvidenceContractDefinition(
        governing_contract=governing_contract,
        evidence_type=evidence_type,
        information_class=governing_contract.information_class,
        material_schema=EvidenceMaterialSchemaReference(
            schema_id="governed_source_material",
            schema_version_id=material_schema_version,
            schema_fingerprint=canonical_fingerprint(
                {
                    "schema_version": "governed_source_material_identity/v1",
                    "schema_id": "governed_source_material",
                    "version": material_schema_version,
                }
            ),
        ),
    )
    values["provenance"] = provenance
    authorization = create_test_authorization(
        authorization_id="test-governed-source",
        authorization_version="1.0.0",
        contract_definition=definition,
        authorized_source=provenance.origin,
        authority=provenance.origin.authority,
    )
    values["contract_authorization"] = authorization
    with govern_test_authorizations(authorization):
        return _create_evidence_artifact(**values)  # type: ignore[arg-type]


def test_authority_has_exactly_the_two_adr_0035_origin_classes() -> None:
    assert tuple(EvidenceAuthority) == (
        EvidenceAuthority.PLATFORM_ORIGIN,
        EvidenceAuthority.EXTERNAL_ORIGIN,
    )
    assert tuple(item.value for item in EvidenceAuthority) == (
        "platform_origin",
        "external_origin",
    )
    with pytest.raises(ValueError):
        EvidenceAuthority("personal_context")
    with pytest.raises(ValueError):
        EvidenceAuthority("derived_intelligence")
    with pytest.raises(ValueError):
        EvidenceAuthority("authoritative_domain_result")


def test_information_class_has_exactly_the_adr_0035_source_classes() -> None:
    assert tuple(EvidenceInformationClass) == (
        EvidenceInformationClass.SOURCE_OBSERVATION,
        EvidenceInformationClass.SOURCE_MEASUREMENT,
        EvidenceInformationClass.SOURCE_ASSERTION,
    )
    for unsupported in (
        "personal_context",
        "derived_intelligence",
        "authoritative_domain_result",
        "recommendation",
        "decision_history",
    ):
        with pytest.raises(ValueError):
            EvidenceInformationClass(unsupported)


def test_models_are_frozen_and_use_slots() -> None:
    identity = _identity("fred")
    source = _source("fred")
    subject = _subject("US")
    contract = _contract("macro_release")
    temporal = _temporal()
    provenance = _provenance()
    artifact = _artifact()
    reference = artifact.reference()

    for value, field_name in (
        (identity, "identity_id"),
        (source, "source_id"),
        (subject, "subject_id"),
        (contract, "contract_id"),
        (temporal, "source_revision"),
        (provenance, "producer"),
        (artifact, "authority"),
        (reference, "artifact_version"),
    ):
        with pytest.raises(FrozenInstanceError):
            setattr(value, field_name, "changed")
        assert not hasattr(value, "__dict__")


def test_models_retain_only_slice_1a_fields() -> None:
    assert tuple(item.name for item in fields(EvidenceTemporalIdentity)) == (
        "platform_received_at",
        "artifact_created_at",
        "observed_at",
        "observation_period_start",
        "observation_period_end",
        "effective_from",
        "effective_until",
        "published_at",
        "source_revision",
        "schema_version",
        "fingerprint",
    )
    assert tuple(item.name for item in fields(EvidenceProvenance)) == (
        "origin",
        "producer",
        "source_references",
        "transformations",
        "predecessors",
        "schema_version",
        "fingerprint",
    )
    assert tuple(item.name for item in fields(EvidenceArtifact)) == (
        "artifact_id",
        "artifact_version",
        "evidence_type",
        "information_class",
        "subjects",
        "authority",
        "temporal_identity",
        "provenance",
        "governing_contract",
        "material_schema_version",
        "contract_authorization",
        "material_fingerprint",
        "schema_version",
        "fingerprint",
    )
    forbidden = {
        "validated",
        "admitted",
        "active",
        "fresh",
        "freshness",
        "admission_state",
        "interpretation",
        "confidence",
        "ranking",
        "recommendation",
        "aggregate_fingerprint",
        "pipeline_fingerprint",
        "task_evaluation_as_of",
    }
    assert forbidden.isdisjoint(EvidenceArtifact.__dataclass_fields__)


def test_schema_versions_are_fixed_internally() -> None:
    identity = _identity("producer", fingerprint=None)
    source = _source("fred")
    subject = _subject("US")
    contract = _contract("macro_release")
    artifact_reference = EvidenceArtifactReference(
        artifact_id="macro.cpi.2026-07",
        artifact_version="1",
        artifact_fingerprint=_PREDECESSOR_FINGERPRINT,
        information_class=EvidenceInformationClass.SOURCE_MEASUREMENT,
        authority=EvidenceAuthority.EXTERNAL_ORIGIN,
    )
    temporal = _temporal()
    provenance = _provenance()
    artifact = _artifact()

    assert temporal.schema_version == EVIDENCE_TEMPORAL_IDENTITY_SCHEMA_VERSION
    assert provenance.schema_version == EVIDENCE_PROVENANCE_SCHEMA_VERSION
    assert artifact.schema_version == EVIDENCE_ARTIFACT_SCHEMA_VERSION
    assert EVIDENCE_TEMPORAL_IDENTITY_SCHEMA_VERSION == (
        "evidence_temporal_identity/v1"
    )
    assert EVIDENCE_PROVENANCE_SCHEMA_VERSION == "evidence_provenance/v1"
    assert EVIDENCE_ARTIFACT_SCHEMA_VERSION == "evidence_artifact/v3"
    assert identity.schema_version == EVIDENCE_IDENTITY_REFERENCE_SCHEMA_VERSION
    assert source.schema_version == EVIDENCE_SOURCE_REFERENCE_SCHEMA_VERSION
    assert subject.schema_version == EVIDENCE_SUBJECT_REFERENCE_SCHEMA_VERSION
    assert contract.schema_version == EVIDENCE_CONTRACT_REFERENCE_SCHEMA_VERSION
    assert (
        artifact_reference.schema_version == EVIDENCE_ARTIFACT_REFERENCE_SCHEMA_VERSION
    )
    for model_type in (
        EvidenceIdentityReference,
        EvidenceSourceReference,
        EvidenceSubjectReference,
        EvidenceContractReference,
        EvidenceArtifactReference,
        EvidenceTemporalIdentity,
        EvidenceProvenance,
        EvidenceArtifact,
    ):
        schema_field = next(
            item for item in fields(model_type) if item.name == "schema_version"
        )
        fingerprint_field = next(
            item for item in fields(model_type) if item.name == "fingerprint"
        )
        assert not schema_field.init
        assert not fingerprint_field.init


def test_temporal_dimensions_remain_separate_and_canonical_utc() -> None:
    offset = timezone(timedelta(hours=8))
    temporal = EvidenceTemporalIdentity(
        observed_at=None,
        observation_period_start=datetime(2026, 7, 1, 8, tzinfo=offset),
        observation_period_end=datetime(2026, 8, 1, 8, tzinfo=offset),
        effective_from=datetime(2026, 8, 2, 8, tzinfo=offset),
        effective_until=datetime(2026, 9, 2, 8, tzinfo=offset),
        published_at=datetime(2026, 8, 3, 8, tzinfo=offset),
        source_revision="second-vintage",
        platform_received_at=datetime(2026, 8, 3, 8, 1, tzinfo=offset),
        artifact_created_at=datetime(2026, 8, 3, 8, 2, tzinfo=offset),
    )
    projection = temporal.to_dict()

    assert temporal.observation_period_start == datetime(2026, 7, 1, tzinfo=UTC)
    assert temporal.observation_period_end == datetime(2026, 8, 1, tzinfo=UTC)
    assert temporal.effective_from == datetime(2026, 8, 2, tzinfo=UTC)
    assert temporal.published_at == datetime(2026, 8, 3, tzinfo=UTC)
    assert temporal.platform_received_at == datetime(2026, 8, 3, 0, 1, tzinfo=UTC)
    assert temporal.artifact_created_at == datetime(2026, 8, 3, 0, 2, tzinfo=UTC)
    assert projection["source_revision"] == "second-vintage"
    assert "task_evaluation_as_of" not in projection
    assert "admitted_at" not in projection


def test_temporal_contract_does_not_invent_inapplicable_source_times() -> None:
    temporal = EvidenceTemporalIdentity(
        platform_received_at=datetime(2026, 8, 25, tzinfo=UTC),
        artifact_created_at=datetime(2026, 8, 25, 0, 1, tzinfo=UTC),
    )

    assert temporal.observed_at is None
    assert temporal.observation_period_start is None
    assert temporal.effective_from is None
    assert temporal.published_at is None
    assert temporal.source_revision is None


@pytest.mark.parametrize(
    "changes,match",
    [
        (
            {
                "observation_period_start": datetime(2026, 8, 1, tzinfo=UTC),
                "observation_period_end": None,
            },
            "supplied together",
        ),
        (
            {
                "observation_period_start": datetime(2026, 8, 1, tzinfo=UTC),
                "observation_period_end": datetime(2026, 8, 2, tzinfo=UTC),
            },
            "mutually exclusive",
        ),
        (
            {"effective_from": None},
            "requires effective_from",
        ),
        (
            {
                "artifact_created_at": datetime(2026, 8, 25, 10, tzinfo=UTC),
                "platform_received_at": datetime(2026, 8, 25, 11, tzinfo=UTC),
            },
            "must not be earlier",
        ),
    ],
)
def test_temporal_contract_rejects_ambiguity(
    changes: dict[str, object],
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        _temporal(**changes)


def test_temporal_fingerprint_is_deterministic_and_dimension_complete() -> None:
    offset = timezone(timedelta(hours=8))
    equivalent = _temporal(
        observed_at=datetime(2026, 8, 25, 16, tzinfo=offset),
        effective_from=datetime(2026, 8, 25, 17, tzinfo=offset),
        effective_until=datetime(2026, 9, 1, 17, tzinfo=offset),
        published_at=datetime(2026, 8, 25, 18, tzinfo=offset),
        platform_received_at=datetime(2026, 8, 25, 18, 1, tzinfo=offset),
        artifact_created_at=datetime(2026, 8, 25, 18, 2, tzinfo=offset),
    )
    baseline = _temporal()

    assert equivalent.fingerprint == baseline.fingerprint
    assert _temporal(source_revision="other").fingerprint != baseline.fingerprint
    assert (
        _temporal(published_at=datetime(2026, 8, 25, 10, 1, tzinfo=UTC)).fingerprint
        != baseline.fingerprint
    )
    assert baseline.fingerprint.startswith("sha256:")


def test_provenance_copies_orders_and_freezes_complete_lineage() -> None:
    origin = _source("fred", namespace="external_source")
    source_record = _source(
        "release",
        namespace="source_record",
        fingerprint=None,
    )
    producer = _identity("adapter", namespace="producer", fingerprint=None)
    provenance = EvidenceProvenance(
        origin=origin,
        producer=producer,
        source_references=(source_record, origin),
    )

    assert provenance.source_references == (origin, source_record)
    assert type(provenance.source_references) is tuple
    assert provenance.origin is not origin
    assert provenance.producer is not producer
    object.__setattr__(origin, "source_id", "tampered")
    assert provenance.origin.source_id == "fred"
    assert provenance.to_dict()["origin"] == provenance.origin.to_dict()


def test_provenance_fingerprint_covers_complete_lineage() -> None:
    baseline = _provenance()
    changed_origin = _source("bls", namespace="external_source")
    changed_source_references = tuple(
        changed_origin if item == baseline.origin else item
        for item in baseline.source_references
    )

    assert baseline.fingerprint == _provenance().fingerprint
    assert (
        _provenance(
            origin=changed_origin,
            source_references=changed_source_references,
        ).fingerprint
        != baseline.fingerprint
    )
    assert _provenance(transformations=()).fingerprint != baseline.fingerprint
    assert _provenance(predecessors=()).fingerprint != baseline.fingerprint


def test_provenance_rejects_mutable_or_incoherent_lineage_inputs() -> None:
    origin = _source("fred", namespace="external_source")
    producer = _identity("adapter", namespace="producer", fingerprint=None)
    with pytest.raises(TypeError, match="exact tuple"):
        EvidenceProvenance(
            origin=origin,
            producer=producer,
            source_references=[origin],  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="exact tuple"):
        EvidenceProvenance(
            origin=origin,
            producer=producer,
            source_references=(origin,),
            transformations=[],  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="include the origin"):
        EvidenceProvenance(
            origin=origin,
            producer=producer,
            source_references=(_source("other", namespace="external_source"),),
        )


def test_role_specific_references_cannot_be_substituted() -> None:
    source = _source("fred", namespace="external_source")
    generic = _identity("fred", namespace="external_source")

    with pytest.raises(TypeError, match="EvidenceSourceReference"):
        EvidenceProvenance(
            origin=generic,  # type: ignore[arg-type]
            producer=_identity("adapter", namespace="producer", fingerprint=None),
            source_references=(source,),
        )
    with pytest.raises(TypeError, match="EvidenceSourceReference"):
        EvidenceProvenance(
            origin=source,
            producer=_identity("adapter", namespace="producer", fingerprint=None),
            source_references=(generic,),  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="EvidenceSubjectReference"):
        _artifact(subjects=(generic,))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="EvidenceContractReference"):
        _artifact(governing_contract=generic)


def test_artifact_is_factory_only_and_source_authority_is_exact() -> None:
    with pytest.raises(TypeError, match="factory-created"):
        EvidenceArtifact()
    with pytest.raises(TypeError, match="exact EvidenceAuthority"):
        _source("provider", authority="external_origin")  # type: ignore[arg-type]


def test_artifact_rejects_mutable_subject_inputs() -> None:
    with pytest.raises(TypeError, match="exact tuple"):
        _artifact(subjects=[_subject("US", namespace="economy")])


def test_artifact_detaches_nested_state_and_exposes_exact_reference() -> None:
    temporal = _temporal()
    provenance = _provenance()
    subject = _subject(
        "US",
        namespace="economy",
        version="economy_identity/v1",
        fingerprint=None,
    )
    artifact = _artifact(
        subjects=(subject,),
        temporal_identity=temporal,
        provenance=provenance,
    )

    assert artifact.temporal_identity is not temporal
    assert artifact.provenance is not provenance
    assert artifact.subjects[0] is not subject
    object.__setattr__(subject, "subject_id", "tampered")
    object.__setattr__(temporal, "source_revision", "tampered")
    assert artifact.subjects[0].subject_id == "US"
    assert artifact.temporal_identity.source_revision == "vintage-2026-08-25"
    assert artifact.reference() == EvidenceArtifactReference(
        artifact_id=artifact.artifact_id,
        artifact_version=artifact.artifact_version,
        artifact_fingerprint=artifact.fingerprint,
        information_class=artifact.information_class,
        authority=artifact.authority,
    )


def test_artifact_fingerprint_is_deterministic_and_content_complete() -> None:
    baseline = _artifact()

    assert baseline.fingerprint == _artifact().fingerprint
    assert _artifact(artifact_version="2").fingerprint != baseline.fingerprint
    platform_origin = _source(
        "instrument_master",
        namespace="platform_source",
        authority=EvidenceAuthority.PLATFORM_ORIGIN,
    )
    assert (
        _artifact(
            provenance=EvidenceProvenance(
                origin=platform_origin,
                producer=_identity("adapter", namespace="producer", fingerprint=None),
                source_references=(platform_origin,),
            )
        ).fingerprint
        != baseline.fingerprint
    )
    assert (
        _artifact(material_fingerprint=_PREDECESSOR_FINGERPRINT).fingerprint
        != baseline.fingerprint
    )
    assert (
        _artifact(temporal_identity=_temporal(source_revision="other")).fingerprint
        != baseline.fingerprint
    )
    assert baseline.to_dict()["fingerprint"] == baseline.fingerprint
    assert baseline.fingerprint.startswith("sha256:")


def test_artifact_rejects_fabricated_nested_or_own_fingerprint() -> None:
    artifact = _artifact()
    object.__setattr__(artifact, "fingerprint", "sha256:" + ("0" * 64))
    with pytest.raises(ValueError, match="does not match"):
        artifact.to_dict()

    nested = _artifact()
    object.__setattr__(
        nested.temporal_identity,
        "fingerprint",
        "sha256:" + ("0" * 64),
    )
    with pytest.raises(ValueError, match="temporal identity retained state"):
        nested.to_dict()


@pytest.mark.parametrize(
    "value",
    [
        "",
        "SHA256:" + ("0" * 64),
        "sha256:" + ("A" * 64),
        "sha256:short",
    ],
)
def test_artifact_rejects_noncanonical_material_fingerprint(value: str) -> None:
    with pytest.raises(ValueError, match="lowercase sha256"):
        _artifact(material_fingerprint=value)


@pytest.mark.parametrize(
    "unsupported_type",
    (
        "user_objective",
        "computed_strategy_output",
        "domain_strategy_result",
        "buy_recommendation",
        "prior_decision_log",
        "workflow_task_input",
        "novel_unapproved_semantic_alias",
    ),
)
def test_non_source_information_cannot_be_semantically_relabelled_as_evidence(
    unsupported_type: str,
) -> None:
    artifact = _artifact()
    with pytest.raises(TypeError, match="unexpected keyword argument"):
        _create_evidence_artifact(
            artifact_id=artifact.artifact_id,
            artifact_version="semantic-attack",
            evidence_type=unsupported_type,
            subjects=artifact.subjects,
            temporal_identity=artifact.temporal_identity,
            provenance=artifact.provenance,
            governing_contract=artifact.governing_contract,
            material_schema_version=artifact.material_schema_version,
            material_fingerprint=artifact.material_fingerprint,
        )


def test_external_origin_authority_is_derived_and_cannot_be_promoted() -> None:
    external = _artifact(
        provenance=_provenance(
            producer=_identity(
                "platform_normalizer",
                namespace="platform_producer",
                fingerprint=None,
            ),
            transformations=(
                _identity(
                    "platform_canonicalization",
                    namespace="transformation",
                    fingerprint=None,
                ),
            ),
        )
    )

    assert external.authority is EvidenceAuthority.EXTERNAL_ORIGIN
    with pytest.raises(TypeError, match="unexpected keyword argument 'authority'"):
        _artifact(authority=EvidenceAuthority.PLATFORM_ORIGIN)


def test_predecessor_lineage_cannot_launder_external_origin_authority() -> None:
    external = _artifact()
    platform_origin = _source(
        "instrument_master",
        namespace="platform_source",
        authority=EvidenceAuthority.PLATFORM_ORIGIN,
    )
    platform_provenance = EvidenceProvenance(
        origin=platform_origin,
        producer=_identity("artifact_builder", namespace="producer", fingerprint=None),
        source_references=(platform_origin,),
        predecessors=(external.reference(),),
    )

    with pytest.raises(ValueError, match="retain exact origin authority"):
        _artifact(
            artifact_version="2",
            provenance=platform_provenance,
        )


def test_valid_source_origins_create_only_their_corresponding_authority() -> None:
    external = _artifact(provenance=_provenance(predecessors=()))
    platform_origin = _source(
        "instrument_master",
        namespace="platform_source",
        authority=EvidenceAuthority.PLATFORM_ORIGIN,
    )
    platform = _artifact(
        provenance=EvidenceProvenance(
            origin=platform_origin,
            producer=_identity(
                "artifact_builder", namespace="producer", fingerprint=None
            ),
            source_references=(platform_origin,),
        )
    )

    assert external.authority is EvidenceAuthority.EXTERNAL_ORIGIN
    assert platform.authority is EvidenceAuthority.PLATFORM_ORIGIN
    assert external.information_class is EvidenceInformationClass.SOURCE_MEASUREMENT
    assert platform.information_class is EvidenceInformationClass.SOURCE_MEASUREMENT


def test_contract_classification_is_immutable_and_matches_artifact() -> None:
    assertion = _artifact(
        governing_contract=_contract(
            "source_assertion",
            information_class=EvidenceInformationClass.SOURCE_ASSERTION,
        ),
        provenance=_provenance(predecessors=()),
    )

    assert assertion.information_class is EvidenceInformationClass.SOURCE_ASSERTION
    assert (
        assertion.governing_contract.information_class
        is EvidenceInformationClass.SOURCE_ASSERTION
    )
    object.__setattr__(
        assertion,
        "information_class",
        EvidenceInformationClass.SOURCE_OBSERVATION,
    )
    with pytest.raises(ValueError, match="not contract-authorized"):
        assertion.to_dict()


def test_predecessor_lineage_cannot_change_source_information_class() -> None:
    measurement = _artifact(provenance=_provenance(predecessors=()))

    with pytest.raises(ValueError, match="retain exact Evidence information class"):
        _artifact(
            artifact_version="2",
            governing_contract=_contract(
                "source_assertion",
                information_class=EvidenceInformationClass.SOURCE_ASSERTION,
            ),
            provenance=_provenance(predecessors=(measurement.reference(),)),
        )
