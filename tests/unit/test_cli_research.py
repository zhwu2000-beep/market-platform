from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest

from market_platform.cli import main as cli_main
from market_platform.data.exceptions import DataProviderError
from market_platform.research import (
    MarketView,
    ResearchAnalysis,
    ResearchCompositeAssessment,
    ResearchRequest,
    ResearchResult,
    ResearchSignalComponent,
    ResearchStatus,
    ResearchWarning,
)

_FIXED_AS_OF = datetime(2026, 1, 2, 23, 59, 59, tzinfo=UTC)


@dataclass
class _FakeWorkflow:
    result: ResearchResult
    ran: bool = False
    received_request: ResearchRequest | None = None
    received_position: object | None = None

    async def run(
        self, request: ResearchRequest, position: object | None = None
    ) -> ResearchResult:
        self.ran = True
        self.received_request = request
        self.received_position = position
        return self.result


@dataclass
class _WorkflowFactory:
    workflow: _FakeWorkflow
    service_calls: list[object]
    workflow_calls: list[tuple[object, int, dict[str, float] | None, str]]

    def __call__(
        self,
        market_data_service: object,
        lookback_calendar_days: int = 120,
        composite_weights: Mapping[str, float] | None = None,
        model_version: str = "research-workflow-v1",
    ) -> _FakeWorkflow:
        self.service_calls.append(market_data_service)
        self.workflow_calls.append(
            (
                market_data_service,
                lookback_calendar_days,
                None if composite_weights is None else dict(composite_weights),
                model_version,
            )
        )
        return self.workflow


class _FailingWorkflow:
    async def run(
        self, request: ResearchRequest, position: object | None = None
    ) -> ResearchResult:
        raise DataProviderError("research workflow failed")


class _FailingWorkflowFactory:
    def __init__(self, workflow: object) -> None:
        self.workflow = workflow

    def __call__(
        self,
        market_data_service: object,
        lookback_calendar_days: int = 120,
        composite_weights: Mapping[str, float] | None = None,
        model_version: str = "research-workflow-v1",
    ) -> object:
        return self.workflow


def _research_result(
    *,
    request_as_of: datetime | None = _FIXED_AS_OF,
    analysis_timestamp: datetime = _FIXED_AS_OF,
) -> ResearchResult:
    request = ResearchRequest(
        symbol="msft",
        horizon_days=20,
        provider="polygon",
        as_of=request_as_of,
    )
    composite = ResearchCompositeAssessment(
        score=0.72,
        classification="strong_bullish",
        included_signals=("trend", "momentum"),
        missing_signals=(),
        configured_weights={"trend": 0.5, "momentum": 0.5},
        normalized_weights={"trend": 0.5, "momentum": 0.5},
        component_contributions={"trend": 0.36, "momentum": 0.36},
        methodology="baseline_uncalibrated_composite_v1",
    )
    analysis = ResearchAnalysis(
        symbol="msft",
        timestamp=analysis_timestamp,
        components=(
            ResearchSignalComponent(
                name="trend",
                raw_value=0.05,
                score=0.5,
                state="positive",
                role="directional",
                methodology="baseline_uncalibrated_directional_rescaling_v1",
                parameters={
                    "scale": 0.1,
                    "formula": "clamp(raw_value / scale, -1.0, 1.0)",
                    "source_parameters": {"source": "cli"},
                },
            ),
            ResearchSignalComponent(
                name="momentum",
                raw_value=0.10,
                score=0.5,
                state="positive",
                role="directional",
                methodology="baseline_uncalibrated_directional_rescaling_v1",
                parameters={
                    "scale": 0.2,
                    "formula": "clamp(raw_value / scale, -1.0, 1.0)",
                    "source_parameters": {"source": "cli"},
                },
            ),
            ResearchSignalComponent(
                name="realized_volatility",
                raw_value=0.35,
                score=None,
                state="high",
                role="volatility",
                methodology="baseline_uncalibrated_volatility_v1",
                parameters={"low_threshold": 0.15, "high_threshold": 0.30},
            ),
        ),
        volatility_state="high",
        volatility_value=0.35,
        composite=composite,
    )
    return ResearchResult(
        request=request,
        status=ResearchStatus.DEGRADED,
        market_view=MarketView(
            direction="bullish",
            strength="strong",
            trend_state="positive",
            momentum_state="positive",
            volatility_state="high",
            price_structure=None,
            confidence=None,
        ),
        warnings=(
            ResearchWarning(
                code="missing_directional_signals",
                message="Missing directional signals: current_drawdown",
            ),
        ),
        summary=(
            "MSFT's current composite signal is classified as bullish; the requested "
            "research horizon is 20 days."
        ),
        model_version="research-workflow-v1",
        analysis=analysis,
    )


def _configure_research_cli(
    monkeypatch: pytest.MonkeyPatch,
    workflow: _FakeWorkflow,
    service: object,
) -> _WorkflowFactory:
    factory = _WorkflowFactory(workflow=workflow, service_calls=[], workflow_calls=[])
    monkeypatch.setattr(cli_main, "create_default_market_data_service", lambda: service)
    monkeypatch.setattr(cli_main, "DefaultResearchWorkflow", factory)
    return factory


def _run_research_cli(
    argv: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    workflow: _FakeWorkflow | object | None = None,
    service: object | None = None,
) -> tuple[int, str, str, _FakeWorkflow | object, _WorkflowFactory | None]:
    service_object = {} if service is None else service
    workflow_object = _research_result() if workflow is None else workflow
    if not isinstance(workflow_object, _FakeWorkflow):
        factory = _FailingWorkflowFactory(workflow_object)
        monkeypatch.setattr(
            cli_main, "create_default_market_data_service", lambda: service_object
        )
        monkeypatch.setattr(cli_main, "DefaultResearchWorkflow", factory)
        exit_code = cli_main.run(["research", "run", *argv])
        captured = capsys.readouterr()
        return exit_code, captured.out, captured.err, workflow_object, None
    factory = _configure_research_cli(monkeypatch, workflow_object, service_object)
    exit_code = cli_main.run(["research", "run", *argv])
    captured = capsys.readouterr()
    return exit_code, captured.out, captured.err, workflow_object, factory


def test_research_run_command_is_registered() -> None:
    parser = cli_main.build_parser()

    args = parser.parse_args(["research", "run", "--symbol", "msft"])

    assert args.command == "research"
    assert args.research_command == "run"
    assert args.symbol == "msft"
    assert args.horizon_days == 20
    assert args.lookback_days == 120
    assert args.format == "table"
    assert callable(args.handler)


def test_research_run_requires_symbol(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli_main.run(["research", "run"])

    captured = capsys.readouterr()

    assert excinfo.value.code == 2
    assert "the following arguments are required: --symbol" in captured.err
    assert "Traceback" not in captured.err


def test_research_run_parser_defaults() -> None:
    parser = cli_main.build_parser()

    args = parser.parse_args(["research", "run", "--symbol", "msft"])

    assert args.horizon_days == 20
    assert args.lookback_days == 120
    assert args.format == "table"


def test_research_run_explicit_provider_and_as_of_conversion(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workflow = _FakeWorkflow(result=_research_result())

    exit_code, stdout, stderr, _, factory = _run_research_cli(
        [
            "--symbol",
            "msft",
            "--provider",
            "polygon",
            "--as-of",
            "2026-01-02",
            "--lookback-days",
            "42",
        ],
        monkeypatch,
        capsys,
        workflow=workflow,
    )

    assert exit_code == 0
    assert factory is not None
    assert factory.workflow_calls == [
        (factory.service_calls[0], 42, None, "research-workflow-v1")
    ]
    assert workflow.ran is True
    assert workflow.received_request is not None
    assert workflow.received_request.provider == "polygon"
    assert workflow.received_request.as_of == _FIXED_AS_OF
    assert stdout
    assert stderr == ""


def test_research_run_default_request_context_leaves_as_of_unset(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workflow = _FakeWorkflow(result=_research_result())

    exit_code, stdout, stderr, _, factory = _run_research_cli(
        ["--symbol", "msft"],
        monkeypatch,
        capsys,
        workflow=workflow,
    )

    assert exit_code == 0
    assert factory is not None
    assert workflow.received_request is not None
    assert workflow.received_request.as_of is None
    assert factory.workflow_calls == [
        (factory.service_calls[0], 120, None, "research-workflow-v1")
    ]
    assert stdout
    assert stderr == ""


def test_research_run_table_output_fields_and_no_fabricated_claims(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workflow = _FakeWorkflow(result=_research_result())

    exit_code, stdout, stderr, _, _ = _run_research_cli(
        ["--symbol", "msft"],
        monkeypatch,
        capsys,
        workflow=workflow,
    )

    assert exit_code == 0
    for label in [
        "Symbol",
        "Status",
        "Requested Horizon",
        "As Of",
        "Direction",
        "Strength",
        "Trend State",
        "Momentum State",
        "Volatility State",
        "Composite Score",
        "Classification",
        "Summary",
        "Warnings",
    ]:
        assert label in stdout
    assert "price target" not in stdout.lower()
    assert "probability" not in stdout.lower()
    assert "strategy" not in stdout.lower()
    assert stderr == ""


def test_research_run_table_as_of_uses_explicit_request_value(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    explicit_as_of = datetime(2026, 1, 3, 23, 59, 59, tzinfo=UTC)
    analysis_timestamp = datetime(2026, 1, 4, 23, 59, 59, tzinfo=UTC)
    workflow = _FakeWorkflow(
        result=_research_result(
            request_as_of=explicit_as_of,
            analysis_timestamp=analysis_timestamp,
        ),
    )

    exit_code, stdout, stderr, _, _ = _run_research_cli(
        ["--symbol", "msft"],
        monkeypatch,
        capsys,
        workflow=workflow,
    )

    assert exit_code == 0
    assert explicit_as_of.isoformat() in stdout
    assert analysis_timestamp.isoformat() not in stdout
    assert stderr == ""


def test_research_run_table_as_of_falls_back_to_analysis_timestamp(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    analysis_timestamp = datetime(2026, 1, 4, 23, 59, 59, tzinfo=UTC)
    workflow = _FakeWorkflow(
        result=_research_result(
            request_as_of=None,
            analysis_timestamp=analysis_timestamp,
        ),
    )

    exit_code, stdout, stderr, _, _ = _run_research_cli(
        ["--symbol", "msft"],
        monkeypatch,
        capsys,
        workflow=workflow,
    )

    assert exit_code == 0
    assert analysis_timestamp.isoformat() in stdout
    assert _FIXED_AS_OF.isoformat() not in stdout
    assert stderr == ""


def test_research_run_table_as_of_renders_placeholder_when_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workflow = _FakeWorkflow(
        result=ResearchResult(
            request=ResearchRequest(
                symbol="msft",
                horizon_days=20,
                provider="polygon",
                as_of=None,
            ),
            status=ResearchStatus.DEGRADED,
            market_view=None,
            warnings=(),
            summary=None,
            model_version="research-workflow-v1",
            analysis=None,
        ),
    )

    exit_code, stdout, stderr, _, _ = _run_research_cli(
        ["--symbol", "msft"],
        monkeypatch,
        capsys,
        workflow=workflow,
    )

    assert exit_code == 0
    assert " - " in stdout or stdout.rstrip().endswith("-")
    assert stderr == ""


def test_research_run_json_output_is_valid_and_nested(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workflow = _FakeWorkflow(result=_research_result())

    exit_code, stdout, stderr, _, _ = _run_research_cli(
        ["--symbol", "msft", "--format", "json"],
        monkeypatch,
        capsys,
        workflow=workflow,
    )

    payload = json.loads(stdout)

    assert exit_code == 0
    assert payload["request"]["symbol"] == "MSFT"
    assert payload["analysis"]["composite"]["score"] == 0.72
    assert payload["analysis"]["components"][0]["name"] == "trend"
    assert payload["warnings"][0]["code"] == "missing_directional_signals"
    assert stderr == ""


def test_research_run_json_preserves_null_request_as_of_when_unset(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workflow = _FakeWorkflow(result=_research_result(request_as_of=None))

    exit_code, stdout, stderr, _, _ = _run_research_cli(
        ["--symbol", "msft", "--format", "json"],
        monkeypatch,
        capsys,
        workflow=workflow,
    )

    payload = json.loads(stdout)

    assert exit_code == 0
    assert payload["request"]["as_of"] is None
    assert stderr == ""


def test_research_run_json_stdout_is_clean(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workflow = _FakeWorkflow(result=_research_result())

    exit_code, stdout, stderr, _, _ = _run_research_cli(
        ["--symbol", "msft", "--format", "json"],
        monkeypatch,
        capsys,
        workflow=workflow,
    )

    assert exit_code == 0
    assert stdout.lstrip().startswith("{")
    assert stderr == ""


@pytest.mark.parametrize("output_format", ["table", "json"])
def test_research_run_output_writes_file_and_creates_parent_directories(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    output_format: str,
) -> None:
    workflow = _FakeWorkflow(result=_research_result())
    output_path = tmp_path / "nested" / "reports" / f"research.{output_format}"

    exit_code, stdout, stderr, _, _ = _run_research_cli(
        [
            "--symbol",
            "msft",
            "--format",
            output_format,
            "--output",
            str(output_path),
        ],
        monkeypatch,
        capsys,
        workflow=workflow,
    )

    assert exit_code == 0
    assert output_path.exists()
    assert output_path.parent.exists()
    assert stdout == ""
    assert stderr == ""
    if output_format == "json":
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        assert payload["analysis"]["composite"]["classification"] == "strong_bullish"
    else:
        assert "Symbol" in output_path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("flag", "value", "expected"),
    [
        (
            "--as-of",
            "2026-13-01",
            "invalid date '2026-13-01'; expected format YYYY-MM-DD",
        ),
        (
            "--horizon-days",
            "0",
            "invalid integer value '0'; expected a positive integer",
        ),
        (
            "--horizon-days",
            "-1",
            "invalid integer value '-1'; expected a positive integer",
        ),
        (
            "--lookback-days",
            "0",
            "invalid integer value '0'; expected a positive integer",
        ),
        (
            "--lookback-days",
            "-1",
            "invalid integer value '-1'; expected a positive integer",
        ),
    ],
)
def test_research_run_invalid_inputs_fail_cleanly(
    flag: str,
    value: str,
    expected: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    argv = ["research", "run", "--symbol", "msft", flag, value]
    with pytest.raises(SystemExit) as excinfo:
        cli_main.run(argv)

    captured = capsys.readouterr()

    assert excinfo.value.code == 2
    assert expected in captured.err
    assert "Traceback" not in captured.err


def test_research_run_provider_and_workflow_exceptions_follow_existing_cli_policy(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workflow = _FailingWorkflow()
    exit_code, stdout, stderr, _, _ = _run_research_cli(
        ["--symbol", "msft"],
        monkeypatch,
        capsys,
        workflow=workflow,
    )

    assert exit_code == 1
    assert stdout == ""
    assert "research workflow failed" in stderr
    assert "Traceback" not in stderr


def test_research_package_exports_are_available() -> None:
    from market_platform.research import (  # noqa: PLC0415
        DefaultResearchWorkflow,
        ResearchRequest,
        ResearchResult,
    )

    assert DefaultResearchWorkflow is not None
    assert ResearchRequest is not None
    assert ResearchResult is not None
