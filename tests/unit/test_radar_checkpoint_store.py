import base64
import errno
import json
import os
import re
import stat
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from market_platform.instruments.identity import CanonicalInstrumentId
from market_platform.radar import checkpoint_store as storage
from market_platform.radar.checkpoint_store import (
    RadarCheckpointFileStore,
    RadarCheckpointStoreError,
)
from market_platform.radar.core import (
    RadarGateIdentity,
    RadarGateOccurrence,
    RadarPipelineOutcome,
    RadarProfile,
)
from market_platform.radar.lightweight_observation import (
    EMA8_EMA20_CALCULATION_REVISION,
    EMA8_EMA20_OBSERVATION_DEFINITION_ID,
    EMA8_EMA20_OBSERVATION_SCHEMA,
    RadarEmaRelation,
    RadarLightweightObservation,
)
from market_platform.radar.meaningful_change import evaluate_meaningful_change
from market_platform.radar.observation import (
    RadarMarketContentScope,
    RadarObservationCheckpoint,
    RadarObservationStateError,
)
from market_platform.radar.observation import (
    RadarObservationLookupStatus as Status,
)
from market_platform.radar.observation_state import (
    RadarObservationState,
)
from market_platform.radar.observation_state import (
    RadarObservationStateLookupStatus as StateStatus,
)


def checkpoint(instrument_id: str = "us-msft") -> RadarObservationCheckpoint:
    return RadarObservationCheckpoint(
        CanonicalInstrumentId(instrument_id),
        date(2026, 9, 23),
        "sha256:" + "a" * 64,
        datetime(2026, 9, 24, tzinfo=UTC),
        RadarMarketContentScope(date(2026, 9, 21), date(2026, 9, 23)),
    )


def target(root: Path, value: RadarObservationCheckpoint) -> Path:
    encoded = base64.b32encode(value.instrument.instrument_id.encode("ascii"))
    return root / ("id-" + encoded.decode().lower().rstrip("=") + ".json")


def test_absolute_root_and_cwd_independence(tmp_path, monkeypatch):
    root = tmp_path / "state"
    root.mkdir()
    store = RadarCheckpointFileStore(str(root))
    monkeypatch.chdir(tmp_path)
    with pytest.raises(RadarCheckpointStoreError, match="absolute"):
        RadarCheckpointFileStore(Path("state"))
    assert store.lookup(checkpoint().instrument).status is Status.ABSENT
    store.save(checkpoint())
    assert target(root, checkpoint()).is_file()
    assert list(tmp_path.glob("*.json")) == []


def test_reload_deterministic_bytes_and_isolation(tmp_path):
    value = checkpoint()
    store = RadarCheckpointFileStore(tmp_path)
    store.save(value)
    path = target(tmp_path, value)
    expected = (
        json.dumps(
            value.to_dict(),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )
    assert path.read_bytes() == expected
    assert set(json.loads(expected)) == {
        "schema_version",
        "instrument",
        "observed_completed_session",
        "normalized_market_content_identity",
        "observed_at",
        "content_scope",
    }
    projection = value.to_dict()
    projection["instrument"]["instrument_id"] = "other"
    projection["content_scope"]["history_start"] = "2000-01-01"
    other = RadarCheckpointFileStore(tmp_path)
    first = other.lookup(value.instrument)
    second = other.lookup(value.instrument)
    assert first.status is Status.PRESENT
    assert first.checkpoint == second.checkpoint == value
    assert first.checkpoint is not second.checkpoint
    assert first.checkpoint.instrument is not second.checkpoint.instrument
    assert first.checkpoint.content_scope is not second.checkpoint.content_scope
    store.save(value)
    assert path.read_bytes() == expected
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("kind", ["missing", "file"])
def test_unusable_root_is_not_absent_or_created(tmp_path, kind):
    root = tmp_path / "state"
    if kind == "file":
        root.write_bytes(b"root")
    store = RadarCheckpointFileStore(root)
    assert store.lookup(checkpoint().instrument).status is Status.UNAVAILABLE
    with pytest.raises(OSError):
        store.save(checkpoint())
    assert root.is_file() if kind == "file" else not root.exists()


def test_absence_does_not_write(tmp_path):
    assert (
        RadarCheckpointFileStore(tmp_path).lookup(checkpoint().instrument).status
        is Status.ABSENT
    )
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "code", [errno.EACCES, errno.EPERM, errno.EBUSY, errno.ENODEV, errno.EIO]
)
@pytest.mark.parametrize("boundary", ["root", "read"])
@pytest.mark.parametrize("lookup_method", ["lookup", "lookup_state"])
def test_recognized_unavailability(
    tmp_path, monkeypatch, code, boundary, lookup_method
):
    store = RadarCheckpointFileStore(tmp_path)
    store.save(checkpoint())
    failure = Mock(side_effect=OSError(code, "injected"))
    if boundary == "root":
        monkeypatch.setattr(storage.os, "scandir", failure)
    else:
        monkeypatch.setattr(Path, "open", failure)
    assert (
        getattr(store, lookup_method)(checkpoint().instrument).status == "UNAVAILABLE"
    )


@pytest.mark.parametrize("lookup_method", ["lookup", "lookup_state"])
def test_unknown_oserror_propagates(tmp_path, monkeypatch, lookup_method):
    error = OSError(errno.EINVAL, "unexpected")
    monkeypatch.setattr(storage.os, "scandir", Mock(side_effect=error))
    with pytest.raises(OSError) as caught:
        getattr(RadarCheckpointFileStore(tmp_path), lookup_method)(
            checkpoint().instrument
        )
    assert caught.value is error


@pytest.mark.parametrize("lookup_method", ["lookup", "lookup_state"])
def test_root_disappearing_before_absence(tmp_path, monkeypatch, lookup_method):
    store = RadarCheckpointFileStore(tmp_path)
    monkeypatch.setattr(
        store, "_check_root", Mock(side_effect=[None, FileNotFoundError()])
    )
    assert (
        getattr(store, lookup_method)(checkpoint().instrument).status == "UNAVAILABLE"
    )


@pytest.mark.parametrize(
    "raw",
    [
        b"{",
        b"\xff",
        b'{"x":1,"x":2}',
        b'{"x":{"a":1,"a":2}}',
        b"[]",
        b"null",
        b"NaN",
        b"Infinity",
        b"-Infinity",
    ],
)
@pytest.mark.parametrize("lookup_method", ["lookup", "lookup_state"])
def test_corrupt_bytes_raise_without_modification(tmp_path, raw, lookup_method):
    path = target(tmp_path, checkpoint())
    path.write_bytes(raw)
    with pytest.raises(RadarObservationStateError):
        getattr(RadarCheckpointFileStore(tmp_path), lookup_method)(
            checkpoint().instrument
        )
    with pytest.raises(RadarObservationStateError):
        RadarCheckpointFileStore(tmp_path).save(checkpoint())
    assert path.read_bytes() == raw


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", "future"),
        ("content_scope", {"schema_version": "future"}),
        ("instrument", {"instrument_id": "bad/path"}),
        ("observed_at", "bad"),
        ("normalized_market_content_identity", "bad"),
    ],
)
@pytest.mark.parametrize("lookup_method", ["lookup", "lookup_state"])
def test_invalid_contract(tmp_path, field, value, lookup_method):
    raw = checkpoint().to_dict()
    raw[field] = value
    target(tmp_path, checkpoint()).write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RadarObservationStateError):
        getattr(RadarCheckpointFileStore(tmp_path), lookup_method)(
            checkpoint().instrument
        )


@pytest.mark.parametrize("lookup_method", ["lookup", "lookup_state"])
def test_instrument_mismatch(tmp_path, lookup_method):
    target(tmp_path, checkpoint()).write_text(
        json.dumps(checkpoint("other").to_dict()), encoding="utf-8"
    )
    with pytest.raises(RadarObservationStateError, match="instrument mismatch"):
        getattr(RadarCheckpointFileStore(tmp_path), lookup_method)(
            checkpoint().instrument
        )


def test_safe_case_sensitive_names(tmp_path):
    ids = ["CON", "NUL", "COM1", "AUX", "con", "Us-msft", "us-msft", "a" * 128]
    store = RadarCheckpointFileStore(tmp_path)
    for instrument_id in ids:
        value = checkpoint(instrument_id)
        store.save(value)
        name = target(tmp_path, value).name
        assert re.fullmatch(r"id-[a-z2-7]+\.json", name)
        assert len(name) <= 255
        assert store.lookup(value.instrument).checkpoint == value
    assert len(list(tmp_path.iterdir())) == len(ids)


def test_atomic_replacement(tmp_path, monkeypatch):
    store = RadarCheckpointFileStore(tmp_path)
    first = checkpoint()
    second = replace(first, normalized_market_content_identity="sha256:" + "b" * 64)
    store.save(first)
    real_replace = os.replace
    calls = []

    def publish(source, destination):
        assert Path(source).parent == tmp_path
        assert store.lookup(first.instrument).checkpoint == first
        assert json.loads(Path(source).read_bytes()) == second.to_dict()
        calls.append(True)
        real_replace(source, destination)

    monkeypatch.setattr(storage.os, "replace", publish)
    store.save(second)
    assert calls == [True]
    assert store.lookup(first.instrument).checkpoint == second


@pytest.mark.parametrize("boundary", ["replace", "fsync", "write", "flush", "fdopen"])
def test_write_failure_preserves_previous_and_cleans_temp(
    tmp_path, monkeypatch, boundary
):
    store = RadarCheckpointFileStore(tmp_path)
    first = checkpoint()
    store.save(first)
    path = target(tmp_path, first)
    original = path.read_bytes()
    error = OSError(errno.EIO, "injected")
    if boundary in {"replace", "fsync", "fdopen"}:
        monkeypatch.setattr(storage.os, boundary, Mock(side_effect=error))
    else:
        real_fdopen = os.fdopen

        def open_stream(*args):
            stream = real_fdopen(*args)
            setattr(stream, boundary, Mock(side_effect=error))
            return stream

        monkeypatch.setattr(storage.os, "fdopen", open_stream)
    with pytest.raises(OSError) as caught:
        store.save(
            replace(first, normalized_market_content_identity="sha256:" + "b" * 64)
        )
    assert caught.value is error
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("dangling", [False, True])
@pytest.mark.parametrize("lookup_method", ["lookup", "lookup_state"])
def test_symlink_rejected(tmp_path, dangling, lookup_method):
    destination = tmp_path / "destination"
    if not dangling:
        destination.write_text(json.dumps(checkpoint().to_dict()), encoding="utf-8")
    path = target(tmp_path, checkpoint())
    try:
        path.symlink_to(destination)
    except OSError as exc:
        if getattr(exc, "winerror", None) == 1314 or exc.errno in {
            errno.EPERM,
            errno.ENOSYS,
        }:
            pytest.skip("symlink creation unavailable without privileges")
        raise
    store = RadarCheckpointFileStore(tmp_path)
    with pytest.raises(RadarCheckpointStoreError):
        getattr(store, lookup_method)(checkpoint().instrument)
    with pytest.raises(RadarCheckpointStoreError):
        store.save(checkpoint())
    assert path.is_symlink()


@pytest.mark.parametrize("boundary", ["lstat", "fstat"])
@pytest.mark.parametrize("lookup_method", ["lookup", "lookup_state"])
def test_reparse_attribute_rejected(tmp_path, monkeypatch, boundary, lookup_method):
    store = RadarCheckpointFileStore(tmp_path)
    store.save(checkpoint())
    info = SimpleNamespace(st_mode=stat.S_IFREG, st_file_attributes=0x400)
    if boundary == "lstat":
        monkeypatch.setattr(Path, "lstat", Mock(return_value=info))
    else:
        monkeypatch.setattr(storage.os, "fstat", Mock(return_value=info))
    with pytest.raises(RadarCheckpointStoreError):
        getattr(store, lookup_method)(checkpoint().instrument)
    if boundary == "lstat":
        with pytest.raises(RadarCheckpointStoreError):
            store.save(checkpoint())


@pytest.mark.parametrize("lookup_method", ["lookup", "lookup_state"])
def test_directory_target_rejected(tmp_path, lookup_method):
    target(tmp_path, checkpoint()).mkdir()
    store = RadarCheckpointFileStore(tmp_path)
    with pytest.raises(RadarCheckpointStoreError):
        getattr(store, lookup_method)(checkpoint().instrument)
    with pytest.raises(RadarCheckpointStoreError):
        store.save(checkpoint())


@pytest.mark.parametrize("value", [None, {}, "checkpoint", 1])
def test_wrong_save_type(tmp_path, value):
    with pytest.raises(TypeError, match="RadarObservationCheckpoint"):
        RadarCheckpointFileStore(tmp_path).save(value)
    assert list(tmp_path.iterdir()) == []


def complete_state(market=None):
    market = checkpoint() if market is None else market
    light = RadarLightweightObservation(
        market.instrument,
        EMA8_EMA20_OBSERVATION_DEFINITION_ID,
        EMA8_EMA20_CALCULATION_REVISION,
        EMA8_EMA20_OBSERVATION_SCHEMA,
        market.observed_completed_session,
        market.normalized_market_content_identity,
        market.content_scope,
        RadarEmaRelation.ABOVE,
        market.observed_at,
    )
    profile = RadarProfile(
        "test",
        "1",
        "test/v1",
        (RadarGateOccurrence("test", RadarGateIdentity("test", "1", "test/v1")),),
    )
    return RadarObservationState(
        market,
        light,
        evaluate_meaningful_change(None, light),
        profile.fingerprint,
        RadarPipelineOutcome.SELECTED,
    )


def test_state_absence_and_legacy_read_without_rewrite(tmp_path):
    store = RadarCheckpointFileStore(tmp_path)
    assert store.lookup_state(checkpoint().instrument).status is StateStatus.ABSENT
    assert list(tmp_path.iterdir()) == []
    store.save(checkpoint())
    path = target(tmp_path, checkpoint())
    raw = path.read_bytes()
    result = store.lookup_state(checkpoint().instrument)
    assert result.status is StateStatus.LEGACY_CONTENT_ONLY
    assert result.legacy_checkpoint == result.checkpoint == checkpoint()
    assert result.state is None
    assert path.read_bytes() == raw


@pytest.mark.parametrize("kind", ["missing", "file"])
def test_state_unusable_root_never_created(tmp_path, kind):
    root = tmp_path / "state"
    if kind == "file":
        root.write_bytes(b"root")
    store = RadarCheckpointFileStore(root)
    assert store.lookup_state(checkpoint().instrument).status is StateStatus.UNAVAILABLE
    with pytest.raises(OSError):
        store.save_state(complete_state())
    assert root.is_file() if kind == "file" else not root.exists()


def test_complete_state_roundtrip_bytes_projection_and_no_cache(tmp_path):
    value = complete_state()
    store = RadarCheckpointFileStore(tmp_path)
    store.save_state(value)
    path = target(tmp_path, checkpoint())
    raw = path.read_bytes()
    expected = (
        json.dumps(
            value.to_dict(),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        + b"\n"
    )
    assert raw == expected
    store.save_state(value)
    assert path.read_bytes() == raw
    assert list(tmp_path.iterdir()) == [path]
    result = store.lookup_state(value.market_observation.instrument)
    assert result.status is StateStatus.PRESENT_COMPLETE_STATE
    assert result.state == value
    assert result.legacy_checkpoint is None
    assert result.checkpoint == value.market_observation
    assert (
        store.lookup(value.market_observation.instrument).checkpoint
        == value.market_observation
    )
    again = RadarCheckpointFileStore(tmp_path).lookup_state(
        value.market_observation.instrument
    )
    assert again.state == value and again.state is not result.state
    replacement = replace(value, pipeline_outcome=RadarPipelineOutcome.FILTERED)
    store.save_state(replacement)
    assert store.lookup_state(value.market_observation.instrument).state == replacement
    path.unlink()
    assert (
        store.lookup_state(value.market_observation.instrument).status
        is StateStatus.ABSENT
    )


@pytest.mark.parametrize("complete", [False, True])
@pytest.mark.parametrize("lookup_method", ["lookup", "lookup_state"])
def test_lookup_reads_authoritative_file_once(
    tmp_path, monkeypatch, complete, lookup_method
):
    store = RadarCheckpointFileStore(tmp_path)
    if complete:
        store.save_state(complete_state())
    else:
        store.save(checkpoint())
    real_open = Path.open
    calls = []

    def open_once(path, *args, **kwargs):
        stream = real_open(path, *args, **kwargs)
        read = stream.read

        def read_once(*args):
            calls.append(path)
            return read(*args)

        stream.read = read_once
        return stream

    monkeypatch.setattr(Path, "open", open_once)
    getattr(store, lookup_method)(checkpoint().instrument)
    assert calls == [target(tmp_path, checkpoint())]


@pytest.mark.parametrize(
    "corruption", ["instrument", "incomplete", "schema", "nested", "duplicate"]
)
@pytest.mark.parametrize("lookup_method", ["lookup", "lookup_state"])
def test_invalid_complete_document_fails_closed(tmp_path, corruption, lookup_method):
    value = (
        complete_state(checkpoint("other"))
        if corruption == "instrument"
        else complete_state()
    )
    raw = value.to_dict()
    if corruption == "incomplete":
        del raw["lightweight_observation"]
    if corruption == "schema":
        raw["schema_version"] = "radar_observation_state/v2"
    if corruption == "nested":
        raw["committed_decision"]["meaningful_change"] = True
    data = json.dumps(raw).encode()
    if corruption == "duplicate":
        data = data.replace(
            b'"relation": "ABOVE"', b'"relation": "ABOVE", "relation": "BELOW"'
        )
    path = target(tmp_path, checkpoint())
    path.write_bytes(data)
    store = RadarCheckpointFileStore(tmp_path)
    with pytest.raises(RadarObservationStateError):
        getattr(store, lookup_method)(checkpoint().instrument)
    with pytest.raises(RadarObservationStateError):
        store.save(checkpoint())
    assert path.read_bytes() == data


def test_legacy_save_rejects_complete_downgrade_before_publication(
    tmp_path, monkeypatch
):
    store = RadarCheckpointFileStore(tmp_path)
    store.save_state(complete_state())
    path = target(tmp_path, checkpoint())
    raw = path.read_bytes()
    publication = Mock()
    temporary = Mock()
    monkeypatch.setattr(storage.os, "replace", publication)
    monkeypatch.setattr(storage.tempfile, "mkstemp", temporary)
    with pytest.raises(RadarCheckpointStoreError, match="downgrade"):
        store.save(checkpoint())
    publication.assert_not_called()
    temporary.assert_not_called()
    assert path.read_bytes() == raw
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("old_complete", [False, True])
def test_complete_atomic_publication_order(tmp_path, monkeypatch, old_complete):
    store = RadarCheckpointFileStore(tmp_path)
    if old_complete:
        store.save_state(complete_state())
    else:
        store.save(checkpoint())
    path = target(tmp_path, checkpoint())
    old = path.read_bytes()
    new = complete_state(
        replace(checkpoint(), normalized_market_content_identity="sha256:" + "b" * 64)
    )
    real_fdopen, real_fsync, real_replace = os.fdopen, os.fsync, os.replace
    calls, streams = [], []

    def fdopen(*args):
        stream = real_fdopen(*args)
        streams.append(stream)
        write, flush = stream.write, stream.flush

        def writing(data):
            calls.append("write")
            return write(data)

        def flushing():
            calls.append("flush")
            return flush()

        stream.write, stream.flush = writing, flushing
        return stream

    def fsync(fd):
        calls.append("fsync")
        assert not streams[0].closed
        real_fsync(fd)

    def publish(source, destination):
        assert calls[:3] == ["write", "flush", "fsync"]
        assert streams[0].closed
        assert path.read_bytes() == old
        assert Path(source).parent == tmp_path
        assert json.loads(Path(source).read_bytes()) == new.to_dict()
        real_replace(source, destination)
        assert store.lookup_state(checkpoint().instrument).state == new

    monkeypatch.setattr(storage.os, "fdopen", fdopen)
    monkeypatch.setattr(storage.os, "fsync", fsync)
    monkeypatch.setattr(storage.os, "replace", publish)
    store.save_state(new)
    assert store.lookup_state(checkpoint().instrument).state == new
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize(
    "boundary",
    ["serialization", "mkstemp", "fdopen", "write", "flush", "fsync", "replace"],
)
@pytest.mark.parametrize("old_complete", [False, True])
def test_state_publication_failure_preserves_bytes(
    tmp_path, monkeypatch, boundary, old_complete
):
    store = RadarCheckpointFileStore(tmp_path)
    if old_complete:
        store.save_state(complete_state())
    else:
        store.save(checkpoint())
    path = target(tmp_path, checkpoint())
    old = path.read_bytes()
    error = OSError(errno.EIO, "injected")
    if boundary == "serialization":
        monkeypatch.setattr(storage.json, "dumps", Mock(side_effect=error))
    elif boundary == "mkstemp":
        monkeypatch.setattr(storage.tempfile, "mkstemp", Mock(side_effect=error))
    elif boundary in {"fdopen", "fsync", "replace"}:
        monkeypatch.setattr(storage.os, boundary, Mock(side_effect=error))
    else:
        real_fdopen = os.fdopen

        def open_stream(*args):
            stream = real_fdopen(*args)
            if boundary == "write":

                def partial_write(data):
                    os.write(stream.fileno(), data[:20])
                    raise error

                stream.write = partial_write
            else:
                stream.flush = Mock(side_effect=error)
            return stream

        monkeypatch.setattr(storage.os, "fdopen", open_stream)
    with pytest.raises(OSError) as caught:
        store.save_state(
            complete_state(
                replace(
                    checkpoint(),
                    normalized_market_content_identity="sha256:" + "b" * 64,
                )
            )
        )
    assert caught.value is error
    assert path.read_bytes() == old
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("replace_fails", [False, True])
def test_cleanup_failure_cannot_undo_or_corrupt_publication(
    tmp_path, monkeypatch, replace_fails
):
    store = RadarCheckpointFileStore(tmp_path)
    store.save(checkpoint())
    path = target(tmp_path, checkpoint())
    old = path.read_bytes()
    monkeypatch.setattr(
        Path, "unlink", Mock(side_effect=OSError(errno.EACCES, "cleanup"))
    )
    if replace_fails:
        error = OSError(errno.EIO, "replace")
        monkeypatch.setattr(storage.os, "replace", Mock(side_effect=error))
        with pytest.raises(OSError) as caught:
            store.save_state(complete_state())
        assert caught.value is error
        assert path.read_bytes() == old
    else:
        store.save_state(complete_state())
        assert store.lookup_state(checkpoint().instrument).state == complete_state()


@pytest.mark.parametrize("kind", ["directory", "reparse", "symlink"])
def test_save_state_path_safety(tmp_path, monkeypatch, kind):
    path = target(tmp_path, checkpoint())
    if kind == "directory":
        path.mkdir()
    elif kind == "reparse":
        monkeypatch.setattr(
            Path,
            "lstat",
            Mock(
                return_value=SimpleNamespace(
                    st_mode=stat.S_IFREG, st_file_attributes=0x400
                )
            ),
        )
    else:
        try:
            path.symlink_to(tmp_path / "missing")
        except OSError as exc:
            if getattr(exc, "winerror", None) == 1314 or exc.errno in {
                errno.EPERM,
                errno.ENOSYS,
            }:
                pytest.skip("symlink creation unavailable without privileges")
            raise
    with pytest.raises(RadarCheckpointStoreError):
        RadarCheckpointFileStore(tmp_path).save_state(complete_state())


@pytest.mark.parametrize("bad", [None, {}, 1, "state", checkpoint()])
def test_save_state_requires_complete_value(tmp_path, bad):
    with pytest.raises(TypeError):
        RadarCheckpointFileStore(tmp_path).save_state(bad)
    assert list(tmp_path.iterdir()) == []


def test_state_case_sensitive_filename_isolation(tmp_path):
    store = RadarCheckpointFileStore(tmp_path)
    for name in ["Us-msft", "us-msft", "CON", "con"]:
        value = complete_state(checkpoint(name))
        store.save_state(value)
        assert target(tmp_path, value.market_observation).is_file()
        assert store.lookup_state(value.market_observation.instrument).state == value
    assert len(list(tmp_path.iterdir())) == 4


def test_legacy_save_does_not_implicitly_project_state(tmp_path):
    with pytest.raises(TypeError, match="RadarObservationCheckpoint"):
        RadarCheckpointFileStore(tmp_path).save(complete_state())
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("boundary", ["root", "read"])
def test_legacy_save_preserves_operational_failure(tmp_path, monkeypatch, boundary):
    store = RadarCheckpointFileStore(tmp_path)
    store.save(checkpoint())
    error = OSError(errno.EACCES, "injected")
    publication = Mock()
    monkeypatch.setattr(storage.os, "replace", publication)
    with monkeypatch.context() as patch:
        if boundary == "root":
            patch.setattr(storage.os, "scandir", Mock(side_effect=error))
        else:
            patch.setattr(Path, "open", Mock(side_effect=error))
        with pytest.raises(OSError) as caught:
            store.save(checkpoint())
        assert caught.value is error
    publication.assert_not_called()
    assert store.lookup(checkpoint().instrument).checkpoint == checkpoint()


@pytest.mark.parametrize("lookup_method", ["lookup", "lookup_state"])
def test_file_disappearing_during_read_still_raises(
    tmp_path, monkeypatch, lookup_method
):
    store = RadarCheckpointFileStore(tmp_path)
    store.save(checkpoint())
    monkeypatch.setattr(Path, "open", Mock(side_effect=FileNotFoundError()))
    with pytest.raises(FileNotFoundError):
        getattr(store, lookup_method)(checkpoint().instrument)


@pytest.mark.parametrize(
    "corruption",
    ["json", "utf8", "duplicate", "schema", "incomplete", "instrument", "nested"],
)
def test_save_state_rejects_invalid_prior_before_publication(
    tmp_path, monkeypatch, corruption
):
    document = complete_state().to_dict()
    if corruption == "schema":
        document["schema_version"] = "radar_observation_state/v2"
    elif corruption == "incomplete":
        del document["lightweight_observation"]
    elif corruption == "instrument":
        document = complete_state(checkpoint("other")).to_dict()
    elif corruption == "nested":
        document["committed_decision"]["meaningful_change"] = True
    raw = json.dumps(document).encode("utf-8")
    if corruption == "json":
        raw = b"{"
    elif corruption == "utf8":
        raw = b"\xff"
    elif corruption == "duplicate":
        raw = raw.replace(
            b'"relation": "ABOVE"', b'"relation": "ABOVE", "relation": "BELOW"'
        )
    path = target(tmp_path, checkpoint())
    path.write_bytes(raw)
    temporary, publication = Mock(), Mock()
    monkeypatch.setattr(storage.tempfile, "mkstemp", temporary)
    monkeypatch.setattr(storage.os, "replace", publication)

    with pytest.raises(RadarObservationStateError):
        RadarCheckpointFileStore(tmp_path).save_state(complete_state())

    temporary.assert_not_called()
    publication.assert_not_called()
    assert path.read_bytes() == raw
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("boundary", ["root", "read"])
@pytest.mark.parametrize("code", [errno.EACCES, errno.EIO, errno.ENOENT, errno.ENOTDIR])
def test_save_state_preflight_propagates_operational_failure(
    tmp_path, monkeypatch, boundary, code
):
    store = RadarCheckpointFileStore(tmp_path)
    store.save(checkpoint())
    path = target(tmp_path, checkpoint())
    original = path.read_bytes()
    error = OSError(code, "injected")
    temporary, publication = Mock(), Mock()
    monkeypatch.setattr(storage.tempfile, "mkstemp", temporary)
    monkeypatch.setattr(storage.os, "replace", publication)
    with monkeypatch.context() as patch:
        if boundary == "root":
            patch.setattr(storage.os, "scandir", Mock(side_effect=error))
        else:
            patch.setattr(Path, "open", Mock(side_effect=error))
        with pytest.raises(OSError) as caught:
            store.save_state(complete_state())
        assert caught.value is error
    temporary.assert_not_called()
    publication.assert_not_called()
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]
