from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import pytest

from market_platform.cli import main as cli_main


@dataclass
class _FakeService:
    frame: pd.DataFrame
    calls: list[tuple[str, str, str, str | None]]

    async def get_daily_prices(
        self,
        symbol: str,
        start: str,
        end: str,
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
            "MSFT",
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
    assert service.calls == [("MSFT", "2026-01-01", "2026-01-02", None)]


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
