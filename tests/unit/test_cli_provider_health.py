from __future__ import annotations

import json
import logging
import shutil
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest

import market_platform.logging as market_logging
from market_platform.cli import main as cli_main
from market_platform.config import Settings
from market_platform.data import health
from market_platform.data.provider import DataProvider
from market_platform.data.registry import ProviderRegistry


@dataclass
class _FakeProvider(DataProvider):
    name: str
    health_result: object
    health_exc: Exception | None = None
    calls: list[str] | None = None

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
        start: datetime,
        end: datetime,
        interval: str = "1min",
    ) -> pd.DataFrame:
        return pd.DataFrame()

    async def get_latest_price(self, symbol: str) -> pd.DataFrame:
        return pd.DataFrame()

    async def health_check(self) -> object:
        if self.calls is not None:
            self.calls.append(self.name)
        if self.health_exc is not None:
            raise self.health_exc
        return self.health_result


def _registry(*providers: _FakeProvider) -> ProviderRegistry:
    registry = ProviderRegistry()
    for provider in providers:
        registry.register(
            provider.name,
            lambda provider=provider, **kwargs: provider,
        )
    return registry


def _settings(order: str) -> Settings:
    return Settings.model_construct(
        data_provider_order=order,
        polygon_api_key="POLYGON-SECRET-123",
        twelve_data_api_key="TWELVE-SECRET-456",
    )


def _health_report(status: str) -> health.ProviderHealthReport:
    return health.ProviderHealthReport(status=status, providers=())


def _stub_health_report(
    monkeypatch: pytest.MonkeyPatch,
    status: str,
) -> None:
    monkeypatch.setattr(
        cli_main,
        "build_provider_health_report",
        lambda provider=None: _health_report(status),
    )


def _stub_logging_health_report(
    monkeypatch: pytest.MonkeyPatch,
    status: str,
) -> None:
    monkeypatch.setattr(
        market_logging,
        "get_settings",
        lambda: Settings.model_construct(log_level="INFO"),
    )

    def _build_provider_health_report(provider: str | None = None) -> (
        health.ProviderHealthReport
    ):
        logging.getLogger("market_platform.tests.health").info(
            "provider health info log"
        )
        return _health_report(status)

    monkeypatch.setattr(
        cli_main,
        "build_provider_health_report",
        _build_provider_health_report,
    )


def test_data_providers_health_command_outputs_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    registry = _registry(
        _FakeProvider(
            name="polygon",
            health_result={"status": "ok", "message": "connected"},
        ),
        _FakeProvider(
            name="twelvedata",
            health_result=pd.DataFrame(
                [{"provider": "twelvedata", "status": "ok", "message": "connected"}]
            ),
        ),
    )
    monkeypatch.setattr(health, "create_default_registry", lambda: registry)
    settings = _settings("polygon,twelve_data")
    monkeypatch.setattr(health, "get_settings", lambda: settings)
    monkeypatch.setattr(
        cli_main,
        "create_default_market_data_service",
        lambda: (_ for _ in ()).throw(AssertionError("should not be called")),
    )

    exit_code = cli_main.run(["data", "providers", "health", "--format", "json"])
    captured = capsys.readouterr()

    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["status"] == "ok"
    assert [provider["provider"] for provider in payload["providers"]] == [
        "polygon",
        "twelvedata",
    ]
    assert all(provider["healthy"] is True for provider in payload["providers"])
    assert "Traceback" not in captured.err
    assert "POLYGON-SECRET-123" not in captured.out
    assert "TWELVE-SECRET-456" not in captured.out


def test_data_providers_health_command_outputs_clean_json_by_default(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _stub_logging_health_report(monkeypatch, "ok")

    exit_code = cli_main.run(["data", "providers", "health", "--format", "json"])
    captured = capsys.readouterr()

    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["status"] == "ok"
    assert "provider health info log" not in captured.out
    assert "provider health info log" not in captured.err


@pytest.mark.parametrize("status", ["degraded", "failed", "unknown"])
def test_data_providers_health_command_default_fail_on_never_keeps_exit_code_zero(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    status: str,
) -> None:
    _stub_health_report(monkeypatch, status)

    exit_code = cli_main.run(["data", "providers", "health"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert f"Overall status: {status}" in captured.out


@pytest.mark.parametrize(
    "argv",
    [
        ["data", "providers", "--quiet", "health", "--format", "json"],
        ["data", "providers", "health", "--quiet", "--format", "json"],
    ],
)
def test_data_providers_health_command_quiet_suppresses_info_logs(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
) -> None:
    _stub_logging_health_report(monkeypatch, "ok")

    exit_code = cli_main.run(argv)
    captured = capsys.readouterr()

    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["status"] == "ok"
    assert "provider health info log" not in captured.err
    assert "provider health info log" not in captured.out


@pytest.mark.parametrize(
    "argv",
    [
        ["data", "providers", "--log-level", "INFO", "health", "--format", "json"],
        ["data", "providers", "health", "--log-level", "INFO", "--format", "json"],
    ],
)
def test_data_providers_health_command_log_level_info_shows_info_logs(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
) -> None:
    _stub_logging_health_report(monkeypatch, "ok")

    exit_code = cli_main.run(argv)
    captured = capsys.readouterr()

    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["status"] == "ok"
    assert "provider health info log" in captured.err
    assert "provider health info log" not in captured.out


@pytest.mark.parametrize(
    "argv",
    [
        ["data", "providers", "--log-level", "ERROR", "health", "--format", "json"],
        ["data", "providers", "health", "--log-level", "ERROR", "--format", "json"],
    ],
)
def test_data_providers_health_command_log_level_error_suppresses_info_logs(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
) -> None:
    _stub_logging_health_report(monkeypatch, "ok")

    exit_code = cli_main.run(argv)
    captured = capsys.readouterr()

    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["status"] == "ok"
    assert "provider health info log" not in captured.err
    assert "provider health info log" not in captured.out


def test_data_providers_health_command_fail_on_before_health(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _stub_health_report(monkeypatch, "degraded")

    exit_code = cli_main.run(
        ["data", "providers", "--fail-on", "degraded", "health"]
    )
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "Overall status: degraded" in captured.out


def test_data_providers_health_command_fail_on_after_health(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _stub_health_report(monkeypatch, "degraded")

    exit_code = cli_main.run(
        ["data", "providers", "health", "--fail-on", "degraded"]
    )
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "Overall status: degraded" in captured.out


@pytest.mark.parametrize(
    ("fail_on", "status", "expected_exit_code"),
    [
        ("failed", "failed", 1),
        ("failed", "degraded", 0),
        ("degraded", "degraded", 1),
        ("degraded", "failed", 1),
        ("unknown", "unknown", 1),
        ("unknown", "degraded", 1),
        ("unknown", "failed", 1),
        ("unknown", "ok", 0),
    ],
)
def test_data_providers_health_command_fail_on_thresholds(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    fail_on: str,
    status: str,
    expected_exit_code: int,
) -> None:
    _stub_health_report(monkeypatch, status)

    exit_code = cli_main.run(
        ["data", "providers", "health", "--fail-on", fail_on]
    )
    capsys.readouterr()

    assert exit_code == expected_exit_code


def test_data_providers_health_command_rejects_invalid_fail_on_value(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli_main.run(["data", "providers", "health", "--fail-on", "sometimes"])

    captured = capsys.readouterr()

    assert exc_info.value.code == 2
    assert "invalid choice" in captured.err


def test_data_providers_health_command_rejects_invalid_log_level_value(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli_main.run(
            ["data", "providers", "health", "--log-level", "sometimes"]
        )

    captured = capsys.readouterr()

    assert exc_info.value.code == 2
    assert "invalid choice" in captured.err


def test_data_providers_health_command_outputs_json_when_format_precedes_health(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    registry = _registry(
        _FakeProvider(name="polygon", health_result=True),
    )
    monkeypatch.setattr(health, "create_default_registry", lambda: registry)
    settings = _settings("polygon")
    monkeypatch.setattr(health, "get_settings", lambda: settings)

    exit_code = cli_main.run(["data", "providers", "--format", "json", "health"])
    captured = capsys.readouterr()

    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["status"] == "ok"
    assert payload["providers"][0]["provider"] == "polygon"


def test_data_providers_health_command_table_includes_provider_and_status(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    registry = _registry(
        _FakeProvider(name="polygon", health_result=True),
        _FakeProvider(name="twelvedata", health_result=False),
    )
    monkeypatch.setattr(health, "create_default_registry", lambda: registry)
    settings = _settings("polygon,twelve_data")
    monkeypatch.setattr(health, "get_settings", lambda: settings)

    exit_code = cli_main.run(["data", "providers", "health"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "polygon" in captured.out
    assert "twelvedata" in captured.out
    assert "status" in captured.out
    assert "healthy" in captured.out


def test_data_providers_health_command_writes_file_with_output_after_health(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    registry = _registry(
        _FakeProvider(name="polygon", health_result=True),
    )
    monkeypatch.setattr(health, "create_default_registry", lambda: registry)
    settings = _settings("polygon")
    monkeypatch.setattr(health, "get_settings", lambda: settings)

    output_root = Path(".test-cli-health-output")
    output_path = output_root / "nested" / "reports" / "health.json"

    try:
        exit_code = cli_main.run(
            [
                "data",
                "providers",
                "health",
                "--format",
                "json",
                "--output",
                str(output_path),
            ]
        )
        captured = capsys.readouterr()

        assert exit_code == 0
        assert output_path.exists()
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        assert payload["status"] == "ok"
        assert "Wrote provider health report" in captured.out
    finally:
        shutil.rmtree(output_root, ignore_errors=True)


def test_data_providers_health_command_writes_file_with_output_before_health(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    registry = _registry(
        _FakeProvider(name="polygon", health_result=True),
    )
    monkeypatch.setattr(health, "create_default_registry", lambda: registry)
    settings = _settings("polygon")
    monkeypatch.setattr(health, "get_settings", lambda: settings)

    output_root = Path(".test-cli-health-output")
    output_path = output_root / "nested" / "reports" / "health.json"

    try:
        exit_code = cli_main.run(
            [
                "data",
                "providers",
                "--output",
                str(output_path),
                "--format",
                "json",
                "health",
            ]
        )
        captured = capsys.readouterr()

        assert exit_code == 0
        assert output_path.exists()
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        assert payload["status"] == "ok"
        assert "Wrote provider health report" in captured.out
    finally:
        shutil.rmtree(output_root, ignore_errors=True)


def test_data_providers_health_command_writes_clean_json_file_with_logs(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _stub_logging_health_report(monkeypatch, "ok")

    output_root = Path(".test-cli-health-output")
    output_path = output_root / "nested" / "reports" / "health-clean.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "market-platform",
            "data",
            "providers",
            "--output",
            str(output_path),
            "--format",
            "json",
            "--log-level",
            "INFO",
            "health",
        ],
    )

    try:
        exit_code = cli_main.run()
        captured = capsys.readouterr()

        assert exit_code == 0
        assert output_path.exists()
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        assert payload["status"] == "ok"
        assert "Wrote provider health report" in captured.out
        assert "provider health info log" not in captured.out
        assert "provider health info log" in captured.err
    finally:
        shutil.rmtree(output_root, ignore_errors=True)


def test_data_providers_health_command_writes_file_with_real_cli_argv(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _stub_health_report(monkeypatch, "degraded")

    output_root = Path(".test-cli-health-output")
    output_path = output_root / "nested" / "reports" / "health-parent.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "market-platform",
            "data",
            "providers",
            "--output",
            str(output_path),
            "--format",
            "json",
            "--fail-on",
            "degraded",
            "health",
        ],
    )

    try:
        exit_code = cli_main.run()
        captured = capsys.readouterr()

        assert exit_code == 1
        assert output_path.exists()
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        assert payload["status"] == "degraded"
        assert "Wrote provider health report" in captured.out
        assert "{\"status\":" not in captured.out
    finally:
        shutil.rmtree(output_root, ignore_errors=True)


def test_data_providers_health_command_explicit_provider_only_checks_one(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[str] = []
    registry = _registry(
        _FakeProvider(name="polygon", health_result=True, calls=calls),
        _FakeProvider(name="twelvedata", health_result=True, calls=calls),
    )
    monkeypatch.setattr(health, "create_default_registry", lambda: registry)
    settings = _settings("")
    monkeypatch.setattr(health, "get_settings", lambda: settings)

    exit_code = cli_main.run(
        ["data", "providers", "health", "--provider", "twelve_data"]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert calls == ["twelvedata"]
    assert "twelvedata" in captured.out
    assert "polygon" not in captured.out


def test_data_providers_health_command_captures_exceptions_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    registry = _registry(
        _FakeProvider(
            name="polygon",
            health_result=True,
            health_exc=RuntimeError("boom"),
        ),
    )
    monkeypatch.setattr(health, "create_default_registry", lambda: registry)
    settings = _settings("polygon")
    monkeypatch.setattr(health, "get_settings", lambda: settings)

    exit_code = cli_main.run(
        ["data", "providers", "health", "--provider", "polygon"]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "RuntimeError" in captured.out
    assert "boom" in captured.out
    assert "Traceback" not in captured.out
    assert "Traceback" not in captured.err


def test_data_providers_health_command_unknown_provider_fails_cleanly(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    registry = _registry()
    monkeypatch.setattr(health, "create_default_registry", lambda: registry)
    settings = _settings("")
    monkeypatch.setattr(health, "get_settings", lambda: settings)

    exit_code = cli_main.run(
        ["data", "providers", "health", "--provider", "unknown"]
    )
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "Unknown provider" in captured.err
    assert "Traceback" not in captured.err
