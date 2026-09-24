"""Passive Radar observation correspondence, without persistence or authority."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum

from market_platform.instruments.identity import CanonicalInstrumentId

RADAR_OBSERVATION_CHECKPOINT_SCHEMA = "radar_observation_checkpoint/v1"
RADAR_MARKET_CONTENT_SCOPE_SCHEMA = "radar_market_content_scope/v1"


class RadarObservationStateError(ValueError):
    """Invalid observation state; never successful absence or unavailability."""


def _text(value: object, name: str) -> str:
    if type(value) is not str:
        raise RadarObservationStateError(f"{name} must be a string")
    return value


def _schema(value: object, expected: str) -> None:
    if _text(value, "schema_version") != expected:
        raise RadarObservationStateError(
            f"Unsupported schema_version; expected {expected}"
        )


def _object(value: object, fields: set[str]) -> dict[str, object]:
    if type(value) is not dict or set(value) != fields:
        raise RadarObservationStateError(
            "Expected an object with exactly required fields"
        )
    return value


def _date(value: object, name: str) -> date:
    if type(value) is not date:
        raise RadarObservationStateError(f"{name} must be a plain date")
    return value


def _decode_date(value: object, name: str) -> date:
    text = _text(value, name)
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise RadarObservationStateError(f"Invalid {name}") from exc
    if parsed.isoformat() != text:
        raise RadarObservationStateError(f"{name} must use YYYY-MM-DD")
    return parsed


def _utc(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise RadarObservationStateError("observed_at must be a datetime")
    try:
        if value.tzinfo is None or value.utcoffset() is None:
            raise RadarObservationStateError("observed_at must be timezone-aware")
        # Reconstruct first: retain neither a datetime subclass nor its attributes.
        plain = datetime(
            value.year,
            value.month,
            value.day,
            value.hour,
            value.minute,
            value.second,
            value.microsecond,
            tzinfo=value.tzinfo,
            fold=value.fold,
        )
        return plain.astimezone(UTC)
    except (ValueError, OverflowError) as exc:
        raise RadarObservationStateError(f"Invalid observed_at: {exc}") from exc


@dataclass(frozen=True, slots=True)
class RadarMarketContentScope:
    """V1: split-adjusted (not dividend-adjusted), completed daily OHLCV.

    Each bar's exchange-local session date is represented as midnight UTC,
    not the session open/close instant. Coverage is the inclusive history_start
    through history_end comparison window, using HistoricalPriceSeries content
    identity v1. Equal scopes are required before comparing content identities.

    This value declares correspondence only: it does not prove bar completeness,
    freshness, adjustment correctness, or calendar membership. Other price bases
    and timestamp representations require a new supported scope schema.
    """

    history_start: date
    history_end: date
    schema_version: str = RADAR_MARKET_CONTENT_SCOPE_SCHEMA

    def __post_init__(self) -> None:
        _schema(self.schema_version, RADAR_MARKET_CONTENT_SCOPE_SCHEMA)
        _date(self.history_start, "history_start")
        _date(self.history_end, "history_end")
        if self.history_start > self.history_end:
            raise RadarObservationStateError(
                "history_start must not exceed history_end"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "history_start": self.history_start.isoformat(),
            "history_end": self.history_end.isoformat(),
        }

    @classmethod
    def from_dict(cls, value: object) -> RadarMarketContentScope:
        raw = _object(value, {"schema_version", "history_start", "history_end"})
        return cls(
            history_start=_decode_date(raw["history_start"], "history_start"),
            history_end=_decode_date(raw["history_end"], "history_end"),
            schema_version=_text(raw["schema_version"], "schema_version"),
        )


@dataclass(frozen=True, slots=True)
class RadarObservationCheckpoint:
    """Successful Radar observation through a completed session and content scope.

    observed_at is the wall-clock completion/acceptance instant, not a market,
    retrieval or Evidence time. This asserts no material change, Candidate,
    research, Evidence admission, Strategy approval or execution authorization.
    Construction neither checks a calendar nor advances any stored checkpoint.
    """

    instrument: CanonicalInstrumentId
    observed_completed_session: date
    normalized_market_content_identity: str
    observed_at: datetime
    content_scope: RadarMarketContentScope
    schema_version: str = RADAR_OBSERVATION_CHECKPOINT_SCHEMA

    def __post_init__(self) -> None:
        _schema(self.schema_version, RADAR_OBSERVATION_CHECKPOINT_SCHEMA)
        if type(self.instrument) is not CanonicalInstrumentId:
            raise RadarObservationStateError(
                "instrument must be a CanonicalInstrumentId"
            )
        _date(self.observed_completed_session, "observed_completed_session")
        if type(self.content_scope) is not RadarMarketContentScope:
            raise RadarObservationStateError(
                "content_scope must be RadarMarketContentScope"
            )
        if self.observed_completed_session != self.content_scope.history_end:
            raise RadarObservationStateError("completed session must equal history_end")
        identity = _text(self.normalized_market_content_identity, "content identity")
        # Exact format emitted by HistoricalPriceSeries.content_fingerprint.
        # No OHLCV hashing or checkpoint hashing belongs in this value contract.
        if re.fullmatch(r"sha256:[0-9a-f]{64}", identity) is None:
            raise RadarObservationStateError(
                "Invalid normalized market-content identity"
            )
        object.__setattr__(self, "observed_at", _utc(self.observed_at))

    def to_dict(self) -> dict[str, object]:
        """Return detached passive data in deterministic field order."""
        return {
            "schema_version": self.schema_version,
            "instrument": self.instrument.to_dict(),
            "observed_completed_session": self.observed_completed_session.isoformat(),
            "normalized_market_content_identity": (
                self.normalized_market_content_identity
            ),
            "observed_at": self.observed_at.isoformat(),
            "content_scope": self.content_scope.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: object) -> RadarObservationCheckpoint:
        """Strictly decode state; malformed data always raises, including None."""
        raw = _object(
            value,
            {
                "schema_version",
                "instrument",
                "observed_completed_session",
                "normalized_market_content_identity",
                "observed_at",
                "content_scope",
            },
        )
        instrument = _object(raw["instrument"], {"instrument_id"})
        try:
            return cls(
                instrument=CanonicalInstrumentId(
                    _text(instrument["instrument_id"], "instrument_id")
                ),
                observed_completed_session=_decode_date(
                    raw["observed_completed_session"], "observed_completed_session"
                ),
                normalized_market_content_identity=_text(
                    raw["normalized_market_content_identity"], "content identity"
                ),
                observed_at=datetime.fromisoformat(
                    _text(raw["observed_at"], "observed_at")
                ),
                content_scope=RadarMarketContentScope.from_dict(raw["content_scope"]),
                schema_version=_text(raw["schema_version"], "schema_version"),
            )
        except (TypeError, ValueError, OverflowError) as exc:
            raise RadarObservationStateError(
                f"Malformed observation checkpoint: {exc}"
            ) from exc


class RadarObservationLookupStatus(StrEnum):
    """Lookup state, independent of any Gate decision or fact-loader wiring."""

    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class RadarObservationLookupResult:
    """Only ABSENT means a successful lookup found no prior checkpoint.

    UNAVAILABLE means an expected operational condition prevented a trustworthy
    answer. Missing fact loaders and malformed persisted state are errors, not
    lookup absence; this contract performs no conversion of either error.
    """

    status: RadarObservationLookupStatus
    checkpoint: RadarObservationCheckpoint | None = None

    def __post_init__(self) -> None:
        if type(self.status) is not RadarObservationLookupStatus:
            raise RadarObservationStateError(
                "status must be RadarObservationLookupStatus"
            )
        if self.status is RadarObservationLookupStatus.PRESENT:
            if type(self.checkpoint) is not RadarObservationCheckpoint:
                raise RadarObservationStateError("PRESENT requires a valid checkpoint")
        elif self.checkpoint is not None:
            raise RadarObservationStateError("ABSENT/UNAVAILABLE forbid a checkpoint")
