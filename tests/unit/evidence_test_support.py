"""Governed adapter fixture used only by Evidence foundation unit tests."""

from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import patch

import market_platform.evidence.authorization as evidence_authorization
from market_platform._fingerprint import canonical_fingerprint
from market_platform.evidence import (
    EvidenceArtifact,
    EvidenceAuthority,
    EvidenceContractAuthorization,
    EvidenceContractDefinition,
    EvidenceContractReference,
    EvidenceMaterialSchemaReference,
    EvidenceProvenance,
    EvidenceSourceReference,
    EvidenceSubjectReference,
    EvidenceTemporalIdentity,
)
from market_platform.evidence.authorization import (
    _create_evidence_contract_authorization_record,
    _EvidenceAuthorizationApprovalCatalog,
)
from market_platform.evidence.models import _create_evidence_artifact


def create_test_authorization(
    *,
    authorization_id: str,
    authorization_version: str,
    contract_definition: EvidenceContractDefinition,
    authorized_source: EvidenceSourceReference,
    authority: EvidenceAuthority,
) -> EvidenceContractAuthorization:
    """Construct a synthetic authorization description for test scope only."""

    return _create_evidence_contract_authorization_record(
        authorization_id=authorization_id,
        authorization_version=authorization_version,
        contract_definition=contract_definition,
        authorized_source=authorized_source,
        authority=authority,
    )


@contextmanager
def govern_test_authorizations(
    *authorizations: EvidenceContractAuthorization,
) -> Iterator[None]:
    """Temporarily replace the production catalog within one test scope."""

    test_catalog = _EvidenceAuthorizationApprovalCatalog(
        authorizations=tuple(authorizations)
    )
    with patch.object(
        evidence_authorization,
        "_GOVERNED_EVIDENCE_AUTHORIZATION_CATALOG",
        test_catalog,
    ):
        yield


def create_governed_test_artifact(
    *,
    artifact_id: str,
    artifact_version: str,
    evidence_type: str,
    subjects: tuple[EvidenceSubjectReference, ...],
    temporal_identity: EvidenceTemporalIdentity,
    provenance: EvidenceProvenance,
    governing_contract: EvidenceContractReference,
    material_schema_version: str,
    material_fingerprint: str,
) -> EvidenceArtifact:
    """Act as the test suite's explicit governed source-adapter boundary."""

    material_schema = EvidenceMaterialSchemaReference(
        schema_id="evidence_test_source_material",
        schema_version_id=material_schema_version,
        schema_fingerprint=canonical_fingerprint(
            {
                "schema_version": "evidence_test_source_material_identity/v1",
                "schema_id": "evidence_test_source_material",
                "schema_version_id": material_schema_version,
            }
        ),
    )
    definition = EvidenceContractDefinition(
        governing_contract=governing_contract,
        evidence_type=evidence_type,
        information_class=governing_contract.information_class,
        material_schema=material_schema,
    )
    authorization = create_test_authorization(
        authorization_id="evidence-unit-test-adapter",
        authorization_version="1.0.0",
        contract_definition=definition,
        authorized_source=provenance.origin,
        authority=provenance.origin.authority,
    )
    with govern_test_authorizations(authorization):
        return _create_evidence_artifact(
            artifact_id=artifact_id,
            artifact_version=artifact_version,
            subjects=subjects,
            temporal_identity=temporal_identity,
            provenance=provenance,
            contract_authorization=authorization,
            material_fingerprint=material_fingerprint,
        )


__all__ = [
    "create_governed_test_artifact",
    "create_test_authorization",
    "govern_test_authorizations",
]
