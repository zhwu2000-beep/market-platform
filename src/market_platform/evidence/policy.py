"""Versioned immutable policy for Evidence admission and consumption."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import cast

from market_platform._fingerprint import canonical_fingerprint
from market_platform.evidence.temporal import EvidenceFreshnessRule
from market_platform.evidence.validation import EvidenceValidationConcern

EVIDENCE_VALIDATION_REQUIREMENT_SCHEMA_VERSION = "evidence_validation_requirement/v1"
EVIDENCE_ADMISSION_RULESET_SCHEMA_VERSION = "evidence_admission_ruleset/v3"
EVIDENCE_ADMISSION_RULESET_REFERENCE_SCHEMA_VERSION = (
    "evidence_admission_ruleset_reference/v1"
)

_FINGERPRINT_PATTERN = re.compile(r"sha256:[0-9a-f]{64}", flags=re.ASCII)
_FOUNDATION_MANDATORY_VALIDATION_CONCERNS = frozenset(
    {
        EvidenceValidationConcern.IDENTITY,
        EvidenceValidationConcern.INTEGRITY,
        EvidenceValidationConcern.PROVENANCE,
        EvidenceValidationConcern.AUTHORITY,
        EvidenceValidationConcern.SCHEMA,
        EvidenceValidationConcern.TEMPORAL_COHERENCE,
        EvidenceValidationConcern.FRESHNESS_CONTRACT,
    }
)


@dataclass(frozen=True, slots=True)
class EvidenceValidationRequirement:
    """Exact governing validation identity required for one concern and scope."""

    concern: EvidenceValidationConcern
    scope: str
    ruleset_id: str
    ruleset_version: str
    schema_version: str = field(
        init=False,
        default=EVIDENCE_VALIDATION_REQUIREMENT_SCHEMA_VERSION,
    )
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if type(self.concern) is not EvidenceValidationConcern:
            raise TypeError("concern must be an exact EvidenceValidationConcern")
        object.__setattr__(self, "scope", _visible_ascii(self.scope, "scope", 256))
        object.__setattr__(
            self,
            "ruleset_id",
            _visible_ascii(self.ruleset_id, "ruleset_id", 256),
        )
        object.__setattr__(
            self,
            "ruleset_version",
            _visible_ascii(self.ruleset_version, "ruleset_version", 128),
        )
        object.__setattr__(
            self,
            "fingerprint",
            canonical_fingerprint(self._fingerprint_payload()),
        )

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "concern": self.concern.value,
            "scope": self.scope,
            "ruleset_id": self.ruleset_id,
            "ruleset_version": self.ruleset_version,
        }

    def _validate(self) -> None:
        reconstructed = EvidenceValidationRequirement(
            concern=self.concern,
            scope=self.scope,
            ruleset_id=self.ruleset_id,
            ruleset_version=self.ruleset_version,
        )
        if self.schema_version != EVIDENCE_VALIDATION_REQUIREMENT_SCHEMA_VERSION:
            raise ValueError("evidence validation requirement schema is invalid")
        if _fingerprint(self.fingerprint, "fingerprint") != reconstructed.fingerprint:
            raise ValueError(
                "evidence validation requirement fingerprint does not match"
            )

    def to_dict(self) -> dict[str, object]:
        """Return the exact immutable validation requirement."""

        self._validate()
        return {**self._fingerprint_payload(), "fingerprint": self.fingerprint}


@dataclass(frozen=True, slots=True)
class EvidenceAdmissionRuleSetReference:
    """Exact identity of one immutable admission ruleset."""

    ruleset_id: str
    ruleset_version: str
    admission_scope: str
    ruleset_fingerprint: str
    schema_version: str = field(
        init=False,
        default=EVIDENCE_ADMISSION_RULESET_REFERENCE_SCHEMA_VERSION,
    )
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "ruleset_id",
            _visible_ascii(self.ruleset_id, "ruleset_id", 256),
        )
        object.__setattr__(
            self,
            "ruleset_version",
            _visible_ascii(self.ruleset_version, "ruleset_version", 128),
        )
        object.__setattr__(
            self,
            "admission_scope",
            _visible_ascii(self.admission_scope, "admission_scope", 256),
        )
        object.__setattr__(
            self,
            "ruleset_fingerprint",
            _fingerprint(self.ruleset_fingerprint, "ruleset_fingerprint"),
        )
        object.__setattr__(
            self,
            "fingerprint",
            canonical_fingerprint(self._fingerprint_payload()),
        )

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "ruleset_id": self.ruleset_id,
            "ruleset_version": self.ruleset_version,
            "admission_scope": self.admission_scope,
            "ruleset_fingerprint": self.ruleset_fingerprint,
        }

    def _validate(self) -> None:
        reconstructed = EvidenceAdmissionRuleSetReference(
            ruleset_id=self.ruleset_id,
            ruleset_version=self.ruleset_version,
            admission_scope=self.admission_scope,
            ruleset_fingerprint=self.ruleset_fingerprint,
        )
        if self.schema_version != EVIDENCE_ADMISSION_RULESET_REFERENCE_SCHEMA_VERSION:
            raise ValueError("evidence admission ruleset reference schema is invalid")
        if _fingerprint(self.fingerprint, "fingerprint") != reconstructed.fingerprint:
            raise ValueError(
                "evidence admission ruleset reference fingerprint does not match"
            )

    def to_dict(self) -> dict[str, object]:
        """Return the exact immutable ruleset-reference projection."""

        self._validate()
        return {**self._fingerprint_payload(), "fingerprint": self.fingerprint}


@dataclass(frozen=True, slots=True)
class EvidenceAdmissionRuleSet:
    """Bounded policy governing Evidence admission and final consumability."""

    ruleset_id: str
    ruleset_version: str
    admission_scope: str
    mandatory_validation_requirements: tuple[EvidenceValidationRequirement, ...]
    admission_freshness_required: bool
    admission_freshness_rule: EvidenceFreshnessRule | None
    task_freshness_required: bool
    task_freshness_rule: EvidenceFreshnessRule | None
    active_validity_required: bool
    schema_version: str = field(
        init=False,
        default=EVIDENCE_ADMISSION_RULESET_SCHEMA_VERSION,
    )
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if type(self.admission_freshness_required) is not bool:
            raise TypeError("admission_freshness_required must be an exact bool")
        if type(self.task_freshness_required) is not bool:
            raise TypeError("task_freshness_required must be an exact bool")
        if type(self.active_validity_required) is not bool:
            raise TypeError("active_validity_required must be an exact bool")
        values: dict[str, object] = {
            "ruleset_id": _visible_ascii(self.ruleset_id, "ruleset_id", 256),
            "ruleset_version": _visible_ascii(
                self.ruleset_version,
                "ruleset_version",
                128,
            ),
            "admission_scope": _visible_ascii(
                self.admission_scope,
                "admission_scope",
                256,
            ),
            "mandatory_validation_requirements": _requirement_tuple(
                self.mandatory_validation_requirements
            ),
            "admission_freshness_rule": _copy_optional_freshness_rule(
                self.admission_freshness_rule
            ),
            "task_freshness_rule": _copy_optional_freshness_rule(
                self.task_freshness_rule
            ),
        }
        for name, value in values.items():
            object.__setattr__(self, name, value)
        if any(
            requirement.scope != self.admission_scope
            for requirement in self.mandatory_validation_requirements
        ):
            raise ValueError(
                "mandatory validation requirements must bind the admission scope"
            )
        missing_concerns = _FOUNDATION_MANDATORY_VALIDATION_CONCERNS.difference(
            self.mandatory_validation_concerns
        )
        if missing_concerns:
            missing = ", ".join(
                concern.value
                for concern in sorted(missing_concerns, key=lambda item: item.value)
            )
            raise ValueError(
                "mandatory_validation_concerns cannot omit foundation concerns: "
                f"{missing}"
            )
        if not self.admission_freshness_required:
            raise ValueError("admission_freshness_required cannot be disabled")
        if not self.task_freshness_required:
            raise ValueError("task_freshness_required cannot be disabled")
        if not self.active_validity_required:
            raise ValueError("active_validity_required cannot be disabled")
        _require_rule_correspondence(
            required=self.admission_freshness_required,
            rule=self.admission_freshness_rule,
            scope=self.admission_scope,
            field_name="admission_freshness_rule",
        )
        _require_rule_correspondence(
            required=self.task_freshness_required,
            rule=self.task_freshness_rule,
            scope=self.admission_scope,
            field_name="task_freshness_rule",
        )
        object.__setattr__(
            self,
            "fingerprint",
            canonical_fingerprint(self._fingerprint_payload()),
        )

    @property
    def mandatory_validation_concerns(
        self,
    ) -> tuple[EvidenceValidationConcern, ...]:
        """Return the concern floor represented by the exact requirements."""

        return tuple(
            requirement.concern
            for requirement in self.mandatory_validation_requirements
        )

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "ruleset_id": self.ruleset_id,
            "ruleset_version": self.ruleset_version,
            "admission_scope": self.admission_scope,
            "mandatory_validation_requirements": [
                requirement.to_dict()
                for requirement in self.mandatory_validation_requirements
            ],
            "admission_freshness_required": self.admission_freshness_required,
            "admission_freshness_rule": (
                None
                if self.admission_freshness_rule is None
                else self.admission_freshness_rule.to_dict()
            ),
            "task_freshness_required": self.task_freshness_required,
            "task_freshness_rule": (
                None
                if self.task_freshness_rule is None
                else self.task_freshness_rule.to_dict()
            ),
            "active_validity_required": self.active_validity_required,
        }

    def _validate(self) -> None:
        reconstructed = EvidenceAdmissionRuleSet(
            ruleset_id=self.ruleset_id,
            ruleset_version=self.ruleset_version,
            admission_scope=self.admission_scope,
            mandatory_validation_requirements=_requirement_tuple(
                self.mandatory_validation_requirements,
                require_retained_tuple=True,
            ),
            admission_freshness_required=self.admission_freshness_required,
            admission_freshness_rule=self.admission_freshness_rule,
            task_freshness_required=self.task_freshness_required,
            task_freshness_rule=self.task_freshness_rule,
            active_validity_required=self.active_validity_required,
        )
        if self.schema_version != EVIDENCE_ADMISSION_RULESET_SCHEMA_VERSION:
            raise ValueError("evidence admission ruleset schema_version is invalid")
        if _fingerprint(self.fingerprint, "fingerprint") != reconstructed.fingerprint:
            raise ValueError("evidence admission ruleset fingerprint does not match")

    def reference(self) -> EvidenceAdmissionRuleSetReference:
        """Return an exact reference to this ruleset."""

        self._validate()
        return EvidenceAdmissionRuleSetReference(
            ruleset_id=self.ruleset_id,
            ruleset_version=self.ruleset_version,
            admission_scope=self.admission_scope,
            ruleset_fingerprint=self.fingerprint,
        )

    def to_dict(self) -> dict[str, object]:
        """Return the canonical immutable ruleset projection."""

        self._validate()
        return {**self._fingerprint_payload(), "fingerprint": self.fingerprint}


def _require_rule_correspondence(
    *,
    required: bool,
    rule: EvidenceFreshnessRule | None,
    scope: str,
    field_name: str,
) -> None:
    if required != (rule is not None):
        raise ValueError(f"{field_name} must be present exactly when required")
    if rule is not None and rule.evaluation_scope != scope:
        raise ValueError(f"{field_name} must bind the admission scope")


def _copy_optional_freshness_rule(
    value: object,
) -> EvidenceFreshnessRule | None:
    if value is None:
        return None
    if type(value) is not EvidenceFreshnessRule:
        raise TypeError("freshness rules must be EvidenceFreshnessRule values")
    value._validate()
    return EvidenceFreshnessRule(
        rule_id=value.rule_id,
        rule_version=value.rule_version,
        declared_temporal_anchor=value.declared_temporal_anchor,
        evaluation_scope=value.evaluation_scope,
    )


def _copy_validation_requirement(
    value: object,
) -> EvidenceValidationRequirement:
    if type(value) is not EvidenceValidationRequirement:
        raise TypeError(
            "mandatory_validation_requirements must contain exact "
            "EvidenceValidationRequirement values"
        )
    value._validate()
    return EvidenceValidationRequirement(
        concern=value.concern,
        scope=value.scope,
        ruleset_id=value.ruleset_id,
        ruleset_version=value.ruleset_version,
    )


def _requirement_tuple(
    value: object,
    *,
    require_retained_tuple: bool = False,
    allow_empty: bool = False,
) -> tuple[EvidenceValidationRequirement, ...]:
    if type(value) is not tuple:
        raise TypeError("mandatory_validation_requirements must be an exact tuple")
    requirements = tuple(
        _copy_validation_requirement(item) for item in cast(tuple[object, ...], value)
    )
    if not requirements and not allow_empty:
        raise ValueError("mandatory_validation_requirements must not be empty")
    concerns = tuple(requirement.concern for requirement in requirements)
    if len(set(concerns)) != len(concerns):
        raise ValueError(
            "mandatory_validation_requirements must not duplicate a concern"
        )
    ordered = tuple(sorted(requirements, key=lambda item: item.concern.value))
    if require_retained_tuple and requirements != ordered:
        raise ValueError(
            "mandatory_validation_requirements retained ordering is not canonical"
        )
    return ordered


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


def _fingerprint(value: object, field_name: str) -> str:
    if type(value) is not str or _FINGERPRINT_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a lowercase sha256 fingerprint")
    return value


__all__ = [
    "EVIDENCE_ADMISSION_RULESET_REFERENCE_SCHEMA_VERSION",
    "EVIDENCE_ADMISSION_RULESET_SCHEMA_VERSION",
    "EVIDENCE_VALIDATION_REQUIREMENT_SCHEMA_VERSION",
    "EvidenceAdmissionRuleSet",
    "EvidenceAdmissionRuleSetReference",
    "EvidenceValidationRequirement",
]
