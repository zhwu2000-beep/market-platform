from __future__ import annotations

import pytest

from market_platform.config import Settings
from market_platform.data import diagnostics


def test_build_provider_diagnostics_report_uses_settings_without_leaking_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings.model_construct(
        data_provider_order="polygon, twelve_data",
        polygon_api_key="POLYGON-SECRET-123",
        twelve_data_api_key="",
    )
    monkeypatch.setattr(diagnostics, "get_settings", lambda: settings)

    report = diagnostics.build_provider_diagnostics_report()
    rendered = diagnostics.render_provider_diagnostics_report(report)

    assert report.configured_provider_order == ("polygon", "twelvedata")
    assert report.known_provider_names == ("polygon", "twelvedata")
    assert report.providers[0].name == "polygon"
    assert report.providers[0].configured is True
    assert report.providers[1].name == "twelvedata"
    assert report.providers[1].configured is False
    assert "daily_prices" in rendered
    assert "health_check" in rendered
    assert "POLYGON-SECRET-123" not in rendered
    assert "configured: yes" in rendered
    assert "configured: no" in rendered
