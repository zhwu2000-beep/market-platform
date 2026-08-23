"""Bounded Agent response projection for Daily Technical Strategy."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from market_platform.application.daily_technical_strategy import (
    DailyTechnicalStrategyApplicationResponse,
)

DAILY_TECHNICAL_STRATEGY_AGENT_RESPONSE_PROJECTION_SCHEMA_VERSION = (
    "daily_technical_strategy_agent_response_projection/v1"
)

_FINGERPRINT_PATTERN = re.compile(r"sha256:[0-9a-f]{64}", re.ASCII)


@dataclass(frozen=True, slots=True, init=False)
class DailyTechnicalStrategyAgentResponseProjection:
    """Immutable descriptive projection of one validated application response."""

    application_request_fingerprint: str
    canonical_instrument_id: str
    requested_symbol: str
    requested_venue: str
    analysis_as_of: datetime
    source_technical_analysis_snapshot_fingerprint: str
    source_daily_instrument_integrity_evidence_fingerprint: str
    interpretation_fingerprint: str
    assessment_fingerprint: str
    strategy_fingerprint: str
    interpretation_policy_id: str
    interpretation_policy_behavioral_revision: str
    interpretation_policy_identity_fingerprint: str
    assessment_policy_id: str
    assessment_policy_behavioral_revision: str
    assessment_policy_identity_fingerprint: str
    strategy_policy_id: str
    strategy_policy_behavioral_revision: str
    strategy_policy_identity_fingerprint: str
    source_quality: str
    source_warnings: tuple[str, ...]
    trend_direction: str
    momentum_direction: str
    volatility_state: str
    extension_state: str
    assessment_outcome: str
    assessment_finding_codes: tuple[str, ...]
    strategy_mode: str
    strategy_rule_code: str
    schema_version: str

    def __init__(self) -> None:
        raise TypeError(
            "DailyTechnicalStrategyAgentResponseProjection is factory-created"
        )

    @classmethod
    def from_application_response(
        cls,
        response: DailyTechnicalStrategyApplicationResponse,
    ) -> DailyTechnicalStrategyAgentResponseProjection:
        """Create a detached bounded projection from an exact valid response."""

        if type(response) is not DailyTechnicalStrategyApplicationResponse:
            raise TypeError(
                "response must be an exact "
                "DailyTechnicalStrategyApplicationResponse"
            )
        response._validate()

        interpretation = response.interpretation
        assessment = response.assessment
        strategy = response.strategy
        projection = object.__new__(cls)
        values: tuple[tuple[str, object], ...] = (
            (
                "application_request_fingerprint",
                response.application_request_fingerprint,
            ),
            (
                "canonical_instrument_id",
                interpretation.canonical_instrument_id.instrument_id,
            ),
            ("requested_symbol", interpretation.requested_trading_identity.symbol),
            ("requested_venue", interpretation.requested_trading_identity.venue),
            ("analysis_as_of", interpretation.analysis_as_of),
            (
                "source_technical_analysis_snapshot_fingerprint",
                interpretation.source_technical_analysis_snapshot_fingerprint,
            ),
            (
                "source_daily_instrument_integrity_evidence_fingerprint",
                interpretation.source_daily_instrument_integrity_evidence_fingerprint,
            ),
            ("interpretation_fingerprint", interpretation.fingerprint),
            ("assessment_fingerprint", assessment.fingerprint),
            ("strategy_fingerprint", strategy.fingerprint),
            (
                "interpretation_policy_id",
                interpretation.interpretation_policy_identity.policy_id,
            ),
            (
                "interpretation_policy_behavioral_revision",
                interpretation.interpretation_policy_identity.behavioral_revision,
            ),
            (
                "interpretation_policy_identity_fingerprint",
                interpretation.interpretation_policy_identity.fingerprint,
            ),
            (
                "assessment_policy_id",
                assessment.assessment_policy_identity.policy_id,
            ),
            (
                "assessment_policy_behavioral_revision",
                assessment.assessment_policy_identity.behavioral_revision,
            ),
            (
                "assessment_policy_identity_fingerprint",
                assessment.assessment_policy_identity.fingerprint,
            ),
            ("strategy_policy_id", strategy.strategy_policy_identity.policy_id),
            (
                "strategy_policy_behavioral_revision",
                strategy.strategy_policy_identity.behavioral_revision,
            ),
            (
                "strategy_policy_identity_fingerprint",
                strategy.strategy_policy_identity.fingerprint,
            ),
            ("source_quality", interpretation.source_quality.value),
            (
                "source_warnings",
                tuple(item.value for item in interpretation.source_warnings),
            ),
            ("trend_direction", interpretation.trend_direction.value),
            ("momentum_direction", interpretation.momentum_direction.value),
            ("volatility_state", interpretation.volatility_state.value),
            ("extension_state", interpretation.extension_state.value),
            ("assessment_outcome", assessment.outcome.value),
            (
                "assessment_finding_codes",
                tuple(item.code for item in assessment.findings),
            ),
            ("strategy_mode", strategy.mode.value),
            ("strategy_rule_code", strategy.rule_code.value),
            (
                "schema_version",
                DAILY_TECHNICAL_STRATEGY_AGENT_RESPONSE_PROJECTION_SCHEMA_VERSION,
            ),
        )
        for name, value in values:
            object.__setattr__(projection, name, value)
        projection._validate()
        return projection

    def _validate(self) -> None:
        try:
            retained = {
                name: object.__getattribute__(self, name)
                for name in self.__dataclass_fields__
            }
        except AttributeError as exc:
            raise ValueError(
                "Agent response projection retained state is incomplete"
            ) from exc

        fingerprint_fields = (
            "application_request_fingerprint",
            "source_technical_analysis_snapshot_fingerprint",
            "source_daily_instrument_integrity_evidence_fingerprint",
            "interpretation_fingerprint",
            "assessment_fingerprint",
            "strategy_fingerprint",
            "interpretation_policy_identity_fingerprint",
            "assessment_policy_identity_fingerprint",
            "strategy_policy_identity_fingerprint",
        )
        if any(
            type(retained[name]) is not str
            or _FINGERPRINT_PATTERN.fullmatch(retained[name]) is None
            for name in fingerprint_fields
        ):
            raise ValueError("Agent response projection fingerprint is invalid")

        text_fields = (
            "canonical_instrument_id",
            "requested_symbol",
            "requested_venue",
            "source_quality",
            "trend_direction",
            "momentum_direction",
            "volatility_state",
            "extension_state",
            "assessment_outcome",
            "strategy_mode",
            "strategy_rule_code",
            "interpretation_policy_id",
            "interpretation_policy_behavioral_revision",
            "assessment_policy_id",
            "assessment_policy_behavioral_revision",
            "strategy_policy_id",
            "strategy_policy_behavioral_revision",
        )
        if any(
            type(retained[name]) is not str
            or not retained[name]
            or retained[name].strip() != retained[name]
            for name in text_fields
        ):
            raise ValueError("Agent response projection text is invalid")

        if (
            type(retained["analysis_as_of"]) is not datetime
            or retained["analysis_as_of"].tzinfo is not UTC
        ):
            raise ValueError("Agent response projection analysis_as_of is invalid")

        for name in ("source_warnings", "assessment_finding_codes"):
            value = retained[name]
            if type(value) is not tuple or any(
                type(item) is not str or not item or item.strip() != item
                for item in value
            ):
                raise ValueError(f"Agent response projection {name} is invalid")

        if retained["schema_version"] != (
            DAILY_TECHNICAL_STRATEGY_AGENT_RESPONSE_PROJECTION_SCHEMA_VERSION
        ):
            raise ValueError("Agent response projection schema is invalid")


__all__ = [
    "DAILY_TECHNICAL_STRATEGY_AGENT_RESPONSE_PROJECTION_SCHEMA_VERSION",
    "DailyTechnicalStrategyAgentResponseProjection",
]
