"""Completed daily-price evidence with deterministic provenance."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import cast
from zoneinfo import ZoneInfo

import pandas as pd

from market_platform._fingerprint import canonical_fingerprint
from market_platform.data.historical import HistoricalPriceRow, HistoricalPriceSeries
from market_platform.data.models import PRICE_COLUMNS
from market_platform.trading.instrument import TradingInstrumentIdentity

DAILY_RESEARCH_EVIDENCE_SCHEMA = "daily_research_evidence/v1"

_MARKET_TIMEZONE = "America/New_York"
_FINGERPRINT_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_EVIDENCE_SEAL = object()
_COMPLETED_SERIES_SEAL = object()


class ResearchTimeframe(StrEnum):
    """Supported research aggregation intervals."""

    DAILY = "1d"


class DailyAnalysisSessionScope(StrEnum):
    """Claim made about admitted provider daily aggregates."""

    PROVIDER_DAILY_AGGREGATE = "provider_daily_aggregate"


class PriceAdjustmentPolicy(StrEnum):
    """Price-adjustment semantics bound into research evidence."""

    ADJUSTED = "adjusted"
    PROVIDER_DEFAULT = "provider_default"


@dataclass(frozen=True, slots=True, init=False)
class DailyResearchEvidence:
    """Immutable provenance for one admitted completed-daily dataset."""

    instrument: TradingInstrumentIdentity
    timeframe: ResearchTimeframe
    session_scope: DailyAnalysisSessionScope
    market_timezone: str
    adjustment_policy: PriceAdjustmentPolicy
    analysis_as_of: datetime
    cutoff_session_date: date
    first_used_session_date: date
    latest_completed_bar_session_date: date
    bar_count: int
    excluded_current_session_row_count: int
    calendar_lag_days: int
    provider: str
    dataset_content_fingerprint: str
    schema_version: str
    fingerprint: str

    def __init__(self) -> None:
        raise TypeError(
            "DailyResearchEvidence must be created by "
            "prepare_completed_daily_price_series()"
        )

    @classmethod
    def _create(
        cls,
        *,
        creation_seal: object,
        instrument: TradingInstrumentIdentity,
        timeframe: ResearchTimeframe,
        session_scope: DailyAnalysisSessionScope,
        market_timezone: str,
        adjustment_policy: PriceAdjustmentPolicy,
        analysis_as_of: datetime,
        cutoff_session_date: date,
        first_used_session_date: date,
        latest_completed_bar_session_date: date,
        bar_count: int,
        excluded_current_session_row_count: int,
        calendar_lag_days: int,
        provider: str,
        dataset_content_fingerprint: str,
    ) -> DailyResearchEvidence:
        if creation_seal is not _EVIDENCE_SEAL:
            raise TypeError("daily research evidence construction is private")
        result = object.__new__(cls)
        values = {
            "instrument": _reconstruct_instrument(instrument),
            "timeframe": timeframe,
            "session_scope": session_scope,
            "market_timezone": market_timezone,
            "adjustment_policy": adjustment_policy,
            "analysis_as_of": analysis_as_of,
            "cutoff_session_date": cutoff_session_date,
            "first_used_session_date": first_used_session_date,
            "latest_completed_bar_session_date": latest_completed_bar_session_date,
            "bar_count": bar_count,
            "excluded_current_session_row_count": (excluded_current_session_row_count),
            "calendar_lag_days": calendar_lag_days,
            "provider": provider,
            "dataset_content_fingerprint": dataset_content_fingerprint,
        }
        for name, value in values.items():
            object.__setattr__(result, name, value)
        object.__setattr__(result, "schema_version", DAILY_RESEARCH_EVIDENCE_SCHEMA)
        result._validate(construction_seal=_EVIDENCE_SEAL)
        object.__setattr__(
            result,
            "fingerprint",
            canonical_fingerprint(result._fingerprint_payload()),
        )
        result._validate()
        return result

    def _fingerprint_payload(self) -> dict[str, object]:
        projection = self._projection(include_fingerprint=False)
        return projection

    def _projection(self, *, include_fingerprint: bool) -> dict[str, object]:
        projection: dict[str, object] = {
            "schema_version": self.schema_version,
            "instrument": self.instrument.to_dict(),
            "timeframe": self.timeframe.value,
            "session_scope": self.session_scope.value,
            "market_timezone": self.market_timezone,
            "adjustment_policy": self.adjustment_policy.value,
            "analysis_as_of": self.analysis_as_of.isoformat(),
            "cutoff_session_date": self.cutoff_session_date.isoformat(),
            "first_used_session_date": self.first_used_session_date.isoformat(),
            "latest_completed_bar_session_date": (
                self.latest_completed_bar_session_date.isoformat()
            ),
            "bar_count": self.bar_count,
            "excluded_current_session_row_count": (
                self.excluded_current_session_row_count
            ),
            "calendar_lag_days": self.calendar_lag_days,
            "provider": self.provider,
            "dataset_content_fingerprint": self.dataset_content_fingerprint,
        }
        if include_fingerprint:
            projection["fingerprint"] = self.fingerprint
        return projection

    def _validate(self, *, construction_seal: object | None = None) -> None:
        retained = _retained(
            self,
            "daily research evidence",
            (
                "instrument",
                "timeframe",
                "session_scope",
                "market_timezone",
                "adjustment_policy",
                "analysis_as_of",
                "cutoff_session_date",
                "first_used_session_date",
                "latest_completed_bar_session_date",
                "bar_count",
                "excluded_current_session_row_count",
                "calendar_lag_days",
                "provider",
                "dataset_content_fingerprint",
                "schema_version",
                "fingerprint",
            ),
            allow_missing_fingerprint=construction_seal is _EVIDENCE_SEAL,
        )
        retained_instrument = cast(TradingInstrumentIdentity, retained["instrument"])
        instrument = _reconstruct_instrument(retained_instrument)
        if instrument.to_dict() != retained_instrument.to_dict():
            raise ValueError("evidence instrument is not canonical")
        if type(retained["timeframe"]) is not ResearchTimeframe:
            raise ValueError("evidence timeframe is invalid")
        if retained["timeframe"] is not ResearchTimeframe.DAILY:
            raise ValueError("evidence timeframe is unsupported")
        if type(retained["session_scope"]) is not DailyAnalysisSessionScope:
            raise ValueError("evidence session_scope is invalid")
        if (
            retained["session_scope"]
            is not DailyAnalysisSessionScope.PROVIDER_DAILY_AGGREGATE
        ):
            raise ValueError("evidence session_scope is unsupported")
        if type(retained["adjustment_policy"]) is not PriceAdjustmentPolicy:
            raise ValueError("evidence adjustment_policy is invalid")
        if (
            type(retained["market_timezone"]) is not str
            or retained["market_timezone"] != _MARKET_TIMEZONE
        ):
            raise ValueError("evidence market_timezone is invalid")
        analysis_as_of = retained["analysis_as_of"]
        if (
            type(analysis_as_of) is not datetime
            or analysis_as_of.tzinfo is not UTC
            or analysis_as_of != analysis_as_of.astimezone(UTC)
        ):
            raise ValueError("evidence analysis_as_of must be canonical UTC")
        for name in (
            "cutoff_session_date",
            "first_used_session_date",
            "latest_completed_bar_session_date",
        ):
            if type(retained[name]) is not date:
                raise ValueError(f"evidence {name} must be an exact date")
        for name in (
            "bar_count",
            "excluded_current_session_row_count",
            "calendar_lag_days",
        ):
            if type(retained[name]) is not int:
                raise ValueError(f"evidence {name} must be an exact int")
        bar_count = cast(int, retained["bar_count"])
        excluded = cast(int, retained["excluded_current_session_row_count"])
        first = cast(date, retained["first_used_session_date"])
        latest = cast(date, retained["latest_completed_bar_session_date"])
        cutoff = cast(date, retained["cutoff_session_date"])
        lag = cast(int, retained["calendar_lag_days"])
        if bar_count < 1:
            raise ValueError("evidence bar_count must be positive")
        if excluded not in (0, 1):
            raise ValueError("evidence excluded row count must be zero or one")
        expected_cutoff = analysis_as_of.astimezone(
            ZoneInfo(_MARKET_TIMEZONE)
        ).date()
        if cutoff != expected_cutoff:
            raise ValueError("evidence cutoff does not match analysis_as_of")
        if not first <= latest < cutoff:
            raise ValueError("evidence session-date ordering is invalid")
        if lag != (cutoff - latest).days:
            raise ValueError("evidence calendar_lag_days is inconsistent")
        _already_trimmed_text(retained["provider"], "evidence provider")
        _fingerprint(retained["dataset_content_fingerprint"], "dataset fingerprint")
        if (
            type(retained["schema_version"]) is not str
            or retained["schema_version"] != DAILY_RESEARCH_EVIDENCE_SCHEMA
        ):
            raise ValueError("evidence schema_version is invalid")
        if "fingerprint" not in retained:
            return
        fingerprint = _fingerprint(retained["fingerprint"], "evidence fingerprint")
        expected = canonical_fingerprint(self._fingerprint_payload())
        if fingerprint != expected:
            raise ValueError("evidence fingerprint does not match content")

    def to_dict(self) -> dict[str, object]:
        """Return the canonical deterministic evidence projection."""

        self._validate()
        return self._projection(include_fingerprint=True)


@dataclass(frozen=True, slots=True, init=False)
class CompletedDailyPriceSeries:
    """Factory-owned completed daily price rows and their evidence."""

    _prices: HistoricalPriceSeries
    _evidence: DailyResearchEvidence

    def __init__(self) -> None:
        raise TypeError(
            "CompletedDailyPriceSeries must be created by "
            "prepare_completed_daily_price_series()"
        )

    @classmethod
    def _create(
        cls,
        *,
        prices: HistoricalPriceSeries,
        evidence: DailyResearchEvidence,
        creation_seal: object,
    ) -> CompletedDailyPriceSeries:
        if creation_seal is not _COMPLETED_SERIES_SEAL:
            raise TypeError("completed daily series construction is private")
        result = object.__new__(cls)
        object.__setattr__(result, "_prices", _reconstruct_prices(prices))
        object.__setattr__(result, "_evidence", evidence)
        result._validate()
        return result

    @property
    def evidence(self) -> DailyResearchEvidence:
        """Return the immutable corresponding research evidence."""

        self._validate()
        return self._evidence

    def __len__(self) -> int:
        self._validate()
        return len(self._prices)

    def iter_rows(self) -> Iterator[HistoricalPriceRow]:
        """Iterate canonical immutable retained rows."""

        prices = self._validated_prices()
        return prices.full_prefix().iter_rows()

    def to_dataframe(self) -> pd.DataFrame:
        """Return a deep isolated copy of retained completed rows."""

        return self._validated_prices().to_dataframe().copy(deep=True)

    def _validated_prices(self) -> HistoricalPriceSeries:
        self._validate()
        return _reconstruct_prices(self._prices)

    def _validate(self) -> None:
        retained = _retained(
            self,
            "completed daily price series",
            ("_prices", "_evidence"),
        )
        if type(retained["_evidence"]) is not DailyResearchEvidence:
            raise ValueError("completed daily evidence is invalid")
        evidence = retained["_evidence"]
        evidence._validate()
        prices = _reconstruct_prices(retained["_prices"])
        rows = tuple(prices.full_prefix().iter_rows())
        if len(rows) != evidence.bar_count:
            raise ValueError("completed daily row count does not match evidence")
        if prices.symbol != evidence.instrument.symbol:
            raise ValueError("completed daily symbol does not match evidence")
        if prices.provider != evidence.provider:
            raise ValueError("completed daily provider does not match evidence")
        if prices.content_fingerprint != evidence.dataset_content_fingerprint:
            raise ValueError("completed daily fingerprint does not match evidence")
        dates = tuple(_daily_session_date(row[1]) for row in rows)
        if dates[0] != evidence.first_used_session_date:
            raise ValueError("completed daily first date does not match evidence")
        if dates[-1] != evidence.latest_completed_bar_session_date:
            raise ValueError("completed daily latest date does not match evidence")
        if any(label >= evidence.cutoff_session_date for label in dates):
            raise ValueError("completed daily rows cross the evidence cutoff")


def prepare_completed_daily_price_series(
    *,
    prices: HistoricalPriceSeries,
    instrument: TradingInstrumentIdentity,
    timeframe: ResearchTimeframe,
    session_scope: DailyAnalysisSessionScope,
    market_timezone: str,
    adjustment_policy: PriceAdjustmentPolicy,
    analysis_as_of: datetime,
) -> CompletedDailyPriceSeries:
    """Admit only provider daily rows completed before the local cutoff date."""

    if type(prices) is not HistoricalPriceSeries:
        raise TypeError("prices must be an exact HistoricalPriceSeries")
    if type(instrument) is not TradingInstrumentIdentity:
        raise TypeError("instrument must be an exact TradingInstrumentIdentity")
    if type(timeframe) is not ResearchTimeframe:
        raise TypeError("timeframe must be an exact ResearchTimeframe")
    if type(session_scope) is not DailyAnalysisSessionScope:
        raise TypeError("session_scope must be an exact DailyAnalysisSessionScope")
    if type(market_timezone) is not str:
        raise TypeError("market_timezone must be an exact str")
    if type(adjustment_policy) is not PriceAdjustmentPolicy:
        raise TypeError("adjustment_policy must be an exact PriceAdjustmentPolicy")
    if type(analysis_as_of) is not datetime:
        raise TypeError("analysis_as_of must be an exact datetime")

    reconstructed_prices = _reconstruct_prices(prices)
    reconstructed_instrument = _reconstruct_instrument(instrument)
    if timeframe is not ResearchTimeframe.DAILY:
        raise ValueError("only the daily research timeframe is supported")
    if session_scope is not DailyAnalysisSessionScope.PROVIDER_DAILY_AGGREGATE:
        raise ValueError("only provider daily aggregate scope is supported")
    if market_timezone != _MARKET_TIMEZONE:
        raise ValueError("market_timezone must be America/New_York")
    if adjustment_policy not in (
        PriceAdjustmentPolicy.ADJUSTED,
        PriceAdjustmentPolicy.PROVIDER_DEFAULT,
    ):
        raise ValueError("adjustment_policy is unsupported")
    if analysis_as_of.tzinfo is None:
        raise ValueError("analysis_as_of must be timezone-aware")
    canonical_as_of = analysis_as_of.astimezone(UTC)

    rows = tuple(reconstructed_prices.full_prefix().iter_rows())
    labels = tuple(_daily_session_date(row[1]) for row in rows)
    if reconstructed_prices.symbol != reconstructed_instrument.symbol:
        raise ValueError("price series symbol must match instrument symbol")
    if len({row[1] for row in rows}) != len(rows):
        raise ValueError("daily prices must not contain duplicate UTC timestamps")
    if len(set(labels)) != len(labels):
        raise ValueError("daily prices must not contain duplicate session dates")

    cutoff = canonical_as_of.astimezone(ZoneInfo(_MARKET_TIMEZONE)).date()
    if any(label > cutoff for label in labels):
        raise ValueError("daily prices must not contain future session labels")
    admitted_rows = tuple(
        row for row, label in zip(rows, labels, strict=True) if label < cutoff
    )
    excluded = sum(label == cutoff for label in labels)
    if not admitted_rows:
        raise ValueError("completed daily evidence must contain at least one row")

    admitted_prices = HistoricalPriceSeries(
        pd.DataFrame(admitted_rows, columns=PRICE_COLUMNS),
        symbol=reconstructed_prices.symbol,
        provider=reconstructed_prices.provider,
    )
    first_date = _daily_session_date(admitted_rows[0][1])
    latest_date = _daily_session_date(admitted_rows[-1][1])
    evidence = DailyResearchEvidence._create(
        creation_seal=_EVIDENCE_SEAL,
        instrument=reconstructed_instrument,
        timeframe=timeframe,
        session_scope=session_scope,
        market_timezone=market_timezone,
        adjustment_policy=adjustment_policy,
        analysis_as_of=canonical_as_of,
        cutoff_session_date=cutoff,
        first_used_session_date=first_date,
        latest_completed_bar_session_date=latest_date,
        bar_count=len(admitted_rows),
        excluded_current_session_row_count=excluded,
        calendar_lag_days=(cutoff - latest_date).days,
        provider=admitted_prices.provider,
        dataset_content_fingerprint=admitted_prices.content_fingerprint,
    )
    return CompletedDailyPriceSeries._create(
        prices=admitted_prices,
        evidence=evidence,
        creation_seal=_COMPLETED_SERIES_SEAL,
    )


def _daily_session_date(timestamp: datetime) -> date:
    if (
        type(timestamp) is not datetime
        or timestamp.tzinfo is not UTC
        or timestamp.hour
        or timestamp.minute
        or timestamp.second
        or timestamp.microsecond
    ):
        raise ValueError("daily timestamps must be exactly midnight UTC")
    return timestamp.date()


def _reconstruct_prices(value: object) -> HistoricalPriceSeries:
    if type(value) is not HistoricalPriceSeries:
        raise ValueError("retained prices must be an exact HistoricalPriceSeries")
    try:
        frame = value.to_dataframe()
        symbol = value.symbol
        provider = value.provider
    except AttributeError as exc:
        raise ValueError("retained prices are missing required state") from exc
    return HistoricalPriceSeries(frame, symbol=symbol, provider=provider)


def _reconstruct_instrument(value: object) -> TradingInstrumentIdentity:
    if type(value) is not TradingInstrumentIdentity:
        raise ValueError("instrument must be an exact TradingInstrumentIdentity")
    try:
        reconstructed = TradingInstrumentIdentity(
            symbol=value.symbol,
            venue=value.venue,
        )
        source_projection = value.to_dict()
    except AttributeError as exc:
        raise ValueError("instrument is missing required retained state") from exc
    if reconstructed.to_dict() != source_projection:
        raise ValueError("instrument retained state is not canonical")
    return reconstructed


def _retained(
    value: object,
    owner: str,
    names: tuple[str, ...],
    *,
    allow_missing_fingerprint: bool = False,
) -> dict[str, object]:
    retained: dict[str, object] = {}
    for name in names:
        try:
            retained[name] = object.__getattribute__(value, name)
        except AttributeError as exc:
            if allow_missing_fingerprint and name == "fingerprint":
                continue
            raise ValueError(f"{owner} is missing retained field {name}") from exc
    return retained


def _already_trimmed_text(value: object, name: str) -> str:
    if type(value) is not str:
        raise ValueError(f"{name} must be an exact string")
    if not value or value != value.strip():
        raise ValueError(f"{name} must be nonempty and already trimmed")
    return value


def _fingerprint(value: object, name: str) -> str:
    if type(value) is not str or _FINGERPRINT_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{name} must be a canonical sha256 fingerprint")
    return value


def _copy_daily_research_evidence(
    value: DailyResearchEvidence,
) -> DailyResearchEvidence:
    """Reconstruct and validate a self-contained evidence value."""

    if type(value) is not DailyResearchEvidence:
        raise ValueError("evidence must be an exact DailyResearchEvidence")
    value._validate()
    return DailyResearchEvidence._create(
        creation_seal=_EVIDENCE_SEAL,
        instrument=value.instrument,
        timeframe=value.timeframe,
        session_scope=value.session_scope,
        market_timezone=value.market_timezone,
        adjustment_policy=value.adjustment_policy,
        analysis_as_of=value.analysis_as_of,
        cutoff_session_date=value.cutoff_session_date,
        first_used_session_date=value.first_used_session_date,
        latest_completed_bar_session_date=value.latest_completed_bar_session_date,
        bar_count=value.bar_count,
        excluded_current_session_row_count=value.excluded_current_session_row_count,
        calendar_lag_days=value.calendar_lag_days,
        provider=value.provider,
        dataset_content_fingerprint=value.dataset_content_fingerprint,
    )
