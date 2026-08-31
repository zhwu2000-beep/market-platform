from __future__ import annotations

import ast
import inspect
from dataclasses import fields, is_dataclass
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path

import pytest
from evidence_test_support import (
    create_governed_test_artifact as _create_evidence_artifact,
)

import market_platform.evidence as evidence

EXPECTED_PUBLIC_API = (
    "EVIDENCE_ADMISSION_RECORD_REFERENCE_SCHEMA_VERSION",
    "EVIDENCE_ADMISSION_RECORD_SCHEMA_VERSION",
    "EVIDENCE_ADMISSION_RULESET_REFERENCE_SCHEMA_VERSION",
    "EVIDENCE_ADMISSION_RULESET_SCHEMA_VERSION",
    "EVIDENCE_ADMISSION_STATE_SCHEMA_VERSION",
    "EVIDENCE_ARTIFACT_REFERENCE_SCHEMA_VERSION",
    "EVIDENCE_ARTIFACT_SCHEMA_VERSION",
    "EVIDENCE_ARTIFACT_SUPERSESSION_LINK_REFERENCE_SCHEMA_VERSION",
    "EVIDENCE_ARTIFACT_SUPERSESSION_LINK_SCHEMA_VERSION",
    "EVIDENCE_ARTIFACT_SUPERSESSION_RESOLUTION_SCHEMA_VERSION",
    "EVIDENCE_CONTRACT_AUTHORIZATION_SCHEMA_VERSION",
    "EVIDENCE_CONTRACT_DEFINITION_SCHEMA_VERSION",
    "EVIDENCE_CONTRACT_REFERENCE_SCHEMA_VERSION",
    "EVIDENCE_FRESHNESS_EVALUATION_RECORD_SCHEMA_VERSION",
    "EVIDENCE_FRESHNESS_EVALUATION_REFERENCE_SCHEMA_VERSION",
    "EVIDENCE_FRESHNESS_RULE_SCHEMA_VERSION",
    "EVIDENCE_IDENTITY_REFERENCE_SCHEMA_VERSION",
    "EVIDENCE_MATERIAL_SCHEMA_REFERENCE_SCHEMA_VERSION",
    "EVIDENCE_PROVENANCE_SCHEMA_VERSION",
    "EVIDENCE_SOURCE_REFERENCE_SCHEMA_VERSION",
    "EVIDENCE_SUBJECT_REFERENCE_SCHEMA_VERSION",
    "EVIDENCE_TEMPORAL_IDENTITY_SCHEMA_VERSION",
    "EVIDENCE_VALIDATION_RECORD_REFERENCE_SCHEMA_VERSION",
    "EVIDENCE_VALIDATION_RECORD_SCHEMA_VERSION",
    "EVIDENCE_VALIDATION_REQUIREMENT_SCHEMA_VERSION",
    "EVIDENCE_VALIDITY_EVENT_SCHEMA_VERSION",
    "EVIDENCE_VALIDITY_REFERENCE_SCHEMA_VERSION",
    "EvidenceAdmissionDisposition",
    "EvidenceAdmissionRecord",
    "EvidenceAdmissionRecordReference",
    "EvidenceAdmissionRuleSet",
    "EvidenceAdmissionRuleSetReference",
    "EvidenceAdmissionState",
    "EvidenceArtifact",
    "EvidenceArtifactReference",
    "EvidenceArtifactSupersessionLink",
    "EvidenceArtifactSupersessionLinkReference",
    "EvidenceArtifactSupersessionResolution",
    "EvidenceArtifactSupersessionResolutionError",
    "EvidenceAuthority",
    "EvidenceContractAuthorization",
    "EvidenceContractDefinition",
    "EvidenceContractReference",
    "EvidenceFreshnessEvaluationRecord",
    "EvidenceFreshnessEvaluationReference",
    "EvidenceFreshnessRule",
    "EvidenceIdentityReference",
    "EvidenceInformationClass",
    "EvidenceMaterialSchemaReference",
    "EvidenceProvenance",
    "EvidenceSourceReference",
    "EvidenceSubjectReference",
    "EvidenceTemporalIdentity",
    "EvidenceValidationConcern",
    "EvidenceValidationDisposition",
    "EvidenceValidationRecord",
    "EvidenceValidationRecordReference",
    "EvidenceValidationRequirement",
    "EvidenceValidityEvent",
    "EvidenceValidityReference",
    "EvidenceValidityStatus",
    "create_evidence_admission_record",
    "create_evidence_artifact_supersession_link",
    "create_evidence_freshness_evaluation_record",
    "create_evidence_validation_record",
    "create_evidence_validity_event",
    "evaluate_evidence_admission_as_of",
    "evaluate_evidence_validity_as_of",
    "resolve_evidence_artifact_supersession_as_of",
)

PUBLIC_EXPORTS_BY_MODULE = {
    "market_platform.evidence.authorization": (
        "EVIDENCE_CONTRACT_AUTHORIZATION_SCHEMA_VERSION",
        "EVIDENCE_CONTRACT_DEFINITION_SCHEMA_VERSION",
        "EVIDENCE_MATERIAL_SCHEMA_REFERENCE_SCHEMA_VERSION",
        "EvidenceContractAuthorization",
        "EvidenceContractDefinition",
        "EvidenceMaterialSchemaReference",
    ),
    "market_platform.evidence.classification": (
        "EvidenceAuthority",
        "EvidenceInformationClass",
    ),
    "market_platform.evidence.models": (
        "EVIDENCE_ARTIFACT_SCHEMA_VERSION",
        "EVIDENCE_PROVENANCE_SCHEMA_VERSION",
        "EVIDENCE_TEMPORAL_IDENTITY_SCHEMA_VERSION",
        "EvidenceArtifact",
        "EvidenceProvenance",
        "EvidenceTemporalIdentity",
    ),
    "market_platform.evidence.references": (
        "EVIDENCE_ARTIFACT_REFERENCE_SCHEMA_VERSION",
        "EVIDENCE_CONTRACT_REFERENCE_SCHEMA_VERSION",
        "EVIDENCE_IDENTITY_REFERENCE_SCHEMA_VERSION",
        "EVIDENCE_SOURCE_REFERENCE_SCHEMA_VERSION",
        "EVIDENCE_SUBJECT_REFERENCE_SCHEMA_VERSION",
        "EvidenceArtifactReference",
        "EvidenceContractReference",
        "EvidenceIdentityReference",
        "EvidenceSourceReference",
        "EvidenceSubjectReference",
    ),
    "market_platform.evidence.validation": (
        "EVIDENCE_VALIDATION_RECORD_REFERENCE_SCHEMA_VERSION",
        "EVIDENCE_VALIDATION_RECORD_SCHEMA_VERSION",
        "EvidenceValidationConcern",
        "EvidenceValidationDisposition",
        "EvidenceValidationRecord",
        "EvidenceValidationRecordReference",
        "create_evidence_validation_record",
    ),
    "market_platform.evidence.temporal": (
        "EVIDENCE_FRESHNESS_EVALUATION_RECORD_SCHEMA_VERSION",
        "EVIDENCE_FRESHNESS_EVALUATION_REFERENCE_SCHEMA_VERSION",
        "EVIDENCE_FRESHNESS_RULE_SCHEMA_VERSION",
        "EvidenceFreshnessEvaluationRecord",
        "EvidenceFreshnessEvaluationReference",
        "EvidenceFreshnessRule",
        "create_evidence_freshness_evaluation_record",
    ),
    "market_platform.evidence.admission": (
        "EVIDENCE_ADMISSION_RECORD_REFERENCE_SCHEMA_VERSION",
        "EVIDENCE_ADMISSION_RECORD_SCHEMA_VERSION",
        "EVIDENCE_ADMISSION_STATE_SCHEMA_VERSION",
        "EvidenceAdmissionDisposition",
        "EvidenceAdmissionRecord",
        "EvidenceAdmissionRecordReference",
        "EvidenceAdmissionState",
        "create_evidence_admission_record",
    ),
    "market_platform.evidence.policy": (
        "EVIDENCE_ADMISSION_RULESET_REFERENCE_SCHEMA_VERSION",
        "EVIDENCE_ADMISSION_RULESET_SCHEMA_VERSION",
        "EVIDENCE_VALIDATION_REQUIREMENT_SCHEMA_VERSION",
        "EvidenceAdmissionRuleSet",
        "EvidenceAdmissionRuleSetReference",
        "EvidenceValidationRequirement",
    ),
    "market_platform.evidence.evaluation": ("evaluate_evidence_admission_as_of",),
    "market_platform.evidence.validity": (
        "EVIDENCE_VALIDITY_EVENT_SCHEMA_VERSION",
        "EVIDENCE_VALIDITY_REFERENCE_SCHEMA_VERSION",
        "EvidenceValidityEvent",
        "EvidenceValidityReference",
        "EvidenceValidityStatus",
        "create_evidence_validity_event",
        "evaluate_evidence_validity_as_of",
    ),
    "market_platform.evidence.supersession": (
        "EVIDENCE_ARTIFACT_SUPERSESSION_LINK_REFERENCE_SCHEMA_VERSION",
        "EVIDENCE_ARTIFACT_SUPERSESSION_LINK_SCHEMA_VERSION",
        "EVIDENCE_ARTIFACT_SUPERSESSION_RESOLUTION_SCHEMA_VERSION",
        "EvidenceArtifactSupersessionLink",
        "EvidenceArtifactSupersessionLinkReference",
        "EvidenceArtifactSupersessionResolution",
        "EvidenceArtifactSupersessionResolutionError",
        "create_evidence_artifact_supersession_link",
        "resolve_evidence_artifact_supersession_as_of",
    ),
}

PRIVATE_NAMES = (
    "_EvidenceAuthorizationApprovalCatalog",
    "_GOVERNED_EVIDENCE_AUTHORIZATION_CATALOG",
    "_AUTHORIZATION_RECORD_SEAL",
    "canonical_fingerprint",
    "_ADMISSION_RECORD_SEAL",
    "_ADMISSION_STATE_SEAL",
    "_ARTIFACT_SEAL",
    "_FINGERPRINT_PATTERN",
    "_FRESHNESS_EVALUATION_RECORD_SEAL",
    "_SUPERSESSION_LINK_SEAL",
    "_VALIDITY_EVENT_SEAL",
    "_artifact_identity",
    "_artifact_reference_tuple",
    "_authorize_evidence_contract",
    "_copy_contract_authorization",
    "_create_evidence_contract_authorization_record",
    "_copy_artifact_reference",
    "_create_evidence_admission_state_from_resolution",
    "_create_evidence_artifact",
    "_fingerprint",
    "_has_supersession_cycle",
    "_resolve_admission",
    "_resolve_governed_evidence_contract_authorization",
    "_resolve_exact_freshness",
    "_resolve_freshness",
    "_resolve_task_freshness",
    "_resolve_validations",
    "_resolve_validity",
    "_resolved_state",
    "_require_resolution_correspondence",
    "_supersession_link_reference_tuple",
    "_supersession_link_tuple",
)

TRUST_ROOT_EXPORTS = frozenset(
    {
        "EVIDENCE_CONTRACT_AUTHORIZATION_SCHEMA_VERSION",
        "EVIDENCE_CONTRACT_DEFINITION_SCHEMA_VERSION",
        "EVIDENCE_MATERIAL_SCHEMA_REFERENCE_SCHEMA_VERSION",
        "EvidenceContractAuthorization",
        "EvidenceContractDefinition",
        "EvidenceMaterialSchemaReference",
    }
)

UNSAFE_ROOT_ENTRY_POINTS = frozenset(
    {
        "approve_evidence_contract",
        "approve_evidence_contract_authorization",
        "_authorize_evidence_contract",
        "_create_evidence_artifact",
        "authorize_evidence_contract",
        "configure_evidence_authorization_catalog",
        "create_evidence_artifact",
        "create_evidence_contract_authorization",
        "evaluate_evidence_admission_state",
        "install_evidence_authorization",
        "mint_evidence_artifact",
        "promote_evidence_authority",
        "register_evidence_contract",
        "replace_evidence_authorization_catalog",
    }
)

TEST_ONLY_GOVERNANCE_NAMES = frozenset(
    {
        "create_governed_test_artifact",
        "create_test_authorization",
        "govern_test_authorizations",
    }
)

FORBIDDEN_GOVERNANCE_PARAMETERS = frozenset(
    {
        "approval_catalog",
        "authorization_catalog",
        "catalog",
        "governance_registry",
        "issuer",
        "registry",
        "test_mode",
    }
)

STALE_PRE_5J_EXPORTS = frozenset(
    {
        "EVIDENCE_MATERIAL_SCHEMA_VERSION",
        "EvidenceAuthorization",
        "EvidenceContract",
        "EvidenceMaterialSchema",
    }
)

VALIDITY_AND_POLICY_EXPORTS = frozenset(
    {
        "EVIDENCE_ADMISSION_RULESET_REFERENCE_SCHEMA_VERSION",
        "EVIDENCE_ADMISSION_RULESET_SCHEMA_VERSION",
        "EVIDENCE_VALIDITY_EVENT_SCHEMA_VERSION",
        "EVIDENCE_VALIDITY_REFERENCE_SCHEMA_VERSION",
        "EvidenceAdmissionRuleSet",
        "EvidenceAdmissionRuleSetReference",
        "EvidenceValidityEvent",
        "EvidenceValidityReference",
        "EvidenceValidityStatus",
        "create_evidence_validity_event",
        "evaluate_evidence_validity_as_of",
    }
)

SUPERSESSION_EXPORTS = frozenset(
    {
        "EVIDENCE_ARTIFACT_SUPERSESSION_LINK_REFERENCE_SCHEMA_VERSION",
        "EVIDENCE_ARTIFACT_SUPERSESSION_LINK_SCHEMA_VERSION",
        "EVIDENCE_ARTIFACT_SUPERSESSION_RESOLUTION_SCHEMA_VERSION",
        "EvidenceArtifactSupersessionLink",
        "EvidenceArtifactSupersessionLinkReference",
        "EvidenceArtifactSupersessionResolution",
        "EvidenceArtifactSupersessionResolutionError",
        "create_evidence_artifact_supersession_link",
        "resolve_evidence_artifact_supersession_as_of",
    }
)

OBSOLETE_ROOT_EXPORTS = frozenset(
    {
        "EVIDENCE_ADMISSION_SUPERSESSION_REFERENCE_SCHEMA_VERSION",
        "EvidenceAdmissionSupersessionReference",
        "create_evidence_admission_supersession_reference",
        "evaluate_evidence_admission_state",
    }
)

FORBIDDEN_SEMANTIC_FIELDS = frozenset(
    {
        "aggregate_fingerprint",
        "confidence",
        "confidence_score",
        "current",
        "current_admission",
        "current_state",
        "current_status",
        "current_validity",
        "interpretation",
        "lifecycle_state",
        "market_significance",
        "market_meaning",
        "pipeline_fingerprint",
        "ranking",
        "rank",
        "recommendation",
        "significance",
        "strategy",
        "trade_action",
        "trading_action",
        "truth",
    }
)

FORBIDDEN_PUBLIC_NAME_FRAGMENTS = frozenset(
    {
        "aggregatefingerprint",
        "authoritativedomainresult",
        "confidence",
        "currentlifecycle",
        "decisionhistory",
        "derivedintelligence",
        "interpretation",
        "personalcontext",
        "personalintelligence",
        "pipelinefingerprint",
        "ranking",
        "recommendation",
        "significance",
        "strategy",
        "tradeaction",
        "tradingaction",
        "truth",
    }
)

FORBIDDEN_DEPENDENCY_SEGMENTS = frozenset(
    {
        "ai",
        "agent_exposure",
        "application",
        "cli",
        "data",
        "execution",
        "execution_planning",
        "indicators",
        "instruments",
        "observation",
        "order_lifecycle",
        "personal_context",
        "personal_intelligence",
        "persistence",
        "providers",
        "replay",
        "research",
        "risk",
        "signals",
        "storage",
        "strategy",
        "structure",
        "trade_planning",
        "trading",
        "trading_state",
    }
)


def test_public_api_is_exact_and_ordered() -> None:
    assert tuple(evidence.__all__) == EXPECTED_PUBLIC_API
    assert len(evidence.__all__) == len(EXPECTED_PUBLIC_API)
    assert len(evidence.__all__) == len(set(evidence.__all__))

    schema_versions = tuple(
        name for name in evidence.__all__ if name.startswith("EVIDENCE_")
    )
    contracts = tuple(name for name in evidence.__all__ if name.startswith("Evidence"))
    operations = tuple(name for name in evidence.__all__ if name[0].islower())
    assert schema_versions == tuple(sorted(schema_versions))
    assert contracts == tuple(sorted(contracts))
    assert operations == tuple(sorted(operations))


def test_public_imports_remain_bound_to_their_defining_modules() -> None:
    defining_exports: set[str] = set()
    for module_name, export_names in PUBLIC_EXPORTS_BY_MODULE.items():
        module = import_module(module_name)
        for export_name in export_names:
            defining_exports.add(export_name)
            assert getattr(evidence, export_name) is getattr(module, export_name)

    assert defining_exports == set(EXPECTED_PUBLIC_API)


def test_private_implementation_details_are_not_exported() -> None:
    for private_name in PRIVATE_NAMES:
        assert private_name not in evidence.__all__
        assert not hasattr(evidence, private_name)


def test_trust_root_contracts_are_public_but_governance_issuance_is_private() -> None:
    authorization = import_module("market_platform.evidence.authorization")
    models = import_module("market_platform.evidence.models")

    assert set(evidence.__all__) >= TRUST_ROOT_EXPORTS
    assert UNSAFE_ROOT_ENTRY_POINTS.isdisjoint(evidence.__all__)
    assert STALE_PRE_5J_EXPORTS.isdisjoint(evidence.__all__)
    assert all(not hasattr(evidence, name) for name in UNSAFE_ROOT_ENTRY_POINTS)
    assert all(not hasattr(evidence, name) for name in STALE_PRE_5J_EXPORTS)
    assert "_authorize_evidence_contract" not in authorization.__all__
    assert not hasattr(authorization, "_authorize_evidence_contract")
    assert "_create_evidence_contract_authorization_record" not in authorization.__all__
    assert "_AUTHORIZATION_RECORD_SEAL" not in authorization.__all__
    assert "_create_evidence_artifact" not in models.__all__
    authorization_record_factory = (
        authorization._create_evidence_contract_authorization_record
    )
    assert all(
        value is not authorization_record_factory for value in vars(evidence).values()
    )
    assert all(
        value is not models._create_evidence_artifact
        for value in vars(evidence).values()
    )

    assert tuple(
        field.name for field in fields(evidence.EvidenceMaterialSchemaReference)
    ) == (
        "schema_id",
        "schema_version_id",
        "schema_fingerprint",
        "schema_version",
        "fingerprint",
    )
    definition_fields = tuple(
        field.name for field in fields(evidence.EvidenceContractDefinition)
    )
    assert definition_fields == (
        "governing_contract",
        "evidence_type",
        "information_class",
        "material_schema",
        "schema_version",
        "fingerprint",
    )
    assert tuple(
        field.name for field in fields(evidence.EvidenceContractAuthorization)
    ) == (
        "authorization_id",
        "authorization_version",
        "contract_definition",
        "authorized_source",
        "authority",
        "schema_version",
        "fingerprint",
    )
    for contract in (
        evidence.EvidenceMaterialSchemaReference,
        evidence.EvidenceContractDefinition,
        evidence.EvidenceContractAuthorization,
    ):
        assert is_dataclass(contract)
        assert contract.__dataclass_params__.frozen
        assert hasattr(contract, "__slots__")

    material_schema = evidence.EvidenceMaterialSchemaReference(
        schema_id="governed_measurement",
        schema_version_id="governed_measurement/v1",
        schema_fingerprint="sha256:" + ("1" * 64),
    )
    definition = evidence.EvidenceContractDefinition(
        governing_contract=evidence.EvidenceContractReference(
            namespace="evidence_contract",
            contract_id="governed_measurement",
            contract_version="1",
            information_class=(evidence.EvidenceInformationClass.SOURCE_MEASUREMENT),
        ),
        evidence_type="governed_measurement",
        information_class=evidence.EvidenceInformationClass.SOURCE_MEASUREMENT,
        material_schema=material_schema,
    )
    source = evidence.EvidenceSourceReference(
        namespace="governed_source",
        source_id="measurement_feed",
        source_version="1",
        authority=evidence.EvidenceAuthority.EXTERNAL_ORIGIN,
    )

    with pytest.raises(TypeError, match="factory-created"):
        evidence.EvidenceContractAuthorization()
    with pytest.raises(TypeError, match="construction is private"):
        evidence.EvidenceContractAuthorization._create(
            authorization_id="governed_measurement",
            authorization_version="1",
            contract_definition=definition,
            authorized_source=source,
            authority=evidence.EvidenceAuthority.EXTERNAL_ORIGIN,
            seal=object(),
        )


def test_governed_approval_source_is_private_closed_and_not_replaceable_from_root() -> (
    None
):
    authorization = import_module("market_platform.evidence.authorization")
    models = import_module("market_platform.evidence.models")
    private_names = {
        "_EvidenceAuthorizationApprovalCatalog",
        "_GOVERNED_EVIDENCE_AUTHORIZATION_CATALOG",
        "_create_evidence_contract_authorization_record",
        "_resolve_governed_evidence_contract_authorization",
    }

    assert authorization._GOVERNED_EVIDENCE_AUTHORIZATION_CATALOG.authorizations == ()
    assert private_names.isdisjoint(authorization.__all__)
    assert all(not hasattr(evidence, name) for name in private_names)
    assert all(
        value is not authorization._GOVERNED_EVIDENCE_AUTHORIZATION_CATALOG
        for value in vars(evidence).values()
    )
    assert all(
        value is not authorization._resolve_governed_evidence_contract_authorization
        for value in vars(evidence).values()
    )
    artifact_parameters = inspect.signature(models._create_evidence_artifact).parameters
    assert FORBIDDEN_GOVERNANCE_PARAMETERS.isdisjoint(artifact_parameters)


def test_root_operations_accept_no_catalog_registry_issuer_or_test_bypass() -> None:
    for name in evidence.__all__:
        value = getattr(evidence, name)
        if inspect.isfunction(value):
            parameters = inspect.signature(value).parameters
            assert FORBIDDEN_GOVERNANCE_PARAMETERS.isdisjoint(parameters), name


def test_test_only_governance_helpers_do_not_escape_test_support() -> None:
    production_modules = tuple(
        import_module(module_name) for module_name in PUBLIC_EXPORTS_BY_MODULE
    )

    assert all(not hasattr(evidence, name) for name in TEST_ONLY_GOVERNANCE_NAMES)
    assert all(
        name not in module.__all__
        for module in production_modules
        for name in TEST_ONLY_GOVERNANCE_NAMES
    )


def test_root_api_does_not_expose_generic_evidence_minting() -> None:
    models = import_module("market_platform.evidence.models")

    assert "create_evidence_artifact" not in evidence.__all__
    assert not hasattr(evidence, "create_evidence_artifact")
    assert "_create_evidence_artifact" not in models.__all__
    assert all(
        value is not _create_evidence_artifact for value in vars(evidence).values()
    )
    with pytest.raises(TypeError, match="factory-created"):
        evidence.EvidenceArtifact()


def test_admission_state_is_a_non_fabricable_detached_read_model() -> None:
    state_fields = {field.name for field in fields(evidence.EvidenceAdmissionState)}

    assert "full_record_resolution" not in state_fields
    assert "aggregate_fingerprint" not in state_fields
    assert "fingerprint" not in state_fields
    assert {
        "artifact_reference",
        "ruleset_reference",
        "required_validation_requirements",
        "selected_validation_record_references",
        "admission_freshness_evaluation_reference",
        "task_freshness_evaluation_reference",
        "selected_admission_record_reference",
        "selected_validity_reference",
        "knowledge_as_of",
        "effective_as_of",
    } <= state_fields
    with pytest.raises(TypeError, match="factory-created"):
        evidence.EvidenceAdmissionState()
    with pytest.raises(TypeError, match="unexpected keyword argument"):
        evidence.EvidenceAdmissionState(
            disposition=evidence.EvidenceAdmissionDisposition.ADMITTED,
            full_record_resolution=True,
        )


def test_information_classification_root_contract_is_exact() -> None:
    assert tuple(
        (information_class.name, information_class.value)
        for information_class in evidence.EvidenceInformationClass
    ) == (
        ("SOURCE_OBSERVATION", "source_observation"),
        ("SOURCE_MEASUREMENT", "source_measurement"),
        ("SOURCE_ASSERTION", "source_assertion"),
    )
    assert tuple(
        (authority.name, authority.value) for authority in evidence.EvidenceAuthority
    ) == (
        ("PLATFORM_ORIGIN", "platform_origin"),
        ("EXTERNAL_ORIGIN", "external_origin"),
    )


def test_post_5h_reference_contracts_retain_semantic_correspondence() -> None:
    source_fields = {field.name for field in fields(evidence.EvidenceSourceReference)}
    contract_fields = {
        field.name for field in fields(evidence.EvidenceContractReference)
    }
    artifact_reference_fields = {
        field.name for field in fields(evidence.EvidenceArtifactReference)
    }
    artifact_fields = {field.name for field in fields(evidence.EvidenceArtifact)}

    assert evidence.EVIDENCE_SOURCE_REFERENCE_SCHEMA_VERSION.endswith("/v2")
    assert evidence.EVIDENCE_CONTRACT_REFERENCE_SCHEMA_VERSION.endswith("/v2")
    assert evidence.EVIDENCE_ARTIFACT_REFERENCE_SCHEMA_VERSION.endswith("/v2")
    assert evidence.EVIDENCE_ARTIFACT_SCHEMA_VERSION.endswith("/v3")
    assert "authority" in source_fields
    assert "information_class" in contract_fields
    assert {"information_class", "authority"} <= artifact_reference_fields
    assert {"information_class", "authority"} <= artifact_fields
    assert "contract_authorization" in artifact_fields


def test_validation_requirement_root_contract_is_exact_and_policy_bound() -> None:
    requirement_fields = tuple(
        field.name for field in fields(evidence.EvidenceValidationRequirement)
    )
    ruleset_fields = {field.name for field in fields(evidence.EvidenceAdmissionRuleSet)}

    assert evidence.EVIDENCE_VALIDATION_REQUIREMENT_SCHEMA_VERSION == (
        "evidence_validation_requirement/v1"
    )
    assert requirement_fields == (
        "concern",
        "scope",
        "ruleset_id",
        "ruleset_version",
        "schema_version",
        "fingerprint",
    )
    assert "mandatory_validation_requirements" in ruleset_fields
    assert "mandatory_validation_concerns" not in ruleset_fields


def test_validity_and_policy_contracts_are_public() -> None:
    assert set(evidence.__all__) >= VALIDITY_AND_POLICY_EXPORTS


def test_validity_root_api_binds_only_the_v3_event_contract() -> None:
    validity = import_module("market_platform.evidence.validity")

    assert evidence.EVIDENCE_VALIDITY_EVENT_SCHEMA_VERSION == (
        "evidence_validity_event/v3"
    )
    assert evidence.EvidenceValidityEvent is validity.EvidenceValidityEvent
    assert "capability_identity" in {
        field.name for field in fields(evidence.EvidenceValidityEvent)
    }
    assert "actor_identity" in {
        field.name for field in fields(evidence.EvidenceValidityEvent)
    }
    assert "predecessor_validity_event_reference" in {
        field.name for field in fields(evidence.EvidenceValidityEvent)
    }


def test_validation_root_api_includes_source_quality() -> None:
    validation = import_module("market_platform.evidence.validation")

    assert evidence.EvidenceValidationConcern is (validation.EvidenceValidationConcern)
    assert evidence.EvidenceValidationConcern.SOURCE_QUALITY.value == ("source_quality")


def test_admission_root_api_binds_only_direct_predecessor_lineage() -> None:
    admission_fields = {
        field.name for field in fields(evidence.EvidenceAdmissionRecord)
    }

    assert {
        "deciding_actor_identity",
        "deciding_capability_identity",
        "predecessor_admission_record_reference",
    } <= admission_fields
    assert OBSOLETE_ROOT_EXPORTS.isdisjoint(evidence.__all__)
    assert all(not hasattr(evidence, name) for name in OBSOLETE_ROOT_EXPORTS)


def test_supersession_lifecycle_contracts_are_public() -> None:
    assert set(evidence.__all__) >= SUPERSESSION_EXPORTS
    assert issubclass(evidence.EvidenceArtifactSupersessionResolutionError, ValueError)


def test_reference_only_evaluator_is_not_a_root_api() -> None:
    admission = import_module("market_platform.evidence.admission")
    weak_evaluator = admission.evaluate_evidence_admission_state

    assert hasattr(admission, "evaluate_evidence_admission_state")
    assert "evaluate_evidence_admission_state" not in evidence.__all__
    assert not hasattr(evidence, "evaluate_evidence_admission_state")
    assert all(value is not weak_evaluator for value in vars(evidence).values())


def test_full_record_evaluator_is_the_only_root_admission_evaluation_path() -> None:
    parameters = inspect.signature(
        evidence.evaluate_evidence_admission_as_of
    ).parameters

    assert tuple(parameters) == (
        "artifact",
        "admission_scope",
        "validation_records",
        "freshness_evaluations",
        "admission_records",
        "validity_events",
        "admission_ruleset",
        "knowledge_as_of",
        "effective_as_of",
    )
    assert all(
        parameter.default is inspect.Parameter.empty
        for parameter in parameters.values()
    )


def test_root_has_no_unlisted_public_evidence_callable_aliases() -> None:
    aliases = {
        name
        for name, value in vars(evidence).items()
        if not name.startswith("_")
        and callable(value)
        and getattr(value, "__module__", "").startswith("market_platform.evidence")
        and name not in evidence.__all__
    }

    assert aliases == set()


def test_public_contracts_do_not_expose_forbidden_semantics() -> None:
    exposed_fields: set[str] = set()
    exposed_parameters: set[str] = set()
    for name in evidence.__all__:
        value = getattr(evidence, name)
        if isinstance(value, type) and is_dataclass(value):
            exposed_fields.update(field.name for field in fields(value))
        elif inspect.isfunction(value):
            exposed_parameters.update(inspect.signature(value).parameters)

    assert FORBIDDEN_SEMANTIC_FIELDS.isdisjoint(exposed_fields)
    assert FORBIDDEN_SEMANTIC_FIELDS.isdisjoint(exposed_parameters)
    normalized_exports = {name.replace("_", "").lower() for name in evidence.__all__}
    assert all(
        fragment not in export_name
        for fragment in FORBIDDEN_PUBLIC_NAME_FRAGMENTS
        for export_name in normalized_exports
    )


def test_public_lifecycle_contracts_preserve_separate_semantic_lanes() -> None:
    provenance_fields = {field.name for field in fields(evidence.EvidenceProvenance)}
    supersession_fields = {
        field.name for field in fields(evidence.EvidenceArtifactSupersessionLink)
    }
    validity_fields = {field.name for field in fields(evidence.EvidenceValidityEvent)}
    admission_state_fields = {
        field.name for field in fields(evidence.EvidenceAdmissionState)
    }
    admission_parameters = inspect.signature(
        evidence.evaluate_evidence_admission_as_of
    ).parameters
    supersession_parameters = inspect.signature(
        evidence.resolve_evidence_artifact_supersession_as_of
    ).parameters

    assert "predecessors" in provenance_fields
    assert {
        "predecessor_artifact_reference",
        "successor_artifact_reference",
        "scope",
        "recorded_at",
        "effective_at",
    } <= supersession_fields
    assert "status" in validity_fields
    assert "status" not in supersession_fields
    assert "SUPERSEDED" not in {
        status.value for status in evidence.EvidenceValidityStatus
    }
    assert "SUPERSEDED" not in {
        disposition.value for disposition in evidence.EvidenceAdmissionDisposition
    }
    assert "supersession_links" not in admission_parameters
    assert "supersession_links" in supersession_parameters
    assert "resolved_artifact_reference" not in admission_state_fields
    assert "fingerprint" not in admission_state_fields
    assert "predecessor_validity_event_reference" in validity_fields
    assert "predecessor_admission_record_reference" in {
        field.name for field in fields(evidence.EvidenceAdmissionRecord)
    }


def test_public_api_represents_the_complete_evidence_lifecycle() -> None:
    required_contracts = {
        "EvidenceMaterialSchemaReference",
        "EvidenceContractDefinition",
        "EvidenceContractAuthorization",
        "EvidenceArtifact",
        "EvidenceValidationRecord",
        "EvidenceAdmissionRuleSet",
        "EvidenceAdmissionRecord",
        "EvidenceAdmissionState",
        "EvidenceValidityEvent",
        "EvidenceFreshnessEvaluationRecord",
        "create_evidence_validation_record",
        "create_evidence_admission_record",
        "create_evidence_validity_event",
        "create_evidence_freshness_evaluation_record",
        "evaluate_evidence_admission_as_of",
        "EvidenceArtifactSupersessionLink",
        "EvidenceArtifactSupersessionResolution",
        "create_evidence_artifact_supersession_link",
        "resolve_evidence_artifact_supersession_as_of",
    }

    assert required_contracts <= set(evidence.__all__)


def test_root_api_evaluates_complete_evidence_lifecycle_as_of() -> None:
    scope = "specialist.market_quote"
    published_at = datetime(2026, 8, 25, 20, tzinfo=UTC)
    source = evidence.EvidenceSourceReference(
        namespace="external_source",
        source_id="market_feed",
        source_version="1",
        authority=evidence.EvidenceAuthority.EXTERNAL_ORIGIN,
    )
    actor = evidence.EvidenceIdentityReference(
        namespace="actor",
        identity_id="evidence_reviewer",
        identity_version="1",
    )
    capability = evidence.EvidenceIdentityReference(
        namespace="capability",
        identity_id="evidence_foundation",
        identity_version="1",
    )
    artifact = _create_evidence_artifact(
        artifact_id="market.quote.spy.2026-08-25",
        artifact_version="1",
        evidence_type="market_quote",
        subjects=(
            evidence.EvidenceSubjectReference(
                namespace="instrument",
                subject_id="SPY",
                subject_version="1",
            ),
        ),
        temporal_identity=evidence.EvidenceTemporalIdentity(
            observed_at=published_at,
            published_at=published_at,
            platform_received_at=datetime(2026, 8, 25, 20, 0, 1, tzinfo=UTC),
            artifact_created_at=datetime(2026, 8, 25, 20, 0, 2, tzinfo=UTC),
        ),
        provenance=evidence.EvidenceProvenance(
            origin=source,
            producer=evidence.EvidenceIdentityReference(
                namespace="producer",
                identity_id="market_feed_adapter",
                identity_version="1",
            ),
            source_references=(source,),
        ),
        governing_contract=evidence.EvidenceContractReference(
            namespace="evidence_contract",
            contract_id="market_quote",
            contract_version="1",
            information_class=evidence.EvidenceInformationClass.SOURCE_MEASUREMENT,
        ),
        material_schema_version="market_quote/v1",
        material_fingerprint="sha256:" + ("0" * 64),
    )
    freshness_rule = evidence.EvidenceFreshnessRule(
        rule_id="market_quote_max_age",
        rule_version="1",
        declared_temporal_anchor="published_at",
        evaluation_scope=scope,
    )
    concerns = tuple(
        sorted(
            (
                evidence.EvidenceValidationConcern.IDENTITY,
                evidence.EvidenceValidationConcern.INTEGRITY,
                evidence.EvidenceValidationConcern.PROVENANCE,
                evidence.EvidenceValidationConcern.AUTHORITY,
                evidence.EvidenceValidationConcern.SCHEMA,
                evidence.EvidenceValidationConcern.TEMPORAL_COHERENCE,
                evidence.EvidenceValidationConcern.FRESHNESS_CONTRACT,
            ),
            key=lambda concern: concern.value,
        )
    )
    ruleset = evidence.EvidenceAdmissionRuleSet(
        ruleset_id="market_quote_admission",
        ruleset_version="1",
        admission_scope=scope,
        mandatory_validation_requirements=tuple(
            evidence.EvidenceValidationRequirement(
                concern=concern,
                scope=scope,
                ruleset_id="market_quote_validation",
                ruleset_version="1",
            )
            for concern in concerns
        ),
        admission_freshness_required=True,
        admission_freshness_rule=freshness_rule,
        task_freshness_required=True,
        task_freshness_rule=freshness_rule,
        active_validity_required=True,
    )
    validations = tuple(
        evidence.create_evidence_validation_record(
            validation_record_id=f"validation.{concern.value}.1",
            artifact_reference=artifact.reference(),
            concern=concern,
            scope=scope,
            disposition=evidence.EvidenceValidationDisposition.PASSED,
            validator_identity=actor,
            validator_capability_identity=capability,
            ruleset_id="market_quote_validation",
            ruleset_version="1",
            recorded_at=datetime(2026, 8, 25, 20, 1, tzinfo=UTC),
            effective_at=datetime(2026, 8, 25, 20, 1, tzinfo=UTC),
            findings=("Mandatory foundation concern passed.",),
        )
        for concern in concerns
    )
    admission_freshness = evidence.create_evidence_freshness_evaluation_record(
        artifact=artifact,
        freshness_rule=freshness_rule,
        evaluation_as_of=datetime(2026, 8, 25, 20, 5, tzinfo=UTC),
        result=True,
        findings=("Admission-time freshness passed.",),
    )
    admission = evidence.create_evidence_admission_record(
        admission_record_id="admission.market.quote.spy.1",
        artifact_reference=artifact.reference(),
        admission_ruleset=ruleset,
        selected_validation_record_references=tuple(
            record.reference() for record in validations
        ),
        admission_freshness_evaluation_reference=admission_freshness.reference(),
        deciding_actor_identity=actor,
        deciding_capability_identity=capability,
        disposition=evidence.EvidenceAdmissionDisposition.ADMITTED,
        recorded_at=datetime(2026, 8, 25, 20, 6, tzinfo=UTC),
        effective_at=datetime(2026, 8, 25, 20, 5, 30, tzinfo=UTC),
        findings=("Evidence admitted under the versioned foundation policy.",),
    )
    active = evidence.create_evidence_validity_event(
        validity_event_id="validity.market.quote.spy.active",
        artifact_reference=artifact.reference(),
        status=evidence.EvidenceValidityStatus.ACTIVE,
        recorded_at=datetime(2026, 8, 25, 20, 6, tzinfo=UTC),
        effective_at=datetime(2026, 8, 25, 20, 5, tzinfo=UTC),
        actor_identity=actor,
        capability_identity=capability,
        reason="Evidence is active for the declared scope.",
        scope=scope,
    )
    task_freshness = evidence.create_evidence_freshness_evaluation_record(
        artifact=artifact,
        freshness_rule=freshness_rule,
        evaluation_as_of=datetime(2026, 8, 25, 20, 10, tzinfo=UTC),
        result=True,
        findings=("Task-time freshness passed.",),
    )

    state = evidence.evaluate_evidence_admission_as_of(
        artifact=artifact,
        admission_scope=scope,
        validation_records=validations,
        freshness_evaluations=(admission_freshness, task_freshness),
        admission_records=(admission,),
        validity_events=(active,),
        admission_ruleset=ruleset,
        knowledge_as_of=datetime(2026, 8, 25, 20, 10, tzinfo=UTC),
        effective_as_of=datetime(2026, 8, 25, 20, 10, tzinfo=UTC),
    )
    rejected_successor = evidence.create_evidence_admission_record(
        admission_record_id="admission.market.quote.spy.2",
        artifact_reference=artifact.reference(),
        admission_ruleset=ruleset,
        selected_validation_record_references=tuple(
            record.reference() for record in validations
        ),
        admission_freshness_evaluation_reference=admission_freshness.reference(),
        deciding_actor_identity=actor,
        deciding_capability_identity=capability,
        disposition=evidence.EvidenceAdmissionDisposition.REJECTED,
        recorded_at=datetime(2026, 8, 25, 20, 11, tzinfo=UTC),
        effective_at=datetime(2026, 8, 25, 20, 11, tzinfo=UTC),
        findings=("Later admission decision rejected.",),
        predecessor=admission,
    )
    revoked_successor = evidence.create_evidence_validity_event(
        validity_event_id="validity.market.quote.spy.revoked",
        artifact_reference=artifact.reference(),
        status=evidence.EvidenceValidityStatus.REVOKED,
        recorded_at=datetime(2026, 8, 25, 20, 11, tzinfo=UTC),
        effective_at=datetime(2026, 8, 25, 20, 11, tzinfo=UTC),
        actor_identity=actor,
        capability_identity=capability,
        reason="Later validity event revoked the artifact.",
        scope=scope,
        predecessor=active,
    )

    assert state.is_consumable
    assert state.artifact_reference == artifact.reference()
    assert state.ruleset_reference == ruleset.reference()
    assert state.selected_validation_record_references == tuple(
        record.reference() for record in validations
    )
    assert state.admission_freshness_evaluation_reference == (
        admission_freshness.reference()
    )
    assert state.task_freshness_evaluation_reference == task_freshness.reference()
    assert state.selected_admission_record_reference == admission.reference()
    assert state.selected_validity_reference == active.reference()
    assert rejected_successor.predecessor_admission_record_reference == (
        admission.reference()
    )
    assert revoked_successor.predecessor_validity_event_reference == active.reference()


def test_root_artifact_supersession_does_not_change_consumability_semantics() -> None:
    first = _root_artifact("1", material_digit="1")
    second = _root_artifact(
        "2",
        material_digit="2",
        predecessors=(first.reference(),),
    )
    link = evidence.create_evidence_artifact_supersession_link(
        supersession_link_id="supersession.market.quote.spy.v1-v2",
        predecessor_artifact_reference=first.reference(),
        successor_artifact_reference=second.reference(),
        scope="specialist.market_quote",
        reason="A source revision superseded the earlier artifact.",
        recorded_at=datetime(2026, 8, 25, 21, 1, tzinfo=UTC),
        effective_at=datetime(2026, 8, 25, 21, tzinfo=UTC),
        responsible_actor_identity=evidence.EvidenceIdentityReference(
            namespace="actor",
            identity_id="evidence_curator",
            identity_version="1",
        ),
    )

    resolution = evidence.resolve_evidence_artifact_supersession_as_of(
        artifact_reference=first.reference(),
        scope="specialist.market_quote",
        artifact_references=(first.reference(), second.reference()),
        supersession_links=(link,),
        knowledge_as_of=datetime(2026, 8, 25, 22, tzinfo=UTC),
        effective_as_of=datetime(2026, 8, 25, 22, tzinfo=UTC),
    )

    assert second.provenance.predecessors == (first.reference(),)
    assert resolution.resolved_artifact_reference == second.reference()
    assert not hasattr(link, "status")
    assert (
        "supersession_links"
        not in inspect.signature(evidence.evaluate_evidence_admission_as_of).parameters
    )


def _root_artifact(
    version: str,
    *,
    material_digit: str,
    predecessors: tuple[evidence.EvidenceArtifactReference, ...] = (),
) -> evidence.EvidenceArtifact:
    source = evidence.EvidenceSourceReference(
        namespace="external_source",
        source_id="market_feed",
        source_version="1",
        authority=evidence.EvidenceAuthority.EXTERNAL_ORIGIN,
    )
    return _create_evidence_artifact(
        artifact_id="market.quote.spy",
        artifact_version=version,
        evidence_type="market_quote",
        subjects=(
            evidence.EvidenceSubjectReference(
                namespace="instrument",
                subject_id="SPY",
                subject_version="1",
            ),
        ),
        temporal_identity=evidence.EvidenceTemporalIdentity(
            observed_at=datetime(2026, 8, 25, 20, tzinfo=UTC),
            platform_received_at=datetime(2026, 8, 25, 20, 1, tzinfo=UTC),
            artifact_created_at=datetime(2026, 8, 25, 20, 2, tzinfo=UTC),
        ),
        provenance=evidence.EvidenceProvenance(
            origin=source,
            producer=evidence.EvidenceIdentityReference(
                namespace="producer",
                identity_id="market_feed_adapter",
                identity_version="1",
            ),
            source_references=(source,),
            predecessors=predecessors,
        ),
        governing_contract=evidence.EvidenceContractReference(
            namespace="evidence_contract",
            contract_id="market_quote",
            contract_version="1",
            information_class=evidence.EvidenceInformationClass.SOURCE_MEASUREMENT,
        ),
        material_schema_version="market_quote/v1",
        material_fingerprint="sha256:" + (material_digit * 64),
    )


def test_evidence_has_no_forbidden_boundary_imports() -> None:
    assert evidence.__file__ is not None
    package_directory = Path(evidence.__file__).resolve().parent
    violations: list[tuple[str, str]] = []

    for source_path in sorted(package_directory.rglob("*.py")):
        tree = ast.parse(source_path.read_text(encoding="utf-8"), source_path.name)
        for imported_name in _imported_names(tree):
            if FORBIDDEN_DEPENDENCY_SEGMENTS.intersection(imported_name.split(".")):
                violations.append(
                    (str(source_path.relative_to(package_directory)), imported_name)
                )

    assert violations == []


def _imported_names(tree: ast.AST) -> tuple[str, ...]:
    imported_names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module_name = node.module or ""
            imported_names.extend(
                ".".join(part for part in (module_name, alias.name) if part)
                for alias in node.names
            )
    return tuple(imported_names)
