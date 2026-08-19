from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

import market_platform.research as research
import market_platform.research.daily_instrument_integrity as integrity_module
from market_platform._fingerprint import canonical_fingerprint
from market_platform.application.instrument_mapping_codec import (
    load_trusted_instrument_mapping_registry,
)
from market_platform.data.capabilities import DataCapability
from market_platform.data.historical import HistoricalPriceSeries
from market_platform.data.providers.polygon import PolygonProvider
from market_platform.data.selection import ProviderCandidate, ProviderSelectionPolicy
from market_platform.data.service import MarketDataService
from market_platform.research import (
    DailyTechnicalAssessment,
    DailyTechnicalInterpretation,
    DailyTechnicalResearchRequest,
    DailyTechnicalStrategy,
    DailyTechnicalStrategyPolicy,
    IntegrityCheckedDailyTechnicalResearchWorkflow,
    ResearchTimeframe,
    assess_daily_technical_interpretation,
    construct_daily_technical_analysis_profile,
    derive_daily_technical_strategy,
    interpret_daily_technical_research,
)
from market_platform.research.classic_daily_technical import (
    ClassicDailyTechnicalAssessmentPolicy,
    ClassicDailyTechnicalInterpretationPolicy,
)
from market_platform.research.daily_technical_assessment import (
    DailyTechnicalAssessmentFindingKind,
    DailyTechnicalAssessmentOutcome,
    build_classic_assessment_findings,
    classic_assessment_outcome,
)
from market_platform.research.daily_technical_interpretation import (
    DailyTechnicalDirectionalState,
    DailyTechnicalExtensionState,
    TechnicalComparisonEvidence,
    TechnicalComparisonOperand,
    TechnicalComparisonOperandSource,
    TechnicalComparisonOperator,
    build_classic_comparison_evidence,
    classic_states,
)
from market_platform.research.interpretation import VolatilityState
from market_platform.research.technical_analysis import (
    TechnicalAnalysisQuality,
    TechnicalAnalysisWarning,
)
from market_platform.research.technical_policy import (
    CLASSIC_DAILY_TECHNICAL_ASSESSMENT_CONFIGURATION_SCHEMA,
    CLASSIC_DAILY_TECHNICAL_INTERPRETATION_CONFIGURATION_SCHEMA,
    ClassicDailyTechnicalAssessmentConfiguration,
    ClassicDailyTechnicalInterpretationConfiguration,
    TechnicalPolicyIdentity,
    TechnicalPolicyKind,
    copy_technical_policy_identity,
)
from market_platform.trading import TradingInstrumentIdentity


def _identity(
    configuration: ClassicDailyTechnicalInterpretationConfiguration | None = None,
    *,
    policy_id: str = "classic_daily_technical",
    revision: str = "1.0.0",
    schema: str = CLASSIC_DAILY_TECHNICAL_INTERPRETATION_CONFIGURATION_SCHEMA,
) -> TechnicalPolicyIdentity:
    return TechnicalPolicyIdentity(
        TechnicalPolicyKind.DAILY_TECHNICAL_INTERPRETATION,
        policy_id,
        revision,
        schema,
        configuration or ClassicDailyTechnicalInterpretationConfiguration(),
    )


def test_typed_configuration_and_identity_are_canonical() -> None:
    first = _identity()
    second = _identity()
    assert first.to_dict() == second.to_dict()
    assert first.fingerprint == second.fingerprint
    changed = (
        _identity(ClassicDailyTechnicalInterpretationConfiguration(rsi_neutral=51.0)),
        _identity(policy_id="other_policy"),
        _identity(revision="1.0.1"),
    )
    assert all(item.fingerprint != first.fingerprint for item in changed)
    assert ClassicDailyTechnicalAssessmentConfiguration().to_dict() == {}
    assessment = ClassicDailyTechnicalAssessmentPolicy().identity
    assert assessment.configuration_schema == (
        CLASSIC_DAILY_TECHNICAL_ASSESSMENT_CONFIGURATION_SCHEMA
    )


def test_policy_identity_requires_exact_kind_configuration_schema_pairing() -> None:
    interpretation = _identity()
    assessment = ClassicDailyTechnicalAssessmentPolicy().identity
    assert copy_technical_policy_identity(interpretation).to_dict() == (
        interpretation.to_dict()
    )
    assert copy_technical_policy_identity(assessment).to_dict() == assessment.to_dict()

    for identity, forged_schema in (
        (interpretation, CLASSIC_DAILY_TECHNICAL_ASSESSMENT_CONFIGURATION_SCHEMA),
        (assessment, CLASSIC_DAILY_TECHNICAL_INTERPRETATION_CONFIGURATION_SCHEMA),
    ):
        object.__setattr__(identity, "configuration_schema", forged_schema)
        object.__setattr__(
            identity,
            "fingerprint",
            canonical_fingerprint(identity._fingerprint_payload()),
        )
        with pytest.raises(ValueError, match="do not correspond"):
            identity._validate()
        with pytest.raises(ValueError, match="do not correspond"):
            copy_technical_policy_identity(identity)


def test_policy_identity_rejects_configuration_type_schema_mismatch() -> None:
    cases = (
        (
            _identity(),
            ClassicDailyTechnicalAssessmentConfiguration(),
            CLASSIC_DAILY_TECHNICAL_ASSESSMENT_CONFIGURATION_SCHEMA,
        ),
        (
            ClassicDailyTechnicalAssessmentPolicy().identity,
            ClassicDailyTechnicalInterpretationConfiguration(),
            CLASSIC_DAILY_TECHNICAL_INTERPRETATION_CONFIGURATION_SCHEMA,
        ),
    )
    for identity, configuration, schema in cases:
        object.__setattr__(identity, "configuration", configuration)
        object.__setattr__(identity, "configuration_schema", schema)
        object.__setattr__(
            identity,
            "fingerprint",
            canonical_fingerprint(identity._fingerprint_payload()),
        )
        with pytest.raises(ValueError, match="do not correspond"):
            identity._validate()


@pytest.mark.parametrize(
    "values",
    [
        {"rsi_depressed": 50.0},
        {"rsi_elevated": 101.0},
        {"realized_volatility_low": 0.3, "realized_volatility_high": 0.3},
        {"ema20_extension_band_percent": 0.0},
        {"rsi_neutral": True},
        {"rsi_neutral": float("inf")},
        {"rsi_neutral": float("nan")},
    ],
)
def test_typed_configuration_rejects_invalid_values(values: dict[str, object]) -> None:
    with pytest.raises((TypeError, ValueError)):
        ClassicDailyTechnicalInterpretationConfiguration(**values)  # type: ignore[arg-type]


def test_configuration_negative_zero_convention() -> None:
    configuration = ClassicDailyTechnicalInterpretationConfiguration(
        realized_volatility_low=-0.0
    )
    assert configuration.realized_volatility_low == 0.0
    assert str(configuration.realized_volatility_low) == "0.0"
    object.__setattr__(configuration, "realized_volatility_low", -0.0)
    with pytest.raises(ValueError, match="canonical"):
        configuration.to_dict()


def _operand(
    source: TechnicalComparisonOperandSource, field: str, value: float
) -> TechnicalComparisonOperand:
    return TechnicalComparisonOperand(source, field, value)


def test_closed_operand_grammar_and_operator_validation() -> None:
    valid = {
        TechnicalComparisonOperandSource.TECHNICAL_ANALYSIS_SNAPSHOT: (
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
        TechnicalComparisonOperandSource.INTERPRETATION_POLICY_CONFIGURATION: (
            "rsi_neutral",
            "rsi_elevated",
            "rsi_depressed",
            "realized_volatility_low",
            "realized_volatility_high",
            "ema20_extension_band_percent",
        ),
        TechnicalComparisonOperandSource.INTERPRETATION_POLICY_DERIVED: (
            "negative_ema20_extension_band_percent",
        ),
    }
    for source, fields in valid.items():
        for field in fields:
            assert _operand(source, field, 1.0).field == field
    with pytest.raises((TypeError, ValueError)):
        TechnicalComparisonOperand("unknown", "ema_8", 1.0)  # type: ignore[arg-type]
    for source in valid:
        with pytest.raises(ValueError, match="field"):
            _operand(source, "unknown", 1.0)
    left = _operand(
        TechnicalComparisonOperandSource.TECHNICAL_ANALYSIS_SNAPSHOT,
        "rsi_14",
        50.0,
    )
    right = _operand(
        TechnicalComparisonOperandSource.INTERPRETATION_POLICY_CONFIGURATION,
        "rsi_neutral",
        50.0,
    )
    expected = {
        TechnicalComparisonOperator.GREATER_THAN: False,
        TechnicalComparisonOperator.GREATER_THAN_OR_EQUAL: True,
        TechnicalComparisonOperator.LESS_THAN: False,
        TechnicalComparisonOperator.LESS_THAN_OR_EQUAL: True,
    }
    for operator, satisfied in expected.items():
        TechnicalComparisonEvidence("comparison", left, operator, right, satisfied)
        with pytest.raises(ValueError, match="satisfied"):
            TechnicalComparisonEvidence(
                "comparison", left, operator, right, not satisfied
            )


def _snapshot_values(**changes: float | None) -> SimpleNamespace:
    values: dict[str, object] = {
        "ema_8": 12.0,
        "ema_20": 11.0,
        "latest_close": 20.0,
        "ema_144": 10.0,
        "ema_169": 9.0,
        "macd_line": 2.0,
        "macd_signal": 1.0,
        "rsi_14": 60.0,
        "realized_volatility": 0.2,
        "volatility_references": SimpleNamespace(distance_from_ema20_percent=0.0),
    }
    distance = changes.pop("distance", None)
    values.update(changes)
    if distance is not None:
        values["volatility_references"] = SimpleNamespace(
            distance_from_ema20_percent=distance
        )
    return SimpleNamespace(**values)


def test_exact_comparison_inventory_and_extension_boundaries() -> None:
    configuration = ClassicDailyTechnicalInterpretationConfiguration()
    snapshot = _snapshot_values()
    evidence = build_classic_comparison_evidence(snapshot, configuration)  # type: ignore[arg-type]
    assert [item.evidence_id for item in evidence] == [
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
    ]
    assert evidence[-1].right_operand.value == -5.0
    for distance, expected in (
        (5.0001, DailyTechnicalExtensionState.ABOVE_REFERENCE_BAND),
        (5.0, DailyTechnicalExtensionState.WITHIN_REFERENCE_BAND),
        (-5.0, DailyTechnicalExtensionState.WITHIN_REFERENCE_BAND),
        (-5.0001, DailyTechnicalExtensionState.BELOW_REFERENCE_BAND),
    ):
        assert (
            classic_states(_snapshot_values(distance=distance), configuration)[3]
            is expected
        )  # type: ignore[arg-type]
    omitted = build_classic_comparison_evidence(
        _snapshot_values(rsi_14=None),
        configuration,  # type: ignore[arg-type]
    )
    assert not any("rsi" in item.evidence_id for item in omitted)


def test_classic_state_boundaries() -> None:
    configuration = ClassicDailyTechnicalInterpretationConfiguration()
    positive = classic_states(_snapshot_values(), configuration)  # type: ignore[arg-type]
    assert positive[:2] == (
        DailyTechnicalDirectionalState.POSITIVE,
        DailyTechnicalDirectionalState.POSITIVE,
    )
    negative = classic_states(
        _snapshot_values(
            ema_8=8.0,
            ema_20=9.0,
            latest_close=5.0,
            ema_144=10.0,
            ema_169=11.0,
            macd_line=-2.0,
            macd_signal=-1.0,
            rsi_14=40.0,
        ),
        configuration,
    )  # type: ignore[arg-type]
    assert negative[:2] == (
        DailyTechnicalDirectionalState.NEGATIVE,
        DailyTechnicalDirectionalState.NEGATIVE,
    )
    assert (
        classic_states(_snapshot_values(ema_8=11.0), configuration)[0]
        is DailyTechnicalDirectionalState.MIXED
    )  # type: ignore[arg-type]
    assert (
        classic_states(_snapshot_values(ema_8=None), configuration)[0]
        is DailyTechnicalDirectionalState.UNAVAILABLE
    )  # type: ignore[arg-type]
    assert (
        classic_states(_snapshot_values(macd_line=1.0), configuration)[1]
        is DailyTechnicalDirectionalState.MIXED
    )  # type: ignore[arg-type]
    assert (
        classic_states(_snapshot_values(rsi_14=None), configuration)[1]
        is DailyTechnicalDirectionalState.UNAVAILABLE
    )  # type: ignore[arg-type]
    for value, expected in (
        (0.149, VolatilityState.LOW),
        (0.15, VolatilityState.NORMAL),
        (0.299, VolatilityState.NORMAL),
        (0.30, VolatilityState.HIGH),
        (None, VolatilityState.UNAVAILABLE),
    ):
        assert (
            classic_states(_snapshot_values(realized_volatility=value), configuration)[
                2
            ]
            is expected
        )  # type: ignore[arg-type]


def _service() -> MarketDataService:
    provider = PolygonProvider(api_key="unused")
    return MarketDataService(
        ProviderSelectionPolicy(
            [
                ProviderCandidate(
                    "polygon",
                    provider,
                    frozenset({DataCapability.DAILY_PRICES}),
                )
            ],
            ["polygon"],
        )
    )


def _registry(tmp_path: Path):
    document = {
        "schema_version": "trusted_instrument_mapping_document/v1",
        "source": {
            "source_id": "test",
            "source_version": "1",
            "configuration_fingerprint": None,
        },
        "instruments": [
            {
                "instrument_id": "test.security",
                "trading_identity": {"symbol": "TEST", "venue": "NASDAQ"},
                "asset_class": "equity",
                "trading_currency": "USD",
            }
        ],
        "mappings": [
            {
                "external_identity": {
                    "namespace": "polygon",
                    "external_symbol": "TEST",
                    "external_venue": "NASDAQ",
                },
                "canonical_instrument_id": "test.security",
                "valid_from": "2020-01-01",
                "expires_at": None,
            }
        ],
    }
    path = tmp_path / "technical_mapping.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return load_trusted_instrument_mapping_registry(path)


def _verified_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, bars: int = 300
):
    dates = pd.date_range(end="2026-08-09", periods=bars, tz=UTC)
    rows = []
    for index, timestamp in enumerate(dates):
        close = 100.0 + index
        rows.append(
            {
                "symbol": "TEST",
                "timestamp": timestamp,
                "open": close,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 1000.0,
                "provider": "polygon",
            }
        )
    prices = HistoricalPriceSeries(
        pd.DataFrame(rows), symbol="TEST", provider="polygon"
    )

    async def acquire(service: object, request: object) -> HistoricalPriceSeries:
        return prices

    monkeypatch.setattr(integrity_module, "_acquire_polygon_daily_prices", acquire)
    request = DailyTechnicalResearchRequest(
        TradingInstrumentIdentity("TEST", "NASDAQ"),
        ResearchTimeframe.DAILY,
        "polygon",
        datetime(2026, 8, 10, tzinfo=UTC),
        construct_daily_technical_analysis_profile(),
    )
    return asyncio.run(
        IntegrityCheckedDailyTechnicalResearchWorkflow(_service()).run(
            request, _registry(tmp_path)
        )
    )


def test_interpretation_and_assessment_runners_propagate_exact_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    verified = _verified_result(tmp_path, monkeypatch)
    interpretation = interpret_daily_technical_research(
        verified, ClassicDailyTechnicalInterpretationPolicy()
    )
    snapshot = verified.research.snapshot
    assert interpretation.source_quality is snapshot.quality
    assert interpretation.source_warnings == snapshot.warnings
    assert interpretation.source_technical_analysis_snapshot_fingerprint == (
        snapshot.fingerprint
    )
    assert interpretation.source_daily_instrument_integrity_evidence_fingerprint == (
        verified.integrity.fingerprint
    )
    assert interpretation.to_dict() == interpretation.to_dict()
    assert interpretation.fingerprint == canonical_fingerprint(
        interpretation._fingerprint_payload()
    )
    assert not {
        "findings",
        "conflicts",
        "cautions",
        "score",
        "confidence",
        "recommendation",
        "action",
        "side",
    }.intersection(interpretation.to_dict())
    assessment = assess_daily_technical_interpretation(
        interpretation, ClassicDailyTechnicalAssessmentPolicy()
    )
    assert assessment.source_interpretation_fingerprint == interpretation.fingerprint
    assert assessment.to_dict() == assessment.to_dict()
    assert assessment.outcome is DailyTechnicalAssessmentOutcome.MIXED
    assert [item.code for item in assessment.findings] == ["rsi_elevated"]


def _replace_interpretation(
    source: DailyTechnicalInterpretation, **changes: object
) -> DailyTechnicalInterpretation:
    values = {
        "canonical_instrument_id": source.canonical_instrument_id,
        "requested_trading_identity": source.requested_trading_identity,
        "analysis_as_of": source.analysis_as_of,
        "source_technical_analysis_snapshot_fingerprint": (
            source.source_technical_analysis_snapshot_fingerprint
        ),
        "source_daily_instrument_integrity_evidence_fingerprint": (
            source.source_daily_instrument_integrity_evidence_fingerprint
        ),
        "interpretation_policy_identity": source.interpretation_policy_identity,
        "source_quality": source.source_quality,
        "source_warnings": source.source_warnings,
        "trend_direction": source.trend_direction,
        "momentum_direction": source.momentum_direction,
        "volatility_state": source.volatility_state,
        "extension_state": source.extension_state,
        "comparison_evidence": source.comparison_evidence,
    }
    values.update(changes)
    return DailyTechnicalInterpretation(**values)  # type: ignore[arg-type]


def test_runner_rejects_missing_reordered_or_fabricated_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    verified = _verified_result(tmp_path, monkeypatch)
    base_policy = ClassicDailyTechnicalInterpretationPolicy()
    valid = base_policy.interpret(verified)

    class Policy:
        identity = base_policy.identity

        def __init__(self, evidence: tuple[TechnicalComparisonEvidence, ...]) -> None:
            self.evidence = evidence

        def interpret(self, value: object) -> DailyTechnicalInterpretation:
            return _replace_interpretation(valid, comparison_evidence=self.evidence)

    variants = (
        valid.comparison_evidence[:-1],
        tuple(reversed(valid.comparison_evidence)),
        valid.comparison_evidence + (valid.comparison_evidence[0],),
    )
    for evidence in variants:
        with pytest.raises(ValueError):
            interpret_daily_technical_research(verified, Policy(evidence))  # type: ignore[arg-type]


def test_complete_warning_tuple_is_defensively_enforced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    verified = _verified_result(tmp_path, monkeypatch, bars=10)
    base_policy = ClassicDailyTechnicalInterpretationPolicy()
    valid = base_policy.interpret(verified)
    assert valid.source_warnings == (
        TechnicalAnalysisWarning.INSUFFICIENT_PROFILE_HISTORY,
    )

    class Policy:
        identity = base_policy.identity

        def __init__(self, **changes: object) -> None:
            self.changes = changes

        def interpret(self, value: object) -> DailyTechnicalInterpretation:
            return _replace_interpretation(valid, **self.changes)

    variants = (
        {"source_warnings": ()},
        {
            "source_warnings": (
                TechnicalAnalysisWarning.STALE_EVIDENCE,
                TechnicalAnalysisWarning.INSUFFICIENT_PROFILE_HISTORY,
            )
        },
        {"source_warnings": (TechnicalAnalysisWarning.STALE_EVIDENCE,)},
        {
            "source_warnings": (
                TechnicalAnalysisWarning.INSUFFICIENT_PROFILE_HISTORY,
                TechnicalAnalysisWarning.INSUFFICIENT_PROFILE_HISTORY,
            )
        },
        {"source_quality": TechnicalAnalysisQuality.COMPLETE},
    )
    for changes in variants:
        with pytest.raises(ValueError, match="quality|warnings"):
            interpret_daily_technical_research(  # type: ignore[arg-type]
                verified, Policy(**changes)
            )


def test_runner_rejects_direct_derived_operand_value_tampering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    verified = _verified_result(tmp_path, monkeypatch)
    base_policy = ClassicDailyTechnicalInterpretationPolicy()
    forged = base_policy.interpret(verified)
    derived = forged.comparison_evidence[-1].right_operand
    assert derived.field == "negative_ema20_extension_band_percent"
    object.__setattr__(derived, "value", derived.value - 1.0)
    object.__setattr__(
        forged, "fingerprint", canonical_fingerprint(forged._fingerprint_payload())
    )
    forged._validate()

    class Policy:
        identity = base_policy.identity

        def interpret(self, value: object) -> DailyTechnicalInterpretation:
            return forged

    with pytest.raises(ValueError, match="comparison evidence"):
        interpret_daily_technical_research(verified, Policy())  # type: ignore[arg-type]


def test_interpretation_runner_rejects_persistent_source_mutations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mutations = (
        ("quality", TechnicalAnalysisQuality.DEGRADED),
        ("warnings", (TechnicalAnalysisWarning.STALE_EVIDENCE,)),
        ("rsi_14", 55.0),
        ("fingerprint", "sha256:" + "0" * 64),
    )
    for field, changed in mutations:
        verified = _verified_result(tmp_path, monkeypatch)
        base_policy = ClassicDailyTechnicalInterpretationPolicy()
        valid = base_policy.interpret(verified)

        class Policy:
            identity = base_policy.identity

            def __init__(
                self,
                owner: object,
                name: str,
                value: object,
                result: DailyTechnicalInterpretation,
            ) -> None:
                self.owner = owner
                self.name = name
                self.value = value
                self.result = result

            def interpret(self, value: object) -> DailyTechnicalInterpretation:
                object.__setattr__(self.owner, self.name, self.value)
                return self.result

        with pytest.raises(ValueError):
            interpret_daily_technical_research(  # type: ignore[arg-type]
                verified, Policy(verified.research.snapshot, field, changed, valid)
            )

    identity_mutations = (
        ("integrity", "fingerprint", "sha256:" + "1" * 64),
        ("requested", "symbol", "OTHER"),
        ("canonical", "instrument_id", "other.security"),
    )
    for target, field, changed in identity_mutations:
        verified = _verified_result(tmp_path, monkeypatch)
        base_policy = ClassicDailyTechnicalInterpretationPolicy()
        valid = base_policy.interpret(verified)
        owner = {
            "integrity": verified.integrity,
            "requested": verified.integrity.requested_trading_identity,
            "canonical": verified.integrity.canonical_instrument_id,
        }[target]

        class Policy:
            identity = base_policy.identity

            def __init__(
                self,
                owner: object,
                name: str,
                value: object,
                result: DailyTechnicalInterpretation,
            ) -> None:
                self.owner = owner
                self.name = name
                self.value = value
                self.result = result

            def interpret(self, value: object) -> DailyTechnicalInterpretation:
                object.__setattr__(self.owner, self.name, self.value)
                return self.result

        with pytest.raises(ValueError):
            interpret_daily_technical_research(  # type: ignore[arg-type]
                verified, Policy(owner, field, changed, valid)
            )


def test_interpretation_runner_rejects_coherently_refingerprinted_source_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    verified = _verified_result(tmp_path, monkeypatch)
    base_policy = ClassicDailyTechnicalInterpretationPolicy()

    class Policy:
        identity = base_policy.identity

        def interpret(self, value: object) -> DailyTechnicalInterpretation:
            snapshot = verified.research.snapshot
            object.__setattr__(snapshot, "rsi_14", 55.0)
            object.__setattr__(
                snapshot,
                "fingerprint",
                canonical_fingerprint(snapshot._fingerprint_payload()),
            )
            snapshot._validate()
            return base_policy.interpret(verified)

    with pytest.raises(ValueError, match="source drifted"):
        interpret_daily_technical_research(verified, Policy())  # type: ignore[arg-type]


def test_interpretation_runner_accepts_source_mutation_then_exact_reversion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    verified = _verified_result(tmp_path, monkeypatch)
    base_policy = ClassicDailyTechnicalInterpretationPolicy()
    expected = base_policy.interpret(verified)

    class Policy:
        identity = base_policy.identity

        def interpret(self, value: object) -> DailyTechnicalInterpretation:
            snapshot = verified.research.snapshot
            original = snapshot.quality
            object.__setattr__(snapshot, "quality", TechnicalAnalysisQuality.DEGRADED)
            object.__setattr__(snapshot, "quality", original)
            return expected

    assert interpret_daily_technical_research(verified, Policy()) is expected  # type: ignore[arg-type]


def test_findings_coexist_and_outcome_precedence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    verified = _verified_result(tmp_path, monkeypatch)
    interpretation = ClassicDailyTechnicalInterpretationPolicy().interpret(verified)
    evidence = {item.evidence_id: item for item in interpretation.comparison_evidence}
    selected = tuple(
        evidence[item]
        for item in (
            "trend_ema8_above_ema20",
            "trend_close_above_ema144",
            "trend_close_above_ema169",
            "momentum_macd_line_below_signal",
            "momentum_rsi_below_neutral",
            "rsi_at_or_above_elevated",
            "extension_above_positive_band",
            "volatility_at_or_above_high",
        )
        if item in evidence
    )
    for item in selected:
        object.__setattr__(item, "satisfied", True)
    synthetic = SimpleNamespace(
        trend_direction=DailyTechnicalDirectionalState.POSITIVE,
        momentum_direction=DailyTechnicalDirectionalState.NEGATIVE,
        volatility_state=VolatilityState.UNAVAILABLE,
        extension_state=DailyTechnicalExtensionState.UNAVAILABLE,
        comparison_evidence=selected,
        source_quality=TechnicalAnalysisQuality.DEGRADED,
        source_warnings=(
            TechnicalAnalysisWarning.INSUFFICIENT_PROFILE_HISTORY,
            TechnicalAnalysisWarning.STALE_EVIDENCE,
        ),
    )
    findings = build_classic_assessment_findings(synthetic)  # type: ignore[arg-type]
    assert [(item.kind.value, item.code) for item in findings] == [
        ("conflict", "direction_opposition"),
        ("caution", "rsi_elevated"),
        ("caution", "ema20_above_reference_band"),
        ("caution", "high_realized_volatility"),
        ("caution", "source_quality_degraded"),
        ("caution", "source_warning_insufficient_profile_history"),
        ("caution", "source_warning_stale_evidence"),
    ]
    assert all(not item.comparison_evidence_ids for item in findings[-3:])
    assert classic_assessment_outcome(synthetic, findings) is (
        DailyTechnicalAssessmentOutcome.INSUFFICIENT_DATA
    )
    assert findings[0].kind is DailyTechnicalAssessmentFindingKind.CONFLICT


def test_runner_end_to_end_retains_source_cautions_under_insufficient_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    interpretation = interpret_daily_technical_research(
        _verified_result(tmp_path, monkeypatch, bars=10),
        ClassicDailyTechnicalInterpretationPolicy(),
    )
    assessment = assess_daily_technical_interpretation(
        interpretation, ClassicDailyTechnicalAssessmentPolicy()
    )
    assert assessment.outcome is DailyTechnicalAssessmentOutcome.INSUFFICIENT_DATA
    codes = [item.code for item in assessment.findings]
    assert "source_quality_degraded" in codes
    assert "source_warning_insufficient_profile_history" in codes
    assert all(
        not item.comparison_evidence_ids
        for item in assessment.findings
        if item.code.startswith("source_")
    )


def test_same_object_identity_is_accepted_and_drift_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    verified = _verified_result(tmp_path, monkeypatch)
    base = ClassicDailyTechnicalInterpretationPolicy()

    class CountingPolicy:
        def __init__(self, mutate: bool) -> None:
            self.identity = base.identity
            self.calls = 0
            self.mutate = mutate

        def interpret(self, value: object) -> DailyTechnicalInterpretation:
            self.calls += 1
            result = base.interpret(verified)
            if self.mutate:
                object.__setattr__(self.identity, "policy_id", "mutated_policy")
                object.__setattr__(
                    self.identity,
                    "fingerprint",
                    canonical_fingerprint(self.identity._fingerprint_payload()),
                )
            return result

    stable = CountingPolicy(False)
    interpret_daily_technical_research(verified, stable)  # type: ignore[arg-type]
    assert stable.calls == 1
    drifting = CountingPolicy(True)
    with pytest.raises(ValueError, match="drifted"):
        interpret_daily_technical_research(verified, drifting)  # type: ignore[arg-type]
    assert drifting.calls == 1


def test_assessment_runner_identity_drift_and_nondefault_config_compatibility(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    verified = _verified_result(tmp_path, monkeypatch)
    interpretation = interpret_daily_technical_research(
        verified,
        ClassicDailyTechnicalInterpretationPolicy(
            ClassicDailyTechnicalInterpretationConfiguration(
                rsi_neutral=55.0,
                rsi_elevated=80.0,
                rsi_depressed=20.0,
                realized_volatility_low=0.10,
                realized_volatility_high=0.40,
                ema20_extension_band_percent=7.0,
            )
        ),
    )
    base = ClassicDailyTechnicalAssessmentPolicy()

    class Policy:
        def __init__(self, mutate: bool) -> None:
            self.identity = base.identity
            self.mutate = mutate
            self.calls = 0

        def assess(self, value: object) -> DailyTechnicalAssessment:
            self.calls += 1
            result = base.assess(interpretation)
            if self.mutate:
                object.__setattr__(self.identity, "behavioral_revision", "1.0.1")
                object.__setattr__(
                    self.identity,
                    "fingerprint",
                    canonical_fingerprint(self.identity._fingerprint_payload()),
                )
            return result

    stable = Policy(False)
    assess_daily_technical_interpretation(interpretation, stable)  # type: ignore[arg-type]
    assert stable.calls == 1
    drifting = Policy(True)
    with pytest.raises(ValueError, match="drifted"):
        assess_daily_technical_interpretation(interpretation, drifting)  # type: ignore[arg-type]
    assert drifting.calls == 1


def test_assessment_runner_rejects_persistent_interpretation_mutations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mutations = (
        ("source_quality", TechnicalAnalysisQuality.DEGRADED),
        ("source_warnings", (TechnicalAnalysisWarning.STALE_EVIDENCE,)),
        ("trend_direction", DailyTechnicalDirectionalState.NEGATIVE),
        ("momentum_direction", DailyTechnicalDirectionalState.NEGATIVE),
        ("volatility_state", VolatilityState.HIGH),
        ("extension_state", DailyTechnicalExtensionState.ABOVE_REFERENCE_BAND),
        ("fingerprint", "sha256:" + "2" * 64),
    )
    for field, changed in mutations:
        verified = _verified_result(tmp_path, monkeypatch)
        interpretation = interpret_daily_technical_research(
            verified, ClassicDailyTechnicalInterpretationPolicy()
        )
        base_policy = ClassicDailyTechnicalAssessmentPolicy()
        valid = base_policy.assess(interpretation)

        class Policy:
            identity = base_policy.identity

            def __init__(
                self,
                source: DailyTechnicalInterpretation,
                name: str,
                value: object,
                result: DailyTechnicalAssessment,
            ) -> None:
                self.source = source
                self.name = name
                self.value = value
                self.result = result

            def assess(self, value: object) -> DailyTechnicalAssessment:
                object.__setattr__(self.source, self.name, self.value)
                return self.result

        with pytest.raises(ValueError):
            assess_daily_technical_interpretation(  # type: ignore[arg-type]
                interpretation, Policy(interpretation, field, changed, valid)
            )

    interpretation = interpret_daily_technical_research(
        _verified_result(tmp_path, monkeypatch),
        ClassicDailyTechnicalInterpretationPolicy(),
    )
    base_policy = ClassicDailyTechnicalAssessmentPolicy()
    valid = base_policy.assess(interpretation)

    class EvidencePolicy:
        identity = base_policy.identity

        def assess(self, value: object) -> DailyTechnicalAssessment:
            object.__setattr__(
                interpretation,
                "comparison_evidence",
                tuple(reversed(interpretation.comparison_evidence)),
            )
            return valid

    with pytest.raises(ValueError):
        assess_daily_technical_interpretation(  # type: ignore[arg-type]
            interpretation, EvidencePolicy()
        )


def test_assessment_runner_rejects_coherent_drift_and_mutated_source_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    interpretation = interpret_daily_technical_research(
        _verified_result(tmp_path, monkeypatch),
        ClassicDailyTechnicalInterpretationPolicy(),
    )
    base_policy = ClassicDailyTechnicalAssessmentPolicy()

    class Policy:
        identity = base_policy.identity

        def assess(self, value: object) -> DailyTechnicalAssessment:
            object.__setattr__(
                interpretation, "source_quality", TechnicalAnalysisQuality.DEGRADED
            )
            object.__setattr__(
                interpretation,
                "fingerprint",
                canonical_fingerprint(interpretation._fingerprint_payload()),
            )
            interpretation._validate()
            return base_policy.assess(interpretation)

    with pytest.raises(ValueError, match="source interpretation drifted"):
        assess_daily_technical_interpretation(  # type: ignore[arg-type]
            interpretation, Policy()
        )


def test_assessment_runner_accepts_interpretation_mutation_then_exact_reversion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    interpretation = interpret_daily_technical_research(
        _verified_result(tmp_path, monkeypatch),
        ClassicDailyTechnicalInterpretationPolicy(),
    )
    base_policy = ClassicDailyTechnicalAssessmentPolicy()
    expected = base_policy.assess(interpretation)

    class Policy:
        identity = base_policy.identity

        def assess(self, value: object) -> DailyTechnicalAssessment:
            original = interpretation.trend_direction
            object.__setattr__(
                interpretation,
                "trend_direction",
                DailyTechnicalDirectionalState.NEGATIVE,
            )
            object.__setattr__(interpretation, "trend_direction", original)
            return expected

    assert assess_daily_technical_interpretation(  # type: ignore[arg-type]
        interpretation, Policy()
    ) is expected


def test_v073_runner_boundaries_reject_exact_model_subclasses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    verified = _verified_result(tmp_path, monkeypatch)

    class VerifiedSubclass(type(verified)):
        pass

    with pytest.raises(TypeError, match="exact integrity-checked"):
        interpret_daily_technical_research(  # type: ignore[arg-type]
            object.__new__(VerifiedSubclass),
            ClassicDailyTechnicalInterpretationPolicy(),
        )

    class InterpretationSubclass(DailyTechnicalInterpretation):
        pass

    with pytest.raises(TypeError, match="exact DailyTechnicalInterpretation"):
        assess_daily_technical_interpretation(  # type: ignore[arg-type]
            object.__new__(InterpretationSubclass),
            ClassicDailyTechnicalAssessmentPolicy(),
        )

    interpretation_policy = ClassicDailyTechnicalInterpretationPolicy()
    valid_interpretation = interpretation_policy.interpret(verified)
    interpretation_subclass = object.__new__(InterpretationSubclass)
    for name in DailyTechnicalInterpretation.__dataclass_fields__:
        object.__setattr__(
            interpretation_subclass, name, getattr(valid_interpretation, name)
        )

    class InterpretationPolicy:
        identity = interpretation_policy.identity

        def interpret(self, value: object) -> DailyTechnicalInterpretation:
            return interpretation_subclass

    with pytest.raises(TypeError, match="policy must return an exact"):
        interpret_daily_technical_research(  # type: ignore[arg-type]
            verified, InterpretationPolicy()
        )

    class AssessmentSubclass(DailyTechnicalAssessment):
        pass

    assessment_policy = ClassicDailyTechnicalAssessmentPolicy()
    valid_assessment = assessment_policy.assess(valid_interpretation)
    assessment_subclass = object.__new__(AssessmentSubclass)
    for name in DailyTechnicalAssessment.__dataclass_fields__:
        object.__setattr__(assessment_subclass, name, getattr(valid_assessment, name))

    class AssessmentPolicy:
        identity = assessment_policy.identity

        def assess(self, value: object) -> DailyTechnicalAssessment:
            return assessment_subclass

    with pytest.raises(TypeError, match="policy must return an exact"):
        assess_daily_technical_interpretation(  # type: ignore[arg-type]
            valid_interpretation, AssessmentPolicy()
        )


def test_root_exports_are_exact_append_and_models_are_non_actionable() -> None:
    assert len(research.__all__) == 93
    assert research.__all__[-9:-3] == [
        "DailyTechnicalInterpretationPolicy",
        "DailyTechnicalAssessmentPolicy",
        "DailyTechnicalInterpretation",
        "DailyTechnicalAssessment",
        "interpret_daily_technical_research",
        "assess_daily_technical_interpretation",
    ]
    assert research.__all__[-3:] == [
        "DailyTechnicalStrategyPolicy",
        "DailyTechnicalStrategy",
        "derive_daily_technical_strategy",
    ]
    assert research.DailyTechnicalStrategyPolicy is DailyTechnicalStrategyPolicy
    assert research.DailyTechnicalStrategy is DailyTechnicalStrategy
    assert research.derive_daily_technical_strategy is derive_daily_technical_strategy
    non_root_strategy_exports = {
        "DailyTechnicalStrategyMode",
        "DailyTechnicalStrategyRuleCode",
        "ClassicDailyTechnicalStrategyPolicy",
        "ClassicDailyTechnicalStrategyConfiguration",
        "TechnicalPolicyKind",
        "TechnicalPolicyIdentity",
    }
    assert non_root_strategy_exports.isdisjoint(research.__all__)
    assert all(not hasattr(research, name) for name in non_root_strategy_exports)
    assert not {
        "recommendation",
        "action",
        "side",
        "entry",
        "stop",
        "target",
        "quantity",
        "account",
        "portfolio",
    }.intersection(DailyTechnicalInterpretation.__dataclass_fields__)
    assert not {
        "recommendation",
        "action",
        "side",
        "score",
        "confidence",
    }.intersection(DailyTechnicalAssessment.__dataclass_fields__)
