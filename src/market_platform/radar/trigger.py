"""Read-only session/content trigger; PASS requests further Radar evaluation."""

import re
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from market_platform.instruments.identity import CanonicalInstrumentId
from market_platform.radar.calendar import ExchangeSessionCalendar
from market_platform.radar.context import RadarEvaluationContext, RadarFactKey
from market_platform.radar.core import (
    RadarGateDisposition,
    RadarGateIdentity,
    RadarGateOccurrence,
    RadarGateResult,
)
from market_platform.radar.observation import (
    RadarMarketContentScope,
    RadarObservationLookupResult,
    RadarObservationLookupStatus,
)
from market_platform.radar.resolver import RadarGateImplementationKey

SESSION_CONTENT_TRIGGER_KEY = RadarGateImplementationKey(
    "session_content_trigger", "1", "session_content_trigger/v1"
)


class RadarCurrentMarketContentError(ValueError):
    """Malformed current correspondence or lookup, never unavailability."""


@dataclass(frozen=True, slots=True)
class RadarCurrentMarketContent:
    """Caller-prepared completed-daily correspondence, without authority.

    No hashing, acquisition or completeness verification occurs here. The scope
    carries the existing normalized market-content comparison conventions.
    """

    instrument: CanonicalInstrumentId
    completed_session: date
    normalized_market_content_identity: str
    content_scope: RadarMarketContentScope

    def __post_init__(self) -> None:
        if type(self.instrument) is not CanonicalInstrumentId:
            raise RadarCurrentMarketContentError(
                "instrument must be a CanonicalInstrumentId"
            )
        if type(self.completed_session) is not date:
            raise RadarCurrentMarketContentError(
                "completed_session must be a plain date"
            )
        if type(self.content_scope) is not RadarMarketContentScope:
            raise RadarCurrentMarketContentError(
                "content_scope must be RadarMarketContentScope"
            )
        if self.content_scope.history_end != self.completed_session:
            raise RadarCurrentMarketContentError(
                "completed session must equal history_end"
            )
        identity = self.normalized_market_content_identity
        if (
            type(identity) is not str
            or re.fullmatch(r"sha256:[0-9a-f]{64}", identity) is None
        ):
            raise RadarCurrentMarketContentError(
                "Invalid normalized market-content identity"
            )


class RadarCurrentMarketContentLookupStatus(StrEnum):
    """Expected availability, independent of Gate disposition."""

    PRESENT = "PRESENT"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class RadarCurrentMarketContentLookupResult:
    """Expected operational unavailability must be supplied explicitly."""

    status: RadarCurrentMarketContentLookupStatus
    content: RadarCurrentMarketContent | None = None

    def __post_init__(self) -> None:
        if type(self.status) is not RadarCurrentMarketContentLookupStatus:
            raise RadarCurrentMarketContentError(
                "status must be RadarCurrentMarketContentLookupStatus"
            )
        if self.status is RadarCurrentMarketContentLookupStatus.PRESENT:
            if type(self.content) is not RadarCurrentMarketContent:
                raise RadarCurrentMarketContentError("PRESENT requires valid content")
        elif self.content is not None:
            raise RadarCurrentMarketContentError("UNAVAILABLE forbids content")


PRIOR_OBSERVATION_LOOKUP = RadarFactKey(
    "radar.prior_observation_lookup/v1", RadarObservationLookupResult
)
CURRENT_MARKET_CONTENT_LOOKUP = RadarFactKey(
    "radar.current_market_content_lookup/v1", RadarCurrentMarketContentLookupResult
)


class RadarSessionContentTriggerGate:
    """V1 has empty configuration and directly injected trusted Calendar wiring.

    Construction performs no queries. Unexpected calendar/fact errors escape to
    the Pipeline. PASS is a trigger only, never a materiality classification.
    """

    __slots__ = ("_occurrence", "_calendar")

    def __init__(
        self, occurrence: RadarGateOccurrence, calendar: ExchangeSessionCalendar
    ) -> None:
        if type(occurrence) is not RadarGateOccurrence:
            raise TypeError("occurrence must be a RadarGateOccurrence")
        identity = occurrence.gate_identity
        key = RadarGateImplementationKey(
            identity.gate_id,
            identity.behavioral_revision,
            identity.configuration_schema,
        )
        if key != SESSION_CONTENT_TRIGGER_KEY:
            raise ValueError("Unsupported session/content trigger implementation")
        if identity.configuration:
            raise ValueError("Session/content trigger v1 requires empty configuration")
        self._occurrence = occurrence
        self._calendar = calendar

    @property
    def identity(self) -> RadarGateIdentity:
        return self._occurrence.gate_identity

    def _result(
        self, disposition: RadarGateDisposition, reason: str
    ) -> RadarGateResult:
        return RadarGateResult(self._occurrence, disposition, reason)

    def evaluate(self, context: RadarEvaluationContext) -> RadarGateResult:
        prior = context.get_fact(PRIOR_OBSERVATION_LOOKUP)
        attention = RadarGateDisposition.ATTENTION
        if prior.status is RadarObservationLookupStatus.UNAVAILABLE:
            return self._result(attention, "PRIOR_STATE_UNAVAILABLE")

        latest = self._calendar.latest_completed_session(context.as_of)
        checkpoint = prior.checkpoint
        if checkpoint is not None:
            if checkpoint.instrument != context.instrument:
                return self._result(attention, "PRIOR_INSTRUMENT_MISMATCH")
            if not self._calendar.is_session(checkpoint.observed_completed_session):
                return self._result(attention, "PRIOR_NOT_SESSION")
            if checkpoint.observed_completed_session > latest:
                return self._result(attention, "PRIOR_SESSION_AHEAD")

        current = context.get_fact(CURRENT_MARKET_CONTENT_LOOKUP)
        if current.status is RadarCurrentMarketContentLookupStatus.UNAVAILABLE:
            return self._result(attention, "CURRENT_CONTENT_UNAVAILABLE")
        content = current.content
        assert content is not None  # Enforced by the typed lookup value.
        if content.instrument != context.instrument:
            return self._result(attention, "CURRENT_INSTRUMENT_MISMATCH")
        if content.completed_session != latest:
            return self._result(attention, "CURRENT_SESSION_MISMATCH")

        if checkpoint is None:
            return self._result(RadarGateDisposition.PASS, "BASELINE_REQUIRED")
        if checkpoint.observed_completed_session < latest:
            return self._result(RadarGateDisposition.PASS, "NEW_COMPLETED_SESSION")
        if checkpoint.content_scope != content.content_scope:
            return self._result(attention, "INCOMPARABLE_CONTENT_SCOPE")
        if (
            checkpoint.normalized_market_content_identity
            == content.normalized_market_content_identity
        ):
            return self._result(RadarGateDisposition.DROP, "UNCHANGED")
        return self._result(RadarGateDisposition.PASS, "MARKET_CONTENT_CHANGED")
