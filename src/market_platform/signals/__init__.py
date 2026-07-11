"""Market signal calculation package."""

from market_platform.signals.batch import (
    SignalClassificationSnapshot,
    classify_composite_signals,
)
from market_platform.signals.calculators import (
    calculate_current_drawdown,
    calculate_distance_from_moving_average,
    calculate_momentum,
    calculate_realized_volatility,
    calculate_trend,
)
from market_platform.signals.classification import (
    SignalClassification,
    SignalClassificationLevel,
    SignalClassificationThresholds,
    classify_composite_signal,
)
from market_platform.signals.composite import calculate_composite_signal
from market_platform.signals.models import MarketSignal, MarketSignalSnapshot
from market_platform.signals.relative_strength import (
    align_asset_and_benchmark_prices,
    calculate_relative_strength,
)
from market_platform.signals.service import calculate_market_signals

__all__ = [
    "SignalClassification",
    "SignalClassificationLevel",
    "SignalClassificationThresholds",
    "SignalClassificationSnapshot",
    "align_asset_and_benchmark_prices",
    "MarketSignal",
    "MarketSignalSnapshot",
    "calculate_composite_signal",
    "calculate_current_drawdown",
    "calculate_distance_from_moving_average",
    "calculate_market_signals",
    "calculate_momentum",
    "calculate_relative_strength",
    "calculate_realized_volatility",
    "calculate_trend",
    "classify_composite_signal",
    "classify_composite_signals",
]
