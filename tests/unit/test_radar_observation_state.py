"""Coordinated state remains passive and strictly bounded."""

import json
from dataclasses import FrozenInstanceError, fields, replace
from datetime import UTC, date, datetime

import pytest

from market_platform.instruments.identity import CanonicalInstrumentId
from market_platform.radar.core import (
    RadarGateIdentity,
    RadarGateOccurrence,
    RadarPipelineOutcome,
    RadarProfile,
)
from market_platform.radar.lightweight_observation import (
    EMA8_EMA20_CALCULATION_REVISION,
    EMA8_EMA20_OBSERVATION_DEFINITION_ID,
    EMA8_EMA20_OBSERVATION_SCHEMA,
    RadarEmaRelation,
    RadarLightweightObservation,
)
from market_platform.radar.meaningful_change import evaluate_meaningful_change
from market_platform.radar.observation import (
    RadarMarketContentScope,
    RadarObservationCheckpoint,
    RadarObservationStateError,
)
from market_platform.radar.observation_state import (
    RADAR_OBSERVATION_STATE_SCHEMA,
    RadarObservationState,
    RadarObservationStateLookupResult,
)
from market_platform.radar.observation_state import (
    RadarObservationStateLookupStatus as Status,
)


def state():
    market = RadarObservationCheckpoint(
        CanonicalInstrumentId("us-msft"),
        date(2026, 9, 23),
        "sha256:" + "a" * 64,
        datetime(2026, 9, 24, tzinfo=UTC),
        RadarMarketContentScope(date(2025, 10, 1), date(2026, 9, 23)),
    )
    light = RadarLightweightObservation(
        market.instrument,
        EMA8_EMA20_OBSERVATION_DEFINITION_ID,
        EMA8_EMA20_CALCULATION_REVISION,
        EMA8_EMA20_OBSERVATION_SCHEMA,
        market.observed_completed_session,
        market.normalized_market_content_identity,
        market.content_scope,
        RadarEmaRelation.ABOVE,
        market.observed_at,
    )
    profile = RadarProfile(
        "test",
        "1",
        "test/v1",
        (RadarGateOccurrence("test", RadarGateIdentity("test", "1", "test/v1")),),
    )
    return RadarObservationState(
        market,
        light,
        evaluate_meaningful_change(None, light),
        profile.fingerprint,
        RadarPipelineOutcome.SELECTED,
    )


def test_schema_frozen_slots_and_bounded_fields():
    value = state()
    assert (
        value.schema_version
        == RADAR_OBSERVATION_STATE_SCHEMA
        == "radar_observation_state/v1"
    )
    assert not hasattr(value, "__dict__")
    with pytest.raises(FrozenInstanceError):
        value.profile_fingerprint = "changed"
    assert {f.name for f in fields(value)} == {
        "schema_version",
        "market_observation",
        "lightweight_observation",
        "committed_decision",
        "profile_fingerprint",
        "pipeline_outcome",
    }
    assert "profile_fingerprint" not in value.lightweight_observation.to_dict()


@pytest.mark.parametrize("field", [f.name for f in fields(RadarObservationState)])
@pytest.mark.parametrize("bad", [None, {}, 1, True])
def test_exact_runtime_types(field, bad):
    with pytest.raises(RadarObservationStateError):
        replace(state(), **{field: bad})


@pytest.mark.parametrize(
    "field", ["market_observation", "lightweight_observation", "committed_decision"]
)
def test_subclasses_rejected(field):
    value = state()
    original = getattr(value, field)
    child = type("Child", (type(original),), {})
    derived = child(**{f.name: getattr(original, f.name) for f in fields(original)})
    with pytest.raises(RadarObservationStateError):
        replace(value, **{field: derived})


@pytest.mark.parametrize(
    "mismatch", ["instrument", "session", "identity", "scope", "decision"]
)
def test_correspondence(mismatch):
    value = state()
    market = value.market_observation
    if mismatch == "instrument":
        market = replace(market, instrument=CanonicalInstrumentId("other"))
    elif mismatch == "session":
        end = date(2026, 9, 24)
        market = replace(
            market,
            observed_completed_session=end,
            content_scope=replace(market.content_scope, history_end=end),
        )
    elif mismatch == "identity":
        market = replace(
            market, normalized_market_content_identity="sha256:" + "b" * 64
        )
    elif mismatch == "scope":
        market = replace(
            market,
            content_scope=replace(
                market.content_scope, history_start=date(2025, 10, 2)
            ),
        )
    else:
        other = replace(value.lightweight_observation, relation=RadarEmaRelation.BELOW)
        with pytest.raises(RadarObservationStateError, match="current"):
            replace(value, committed_decision=evaluate_meaningful_change(None, other))
        return
    with pytest.raises(RadarObservationStateError, match="mismatch"):
        replace(value, market_observation=market)


@pytest.mark.parametrize(
    "fingerprint",
    [
        "",
        "a" * 64,
        "sha256:" + "A" * 64,
        "sha256:" + "a" * 63,
        "sha256:" + "a" * 64 + "\n",
    ],
)
def test_profile_fingerprint_format(fingerprint):
    with pytest.raises(RadarObservationStateError):
        replace(state(), profile_fingerprint=fingerprint)


@pytest.mark.parametrize("outcome", list(RadarPipelineOutcome))
def test_accepted_outcomes(outcome):
    if outcome in {RadarPipelineOutcome.SELECTED, RadarPipelineOutcome.FILTERED}:
        assert replace(state(), pipeline_outcome=outcome).pipeline_outcome is outcome
    else:
        with pytest.raises(RadarObservationStateError):
            replace(state(), pipeline_outcome=outcome)
    with pytest.raises(RadarObservationStateError):
        replace(state(), pipeline_outcome=outcome.value)


@pytest.mark.parametrize(
    "kind", ["baseline", "unchanged", "transition", "incompatible", "new_session"]
)
def test_deterministic_detached_roundtrip(kind):
    value = state()
    current = value.lightweight_observation
    prior = None
    if kind != "baseline":
        prior = current
    if kind == "transition":
        prior = replace(
            current,
            relation=RadarEmaRelation.BELOW,
            normalized_market_content_identity="sha256:" + "b" * 64,
        )
    if kind == "incompatible":
        prior = replace(current, calculation_revision="2")
    if kind == "new_session":
        end = date(2026, 9, 22)
        prior = replace(
            current,
            completed_session=end,
            relation=RadarEmaRelation.EQUAL,
            content_scope=replace(current.content_scope, history_end=end),
        )
    value = replace(
        value, committed_decision=evaluate_meaningful_change(prior, current)
    )
    raw = value.to_dict()
    serialized = json.dumps(raw)
    assert json.dumps(value.to_dict()) == serialized
    assert RadarObservationState.from_dict(json.loads(serialized)) == value
    raw["committed_decision"]["current"]["relation"] = "BAD"
    assert json.dumps(value.to_dict()) == serialized


@pytest.mark.parametrize("field", [f.name for f in fields(RadarObservationState)])
def test_missing_fields(field):
    raw = state().to_dict()
    del raw[field]
    with pytest.raises(RadarObservationStateError):
        RadarObservationState.from_dict(raw)


@pytest.mark.parametrize("raw", [None, [], "state", {}, 1])
def test_malformed_top_level(raw):
    with pytest.raises(RadarObservationStateError):
        RadarObservationState.from_dict(raw)


@pytest.mark.parametrize(
    "path,bad",
    [
        (("extra",), "forbidden"),
        (("schema_version",), "future"),
        (("pipeline_outcome",), "UNKNOWN"),
        (("pipeline_outcome",), "ATTENTION"),
        (("pipeline_outcome",), "FAILED"),
        (("pipeline_outcome",), RadarPipelineOutcome.SELECTED),
        (("market_observation", "observed_at"), "bad"),
        (("market_observation", "content_scope", "schema_version"), "future"),
        (("lightweight_observation", "relation"), "bad"),
        (("lightweight_observation", "extra"), 1),
        (("committed_decision", "reason"), "STATE_UNCHANGED"),
        (("committed_decision", "classification"), "STATE_TRANSITION"),
        (("committed_decision", "comparison_kind"), "bad"),
        (("committed_decision", "meaningful_change"), True),
        (("committed_decision", "meaningful_change"), 0),
        (("committed_decision", "incompatibilities"), ()),
        (("committed_decision", "incompatibilities"), ["bad"]),
        (("committed_decision", "policy", "behavioral_revision"), "2"),
        (("committed_decision", "policy", "extra"), 1),
        (("committed_decision", "prior"), {}),
        (("committed_decision", "current", "relation"), "BELOW"),
        (("committed_decision", "extra"), 1),
    ],
)
def test_corrupt_nested_data(path, bad):
    raw = state().to_dict()
    node = raw
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = bad
    with pytest.raises(RadarObservationStateError):
        RadarObservationState.from_dict(raw)


def test_constructor_revalidates_decision_contract():
    value = state()
    object.__setattr__(value.committed_decision, "reason", "corrupt")
    with pytest.raises(RadarObservationStateError):
        replace(value)


@pytest.mark.parametrize("status", list(Status))
def test_lookup_payload_contract(status):
    value = state()
    if status is Status.LEGACY_CONTENT_ONLY:
        result = RadarObservationStateLookupResult(
            status, legacy_checkpoint=value.market_observation
        )
        assert result.state is None
    elif status is Status.PRESENT_COMPLETE_STATE:
        result = RadarObservationStateLookupResult(status, state=value)
        assert result.legacy_checkpoint is None
    else:
        result = RadarObservationStateLookupResult(status)
        assert result.checkpoint is None
    if status in {Status.LEGACY_CONTENT_ONLY, Status.PRESENT_COMPLETE_STATE}:
        assert result.checkpoint is value.market_observation
        with pytest.raises(RadarObservationStateError):
            RadarObservationStateLookupResult(status)
    with pytest.raises(RadarObservationStateError):
        RadarObservationStateLookupResult(status, value.market_observation, value)
    with pytest.raises(RadarObservationStateError):
        RadarObservationStateLookupResult(status.value)
