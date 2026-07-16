from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime, timedelta, timezone

import pytest

from market_platform.strategy import (
    StrategyEvaluation,
    StrategyEvaluationStatus,
    StrategyEvidence,
    StrategyEvidenceSource,
    StrategyProvenance,
)

_AS_OF = datetime(2026, 7, 17, tzinfo=UTC)


def _provenance(**overrides: object) -> StrategyProvenance:
    values: dict[str, object] = {
        "strategy_id": "test-strategy",
        "strategy_version": "v1",
        "parameters": {"thresholds": {"minimum": 0.25}, "inputs": ["trend"]},
        "observation_fingerprint": "sha256:observation",
        "state_model_id": "baseline-market-state",
        "state_model_version": "v1",
    }
    values.update(overrides)
    return StrategyProvenance(**values)  # type: ignore[arg-type]


def _evidence(**overrides: object) -> StrategyEvidence:
    values: dict[str, object] = {
        "source": StrategyEvidenceSource.MARKET_STATE,
        "field": "directional_regime",
        "observed_value": "up",
        "rationale": "The strategy requires an upward directional regime.",
        "observed_at": _AS_OF,
    }
    values.update(overrides)
    return StrategyEvidence(**values)  # type: ignore[arg-type]


def _evaluation(**overrides: object) -> StrategyEvaluation:
    values: dict[str, object] = {
        "symbol": "MSFT",
        "interval": "1day",
        "as_of": _AS_OF,
        "provenance": _provenance(),
        "status": StrategyEvaluationStatus.APPLICABLE,
        "rationale": "All required inputs are present and the rules apply.",
        "required_inputs": ("directional_regime",),
        "missing_inputs": (),
        "evidence": (_evidence(),),
    }
    values.update(overrides)
    return StrategyEvaluation(**values)  # type: ignore[arg-type]


def test_strategy_models_are_frozen_and_use_slots() -> None:
    evidence = _evidence()
    provenance = _provenance()
    evaluation = _evaluation(provenance=provenance, evidence=(evidence,))

    for model in (evidence, provenance, evaluation):
        assert not hasattr(model, "__dict__")
    with pytest.raises(FrozenInstanceError):
        evidence.field = "replacement"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        provenance.strategy_id = "replacement"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        evaluation.symbol = "AAPL"  # type: ignore[misc]


def test_strategy_provenance_defensively_freezes_nested_parameters() -> None:
    threshold: dict[str, object] = {"minimum": 0.25}
    inputs = ["trend"]
    parameters: dict[str, object] = {
        "thresholds": threshold,
        "inputs": inputs,
    }

    provenance = _provenance(parameters=parameters)
    threshold["minimum"] = 0.75
    inputs.append("momentum")
    parameters["new"] = True

    assert provenance.to_dict()["parameters"] == {
        "thresholds": {"minimum": 0.25},
        "inputs": ["trend"],
    }
    with pytest.raises(TypeError):
        provenance.parameters["new"] = True  # type: ignore[index]
    frozen_thresholds = provenance.parameters["thresholds"]
    assert isinstance(frozen_thresholds, Mapping)
    with pytest.raises(TypeError):
        frozen_thresholds["minimum"] = 0.75  # type: ignore[index]


def test_strategy_enums_use_expected_string_values_only() -> None:
    assert {status.value for status in StrategyEvaluationStatus} == {
        "applicable",
        "not_applicable",
        "insufficient_data",
    }
    assert {source.value for source in StrategyEvidenceSource} == {
        "market_state",
        "market_observation",
    }


def test_aware_datetimes_are_normalized_to_utc() -> None:
    local_time = datetime(
        2026,
        7,
        17,
        8,
        tzinfo=timezone(timedelta(hours=8)),
    )
    evidence = _evidence(observed_value=local_time, observed_at=local_time)
    evaluation = _evaluation(as_of=local_time, evidence=(evidence,))

    assert evidence.observed_value == datetime(2026, 7, 17, tzinfo=UTC)
    assert evidence.observed_at == datetime(2026, 7, 17, tzinfo=UTC)
    assert evaluation.as_of == datetime(2026, 7, 17, tzinfo=UTC)


@pytest.mark.parametrize(
    "factory",
    [
        lambda: _evidence(observed_value=datetime(2026, 7, 17)),
        lambda: _evidence(observed_at=datetime(2026, 7, 17)),
        lambda: _evaluation(as_of=datetime(2026, 7, 17)),
    ],
)
def test_naive_datetimes_are_rejected(factory: object) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        factory()  # type: ignore[operator]


@pytest.mark.parametrize("value", [math.inf, -math.inf, math.nan])
def test_non_finite_float_evidence_is_rejected(value: float) -> None:
    with pytest.raises(ValueError, match="must be finite"):
        _evidence(observed_value=value)


def test_bool_and_int_evidence_values_keep_their_exact_types() -> None:
    bool_evidence = _evidence(observed_value=True)
    int_evidence = _evidence(observed_value=1)

    assert type(bool_evidence.observed_value) is bool
    assert type(int_evidence.observed_value) is int


@pytest.mark.parametrize(
    "status",
    [
        StrategyEvaluationStatus.APPLICABLE,
        StrategyEvaluationStatus.NOT_APPLICABLE,
    ],
)
def test_complete_evaluation_statuses_reject_missing_inputs(
    status: StrategyEvaluationStatus,
) -> None:
    with pytest.raises(ValueError, match="must not have missing_inputs"):
        _evaluation(
            status=status,
            required_inputs=("trend_regime",),
            missing_inputs=("trend_regime",),
        )


def test_insufficient_data_requires_missing_inputs() -> None:
    with pytest.raises(ValueError, match="must have missing_inputs"):
        _evaluation(
            status=StrategyEvaluationStatus.INSUFFICIENT_DATA,
            required_inputs=("trend_regime",),
            missing_inputs=(),
        )


def test_insufficient_data_accepts_declared_missing_inputs() -> None:
    evaluation = _evaluation(
        status=StrategyEvaluationStatus.INSUFFICIENT_DATA,
        rationale="The trend regime is unavailable.",
        required_inputs=["trend_regime"],
        missing_inputs=["trend_regime"],
        evidence=[],
    )

    assert evaluation.required_inputs == ("trend_regime",)
    assert evaluation.missing_inputs == ("trend_regime",)
    assert evaluation.evidence == ()


def test_missing_inputs_must_be_subset_of_required_inputs() -> None:
    with pytest.raises(ValueError, match="subset"):
        _evaluation(
            status=StrategyEvaluationStatus.INSUFFICIENT_DATA,
            required_inputs=("trend_regime",),
            missing_inputs=("momentum_regime",),
        )


def test_future_evidence_is_rejected() -> None:
    evidence = _evidence(observed_at=_AS_OF + timedelta(seconds=1))

    with pytest.raises(ValueError, match="not be later than as_of"):
        _evaluation(evidence=(evidence,))


def test_strategy_evaluation_to_dict_is_json_compatible() -> None:
    payload = _evaluation().to_dict()

    assert payload["status"] == "applicable"
    assert payload["evidence"] == [
        {
            "source": "market_state",
            "field": "directional_regime",
            "observed_value": "up",
            "rationale": "The strategy requires an upward directional regime.",
            "observed_at": _AS_OF.isoformat(),
        }
    ]
    json.dumps(payload)


def test_datetime_evidence_value_serializes_as_utc_text() -> None:
    local_time = datetime(
        2026,
        7,
        17,
        8,
        tzinfo=timezone(timedelta(hours=8)),
    )

    payload = _evidence(observed_value=local_time).to_dict()

    assert payload["observed_value"] == datetime(
        2026,
        7,
        17,
        tzinfo=UTC,
    ).isoformat()
    json.dumps(payload)


def test_strategy_domain_fields_have_no_execution_or_prediction_semantics() -> None:
    field_names = {
        field.name
        for model_type in (StrategyEvidence, StrategyProvenance, StrategyEvaluation)
        for field in fields(model_type)
    }
    forbidden = {
        "action",
        "order",
        "side",
        "quantity",
        "allocation",
        "position_size",
        "target_price",
        "probability",
        "broker",
        "execution",
    }

    assert field_names.isdisjoint(forbidden)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("strategy_id", " "),
        ("strategy_version", " "),
        ("state_model_id", " "),
        ("state_model_version", " "),
    ],
)
def test_strategy_provenance_rejects_empty_identity_fields(
    field_name: str,
    value: str,
) -> None:
    with pytest.raises(ValueError, match=f"{field_name} must not be empty"):
        _provenance(**{field_name: value})


def test_strategy_evidence_rejects_untyped_container_value() -> None:
    with pytest.raises(TypeError, match="observed_value"):
        _evidence(observed_value={"direction": "up"})


def test_strategy_parameters_reject_unordered_set_values() -> None:
    with pytest.raises(TypeError, match="JSON-compatible"):
        _provenance(parameters={"inputs": {"trend", "momentum"}})


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: _evidence(field=" "), "field must not be empty"),
        (lambda: _evidence(rationale=" "), "rationale must not be empty"),
        (lambda: _evaluation(symbol=" "), "symbol must not be empty"),
        (lambda: _evaluation(interval=" "), "interval must not be empty"),
        (lambda: _evaluation(rationale=" "), "rationale must not be empty"),
    ],
)
def test_strategy_models_reject_empty_required_text(
    factory: object,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        factory()  # type: ignore[operator]


@pytest.mark.parametrize(
    ("field_name", "values"),
    [
        ("required_inputs", ("trend_regime", "trend_regime")),
        ("missing_inputs", ("trend_regime", "trend_regime")),
    ],
)
def test_strategy_evaluation_rejects_duplicate_input_names(
    field_name: str,
    values: tuple[str, ...],
) -> None:
    overrides: dict[str, object] = {
        "status": StrategyEvaluationStatus.INSUFFICIENT_DATA,
        "required_inputs": ("trend_regime",),
        "missing_inputs": ("trend_regime",),
        field_name: values,
    }

    with pytest.raises(ValueError, match="must not contain duplicates"):
        _evaluation(**overrides)
