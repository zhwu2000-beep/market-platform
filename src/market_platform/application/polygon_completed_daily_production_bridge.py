"""Versioned whole-material representation after authentic use qualification."""

from __future__ import annotations

import math
import struct
from collections.abc import Callable
from contextlib import ExitStack
from copy import deepcopy
from dataclasses import dataclass, fields, replace
from datetime import UTC, date, datetime, time
from decimal import Decimal
from enum import StrEnum
from threading import Lock
from uuid import uuid4

import pandas as pd

from market_platform._fingerprint import canonical_fingerprint
from market_platform.application import (
    polygon_completed_daily_production_admission as a,
)
from market_platform.application import (
    polygon_completed_daily_production_governance as g,
)
from market_platform.application import (
    polygon_completed_daily_production_qualification as q,
)
from market_platform.data.historical import HistoricalPriceSeries
from market_platform.data.models import PRICE_COLUMNS
from market_platform.evidence import EvidenceArtifactReference
from market_platform.evidence_ingress.polygon_completed_daily_ohlcv import (
    PolygonCompletedDailyOhlcvMaterial,
    _canonical_numeric_text,
)
from market_platform.research.daily_evidence import (
    CompletedDailyPriceSeries,
    DailyAnalysisSessionScope,
    PriceAdjustmentPolicy,
    ResearchTimeframe,
    prepare_completed_daily_price_series,
)

_FIELDS = ("open", "high", "low", "close", "volume")
_TRANSFORMATION = q._PROFILE.transformation
_OPERATION = "production.polygon_completed_daily.bridge.completed_daily_price_series"
_EXECUTOR = "market_platform.application.polygon_completed_daily_production_bridge/v1"
# Exact binary64 endpoints; construction is independent of Decimal context.
_MINIMUM_NORMAL_SOURCE = Decimal.from_float(float.fromhex("0x1.0000000000000p-1022"))
_MAXIMUM_FINITE_SOURCE = Decimal.from_float(float.fromhex("0x1.fffffffffffffp+1023"))


class PolygonCompletedDailyBridgeRefusalReason(StrEnum):
    QUALIFICATION_UNAVAILABLE = "qualification_unavailable"
    HISTORY_INVALID = "history_incomplete_or_corrupt"
    REPRESENTATION_UNSUPPORTED = "representation_unsupported"
    CORRESPONDENCE_FAILED = "end_to_end_correspondence_failed"
    TEMPORAL_FAILURE = "temporal_failure"
    PUBLICATION_FAILED = "bridge_publication_failed"


class PolygonCompletedDailyBridgeRefused(RuntimeError):
    def __init__(
        self, reason: PolygonCompletedDailyBridgeRefusalReason, message: str
    ) -> None:
        self.reason = reason
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class PolygonCompletedDailyBridgeRequest:
    artifact_reference: EvidenceArtifactReference
    construction_execution_id: str
    qualification_execution_id: str
    qualification_fingerprint: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "artifact_reference",
            a._copy_artifact_reference(self.artifact_reference),
        )
        a._construction_execution_id(self.construction_execution_id)
        if type(
            self.qualification_execution_id
        ) is not str or not self.qualification_execution_id.startswith(
            "polygon_completed_daily_qualification:"
        ):
            raise ValueError("exact qualification occurrence reference required")
        g._fingerprint(self.qualification_fingerprint, "qualification fingerprint")


@dataclass(frozen=True, slots=True)
class _ConvertedRow:
    """Expected conversion retained before any representation factory runs."""

    session_date: str
    timestamp: datetime
    source: tuple[str, ...]
    values: tuple[float, ...]


def _binary64(value: float) -> str:
    """Big-endian IEEE-754 hex; zeros share the released canonical zero identity."""
    if type(value) is not float or not math.isfinite(value):
        raise ValueError("binary64 projection requires a finite Python float")
    return struct.pack(">d", 0.0 if value == 0.0 else value).hex()


def _convert_numeric(source: str, field: str) -> float:
    if type(source) is not str:
        raise ValueError("source decimal must be an exact canonical string")
    decimal = Decimal(source)
    if not decimal.is_finite() or _canonical_numeric_text(decimal, field) != source:
        raise ValueError("source decimal is not canonical finite material")
    if decimal != 0 and not _MINIMUM_NORMAL_SOURCE <= decimal <= _MAXIMUM_FINITE_SOURCE:
        raise ValueError("exact source is outside the approved positive normal range")
    # Direct Decimal conversion only: no quantization or intervening decimal float.
    result = float(decimal)
    bits = int(_binary64(result), 16)
    exponent = (bits >> 52) & 0x7FF
    if decimal != 0 and (exponent == 0 or bool(bits >> 63) != decimal.is_signed()):
        raise ValueError("nonzero source requires sign-preserving normal binary64")
    if decimal == 0:
        if field != "volume":
            raise ValueError("zero is unsupported for an OHLC representation")
        return 0.0
    return result


def _session_timestamp(label: str) -> datetime:
    if type(label) is not str:
        raise ValueError("session date must be a canonical string")
    parsed = date.fromisoformat(label)
    if parsed.isoformat() != label or not "1677-09-22" <= label <= "2262-04-11":
        raise ValueError("session date is outside the approved representation range")
    return datetime.combine(parsed, time(), UTC)


def _convert_material(
    material: PolygonCompletedDailyOhlcvMaterial,
) -> tuple[_ConvertedRow, ...]:
    return tuple(
        _ConvertedRow(
            row.session_date,
            _session_timestamp(row.session_date),
            tuple(getattr(row, field) for field in _FIELDS),
            tuple(_convert_numeric(getattr(row, field), field) for field in _FIELDS),
        )
        for row in material.rows
    )


def _prepare(
    qualified: q.PolygonCompletedDailyQualifiedUse, expected: tuple[_ConvertedRow, ...]
) -> CompletedDailyPriceSeries:
    material = qualified.construction_result.material
    instrument = material.mapping_resolution_provenance.mapping.canonical_instrument
    rows = tuple(
        (instrument.trading_identity.symbol, row.timestamp, *row.values, "polygon")
        for row in expected
    )
    return prepare_completed_daily_price_series(
        prices=HistoricalPriceSeries(pd.DataFrame(rows, columns=PRICE_COLUMNS)),
        instrument=instrument.trading_identity,
        timeframe=ResearchTimeframe.DAILY,
        session_scope=DailyAnalysisSessionScope.PROVIDER_DAILY_AGGREGATE,
        market_timezone="America/New_York",
        adjustment_policy=PriceAdjustmentPolicy.ADJUSTED,
        analysis_as_of=qualified.analysis_as_of,
    )


def _row_dates(dates: tuple[str, ...]) -> str:
    return canonical_fingerprint(
        {
            "schema_version": "polygon_completed_daily_row_dates/v1",
            "ordered_session_dates": list(dates),
            "row_count": len(dates),
        }
    )


def _mapping_proof_identity(qualified: q.PolygonCompletedDailyQualifiedUse) -> str:
    """Authenticate Slice 6's retained proof binding, without resolving coverage."""
    target = qualified.construction_result
    request = target.request
    return canonical_fingerprint(
        {
            "schema_version": "polygon_completed_daily_mapping_coverage/v1",
            "construction_receipt_fingerprint": target.receipt.fingerprint,
            "available_at": target.receipt.available_at.isoformat(),
            "external_identity": request.external_identity.to_dict(),
            "registry": [item.to_dict() for item in request.mappings],
            "selected_mapping": (
                target.material.mapping_resolution_provenance.mapping.to_dict()
            ),
            "ordered_session_dates": list(qualified.original_ordered_dates),
            "all_rows_covered": True,
        }
    )


def _dataset_payload(
    material: PolygonCompletedDailyOhlcvMaterial,
    rows: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "schema_version": "polygon_completed_daily_research_dataset/v1",
        "canonical_subject": material.canonical_subject.to_dict(),
        "instrument": (
            material.mapping_resolution_provenance.mapping.canonical_instrument.trading_identity.to_dict()
        ),
        "transformation_id": _TRANSFORMATION.definition_id,
        "transformation_version": _TRANSFORMATION.definition_version,
        "transformation_fingerprint": _TRANSFORMATION.fingerprint,
        "provider": "polygon",
        "session_scope": "provider_daily_aggregate",
        "adjustment_policy": "adjusted",
        "row_count": len(rows),
        "rows": rows,
    }


def _prove(
    qualified: q.PolygonCompletedDailyQualifiedUse,
    expected: tuple[_ConvertedRow, ...],
    result: CompletedDailyPriceSeries,
) -> tuple[str, str, str]:
    """Compare FINAL storage and public rows to ORIGINAL material by ordinal."""
    if type(result) is not CompletedDailyPriceSeries:
        raise ValueError("exact completed daily representation required")
    material = qualified.construction_result.material
    original = material.rows
    rows = tuple(result.iter_rows())
    # Inspect owned storage too: public CompletedDaily access reconstructs/sorts it.
    # Reading the existing carrier is not private construction or seal reuse.
    frame = result._prices.to_dataframe()
    if not original or len(original) != len(rows) or len(original) != len(expected):
        raise ValueError("original governed row count changed")
    if len(result) != len(original) or len(frame) != len(original):
        raise ValueError("final storage count differs from original material")
    if (
        type(frame.index) is not pd.RangeIndex
        or not frame.index.equals(pd.RangeIndex(len(original)))
        or str(frame["timestamp"].dtype) != "datetime64[ns, UTC]"
        or any(str(frame[field].dtype) != "float64" for field in _FIELDS)
    ):
        raise ValueError("final target storage differs from approved representation")
    instrument = material.mapping_resolution_provenance.mapping.canonical_instrument
    evidence = result.evidence
    if (
        evidence.instrument != instrument.trading_identity
        or evidence.provider != "polygon"
        or evidence.analysis_as_of != qualified.analysis_as_of
        or evidence.excluded_current_session_row_count != 0
        or evidence.timeframe is not ResearchTimeframe.DAILY
        or evidence.session_scope
        is not DailyAnalysisSessionScope.PROVIDER_DAILY_AGGREGATE
        or evidence.adjustment_policy is not PriceAdjustmentPolicy.ADJUSTED
        or evidence.market_timezone != "America/New_York"
    ):
        raise ValueError("final representation subject/context changed")
    proof_rows: list[dict[str, object]] = []
    dataset_rows: list[dict[str, object]] = []
    dates: list[str] = []
    for ordinal, (source, converted, target) in enumerate(
        zip(original, expected, rows, strict=True)
    ):
        source_values = tuple(getattr(source, field) for field in _FIELDS)
        timestamp = _session_timestamp(source.session_date)
        expected_bits = tuple(_binary64(value) for value in converted.values)
        target_bits = tuple(_binary64(value) for value in target[2:7])
        if (
            converted.source != source_values
            or converted.session_date != source.session_date
            or converted.timestamp != timestamp
            or target[0] != instrument.trading_identity.symbol
            or target[7] != "polygon"
            or type(target[1]) is not datetime
            or target[1].tzinfo is not UTC
            or target[1] != timestamp
            or target_bits != expected_bits
            or frame["timestamp"].iloc[ordinal] != pd.Timestamp(timestamp)
            or tuple(_binary64(float(frame[field].iloc[ordinal])) for field in _FIELDS)
            != expected_bits
            or frame["symbol"].iloc[ordinal] != target[0]
            or frame["provider"].iloc[ordinal] != target[7]
        ):
            raise ValueError(f"original governed row {ordinal} changed in final target")
        # Canonical fingerprints equate zeros, but approved stored zero is positive.
        if any(
            value == 0.0 and math.copysign(1.0, value) < 0
            for value in (
                *target[2:7],
                *(float(frame[f].iloc[ordinal]) for f in _FIELDS),
            )
        ):
            raise ValueError("final zero must be positive")
        dates.append(target[1].date().isoformat())
        dataset_rows.append(
            {"timestamp": timestamp.isoformat(), "ohlcv_binary64": target_bits}
        )
        proof_rows.append(
            {
                "ordinal": ordinal,
                "source_session_date": source.session_date,
                "source_ohlcv": source_values,
                "target_timestamp": target[1].isoformat(),
                "expected_binary64": expected_bits,
                "target_binary64": target_bits,
            }
        )
    date_fingerprint = _row_dates(tuple(dates))
    if date_fingerprint != qualified.original_row_date_fingerprint:
        raise ValueError("original Slice 6 date/order identity changed")
    dataset = canonical_fingerprint(_dataset_payload(material, dataset_rows))
    proof = canonical_fingerprint(
        {
            "schema_version": "polygon_completed_daily_no_drop_proof/v1",
            "source_material_fingerprint": material.fingerprint,
            "source_row_date_fingerprint": qualified.original_row_date_fingerprint,
            "transformation_fingerprint": _TRANSFORMATION.fingerprint,
            "dataset_fingerprint": dataset,
            "row_count": len(original),
            "rows": proof_rows,
        }
    )
    return dataset, proof, date_fingerprint


@dataclass(frozen=True, slots=True, init=False)
class PolygonCompletedDailyBridgeResult:
    """Immutable retained result; possession never grants history import authority."""

    qualification: q.PolygonCompletedDailyQualifiedUse
    completed_prices: CompletedDailyPriceSeries
    _expected: tuple[_ConvertedRow, ...]
    dataset_fingerprint: str
    no_drop_proof_fingerprint: str
    target_row_date_fingerprint: str
    execution_id: str
    history_sequence: int
    history_namespace_id: str
    execution_started_at: datetime
    execution_completed_at: datetime
    available_at: datetime
    fingerprint: str

    def __init__(self) -> None:
        raise TypeError("bridge results are published only by trusted bridge execution")

    @property
    def source_row_count(self) -> int:
        return self.qualification.original_row_count

    @property
    def target_row_count(self) -> int:
        return len(self.completed_prices)

    def _payload(self) -> dict[str, object]:
        qualified = self.qualification
        construction = qualified.construction_result
        profile = qualified.production_profile
        return {
            "schema_version": "polygon_completed_daily_bridge_result/v1",
            "qualification_execution_id": qualified.execution_id,
            "qualification_history_namespace_id": qualified.history_namespace_id,
            "qualification_history_sequence": qualified.history_sequence,
            "qualification_fingerprint": qualified.fingerprint,
            "artifact_reference": construction.artifact.reference().to_dict(),
            "construction_receipt": construction.receipt.to_dict(),
            "source_material_fingerprint": construction.material.fingerprint,
            "source_row_count": self.source_row_count,
            "source_row_date_fingerprint": qualified.original_row_date_fingerprint,
            "production_profile_fingerprint": profile.fingerprint,
            "consumer": profile.consumer.to_dict(),
            "use": profile.use.to_dict(),
            "analysis_profile": profile.analysis_profile.to_dict(),
            "transformation": profile.transformation.to_dict(),
            "analysis_as_of": qualified.analysis_as_of.isoformat(),
            "qualification_knowledge_as_of": qualified.knowledge_as_of.isoformat(),
            "dataset_fingerprint": self.dataset_fingerprint,
            "legacy_dataset_content_fingerprint": (
                self.completed_prices.evidence.dataset_content_fingerprint
            ),
            "target_row_count": self.target_row_count,
            "target_row_date_fingerprint": self.target_row_date_fingerprint,
            "no_drop_proof_fingerprint": self.no_drop_proof_fingerprint,
            "execution_id": self.execution_id,
            "history_sequence": self.history_sequence,
            "history_namespace_id": self.history_namespace_id,
            "operation": _OPERATION,
            "executor": _EXECUTOR,
            "execution_started_at": self.execution_started_at.isoformat(),
            "execution_completed_at": self.execution_completed_at.isoformat(),
            "available_at": self.available_at.isoformat(),
        }

    def to_dict(self) -> dict[str, object]:
        self.qualification.to_dict()
        qualified = self.qualification
        if (
            qualified.production_profile != q._approved_profile()
            or qualified.canonical_state.is_consumable is not True
            or qualified.all_row_mapping_covered is not True
            or qualified.whole_material_completed is not True
            or qualified.mapping_context_fingerprint
            != _mapping_proof_identity(qualified)
            or qualified.original_row_count != len(self._expected)
        ):
            raise ValueError("retained qualification correspondence changed")
        if _prove(self.qualification, self._expected, self.completed_prices) != (
            self.dataset_fingerprint,
            self.no_drop_proof_fingerprint,
            self.target_row_date_fingerprint,
        ):
            raise ValueError("retained final correspondence changed")
        if not (
            self.qualification.available_at
            <= self.execution_started_at
            <= self.execution_completed_at
            <= self.available_at
        ):
            raise ValueError("bridge occurrence chronology invalid")
        payload = self._payload()
        if canonical_fingerprint(payload) != self.fingerprint:
            raise ValueError("bridge result fingerprint mismatch")
        return {**payload, "fingerprint": self.fingerprint}


def _public_result_copy(
    retained: PolygonCompletedDailyBridgeResult,
) -> PolygonCompletedDailyBridgeResult:
    """Detach mutable research storage without creating a new execution occurrence."""
    retained.to_dict()
    public = object.__new__(PolygonCompletedDailyBridgeResult)
    for field in fields(retained):
        value = getattr(retained, field.name)
        if field.name == "completed_prices":
            value = deepcopy(retained.completed_prices)
        object.__setattr__(public, field.name, value)
    public.to_dict()
    return public


class _BridgeHistory:
    def __init__(self) -> None:
        self._lock = Lock()
        self._namespace_id = f"polygon_completed_daily_bridge_history:{uuid4().hex}"
        self._state: tuple[int, tuple[PolygonCompletedDailyBridgeResult, ...]] = (1, ())
        self._pending: PolygonCompletedDailyBridgeResult | None = None

    def _stage_publication(self, result: PolygonCompletedDailyBridgeResult) -> None:
        result.to_dict()
        self._pending = result

    def _validate(self) -> None:
        sequence, entries = self._state
        if sequence != len(entries) + 1:
            raise ValueError("bridge history is incomplete")
        ids: set[str] = set()
        previous: datetime | None = None
        for index, item in enumerate(entries, 1):
            if type(item) is not PolygonCompletedDailyBridgeResult:
                raise ValueError("bridge history type invalid")
            item.to_dict()
            if (
                item.history_sequence != index
                or item.history_namespace_id != self._namespace_id
                or item.execution_id in ids
                or (previous is not None and item.available_at < previous)
            ):
                raise ValueError("bridge occurrence history is corrupt")
            ids.add(item.execution_id)
            previous = item.available_at


class PolygonCompletedDailyProductionBridgeApplicationService:
    def __init__(
        self,
        qualification_service: (
            q.PolygonCompletedDailyProductionQualificationApplicationService
        ),
        *,
        execution_clock: Callable[[], datetime] | None = None,
    ) -> None:
        if type(qualification_service) is not (
            q.PolygonCompletedDailyProductionQualificationApplicationService
        ):
            raise TypeError("exact trusted qualification service required")
        if execution_clock is not None and not callable(execution_clock):
            raise TypeError("execution_clock must be callable")
        self._qualification_service = qualification_service
        self._clock = a._utc_now if execution_clock is None else execution_clock
        self._history = _BridgeHistory()

    def bridge(
        self, request: PolygonCompletedDailyBridgeRequest
    ) -> PolygonCompletedDailyBridgeResult:
        if type(request) is not PolygonCompletedDailyBridgeRequest:
            raise TypeError("only exact bridge intent/reference requests are accepted")
        request = replace(request)
        reason = PolygonCompletedDailyBridgeRefusalReason.HISTORY_INVALID
        try:
            started = a._timestamp(self._clock())
            source = self._qualification_service
            with ExitStack() as stack:
                source._lock_inputs(stack)
                stack.enter_context(source._history._lock)
                stack.enter_context(self._history._lock)
                self._history._validate()
                qualified = self._resolve(request, started)
                reason = (
                    PolygonCompletedDailyBridgeRefusalReason.REPRESENTATION_UNSUPPORTED
                )
                expected = _convert_material(qualified.construction_result.material)
                prices = _prepare(qualified, expected)
                reason = PolygonCompletedDailyBridgeRefusalReason.CORRESPONDENCE_FAILED
                dataset, proof, dates = _prove(qualified, expected, prices)
                reason = PolygonCompletedDailyBridgeRefusalReason.TEMPORAL_FAILURE
                completed = a._timestamp(self._clock())
                if completed < started:
                    raise ValueError("bridge completion clock moved backward")
                reason = PolygonCompletedDailyBridgeRefusalReason.PUBLICATION_FAILED
                return self._publish(
                    qualified,
                    expected,
                    prices,
                    dataset,
                    proof,
                    dates,
                    started,
                    completed,
                )
        except PolygonCompletedDailyBridgeRefused:
            raise
        except (
            TypeError,
            ValueError,
            RuntimeError,
            ArithmeticError,
            AttributeError,
        ) as error:
            raise PolygonCompletedDailyBridgeRefused(reason, str(error)) from error

    def _resolve(
        self, request: PolygonCompletedDailyBridgeRequest, started: datetime
    ) -> q.PolygonCompletedDailyQualifiedUse:
        source = self._qualification_service
        source._check_history()
        matches = tuple(
            item
            for item in source._history._state[1]
            if item.execution_id == request.qualification_execution_id
            and item.fingerprint == request.qualification_fingerprint
            and item.available_at <= started
        )
        if len(matches) != 1:
            raise PolygonCompletedDailyBridgeRefused(
                PolygonCompletedDailyBridgeRefusalReason.QUALIFICATION_UNAVAILABLE,
                "exact qualification occurrence unavailable in trusted history",
            )
        qualified = matches[0]
        if type(qualified) is not q.PolygonCompletedDailyQualifiedUse:
            raise ValueError("qualification history type invalid")
        qualified.to_dict()
        target = qualified.construction_result
        profile = q._approved_profile()
        state = qualified.canonical_state
        material = target.material
        dates = tuple(row.session_date for row in material.rows)
        if (
            target.receipt.execution_id != request.construction_execution_id
            or target.artifact.reference() != request.artifact_reference
            or qualified.production_profile != profile
            or qualified.production_profile.fingerprint != q._PROFILE_FINGERPRINT
            or profile.transformation != _TRANSFORMATION
            or state.is_consumable is not True
            or state.artifact_reference != request.artifact_reference
            or state.admission_scope != profile.scope
            or state.knowledge_as_of != qualified.knowledge_as_of
            or state.effective_as_of != qualified.analysis_as_of
            or qualified.effective_as_of != qualified.analysis_as_of
            or qualified.all_row_mapping_covered is not True
            or qualified.whole_material_completed is not True
            or not dates
            or qualified.original_row_count != len(dates)
            or qualified.original_ordered_dates != dates
            or qualified.original_row_date_fingerprint != _row_dates(dates)
            or qualified.mapping_context_fingerprint
            != _mapping_proof_identity(qualified)
            or not qualified.knowledge_as_of
            <= qualified.execution_completed_at
            <= qualified.available_at
            <= started
        ):
            raise ValueError("exact qualified material/profile/context mismatch")
        # Read-only provenance resolution. Never evaluate lifecycle or requalify use.
        history = source._snapshot(
            q.PolygonCompletedDailyQualificationRequest(
                request.artifact_reference,
                request.construction_execution_id,
                qualified.analysis_as_of,
                qualified.knowledge_as_of,
            ),
            qualified.knowledge_as_of,
        )
        if (
            history.fingerprint != qualified.history_context.fingerprint
            or not any(item is target for item in history.constructions)
            or not any(
                item is qualified.task_freshness_result for item in history.freshness
            )
        ):
            raise ValueError("qualification retained provenance incomplete or corrupt")
        return qualified

    def _publish(
        self,
        qualified: q.PolygonCompletedDailyQualifiedUse,
        expected: tuple[_ConvertedRow, ...],
        prices: CompletedDailyPriceSeries,
        dataset: str,
        proof: str,
        dates: str,
        started: datetime,
        completed: datetime,
    ) -> PolygonCompletedDailyBridgeResult:
        sequence, entries = self._history._state
        staged = object.__new__(PolygonCompletedDailyBridgeResult)
        values: dict[str, object] = {
            "qualification": qualified,
            "completed_prices": prices,
            "_expected": expected,
            "dataset_fingerprint": dataset,
            "no_drop_proof_fingerprint": proof,
            "target_row_date_fingerprint": dates,
            "execution_id": f"polygon_completed_daily_bridge:{uuid4().hex}",
            "history_sequence": sequence,
            "history_namespace_id": self._history._namespace_id,
            "execution_started_at": started,
            "execution_completed_at": completed,
            "available_at": completed,
        }
        for key, value in values.items():
            object.__setattr__(staged, key, value)
        object.__setattr__(
            staged, "fingerprint", canonical_fingerprint(staged._payload())
        )
        try:
            self._history._stage_publication(staged)
            # The final availability sample is inside the lock-held transaction.
            available = a._timestamp(self._clock())
            if available < completed or (
                entries and available < entries[-1].available_at
            ):
                raise ValueError("bridge publication clock moved backward")
            published = object.__new__(PolygonCompletedDailyBridgeResult)
            for field in fields(staged):
                object.__setattr__(published, field.name, getattr(staged, field.name))
            object.__setattr__(published, "available_at", available)
            object.__setattr__(
                published, "fingerprint", canonical_fingerprint(published._payload())
            )
            published.to_dict()
            # Copy and validate before publication: copy failure exposes no success.
            public = _public_result_copy(published)
            self._history._state = sequence + 1, (*entries, published)
            return public
        finally:
            self._history._pending = None

    def get_bridge_history_as_of(
        self,
        artifact_reference: EvidenceArtifactReference,
        *,
        knowledge_as_of: datetime,
    ) -> tuple[PolygonCompletedDailyBridgeResult, ...]:
        reference = a._copy_artifact_reference(artifact_reference)
        cutoff = a._timestamp(knowledge_as_of)
        with self._history._lock:
            self._history._validate()
            return tuple(
                _public_result_copy(item)
                for item in self._history._state[1]
                if item.qualification.construction_result.artifact.reference()
                == reference
                and item.available_at <= cutoff
            )


__all__ = [
    "PolygonCompletedDailyBridgeRefusalReason",
    "PolygonCompletedDailyBridgeRefused",
    "PolygonCompletedDailyBridgeRequest",
    "PolygonCompletedDailyBridgeResult",
    "PolygonCompletedDailyProductionBridgeApplicationService",
]
