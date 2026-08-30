from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from inspect import signature

import pytest
from evidence_test_support import (
    create_governed_test_artifact as _create_evidence_artifact,
)

from market_platform._fingerprint import canonical_fingerprint
from market_platform.evidence.admission import (
    EVIDENCE_ADMISSION_RECORD_SCHEMA_VERSION,
    EVIDENCE_ADMISSION_STATE_SCHEMA_VERSION,
    EvidenceAdmissionDisposition,
    EvidenceAdmissionRecord,
    EvidenceAdmissionState,
    create_evidence_admission_record,
    evaluate_evidence_admission_state,
)
from market_platform.evidence.classification import (
    EvidenceAuthority,
    EvidenceInformationClass,
)
from market_platform.evidence.models import (
    EvidenceProvenance,
    EvidenceTemporalIdentity,
)
from market_platform.evidence.policy import (
    EvidenceAdmissionRuleSet,
    EvidenceValidationRequirement,
)
from market_platform.evidence.references import (
    EvidenceContractReference,
    EvidenceIdentityReference,
    EvidenceSourceReference,
    EvidenceSubjectReference,
)
from market_platform.evidence.temporal import (
    EvidenceFreshnessRule,
    create_evidence_freshness_evaluation_record,
)
from market_platform.evidence.validation import (
    EvidenceValidationConcern,
    EvidenceValidationDisposition,
    create_evidence_validation_record,
)

_SCOPE = "specialist.market_quote"
_CONCERNS = tuple(
    sorted(
        (
            EvidenceValidationConcern.IDENTITY,
            EvidenceValidationConcern.INTEGRITY,
            EvidenceValidationConcern.PROVENANCE,
            EvidenceValidationConcern.AUTHORITY,
            EvidenceValidationConcern.SCHEMA,
            EvidenceValidationConcern.TEMPORAL_COHERENCE,
            EvidenceValidationConcern.FRESHNESS_CONTRACT,
        ),
        key=lambda concern: concern.value,
    )
)


def _artifact():
    origin = EvidenceSourceReference(
        namespace="external_source",
        source_id="provider",
        source_version="1",
        authority=EvidenceAuthority.EXTERNAL_ORIGIN,
    )
    return _create_evidence_artifact(
        artifact_id="quote.spy.2026-08-25",
        artifact_version="1",
        evidence_type="market_quote",
        subjects=(
            EvidenceSubjectReference(
                namespace="instrument",
                subject_id="SPY",
                subject_version="1",
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
                identity_id="adapter",
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
        material_schema_version="market_quote/v1",
        material_fingerprint=canonical_fingerprint(
            {"schema_version": "market_quote/v1", "price": "650"}
        ),
    )


def _rule() -> EvidenceFreshnessRule:
    return EvidenceFreshnessRule(
        rule_id="quote_max_age",
        rule_version="1",
        declared_temporal_anchor="published_at",
        evaluation_scope=_SCOPE,
    )


def _ruleset(
    *,
    concerns: tuple[EvidenceValidationConcern, ...] = _CONCERNS,
    admission_freshness_required: bool = True,
    task_freshness_required: bool = True,
    active_validity_required: bool = True,
) -> EvidenceAdmissionRuleSet:
    rule = _rule()
    return EvidenceAdmissionRuleSet(
        ruleset_id="market_quote_admission",
        ruleset_version="1",
        admission_scope=_SCOPE,
        mandatory_validation_requirements=tuple(
            EvidenceValidationRequirement(
                concern=concern,
                scope=_SCOPE,
                ruleset_id="quote_validation",
                ruleset_version="1",
            )
            for concern in concerns
        ),
        admission_freshness_required=admission_freshness_required,
        admission_freshness_rule=(rule if admission_freshness_required else None),
        task_freshness_required=task_freshness_required,
        task_freshness_rule=rule if task_freshness_required else None,
        active_validity_required=active_validity_required,
    )


def _validation(
    artifact,
    concern: EvidenceValidationConcern,
    *,
    ruleset_id: str = "quote_validation",
    ruleset_version: str = "1",
):
    return create_evidence_validation_record(
        validation_record_id=f"validation.{concern.value}.1",
        artifact_reference=artifact.reference(),
        concern=concern,
        scope=_SCOPE,
        disposition=EvidenceValidationDisposition.PASSED,
        validator_identity=EvidenceIdentityReference(
            namespace="actor",
            identity_id="validator",
            identity_version="1",
        ),
        ruleset_id=ruleset_id,
        ruleset_version=ruleset_version,
        recorded_at=datetime(2026, 8, 25, 20, 1, tzinfo=UTC),
        effective_at=datetime(2026, 8, 25, 20, 1, tzinfo=UTC),
        findings=("Concern passed.",),
    )


def _freshness(artifact, *, as_of: datetime, result: bool = True):
    return create_evidence_freshness_evaluation_record(
        artifact=artifact,
        freshness_rule=_rule(),
        evaluation_as_of=as_of,
        result=result,
        findings=("Freshness evaluated.",),
    )


def _admission(artifact, *, ruleset: EvidenceAdmissionRuleSet | None = None):
    policy = _ruleset() if ruleset is None else ruleset
    validations = tuple(_validation(artifact, concern) for concern in _CONCERNS)
    admission_freshness = _freshness(
        artifact,
        as_of=datetime(2026, 8, 25, 20, 5, tzinfo=UTC),
    )
    return create_evidence_admission_record(
        admission_record_id="admission.quote.spy.1",
        artifact_reference=artifact.reference(),
        admission_ruleset=policy,
        selected_validation_record_references=tuple(
            record.reference() for record in validations
        ),
        admission_freshness_evaluation_reference=admission_freshness.reference(),
        deciding_actor_identity=EvidenceIdentityReference(
            namespace="actor",
            identity_id="admission_reviewer",
            identity_version="1",
        ),
        deciding_capability_identity=EvidenceIdentityReference(
            namespace="capability",
            identity_id="evidence_admission",
            identity_version="1",
        ),
        disposition=EvidenceAdmissionDisposition.ADMITTED,
        recorded_at=datetime(2026, 8, 25, 20, 6, tzinfo=UTC),
        effective_at=datetime(2026, 8, 25, 20, 5, 30, tzinfo=UTC),
        findings=("Admission prerequisites passed.",),
    )


def test_ruleset_is_bounded_immutable_and_deterministic() -> None:
    ruleset = _ruleset()

    assert ruleset.mandatory_validation_concerns == _CONCERNS
    assert ruleset.fingerprint == _ruleset().fingerprint
    assert ruleset.reference().ruleset_fingerprint == ruleset.fingerprint
    with pytest.raises(FrozenInstanceError):
        ruleset.ruleset_version = "2"  # type: ignore[misc]
    with pytest.raises(ValueError, match="must not be empty"):
        _ruleset(concerns=())
    with pytest.raises(TypeError, match="exact tuple"):
        EvidenceAdmissionRuleSet(
            ruleset_id=ruleset.ruleset_id,
            ruleset_version=ruleset.ruleset_version,
            admission_scope=ruleset.admission_scope,
            mandatory_validation_requirements={},  # type: ignore[arg-type]
            admission_freshness_required=True,
            admission_freshness_rule=_rule(),
            task_freshness_required=True,
            task_freshness_rule=_rule(),
            active_validity_required=True,
        )
    with pytest.raises(ValueError, match="present exactly when required"):
        EvidenceAdmissionRuleSet(
            ruleset_id="invalid",
            ruleset_version="1",
            admission_scope=_SCOPE,
            mandatory_validation_requirements=_ruleset().mandatory_validation_requirements,
            admission_freshness_required=True,
            admission_freshness_rule=None,
            task_freshness_required=True,
            task_freshness_rule=_rule(),
            active_validity_required=True,
        )


def test_full_evaluator_policy_cannot_be_weakened_by_ad_hoc_parameters() -> None:
    from market_platform.evidence.evaluation import evaluate_evidence_admission_as_of

    parameters = signature(evaluate_evidence_admission_as_of).parameters

    assert "admission_ruleset" in parameters
    assert "artifact" in parameters
    assert "artifact_reference" not in parameters
    assert "required_validation_concerns" not in parameters
    assert "freshness_required" not in parameters


def test_admitted_record_cannot_downgrade_policy_requirements() -> None:
    artifact = _artifact()
    ruleset = _ruleset()
    identity = _validation(artifact, EvidenceValidationConcern.IDENTITY)
    actor = EvidenceIdentityReference(
        namespace="actor",
        identity_id="reviewer",
        identity_version="1",
    )
    common = {
        "admission_record_id": "admission.invalid",
        "artifact_reference": artifact.reference(),
        "admission_ruleset": ruleset,
        "selected_validation_record_references": (identity.reference(),),
        "admission_freshness_evaluation_reference": None,
        "deciding_actor_identity": actor,
        "disposition": EvidenceAdmissionDisposition.ADMITTED,
        "recorded_at": datetime(2026, 8, 25, 20, 6, tzinfo=UTC),
        "effective_at": datetime(2026, 8, 25, 20, 5, tzinfo=UTC),
        "findings": ("Attempted admission.",),
    }

    with pytest.raises(ValueError, match="exact mandatory concern set"):
        create_evidence_admission_record(**common)  # type: ignore[arg-type]
    common["selected_validation_record_references"] = tuple(
        _validation(artifact, concern).reference() for concern in _CONCERNS
    )
    with pytest.raises(ValueError, match="freshness is missing"):
        create_evidence_admission_record(**common)  # type: ignore[arg-type]


def test_admission_binds_actor_capability_ruleset_and_historical_freshness() -> None:
    artifact = _artifact()
    record = _admission(artifact)
    retained_reference = record.admission_freshness_evaluation_reference
    later = _freshness(
        artifact,
        as_of=datetime(2026, 8, 25, 21, tzinfo=UTC),
        result=False,
    )

    assert record.deciding_actor_identity.identity_id == "admission_reviewer"
    assert record.deciding_capability_identity is not None
    assert record.deciding_capability_identity.identity_id == "evidence_admission"
    assert record.admission_ruleset_reference == _ruleset().reference()
    assert record.admission_freshness_evaluation_reference == retained_reference
    assert later.reference() != retained_reference
    assert record.schema_version == "evidence_admission_record/v3"
    assert record.schema_version == EVIDENCE_ADMISSION_RECORD_SCHEMA_VERSION
    assert record.fingerprint == _admission(artifact).fingerprint
    with pytest.raises(FrozenInstanceError):
        record.findings = ("mutated",)  # type: ignore[misc]


def test_legacy_reference_only_evaluator_cannot_claim_consumability() -> None:
    artifact = _artifact()
    record = _admission(artifact)
    state = evaluate_evidence_admission_state(
        artifact_reference=artifact.reference(),
        admission_scope=_SCOPE,
        admission_records=(record,),
        required_validation_concerns=(),
        freshness_required=False,
        knowledge_as_of=datetime(2026, 8, 25, 20, 10, tzinfo=UTC),
        effective_as_of=datetime(2026, 8, 25, 20, 10, tzinfo=UTC),
    )

    assert not state.is_admitted
    assert not state.is_consumable
    assert state.ruleset_reference is None
    assert "cannot establish" in state.findings[-1].lower()
    assert EVIDENCE_ADMISSION_STATE_SCHEMA_VERSION == "evidence_admission_state/v3"


def test_admission_contracts_have_no_forbidden_financial_semantics() -> None:
    forbidden = {
        "confidence",
        "market_meaning",
        "ranking",
        "recommendation",
        "strategy",
        "trade_action",
    }

    assert forbidden.isdisjoint(EvidenceAdmissionRuleSet.__dataclass_fields__)
    assert forbidden.isdisjoint(EvidenceAdmissionRecord.__dataclass_fields__)
    assert forbidden.isdisjoint(EvidenceAdmissionState.__dataclass_fields__)


@pytest.mark.parametrize("omitted", _CONCERNS)
def test_ruleset_rejects_every_foundation_concern_downgrade(
    omitted: EvidenceValidationConcern,
) -> None:
    with pytest.raises(ValueError, match=omitted.value):
        _ruleset(concerns=tuple(item for item in _CONCERNS if item is not omitted))


def test_ruleset_rejects_identity_only_and_consumability_flag_downgrades() -> None:
    with pytest.raises(ValueError, match="cannot omit foundation concerns"):
        _ruleset(concerns=(EvidenceValidationConcern.IDENTITY,))
    with pytest.raises(ValueError, match="admission_freshness_required"):
        _ruleset(admission_freshness_required=False)
    with pytest.raises(ValueError, match="task_freshness_required"):
        _ruleset(task_freshness_required=False)
    with pytest.raises(ValueError, match="active_validity_required"):
        _ruleset(active_validity_required=False)


def test_ruleset_allows_stricter_contract_specific_source_quality() -> None:
    stricter = _ruleset(concerns=(*_CONCERNS, EvidenceValidationConcern.SOURCE_QUALITY))

    assert EvidenceValidationConcern.SOURCE_QUALITY in (
        stricter.mandatory_validation_concerns
    )
    assert set(_CONCERNS).issubset(stricter.mandatory_validation_concerns)


def test_contract_specific_source_quality_requirement_is_enforced_at_admission() -> (
    None
):
    artifact = _artifact()
    ruleset = _ruleset(concerns=(*_CONCERNS, EvidenceValidationConcern.SOURCE_QUALITY))
    validations = tuple(
        _validation(artifact, concern)
        for concern in ruleset.mandatory_validation_concerns
    )
    freshness = _freshness(
        artifact,
        as_of=datetime(2026, 8, 25, 20, 5, tzinfo=UTC),
    )

    admitted = create_evidence_admission_record(
        admission_record_id="admission.source.quality",
        artifact_reference=artifact.reference(),
        admission_ruleset=ruleset,
        selected_validation_record_references=tuple(
            record.reference() for record in validations
        ),
        admission_freshness_evaluation_reference=freshness.reference(),
        deciding_actor_identity=EvidenceIdentityReference(
            namespace="actor",
            identity_id="source_quality_reviewer",
            identity_version="1",
        ),
        disposition=EvidenceAdmissionDisposition.ADMITTED,
        recorded_at=datetime(2026, 8, 25, 20, 6, tzinfo=UTC),
        effective_at=datetime(2026, 8, 25, 20, 5, 30, tzinfo=UTC),
        findings=("Contract-defined source-quality conditions passed.",),
    )

    assert EvidenceValidationConcern.SOURCE_QUALITY in {
        reference.concern
        for reference in admitted.selected_validation_record_references
    }


@pytest.mark.parametrize(
    ("ruleset_id", "ruleset_version"),
    (
        ("unrelated_validation_policy", "999"),
        ("quote_validation", "999"),
    ),
)
def test_admission_rejects_wrong_validation_policy_identity(
    ruleset_id: str,
    ruleset_version: str,
) -> None:
    artifact = _artifact()
    policy = _ruleset()
    validations = tuple(
        _validation(
            artifact,
            concern,
            ruleset_id=(
                ruleset_id
                if concern is EvidenceValidationConcern.SCHEMA
                else "quote_validation"
            ),
            ruleset_version=(
                ruleset_version if concern is EvidenceValidationConcern.SCHEMA else "1"
            ),
        )
        for concern in _CONCERNS
    )
    freshness = _freshness(
        artifact,
        as_of=datetime(2026, 8, 25, 20, 5, tzinfo=UTC),
    )

    with pytest.raises(ValueError, match="exact policy requirements"):
        create_evidence_admission_record(
            admission_record_id="admission.wrong.validation.policy",
            artifact_reference=artifact.reference(),
            admission_ruleset=policy,
            selected_validation_record_references=tuple(
                record.reference() for record in validations
            ),
            admission_freshness_evaluation_reference=freshness.reference(),
            deciding_actor_identity=EvidenceIdentityReference(
                namespace="actor",
                identity_id="admission_reviewer",
                identity_version="1",
            ),
            disposition=EvidenceAdmissionDisposition.ADMITTED,
            recorded_at=datetime(2026, 8, 25, 20, 6, tzinfo=UTC),
            effective_at=datetime(2026, 8, 25, 20, 5, 30, tzinfo=UTC),
            findings=("Attempted unrelated validation policy admission.",),
        )


def test_ruleset_retains_exact_typed_validation_requirements() -> None:
    ruleset = _ruleset()
    schema = next(
        requirement
        for requirement in ruleset.mandatory_validation_requirements
        if requirement.concern is EvidenceValidationConcern.SCHEMA
    )

    assert schema.scope == _SCOPE
    assert schema.ruleset_id == "quote_validation"
    assert schema.ruleset_version == "1"
    assert schema.to_dict()["fingerprint"] == schema.fingerprint
    assert ruleset.to_dict()["mandatory_validation_requirements"]
