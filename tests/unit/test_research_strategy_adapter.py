from __future__ import annotations

import ast
import json
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime
from pathlib import Path

import pytest

import market_platform.strategy as strategy_package
from market_platform.research import (
    ResearchRequest,
    ResearchResult,
    ResearchStatus,
    ResearchStrategyAssessment,
    adapt_strategy_run_result,
)
from market_platform.strategy import (
    StrategyEvaluation,
    StrategyEvaluationStatus,
    StrategyEvidence,
    StrategyEvidenceSource,
    StrategyProvenance,
    StrategyRunResult,
)

_AS_OF = datetime(2026, 7, 17, tzinfo=UTC)
_FINGERPRINT = "sha256:observation"


def _evidence(field: str) -> StrategyEvidence:
    return StrategyEvidence(
        source=StrategyEvidenceSource.MARKET_STATE,
        field=field,
        observed_value="up",
        rationale=f"{field} supports the evaluation.",
        observed_at=_AS_OF,
    )


def _evaluation(
    strategy_id: str,
    *,
    status: StrategyEvaluationStatus = StrategyEvaluationStatus.APPLICABLE,
    rationale: str | None = None,
    evidence: tuple[StrategyEvidence, ...] = (),
) -> StrategyEvaluation:
    return StrategyEvaluation(
        symbol="MSFT",
        interval="1day",
        as_of=_AS_OF,
        provenance=StrategyProvenance(
            strategy_id=strategy_id,
            strategy_version="v1",
            parameters={},
            observation_fingerprint=_FINGERPRINT,
            state_model_id="baseline-market-state",
            state_model_version="v1",
        ),
        status=status,
        rationale=rationale or f"{strategy_id} assessment",
        evidence=evidence,
    )


def _run_result(
    evaluations: tuple[StrategyEvaluation, ...],
) -> StrategyRunResult:
    return StrategyRunResult(
        symbol="MSFT",
        interval="1day",
        as_of=_AS_OF,
        observation_fingerprint=_FINGERPRINT,
        state_model_id="baseline-market-state",
        state_model_version="v1",
        evaluations=evaluations,
    )


def test_strategy_run_result_is_projected_to_research_assessment() -> None:
    evaluation = _evaluation(
        "trend",
        status=StrategyEvaluationStatus.NOT_APPLICABLE,
        rationale="Trend conditions are absent.",
        evidence=(_evidence("trend_regime"), _evidence("momentum_regime")),
    )

    assessments = adapt_strategy_run_result(_run_result((evaluation,)))

    assert assessments == (
        ResearchStrategyAssessment(
            strategy_id="trend",
            strategy_version="v1",
            status="not_applicable",
            rationale="Trend conditions are absent.",
            evidence_count=2,
            as_of=_AS_OF,
        ),
    )
    assert assessments[0].as_of == evaluation.as_of
    json.dumps(assessments[0].to_dict())


def test_multiple_strategy_assessments_preserve_evaluation_order() -> None:
    result = _run_result(
        (
            _evaluation("trend"),
            _evaluation("breakout"),
            _evaluation("mean-reversion"),
        )
    )

    assessments = adapt_strategy_run_result(result)

    assert tuple(item.strategy_id for item in assessments) == (
        "trend",
        "breakout",
        "mean-reversion",
    )


def test_empty_strategy_run_result_returns_empty_tuple() -> None:
    assert adapt_strategy_run_result(_run_result(())) == ()


def test_adapter_does_not_modify_input() -> None:
    result = _run_result((_evaluation("trend"),))
    before = result.to_dict()

    adapt_strategy_run_result(result)

    assert result.to_dict() == before


def test_research_strategy_assessment_is_immutable() -> None:
    assessment = adapt_strategy_run_result(
        _run_result((_evaluation("trend"),))
    )[0]

    with pytest.raises(FrozenInstanceError):
        assessment.status = "replacement"  # type: ignore[misc]


def test_research_strategy_assessment_has_no_trading_semantics() -> None:
    field_names = {field.name for field in fields(ResearchStrategyAssessment)}
    forbidden = {
        "order",
        "position",
        "quantity",
        "target_price",
        "probability",
        "portfolio",
        "risk",
        "execution",
    }

    assert field_names.isdisjoint(forbidden)


def test_adapter_rejects_non_strategy_run_result() -> None:
    with pytest.raises(TypeError, match="StrategyRunResult"):
        adapt_strategy_run_result(object())  # type: ignore[arg-type]


def _imported_modules(package_dir: Path) -> set[str]:
    imported: set[str] = set()
    for source_path in package_dir.glob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported.add(node.module)
    return imported


def test_strategy_package_has_no_research_dependency() -> None:
    package_file = strategy_package.__file__
    assert isinstance(package_file, str)

    imported = _imported_modules(Path(package_file).parent)

    assert not any(
        module == "market_platform.research"
        or module.startswith("market_platform.research.")
        for module in imported
    )


def test_research_result_schema_remains_compatible() -> None:
    expected_fields = (
        "request",
        "status",
        "model_version",
        "market_view",
        "price_targets",
        "probabilities",
        "price_levels",
        "position_actions",
        "strategy_candidates",
        "warnings",
        "summary",
        "analysis",
    )
    result = ResearchResult(
        request=ResearchRequest(symbol="MSFT", horizon_days=20),
        status=ResearchStatus.OK,
        model_version="research-v1",
    )

    assert tuple(field.name for field in fields(ResearchResult)) == expected_fields
    assert tuple(result.to_dict()) == expected_fields
