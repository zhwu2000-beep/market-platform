from __future__ import annotations

import ast
import json
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from market_platform.cli import main as cli_main
from market_platform.data.exceptions import DataProviderError
from market_platform.replay import HistoricalReplaySummary


@dataclass
class _FakeDailyService:
    frame: pd.DataFrame
    calls: list[tuple[str, date, date, str | None]]

    async def get_daily_prices(
        self,
        symbol: str,
        start: date,
        end: date,
        provider: str | None = None,
    ) -> pd.DataFrame:
        self.calls.append((symbol, start, end, provider))
        return self.frame


class _FailingDailyService:
    async def get_daily_prices(
        self,
        symbol: str,
        start: date,
        end: date,
        provider: str | None = None,
    ) -> pd.DataFrame:
        raise DataProviderError("provider unavailable")


class _ExplodingReplayService:
    def __init__(self) -> None:
        raise AssertionError("replay should not be constructed")


class _ContractFailingReplayService:
    def run(self, *args: object, **kwargs: object) -> object:
        raise ValueError("replay contract violation")


def _prices(count: int = 5) -> pd.DataFrame:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    rows = []
    for index in range(count):
        timestamp = start + timedelta(days=index)
        close = 100.0 + index
        rows.append(
            {
                "symbol": "MSFT",
                "timestamp": pd.Timestamp(timestamp),
                "open": close,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 1_000_000.0,
                "provider": "polygon",
            }
        )
    return pd.DataFrame(rows)


def _exclusive_service_frame(start: date, end: date) -> pd.DataFrame:
    rows = []
    current = start
    while current < end:
        offset = (current - start).days
        close = 100.0 + offset
        rows.append(
            {
                "symbol": "MSFT",
                "timestamp": pd.Timestamp(
                    datetime(current.year, current.month, current.day, tzinfo=UTC)
                ),
                "open": close,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 1_000_000.0,
                "provider": "polygon",
            }
        )
        current = current + timedelta(days=1)
    return pd.DataFrame(rows)


def _install_service(
    monkeypatch: pytest.MonkeyPatch,
    service: object,
) -> None:
    monkeypatch.setattr(
        cli_main,
        "create_default_market_data_service",
        lambda: service,
    )


def test_parser_registers_replay_run() -> None:
    parser = cli_main.build_parser()

    args = parser.parse_args(
        [
            "replay",
            "run",
            "--symbol",
            "MSFT",
            "--start",
            "2026-01-01",
            "--end",
            "2026-01-02",
        ]
    )

    assert args.command == "replay"
    assert args.replay_command == "run"
    assert args.view == "summary"
    assert args.format == "table"


def test_replay_run_requires_arguments(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli_main.run(["replay", "run"])

    captured = capsys.readouterr()

    assert excinfo.value.code == 2
    assert "required" in captured.err


@pytest.mark.parametrize(
    "argv",
    [
        [
            "replay",
            "run",
            "--symbol",
            "MSFT",
            "--start",
            "bad-date",
            "--end",
            "2026-01-02",
        ],
        [
            "replay",
            "run",
            "--symbol",
            "MSFT",
            "--start",
            "2026-01-01",
            "--end",
            "2026-01-02",
            "--max-bars",
            "0",
        ],
    ],
)
def test_replay_invalid_arguments_exit_2(
    argv: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli_main.run(argv)

    captured = capsys.readouterr()

    assert excinfo.value.code == 2
    assert "Traceback" not in captured.err


def test_replay_start_after_end_exits_2(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    created = False

    def _create_service() -> _FakeDailyService:
        nonlocal created
        created = True
        return _FakeDailyService(_prices(), [])

    monkeypatch.setattr(cli_main, "create_default_market_data_service", _create_service)

    exit_code = cli_main.run(
        [
            "replay",
            "run",
            "--symbol",
            "MSFT",
            "--start",
            "2026-01-03",
            "--end",
            "2026-01-02",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 2
    assert not created
    assert "start date" in captured.err


def test_replay_rejects_unsupported_view_format_combo(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = _FakeDailyService(_prices(), [])
    _install_service(monkeypatch, service)

    exit_code = cli_main.run(
        [
            "replay",
            "run",
            "--symbol",
            "MSFT",
            "--start",
            "2026-01-01",
            "--end",
            "2026-01-02",
            "--view",
            "steps",
            "--format",
            "table",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 2
    assert service.calls == []
    assert "steps view only supports --format json" in captured.err


def test_replay_forwards_symbol_provider_and_inclusive_fetch_boundary(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = _FakeDailyService(_prices(), [])
    _install_service(monkeypatch, service)

    exit_code = cli_main.run(
        [
            "replay",
            "run",
            "--symbol",
            "msft",
            "--start",
            "2026-01-01",
            "--end",
            "2026-01-03",
            "--provider",
            "polygon",
            "--format",
            "json",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert service.calls == [
        ("MSFT", date(2026, 1, 1), date(2026, 1, 4), "polygon")
    ]
    assert json.loads(captured.out)["step_count"] == 3


def test_replay_includes_user_end_date_when_provider_end_is_exclusive(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    start = date(2026, 1, 1)
    user_end = date(2026, 1, 3)
    service = _FakeDailyService(
        _exclusive_service_frame(start, user_end + timedelta(days=1)), []
    )
    _install_service(monkeypatch, service)

    exit_code = cli_main.run(
        [
            "replay",
            "run",
            "--symbol",
            "MSFT",
            "--start",
            start.isoformat(),
            "--end",
            user_end.isoformat(),
            "--format",
            "json",
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["end_as_of"].startswith("2026-01-03")
    assert payload["step_count"] == 3


def test_replay_summary_table_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = _FakeDailyService(_prices(2), [])
    _install_service(monkeypatch, service)

    exit_code = cli_main.run(
        [
            "replay",
            "run",
            "--symbol",
            "MSFT",
            "--start",
            "2026-01-01",
            "--end",
            "2026-01-02",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "baseline_trend_regime" in captured.out
    assert "insufficient_data_count" in captured.out
    assert "MSFT" in captured.out


def test_replay_summary_json_stdout_is_pure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = _FakeDailyService(_prices(2), [])
    _install_service(monkeypatch, service)

    exit_code = cli_main.run(
        [
            "replay",
            "run",
            "--symbol",
            "MSFT",
            "--start",
            "2026-01-01",
            "--end",
            "2026-01-02",
            "--format",
            "json",
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert captured.err == ""
    assert payload["symbol"] == "MSFT"
    assert payload["strategies"][0]["insufficient_data_count"] == 2


def test_replay_summary_csv_file_output_has_fixed_columns(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    service = _FakeDailyService(_prices(2), [])
    output_path = tmp_path / "reports" / "summary.csv"
    _install_service(monkeypatch, service)

    exit_code = cli_main.run(
        [
            "replay",
            "run",
            "--symbol",
            "MSFT",
            "--start",
            "2026-01-01",
            "--end",
            "2026-01-02",
            "--format",
            "csv",
            "--output",
            str(output_path),
        ]
    )
    captured = capsys.readouterr()
    content = output_path.read_text(encoding="utf-8")

    assert exit_code == 0
    assert captured.out == ""
    assert "Wrote replay summary" in captured.err
    assert content.startswith(
        "symbol,interval,start_as_of,end_as_of,step_count,strategy_id,"
        "strategy_version,configuration_fingerprint,applicable_count,"
        "not_applicable_count,insufficient_data_count,first_applicable_as_of,"
        "last_applicable_as_of,status_transition_count"
    )
    assert "baseline_trend_regime" in content
    assert "StrategyReplaySummary" not in content


def test_replay_steps_json_file_output_and_parent_creation(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    service = _FakeDailyService(_prices(2), [])
    output_path = tmp_path / "nested" / "steps.json"
    _install_service(monkeypatch, service)

    exit_code = cli_main.run(
        [
            "replay",
            "run",
            "--symbol",
            "MSFT",
            "--start",
            "2026-01-01",
            "--end",
            "2026-01-02",
            "--view",
            "steps",
            "--format",
            "json",
            "--output",
            str(output_path),
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert captured.out == ""
    assert "Wrote replay steps" in captured.err
    assert output_path.parent.exists()
    assert len(payload["steps"]) == 2
    assert payload["steps"][0]["strategy_result"]["evaluations"]


def test_replay_max_bars_rejects_before_replay_execution(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = _FakeDailyService(_prices(3), [])
    _install_service(monkeypatch, service)
    monkeypatch.setattr(cli_main, "HistoricalReplayService", _ExplodingReplayService)

    exit_code = cli_main.run(
        [
            "replay",
            "run",
            "--symbol",
            "MSFT",
            "--start",
            "2026-01-01",
            "--end",
            "2026-01-03",
            "--max-bars",
            "2",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "exceeding --max-bars 2" in captured.err


def test_replay_warmup_insufficient_data_returns_success(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = _FakeDailyService(_prices(1), [])
    _install_service(monkeypatch, service)

    exit_code = cli_main.run(
        [
            "replay",
            "run",
            "--symbol",
            "MSFT",
            "--start",
            "2026-01-01",
            "--end",
            "2026-01-01",
            "--format",
            "json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["strategies"][0]["insufficient_data_count"] == 1


def test_replay_provider_failure_returns_1(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _install_service(monkeypatch, _FailingDailyService())

    exit_code = cli_main.run(
        [
            "replay",
            "run",
            "--symbol",
            "MSFT",
            "--start",
            "2026-01-01",
            "--end",
            "2026-01-02",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "provider unavailable" in captured.err
    assert "Traceback" not in captured.err


def test_replay_contract_failure_returns_1(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = _FakeDailyService(_prices(1), [])
    _install_service(monkeypatch, service)
    monkeypatch.setattr(
        cli_main,
        "HistoricalReplayService",
        _ContractFailingReplayService,
    )

    exit_code = cli_main.run(
        [
            "replay",
            "run",
            "--symbol",
            "MSFT",
            "--start",
            "2026-01-01",
            "--end",
            "2026-01-01",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "replay contract violation" in captured.err
    assert "Traceback" not in captured.err


def test_replay_file_write_failure_returns_1(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = _FakeDailyService(_prices(1), [])
    _install_service(monkeypatch, service)

    def _raise_os_error(path: Path, content: str) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(cli_main, "_write_output", _raise_os_error)

    exit_code = cli_main.run(
        [
            "replay",
            "run",
            "--symbol",
            "MSFT",
            "--start",
            "2026-01-01",
            "--end",
            "2026-01-01",
            "--output",
            "summary.json",
            "--format",
            "json",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "disk full" in captured.err
    assert captured.out == ""


def test_replay_summary_renderer_handles_empty_strategy_evaluations() -> None:
    summary = HistoricalReplaySummary(
        symbol="MSFT",
        interval="1day",
        start_as_of=None,
        end_as_of=None,
        step_count=0,
        strategies=(),
    )

    assert cli_main._render_replay_summary(summary, "table") == (
        "No replay strategies returned.\n"
    )


def test_replay_handler_has_no_research_workflow_dependency() -> None:
    source = Path("src/market_platform/cli/main.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    replay_handler = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_handle_replay_run"
    )
    names = {node.id for node in ast.walk(replay_handler) if isinstance(node, ast.Name)}

    assert "DefaultResearchWorkflow" not in names
    assert "ResearchRequest" not in names


def test_replay_outputs_have_no_trading_or_performance_terms(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = _FakeDailyService(_prices(2), [])
    _install_service(monkeypatch, service)

    exit_code = cli_main.run(
        [
            "replay",
            "run",
            "--symbol",
            "MSFT",
            "--start",
            "2026-01-01",
            "--end",
            "2026-01-02",
            "--format",
            "json",
        ]
    )
    output = capsys.readouterr().out.lower()

    assert exit_code == 0
    for forbidden in ("buy", "sell", "hold", "p&l", "sharpe", "drawdown"):
        assert forbidden not in output
    assert "performance" not in output


def test_replay_real_sys_argv_path(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = _FakeDailyService(_prices(1), [])
    _install_service(monkeypatch, service)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "market-platform",
            "replay",
            "run",
            "--symbol",
            "MSFT",
            "--start",
            "2026-01-01",
            "--end",
            "2026-01-01",
            "--format",
            "json",
        ],
    )

    with pytest.raises(SystemExit) as excinfo:
        cli_main.main()

    captured = capsys.readouterr()

    assert excinfo.value.code == 0
    assert json.loads(captured.out)["symbol"] == "MSFT"
