import pytest

from market_platform.config import Settings


def test_settings_defaults() -> None:
    settings = Settings()

    assert settings.environment == "dev"
    assert settings.default_data_provider == "polygon"
    assert settings.data_provider_order == ""


def test_settings_loads_provider_order_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "MARKET_PLATFORM_DATA_PROVIDER_ORDER",
        "polygon,twelve_data",
    )

    settings = Settings()

    assert settings.data_provider_order == "polygon,twelve_data"
