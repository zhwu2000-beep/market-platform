from __future__ import annotations

from datetime import UTC, datetime

import pytest
from evidence_test_support import (
    create_governed_test_artifact,
    create_test_authorization,
    govern_test_authorizations,
)
from test_evidence_admission import _CONCERNS, _freshness, _ruleset, _validation
from test_evidence_evaluation import _admission, _evaluate, _validity

import market_platform.evidence as evidence
import market_platform.evidence.authorization as evidence_authorization
from market_platform._fingerprint import canonical_fingerprint
from market_platform.evidence.authorization import EvidenceContractDefinition
from market_platform.evidence.models import _create_evidence_artifact


def _source(
    authority: evidence.EvidenceAuthority,
    *,
    source_id: str = "same-material-source",
    source_version: str = "1",
    fingerprint_key: str = "same",
) -> evidence.EvidenceSourceReference:
    return evidence.EvidenceSourceReference(
        namespace="governed_test_source",
        source_id=source_id,
        source_version=source_version,
        authority=authority,
        source_fingerprint=canonical_fingerprint(
            {
                "schema_version": "source_identity/v1",
                "source": fingerprint_key,
            }
        ),
    )


def _authorization(
    *,
    authorization_id: str = "evidence-unit-test-adapter",
    authorization_version: str = "1.0.0",
    contract_id: str = "governed_measurement",
    contract_version: str = "1",
    evidence_type: str = "governed_measurement",
    information_class: evidence.EvidenceInformationClass = (
        evidence.EvidenceInformationClass.SOURCE_MEASUREMENT
    ),
    material_schema_id: str = "governed_measurement_material",
    material_schema_version: str = "governed_measurement_material/v1",
    material_schema_fingerprint_key: str = "baseline",
    source_id: str = "same-material-source",
    source_version: str = "1",
    source_fingerprint_key: str = "same",
    authority: evidence.EvidenceAuthority = (
        evidence.EvidenceAuthority.EXTERNAL_ORIGIN
    ),
) -> evidence.EvidenceContractAuthorization:
    source = _source(
        authority,
        source_id=source_id,
        source_version=source_version,
        fingerprint_key=source_fingerprint_key,
    )
    definition = EvidenceContractDefinition(
        governing_contract=evidence.EvidenceContractReference(
            namespace="evidence_contract",
            contract_id=contract_id,
            contract_version=contract_version,
            information_class=information_class,
        ),
        evidence_type=evidence_type,
        information_class=information_class,
        material_schema=evidence.EvidenceMaterialSchemaReference(
            schema_id=material_schema_id,
            schema_version_id=material_schema_version,
            schema_fingerprint=canonical_fingerprint(
                {
                    "schema_version": "material_schema_identity/v1",
                    "key": material_schema_fingerprint_key,
                }
            ),
        ),
    )
    return create_test_authorization(
        authorization_id=authorization_id,
        authorization_version=authorization_version,
        contract_definition=definition,
        authorized_source=source,
        authority=authority,
    )


def _mint(
    authorization: evidence.EvidenceContractAuthorization,
) -> evidence.EvidenceArtifact:
    source = authorization.authorized_source
    return _create_evidence_artifact(
        artifact_id="trust-root.synthetic",
        artifact_version="1",
        subjects=(
            evidence.EvidenceSubjectReference(
                namespace="test_subject",
                subject_id="subject",
                subject_version="1",
            ),
        ),
        temporal_identity=evidence.EvidenceTemporalIdentity(
            observed_at=datetime(2026, 8, 25, 20, tzinfo=UTC),
            published_at=datetime(2026, 8, 25, 20, tzinfo=UTC),
            platform_received_at=datetime(2026, 8, 25, 20, 0, 1, tzinfo=UTC),
            artifact_created_at=datetime(2026, 8, 25, 20, 0, 2, tzinfo=UTC),
        ),
        provenance=evidence.EvidenceProvenance(
            origin=source,
            producer=evidence.EvidenceIdentityReference(
                namespace="producer",
                identity_id="governed_test_adapter",
                identity_version="1",
            ),
            source_references=(source,),
        ),
        contract_authorization=authorization,
        material_fingerprint=canonical_fingerprint(
            {
                "schema_version": (
                    authorization.contract_definition.material_schema.schema_version_id
                ),
                "value": "observed",
            }
        ),
    )


def _artifact(
    information_class: evidence.EvidenceInformationClass,
    *,
    authority: evidence.EvidenceAuthority = evidence.EvidenceAuthority.EXTERNAL_ORIGIN,
    evidence_type: str | None = None,
) -> evidence.EvidenceArtifact:
    source = _source(authority)
    type_id = evidence_type or f"governed_{information_class.value}"
    return create_governed_test_artifact(
        artifact_id=f"trust-root.{information_class.value}.{authority.value}",
        artifact_version="1",
        evidence_type=type_id,
        subjects=(
            evidence.EvidenceSubjectReference(
                namespace="test_subject",
                subject_id="subject",
                subject_version="1",
            ),
        ),
        temporal_identity=evidence.EvidenceTemporalIdentity(
            observed_at=datetime(2026, 8, 25, 20, tzinfo=UTC),
            published_at=datetime(2026, 8, 25, 20, tzinfo=UTC),
            platform_received_at=datetime(2026, 8, 25, 20, 0, 1, tzinfo=UTC),
            artifact_created_at=datetime(2026, 8, 25, 20, 0, 2, tzinfo=UTC),
        ),
        provenance=evidence.EvidenceProvenance(
            origin=source,
            producer=evidence.EvidenceIdentityReference(
                namespace="producer",
                identity_id="governed_test_adapter",
                identity_version="1",
            ),
            source_references=(source,),
        ),
        governing_contract=evidence.EvidenceContractReference(
            namespace="evidence_contract",
            contract_id=type_id,
            contract_version="1",
            information_class=information_class,
        ),
        material_schema_version=f"{type_id}_material/v1",
        material_fingerprint=canonical_fingerprint(
            {"schema_version": f"{type_id}_material/v1", "value": "observed"}
        ),
    )


def _complete_lifecycle(
    artifact: evidence.EvidenceArtifact,
) -> evidence.EvidenceAdmissionState:
    ruleset = _ruleset()
    validations = tuple(_validation(artifact, concern) for concern in _CONCERNS)
    admission_freshness = _freshness(
        artifact,
        as_of=datetime(2026, 8, 25, 20, 5, tzinfo=UTC),
    )
    task_freshness = _freshness(
        artifact,
        as_of=datetime(2026, 8, 25, 20, 10, tzinfo=UTC),
    )
    admission = _admission(
        artifact,
        validations,
        admission_freshness,
        ruleset=ruleset,
    )
    active = _validity(artifact)
    return _evaluate(
        artifact,
        ruleset=ruleset,
        validations=validations,
        freshness=(admission_freshness, task_freshness),
        admissions=(admission,),
        validity=(active,),
    )


def test_arbitrary_caller_authorization_cannot_mint_or_reach_consumability() -> None:
    authorization = _authorization(
        contract_id="novel_personal_objective_quasar",
        evidence_type="novel_personal_objective_quasar",
    )

    with pytest.raises(ValueError, match="not governed/approved"):
        _mint(authorization)


@pytest.mark.parametrize(
    "alias",
    (
        "unseen_personalized_alpha_prompt",
        "novel_private_goal_pulsar",
        "memory_derived_market_fact_nebula",
        "generated_strategy_evidence_comet",
    ),
)
def test_novel_aliases_remain_unapproved_without_catalog_membership(
    alias: str,
) -> None:
    authorization = _authorization(contract_id=alias, evidence_type=alias)

    with pytest.raises(ValueError, match="not governed/approved"):
        _mint(authorization)


def test_contract_definition_and_authorization_record_do_not_grant_authority() -> None:
    authorization = _authorization(evidence_type="unapproved_novel_semantic_alias")

    with pytest.raises(TypeError, match="factory-created"):
        evidence.EvidenceContractAuthorization()
    with pytest.raises(ValueError, match="not governed/approved"):
        _mint(authorization)


def test_exact_governed_authorization_is_required_for_artifact_construction() -> None:
    approved = _authorization()
    changed_authorizations = (
        _authorization(contract_id="changed_contract"),
        _authorization(contract_version="2"),
        _authorization(evidence_type="changed_evidence_type"),
        _authorization(
            information_class=evidence.EvidenceInformationClass.SOURCE_ASSERTION
        ),
        _authorization(material_schema_id="changed_material_schema"),
        _authorization(material_schema_version="governed_measurement_material/v2"),
        _authorization(material_schema_fingerprint_key="changed"),
        _authorization(source_id="changed-source"),
        _authorization(source_version="2"),
        _authorization(source_fingerprint_key="changed"),
        _authorization(
            authority=evidence.EvidenceAuthority.PLATFORM_ORIGIN,
        ),
        _authorization(authorization_version="2.0.0"),
    )

    with govern_test_authorizations(approved):
        artifact = _mint(approved)
        assert artifact.contract_authorization == approved
        for changed in changed_authorizations:
            with pytest.raises(ValueError, match="not governed/approved"):
                _mint(changed)


def test_external_origin_approval_cannot_be_laundered_to_platform_origin() -> None:
    external = _authorization(
        authority=evidence.EvidenceAuthority.EXTERNAL_ORIGIN,
    )
    reconstructed_platform = _authorization(
        authority=evidence.EvidenceAuthority.PLATFORM_ORIGIN,
    )

    with govern_test_authorizations(external):
        assert _mint(external).authority is evidence.EvidenceAuthority.EXTERNAL_ORIGIN
        with pytest.raises(ValueError, match="not governed/approved"):
            _mint(reconstructed_platform)


def test_production_governance_catalog_is_closed_and_empty_by_default() -> None:
    catalog = evidence_authorization._GOVERNED_EVIDENCE_AUTHORIZATION_CATALOG

    assert catalog.authorizations == ()
    with pytest.raises(ValueError, match="not governed/approved"):
        _mint(_authorization())
    assert not hasattr(evidence, "authorize_evidence_contract")
    assert not hasattr(evidence, "create_evidence_artifact")


@pytest.mark.parametrize("information_class", tuple(evidence.EvidenceInformationClass))
def test_all_three_test_governed_source_classes_complete_the_lifecycle(
    information_class: evidence.EvidenceInformationClass,
) -> None:
    state = _complete_lifecycle(_artifact(information_class))
    assert state.is_consumable


def test_test_scoped_catalog_restores_production_default_deterministically() -> None:
    authorization = _authorization()

    with govern_test_authorizations(authorization):
        assert _mint(authorization).contract_authorization == authorization

    assert (
        evidence_authorization._GOVERNED_EVIDENCE_AUTHORIZATION_CATALOG.authorizations
        == ()
    )
    with pytest.raises(ValueError, match="not governed/approved"):
        _mint(authorization)


def test_legitimately_test_governed_platform_origin_completes_the_lifecycle() -> None:
    platform = _artifact(
        evidence.EvidenceInformationClass.SOURCE_OBSERVATION,
        authority=evidence.EvidenceAuthority.PLATFORM_ORIGIN,
    )
    state = _complete_lifecycle(platform)

    assert platform.authority is evidence.EvidenceAuthority.PLATFORM_ORIGIN
    assert state.is_consumable
