"""Passive ADR0052 readiness contracts; construction authenticates nothing.

Requests identify purported inputs for later owned resolution. Assessments describe
only their recorded context, even when READY. A future research invoker must
independently revalidate current Pending trust, material, governance, task freshness,
policy and timing. This module performs no assessment, governance or activation.
Opt-in Pending resolution authenticates only the retained delivery graph.
"""

import re
from dataclasses import dataclass, field, fields, replace
from datetime import UTC, datetime
from enum import StrEnum

from market_platform._fingerprint import canonical_fingerprint
from market_platform.application.polygon_completed_daily_production_admission import (
    PolygonCompletedDailyFreshnessExecutionReference,
)
from market_platform.application.polygon_completed_daily_production_technical import (
    PolygonCompletedDailyTechnicalRequest,
)
from market_platform.application.radar_candidate_delivery import (
    DeliveryFailure,
    RadarCandidateDeliveryError,
    SourceRecoveryIdentity,
)
from market_platform.application.radar_candidate_delivery_store import (
    RadarCandidateDeliveryFileStore,
    RadarCandidateDeliveryUnavailableError,
)
from market_platform.evidence.references import (
    EvidenceArtifactReference,
    EvidenceIdentityReference,
)

READINESS_POLICY_ID = "exact_governed_250_session_technical_readiness"
READINESS_POLICY_REVISION = "1"
READINESS_POLICY_SCHEMA = "radar_research_escalation_readiness_policy/v1"


def _fingerprint(value: str, name: str) -> None:
    if type(value) is not str or re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None:
        raise ValueError(f"{name} must be a canonical fingerprint")


def _timestamp(value: datetime) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be a timezone-aware datetime")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class RadarResearchReadinessPolicyIdentity:
    """Closed revision-1 policy implementing ADR0052 Decisions 1-6.

    Requires the complete exact ordered 250-session Candidate window, including
    its triggering completed session, exact normalized historical content, and
    current governed qualification for the intended task. Acquisition, refetch and
    repair are forbidden; unsupported timing is REFUSED. Identity is correspondence,
    distinct from eligibility, Admission, Technical and invocation authority.
    """

    policy_id: str = READINESS_POLICY_ID
    behavioral_revision: str = READINESS_POLICY_REVISION
    schema_version: str = READINESS_POLICY_SCHEMA
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        for name, expected in (
            ("policy_id", READINESS_POLICY_ID),
            ("behavioral_revision", READINESS_POLICY_REVISION),
            ("schema_version", READINESS_POLICY_SCHEMA),
        ):
            if type(getattr(self, name)) is not str:
                raise TypeError(f"{name} must be a string")
            if getattr(self, name) != expected:
                raise ValueError("Unsupported readiness policy")
        object.__setattr__(self, "fingerprint", canonical_fingerprint(self._payload()))

    @property
    def required_session_count(self) -> int:
        return 250

    def _payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "policy_id": self.policy_id,
            "behavioral_revision": self.behavioral_revision,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._payload(), "fingerprint": self.fingerprint}


class RadarResearchReadinessOutcome(StrEnum):
    """Bounded descriptions of a recorded context, never invocation permission."""

    READY = "READY"
    BLOCKED = "BLOCKED"
    REFUSED = "REFUSED"


@dataclass(frozen=True, slots=True)
class RadarResearchReadinessRequest:
    """Untrusted lookup/context values; no supplied reference proves authority.

    Pending is looked up by existing Candidate fingerprint; source_identity names
    its intended Prepared/Accepted/Decision graph. The artifact is a logical exact
    version; construction_execution_id separately selects its material occurrence.
    Consumer/use/profile references must later be resolved to approved definitions.

    analysis_as_of is the intended effective and exact task-freshness cutoff;
    knowledge_as_of bounds available records. Original observation/query/receipt
    times and freshness execution/availability remain with their referenced owners.
    Neither cutoff is an assessment execution time or a source-availability claim.
    """

    candidate_fingerprint: str
    source_identity: SourceRecoveryIdentity
    artifact_reference: EvidenceArtifactReference
    construction_execution_id: str
    consumer_reference: EvidenceIdentityReference
    intended_use_reference: EvidenceIdentityReference
    technical_profile_reference: EvidenceIdentityReference
    analysis_as_of: datetime
    knowledge_as_of: datetime

    def __post_init__(self) -> None:
        _fingerprint(self.candidate_fingerprint, "candidate_fingerprint")
        if type(self.source_identity) is not SourceRecoveryIdentity:
            raise TypeError("source_identity must be SourceRecoveryIdentity")
        object.__setattr__(self, "source_identity", replace(self.source_identity))
        if type(self.artifact_reference) is not EvidenceArtifactReference:
            raise TypeError("artifact_reference must be EvidenceArtifactReference")
        self.artifact_reference.to_dict()
        object.__setattr__(self, "artifact_reference", replace(self.artifact_reference))
        if (
            type(self.construction_execution_id) is not str
            or re.fullmatch(
                r"polygon_completed_daily_construction:[0-9a-f]{32}",
                self.construction_execution_id,
            )
            is None
        ):
            raise ValueError("exact construction occurrence reference required")
        for name in (
            "consumer_reference",
            "intended_use_reference",
            "technical_profile_reference",
        ):
            reference = getattr(self, name)
            if type(reference) is not EvidenceIdentityReference:
                raise TypeError(f"{name} must be EvidenceIdentityReference")
            reference.to_dict()
            object.__setattr__(self, name, replace(reference))
        object.__setattr__(self, "analysis_as_of", _timestamp(self.analysis_as_of))
        object.__setattr__(self, "knowledge_as_of", _timestamp(self.knowledge_as_of))
        if self.analysis_as_of > self.knowledge_as_of:
            raise ValueError("analysis/effective cutoff is after knowledge cutoff")


@dataclass(frozen=True, slots=True)
class RadarResearchPendingResolution:
    """References returned after trusted owner authentication of a Pending graph.

    The source identity binds Prepared/Accepted/Decision and its retained policy;
    the Candidate fingerprint identifies exact Pending work. No material or
    readiness conclusion is made. Constructing this value authenticates nothing,
    and it is never a permit; only the resolver establishes owned correspondence.
    """

    candidate_fingerprint: str
    source_identity: SourceRecoveryIdentity

    def __post_init__(self) -> None:
        _fingerprint(self.candidate_fingerprint, "candidate_fingerprint")
        if type(self.source_identity) is not SourceRecoveryIdentity:
            raise TypeError("source_identity must be SourceRecoveryIdentity")
        object.__setattr__(self, "source_identity", replace(self.source_identity))


class RadarResearchPendingResolver:
    """Explicit read-only boundary; authentic Pending is insufficient for READY.

    The injected existing owner is trusted by composition, never supplied as a
    request record. Unavailability raises RadarCandidateDeliveryUnavailableError
    (BLOCKED-type); malformed input and graph contradictions retain the existing
    RadarCandidateDeliveryError (REFUSED-type). No later readiness checks run.
    """

    def __init__(self, store: RadarCandidateDeliveryFileStore | None) -> None:
        if store is not None and type(store) is not RadarCandidateDeliveryFileStore:
            raise TypeError("Expected owned Candidate delivery store or None")
        self._store = store

    def resolve(
        self, request: RadarResearchReadinessRequest
    ) -> RadarResearchPendingResolution:
        if type(request) is not RadarResearchReadinessRequest:
            raise RadarCandidateDeliveryError(DeliveryFailure.INVARIANT)
        # Validate only Pending lookup identities; other references remain untrusted
        # and unexamined. Neither copied records nor evaluated contexts are inputs.
        try:
            _fingerprint(request.candidate_fingerprint, "candidate_fingerprint")
            if type(request.source_identity) is not SourceRecoveryIdentity:
                raise TypeError("Expected source recovery identity")
            identity = replace(request.source_identity)
        except Exception as exc:
            raise RadarCandidateDeliveryError(DeliveryFailure.INVARIANT) from exc
        if self._store is None:
            raise RadarCandidateDeliveryUnavailableError("Trusted owner unavailable")
        pending = self._store.resolve_pending(request.candidate_fingerprint, identity)
        if pending is None:
            raise RadarCandidateDeliveryUnavailableError("Retained Pending unavailable")
        return RadarResearchPendingResolution(
            pending.candidate_fingerprint, pending.source_identity
        )


@dataclass(frozen=True, slots=True)
class RadarResearchReadinessOccurrenceReference:
    """Reference to an existing owned occurrence; construction authenticates nothing.

    Construction and Qualification have no public payload-free occurrence
    reference type. Retain their existing identities unchanged, without minting a
    new identifier. The referenced receipt/result retains authoritative lineage,
    governance histories, task context and execution/availability times.
    """

    execution_id: str
    history_namespace_id: str
    history_sequence: int
    fingerprint: str

    def __post_init__(self) -> None:
        match = (
            re.fullmatch(
                r"(polygon_completed_daily_(?:construction|qualification))"
                r":[0-9a-f]{32}",
                self.execution_id,
            )
            if type(self.execution_id) is str
            else None
        )
        if match is None:
            raise ValueError("existing construction/qualification occurrence required")
        if (
            type(self.history_namespace_id) is not str
            or re.fullmatch(
                match[1] + r"_history:[0-9a-f]{32}", self.history_namespace_id
            )
            is None
        ):
            raise ValueError("matching occurrence owner history namespace required")
        if type(self.history_sequence) is not int or self.history_sequence < 1:
            raise ValueError("history_sequence must be a positive integer")
        _fingerprint(self.fingerprint, "occurrence fingerprint")


@dataclass(frozen=True, slots=True)
class RadarResearchReadinessEvaluatedContext:
    """References actually used by a later owned evaluator, separate from request.

    Construction authenticates nothing, including synthetic complete contexts.
    None explicitly records a reference not established before evaluation stopped;
    partial contexts impose no evaluator call order. READY requires every field.

    The evaluated source identity and Candidate fingerprint reference the delivery
    graph through its existing owner, without copying Pending or Candidate values.
    The current Qualification occurrence retains the actual governance histories,
    effective/knowledge cutoffs, use/profile and material lineage evaluated. Bridge
    retains its original Qualification, which need not be the current one.
    Task freshness references its own exact evaluation and execution companion.
    Authoritative timing remains in these owner references/records, not duplicated
    as assessment timestamps. No payloads, lifecycle conclusions or permissions
    are retained here. Correspondence and authentication belong to trusted owners.
    """

    candidate_fingerprint: str | None = None
    source_identity: SourceRecoveryIdentity | None = None
    artifact_reference: EvidenceArtifactReference | None = None
    construction_reference: RadarResearchReadinessOccurrenceReference | None = None
    current_qualification_reference: (
        RadarResearchReadinessOccurrenceReference | None
    ) = None
    task_freshness_reference: (
        PolygonCompletedDailyFreshnessExecutionReference | None
    ) = None
    bridge_reference: PolygonCompletedDailyTechnicalRequest | None = None

    def __post_init__(self) -> None:
        if self.candidate_fingerprint is not None:
            _fingerprint(self.candidate_fingerprint, "evaluated candidate_fingerprint")
        for name, expected in (
            ("source_identity", SourceRecoveryIdentity),
            ("artifact_reference", EvidenceArtifactReference),
            ("construction_reference", RadarResearchReadinessOccurrenceReference),
            (
                "current_qualification_reference",
                RadarResearchReadinessOccurrenceReference,
            ),
            (
                "task_freshness_reference",
                PolygonCompletedDailyFreshnessExecutionReference,
            ),
            ("bridge_reference", PolygonCompletedDailyTechnicalRequest),
        ):
            reference = getattr(self, name)
            if reference is None:
                continue
            if type(reference) is not expected:
                raise TypeError(f"{name} must be {expected.__name__} or None")
            if name in (
                "artifact_reference",
                "task_freshness_reference",
                "bridge_reference",
            ):
                reference.to_dict()
            object.__setattr__(self, name, replace(reference))
        for name, kind in (
            ("construction_reference", "construction"),
            ("current_qualification_reference", "qualification"),
        ):
            reference = getattr(self, name)
            if reference is not None and not reference.execution_id.startswith(
                f"polygon_completed_daily_{kind}:"
            ):
                raise ValueError(f"{name} requires an existing {kind} occurrence")


class RadarResearchReadinessFindingCode(StrEnum):
    """Readiness concern families, without duplicating owned governance rules."""

    PENDING_AUTHORITY = "pending_authority"
    MATERIAL_CORRESPONDENCE = "material_correspondence"
    GOVERNANCE_PREREQUISITES = "governance_prerequisites"
    TIMING_CONTEXT = "timing_context"
    INPUT_INTEGRITY = "input_integrity"


class RadarResearchReadinessFindingCondition(StrEnum):
    """Absence/unsatisfied prerequisites differ from contradiction/unsupported use."""

    PASSED = "PASSED"
    UNAVAILABLE = "UNAVAILABLE"
    UNSATISFIED = "UNSATISFIED"
    CONTRADICTORY = "CONTRADICTORY"
    UNSUPPORTED = "UNSUPPORTED"
    NOT_CHECKED = "NOT_CHECKED"


@dataclass(frozen=True, slots=True)
class RadarResearchReadinessFinding:
    """Structured summary; optional detail adds explanation, never authority."""

    code: RadarResearchReadinessFindingCode
    condition: RadarResearchReadinessFindingCondition
    detail: str | None = None

    def __post_init__(self) -> None:
        if type(self.code) is not RadarResearchReadinessFindingCode:
            raise TypeError("code must be RadarResearchReadinessFindingCode")
        if type(self.condition) is not RadarResearchReadinessFindingCondition:
            raise TypeError("condition must be RadarResearchReadinessFindingCondition")
        if self.detail is not None and type(self.detail) is not str:
            raise TypeError("detail must be a string or None")

    @property
    def required_outcome(self) -> RadarResearchReadinessOutcome | None:
        match self.condition:
            case (
                RadarResearchReadinessFindingCondition.UNAVAILABLE
                | RadarResearchReadinessFindingCondition.UNSATISFIED
            ):
                return RadarResearchReadinessOutcome.BLOCKED
            case (
                RadarResearchReadinessFindingCondition.CONTRADICTORY
                | RadarResearchReadinessFindingCondition.UNSUPPORTED
            ):
                return RadarResearchReadinessOutcome.REFUSED
            case _:
                return None


@dataclass(frozen=True, slots=True)
class RadarResearchReadinessAssessment:
    """Immutable descriptive result, not an authenticated publication or permit.

    request retains supplied references only; evaluated_context separately records
    what a later owned evaluator actually used, with explicit missing references.
    Construction does not claim successful resolution or authentication.
    Findings summarize recorded checks without executing
    them. Omitted families and NOT_CHECKED entries remain unperformed, never passed.
    READY requires positive summaries of every family and no unperformed checks.
    Negative outcomes require a corresponding structured condition; contradictions
    and unsupported context cannot be downgraded to BLOCKED. Findings retain caller
    order for deterministic value semantics. Empty findings cannot explain a result.

    Execution times do not rewrite historical availability. A caller-constructed
    READY value proves no Pending ownership, Evidence authenticity, Admission,
    Validity, Freshness, Qualification, correspondence or research authorization.
    """

    request: RadarResearchReadinessRequest
    policy: RadarResearchReadinessPolicyIdentity
    outcome: RadarResearchReadinessOutcome
    execution_started_at: datetime
    execution_completed_at: datetime
    findings: tuple[RadarResearchReadinessFinding, ...]
    evaluated_context: RadarResearchReadinessEvaluatedContext | None = None

    def __post_init__(self) -> None:
        if type(self.request) is not RadarResearchReadinessRequest:
            raise TypeError("request must be RadarResearchReadinessRequest")
        object.__setattr__(self, "request", replace(self.request))
        if self.evaluated_context is not None:
            if (
                type(self.evaluated_context)
                is not RadarResearchReadinessEvaluatedContext
            ):
                raise TypeError("evaluated_context must be evaluated context or None")
            object.__setattr__(
                self, "evaluated_context", replace(self.evaluated_context)
            )
        if type(self.policy) is not RadarResearchReadinessPolicyIdentity:
            raise TypeError("policy must be RadarResearchReadinessPolicyIdentity")
        policy = replace(self.policy)
        if policy != self.policy:
            raise ValueError("readiness policy fingerprint mismatch")
        object.__setattr__(self, "policy", policy)
        if type(self.outcome) is not RadarResearchReadinessOutcome:
            raise TypeError("outcome must be RadarResearchReadinessOutcome")
        object.__setattr__(
            self, "execution_started_at", _timestamp(self.execution_started_at)
        )
        object.__setattr__(
            self, "execution_completed_at", _timestamp(self.execution_completed_at)
        )
        if self.execution_completed_at < self.execution_started_at:
            raise ValueError("assessment completion precedes start")
        if self.request.knowledge_as_of > self.execution_completed_at:
            raise ValueError("knowledge cutoff is after assessment execution")
        if type(self.findings) is not tuple:
            raise TypeError("findings must be an immutable ordered tuple")
        if not self.findings:
            raise ValueError("assessment requires structured findings")
        if any(
            type(item) is not RadarResearchReadinessFinding for item in self.findings
        ):
            raise TypeError("findings must contain RadarResearchReadinessFinding")
        object.__setattr__(
            self, "findings", tuple(replace(item) for item in self.findings)
        )
        required = {item.required_outcome for item in self.findings}
        if self.outcome is RadarResearchReadinessOutcome.READY:
            if self.unperformed_checks or any(
                item.condition is not RadarResearchReadinessFindingCondition.PASSED
                for item in self.findings
            ):
                raise ValueError("READY requires every readiness concern to pass")
            if self.evaluated_context is None or any(
                getattr(self.evaluated_context, item.name) is None
                for item in fields(self.evaluated_context)
            ):
                raise ValueError("READY requires complete evaluated-reference context")
        elif self.outcome is RadarResearchReadinessOutcome.BLOCKED:
            if (
                RadarResearchReadinessOutcome.BLOCKED not in required
                or RadarResearchReadinessOutcome.REFUSED in required
            ):
                raise ValueError("BLOCKED requires absence/unsatisfied without refusal")
        elif RadarResearchReadinessOutcome.REFUSED not in required:
            raise ValueError("REFUSED requires contradiction or unsupported context")

    @property
    def unperformed_checks(self) -> tuple[RadarResearchReadinessFindingCode, ...]:
        """Include omissions and every explicit NOT_CHECKED, even in mixed families."""
        return tuple(
            code
            for code in RadarResearchReadinessFindingCode
            if any(
                item.code is code
                and item.condition is RadarResearchReadinessFindingCondition.NOT_CHECKED
                for item in self.findings
            )
            or not any(item.code is code for item in self.findings)
        )
