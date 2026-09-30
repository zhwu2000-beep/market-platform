"""Frozen readiness contracts and opt-in retained Pending authentication."""

import inspect
import json
from dataclasses import FrozenInstanceError, fields, replace
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from test_radar_application import AS_OF, INSTRUMENT
from test_radar_candidate_delivery import Harness

from market_platform._fingerprint import canonical_fingerprint
from market_platform.application import radar_candidate_delivery as delivery
from market_platform.application import radar_candidate_delivery_store as storage
from market_platform.application import radar_research_escalation as subject
from market_platform.application.polygon_completed_daily_production_admission import (
    PolygonCompletedDailyFreshnessExecutionReference,
)
from market_platform.application.polygon_completed_daily_production_technical import (
    PolygonCompletedDailyTechnicalRequest,
)
from market_platform.application.radar_candidate import (
    RadarCandidateDecision,
    RadarCandidateDecisionReason,
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
from market_platform.application.radar_research_escalation import (
    RadarResearchPendingResolution,
    RadarResearchPendingResolver,
)
from market_platform.application.radar_research_escalation import (
    RadarResearchReadinessAssessment as Assessment,
)
from market_platform.application.radar_research_escalation import (
    RadarResearchReadinessEvaluatedContext as EvaluatedContext,
)
from market_platform.application.radar_research_escalation import (
    RadarResearchReadinessFinding as Finding,
)
from market_platform.application.radar_research_escalation import (
    RadarResearchReadinessFindingCode as Code,
)
from market_platform.application.radar_research_escalation import (
    RadarResearchReadinessFindingCondition as Condition,
)
from market_platform.application.radar_research_escalation import (
    RadarResearchReadinessOccurrenceReference as OccurrenceReference,
)
from market_platform.application.radar_research_escalation import (
    RadarResearchReadinessOutcome as Outcome,
)
from market_platform.application.radar_research_escalation import (
    RadarResearchReadinessPolicyIdentity as Policy,
)
from market_platform.application.radar_research_escalation import (
    RadarResearchReadinessRequest as Request,
)
from market_platform.evidence.classification import (
    EvidenceAuthority,
    EvidenceInformationClass,
)
from market_platform.evidence.references import (
    EvidenceArtifactReference,
    EvidenceIdentityReference,
)
from market_platform.evidence.temporal import EvidenceFreshnessEvaluationReference
from market_platform.radar.lightweight_observation import (
    EMA8_EMA20_OBSERVATION_LOOKUP,
    RadarEmaRelation,
)
from market_platform.radar.trigger import CURRENT_MARKET_CONTENT_LOOKUP

ANALYSIS = datetime(2026, 9, 24, tzinfo=UTC)
KNOWLEDGE = ANALYSIS + timedelta(days=1)
STARTED = KNOWLEDGE + timedelta(hours=1)
COMPLETED = STARTED + timedelta(seconds=2)


def request(**changes):
    # Purported references deliberately have no corresponding owned records.
    return replace(
        Request(
            candidate_fingerprint="sha256:" + "a" * 64,
            source_identity=SourceRecoveryIdentity("sha256:" + "b" * 64),
            artifact_reference=EvidenceArtifactReference(
                "test-artifact",
                "1",
                "sha256:" + "c" * 64,
                EvidenceInformationClass.SOURCE_OBSERVATION,
                EvidenceAuthority.EXTERNAL_ORIGIN,
            ),
            construction_execution_id="polygon_completed_daily_construction:"
            + "d" * 32,
            consumer_reference=EvidenceIdentityReference(
                "consumer", "market_platform.research.daily_technical", "1.0.0"
            ),
            intended_use_reference=EvidenceIdentityReference(
                "use", "production.polygon_completed_daily.use.daily_technical", "1.0.0"
            ),
            technical_profile_reference=EvidenceIdentityReference(
                "analysis_profile",
                "daily_technical_analysis_default",
                "1.0.0",
                "sha256:" + "e" * 64,
            ),
            analysis_as_of=ANALYSIS,
            knowledge_as_of=KNOWLEDGE,
        ),
        **changes,
    )


def passed_findings():
    return tuple(Finding(code, Condition.PASSED) for code in Code)


def occurrence_reference(kind, **changes):
    # Existing identity shapes only; no corresponding owned occurrence exists.
    return replace(
        OccurrenceReference(
            execution_id=f"polygon_completed_daily_{kind}:" + "1" * 32,
            history_namespace_id=f"polygon_completed_daily_{kind}_history:" + "2" * 32,
            history_sequence=3,
            fingerprint="sha256:" + "3" * 64,
        ),
        **changes,
    )


def evaluated_context(**changes):
    supplied = request()
    return replace(
        EvaluatedContext(
            candidate_fingerprint=supplied.candidate_fingerprint,
            source_identity=supplied.source_identity,
            artifact_reference=supplied.artifact_reference,
            construction_reference=occurrence_reference(
                "construction", execution_id=supplied.construction_execution_id
            ),
            current_qualification_reference=occurrence_reference("qualification"),
            task_freshness_reference=PolygonCompletedDailyFreshnessExecutionReference(
                freshness_evaluation_reference=EvidenceFreshnessEvaluationReference(
                    artifact_reference=supplied.artifact_reference,
                    freshness_rule_fingerprint="sha256:" + "4" * 64,
                    evaluation_scope="task",
                    evaluation_as_of=ANALYSIS,
                    result=True,
                    evaluation_fingerprint="sha256:" + "5" * 64,
                ),
                execution_id="polygon_completed_daily_freshness:" + "6" * 32,
                history_namespace_id="polygon_completed_daily_freshness_history:"
                + "7" * 32,
                history_sequence=8,
                available_at=KNOWLEDGE,
                companion_fingerprint="sha256:" + "8" * 64,
            ),
            bridge_reference=PolygonCompletedDailyTechnicalRequest(
                artifact_reference=supplied.artifact_reference,
                bridge_history_namespace_id="polygon_completed_daily_bridge_history:"
                + "9" * 32,
                bridge_history_sequence=10,
                bridge_execution_id="polygon_completed_daily_bridge:" + "a" * 32,
                bridge_fingerprint="sha256:" + "b" * 64,
            ),
        ),
        **changes,
    )


def assessment(outcome=Outcome.READY, findings=None, **changes):
    return Assessment(
        **{
            "request": request(),
            "policy": Policy(),
            "outcome": outcome,
            "execution_started_at": STARTED,
            "execution_completed_at": COMPLETED,
            "findings": passed_findings() if findings is None else findings,
            "evaluated_context": evaluated_context()
            if outcome is Outcome.READY
            else None,
            **changes,
        }
    )


def test_closed_policy_identity_and_exact_window():
    policy = Policy()
    payload = {
        "schema_version": "radar_research_escalation_readiness_policy/v1",
        "policy_id": "exact_governed_250_session_technical_readiness",
        "behavioral_revision": "1",
    }
    assert policy.required_session_count == 250
    assert policy.to_dict() == {
        **payload,
        "fingerprint": canonical_fingerprint(payload),
    }
    assert policy == Policy() == replace(policy)
    assert hash(policy) == hash(Policy())
    assert json.loads(json.dumps(policy.to_dict())) == policy.to_dict()
    assert "complete exact ordered 250-session" in Policy.__doc__
    assert "triggering completed session" in Policy.__doc__
    assert "current governed qualification" in Policy.__doc__
    assert "Acquisition, refetch and" in Policy.__doc__
    assert "unsupported timing is REFUSED" in Policy.__doc__
    with pytest.raises(FrozenInstanceError):
        policy.policy_id = "other"
    with pytest.raises(TypeError):
        Policy(required_session_count=249)


@pytest.mark.parametrize(
    "changes",
    [
        {"policy_id": "selected_meaningful_transition"},
        {"policy_id": "daily_technical_analysis_default"},
        {"policy_id": "evidence_admission"},
        {"policy_id": "research_invocation"},
        {"behavioral_revision": "2"},
        {"schema_version": "radar_research_escalation_readiness_policy/v2"},
        {"behavioral_revision": 1},
    ],
)
def test_policy_rejects_unsupported_identity_without_fallback(changes):
    with pytest.raises((TypeError, ValueError)):
        Policy(**changes)


def test_outcomes_are_exact_distinct_string_values():
    assert [item.value for item in Outcome] == ["READY", "BLOCKED", "REFUSED"]
    assert json.loads(json.dumps(list(Outcome))) == ["READY", "BLOCKED", "REFUSED"]
    for outcome in Outcome:
        assert Outcome(outcome.value) is outcome
    with pytest.raises(ValueError):
        Outcome("AUTHORIZED")


def test_request_preserves_existing_references_and_occurrence_distinction():
    supplied = request()
    same = replace(supplied)
    assert same == supplied
    assert hash(same) == hash(supplied)
    for name in (
        "source_identity",
        "artifact_reference",
        "consumer_reference",
        "intended_use_reference",
        "technical_profile_reference",
    ):
        assert getattr(same, name) == getattr(supplied, name)
    assert same.candidate_fingerprint == supplied.candidate_fingerprint
    assert same.construction_execution_id == supplied.construction_execution_id
    other_occurrence = replace(
        supplied,
        construction_execution_id="polygon_completed_daily_construction:" + "f" * 32,
    )
    assert other_occurrence.artifact_reference == supplied.artifact_reference
    assert other_occurrence != supplied
    assert supplied.analysis_as_of == ANALYSIS
    assert supplied.knowledge_as_of == KNOWLEDGE
    assert "Untrusted" in Request.__doc__
    assert "no supplied reference proves authority" in Request.__doc__


@pytest.mark.parametrize(
    "changes",
    [
        {"candidate_fingerprint": "copied-candidate"},
        {"source_identity": "sha256:" + "b" * 64},
        {"artifact_reference": {}},
        {"construction_execution_id": "sha256:" + "c" * 64},
        {"consumer_reference": {}},
        {"intended_use_reference": "daily_technical"},
        {"technical_profile_reference": True},
    ],
)
def test_request_rejects_wrong_reference_shapes(changes):
    with pytest.raises((TypeError, ValueError)):
        request(**changes)


@pytest.mark.parametrize("name", ["analysis_as_of", "knowledge_as_of"])
def test_request_requires_aware_timestamps(name):
    with pytest.raises(ValueError, match="timezone-aware"):
        request(**{name: ANALYSIS.replace(tzinfo=None)})


def test_request_canonicalizes_times_without_collapsing_cutoffs():
    offset = timezone(timedelta(hours=8))
    supplied = request(
        analysis_as_of=ANALYSIS.astimezone(offset),
        knowledge_as_of=KNOWLEDGE.astimezone(offset),
    )
    assert supplied == request()
    assert supplied.analysis_as_of.tzinfo is UTC
    assert supplied.knowledge_as_of.tzinfo is UTC
    assert supplied.analysis_as_of != supplied.knowledge_as_of
    with pytest.raises(ValueError, match="after knowledge"):
        request(analysis_as_of=KNOWLEDGE + timedelta(seconds=1))


@pytest.mark.parametrize("code", list(Code))
@pytest.mark.parametrize(
    ("condition", "required"),
    [
        (Condition.PASSED, None),
        (Condition.UNAVAILABLE, Outcome.BLOCKED),
        (Condition.UNSATISFIED, Outcome.BLOCKED),
        (Condition.CONTRADICTORY, Outcome.REFUSED),
        (Condition.UNSUPPORTED, Outcome.REFUSED),
        (Condition.NOT_CHECKED, None),
    ],
)
def test_structured_findings_keep_failure_semantics_independent_of_detail(
    code, condition, required
):
    finding = Finding(code, condition)
    assert finding.required_outcome is required
    assert (
        replace(finding, detail="Diagnostic explanation").required_outcome is required
    )
    assert finding == replace(finding)
    assert hash(finding) == hash(replace(finding))


@pytest.mark.parametrize(
    "args",
    [
        ("pending_authority", Condition.UNAVAILABLE),
        (Code.PENDING_AUTHORITY, "UNAVAILABLE"),
        (Code.PENDING_AUTHORITY, Condition.UNAVAILABLE, {}),
    ],
)
def test_findings_require_typed_machine_semantics(args):
    with pytest.raises(TypeError):
        Finding(*args)


def test_ready_result_is_a_descriptive_value_with_explicit_context():
    result = assessment()
    assert result.outcome is Outcome.READY
    assert result.request == request()
    assert result.evaluated_context == evaluated_context()
    assert result.policy == Policy()
    assert result.findings == passed_findings()
    assert result.unperformed_checks == ()
    assert result.execution_started_at == STARTED
    assert result.execution_completed_at == COMPLETED
    assert result.request.analysis_as_of < result.request.knowledge_as_of < STARTED
    assert result == replace(result)
    assert hash(result) == hash(replace(result))
    assert repr(result) == repr(replace(result))
    assert "not an authenticated publication or permit" in Assessment.__doc__


def test_blocked_result_does_not_imply_later_checks_passed():
    findings = (
        Finding(Code.INPUT_INTEGRITY, Condition.PASSED),
        Finding(Code.PENDING_AUTHORITY, Condition.UNAVAILABLE),
        Finding(Code.MATERIAL_CORRESPONDENCE, Condition.NOT_CHECKED),
    )
    result = assessment(Outcome.BLOCKED, findings)
    assert result.findings == findings
    assert result.unperformed_checks == (
        Code.MATERIAL_CORRESPONDENCE,
        Code.GOVERNANCE_PREREQUISITES,
        Code.TIMING_CONTEXT,
    )


@pytest.mark.parametrize("condition", [Condition.CONTRADICTORY, Condition.UNSUPPORTED])
def test_refused_result_retains_refusal_even_with_ordinary_absence(condition):
    result = assessment(
        Outcome.REFUSED,
        (
            Finding(Code.PENDING_AUTHORITY, Condition.UNAVAILABLE),
            Finding(Code.TIMING_CONTEXT, condition),
        ),
    )
    assert result.outcome is Outcome.REFUSED
    assert Code.GOVERNANCE_PREREQUISITES in result.unperformed_checks


@pytest.mark.parametrize(
    "condition", [c for c in Condition if c is not Condition.PASSED]
)
def test_ready_rejects_negative_or_unperformed_findings(condition):
    findings = (*passed_findings(), Finding(Code.PENDING_AUTHORITY, condition))
    with pytest.raises(ValueError, match="READY requires"):
        assessment(findings=findings)


@pytest.mark.parametrize("missing", list(Code))
def test_ready_requires_every_policy_concern_to_have_passed(missing):
    with pytest.raises(ValueError, match="READY requires"):
        assessment(
            findings=tuple(f for f in passed_findings() if f.code is not missing)
        )


@pytest.mark.parametrize("outcome", list(Outcome))
def test_empty_findings_cannot_explain_an_assessment(outcome):
    with pytest.raises(ValueError, match="requires structured findings"):
        assessment(outcome, ())


@pytest.mark.parametrize("condition", [Condition.CONTRADICTORY, Condition.UNSUPPORTED])
def test_blocked_cannot_downgrade_contradictions_or_unsupported_authority(condition):
    with pytest.raises(ValueError, match="without refusal"):
        assessment(
            Outcome.BLOCKED,
            (
                Finding(Code.MATERIAL_CORRESPONDENCE, Condition.UNAVAILABLE),
                Finding(Code.PENDING_AUTHORITY, condition),
            ),
        )


@pytest.mark.parametrize("outcome", [Outcome.BLOCKED, Outcome.REFUSED])
def test_negative_result_requires_a_matching_condition(outcome):
    with pytest.raises(ValueError):
        assessment(outcome)
    with pytest.raises(ValueError):
        assessment(outcome, (Finding(Code.PENDING_AUTHORITY, Condition.NOT_CHECKED),))


@pytest.mark.parametrize(
    "changes",
    [
        {"request": {}},
        {"evaluated_context": {}},
        {"evaluated_context": request()},
        {"policy": {}},
        {"outcome": "READY"},
        {"findings": list(passed_findings())},
        {"findings": ("PASSED",)},
    ],
)
def test_result_rejects_untyped_or_mutable_inputs(changes):
    with pytest.raises(TypeError):
        assessment(**changes)


@pytest.mark.parametrize("name", ["execution_started_at", "execution_completed_at"])
def test_result_requires_aware_execution_times(name):
    with pytest.raises(ValueError, match="timezone-aware"):
        assessment(**{name: STARTED.replace(tzinfo=None)})


def test_result_canonicalizes_execution_times_and_preserves_request_times():
    offset = timezone(timedelta(hours=-4))
    result = assessment(
        execution_started_at=STARTED.astimezone(offset),
        execution_completed_at=COMPLETED.astimezone(offset),
    )
    assert result == assessment()
    assert result.execution_started_at.tzinfo is UTC
    assert result.execution_completed_at.tzinfo is UTC
    assert result.request == request()
    with pytest.raises(ValueError, match="completion precedes"):
        assessment(execution_completed_at=STARTED - timedelta(seconds=1))
    with pytest.raises(ValueError, match="after assessment execution"):
        assessment(request=request(knowledge_as_of=COMPLETED + timedelta(seconds=1)))
    # Knowledge can be captured during execution; it need not equal start/completion.
    assert (
        assessment(request=request(knowledge_as_of=STARTED)).request.knowledge_as_of
        == STARTED
    )


def test_policy_fingerprint_mismatch_is_not_silently_repaired_by_result():
    policy = Policy()
    object.__setattr__(policy, "fingerprint", "sha256:" + "0" * 64)
    with pytest.raises(ValueError, match="policy fingerprint mismatch"):
        assessment(policy=policy)


@pytest.mark.parametrize(
    "value",
    [
        Policy(),
        request(),
        evaluated_context(),
        occurrence_reference("qualification"),
        Finding(Code.INPUT_INTEGRITY, Condition.PASSED),
        assessment(),
    ],
)
def test_contracts_are_frozen_without_mutable_collection_defaults(value):
    first = fields(value)[0]
    with pytest.raises(FrozenInstanceError):
        setattr(value, first.name, getattr(value, first.name))
    for item in fields(value):
        assert not isinstance(item.default, (dict, list, set))
        assert not isinstance(getattr(value, item.name), (dict, list, set))


def test_contract_construction_provides_no_authority_or_execution_capability():
    # Even a coherent synthetic READY result authenticates none of these references.
    result = assessment()
    assert "construction authenticates nothing" in subject.__doc__
    assert "independently revalidate current" in subject.__doc__
    for value in (
        request(),
        result,
        result.evaluated_context,
        occurrence_reference("construction"),
        result.policy,
        *result.findings,
    ):
        assert not hasattr(value, "__dict__")
        for forbidden in (
            "authorized",
            "permit",
            "token",
            "dispatch",
            "execute",
            "candidate",
            "qualification_result",
            "bridge_payload",
            "technical_result",
            "strategy_result",
        ):
            assert not hasattr(value, forbidden)
    assert not any(
        inspect.isfunction(value) and not name.startswith("_")
        for name, value in vars(subject).items()
        if getattr(value, "__module__", None) == subject.__name__
    )


@pytest.mark.parametrize("code", list(Code))
@pytest.mark.parametrize("checked", [Condition.PASSED, Condition.UNSATISFIED])
@pytest.mark.parametrize(
    ("outcome", "failure"),
    [
        (Outcome.BLOCKED, Condition.UNAVAILABLE),
        (Outcome.REFUSED, Condition.UNSUPPORTED),
    ],
)
def test_negative_mixed_family_preserves_every_explicit_unperformed_check(
    code, checked, outcome, failure
):
    findings = (
        *passed_findings(),
        Finding(code, checked),
        Finding(code, Condition.NOT_CHECKED),
        Finding(Code.INPUT_INTEGRITY, failure),
    )
    result = assessment(outcome, findings)
    assert result.unperformed_checks == (code,)
    assert result.findings == findings
    assert assessment(outcome, tuple(reversed(findings))).unperformed_checks == (code,)
    if outcome is Outcome.REFUSED:
        with pytest.raises(ValueError, match="without refusal"):
            assessment(Outcome.BLOCKED, findings)


def test_evaluated_references_are_retained_separately_from_supplied_request():
    supplied = request()
    actual_artifact = replace(
        supplied.artifact_reference, artifact_id="evaluated-artifact"
    )
    actual_freshness = replace(
        evaluated_context().task_freshness_reference,
        freshness_evaluation_reference=replace(
            evaluated_context().task_freshness_reference.freshness_evaluation_reference,
            artifact_reference=actual_artifact,
        ),
    )
    actual = evaluated_context(
        candidate_fingerprint="sha256:" + "9" * 64,
        source_identity=SourceRecoveryIdentity("sha256:" + "0" * 64),
        artifact_reference=actual_artifact,
        construction_reference=occurrence_reference("construction"),
        task_freshness_reference=actual_freshness,
        bridge_reference=replace(
            evaluated_context().bridge_reference, artifact_reference=actual_artifact
        ),
    )
    result = assessment(
        Outcome.REFUSED,
        (Finding(Code.MATERIAL_CORRESPONDENCE, Condition.CONTRADICTORY),),
        request=supplied,
        evaluated_context=actual,
    )
    assert result.request == supplied
    assert result.evaluated_context == actual
    for item in fields(actual):
        assert getattr(result.evaluated_context, item.name) == getattr(
            actual, item.name
        )
    assert actual.source_identity != supplied.source_identity
    assert actual.candidate_fingerprint != supplied.candidate_fingerprint
    assert actual.artifact_reference != supplied.artifact_reference
    assert (
        actual.construction_reference.execution_id != supplied.construction_execution_id
    )
    assert actual.current_qualification_reference.fingerprint == "sha256:" + "3" * 64
    assert (
        actual.bridge_reference.bridge_execution_id
        == "polygon_completed_daily_bridge:" + "a" * 32
    )


@pytest.mark.parametrize("missing", [item.name for item in fields(EvaluatedContext)])
def test_ready_requires_each_necessary_evaluated_reference(missing):
    with pytest.raises(ValueError, match="READY requires complete evaluated-reference"):
        assessment(evaluated_context=evaluated_context(**{missing: None}))


@pytest.mark.parametrize("context", [None, EvaluatedContext()])
def test_ready_requires_explicit_evaluated_context(context):
    with pytest.raises(ValueError, match="READY requires complete evaluated-reference"):
        assessment(evaluated_context=context)


@pytest.mark.parametrize(
    ("outcome", "condition"),
    [
        (Outcome.BLOCKED, Condition.UNAVAILABLE),
        (Outcome.REFUSED, Condition.CONTRADICTORY),
    ],
)
@pytest.mark.parametrize(
    "context",
    [
        None,
        EvaluatedContext(),
        EvaluatedContext(source_identity=request().source_identity),
        EvaluatedContext(construction_reference=occurrence_reference("construction")),
    ],
)
def test_negative_outcomes_retain_partial_or_missing_evaluated_context(
    outcome, condition, context
):
    result = assessment(
        outcome,
        (Finding(Code.PENDING_AUTHORITY, condition),),
        evaluated_context=context,
    )
    assert result.evaluated_context == context
    if context is not None:
        assert result.evaluated_context.current_qualification_reference is None
        assert result.evaluated_context.task_freshness_reference is None
        assert result.evaluated_context.bridge_reference is None


@pytest.mark.parametrize(
    "changes",
    [
        {"candidate_fingerprint": "copied-candidate"},
        {"source_identity": "sha256:" + "0" * 64},
        {"artifact_reference": {}},
        {"construction_reference": request().construction_execution_id},
        {"current_qualification_reference": True},
        {"task_freshness_reference": {}},
        {"bridge_reference": {}},
        {"construction_reference": occurrence_reference("qualification")},
        {"current_qualification_reference": occurrence_reference("construction")},
        {"bridge_reference": occurrence_reference("qualification")},
    ],
)
def test_evaluated_context_rejects_payloads_and_wrong_reference_kinds(changes):
    with pytest.raises((TypeError, ValueError)):
        evaluated_context(**changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"execution_id": "copied-result"},
        {"execution_id": 1},
        {"history_namespace_id": "polygon_completed_daily_bridge_history:" + "2" * 32},
        {"history_namespace_id": None},
        {"history_sequence": 0},
        {"history_sequence": True},
        {"fingerprint": "copied-fingerprint"},
    ],
)
def test_occurrence_reference_preserves_existing_identity_conventions(changes):
    with pytest.raises((TypeError, ValueError)):
        occurrence_reference("qualification", **changes)


def test_evaluated_context_is_a_value_without_payloads_or_duplicated_timing():
    context = evaluated_context()
    assert context == replace(context)
    assert hash(context) == hash(replace(context))
    assert repr(context) == repr(replace(context))
    assert "Construction authenticates nothing" in EvaluatedContext.__doc__
    assert "construction authenticates nothing" in OccurrenceReference.__doc__
    allowed_types = (
        str,
        SourceRecoveryIdentity,
        EvidenceArtifactReference,
        OccurrenceReference,
        PolygonCompletedDailyFreshnessExecutionReference,
        PolygonCompletedDailyTechnicalRequest,
    )
    assert all(
        type(getattr(context, item.name)) in allowed_types for item in fields(context)
    )
    freshness = context.task_freshness_reference
    assert freshness == evaluated_context().task_freshness_reference
    assert freshness.freshness_evaluation_reference.evaluation_as_of == ANALYSIS
    assert freshness.available_at == KNOWLEDGE
    assert freshness.companion_fingerprint == "sha256:" + "8" * 64
    # The companion holds execution times; retained Qualification/Bridge results
    # hold their cutoffs and timing. Readiness neither copies nor rewrites them.
    assert not any(
        isinstance(getattr(context, item.name), datetime) for item in fields(context)
    )
    for name in ("construction_reference", "current_qualification_reference"):
        reference = getattr(context, name)
        assert [item.name for item in fields(reference)] == [
            "execution_id",
            "history_namespace_id",
            "history_sequence",
            "fingerprint",
        ]
        assert reference == replace(reference)
        assert hash(reference) == hash(replace(reference))
    assert (
        context.bridge_reference.to_dict()
        == evaluated_context().bridge_reference.to_dict()
    )
    with pytest.raises(TypeError):
        EvaluatedContext(qualification_result=True)
    with pytest.raises(TypeError):
        EvaluatedContext(bridge_payload={})


def retained_graph(h):
    source = h.store.discover_prepared(INSTRUMENT)[0]
    accepted = h.store.read_accepted(source.identity)
    decision = h.store.read_decision(source.identity)
    pending = h.store.read_pending(decision.decision.candidate.fingerprint)
    supplied = request(
        candidate_fingerprint=pending.candidate_fingerprint,
        source_identity=source.identity,
    )
    return source, accepted, decision, pending, supplied


def retained_bytes(h):
    return {
        str(path.relative_to(h.records.parent)): path.read_bytes()
        for root in (h.records, h.checkpoints)
        for path in root.iterdir()
    }


def forbid_regeneration(h, monkeypatch):
    forbidden = Mock(side_effect=AssertionError("Resolution must only read"))
    monkeypatch.setattr(delivery, "evaluate_radar_candidate", forbidden)
    for name in ("recover", "publish", "_complete", "_save"):
        monkeypatch.setattr(delivery.RadarCandidateDeliveryCoordinator, name, forbidden)
    monkeypatch.setattr(storage.RadarCandidateDeliveryFileStore, "_publish", forbidden)
    monkeypatch.setattr(h.checkpoint, "save_state", forbidden)
    return forbidden


@pytest.fixture
def retained_pending(tmp_path, monkeypatch):
    h = Harness(tmp_path)
    h.run(h.coordinator())
    graph = retained_graph(h)
    h.restart()
    forbidden = forbid_regeneration(h, monkeypatch)
    yield h, graph
    forbidden.assert_not_called()
    h.assert_no_acquisition()


def test_trusted_complete_pending_resolution_is_bounded_and_non_consuming(
    retained_pending,
    monkeypatch,
):
    h, (source, accepted, decision, pending, supplied) = retained_pending
    # Purported material references must not even be projected by this slice.
    forbidden = Mock(side_effect=AssertionError("No material resolution"))
    monkeypatch.setattr(EvidenceArtifactReference, "to_dict", forbidden)
    monkeypatch.setattr(PolygonCompletedDailyTechnicalRequest, "to_dict", forbidden)
    before = retained_bytes(h)
    resolver = RadarResearchPendingResolver(h.store)
    resolved = resolver.resolve(supplied)
    assert resolved == resolver.resolve(supplied)
    assert resolved.candidate_fingerprint == pending.candidate_fingerprint
    assert resolved.source_identity == source.identity == accepted.source_identity
    assert (
        resolved.source_identity == decision.source_identity == pending.source_identity
    )
    assert resolved.source_identity is not supplied.source_identity
    assert [item.name for item in fields(resolved)] == [
        "candidate_fingerprint",
        "source_identity",
    ]
    context = EvaluatedContext(
        candidate_fingerprint=resolved.candidate_fingerprint,
        source_identity=resolved.source_identity,
    )
    assert all(
        getattr(context, item.name) is None
        for item in fields(context)
        if item.name not in {"candidate_fingerprint", "source_identity"}
    )
    assert hash(resolved) == hash(replace(resolved))
    assert not hasattr(resolved, "__dict__")
    assert not hasattr(resolved, "outcome")
    with pytest.raises(FrozenInstanceError):
        resolved.source_identity = supplied.source_identity
    assert h.store.read_pending(resolved.candidate_fingerprint) == pending
    assert retained_bytes(h) == before
    forbidden.assert_not_called()


def test_missing_pending_is_unavailable_without_completing_publication(
    retained_pending,
):
    h, (_, _, _, pending, supplied) = retained_pending
    (h.records / storage._filename(pending)).unlink()
    before = retained_bytes(h)
    with pytest.raises(RadarCandidateDeliveryUnavailableError):
        RadarResearchPendingResolver(h.store).resolve(supplied)
    assert retained_bytes(h) == before


@pytest.mark.parametrize("missing", [0, 1, 2, "all"])
def test_missing_graph_links_and_orphan_pending_are_refused(retained_pending, missing):
    h, graph = retained_pending
    for index in range(3) if missing == "all" else (missing,):
        (h.records / storage._filename(graph[index])).unlink()
    before = retained_bytes(h)
    with pytest.raises(RadarCandidateDeliveryError) as caught:
        RadarResearchPendingResolver(h.store).resolve(graph[-1])
    assert caught.value.failure is DeliveryFailure.INVARIANT
    assert retained_bytes(h) == before


@pytest.mark.parametrize(
    "contradiction",
    [
        "ineligible_decision",
        "nonmatching_candidate",
        "pending_decision",
        "accepted_state",
        "pending_source",
        "candidate_fingerprint",
        "decision_source",
        "prepared_policy",
        "decision_policy",
        "pending_policy",
    ],
)
def test_retained_graph_contradictions_are_refused(retained_pending, contradiction):
    h, (source, accepted, decision, pending, supplied) = retained_pending
    record = pending
    if contradiction == "ineligible_decision":
        record = replace(
            decision,
            decision=RadarCandidateDecision(
                decision.decision.policy,
                RadarCandidateDecisionReason.NOT_SELECTED,
                None,
            ),
        )
    elif contradiction in {"nonmatching_candidate", "pending_decision"}:
        candidate = decision.decision.candidate
        altered = replace(
            candidate.source_observation_state,
            market_observation=replace(
                candidate.source_observation_state.market_observation, observed_at=AS_OF
            ),
        )
        record = replace(
            pending if contradiction == "pending_decision" else decision,
            decision=replace(
                decision.decision,
                candidate=replace(candidate, source_observation_state=altered),
            ),
        )
    elif contradiction == "accepted_state":
        record = replace(
            accepted,
            accepted_state=replace(
                accepted.accepted_state,
                market_observation=replace(
                    accepted.accepted_state.market_observation, observed_at=AS_OF
                ),
            ),
        )
    elif contradiction.startswith("prepared"):
        record = source
    elif contradiction.startswith("decision"):
        record = decision
    raw = record.to_dict()
    if contradiction in {"pending_source", "decision_source"}:
        raw["source_identity"] = "sha256:" + "f" * 64
    elif contradiction == "candidate_fingerprint":
        raw["candidate_fingerprint"] = "sha256:" + "f" * 64
    elif contradiction.endswith("policy"):
        policy = raw["policy"] if record is source else raw["decision"]["policy"]
        policy["behavioral_revision"] = "2"
    (h.records / storage._filename(record)).write_text(
        json.dumps(raw), encoding="utf-8"
    )
    before = retained_bytes(h)
    with pytest.raises(RadarCandidateDeliveryError) as caught:
        RadarResearchPendingResolver(h.store).resolve(supplied)
    assert caught.value.failure is DeliveryFailure.INVARIANT
    assert retained_bytes(h) == before


@pytest.mark.parametrize("index", range(4))
def test_malformed_retained_records_are_refused_without_repair(retained_pending, index):
    h, graph = retained_pending
    (h.records / storage._filename(graph[index])).write_bytes(b'{"partial":')
    before = retained_bytes(h)
    with pytest.raises(RadarCandidateDeliveryError) as caught:
        RadarResearchPendingResolver(h.store).resolve(graph[-1])
    assert caught.value.failure is DeliveryFailure.INVARIANT
    assert retained_bytes(h) == before


def test_source_lookup_mismatch_is_refused(retained_pending):
    h, (*_, supplied) = retained_pending
    mismatched = replace(
        supplied, source_identity=SourceRecoveryIdentity("sha256:" + "f" * 64)
    )
    with pytest.raises(RadarCandidateDeliveryError) as caught:
        RadarResearchPendingResolver(h.store).resolve(mismatched)
    assert caught.value.failure is DeliveryFailure.INVARIANT


def test_no_matching_candidate_is_unavailable(retained_pending):
    h, (*_, supplied) = retained_pending
    with pytest.raises(RadarCandidateDeliveryUnavailableError):
        RadarResearchPendingResolver(h.store).resolve(
            replace(supplied, candidate_fingerprint="sha256:" + "f" * 64)
        )


def test_unreadable_retained_record_is_unavailable_without_repair(
    retained_pending,
    monkeypatch,
):
    h, (_, _, _, pending, supplied) = retained_pending
    path = h.records / storage._filename(pending)
    before = retained_bytes(h)
    original = type(path).open

    def unavailable(target, *args, **kwargs):
        if target == path:
            raise PermissionError("Retained record inaccessible")
        return original(target, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(type(path), "open", unavailable)
        with pytest.raises(RadarCandidateDeliveryUnavailableError):
            RadarResearchPendingResolver(h.store).resolve(supplied)
    assert retained_bytes(h) == before


@pytest.mark.parametrize("detached", ["pending", "candidate", "json", "resolution"])
def test_detached_records_cannot_replace_owner_lookup(retained_pending, detached):
    h, (_, _, _, pending, supplied) = retained_pending
    values = {
        "pending": pending,
        "candidate": pending.decision.candidate,
        "json": pending.to_dict(),
        "resolution": RadarResearchPendingResolution(
            pending.candidate_fingerprint, pending.source_identity
        ),
    }
    with pytest.raises(RadarCandidateDeliveryError) as caught:
        RadarResearchPendingResolver(h.store).resolve(values[detached])
    assert caught.value.failure is DeliveryFailure.INVARIANT
    for path in h.records.iterdir():
        path.unlink()
    # Keeping all detached values cannot restore the lost owned graph.
    with pytest.raises(RadarCandidateDeliveryUnavailableError):
        RadarResearchPendingResolver(h.store).resolve(supplied)
    with pytest.raises(TypeError):
        RadarResearchPendingResolver(values[detached])


@pytest.mark.parametrize("owner", ["none", "missing_root", "inaccessible_root"])
def test_lost_trusted_owner_fails_closed_without_root_creation(
    retained_pending,
    monkeypatch,
    owner,
):
    h, (*_, supplied) = retained_pending
    store = h.store
    missing = h.records.parent / "lost-owner"
    before = retained_bytes(h)
    if owner == "none":
        store = None
    elif owner == "missing_root":
        store = RadarCandidateDeliveryFileStore(missing)
    with monkeypatch.context() as patch:
        if owner == "inaccessible_root":
            patch.setattr(storage.os, "scandir", Mock(side_effect=PermissionError))
        with pytest.raises(RadarCandidateDeliveryUnavailableError):
            RadarResearchPendingResolver(store).resolve(supplied)
    assert not missing.exists()
    assert retained_bytes(h) == before


@pytest.mark.parametrize("field", ["candidate_fingerprint", "source_identity"])
def test_corrupted_lookup_identity_is_refused_even_when_owner_unavailable(field):
    supplied = request()
    object.__setattr__(supplied, field, "invalid")
    with pytest.raises(RadarCandidateDeliveryError) as caught:
        RadarResearchPendingResolver(None).resolve(supplied)
    assert caught.value.failure is DeliveryFailure.INVARIANT


def test_previous_pending_resolves_after_later_checkpoint_replacement(
    tmp_path, monkeypatch
):
    h = Harness(tmp_path)
    h.run(h.coordinator())
    source, _, _, pending, supplied = retained_graph(h)
    new_light = replace(
        h.loaders[EMA8_EMA20_OBSERVATION_LOOKUP].return_value.observation,
        relation=RadarEmaRelation.BELOW,
        normalized_market_content_identity="sha256:" + "c" * 64,
    )
    current = h.loaders[CURRENT_MARKET_CONTENT_LOOKUP].return_value
    h.loaders[CURRENT_MARKET_CONTENT_LOOKUP].return_value = replace(
        current,
        content=replace(
            current.content,
            normalized_market_content_identity=new_light.normalized_market_content_identity,
        ),
    )
    lookup = h.loaders[EMA8_EMA20_OBSERVATION_LOOKUP].return_value
    h.loaders[EMA8_EMA20_OBSERVATION_LOOKUP].return_value = replace(
        lookup, observation=new_light
    )
    later = h.run(h.coordinator())
    assert later.saved_state != source.proposed_state
    assert len(h.store.discover_prepared(INSTRUMENT)) == 2
    assert len(list(h.records.glob("pending-*"))) == 2
    h.restart()
    forbidden = forbid_regeneration(h, monkeypatch)
    before = retained_bytes(h)
    resolved = RadarResearchPendingResolver(h.store).resolve(supplied)
    assert resolved.source_identity == source.identity
    assert resolved.candidate_fingerprint == pending.candidate_fingerprint
    assert h.store.read_pending(resolved.candidate_fingerprint) == pending
    assert retained_bytes(h) == before
    forbidden.assert_not_called()
    h.assert_no_acquisition()
