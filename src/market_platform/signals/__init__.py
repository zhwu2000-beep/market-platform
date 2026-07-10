"""Market signal calculation package."""

from market_platform.signals.calculators import (
    calculate_current_drawdown,
    calculate_distance_from_moving_average,
    calculate_momentum,
    calculate_realized_volatility,
    calculate_trend,
)
from market_platform.signals.models import MarketSignal, MarketSignalSnapshot
from market_platform.signals.relative_strength import (
    align_asset_and_benchmark_prices,
    calculate_relative_strength,
)
from market_platform.signals.service import calculate_market_signals

__all__ = [
    "align_asset_and_benchmark_prices",
    "MarketSignal",
    "MarketSignalSnapshot",
    "calculate_current_drawdown",
    "calculate_distance_from_moving_average",
    "calculate_market_signals",
    "calculate_momentum",
    "calculate_relative_strength",
    "calculate_realized_volatility",
    "calculate_trend",
]
