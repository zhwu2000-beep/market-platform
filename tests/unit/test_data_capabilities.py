from __future__ import annotations

import pytest

from market_platform.data.capabilities import (
    DataCapability,
    get_provider_capabilities,
)
from market_platform.data.exceptions import ConfigurationError


def test_polygon_reports_supported_capabilities() -> None:
    capabilities = get_provider_capabilities("polygon")

    assert DataCapability.DAILY_PRICES in capabilities
    assert DataCapability.INTRADAY_PRICES not in capabilities
    assert DataCapability.LATEST_PRICE in capabilities
    assert DataCapability.HEALTH_CHECK in capabilities


def test_twelve_data_reports_only_implemented_capabilities() -> None:
    capabilities = get_provider_capabilities("twelvedata")

    assert DataCapability.DAILY_PRICES in capabilities
    assert DataCapability.INTRADAY_PRICES in capabilities
    assert DataCapability.LATEST_PRICE in capabilities
    assert DataCapability.HEALTH_CHECK in capabilities


def test_unknown_provider_capabilities_raise_configuration_error() -> None:
    with pytest.raises(ConfigurationError, match="Unknown provider"):
        get_provider_capabilities("missing")
