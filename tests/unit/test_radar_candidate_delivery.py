"""Actual application preparation, filesystem restarts, and no activation."""

import ast
import inspect
import json
from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest
from test_radar_application import (
    AS_OF,
    CHECKPOINT,
    COMPLETION,
    CURRENT,
    INSTRUMENT,
    LIGHT,
    LIGHT_LOOKUP,
    OTHER,
    OTHER_KEY,
    SESSION,
    TRIGGER,
    profile,
    state_for,
)

from market_platform.application import radar_candidate_delivery as delivery
from market_platform.application.radar_candidate import (
    RadarCandidateDecisionReason as Reason,
)
from market_platform.application.radar_candidate import (
    RadarCandidateEligibilityPolicyIdentity,
)
from market_platform.application.radar_candidate_delivery import (
    AcceptedSource,
    CandidateDecisionRecord,
    DeliveryFailure,
    PendingCandidateWork,
    PreparedSourceIntent,
    RadarCandidateDeliveryCoordinator,
    RadarCandidateDeliveryError,
    RadarPredecessorWitness,
)
from market_platform.application.radar_candidate_delivery_store import (
    RadarCandidateDeliveryFileStore,
)
from market_platform.radar.application import RadarApplicationService
from market_platform.radar.calendar import ExchangeSessionCalendar
from market_platform.radar.checkpoint_store import RadarCheckpointFileStore
from market_platform.radar.core import (
    RadarGateDisposition,
    RadarGateResult,
)
from market_platform.radar.lightweight_observation import (
    EMA8_EMA20_OBSERVATION_LOOKUP,
    RadarEmaRelation,
)
from market_platform.radar.observation_state import (
    RadarObservationStateLookupResult,
    RadarObservationStateLookupStatus,
)
from market_platform.radar.pipeline import RadarPipeline
from market_platform.radar.resolver import RadarGateFactoryBinding, RadarGateResolver
from market_platform.radar.trigger import (
    CURRENT_MARKET_CONTENT_LOOKUP,
    SESSION_CONTENT_TRIGGER_KEY,
    RadarSessionContentTriggerGate,
)

POLICY = RadarCandidateEligibilityPolicyIdentity()


class PreparedInterruption(Exception):
    pass


class Harness:
    """No market acquisition: actual Trigger and application, injected facts/time."""

    def __init__(self, root, kind="complete", filtered=False):
        self.checkpoints = root / "checkpoints"
        self.records = root / "delivery"
        self.checkpoints.mkdir()
        self.records.mkdir()
        self.checkpoint = RadarCheckpointFileStore(self.checkpoints)
        self.store = RadarCandidateDeliveryFileStore(self.records)
        prior_light = replace(
            LIGHT,
            relation=RadarEmaRelation.BELOW,
            normalized_market_content_identity="sha256:" + "b" * 64,
        )
        if kind == "unchanged":
            prior_light = replace(prior_light, relation=LIGHT.relation)
        if kind == "incomparable":
            prior_light = replace(prior_light, calculation_revision="old")
        market = replace(
            CHECKPOINT,
            normalized_market_content_identity=prior_light.normalized_market_content_identity,
        )
        if kind == "legacy_session":
            market = replace(
                market,
                observed_completed_session=SESSION - timedelta(days=1),
                content_scope=replace(
                    market.content_scope, history_end=SESSION - timedelta(days=1)
                ),
            )
        if kind == "legacy_unchanged":
            market = CHECKPOINT
        if kind.startswith("legacy"):
            self.checkpoint.save(market)
        elif kind != "absent":
            self.checkpoint.save_state(state_for(market, prior_light))
        self.predecessor = self.checkpoint.lookup_state(INSTRUMENT)
        calendar = Mock(spec=ExchangeSessionCalendar)
        calendar.latest_completed_session.return_value = SESSION
        calendar.is_session.return_value = True
        other = Mock()
        other.identity = OTHER.gate_identity
        other.evaluate.return_value = RadarGateResult(
            OTHER,
            RadarGateDisposition.DROP if filtered else RadarGateDisposition.PASS,
            "FILTER" if filtered else "PASS",
        )
        self.resolver = RadarGateResolver(
            [
                RadarGateFactoryBinding(
                    SESSION_CONTENT_TRIGGER_KEY,
                    lambda occurrence: RadarSessionContentTriggerGate(
                        occurrence, calendar
                    ),
                ),
                RadarGateFactoryBinding(OTHER_KEY, lambda occurrence: other),
            ]
        )
        self.profile = profile(TRIGGER, OTHER)
        self.clock = Mock(return_value=COMPLETION)
        self.loaders = {
            CURRENT_MARKET_CONTENT_LOOKUP: Mock(return_value=CURRENT),
            EMA8_EMA20_OBSERVATION_LOOKUP: Mock(return_value=LIGHT_LOOKUP),
        }

    def run(self, coordinator):
        return RadarApplicationService(
            self.resolver, self.checkpoint, self.clock, coordinator=coordinator
        ).evaluate(
            self.profile,
            INSTRUMENT,
            AS_OF,
            self.loaders,
        )

    def coordinator(self):
        return RadarCandidateDeliveryCoordinator(self.store, policy=POLICY)

    def prepare(self):
        capture = Mock()

        def publish(instrument, pipeline, state, predecessor, checkpoint_store):
            self.source = PreparedSourceIntent(
                instrument,
                pipeline,
                state,
                RadarPredecessorWitness.from_lookup(predecessor),
                POLICY,
            )
            raise PreparedInterruption

        capture.publish.side_effect = publish
        with pytest.raises(PreparedInterruption):
            self.run(capture)
        return self.source

    def restart(self):
        self.store = RadarCandidateDeliveryFileStore(self.records)
        self.checkpoint = RadarCheckpointFileStore(self.checkpoints)
        self.clock.reset_mock()
        for loader in self.loaders.values():
            loader.reset_mock()
        return self.coordinator()

    def assert_no_acquisition(self):
        self.clock.assert_not_called()
        for loader in self.loaders.values():
            loader.assert_not_called()


def capture_publication_context(harness, monkeypatch):
    original = RadarApplicationService._prepare_state
    context = []

    def prepare(service, evaluation, pipeline, predecessor, reason):
        state = original(service, evaluation, pipeline, predecessor, reason)
        context.append((pipeline, state))
        return state

    monkeypatch.setattr(RadarApplicationService, "_prepare_state", prepare)
    return context


def assert_error_context(error, context):
    assert len(context) == 1
    pipeline, state = context[0]
    assert error.pipeline_result == pipeline
    assert error.prepared_state == state
    assert error.pipeline_result is not pipeline
    assert error.prepared_state is not state
    assert not hasattr(error, "application_result")
    assert not hasattr(error, "candidate")


def seed_prepared(harness):
    source = harness.prepare()
    harness.store.publish_prepared(source)
    return source


def assert_complete(harness, source, reason=Reason.ELIGIBLE):
    assert harness.store.read_accepted(source.identity) == AcceptedSource(
        source.identity, source.proposed_state
    )
    record = harness.store.read_decision(source.identity)
    assert record.decision.reason is reason
    assert harness.store.is_resolved(source)
    if reason is Reason.ELIGIBLE:
        candidate = record.decision.candidate
        pending = harness.store.read_pending(candidate.fingerprint)
        assert pending == PendingCandidateWork(source.identity, record.decision)
        assert candidate.source_observation_state == source.proposed_state
    else:
        assert record.decision.candidate is None
        assert all(
            json.loads(path.read_text(encoding="utf-8"))["source_identity"]
            != source.identity.fingerprint
            for path in harness.records.glob("pending-*")
        )
    return record


@pytest.mark.parametrize(
    "kind,reason",
    [
        ("complete", Reason.ELIGIBLE),
        ("absent", Reason.NO_MEANINGFUL_TRANSITION),
        ("unchanged", Reason.NO_MEANINGFUL_TRANSITION),
        ("incomparable", Reason.NO_MEANINGFUL_TRANSITION),
        ("legacy_session", Reason.NO_MEANINGFUL_TRANSITION),
        ("legacy_correction", Reason.NO_MEANINGFUL_TRANSITION),
        ("legacy_unchanged", Reason.NOT_SELECTED),
    ],
)
def test_case_b_fresh_restart_exact_predecessor(tmp_path, monkeypatch, kind, reason):
    h = Harness(tmp_path, kind)
    source = seed_prepared(h)
    coordinator = h.restart()
    save = Mock(wraps=h.checkpoint.save_state)
    monkeypatch.setattr(h.checkpoint, "save_state", save)
    monkeypatch.setattr(
        RadarPipeline, "evaluate", Mock(side_effect=AssertionError("No rerun"))
    )
    coordinator.recover(INSTRUMENT, h.checkpoint)
    save.assert_called_once_with(source.proposed_state)
    assert h.checkpoint.lookup_state(INSTRUMENT).state == source.proposed_state
    assert_complete(h, source, reason)
    h.assert_no_acquisition()
    if kind in {"legacy_session", "legacy_correction"}:
        assert source.pipeline.executed_results[0].reason_code == (
            "NEW_COMPLETED_SESSION"
            if kind == "legacy_session"
            else "MARKET_CONTENT_CHANGED"
        )
        decision = source.proposed_state.committed_decision
        assert decision.prior is None
        assert decision.classification == "BASELINE_INITIALIZED"
        assert not decision.meaningful_change


@pytest.mark.parametrize(
    "kind,filtered,reason",
    [
        ("complete", False, Reason.ELIGIBLE),
        ("complete", True, Reason.NOT_SELECTED),
        ("absent", False, Reason.NO_MEANINGFUL_TRANSITION),
    ],
)
def test_normal_publication_order_and_result(
    tmp_path, monkeypatch, kind, filtered, reason
):
    h = Harness(tmp_path, kind, filtered)
    stages = []
    publish = h.store._publish
    save = h.checkpoint.save_state

    def record(value):
        stages.append(type(value).__name__)
        publish(value)

    def checkpoint(state):
        prepared = h.store.discover_prepared(INSTRUMENT)
        assert len(prepared) == 1
        assert prepared[0].proposed_state == state
        assert h.store.read_accepted(prepared[0].identity) is None
        stages.append("checkpoint")
        save(state)

    monkeypatch.setattr(h.store, "_publish", record)
    monkeypatch.setattr(h.checkpoint, "save_state", checkpoint)
    result = h.run(h.coordinator())
    source = h.store.discover_prepared(INSTRUMENT)[0]
    assert stages == [
        "PreparedSourceIntent",
        "checkpoint",
        "AcceptedSource",
        "CandidateDecisionRecord",
    ] + (["PendingCandidateWork"] if reason is Reason.ELIGIBLE else [])
    assert result.advancement == "SAVED"
    assert result.pipeline_result == source.pipeline
    assert result.saved_state == source.proposed_state
    assert_complete(h, source, reason)
    h.clock.assert_called_once_with()


@pytest.mark.parametrize(
    "stage,failure",
    [
        (PreparedSourceIntent, DeliveryFailure.PREPARED),
        (AcceptedSource, DeliveryFailure.ACCEPTED),
        (CandidateDecisionRecord, DeliveryFailure.DECISION),
        (PendingCandidateWork, DeliveryFailure.PENDING),
    ],
)
def test_persistence_failure_boundaries_and_restart(
    tmp_path, monkeypatch, stage, failure
):
    h = Harness(tmp_path)
    context = capture_publication_context(h, monkeypatch)
    publish = h.store._publish
    save = Mock(wraps=h.checkpoint.save_state)
    monkeypatch.setattr(h.checkpoint, "save_state", save)

    def fail(value):
        if type(value) is stage:
            raise OSError("private I/O detail")
        publish(value)

    monkeypatch.setattr(h.store, "_publish", fail)
    with pytest.raises(RadarCandidateDeliveryError) as caught:
        h.run(h.coordinator())
    assert_error_context(caught.value, context)
    assert caught.value.failure is failure
    assert "private" not in str(caught.value)
    assert isinstance(caught.value.__cause__, OSError)
    assert caught.value.checkpoint_may_be_published is (
        stage is not PreparedSourceIntent
    )
    if stage is PreparedSourceIntent:
        save.assert_not_called()
        assert h.store.discover_prepared(INSTRUMENT) == ()
        assert h.checkpoint.lookup_state(INSTRUMENT) == h.predecessor
        return
    save.assert_called_once()
    source = h.store.discover_prepared(INSTRUMENT)[0]
    assert not h.store.is_resolved(source)
    coordinator = h.restart()
    monkeypatch.setattr(
        h.checkpoint, "save_state", Mock(side_effect=AssertionError("No second save"))
    )
    coordinator.recover(INSTRUMENT, h.checkpoint)
    assert_complete(h, source)
    h.assert_no_acquisition()


@pytest.mark.parametrize("published", [False, True])
def test_uncertain_checkpoint_failure_recovers_from_fresh_bytes(
    tmp_path, monkeypatch, published
):
    h = Harness(tmp_path)
    context = capture_publication_context(h, monkeypatch)
    save = h.checkpoint.save_state

    def interrupted(state):
        if published:
            save(state)
        raise OSError("interrupted")

    monkeypatch.setattr(h.checkpoint, "save_state", interrupted)
    with pytest.raises(RadarCandidateDeliveryError) as caught:
        h.run(h.coordinator())
    assert_error_context(caught.value, context)
    assert caught.value.failure is DeliveryFailure.CHECKPOINT
    assert caught.value.checkpoint_may_be_published
    source = h.store.unresolved(INSTRUMENT)[0]
    assert h.store.read_accepted(source.identity) is None
    coordinator = h.restart()
    save_spy = Mock(wraps=h.checkpoint.save_state)
    monkeypatch.setattr(h.checkpoint, "save_state", save_spy)
    coordinator.recover(INSTRUMENT, h.checkpoint)
    assert save_spy.call_count == (0 if published else 1)
    assert_complete(h, source)
    h.assert_no_acquisition()


@pytest.mark.parametrize("stage", ["prepared", "accepted", "decision", "pending"])
def test_repeated_restart_at_each_incomplete_stage(tmp_path, monkeypatch, stage):
    h = Harness(tmp_path)
    source = seed_prepared(h)
    h.checkpoint.save_state(source.proposed_state)
    if stage != "prepared":
        h.store.publish_accepted(AcceptedSource(source.identity, source.proposed_state))
    if stage in {"decision", "pending"}:
        coordinator = h.restart()
        original = h.store._publish

        def stop_pending(record):
            if type(record) is PendingCandidateWork and stage == "decision":
                raise OSError("pending interruption")
            original(record)

        monkeypatch.setattr(h.store, "_publish", stop_pending)
        if stage == "decision":
            with pytest.raises(RadarCandidateDeliveryError):
                coordinator.recover(INSTRUMENT, h.checkpoint)
        else:
            coordinator.recover(INSTRUMENT, h.checkpoint)
    for _ in range(3):
        coordinator = h.restart()
        monkeypatch.setattr(
            h.checkpoint,
            "save_state",
            Mock(side_effect=AssertionError("Case A never republishes")),
        )
        coordinator.recover(INSTRUMENT, h.checkpoint)
        decision = assert_complete(h, source)
        h.assert_no_acquisition()
    assert h.store.read_decision(source.identity) == decision


@pytest.mark.parametrize(
    "current", ["unexpected", "corrupt", "unavailable", "unreadable"]
)
@pytest.mark.parametrize("accepted", [False, True])
def test_case_c_blocks_before_new_fact_loading(
    tmp_path, monkeypatch, current, accepted
):
    h = Harness(tmp_path)
    source = seed_prepared(h)
    if accepted:
        h.checkpoint.save_state(source.proposed_state)
        h.store.publish_accepted(AcceptedSource(source.identity, source.proposed_state))
    if current == "unexpected":
        h.checkpoint.save_state(
            replace(
                source.proposed_state,
                market_observation=replace(
                    source.proposed_state.market_observation, observed_at=AS_OF
                ),
            )
        )
    elif current == "corrupt":
        next(h.checkpoints.glob("*.json")).write_text("{", encoding="utf-8")
    coordinator = h.restart()
    if current == "unavailable":
        monkeypatch.setattr(
            h.checkpoint,
            "lookup_state",
            Mock(
                return_value=RadarObservationStateLookupResult(
                    RadarObservationStateLookupStatus.UNAVAILABLE
                )
            ),
        )
    elif current == "unreadable":
        monkeypatch.setattr(
            h.checkpoint, "lookup_state", Mock(side_effect=PermissionError("private"))
        )
    save = Mock(side_effect=AssertionError("No overwrite"))
    monkeypatch.setattr(h.checkpoint, "save_state", save)
    with pytest.raises(RadarCandidateDeliveryError) as caught:
        h.run(coordinator)
    assert caught.value.pipeline_result is None
    assert caught.value.prepared_state is None
    assert caught.value.failure is DeliveryFailure.RECOVERY
    assert h.store.read_decision(source.identity) is None
    if not accepted:
        assert h.store.read_accepted(source.identity) is None
    h.assert_no_acquisition()
    save.assert_not_called()


def test_predecessor_rechecked_after_prepared_before_save(tmp_path, monkeypatch):
    h = Harness(tmp_path)
    context = capture_publication_context(h, monkeypatch)
    original = h.store._publish

    def bypass(value):
        original(value)
        if type(value) is PreparedSourceIntent:
            h.checkpoint.save_state(
                replace(
                    value.proposed_state,
                    market_observation=replace(
                        value.proposed_state.market_observation, observed_at=AS_OF
                    ),
                )
            )

    monkeypatch.setattr(h.store, "_publish", bypass)
    with pytest.raises(RadarCandidateDeliveryError) as caught:
        h.run(h.coordinator())
    assert_error_context(caught.value, context)
    assert caught.value.failure is DeliveryFailure.RECOVERY
    assert caught.value.checkpoint_may_be_published is False
    source = h.store.unresolved(INSTRUMENT)[0]
    assert h.store.read_accepted(source.identity) is None


@pytest.mark.parametrize(
    "kind,reason",
    [("absent", Reason.NO_MEANINGFUL_TRANSITION), ("complete", Reason.ELIGIBLE)],
)
def test_recovery_releases_interlock_and_retains_s1_after_s2(tmp_path, kind, reason):
    h = Harness(tmp_path, kind)
    source = seed_prepared(h)
    coordinator = h.restart()
    new_light = replace(
        LIGHT,
        relation=RadarEmaRelation.BELOW,
        normalized_market_content_identity="sha256:" + "c" * 64,
    )
    h.loaders[CURRENT_MARKET_CONTENT_LOOKUP].return_value = replace(
        CURRENT,
        content=replace(
            CURRENT.content,
            normalized_market_content_identity=new_light.normalized_market_content_identity,
        ),
    )
    h.loaders[EMA8_EMA20_OBSERVATION_LOOKUP].return_value = replace(
        LIGHT_LOOKUP, observation=new_light
    )
    result = h.run(coordinator)
    assert result.saved_state != source.proposed_state
    first_decision = assert_complete(h, source, reason)
    assert h.checkpoint.lookup_state(INSTRUMENT).state == result.saved_state
    assert h.store.read_prepared(INSTRUMENT, source.identity) == source
    assert h.store.read_decision(source.identity) == first_decision
    assert len(h.store.discover_prepared(INSTRUMENT)) == 2
    assert not h.store.unresolved(INSTRUMENT)


def test_multiple_unresolved_block_before_facts(tmp_path):
    h = Harness(tmp_path)
    source = seed_prepared(h)
    other = replace(
        source,
        proposed_state=replace(
            source.proposed_state,
            market_observation=replace(
                source.proposed_state.market_observation, observed_at=AS_OF
            ),
        ),
    )
    h.store.publish_prepared(other)
    coordinator = h.restart()
    with pytest.raises(RadarCandidateDeliveryError):
        h.run(coordinator)
    h.assert_no_acquisition()


def test_pre_activation_checkpoint_is_not_backfilled(tmp_path):
    h = Harness(tmp_path)
    before = h.checkpoint.lookup_state(INSTRUMENT)
    h.restart().recover(INSTRUMENT, h.checkpoint)
    assert list(h.records.iterdir()) == []
    assert h.checkpoint.lookup_state(INSTRUMENT) == before
    h.assert_no_acquisition()


@pytest.mark.parametrize(
    "kind,filtered",
    [
        ("complete", False),
        ("complete", True),
        ("absent", False),
        ("legacy_unchanged", False),
        ("legacy_session", False),
        ("legacy_correction", False),
    ],
)
def test_source_codec_roundtrip_preserves_actual_execution(tmp_path, kind, filtered):
    h = Harness(tmp_path, kind, filtered)
    source = h.prepare()
    rebuilt = delivery._decode_record(json.loads(json.dumps(source.to_dict())))
    assert rebuilt == source
    assert rebuilt is not source
    assert rebuilt.pipeline.profile.gates == source.pipeline.profile.gates
    assert rebuilt.pipeline.executed_results == source.pipeline.executed_results
    assert rebuilt.pipeline.instrument == INSTRUMENT
    assert rebuilt.pipeline.as_of == AS_OF
    assert (
        rebuilt.proposed_state.committed_decision
        == source.proposed_state.committed_decision
    )
    assert rebuilt.identity == source.identity
    assert not hasattr(rebuilt, "to_application_result")
    assert not hasattr(rebuilt, "candidate")
    with pytest.raises(FrozenInstanceError):
        rebuilt.policy = POLICY
    if kind == "legacy_unchanged":
        assert len(rebuilt.pipeline.executed_results) == 1
        assert len(rebuilt.pipeline.profile.gates) == 2


@pytest.mark.parametrize(
    "corruption",
    [
        "profile_fingerprint",
        "gate_fingerprint",
        "order",
        "prefix",
        "failure",
        "outcome",
        "instrument",
        "naive",
        "as_of_type",
        "policy_missing",
        "policy_unsupported",
        "identity",
        "state_outcome",
        "technical_prior",
        "trigger",
        "extra",
        "schema",
    ],
)
def test_source_codec_rejects_contradictions(tmp_path, corruption):
    h = Harness(tmp_path)
    raw = h.prepare().to_dict()
    pipeline = raw["pipeline"]
    if corruption == "profile_fingerprint":
        pipeline["profile"]["fingerprint"] = "sha256:" + "0" * 64
    elif corruption == "gate_fingerprint":
        pipeline["profile"]["gates"][0]["gate_identity"]["fingerprint"] = "bad"
    elif corruption == "order":
        pipeline["profile"]["gates"].reverse()
    elif corruption == "prefix":
        pipeline["executed_results"].reverse()
    elif corruption == "failure":
        pipeline["failure"] = {
            "occurrence": pipeline["profile"]["gates"][0],
            "category": "GATE_EXCEPTION",
        }
    elif corruption == "outcome":
        pipeline["outcome"] = "FAILED"
    elif corruption == "instrument":
        pipeline["instrument"]["instrument_id"] = "../outside"
    elif corruption == "naive":
        pipeline["as_of"] = "2026-09-24T00:00:00"
    elif corruption == "as_of_type":
        pipeline["as_of"] = 7
    elif corruption == "policy_missing":
        del raw["policy"]
    elif corruption == "policy_unsupported":
        raw["policy"]["behavioral_revision"] = "2"
    elif corruption == "identity":
        raw["source_identity"] = "bad"
    elif corruption == "state_outcome":
        raw["proposed_state"]["pipeline_outcome"] = "FILTERED"
    elif corruption == "technical_prior":
        raw["predecessor"] = RadarPredecessorWitness(
            RadarObservationStateLookupStatus.ABSENT
        ).to_dict()
    elif corruption == "trigger":
        pipeline["executed_results"][0]["reason_code"] = "BASELINE_REQUIRED"
    elif corruption == "schema":
        raw["schema_version"] = "prepared/v99"
    else:
        raw["unexpected"] = None
    with pytest.raises(RadarCandidateDeliveryError):
        delivery._decode_record(raw)


def test_gate_configuration_and_source_identity_are_complete(tmp_path):
    h = Harness(tmp_path)
    source = h.prepare()
    changed_gate = replace(
        OTHER,
        gate_identity=replace(
            OTHER.gate_identity, configuration={"nested": [1, True, {"key": "value"}]}
        ),
    )
    changed_profile = replace(
        source.pipeline.profile,
        gates=(TRIGGER, changed_gate),
        configuration={"profile": [1, 2]},
    )
    changed_pipeline = replace(
        source.pipeline,
        profile=changed_profile,
        executed_results=(
            source.pipeline.executed_results[0],
            replace(source.pipeline.executed_results[1], occurrence=changed_gate),
        ),
    )
    changed = replace(
        source,
        pipeline=changed_pipeline,
        proposed_state=replace(
            source.proposed_state, profile_fingerprint=changed_profile.fingerprint
        ),
    )
    assert delivery._decode_record(changed.to_dict()) == changed
    assert changed.identity != source.identity
    proposal = replace(
        source,
        proposed_state=replace(
            source.proposed_state,
            market_observation=replace(
                source.proposed_state.market_observation, observed_at=AS_OF
            ),
        ),
    )
    predecessor = replace(
        source,
        predecessor=replace(
            source.predecessor,
            state=replace(
                source.predecessor.state,
                market_observation=replace(
                    source.predecessor.state.market_observation, observed_at=COMPLETION
                ),
            ),
        ),
    )
    assert (
        len(
            {source.identity, changed.identity, proposal.identity, predecessor.identity}
        )
        == 4
    )
    # v1 is closed: a policy revision cannot silently create another valid identity.
    raw = source.to_dict()
    raw["policy"]["behavioral_revision"] = "2"
    assert (
        delivery.canonical_fingerprint(
            {k: v for k, v in raw.items() if k != "source_identity"}
        )
        != source.identity.fingerprint
    )
    with pytest.raises(RadarCandidateDeliveryError):
        delivery._decode_record(raw)


def test_prepared_and_external_accepted_are_not_bearer_inputs(tmp_path):
    h = Harness(tmp_path)
    source = h.prepare()
    accepted = AcceptedSource(source.identity, source.proposed_state)
    rebuilt = delivery._decode_record(accepted.to_dict())
    assert rebuilt == accepted
    assert list(h.records.iterdir()) == []
    for external in (source, source.to_dict(), accepted, accepted.to_dict()):
        with pytest.raises(RadarCandidateDeliveryError):
            h.coordinator().recover(external, h.checkpoint)
    assert not hasattr(h.coordinator(), "reconstruct")
    assert not hasattr(delivery, "reconstruct_application_result")
    assert list(h.records.iterdir()) == []


def test_candidate_invariant_is_operational_not_negative(tmp_path, monkeypatch):
    h = Harness(tmp_path)
    context = capture_publication_context(h, monkeypatch)
    monkeypatch.setattr(
        delivery,
        "evaluate_radar_candidate",
        Mock(side_effect=ValueError("private invariant")),
    )
    with pytest.raises(RadarCandidateDeliveryError) as caught:
        h.run(h.coordinator())
    assert_error_context(caught.value, context)
    assert caught.value.failure is DeliveryFailure.INVARIANT
    assert caught.value.checkpoint_may_be_published
    source = h.store.unresolved(INSTRUMENT)[0]
    assert h.store.read_accepted(source.identity) is not None
    assert h.store.read_decision(source.identity) is None


def test_recovery_uses_retained_policy_not_current_default(tmp_path):
    h = Harness(tmp_path)
    source = seed_prepared(h)
    coordinator = h.restart()
    coordinator._policy = object()  # Current selection is irrelevant to old bytes.
    coordinator.recover(INSTRUMENT, h.checkpoint)
    assert assert_complete(h, source).decision.policy == source.policy


@pytest.mark.parametrize(
    "relative",
    [
        "radar/application.py",
        "application/radar_single_symbol.py",
        "application/radar_batch.py",
        "application/__init__.py",
    ],
)
def test_non_activation_imports_and_instantiation(relative):
    root = Path(inspect.getfile(delivery)).parents[1]
    tree = ast.parse((root / relative).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert "radar_candidate" not in (node.module or "")
        elif isinstance(node, ast.Import):
            assert all("radar_candidate" not in alias.name for alias in node.names)
        elif isinstance(node, ast.Name):
            assert node.id not in {
                "RadarCandidateDeliveryCoordinator",
                "RadarCandidateDeliveryFileStore",
            }


@pytest.mark.parametrize(
    "module", ["radar_candidate_delivery.py", "radar_candidate_delivery_store.py"]
)
def test_delivery_has_no_provider_or_research_capability(module):
    tree = ast.parse(
        Path(inspect.getfile(delivery)).with_name(module).read_text(encoding="utf-8")
    )
    allowed = {
        "market_platform._fingerprint",
        "market_platform.application.radar_candidate",
        "market_platform.application.radar_candidate_delivery",
        "market_platform.application.radar_candidate_delivery_store",
        "market_platform.instruments.identity",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
            "market_platform."
        ):
            assert node.module in allowed or node.module.startswith(
                "market_platform.radar."
            )
        if isinstance(node, ast.Import):
            assert all(
                alias.name.split(".")[0]
                not in {"httpx", "requests", "socket", "urllib"}
                for alias in node.names
            )


@pytest.mark.parametrize(
    "stage", [AcceptedSource, CandidateDecisionRecord, PendingCandidateWork]
)
def test_storage_incomplete_s1_blocks_s2_before_facts(tmp_path, monkeypatch, stage):
    h = Harness(tmp_path)
    source = seed_prepared(h)
    coordinator = h.restart()
    publish = h.store._publish

    def unavailable(record):
        if type(record) is stage:
            raise OSError("storage unavailable")
        publish(record)

    monkeypatch.setattr(h.store, "_publish", unavailable)
    with pytest.raises(RadarCandidateDeliveryError):
        h.run(coordinator)
    h.assert_no_acquisition()
    assert not h.store.is_resolved(source)
    coordinator = h.restart()
    coordinator.recover(INSTRUMENT, h.checkpoint)
    assert_complete(h, source)


@pytest.mark.parametrize(
    "stage",
    [
        PreparedSourceIntent,
        AcceptedSource,
        CandidateDecisionRecord,
        PendingCandidateWork,
    ],
)
def test_interruption_after_each_record_publication_recovers(
    tmp_path, monkeypatch, stage
):
    h = Harness(tmp_path)
    publish = h.store._publish

    def interrupted(record):
        publish(record)
        if type(record) is stage:
            raise OSError("interrupted after durable publication")

    monkeypatch.setattr(h.store, "_publish", interrupted)
    with pytest.raises(RadarCandidateDeliveryError) as caught:
        h.run(h.coordinator())
    assert caught.value.checkpoint_may_be_published is (
        stage is not PreparedSourceIntent
    )
    source = h.store.discover_prepared(INSTRUMENT)[0]
    coordinator = h.restart()
    coordinator.recover(INSTRUMENT, h.checkpoint)
    assert_complete(h, source)
    h.assert_no_acquisition()


@pytest.mark.parametrize("corruption", ["missing", "unsupported"])
def test_historical_policy_corruption_blocks_recovery(tmp_path, corruption):
    h = Harness(tmp_path)
    source = seed_prepared(h)
    path = next(h.records.glob("prepared-*"))
    raw = json.loads(path.read_text(encoding="utf-8"))
    if corruption == "missing":
        del raw["policy"]
    else:
        raw["policy"]["behavioral_revision"] = "2"
    path.write_text(json.dumps(raw), encoding="utf-8")
    coordinator = h.restart()
    with pytest.raises(RadarCandidateDeliveryError):
        h.run(coordinator)
    h.assert_no_acquisition()
    assert h.checkpoint.lookup_state(INSTRUMENT) == h.predecessor
    assert h.store.read_accepted(source.identity) is None


@pytest.mark.parametrize("kind", ["legacy_correction", "complete"])
def test_predecessor_comparison_includes_all_retained_fields(tmp_path, kind):
    h = Harness(tmp_path, kind)
    source = seed_prepared(h)
    # Same instrument/session/content; a different completion time still conflicts.
    if kind == "legacy_correction":
        h.checkpoint.save(
            replace(h.predecessor.legacy_checkpoint, observed_at=COMPLETION)
        )
    else:
        prior = h.predecessor.state
        h.checkpoint.save_state(
            replace(
                prior,
                market_observation=replace(
                    prior.market_observation, observed_at=COMPLETION
                ),
            )
        )
    coordinator = h.restart()
    with pytest.raises(RadarCandidateDeliveryError):
        coordinator.recover(INSTRUMENT, h.checkpoint)
    assert h.store.read_accepted(source.identity) is None
    h.assert_no_acquisition()


def test_candidate_evaluation_sees_only_durable_accepted_original_source(
    tmp_path, monkeypatch
):
    h = Harness(tmp_path)
    evaluate = delivery.evaluate_radar_candidate
    invocations = []

    def evaluate_accepted(application, *, policy):
        source = h.store.discover_prepared(INSTRUMENT)[0]
        accepted = h.store.read_accepted(source.identity)
        assert accepted is not None
        assert application.advancement == "SAVED"
        assert application.pipeline_result == source.pipeline
        assert application.saved_checkpoint == source.proposed_state.market_observation
        assert (
            application.meaningful_change_decision
            == source.proposed_state.committed_decision
        )
        assert application.saved_state == source.proposed_state
        assert policy == source.policy
        invocations.append(application)
        return evaluate(application, policy=policy)

    monkeypatch.setattr(delivery, "evaluate_radar_candidate", evaluate_accepted)
    source = h.prepare()
    delivery._decode_record(source.to_dict())
    assert invocations == []
    h.store.publish_prepared(source)
    assert invocations == []
    h.restart().recover(INSTRUMENT, h.checkpoint)
    assert len(invocations) == 1
    assert_complete(h, source)


@pytest.mark.parametrize("kind", ["unavailable", "malformed", "corrupt"])
def test_prepared_rejects_invalid_predecessor(tmp_path, kind):
    h = Harness(tmp_path)
    source = h.prepare()
    if kind == "unavailable":
        lookup = RadarObservationStateLookupResult(
            RadarObservationStateLookupStatus.UNAVAILABLE
        )
    elif kind == "malformed":
        lookup = object()
    else:
        lookup = h.predecessor
        object.__setattr__(lookup.state, "profile_fingerprint", "corrupt")
    with pytest.raises((TypeError, ValueError)):
        replace(source, predecessor=RadarPredecessorWitness.from_lookup(lookup))


def test_failure_codec_preserves_location_but_cannot_prepare_failed_source(tmp_path):
    from market_platform.radar.pipeline import (
        RadarPipelineFailure,
        RadarPipelineFailureCategory,
    )

    h = Harness(tmp_path)
    source = h.prepare()
    failed = replace(
        source.pipeline,
        executed_results=(source.pipeline.executed_results[0],),
        failure=RadarPipelineFailure(
            OTHER, RadarPipelineFailureCategory.GATE_EXCEPTION
        ),
    )
    assert delivery._pipeline(delivery._pipeline_payload(failed)) == failed
    with pytest.raises(ValueError):
        replace(source, pipeline=failed)


@pytest.mark.parametrize(
    "field", ["reason", "candidate_type", "policy_type", "pending_key"]
)
def test_decision_and_pending_codec_rejects_unknown_or_wrong_types(tmp_path, field):
    h = Harness(tmp_path)
    h.run(h.coordinator())
    source = h.store.discover_prepared(INSTRUMENT)[0]
    decision = h.store.read_decision(source.identity)
    raw = delivery.PendingCandidateWork(source.identity, decision.decision).to_dict()
    if field == "reason":
        raw["decision"]["reason"] = "ERROR"
    elif field == "candidate_type":
        raw["decision"]["candidate"] = []
    elif field == "policy_type":
        raw["decision"]["policy"]["behavioral_revision"] = 1
    else:
        raw["candidate_fingerprint"] = "sha256:" + "f" * 64
    with pytest.raises(RadarCandidateDeliveryError):
        delivery._decode_record(raw)
