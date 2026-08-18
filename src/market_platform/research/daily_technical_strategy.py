"""Immutable strategy vocabulary for daily technical assessments."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from market_platform._fingerprint import canonical_fingerprint
from market_platform.instruments.identity import CanonicalInstrumentId
from market_platform.research.technical_policy import (
    TechnicalPolicyIdentity,
    TechnicalPolicyKind,
    copy_technical_policy_identity,
)

DAILY_TECHNICAL_STRATEGY_SCHEMA = "daily_technical_strategy/v1"
_FINGERPRINT_PATTERN = re.compile(r"sha256:[0-9a-f]{64}", re.ASCII)


class DailyTechnicalStrategyMode(StrEnum):
    POSITIVE_DIRECTIONAL_CONTINUATION = "positive_directional_continuation"
    NEGATIVE_DIRECTIONAL_CONTINUATION = "negative_directional_continuation"
    NO_ACTIVE_STRATEGY = "no_active_strategy"


class DailyTechnicalStrategyRuleCode(StrEnum):
    ALIGNED_POSITIVE_CONTINUATION = "aligned_positive_continuation"
    ALIGNED_NEGATIVE_CONTINUATION = "aligned_negative_continuation"
    CAUTION_NO_ACTIVE_STRATEGY = "caution_no_active_strategy"
    MIXED_NO_ACTIVE_STRATEGY = "mixed_no_active_strategy"
    INSUFFICIENT_DATA_NO_ACTIVE_STRATEGY = "insufficient_data_no_active_strategy"


_ALLOWED_MODE_RULE_PAIRS = frozenset(
    {
        (
            DailyTechnicalStrategyMode.POSITIVE_DIRECTIONAL_CONTINUATION,
            DailyTechnicalStrategyRuleCode.ALIGNED_POSITIVE_CONTINUATION,
        ),
        (
            DailyTechnicalStrategyMode.NEGATIVE_DIRECTIONAL_CONTINUATION,
            DailyTechnicalStrategyRuleCode.ALIGNED_NEGATIVE_CONTINUATION,
        ),
        (
            DailyTechnicalStrategyMode.NO_ACTIVE_STRATEGY,
            DailyTechnicalStrategyRuleCode.CAUTION_NO_ACTIVE_STRATEGY,
        ),
        (
            DailyTechnicalStrategyMode.NO_ACTIVE_STRATEGY,
            DailyTechnicalStrategyRuleCode.MIXED_NO_ACTIVE_STRATEGY,
        ),
        (
            DailyTechnicalStrategyMode.NO_ACTIVE_STRATEGY,
            DailyTechnicalStrategyRuleCode.INSUFFICIENT_DATA_NO_ACTIVE_STRATEGY,
        ),
    }
)


def _copy_canonical_instrument_id(value: object) -> CanonicalInstrumentId:
    if type(value) is not CanonicalInstrumentId:
        raise ValueError("strategy canonical instrument ID is invalid")
    try:
        reconstructed = CanonicalInstrumentId(value.instrument_id)
        retained = value.to_dict()
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("strategy canonical instrument ID is invalid") from exc
    if retained != reconstructed.to_dict():
        raise ValueError("strategy canonical instrument ID is noncanonical")
    return reconstructed


@dataclass(frozen=True, slots=True)
class DailyTechnicalStrategy:
    canonical_instrument_id: CanonicalInstrumentId
    analysis_as_of: datetime
    source_assessment_fingerprint: str
    strategy_policy_identity: TechnicalPolicyIdentity
    mode: DailyTechnicalStrategyMode
    rule_code: DailyTechnicalStrategyRuleCode
    schema_version: str = field(init=False, default=DAILY_TECHNICAL_STRATEGY_SCHEMA)
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "canonical_instrument_id",
            _copy_canonical_instrument_id(self.canonical_instrument_id),
        )
        object.__setattr__(
            self,
            "strategy_policy_identity",
            copy_technical_policy_identity(self.strategy_policy_identity),
        )
        if type(self.mode) is not DailyTechnicalStrategyMode:
            raise ValueError("strategy mode is invalid")
        if type(self.rule_code) is not DailyTechnicalStrategyRuleCode:
            raise ValueError("strategy rule code is invalid")
        object.__setattr__(
            self, "fingerprint", canonical_fingerprint(self._fingerprint_payload())
        )
        self._validate()

    def _projection(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "canonical_instrument_id": self.canonical_instrument_id.to_dict(),
            "analysis_as_of": self.analysis_as_of.isoformat(),
            "source_assessment_fingerprint": self.source_assessment_fingerprint,
            "strategy_policy_identity": self.strategy_policy_identity.to_dict(),
            "mode": self.mode.value,
            "rule_code": self.rule_code.value,
        }

    def _fingerprint_payload(self) -> dict[str, object]:
        return self._projection()

    def _validate(self) -> None:
        try:
            values = {
                name: object.__getattribute__(self, name)
                for name in (
                    "canonical_instrument_id",
                    "analysis_as_of",
                    "source_assessment_fingerprint",
                    "strategy_policy_identity",
                    "mode",
                    "rule_code",
                    "schema_version",
                    "fingerprint",
                )
            }
        except AttributeError as exc:
            raise ValueError("strategy retained state is incomplete") from exc
        _copy_canonical_instrument_id(values["canonical_instrument_id"])
        if (
            type(values["analysis_as_of"]) is not datetime
            or values["analysis_as_of"].tzinfo is not UTC
        ):
            raise ValueError("strategy analysis_as_of must be canonical UTC")
        for name in ("source_assessment_fingerprint", "fingerprint"):
            if (
                type(values[name]) is not str
                or _FINGERPRINT_PATTERN.fullmatch(values[name]) is None
            ):
                raise ValueError(f"strategy {name} is invalid")
        if type(values["strategy_policy_identity"]) is not TechnicalPolicyIdentity:
            raise ValueError("strategy policy identity is invalid")
        self.strategy_policy_identity._validate()
        if (
            self.strategy_policy_identity.policy_kind
            is not TechnicalPolicyKind.DAILY_TECHNICAL_STRATEGY
        ):
            raise ValueError("strategy policy kind is invalid")
        if type(values["mode"]) is not DailyTechnicalStrategyMode:
            raise ValueError("strategy mode is invalid")
        if type(values["rule_code"]) is not DailyTechnicalStrategyRuleCode:
            raise ValueError("strategy rule code is invalid")
        if (self.mode, self.rule_code) not in _ALLOWED_MODE_RULE_PAIRS:
            raise ValueError("strategy mode and rule code do not correspond")
        if values["schema_version"] != DAILY_TECHNICAL_STRATEGY_SCHEMA:
            raise ValueError("strategy schema is invalid")
        if self.fingerprint != canonical_fingerprint(self._fingerprint_payload()):
            raise ValueError("strategy fingerprint does not match content")

    def to_dict(self) -> dict[str, object]:
        self._validate()
        return {**self._projection(), "fingerprint": self.fingerprint}


__all__ = [
    "DAILY_TECHNICAL_STRATEGY_SCHEMA",
    "DailyTechnicalStrategy",
    "DailyTechnicalStrategyMode",
    "DailyTechnicalStrategyRuleCode",
]
