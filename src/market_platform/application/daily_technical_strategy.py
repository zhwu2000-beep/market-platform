"""Transport-neutral contracts for the daily technical Strategy application."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from market_platform._fingerprint import canonical_fingerprint
from market_platform.research.daily_instrument_integrity import (
    IntegrityCheckedDailyTechnicalResearchResult,
)
from market_platform.research.daily_technical_assessment import DailyTechnicalAssessment
from market_platform.research.daily_technical_interpretation import (
    DailyTechnicalInterpretation,
)
from market_platform.research.daily_technical_strategy import DailyTechnicalStrategy

DAILY_TECHNICAL_STRATEGY_APPLICATION_REQUEST_SCHEMA_VERSION = (
    "daily_technical_strategy_application_request/v1"
)
DAILY_TECHNICAL_STRATEGY_APPLICATION_RESPONSE_SCHEMA_VERSION = (
    "daily_technical_strategy_application_response/v1"
)
_FINGERPRINT_PATTERN = re.compile(r"sha256:[0-9a-f]{64}", re.ASCII)


@dataclass(frozen=True, slots=True)
class DailyTechnicalStrategyApplicationRequest:
    """Verified research input for the fixed daily technical Strategy profile."""

    verified_research: IntegrityCheckedDailyTechnicalResearchResult = field(repr=False)
    schema_version: str = field(
        init=False,
        default=DAILY_TECHNICAL_STRATEGY_APPLICATION_REQUEST_SCHEMA_VERSION,
    )
    request_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        _validate_verified_research(self.verified_research)
        object.__setattr__(
            self,
            "request_fingerprint",
            canonical_fingerprint(self._fingerprint_payload()),
        )
        self._validate()

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "schema_version": (
                DAILY_TECHNICAL_STRATEGY_APPLICATION_REQUEST_SCHEMA_VERSION
            ),
            "verified_research": self.verified_research.to_dict(),
        }

    def _validate(self) -> None:
        try:
            verified_research = object.__getattribute__(self, "verified_research")
            schema_version = object.__getattribute__(self, "schema_version")
            request_fingerprint = object.__getattribute__(
                self, "request_fingerprint"
            )
        except AttributeError as exc:
            raise ValueError(
                "application request retained state is incomplete"
            ) from exc
        _validate_verified_research(verified_research)
        if (
            schema_version
            != DAILY_TECHNICAL_STRATEGY_APPLICATION_REQUEST_SCHEMA_VERSION
        ):
            raise ValueError("application request schema is invalid")
        if (
            type(request_fingerprint) is not str
            or request_fingerprint
            != canonical_fingerprint(self._fingerprint_payload())
        ):
            raise ValueError(
                "application request fingerprint does not match canonical content"
            )


@dataclass(frozen=True, slots=True, init=False)
class DailyTechnicalStrategyApplicationResponse:
    """Factory-only success response retaining the complete domain chain."""

    application_request_fingerprint: str
    interpretation: DailyTechnicalInterpretation = field(repr=False)
    assessment: DailyTechnicalAssessment = field(repr=False)
    strategy: DailyTechnicalStrategy = field(repr=False)
    schema_version: str

    def __init__(self) -> None:
        raise TypeError(
            "DailyTechnicalStrategyApplicationResponse is factory-created"
        )

    @classmethod
    def _create(
        cls,
        request: DailyTechnicalStrategyApplicationRequest,
        interpretation: DailyTechnicalInterpretation,
        assessment: DailyTechnicalAssessment,
        strategy: DailyTechnicalStrategy,
    ) -> DailyTechnicalStrategyApplicationResponse:
        if type(request) is not DailyTechnicalStrategyApplicationRequest:
            raise TypeError(
                "request must be an exact DailyTechnicalStrategyApplicationRequest"
            )
        request._validate()
        _validate_application_correspondence(
            request.verified_research,
            interpretation,
            assessment,
            strategy,
        )
        response = object.__new__(cls)
        object.__setattr__(
            response,
            "application_request_fingerprint",
            request.request_fingerprint,
        )
        object.__setattr__(response, "interpretation", interpretation)
        object.__setattr__(response, "assessment", assessment)
        object.__setattr__(response, "strategy", strategy)
        object.__setattr__(
            response,
            "schema_version",
            DAILY_TECHNICAL_STRATEGY_APPLICATION_RESPONSE_SCHEMA_VERSION,
        )
        response._validate()
        return response

    def _validate(self) -> None:
        try:
            application_request_fingerprint = object.__getattribute__(
                self, "application_request_fingerprint"
            )
            interpretation = object.__getattribute__(self, "interpretation")
            assessment = object.__getattribute__(self, "assessment")
            strategy = object.__getattribute__(self, "strategy")
            schema_version = object.__getattribute__(self, "schema_version")
        except AttributeError as exc:
            raise ValueError(
                "application response retained state is incomplete"
            ) from exc
        if (
            type(application_request_fingerprint) is not str
            or _FINGERPRINT_PATTERN.fullmatch(application_request_fingerprint) is None
        ):
            raise ValueError("application request fingerprint is invalid")
        if (
            schema_version
            != DAILY_TECHNICAL_STRATEGY_APPLICATION_RESPONSE_SCHEMA_VERSION
        ):
            raise ValueError("application response schema is invalid")
        _validate_completed_domain_chain(interpretation, assessment, strategy)


def _validate_verified_research(value: object) -> None:
    if type(value) is not IntegrityCheckedDailyTechnicalResearchResult:
        raise TypeError("verified_research must be an exact integrity-checked result")
    value._validate()
    value.to_dict()


def _validate_application_correspondence(
    verified_research: IntegrityCheckedDailyTechnicalResearchResult,
    interpretation: DailyTechnicalInterpretation,
    assessment: DailyTechnicalAssessment,
    strategy: DailyTechnicalStrategy,
) -> None:
    _validate_verified_research(verified_research)
    _validate_completed_domain_chain(interpretation, assessment, strategy)
    research = verified_research.research
    integrity = verified_research.integrity
    if (
        interpretation.canonical_instrument_id.to_dict()
        != integrity.canonical_instrument_id.to_dict()
        or interpretation.requested_trading_identity.to_dict()
        != integrity.requested_trading_identity.to_dict()
        or interpretation.analysis_as_of != research.request.analysis_as_of
        or interpretation.source_technical_analysis_snapshot_fingerprint
        != research.snapshot.fingerprint
        or interpretation.source_daily_instrument_integrity_evidence_fingerprint
        != integrity.fingerprint
        or interpretation.source_quality is not research.snapshot.quality
        or interpretation.source_warnings != research.snapshot.warnings
    ):
        raise ValueError("interpretation does not correspond to verified research")


def _validate_completed_domain_chain(
    interpretation: object,
    assessment: object,
    strategy: object,
) -> None:
    if type(interpretation) is not DailyTechnicalInterpretation:
        raise TypeError("interpretation must be an exact DailyTechnicalInterpretation")
    if type(assessment) is not DailyTechnicalAssessment:
        raise TypeError("assessment must be an exact DailyTechnicalAssessment")
    if type(strategy) is not DailyTechnicalStrategy:
        raise TypeError("strategy must be an exact DailyTechnicalStrategy")
    interpretation._validate()
    assessment._validate()
    strategy._validate()
    if (
        assessment.canonical_instrument_id.to_dict()
        != interpretation.canonical_instrument_id.to_dict()
        or assessment.analysis_as_of != interpretation.analysis_as_of
        or assessment.source_interpretation_fingerprint
        != interpretation.fingerprint
    ):
        raise ValueError("assessment does not correspond to interpretation")
    assessment._validate_references(interpretation)
    if (
        strategy.canonical_instrument_id.to_dict()
        != interpretation.canonical_instrument_id.to_dict()
        or strategy.canonical_instrument_id.to_dict()
        != assessment.canonical_instrument_id.to_dict()
        or strategy.analysis_as_of != interpretation.analysis_as_of
        or strategy.analysis_as_of != assessment.analysis_as_of
        or strategy.source_assessment_fingerprint != assessment.fingerprint
    ):
        raise ValueError(
            "strategy does not correspond to interpretation and assessment"
        )


__all__ = [
    "DAILY_TECHNICAL_STRATEGY_APPLICATION_REQUEST_SCHEMA_VERSION",
    "DAILY_TECHNICAL_STRATEGY_APPLICATION_RESPONSE_SCHEMA_VERSION",
    "DailyTechnicalStrategyApplicationRequest",
    "DailyTechnicalStrategyApplicationResponse",
]
