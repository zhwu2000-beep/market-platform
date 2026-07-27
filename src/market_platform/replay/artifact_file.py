"""Atomic local JSON persistence for historical replay artifacts."""

from __future__ import annotations

import codecs
import json
import os
import tempfile
from os import PathLike
from pathlib import Path

from market_platform.replay.artifact import (
    HistoricalReplayArtifact,
    HistoricalReplayArtifactError,
)


def save_historical_replay_artifact(
    path: str | PathLike[str],
    artifact: HistoricalReplayArtifact,
    *,
    overwrite: bool = False,
) -> Path:
    """Atomically save one deterministic historical replay artifact."""

    if not isinstance(artifact, HistoricalReplayArtifact):
        raise TypeError("artifact must be a HistoricalReplayArtifact")
    if not isinstance(overwrite, bool):
        raise TypeError("overwrite must be a bool")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not overwrite:
        raise FileExistsError(target)

    payload = json.dumps(
        artifact.to_dict(),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8") + b"\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=target.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if overwrite:
            os.replace(temporary_path, target)
        else:
            os.link(temporary_path, target)
            # Publication has succeeded. Failure to remove the temporary hard-link
            # name must not turn a successful save into a reported failure.
            _best_effort_unlink(temporary_path)
    except Exception:
        _best_effort_unlink(temporary_path)
        raise
    return target


def _best_effort_unlink(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass


def load_historical_replay_artifact(
    path: str | PathLike[str],
) -> HistoricalReplayArtifact:
    """Load, reconstruct, and verify one local Replay artifact."""

    source = Path(path)
    raw = source.read_bytes()
    if raw.startswith(codecs.BOM_UTF8):
        raise HistoricalReplayArtifactError("artifact must not contain a UTF-8 BOM")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise HistoricalReplayArtifactError("artifact is not valid UTF-8") from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise HistoricalReplayArtifactError("artifact is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise HistoricalReplayArtifactError("artifact JSON root must be an object")
    return HistoricalReplayArtifact.from_dict(payload)


def verify_historical_replay_artifact(
    path: str | PathLike[str],
) -> HistoricalReplayArtifact:
    """Verify and return one local Replay artifact."""

    return load_historical_replay_artifact(path)


__all__ = [
    "load_historical_replay_artifact",
    "save_historical_replay_artifact",
    "verify_historical_replay_artifact",
]
