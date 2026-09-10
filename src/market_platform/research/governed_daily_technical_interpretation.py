"""Governed Interpretation values; self-consistency is not execution authority.

The caller must authenticate retained Polygon technical provenance before using
the semantic entry point. This module neither resolves history nor issues results.
"""

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass, field, fields, replace
from datetime import UTC, datetime

from market_platform._fingerprint import canonical_fingerprint
from market_platform.evidence import EvidenceArtifactReference
from market_platform.instruments.identity import (
    CanonicalInstrument,
    CanonicalInstrumentId,
)
from market_platform.research import daily_technical_interpretation as classic
from market_platform.research.classic_daily_technical import (
    ClassicDailyTechnicalInterpretationPolicy,
)
from market_platform.research.daily_technical_interpretation import (
    DailyTechnicalDirectionalState,
    DailyTechnicalExtensionState,
    TechnicalComparisonEvidence,
    build_classic_comparison_evidence,
    classic_states,
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


def _copy_artifact(value: EvidenceArtifactReference) -> EvidenceArtifactReference:
    if type(value) is not EvidenceArtifactReference:
        raise TypeError("exact EvidenceArtifactReference required")
    value._validate()
    copied = replace(value)
    if copied != value:
        raise ValueError("artifact reference is noncanonical")
    return copied


@dataclass(frozen=True, slots=True, kw_only=True)
class PolygonCompletedDailyInterpretationRequest:
    """Five exact source selectors, never bearer authority or a history lookup."""

    artifact_reference: EvidenceArtifactReference
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
        _copy_artifact(self.artifact_reference)
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
    copied = CanonicalInstrumentId(value.instrument_id)
    if copied != value:
        raise ValueError("canonical instrument ID is noncanonical")
    return copied


def _copy_trading(value: TradingInstrumentIdentity) -> TradingInstrumentIdentity:
    if type(value) is not TradingInstrumentIdentity:
        raise TypeError("exact source trading identity required")
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
    interpretation_policy_identity: TechnicalPolicyIdentity
    source_quality: TechnicalAnalysisQuality
    source_warnings: tuple[TechnicalAnalysisWarning, ...]
    trend_direction: DailyTechnicalDirectionalState
    momentum_direction: DailyTechnicalDirectionalState
    volatility_state: VolatilityState
    extension_state: DailyTechnicalExtensionState
    comparison_evidence: tuple[TechnicalComparisonEvidence, ...]
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
                copy_technical_policy_identity(self.interpretation_policy_identity),
            ),
            ("comparison_evidence", deepcopy(self.comparison_evidence)),
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
        _check_policy(self.interpretation_policy_identity)
        for value, kind in (
            (self.source_quality, TechnicalAnalysisQuality),
            (self.trend_direction, DailyTechnicalDirectionalState),
            (self.momentum_direction, DailyTechnicalDirectionalState),
            (self.volatility_state, VolatilityState),
            (self.extension_state, DailyTechnicalExtensionState),
        ):
            if type(value) is not kind:
                raise TypeError("exact Interpretation state required")
        if type(self.source_warnings) is not tuple or any(
            type(item) is not TechnicalAnalysisWarning for item in self.source_warnings
        ):
            raise TypeError("exact source warning tuple required")
        if self.source_warnings != tuple(
            item for item in TechnicalAnalysisWarning if item in self.source_warnings
        ):
            raise ValueError(
                "source warnings must retain canonical order without duplicates"
            )
        if type(self.comparison_evidence) is not tuple:
            raise TypeError("exact comparison tuple required")
        for item in self.comparison_evidence:
            if type(item) is not TechnicalComparisonEvidence:
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
    expected_states = classic.classic_states(expected_source, expected_configuration)
    expected_comparisons = deepcopy(
        classic.build_classic_comparison_evidence(
            expected_source, expected_configuration
        )
    )
    expected = {
        "schema_version": GOVERNED_DAILY_TECHNICAL_INTERPRETATION_SCHEMA,
        "source_technical_occurrence": reference_before,
        "canonical_instrument_id": instrument.instrument_id.to_dict(),
        "source_trading_identity": instrument.trading_identity.to_dict(),
        "analysis_as_of": detached.evidence.analysis_as_of.isoformat(),
        "source_technical_analysis_snapshot_fingerprint": detached.fingerprint,
        "source_governed_dataset_fingerprint": source_governed_dataset_fingerprint,
        "source_research_dataset_content_fingerprint": (
            detached.evidence.dataset_content_fingerprint
        ),
        "interpretation_policy_identity": policy_before,
        "source_quality": detached.quality.value,
        "source_warnings": [item.value for item in detached.warnings],
        "trend_direction": expected_states[0].value,
        "momentum_direction": expected_states[1].value,
        "volatility_state": expected_states[2].value,
        "extension_state": expected_states[3].value,
        "comparison_evidence": [item.to_dict() for item in expected_comparisons],
    }

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
        interpretation_policy_identity=working_policy,
        source_quality=detached.quality,
        source_warnings=detached.warnings,
        trend_direction=trend,
        momentum_direction=momentum,
        volatility_state=volatility,
        extension_state=extension,
        comparison_evidence=comparisons,
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
    if type(result) is not GovernedDailyTechnicalInterpretation:
        raise TypeError("exact governed Interpretation content required")
    result._validate()
    if result._projection(fingerprint_floats=False) != expected:
        raise ValueError(
            "governed Interpretation source/semantic correspondence mismatch"
        )
    return result


__all__ = [
    "GOVERNED_DAILY_TECHNICAL_INTERPRETATION_SCHEMA",
    "PolygonCompletedDailyInterpretationRequest",
    "GovernedDailyTechnicalInterpretation",
    "interpret_governed_daily_technical_snapshot",
]
