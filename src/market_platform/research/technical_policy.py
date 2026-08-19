"""Stable identities and typed configuration for daily technical policies."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from enum import StrEnum
from numbers import Real

from market_platform._fingerprint import canonical_fingerprint, canonical_float

TECHNICAL_POLICY_IDENTITY_SCHEMA = "technical_policy_identity/v1"
CLASSIC_DAILY_TECHNICAL_INTERPRETATION_CONFIGURATION_SCHEMA = (
    "classic_daily_technical_interpretation_configuration/v1"
)
CLASSIC_DAILY_TECHNICAL_ASSESSMENT_CONFIGURATION_SCHEMA = (
    "classic_daily_technical_assessment_configuration/v1"
)
CLASSIC_DAILY_TECHNICAL_STRATEGY_CONFIGURATION_SCHEMA = (
    "classic_daily_technical_strategy_configuration/v1"
)

_IDENTIFIER_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,127}", re.ASCII)
_REVISION_PATTERN = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+", re.ASCII)
_SCHEMA_PATTERN = re.compile(r"[a-z][a-z0-9_]*(?:/[a-z0-9._-]+)+", re.ASCII)
_FINGERPRINT_PATTERN = re.compile(r"sha256:[0-9a-f]{64}", re.ASCII)


class TechnicalPolicyKind(StrEnum):
    DAILY_TECHNICAL_INTERPRETATION = "daily_technical_interpretation"
    DAILY_TECHNICAL_ASSESSMENT = "daily_technical_assessment"
    DAILY_TECHNICAL_STRATEGY = "daily_technical_strategy"


def _number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return 0.0 if result == 0.0 else result


def _canonical_retained_float(value: object, name: str) -> float:
    if (
        type(value) is not float
        or not math.isfinite(value)
        or (value == 0.0 and math.copysign(1.0, value) < 0.0)
    ):
        raise ValueError(f"retained {name} must be a canonical finite float")
    return value


@dataclass(frozen=True, slots=True)
class ClassicDailyTechnicalInterpretationConfiguration:
    rsi_neutral: float = 50.0
    rsi_elevated: float = 70.0
    rsi_depressed: float = 30.0
    realized_volatility_low: float = 0.15
    realized_volatility_high: float = 0.30
    ema20_extension_band_percent: float = 5.0

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            object.__setattr__(self, name, _number(getattr(self, name), name))
        self._validate()

    def _validate(self) -> None:
        for name in self.__dataclass_fields__:
            _canonical_retained_float(getattr(self, name), name)
        if not (
            0.0 <= self.rsi_depressed < self.rsi_neutral < self.rsi_elevated <= 100.0
        ):
            raise ValueError("RSI thresholds must be strictly ordered within 0..100")
        if not (0.0 <= self.realized_volatility_low < self.realized_volatility_high):
            raise ValueError("volatility thresholds must be nonnegative and ordered")
        if self.ema20_extension_band_percent <= 0.0:
            raise ValueError("EMA20 extension band must be positive")

    def to_dict(self, *, fingerprint_floats: bool = False) -> dict[str, object]:
        self._validate()
        return {
            name: canonical_float(getattr(self, name))
            if fingerprint_floats
            else getattr(self, name)
            for name in self.__dataclass_fields__
        }


@dataclass(frozen=True, slots=True)
class ClassicDailyTechnicalAssessmentConfiguration:
    def _validate(self) -> None:
        if self.to_dict():
            raise ValueError("assessment configuration must remain empty")

    def to_dict(self, *, fingerprint_floats: bool = False) -> dict[str, object]:
        del fingerprint_floats
        return {}


@dataclass(frozen=True, slots=True)
class ClassicDailyTechnicalStrategyConfiguration:
    def _validate(self) -> None:
        if self.to_dict():
            raise ValueError("strategy configuration must remain empty")

    def to_dict(self, *, fingerprint_floats: bool = False) -> dict[str, object]:
        del fingerprint_floats
        return {}


type TechnicalPolicyConfiguration = (
    ClassicDailyTechnicalInterpretationConfiguration
    | ClassicDailyTechnicalAssessmentConfiguration
    | ClassicDailyTechnicalStrategyConfiguration
)


def _copy_configuration(value: object) -> TechnicalPolicyConfiguration:
    if type(value) is ClassicDailyTechnicalInterpretationConfiguration:
        value._validate()
        return ClassicDailyTechnicalInterpretationConfiguration(
            rsi_neutral=value.rsi_neutral,
            rsi_elevated=value.rsi_elevated,
            rsi_depressed=value.rsi_depressed,
            realized_volatility_low=value.realized_volatility_low,
            realized_volatility_high=value.realized_volatility_high,
            ema20_extension_band_percent=value.ema20_extension_band_percent,
        )
    if type(value) is ClassicDailyTechnicalAssessmentConfiguration:
        value._validate()
        return ClassicDailyTechnicalAssessmentConfiguration()
    if type(value) is ClassicDailyTechnicalStrategyConfiguration:
        value._validate()
        return ClassicDailyTechnicalStrategyConfiguration()
    raise TypeError("configuration must be an exact supported typed configuration")


@dataclass(frozen=True, slots=True)
class TechnicalPolicyIdentity:
    policy_kind: TechnicalPolicyKind
    policy_id: str
    behavioral_revision: str
    configuration_schema: str
    configuration: TechnicalPolicyConfiguration
    schema_version: str = field(init=False, default=TECHNICAL_POLICY_IDENTITY_SCHEMA)
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        configuration = _copy_configuration(self.configuration)
        object.__setattr__(self, "configuration", configuration)
        object.__setattr__(
            self, "fingerprint", canonical_fingerprint(self._fingerprint_payload())
        )
        self._validate()

    def _projection(self, *, fingerprint_floats: bool) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "policy_kind": self.policy_kind.value,
            "policy_id": self.policy_id,
            "behavioral_revision": self.behavioral_revision,
            "configuration_schema": self.configuration_schema,
            "configuration": self.configuration.to_dict(
                fingerprint_floats=fingerprint_floats
            ),
        }

    def _fingerprint_payload(self) -> dict[str, object]:
        return self._projection(fingerprint_floats=True)

    def _validate(self) -> None:
        try:
            retained = {
                name: object.__getattribute__(self, name)
                for name in (
                    "policy_kind",
                    "policy_id",
                    "behavioral_revision",
                    "configuration_schema",
                    "configuration",
                    "schema_version",
                    "fingerprint",
                )
            }
        except AttributeError as exc:
            raise ValueError("policy identity retained state is incomplete") from exc
        if type(retained["policy_kind"]) is not TechnicalPolicyKind:
            raise ValueError("policy kind is invalid")
        if (
            type(retained["policy_id"]) is not str
            or _IDENTIFIER_PATTERN.fullmatch(retained["policy_id"]) is None
        ):
            raise ValueError("policy ID is invalid")
        if (
            type(retained["behavioral_revision"]) is not str
            or _REVISION_PATTERN.fullmatch(retained["behavioral_revision"]) is None
        ):
            raise ValueError("behavioral revision is invalid")
        if (
            type(retained["configuration_schema"]) is not str
            or _SCHEMA_PATTERN.fullmatch(retained["configuration_schema"]) is None
        ):
            raise ValueError("configuration schema is invalid")
        configuration = _copy_configuration(retained["configuration"])
        if configuration.to_dict() != self.configuration.to_dict():
            raise ValueError("policy configuration retained state is noncanonical")
        expected_type, expected_schema = {
            TechnicalPolicyKind.DAILY_TECHNICAL_INTERPRETATION: (
                ClassicDailyTechnicalInterpretationConfiguration,
                CLASSIC_DAILY_TECHNICAL_INTERPRETATION_CONFIGURATION_SCHEMA,
            ),
            TechnicalPolicyKind.DAILY_TECHNICAL_ASSESSMENT: (
                ClassicDailyTechnicalAssessmentConfiguration,
                CLASSIC_DAILY_TECHNICAL_ASSESSMENT_CONFIGURATION_SCHEMA,
            ),
            TechnicalPolicyKind.DAILY_TECHNICAL_STRATEGY: (
                ClassicDailyTechnicalStrategyConfiguration,
                CLASSIC_DAILY_TECHNICAL_STRATEGY_CONFIGURATION_SCHEMA,
            ),
        }[retained["policy_kind"]]
        if type(configuration) is not expected_type:
            raise ValueError("policy kind and configuration type do not correspond")
        if retained["configuration_schema"] != expected_schema:
            raise ValueError(
                "policy kind, configuration type, and configuration schema "
                "do not correspond"
            )
        if retained["schema_version"] != TECHNICAL_POLICY_IDENTITY_SCHEMA:
            raise ValueError("policy identity schema is invalid")
        if (
            type(retained["fingerprint"]) is not str
            or _FINGERPRINT_PATTERN.fullmatch(retained["fingerprint"]) is None
            or retained["fingerprint"]
            != canonical_fingerprint(self._fingerprint_payload())
        ):
            raise ValueError("policy identity fingerprint does not match content")

    def to_dict(self) -> dict[str, object]:
        self._validate()
        return {
            **self._projection(fingerprint_floats=False),
            "fingerprint": self.fingerprint,
        }


def copy_technical_policy_identity(value: object) -> TechnicalPolicyIdentity:
    """Reconstruct a detached canonical value from retained identity state."""

    if type(value) is not TechnicalPolicyIdentity:
        raise ValueError("policy identity must be an exact TechnicalPolicyIdentity")
    value._validate()
    return TechnicalPolicyIdentity(
        policy_kind=value.policy_kind,
        policy_id=value.policy_id,
        behavioral_revision=value.behavioral_revision,
        configuration_schema=value.configuration_schema,
        configuration=value.configuration,
    )


__all__ = [
    "TECHNICAL_POLICY_IDENTITY_SCHEMA",
    "CLASSIC_DAILY_TECHNICAL_INTERPRETATION_CONFIGURATION_SCHEMA",
    "CLASSIC_DAILY_TECHNICAL_ASSESSMENT_CONFIGURATION_SCHEMA",
    "CLASSIC_DAILY_TECHNICAL_STRATEGY_CONFIGURATION_SCHEMA",
    "TechnicalPolicyKind",
    "TechnicalPolicyIdentity",
    "ClassicDailyTechnicalInterpretationConfiguration",
    "ClassicDailyTechnicalAssessmentConfiguration",
    "ClassicDailyTechnicalStrategyConfiguration",
]
