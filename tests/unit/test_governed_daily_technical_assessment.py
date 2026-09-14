from __future__ import annotations

import ast
from copy import copy, deepcopy
from dataclasses import FrozenInstanceError, fields, replace
from datetime import UTC, datetime, timedelta, timezone
from enum import Enum, IntEnum, StrEnum
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_governed_daily_technical_interpretation import assert_enum_free, public_graph

from market_platform._fingerprint import canonical_fingerprint
from market_platform.instruments.identity import CanonicalInstrumentId
from market_platform.research import daily_technical_assessment as classic
from market_platform.research import daily_technical_interpretation as legacy
from market_platform.research import governed_daily_technical_assessment as g
from market_platform.research import governed_daily_technical_interpretation as gi
from market_platform.research.classic_daily_technical import (
    ClassicDailyTechnicalAssessmentPolicy,
)
from market_platform.research.interpretation import VolatilityState
from market_platform.research.technical_analysis import (
    TechnicalAnalysisQuality,
    TechnicalAnalysisWarning,
)
from market_platform.research.technical_policy import (
    ClassicDailyTechnicalInterpretationConfiguration,
)
from market_platform.trading.instrument import TradingInstrumentIdentity

FP = "sha256:" + "a" * 64
POSITIVE_SUPPORT = (
    "trend_ema8_above_ema20",
    "trend_close_above_ema144",
    "trend_close_above_ema169",
    "momentum_macd_line_below_signal",
    "momentum_rsi_below_neutral",
)
NEGATIVE_SUPPORT = (
    "trend_ema8_below_ema20",
    "trend_close_below_ema144",
    "trend_close_below_ema169",
    "momentum_macd_line_above_signal",
    "momentum_rsi_at_or_above_neutral",
)
CAUTION_SUPPORT = (
    ("rsi_elevated", "rsi_at_or_above_elevated"),
    ("rsi_depressed", "rsi_at_or_below_depressed"),
    ("ema20_above_reference_band", "extension_above_positive_band"),
    ("ema20_below_reference_band", "extension_below_negative_band"),
    ("high_realized_volatility", "volatility_at_or_above_high"),
)
CODES = (
    "direction_opposition",
    *(code for code, _ in CAUTION_SUPPORT),
    "source_quality_degraded",
    "source_warning_insufficient_profile_history",
    "source_warning_stale_evidence",
)


def artifact():
    return gi.GovernedTechnicalArtifactReference(
        artifact_id="test:detached",
        artifact_version="1.0.0",
        artifact_fingerprint=FP,
        information_class="source_observation",
        authority="external_origin",
    )


def occurrence(**changes):
    return g.PolygonCompletedDailyAssessmentRequest(
        **(
            dict(
                artifact_reference=artifact(),
                interpretation_history_namespace_id=(
                    "polygon_completed_daily_interpretation_history:" + "1" * 32
                ),
                interpretation_history_sequence=1,
                interpretation_execution_id="polygon_completed_daily_interpretation:"
                + "2" * 32,
                interpretation_fingerprint="sha256:" + "b" * 64,
            )
            | changes
        )
    )


def comparison(evidence_id, satisfied=True):
    # Synthetic retained truth, with valid scalar/relational contracts. This does
    # not claim the operands or states came from a technical publication.
    return gi.GovernedTechnicalComparisonEvidence(
        evidence_id,
        gi.GovernedTechnicalComparisonOperand(
            "technical_analysis_snapshot", "ema_8", 2.0 if satisfied else 0.0
        ),
        "greater_than",
        gi.GovernedTechnicalComparisonOperand(
            "technical_analysis_snapshot", "ema_20", 1.0
        ),
        satisfied,
    )


def source(*, truths=(), false=(), **changes):
    comparison_ids = gi._COMPARISON_IDS
    return gi.GovernedDailyTechnicalInterpretation(
        **(
            dict(
                source_technical_occurrence=gi.PolygonCompletedDailyInterpretationRequest(
                    artifact_reference=artifact(),
                    technical_history_namespace_id="polygon_completed_daily_technical_history:"
                    + "3" * 32,
                    technical_history_sequence=1,
                    technical_execution_id="polygon_completed_daily_technical:"
                    + "4" * 32,
                    technical_fingerprint=FP,
                ),
                canonical_instrument_id=CanonicalInstrumentId("us-aapl"),
                source_trading_identity=TradingInstrumentIdentity("AAPL", "NASDAQ"),
                analysis_as_of=datetime(2026, 1, 2, tzinfo=UTC),
                source_technical_analysis_snapshot_fingerprint=FP,
                source_governed_dataset_fingerprint=FP,
                source_research_dataset_content_fingerprint=FP,
                interpretation_policy_identity=gi.GovernedTechnicalPolicyIdentity(
                    policy_kind="daily_technical_interpretation",
                    policy_id="classic_daily_technical",
                    behavioral_revision="1.0.0",
                    configuration_schema="classic_daily_technical_interpretation_configuration/v1",
                    configuration=ClassicDailyTechnicalInterpretationConfiguration(),
                ),
                source_quality="complete",
                source_warnings=(),
                trend_direction="positive",
                momentum_direction="positive",
                volatility_state="normal",
                extension_state="within_reference_band",
                comparison_evidence=tuple(
                    comparison(key, key in truths)
                    for key in comparison_ids
                    if key in truths or key in false
                ),
            )
            | changes
        )
    )


def assess(s=None, ref=None):
    return g.assess_governed_daily_technical_interpretation(
        interpretation=s if s is not None else source(),
        source_interpretation_occurrence=ref if ref is not None else occurrence(),
    )


def validate(content, s, ref=None):
    g.validate_governed_daily_technical_assessment(
        content=content,
        interpretation=s,
        source_interpretation_occurrence=ref if ref is not None else occurrence(),
    )


def oracle(s):
    # Independent test view: do not reuse the production adapter.
    view = SimpleNamespace(
        trend_direction=legacy.DailyTechnicalDirectionalState(s.trend_direction),
        momentum_direction=legacy.DailyTechnicalDirectionalState(s.momentum_direction),
        volatility_state=VolatilityState(s.volatility_state),
        extension_state=legacy.DailyTechnicalExtensionState(s.extension_state),
        comparison_evidence=tuple(
            SimpleNamespace(evidence_id=item.evidence_id, satisfied=item.satisfied)
            for item in s.comparison_evidence
        ),
        source_quality=TechnicalAnalysisQuality(s.source_quality),
        source_warnings=tuple(TechnicalAnalysisWarning(w) for w in s.source_warnings),
    )
    findings = classic.build_classic_assessment_findings(view)
    return [f.to_dict() for f in findings], classic.classic_assessment_outcome(
        view, findings
    ).value


@pytest.mark.parametrize("code,evidence_id", CAUTION_SUPPORT)
@pytest.mark.parametrize("satisfied", [True, False, None])
def test_each_comparison_caution_parity(code, evidence_id, satisfied):
    s = source(
        truths=(evidence_id,) if satisfied else (),
        false=(evidence_id,) if satisfied is False else (),
    )
    result = assess(s)
    expected, outcome = oracle(s)
    assert [f.to_dict() for f in result.findings] == expected
    assert result.outcome == outcome
    assert [(f.code, f.comparison_evidence_ids) for f in result.findings] == (
        [(code, (evidence_id,))] if satisfied else []
    )


@pytest.mark.parametrize(
    "trend,momentum,support",
    [
        ("positive", "negative", POSITIVE_SUPPORT),
        ("negative", "positive", NEGATIVE_SUPPORT),
    ],
)
def test_all_nine_findings_order_and_both_oppositions(trend, momentum, support):
    s = source(
        truths=(*support, *(ref for _, ref in CAUTION_SUPPORT)),
        trend_direction=trend,
        momentum_direction=momentum,
        source_quality="degraded",
        source_warnings=("insufficient_profile_history", "stale_evidence"),
    )
    result = assess(s)
    assert tuple(f.code for f in result.findings) == CODES
    assert result.findings[0].comparison_evidence_ids == support
    assert [f.comparison_evidence_ids for f in result.findings[1:]] == [
        *((ref,) for _, ref in CAUTION_SUPPORT),
        (),
        (),
        (),
    ]
    assert ([f.to_dict() for f in result.findings], result.outcome) == oracle(s)
    assert result.outcome == "mixed"


@pytest.mark.parametrize("support", [POSITIVE_SUPPORT, NEGATIVE_SUPPORT])
@pytest.mark.parametrize("index", range(5))
@pytest.mark.parametrize("false", [False, True])
def test_opposition_missing_or_false_support_fails_closed(support, index, false):
    s = source(
        truths=support[:index] + support[index + 1 :],
        false=(support[index],) if false else (),
        trend_direction="positive" if support == POSITIVE_SUPPORT else "negative",
        momentum_direction="negative" if support == POSITIVE_SUPPORT else "positive",
    )
    with pytest.raises(ValueError, match="supporting evidence"):
        assess(s)
    with pytest.raises(ValueError, match="supporting evidence"):
        validate(assess(), s)


@pytest.mark.parametrize(
    "state_field,unavailable",
    [
        ("trend_direction", "unavailable"),
        ("momentum_direction", "unavailable"),
        ("volatility_state", "unavailable"),
        ("extension_state", "unavailable"),
    ],
)
def test_insufficient_precedes_mixed_and_retains_cautions(state_field, unavailable):
    s = source(
        **(
            dict(trend_direction="mixed", source_quality="degraded")
            | {state_field: unavailable}
        )
    )
    result = assess(s)
    assert result.outcome == "insufficient_data"
    assert [f.code for f in result.findings] == ["source_quality_degraded"]
    assert ([f.to_dict() for f in result.findings], result.outcome) == oracle(s)


@pytest.mark.parametrize(
    "changes,outcome",
    [
        ({}, "aligned"),
        ({"source_quality": "degraded"}, "caution"),
        ({"trend_direction": "mixed", "source_quality": "degraded"}, "mixed"),
        ({"momentum_direction": "mixed"}, "mixed"),
        ({"source_warnings": ("insufficient_profile_history",)}, "caution"),
        ({"source_warnings": ("stale_evidence",)}, "caution"),
    ],
)
def test_outcomes_and_source_cautions(changes, outcome):
    s = source(**changes)
    result = assess(s)
    assert result.outcome == outcome
    assert ([f.to_dict() for f in result.findings], outcome) == oracle(s)


class Text(str):
    pass


class Integer(int):
    pass


class Category(StrEnum):
    COMPLETE = "complete"


class Sequence(IntEnum):
    ONE = 1


@pytest.mark.parametrize("value", [True, False, 0, -1, 1.0, Integer(1), Sequence.ONE])
def test_exact_sequence(value):
    with pytest.raises((TypeError, ValueError)):
        occurrence(interpretation_history_sequence=value)


@pytest.mark.parametrize(
    "field_name",
    [
        "interpretation_history_namespace_id",
        "interpretation_execution_id",
        "interpretation_fingerprint",
    ],
)
@pytest.mark.parametrize(
    "mutation",
    [
        lambda v: Text(v),
        lambda v: v.upper(),
        lambda v: v + "\n",
        lambda v: v[:-1],
        lambda v: 1,
    ],
)
def test_selector_grammar_and_exact_strings(field_name, mutation):
    with pytest.raises((TypeError, ValueError)):
        occurrence(**{field_name: mutation(getattr(occurrence(), field_name))})


def test_occurrence_complete_projection_and_artifact_detachment():
    a = artifact()
    ref = occurrence(artifact_reference=a)
    assert ref.artifact_reference is not a
    assert ref.artifact_reference.to_dict() == a.to_dict()
    assert set(ref.to_dict()) == {f.name for f in fields(ref)}
    object.__setattr__(a, "artifact_id", "changed")
    assert ref.artifact_reference.artifact_id == "test:detached"
    with pytest.raises((TypeError, ValueError)):
        occurrence(artifact_reference=a)


@pytest.mark.parametrize(
    "name,value",
    [
        ("kind", "unknown"),
        ("kind", "conflict"),
        ("kind", Text("caution")),
        ("code", "other_valid_grammar"),
        ("code", Text("rsi_elevated")),
        ("comparison_evidence_ids", []),
        ("comparison_evidence_ids", ()),
        ("comparison_evidence_ids", (Text("rsi_at_or_above_elevated"),)),
        ("comparison_evidence_ids", ("rsi_at_or_above_elevated",) * 2),
        ("comparison_evidence_ids", ("rsi_at_or_below_depressed",)),
    ],
)
def test_finding_contract(name, value):
    finding = g.GovernedDailyTechnicalAssessmentFinding(
        "caution", "rsi_elevated", ("rsi_at_or_above_elevated",)
    )
    with pytest.raises((TypeError, ValueError)):
        replace(finding, **{name: value})


@pytest.mark.parametrize("support", [POSITIVE_SUPPORT, NEGATIVE_SUPPORT])
def test_opposition_reference_order(support):
    with pytest.raises(ValueError):
        g.GovernedDailyTechnicalAssessmentFinding(
            "conflict", "direction_opposition", tuple(reversed(support))
        )


@pytest.mark.parametrize(
    "name,value",
    [
        ("source_quality", "unknown"),
        ("source_quality", Category.COMPLETE),
        ("source_quality", Text("complete")),
        ("source_warnings", []),
        ("source_warnings", ("unknown",)),
        ("source_warnings", (Text("stale_evidence"),)),
        ("source_warnings", ("stale_evidence", "insufficient_profile_history")),
        ("source_warnings", ("stale_evidence", "stale_evidence")),
        ("outcome", "unknown"),
        ("outcome", Text("aligned")),
        ("findings", []),
        ("analysis_as_of", datetime(2026, 1, 2)),
        ("analysis_as_of", datetime(2026, 1, 2, tzinfo=timezone(timedelta(hours=8)))),
        (
            "analysis_as_of",
            datetime(2026, 1, 2, tzinfo=timezone(timedelta(0), "other")),
        ),
        ("canonical_instrument_id", "us-aapl"),
        ("source_trading_identity", object()),
        (
            "assessment_policy_identity",
            ClassicDailyTechnicalAssessmentPolicy().identity,
        ),
        ("source_interpretation_content_fingerprint", Text(FP)),
        ("source_interpretation_occurrence", object()),
    ],
)
def test_content_contract(name, value):
    with pytest.raises((TypeError, ValueError)):
        replace(assess(), **{name: value})


@pytest.mark.parametrize("name", ["schema_version", "fingerprint"])
def test_content_mutated_exact_strings(name):
    value = assess()
    object.__setattr__(value, name, Text(getattr(value, name)))
    with pytest.raises(ValueError):
        value.to_dict()


def test_duplicate_and_reordered_findings():
    result = assess(
        source(source_quality="degraded", source_warnings=("stale_evidence",))
    )
    for findings in (result.findings * 2, tuple(reversed(result.findings))):
        with pytest.raises(ValueError, match="order/duplicates"):
            replace(result, findings=findings)


def test_fixed_policy_complete_parity_and_fresh_configuration():
    p = g.GovernedDailyTechnicalAssessmentPolicyIdentity()
    assert p.to_dict() == ClassicDailyTechnicalAssessmentPolicy().identity.to_dict()
    assert (
        p.fingerprint
        == "sha256:dbdf4bdb4eeb3880d5a6ad4f90d17d9934782f6e1d0d455cb3af93a20d74874f"
    )
    assert set(p.to_dict()) == {f.name for f in fields(p)}
    supplied = {}
    other = g.GovernedDailyTechnicalAssessmentPolicyIdentity(configuration=supplied)
    assert (
        other.configuration is not supplied
        and other.configuration is not p.configuration
    )
    projection = p.to_dict()
    projection["configuration"]["changed"] = True
    assert p.configuration == {}
    p.configuration["changed"] = True
    with pytest.raises(ValueError):
        p.to_dict()
    assert other.to_dict() == ClassicDailyTechnicalAssessmentPolicy().identity.to_dict()


@pytest.mark.parametrize(
    "name",
    [
        "policy_kind",
        "policy_id",
        "behavioral_revision",
        "configuration_schema",
        "schema_version",
        "fingerprint",
        "configuration",
    ],
)
@pytest.mark.parametrize("subclass", [False, True])
def test_mutated_policy_complete_validation(name, subclass):
    p = g.GovernedDailyTechnicalAssessmentPolicyIdentity()
    original = getattr(p, name)
    value = (
        (Text(original) if subclass else "other")
        if name != "configuration"
        else {"x": 1}
    )
    object.__setattr__(p, name, value)
    if not subclass and name not in ("schema_version", "fingerprint"):
        object.__setattr__(
            p, "fingerprint", canonical_fingerprint(p._fingerprint_payload())
        )
    with pytest.raises((TypeError, ValueError)):
        p.to_dict()


@pytest.mark.parametrize(
    "changes",
    [
        {"interpretation_history_sequence": 2},
        {
            "interpretation_history_namespace_id": (
                "polygon_completed_daily_interpretation_history:" + "9" * 32
            )
        },
        {
            "interpretation_execution_id": "polygon_completed_daily_interpretation:"
            + "9" * 32
        },
        {"interpretation_fingerprint": "sha256:" + "9" * 64},
    ],
)
def test_equal_content_distinct_occurrences(changes):
    s = source()
    first, second = assess(s), assess(s, occurrence(**changes))
    assert first.fingerprint != second.fingerprint
    assert (
        first.source_interpretation_content_fingerprint
        == second.source_interpretation_content_fingerprint
        == s.fingerprint
    )
    with pytest.raises(ValueError, match="correspondence"):
        validate(first, s, occurrence(**changes))


def test_artifact_selector_correspondence_and_identity():
    s = source()
    changed = replace(artifact(), artifact_version="2.0.0")
    ref = occurrence(artifact_reference=changed)
    with pytest.raises(ValueError, match="artifact correspondence"):
        assess(s, ref)
    altered = replace(
        s,
        source_technical_occurrence=replace(
            s.source_technical_occurrence, artifact_reference=changed
        ),
    )
    assert assess(altered, ref).fingerprint != assess(s).fingerprint


def test_complete_content_identity_and_roles():
    s, ref = source(), occurrence()
    first = assess(s, ref)
    assert first == assess(deepcopy(s), deepcopy(ref))
    assert first.source_interpretation_content_fingerprint == s.fingerprint
    assert (
        first.source_interpretation_occurrence.interpretation_fingerprint
        == ref.interpretation_fingerprint
    )
    assert s.fingerprint != ref.interpretation_fingerprint
    payload = first._fingerprint_payload()
    assert set(payload) == {f.name for f in fields(first)} - {"fingerprint"}
    assert len(fields(first)) == 12
    assert canonical_fingerprint(payload) == first.fingerprint
    assert payload["analysis_as_of"] == "2026-01-02T00:00:00+00:00"
    for name in payload:
        altered = deepcopy(payload)
        altered[name] = "changed"
        assert canonical_fingerprint(altered) != first.fingerprint


@pytest.mark.parametrize(
    "name,value",
    [
        ("source_interpretation_content_fingerprint", FP),
        ("canonical_instrument_id", CanonicalInstrumentId("other")),
        ("source_trading_identity", TradingInstrumentIdentity("MSFT", "NASDAQ")),
        ("analysis_as_of", datetime(2026, 1, 3, tzinfo=UTC)),
        ("source_quality", "degraded"),
        ("source_warnings", ("stale_evidence",)),
        ("outcome", "mixed"),
        (
            "findings",
            (
                g.GovernedDailyTechnicalAssessmentFinding(
                    "caution", "source_quality_degraded", ()
                ),
            ),
        ),
    ],
)
def test_coherent_wrong_semantics_and_source_facts_rejected(name, value):
    s = source()
    candidate = replace(assess(s), **{name: value})
    candidate.to_dict()  # A coherent content fingerprint is insufficient.
    with pytest.raises(ValueError, match="correspondence"):
        validate(candidate, s)


def test_wrong_but_valid_opposition_tuple_rejected():
    s = source(truths=POSITIVE_SUPPORT, momentum_direction="negative")
    result = assess(s)
    wrong = replace(
        result,
        findings=(
            replace(result.findings[0], comparison_evidence_ids=NEGATIVE_SUPPORT),
        ),
    )
    with pytest.raises(ValueError, match="correspondence"):
        validate(wrong, s)


def test_zero_enum_all_public_graphs_and_mutation_isolation():
    s = source(truths=("rsi_at_or_above_elevated",), source_quality="degraded")
    ref = occurrence()
    one, two = assess(s, ref), assess(s, ref)
    expected = two.to_dict()
    classic_policy = ClassicDailyTechnicalAssessmentPolicy()
    policy_before = classic_policy.identity.to_dict()
    enum_types = (
        TechnicalAnalysisQuality,
        TechnicalAnalysisWarning,
        VolatilityState,
        legacy.DailyTechnicalDirectionalState,
        legacy.DailyTechnicalExtensionState,
        classic.DailyTechnicalAssessmentFindingKind,
        classic.DailyTechnicalAssessmentOutcome,
    )
    enums_before = [(item, dict(vars(item))) for cls in enum_types for item in cls]
    for value in (
        ref,
        one.assessment_policy_identity,
        *one.findings,
        one,
        two,
        copy(one),
        deepcopy(one),
        one.to_dict(),
    ):
        assert_enum_free(value)
        for _, leaf in public_graph(value):
            assert not isinstance(leaf, (Enum, StrEnum, IntEnum))
            if type(leaf) is str:
                with pytest.raises((TypeError, AttributeError)):
                    object.__setattr__(leaf, "_value_", "changed")
    with pytest.raises(FrozenInstanceError):
        one.outcome = "mixed"
    object.__setattr__(one.findings[0], "code", "rsi_depressed")
    object.__setattr__(
        one.source_interpretation_occurrence.artifact_reference,
        "artifact_id",
        "changed",
    )
    one.assessment_policy_identity.configuration["x"] = 1
    object.__setattr__(one.canonical_instrument_id, "instrument_id", "changed")
    object.__setattr__(one.source_trading_identity, "symbol", "MSFT")
    assert two.to_dict() == expected == assess(s, ref).to_dict()
    assert classic_policy.identity.to_dict() == policy_before
    assert [
        (item, dict(vars(item))) for cls in enum_types for item in cls
    ] == enums_before


def test_no_forbidden_execution_and_exact_adapter(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("forbidden semantic boundary")

    for module, name in (
        (classic, "assess_daily_technical_interpretation"),
        (ClassicDailyTechnicalAssessmentPolicy, "assess"),
        (legacy, "classic_states"),
        (gi, "classic_states"),
        (legacy, "build_classic_comparison_evidence"),
        (gi, "build_classic_comparison_evidence"),
        (gi, "validate_governed_daily_technical_interpretation"),
    ):
        monkeypatch.setattr(module, name, forbidden)
    original = classic.build_classic_assessment_findings
    calls = []

    def inspect_view(view):
        assert {f.name for f in fields(view)} == {
            "trend_direction",
            "momentum_direction",
            "volatility_state",
            "extension_state",
            "comparison_evidence",
            "source_quality",
            "source_warnings",
        }
        for item in view.comparison_evidence:
            assert {f.name for f in fields(item)} == {"evidence_id", "satisfied"}
        calls.append("findings")
        return original(view)

    original_outcome = classic.classic_assessment_outcome

    def inspect_outcome(view, findings):
        assert calls[-1] == "findings"
        calls.append("outcome")
        return original_outcome(view, findings)

    monkeypatch.setattr(g, "build_classic_assessment_findings", inspect_view)
    monkeypatch.setattr(classic, "build_classic_assessment_findings", inspect_view)
    monkeypatch.setattr(g, "classic_assessment_outcome", inspect_outcome)
    monkeypatch.setattr(classic, "classic_assessment_outcome", inspect_outcome)
    assert_enum_free(assess(source(truths=("rsi_at_or_above_elevated",))))
    assert calls == ["findings", "outcome", "findings", "outcome"]
    tree = ast.parse(Path(g.__file__).read_text())
    assert not any(
        "application" in (node.module or "")
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    )
    assert set(g.__all__) == {
        "GOVERNED_DAILY_TECHNICAL_ASSESSMENT_SCHEMA",
        "PolygonCompletedDailyAssessmentRequest",
        "GovernedDailyTechnicalAssessmentPolicyIdentity",
        "GovernedDailyTechnicalAssessmentFinding",
        "GovernedDailyTechnicalAssessment",
        "assess_governed_daily_technical_interpretation",
        "validate_governed_daily_technical_assessment",
    }


@pytest.mark.parametrize(
    "helper", ["build_classic_assessment_findings", "classic_assessment_outcome"]
)
def test_independent_validator_rejects_corrupted_entry_helper(monkeypatch, helper):
    s = source(source_quality="degraded")
    wrong = (
        (lambda view: ())
        if helper == "build_classic_assessment_findings"
        else (lambda view, findings: classic.DailyTechnicalAssessmentOutcome.MIXED)
    )
    monkeypatch.setattr(g, helper, wrong)
    with pytest.raises(ValueError, match="correspondence"):
        assess(s)


@pytest.mark.parametrize("target", ["source", "occurrence", "adapter"])
def test_persistent_input_or_adapter_drift_rejected(monkeypatch, target):
    s, ref = source(), occurrence()
    original = g.build_classic_assessment_findings

    def mutate(view):
        findings = original(view)
        if target == "source":
            object.__setattr__(s, "source_quality", "degraded")
            object.__setattr__(
                s, "fingerprint", canonical_fingerprint(s._fingerprint_payload())
            )
        elif target == "occurrence":
            object.__setattr__(ref, "interpretation_history_sequence", 2)
        else:
            object.__setattr__(
                view, "source_quality", TechnicalAnalysisQuality.DEGRADED
            )
        return findings

    monkeypatch.setattr(g, "build_classic_assessment_findings", mutate)
    with pytest.raises(ValueError, match="drift"):
        assess(s, ref)


def test_coherent_constructor_corruption_rejected(monkeypatch):
    original = g.GovernedDailyTechnicalAssessment.__post_init__

    def corrupt(result):
        original(result)
        object.__setattr__(result, "outcome", "mixed")
        object.__setattr__(
            result, "fingerprint", canonical_fingerprint(result._fingerprint_payload())
        )

    monkeypatch.setattr(g.GovernedDailyTechnicalAssessment, "__post_init__", corrupt)
    with pytest.raises(ValueError, match="correspondence"):
        assess()


@pytest.mark.parametrize(
    "name,value",
    [
        ("source_quality", Category.COMPLETE),
        ("source_warnings", (Text("stale_evidence"),)),
        ("trend_direction", legacy.DailyTechnicalDirectionalState.POSITIVE),
        ("momentum_direction", Text("positive")),
        ("comparison_evidence", []),
        ("fingerprint", "sha256:" + "0" * 64),
    ],
)
def test_mutated_source_scalar_contracts_rejected(name, value):
    s = source()
    object.__setattr__(s, name, value)
    with pytest.raises((TypeError, ValueError)):
        assess(s)
    with pytest.raises((TypeError, ValueError)):
        validate(assess(), s)


def test_insufficient_preserves_conflict_and_caution():
    s = source(
        truths=POSITIVE_SUPPORT,
        momentum_direction="negative",
        volatility_state="unavailable",
        source_quality="degraded",
    )
    result = assess(s)
    assert result.outcome == "insufficient_data"
    assert tuple(f.code for f in result.findings) == (
        "direction_opposition",
        "source_quality_degraded",
    )
    assert ([f.to_dict() for f in result.findings], result.outcome) == oracle(s)


@pytest.mark.parametrize("target", ["content", "reference", "finding"])
def test_coherent_public_mutation_does_not_change_other_or_future_graphs(target):
    s = source(source_quality="degraded")
    one, two = assess(s), assess(s)
    expected = two.to_dict()
    if target == "content":
        object.__setattr__(one, "outcome", "mixed")
    elif target == "reference":
        object.__setattr__(
            one.source_interpretation_occurrence, "interpretation_history_sequence", 2
        )
    else:
        object.__setattr__(one.findings[0], "code", "source_warning_stale_evidence")
    object.__setattr__(
        one, "fingerprint", canonical_fingerprint(one._fingerprint_payload())
    )
    one.to_dict()
    assert_enum_free(one)
    with pytest.raises(ValueError, match="correspondence"):
        validate(one, s)
    assert two.to_dict() == expected == assess(s).to_dict()


def test_exact_configuration_type_and_incomplete_content():
    class Configuration(dict):
        pass

    for configuration in (Configuration(), (), None):
        with pytest.raises(ValueError):
            g.GovernedDailyTechnicalAssessmentPolicyIdentity(
                configuration=configuration
            )
    result = assess()
    object.__delattr__(result, "findings")
    with pytest.raises(ValueError, match="incomplete"):
        result.to_dict()


def test_fresh_nested_values_and_projection():
    s, ref = source(source_quality="degraded"), occurrence()
    first, second = assess(s, ref), assess(s, ref)
    for name in (
        "source_interpretation_occurrence",
        "canonical_instrument_id",
        "source_trading_identity",
        "assessment_policy_identity",
    ):
        assert getattr(first, name) is not getattr(second, name)
    assert first.source_interpretation_occurrence is not ref
    assert first.canonical_instrument_id is not s.canonical_instrument_id
    assert first.source_trading_identity is not s.source_trading_identity
    assert first.findings[0] is not second.findings[0]
    projection = first.to_dict()
    projection["findings"][0]["code"] = "changed"
    projection["source_interpretation_occurrence"]["artifact_reference"][
        "artifact_id"
    ] = "changed"
    assert first.to_dict() == second.to_dict()
