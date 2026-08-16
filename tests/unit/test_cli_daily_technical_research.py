from __future__ import annotations

import asyncio
import json
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pandas as pd
import pytest

import market_platform.research.daily_instrument_integrity as integrity_module
from market_platform.cli import main as cli_main
from market_platform.data.capabilities import DataCapability
from market_platform.data.exceptions import DataProviderError
from market_platform.data.http import HTTPClient
from market_platform.data.provider import DataProvider
from market_platform.data.providers.polygon import PolygonProvider
from market_platform.data.selection import ProviderCandidate, ProviderSelectionPolicy
from market_platform.data.service import MarketDataService
from market_platform.research import (
    DailyTechnicalResearchRequest,
    DailyTechnicalResearchResult,
    DailyTechnicalResearchWorkflow,
    ResearchTimeframe,
    TechnicalAnalysisQuality,
    TechnicalAnalysisWarning,
    construct_daily_technical_analysis_profile,
)
from market_platform.trading.instrument import TradingInstrumentIdentity

_AS_OF = datetime(2026, 8, 12, 16, tzinfo=UTC)


class _Provider(DataProvider):
    name = "polygon"

    def __init__(self, count: int = 260) -> None:
        dates = pd.bdate_range(end=date(2026, 8, 11), periods=count, tz=UTC)
        self.frame = pd.DataFrame(
            [
                {
                    "symbol": "NVDA",
                    "timestamp": timestamp,
                    "open": 100.0 + index,
                    "high": 102.0 + index,
                    "low": 99.0 + index,
                    "close": 101.123456789 + index,
                    "volume": 1_000_000.0 + index,
                    "provider": "polygon",
                }
                for index, timestamp in enumerate(dates)
            ]
        )

    async def get_daily_prices(
        self, symbol: str, start: date | str, end: date | str
    ) -> pd.DataFrame:
        return self.frame.copy(deep=True)

    async def get_intraday_prices(
        self, symbol: str, start: object, end: object, interval: str = "1min"
    ) -> pd.DataFrame:
        raise AssertionError

    async def get_latest_price(self, symbol: str) -> pd.DataFrame:
        raise AssertionError

    async def health_check(self) -> pd.DataFrame:
        raise AssertionError


def _polygon_provider(count: int = 260) -> PolygonProvider:
    source = _Provider(count)

    def handler(request: httpx.Request) -> httpx.Response:
        results = [
            {
                "t": int((row.timestamp + pd.Timedelta(hours=12)).timestamp() * 1000),
                "o": row.open,
                "h": row.high,
                "l": row.low,
                "c": row.close,
                "v": row.volume,
            }
            for row in source.frame.itertuples()
        ]
        return httpx.Response(200, json={"adjusted": True, "results": results})

    return PolygonProvider(
        api_key="test-key",
        http_client=HTTPClient(
            client=httpx.Client(transport=httpx.MockTransport(handler))
        ),
    )


def _result(
    count: int = 260, *, as_of: datetime = _AS_OF
) -> DailyTechnicalResearchResult:
    provider = _polygon_provider(count)
    service = MarketDataService(
        ProviderSelectionPolicy(
            [
                ProviderCandidate(
                    "polygon", provider, frozenset({DataCapability.DAILY_PRICES})
                )
            ],
            ["polygon"],
        )
    )
    request = DailyTechnicalResearchRequest(
        TradingInstrumentIdentity("NVDA", "NASDAQ"),
        ResearchTimeframe.DAILY,
        "polygon",
        as_of,
        construct_daily_technical_analysis_profile(),
    )
    return asyncio.run(DailyTechnicalResearchWorkflow(service).run(request))


class _Workflow:
    result: DailyTechnicalResearchResult = _result()
    error: Exception | None = None
    requests: list[DailyTechnicalResearchRequest] = []

    def __init__(self, service: object) -> None:
        self.service = service

    async def run(
        self, request: DailyTechnicalResearchRequest
    ) -> DailyTechnicalResearchResult:
        type(self).requests.append(request)
        if self.error is not None:
            raise self.error
        return self.result


def _configure(
    monkeypatch: pytest.MonkeyPatch, result: DailyTechnicalResearchResult | None = None
) -> None:
    _Workflow.result = result or _result()
    _Workflow.error = None
    _Workflow.requests = []
    monkeypatch.setattr(cli_main, "create_default_market_data_service", object)
    monkeypatch.setattr(cli_main, "DailyTechnicalResearchWorkflow", _Workflow)


def _run(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], *args: str
) -> tuple[int, str, str]:
    _configure(monkeypatch)
    code = cli_main.run(
        [
            "research",
            "analyze",
            "--symbol",
            "NVDA",
            "--venue",
            "NASDAQ",
            "--as-of",
            _AS_OF.isoformat(),
            *args,
        ]
    )
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_parser_registration_defaults_and_choices() -> None:
    args = cli_main.build_parser().parse_args(
        ["research", "analyze", "--symbol", "nvda", "--venue", "nasdaq"]
    )
    assert (args.research_command, args.timeframe, args.provider, args.format) == (
        "analyze",
        "1d",
        "polygon",
        "table",
    )
    for option, value in (
        ("--timeframe", "1h"),
        ("--provider", "twelvedata"),
        ("--format", "csv"),
    ):
        with pytest.raises(SystemExit) as excinfo:
            cli_main.build_parser().parse_args(
                [
                    "research",
                    "analyze",
                    "--symbol",
                    "NVDA",
                    "--venue",
                    "NASDAQ",
                    option,
                    value,
                ]
            )
        assert excinfo.value.code == 2


@pytest.mark.parametrize("missing", ["--symbol", "--venue"])
def test_parser_requires_symbol_and_venue(missing: str) -> None:
    argv = ["research", "analyze", "--symbol", "NVDA", "--venue", "NASDAQ"]
    index = argv.index(missing)
    del argv[index : index + 2]
    with pytest.raises(SystemExit) as excinfo:
        cli_main.build_parser().parse_args(argv)
    assert excinfo.value.code == 2


def test_identity_normalizes_and_injects_exact_as_of(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _configure(monkeypatch)
    capsys.readouterr()
    code = cli_main.run(
        [
            "research",
            "analyze",
            "--symbol",
            " nvda ",
            "--venue",
            " nasdaq ",
            "--as-of",
            "2026-08-13T00:00:00+08:00",
            "--format",
            "json",
        ]
    )
    captured = capsys.readouterr()
    request = _Workflow.requests[0]
    assert code == 0 and captured.err == ""
    assert (request.instrument.symbol, request.instrument.venue) == ("NVDA", "NASDAQ")
    assert request.analysis_as_of == _AS_OF


@pytest.mark.parametrize(
    "symbol,venue",
    [
        (" ", "NASDAQ"),
        ("NV DA", "NASDAQ"),
        ("NASDAQ:NVDA", "NASDAQ"),
        ("NVDA", " "),
        ("NVDA", "NAS DAQ"),
    ],
)
def test_invalid_identity_returns_two(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    symbol: str,
    venue: str,
) -> None:
    _configure(monkeypatch)
    code = cli_main.run(
        [
            "research",
            "analyze",
            "--symbol",
            symbol,
            "--venue",
            venue,
            "--as-of",
            _AS_OF.isoformat(),
        ]
    )
    assert code == 2
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    "value",
    [
        "2026-08-12T16:00:00Z",
        "2026-08-12T16:00:00.123456Z",
        "2026-08-13T00:00:00+08:00",
    ],
)
def test_aware_as_of_forms_are_accepted(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], value: str
) -> None:
    _configure(monkeypatch)
    assert (
        cli_main.run(
            [
                "research",
                "analyze",
                "--symbol",
                "NVDA",
                "--venue",
                "NASDAQ",
                "--as-of",
                value,
                "--format",
                "json",
            ]
        )
        == 0
    )
    assert _Workflow.requests[0].analysis_as_of.tzinfo is UTC
    capsys.readouterr()


@pytest.mark.parametrize(
    "value",
    [
        "2026-08-12",
        "2026-08-12T16:00:00",
        "2026-08-12T16:00:00+0800",
        "bad+08:00",
        "2026-08-12 16:00:00Z",
    ],
)
def test_invalid_as_of_is_parser_error(value: str) -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli_main.build_parser().parse_args(
            [
                "research",
                "analyze",
                "--symbol",
                "NVDA",
                "--venue",
                "NASDAQ",
                "--as-of",
                value,
            ]
        )
    assert excinfo.value.code == 2


def test_default_clock_is_read_exactly_once(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _configure(monkeypatch, _result(as_of=_AS_OF))
    calls: list[object] = []

    class _Clock(datetime):
        @classmethod
        def now(cls, tz: object = None) -> datetime:
            calls.append(tz)
            return _AS_OF

    monkeypatch.setattr(cli_main, "datetime", _Clock)
    code = cli_main.run(
        [
            "research",
            "analyze",
            "--symbol",
            "NVDA",
            "--venue",
            "NASDAQ",
            "--format",
            "json",
        ]
    )
    assert code == 0 and calls == [UTC]
    assert _Workflow.requests[0].analysis_as_of == _AS_OF
    capsys.readouterr()


def test_table_has_exact_field_order_and_presentation_only_formatting(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    result = _result()
    semantic = result.snapshot.latest_close
    _configure(monkeypatch, result)
    code = cli_main.run(
        [
            "research",
            "analyze",
            "--symbol",
            "NVDA",
            "--venue",
            "NASDAQ",
            "--as-of",
            _AS_OF.isoformat(),
        ]
    )
    output = capsys.readouterr().out
    expected = [
        "Symbol",
        "Venue",
        "Timeframe",
        "Provider",
        "Adjustment",
        "Analysis As Of",
        "Latest Completed Session",
        "Bars",
        "Calendar Lag Days",
        "Quality",
        "Latest Close",
        "EMA8",
        "EMA20",
        "EMA144",
        "EMA169",
        "EMA Alignment",
        "Tunnel Position",
        "MACD",
        "MACD Signal",
        "MACD Histogram",
        "RSI14",
        "Wilder ATR14",
        "ATR%",
        "Realized Volatility",
        "Current Drawdown",
        "-1 ATR",
        "+1 ATR",
        "-1.5 ATR",
        "+1.5 ATR",
        "-2 ATR",
        "+2 ATR",
        "EMA20 Distance %",
        "Trend State",
        "Momentum State",
        "Volatility State",
        "Warnings",
        "Unavailable Components",
        "Dataset Fingerprint",
        "Evidence Fingerprint",
        "Profile Fingerprint",
        "Snapshot Fingerprint",
    ]
    positions = [output.index(field) for field in expected]
    assert code == 0 and positions == sorted(positions)
    assert "Section" in output and "Field" in output and "Value" in output
    assert result.snapshot.latest_close == semantic
    assert str(semantic) not in output and f"{semantic:.4f}" in output


def test_degraded_table_renders_placeholders_warnings_and_unavailable_order(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    result = _result(5)
    _configure(monkeypatch, result)
    code = cli_main.run(
        [
            "research",
            "analyze",
            "--symbol",
            "NVDA",
            "--venue",
            "NASDAQ",
            "--as-of",
            _AS_OF.isoformat(),
        ]
    )
    output = capsys.readouterr().out
    assert code == 0 and result.snapshot.quality is TechnicalAnalysisQuality.DEGRADED
    assert "Insufficient history for the complete fixed profile" in output
    assert "ema_8, ema_20, ema_144, ema_169, macd" in output
    assert " -" in output


def test_stale_success_returns_zero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    result = _result(260, as_of=datetime(2026, 9, 1, tzinfo=UTC))
    _configure(monkeypatch, result)
    code = cli_main.run(
        [
            "research",
            "analyze",
            "--symbol",
            "NVDA",
            "--venue",
            "NASDAQ",
            "--as-of",
            "2026-09-01T00:00:00Z",
        ]
    )
    assert (
        code == 0
        and TechnicalAnalysisWarning.STALE_EVIDENCE in result.snapshot.warnings
    )
    capsys.readouterr()


def test_json_is_exact_unrounded_projection_with_fingerprints(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    result = _result()
    _configure(monkeypatch, result)
    code = cli_main.run(
        [
            "research",
            "analyze",
            "--symbol",
            "NVDA",
            "--venue",
            "NASDAQ",
            "--as-of",
            _AS_OF.isoformat(),
            "--format",
            "json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 0 and list(payload) == ["request", "snapshot"]
    assert payload == result.to_dict()
    assert payload["snapshot"]["latest_close"] == result.snapshot.latest_close
    assert payload["snapshot"]["fingerprint"] == result.snapshot.fingerprint


@pytest.mark.parametrize("output_format", ["table", "json"])
def test_output_file(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    output_format: str,
) -> None:
    _configure(monkeypatch)
    path = tmp_path / "nested" / f"analysis.{output_format}"
    code = cli_main.run(
        [
            "research",
            "analyze",
            "--symbol",
            "NVDA",
            "--venue",
            "NASDAQ",
            "--as-of",
            _AS_OF.isoformat(),
            "--format",
            output_format,
            "--output",
            str(path),
        ]
    )
    assert code == 0 and capsys.readouterr().out == ""
    assert path.read_text(encoding="utf-8").endswith("\n")


def test_output_and_provider_failures_return_one(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _configure(monkeypatch)
    monkeypatch.setattr(
        cli_main,
        "_write_output",
        lambda path, content: (_ for _ in ()).throw(OSError("write failed")),
    )
    assert (
        cli_main.run(
            [
                "research",
                "analyze",
                "--symbol",
                "NVDA",
                "--venue",
                "NASDAQ",
                "--as-of",
                _AS_OF.isoformat(),
                "--output",
                "x",
            ]
        )
        == 1
    )
    capsys.readouterr()
    _configure(monkeypatch)
    _Workflow.error = DataProviderError("acquisition failed")
    assert (
        cli_main.run(
            [
                "research",
                "analyze",
                "--symbol",
                "NVDA",
                "--venue",
                "NASDAQ",
                "--as-of",
                _AS_OF.isoformat(),
            ]
        )
        == 1
    )
    assert "acquisition failed" in capsys.readouterr().err


def test_research_run_defaults_remain_unchanged() -> None:
    args = cli_main.build_parser().parse_args(["research", "run", "--symbol", "MSFT"])
    assert (args.horizon_days, args.lookback_days, args.format) == (20, 120, "table")


@pytest.mark.parametrize(
    ("option", "first", "second"),
    [
        ("--symbol", "NVDA", "AAPL"),
        ("--venue", "NASDAQ", "NYSE"),
        ("--timeframe", "1d", "1d"),
        ("--provider", "polygon", "polygon"),
        ("--as-of", "2026-08-12T16:00:00Z", "2026-08-12T17:00:00Z"),
        ("--format", "table", "json"),
        ("--output", "a", "b"),
    ],
)
def test_duplicate_research_analyze_singletons_exit_two(
    option: str, first: str, second: str
) -> None:
    argv = ["research", "analyze", "--symbol", "NVDA", "--venue", "NASDAQ"]
    if option in {"--symbol", "--venue"}:
        index = argv.index(option)
        argv[index + 1] = first
    else:
        argv.extend([option, first])
    argv.extend([option, second])
    with pytest.raises(SystemExit) as excinfo:
        cli_main.build_parser().parse_args(argv)
    assert excinfo.value.code == 2


@pytest.mark.parametrize(
    "value",
    [
        "2026-08-12T16:00:00+08:60",
        "2026-08-12T16:00:00+08:99",
        "2026-08-12T16:00:00+24:00",
        "20260812T160000Z",
        "2026-W33-3T16:00:00Z",
        "2026-224T16:00:00Z",
        "2026-08-12T16:00Z",
        "2026-08-12T16:00:00,1Z",
        "2026-08-12T16:00:00z",
        "2026-08-12T16:00:00Zjunk",
    ],
)
def test_strict_as_of_rejects_iso_alternatives(value: str) -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli_main.build_parser().parse_args(
            [
                "research",
                "analyze",
                "--symbol",
                "NVDA",
                "--venue",
                "NASDAQ",
                "--as-of",
                value,
            ]
        )
    assert excinfo.value.code == 2


def test_service_factory_configuration_error_returns_one(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _configure(monkeypatch)
    monkeypatch.setattr(
        cli_main,
        "create_default_market_data_service",
        lambda: (_ for _ in ()).throw(cli_main.ConfigurationError("factory failed")),
    )
    code = cli_main.run(
        ["research", "analyze", "--symbol", "NVDA", "--venue", "NASDAQ"]
    )
    assert code == 1 and "factory failed" in capsys.readouterr().err


def test_table_and_json_share_result_validation_boundary() -> None:
    result = _result()
    object.__setattr__(result.request, "provider", "twelvedata")
    with pytest.raises(ValueError):
        cli_main._render_daily_technical_research_result(result, "table")
    with pytest.raises(ValueError):
        cli_main._render_daily_technical_research_result(result, "json")


def test_table_number_format_preserves_nonzero_and_normalizes_negative_zero() -> None:
    assert cli_main._format_analysis_number(-0.0, 4) == "0"
    assert cli_main._format_analysis_number(0.000001, 4) not in {"0", "-0"}


def test_table_has_exact_41_semantic_rows() -> None:
    lines = cli_main._render_daily_technical_research_table(_result()).splitlines()
    header_index = next(
        index
        for index, line in enumerate(lines)
        if "Section" in line and "Field" in line
    )
    header = lines[header_index]
    section_end = header.index("Section") + len("Section")
    field_end = header.index("Field") + len("Field")
    semantic = [
        (line[:section_end].strip(), line[section_end:field_end].strip())
        for line in lines[header_index + 1 :]
        if line[:section_end].strip(" |+-")
        and line[section_end:field_end].strip(" |+-")
    ]
    assert semantic == [
        ("Identity", "Symbol"),
        ("Identity", "Venue"),
        ("Identity", "Timeframe"),
        ("Data", "Provider"),
        ("Data", "Adjustment"),
        ("Data", "Analysis As Of"),
        ("Data", "Latest Completed Session"),
        ("Data", "Bars"),
        ("Data", "Calendar Lag Days"),
        ("Data", "Quality"),
        ("Trend", "Latest Close"),
        ("Trend", "EMA8"),
        ("Trend", "EMA20"),
        ("Trend", "EMA144"),
        ("Trend", "EMA169"),
        ("Trend", "EMA Alignment"),
        ("Trend", "Tunnel Position"),
        ("Momentum", "MACD"),
        ("Momentum", "MACD Signal"),
        ("Momentum", "MACD Histogram"),
        ("Momentum", "RSI14"),
        ("Volatility", "Wilder ATR14"),
        ("Volatility", "ATR%"),
        ("Volatility", "Realized Volatility"),
        ("Volatility", "Current Drawdown"),
        ("References", "-1 ATR"),
        ("References", "+1 ATR"),
        ("References", "-1.5 ATR"),
        ("References", "+1.5 ATR"),
        ("References", "-2 ATR"),
        ("References", "+2 ATR"),
        ("References", "EMA20 Distance %"),
        ("Conclusion", "Trend State"),
        ("Conclusion", "Momentum State"),
        ("Conclusion", "Volatility State"),
        ("Warnings", "Warnings"),
        ("Warnings", "Unavailable Components"),
        ("Provenance", "Dataset Fingerprint"),
        ("Provenance", "Evidence Fingerprint"),
        ("Provenance", "Profile Fingerprint"),
        ("Provenance", "Snapshot Fingerprint"),
    ]


def test_verified_parser_defaults_and_required_mapping_path() -> None:
    args = cli_main.build_parser().parse_args(
        [
            "research",
            "analyze-verified",
            "--symbol",
            "NVDA",
            "--venue",
            "NASDAQ",
            "--instrument-mappings",
            "mapping.json",
        ]
    )
    assert (args.timeframe, args.provider, args.format, args.output) == (
        "1d",
        "polygon",
        "table",
        None,
    )


@pytest.mark.parametrize(
    ("option", "value"),
    [
        ("--symbol", "NVDA"),
        ("--venue", "NASDAQ"),
        ("--instrument-mappings", "mapping.json"),
        ("--timeframe", "1d"),
        ("--provider", "polygon"),
        ("--as-of", "2026-08-12T00:00:00Z"),
        ("--format", "json"),
        ("--output", "output.json"),
    ],
)
def test_verified_singleton_options_reject_repetition(option: str, value: str) -> None:
    argv = [
        "research",
        "analyze-verified",
        "--symbol",
        "NVDA",
        "--venue",
        "NASDAQ",
        "--instrument-mappings",
        "mapping.json",
    ]
    with pytest.raises(SystemExit) as error:
        cli_main.build_parser().parse_args([*argv, option, value, option, value])
    assert error.value.code == 2


def test_verified_metadata_load_precedes_service_creation(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service_calls = 0

    def service_factory() -> object:
        nonlocal service_calls
        service_calls += 1
        raise AssertionError("service factory must not be reached")

    monkeypatch.setattr(
        cli_main,
        "load_trusted_instrument_mapping_registry",
        lambda path: (_ for _ in ()).throw(ValueError("invalid metadata")),
    )
    monkeypatch.setattr(cli_main, "create_default_market_data_service", service_factory)
    code = cli_main.run(
        [
            "research",
            "analyze-verified",
            "--symbol",
            "NVDA",
            "--venue",
            "NASDAQ",
            "--instrument-mappings",
            "secret-mapping-path.json",
        ]
    )
    captured = capsys.readouterr()
    assert code == 1
    assert service_calls == 0
    assert "invalid metadata" in captured.err
    assert "secret-mapping-path.json" not in captured.out + captured.err


def _verified_mapping_document(case: str) -> dict[str, object]:
    canonical_identity = {"symbol": "NVDA", "venue": "NASDAQ"}
    if case == "canonical_mismatch":
        canonical_identity = {"symbol": "NVDA", "venue": "NYSE"}
    instruments = [
        {
            "instrument_id": "synthetic.current",
            "trading_identity": canonical_identity,
            "asset_class": "equity",
            "trading_currency": "USD",
        }
    ]
    external_venue = "NYSE" if case == "missing" else "NASDAQ"
    valid_from = "2026-08-13" if case == "inactive" else "2020-01-01"
    mappings = [
        {
            "external_identity": {
                "namespace": "polygon",
                "external_symbol": "NVDA",
                "external_venue": external_venue,
            },
            "canonical_instrument_id": "synthetic.current",
            "valid_from": valid_from,
            "expires_at": None,
        }
    ]
    if case in {"ambiguous", "conflicting"}:
        second_id = "synthetic.current"
        if case == "conflicting":
            second_id = "synthetic.other"
            instruments.append(
                {
                    "instrument_id": second_id,
                    "trading_identity": {
                        "symbol": "NVDA",
                        "venue": "NASDAQ",
                    },
                    "asset_class": "equity",
                    "trading_currency": "USD",
                }
            )
        mappings.append(
            {
                "external_identity": {
                    "namespace": "polygon",
                    "external_symbol": "NVDA",
                    "external_venue": "NASDAQ",
                },
                "canonical_instrument_id": second_id,
                "valid_from": "2021-01-01",
                "expires_at": None,
            }
        )
    return {
        "schema_version": "trusted_instrument_mapping_document/v1",
        "source": {
            "source_id": "synthetic",
            "source_version": "1",
            "configuration_fingerprint": None,
        },
        "instruments": instruments,
        "mappings": mappings,
    }


@pytest.mark.parametrize(
    "case", ["missing", "inactive", "ambiguous", "conflicting", "canonical_mismatch"]
)
def test_verified_semantic_metadata_failure_precedes_service_and_provider_io(
    case: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service_calls = 0
    provider_calls = 0

    def service_factory() -> object:
        nonlocal service_calls
        service_calls += 1
        raise AssertionError("service factory must not be reached")

    async def acquire(service: object, request: object) -> object:
        nonlocal provider_calls
        provider_calls += 1
        raise AssertionError("provider I/O must not be reached")

    path = tmp_path / f"{case}.json"
    path.write_text(json.dumps(_verified_mapping_document(case)), encoding="utf-8")
    monkeypatch.setattr(cli_main, "create_default_market_data_service", service_factory)
    monkeypatch.setattr(integrity_module, "_acquire_polygon_daily_prices", acquire)
    code = cli_main.run(
        [
            "research",
            "analyze-verified",
            "--symbol",
            "NVDA",
            "--venue",
            "NASDAQ",
            "--as-of",
            _AS_OF.isoformat(),
            "--instrument-mappings",
            str(path),
        ]
    )
    assert code == 1
    assert service_calls == 0
    assert provider_calls == 0
