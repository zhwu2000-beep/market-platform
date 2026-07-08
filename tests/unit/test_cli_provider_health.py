from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest

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


def test_data_providers_health_command_writes_file_and_creates_parent_dirs(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    registry = _registry(
        _FakeProvider(name="polygon", health_result=True),
    )
    monkeypatch.setattr(health, "create_default_registry", lambda: registry)
    monkeypatch.setattr(health, "get_settings", lambda: _settings("polygon"))

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
