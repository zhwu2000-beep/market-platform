"""Governed Interpretation values; self-consistency is not execution authority.

The caller must authenticate retained Polygon technical provenance before using
the semantic entry point. This module neither resolves history nor issues results.
"""

from __future__ import annotations

import math
import re
from copy import deepcopy
from dataclasses import dataclass, field, fields, replace
from datetime import UTC, datetime

from market_platform._fingerprint import canonical_fingerprint, canonical_float
from market_platform.evidence import (
    EvidenceArtifactReference,
    EvidenceAuthority,
    EvidenceInformationClass,
)
from market_platform.instruments.identity import (
    CanonicalInstrument,
    CanonicalInstrumentId,
)
from market_platform.research import daily_technical_interpretation as classic
from market_platform.research.classic_daily_technical import (
    ClassicDailyTechnicalInterpretationPolicy,
)
from market_platform.research.daily_technical_interpretation import (
    TechnicalComparisonEvidence,
    build_classic_comparison_evidence,
    classic_states,
)
from market_platform.research.technical_analysis import (
    TechnicalAnalysisSnapshot,
)
from market_platform.research.technical_policy import (
    ClassicDailyTechnicalInterpretationConfiguration,
    TechnicalPolicyIdentity,
    TechnicalPolicyKind,
    copy_technical_policy_identity,
)
from market_platform.trading.instrument import TradingInstrumentIdentity

GOVERNED_DAILY_TECHNICAL_INTERPRETATION_SCHEMA = (
    "governed_daily_technical_interpretation/v1"
)
_POLICY_FINGERPRINT = (
    "sha256:9d81e49a6d45d27071e804b46486ae247d71f650184e8032a792586807fc3d02"
)
_FINGERPRINT = re.compile(r"sha256:[0-9a-f]{64}", re.ASCII)
_COMPARISON_IDS = (
    "trend_ema8_above_ema20",
    "trend_ema8_below_ema20",
    "trend_close_above_ema144",
    "trend_close_below_ema144",
    "trend_close_above_ema169",
    "trend_close_below_ema169",
    "momentum_macd_line_above_signal",
    "momentum_macd_line_below_signal",
    "momentum_rsi_at_or_above_neutral",
    "momentum_rsi_below_neutral",
    "rsi_at_or_above_elevated",
    "rsi_at_or_below_depressed",
    "volatility_below_low",
    "volatility_at_or_above_low",
    "volatility_below_high",
    "volatility_at_or_above_high",
    "extension_above_positive_band",
    "extension_below_negative_band",
)


def _fingerprint(value: object) -> None:
    if type(value) is not str or _FINGERPRINT.fullmatch(value) is None:
        raise ValueError("exact SHA-256 fingerprint required")


def _choice(value: object, choices: tuple[str, ...]) -> None:
    if type(value) is not str or value not in choices:
        raise ValueError("exact closed scalar category required")


@dataclass(frozen=True, slots=True, kw_only=True)
class GovernedTechnicalArtifactReference:
    """Scalar artifact value; possession conveys no publication authority."""

    artifact_id: str
    artifact_version: str
    artifact_fingerprint: str
    information_class: str
    authority: str
    schema_version: str = field(init=False, default="evidence_artifact_reference/v2")
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        self._validate_structure()
        object.__setattr__(
            self, "fingerprint", canonical_fingerprint(self._fingerprint_payload())
        )

    def _validate_structure(self) -> None:
        for value, limit in ((self.artifact_id, 256), (self.artifact_version, 128)):
            if (
                type(value) is not str
                or not 1 <= len(value) <= limit
                or any(not "!" <= char <= "~" for char in value)
            ):
                raise ValueError("canonical visible ASCII artifact identity required")
        _fingerprint(self.artifact_fingerprint)
        _choice(self.schema_version, ("evidence_artifact_reference/v2",))
        _choice(
            self.information_class,
            ("source_observation", "source_measurement", "source_assertion"),
        )
        _choice(self.authority, ("platform_origin", "external_origin"))

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "artifact_id": self.artifact_id,
            "artifact_version": self.artifact_version,
            "artifact_fingerprint": self.artifact_fingerprint,
            "information_class": self.information_class,
            "authority": self.authority,
        }

    def _validate(self) -> None:
        self._validate_structure()
        _fingerprint(self.fingerprint)
        if self.fingerprint != canonical_fingerprint(self._fingerprint_payload()):
            raise ValueError("artifact reference fingerprint mismatch")

    def to_dict(self) -> dict[str, object]:
        self._validate()
        return {**self._fingerprint_payload(), "fingerprint": self.fingerprint}


def _copy_artifact(value: object) -> GovernedTechnicalArtifactReference:
    if type(value) is GovernedTechnicalArtifactReference:
        value._validate()
        return replace(value)
    if type(value) is not EvidenceArtifactReference:
        raise TypeError("exact legacy or governed artifact reference required")
    value._validate()
    copied = GovernedTechnicalArtifactReference(
        artifact_id=value.artifact_id,
        artifact_version=value.artifact_version,
        artifact_fingerprint=value.artifact_fingerprint,
        information_class=value.information_class.value,
        authority=value.authority.value,
    )
    if copied.to_dict() != value.to_dict():
        raise ValueError("artifact reference is noncanonical")
    return copied


def _legacy_artifact(
    value: GovernedTechnicalArtifactReference,
) -> EvidenceArtifactReference:
    """Ephemeral adapter for private Slice 8 resolution, never retained authority."""
    scalar = _copy_artifact(value)
    legacy = EvidenceArtifactReference(
        artifact_id=scalar.artifact_id,
        artifact_version=scalar.artifact_version,
        artifact_fingerprint=scalar.artifact_fingerprint,
        information_class=EvidenceInformationClass(scalar.information_class),
        authority=EvidenceAuthority(scalar.authority),
    )
    if legacy.to_dict() != scalar.to_dict():
        raise ValueError("private artifact reconstruction mismatch")
    return legacy


@dataclass(frozen=True, slots=True, kw_only=True)
class GovernedTechnicalPolicyIdentity:
    policy_kind: str
    policy_id: str
    behavioral_revision: str
    configuration_schema: str
    configuration: ClassicDailyTechnicalInterpretationConfiguration
    schema_version: str = field(init=False, default="technical_policy_identity/v1")
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        self._validate_structure()
        object.__setattr__(self, "configuration", replace(self.configuration))
        object.__setattr__(
            self, "fingerprint", canonical_fingerprint(self._fingerprint_payload())
        )
        self._validate()

    def _validate_structure(self) -> None:
        for value, expected in (
            (self.schema_version, "technical_policy_identity/v1"),
            (self.policy_kind, "daily_technical_interpretation"),
            (self.policy_id, "classic_daily_technical"),
            (self.behavioral_revision, "1.0.0"),
            (
                self.configuration_schema,
                "classic_daily_technical_interpretation_configuration/v1",
            ),
        ):
            _choice(value, (expected,))
        if (
            type(self.configuration)
            is not ClassicDailyTechnicalInterpretationConfiguration
        ):
            raise TypeError("exact fixed configuration required")
        self.configuration._validate()
        if self.configuration.to_dict() != {
            "rsi_neutral": 50.0,
            "rsi_elevated": 70.0,
            "rsi_depressed": 30.0,
            "realized_volatility_low": 0.15,
            "realized_volatility_high": 0.30,
            "ema20_extension_band_percent": 5.0,
        }:
            raise ValueError("fixed classic default policy mismatch")

    def _projection(self, *, fingerprint_floats: bool) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "policy_kind": self.policy_kind,
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
        self._validate_structure()
        _fingerprint(self.fingerprint)
        if (
            self.fingerprint != _POLICY_FINGERPRINT
            or self.fingerprint != canonical_fingerprint(self._fingerprint_payload())
        ):
            raise ValueError("fixed classic default policy mismatch")

    def to_dict(self) -> dict[str, object]:
        self._validate()
        return {
            **self._projection(fingerprint_floats=False),
            "fingerprint": self.fingerprint,
        }


def _scalar_policy(value: TechnicalPolicyIdentity) -> GovernedTechnicalPolicyIdentity:
    _check_policy(value)
    assert type(value.configuration) is ClassicDailyTechnicalInterpretationConfiguration
    return GovernedTechnicalPolicyIdentity(
        policy_kind=value.policy_kind.value,
        policy_id=value.policy_id,
        behavioral_revision=value.behavioral_revision,
        configuration_schema=value.configuration_schema,
        configuration=value.configuration,
    )


_OPERAND_FIELDS = {
    "technical_analysis_snapshot": (
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
    ),
    "interpretation_policy_configuration": (
        "rsi_neutral",
        "rsi_elevated",
        "rsi_depressed",
        "realized_volatility_low",
        "realized_volatility_high",
        "ema20_extension_band_percent",
    ),
    "interpretation_policy_derived": ("negative_ema20_extension_band_percent",),
}


@dataclass(frozen=True, slots=True)
class GovernedTechnicalComparisonOperand:
    source: str
    field: str
    value: float

    def __post_init__(self) -> None:
        self._validate()

    def _validate(self) -> None:
        _choice(self.source, tuple(_OPERAND_FIELDS))
        _choice(self.field, _OPERAND_FIELDS[self.source])
        if type(self.value) is not float or not math.isfinite(self.value):
            raise TypeError("operand value must be an exact finite float")
        if self.value == 0.0 and math.copysign(1.0, self.value) < 0.0:
            raise ValueError("operand value must not retain negative zero")

    def to_dict(self, *, fingerprint_floats: bool = False) -> dict[str, object]:
        self._validate()
        return {
            "source": self.source,
            "field": self.field,
            "value": canonical_float(self.value) if fingerprint_floats else self.value,
        }


@dataclass(frozen=True, slots=True)
class GovernedTechnicalComparisonEvidence:
    evidence_id: str
    left_operand: GovernedTechnicalComparisonOperand
    operator: str
    right_operand: GovernedTechnicalComparisonOperand
    satisfied: bool

    def __post_init__(self) -> None:
        self._validate()
        object.__setattr__(self, "left_operand", replace(self.left_operand))
        object.__setattr__(self, "right_operand", replace(self.right_operand))

    def _validate(self) -> None:
        _choice(self.evidence_id, _COMPARISON_IDS)
        for operand in (self.left_operand, self.right_operand):
            if type(operand) is not GovernedTechnicalComparisonOperand:
                raise TypeError("exact governed operand required")
            operand._validate()
        _choice(
            self.operator,
            (
                "greater_than",
                "greater_than_or_equal",
                "less_than",
                "less_than_or_equal",
            ),
        )
        if type(self.satisfied) is not bool:
            raise TypeError("exact comparison satisfied bool required")
        # Use the released comparison validator, including its relational check.
        classic.TechnicalComparisonEvidence(
            self.evidence_id,
            classic.TechnicalComparisonOperand(
                classic.TechnicalComparisonOperandSource(self.left_operand.source),
                self.left_operand.field,
                self.left_operand.value,
            ),
            classic.TechnicalComparisonOperator(self.operator),
            classic.TechnicalComparisonOperand(
                classic.TechnicalComparisonOperandSource(self.right_operand.source),
                self.right_operand.field,
                self.right_operand.value,
            ),
            self.satisfied,
        )._validate()

    def to_dict(self, *, fingerprint_floats: bool = False) -> dict[str, object]:
        self._validate()
        return {
            "evidence_id": self.evidence_id,
            "left_operand": self.left_operand.to_dict(
                fingerprint_floats=fingerprint_floats
            ),
            "operator": self.operator,
            "right_operand": self.right_operand.to_dict(
                fingerprint_floats=fingerprint_floats
            ),
            "satisfied": self.satisfied,
        }


def _scalar_comparison(
    value: TechnicalComparisonEvidence,
) -> GovernedTechnicalComparisonEvidence:
    if type(value) is not TechnicalComparisonEvidence:
        raise TypeError("exact released comparison required")
    value._validate()
    return GovernedTechnicalComparisonEvidence(
        value.evidence_id,
        GovernedTechnicalComparisonOperand(
            value.left_operand.source.value,
            value.left_operand.field,
            value.left_operand.value,
        ),
        value.operator.value,
        GovernedTechnicalComparisonOperand(
            value.right_operand.source.value,
            value.right_operand.field,
            value.right_operand.value,
        ),
        value.satisfied,
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class PolygonCompletedDailyInterpretationRequest:
    """Five exact source selectors, never bearer authority or a history lookup."""

    artifact_reference: GovernedTechnicalArtifactReference
    technical_history_namespace_id: str
    technical_history_sequence: int
    technical_execution_id: str
    technical_fingerprint: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "artifact_reference", _copy_artifact(self.artifact_reference)
        )
        self._validate()

    def _validate(self) -> None:
        if type(self.artifact_reference) is not GovernedTechnicalArtifactReference:
            raise TypeError("exact governed artifact reference required")
        self.artifact_reference._validate()
        for value, prefix in (
            (
                self.technical_history_namespace_id,
                "polygon_completed_daily_technical_history",
            ),
            (self.technical_execution_id, "polygon_completed_daily_technical"),
        ):
            if (
                type(value) is not str
                or re.fullmatch(prefix + r":[0-9a-f]{32}", value) is None
            ):
                raise ValueError("exact technical occurrence identity required")
        if (
            type(self.technical_history_sequence) is not int
            or self.technical_history_sequence < 1
        ):
            raise ValueError("positive exact technical history sequence required")
        _fingerprint(self.technical_fingerprint)

    def to_dict(self) -> dict[str, object]:
        self._validate()
        return {
            "artifact_reference": self.artifact_reference.to_dict(),
            "technical_history_namespace_id": self.technical_history_namespace_id,
            "technical_history_sequence": self.technical_history_sequence,
            "technical_execution_id": self.technical_execution_id,
            "technical_fingerprint": self.technical_fingerprint,
        }


def _copy_reference(
    value: PolygonCompletedDailyInterpretationRequest,
) -> PolygonCompletedDailyInterpretationRequest:
    if type(value) is not PolygonCompletedDailyInterpretationRequest:
        raise TypeError("exact technical occurrence reference required")
    value._validate()
    return replace(value)


def _check_policy(value: TechnicalPolicyIdentity) -> None:
    if type(value) is not TechnicalPolicyIdentity:
        raise TypeError("exact fixed policy identity required")
    value._validate()
    if (
        type(value.schema_version) is not str
        or type(value.configuration_schema) is not str
        or value.policy_kind is not TechnicalPolicyKind.DAILY_TECHNICAL_INTERPRETATION
        or value.policy_id != "classic_daily_technical"
        or value.behavioral_revision != "1.0.0"
        or value.configuration_schema
        != "classic_daily_technical_interpretation_configuration/v1"
        or type(value.configuration)
        is not ClassicDailyTechnicalInterpretationConfiguration
        or value.configuration.to_dict()
        != {
            "rsi_neutral": 50.0,
            "rsi_elevated": 70.0,
            "rsi_depressed": 30.0,
            "realized_volatility_low": 0.15,
            "realized_volatility_high": 0.30,
            "ema20_extension_band_percent": 5.0,
        }
        or value.fingerprint != _POLICY_FINGERPRINT
    ):
        raise ValueError("fixed classic default policy mismatch")


def _fixed_policy() -> TechnicalPolicyIdentity:
    identity = ClassicDailyTechnicalInterpretationPolicy().identity
    _check_policy(identity)
    return identity


def _copy_canonical(value: CanonicalInstrumentId) -> CanonicalInstrumentId:
    if type(value) is not CanonicalInstrumentId:
        raise TypeError("exact canonical instrument ID required")
    if type(value.instrument_id) is not str:
        raise TypeError("exact canonical instrument scalar required")
    copied = CanonicalInstrumentId(value.instrument_id)
    if copied != value:
        raise ValueError("canonical instrument ID is noncanonical")
    return copied


def _copy_trading(value: TradingInstrumentIdentity) -> TradingInstrumentIdentity:
    if type(value) is not TradingInstrumentIdentity:
        raise TypeError("exact source trading identity required")
    if any(type(getattr(value, item.name)) is not str for item in fields(value)):
        raise TypeError("exact trading identity scalars required")
    copied = TradingInstrumentIdentity(value.symbol, value.venue)
    if copied != value:
        raise ValueError("source trading identity is noncanonical")
    return copied


@dataclass(frozen=True, slots=True, kw_only=True)
class GovernedDailyTechnicalInterpretation:
    """Detached content, not an authenticated or published execution occurrence.

    Structural validation cannot prove provenance or snapshot correspondence without
    the source. Use the semantic entry point after application authentication.
    """

    source_technical_occurrence: PolygonCompletedDailyInterpretationRequest
    canonical_instrument_id: CanonicalInstrumentId
    source_trading_identity: TradingInstrumentIdentity
    analysis_as_of: datetime
    source_technical_analysis_snapshot_fingerprint: str
    source_governed_dataset_fingerprint: str
    source_research_dataset_content_fingerprint: str
    interpretation_policy_identity: GovernedTechnicalPolicyIdentity
    source_quality: str
    source_warnings: tuple[str, ...]
    trend_direction: str
    momentum_direction: str
    volatility_state: str
    extension_state: str
    comparison_evidence: tuple[GovernedTechnicalComparisonEvidence, ...]
    schema_version: str = field(
        init=False, default=GOVERNED_DAILY_TECHNICAL_INTERPRETATION_SCHEMA
    )
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        self._validate_structure()
        for name, copied in (
            (
                "source_technical_occurrence",
                _copy_reference(self.source_technical_occurrence),
            ),
            ("canonical_instrument_id", _copy_canonical(self.canonical_instrument_id)),
            ("source_trading_identity", _copy_trading(self.source_trading_identity)),
            (
                "interpretation_policy_identity",
                replace(self.interpretation_policy_identity),
            ),
            (
                "comparison_evidence",
                tuple(replace(item) for item in self.comparison_evidence),
            ),
        ):
            object.__setattr__(self, name, copied)
        object.__setattr__(
            self, "fingerprint", canonical_fingerprint(self._fingerprint_payload())
        )
        self._validate()

    def _validate_structure(self) -> None:
        _copy_reference(self.source_technical_occurrence)
        _copy_canonical(self.canonical_instrument_id)
        _copy_trading(self.source_trading_identity)
        if (
            type(self.analysis_as_of) is not datetime
            or self.analysis_as_of.tzinfo is not UTC
        ):
            raise ValueError("analysis_as_of must be canonical UTC")
        for value in (
            self.source_technical_analysis_snapshot_fingerprint,
            self.source_governed_dataset_fingerprint,
            self.source_research_dataset_content_fingerprint,
        ):
            _fingerprint(value)
        if (
            type(self.interpretation_policy_identity)
            is not GovernedTechnicalPolicyIdentity
        ):
            raise TypeError("exact governed policy identity required")
        self.interpretation_policy_identity._validate()
        for value, choices in (
            (self.source_quality, ("complete", "degraded")),
            (self.trend_direction, ("positive", "negative", "mixed", "unavailable")),
            (self.momentum_direction, ("positive", "negative", "mixed", "unavailable")),
            (self.volatility_state, ("low", "normal", "high", "unavailable")),
            (
                self.extension_state,
                (
                    "above_reference_band",
                    "within_reference_band",
                    "below_reference_band",
                    "unavailable",
                ),
            ),
        ):
            _choice(value, choices)
        if type(self.source_warnings) is not tuple:
            raise TypeError("exact source warning tuple required")
        warnings = ("insufficient_profile_history", "stale_evidence")
        for warning in self.source_warnings:
            _choice(warning, warnings)
        if self.source_warnings != tuple(
            item for item in warnings if item in self.source_warnings
        ):
            raise ValueError(
                "source warnings must retain canonical order without duplicates"
            )
        if type(self.comparison_evidence) is not tuple:
            raise TypeError("exact comparison tuple required")
        for item in self.comparison_evidence:
            if type(item) is not GovernedTechnicalComparisonEvidence:
                raise TypeError("exact comparison evidence required")
            item._validate()
        ids = tuple(item.evidence_id for item in self.comparison_evidence)
        if ids != tuple(item for item in _COMPARISON_IDS if item in ids):
            raise ValueError("comparison inventory/order is invalid")
        if (
            type(self.schema_version) is not str
            or self.schema_version != GOVERNED_DAILY_TECHNICAL_INTERPRETATION_SCHEMA
        ):
            raise ValueError("governed Interpretation schema mismatch")

    def _projection(self, *, fingerprint_floats: bool) -> dict[str, object]:
        policy = self.interpretation_policy_identity
        return {
            "schema_version": self.schema_version,
            "source_technical_occurrence": self.source_technical_occurrence.to_dict(),
            "canonical_instrument_id": self.canonical_instrument_id.to_dict(),
            "source_trading_identity": self.source_trading_identity.to_dict(),
            "analysis_as_of": self.analysis_as_of.isoformat(),
            "source_technical_analysis_snapshot_fingerprint": (
                self.source_technical_analysis_snapshot_fingerprint
            ),
            "source_governed_dataset_fingerprint": (
                self.source_governed_dataset_fingerprint
            ),
            "source_research_dataset_content_fingerprint": (
                self.source_research_dataset_content_fingerprint
            ),
            "interpretation_policy_identity": {
                **policy.to_dict(),
                "configuration": policy.configuration.to_dict(
                    fingerprint_floats=fingerprint_floats
                ),
            },
            "source_quality": self.source_quality,
            "source_warnings": list(self.source_warnings),
            "trend_direction": self.trend_direction,
            "momentum_direction": self.momentum_direction,
            "volatility_state": self.volatility_state,
            "extension_state": self.extension_state,
            "comparison_evidence": [
                item.to_dict(fingerprint_floats=fingerprint_floats)
                for item in self.comparison_evidence
            ],
        }

    def _fingerprint_payload(self) -> dict[str, object]:
        return self._projection(fingerprint_floats=True)

    def _validate(self) -> None:
        try:
            for item in fields(self):
                object.__getattribute__(self, item.name)
        except AttributeError as exc:
            raise ValueError(
                "governed Interpretation retained state incomplete"
            ) from exc
        self._validate_structure()
        _fingerprint(self.fingerprint)
        if self.fingerprint != canonical_fingerprint(self._fingerprint_payload()):
            raise ValueError("governed Interpretation fingerprint mismatch")

    def to_dict(self) -> dict[str, object]:
        self._validate()
        return {
            **self._projection(fingerprint_floats=False),
            "fingerprint": self.fingerprint,
        }


def _expected_projection(
    snapshot: TechnicalAnalysisSnapshot,
    reference: PolygonCompletedDailyInterpretationRequest,
    instrument: CanonicalInstrument,
    dataset_fingerprint: str,
    policy: TechnicalPolicyIdentity,
) -> dict[str, object]:
    """One complete correspondence projection using only the released core."""
    expected: dict[str, object] = {
        "schema_version": GOVERNED_DAILY_TECHNICAL_INTERPRETATION_SCHEMA,
        "source_technical_occurrence": reference.to_dict(),
        "canonical_instrument_id": instrument.instrument_id.to_dict(),
        "source_trading_identity": instrument.trading_identity.to_dict(),
        "analysis_as_of": snapshot.evidence.analysis_as_of.isoformat(),
        "source_technical_analysis_snapshot_fingerprint": snapshot.fingerprint,
        "source_governed_dataset_fingerprint": dataset_fingerprint,
        "source_research_dataset_content_fingerprint": (
            snapshot.evidence.dataset_content_fingerprint
        ),
        "interpretation_policy_identity": _scalar_policy(policy).to_dict(),
        "source_quality": snapshot.quality.value,
        "source_warnings": [item.value for item in snapshot.warnings],
    }
    configuration = policy.configuration
    assert type(configuration) is ClassicDailyTechnicalInterpretationConfiguration
    states = classic.classic_states(snapshot, configuration)
    comparisons = classic.build_classic_comparison_evidence(snapshot, configuration)
    expected.update(
        {
            "trend_direction": states[0].value,
            "momentum_direction": states[1].value,
            "volatility_state": states[2].value,
            "extension_state": states[3].value,
            "comparison_evidence": [
                _scalar_comparison(item).to_dict() for item in comparisons
            ],
        }
    )
    return deepcopy(expected)


def _check_expected_content(
    content: GovernedDailyTechnicalInterpretation, expected: dict[str, object]
) -> None:
    if type(content) is not GovernedDailyTechnicalInterpretation:
        raise TypeError("exact governed Interpretation content required")
    content._validate()
    if content._projection(fingerprint_floats=False) != expected:
        raise ValueError(
            "governed Interpretation source/semantic correspondence mismatch"
        )


def validate_governed_daily_technical_interpretation(
    *,
    content: GovernedDailyTechnicalInterpretation,
    snapshot: TechnicalAnalysisSnapshot,
    source_technical_occurrence: PolygonCompletedDailyInterpretationRequest,
    canonical_instrument: CanonicalInstrument,
    source_governed_dataset_fingerprint: str,
) -> None:
    """Verify complete frozen semantics against source values, never history authority.

    The application must separately authenticate the retained source. Expectations
    use detached inputs and the same released core as the semantic entry point.
    """
    if type(content) is not GovernedDailyTechnicalInterpretation:
        raise TypeError("exact governed Interpretation content required")
    content_before = deepcopy(content.to_dict())
    if type(snapshot) is not TechnicalAnalysisSnapshot:
        raise TypeError("exact TechnicalAnalysisSnapshot required")
    snapshot._validate()
    source_before = deepcopy(snapshot.to_dict())
    detached = deepcopy(snapshot)
    detached._validate()
    if detached.to_dict() != source_before:
        raise ValueError("snapshot changed during verification detachment")
    reference = _copy_reference(source_technical_occurrence)
    reference_before = deepcopy(reference.to_dict())
    if type(canonical_instrument) is not CanonicalInstrument:
        raise TypeError("exact canonical instrument descriptor required")
    canonical_instrument._validate()
    instrument_before = deepcopy(canonical_instrument.to_dict())
    instrument = deepcopy(canonical_instrument)
    if instrument.trading_identity != detached.evidence.instrument:
        raise ValueError("canonical instrument/source trading identity mismatch")
    _fingerprint(source_governed_dataset_fingerprint)
    policy = _fixed_policy()
    _check_policy(policy)
    policy_before = deepcopy(policy.to_dict())
    working_policy = copy_technical_policy_identity(policy)
    expected = _expected_projection(
        detached,
        reference,
        instrument,
        source_governed_dataset_fingerprint,
        working_policy,
    )
    for source in (snapshot, detached):
        source._validate()
        if source.to_dict() != source_before:
            raise ValueError("snapshot source drift during correspondence verification")
    for occurrence in (source_technical_occurrence, reference):
        if occurrence.to_dict() != reference_before:
            raise ValueError(
                "source occurrence drift during correspondence verification"
            )
    for subject in (canonical_instrument, instrument):
        subject._validate()
        if subject.to_dict() != instrument_before:
            raise ValueError(
                "canonical instrument drift during correspondence verification"
            )
    for identity in (policy, working_policy):
        _check_policy(identity)
        if identity.to_dict() != policy_before:
            raise ValueError("policy drift during correspondence verification")
    if content.to_dict() != content_before:
        raise ValueError("content drift during correspondence verification")
    _check_expected_content(content, expected)


def interpret_governed_daily_technical_snapshot(
    *,
    snapshot: TechnicalAnalysisSnapshot,
    source_technical_occurrence: PolygonCompletedDailyInterpretationRequest,
    canonical_instrument: CanonicalInstrument,
    source_governed_dataset_fingerprint: str,
) -> GovernedDailyTechnicalInterpretation:
    """Apply fixed classic semantics after caller-owned provenance authentication.

    Canonical mapping and governed dataset authenticity require Slice 2 retained
    resolution. A self-consistent descriptor/reference here is only a value.
    Snapshot time, trading identity, and research dataset identity are derived,
    never caller overrides. No execution metadata or authority is produced.
    """

    if type(snapshot) is not TechnicalAnalysisSnapshot:
        raise TypeError("exact TechnicalAnalysisSnapshot required")
    snapshot._validate()
    source_before = deepcopy(snapshot.to_dict())
    detached = deepcopy(snapshot)
    detached._validate()
    if detached.to_dict() != source_before:
        raise ValueError("snapshot changed during detachment")
    reference = _copy_reference(source_technical_occurrence)
    reference_before = reference.to_dict()
    if type(canonical_instrument) is not CanonicalInstrument:
        raise TypeError("exact canonical instrument descriptor required")
    canonical_instrument._validate()
    instrument_before = deepcopy(canonical_instrument.to_dict())
    instrument = deepcopy(canonical_instrument)
    if instrument.trading_identity.to_dict() != detached.evidence.instrument.to_dict():
        raise ValueError("canonical instrument/source trading identity mismatch")
    _fingerprint(source_governed_dataset_fingerprint)
    _fingerprint(detached.fingerprint)
    _fingerprint(detached.evidence.dataset_content_fingerprint)
    policy = _fixed_policy()
    _check_policy(policy)
    policy_before = deepcopy(policy.to_dict())
    working_policy = copy_technical_policy_identity(policy)
    configuration = working_policy.configuration
    assert type(configuration) is ClassicDailyTechnicalInterpretationConfiguration

    # Expectations use a separate detached graph and the released core, before
    # computation can mutate either its working input or caller-owned values.
    expected_source = deepcopy(detached)
    expected_policy = copy_technical_policy_identity(policy)
    expected_configuration = expected_policy.configuration
    assert (
        type(expected_configuration) is ClassicDailyTechnicalInterpretationConfiguration
    )
    expected = _expected_projection(
        expected_source,
        reference,
        instrument,
        source_governed_dataset_fingerprint,
        expected_policy,
    )

    trend, momentum, volatility, extension = classic_states(detached, configuration)
    comparisons = build_classic_comparison_evidence(detached, configuration)
    result = GovernedDailyTechnicalInterpretation(
        source_technical_occurrence=reference,
        canonical_instrument_id=instrument.instrument_id,
        source_trading_identity=instrument.trading_identity,
        analysis_as_of=detached.evidence.analysis_as_of,
        source_technical_analysis_snapshot_fingerprint=detached.fingerprint,
        source_governed_dataset_fingerprint=source_governed_dataset_fingerprint,
        source_research_dataset_content_fingerprint=detached.evidence.dataset_content_fingerprint,
        interpretation_policy_identity=_scalar_policy(working_policy),
        source_quality=detached.quality.value,
        source_warnings=tuple(item.value for item in detached.warnings),
        trend_direction=trend.value,
        momentum_direction=momentum.value,
        volatility_state=volatility.value,
        extension_state=extension.value,
        comparison_evidence=tuple(_scalar_comparison(item) for item in comparisons),
    )
    for source in (snapshot, detached, expected_source):
        source._validate()
        if source.to_dict() != source_before:
            raise ValueError("snapshot source drift during Interpretation")
    for identity in (policy, working_policy, expected_policy):
        _check_policy(identity)
        if identity.to_dict() != policy_before:
            raise ValueError("policy drift during Interpretation")
    for retained_configuration in (configuration, expected_configuration):
        if retained_configuration.to_dict() != policy_before["configuration"]:
            raise ValueError("policy configuration drift during Interpretation")
    for occurrence in (source_technical_occurrence, reference):
        if occurrence.to_dict() != reference_before:
            raise ValueError("source occurrence drift during Interpretation")
    for subject in (canonical_instrument, instrument):
        subject._validate()
        if subject.to_dict() != instrument_before:
            raise ValueError("canonical instrument drift during Interpretation")
    _check_expected_content(result, expected)
    return result


__all__ = [
    "GOVERNED_DAILY_TECHNICAL_INTERPRETATION_SCHEMA",
    "PolygonCompletedDailyInterpretationRequest",
    "GovernedDailyTechnicalInterpretation",
    "GovernedTechnicalArtifactReference",
    "GovernedTechnicalPolicyIdentity",
    "GovernedTechnicalComparisonOperand",
    "GovernedTechnicalComparisonEvidence",
    "interpret_governed_daily_technical_snapshot",
    "validate_governed_daily_technical_interpretation",
]
