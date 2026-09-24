"""Local checkpoint storage, with no checkpoint advancement policy.

One local owner must prevent overlapping evaluations/writes for each instrument.
Distinct files are independent; there is no multi-instrument transaction. Atomic
replacement prevents torn publication, not stale-writer overwrite.
"""

from __future__ import annotations

import base64
import errno
import json
import os
import stat
import tempfile
from contextlib import suppress
from pathlib import Path

from market_platform.instruments.identity import CanonicalInstrumentId
from market_platform.radar.observation import (
    RadarObservationCheckpoint,
    RadarObservationLookupResult,
    RadarObservationLookupStatus,
    RadarObservationStateError,
)

_REPARSE_POINT = 0x400
_UNAVAILABLE_ERRNOS = {errno.EACCES, errno.EPERM, errno.EBUSY, errno.ENODEV, errno.EIO}
# Access denied, sharing/lock violation, and device not ready.
_UNAVAILABLE_WINERRORS = {5, 21, 32, 33}


class RadarCheckpointStoreError(ValueError):
    """Invalid store configuration or unsafe authoritative target."""


def _filename(instrument: CanonicalInstrumentId) -> str:
    if type(instrument) is not CanonicalInstrumentId:
        raise TypeError("instrument must be a CanonicalInstrumentId")
    encoded = base64.b32encode(instrument.instrument_id.encode("ascii"))
    return "id-" + encoded.decode("ascii").rstrip("=").lower() + ".json"


def _regular_file(info: os.stat_result) -> None:
    if (
        not stat.S_ISREG(info.st_mode)
        or getattr(info, "st_file_attributes", 0) & _REPARSE_POINT
    ):
        raise RadarCheckpointStoreError(
            "checkpoint target must be a regular non-reparse file"
        )


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise RadarObservationStateError("Duplicate checkpoint JSON key")
        result[key] = value
    return result


def _reject_constant(value: str) -> object:
    raise RadarObservationStateError("Non-finite checkpoint JSON number")


class RadarCheckpointFileStore:
    """Persist explicit checkpoints under a caller-provisioned absolute root.

    The root is trusted local storage and is never created here. Filesystem
    write failures and unexpected lookup OSErrors propagate to the caller.
    No directory fsync, locking, or exactly-once guarantee is provided.
    """

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self._root = Path(root)
        if not self._root.is_absolute():
            raise RadarCheckpointStoreError("checkpoint root must be absolute")

    def _check_root(self) -> None:
        # Opening the directory checks availability even when the file is absent.
        with os.scandir(self._root):
            pass

    def lookup(self, instrument: CanonicalInstrumentId) -> RadarObservationLookupResult:
        target = self._root / _filename(instrument)
        try:
            try:
                self._check_root()
            except FileNotFoundError, NotADirectoryError:
                return RadarObservationLookupResult(
                    RadarObservationLookupStatus.UNAVAILABLE
                )
            try:
                info = target.lstat()
            except FileNotFoundError:
                # A root removed since the initial check is not successful absence.
                try:
                    self._check_root()
                except FileNotFoundError, NotADirectoryError:
                    return RadarObservationLookupResult(
                        RadarObservationLookupStatus.UNAVAILABLE
                    )
                return RadarObservationLookupResult(RadarObservationLookupStatus.ABSENT)
            _regular_file(info)
            with target.open("rb") as stream:
                _regular_file(os.fstat(stream.fileno()))
                raw = stream.read()
        except OSError as exc:
            if (
                exc.errno in _UNAVAILABLE_ERRNOS
                or getattr(exc, "winerror", None) in _UNAVAILABLE_WINERRORS
            ):
                return RadarObservationLookupResult(
                    RadarObservationLookupStatus.UNAVAILABLE
                )
            raise
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RadarObservationStateError("Checkpoint is not valid UTF-8") from exc
        try:
            payload = json.loads(
                text, object_pairs_hook=_unique_object, parse_constant=_reject_constant
            )
        except json.JSONDecodeError as exc:
            raise RadarObservationStateError("Checkpoint is not valid JSON") from exc
        checkpoint = RadarObservationCheckpoint.from_dict(payload)
        if checkpoint.instrument != instrument:
            raise RadarObservationStateError("Checkpoint instrument mismatch")
        return RadarObservationLookupResult(
            RadarObservationLookupStatus.PRESENT, checkpoint
        )

    def save(self, checkpoint: RadarObservationCheckpoint) -> None:
        if type(checkpoint) is not RadarObservationCheckpoint:
            raise TypeError("checkpoint must be a RadarObservationCheckpoint")
        payload = (
            json.dumps(
                checkpoint.to_dict(),
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            + b"\n"
        )
        self._check_root()
        target = self._root / _filename(checkpoint.instrument)
        try:
            info = target.lstat()
        except FileNotFoundError:
            pass
        else:
            _regular_file(info)
        descriptor, name = tempfile.mkstemp(
            prefix=".radar-", suffix=".tmp", dir=self._root
        )
        temporary = Path(name)
        try:
            try:
                stream = os.fdopen(descriptor, "wb")
            except Exception:
                os.close(descriptor)
                raise
            with stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            # Cleanup must not hide the original failure or undo publication.
            with suppress(OSError):
                temporary.unlink(missing_ok=True)
