import pytest

from market_platform.data.providers.twelve_data import TwelveDataProvider


@pytest.mark.integration
def test_twelve_data_provider_name() -> None:
    provider = TwelveDataProvider()

    assert provider.name == "twelve_data"
