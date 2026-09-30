"""Strict immutable local persistence, independent reads, and retained graphs."""

import json
import os
import re
from dataclasses import replace
from unittest.mock import Mock

import pytest
from test_radar_application import AS_OF, INSTRUMENT
from test_radar_candidate_delivery import Harness, assert_complete, seed_prepared

from market_platform.application import radar_candidate_delivery as delivery
from market_platform.application import radar_candidate_delivery_store as storage
from market_platform.application.radar_candidate import (
    RadarCandidateDecision,
    RadarCandidateDecisionReason,
)
from market_platform.application.radar_candidate_delivery import (
    AcceptedSource,
    CandidateDecisionRecord,
    DeliveryFailure,
    RadarCandidateDeliveryError,
    SourceRecoveryIdentity,
)
from market_platform.application.radar_candidate_delivery_store import (
    RadarCandidateDeliveryFileStore,
    RadarCandidateDeliveryUnavailableError,
)
from market_platform.instruments.identity import CanonicalInstrumentId


def completed(h):
    h.run(h.coordinator())
    source = h.store.discover_prepared(INSTRUMENT)[0]
    accepted = h.store.read_accepted(source.identity)
    decision = h.store.read_decision(source.identity)
    pending = h.store.read_pending(decision.decision.candidate.fingerprint)
    return source, accepted, decision, pending


def test_safe_deterministic_flat_layout_and_fresh_reads(tmp_path):
    h = Harness(tmp_path)
    records = completed(h)
    fresh = RadarCandidateDeliveryFileStore(h.records)
    source, accepted, decision, pending = records
    assert fresh.read_prepared(INSTRUMENT, source.identity) == source
    assert fresh.read_accepted(source.identity) == accepted
    assert fresh.read_decision(source.identity) == decision
    assert fresh.read_pending(pending.candidate_fingerprint) == pending
    assert fresh.discover_prepared(INSTRUMENT) == (source,)
    assert fresh.discover_prepared(CanonicalInstrumentId("other")) == ()
    for record in records:
        filename = storage._filename(record)
        assert re.fullmatch(
            r"(?:prepared-[0-9a-f]{64}-|accepted-|decision-|pending-)[0-9a-f]{64}\.json",
            filename,
        )
        assert INSTRUMENT.instrument_id not in filename
        assert len(filename) < 255
        assert (h.records / filename).is_file()
    assert storage._instrument_key(
        CanonicalInstrumentId("A")
    ) != storage._instrument_key(CanonicalInstrumentId("a"))
    assert len(storage._instrument_key(CanonicalInstrumentId("X" * 128))) == 64


@pytest.mark.parametrize("index", range(4))
def test_each_record_idempotent_replay_does_not_write(tmp_path, monkeypatch, index):
    h = Harness(tmp_path)
    record = completed(h)[index]
    before = {p.name: p.read_bytes() for p in h.records.iterdir()}
    monkeypatch.setattr(
        storage.os, "link", Mock(side_effect=AssertionError("No republish"))
    )
    fresh = RadarCandidateDeliveryFileStore(h.records)
    fresh._publish(record)
    assert before == {p.name: p.read_bytes() for p in h.records.iterdir()}


@pytest.mark.parametrize("index", [1, 2, 3])
def test_same_key_different_complete_payload_conflicts(tmp_path, index):
    h = Harness(tmp_path)
    records = completed(h)
    record = records[index]
    if type(record) is AcceptedSource:
        changed = replace(
            record,
            accepted_state=replace(
                record.accepted_state,
                market_observation=replace(
                    record.accepted_state.market_observation, observed_at=AS_OF
                ),
            ),
        )
    elif type(record) is CandidateDecisionRecord:
        changed = replace(
            record,
            decision=RadarCandidateDecision(
                record.decision.policy, RadarCandidateDecisionReason.NOT_SELECTED, None
            ),
        )
    else:
        changed = replace(
            record, source_identity=SourceRecoveryIdentity("sha256:" + "f" * 64)
        )
    path = h.records / storage._filename(record)
    before = path.read_bytes()
    with pytest.raises(RadarCandidateDeliveryError) as caught:
        h.store._publish(changed)
    assert caught.value.failure is DeliveryFailure.CONFLICT
    assert caught.value.conflict
    assert path.read_bytes() == before


def test_prepared_hash_match_alone_cannot_overwrite_payload(tmp_path, monkeypatch):
    h = Harness(tmp_path)
    source = seed_prepared(h)
    actual = delivery.canonical_fingerprint

    def collision(payload):
        if payload.get("schema_version") == delivery.PREPARED_SCHEMA:
            return source.identity.fingerprint
        return actual(payload)

    monkeypatch.setattr(delivery, "canonical_fingerprint", collision)
    changed = replace(
        source,
        proposed_state=replace(
            source.proposed_state,
            market_observation=replace(
                source.proposed_state.market_observation, observed_at=AS_OF
            ),
        ),
    )
    assert changed.identity == source.identity
    with pytest.raises(RadarCandidateDeliveryError) as caught:
        h.store.publish_prepared(changed)
    assert caught.value.failure is DeliveryFailure.CONFLICT
    assert h.store.read_prepared(INSTRUMENT, source.identity) == source


@pytest.mark.parametrize("index", range(4))
@pytest.mark.parametrize(
    "corruption",
    ["missing", "extra", "type", "schema", "duplicate", "partial", "utf8", "nonfinite"],
)
def test_strict_record_reads_fail_closed(tmp_path, index, corruption):
    h = Harness(tmp_path)
    record = completed(h)[index]
    path = h.records / storage._filename(record)
    raw = record.to_dict()
    if corruption == "missing":
        del raw["schema_version"]
    elif corruption == "extra":
        raw["extra"] = False
    elif corruption == "type":
        raw["source_identity"] = 123
    elif corruption == "schema":
        raw["schema_version"] = "unknown/v99"
    payload = json.dumps(raw).encode("utf-8")
    if corruption == "duplicate":
        payload = payload[:-1] + b',"schema_version":"duplicate"}'
    elif corruption == "partial":
        payload = payload[:50]
    elif corruption == "utf8":
        payload = b"\xff"
    elif corruption == "nonfinite":
        payload = payload[:-1] + b',"extra":NaN}'
    path.write_bytes(payload)
    fresh = RadarCandidateDeliveryFileStore(h.records)
    with pytest.raises(RadarCandidateDeliveryError):
        fresh._read(path.name)
    with pytest.raises(RadarCandidateDeliveryError):
        fresh.unresolved(INSTRUMENT)


def test_unpublished_temporary_files_have_no_authority(tmp_path):
    path = tmp_path / ".delivery-interrupted.tmp"
    path.write_text('{"partial":', encoding="utf-8")
    store = RadarCandidateDeliveryFileStore(tmp_path)
    assert store.discover_prepared(INSTRUMENT) == ()
    assert store.unresolved(INSTRUMENT) == ()
    assert path.exists()


@pytest.mark.parametrize(
    "kind", ["directory", "unknown_file", "filename_mismatch", "orphan"]
)
def test_unsafe_or_incoherent_entries_fail_closed(tmp_path, kind):
    h = Harness(tmp_path)
    source = h.prepare()
    if kind == "directory":
        (h.records / ".delivery-unsafe.tmp").mkdir()
    elif kind == "unknown_file":
        (h.records / "unknown.json").write_text("{}", encoding="utf-8")
    elif kind == "filename_mismatch":
        (
            h.records
            / ("prepared-" + "0" * 64 + "-" + source.identity.fingerprint[7:] + ".json")
        ).write_text(json.dumps(source.to_dict()), encoding="utf-8")
    else:
        h.store.publish_accepted(AcceptedSource(source.identity, source.proposed_state))
    with pytest.raises(RadarCandidateDeliveryError):
        h.store.unresolved(INSTRUMENT)


def test_symlink_and_reparse_entries_rejected_without_platform_privileges(tmp_path):
    # Exercise the same lstat mode/attribute checks on all platforms.
    regular = tmp_path / "regular"
    regular.write_text("", encoding="utf-8")
    info = regular.stat()
    proxy = Mock(st_mode=info.st_mode, st_file_attributes=0x400)
    with pytest.raises(ValueError):
        storage._safe(proxy)
    proxy.st_file_attributes = 0
    proxy.st_mode = 0o120777
    with pytest.raises(ValueError):
        storage._safe(proxy)


def test_roots_are_absolute_caller_provisioned_and_missing_is_not_absent(tmp_path):
    with pytest.raises(ValueError):
        RadarCandidateDeliveryFileStore("relative")
    root = tmp_path / "missing"
    store = RadarCandidateDeliveryFileStore(root)
    with pytest.raises(RadarCandidateDeliveryError):
        store.unresolved(INSTRUMENT)
    assert not root.exists()


def test_multiple_unresolved_sources_fail_closed(tmp_path):
    h = Harness(tmp_path)
    source = seed_prepared(h)
    changed = replace(
        source,
        proposed_state=replace(
            source.proposed_state,
            market_observation=replace(
                source.proposed_state.market_observation, observed_at=AS_OF
            ),
        ),
    )
    h.store.publish_prepared(changed)
    assert len(h.store.discover_prepared(INSTRUMENT)) == 2
    with pytest.raises(RadarCandidateDeliveryError) as caught:
        RadarCandidateDeliveryFileStore(h.records).unresolved(INSTRUMENT)
    assert caught.value.failure is DeliveryFailure.RECOVERY


def test_negative_decision_resolves_without_pending(tmp_path):
    h = Harness(tmp_path, "absent")
    h.run(h.coordinator())
    source = h.store.discover_prepared(INSTRUMENT)[0]
    assert_complete(h, source, RadarCandidateDecisionReason.NO_MEANINGFUL_TRANSITION)
    assert h.store.unresolved(INSTRUMENT) == ()
    assert len(list(h.records.iterdir())) == 3


def test_eligible_decision_requires_exact_pending(tmp_path):
    h = Harness(tmp_path)
    source, accepted, decision, pending = completed(h)
    pending_path = h.records / storage._filename(pending)
    pending_path.unlink()  # Simulate an interruption before Pending publication.
    fresh = RadarCandidateDeliveryFileStore(h.records)
    assert fresh.unresolved(INSTRUMENT) == (source,)
    fresh.publish_pending(pending)
    assert fresh.is_resolved(source)
    assert fresh.read_accepted(source.identity) == accepted
    assert fresh.read_decision(source.identity) == decision


@pytest.mark.parametrize("link", ["accepted", "decision", "pending"])
def test_incoherent_record_links_block_discovery(tmp_path, link):
    h = Harness(tmp_path)
    source, accepted, decision, pending = completed(h)
    if link == "accepted":
        altered = replace(
            accepted,
            accepted_state=replace(
                accepted.accepted_state,
                market_observation=replace(
                    accepted.accepted_state.market_observation, observed_at=AS_OF
                ),
            ),
        )
    elif link == "decision":
        altered = replace(
            decision,
            decision=RadarCandidateDecision(
                decision.decision.policy,
                RadarCandidateDecisionReason.NO_MEANINGFUL_TRANSITION,
                None,
            ),
        )
    else:
        altered = replace(
            pending, source_identity=SourceRecoveryIdentity("sha256:" + "e" * 64)
        )
    (h.records / storage._filename(altered)).write_text(
        json.dumps(altered.to_dict()), encoding="utf-8"
    )
    with pytest.raises(RadarCandidateDeliveryError):
        h.store.is_resolved(source)


@pytest.mark.parametrize("failure", ["fsync", "link", "readback"])
def test_immutable_publication_failure_and_temp_cleanup(tmp_path, monkeypatch, failure):
    h = Harness(tmp_path)
    source = h.prepare()
    if failure in {"fsync", "link"}:
        monkeypatch.setattr(storage.os, failure, Mock(side_effect=OSError("private")))
    else:
        read = h.store._read
        calls = 0

        def fail_readback(name):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("readback failed after link")
            return read(name)

        monkeypatch.setattr(h.store, "_read", fail_readback)
    with pytest.raises(OSError):
        h.store.publish_prepared(source)
    assert list(h.records.glob("*.tmp")) == []
    assert len(list(h.records.glob("*.json"))) == (1 if failure == "readback" else 0)
    if failure == "readback":
        assert (
            RadarCandidateDeliveryFileStore(h.records).read_prepared(
                INSTRUMENT, source.identity
            )
            == source
        )


def test_temp_is_flushed_fsynced_and_closed_before_link(tmp_path, monkeypatch):
    h = Harness(tmp_path)
    source = h.prepare()
    fsync, link = os.fsync, os.link
    seen = []

    def sync(descriptor):
        seen.append("fsync")
        fsync(descriptor)

    def publish(temporary, target):
        assert seen == ["fsync"]
        assert json.loads(temporary.read_text(encoding="utf-8")) == source.to_dict()
        seen.append("link")
        link(temporary, target)

    monkeypatch.setattr(storage.os, "fsync", sync)
    monkeypatch.setattr(storage.os, "link", publish)
    h.store.publish_prepared(source)
    assert seen == ["fsync", "link"]


def test_no_clobber_race_compares_complete_existing_payload(tmp_path, monkeypatch):
    h = Harness(tmp_path)
    source = h.prepare()
    original = os.link

    def publish_then_exists(temporary, target):
        original(temporary, target)
        raise FileExistsError

    monkeypatch.setattr(storage.os, "link", publish_then_exists)
    h.store.publish_prepared(source)
    assert h.store.read_prepared(INSTRUMENT, source.identity) == source


def native_symlink(link, target, *, directory=False):
    try:
        link.symlink_to(target, target_is_directory=directory)
    except OSError as exc:
        if os.name == "nt" and getattr(exc, "winerror", None) == 1314:
            pytest.skip("native Windows symlink capability unavailable (WinError 1314)")
        raise
    assert link.is_symlink()


def test_native_symlink_delivery_root_fails_closed(tmp_path):
    h = Harness(tmp_path)
    source = h.prepare()
    alias = tmp_path / "delivery-alias"
    native_symlink(alias, h.records, directory=True)
    store = RadarCandidateDeliveryFileStore(alias)
    for operation in (
        lambda: store.read_prepared(INSTRUMENT, source.identity),
        lambda: store.discover_prepared(INSTRUMENT),
        lambda: store.unresolved(INSTRUMENT),
        lambda: store.publish_prepared(source),
    ):
        with pytest.raises(RadarCandidateDeliveryError):
            operation()
    assert list(h.records.iterdir()) == []
    assert alias.is_symlink()


@pytest.mark.parametrize("dangling", [False, True], ids=["live", "dangling"])
def test_native_symlink_record_fails_closed(tmp_path, dangling):
    h = Harness(tmp_path)
    source = h.prepare()
    target = tmp_path / "record-target.json"
    payload = json.dumps(source.to_dict()).encode("utf-8")
    if not dangling:
        target.write_bytes(payload)
    link = h.records / storage._filename(source)
    native_symlink(link, target)
    store = RadarCandidateDeliveryFileStore(h.records)
    for operation in (
        lambda: store.read_prepared(INSTRUMENT, source.identity),
        lambda: store.discover_prepared(INSTRUMENT),
        lambda: store.unresolved(INSTRUMENT),
        lambda: store.publish_prepared(source),
    ):
        with pytest.raises(RadarCandidateDeliveryError):
            operation()
        assert link.is_symlink()
        if dangling:
            assert not target.exists()
        else:
            assert target.read_bytes() == payload
    assert list(h.records.iterdir()) == [link]


@pytest.mark.parametrize("dangling", [False, True], ids=["live", "dangling"])
def test_native_symlink_checkpoint_blocks_recovery(tmp_path, monkeypatch, dangling):
    h = Harness(tmp_path)
    source = seed_prepared(h)
    authority = next(h.checkpoints.glob("*.json"))
    original = authority.read_bytes()
    retained = tmp_path / "retained-checkpoint.json"
    authority.rename(retained)
    target = tmp_path / "missing-checkpoint.json" if dangling else retained
    native_symlink(authority, target)
    coordinator = h.restart()
    save = Mock(wraps=h.checkpoint.save_state)
    monkeypatch.setattr(h.checkpoint, "save_state", save)
    with pytest.raises(RadarCandidateDeliveryError) as caught:
        h.run(coordinator)
    assert caught.value.failure is DeliveryFailure.RECOVERY
    assert caught.value.pipeline_result is None
    assert caught.value.prepared_state is None
    save.assert_not_called()
    h.assert_no_acquisition()
    assert h.store.read_accepted(source.identity) is None
    assert h.store.read_decision(source.identity) is None
    assert list(h.records.glob("pending-*")) == []
    assert authority.is_symlink()
    assert retained.read_bytes() == original
    if dangling:
        assert not target.exists()


def test_resolve_pending_authenticates_inventory_and_preserves_retained_bytes(tmp_path):
    h = Harness(tmp_path)
    source, _, _, pending = completed(h)
    before = {p.name: p.read_bytes() for p in h.records.iterdir()}
    fresh = RadarCandidateDeliveryFileStore(h.records)
    assert (
        fresh.resolve_pending(pending.candidate_fingerprint, source.identity) == pending
    )
    assert fresh.resolve_pending("sha256:" + "f" * 64, source.identity) is None
    assert before == {p.name: p.read_bytes() for p in h.records.iterdir()}


def test_resolution_preserves_corruption_precedence_over_missing_pending(tmp_path):
    h = Harness(tmp_path)
    source, accepted, _, _ = completed(h)
    (h.records / storage._filename(accepted)).unlink()
    with pytest.raises(RadarCandidateDeliveryError) as caught:
        h.store.resolve_pending("sha256:" + "f" * 64, source.identity)
    assert caught.value.failure is DeliveryFailure.INVARIANT


def test_resolution_distinguishes_missing_root_from_corrupt_root(tmp_path):
    identity = SourceRecoveryIdentity("sha256:" + "a" * 64)
    missing = tmp_path / "missing-root"
    with pytest.raises(RadarCandidateDeliveryUnavailableError):
        RadarCandidateDeliveryFileStore(missing).resolve_pending(
            "sha256:" + "b" * 64, identity
        )
    assert not missing.exists()
    corrupt = tmp_path / "root-file"
    corrupt.write_bytes(b"not a directory")
    with pytest.raises(RadarCandidateDeliveryError) as caught:
        RadarCandidateDeliveryFileStore(corrupt).resolve_pending(
            "sha256:" + "b" * 64, identity
        )
    assert caught.value.failure is DeliveryFailure.INVARIANT


def test_resolution_rejects_mocked_reparse_root_without_native_privileges(
    tmp_path,
    monkeypatch,
):
    store = RadarCandidateDeliveryFileStore(tmp_path)
    info = tmp_path.stat()
    unsafe = Mock(st_mode=info.st_mode, st_file_attributes=0x400)
    monkeypatch.setattr(type(store._root), "lstat", Mock(return_value=unsafe))
    with pytest.raises(RadarCandidateDeliveryError) as caught:
        store.resolve_pending(
            "sha256:" + "a" * 64, SourceRecoveryIdentity("sha256:" + "b" * 64)
        )
    assert caught.value.failure is DeliveryFailure.INVARIANT
