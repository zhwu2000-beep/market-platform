from market_platform.config import Settings


def test_settings_defaults() -> None:
    settings = Settings()

    assert settings.environment == "dev"
    assert settings.default_data_provider == "polygon"
