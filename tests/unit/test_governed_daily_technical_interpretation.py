from __future__ import annotations

import ast
import inspect
import json
import tomllib
from copy import deepcopy
from dataclasses import FrozenInstanceError, fields, replace
from datetime import timedelta
from pathlib import Path

import pytest
from test_daily_technical_analysis import snapshot as make_snapshot

from market_platform._fingerprint import canonical_fingerprint
from market_platform.evidence import (
    EvidenceArtifactReference,
    EvidenceAuthority,
    EvidenceInformationClass,
)
from market_platform.instruments.identity import (
    CanonicalInstrument,
    CanonicalInstrumentId,
    InstrumentAssetClass,
)
from market_platform.research import daily_technical_interpretation as classic
from market_platform.research import governed_daily_technical_interpretation as g
from market_platform.research import technical_analysis as technical
from market_platform.research.classic_daily_technical import (
    ClassicDailyTechnicalInterpretationPolicy,
)
from market_platform.research.technical_policy import (
    ClassicDailyTechnicalInterpretationConfiguration,
)
from market_platform.trading.instrument import TradingInstrumentIdentity

POLICY_FINGERPRINT = (
    "sha256:9d81e49a6d45d27071e804b46486ae247d71f650184e8032a792586807fc3d02"
)
IDS = (
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


def reference(**changes):
    values = dict(
        artifact_reference=EvidenceArtifactReference(
            "polygon_fixture",
            "1.0.0",
            "sha256:" + "a" * 64,
            EvidenceInformationClass.SOURCE_OBSERVATION,
            EvidenceAuthority.EXTERNAL_ORIGIN,
        ),
        technical_history_namespace_id="polygon_completed_daily_technical_history:"
        + "1" * 32,
        technical_history_sequence=1,
        technical_execution_id="polygon_completed_daily_technical:" + "2" * 32,
        technical_fingerprint="sha256:" + "b" * 64,
    )
    return g.PolygonCompletedDailyInterpretationRequest(**(values | changes))


@pytest.fixture
def source():
    return make_snapshot(250)


def arguments(source):
    return dict(
        snapshot=source,
        source_technical_occurrence=reference(),
        canonical_instrument=CanonicalInstrument(
            CanonicalInstrumentId("us-aapl"),
            deepcopy(source.evidence.instrument),
            InstrumentAssetClass.EQUITY,
            "USD",
        ),
        source_governed_dataset_fingerprint="sha256:" + "c" * 64,
    )


def interpret(source, **changes):
    return g.interpret_governed_daily_technical_snapshot(
        **(arguments(source) | changes)
    )


def refingerprint(value):
    object.__setattr__(
        value, "fingerprint", canonical_fingerprint(value._fingerprint_payload())
    )


@pytest.mark.parametrize(
    "name,value",
    [
        (
            "technical_history_namespace_id",
            "polygon_completed_daily_technical_history:" + "A" * 32,
        ),
        (
            "technical_history_namespace_id",
            "polygon_completed_daily_bridge_history:" + "1" * 32,
        ),
        (
            "technical_history_namespace_id",
            "polygon_completed_daily_technical_history:" + "1" * 31,
        ),
        ("technical_execution_id", "polygon_completed_daily_technical:" + "A" * 32),
        ("technical_execution_id", "polygon_completed_daily_bridge:" + "2" * 32),
        ("technical_execution_id", 123),
        ("technical_history_sequence", 0),
        ("technical_history_sequence", -1),
        ("technical_history_sequence", True),
        ("technical_history_sequence", 1.0),
        ("technical_fingerprint", "sha256:" + "B" * 64),
        ("technical_fingerprint", "sha256:" + "b" * 63),
        ("technical_fingerprint", None),
        ("artifact_reference", object()),
    ],
)
def test_reference_rejects_invalid_exact_facts(name, value):
    with pytest.raises((TypeError, ValueError)):
        reference(**{name: value})


def test_reference_detaches_artifact_and_has_only_selectors():
    original = reference().artifact_reference
    ref = reference(artifact_reference=original)
    assert ref.artifact_reference == original
    assert ref.artifact_reference is not original
    assert set(ref.to_dict()) == {item.name for item in fields(ref)}
    assert len(fields(ref)) == 5
    public = ref.to_dict()
    public["artifact_reference"]["artifact_id"] = "changed"
    object.__setattr__(original, "artifact_id", "changed")
    assert ref.to_dict()["artifact_reference"]["artifact_id"] == "polygon_fixture"
    assert {
        name
        for name in dir(ref)
        if callable(getattr(ref, name)) and not name.startswith("_")
    } == {"to_dict"}
    with pytest.raises(FrozenInstanceError):
        ref.technical_history_sequence = 2
    object.__setattr__(ref, "technical_history_sequence", True)
    with pytest.raises(ValueError):
        ref.to_dict()


def test_reference_rejects_subclasses_and_noncanonical_artifact(source):
    class Ref(g.PolygonCompletedDailyInterpretationRequest):
        pass

    subclass = Ref(
        **{item.name: getattr(reference(), item.name) for item in fields(reference())}
    )
    with pytest.raises(TypeError):
        interpret(source, source_technical_occurrence=subclass)
    artifact = reference().artifact_reference
    object.__setattr__(artifact, "artifact_id", " padded ")
    refingerprint(artifact)
    with pytest.raises(ValueError):
        reference(artifact_reference=artifact)


def test_content_exact_fields_policy_and_detached_graph(source):
    args = arguments(source)
    result = g.interpret_governed_daily_technical_snapshot(**args)
    result._validate()
    assert result.schema_version == "governed_daily_technical_interpretation/v1"
    assert result.source_trading_identity == source.evidence.instrument
    assert type(result.source_trading_identity) is TradingInstrumentIdentity
    assert result.source_trading_identity is not source.evidence.instrument
    assert result.source_technical_occurrence is not args["source_technical_occurrence"]
    assert (
        result.canonical_instrument_id is not args["canonical_instrument"].instrument_id
    )
    assert result.analysis_as_of == source.evidence.analysis_as_of
    assert result.source_technical_analysis_snapshot_fingerprint == source.fingerprint
    assert (
        result.source_governed_dataset_fingerprint
        == args["source_governed_dataset_fingerprint"]
    )
    assert (
        result.source_research_dataset_content_fingerprint
        == source.evidence.dataset_content_fingerprint
    )
    assert (
        len(
            {
                result.source_technical_analysis_snapshot_fingerprint,
                result.source_governed_dataset_fingerprint,
                result.source_research_dataset_content_fingerprint,
            }
        )
        == 3
    )
    policy = result.interpretation_policy_identity
    assert (
        policy.to_dict()
        == ClassicDailyTechnicalInterpretationPolicy().identity.to_dict()
    )
    assert policy.fingerprint == POLICY_FINGERPRINT
    assert (
        type(policy.configuration) is ClassicDailyTechnicalInterpretationConfiguration
    )
    assert policy.configuration.to_dict() == {
        "rsi_neutral": 50.0,
        "rsi_elevated": 70.0,
        "rsi_depressed": 30.0,
        "realized_volatility_low": 0.15,
        "realized_volatility_high": 0.30,
        "ema20_extension_band_percent": 5.0,
    }
    payload = result.to_dict()
    assert set(payload) == {item.name for item in fields(result)}
    assert json.loads(json.dumps(payload)) == payload
    for forbidden in (
        "source_daily_instrument_integrity_evidence_fingerprint",
        "requested_trading_identity",
        "execution_id",
        "history_namespace_id",
        "history_sequence",
        "execution_started_at",
        "execution_completed_at",
        "available_at",
        "assessment",
        "strategy",
        "recommendation",
        "signal",
    ):
        assert forbidden not in payload
    payload["source_technical_occurrence"]["artifact_reference"]["artifact_id"] = (
        "other"
    )
    payload["comparison_evidence"][0]["left_operand"]["value"] = 0.0
    payload["interpretation_policy_identity"]["configuration"]["rsi_neutral"] = 55.0
    assert result.to_dict() != payload
    rebuilt = replace(result)
    assert rebuilt == result
    assert rebuilt.comparison_evidence[0] is not result.comparison_evidence[0]
    assert (
        rebuilt.comparison_evidence[0].left_operand
        is not result.comparison_evidence[0].left_operand
    )
    object.__setattr__(rebuilt.comparison_evidence[0].left_operand, "value", 0.0)
    result._validate()
    with pytest.raises((ValueError, TypeError)):
        rebuilt.to_dict()


@pytest.mark.parametrize(
    "name", ["policy", "configuration", "history_service", "provider"]
)
def test_no_caller_extension_parameters(source, name):
    with pytest.raises(TypeError, match="unexpected keyword"):
        interpret(source, **{name: object()})
    assert all(
        p.kind is inspect.Parameter.KEYWORD_ONLY
        for p in inspect.signature(
            g.interpret_governed_daily_technical_snapshot
        ).parameters.values()
    )


@pytest.mark.parametrize(
    "name,value",
    [
        ("policy_id", "different"),
        ("behavioral_revision", "1.0.1"),
        (
            "configuration",
            ClassicDailyTechnicalInterpretationConfiguration(rsi_neutral=51.0),
        ),
    ],
)
def test_changed_fixed_policy_refused(source, monkeypatch, name, value):
    changed = replace(
        ClassicDailyTechnicalInterpretationPolicy().identity, **{name: value}
    )
    monkeypatch.setattr(g, "_fixed_policy", lambda: changed)
    with pytest.raises(ValueError, match="fixed classic"):
        interpret(source)


def test_actual_default_factory_drift_refused(source, monkeypatch):
    monkeypatch.setattr(
        g,
        "ClassicDailyTechnicalInterpretationPolicy",
        lambda: ClassicDailyTechnicalInterpretationPolicy(
            ClassicDailyTechnicalInterpretationConfiguration(rsi_neutral=51.0)
        ),
    )
    with pytest.raises(ValueError, match="fixed classic"):
        interpret(source)


@pytest.mark.parametrize(
    "count,lag", [(1, 1), (10, 12), (20, 1), (33, 1), (100, 1), (250, 1), (250, 12)]
)
def test_semantic_equivalence_omissions_quality_and_warning_order(count, lag):
    source = make_snapshot(count, lag_days=lag)
    result = interpret(source)
    config = ClassicDailyTechnicalInterpretationConfiguration()
    assert (
        result.trend_direction,
        result.momentum_direction,
        result.volatility_state,
        result.extension_state,
    ) == classic.classic_states(source, config)
    assert result.comparison_evidence == classic.build_classic_comparison_evidence(
        source, config
    )
    assert result.source_quality is source.quality
    assert result.source_warnings == source.warnings
    ids = tuple(item.evidence_id for item in result.comparison_evidence)
    assert ids == tuple(item for item in IDS if item in ids)
    if count == 250:
        assert ids == IDS
        assert {item.satisfied for item in result.comparison_evidence} == {True, False}
    if count == 10 and lag == 12:
        assert result.source_quality is technical.TechnicalAnalysisQuality.DEGRADED
        assert tuple(item.value for item in result.source_warnings) == (
            "insufficient_profile_history",
            "stale_evidence",
        )
    if count == 1:
        assert result.comparison_evidence == ()
        assert (
            result.trend_direction.value
            == result.momentum_direction.value
            == "unavailable"
        )


def adjusted(source, **changes):
    """Coherent scalar fixture; released validation remains fully enabled."""
    for name, value in changes.items():
        object.__setattr__(source, name, value)
    object.__setattr__(source, "macd_histogram", source.macd_line - source.macd_signal)
    alignment = technical._ema_alignment(
        source.ema_8, source.ema_20, source.ema_144, source.ema_169
    )
    tunnel = technical._tunnel_position(
        source.latest_close, source.ema_144, source.ema_169
    )
    for name, value in {
        "ema_alignment": alignment,
        "tunnel_position": tunnel,
        "trend_state": technical._trend_state(alignment, tunnel),
        "momentum_state": technical._momentum_state(
            source.macd_line, source.macd_signal, source.macd_histogram, source.rsi_14
        ),
        "volatility_state": technical._volatility_state(
            source.realized_volatility,
            source.profile.realized_volatility_low_threshold,
            source.profile.realized_volatility_high_threshold,
        ),
        "volatility_references": technical._references(
            source.latest_close, source.wilder_atr_14, source.ema_20
        ),
    }.items():
        object.__setattr__(source, name, value)
    refingerprint(source)
    source._validate()
    return source


@pytest.mark.parametrize(
    "realized,state",
    [(0.149, "low"), (0.15, "normal"), (0.299, "normal"), (0.30, "high")],
)
def test_volatility_thresholds(source, realized, state):
    assert (
        interpret(adjusted(source, realized_volatility=realized)).volatility_state.value
        == state
    )


@pytest.mark.parametrize(
    "rsi,line,signal,state",
    [
        (50.0, 2.0, 1.0, "positive"),
        (49.9, 1.0, 2.0, "negative"),
        (50.0, 1.0, 2.0, "mixed"),
        (50.0, 1.0, 1.0, "mixed"),
    ],
)
def test_momentum_equality_and_mixed(source, rsi, line, signal, state):
    result = interpret(adjusted(source, rsi_14=rsi, macd_line=line, macd_signal=signal))
    assert result.momentum_direction.value == state
    assert type(result.momentum_direction) is not type(source.momentum_state)


@pytest.mark.parametrize(
    "close,ema,state",
    [
        (105.0, 100.0, "above_reference_band"),
        (95.0, 100.0, "below_reference_band"),
        (106.0, 100.0, "above_reference_band"),
        (94.0, 100.0, "below_reference_band"),
    ],
)
def test_extension_equality(source, close, ema, state):
    # Released ratio arithmetic gives +/-5.000000000000004 for 105/100
    # and 95/100. Do not round these actual snapshot operands to the band.
    source = adjusted(
        source,
        latest_close=close,
        ema_20=ema,
        atr_percent_14=100.0 * source.wilder_atr_14 / close,
    )
    assert interpret(source).extension_state.value == state


@pytest.mark.parametrize(
    "ema8,ema20,ema144,ema169,state",
    [
        (110.0, 100.0, 90.0, 80.0, "positive"),
        (110.0, 100.0, 120.0, 130.0, "positive"),
        (80.0, 90.0, 400.0, 410.0, "negative"),
        (100.0, 100.0, 90.0, 80.0, "mixed"),
        (110.0, 100.0, 400.0, 80.0, "mixed"),
    ],
)
def test_trend_direction_is_not_snapshot_description(
    source, ema8, ema20, ema144, ema169, state
):
    result = interpret(
        adjusted(source, ema_8=ema8, ema_20=ema20, ema_144=ema144, ema_169=ema169)
    )
    assert result.trend_direction.value == state
    assert type(result.trend_direction) is not type(source.trend_state)
    if ema144 == 120.0:
        assert source.trend_state.value == "mixed"
        assert result.trend_direction.value == "positive"


@pytest.mark.parametrize(
    "name,value",
    [
        ("schema_version", "daily_technical_interpretation/v1"),
        ("source_quality", "complete"),
        ("source_warnings", []),
        ("source_trading_identity", object()),
        ("canonical_instrument_id", "us-aapl"),
        ("analysis_as_of", "2024-01-01"),
        ("source_technical_analysis_snapshot_fingerprint", "bad"),
        ("source_governed_dataset_fingerprint", "bad"),
        ("source_research_dataset_content_fingerprint", "bad"),
        ("comparison_evidence", []),
        ("trend_direction", "positive"),
    ],
)
def test_content_mutation_detected(source, name, value):
    result = interpret(source)
    with pytest.raises(FrozenInstanceError):
        result.source_quality = technical.TechnicalAnalysisQuality.DEGRADED
    object.__setattr__(result, name, value)
    with pytest.raises((ValueError, TypeError)):
        result.to_dict()


def test_constructor_rejects_bad_types_and_missing_retained_fields(source):
    result = interpret(source)
    for changes in (
        {"source_warnings": []},
        {"comparison_evidence": []},
        {"source_trading_identity": object()},
        {
            "interpretation_policy_identity": replace(
                result.interpretation_policy_identity, policy_id="other"
            )
        },
    ):
        with pytest.raises((ValueError, TypeError)):
            replace(result, **changes)
    object.__delattr__(result, "source_quality")
    with pytest.raises(ValueError, match="incomplete"):
        result.to_dict()


@pytest.mark.parametrize(
    "target,coherent",
    [("live", False), ("live", True), ("detached", True), ("nested", True)],
)
def test_source_persistent_mutation_refused(source, monkeypatch, target, coherent):
    original = g.classic_states

    def mutate(working, config):
        result = original(working, config)
        victim = source if target == "live" else working
        if target == "nested":
            object.__setattr__(
                victim.volatility_references, "distance_from_ema20_percent", 99.0
            )
        else:
            object.__setattr__(victim.evidence, "provider", "rewritten")
            refingerprint(victim.evidence)
        if coherent:
            refingerprint(victim)
            if target != "nested":
                victim._validate()
        return result

    monkeypatch.setattr(g, "classic_states", mutate)
    with pytest.raises(ValueError):
        interpret(source)


@pytest.mark.parametrize("target", ["configuration", "identity", "live_configuration"])
def test_policy_coherent_drift_refused(source, monkeypatch, target):
    policy = ClassicDailyTechnicalInterpretationPolicy().identity
    monkeypatch.setattr(g, "_fixed_policy", lambda: policy)
    original = g.classic_states

    def mutate(working, configuration):
        states = original(working, configuration)
        if target == "configuration":
            object.__setattr__(configuration, "rsi_neutral", 51.0)
        elif target == "identity":
            object.__setattr__(policy, "policy_id", "other")
            refingerprint(policy)
            policy._validate()
        else:
            object.__setattr__(policy.configuration, "rsi_neutral", 51.0)
            refingerprint(policy)
            policy._validate()
        return states

    monkeypatch.setattr(g, "classic_states", mutate)
    with pytest.raises(ValueError):
        interpret(source)


@pytest.mark.parametrize("target", ["reference", "canonical", "trading"])
def test_provenance_drift_refused(source, monkeypatch, target):
    args = arguments(source)
    original = g.classic_states

    def mutate(working, configuration):
        states = original(working, configuration)
        if target == "reference":
            object.__setattr__(
                args["source_technical_occurrence"],
                "technical_fingerprint",
                "sha256:" + "f" * 64,
            )
        else:
            instrument = args["canonical_instrument"]
            if target == "canonical":
                object.__setattr__(instrument.instrument_id, "instrument_id", "other")
            else:
                object.__setattr__(
                    instrument,
                    "trading_identity",
                    TradingInstrumentIdentity("MSFT", "NASDAQ"),
                )
            refingerprint(instrument)
            instrument._validate()
        return states

    monkeypatch.setattr(g, "classic_states", mutate)
    with pytest.raises(ValueError):
        g.interpret_governed_daily_technical_snapshot(**args)


@pytest.mark.parametrize(
    "change", ["omit_false", "reorder", "operand", "operator", "satisfied", "states"]
)
def test_semantic_output_correspondence(source, monkeypatch, change):
    if change == "states":
        monkeypatch.setattr(
            g,
            "classic_states",
            lambda s, c: (
                (classic.DailyTechnicalDirectionalState.NEGATIVE,) * 2
                + classic.classic_states(s, c)[2:]
            ),
        )
    else:
        original = g.build_classic_comparison_evidence

        def altered(s, c):
            items = original(s, c)
            if change == "omit_false":
                return tuple(item for item in items if item.satisfied)
            if change == "reorder":
                return tuple(reversed(items))
            item = items[0]
            if change == "operand":
                item = replace(
                    item,
                    left_operand=replace(
                        item.left_operand, value=item.left_operand.value + 1.0
                    ),
                )
            elif change == "operator":
                item = replace(
                    item,
                    operator=classic.TechnicalComparisonOperator.GREATER_THAN_OR_EQUAL,
                )
            else:
                object.__setattr__(item, "satisfied", not item.satisfied)
            return (item, *items[1:])

        monkeypatch.setattr(g, "build_classic_comparison_evidence", altered)
    with pytest.raises((TypeError, ValueError)):
        interpret(source)


@pytest.mark.parametrize(
    "name",
    [
        "source_technical_occurrence",
        "canonical_instrument_id",
        "source_trading_identity",
        "analysis_as_of",
        "source_technical_analysis_snapshot_fingerprint",
        "source_governed_dataset_fingerprint",
        "source_research_dataset_content_fingerprint",
        "source_quality",
        "source_warnings",
    ],
)
def test_coherently_changed_result_facts_refused(source, monkeypatch, name):
    original = g.GovernedDailyTechnicalInterpretation.__post_init__

    def changed(result):
        original(result)
        changes = {
            "source_technical_occurrence": reference(technical_history_sequence=2),
            "canonical_instrument_id": CanonicalInstrumentId("other"),
            "source_trading_identity": TradingInstrumentIdentity("MSFT", "NASDAQ"),
            "analysis_as_of": source.evidence.analysis_as_of + timedelta(days=1),
            "source_technical_analysis_snapshot_fingerprint": "sha256:" + "d" * 64,
            "source_governed_dataset_fingerprint": "sha256:" + "d" * 64,
            "source_research_dataset_content_fingerprint": "sha256:" + "d" * 64,
            "source_quality": technical.TechnicalAnalysisQuality.DEGRADED,
            "source_warnings": (technical.TechnicalAnalysisWarning.STALE_EVIDENCE,),
        }
        object.__setattr__(result, name, changes[name])
        refingerprint(result)
        result._validate()

    monkeypatch.setattr(
        g.GovernedDailyTechnicalInterpretation, "__post_init__", changed
    )
    with pytest.raises(ValueError, match="correspondence"):
        interpret(source)


def test_reordered_warnings_refused():
    result = interpret(make_snapshot(10, lag_days=12))
    with pytest.raises(ValueError, match="canonical order"):
        replace(result, source_warnings=tuple(reversed(result.source_warnings)))


def test_source_types_trading_correspondence_and_invalid_snapshots(source):
    args = arguments(source)
    for changes in (
        {"snapshot": object()},
        {"canonical_instrument": object()},
        {"source_governed_dataset_fingerprint": "bad"},
        {
            "canonical_instrument": replace(
                args["canonical_instrument"],
                trading_identity=TradingInstrumentIdentity("MSFT", "NASDAQ"),
            )
        },
    ):
        with pytest.raises((TypeError, ValueError)):
            g.interpret_governed_daily_technical_snapshot(**(args | changes))
    object.__setattr__(source, "fingerprint", "sha256:" + "0" * 64)
    with pytest.raises(ValueError):
        interpret(source)


def test_deterministic_content_and_distinct_source_occurrences(source):
    first = interpret(source)
    assert first == interpret(deepcopy(source))
    for changes in (
        {"technical_history_sequence": 2},
        {"technical_execution_id": "polygon_completed_daily_technical:" + "3" * 32},
        {
            "technical_history_namespace_id": (
                "polygon_completed_daily_technical_history:" + "3" * 32
            )
        },
        {"technical_fingerprint": "sha256:" + "d" * 64},
        {
            "artifact_reference": replace(
                reference().artifact_reference, artifact_version="2.0.0"
            )
        },
    ):
        other = interpret(source, source_technical_occurrence=reference(**changes))
        assert other.fingerprint != first.fingerprint
        assert other.comparison_evidence == first.comparison_evidence


def test_complete_fingerprint_payload_and_canonical_numeric_identity(source):
    result = interpret(source)
    assert result.fingerprint == (
        "sha256:95f49c65e0e1e2be0738b5f2512239ca4da3e876c099c1feb0f0ea3db32f7c55"
    )
    payload = result._fingerprint_payload()
    assert set(payload) == {item.name for item in fields(result)} - {"fingerprint"}
    assert result.fingerprint == canonical_fingerprint(payload)
    assert (
        payload["interpretation_policy_identity"]["configuration"]["rsi_neutral"]
        == "50.0"
    )
    assert isinstance(payload["comparison_evidence"][0]["left_operand"]["value"], str)
    for name in payload:
        altered = deepcopy(payload)
        altered[name] = "changed"
        assert canonical_fingerprint(altered) != result.fingerprint
    false_index = next(
        i for i, item in enumerate(result.comparison_evidence) if not item.satisfied
    )
    altered = deepcopy(payload)
    altered["comparison_evidence"][false_index]["satisfied"] = True
    assert canonical_fingerprint(altered) != result.fingerprint
    warned = interpret(make_snapshot(10, lag_days=12))._fingerprint_payload()
    reordered = deepcopy(warned)
    reordered["source_warnings"].reverse()
    assert canonical_fingerprint(warned) != canonical_fingerprint(reordered)
    legacy = deepcopy(payload)
    legacy["schema_version"] = classic.DAILY_TECHNICAL_INTERPRETATION_SCHEMA
    assert canonical_fingerprint(legacy) != result.fingerprint


def test_no_out_of_scope_execution_or_authority(source, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("out-of-scope execution")

    from market_platform.research import daily_technical_assessment as assessment
    from market_platform.research import daily_technical_strategy as strategy

    monkeypatch.setattr(technical, "analyze_daily_technical_snapshot", forbidden)
    monkeypatch.setattr(classic, "interpret_daily_technical_research", forbidden)
    monkeypatch.setattr(
        ClassicDailyTechnicalInterpretationPolicy, "interpret", forbidden
    )
    monkeypatch.setattr(assessment, "assess_daily_technical_interpretation", forbidden)
    monkeypatch.setattr(strategy, "derive_daily_technical_strategy", forbidden)
    result = interpret(source)
    assert result.to_dict()
    module = ast.parse(Path(g.__file__).read_text())
    imports = [
        node.module or ""
        for node in ast.walk(module)
        if isinstance(node, ast.ImportFrom)
    ]
    assert not any(
        "application" in name or "provider" in name or "data." in name
        for name in imports
    )
    assert not any("assessment" in name or "strategy" in name for name in imports)
    assert [
        name for name in imports if name.startswith("market_platform.evidence")
    ] == ["market_platform.evidence"]
    assert {
        name
        for name in dir(result)
        if callable(getattr(result, name)) and not name.startswith("_")
    } == {"to_dict"}


def test_frozen_package_and_evidence_inventory():
    from market_platform import evidence

    assert len(evidence.__all__) == len(set(evidence.__all__)) == 69
    assert (
        tomllib.loads(Path("pyproject.toml").read_text())["project"]["version"]
        == "0.1.0"
    )


@pytest.mark.parametrize("distance", [-5.0, 5.0])
def test_exact_extension_operand_equality_uses_released_helper(distance):
    from test_daily_technical_interpretation_assessment import _snapshot_values

    assert g.classic_states is classic.classic_states
    assert (
        g.build_classic_comparison_evidence is classic.build_classic_comparison_evidence
    )
    source = _snapshot_values(distance=distance)
    configuration = ClassicDailyTechnicalInterpretationConfiguration()
    assert g.classic_states(source, configuration)[3].value == "within_reference_band"
    assert all(
        not item.satisfied
        for item in g.build_classic_comparison_evidence(source, configuration)[-2:]
    )


@pytest.mark.parametrize(
    "rsi,evidence_id",
    [(70.0, "rsi_at_or_above_elevated"), (30.0, "rsi_at_or_below_depressed")],
)
def test_rsi_extreme_threshold_equality(source, rsi, evidence_id):
    result = interpret(adjusted(source, rsi_14=rsi))
    assert next(
        item for item in result.comparison_evidence if item.evidence_id == evidence_id
    ).satisfied


@pytest.mark.parametrize("field", ["schema_version", "fingerprint"])
def test_content_rejects_str_subclass(source, field):
    class Text(str):
        pass

    result = interpret(source)
    object.__setattr__(result, field, Text(getattr(result, field)))
    with pytest.raises(ValueError):
        result._validate()


def test_coherent_working_policy_refingerprint_still_refused(source, monkeypatch):
    original_copy = g.copy_technical_policy_identity
    copies = []

    def capture(identity):
        copied = original_copy(identity)
        copies.append(copied)
        return copied

    original = g.classic_states

    def mutate(snapshot, configuration):
        states = original(snapshot, configuration)
        identity = next(item for item in copies if item.configuration is configuration)
        object.__setattr__(configuration, "rsi_neutral", 51.0)
        refingerprint(identity)
        identity._validate()
        return states

    monkeypatch.setattr(g, "copy_technical_policy_identity", capture)
    monkeypatch.setattr(g, "classic_states", mutate)
    with pytest.raises(ValueError, match="fixed classic"):
        interpret(source)


def test_copy_failure_and_coherent_copy_change_refused(source, monkeypatch):
    original = g.deepcopy

    def corrupted_copy(value):
        copied = original(value)
        if type(copied) is technical.TechnicalAnalysisSnapshot:
            object.__setattr__(copied.evidence, "provider", "copy_rewrite")
            refingerprint(copied.evidence)
            refingerprint(copied)
            copied._validate()
        return copied

    monkeypatch.setattr(g, "deepcopy", corrupted_copy)
    with pytest.raises(ValueError, match="detachment"):
        interpret(source)

    def failed_copy(value):
        raise ValueError("copy failure")

    monkeypatch.setattr(g, "deepcopy", failed_copy)
    with pytest.raises(ValueError, match="copy failure"):
        interpret(source)


def test_released_slice8_source_shape_without_upstream_execution(monkeypatch):
    from test_polygon_completed_daily_production_technical import (
        _request,
        _service,
        authentic,
    )

    upstream = authentic.__wrapped__()
    retained = _service(upstream).execute(_request(upstream[1]))
    material = upstream[1].qualification.construction_result.material
    instrument = material.mapping_resolution_provenance.mapping.canonical_instrument
    args = dict(
        snapshot=retained.snapshot,
        source_technical_occurrence=reference(
            artifact_reference=retained.source.bridge_reference.artifact_reference,
            technical_history_namespace_id=retained.history_namespace_id,
            technical_history_sequence=retained.history_sequence,
            technical_execution_id=retained.execution_id,
            technical_fingerprint=retained.fingerprint,
        ),
        canonical_instrument=instrument,
        source_governed_dataset_fingerprint=retained.source.dataset_fingerprint,
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("upstream execution/resolution is out of scope")

    # The fixture has finished. No upstream work is allowed during Interpretation.
    for service in (
        upstream[0],
        upstream[0]._qualification_service,
        upstream[0]._qualification_service._validity_service,
    ):
        for name in ("bridge", "qualify", "execute", "_resolve", "_snapshot"):
            if hasattr(type(service), name):
                monkeypatch.setattr(type(service), name, forbidden)
    monkeypatch.setattr(technical, "analyze_daily_technical_snapshot", forbidden)
    result = g.interpret_governed_daily_technical_snapshot(**args)
    assert result.canonical_instrument_id == instrument.instrument_id
    assert (
        result.source_research_dataset_content_fingerprint
        == retained.source.evidence.dataset_content_fingerprint
    )
    assert result.source_quality is retained.snapshot.quality
    assert result.source_warnings == retained.snapshot.warnings
