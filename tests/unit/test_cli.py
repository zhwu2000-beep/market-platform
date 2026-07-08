from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from market_platform.cli import main as cli_main


@dataclass
class _FakeService:
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


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": "MSFT",
                "timestamp": pd.Timestamp("2026-01-01T00:00:00Z"),
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": 1000,
                "provider": "polygon",
            }
        ]
    )


def test_default_table_format_still_works(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = _FakeService(frame=_frame(), calls=[])
    monkeypatch.setattr(
        cli_main,
        "create_default_market_data_service",
        lambda: service,
    )

    exit_code = cli_main.run(
        [
            "data",
            "fetch",
            "--symbol",
            "msft",
            "--start",
            "2026-01-01",
            "--end",
            "2026-01-02",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "MSFT" in captured.out
    assert "polygon" in captured.out
    assert service.calls == [
        (
            "MSFT",
            date(2026, 1, 1),
            date(2026, 1, 2),
            None,
        )
    ]


def test_json_format_produces_valid_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = _FakeService(frame=_frame(), calls=[])
    monkeypatch.setattr(
        cli_main,
        "create_default_market_data_service",
        lambda: service,
    )

    exit_code = cli_main.run(
        [
            "data",
            "fetch",
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
    assert payload == [
        {
            "symbol": "MSFT",
            "timestamp": "2026-01-01T00:00:00+00:00",
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 1000,
            "provider": "polygon",
        }
    ]


def test_csv_format_produces_csv_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = _FakeService(frame=_frame(), calls=[])
    monkeypatch.setattr(
        cli_main,
        "create_default_market_data_service",
        lambda: service,
    )

    exit_code = cli_main.run(
        [
            "data",
            "fetch",
            "--symbol",
            "MSFT",
            "--start",
            "2026-01-01",
            "--end",
            "2026-01-02",
            "--format",
            "csv",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "symbol,timestamp,open,high,low,close,volume,provider" in captured.out
    assert "MSFT,2026-01-01T00:00:00+00:00,100.0,101.0,99.0,100.5,1000,polygon" in (
        captured.out
    )


@pytest.mark.parametrize(
    ("flag", "value", "expected"),
    [
        (
            "--start",
            "2026-13-01",
            "argument --start: invalid date '2026-13-01'; expected format YYYY-MM-DD",
        ),
        (
            "--end",
            "abc",
            "argument --end: invalid date 'abc'; expected format YYYY-MM-DD",
        ),
    ],
)
def test_invalid_date_inputs_exit_cleanly(
    flag: str,
    value: str,
    expected: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli_main.run(
            [
                "data",
                "fetch",
                "--symbol",
                "MSFT",
                "--start",
                "2026-01-01" if flag == "--end" else value,
                "--end",
                "2026-01-02" if flag == "--start" else value,
            ]
        )

    captured = capsys.readouterr()

    assert excinfo.value.code == 2
    assert expected in captured.err
    assert "Traceback" not in captured.err


def test_start_after_end_fails_before_service_call(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    created = False

    def _create_service() -> _FakeService:
        nonlocal created
        created = True
        return _FakeService(frame=_frame(), calls=[])

    monkeypatch.setattr(
        cli_main,
        "create_default_market_data_service",
        _create_service,
    )

    exit_code = cli_main.run(
        [
            "data",
            "fetch",
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
    assert "start date must be earlier than or equal to end date" in captured.err


def test_csv_format_with_output_writes_file(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    service = _FakeService(frame=_frame(), calls=[])
    output_path = tmp_path / "data" / "msft.csv"
    monkeypatch.setattr(
        cli_main,
        "create_default_market_data_service",
        lambda: service,
    )

    exit_code = cli_main.run(
        [
            "data",
            "fetch",
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

    assert exit_code == 0
    assert output_path.exists()
    assert output_path.read_text(encoding="utf-8").startswith(
        "symbol,timestamp,open,high,low,close,volume,provider"
    )
    assert "Wrote 1 rows" in captured.out


def test_output_creates_parent_directories(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    service = _FakeService(frame=_frame(), calls=[])
    output_path = tmp_path / "nested" / "reports" / "msft.json"
    monkeypatch.setattr(
        cli_main,
        "create_default_market_data_service",
        lambda: service,
    )

    exit_code = cli_main.run(
        [
            "data",
            "fetch",
            "--symbol",
            "MSFT",
            "--start",
            "2026-01-01",
            "--end",
            "2026-01-02",
            "--format",
            "json",
            "--output",
            str(output_path),
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert output_path.exists()
    assert output_path.parent.exists()
    assert json.loads(output_path.read_text(encoding="utf-8"))[0]["symbol"] == "MSFT"
    assert "Wrote 1 rows" in captured.out


def test_data_providers_default_table_format_still_works(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = cli_main.run(["data", "providers"])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Provider diagnostics" in captured.out
    assert "Configured provider order:" in captured.out
    assert "Known providers:" in captured.out


def test_data_providers_json_format_produces_valid_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = cli_main.run(["data", "providers", "--format", "json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert sorted(payload) == [
        "configured_provider_order",
        "known_provider_names",
        "providers",
    ]
    assert isinstance(payload["configured_provider_order"], list)
    assert isinstance(payload["known_provider_names"], list)
    assert isinstance(payload["providers"], list)
    assert payload["providers"]
    assert {
        "name",
        "configured",
        "capabilities",
    } <= set(payload["providers"][0])


def test_data_providers_json_output_writes_file(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "reports" / "providers.json"

    exit_code = cli_main.run(
        [
            "data",
            "providers",
            "--format",
            "json",
            "--output",
            str(output_path),
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert output_path.exists()
    assert output_path.parent.exists()
    assert isinstance(payload["providers"], list)
    assert "Wrote provider diagnostics" in captured.out