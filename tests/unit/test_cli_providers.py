from __future__ import annotations

import json

import pytest

from market_platform.cli import main as cli_main
from market_platform.config import Settings
from market_platform.data import diagnostics


def test_data_providers_command_outputs_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = Settings.model_construct(
        data_provider_order="polygon,twelve_data",
        polygon_api_key="POLYGON-SECRET-123",
        twelve_data_api_key="",
    )
    monkeypatch.setattr(diagnostics, "get_settings", lambda: settings)
    monkeypatch.setattr(
        cli_main,
        "create_default_market_data_service",
        lambda: (_ for _ in ()).throw(AssertionError("should not be called")),
    )

    exit_code = cli_main.run(["data", "providers"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "polygon" in captured.out
    assert "twelvedata" in captured.out
    assert "configured: yes" in captured.out
    assert "configured: no" in captured.out
    assert "daily_prices" in captured.out
    assert "health_check" in captured.out
    assert "POLYGON-SECRET-123" not in captured.out


def test_data_providers_command_outputs_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = Settings.model_construct(
        data_provider_order="polygon,twelve_data",
        polygon_api_key="POLYGON-SECRET-123",
        twelve_data_api_key="",
    )
    monkeypatch.setattr(diagnostics, "get_settings", lambda: settings)

    exit_code = cli_main.run(["data", "providers", "--format", "json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["configured_provider_order"] == ["polygon", "twelvedata"]
    assert payload["known_provider_names"] == ["polygon", "twelvedata"]
    assert "POLYGON-SECRET-123" not in captured.out
