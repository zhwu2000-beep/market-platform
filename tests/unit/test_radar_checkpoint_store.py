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
from market_platform.radar.observation import (
    RadarMarketContentScope,
    RadarObservationCheckpoint,
    RadarObservationStateError,
)
from market_platform.radar.observation import (
    RadarObservationLookupStatus as Status,
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
def test_recognized_unavailability(tmp_path, monkeypatch, code, boundary):
    store = RadarCheckpointFileStore(tmp_path)
    store.save(checkpoint())
    failure = Mock(side_effect=OSError(code, "injected"))
    if boundary == "root":
        monkeypatch.setattr(storage.os, "scandir", failure)
    else:
        monkeypatch.setattr(Path, "open", failure)
    assert store.lookup(checkpoint().instrument).status is Status.UNAVAILABLE


def test_unknown_oserror_propagates(tmp_path, monkeypatch):
    error = OSError(errno.EINVAL, "unexpected")
    monkeypatch.setattr(storage.os, "scandir", Mock(side_effect=error))
    with pytest.raises(OSError) as caught:
        RadarCheckpointFileStore(tmp_path).lookup(checkpoint().instrument)
    assert caught.value is error


def test_root_disappearing_before_absence(tmp_path, monkeypatch):
    store = RadarCheckpointFileStore(tmp_path)
    monkeypatch.setattr(
        store, "_check_root", Mock(side_effect=[None, FileNotFoundError()])
    )
    assert store.lookup(checkpoint().instrument).status is Status.UNAVAILABLE


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
def test_corrupt_bytes_raise_without_modification(tmp_path, raw):
    path = target(tmp_path, checkpoint())
    path.write_bytes(raw)
    with pytest.raises(RadarObservationStateError):
        RadarCheckpointFileStore(tmp_path).lookup(checkpoint().instrument)
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
def test_invalid_contract(tmp_path, field, value):
    raw = checkpoint().to_dict()
    raw[field] = value
    target(tmp_path, checkpoint()).write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RadarObservationStateError):
        RadarCheckpointFileStore(tmp_path).lookup(checkpoint().instrument)


def test_instrument_mismatch(tmp_path):
    target(tmp_path, checkpoint()).write_text(
        json.dumps(checkpoint("other").to_dict()), encoding="utf-8"
    )
    with pytest.raises(RadarObservationStateError, match="instrument mismatch"):
        RadarCheckpointFileStore(tmp_path).lookup(checkpoint().instrument)


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
def test_symlink_rejected(tmp_path, dangling):
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
        store.lookup(checkpoint().instrument)
    with pytest.raises(RadarCheckpointStoreError):
        store.save(checkpoint())
    assert path.is_symlink()


@pytest.mark.parametrize("boundary", ["lstat", "fstat"])
def test_reparse_attribute_rejected(tmp_path, monkeypatch, boundary):
    store = RadarCheckpointFileStore(tmp_path)
    store.save(checkpoint())
    info = SimpleNamespace(st_mode=stat.S_IFREG, st_file_attributes=0x400)
    if boundary == "lstat":
        monkeypatch.setattr(Path, "lstat", Mock(return_value=info))
    else:
        monkeypatch.setattr(storage.os, "fstat", Mock(return_value=info))
    with pytest.raises(RadarCheckpointStoreError):
        store.lookup(checkpoint().instrument)
    if boundary == "lstat":
        with pytest.raises(RadarCheckpointStoreError):
            store.save(checkpoint())


def test_directory_target_rejected(tmp_path):
    target(tmp_path, checkpoint()).mkdir()
    store = RadarCheckpointFileStore(tmp_path)
    with pytest.raises(RadarCheckpointStoreError):
        store.lookup(checkpoint().instrument)
    with pytest.raises(RadarCheckpointStoreError):
        store.save(checkpoint())


@pytest.mark.parametrize("value", [None, {}, "checkpoint", 1])
def test_wrong_save_type(tmp_path, value):
    with pytest.raises(TypeError, match="RadarObservationCheckpoint"):
        RadarCheckpointFileStore(tmp_path).save(value)
    assert list(tmp_path.iterdir()) == []
