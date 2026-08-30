from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, fields
from pathlib import Path

import pytest

from market_platform._fingerprint import canonical_fingerprint
from market_platform.evidence import (
    EVIDENCE_ARTIFACT_REFERENCE_SCHEMA_VERSION,
    EVIDENCE_CONTRACT_REFERENCE_SCHEMA_VERSION,
    EVIDENCE_IDENTITY_REFERENCE_SCHEMA_VERSION,
    EVIDENCE_SOURCE_REFERENCE_SCHEMA_VERSION,
    EVIDENCE_SUBJECT_REFERENCE_SCHEMA_VERSION,
    EvidenceArtifactReference,
    EvidenceAuthority,
    EvidenceContractReference,
    EvidenceIdentityReference,
    EvidenceInformationClass,
    EvidenceSourceReference,
    EvidenceSubjectReference,
)

_TARGET_FINGERPRINT = canonical_fingerprint(
    {"schema_version": "target/v1", "identity": "same"}
)


def _references() -> tuple[object, ...]:
    return (
        EvidenceIdentityReference(
            namespace="producer",
            identity_id="adapter",
            identity_version="1",
            identity_fingerprint=_TARGET_FINGERPRINT,
        ),
        EvidenceSourceReference(
            namespace="external_source",
            source_id="fred",
            source_version="1",
            authority=EvidenceAuthority.EXTERNAL_ORIGIN,
            source_fingerprint=_TARGET_FINGERPRINT,
        ),
        EvidenceSubjectReference(
            namespace="instrument",
            subject_id="SPY",
            subject_version="1",
            subject_fingerprint=_TARGET_FINGERPRINT,
        ),
        EvidenceContractReference(
            namespace="evidence_contract",
            contract_id="market_quote",
            contract_version="1",
            information_class=EvidenceInformationClass.SOURCE_MEASUREMENT,
            contract_fingerprint=_TARGET_FINGERPRINT,
        ),
        EvidenceArtifactReference(
            artifact_id="market.quote.spy",
            artifact_version="1",
            artifact_fingerprint=_TARGET_FINGERPRINT,
            information_class=EvidenceInformationClass.SOURCE_MEASUREMENT,
            authority=EvidenceAuthority.EXTERNAL_ORIGIN,
        ),
    )


def test_reference_contracts_are_frozen_slotted_and_exact() -> None:
    expected_fields = {
        EvidenceIdentityReference: (
            "namespace",
            "identity_id",
            "identity_version",
            "identity_fingerprint",
            "schema_version",
            "fingerprint",
        ),
        EvidenceSourceReference: (
            "namespace",
            "source_id",
            "source_version",
            "authority",
            "source_fingerprint",
            "schema_version",
            "fingerprint",
        ),
        EvidenceSubjectReference: (
            "namespace",
            "subject_id",
            "subject_version",
            "subject_fingerprint",
            "schema_version",
            "fingerprint",
        ),
        EvidenceContractReference: (
            "namespace",
            "contract_id",
            "contract_version",
            "information_class",
            "contract_fingerprint",
            "schema_version",
            "fingerprint",
        ),
        EvidenceArtifactReference: (
            "artifact_id",
            "artifact_version",
            "artifact_fingerprint",
            "information_class",
            "authority",
            "schema_version",
            "fingerprint",
        ),
    }

    for reference in _references():
        assert (
            tuple(item.name for item in fields(type(reference)))
            == expected_fields[type(reference)]
        )
        assert not hasattr(reference, "__dict__")
        with pytest.raises(FrozenInstanceError):
            reference.fingerprint = _TARGET_FINGERPRINT  # type: ignore[attr-defined]


def test_reference_schema_identifiers_are_fixed_internally() -> None:
    expected_schemas = (
        EVIDENCE_IDENTITY_REFERENCE_SCHEMA_VERSION,
        EVIDENCE_SOURCE_REFERENCE_SCHEMA_VERSION,
        EVIDENCE_SUBJECT_REFERENCE_SCHEMA_VERSION,
        EVIDENCE_CONTRACT_REFERENCE_SCHEMA_VERSION,
        EVIDENCE_ARTIFACT_REFERENCE_SCHEMA_VERSION,
    )
    assert expected_schemas == (
        "evidence_identity_reference/v1",
        "evidence_source_reference/v2",
        "evidence_subject_reference/v1",
        "evidence_contract_reference/v2",
        "evidence_artifact_reference/v2",
    )

    for reference, expected_schema in zip(_references(), expected_schemas, strict=True):
        assert reference.schema_version == expected_schema  # type: ignore[attr-defined]
        schema_field = next(
            item for item in fields(type(reference)) if item.name == "schema_version"
        )
        fingerprint_field = next(
            item for item in fields(type(reference)) if item.name == "fingerprint"
        )
        assert not schema_field.init
        assert not fingerprint_field.init


def test_reference_fingerprints_are_deterministic_and_role_separated() -> None:
    first = _references()
    second = _references()

    assert tuple(item.fingerprint for item in first) == tuple(  # type: ignore[attr-defined]
        item.fingerprint
        for item in second  # type: ignore[attr-defined]
    )
    assert len(  # every role is a distinct identity contract
        {item.fingerprint for item in first}  # type: ignore[attr-defined]
    ) == len(first)
    for reference in first:
        projection = reference.to_dict()  # type: ignore[attr-defined]
        fingerprint = projection.pop("fingerprint")
        assert fingerprint == canonical_fingerprint(projection)


def test_artifact_reference_binds_exact_artifact_identity() -> None:
    reference = EvidenceArtifactReference(
        artifact_id="market.quote.spy",
        artifact_version="1",
        artifact_fingerprint=_TARGET_FINGERPRINT,
        information_class=EvidenceInformationClass.SOURCE_MEASUREMENT,
        authority=EvidenceAuthority.EXTERNAL_ORIGIN,
    )
    changed_version = EvidenceArtifactReference(
        artifact_id="market.quote.spy",
        artifact_version="2",
        artifact_fingerprint=_TARGET_FINGERPRINT,
        information_class=EvidenceInformationClass.SOURCE_MEASUREMENT,
        authority=EvidenceAuthority.EXTERNAL_ORIGIN,
    )
    changed_artifact = EvidenceArtifactReference(
        artifact_id="market.quote.spy",
        artifact_version="1",
        artifact_fingerprint=canonical_fingerprint(
            {"schema_version": "target/v1", "identity": "different"}
        ),
        information_class=EvidenceInformationClass.SOURCE_MEASUREMENT,
        authority=EvidenceAuthority.EXTERNAL_ORIGIN,
    )

    assert reference.to_dict()["artifact_fingerprint"] == _TARGET_FINGERPRINT
    assert changed_version.fingerprint != reference.fingerprint
    assert changed_artifact.fingerprint != reference.fingerprint


def test_reference_rejects_retained_identity_or_fingerprint_tampering() -> None:
    source = EvidenceSourceReference(
        namespace="external_source",
        source_id="fred",
        source_version="1",
        authority=EvidenceAuthority.EXTERNAL_ORIGIN,
    )
    object.__setattr__(source, "source_id", "other")
    with pytest.raises(ValueError, match="does not match identity"):
        source.to_dict()

    artifact = EvidenceArtifactReference(
        artifact_id="market.quote.spy",
        artifact_version="1",
        artifact_fingerprint=_TARGET_FINGERPRINT,
        information_class=EvidenceInformationClass.SOURCE_MEASUREMENT,
        authority=EvidenceAuthority.EXTERNAL_ORIGIN,
    )
    object.__setattr__(artifact, "fingerprint", "sha256:" + ("0" * 64))
    with pytest.raises(ValueError, match="does not match identity"):
        artifact.to_dict()


def test_evidence_package_has_no_outward_layer_dependencies() -> None:
    evidence_directory = (
        Path(__file__).resolve().parents[2] / "src" / "market_platform" / "evidence"
    )
    platform_imports: set[str] = set()

    for path in evidence_directory.glob("*.py"):
        module = ast.parse(path.read_text(encoding="utf-8"))
        platform_imports.update(
            node.module
            for node in ast.walk(module)
            if isinstance(node, ast.ImportFrom)
            and node.module is not None
            and node.module.startswith("market_platform")
        )

    assert all(
        imported == "market_platform._fingerprint"
        or imported.startswith("market_platform.evidence")
        for imported in platform_imports
    )
