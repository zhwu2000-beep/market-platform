"""Pure transition decisions; accepted-input correspondence is not authority."""

import json
from dataclasses import FrozenInstanceError, fields, replace
from datetime import UTC, date, datetime
from itertools import product

import pytest

from market_platform.instruments.identity import CanonicalInstrumentId
from market_platform.radar.lightweight_observation import (
    EMA8_EMA20_CALCULATION_REVISION,
    EMA8_EMA20_OBSERVATION_DEFINITION_ID,
    EMA8_EMA20_OBSERVATION_SCHEMA,
    RadarEmaRelation,
    RadarLightweightObservation,
)
from market_platform.radar.meaningful_change import (
    RadarComparisonKind as Kind,
)
from market_platform.radar.meaningful_change import (
    RadarMeaningfulChangeClassification as Classification,
)
from market_platform.radar.meaningful_change import (
    RadarMeaningfulChangeDecision,
    RadarMeaningfulChangePolicyIdentity,
    evaluate_meaningful_change,
)
from market_platform.radar.meaningful_change import (
    RadarMeaningfulChangeReason as Reason,
)
from market_platform.radar.meaningful_change import (
    RadarObservationIncompatibility as Incompatibility,
)
from market_platform.radar.observation import RadarMarketContentScope


def observation(relation=RadarEmaRelation.ABOVE, *, later=False, corrected=False):
    end = date(2026, 9, 24 if later else 23)
    start = date(2025, 10, 2 if later else 1)
    return RadarLightweightObservation(
        CanonicalInstrumentId("test"),
        EMA8_EMA20_OBSERVATION_DEFINITION_ID,
        EMA8_EMA20_CALCULATION_REVISION,
        EMA8_EMA20_OBSERVATION_SCHEMA,
        end,
        "sha256:" + ("b" if corrected or later else "a") * 64,
        RadarMarketContentScope(start, end),
        relation,
        datetime(2026, 9, 25, tzinfo=UTC),
    )


def test_baseline():
    current = observation()
    result = evaluate_meaningful_change(None, current)
    assert result.prior is None and result.current is current
    assert result.classification is Classification.BASELINE_INITIALIZED
    assert result.reason is Reason.BASELINE_INITIALIZED
    assert result.comparison_kind is Kind.MISSING_PRIOR
    assert not result.meaningful_change
    assert result.incompatibilities == ()
    assert result.policy.to_dict() == {
        "policy_id": "ema8_ema20_relation_transition",
        "behavioral_revision": "1",
        "decision_schema": "radar_meaningful_change_decision/v1",
    }


@pytest.mark.parametrize(
    "prior_relation,current_relation", tuple(product(RadarEmaRelation, repeat=2))
)
@pytest.mark.parametrize("new_session", [True, False])
def test_all_pairs(prior_relation, current_relation, new_session):
    prior = observation(prior_relation)
    current = observation(
        current_relation, later=new_session, corrected=not new_session
    )
    result = evaluate_meaningful_change(prior, current)
    changed = prior_relation is not current_relation
    assert result.meaningful_change is changed
    assert result.classification is (
        Classification.STATE_TRANSITION if changed else Classification.STATE_UNCHANGED
    )
    assert result.comparison_kind is (
        Kind.NEW_SESSION if new_session else Kind.CORRECTED_CONTENT
    )
    assert result.reason is (
        Reason.NEW_SESSION_STATE_TRANSITION
        if changed and new_session
        else Reason.CORRECTED_CONTENT_STATE_TRANSITION
        if changed
        else Reason.STATE_UNCHANGED
    )
    assert result.incompatibilities == ()


def test_rolling_window_and_skipped_sessions():
    current = observation(RadarEmaRelation.BELOW, later=True)
    current = replace(
        current,
        completed_session=date(2026, 9, 30),
        content_scope=RadarMarketContentScope(date(2025, 10, 8), date(2026, 9, 30)),
    )
    assert (
        evaluate_meaningful_change(observation(), current).reason
        is Reason.NEW_SESSION_STATE_TRANSITION
    )


@pytest.mark.parametrize("relation", RadarEmaRelation)
def test_identical_content(relation):
    prior = observation(relation)
    result = evaluate_meaningful_change(
        prior, replace(prior, as_of=datetime(2026, 9, 26, tzinfo=UTC))
    )
    assert result.reason is Reason.STATE_UNCHANGED
    assert result.comparison_kind is Kind.SAME_CONTENT
    assert not result.meaningful_change


@pytest.mark.parametrize(
    "prior_relation,current_relation",
    [(a, b) for a, b in product(RadarEmaRelation, repeat=2) if a is not b],
)
def test_incoherent_relation(prior_relation, current_relation):
    with pytest.raises(ValueError, match="incoherent"):
        evaluate_meaningful_change(
            observation(prior_relation), observation(current_relation)
        )


def test_same_session_scope_mismatch():
    current = replace(
        observation(),
        content_scope=RadarMarketContentScope(date(2025, 10, 2), date(2026, 9, 23)),
    )
    with pytest.raises(ValueError, match="concrete scope"):
        evaluate_meaningful_change(observation(), current)


@pytest.mark.parametrize("incompatible", [False, True])
def test_invalid_attachment_precedes_incompatibility(incompatible):
    prior = observation(later=True)
    if incompatible:
        prior = replace(prior, calculation_revision="2")
    with pytest.raises(ValueError, match="reversed"):
        evaluate_meaningful_change(prior, observation())
    with pytest.raises(ValueError, match="instrument"):
        evaluate_meaningful_change(
            replace(prior, instrument=CanonicalInstrumentId("other")),
            observation(later=True),
        )


@pytest.mark.parametrize(
    "field,value,category",
    [
        ("definition_id", "other_observation", Incompatibility.DEFINITION_MISMATCH),
        ("calculation_revision", "2", Incompatibility.CALCULATION_REVISION_MISMATCH),
        (
            "observation_schema",
            "observation/v2",
            Incompatibility.OBSERVATION_SCHEMA_MISMATCH,
        ),
    ],
)
@pytest.mark.parametrize("different_scope", [False, True])
def test_incompatible(field, value, category, different_scope):
    prior = replace(observation(), **{field: value})
    if different_scope:
        prior = replace(
            prior,
            content_scope=RadarMarketContentScope(date(2025, 10, 2), date(2026, 9, 23)),
        )
    assert RadarLightweightObservation.from_dict(prior.to_dict()) == prior
    result = evaluate_meaningful_change(prior, observation())
    assert result.classification is Classification.INCOMPARABLE_BASELINE_INITIALIZED
    assert result.reason is Reason.INCOMPARABLE_BASELINE_INITIALIZED
    assert result.comparison_kind is Kind.INCOMPATIBLE_PRIOR
    assert result.incompatibilities == (category,)
    assert not result.meaningful_change


def test_multiple_incompatibilities_deterministic():
    prior = replace(
        observation(),
        definition_id="other",
        calculation_revision="2",
        observation_schema="other/v2",
    )
    result = evaluate_meaningful_change(prior, observation())
    assert result.incompatibilities == (
        Incompatibility.DEFINITION_MISMATCH,
        Incompatibility.CALCULATION_REVISION_MISMATCH,
        Incompatibility.OBSERVATION_SCHEMA_MISMATCH,
    )
    assert (
        result.to_dict() == evaluate_meaningful_change(prior, observation()).to_dict()
    )
    with pytest.raises(ValueError):
        replace(result, incompatibilities=tuple(reversed(result.incompatibilities)))


@pytest.mark.parametrize("schema", ["future/v2", "", "radar_market_content_scope/v2"])
def test_unsupported_scope_is_not_incompatibility(schema):
    with pytest.raises(ValueError):
        RadarMarketContentScope(date(2025, 10, 1), date(2026, 9, 23), schema)
    raw = observation().to_dict()
    raw["content_scope"]["schema_version"] = schema
    with pytest.raises(ValueError):
        evaluate_meaningful_change(
            RadarLightweightObservation.from_dict(raw), observation()
        )


def test_reserved_scope_category_cannot_be_injected():
    reserved = Incompatibility.CONTENT_SCOPE_SEMANTICS_MISMATCH
    assert json.loads(json.dumps(reserved)) == "CONTENT_SCOPE_SEMANTICS_MISMATCH"
    with pytest.raises(ValueError):
        Incompatibility("corrupt scope")
    with pytest.raises(ValueError):
        replace(
            evaluate_meaningful_change(observation(), observation()),
            incompatibilities=(reserved,),
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"prior": None},
        {"classification": Classification.STATE_UNCHANGED},
        {"reason": Reason.CORRECTED_CONTENT_STATE_TRANSITION},
        {"comparison_kind": Kind.MISSING_PRIOR},
        {"incompatibilities": (Incompatibility.DEFINITION_MISMATCH,)},
        {"incompatibilities": ("free text",)},
        {"incompatibilities": []},
        {"policy": "policy"},
        {"classification": "STATE_TRANSITION"},
    ],
)
def test_contradictory_or_untyped_decision(changes):
    result = evaluate_meaningful_change(
        observation(), observation(RadarEmaRelation.BELOW, later=True)
    )
    with pytest.raises((ValueError, TypeError)):
        replace(result, **changes)


def test_baseline_and_incomparable_invariants():
    baseline = evaluate_meaningful_change(None, observation())
    with pytest.raises(ValueError):
        replace(baseline, prior=observation())
    incompatible = evaluate_meaningful_change(
        replace(observation(), calculation_revision="2"), observation()
    )
    with pytest.raises(ValueError):
        replace(incompatible, incompatibilities=())
    unchanged = evaluate_meaningful_change(observation(), observation(later=True))
    with pytest.raises(ValueError):
        replace(
            unchanged,
            classification=Classification.STATE_TRANSITION,
            reason=Reason.NEW_SESSION_STATE_TRANSITION,
        )


@pytest.mark.parametrize(
    "field", ["policy_id", "behavioral_revision", "decision_schema"]
)
def test_fixed_policy(field):
    with pytest.raises(ValueError):
        replace(RadarMeaningfulChangePolicyIdentity(), **{field: "other"})
    with pytest.raises(TypeError):
        replace(RadarMeaningfulChangePolicyIdentity(), **{field: 1})


def test_immutable_derived_and_passive():
    result = evaluate_meaningful_change(None, observation())
    assert "meaningful_change" not in {f.name for f in fields(result)}
    assert not hasattr(result, "__dict__")
    with pytest.raises((FrozenInstanceError, TypeError, AttributeError)):
        result.meaningful_change = True
    with pytest.raises(TypeError):
        RadarMeaningfulChangeDecision(
            **{f.name: getattr(result, f.name) for f in fields(result)},
            meaningful_change=True,
        )
    raw = result.to_dict()
    assert json.dumps(raw) == json.dumps(result.to_dict())
    raw["current"]["instrument"]["instrument_id"] = "changed"
    assert result.current.instrument == CanonicalInstrumentId("test")
    assert set(result.to_dict()) == {
        "prior",
        "current",
        "policy",
        "classification",
        "reason",
        "comparison_kind",
        "incompatibilities",
        "meaningful_change",
    }


@pytest.mark.parametrize(
    "prior,current", [({}, observation()), (None, {}), ("corrupt", observation())]
)
def test_invalid_operands(prior, current):
    with pytest.raises(TypeError):
        evaluate_meaningful_change(prior, current)
