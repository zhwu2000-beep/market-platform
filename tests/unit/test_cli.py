from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from market_platform.cli import main as cli_main
from market_platform.data.capabilities import DataCapability
from market_platform.data.provider import DataProvider
from market_platform.data.selection import ProviderCandidate, ProviderSelectionPolicy
from market_platform.data.service import MarketDataService


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


@dataclass
class _LatestFakeService:
    frame: pd.DataFrame
    calls: list[tuple[str, str | None]]

    async def get_latest_price(
        self,
        symbol: str,
        provider: str | None = None,
    ) -> pd.DataFrame:
        self.calls.append((symbol, provider))
        return self.frame


@dataclass
class _IntradayFakeService:
    frame: pd.DataFrame
    calls: list[tuple[str, str | None, str]]

    async def get_intraday_prices(
        self,
        symbol: str,
        provider: str | None = None,
        interval: str = "1min",
    ) -> pd.DataFrame:
        self.calls.append((symbol, provider, interval))
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


def _latest_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": "MSFT",
                "timestamp": pd.Timestamp("2026-01-01T00:00:00Z"),
                "price": 100.5,
                "provider": "polygon",
            }
        ]
    )


def _intraday_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": "AAPL",
                "timestamp": pd.Timestamp("2026-01-01T09:31:00Z"),
                "open": 101.0,
                "high": 102.0,
                "low": 100.0,
                "close": 101.5,
                "volume": 1000,
                "provider": "twelvedata",
            },
            {
                "symbol": "AAPL",
                "timestamp": pd.Timestamp("2026-01-01T09:30:00Z"),
                "open": 100.0,
                "high": 101.0,
                "low": 99.5,
                "close": 100.5,
                "volume": 900,
                "provider": "twelvedata",
            },
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


def test_latest_table_format_still_works(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = _LatestFakeService(frame=_latest_frame(), calls=[])
    monkeypatch.setattr(
        cli_main,
        "create_default_market_data_service",
        lambda: service,
    )

    exit_code = cli_main.run(
        [
            "data",
            "latest",
            "--symbol",
            "msft",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "MSFT" in captured.out
    assert "100.5" in captured.out
    assert service.calls == [("MSFT", None)]


def test_latest_json_format_produces_valid_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = _LatestFakeService(frame=_latest_frame(), calls=[])
    monkeypatch.setattr(
        cli_main,
        "create_default_market_data_service",
        lambda: service,
    )

    exit_code = cli_main.run(
        [
            "data",
            "latest",
            "--symbol",
            "MSFT",
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
            "price": 100.5,
            "provider": "polygon",
        }
    ]
    assert service.calls == [("MSFT", None)]


def test_latest_csv_format_with_output_writes_file(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    service = _LatestFakeService(frame=_latest_frame(), calls=[])
    output_path = tmp_path / "data" / "msft_latest.csv"
    monkeypatch.setattr(
        cli_main,
        "create_default_market_data_service",
        lambda: service,
    )

    exit_code = cli_main.run(
        [
            "data",
            "latest",
            "--symbol",
            "MSFT",
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
        "symbol,timestamp,price,provider"
    )
    assert "Wrote 1 row" in captured.out
    assert service.calls == [("MSFT", None)]


def test_latest_explicit_twelve_data_provider_passes_through(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = _LatestFakeService(frame=_latest_frame(), calls=[])
    monkeypatch.setattr(
        cli_main,
        "create_default_market_data_service",
        lambda: service,
    )

    exit_code = cli_main.run(
        [
            "data",
            "latest",
            "--symbol",
            "msft",
            "--provider",
            "twelve_data",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "MSFT" in captured.out
    assert service.calls == [("MSFT", "twelve_data")]


def test_intraday_table_format_still_works(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = _IntradayFakeService(frame=_intraday_frame(), calls=[])
    monkeypatch.setattr(
        cli_main,
        "create_default_market_data_service",
        lambda: service,
    )

    exit_code = cli_main.run(
        [
            "data",
            "intraday",
            "--symbol",
            "aapl",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "AAPL" in captured.out
    assert "twelvedata" in captured.out
    assert service.calls == [("AAPL", None, "1min")]


def test_intraday_json_format_produces_valid_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = _IntradayFakeService(frame=_intraday_frame(), calls=[])
    monkeypatch.setattr(
        cli_main,
        "create_default_market_data_service",
        lambda: service,
    )

    exit_code = cli_main.run(
        [
            "data",
            "intraday",
            "--symbol",
            "AAPL",
            "--format",
            "json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload[0]["symbol"] == "AAPL"
    assert payload[0]["provider"] == "twelvedata"
    assert service.calls == [("AAPL", None, "1min")]


def test_intraday_csv_format_with_output_writes_file(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    service = _IntradayFakeService(frame=_intraday_frame(), calls=[])
    output_path = tmp_path / "data" / "aapl-intraday.csv"
    monkeypatch.setattr(
        cli_main,
        "create_default_market_data_service",
        lambda: service,
    )

    exit_code = cli_main.run(
        [
            "data",
            "intraday",
            "--symbol",
            "AAPL",
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
    assert "Wrote 2 rows" in captured.out
    assert service.calls == [("AAPL", None, "1min")]


def test_intraday_interval_is_passed_through(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = _IntradayFakeService(frame=_intraday_frame(), calls=[])
    monkeypatch.setattr(
        cli_main,
        "create_default_market_data_service",
        lambda: service,
    )

    exit_code = cli_main.run(
        [
            "data",
            "intraday",
            "--symbol",
            "AAPL",
            "--interval",
            "5min",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "AAPL" in captured.out
    assert service.calls == [("AAPL", None, "5min")]


def test_intraday_explicit_twelve_data_provider_passes_through(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = _IntradayFakeService(frame=_intraday_frame(), calls=[])
    monkeypatch.setattr(
        cli_main,
        "create_default_market_data_service",
        lambda: service,
    )

    exit_code = cli_main.run(
        [
            "data",
            "intraday",
            "--symbol",
            "AAPL",
            "--provider",
            "twelve_data",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "AAPL" in captured.out
    assert service.calls == [("AAPL", "twelve_data", "1min")]


class _MissingIntradayProvider(DataProvider):
    name = "legacy"

    async def get_daily_prices(
        self,
        symbol: str,
        start: date,
        end: date,
    ) -> pd.DataFrame:
        return pd.DataFrame()

    async def get_intraday_prices(
        self,
        symbol: str,
        start: pd.Timestamp,
        end: pd.Timestamp,
        interval: str = "1min",
    ) -> pd.DataFrame:
        return pd.DataFrame()

    async def get_latest_price(self, symbol: str) -> pd.DataFrame:
        return pd.DataFrame()

    async def health_check(self) -> pd.DataFrame:
        return pd.DataFrame()


def test_intraday_unsupported_provider_capability_errors_cleanly(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = MarketDataService(
        ProviderSelectionPolicy(
            candidates=[
                ProviderCandidate(
                    name="polygon",
                    provider=_MissingIntradayProvider(),
                    priority=1,
                    capabilities=frozenset[DataCapability](),
                ),
                ProviderCandidate(
                    name="twelvedata",
                    provider=_MissingIntradayProvider(),
                    priority=2,
                    capabilities=frozenset[DataCapability](),
                ),
            ]
        )
    )
    monkeypatch.setattr(
        cli_main,
        "create_default_market_data_service",
        lambda: service,
    )

    exit_code = cli_main.run(
        [
            "data",
            "intraday",
            "--symbol",
            "AAPL",
            "--provider",
            "polygon",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert "does not support intraday_prices" in captured.err
    assert "Traceback" not in captured.err


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
