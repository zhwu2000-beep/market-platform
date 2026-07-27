"""Versioned durable envelope for one historical replay execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from market_platform.replay.provenance import HistoricalReplayExecution

if TYPE_CHECKING:
    from collections.abc import Mapping

ARTIFACT_SCHEMA_VERSION = "historical_replay_artifact/v1"
INTEGRITY_SCHEMA_VERSION = "historical_replay_artifact_integrity/v1"
INTEGRITY_ALGORITHM = "sha256"


class HistoricalReplayArtifactError(ValueError):
    """Raised when a historical replay artifact is malformed."""


class HistoricalReplayArtifactIntegrityError(HistoricalReplayArtifactError):
    """Raised when replay artifact identity or integrity verification fails."""


@dataclass(frozen=True, slots=True)
class HistoricalReplayArtifact:
    """Immutable, versioned durable envelope for a replay execution."""

    execution: HistoricalReplayExecution
    schema_version: str = field(init=False, default=ARTIFACT_SCHEMA_VERSION)
    result_fingerprint: str = field(init=False)
    integrity_checksum: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.execution, HistoricalReplayExecution):
            raise TypeError("execution must be a HistoricalReplayExecution")
        from market_platform.replay.artifact_serialization import (
            historical_replay_artifact_integrity_checksum,
            historical_replay_result_fingerprint,
        )

        result_fingerprint = historical_replay_result_fingerprint(
            self.execution.result
        )
        object.__setattr__(self, "result_fingerprint", result_fingerprint)
        object.__setattr__(
            self,
            "integrity_checksum",
            historical_replay_artifact_integrity_checksum(
                self.execution,
                result_fingerprint,
            ),
        )

    @classmethod
    def from_execution(
        cls,
        execution: HistoricalReplayExecution,
    ) -> HistoricalReplayArtifact:
        """Build a verified artifact from an in-memory execution."""

        return cls(execution=execution)

    def to_dict(self) -> dict[str, object]:
        """Return the canonical versioned artifact payload."""

        from market_platform.replay.artifact_serialization import artifact_to_dict

        return artifact_to_dict(self)

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, object],
    ) -> HistoricalReplayArtifact:
        """Strictly decode and verify a versioned artifact payload."""

        from market_platform.replay.artifact_serialization import artifact_from_dict

        return artifact_from_dict(payload)


__all__ = [
    "HistoricalReplayArtifact",
    "HistoricalReplayArtifactError",
    "HistoricalReplayArtifactIntegrityError",
]
