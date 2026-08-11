"""Deterministic provider-independent daily technical analysis."""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from numbers import Real
from typing import cast

from market_platform._fingerprint import canonical_fingerprint, canonical_float
from market_platform.indicators import (
    calculate_atr_percent,
    calculate_ema,
    calculate_macd,
    calculate_rsi,
    calculate_wilder_atr,
)
from market_platform.research.daily_evidence import (
    CompletedDailyPriceSeries,
    DailyResearchEvidence,
    _copy_daily_research_evidence,
)
from market_platform.research.interpretation import (
    VolatilityState,
    interpret_realized_volatility,
)
from market_platform.signals.calculators import (
    calculate_current_drawdown,
    calculate_realized_volatility,
)
from market_platform.signals.models import MarketSignal

DAILY_TECHNICAL_ANALYSIS_PROFILE_SCHEMA = "daily_technical_analysis_profile/v1"
TECHNICAL_ANALYSIS_SNAPSHOT_SCHEMA = "technical_analysis_snapshot/v1"
_PROFILE_SEAL = object()
_SNAPSHOT_SEAL = object()
_FINGERPRINT_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


class TechnicalAnalysisQuality(StrEnum):
    COMPLETE = "complete"
    DEGRADED = "degraded"


class TechnicalTrendState(StrEnum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    MIXED = "mixed"
    UNAVAILABLE = "unavailable"


class TechnicalMomentumState(StrEnum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    MIXED = "mixed"
    UNAVAILABLE = "unavailable"


class EmaAlignment(StrEnum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    MIXED = "mixed"
    UNAVAILABLE = "unavailable"


class TunnelPosition(StrEnum):
    ABOVE = "above"
    INSIDE = "inside"
    BELOW = "below"
    UNAVAILABLE = "unavailable"


class TechnicalAnalysisComponent(StrEnum):
    EMA_8 = "ema_8"
    EMA_20 = "ema_20"
    EMA_144 = "ema_144"
    EMA_169 = "ema_169"
    MACD = "macd"
    RSI_14 = "rsi_14"
    WILDER_ATR_14 = "wilder_atr_14"
    ATR_PERCENT_14 = "atr_percent_14"
    REALIZED_VOLATILITY = "realized_volatility"
    DISTANCE_FROM_EMA20 = "distance_from_ema20"


class TechnicalAnalysisUnavailableReason(StrEnum):
    INSUFFICIENT_HISTORY = "insufficient_history"


class TechnicalAnalysisWarning(StrEnum):
    INSUFFICIENT_PROFILE_HISTORY = "insufficient_profile_history"
    STALE_EVIDENCE = "stale_evidence"


_PROFILE_VALUES = {
    "profile_id": "daily_technical_analysis_default",
    "profile_version": "1.0.0",
    "ema_fast_period": 8,
    "ema_slow_period": 20,
    "tunnel_fast_period": 144,
    "tunnel_slow_period": 169,
    "macd_fast_period": 12,
    "macd_slow_period": 26,
    "macd_signal_period": 9,
    "rsi_period": 14,
    "atr_period": 14,
    "minimum_bar_count": 250,
    "stale_after_calendar_days": 7,
    "realized_volatility_low_threshold": 0.15,
    "realized_volatility_high_threshold": 0.30,
    "rules_version": "daily_technical_analysis_rules/v1",
}


@dataclass(frozen=True, slots=True, init=False)
class DailyTechnicalAnalysisProfile:
    profile_id: str
    profile_version: str
    ema_fast_period: int
    ema_slow_period: int
    tunnel_fast_period: int
    tunnel_slow_period: int
    macd_fast_period: int
    macd_slow_period: int
    macd_signal_period: int
    rsi_period: int
    atr_period: int
    minimum_bar_count: int
    stale_after_calendar_days: int
    realized_volatility_low_threshold: float
    realized_volatility_high_threshold: float
    rules_version: str
    schema_version: str
    fingerprint: str

    def __init__(self) -> None:
        raise TypeError("DailyTechnicalAnalysisProfile is factory-owned")

    @classmethod
    def _create(cls, seal: object) -> DailyTechnicalAnalysisProfile:
        if seal is not _PROFILE_SEAL:
            raise TypeError("daily technical profile construction is private")
        result = object.__new__(cls)
        for name, value in _PROFILE_VALUES.items():
            object.__setattr__(result, name, value)
        object.__setattr__(
            result, "schema_version", DAILY_TECHNICAL_ANALYSIS_PROFILE_SCHEMA
        )
        object.__setattr__(
            result, "fingerprint", canonical_fingerprint(result._fingerprint_payload())
        )
        result._validate()
        return result

    def _projection(self, fingerprint_floats: bool = False) -> dict[str, object]:
        result: dict[str, object] = {"schema_version": self.schema_version}
        for name in _PROFILE_VALUES:
            value = getattr(self, name)
            if fingerprint_floats and type(value) is float:
                value = canonical_float(value)
            result[name] = value
        return result

    def _fingerprint_payload(self) -> dict[str, object]:
        return self._projection(True)

    def _validate(self) -> None:
        values = _retained(
            self, (*_PROFILE_VALUES, "schema_version", "fingerprint"), "profile"
        )
        for name, expected in _PROFILE_VALUES.items():
            if type(values[name]) is not type(expected) or values[name] != expected:
                raise ValueError("profile must match the exact fixed v1 configuration")
        if (
            type(values["schema_version"]) is not str
            or values["schema_version"] != DAILY_TECHNICAL_ANALYSIS_PROFILE_SCHEMA
        ):
            raise ValueError("profile schema is invalid")
        fingerprint = _canonical_fingerprint_string(
            values["fingerprint"], "profile fingerprint"
        )
        if fingerprint != canonical_fingerprint(self._fingerprint_payload()):
            raise ValueError("profile fingerprint does not match content")

    def to_dict(self) -> dict[str, object]:
        self._validate()
        return {**self._projection(), "fingerprint": self.fingerprint}


def construct_daily_technical_analysis_profile() -> DailyTechnicalAnalysisProfile:
    return DailyTechnicalAnalysisProfile._create(_PROFILE_SEAL)


@dataclass(frozen=True, slots=True)
class TechnicalAnalysisUnavailable:
    component: TechnicalAnalysisComponent
    reason: TechnicalAnalysisUnavailableReason
    required_bars: int
    available_bars: int

    def __post_init__(self) -> None:
        if type(self.component) is not TechnicalAnalysisComponent:
            raise TypeError("component must be an exact TechnicalAnalysisComponent")
        if type(self.reason) is not TechnicalAnalysisUnavailableReason:
            raise TypeError("reason must be an exact unavailable reason")
        if type(self.required_bars) is not int or type(self.available_bars) is not int:
            raise TypeError("bar counts must be exact ints")
        if self.required_bars <= 0 or not 0 <= self.available_bars < self.required_bars:
            raise ValueError("unavailable bar counts are invalid")

    def _validate(self) -> None:
        try:
            TechnicalAnalysisUnavailable(
                self.component, self.reason, self.required_bars, self.available_bars
            )
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError("retained unavailable value is invalid") from exc

    def to_dict(self) -> dict[str, object]:
        self._validate()
        return {
            "component": self.component.value,
            "reason": self.reason.value,
            "required_bars": self.required_bars,
            "available_bars": self.available_bars,
        }


_REFERENCE_FIELDS = (
    "atr",
    "one_atr_below",
    "one_atr_above",
    "one_and_half_atr_below",
    "one_and_half_atr_above",
    "two_atr_below",
    "two_atr_above",
    "distance_from_ema20_percent",
)


@dataclass(frozen=True, slots=True)
class ResearchVolatilityReferences:
    atr: float | None
    one_atr_below: float | None
    one_atr_above: float | None
    one_and_half_atr_below: float | None
    one_and_half_atr_above: float | None
    two_atr_below: float | None
    two_atr_above: float | None
    distance_from_ema20_percent: float | None

    def __post_init__(self) -> None:
        for name in _REFERENCE_FIELDS:
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _number(value, name))
        price_references = tuple(getattr(self, name) for name in _REFERENCE_FIELDS[1:7])
        if self.atr is None and any(value is not None for value in price_references):
            raise ValueError("ATR references must be None without ATR")
        if self.atr is not None and any(value is None for value in price_references):
            raise ValueError("ATR references must all exist with ATR")
        if self.atr is not None and self.atr < 0.0:
            raise ValueError("ATR must not be negative")

    def _validate(self) -> None:
        retained = _retained(
            self, _REFERENCE_FIELDS, "volatility references"
        )
        for name in _REFERENCE_FIELDS:
            _canonical_retained_float(retained[name], name, optional=True)
        reference_values = cast(dict[str, float | None], retained)
        try:
            rebuilt = ResearchVolatilityReferences(
                **reference_values
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("retained volatility references are invalid") from exc
        if any(
            type(retained[name]) is not type(getattr(rebuilt, name))
            or retained[name] != getattr(rebuilt, name)
            for name in _REFERENCE_FIELDS
        ):
            raise ValueError("retained volatility references are noncanonical")

    def to_dict(self, fingerprint_floats: bool = False) -> dict[str, object]:
        self._validate()
        return {
            name: _project_float(getattr(self, name), fingerprint_floats)
            for name in _REFERENCE_FIELDS
        }


_SNAPSHOT_FIELDS = (
    "evidence",
    "profile",
    "latest_close",
    "ema_8",
    "ema_20",
    "ema_144",
    "ema_169",
    "ema_alignment",
    "tunnel_position",
    "macd_line",
    "macd_signal",
    "macd_histogram",
    "rsi_14",
    "wilder_atr_14",
    "atr_percent_14",
    "realized_volatility",
    "current_drawdown",
    "trend_state",
    "momentum_state",
    "volatility_state",
    "volatility_references",
    "quality",
    "unavailable",
    "warnings",
)
_FLOAT_FIELDS = (
    "latest_close",
    "ema_8",
    "ema_20",
    "ema_144",
    "ema_169",
    "macd_line",
    "macd_signal",
    "macd_histogram",
    "rsi_14",
    "wilder_atr_14",
    "atr_percent_14",
    "realized_volatility",
    "current_drawdown",
)


@dataclass(frozen=True, slots=True, init=False)
class TechnicalAnalysisSnapshot:
    evidence: DailyResearchEvidence
    profile: DailyTechnicalAnalysisProfile
    latest_close: float
    ema_8: float | None
    ema_20: float | None
    ema_144: float | None
    ema_169: float | None
    ema_alignment: EmaAlignment
    tunnel_position: TunnelPosition
    macd_line: float | None
    macd_signal: float | None
    macd_histogram: float | None
    rsi_14: float | None
    wilder_atr_14: float | None
    atr_percent_14: float | None
    realized_volatility: float | None
    current_drawdown: float
    trend_state: TechnicalTrendState
    momentum_state: TechnicalMomentumState
    volatility_state: VolatilityState
    volatility_references: ResearchVolatilityReferences
    quality: TechnicalAnalysisQuality
    unavailable: tuple[TechnicalAnalysisUnavailable, ...]
    warnings: tuple[TechnicalAnalysisWarning, ...]
    schema_version: str
    fingerprint: str

    def __init__(self) -> None:
        raise TypeError("TechnicalAnalysisSnapshot is analyzer-owned")

    @classmethod
    def _create(cls, *, seal: object, **values: object) -> TechnicalAnalysisSnapshot:
        if seal is not _SNAPSHOT_SEAL:
            raise TypeError("snapshot construction is private")
        result = object.__new__(cls)
        for name in _SNAPSHOT_FIELDS:
            object.__setattr__(result, name, values[name])
        object.__setattr__(
            result, "evidence", _copy_daily_research_evidence(result.evidence)
        )
        object.__setattr__(
            result, "profile", construct_daily_technical_analysis_profile()
        )
        object.__setattr__(result, "schema_version", TECHNICAL_ANALYSIS_SNAPSHOT_SCHEMA)
        object.__setattr__(
            result, "fingerprint", canonical_fingerprint(result._fingerprint_payload())
        )
        result._validate()
        return result

    def _projection(self, fingerprint_floats: bool = False) -> dict[str, object]:
        result: dict[str, object] = {
            "schema_version": self.schema_version,
            "evidence": self.evidence.to_dict(),
            "profile": {
                **self.profile._projection(fingerprint_floats),
                "fingerprint": self.profile.fingerprint,
            },
        }
        for name in _SNAPSHOT_FIELDS[2:]:
            value = getattr(self, name)
            if name in _FLOAT_FIELDS:
                value = _project_float(value, fingerprint_floats)
            elif isinstance(value, StrEnum):
                value = value.value
            elif name == "volatility_references":
                value = self.volatility_references.to_dict(fingerprint_floats)
            elif name == "unavailable":
                value = [item.to_dict() for item in self.unavailable]
            elif name == "warnings":
                value = [item.value for item in self.warnings]
            result[name] = value
        return result

    def _fingerprint_payload(self) -> dict[str, object]:
        return self._projection(True)

    def _validate(self) -> None:
        values = _retained(
            self, (*_SNAPSHOT_FIELDS, "schema_version", "fingerprint"), "snapshot"
        )
        if type(values["evidence"]) is not DailyResearchEvidence:
            raise ValueError("snapshot evidence is invalid")
        self.evidence._validate()
        if type(values["profile"]) is not DailyTechnicalAnalysisProfile:
            raise ValueError("snapshot profile is invalid")
        self.profile._validate()
        for name in _FLOAT_FIELDS:
            optional = name not in ("latest_close", "current_drawdown")
            _canonical_retained_float(values[name], name, optional)
        if (
            self.latest_close <= 0.0
            or self.current_drawdown <= -1.0
            or self.current_drawdown > 0.0
        ):
            raise ValueError("snapshot close or drawdown is invalid")
        if self.rsi_14 is not None and not 0.0 <= self.rsi_14 <= 100.0:
            raise ValueError("snapshot RSI is invalid")
        enum_fields = {
            "ema_alignment": EmaAlignment,
            "tunnel_position": TunnelPosition,
            "trend_state": TechnicalTrendState,
            "momentum_state": TechnicalMomentumState,
            "volatility_state": VolatilityState,
            "quality": TechnicalAnalysisQuality,
        }
        if any(type(values[name]) is not kind for name, kind in enum_fields.items()):
            raise ValueError("snapshot state value is invalid")
        self._validate_collections()
        self._validate_semantics()
        if (
            type(values["schema_version"]) is not str
            or values["schema_version"] != TECHNICAL_ANALYSIS_SNAPSHOT_SCHEMA
        ):
            raise ValueError("snapshot schema is invalid")
        fingerprint = _canonical_fingerprint_string(
            values["fingerprint"], "snapshot fingerprint"
        )
        if fingerprint != canonical_fingerprint(self._fingerprint_payload()):
            raise ValueError("snapshot fingerprint does not match content")

    def _validate_collections(self) -> None:
        if type(self.unavailable) is not tuple:
            raise ValueError("snapshot unavailable must be a tuple")
        for item in self.unavailable:
            if type(item) is not TechnicalAnalysisUnavailable:
                raise ValueError("snapshot unavailable entry is invalid")
            item._validate()
        components = [item.component for item in self.unavailable]
        order = {value: index for index, value in enumerate(TechnicalAnalysisComponent)}
        if len(set(components)) != len(components) or components != sorted(
            components, key=order.__getitem__
        ):
            raise ValueError("snapshot unavailable entries are invalid")
        if type(self.warnings) is not tuple or any(
            type(item) is not TechnicalAnalysisWarning for item in self.warnings
        ):
            raise ValueError("snapshot warnings are invalid")
        warning_order = {
            value: index for index, value in enumerate(TechnicalAnalysisWarning)
        }
        if len(set(self.warnings)) != len(self.warnings) or list(
            self.warnings
        ) != sorted(self.warnings, key=warning_order.__getitem__):
            raise ValueError("snapshot warnings are duplicated or out of order")

    def _validate_semantics(self) -> None:
        alignment = _ema_alignment(self.ema_8, self.ema_20, self.ema_144, self.ema_169)
        macd_values = (self.macd_line, self.macd_signal, self.macd_histogram)
        if self.macd_line is None and any(
            value is not None for value in macd_values[1:]
        ):
            raise ValueError("snapshot MACD values are inconsistent")
        if (self.macd_signal is None) != (self.macd_histogram is None):
            raise ValueError("snapshot MACD values are inconsistent")
        if all(value is not None for value in macd_values):
            assert self.macd_line is not None
            assert self.macd_signal is not None
            expected_histogram = _number(
                self.macd_line - self.macd_signal, "macd_histogram"
            )
            if self.macd_histogram != expected_histogram:
                raise ValueError("snapshot MACD histogram is inconsistent")
        if self.wilder_atr_14 is None:
            if self.atr_percent_14 is not None:
                raise ValueError("snapshot ATR percent is inconsistent")
        else:
            expected_atr_percent = _number(
                100.0 * self.wilder_atr_14 / self.latest_close,
                "atr_percent_14",
            )
            if self.atr_percent_14 != expected_atr_percent:
                raise ValueError("snapshot ATR percent is inconsistent")
        tunnel = _tunnel_position(self.latest_close, self.ema_144, self.ema_169)
        if self.ema_alignment is not alignment or self.tunnel_position is not tunnel:
            raise ValueError("snapshot trend inputs are inconsistent")
        if self.trend_state is not _trend_state(alignment, tunnel):
            raise ValueError("snapshot trend state is inconsistent")
        if self.momentum_state is not _momentum_state(
            self.macd_line, self.macd_signal, self.macd_histogram, self.rsi_14
        ):
            raise ValueError("snapshot momentum state is inconsistent")
        if self.volatility_state is not _volatility_state(
            self.realized_volatility,
            self.profile.realized_volatility_low_threshold,
            self.profile.realized_volatility_high_threshold,
        ):
            raise ValueError("snapshot volatility state is inconsistent")
        if type(self.volatility_references) is not ResearchVolatilityReferences:
            raise ValueError("snapshot volatility references are invalid")
        expected_references = _references(
            self.latest_close, self.wilder_atr_14, self.ema_20
        )
        self.volatility_references._validate()
        if self.volatility_references != expected_references:
            raise ValueError("snapshot volatility reference arithmetic is invalid")
        unavailable = _unavailable(
            bar_count=self.evidence.bar_count,
            ema_8=self.ema_8,
            ema_20=self.ema_20,
            ema_144=self.ema_144,
            ema_169=self.ema_169,
            macd_line=self.macd_line,
            macd_signal=self.macd_signal,
            macd_histogram=self.macd_histogram,
            rsi_14=self.rsi_14,
            wilder_atr_14=self.wilder_atr_14,
            atr_percent_14=self.atr_percent_14,
            realized_volatility=self.realized_volatility,
        )
        if self.unavailable != unavailable:
            raise ValueError("snapshot unavailable entries are inconsistent")
        quality = (
            TechnicalAnalysisQuality.COMPLETE
            if self.evidence.bar_count >= self.profile.minimum_bar_count
            and not unavailable
            else TechnicalAnalysisQuality.DEGRADED
        )
        if self.quality is not quality:
            raise ValueError("snapshot quality is inconsistent")
        if self.warnings != _warnings(self.evidence, self.profile):
            raise ValueError("snapshot warnings are inconsistent")

    def to_dict(self) -> dict[str, object]:
        self._validate()
        return {**self._projection(), "fingerprint": self.fingerprint}


def analyze_daily_technical_snapshot(
    *,
    completed_prices: CompletedDailyPriceSeries,
    profile: DailyTechnicalAnalysisProfile,
) -> TechnicalAnalysisSnapshot:
    if type(completed_prices) is not CompletedDailyPriceSeries:
        raise TypeError("completed_prices must be exact CompletedDailyPriceSeries")
    if type(profile) is not DailyTechnicalAnalysisProfile:
        raise TypeError("profile must be exact DailyTechnicalAnalysisProfile")
    prices = completed_prices._validated_prices()
    evidence = completed_prices.evidence
    profile._validate()
    rows = tuple(prices.full_prefix().iter_rows())
    highs = tuple(row[3] for row in rows)
    lows = tuple(row[4] for row in rows)
    closes = tuple(row[5] for row in rows)
    numeric_highs = cast(Sequence[Real], highs)
    numeric_lows = cast(Sequence[Real], lows)
    numeric_closes = cast(Sequence[Real], closes)
    ema_8 = calculate_ema(numeric_closes, period=profile.ema_fast_period)[-1]
    ema_20 = calculate_ema(numeric_closes, period=profile.ema_slow_period)[-1]
    ema_144 = calculate_ema(numeric_closes, period=profile.tunnel_fast_period)[-1]
    ema_169 = calculate_ema(numeric_closes, period=profile.tunnel_slow_period)[-1]
    macd = calculate_macd(
        numeric_closes,
        fast_period=profile.macd_fast_period,
        slow_period=profile.macd_slow_period,
        signal_period=profile.macd_signal_period,
    )
    rsi_14 = calculate_rsi(numeric_closes, period=profile.rsi_period)[-1]
    atr_values = calculate_wilder_atr(
        numeric_highs, numeric_lows, numeric_closes, period=profile.atr_period
    )
    wilder_atr_14 = atr_values[-1]
    atr_percent_14 = calculate_atr_percent(
        cast(Sequence[Real | None], atr_values), numeric_closes
    )[-1]
    frame = prices.to_dataframe()
    realized_raw = calculate_realized_volatility(frame, window=20)
    realized = (
        None if realized_raw is None else _number(realized_raw, "realized_volatility")
    )
    drawdown = _number(calculate_current_drawdown(frame), "current_drawdown")
    alignment = _ema_alignment(ema_8, ema_20, ema_144, ema_169)
    tunnel = _tunnel_position(closes[-1], ema_144, ema_169)
    volatility = interpret_realized_volatility(
        MarketSignal(
            symbol=evidence.instrument.symbol,
            name="realized_volatility",
            value=realized,
            timestamp=rows[-1][1],
            parameters={},
        ),
        low_threshold=profile.realized_volatility_low_threshold,
        high_threshold=profile.realized_volatility_high_threshold,
    ).state
    values: dict[str, object] = {
        "evidence": evidence,
        "profile": profile,
        "latest_close": closes[-1],
        "ema_8": ema_8,
        "ema_20": ema_20,
        "ema_144": ema_144,
        "ema_169": ema_169,
        "ema_alignment": alignment,
        "tunnel_position": tunnel,
        "macd_line": macd.macd[-1],
        "macd_signal": macd.signal[-1],
        "macd_histogram": macd.histogram[-1],
        "rsi_14": rsi_14,
        "wilder_atr_14": wilder_atr_14,
        "atr_percent_14": atr_percent_14,
        "realized_volatility": realized,
        "current_drawdown": drawdown,
        "trend_state": _trend_state(alignment, tunnel),
        "momentum_state": _momentum_state(
            macd.macd[-1], macd.signal[-1], macd.histogram[-1], rsi_14
        ),
        "volatility_state": volatility,
        "volatility_references": _references(closes[-1], wilder_atr_14, ema_20),
    }
    unavailable = _unavailable(
        bar_count=evidence.bar_count,
        ema_8=ema_8,
        ema_20=ema_20,
        ema_144=ema_144,
        ema_169=ema_169,
        macd_line=macd.macd[-1],
        macd_signal=macd.signal[-1],
        macd_histogram=macd.histogram[-1],
        rsi_14=rsi_14,
        wilder_atr_14=wilder_atr_14,
        atr_percent_14=atr_percent_14,
        realized_volatility=realized,
    )
    values["unavailable"] = unavailable
    values["quality"] = (
        TechnicalAnalysisQuality.COMPLETE
        if evidence.bar_count >= profile.minimum_bar_count and not unavailable
        else TechnicalAnalysisQuality.DEGRADED
    )
    values["warnings"] = _warnings(evidence, profile)
    return TechnicalAnalysisSnapshot._create(seal=_SNAPSHOT_SEAL, **values)




def _ema_alignment(
    ema_8: float | None,
    ema_20: float | None,
    ema_144: float | None,
    ema_169: float | None,
) -> EmaAlignment:
    if any(value is None for value in (ema_8, ema_20, ema_144, ema_169)):
        return EmaAlignment.UNAVAILABLE
    assert all(value is not None for value in (ema_8, ema_20, ema_144, ema_169))
    if ema_8 > ema_20 > ema_144 > ema_169:  # type: ignore[operator]
        return EmaAlignment.BULLISH
    if ema_8 < ema_20 < ema_144 < ema_169:  # type: ignore[operator]
        return EmaAlignment.BEARISH
    return EmaAlignment.MIXED


def _tunnel_position(
    close: float, ema_144: float | None, ema_169: float | None
) -> TunnelPosition:
    if ema_144 is None or ema_169 is None:
        return TunnelPosition.UNAVAILABLE
    if close > max(ema_144, ema_169):
        return TunnelPosition.ABOVE
    if close < min(ema_144, ema_169):
        return TunnelPosition.BELOW
    return TunnelPosition.INSIDE


def _trend_state(
    alignment: EmaAlignment, tunnel: TunnelPosition
) -> TechnicalTrendState:
    if alignment is EmaAlignment.UNAVAILABLE or tunnel is TunnelPosition.UNAVAILABLE:
        return TechnicalTrendState.UNAVAILABLE
    if alignment is EmaAlignment.BULLISH and tunnel is TunnelPosition.ABOVE:
        return TechnicalTrendState.BULLISH
    if alignment is EmaAlignment.BEARISH and tunnel is TunnelPosition.BELOW:
        return TechnicalTrendState.BEARISH
    return TechnicalTrendState.MIXED


def _momentum_state(
    line: float | None,
    signal: float | None,
    histogram: float | None,
    rsi: float | None,
) -> TechnicalMomentumState:
    if any(value is None for value in (line, signal, histogram, rsi)):
        return TechnicalMomentumState.UNAVAILABLE
    assert line is not None and signal is not None
    assert histogram is not None and rsi is not None
    if line > signal and histogram > 0.0 and rsi >= 50.0:
        return TechnicalMomentumState.BULLISH
    if line < signal and histogram < 0.0 and rsi < 50.0:
        return TechnicalMomentumState.BEARISH
    return TechnicalMomentumState.MIXED


def _volatility_state(value: float | None, low: float, high: float) -> VolatilityState:
    if value is None:
        return VolatilityState.UNAVAILABLE
    if value < low:
        return VolatilityState.LOW
    if value < high:
        return VolatilityState.NORMAL
    return VolatilityState.HIGH


def _references(
    close: float, atr: float | None, ema_20: float | None
) -> ResearchVolatilityReferences:
    distance = (
        None
        if ema_20 is None
        else _number(100.0 * (close / ema_20 - 1.0), "distance_from_ema20_percent")
    )
    if atr is None:
        return ResearchVolatilityReferences(
            None, None, None, None, None, None, None, distance
        )
    return ResearchVolatilityReferences(
        atr,
        _number(close - atr, "one_atr_below"),
        _number(close + atr, "one_atr_above"),
        _number(close - 1.5 * atr, "one_and_half_atr_below"),
        _number(close + 1.5 * atr, "one_and_half_atr_above"),
        _number(close - 2.0 * atr, "two_atr_below"),
        _number(close + 2.0 * atr, "two_atr_above"),
        distance,
    )


def _unavailable(
    *,
    bar_count: int,
    ema_8: float | None,
    ema_20: float | None,
    ema_144: float | None,
    ema_169: float | None,
    macd_line: float | None,
    macd_signal: float | None,
    macd_histogram: float | None,
    rsi_14: float | None,
    wilder_atr_14: float | None,
    atr_percent_14: float | None,
    realized_volatility: float | None,
) -> tuple[TechnicalAnalysisUnavailable, ...]:
    checks = (
        (TechnicalAnalysisComponent.EMA_8, 8, ema_8 is not None),
        (TechnicalAnalysisComponent.EMA_20, 20, ema_20 is not None),
        (TechnicalAnalysisComponent.EMA_144, 144, ema_144 is not None),
        (TechnicalAnalysisComponent.EMA_169, 169, ema_169 is not None),
        (
            TechnicalAnalysisComponent.MACD,
            34,
            macd_line is not None
            and macd_signal is not None
            and macd_histogram is not None,
        ),
        (TechnicalAnalysisComponent.RSI_14, 15, rsi_14 is not None),
        (TechnicalAnalysisComponent.WILDER_ATR_14, 14, wilder_atr_14 is not None),
        (TechnicalAnalysisComponent.ATR_PERCENT_14, 14, atr_percent_14 is not None),
        (
            TechnicalAnalysisComponent.REALIZED_VOLATILITY,
            21,
            realized_volatility is not None,
        ),
        (TechnicalAnalysisComponent.DISTANCE_FROM_EMA20, 20, ema_20 is not None),
    )
    return tuple(
        TechnicalAnalysisUnavailable(
            component,
            TechnicalAnalysisUnavailableReason.INSUFFICIENT_HISTORY,
            required,
            bar_count,
        )
        for component, required, available in checks
        if not available
    )


def _warnings(
    evidence: DailyResearchEvidence, profile: DailyTechnicalAnalysisProfile
) -> tuple[TechnicalAnalysisWarning, ...]:
    result: list[TechnicalAnalysisWarning] = []
    if evidence.bar_count < profile.minimum_bar_count:
        result.append(TechnicalAnalysisWarning.INSUFFICIENT_PROFILE_HISTORY)
    if evidence.calendar_lag_days > profile.stale_after_calendar_days:
        result.append(TechnicalAnalysisWarning.STALE_EVIDENCE)
    return tuple(result)


def _retained(value: object, names: tuple[str, ...], owner: str) -> dict[str, object]:
    result: dict[str, object] = {}
    for name in names:
        try:
            result[name] = object.__getattribute__(value, name)
        except AttributeError as exc:
            raise ValueError(f"{owner} is missing retained field {name}") from exc
    return result


def _number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return 0.0 if result == 0.0 else result


def _canonical_retained_float(value: object, name: str, optional: bool) -> None:
    if optional and value is None:
        return
    if (
        type(value) is not float
        or not math.isfinite(value)
        or (value == 0.0 and math.copysign(1.0, value) < 0.0)
    ):
        raise ValueError(f"retained {name} must be a canonical finite float")


def _canonical_fingerprint_string(value: object, name: str) -> str:
    if type(value) is not str or _FINGERPRINT_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{name} must be a canonical sha256 fingerprint")
    return value


def _project_float(value: float | None, fingerprint_floats: bool) -> float | str | None:
    if value is None or not fingerprint_floats:
        return value
    return canonical_float(value)
