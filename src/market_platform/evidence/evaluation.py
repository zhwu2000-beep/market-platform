"""Deterministic full-record as-of evaluation for Evidence admission."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from market_platform.evidence.admission import (
    EvidenceAdmissionDisposition,
    EvidenceAdmissionRecord,
    EvidenceAdmissionRecordReference,
    EvidenceAdmissionState,
    _create_evidence_admission_state_from_resolution,
)
from market_platform.evidence.models import EvidenceArtifact
from market_platform.evidence.policy import (
    EvidenceAdmissionRuleSet,
    EvidenceValidationRequirement,
)
from market_platform.evidence.references import EvidenceArtifactReference
from market_platform.evidence.temporal import (
    EvidenceFreshnessEvaluationRecord,
    _derive_artifact_temporal_values,
)
from market_platform.evidence.validation import (
    EvidenceValidationConcern,
    EvidenceValidationDisposition,
    EvidenceValidationRecord,
    EvidenceValidationRecordReference,
)
from market_platform.evidence.validity import (
    EvidenceValidityEvent,
    EvidenceValidityReference,
    EvidenceValidityStatus,
    _resolve_validity_lineage,
)


def evaluate_evidence_admission_as_of(
    *,
    artifact: EvidenceArtifact,
    admission_scope: str,
    validation_records: tuple[EvidenceValidationRecord, ...],
    freshness_evaluations: tuple[EvidenceFreshnessEvaluationRecord, ...],
    admission_records: tuple[EvidenceAdmissionRecord, ...],
    validity_events: tuple[EvidenceValidityEvent, ...],
    admission_ruleset: EvidenceAdmissionRuleSet,
    knowledge_as_of: datetime,
    effective_as_of: datetime,
) -> EvidenceAdmissionState:
    """Resolve full records under immutable policy and historical cutoffs."""

    if type(artifact) is not EvidenceArtifact:
        raise TypeError("artifact must be an EvidenceArtifact")
    artifact._validate()
    artifact_reference = artifact.reference()
    scope = _visible_ascii(admission_scope, "admission_scope", 256)
    knowledge_cutoff = _timestamp(knowledge_as_of, "knowledge_as_of")
    effective_cutoff = _timestamp(effective_as_of, "effective_as_of")
    if type(admission_ruleset) is not EvidenceAdmissionRuleSet:
        raise TypeError("admission_ruleset must be an EvidenceAdmissionRuleSet")
    admission_ruleset._validate()
    if admission_ruleset.admission_scope != scope:
        raise ValueError("admission_ruleset must bind the requested admission_scope")
    requirements = admission_ruleset.mandatory_validation_requirements
    concerns = admission_ruleset.mandatory_validation_concerns
    validations = _validation_record_tuple(validation_records)
    freshness_records = _freshness_record_tuple(freshness_evaluations)
    admissions = _admission_record_tuple(admission_records)
    validity = _validity_event_tuple(validity_events)

    selected_validations, validation_lineage, validation_failure = _resolve_validations(
        artifact_reference,
        scope,
        validations,
        requirements,
        knowledge_cutoff,
        effective_cutoff,
    )
    selected_admission, admission_lineage, admission_failure = _resolve_admission(
        artifact_reference,
        scope,
        admissions,
        knowledge_cutoff,
        effective_cutoff,
    )

    failures: list[str] = []
    for records, record_kind in (
        (validations, "validation"),
        (freshness_records, "freshness"),
        (admissions, "admission"),
        (validity, "validity"),
    ):
        if any(record.artifact_reference != artifact_reference for record in records):
            failures.append(
                f"Supplied {record_kind} records do not all bind the exact artifact."
            )
    if validation_failure is not None:
        failures.append(validation_failure)
    if admission_failure is not None:
        failures.append(admission_failure)

    admission_freshness: EvidenceFreshnessEvaluationRecord | None = None
    task_freshness: EvidenceFreshnessEvaluationRecord | None = None
    selected_validity: EvidenceValidityEvent | None = None
    validity_lineage: tuple[EvidenceValidityReference, ...] = ()

    if selected_admission is not None:
        if (
            selected_admission.admission_ruleset_reference
            != admission_ruleset.reference()
        ):
            failures.append("Selected admission record does not bind the ruleset.")
        admission_references = {
            reference.concern: reference
            for reference in selected_admission.selected_validation_record_references
        }
        for concern in concerns:
            selected_validation = selected_validations.get(concern)
            if selected_validation is None:
                continue
            if admission_references.get(concern) != selected_validation.reference():
                failures.append(
                    "Admission record does not reference the selected validation "
                    f"record for {concern.value}."
                )
        if set(admission_references) != set(concerns):
            failures.append(
                "Admission record does not retain the exact mandatory concern set."
            )
        if selected_admission.disposition is not EvidenceAdmissionDisposition.ADMITTED:
            failures.append("The selected admission record is rejected.")

        admission_reference = (
            selected_admission.admission_freshness_evaluation_reference
        )
        if admission_ruleset.admission_freshness_required:
            if admission_reference is None:
                failures.append("Required admission-time freshness is missing.")
            else:
                admission_freshness, failure = _resolve_exact_freshness(
                    admission_reference,
                    freshness_records,
                )
                if failure is not None:
                    failures.append(failure)
                elif admission_freshness is not None:
                    admission_rule = admission_ruleset.admission_freshness_rule
                    assert admission_rule is not None
                    if admission_freshness.freshness_rule != admission_rule:
                        failures.append(
                            "Admission-time freshness policy does not match ruleset."
                        )
                    if (
                        admission_freshness.evaluation_as_of
                        > selected_admission.effective_at
                    ):
                        failures.append(
                            "Admission-time freshness is after admission effective_at."
                        )
                    if not admission_freshness.result:
                        failures.append("Admission-time freshness did not pass.")
                    correspondence_failure = _freshness_correspondence_failure(
                        artifact,
                        admission_freshness,
                        "Admission-time",
                    )
                    if correspondence_failure is not None:
                        failures.append(correspondence_failure)
        elif admission_reference is not None:
            failures.append(
                "Admission record retains freshness not permitted by its ruleset."
            )
    elif admission_failure is None:
        failures.append("No effective admission record exists.")

    if admission_ruleset.active_validity_required:
        selected_validity, validity_lineage, failure = _resolve_validity(
            artifact_reference,
            scope,
            validity,
            knowledge_cutoff,
            effective_cutoff,
        )
        if failure is not None:
            failures.append(failure)
        elif (
            selected_validity is None
            or selected_validity.status is not EvidenceValidityStatus.ACTIVE
        ):
            failures.append("Evidence validity is not ACTIVE.")

    if admission_ruleset.task_freshness_required:
        task_rule = admission_ruleset.task_freshness_rule
        assert task_rule is not None
        task_freshness, failure = _resolve_task_freshness(
            artifact_reference,
            freshness_records,
            task_rule.fingerprint,
            task_rule.evaluation_scope,
            knowledge_cutoff,
            effective_cutoff,
        )
        if failure is not None:
            failures.append(failure)
        elif task_freshness is not None and not task_freshness.result:
            failures.append("Task-time freshness did not pass.")
        if task_freshness is not None:
            correspondence_failure = _freshness_correspondence_failure(
                artifact,
                task_freshness,
                "Task-time",
            )
            if correspondence_failure is not None:
                failures.append(correspondence_failure)
    return _resolved_state(
        artifact,
        scope,
        knowledge_cutoff,
        effective_cutoff,
        admission_ruleset,
        selected_admission,
        tuple(
            selected_validations[concern]
            for concern in concerns
            if concern in selected_validations
        ),
        admission_freshness,
        task_freshness,
        selected_validity,
        validation_lineage,
        admission_lineage,
        validity_lineage,
        (
            EvidenceAdmissionDisposition.ADMITTED
            if not failures
            else EvidenceAdmissionDisposition.REJECTED
        ),
        (
            ("All policy-bound records resolved; Evidence is consumable.",)
            if not failures
            else tuple(failures)
        ),
    )


def _resolved_state(
    artifact: EvidenceArtifact,
    admission_scope: str,
    knowledge_as_of: datetime,
    effective_as_of: datetime,
    ruleset: EvidenceAdmissionRuleSet,
    selected_admission: EvidenceAdmissionRecord | None,
    selected_validations: tuple[EvidenceValidationRecord, ...],
    admission_freshness: EvidenceFreshnessEvaluationRecord | None,
    task_freshness: EvidenceFreshnessEvaluationRecord | None,
    selected_validity: EvidenceValidityEvent | None,
    validation_lineage: tuple[EvidenceValidationRecordReference, ...],
    admission_lineage: tuple[EvidenceAdmissionRecordReference, ...],
    validity_lineage: tuple[EvidenceValidityReference, ...],
    disposition: EvidenceAdmissionDisposition,
    findings: tuple[str, ...],
) -> EvidenceAdmissionState:
    return _create_evidence_admission_state_from_resolution(
        artifact=artifact,
        admission_scope=admission_scope,
        knowledge_as_of=knowledge_as_of,
        effective_as_of=effective_as_of,
        ruleset=ruleset,
        disposition=disposition,
        selected_validations=selected_validations,
        admission_freshness=admission_freshness,
        task_freshness=task_freshness,
        selected_admission=selected_admission,
        selected_validity=selected_validity,
        validation_supersession_references=validation_lineage,
        admission_predecessor_references=admission_lineage,
        validity_predecessor_references=validity_lineage,
        findings=findings,
    )


def _resolve_validations(
    artifact_reference: EvidenceArtifactReference,
    scope: str,
    records: tuple[EvidenceValidationRecord, ...],
    requirements: tuple[EvidenceValidationRequirement, ...],
    knowledge_as_of: datetime,
    effective_as_of: datetime,
) -> tuple[
    dict[EvidenceValidationConcern, EvidenceValidationRecord],
    tuple[EvidenceValidationRecordReference, ...],
    str | None,
]:
    selected: dict[EvidenceValidationConcern, EvidenceValidationRecord] = {}
    lineage: list[EvidenceValidationRecordReference] = []
    failures: list[str] = []
    for requirement in requirements:
        concern = requirement.concern
        eligible = tuple(
            record
            for record in records
            if record.artifact_reference == artifact_reference
            and record.scope == requirement.scope == scope
            and record.concern is concern
            and record.ruleset_id == requirement.ruleset_id
            and record.ruleset_version == requirement.ruleset_version
            and record.recorded_at <= knowledge_as_of
            and record.effective_at <= effective_as_of
        )
        winner, concern_lineage, failure = _resolve_validation_concern(
            eligible,
            concern,
        )
        lineage.extend(concern_lineage)
        if winner is not None:
            selected[concern] = winner
        if failure is not None:
            failures.append(failure)
    return (
        selected,
        tuple(sorted(lineage, key=lambda item: item.fingerprint)),
        None if not failures else " ".join(failures),
    )


def _resolve_validation_concern(
    eligible: tuple[EvidenceValidationRecord, ...],
    concern: EvidenceValidationConcern,
) -> tuple[
    EvidenceValidationRecord | None,
    tuple[EvidenceValidationRecordReference, ...],
    str | None,
]:
    if not eligible:
        return None, (), f"Required validation concern is missing: {concern.value}."
    eligible_by_identity = {
        (record.validation_record_id, record.fingerprint): record for record in eligible
    }
    successors: dict[tuple[str, str], tuple[str, str]] = {}
    lineage: list[EvidenceValidationRecordReference] = []
    for record in eligible:
        predecessor = record.predecessor_validation_record_reference
        if predecessor is None:
            continue
        predecessor_identity = (
            predecessor.validation_record_id,
            predecessor.validation_record_fingerprint,
        )
        successor_identity = (record.validation_record_id, record.fingerprint)
        actual_predecessor = eligible_by_identity.get(predecessor_identity)
        if actual_predecessor is None or actual_predecessor.reference() != predecessor:
            return (
                None,
                tuple(sorted(lineage, key=lambda item: item.fingerprint)),
                "Validation supersession has an unresolved predecessor: "
                f"{concern.value}.",
            )
        retained = successors.get(predecessor_identity)
        if retained is not None and retained != successor_identity:
            return (
                None,
                tuple(sorted(lineage, key=lambda item: item.fingerprint)),
                f"Forked validation supersession fails closed: {concern.value}.",
            )
        successors[predecessor_identity] = successor_identity
        lineage.append(actual_predecessor.reference())
    exact_lineage = tuple(sorted(lineage, key=lambda item: item.fingerprint))
    if _has_supersession_cycle(successors):
        return (
            None,
            exact_lineage,
            f"Cyclic validation supersession fails closed: {concern.value}.",
        )
    remaining = tuple(
        record
        for identity, record in eligible_by_identity.items()
        if identity not in successors
    )
    if not remaining:
        return (
            None,
            exact_lineage,
            f"No validation record remains after supersession: {concern.value}.",
        )
    precedence = max((record.effective_at, record.recorded_at) for record in remaining)
    co_precedent = tuple(
        record
        for record in remaining
        if (record.effective_at, record.recorded_at) == precedence
    )
    if len(co_precedent) != 1:
        return (
            None,
            exact_lineage,
            f"Conflicting validation records fail closed: {concern.value}.",
        )
    winner = co_precedent[0]
    if winner.disposition is not EvidenceValidationDisposition.PASSED:
        return (
            winner,
            exact_lineage,
            f"Selected validation concern did not pass: {concern.value}.",
        )
    return winner, exact_lineage, None


def _resolve_exact_freshness(
    reference: object,
    records: tuple[EvidenceFreshnessEvaluationRecord, ...],
) -> tuple[EvidenceFreshnessEvaluationRecord | None, str | None]:
    from market_platform.evidence.temporal import EvidenceFreshnessEvaluationReference

    if type(reference) is not EvidenceFreshnessEvaluationReference:
        return None, "Admission freshness reference is invalid."
    matches = tuple(
        record
        for record in records
        if record.fingerprint == reference.evaluation_fingerprint
    )
    if not matches:
        return None, "Referenced admission-time freshness record is missing."
    if len(matches) != 1:
        return None, "Ambiguous admission-time freshness records fail closed."
    selected = matches[0]
    if selected.reference() != reference:
        return selected, "Admission-time freshness reference mismatch."
    return selected, None


def _resolve_task_freshness(
    artifact_reference: EvidenceArtifactReference,
    records: tuple[EvidenceFreshnessEvaluationRecord, ...],
    rule_fingerprint: str,
    scope: str,
    knowledge_as_of: datetime,
    effective_as_of: datetime,
) -> tuple[EvidenceFreshnessEvaluationRecord | None, str | None]:
    eligible = tuple(
        record
        for record in records
        if record.artifact_reference == artifact_reference
        and record.freshness_rule.fingerprint == rule_fingerprint
        and record.freshness_rule.evaluation_scope == scope
        and record.evaluation_as_of == effective_as_of
        and record.evaluation_as_of <= knowledge_as_of
    )
    if not eligible:
        return None, "Required task-time freshness evaluation is missing."
    if len(eligible) != 1:
        return None, "Conflicting task-time freshness evaluations fail closed."
    return eligible[0], None


def _freshness_correspondence_failure(
    artifact: EvidenceArtifact,
    record: EvidenceFreshnessEvaluationRecord,
    phase: str,
) -> str | None:
    if record.artifact_reference != artifact.reference():
        return f"{phase} freshness does not bind the exact artifact."
    try:
        expected = _derive_artifact_temporal_values(
            artifact,
            record.freshness_rule.declared_temporal_anchor,
        )
    except ValueError as error:
        return f"{phase} freshness artifact anchor is unavailable: {error}"
    if record.evaluated_temporal_values != expected:
        return (
            f"{phase} freshness temporal value does not exactly correspond "
            "to the artifact."
        )
    return None


def _resolve_admission(
    artifact_reference: EvidenceArtifactReference,
    scope: str,
    records: tuple[EvidenceAdmissionRecord, ...],
    knowledge_as_of: datetime,
    effective_as_of: datetime,
) -> tuple[
    EvidenceAdmissionRecord | None,
    tuple[EvidenceAdmissionRecordReference, ...],
    str | None,
]:
    eligible = tuple(
        record
        for record in records
        if record.artifact_reference == artifact_reference
        and record.admission_scope == scope
        and record.recorded_at <= knowledge_as_of
        and record.effective_at <= effective_as_of
    )
    eligible_by_identity = {
        (record.admission_record_id, record.fingerprint): record for record in eligible
    }
    successors: dict[tuple[str, str], tuple[str, str]] = {}
    lineage: list[EvidenceAdmissionRecordReference] = []
    for record in eligible:
        predecessor_reference = record.predecessor_admission_record_reference
        if predecessor_reference is None:
            continue
        predecessor_identity = (
            predecessor_reference.admission_record_id,
            predecessor_reference.admission_record_fingerprint,
        )
        successor_identity = (record.admission_record_id, record.fingerprint)
        predecessor = eligible_by_identity.get(predecessor_identity)
        if predecessor is None or predecessor.reference() != predecessor_reference:
            return (
                None,
                tuple(sorted(lineage, key=lambda item: item.fingerprint)),
                "Admission predecessor lineage has an unresolved predecessor.",
            )
        if predecessor.recorded_at > record.recorded_at:
            return (
                None,
                tuple(sorted(lineage, key=lambda item: item.fingerprint)),
                "Admission predecessor lineage is not append-only.",
            )
        retained_successor = successors.get(predecessor_identity)
        if retained_successor is not None and retained_successor != successor_identity:
            return (
                None,
                tuple(sorted(lineage, key=lambda item: item.fingerprint)),
                "Forked admission predecessor lineage fails closed.",
            )
        successors[predecessor_identity] = successor_identity
        lineage.append(predecessor.reference())
    if _has_supersession_cycle(successors):
        return (
            None,
            tuple(sorted(lineage, key=lambda item: item.fingerprint)),
            "Cyclic admission predecessor lineage fails closed.",
        )
    remaining = tuple(
        record
        for identity, record in eligible_by_identity.items()
        if identity not in successors
    )
    if not remaining:
        return (
            None,
            tuple(sorted(lineage, key=lambda item: item.fingerprint)),
            "No effective admission record remains after predecessor resolution.",
        )
    precedence = max((record.effective_at, record.recorded_at) for record in remaining)
    co_precedent = tuple(
        record
        for record in remaining
        if (record.effective_at, record.recorded_at) == precedence
    )
    if len(co_precedent) != 1:
        return (
            None,
            tuple(sorted(lineage, key=lambda item: item.fingerprint)),
            "Conflicting co-precedent admission records fail closed.",
        )
    return (
        co_precedent[0],
        tuple(sorted(lineage, key=lambda item: item.fingerprint)),
        None,
    )


def _resolve_validity(
    artifact_reference: EvidenceArtifactReference,
    scope: str,
    events: tuple[EvidenceValidityEvent, ...],
    knowledge_as_of: datetime,
    effective_as_of: datetime,
) -> tuple[
    EvidenceValidityEvent | None,
    tuple[EvidenceValidityReference, ...],
    str | None,
]:
    eligible = tuple(
        event
        for event in events
        if event.artifact_reference == artifact_reference
        and event.scope == scope
        and event.recorded_at <= knowledge_as_of
        and event.effective_at <= effective_as_of
    )
    selected, lineage, failure = _resolve_validity_lineage(eligible)
    return selected, lineage, failure


def _has_supersession_cycle(
    successors: dict[tuple[str, str], tuple[str, str]],
) -> bool:
    for start in successors:
        seen: set[tuple[str, str]] = set()
        current = start
        while current in successors:
            if current in seen:
                return True
            seen.add(current)
            current = successors[current]
    return False


def _validation_record_tuple(
    value: object,
) -> tuple[EvidenceValidationRecord, ...]:
    if type(value) is not tuple:
        raise TypeError("validation_records must be an exact tuple")
    records: list[EvidenceValidationRecord] = []
    for item in cast(tuple[object, ...], value):
        if type(item) is not EvidenceValidationRecord:
            raise TypeError(
                "validation_records must contain EvidenceValidationRecord values"
            )
        item.to_dict()
        records.append(item)
    record_ids = tuple(record.validation_record_id for record in records)
    if len(set(record_ids)) != len(record_ids):
        raise ValueError("validation_records must not duplicate record identities")
    return tuple(
        sorted(
            records,
            key=lambda record: (
                record.artifact_reference.artifact_id,
                record.scope,
                record.concern.value,
                record.effective_at,
                record.recorded_at,
                record.validation_record_id,
            ),
        )
    )


def _freshness_record_tuple(
    value: object,
) -> tuple[EvidenceFreshnessEvaluationRecord, ...]:
    if type(value) is not tuple:
        raise TypeError("freshness_evaluations must be an exact tuple")
    records: list[EvidenceFreshnessEvaluationRecord] = []
    for item in cast(tuple[object, ...], value):
        if type(item) is not EvidenceFreshnessEvaluationRecord:
            raise TypeError(
                "freshness_evaluations must contain "
                "EvidenceFreshnessEvaluationRecord values"
            )
        item.to_dict()
        records.append(item)
    fingerprints = tuple(record.fingerprint for record in records)
    if len(set(fingerprints)) != len(fingerprints):
        raise ValueError("freshness_evaluations must not contain duplicates")
    return tuple(
        sorted(
            records,
            key=lambda record: (
                record.artifact_reference.artifact_id,
                record.freshness_rule.evaluation_scope,
                record.freshness_rule.fingerprint,
                record.evaluation_as_of,
                record.fingerprint,
            ),
        )
    )


def _admission_record_tuple(
    value: object,
) -> tuple[EvidenceAdmissionRecord, ...]:
    if type(value) is not tuple:
        raise TypeError("admission_records must be an exact tuple")
    records: list[EvidenceAdmissionRecord] = []
    for item in cast(tuple[object, ...], value):
        if type(item) is not EvidenceAdmissionRecord:
            raise TypeError(
                "admission_records must contain EvidenceAdmissionRecord values"
            )
        item.to_dict()
        records.append(item)
    record_ids = tuple(record.admission_record_id for record in records)
    if len(set(record_ids)) != len(record_ids):
        raise ValueError("admission_records must not duplicate record identities")
    return tuple(
        sorted(
            records,
            key=lambda record: (
                record.artifact_reference.artifact_id,
                record.admission_scope,
                record.effective_at,
                record.recorded_at,
                record.admission_record_id,
            ),
        )
    )


def _validity_event_tuple(
    value: object,
) -> tuple[EvidenceValidityEvent, ...]:
    if type(value) is not tuple:
        raise TypeError("validity_events must be an exact tuple")
    events: list[EvidenceValidityEvent] = []
    for item in cast(tuple[object, ...], value):
        if type(item) is not EvidenceValidityEvent:
            raise TypeError("validity_events must contain EvidenceValidityEvent values")
        item.to_dict()
        events.append(item)
    event_ids = tuple(event.validity_event_id for event in events)
    if len(set(event_ids)) != len(event_ids):
        raise ValueError("validity_events must not duplicate event identities")
    return tuple(
        sorted(
            events,
            key=lambda event: (
                event.artifact_reference.artifact_id,
                event.scope,
                event.effective_at,
                event.recorded_at,
                event.validity_event_id,
            ),
        )
    )


def _visible_ascii(value: object, field_name: str, maximum_length: int) -> str:
    if type(value) is not str:
        raise TypeError(f"{field_name} must be a string")
    if not value:
        raise ValueError(f"{field_name} must not be empty")
    if len(value) > maximum_length:
        raise ValueError(f"{field_name} exceeds maximum length {maximum_length}")
    if any(not 0x21 <= ord(character) <= 0x7E for character in value):
        raise ValueError(f"{field_name} must contain visible ASCII without whitespace")
    return value


def _timestamp(value: object, field_name: str) -> datetime:
    if type(value) is not datetime:
        raise TypeError(f"{field_name} must be a datetime")
    timestamp = value
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return timestamp.astimezone(UTC)


__all__ = [
    "evaluate_evidence_admission_as_of",
]
