"""Passive ADR0052 readiness contracts; construction authenticates nothing.

Requests identify purported inputs for later owned resolution. Assessments describe
only their recorded context, even when READY. A future research invoker must
independently revalidate current Pending trust, material, governance, task freshness,
policy and timing. Opt-in final assessment stops at a descriptive result.
Opt-in Pending resolution authenticates only the retained delivery graph.
Opt-in governed resolution evaluates retained material and current task governance.
"""

import re
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import dataclass, field, fields, replace
from datetime import UTC, date, datetime
from enum import StrEnum
from zoneinfo import ZoneInfo

from market_platform._fingerprint import canonical_fingerprint
from market_platform.application import polygon_completed_daily_production_bridge as b
from market_platform.application import (
    polygon_completed_daily_production_qualification as q,
)
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
from market_platform.radar.calendar import CalendarError, ExchangeSessionCalendar

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


class RadarResearchGovernedContextError(RuntimeError):
    """A bounded finding, with typed canonical cause retained when applicable."""

    def __init__(self, finding: RadarResearchReadinessFinding) -> None:
        self.finding = finding
        super().__init__(finding.detail)


@dataclass(frozen=True, slots=True)
class RadarResearchGovernedContextResolution:
    """Authenticated references for this context only; never a research permit.

    Construction authenticates nothing. No READY assessment is made. The existing
    evaluated context supplies the governed fields without duplicating reference
    types or payloads; Pending fields record the owned input reauthenticated here.
    """

    evaluated_context: RadarResearchReadinessEvaluatedContext

    def __post_init__(self) -> None:
        if type(self.evaluated_context) is not RadarResearchReadinessEvaluatedContext:
            raise TypeError("exact evaluated context required")
        context = replace(self.evaluated_context)
        if any(getattr(context, item.name) is None for item in fields(context)):
            raise ValueError("resolved context requires all authenticated references")
        object.__setattr__(self, "evaluated_context", context)


def _governed_failure(
    code: RadarResearchReadinessFindingCode,
    condition: RadarResearchReadinessFindingCondition,
    detail: str,
) -> RadarResearchGovernedContextError:
    return RadarResearchGovernedContextError(
        RadarResearchReadinessFinding(code, condition, detail)
    )


class RadarResearchGovernedContextResolver:
    """Explicit no-refetch resolution over trusted owners; no downstream executor.

    Pending resolution values are not bearer proof. The same Slice-2 resolver and
    delivery owner are required again, so a detached or fabricated value cannot
    bypass Pending authentication. Composition supplies exact trusted governance
    services and the same exchange calendar semantics used for Radar acceptance.
    No production composition calls this boundary.
    """

    def __init__(
        self,
        store: RadarCandidateDeliveryFileStore | None,
        qualification_service: (
            q.PolygonCompletedDailyProductionQualificationApplicationService | None
        ),
        bridge_service: b.PolygonCompletedDailyProductionBridgeApplicationService
        | None,
        calendar: ExchangeSessionCalendar,
        *,
        execution_clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._pending_resolver = RadarResearchPendingResolver(store)
        for owner, expected in (
            (
                qualification_service,
                q.PolygonCompletedDailyProductionQualificationApplicationService,
            ),
            (bridge_service, b.PolygonCompletedDailyProductionBridgeApplicationService),
        ):
            if owner is not None and type(owner) is not expected:
                raise TypeError("exact trusted governed owner required")
        self._store = store
        self._qualification = qualification_service
        self._bridge = bridge_service
        self._calendar = calendar
        self._clock = execution_clock or (lambda: datetime.now(UTC))

    def resolve(
        self,
        pending: RadarResearchPendingResolution,
        request: RadarResearchReadinessRequest,
    ) -> RadarResearchGovernedContextResolution:
        code = RadarResearchReadinessFindingCode
        condition = RadarResearchReadinessFindingCondition
        try:
            if type(pending) is not RadarResearchPendingResolution:
                raise TypeError("owned Pending resolution required")
            authenticated = self._pending_resolver.resolve(request)
            if replace(pending) != authenticated:
                raise RadarCandidateDeliveryError(DeliveryFailure.INVARIANT)
            assert self._store is not None
            work = self._store.resolve_pending(
                authenticated.candidate_fingerprint, authenticated.source_identity
            )
            if work is None:
                raise RadarCandidateDeliveryUnavailableError("Pending disappeared")
        except RadarCandidateDeliveryUnavailableError as error:
            raise _governed_failure(
                code.PENDING_AUTHORITY, condition.UNAVAILABLE, str(error)
            ) from error
        except (TypeError, ValueError, RadarCandidateDeliveryError) as error:
            raise _governed_failure(
                code.PENDING_AUTHORITY, condition.CONTRADICTORY, str(error)
            ) from error
        try:
            supplied = replace(request)
            now = _timestamp(self._clock())
            if supplied.knowledge_as_of > now:
                raise _governed_failure(
                    code.TIMING_CONTEXT,
                    condition.UNSUPPORTED,
                    "future knowledge cutoff",
                )
            candidate = work.decision.candidate
            assert candidate is not None
            observation = candidate.source_observation_state.lightweight_observation
            scope = observation.content_scope
            # Exact material cannot legitimately include the NY query civil date.
            if (
                observation.completed_session
                >= supplied.knowledge_as_of.astimezone(
                    ZoneInfo("America/New_York")
                ).date()
            ):
                raise _governed_failure(
                    code.TIMING_CONTEXT,
                    condition.UNSUPPORTED,
                    "same-day/post-close exact governance unsupported",
                )
            # Approved task identity does not depend on current consumability.
            # An unavailable Qualification owner cannot establish this comparison.
            if self._qualification is not None:
                profile = q._approved_profile()
                profile_fingerprint = profile.analysis_profile.get(
                    "profile_fingerprint"
                )
                if type(profile_fingerprint) is not str:
                    raise ValueError("approved technical profile fingerprint required")
                if (
                    supplied.consumer_reference
                    != EvidenceIdentityReference(
                        "consumer",
                        profile.consumer.definition_id,
                        profile.consumer.definition_version,
                        profile.consumer.fingerprint,
                    )
                    or supplied.intended_use_reference
                    != EvidenceIdentityReference(
                        "use",
                        profile.use.definition_id,
                        profile.use.definition_version,
                        profile.use.fingerprint,
                    )
                    or supplied.technical_profile_reference
                    != EvidenceIdentityReference(
                        "analysis_profile",
                        profile.analysis_profile.definition_id,
                        profile.analysis_profile.definition_version,
                        profile_fingerprint,
                    )
                ):
                    raise _governed_failure(
                        code.INPUT_INTEGRITY,
                        condition.CONTRADICTORY,
                        "exact task/profile linkage mismatch",
                    )
            # Authenticate retained representation and original provenance without
            # requalifying its historical context or issuing a new Bridge.
            if self._bridge is not None:
                original_owner = self._bridge._qualification_service
                with ExitStack() as stack:
                    original_owner._lock_inputs(stack)
                    stack.enter_context(original_owner._history._lock)
                    for retained in self._bridge.get_bridge_history_as_of(
                        supplied.artifact_reference,
                        knowledge_as_of=supplied.knowledge_as_of,
                    ):
                        original = retained.qualification
                        try:
                            owned = self._bridge._resolve(
                                b.PolygonCompletedDailyBridgeRequest(
                                    supplied.artifact_reference,
                                    original.construction_result.receipt.execution_id,
                                    original.execution_id,
                                    original.fingerprint,
                                ),
                                now,
                            )
                        except b.PolygonCompletedDailyBridgeRefused as error:
                            if error.reason is not (
                                b.PolygonCompletedDailyBridgeRefusalReason.QUALIFICATION_UNAVAILABLE
                            ):
                                raise
                            # Absence proves no provenance contradiction. The
                            # required current Bridge resolution still runs below.
                            continue
                        if owned != original:
                            raise ValueError("retained Bridge/Qualification mismatch")
                        retained_evidence = retained.completed_prices.evidence
                        if (
                            owned.construction_result.receipt.execution_id
                            == supplied.construction_execution_id
                            and retained_evidence.dataset_content_fingerprint
                            != observation.normalized_market_content_identity
                        ):
                            raise _governed_failure(
                                code.MATERIAL_CORRESPONDENCE,
                                condition.CONTRADICTORY,
                                "normalized historical-content mismatch",
                            )
            if self._qualification is None:
                raise _governed_failure(
                    code.GOVERNANCE_PREREQUISITES,
                    condition.UNAVAILABLE,
                    "trusted governed owner unavailable",
                )
            intent = q.PolygonCompletedDailyQualificationRequest(
                supplied.artifact_reference,
                supplied.construction_execution_id,
                supplied.analysis_as_of,
                supplied.knowledge_as_of,
            )
            material_owner = self._qualification.resolve_retained_material(intent)
            material = material_owner.material
            if (
                material.canonical_subject.subject_id
                != observation.instrument.instrument_id
            ):
                raise _governed_failure(
                    code.MATERIAL_CORRESPONDENCE,
                    condition.CONTRADICTORY,
                    "canonical instrument mismatch",
                )
            expected = self._calendar.sessions_in_range(
                scope.history_start, scope.history_end
            )
            dates = tuple(date.fromisoformat(row.session_date) for row in material.rows)
            start = observation.completed_session
            for _ in range(249):
                start = self._calendar.previous_session(start)
            if (
                len(expected) != 250
                or scope.history_start != start
                or self._calendar.latest_completed_session(observation.as_of)
                != observation.completed_session
                or tuple(sorted(set(expected))) != expected
                or dates != expected
                or expected[-1] != observation.completed_session
                or material.start_session_date != scope.history_start.isoformat()
                or material.end_session_date != scope.history_end.isoformat()
            ):
                raise _governed_failure(
                    code.MATERIAL_CORRESPONDENCE,
                    condition.CONTRADICTORY,
                    "exact ordered 250-session triggering window mismatch",
                )
            if (
                dates[-1]
                >= material.query_as_of.astimezone(ZoneInfo("America/New_York")).date()
            ):
                raise _governed_failure(
                    code.TIMING_CONTEXT,
                    condition.UNSUPPORTED,
                    "original source timing does not govern triggering row",
                )
            if self._bridge is None:
                raise _governed_failure(
                    code.GOVERNANCE_PREREQUISITES,
                    condition.UNAVAILABLE,
                    "trusted Bridge owner unavailable",
                )
            qualified = self._qualification.qualify(intent)
            if qualified.construction_result.receipt != material_owner.receipt:
                raise _governed_failure(
                    code.INPUT_INTEGRITY,
                    condition.CONTRADICTORY,
                    "exact material linkage mismatch",
                )
            bridge = self._bridge.bridge(
                b.PolygonCompletedDailyBridgeRequest(
                    supplied.artifact_reference,
                    supplied.construction_execution_id,
                    qualified.execution_id,
                    qualified.fingerprint,
                )
            )
            # Issuance resolves its own retained Qualification and proves no-drop
            # correspondence, including current storage. Dataset and normalized
            # historical identities intentionally have different meanings.
            bridge.to_dict()
            if bridge.qualification != qualified:
                raise _governed_failure(
                    code.MATERIAL_CORRESPONDENCE,
                    condition.CONTRADICTORY,
                    "Bridge/Qualification linkage mismatch",
                )
            if (
                bridge.completed_prices.evidence.dataset_content_fingerprint
                != observation.normalized_market_content_identity
            ):
                raise _governed_failure(
                    code.MATERIAL_CORRESPONDENCE,
                    condition.CONTRADICTORY,
                    "normalized historical-content mismatch",
                )
            task = qualified.task_freshness_result
            companion = task.companion
            receipt = material_owner.receipt
            return RadarResearchGovernedContextResolution(
                RadarResearchReadinessEvaluatedContext(
                    candidate_fingerprint=authenticated.candidate_fingerprint,
                    source_identity=authenticated.source_identity,
                    artifact_reference=material_owner.artifact.reference(),
                    construction_reference=RadarResearchReadinessOccurrenceReference(
                        receipt.execution_id,
                        receipt.history_namespace_id,
                        receipt.history_sequence,
                        receipt.fingerprint,
                    ),
                    current_qualification_reference=RadarResearchReadinessOccurrenceReference(
                        qualified.execution_id,
                        qualified.history_namespace_id,
                        qualified.history_sequence,
                        qualified.fingerprint,
                    ),
                    task_freshness_reference=PolygonCompletedDailyFreshnessExecutionReference(
                        task.freshness_record.reference(),
                        companion.execution_id,
                        companion.history_namespace_id,
                        companion.history_sequence,
                        companion.available_at,
                        companion.fingerprint,
                    ),
                    bridge_reference=PolygonCompletedDailyTechnicalRequest(
                        supplied.artifact_reference,
                        bridge.history_namespace_id,
                        bridge.history_sequence,
                        bridge.execution_id,
                        bridge.fingerprint,
                    ),
                )
            )
        except RadarResearchGovernedContextError:
            raise
        except q.PolygonCompletedDailyQualificationRefused as error:
            reason = error.reason
            blocked = reason in (
                q.PolygonCompletedDailyQualificationRefusalReason.INPUT_UNAVAILABLE,
                q.PolygonCompletedDailyQualificationRefusalReason.TASK_UNAVAILABLE,
                q.PolygonCompletedDailyQualificationRefusalReason.LIFECYCLE_REFUSED,
            )
            raise _governed_failure(
                code.GOVERNANCE_PREREQUISITES,
                condition.UNSATISFIED if blocked else condition.CONTRADICTORY,
                str(error),
            ) from error
        except b.PolygonCompletedDailyBridgeRefused as error:
            absent = (
                error.reason
                is b.PolygonCompletedDailyBridgeRefusalReason.QUALIFICATION_UNAVAILABLE
            )
            raise _governed_failure(
                code.GOVERNANCE_PREREQUISITES,
                condition.UNAVAILABLE if absent else condition.CONTRADICTORY,
                str(error),
            ) from error
        except CalendarError as error:
            raise _governed_failure(
                code.MATERIAL_CORRESPONDENCE, condition.UNSUPPORTED, str(error)
            ) from error
        except (
            TypeError,
            ValueError,
            RuntimeError,
            AttributeError,
            ArithmeticError,
        ) as error:
            raise _governed_failure(
                code.INPUT_INTEGRITY, condition.CONTRADICTORY, str(error)
            ) from error


class RadarResearchReadinessApplicationService:
    """Compose trusted resolution into a recorded assessment, then stop.

    READY describes this assessment only. A future invoker must independently
    revalidate current conditions. No acquisition or downstream capability is a
    dependency. Failed governed resolution exposes no partial references/check
    trace, so its incomplete concern families remain explicitly NOT_CHECKED.
    """

    def __init__(
        self,
        pending_resolver: RadarResearchPendingResolver,
        governed_context_resolver: RadarResearchGovernedContextResolver,
        *,
        execution_clock: Callable[[], datetime] | None = None,
    ) -> None:
        if type(pending_resolver) is not RadarResearchPendingResolver:
            raise TypeError("exact trusted Pending resolver required")
        if type(governed_context_resolver) is not RadarResearchGovernedContextResolver:
            raise TypeError("exact trusted governed-context resolver required")
        self._pending_resolver = pending_resolver
        self._governed_context_resolver = governed_context_resolver
        self._clock = execution_clock or (lambda: datetime.now(UTC))

    def assess(
        self, request: RadarResearchReadinessRequest
    ) -> RadarResearchReadinessAssessment:
        # Invalid contract values cannot be retained in the frozen assessment.
        # Their contract validation errors propagate rather than inventing inputs.
        supplied = replace(request)
        started = _timestamp(self._clock())
        code = RadarResearchReadinessFindingCode
        condition = RadarResearchReadinessFindingCondition
        failure: RadarResearchReadinessFinding | None = None
        context: RadarResearchReadinessEvaluatedContext | None = None
        try:
            pending = self._pending_resolver.resolve(supplied)
        except RadarCandidateDeliveryUnavailableError as error:
            failure = RadarResearchReadinessFinding(
                code.PENDING_AUTHORITY, condition.UNAVAILABLE, str(error)
            )
        except RadarCandidateDeliveryError as error:
            failure = RadarResearchReadinessFinding(
                code.PENDING_AUTHORITY, condition.CONTRADICTORY, str(error)
            )
        else:
            context = RadarResearchReadinessEvaluatedContext(
                candidate_fingerprint=pending.candidate_fingerprint,
                source_identity=pending.source_identity,
            )
            try:
                resolved = self._governed_context_resolver.resolve(pending, supplied)
            except RadarResearchGovernedContextError as error:
                failure = error.finding
            else:
                evaluated = resolved.evaluated_context
                if (
                    evaluated.candidate_fingerprint != pending.candidate_fingerprint
                    or evaluated.source_identity != pending.source_identity
                ):
                    failure = RadarResearchReadinessFinding(
                        code.INPUT_INTEGRITY,
                        condition.CONTRADICTORY,
                        "authenticated Pending/governed context mismatch",
                    )
                else:
                    context = evaluated

        findings: list[RadarResearchReadinessFinding] = []
        for concern in code:
            if failure is not None and failure.code is concern:
                findings.append(failure)
            if failure is None or (
                concern is code.PENDING_AUTHORITY and context is not None
            ):
                findings.append(
                    RadarResearchReadinessFinding(concern, condition.PASSED)
                )
            elif concern is not code.PENDING_AUTHORITY:
                findings.append(
                    RadarResearchReadinessFinding(concern, condition.NOT_CHECKED)
                )
        outcome = (
            RadarResearchReadinessOutcome.READY
            if failure is None
            else failure.required_outcome
        )
        if outcome is None:
            raise RuntimeError("resolver failure requires a bounded negative condition")
        return RadarResearchReadinessAssessment(
            request=supplied,
            policy=RadarResearchReadinessPolicyIdentity(),
            outcome=outcome,
            execution_started_at=started,
            execution_completed_at=_timestamp(self._clock()),
            findings=tuple(findings),
            evaluated_context=context,
        )
