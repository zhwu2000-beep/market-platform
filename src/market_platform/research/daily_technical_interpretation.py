"""Policy boundary and immutable result for daily technical interpretation."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from market_platform._fingerprint import canonical_fingerprint, canonical_float
from market_platform.instruments.identity import CanonicalInstrumentId
from market_platform.research.daily_instrument_integrity import (
    IntegrityCheckedDailyTechnicalResearchResult,
)
from market_platform.research.interpretation import VolatilityState
from market_platform.research.technical_analysis import (
    TechnicalAnalysisQuality,
    TechnicalAnalysisSnapshot,
    TechnicalAnalysisWarning,
)
from market_platform.research.technical_policy import (
    ClassicDailyTechnicalInterpretationConfiguration,
    TechnicalPolicyIdentity,
    TechnicalPolicyKind,
    copy_technical_policy_identity,
)
from market_platform.trading.instrument import TradingInstrumentIdentity

DAILY_TECHNICAL_INTERPRETATION_SCHEMA = "daily_technical_interpretation/v1"
_FINGERPRINT_PATTERN = re.compile(r"sha256:[0-9a-f]{64}", re.ASCII)


class DailyTechnicalDirectionalState(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    MIXED = "mixed"
    UNAVAILABLE = "unavailable"


class DailyTechnicalExtensionState(StrEnum):
    ABOVE_REFERENCE_BAND = "above_reference_band"
    WITHIN_REFERENCE_BAND = "within_reference_band"
    BELOW_REFERENCE_BAND = "below_reference_band"
    UNAVAILABLE = "unavailable"


class TechnicalComparisonOperandSource(StrEnum):
    TECHNICAL_ANALYSIS_SNAPSHOT = "technical_analysis_snapshot"
    INTERPRETATION_POLICY_CONFIGURATION = "interpretation_policy_configuration"
    INTERPRETATION_POLICY_DERIVED = "interpretation_policy_derived"


class TechnicalComparisonOperator(StrEnum):
    GREATER_THAN = "greater_than"
    GREATER_THAN_OR_EQUAL = "greater_than_or_equal"
    LESS_THAN = "less_than"
    LESS_THAN_OR_EQUAL = "less_than_or_equal"


_OPERAND_FIELDS = {
    TechnicalComparisonOperandSource.TECHNICAL_ANALYSIS_SNAPSHOT: frozenset(
        {
            "ema_8",
            "ema_20",
            "ema_144",
            "ema_169",
            "latest_close",
            "macd_line",
            "macd_signal",
            "rsi_14",
            "realized_volatility",
            "volatility_references.distance_from_ema20_percent",
        }
    ),
    TechnicalComparisonOperandSource.INTERPRETATION_POLICY_CONFIGURATION: frozenset(
        {
            "rsi_neutral",
            "rsi_elevated",
            "rsi_depressed",
            "realized_volatility_low",
            "realized_volatility_high",
            "ema20_extension_band_percent",
        }
    ),
    TechnicalComparisonOperandSource.INTERPRETATION_POLICY_DERIVED: frozenset(
        {"negative_ema20_extension_band_percent"}
    ),
}


def _canonical_number(value: object, name: str) -> float:
    if type(value) is not float or not math.isfinite(value):
        raise TypeError(f"{name} must be an exact finite float")
    if value == 0.0 and math.copysign(1.0, value) < 0.0:
        raise ValueError(f"{name} must not retain negative zero")
    return value


@dataclass(frozen=True, slots=True)
class TechnicalComparisonOperand:
    source: TechnicalComparisonOperandSource
    field: str
    value: float

    def __post_init__(self) -> None:
        self._validate()

    def _validate(self) -> None:
        if type(self.source) is not TechnicalComparisonOperandSource:
            raise TypeError("operand source is invalid")
        if (
            type(self.field) is not str
            or self.field not in _OPERAND_FIELDS[self.source]
        ):
            raise ValueError("operand field is not permitted for its source")
        _canonical_number(self.value, "operand value")

    def to_dict(self, *, fingerprint_floats: bool = False) -> dict[str, object]:
        self._validate()
        return {
            "source": self.source.value,
            "field": self.field,
            "value": canonical_float(self.value) if fingerprint_floats else self.value,
        }


def _compare(left: float, operator: TechnicalComparisonOperator, right: float) -> bool:
    if operator is TechnicalComparisonOperator.GREATER_THAN:
        return left > right
    if operator is TechnicalComparisonOperator.GREATER_THAN_OR_EQUAL:
        return left >= right
    if operator is TechnicalComparisonOperator.LESS_THAN:
        return left < right
    return left <= right


@dataclass(frozen=True, slots=True)
class TechnicalComparisonEvidence:
    evidence_id: str
    left_operand: TechnicalComparisonOperand
    operator: TechnicalComparisonOperator
    right_operand: TechnicalComparisonOperand
    satisfied: bool

    def __post_init__(self) -> None:
        self._validate()

    def _validate(self) -> None:
        if (
            type(self.evidence_id) is not str
            or not self.evidence_id
            or len(self.evidence_id) > 128
            or not self.evidence_id.replace("_", "a").isalnum()
        ):
            raise ValueError("evidence ID is invalid")
        if type(self.left_operand) is not TechnicalComparisonOperand:
            raise TypeError("left operand is invalid")
        if type(self.right_operand) is not TechnicalComparisonOperand:
            raise TypeError("right operand is invalid")
        self.left_operand._validate()
        self.right_operand._validate()
        if type(self.operator) is not TechnicalComparisonOperator:
            raise TypeError("comparison operator is invalid")
        if type(self.satisfied) is not bool:
            raise TypeError("comparison satisfied must be an exact bool")
        if self.satisfied is not _compare(
            self.left_operand.value, self.operator, self.right_operand.value
        ):
            raise ValueError("comparison satisfied does not match its operands")

    def to_dict(self, *, fingerprint_floats: bool = False) -> dict[str, object]:
        self._validate()
        return {
            "evidence_id": self.evidence_id,
            "left_operand": self.left_operand.to_dict(
                fingerprint_floats=fingerprint_floats
            ),
            "operator": self.operator.value,
            "right_operand": self.right_operand.to_dict(
                fingerprint_floats=fingerprint_floats
            ),
            "satisfied": self.satisfied,
        }


@dataclass(frozen=True, slots=True)
class DailyTechnicalInterpretation:
    canonical_instrument_id: CanonicalInstrumentId
    requested_trading_identity: TradingInstrumentIdentity
    analysis_as_of: datetime
    source_technical_analysis_snapshot_fingerprint: str
    source_daily_instrument_integrity_evidence_fingerprint: str
    interpretation_policy_identity: TechnicalPolicyIdentity
    source_quality: TechnicalAnalysisQuality
    source_warnings: tuple[TechnicalAnalysisWarning, ...]
    trend_direction: DailyTechnicalDirectionalState
    momentum_direction: DailyTechnicalDirectionalState
    volatility_state: VolatilityState
    extension_state: DailyTechnicalExtensionState
    comparison_evidence: tuple[TechnicalComparisonEvidence, ...]
    schema_version: str = field(
        init=False, default=DAILY_TECHNICAL_INTERPRETATION_SCHEMA
    )
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "interpretation_policy_identity",
            copy_technical_policy_identity(self.interpretation_policy_identity),
        )
        object.__setattr__(
            self, "fingerprint", canonical_fingerprint(self._fingerprint_payload())
        )
        self._validate()

    def _projection(self, *, fingerprint_floats: bool) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "canonical_instrument_id": self.canonical_instrument_id.to_dict(),
            "requested_trading_identity": self.requested_trading_identity.to_dict(),
            "analysis_as_of": self.analysis_as_of.isoformat(),
            "source_technical_analysis_snapshot_fingerprint": (
                self.source_technical_analysis_snapshot_fingerprint
            ),
            "source_daily_instrument_integrity_evidence_fingerprint": (
                self.source_daily_instrument_integrity_evidence_fingerprint
            ),
            "interpretation_policy_identity": (
                self.interpretation_policy_identity.to_dict()
            ),
            "source_quality": self.source_quality.value,
            "source_warnings": [item.value for item in self.source_warnings],
            "trend_direction": self.trend_direction.value,
            "momentum_direction": self.momentum_direction.value,
            "volatility_state": self.volatility_state.value,
            "extension_state": self.extension_state.value,
            "comparison_evidence": [
                item.to_dict(fingerprint_floats=fingerprint_floats)
                for item in self.comparison_evidence
            ],
        }

    def _fingerprint_payload(self) -> dict[str, object]:
        return self._projection(fingerprint_floats=True)

    def _validate(self) -> None:
        try:
            values = {
                name: object.__getattribute__(self, name)
                for name in (
                    "canonical_instrument_id",
                    "requested_trading_identity",
                    "analysis_as_of",
                    "source_technical_analysis_snapshot_fingerprint",
                    "source_daily_instrument_integrity_evidence_fingerprint",
                    "interpretation_policy_identity",
                    "source_quality",
                    "source_warnings",
                    "trend_direction",
                    "momentum_direction",
                    "volatility_state",
                    "extension_state",
                    "comparison_evidence",
                    "schema_version",
                    "fingerprint",
                )
            }
        except AttributeError as exc:
            raise ValueError("interpretation retained state is incomplete") from exc
        if type(values["canonical_instrument_id"]) is not CanonicalInstrumentId:
            raise ValueError("canonical instrument ID is invalid")
        fixed_id = CanonicalInstrumentId(self.canonical_instrument_id.instrument_id)
        if fixed_id.to_dict() != self.canonical_instrument_id.to_dict():
            raise ValueError("canonical instrument ID is noncanonical")
        if type(values["requested_trading_identity"]) is not TradingInstrumentIdentity:
            raise ValueError("requested trading identity is invalid")
        fixed_trading = TradingInstrumentIdentity(
            self.requested_trading_identity.symbol,
            self.requested_trading_identity.venue,
        )
        if fixed_trading.to_dict() != self.requested_trading_identity.to_dict():
            raise ValueError("requested trading identity is noncanonical")
        if (
            type(values["analysis_as_of"]) is not datetime
            or self.analysis_as_of.tzinfo is not UTC
        ):
            raise ValueError("analysis_as_of must be canonical UTC")
        for name in (
            "source_technical_analysis_snapshot_fingerprint",
            "source_daily_instrument_integrity_evidence_fingerprint",
            "fingerprint",
        ):
            if (
                type(values[name]) is not str
                or _FINGERPRINT_PATTERN.fullmatch(values[name]) is None
            ):
                raise ValueError(f"{name} is invalid")
        if (
            type(values["interpretation_policy_identity"])
            is not TechnicalPolicyIdentity
        ):
            raise ValueError("interpretation policy identity is invalid")
        self.interpretation_policy_identity._validate()
        if (
            self.interpretation_policy_identity.policy_kind
            is not TechnicalPolicyKind.DAILY_TECHNICAL_INTERPRETATION
        ):
            raise ValueError("interpretation policy kind is invalid")
        enum_types = {
            "source_quality": TechnicalAnalysisQuality,
            "trend_direction": DailyTechnicalDirectionalState,
            "momentum_direction": DailyTechnicalDirectionalState,
            "volatility_state": VolatilityState,
            "extension_state": DailyTechnicalExtensionState,
        }
        if any(type(values[name]) is not kind for name, kind in enum_types.items()):
            raise ValueError("interpretation state is invalid")
        if type(values["source_warnings"]) is not tuple or any(
            type(item) is not TechnicalAnalysisWarning for item in self.source_warnings
        ):
            raise ValueError("source warnings are invalid")
        if len(set(self.source_warnings)) != len(self.source_warnings):
            raise ValueError("source warnings must be unique")
        if type(values["comparison_evidence"]) is not tuple:
            raise ValueError("comparison evidence must be a tuple")
        for item in self.comparison_evidence:
            if type(item) is not TechnicalComparisonEvidence:
                raise ValueError("comparison evidence entry is invalid")
            item._validate()
        ids = tuple(item.evidence_id for item in self.comparison_evidence)
        if len(set(ids)) != len(ids):
            raise ValueError("comparison evidence IDs must be unique")
        if self.schema_version != DAILY_TECHNICAL_INTERPRETATION_SCHEMA:
            raise ValueError("interpretation schema is invalid")
        if self.fingerprint != canonical_fingerprint(self._fingerprint_payload()):
            raise ValueError("interpretation fingerprint does not match content")

    def to_dict(self) -> dict[str, object]:
        self._validate()
        return {
            **self._projection(fingerprint_floats=False),
            "fingerprint": self.fingerprint,
        }


@runtime_checkable
class DailyTechnicalInterpretationPolicy(Protocol):
    @property
    def identity(self) -> TechnicalPolicyIdentity: ...

    def interpret(
        self, verified_research: IntegrityCheckedDailyTechnicalResearchResult
    ) -> DailyTechnicalInterpretation: ...


@dataclass(frozen=True, slots=True)
class _DetachedVolatilityReferences:
    distance_from_ema20_percent: float | None


@dataclass(frozen=True, slots=True)
class _DetachedVerifiedResearchSemantics:
    canonical_instrument_id: tuple[tuple[str, object], ...]
    requested_trading_identity: tuple[tuple[str, object], ...]
    analysis_as_of: datetime
    snapshot_fingerprint: str
    integrity_fingerprint: str
    source_quality: TechnicalAnalysisQuality
    source_warnings: tuple[TechnicalAnalysisWarning, ...]
    latest_close: float
    ema_8: float | None
    ema_20: float | None
    ema_144: float | None
    ema_169: float | None
    macd_line: float | None
    macd_signal: float | None
    rsi_14: float | None
    realized_volatility: float | None
    volatility_references: _DetachedVolatilityReferences
    complete_source_projection: str


def _detach_verified_research_semantics(
    verified_research: IntegrityCheckedDailyTechnicalResearchResult,
) -> _DetachedVerifiedResearchSemantics:
    research = verified_research.research
    integrity = verified_research.integrity
    snapshot = research.snapshot
    return _DetachedVerifiedResearchSemantics(
        canonical_instrument_id=tuple(
            sorted(integrity.canonical_instrument_id.to_dict().items())
        ),
        requested_trading_identity=tuple(
            sorted(integrity.requested_trading_identity.to_dict().items())
        ),
        analysis_as_of=research.request.analysis_as_of,
        snapshot_fingerprint=snapshot.fingerprint,
        integrity_fingerprint=integrity.fingerprint,
        source_quality=snapshot.quality,
        source_warnings=tuple(snapshot.warnings),
        latest_close=snapshot.latest_close,
        ema_8=snapshot.ema_8,
        ema_20=snapshot.ema_20,
        ema_144=snapshot.ema_144,
        ema_169=snapshot.ema_169,
        macd_line=snapshot.macd_line,
        macd_signal=snapshot.macd_signal,
        rsi_14=snapshot.rsi_14,
        realized_volatility=snapshot.realized_volatility,
        volatility_references=_DetachedVolatilityReferences(
            snapshot.volatility_references.distance_from_ema20_percent
        ),
        complete_source_projection=json.dumps(
            verified_research.to_dict(), sort_keys=True, separators=(",", ":")
        ),
    )


def _snapshot_operand(field: str, value: float) -> TechnicalComparisonOperand:
    return TechnicalComparisonOperand(
        TechnicalComparisonOperandSource.TECHNICAL_ANALYSIS_SNAPSHOT, field, value
    )


def _configuration_operand(field: str, value: float) -> TechnicalComparisonOperand:
    return TechnicalComparisonOperand(
        TechnicalComparisonOperandSource.INTERPRETATION_POLICY_CONFIGURATION,
        field,
        value,
    )


def _derived_operand(field: str, value: float) -> TechnicalComparisonOperand:
    return TechnicalComparisonOperand(
        TechnicalComparisonOperandSource.INTERPRETATION_POLICY_DERIVED, field, value
    )


def _comparison(
    evidence_id: str,
    left: TechnicalComparisonOperand,
    operator: TechnicalComparisonOperator,
    right: TechnicalComparisonOperand,
) -> TechnicalComparisonEvidence:
    return TechnicalComparisonEvidence(
        evidence_id, left, operator, right, _compare(left.value, operator, right.value)
    )


def build_classic_comparison_evidence(
    snapshot: TechnicalAnalysisSnapshot,
    configuration: ClassicDailyTechnicalInterpretationConfiguration,
) -> tuple[TechnicalComparisonEvidence, ...]:
    """Build the closed classic v1 comparison inventory in canonical order."""

    configuration._validate()
    specs = (
        (
            "trend_ema8_above_ema20",
            "ema_8",
            TechnicalComparisonOperator.GREATER_THAN,
            "ema_20",
            "snapshot",
        ),
        (
            "trend_ema8_below_ema20",
            "ema_8",
            TechnicalComparisonOperator.LESS_THAN,
            "ema_20",
            "snapshot",
        ),
        (
            "trend_close_above_ema144",
            "latest_close",
            TechnicalComparisonOperator.GREATER_THAN,
            "ema_144",
            "snapshot",
        ),
        (
            "trend_close_below_ema144",
            "latest_close",
            TechnicalComparisonOperator.LESS_THAN,
            "ema_144",
            "snapshot",
        ),
        (
            "trend_close_above_ema169",
            "latest_close",
            TechnicalComparisonOperator.GREATER_THAN,
            "ema_169",
            "snapshot",
        ),
        (
            "trend_close_below_ema169",
            "latest_close",
            TechnicalComparisonOperator.LESS_THAN,
            "ema_169",
            "snapshot",
        ),
        (
            "momentum_macd_line_above_signal",
            "macd_line",
            TechnicalComparisonOperator.GREATER_THAN,
            "macd_signal",
            "snapshot",
        ),
        (
            "momentum_macd_line_below_signal",
            "macd_line",
            TechnicalComparisonOperator.LESS_THAN,
            "macd_signal",
            "snapshot",
        ),
        (
            "momentum_rsi_at_or_above_neutral",
            "rsi_14",
            TechnicalComparisonOperator.GREATER_THAN_OR_EQUAL,
            "rsi_neutral",
            "config",
        ),
        (
            "momentum_rsi_below_neutral",
            "rsi_14",
            TechnicalComparisonOperator.LESS_THAN,
            "rsi_neutral",
            "config",
        ),
        (
            "rsi_at_or_above_elevated",
            "rsi_14",
            TechnicalComparisonOperator.GREATER_THAN_OR_EQUAL,
            "rsi_elevated",
            "config",
        ),
        (
            "rsi_at_or_below_depressed",
            "rsi_14",
            TechnicalComparisonOperator.LESS_THAN_OR_EQUAL,
            "rsi_depressed",
            "config",
        ),
        (
            "volatility_below_low",
            "realized_volatility",
            TechnicalComparisonOperator.LESS_THAN,
            "realized_volatility_low",
            "config",
        ),
        (
            "volatility_at_or_above_low",
            "realized_volatility",
            TechnicalComparisonOperator.GREATER_THAN_OR_EQUAL,
            "realized_volatility_low",
            "config",
        ),
        (
            "volatility_below_high",
            "realized_volatility",
            TechnicalComparisonOperator.LESS_THAN,
            "realized_volatility_high",
            "config",
        ),
        (
            "volatility_at_or_above_high",
            "realized_volatility",
            TechnicalComparisonOperator.GREATER_THAN_OR_EQUAL,
            "realized_volatility_high",
            "config",
        ),
        (
            "extension_above_positive_band",
            "volatility_references.distance_from_ema20_percent",
            TechnicalComparisonOperator.GREATER_THAN,
            "ema20_extension_band_percent",
            "config",
        ),
        (
            "extension_below_negative_band",
            "volatility_references.distance_from_ema20_percent",
            TechnicalComparisonOperator.LESS_THAN,
            "negative_ema20_extension_band_percent",
            "derived",
        ),
    )
    result: list[TechnicalComparisonEvidence] = []
    for evidence_id, left_field, operator, right_field, right_source in specs:
        left_value = (
            snapshot.volatility_references.distance_from_ema20_percent
            if left_field == "volatility_references.distance_from_ema20_percent"
            else getattr(snapshot, left_field)
        )
        right_value = (
            getattr(snapshot, right_field)
            if right_source == "snapshot"
            else getattr(configuration, right_field)
            if right_source == "config"
            else 0.0 - configuration.ema20_extension_band_percent
        )
        if left_value is None or right_value is None:
            continue
        right = (
            _snapshot_operand(right_field, right_value)
            if right_source == "snapshot"
            else _configuration_operand(right_field, right_value)
            if right_source == "config"
            else _derived_operand(right_field, right_value)
        )
        result.append(
            _comparison(
                evidence_id, _snapshot_operand(left_field, left_value), operator, right
            )
        )
    return tuple(result)


def classic_states(
    snapshot: TechnicalAnalysisSnapshot,
    configuration: ClassicDailyTechnicalInterpretationConfiguration,
) -> tuple[
    DailyTechnicalDirectionalState,
    DailyTechnicalDirectionalState,
    VolatilityState,
    DailyTechnicalExtensionState,
]:
    ema_8 = snapshot.ema_8
    ema_20 = snapshot.ema_20
    ema_144 = snapshot.ema_144
    ema_169 = snapshot.ema_169
    if ema_8 is None or ema_20 is None or ema_144 is None or ema_169 is None:
        trend = DailyTechnicalDirectionalState.UNAVAILABLE
    else:
        if (
            ema_8 > ema_20
            and snapshot.latest_close > ema_144
            and snapshot.latest_close > ema_169
        ):
            trend = DailyTechnicalDirectionalState.POSITIVE
        elif (
            ema_8 < ema_20
            and snapshot.latest_close < ema_144
            and snapshot.latest_close < ema_169
        ):
            trend = DailyTechnicalDirectionalState.NEGATIVE
        else:
            trend = DailyTechnicalDirectionalState.MIXED
    macd_line = snapshot.macd_line
    macd_signal = snapshot.macd_signal
    rsi_14 = snapshot.rsi_14
    if macd_line is None or macd_signal is None or rsi_14 is None:
        momentum = DailyTechnicalDirectionalState.UNAVAILABLE
    else:
        if macd_line > macd_signal and rsi_14 >= configuration.rsi_neutral:
            momentum = DailyTechnicalDirectionalState.POSITIVE
        elif macd_line < macd_signal and rsi_14 < configuration.rsi_neutral:
            momentum = DailyTechnicalDirectionalState.NEGATIVE
        else:
            momentum = DailyTechnicalDirectionalState.MIXED
    realized = snapshot.realized_volatility
    if realized is None:
        volatility = VolatilityState.UNAVAILABLE
    elif realized < configuration.realized_volatility_low:
        volatility = VolatilityState.LOW
    elif realized < configuration.realized_volatility_high:
        volatility = VolatilityState.NORMAL
    else:
        volatility = VolatilityState.HIGH
    distance = snapshot.volatility_references.distance_from_ema20_percent
    if distance is None:
        extension = DailyTechnicalExtensionState.UNAVAILABLE
    elif distance > configuration.ema20_extension_band_percent:
        extension = DailyTechnicalExtensionState.ABOVE_REFERENCE_BAND
    elif distance < 0.0 - configuration.ema20_extension_band_percent:
        extension = DailyTechnicalExtensionState.BELOW_REFERENCE_BAND
    else:
        extension = DailyTechnicalExtensionState.WITHIN_REFERENCE_BAND
    return trend, momentum, volatility, extension


def interpret_daily_technical_research(
    verified_research: IntegrityCheckedDailyTechnicalResearchResult,
    policy: DailyTechnicalInterpretationPolicy,
) -> DailyTechnicalInterpretation:
    if type(verified_research) is not IntegrityCheckedDailyTechnicalResearchResult:
        raise TypeError("verified_research must be an exact integrity-checked result")
    verified_research._validate()
    source_before = _detach_verified_research_semantics(verified_research)
    try:
        before = copy_technical_policy_identity(policy.identity)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("interpretation policy identity is invalid") from exc
    if before.policy_kind is not TechnicalPolicyKind.DAILY_TECHNICAL_INTERPRETATION:
        raise ValueError("interpretation policy identity kind is invalid")
    if (
        type(before.configuration)
        is not ClassicDailyTechnicalInterpretationConfiguration
    ):
        raise ValueError("interpretation policy configuration type is unsupported")
    result = policy.interpret(verified_research)
    verified_research._validate()
    source_after = _detach_verified_research_semantics(verified_research)
    if source_after != source_before:
        raise ValueError("verified research source drifted during invocation")
    try:
        after = copy_technical_policy_identity(policy.identity)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("post-call interpretation policy identity is invalid") from exc
    if before.to_dict() != after.to_dict():
        raise ValueError("interpretation policy identity drifted during invocation")
    if type(result) is not DailyTechnicalInterpretation:
        raise TypeError("policy must return an exact DailyTechnicalInterpretation")
    result._validate()
    if result.interpretation_policy_identity.to_dict() != before.to_dict():
        raise ValueError("result does not correspond to pre-call policy identity")
    if (
        tuple(sorted(result.canonical_instrument_id.to_dict().items()))
        != source_before.canonical_instrument_id
        or tuple(sorted(result.requested_trading_identity.to_dict().items()))
        != source_before.requested_trading_identity
        or result.analysis_as_of != source_before.analysis_as_of
        or result.source_technical_analysis_snapshot_fingerprint
        != source_before.snapshot_fingerprint
        or result.source_daily_instrument_integrity_evidence_fingerprint
        != source_before.integrity_fingerprint
    ):
        raise ValueError("interpretation source correspondence is invalid")
    if (
        result.source_quality is not source_before.source_quality
        or result.source_warnings != source_before.source_warnings
    ):
        raise ValueError("interpretation source quality or warnings do not correspond")
    configuration = before.configuration
    expected_evidence = build_classic_comparison_evidence(
        source_before,  # type: ignore[arg-type]
        configuration,
    )
    if result.comparison_evidence != expected_evidence:
        raise ValueError("interpretation comparison evidence is not complete and exact")
    expected_states = classic_states(
        source_before,  # type: ignore[arg-type]
        configuration,
    )
    actual_states = (
        result.trend_direction,
        result.momentum_direction,
        result.volatility_state,
        result.extension_state,
    )
    if actual_states != expected_states:
        raise ValueError("interpretation states do not correspond to source evidence")
    return result


__all__ = [
    "DAILY_TECHNICAL_INTERPRETATION_SCHEMA",
    "DailyTechnicalDirectionalState",
    "DailyTechnicalExtensionState",
    "TechnicalComparisonOperandSource",
    "TechnicalComparisonOperator",
    "TechnicalComparisonOperand",
    "TechnicalComparisonEvidence",
    "DailyTechnicalInterpretationPolicy",
    "DailyTechnicalInterpretation",
    "interpret_daily_technical_research",
]
