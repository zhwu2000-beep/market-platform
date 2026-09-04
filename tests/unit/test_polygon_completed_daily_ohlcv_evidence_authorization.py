from __future__ import annotations

from datetime import UTC, datetime

import pytest
from evidence_test_support import (
    create_test_authorization,
    govern_test_authorizations,
)

import market_platform.evidence as evidence
import market_platform.evidence.authorization as evidence_authorization
from market_platform._fingerprint import canonical_fingerprint
from market_platform.evidence.models import _create_evidence_artifact
from market_platform.evidence.polygon_completed_daily_ohlcv import (
    _create_polygon_completed_daily_ohlcv_evidence_artifact,
)


def _authorization(
    *,
    authorization_id: str = "production.polygon_completed_daily_ohlcv",
    authorization_version: str = "1.0.0",
    contract_namespace: str = "market_platform.evidence",
    contract_id: str = "polygon_completed_daily_ohlcv",
    contract_version: str = "1.0.0",
    contract_fingerprint: str | None = (
        evidence_authorization._POLYGON_COMPLETED_DAILY_OHLCV_CONTRACT_DEFINITION_FINGERPRINT
    ),
    evidence_type: str = "polygon_completed_daily_ohlcv",
    information_class: evidence.EvidenceInformationClass = (
        evidence.EvidenceInformationClass.SOURCE_MEASUREMENT
    ),
    material_schema_id: str = "polygon_completed_daily_ohlcv_material",
    material_schema_version: str = "1.0.0",
    material_schema_fingerprint: str = (
        evidence_authorization._POLYGON_COMPLETED_DAILY_OHLCV_MATERIAL_DEFINITION_FINGERPRINT
    ),
    source_namespace: str = "massive",
    source_id: str = "stocks_custom_bars_1_day_adjusted_api_polygon_io",
    source_version: str = "1.0.0",
    source_fingerprint: str | None = (
        evidence_authorization._POLYGON_COMPLETED_DAILY_OHLCV_SOURCE_DEFINITION_FINGERPRINT
    ),
    authority: evidence.EvidenceAuthority = (
        evidence.EvidenceAuthority.EXTERNAL_ORIGIN
    ),
) -> evidence.EvidenceContractAuthorization:
    source = evidence.EvidenceSourceReference(
        namespace=source_namespace,
        source_id=source_id,
        source_version=source_version,
        authority=authority,
        source_fingerprint=source_fingerprint,
    )
    definition = evidence.EvidenceContractDefinition(
        governing_contract=evidence.EvidenceContractReference(
            namespace=contract_namespace,
            contract_id=contract_id,
            contract_version=contract_version,
            information_class=information_class,
            contract_fingerprint=contract_fingerprint,
        ),
        evidence_type=evidence_type,
        information_class=information_class,
        material_schema=evidence.EvidenceMaterialSchemaReference(
            schema_id=material_schema_id,
            schema_version_id=material_schema_version,
            schema_fingerprint=material_schema_fingerprint,
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
        artifact_id="polygon.completed_daily.spy.2026-08-20.2026-08-21",
        artifact_version="sha256:" + ("1" * 64),
        subjects=(
            evidence.EvidenceSubjectReference(
                namespace="canonical_instrument",
                subject_id="us_equity:SPY",
                subject_version="1.0.0",
                subject_fingerprint="sha256:" + ("2" * 64),
            ),
        ),
        temporal_identity=evidence.EvidenceTemporalIdentity(
            observation_period_start=datetime(2026, 8, 20, 4, tzinfo=UTC),
            observation_period_end=datetime(2026, 8, 22, 4, tzinfo=UTC),
            source_revision="sha256:" + ("3" * 64),
            platform_received_at=datetime(2026, 8, 24, 12, tzinfo=UTC),
            artifact_created_at=datetime(2026, 8, 24, 12, 0, 1, tzinfo=UTC),
        ),
        provenance=evidence.EvidenceProvenance(
            origin=source,
            producer=evidence.EvidenceIdentityReference(
                namespace="producer",
                identity_id="polygon_completed_daily_ohlcv_adapter",
                identity_version="1.0.0",
            ),
            source_references=(source,),
        ),
        contract_authorization=authorization,
        material_fingerprint="sha256:" + ("3" * 64),
    )


def test_exact_approved_contract_resolves_and_mints_candidate_artifact() -> None:
    approved = evidence_authorization._POLYGON_COMPLETED_DAILY_OHLCV_AUTHORIZATION
    source = approved.authorized_source

    artifact = _create_polygon_completed_daily_ohlcv_evidence_artifact(
        artifact_id="polygon.completed_daily.spy.2026-08-20.2026-08-21",
        artifact_version="sha256:" + ("1" * 64),
        subjects=(
            evidence.EvidenceSubjectReference(
                namespace="canonical_instrument",
                subject_id="us_equity:SPY",
                subject_version="1.0.0",
                subject_fingerprint="sha256:" + ("2" * 64),
            ),
        ),
        temporal_identity=evidence.EvidenceTemporalIdentity(
            observation_period_start=datetime(2026, 8, 20, 4, tzinfo=UTC),
            observation_period_end=datetime(2026, 8, 22, 4, tzinfo=UTC),
            source_revision="sha256:" + ("3" * 64),
            platform_received_at=datetime(2026, 8, 24, 12, tzinfo=UTC),
            artifact_created_at=datetime(2026, 8, 24, 12, 0, 1, tzinfo=UTC),
        ),
        provenance=evidence.EvidenceProvenance(
            origin=source,
            producer=evidence.EvidenceIdentityReference(
                namespace="producer",
                identity_id="polygon_completed_daily_ohlcv_adapter",
                identity_version="1.0.0",
            ),
            source_references=(source,),
        ),
        material_fingerprint="sha256:" + ("3" * 64),
    )

    assert artifact.contract_authorization == approved
    assert artifact.governing_contract.contract_id == ("polygon_completed_daily_ohlcv")
    assert artifact.evidence_type == "polygon_completed_daily_ohlcv"
    assert artifact.material_schema_version == "1.0.0"
    assert artifact.authority is evidence.EvidenceAuthority.EXTERNAL_ORIGIN
    assert artifact.information_class is (
        evidence.EvidenceInformationClass.SOURCE_MEASUREMENT
    )
    assert artifact.provenance.origin == source


@pytest.mark.parametrize(
    "authorization",
    (
        _authorization(contract_id="polygon_completed_daily_ohlcv_other"),
        _authorization(contract_version="1.0.1"),
        _authorization(
            contract_fingerprint=canonical_fingerprint(
                {"schema_version": "contract_definition/v1", "profile": "other"}
            )
        ),
        _authorization(evidence_type="polygon_completed_daily_ohlcv_other"),
        _authorization(
            information_class=evidence.EvidenceInformationClass.SOURCE_OBSERVATION
        ),
        _authorization(
            material_schema_id="polygon_completed_daily_ohlcv_material_other"
        ),
        _authorization(material_schema_version="1.0.1"),
        _authorization(
            material_schema_fingerprint=canonical_fingerprint(
                {"schema_version": "material_definition/v1", "profile": "other"}
            )
        ),
        _authorization(source_namespace="polygon"),
        _authorization(source_id="stocks_custom_bars_1_day_unadjusted_api_polygon_io"),
        _authorization(source_version="1.0.1"),
        _authorization(
            source_fingerprint=canonical_fingerprint(
                {"schema_version": "source_definition/v1", "profile": "other"}
            )
        ),
        _authorization(authority=evidence.EvidenceAuthority.PLATFORM_ORIGIN),
        _authorization(
            authorization_id="production.polygon_completed_daily_ohlcv_other"
        ),
        _authorization(authorization_version="1.0.1"),
    ),
    ids=(
        "contract-id",
        "contract-version",
        "contract-fingerprint",
        "evidence-type",
        "information-class",
        "material-schema-id",
        "material-schema-version",
        "material-schema-fingerprint",
        "source-namespace",
        "source-id",
        "source-version",
        "source-fingerprint",
        "authority",
        "authorization-id",
        "authorization-version",
    ),
)
def test_exact_semantic_near_misses_fail_closed(
    authorization: evidence.EvidenceContractAuthorization,
) -> None:
    with pytest.raises(ValueError, match="not governed/approved"):
        _mint(authorization)


def test_reconstructed_description_does_not_itself_create_approval() -> None:
    approved = evidence_authorization._POLYGON_COMPLETED_DAILY_OHLCV_AUTHORIZATION
    reconstructed = _authorization()

    assert reconstructed == approved
    assert reconstructed is not approved
    with (
        govern_test_authorizations(),
        pytest.raises(ValueError, match="not governed/approved"),
    ):
        _mint(reconstructed)
    assert (
        evidence_authorization._GOVERNED_EVIDENCE_AUTHORIZATION_CATALOG.authorizations
        == (approved,)
    )


def test_self_consistent_novel_contract_cannot_become_production_evidence() -> None:
    novel = _authorization(
        authorization_id="caller.novel_daily_values",
        contract_id="caller_novel_daily_values",
        contract_version="9.0.0",
        contract_fingerprint=canonical_fingerprint(
            {"schema_version": "contract_definition/v1", "contract": "novel"}
        ),
        evidence_type="caller_novel_daily_values",
        material_schema_id="caller_novel_daily_values_material",
        material_schema_version="9.0.0",
        material_schema_fingerprint=canonical_fingerprint(
            {"schema_version": "material_definition/v1", "material": "novel"}
        ),
        source_namespace="caller_source",
        source_id="caller_novel_source",
        source_version="9.0.0",
        source_fingerprint=canonical_fingerprint(
            {"schema_version": "source_definition/v1", "source": "novel"}
        ),
    )

    with pytest.raises(ValueError, match="not governed/approved"):
        _mint(novel)


@pytest.mark.parametrize(
    "authorization",
    (
        _authorization(
            source_id="stocks_custom_bars_1_day_adjusted_api_massive_com",
            source_fingerprint=canonical_fingerprint(
                {
                    "schema_version": "source_definition/v1",
                    "api_base": "https://api.massive.com",
                }
            ),
        ),
        _authorization(
            source_id="stocks_previous_close_adjusted_api_polygon_io",
            source_fingerprint=canonical_fingerprint(
                {
                    "schema_version": "source_definition/v1",
                    "capability": "stocks_previous_close",
                }
            ),
        ),
    ),
    ids=("api-massive-com", "other-massive-polygon-capability"),
)
def test_massive_polygon_branding_is_not_a_wildcard(
    authorization: evidence.EvidenceContractAuthorization,
) -> None:
    with pytest.raises(ValueError, match="not governed/approved"):
        _mint(authorization)


def test_existing_unapproved_contract_remains_unauthorized() -> None:
    existing_style = _authorization(
        authorization_id="evidence-unit-test-adapter",
        contract_namespace="evidence_contract",
        contract_id="governed_measurement",
        contract_version="1",
        contract_fingerprint=None,
        evidence_type="governed_measurement",
        material_schema_id="governed_measurement_material",
        material_schema_version="governed_measurement_material/v1",
        material_schema_fingerprint="sha256:" + ("4" * 64),
        source_namespace="governed_test_source",
        source_id="same-material-source",
        source_version="1",
        source_fingerprint="sha256:" + ("5" * 64),
    )

    with pytest.raises(ValueError, match="not governed/approved"):
        _mint(existing_style)


def test_production_catalog_contains_exactly_the_adr0037_membership() -> None:
    catalog = evidence_authorization._GOVERNED_EVIDENCE_AUTHORIZATION_CATALOG
    approved = catalog.authorizations[0]
    definition = approved.contract_definition

    assert catalog.authorizations == (
        evidence_authorization._POLYGON_COMPLETED_DAILY_OHLCV_AUTHORIZATION,
    )
    assert approved.authorization_id == ("production.polygon_completed_daily_ohlcv")
    assert approved.authorization_version == "1.0.0"
    assert approved.authorized_source == (
        evidence_authorization._POLYGON_COMPLETED_DAILY_OHLCV_SOURCE
    )
    assert definition.governing_contract == (
        evidence_authorization._POLYGON_COMPLETED_DAILY_OHLCV_GOVERNING_CONTRACT
    )
    assert definition.material_schema == (
        evidence_authorization._POLYGON_COMPLETED_DAILY_OHLCV_MATERIAL_SCHEMA
    )
    assert approved.authority is evidence.EvidenceAuthority.EXTERNAL_ORIGIN
    assert definition.information_class is (
        evidence.EvidenceInformationClass.SOURCE_MEASUREMENT
    )


def test_definition_fingerprints_bind_the_static_adr0037_semantics() -> None:
    source_definition = (
        evidence_authorization._POLYGON_COMPLETED_DAILY_OHLCV_SOURCE_DEFINITION
    )
    material_definition = (
        evidence_authorization._POLYGON_COMPLETED_DAILY_OHLCV_MATERIAL_DEFINITION
    )
    contract_definition = (
        evidence_authorization._POLYGON_COMPLETED_DAILY_OHLCV_CONTRACT_DEFINITION
    )

    assert source_definition["governing_adr"].endswith(
        "@d9c30a57fef451eb7b5e66850af2d94be128f5fb"
    )
    assert source_definition["vendor_service"] == ("massive.com_formerly_polygon.io")
    assert source_definition["api_base"] == "https://api.polygon.io"
    assert source_definition["adjusted"] is True
    assert source_definition["sort"] == "asc"
    assert source_definition["limit"] == 50000
    assert source_definition["market_timezone"] == "America/New_York"
    assert source_definition["price_adjustment"] == (
        "split_adjusted_not_dividend_adjusted"
    )
    assert source_definition["split_adjustment_formula"] == (
        "provider_internal_undocumented_not_asserted_or_reconstructed"
    )
    assert source_definition["volume_semantics"] == (
        "provider_reported_split_adjusted_aggregate_decimal_capable"
    )
    assert "https://api.massive.com" not in source_definition.values()
    assert material_definition["volume_type"] == (
        "decimal_capable_provider_reported_value"
    )
    assert contract_definition["lifecycle"] == (
        "candidate_unvalidated_unadmitted_not_consumable"
    )
    assert canonical_fingerprint(source_definition) == (
        evidence_authorization._POLYGON_COMPLETED_DAILY_OHLCV_SOURCE_DEFINITION_FINGERPRINT
    )
    assert canonical_fingerprint(material_definition) == (
        evidence_authorization._POLYGON_COMPLETED_DAILY_OHLCV_MATERIAL_DEFINITION_FINGERPRINT
    )
    assert canonical_fingerprint(contract_definition) == (
        evidence_authorization._POLYGON_COMPLETED_DAILY_OHLCV_CONTRACT_DEFINITION_FINGERPRINT
    )


def test_no_public_authorization_or_catalog_mutation_surface_is_added() -> None:
    forbidden_names = {
        "authorize_evidence_contract",
        "create_evidence_artifact",
        "create_polygon_completed_daily_ohlcv_evidence_artifact",
        "get_evidence_authorization_catalog",
        "register_evidence_authorization",
    }

    assert forbidden_names.isdisjoint(evidence.__all__)
    assert all(not hasattr(evidence, name) for name in forbidden_names)
    assert evidence_authorization.__all__ == [
        "EVIDENCE_CONTRACT_AUTHORIZATION_SCHEMA_VERSION",
        "EVIDENCE_CONTRACT_DEFINITION_SCHEMA_VERSION",
        "EVIDENCE_MATERIAL_SCHEMA_REFERENCE_SCHEMA_VERSION",
        "EvidenceContractAuthorization",
        "EvidenceContractDefinition",
        "EvidenceMaterialSchemaReference",
    ]
