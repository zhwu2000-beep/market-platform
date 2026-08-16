"""Fail-closed instrument-history integrity for daily research."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import StrEnum

import pandas as pd

from market_platform._fingerprint import canonical_fingerprint
from market_platform.data.historical import HistoricalPriceSeries
from market_platform.data.models import PRICE_COLUMNS
from market_platform.data.service import MarketDataService
from market_platform.instruments import (
    CanonicalInstrument,
    CanonicalInstrumentId,
    ExternalInstrumentIdentity,
    InstrumentAssetClass,
    InstrumentMapping,
    InstrumentMappingSourceIdentity,
    InstrumentResolution,
    InstrumentResolutionCorrespondenceError,
    resolve_instrument_mapping,
)
from market_platform.research.daily_analysis import (
    _RESULT_SEAL,
    DailyTechnicalResearchRequest,
    DailyTechnicalResearchResult,
    _acquire_polygon_daily_prices,
)
from market_platform.research.daily_evidence import (
    CompletedDailyPriceSeries,
    DailyAnalysisSessionScope,
    PriceAdjustmentPolicy,
    ResearchTimeframe,
    prepare_completed_daily_price_series,
)
from market_platform.research.technical_analysis import analyze_daily_technical_snapshot
from market_platform.trading import TradingInstrumentIdentity

DAILY_INSTRUMENT_INTEGRITY_EVIDENCE_SCHEMA = "daily_instrument_integrity_evidence/v1"
TRUSTED_INSTRUMENT_MAPPING_REGISTRY_SCHEMA = "trusted_instrument_mapping_registry/v1"
_REGISTRY_SEAL = object()
_EVIDENCE_SEAL = object()
_MARKET_TIMEZONE = "America/New_York"


class DailyInstrumentIntegrityPolicy(StrEnum):
    TRIM_TO_MAPPING_INTERVAL = "trim_to_mapping_interval"


@dataclass(frozen=True, slots=True, init=False)
class TrustedInstrumentMappingRegistry:
    _source: InstrumentMappingSourceIdentity = field(repr=False)
    _instruments: tuple[CanonicalInstrument, ...] = field(repr=False)
    _mappings: tuple[InstrumentMapping, ...] = field(repr=False)
    schema_version: str
    fingerprint: str
    _creation_fingerprint: str = field(repr=False)

    def __init__(self) -> None:
        raise TypeError("TrustedInstrumentMappingRegistry must be created by the codec")

    @classmethod
    def _create(
        cls,
        *,
        source: InstrumentMappingSourceIdentity,
        instruments: tuple[CanonicalInstrument, ...],
        mappings: tuple[InstrumentMapping, ...],
        seal: object,
    ) -> TrustedInstrumentMappingRegistry:
        if seal is not _REGISTRY_SEAL:
            raise TypeError("trusted registry construction is private")
        result = object.__new__(cls)
        fixed_source = _source(source)
        fixed_instruments = tuple(_instrument(item) for item in instruments)
        by_id = {item.instrument_id.instrument_id: item for item in fixed_instruments}
        fixed_mappings = tuple(_mapping(item, by_id, fixed_source) for item in mappings)
        object.__setattr__(result, "_source", fixed_source)
        object.__setattr__(result, "_instruments", fixed_instruments)
        object.__setattr__(result, "_mappings", fixed_mappings)
        object.__setattr__(
            result, "schema_version", TRUSTED_INSTRUMENT_MAPPING_REGISTRY_SCHEMA
        )
        fingerprint = canonical_fingerprint(result._payload())
        object.__setattr__(result, "fingerprint", fingerprint)
        object.__setattr__(result, "_creation_fingerprint", fingerprint)
        result._validate()
        return result

    @property
    def source(self) -> InstrumentMappingSourceIdentity:
        self._validate()
        return self._source

    @property
    def instruments(self) -> tuple[CanonicalInstrument, ...]:
        self._validate()
        return self._instruments

    @property
    def mappings(self) -> tuple[InstrumentMapping, ...]:
        self._validate()
        return self._mappings

    def _payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "source": self._source.to_dict(),
            "instruments": [
                item.to_dict()
                for item in sorted(
                    self._instruments,
                    key=lambda item: (
                        item.instrument_id.instrument_id,
                        item.fingerprint,
                    ),
                )
            ],
            "mappings": [
                item.to_dict()
                for item in sorted(self._mappings, key=lambda item: item.fingerprint)
            ],
        }

    def _validate(self) -> None:
        try:
            self._validate_retained_state()
        except (AttributeError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise ValueError(
                f"trusted registry retained state is invalid: {exc}"
            ) from exc

    def _validate_retained_state(self) -> None:
        source = _source(self._source)
        instruments = tuple(_instrument(item) for item in self._instruments)
        creation_fingerprint = self._creation_fingerprint
        if (
            self.schema_version != TRUSTED_INSTRUMENT_MAPPING_REGISTRY_SCHEMA
            or type(self._instruments) is not tuple
            or not instruments
            or type(self._mappings) is not tuple
            or not self._mappings
        ):
            raise ValueError("trusted registry structure is invalid")
        identifiers = [item.instrument_id.instrument_id for item in instruments]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("trusted registry repeats an instrument ID")
        by_id = {item.instrument_id.instrument_id: item for item in instruments}
        mappings = tuple(_mapping(item, by_id, source) for item in self._mappings)
        fingerprints = [item.fingerprint for item in mappings]
        if len(fingerprints) != len(set(fingerprints)):
            raise ValueError("trusted registry repeats a mapping fingerprint")
        if (
            self.fingerprint != creation_fingerprint
            or self.fingerprint != canonical_fingerprint(self._payload())
        ):
            raise ValueError("trusted registry fingerprint does not match content")

    def to_dict(self) -> dict[str, object]:
        self._validate()
        return {**self._payload(), "fingerprint": self.fingerprint}


def _prices(value: object) -> HistoricalPriceSeries:
    if type(value) is not HistoricalPriceSeries:
        raise ValueError("retained prices have invalid runtime type")
    return HistoricalPriceSeries(
        value.to_dataframe(), symbol=value.symbol, provider=value.provider
    )


def _source(value: object) -> InstrumentMappingSourceIdentity:
    if type(value) is not InstrumentMappingSourceIdentity:
        raise ValueError("mapping source has invalid runtime type")
    value._validate()
    result = InstrumentMappingSourceIdentity(
        value.source_id, value.source_version, value.configuration_fingerprint
    )
    if result.to_dict() != value.to_dict():
        raise ValueError("mapping source retained state is invalid")
    return result


def _instrument(value: object) -> CanonicalInstrument:
    if type(value) is not CanonicalInstrument:
        raise ValueError("canonical instrument has invalid runtime type")
    value._validate()
    result = CanonicalInstrument(
        CanonicalInstrumentId(value.instrument_id.instrument_id),
        TradingInstrumentIdentity(
            value.trading_identity.symbol, value.trading_identity.venue
        ),
        InstrumentAssetClass(value.asset_class.value),
        value.trading_currency,
    )
    if result.to_dict() != value.to_dict():
        raise ValueError("canonical instrument retained state is invalid")
    return result


def _mapping(
    value: object,
    instruments: dict[str, CanonicalInstrument],
    source: InstrumentMappingSourceIdentity,
) -> InstrumentMapping:
    if type(value) is not InstrumentMapping:
        raise ValueError("mapping has invalid runtime type")
    value._validate()
    identifier = value.canonical_instrument.instrument_id.instrument_id
    if identifier not in instruments:
        raise ValueError("mapping has dangling canonical reference")
    if (
        instruments[identifier].to_dict() != value.canonical_instrument.to_dict()
        or source.to_dict() != value.source.to_dict()
    ):
        raise ValueError("mapping descriptor is inconsistent")
    result = InstrumentMapping(
        ExternalInstrumentIdentity(
            value.external_identity.namespace,
            value.external_identity.external_symbol,
            value.external_identity.external_venue,
        ),
        instruments[identifier],
        source,
        value.valid_from,
        value.expires_at,
    )
    if result.to_dict() != value.to_dict():
        raise ValueError("mapping retained state is invalid")
    return result


@dataclass(frozen=True, slots=True, init=False)
class DailyInstrumentIntegrityEvidence:
    integrity_policy: DailyInstrumentIntegrityPolicy
    canonical_instrument_id: CanonicalInstrumentId
    requested_trading_identity: TradingInstrumentIdentity
    resolved_external_identity: ExternalInstrumentIdentity
    mapping_valid_from: date
    mapping_expires_at: date | None
    original_completed_bar_count: int
    admitted_bar_count: int
    excluded_before_valid_from_count: int
    excluded_at_or_after_expires_at_count: int
    original_first_session_date: date
    original_last_session_date: date
    admitted_first_session_date: date
    admitted_last_session_date: date
    mapping_source_fingerprint: str
    mapping_fingerprint: str
    registry_fingerprint: str
    original_completed_dataset_fingerprint: str
    admitted_dataset_fingerprint: str
    schema_version: str
    fingerprint: str
    _creation_fingerprint: str = field(repr=False)
    _mapping: InstrumentMapping = field(repr=False)
    _registry: TrustedInstrumentMappingRegistry = field(repr=False)
    _original: HistoricalPriceSeries = field(repr=False)
    _admitted: HistoricalPriceSeries = field(repr=False)
    _resolved_as_of: datetime = field(repr=False)
    _resolution: InstrumentResolution = field(repr=False)
    _creation_resolved_as_of: datetime = field(repr=False)

    def __init__(self) -> None:
        raise TypeError("DailyInstrumentIntegrityEvidence is factory-owned")

    @classmethod
    def _create(
        cls,
        *,
        request: DailyTechnicalResearchRequest,
        resolution: InstrumentResolution,
        registry: TrustedInstrumentMappingRegistry,
        original: CompletedDailyPriceSeries,
        admitted: CompletedDailyPriceSeries,
        excluded_before: int,
        excluded_after: int,
        seal: object,
    ) -> DailyInstrumentIntegrityEvidence:
        if seal is not _EVIDENCE_SEAL:
            raise TypeError("integrity evidence construction is private")
        if type(resolution) is not InstrumentResolution:
            raise TypeError("resolution must be an exact InstrumentResolution")
        expected_resolution = _preflight_daily_instrument_resolution(request, registry)
        try:
            resolution._validate()
            supplied_projection = resolution.to_dict()
        except (
            AttributeError,
            TypeError,
            ValueError,
            InstrumentResolutionCorrespondenceError,
        ) as exc:
            raise ValueError("instrument resolution retained state is invalid") from exc
        if supplied_projection != expected_resolution.to_dict():
            raise ValueError("instrument resolution does not match trusted preflight")
        mapping = expected_resolution.mapping
        original_prices = _prices(original._validated_prices())
        admitted_prices = _prices(admitted._validated_prices())
        rows = tuple(original_prices.full_prefix().iter_rows())
        admitted_rows = tuple(admitted_prices.full_prefix().iter_rows())
        result = object.__new__(cls)
        values = {
            "integrity_policy": DailyInstrumentIntegrityPolicy.TRIM_TO_MAPPING_INTERVAL,
            "canonical_instrument_id": CanonicalInstrumentId(
                mapping.canonical_instrument.instrument_id.instrument_id
            ),
            "requested_trading_identity": TradingInstrumentIdentity(
                request.instrument.symbol, request.instrument.venue
            ),
            "resolved_external_identity": ExternalInstrumentIdentity(
                mapping.external_identity.namespace,
                mapping.external_identity.external_symbol,
                mapping.external_identity.external_venue,
            ),
            "mapping_valid_from": mapping.valid_from.date(),
            "mapping_expires_at": None
            if mapping.expires_at is None
            else mapping.expires_at.date(),
            "original_completed_bar_count": len(rows),
            "admitted_bar_count": len(admitted_rows),
            "excluded_before_valid_from_count": excluded_before,
            "excluded_at_or_after_expires_at_count": excluded_after,
            "original_first_session_date": rows[0][1].date(),
            "original_last_session_date": rows[-1][1].date(),
            "admitted_first_session_date": admitted_rows[0][1].date(),
            "admitted_last_session_date": admitted_rows[-1][1].date(),
            "mapping_source_fingerprint": mapping.source.fingerprint,
            "mapping_fingerprint": mapping.fingerprint,
            "registry_fingerprint": registry.fingerprint,
            "original_completed_dataset_fingerprint": (
                original_prices.content_fingerprint
            ),
            "admitted_dataset_fingerprint": admitted_prices.content_fingerprint,
            "schema_version": DAILY_INSTRUMENT_INTEGRITY_EVIDENCE_SCHEMA,
            "_mapping": mapping,
            "_registry": registry,
            "_original": original_prices,
            "_admitted": admitted_prices,
            "_resolved_as_of": expected_resolution.resolved_as_of,
            "_resolution": expected_resolution,
            "_creation_resolved_as_of": expected_resolution.resolved_as_of,
        }
        for name, value in values.items():
            object.__setattr__(result, name, value)
        fingerprint = canonical_fingerprint(result._projection(False))
        object.__setattr__(result, "fingerprint", fingerprint)
        object.__setattr__(result, "_creation_fingerprint", fingerprint)
        result._validate()
        if (
            admitted.evidence.dataset_content_fingerprint
            != result.admitted_dataset_fingerprint
        ):
            raise ValueError("admitted research evidence fingerprint mismatch")
        return result

    def _projection(self, include_fingerprint: bool) -> dict[str, object]:
        result: dict[str, object] = {
            "schema_version": self.schema_version,
            "integrity_policy": self.integrity_policy.value,
            "canonical_instrument_id": self.canonical_instrument_id.to_dict(),
            "requested_trading_identity": self.requested_trading_identity.to_dict(),
            "resolved_external_identity": self.resolved_external_identity.to_dict(),
            "mapping_valid_from": self.mapping_valid_from.isoformat(),
            "mapping_expires_at": None
            if self.mapping_expires_at is None
            else self.mapping_expires_at.isoformat(),
            "original_completed_bar_count": self.original_completed_bar_count,
            "admitted_bar_count": self.admitted_bar_count,
            "excluded_before_valid_from_count": self.excluded_before_valid_from_count,
            "excluded_at_or_after_expires_at_count": (
                self.excluded_at_or_after_expires_at_count
            ),
            "original_first_session_date": self.original_first_session_date.isoformat(),
            "original_last_session_date": self.original_last_session_date.isoformat(),
            "admitted_first_session_date": self.admitted_first_session_date.isoformat(),
            "admitted_last_session_date": self.admitted_last_session_date.isoformat(),
            "mapping_source_fingerprint": self.mapping_source_fingerprint,
            "mapping_fingerprint": self.mapping_fingerprint,
            "registry_fingerprint": self.registry_fingerprint,
            "original_completed_dataset_fingerprint": (
                self.original_completed_dataset_fingerprint
            ),
            "admitted_dataset_fingerprint": self.admitted_dataset_fingerprint,
        }
        if include_fingerprint:
            result["fingerprint"] = self.fingerprint
        return result

    def _validate(self) -> None:
        try:
            self._validate_retained_state()
        except (
            AttributeError,
            TypeError,
            ValueError,
            InstrumentResolutionCorrespondenceError,
        ) as exc:
            raise ValueError(
                f"integrity evidence retained state is invalid: {exc}"
            ) from exc

    def _validate_retained_state(self) -> None:
        try:
            mapping, registry = self._mapping, self._registry
            original, admitted = _prices(self._original), _prices(self._admitted)
            creation_fingerprint = self._creation_fingerprint
            creation_resolved_as_of = self._creation_resolved_as_of
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError("integrity evidence retained state is invalid") from exc
        if type(registry) is not TrustedInstrumentMappingRegistry:
            raise ValueError("integrity registry is invalid")
        if type(mapping) is not InstrumentMapping:
            raise ValueError("integrity mapping is invalid")
        if type(self._resolution) is not InstrumentResolution:
            raise ValueError("integrity resolution is invalid")
        registry._validate()
        mapping._validate()
        self._resolution._validate()
        if (
            self.schema_version != DAILY_INSTRUMENT_INTEGRITY_EVIDENCE_SCHEMA
            or self.integrity_policy
            is not DailyInstrumentIntegrityPolicy.TRIM_TO_MAPPING_INTERVAL
        ):
            raise ValueError("integrity evidence schema or policy is invalid")
        counts = (
            self.original_completed_bar_count,
            self.admitted_bar_count,
            self.excluded_before_valid_from_count,
            self.excluded_at_or_after_expires_at_count,
        )
        if any(type(count) is not int or count < 0 for count in counts):
            raise ValueError("integrity counts must be strict nonnegative integers")
        if self.admitted_bar_count == 0:
            raise ValueError("integrity admitted count must be positive")
        dates = (
            self.mapping_valid_from,
            self.original_first_session_date,
            self.original_last_session_date,
            self.admitted_first_session_date,
            self.admitted_last_session_date,
        )
        if any(type(item) is not date for item in dates) or (
            self.mapping_expires_at is not None
            and type(self.mapping_expires_at) is not date
        ):
            raise ValueError("integrity dates must be exact dates")
        if (
            type(creation_resolved_as_of) is not datetime
            or creation_resolved_as_of.tzinfo is not UTC
        ):
            raise ValueError("integrity creation resolution instant is invalid")
        if (
            type(self._resolved_as_of) is not datetime
            or self._resolved_as_of.tzinfo is not UTC
        ):
            raise ValueError("integrity resolution instant is invalid")
        if self._resolved_as_of != creation_resolved_as_of:
            raise ValueError("integrity resolution instant drifted from creation")
        if not mapping.is_active(self._resolved_as_of):
            raise ValueError("integrity mapping is inactive at resolution instant")
        if (
            not any(mapping.to_dict() == item.to_dict() for item in registry.mappings)
            or mapping.source.to_dict() != registry.source.to_dict()
        ):
            raise ValueError("mapping does not belong to registry")
        if (
            self.mapping_fingerprint,
            self.mapping_source_fingerprint,
            self.registry_fingerprint,
        ) != (mapping.fingerprint, mapping.source.fingerprint, registry.fingerprint):
            raise ValueError("integrity provenance mismatch")
        identity_types = (
            (self.canonical_instrument_id, CanonicalInstrumentId),
            (self.requested_trading_identity, TradingInstrumentIdentity),
            (self.resolved_external_identity, ExternalInstrumentIdentity),
        )
        if any(type(value) is not expected for value, expected in identity_types):
            raise ValueError("integrity identity has invalid runtime type")
        fixed_canonical_id = CanonicalInstrumentId(
            self.canonical_instrument_id.instrument_id
        )
        fixed_requested_identity = TradingInstrumentIdentity(
            self.requested_trading_identity.symbol,
            self.requested_trading_identity.venue,
        )
        self.resolved_external_identity._validate()
        fixed_external_identity = ExternalInstrumentIdentity(
            self.resolved_external_identity.namespace,
            self.resolved_external_identity.external_symbol,
            self.resolved_external_identity.external_venue,
        )
        if (
            fixed_canonical_id.to_dict() != self.canonical_instrument_id.to_dict()
            or fixed_requested_identity.to_dict()
            != self.requested_trading_identity.to_dict()
            or fixed_external_identity.to_dict()
            != self.resolved_external_identity.to_dict()
        ):
            raise ValueError("integrity identity retained state is invalid")
        if (
            self.canonical_instrument_id.to_dict()
            != mapping.canonical_instrument.instrument_id.to_dict()
            or self.requested_trading_identity.to_dict()
            != mapping.canonical_instrument.trading_identity.to_dict()
            or self.resolved_external_identity.to_dict()
            != mapping.external_identity.to_dict()
        ):
            raise ValueError("integrity identity correspondence mismatch")
        resolution = self._resolution
        if (
            resolution.resolved_as_of != creation_resolved_as_of
            or resolution.resolved_as_of != self._resolved_as_of
            or resolution.mapping.to_dict() != mapping.to_dict()
            or resolution.external_identity.to_dict()
            != self.resolved_external_identity.to_dict()
        ):
            raise ValueError("integrity resolution correspondence mismatch")
        rows = tuple(original.full_prefix().iter_rows())
        admitted_rows = tuple(admitted.full_prefix().iter_rows())
        before = tuple(row for row in rows if row[1].date() < mapping.valid_from.date())
        after = tuple(
            row
            for row in rows
            if mapping.expires_at is not None
            and row[1].date() >= mapping.expires_at.date()
        )
        expected = tuple(row for row in rows if row not in before and row not in after)
        if not admitted_rows or admitted_rows != expected:
            raise ValueError("admitted rows are not the stable lifecycle subsequence")
        observed_counts = (len(rows), len(admitted_rows), len(before), len(after))
        if observed_counts != (
            self.original_completed_bar_count,
            self.admitted_bar_count,
            self.excluded_before_valid_from_count,
            self.excluded_at_or_after_expires_at_count,
        ) or observed_counts[0] != sum(observed_counts[1:]):
            raise ValueError("integrity row count mismatch")
        ranges = (
            rows[0][1].date(),
            rows[-1][1].date(),
            admitted_rows[0][1].date(),
            admitted_rows[-1][1].date(),
        )
        if ranges != (
            self.original_first_session_date,
            self.original_last_session_date,
            self.admitted_first_session_date,
            self.admitted_last_session_date,
        ):
            raise ValueError("integrity range mismatch")
        if (
            self.mapping_valid_from != mapping.valid_from.date()
            or self.mapping_expires_at
            != (None if mapping.expires_at is None else mapping.expires_at.date())
        ):
            raise ValueError("mapping interval mismatch")
        if (
            self.original_completed_dataset_fingerprint != original.content_fingerprint
            or self.admitted_dataset_fingerprint != admitted.content_fingerprint
        ):
            raise ValueError("dataset fingerprint mismatch")
        if (
            self.fingerprint != creation_fingerprint
            or self.fingerprint != canonical_fingerprint(self._projection(False))
        ):
            raise ValueError("integrity evidence fingerprint mismatch")

    def to_dict(self) -> dict[str, object]:
        self._validate()
        return self._projection(True)


@dataclass(frozen=True, slots=True, init=False)
class IntegrityCheckedDailyTechnicalResearchResult:
    research: DailyTechnicalResearchResult
    integrity: DailyInstrumentIntegrityEvidence

    def __init__(self) -> None:
        raise TypeError(
            "IntegrityCheckedDailyTechnicalResearchResult is workflow-owned"
        )

    @classmethod
    def _create(
        cls,
        research: DailyTechnicalResearchResult,
        integrity: DailyInstrumentIntegrityEvidence,
    ) -> IntegrityCheckedDailyTechnicalResearchResult:
        result = object.__new__(cls)
        object.__setattr__(result, "research", research)
        object.__setattr__(result, "integrity", integrity)
        result._validate()
        return result

    def _validate(self) -> None:
        try:
            self._validate_retained_state()
        except (
            AttributeError,
            TypeError,
            ValueError,
            InstrumentResolutionCorrespondenceError,
        ) as exc:
            raise ValueError(
                f"verified result retained state is invalid: {exc}"
            ) from exc

    def _validate_retained_state(self) -> None:
        try:
            research, integrity = self.research, self.integrity
        except AttributeError as exc:
            raise ValueError("verified result retained state is incomplete") from exc
        if (
            type(research) is not DailyTechnicalResearchResult
            or type(integrity) is not DailyInstrumentIntegrityEvidence
        ):
            raise ValueError("verified nested model is invalid")
        research._validate()
        integrity._validate()
        evidence = research.snapshot.evidence
        if (
            research.request.instrument.to_dict()
            != integrity.requested_trading_identity.to_dict()
            or research.request.analysis_as_of != integrity._resolved_as_of
        ):
            raise ValueError("verified request correspondence mismatch")
        if research.request.provider != "polygon":
            raise ValueError("verified provider must be polygon")
        if (
            evidence.dataset_content_fingerprint
            != integrity.admitted_dataset_fingerprint
            or evidence.bar_count != integrity.admitted_bar_count
        ):
            raise ValueError("verified admitted dataset mismatch")
        if (
            evidence.first_used_session_date,
            evidence.latest_completed_bar_session_date,
        ) != (
            integrity.admitted_first_session_date,
            integrity.admitted_last_session_date,
        ):
            raise ValueError("verified admitted range mismatch")

    def to_dict(self) -> dict[str, object]:
        self._validate()
        return {
            "research": self.research.to_dict(),
            "integrity": self.integrity.to_dict(),
        }


class IntegrityCheckedDailyTechnicalResearchWorkflow:
    def __init__(self, market_data_service: MarketDataService) -> None:
        if type(market_data_service) is not MarketDataService:
            raise TypeError("market_data_service must be an exact MarketDataService")
        self._market_data_service = market_data_service

    async def run(
        self,
        request: DailyTechnicalResearchRequest,
        registry: TrustedInstrumentMappingRegistry,
    ) -> IntegrityCheckedDailyTechnicalResearchResult:
        resolution = _preflight_daily_instrument_resolution(request, registry)
        prices = await _acquire_polygon_daily_prices(self._market_data_service, request)
        original = _prepare(prices, request)
        rows = tuple(original.iter_rows())
        valid_from = resolution.mapping.valid_from.date()
        expires_at = (
            None
            if resolution.mapping.expires_at is None
            else resolution.mapping.expires_at.date()
        )
        before = tuple(row for row in rows if row[1].date() < valid_from)
        after = tuple(
            row
            for row in rows
            if expires_at is not None and row[1].date() >= expires_at
        )
        admitted_rows = tuple(
            row for row in rows if row not in before and row not in after
        )
        if not admitted_rows:
            raise ValueError(
                "instrument mapping interval admits no completed daily rows"
            )
        admitted = _prepare(
            HistoricalPriceSeries(
                pd.DataFrame(admitted_rows, columns=PRICE_COLUMNS),
                symbol=request.instrument.symbol,
                provider="polygon",
            ),
            request,
        )
        snapshot = analyze_daily_technical_snapshot(
            completed_prices=admitted, profile=request.profile
        )
        research = DailyTechnicalResearchResult._create(
            request=request, snapshot=snapshot, seal=_RESULT_SEAL
        )
        integrity = DailyInstrumentIntegrityEvidence._create(
            request=request,
            resolution=resolution,
            registry=registry,
            original=original,
            admitted=admitted,
            excluded_before=len(before),
            excluded_after=len(after),
            seal=_EVIDENCE_SEAL,
        )
        return IntegrityCheckedDailyTechnicalResearchResult._create(research, integrity)


def _prepare(
    prices: HistoricalPriceSeries, request: DailyTechnicalResearchRequest
) -> CompletedDailyPriceSeries:
    return prepare_completed_daily_price_series(
        prices=prices,
        instrument=request.instrument,
        timeframe=ResearchTimeframe.DAILY,
        session_scope=DailyAnalysisSessionScope.PROVIDER_DAILY_AGGREGATE,
        market_timezone=_MARKET_TIMEZONE,
        adjustment_policy=PriceAdjustmentPolicy.ADJUSTED,
        analysis_as_of=request.analysis_as_of,
    )


__all__ = [
    "DAILY_INSTRUMENT_INTEGRITY_EVIDENCE_SCHEMA",
    "TRUSTED_INSTRUMENT_MAPPING_REGISTRY_SCHEMA",
    "DailyInstrumentIntegrityPolicy",
    "DailyInstrumentIntegrityEvidence",
    "TrustedInstrumentMappingRegistry",
    "IntegrityCheckedDailyTechnicalResearchResult",
    "IntegrityCheckedDailyTechnicalResearchWorkflow",
]


def _preflight_daily_instrument_resolution(
    request: DailyTechnicalResearchRequest,
    registry: TrustedInstrumentMappingRegistry,
) -> InstrumentResolution:
    """Purely resolve and verify trusted metadata before external construction."""

    if type(request) is not DailyTechnicalResearchRequest:
        raise TypeError("request must be an exact DailyTechnicalResearchRequest")
    request._validate()
    if type(registry) is not TrustedInstrumentMappingRegistry:
        raise TypeError("registry must be an exact TrustedInstrumentMappingRegistry")
    registry._validate()
    external = ExternalInstrumentIdentity(
        "polygon", request.instrument.symbol, request.instrument.venue
    )
    resolution = resolve_instrument_mapping(
        external, registry.mappings, request.analysis_as_of
    )
    resolution._validate()
    mapping = resolution.mapping
    if mapping.canonical_instrument.trading_identity.to_dict() != (
        request.instrument.to_dict()
    ):
        raise ValueError(
            "resolved canonical descriptor does not match request identity"
        )
    if not any(mapping.to_dict() == item.to_dict() for item in registry.mappings):
        raise ValueError("resolved mapping does not belong to trusted registry")
    if mapping.source.to_dict() != registry.source.to_dict():
        raise ValueError("resolved mapping source does not belong to trusted registry")
    if resolution.external_identity.to_dict() != mapping.external_identity.to_dict():
        raise ValueError("resolved external identity does not match mapping")
    return resolution
