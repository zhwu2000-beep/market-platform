from __future__ import annotations

import ast
import hashlib
import inspect
import json
from copy import copy, deepcopy
from dataclasses import FrozenInstanceError, fields, replace
from datetime import UTC, datetime, timedelta, timezone
from enum import IntEnum, StrEnum
from itertools import product
from pathlib import Path

import pytest
from test_governed_daily_technical_assessment import artifact, assess, source
from test_governed_daily_technical_interpretation import assert_enum_free

from market_platform._fingerprint import canonical_fingerprint
from market_platform.instruments.identity import CanonicalInstrumentId
from market_platform.research import classic_daily_technical as classic
from market_platform.research import daily_technical_strategy as legacy
from market_platform.research import governed_daily_technical_assessment as ga
from market_platform.research import governed_daily_technical_interpretation as gi
from market_platform.research import governed_daily_technical_strategy as g
from market_platform.trading.instrument import TradingInstrumentIdentity

FP = "sha256:" + "b" * 64
REQUEST_FIELDS = (
    "artifact_reference",
    "assessment_history_namespace_id",
    "assessment_history_sequence",
    "assessment_execution_id",
    "assessment_fingerprint",
)
CONTENT_FIELDS = (
    "source_assessment_occurrence",
    "source_assessment_content_fingerprint",
    "source_interpretation_content_fingerprint",
    "canonical_instrument_id",
    "analysis_as_of",
    "strategy_policy_identity",
    "mode",
    "rule_code",
    "schema_version",
    "fingerprint",
)
POLICY = {
    "schema_version": "technical_policy_identity/v1",
    "policy_kind": "daily_technical_strategy",
    "policy_id": "classic_daily_technical_strategy",
    "behavioral_revision": "1.0.0",
    "configuration_schema": "classic_daily_technical_strategy_configuration/v1",
    "configuration": {},
    "fingerprint": (
        "sha256:acbdd8c9ac7ba7d336f5f5e74b7484b05d0fc15b3a6f24bc81288d1fc8ea817e"
    ),
}


def request(**changes):
    return g.PolygonCompletedDailyStrategyRequest(
        **(
            dict(
                artifact_reference=artifact(),
                assessment_history_namespace_id="polygon_completed_daily_assessment_history:"
                + "1" * 32,
                assessment_history_sequence=1,
                assessment_execution_id="polygon_completed_daily_assessment:"
                + "2" * 32,
                assessment_fingerprint=FP,
            )
            | changes
        )
    )


def derive(a=None, i=None, r=None):
    i = source() if i is None else i
    return g.derive_governed_daily_technical_strategy(
        assessment=assess(i) if a is None else a,
        interpretation=i,
        source_assessment_occurrence=request() if r is None else r,
    )


def validate(content, a=None, i=None, r=None):
    i = source() if i is None else i
    g.validate_governed_daily_technical_strategy(
        content=content,
        assessment=assess(i) if a is None else a,
        interpretation=i,
        source_assessment_occurrence=request() if r is None else r,
    )


def refingerprint(value):
    object.__setattr__(
        value, "fingerprint", canonical_fingerprint(value._fingerprint_payload())
    )
    return value


class Text(str):
    pass


class Integer(int):
    pass


class TextCategory(StrEnum):
    VALUE = "positive_directional_continuation"


class NumberCategory(IntEnum):
    ONE = 1


def test_exact_public_contracts():
    assert g.__all__ == [
        "GOVERNED_DAILY_TECHNICAL_STRATEGY_SCHEMA",
        "PolygonCompletedDailyStrategyRequest",
        "GovernedDailyTechnicalStrategyPolicyIdentity",
        "GovernedDailyTechnicalStrategy",
        "derive_governed_daily_technical_strategy",
        "validate_governed_daily_technical_strategy",
    ]
    r, content = request(), derive()
    assert tuple(f.name for f in fields(r)) == REQUEST_FIELDS
    assert set(r.to_dict()) == set(REQUEST_FIELDS)
    assert not hasattr(r, "schema_version") and not hasattr(r, "fingerprint")
    assert tuple(f.name for f in fields(content)) == CONTENT_FIELDS
    assert set(content.to_dict()) == set(CONTENT_FIELDS)
    assert (
        content.schema_version
        == g.GOVERNED_DAILY_TECHNICAL_STRATEGY_SCHEMA
        == "governed_daily_technical_strategy/v1"
    )
    for value in (r, content, content.strategy_policy_identity):
        assert not hasattr(value, "__dict__")
        with pytest.raises(FrozenInstanceError):
            setattr(value, fields(value)[0].name, "changed")
    assert all(
        p.kind is inspect.Parameter.KEYWORD_ONLY
        for p in inspect.signature(type(r)).parameters.values()
    )
    assert (
        inspect.signature(g.GovernedDailyTechnicalStrategyPolicyIdentity).parameters
        == {}
    )


@pytest.mark.parametrize(
    "name,value",
    [
        ("artifact_reference", object()),
        ("assessment_history_sequence", True),
        ("assessment_history_sequence", Integer(1)),
        ("assessment_history_sequence", NumberCategory.ONE),
        ("assessment_history_sequence", 0),
        ("assessment_history_sequence", -1),
        ("assessment_history_sequence", 1.0),
        (
            "assessment_history_namespace_id",
            Text("polygon_completed_daily_assessment_history:" + "1" * 32),
        ),
        (
            "assessment_history_namespace_id",
            "polygon_completed_daily_assessment_history:" + "A" * 32,
        ),
        (
            "assessment_history_namespace_id",
            "polygon_completed_daily_interpretation_history:" + "1" * 32,
        ),
        ("assessment_execution_id", "polygon_completed_daily_assessment:short"),
        (
            "assessment_execution_id",
            Text("polygon_completed_daily_assessment:" + "1" * 32),
        ),
        ("assessment_fingerprint", Text(FP)),
        ("assessment_fingerprint", "sha256:" + "A" * 64),
        ("assessment_fingerprint", "sha256:" + "a" * 63),
    ],
)
def test_request_exact_scalars(name, value):
    with pytest.raises((TypeError, ValueError)):
        request(**{name: value})


def test_reference_exact_type_and_detach_before_validation(monkeypatch):
    class Reference(gi.GovernedTechnicalArtifactReference):
        pass

    with pytest.raises(TypeError):
        request(
            artifact_reference=Reference(
                artifact_id="test",
                artifact_version="1",
                artifact_fingerprint=FP,
                information_class="source_observation",
                authority="external_origin",
            )
        )
    supplied = artifact()
    original = gi.GovernedTechnicalArtifactReference._validate
    seen = []

    def check(value):
        assert value is not supplied
        seen.append(value)
        original(value)

    monkeypatch.setattr(gi.GovernedTechnicalArtifactReference, "_validate", check)
    r = request(artifact_reference=supplied)
    assert seen and r.artifact_reference is not supplied
    expected = r.to_dict()
    object.__setattr__(supplied, "artifact_id", "changed")
    assert r.to_dict() == expected


@pytest.mark.parametrize(
    "name", ["fingerprint", "schema_version", "artifact_fingerprint"]
)
def test_copy_does_not_repair_caller_reference(name):
    supplied = artifact()
    object.__setattr__(supplied, name, "invalid")
    with pytest.raises(ValueError):
        request(artifact_reference=supplied)


def test_fixed_policy_and_fresh_configuration():
    p = g.GovernedDailyTechnicalStrategyPolicyIdentity()
    assert (
        p.to_dict()
        == POLICY
        == classic.ClassicDailyTechnicalStrategyPolicy().policy_identity.to_dict()
    )
    assert all(type(v) is str for k, v in p.to_dict().items() if k != "configuration")
    assert p.configuration is not p.configuration
    p.configuration["changed"] = True
    projection = p.to_dict()
    projection["configuration"]["changed"] = True
    assert p.to_dict() == POLICY
    with pytest.raises(TypeError):
        g.GovernedDailyTechnicalStrategyPolicyIdentity(configuration={})


@pytest.mark.parametrize("name", [k for k in POLICY if k != "configuration"])
@pytest.mark.parametrize("change", ["wrong", "subclass", "refingerprint"])
def test_policy_complete_projection_not_digest_only(name, change):
    p = g.GovernedDailyTechnicalStrategyPolicyIdentity()
    object.__setattr__(
        p, name, Text(getattr(p, name)) if change == "subclass" else "wrong"
    )
    if change == "refingerprint" and name != "fingerprint":
        refingerprint(p)
    with pytest.raises(ValueError):
        p.to_dict()
    with pytest.raises(ValueError):
        replace(derive(), strategy_policy_identity=p)


def test_complete_canonical_fingerprint_and_determinism():
    i, r = source(), request()
    a = assess(i)
    result = derive(a, i, r)
    assert result == derive(deepcopy(a), deepcopy(i), deepcopy(r))
    payload = result.to_dict()
    digest = payload.pop("fingerprint")
    assert (
        digest
        == "sha256:"
        + hashlib.sha256(
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
    )
    assert payload["analysis_as_of"] == "2026-01-02T00:00:00+00:00"
    for key in payload:
        changed = deepcopy(payload)
        changed[key] = "changed"
        assert canonical_fingerprint(changed) != digest
    assert (
        result.source_assessment_content_fingerprint
        == a.fingerprint
        != r.assessment_fingerprint
    )
    assert result.source_interpretation_content_fingerprint == i.fingerprint


@pytest.mark.parametrize(
    "changes",
    [
        {
            "assessment_history_namespace_id": (
                "polygon_completed_daily_assessment_history:" + "9" * 32
            )
        },
        {"assessment_history_sequence": 2},
        {"assessment_execution_id": "polygon_completed_daily_assessment:" + "9" * 32},
        {"assessment_fingerprint": "sha256:" + "9" * 64},
    ],
)
def test_occurrence_binding_is_not_authentication(changes):
    first, second = derive(), derive(r=request(**changes))
    assert first.fingerprint != second.fingerprint
    assert (
        first.source_assessment_content_fingerprint
        == second.source_assessment_content_fingerprint
    )
    validate(second, r=request(**changes))
    with pytest.raises(ValueError):
        validate(first, r=request(**changes))
    # There is no result envelope in this domain. Even substitution of content
    # for an envelope digest is not detectable here; application must reject it.
    a = assess(source())
    value = derive(a=a, r=request(assessment_fingerprint=a.fingerprint))
    assert value.source_assessment_occurrence.assessment_fingerprint == a.fingerprint


@pytest.mark.parametrize(
    "changes,outcome,mode,rule",
    [
        (
            {"trend_direction": "unavailable"},
            "insufficient_data",
            "no_active_strategy",
            "insufficient_data_no_active_strategy",
        ),
        (
            {"trend_direction": "mixed"},
            "mixed",
            "no_active_strategy",
            "mixed_no_active_strategy",
        ),
        (
            {"source_quality": "degraded"},
            "caution",
            "no_active_strategy",
            "caution_no_active_strategy",
        ),
        (
            {},
            "aligned",
            "positive_directional_continuation",
            "aligned_positive_continuation",
        ),
        (
            {"trend_direction": "negative", "momentum_direction": "negative"},
            "aligned",
            "negative_directional_continuation",
            "aligned_negative_continuation",
        ),
    ],
)
def test_all_five_released_rows(changes, outcome, mode, rule):
    i = source(**changes)
    a = assess(i)
    assert a.outcome == outcome
    value = derive(a, i)
    assert (value.mode, value.rule_code) == (mode, rule)
    validate(value, a, i)


@pytest.mark.parametrize(
    "trend,momentum",
    [
        p
        for p in product(("positive", "negative", "mixed", "unavailable"), repeat=2)
        if p not in (("positive", "positive"), ("negative", "negative"))
    ],
)
def test_unsupported_aligned_combinations_fail_closed(trend, momentum):
    i = source(trend_direction=trend, momentum_direction=momentum)
    a = replace(
        assess(source()), source_interpretation_content_fingerprint=i.fingerprint
    )
    with pytest.raises(ValueError):
        derive(a, i)
    with pytest.raises(ValueError):
        validate(derive(), a, i)


@pytest.mark.parametrize(
    "target,name,value",
    [
        ("assessment", "outcome", "future"),
        ("interpretation", "trend_direction", "future"),
        ("interpretation", "momentum_direction", "future"),
        ("interpretation", "source_quality", "future"),
        ("interpretation", "source_warnings", ("future",)),
        ("interpretation", "trend_direction", Text("positive")),
    ],
)
def test_unknown_source_values_fail_closed(target, name, value):
    i = source()
    a = assess(i)
    object.__setattr__(a if target == "assessment" else i, name, value)
    with pytest.raises((TypeError, ValueError)):
        derive(a, i)
    with pytest.raises((TypeError, ValueError)):
        validate(derive(), a, i)


def test_one_semantic_authority_and_independent_validation(monkeypatch):
    i, r = source(), request()
    a = assess(i)
    original = classic._classic_strategy_semantics
    assessment_validator = ga.validate_governed_daily_technical_assessment
    calls = []

    def check_assessment(**kwargs):
        assert kwargs["content"] is not a
        assert kwargs["interpretation"] is not i
        calls.append("assessment")
        return assessment_validator(**kwargs)

    def helper(iv, av):
        assert {f.name for f in fields(iv)} == {"trend_direction", "momentum_direction"}
        assert {f.name for f in fields(av)} == {"outcome"}
        calls.append("strategy")
        return original(iv, av)

    monkeypatch.setattr(classic, "_classic_strategy_semantics", helper)
    monkeypatch.setattr(
        ga, "validate_governed_daily_technical_assessment", check_assessment
    )
    result = derive(a, i, r)
    assert calls == ["assessment", "strategy"]

    def forbidden(*args, **kwargs):
        raise AssertionError("forbidden derivation")

    monkeypatch.setattr(g, "derive_governed_daily_technical_strategy", forbidden)
    validate(result, a, i, r)
    assert calls == ["assessment", "strategy", "assessment", "strategy"]


def test_helper_output_is_used_not_a_duplicate_mapping(monkeypatch):
    monkeypatch.setattr(
        classic,
        "_classic_strategy_semantics",
        lambda *args: (
            legacy.DailyTechnicalStrategyMode.NO_ACTIVE_STRATEGY,
            legacy.DailyTechnicalStrategyRuleCode.CAUTION_NO_ACTIVE_STRATEGY,
        ),
    )
    value = derive()
    assert (value.mode, value.rule_code) == (
        "no_active_strategy",
        "caution_no_active_strategy",
    )
    validate(value)


def test_assessment_validator_failure_propagates_before_strategy(monkeypatch):
    i = source()
    a = assess(i)

    class SourceFailure(ValueError):
        pass

    def fail(**kwargs):
        raise SourceFailure("source")

    def forbidden(*args):
        raise AssertionError("must not reach Strategy helper")

    candidate = derive(a, i)
    monkeypatch.setattr(ga, "validate_governed_daily_technical_assessment", fail)
    monkeypatch.setattr(classic, "_classic_strategy_semantics", forbidden)
    with pytest.raises(SourceFailure):
        derive(a, i)
    with pytest.raises(SourceFailure):
        validate(candidate, a, i)


@pytest.mark.parametrize(
    "name,value",
    [
        ("source_interpretation_content_fingerprint", FP),
        ("canonical_instrument_id", CanonicalInstrumentId("other")),
        ("analysis_as_of", datetime(2026, 2, 1, tzinfo=UTC)),
        ("source_trading_identity", TradingInstrumentIdentity("MSFT", "NASDAQ")),
        ("source_quality", "degraded"),
        ("source_warnings", ("stale_evidence",)),
        ("outcome", "mixed"),
        (
            "findings",
            (
                ga.GovernedDailyTechnicalAssessmentFinding(
                    "caution", "source_quality_degraded", ()
                ),
            ),
        ),
    ],
)
def test_complete_assessment_interpretation_correspondence(name, value):
    i = source()
    a = replace(assess(i), **{name: value})
    a.to_dict()
    with pytest.raises(ValueError):
        derive(a, i)
    with pytest.raises(ValueError):
        validate(derive(), a, i)


def test_wrong_bound_interpretation_and_artifact_rejected():
    i = source(source_quality="degraded")
    with pytest.raises(ValueError):
        derive(assess(source()), i)
    r = request(artifact_reference=replace(artifact(), artifact_version="2"))
    with pytest.raises(ValueError):
        derive(r=r)
    a = assess(source())
    a = replace(
        a,
        source_interpretation_occurrence=replace(
            a.source_interpretation_occurrence, artifact_reference=r.artifact_reference
        ),
    )
    with pytest.raises(ValueError):
        derive(a=a, r=r)


def test_ordered_warning_correspondence():
    i = source(source_warnings=("insufficient_profile_history", "stale_evidence"))
    a = assess(i)
    object.__setattr__(a, "source_warnings", tuple(reversed(a.source_warnings)))
    refingerprint(a)
    with pytest.raises(ValueError):
        derive(a, i)


@pytest.mark.parametrize(
    "changes",
    [
        {
            "mode": "negative_directional_continuation",
            "rule_code": "aligned_negative_continuation",
        },
        {"mode": "no_active_strategy", "rule_code": "mixed_no_active_strategy"},
        {"source_assessment_occurrence": request(assessment_history_sequence=2)},
        {"source_assessment_content_fingerprint": FP},
        {"source_interpretation_content_fingerprint": FP},
        {"canonical_instrument_id": CanonicalInstrumentId("other")},
        {"analysis_as_of": datetime(2026, 2, 1, tzinfo=UTC)},
    ],
)
def test_coherent_wrong_candidate_rejected(changes):
    candidate = replace(derive(), **changes)
    candidate.to_dict()
    with pytest.raises(ValueError):
        validate(candidate)


@pytest.mark.parametrize(
    "name,value",
    [
        ("mode", "future"),
        ("mode", TextCategory.VALUE),
        ("rule_code", Text("aligned_positive_continuation")),
        ("rule_code", "mixed_no_active_strategy"),
        ("source_assessment_content_fingerprint", Text(FP)),
        ("source_interpretation_content_fingerprint", "invalid"),
        ("analysis_as_of", datetime(2026, 1, 2)),
        ("analysis_as_of", datetime(2026, 1, 2, tzinfo=timezone(timedelta(hours=8)))),
        ("canonical_instrument_id", "us-aapl"),
        (
            "strategy_policy_identity",
            classic.ClassicDailyTechnicalStrategyPolicy().policy_identity,
        ),
        ("source_assessment_occurrence", object()),
    ],
)
def test_exact_content_contract(name, value):
    with pytest.raises((TypeError, ValueError)):
        replace(derive(), **{name: value})


@pytest.mark.parametrize("name", ["schema_version", "fingerprint"])
def test_candidate_schema_and_fingerprint(name):
    value = derive()
    object.__setattr__(value, name, Text(getattr(value, name)))
    with pytest.raises(ValueError):
        validate(value)
    object.__setattr__(value, name, "invalid")
    with pytest.raises(ValueError):
        validate(value)


def test_zero_enum_and_nested_copy_isolation():
    i, r = source(), request()
    a = assess(i)
    first, second = derive(a, i, r), derive(a, i, r)
    expected = second.to_dict()
    legacy_before = (
        classic.ClassicDailyTechnicalStrategyPolicy().policy_identity.to_dict()
    )
    for value in (
        r,
        r.artifact_reference,
        first.strategy_policy_identity,
        first.strategy_policy_identity.configuration,
        first,
        first.to_dict(),
        copy(first),
        deepcopy(first),
        replace(first),
    ):
        assert_enum_free(value)
    for clone in (copy(first), deepcopy(first), replace(first)):
        assert (
            clone.source_assessment_occurrence is not first.source_assessment_occurrence
        )
        assert (
            clone.source_assessment_occurrence.artifact_reference
            is not first.source_assessment_occurrence.artifact_reference
        )
        assert clone.canonical_instrument_id is not first.canonical_instrument_id
        assert clone.strategy_policy_identity is not first.strategy_policy_identity
        object.__setattr__(
            clone.source_assessment_occurrence.artifact_reference,
            "artifact_id",
            "changed",
        )
        object.__setattr__(clone.canonical_instrument_id, "instrument_id", "changed")
        object.__setattr__(clone.strategy_policy_identity, "policy_id", "changed")
        assert first.to_dict() == expected
    projection = first.to_dict()
    projection["source_assessment_occurrence"]["artifact_reference"]["artifact_id"] = (
        "changed"
    )
    projection["strategy_policy_identity"]["configuration"]["changed"] = True
    object.__setattr__(
        first.source_assessment_occurrence, "assessment_history_sequence", 2
    )
    refingerprint(first)
    with pytest.raises(ValueError):
        validate(first, a, i, r)
    assert second.to_dict() == expected == derive(a, i, r).to_dict()
    assert (
        classic.ClassicDailyTechnicalStrategyPolicy().policy_identity.to_dict()
        == legacy_before
    )
    clone = copy(r)
    object.__setattr__(clone.artifact_reference, "artifact_id", "changed")
    assert r.to_dict() == request().to_dict()


def test_no_upstream_execution_or_legacy_runner(monkeypatch):
    i = source()
    a = assess(i)

    def forbidden(*args, **kwargs):
        raise AssertionError("forbidden execution")

    for module, name in (
        (legacy, "derive_daily_technical_strategy"),
        (classic.ClassicDailyTechnicalStrategyPolicy, "determine"),
        (classic.ClassicDailyTechnicalInterpretationPolicy, "interpret"),
        (classic.ClassicDailyTechnicalAssessmentPolicy, "assess"),
        (ga, "assess_governed_daily_technical_interpretation"),
        (gi, "interpret_governed_daily_technical_snapshot"),
        (gi, "validate_governed_daily_technical_interpretation"),
        (gi, "classic_states"),
        (gi, "build_classic_comparison_evidence"),
    ):
        monkeypatch.setattr(module, name, forbidden)
    value = derive(a, i)
    validate(value, a, i)
    tree = ast.parse(Path(g.__file__).read_text())
    imports = [
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    ]
    assert not any(
        any(
            word in (module or "")
            for word in (
                "application",
                "provider",
                "threading",
                "asyncio",
                "uuid",
                "time",
            )
        )
        for module in imports
        if module != "datetime"
    )
    calls = [
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]
    assert not set(calls) & {
        "execute",
        "determine",
        "interpret",
        "assess",
        "now",
        "utcnow",
        "get_result_history_as_of",
        "fetch",
        "acquire",
    }
    assert calls.count("_classic_strategy_semantics") == 1
    assert not any(
        isinstance(node, (ast.If, ast.Match))
        and any(
            isinstance(child, ast.Attribute)
            and child.attr in ("outcome", "trend_direction", "momentum_direction")
            for child in ast.walk(
                node.test if isinstance(node, ast.If) else node.subject
            )
        )
        for node in ast.walk(tree)
    )
    names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.ClassDef, ast.FunctionDef))
    }
    assert not any(
        any(
            word in name.lower()
            for word in ("result", "application", "lock", "history", "publish", "owner")
        )
        for name in names
    )
    assert not set(CONTENT_FIELDS) & {
        "action",
        "recommendation",
        "signal",
        "order_intent",
        "entry",
        "target",
        "stop",
        "quantity",
        "position_target",
        "outcome",
        "findings",
        "warnings",
        "confidence",
        "thesis",
        "source_trading_identity",
    }


@pytest.mark.parametrize(
    "target", ["assessment", "interpretation", "request", "adapter"]
)
def test_source_and_adapter_drift_rejected(monkeypatch, target):
    i, r = source(), request()
    a = assess(i)
    original = classic._classic_strategy_semantics

    def helper(iv, av):
        result = original(iv, av)
        if target == "assessment":
            object.__setattr__(a, "outcome", "mixed")
            refingerprint(a)
        elif target == "interpretation":
            object.__setattr__(i, "trend_direction", "mixed")
            refingerprint(i)
        elif target == "request":
            object.__setattr__(r, "assessment_history_sequence", 2)
        else:
            object.__setattr__(
                iv, "trend_direction", classic.DailyTechnicalDirectionalState.MIXED
            )
        return result

    monkeypatch.setattr(classic, "_classic_strategy_semantics", helper)
    with pytest.raises(ValueError, match="drift"):
        derive(a, i, r)


def test_constructor_corruption_is_checked_without_second_helper_call(monkeypatch):
    original = g.GovernedDailyTechnicalStrategy.__post_init__

    def corrupt(value):
        original(value)
        object.__setattr__(value, "source_assessment_content_fingerprint", FP)
        refingerprint(value)

    monkeypatch.setattr(g.GovernedDailyTechnicalStrategy, "__post_init__", corrupt)
    with pytest.raises(ValueError, match="correspondence"):
        derive()


@pytest.mark.parametrize(
    "which", ["assessment", "interpretation", "request", "content"]
)
def test_exact_outer_types(which):
    values = dict(
        assessment=assess(source()),
        interpretation=source(),
        source_assessment_occurrence=request(),
    )
    key = {"request": "source_assessment_occurrence"}.get(which, which)
    if which == "content":
        with pytest.raises(TypeError):
            g.validate_governed_daily_technical_strategy(content=object(), **values)
    else:
        value = values[key]

        class Subclass(type(value)):
            pass

        altered = object.__new__(Subclass)
        for f in fields(value):
            object.__setattr__(altered, f.name, getattr(value, f.name))
        values[key] = altered
        with pytest.raises(TypeError):
            g.derive_governed_daily_technical_strategy(**values)
        with pytest.raises(TypeError):
            g.validate_governed_daily_technical_strategy(content=derive(), **values)


@pytest.mark.parametrize(
    "target",
    [
        "assessment",
        "interpretation",
        "assessment_policy",
        "interpretation_policy",
        "artifact",
    ],
)
def test_detachment_preserves_invalid_source_fingerprints(target):
    i = source()
    a = assess(i)
    value = {
        "assessment": a,
        "interpretation": i,
        "assessment_policy": a.assessment_policy_identity,
        "interpretation_policy": i.interpretation_policy_identity,
        "artifact": a.source_interpretation_occurrence.artifact_reference,
    }[target]
    object.__setattr__(value, "fingerprint", FP)
    with pytest.raises(ValueError):
        derive(a, i)
    with pytest.raises(ValueError):
        validate(derive(), a, i)


@pytest.mark.parametrize("target", ["assessment", "interpretation"])
def test_coherent_upstream_policy_change_rejected(target):
    i = source()
    a = assess(i)
    value = (
        a.assessment_policy_identity
        if target == "assessment"
        else i.interpretation_policy_identity
    )
    object.__setattr__(value, "policy_id", "other")
    refingerprint(value)
    with pytest.raises(ValueError):
        derive(a, i)


def test_constructor_detaches_all_nested_inputs():
    original = derive()
    r = request()
    p = g.GovernedDailyTechnicalStrategyPolicyIdentity()
    instrument = CanonicalInstrumentId("us-aapl")
    value = replace(
        original,
        source_assessment_occurrence=r,
        strategy_policy_identity=p,
        canonical_instrument_id=instrument,
    )
    expected = value.to_dict()
    assert value.source_assessment_occurrence is not r
    assert (
        value.source_assessment_occurrence.artifact_reference
        is not r.artifact_reference
    )
    assert value.strategy_policy_identity is not p
    assert value.canonical_instrument_id is not instrument
    object.__setattr__(r, "assessment_history_sequence", 2)
    object.__setattr__(r.artifact_reference, "artifact_id", "changed")
    object.__setattr__(p, "policy_id", "changed")
    object.__setattr__(instrument, "instrument_id", "changed")
    assert value.to_dict() == expected


def test_helper_failure_and_unknown_outputs_fail_closed(monkeypatch):
    from types import SimpleNamespace

    i = source()
    a = assess(i)
    candidate = derive(a, i)
    for mode, rule in (
        ("future", "future"),
        (TextCategory.VALUE, "aligned_positive_continuation"),
        ("positive_directional_continuation", "future"),
    ):
        monkeypatch.setattr(
            classic,
            "_classic_strategy_semantics",
            lambda *args, mode=mode, rule=rule: (
                SimpleNamespace(value=mode),
                SimpleNamespace(value=rule),
            ),
        )
        with pytest.raises(ValueError):
            derive(a, i)
        with pytest.raises(ValueError):
            validate(candidate, a, i)

    def fail(*args):
        raise ValueError("helper failed")

    monkeypatch.setattr(classic, "_classic_strategy_semantics", fail)
    with pytest.raises(ValueError, match="helper failed"):
        derive(a, i)
    with pytest.raises(ValueError, match="helper failed"):
        validate(candidate, a, i)
