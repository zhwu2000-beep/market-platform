"""Application composition for one Polygon completed-daily Evidence Candidate."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Protocol, runtime_checkable

from market_platform.data.providers.polygon import PolygonCompletedDailyAcquisition
from market_platform.evidence_ingress import (
    PolygonCompletedDailyOhlcvEvidenceIngressResult,
    create_polygon_completed_daily_ohlcv_evidence,
)
from market_platform.instruments import (
    ExternalInstrumentIdentity,
    InstrumentMapping,
    resolve_instrument_mapping,
)


@dataclass(frozen=True, slots=True)
class PolygonCompletedDailyEvidenceCandidateApplicationRequest:
    """Trusted operator inputs for the fixed Polygon Candidate use case."""

    external_identity: ExternalInstrumentIdentity
    mappings: tuple[InstrumentMapping, ...]
    requested_from: date
    requested_to: date
    query_as_of: datetime

    def __post_init__(self) -> None:
        if type(self.query_as_of) is not datetime:
            raise TypeError("query_as_of must be an exact datetime")
        if self.query_as_of.tzinfo is None or self.query_as_of.utcoffset() is None:
            raise ValueError("query_as_of must be timezone-aware")
        object.__setattr__(self, "query_as_of", self.query_as_of.astimezone(UTC))
        self._validate()

    def _validate(self) -> None:
        if type(self.external_identity) is not ExternalInstrumentIdentity:
            raise TypeError(
                "external_identity must be an exact ExternalInstrumentIdentity"
            )
        self.external_identity._validate()
        if type(self.mappings) is not tuple:
            raise TypeError("mappings must be an exact immutable tuple")
        for mapping in self.mappings:
            if type(mapping) is not InstrumentMapping:
                raise TypeError("every mapping must be an exact InstrumentMapping")
            mapping._validate()
        if type(self.requested_from) is not date:
            raise TypeError("requested_from must be an exact date")
        if type(self.requested_to) is not date:
            raise TypeError("requested_to must be an exact date")
        if self.requested_from > self.requested_to:
            raise ValueError(
                "requested_from must be earlier than or equal to requested_to"
            )
        if type(self.query_as_of) is not datetime:
            raise TypeError("query_as_of must be an exact datetime")
        if self.query_as_of.tzinfo is not UTC:
            raise ValueError("query_as_of must be normalized to UTC")


@runtime_checkable
class PolygonCompletedDailyAcquirer(Protocol):
    """The only provider capability required by this application service."""

    async def get_completed_daily_acquisition(
        self,
        ticker: str,
        start: date,
        end: date,
    ) -> PolygonCompletedDailyAcquisition:
        """Acquire one exact completed-daily Polygon response."""
        ...


class PolygonCompletedDailyEvidenceCandidateApplicationService:
    """Compose mapping preflight, acquisition, clock, and pure ingress."""

    __slots__ = ("_acquirer", "_creation_clock")

    def __init__(
        self,
        acquirer: PolygonCompletedDailyAcquirer,
        creation_clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(acquirer, PolygonCompletedDailyAcquirer):
            raise TypeError("acquirer must implement PolygonCompletedDailyAcquirer")
        if creation_clock is not None and not callable(creation_clock):
            raise TypeError("creation_clock must be callable")
        self._acquirer = acquirer
        self._creation_clock = _utc_now if creation_clock is None else creation_clock

    async def execute(
        self,
        request: PolygonCompletedDailyEvidenceCandidateApplicationRequest,
    ) -> PolygonCompletedDailyOhlcvEvidenceIngressResult:
        """Construct one production-authorized, unvalidated Candidate."""

        if (
            type(request)
            is not PolygonCompletedDailyEvidenceCandidateApplicationRequest
        ):
            raise TypeError(
                "request must be an exact "
                "PolygonCompletedDailyEvidenceCandidateApplicationRequest"
            )
        request._validate()

        resolve_instrument_mapping(
            request.external_identity,
            request.mappings,
            request.query_as_of,
        )
        acquisition = await self._acquirer.get_completed_daily_acquisition(
            ticker=request.external_identity.external_symbol,
            start=request.requested_from,
            end=request.requested_to,
        )
        artifact_created_at = self._creation_clock()
        return create_polygon_completed_daily_ohlcv_evidence(
            acquisition=acquisition,
            external_identity=request.external_identity,
            mappings=request.mappings,
            query_as_of=request.query_as_of,
            artifact_created_at=artifact_created_at,
        )


def _utc_now() -> datetime:
    return datetime.now(UTC)


__all__ = [
    "PolygonCompletedDailyAcquirer",
    "PolygonCompletedDailyEvidenceCandidateApplicationRequest",
    "PolygonCompletedDailyEvidenceCandidateApplicationService",
]
