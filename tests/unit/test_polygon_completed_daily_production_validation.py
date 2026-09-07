from __future__ import annotations

import asyncio
import inspect
from dataclasses import fields, replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import market_platform.evidence as evidence
from market_platform.application import (
    polygon_completed_daily_production_freshness as freshness,
)
from market_platform.application import (
    polygon_completed_daily_production_validation as validation,
)
from market_platform.application.polygon_completed_daily_evidence_candidate import (
    PolygonCompletedDailyEvidenceCandidateApplicationRequest,
)
from market_platform.application.polygon_completed_daily_production_construction import (  # noqa: E501
    PolygonCompletedDailyProductionConstructionApplicationService,
    PolygonCompletedDailyProductionConstructionResult,
)
from market_platform.application.polygon_completed_daily_production_governance import (
    _POLYGON_COMPLETED_DAILY_PRODUCTION_PROFILE,
)
from market_platform.data.providers.polygon import (
    PolygonCompletedDailyAcquisition,
    PolygonCompletedDailyAggregate,
)
from market_platform.evidence import (
    EvidenceAuthority,
    EvidenceFreshnessRule,
    EvidenceValidationConcern,
    EvidenceValidationDisposition,
)
from market_platform.instruments import (
    CanonicalInstrument,
    CanonicalInstrumentId,
    ExternalInstrumentIdentity,
    InstrumentAssetClass,
    InstrumentMapping,
    InstrumentMappingSourceIdentity,
)
from market_platform.trading import TradingInstrumentIdentity

_NY = ZoneInfo("America/New_York")
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_PROFILE_FINGERPRINT = (
    "sha256:341279ccfd6839287e5e5c9af46f9eb834577a07e9ffd1a16c0e27ccc35cfd49"
)
_AUTHORIZATION_FINGERPRINT = (
    "sha256:e9d8057dde8e20c5fb297ea08be7bcc723131cea42fab0e8a528f5b40c343387"
)
_DEFINITIONS = _POLYGON_COMPLETED_DAILY_PRODUCTION_PROFILE.validation_definitions
_REFUSAL = validation.PolygonCompletedDailyValidationRefusalReason


class _Clock:
    def __init__(self, *values: datetime) -> None:
        self._values = iter(values)

    def __call__(self) -> datetime:
        return next(self._values)


class _Acquirer:
    def __init__(self, acquisition: PolygonCompletedDailyAcquisition) -> None:
        self.acquisition = acquisition

    async def get_completed_daily_acquisition(
        self, ticker: str, start: date, end: date
    ) -> PolygonCompletedDailyAcquisition:
        return self.acquisition


def _ny_instant(session_date: date, hour: int = 12) -> datetime:
    return datetime.combine(session_date, time(hour=hour), tzinfo=_NY).astimezone(UTC)


def _milliseconds(session_date: date) -> int:
    return (_ny_instant(session_date) - _EPOCH) // timedelta(milliseconds=1)


def _row(
    session_date: date,
    *,
    open_value: str = "100",
    high: str = "102",
    low: str = "99",
    close: str = "101",
    volume: str = "1000",
) -> PolygonCompletedDailyAggregate:
    return PolygonCompletedDailyAggregate(
        timestamp=_milliseconds(session_date),
        open=Decimal(open_value),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal(volume),
    )


def _external() -> ExternalInstrumentIdentity:
    return ExternalInstrumentIdentity("polygon", "AAPL", "NASDAQ")


def _mapping(*, valid_from: datetime | None = None) -> InstrumentMapping:
    return InstrumentMapping(
        _external(),
        CanonicalInstrument(
            CanonicalInstrumentId("us_equity.AAPL"),
            TradingInstrumentIdentity("AAPL", "NASDAQ"),
            InstrumentAssetClass.EQUITY,
            "USD",
        ),
        InstrumentMappingSourceIdentity("operator_registry", "1.0.0"),
        datetime(2020, 1, 1, tzinfo=UTC) if valid_from is None else valid_from,
    )


def _construction(
    rows: tuple[PolygonCompletedDailyAggregate, ...] = (
        _row(date(2026, 8, 27)),
        _row(date(2026, 8, 28)),
    ),
    *,
    requested_from: date = date(2026, 8, 27),
    requested_to: date = date(2026, 8, 28),
    mapping: InstrumentMapping | None = None,
) -> tuple[
    PolygonCompletedDailyProductionConstructionApplicationService,
    PolygonCompletedDailyProductionConstructionResult,
]:
    query = _ny_instant(requested_to + timedelta(days=1))
    received = query + timedelta(minutes=1)
    created = query + timedelta(minutes=2)
    acquisition = PolygonCompletedDailyAcquisition(
        requested_ticker="AAPL",
        requested_from=requested_from.isoformat(),
        requested_to=requested_to.isoformat(),
        response_ticker_is_present=True,
        response_ticker="AAPL",
        response_adjusted_is_present=True,
        response_adjusted=True,
        request_id_is_present=True,
        request_id="request-123",
        query_count_is_present=True,
        query_count=len(rows),
        results_count_is_present=True,
        results_count=len(rows),
        count_is_present=True,
        count=len(rows),
        next_url_is_present=False,
        next_page_reference=None,
        results_is_present=True,
        rows=rows,
        response_received_at=received,
    )
    service = PolygonCompletedDailyProductionConstructionApplicationService(
        _Acquirer(acquisition),
        creation_clock=lambda: created,
        execution_clock=_Clock(
            query,
            query + timedelta(minutes=3),
            query + timedelta(minutes=4),
        ),
    )
    request = PolygonCompletedDailyEvidenceCandidateApplicationRequest(
        external_identity=_external(),
        mappings=(_mapping() if mapping is None else mapping,),
        requested_from=requested_from,
        requested_to=requested_to,
        query_as_of=query,
    )
    return service, asyncio.run(service.execute(request))


def _validation_service(
    construction_service: PolygonCompletedDailyProductionConstructionApplicationService,
    construction_result: PolygonCompletedDailyProductionConstructionResult,
    *,
    start: datetime | None = None,
    constant: bool = False,
) -> validation.PolygonCompletedDailyProductionValidationApplicationService:
    first = (
        construction_result.receipt.available_at + timedelta(minutes=1)
        if start is None
        else start
    )
    times = (
        (first,) * 64
        if constant
        else tuple(first + timedelta(seconds=index) for index in range(64))
    )
    return validation.PolygonCompletedDailyProductionValidationApplicationService(
        construction_service, execution_clock=_Clock(*times)
    )


def _request(
    result: PolygonCompletedDailyProductionConstructionResult,
) -> validation.PolygonCompletedDailyValidationRequest:
    return validation.PolygonCompletedDailyValidationRequest(
        artifact_reference=result.artifact.reference(),
        construction_execution_id=result.receipt.execution_id,
    )


def _by_concern(
    results: tuple[validation.PolygonCompletedDailyProductionValidationResult, ...],
) -> dict[
    EvidenceValidationConcern,
    validation.PolygonCompletedDailyProductionValidationResult,
]:
    return {item.validation_record.concern: item for item in results}


def _support(
    result: PolygonCompletedDailyProductionConstructionResult,
) -> validation._ValidationSupport:
    return validation._derive_support(result)


def _evaluate(
    concern: EvidenceValidationConcern,
    support: validation._ValidationSupport,
) -> EvidenceValidationDisposition:
    return validation._evaluate_definition(
        validation._approved_definition(concern), support
    ).disposition


def _material_with_rows(
    result: PolygonCompletedDailyProductionConstructionResult,
    rows: tuple[object, ...],
):
    return replace(result.material, rows=rows)


def test_exact_profile_executes_eight_independent_passed_lifecycle_records() -> None:
    construction_service, constructed = _construction()
    service = _validation_service(construction_service, constructed)

    results = service.execute_profile(_request(constructed))

    assert tuple(item.validation_record.concern for item in results) == tuple(
        definition.requirement.concern
        for definition in _DEFINITIONS
    )
    assert len(results) == 8
    assert all(
        item.validation_record.disposition is EvidenceValidationDisposition.PASSED
        for item in results
    )
    assert all(
        type(item.validation_record) is evidence.EvidenceValidationRecord
        for item in results
    )
    assert {item.validation_record.concern for item in results} == set(
        EvidenceValidationConcern
    )


def test_companion_binds_construction_profile_support_record_and_actual_times() -> None:
    construction_service, constructed = _construction()
    results = _validation_service(construction_service, constructed).execute_profile(
        _request(constructed)
    )

    for item in results:
        companion = item.companion
        record = item.validation_record
        assert companion.construction_execution_id == constructed.receipt.execution_id
        assert (
            companion.construction_receipt_fingerprint
            == constructed.receipt.fingerprint
        )
        assert companion.artifact_reference == constructed.artifact.reference()
        assert companion.material_fingerprint == constructed.material.fingerprint
        assert companion.production_profile_fingerprint == _PROFILE_FINGERPRINT
        assert (
            companion.construction_authorization_fingerprint
            == _AUTHORIZATION_FINGERPRINT
        )
        assert companion.validation_reference == record.reference()
        assert companion.disposition is record.disposition
        assert companion.validator == record.validator_identity
        assert companion.validator_capability == record.validator_capability_identity
        assert record.recorded_at == companion.execution_completed_at
        assert record.effective_at == companion.execution_completed_at
        assert companion.execution_started_at <= companion.execution_completed_at
        assert companion.execution_completed_at <= companion.available_at
        assert companion.fingerprint == validation.canonical_fingerprint(
            companion._fingerprint_payload()
        )


def test_request_and_service_expose_no_outcome_rule_support_or_subset_authority() -> (
    None
):
    construction_service, constructed = _construction()
    service = _validation_service(construction_service, constructed)
    request_fields = {
        item.name for item in fields(validation.PolygonCompletedDailyValidationRequest)
    }
    execute_parameters = tuple(inspect.signature(service.execute_profile).parameters)

    assert request_fields == {"artifact_reference", "construction_execution_id"}
    assert execute_parameters == ("request",)
    for forbidden in (
        "disposition",
        "requirement",
        "rules",
        "concerns",
        "findings",
        "support",
        "available_at",
        "executor",
        "capability",
        "history",
    ):
        assert forbidden not in request_fields
        assert forbidden not in execute_parameters


def test_identity_rejects_id_and_version_mismatches_and_missing_mapping_is_unable() -> (
    None
):
    _, constructed = _construction()
    artifact = constructed.artifact
    original_id = artifact.artifact_id
    object.__setattr__(artifact, "artifact_id", "sha256:" + ("0" * 64))
    assert (
        _evaluate(EvidenceValidationConcern.IDENTITY, _support(constructed))
        is EvidenceValidationDisposition.REJECTED
    )
    object.__setattr__(artifact, "artifact_id", original_id)
    original_version = artifact.artifact_version
    object.__setattr__(artifact, "artifact_version", "sha256:" + ("0" * 64))
    assert (
        _evaluate(EvidenceValidationConcern.IDENTITY, _support(constructed))
        is EvidenceValidationDisposition.REJECTED
    )
    object.__setattr__(artifact, "artifact_version", original_version)

    missing = replace(_support(constructed), mapping_resolution=None)
    assert (
        _evaluate(EvidenceValidationConcern.IDENTITY, missing)
        is EvidenceValidationDisposition.UNABLE_TO_VALIDATE
    )


def test_identity_does_not_perform_historical_all_row_mapping_coverage() -> None:
    historical = date(2019, 12, 31)
    construction_service, constructed = _construction(
        (_row(historical),),
        requested_from=historical,
        requested_to=date(2026, 8, 28),
        mapping=_mapping(valid_from=datetime(2026, 1, 1, tzinfo=UTC)),
    )

    result = _by_concern(
        _validation_service(construction_service, constructed).execute_profile(
            _request(constructed)
        )
    )[EvidenceValidationConcern.IDENTITY]

    assert result.validation_record.disposition is EvidenceValidationDisposition.PASSED


def test_integrity_exact_changed_and_missing_support_dispositions() -> None:
    _, constructed = _construction()
    exact = _support(constructed)
    changed_row = replace(constructed.material.rows[0], close="100.5")
    changed = replace(
        exact,
        material=_material_with_rows(
            constructed, (changed_row, *constructed.material.rows[1:])
        ),
    )

    assert (
        _evaluate(EvidenceValidationConcern.INTEGRITY, exact)
        is EvidenceValidationDisposition.PASSED
    )
    assert (
        _evaluate(EvidenceValidationConcern.INTEGRITY, changed)
        is EvidenceValidationDisposition.REJECTED
    )
    assert (
        _evaluate(EvidenceValidationConcern.INTEGRITY, replace(exact, material=None))
        is EvidenceValidationDisposition.UNABLE_TO_VALIDATE
    )


def test_provenance_exact_mismatch_missing_and_no_raw_transport_invention() -> None:
    _, constructed = _construction()
    exact = _support(constructed)
    wrong_request = replace(
        constructed.request,
        requested_from=constructed.request.requested_from - timedelta(days=1),
    )
    assert (
        _evaluate(EvidenceValidationConcern.PROVENANCE, exact)
        is EvidenceValidationDisposition.PASSED
    )
    assert (
        _evaluate(
            EvidenceValidationConcern.PROVENANCE, replace(exact, request=wrong_request)
        )
        is EvidenceValidationDisposition.REJECTED
    )
    assert (
        _evaluate(EvidenceValidationConcern.PROVENANCE, replace(exact, receipt=None))
        is EvidenceValidationDisposition.UNABLE_TO_VALIDATE
    )
    source = inspect.getsource(validation._evaluate_provenance)
    assert "raw_response" not in source
    assert "http" not in source.lower()


def test_authority_exact_wrong_class_lookalike_and_missing_policy() -> None:
    _, constructed = _construction()
    exact = _support(constructed)
    artifact = constructed.artifact
    assert (
        _evaluate(EvidenceValidationConcern.AUTHORITY, exact)
        is EvidenceValidationDisposition.PASSED
    )
    object.__setattr__(artifact, "authority", EvidenceAuthority.PLATFORM_ORIGIN)
    assert (
        _evaluate(EvidenceValidationConcern.AUTHORITY, _support(constructed))
        is EvidenceValidationDisposition.REJECTED
    )
    object.__setattr__(artifact, "authority", EvidenceAuthority.EXTERNAL_ORIGIN)
    lookalike = replace(
        exact.approved_profile, scope="research.daily_technical.lookalike"
    )
    assert (
        _evaluate(
            EvidenceValidationConcern.AUTHORITY,
            replace(exact, approved_profile=lookalike),
        )
        is EvidenceValidationDisposition.REJECTED
    )
    assert (
        _evaluate(
            EvidenceValidationConcern.AUTHORITY, replace(exact, approved_profile=None)
        )
        is EvidenceValidationDisposition.UNABLE_TO_VALIDATE
    )


@pytest.mark.parametrize(
    "row",
    (
        validation.PolygonCompletedDailyOhlcvMaterialRow(
            "2026-08-27", "01", "102", "99", "101", "1000"
        ),
        validation.PolygonCompletedDailyOhlcvMaterialRow(
            "2026-8-27", "100", "102", "99", "101", "1000"
        ),
        validation.PolygonCompletedDailyOhlcvMaterialRow(
            "2026-08-27", "100", "102", "99", "101", "NaN"
        ),
    ),
)
def test_schema_exact_malformed_and_missing_support(row: object) -> None:
    _, constructed = _construction()
    exact = _support(constructed)
    malformed = replace(exact, material=_material_with_rows(constructed, (row,)))

    assert (
        _evaluate(EvidenceValidationConcern.SCHEMA, exact)
        is EvidenceValidationDisposition.PASSED
    )
    assert (
        _evaluate(EvidenceValidationConcern.SCHEMA, malformed)
        is EvidenceValidationDisposition.REJECTED
    )
    assert (
        _evaluate(EvidenceValidationConcern.SCHEMA, replace(exact, material=None))
        is EvidenceValidationDisposition.UNABLE_TO_VALIDATE
    )


def test_temporal_exact_outside_incomplete_chronology_and_missing_support() -> None:
    _, constructed = _construction()
    exact = _support(constructed)
    outside = validation.PolygonCompletedDailyOhlcvMaterialRow(
        "2026-08-26", "100", "102", "99", "101", "1000"
    )
    current = validation.PolygonCompletedDailyOhlcvMaterialRow(
        "2026-08-29", "100", "102", "99", "101", "1000"
    )

    assert (
        _evaluate(EvidenceValidationConcern.TEMPORAL_COHERENCE, exact)
        is EvidenceValidationDisposition.PASSED
    )
    assert (
        _evaluate(
            EvidenceValidationConcern.TEMPORAL_COHERENCE,
            replace(exact, material=_material_with_rows(constructed, (outside,))),
        )
        is EvidenceValidationDisposition.REJECTED
    )
    assert (
        _evaluate(
            EvidenceValidationConcern.TEMPORAL_COHERENCE,
            replace(exact, material=_material_with_rows(constructed, (current,))),
        )
        is EvidenceValidationDisposition.REJECTED
    )

    receipt = constructed.receipt
    original_response = receipt.response_received_at
    object.__setattr__(
        receipt,
        "response_received_at",
        constructed.material.query_as_of - timedelta(seconds=1),
    )
    assert (
        _evaluate(EvidenceValidationConcern.TEMPORAL_COHERENCE, _support(constructed))
        is EvidenceValidationDisposition.REJECTED
    )
    object.__setattr__(receipt, "response_received_at", original_response)
    assert (
        _evaluate(
            EvidenceValidationConcern.TEMPORAL_COHERENCE,
            replace(exact, receipt=None),
        )
        is EvidenceValidationDisposition.UNABLE_TO_VALIDATE
    )


def test_carried_artifact_timestamp_alone_does_not_establish_availability() -> None:
    _, constructed = _construction()
    support = replace(_support(constructed), receipt=None)

    assert constructed.artifact.temporal_identity.artifact_created_at is not None
    assert (
        _evaluate(EvidenceValidationConcern.TEMPORAL_COHERENCE, support)
        is EvidenceValidationDisposition.UNABLE_TO_VALIDATE
    )


def test_freshness_contract_is_evaluability_not_freshness_outcome() -> None:
    old_date = date(2020, 1, 2)
    _, constructed = _construction(
        (_row(old_date),), requested_from=old_date, requested_to=date(2026, 8, 28)
    )
    exact = _support(constructed)

    assert (
        _evaluate(EvidenceValidationConcern.FRESHNESS_CONTRACT, exact)
        is EvidenceValidationDisposition.PASSED
    )
    assert "freshness_record" not in inspect.getsource(
        validation._evaluate_freshness_contract
    )
    assert "freshness_result" not in inspect.getsource(
        validation._evaluate_freshness_contract
    )


def test_freshness_contract_wrong_anchor_profile_and_missing_material() -> None:
    _, constructed = _construction()
    exact = _support(constructed)
    profile = exact.approved_profile
    assert profile is not None
    wrong_admission = replace(
        profile.admission_freshness,
        rule=EvidenceFreshnessRule(
            profile.admission_freshness.rule.rule_id,
            "1.0.0",
            "platform_received_at",
            profile.scope,
        ),
    )
    wrong_profile = replace(profile, admission_freshness=wrong_admission)

    assert (
        _evaluate(
            EvidenceValidationConcern.FRESHNESS_CONTRACT,
            replace(exact, approved_profile=wrong_profile),
        )
        is EvidenceValidationDisposition.REJECTED
    )
    assert (
        _evaluate(
            EvidenceValidationConcern.FRESHNESS_CONTRACT,
            replace(exact, material=None),
        )
        is EvidenceValidationDisposition.UNABLE_TO_VALIDATE
    )


@pytest.mark.parametrize(
    ("changes", "expected"),
    (
        ({"open_value": "0"}, EvidenceValidationDisposition.REJECTED),
        ({"high": "0"}, EvidenceValidationDisposition.REJECTED),
        ({"low": "0"}, EvidenceValidationDisposition.REJECTED),
        ({"close": "0"}, EvidenceValidationDisposition.REJECTED),
        ({"volume": "-1"}, EvidenceValidationDisposition.REJECTED),
        ({"high": "98"}, EvidenceValidationDisposition.REJECTED),
        ({"open_value": "103"}, EvidenceValidationDisposition.REJECTED),
        ({"close": "103"}, EvidenceValidationDisposition.REJECTED),
        ({"volume": "0"}, EvidenceValidationDisposition.PASSED),
        ({"volume": "0.5"}, EvidenceValidationDisposition.PASSED),
        (
            {
                "open_value": "0.0000000000000000000000000000001",
                "low": "0.0000000000000000000000000000001",
            },
            EvidenceValidationDisposition.PASSED,
        ),
    ),
)
def test_source_quality_numeric_rules_without_binary64_policy(
    changes: dict[str, str], expected: EvidenceValidationDisposition
) -> None:
    _, constructed = _construction()
    row = _row(date(2026, 8, 27), **changes)
    material_row = validation.PolygonCompletedDailyOhlcvMaterialRow(
        "2026-08-27",
        validation.ingress._canonical_numeric_text(row.open, "open"),
        validation.ingress._canonical_numeric_text(row.high, "high"),
        validation.ingress._canonical_numeric_text(row.low, "low"),
        validation.ingress._canonical_numeric_text(row.close, "close"),
        validation.ingress._canonical_numeric_text(row.volume, "volume"),
    )
    support = replace(
        _support(constructed),
        material=_material_with_rows(constructed, (material_row,)),
    )
    assert _evaluate(EvidenceValidationConcern.SOURCE_QUALITY, support) is expected


def test_source_quality_empty_duplicate_order_and_missing_support() -> None:
    _, constructed = _construction()
    exact = _support(constructed)
    first, second = constructed.material.rows
    duplicate = replace(second, session_date=first.session_date)
    reversed_rows = (second, first)

    assert (
        _evaluate(EvidenceValidationConcern.SOURCE_QUALITY, exact)
        is EvidenceValidationDisposition.PASSED
    )
    assert (
        _evaluate(
            EvidenceValidationConcern.SOURCE_QUALITY,
            replace(exact, material=_material_with_rows(constructed, ())),
        )
        is EvidenceValidationDisposition.REJECTED
    )
    assert (
        _evaluate(
            EvidenceValidationConcern.SOURCE_QUALITY,
            replace(
                exact, material=_material_with_rows(constructed, (first, duplicate))
            ),
        )
        is EvidenceValidationDisposition.REJECTED
    )
    assert (
        _evaluate(
            EvidenceValidationConcern.SOURCE_QUALITY,
            replace(exact, material=_material_with_rows(constructed, reversed_rows)),
        )
        is EvidenceValidationDisposition.REJECTED
    )
    assert (
        _evaluate(
            EvidenceValidationConcern.SOURCE_QUALITY, replace(exact, material=None)
        )
        is EvidenceValidationDisposition.UNABLE_TO_VALIDATE
    )


def test_source_quality_excludes_calendar_minimum_history_and_float_checks() -> None:
    source = inspect.getsource(validation._evaluate_source_quality).lower()

    for forbidden in (
        "float(",
        "binary64",
        "exchange_calendar",
        "minimum_history",
        "degraded",
        "sort(",
        "sorted(",
    ):
        assert forbidden not in source


def test_disposition_precedence_distinguishes_violation_from_missing_support() -> None:
    unable = validation._conclude(
        EvidenceValidationConcern.IDENTITY, [], ["mapping"], "unused"
    )
    rejected = validation._conclude(
        EvidenceValidationConcern.IDENTITY,
        ["wrong subject"],
        ["mapping"],
        "unused",
    )

    assert unable.disposition is EvidenceValidationDisposition.UNABLE_TO_VALIDATE
    assert rejected.disposition is EvidenceValidationDisposition.REJECTED
    assert unable.disposition is not EvidenceValidationDisposition.PASSED


def test_authentic_empty_material_retains_adverse_rejected_history() -> None:
    construction_service, constructed = _construction(rows=())
    service = _validation_service(construction_service, constructed)
    results = _by_concern(service.execute_profile(_request(constructed)))
    quality = results[EvidenceValidationConcern.SOURCE_QUALITY]

    assert (
        quality.validation_record.disposition is EvidenceValidationDisposition.REJECTED
    )
    assert service.get_validation_history(
        constructed.artifact.reference(),
        construction_execution_id=constructed.receipt.execution_id,
        concern=EvidenceValidationConcern.SOURCE_QUALITY,
    ) == (quality,)


def test_missing_platform_support_can_publish_unable_without_becoming_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    construction_service, constructed = _construction()
    original = validation._derive_support

    def without_mapping(
        result: PolygonCompletedDailyProductionConstructionResult,
    ) -> validation._ValidationSupport:
        return replace(original(result), mapping_resolution=None)

    monkeypatch.setattr(validation, "_derive_support", without_mapping)
    service = _validation_service(construction_service, constructed)
    results = _by_concern(service.execute_profile(_request(constructed)))

    assert (
        results[EvidenceValidationConcern.IDENTITY].validation_record.disposition
        is EvidenceValidationDisposition.UNABLE_TO_VALIDATE
    )
    assert (
        results[EvidenceValidationConcern.PROVENANCE].validation_record.disposition
        is EvidenceValidationDisposition.UNABLE_TO_VALIDATE
    )
    history = service.get_validation_history(
        constructed.artifact.reference(),
        construction_execution_id=constructed.receipt.execution_id,
        concern=EvidenceValidationConcern.IDENTITY,
    )
    assert history == (results[EvidenceValidationConcern.IDENTITY],)


def test_knowledge_cutoff_is_inclusive_and_returns_complete_concern_history() -> None:
    construction_service, constructed = _construction()
    service = _validation_service(construction_service, constructed)
    identity = _by_concern(service.execute_profile(_request(constructed)))[
        EvidenceValidationConcern.IDENTITY
    ]
    available = identity.companion.available_at
    kwargs = {
        "construction_execution_id": constructed.receipt.execution_id,
        "concern": EvidenceValidationConcern.IDENTITY,
    }

    assert (
        service.get_validation_history_as_of(
            constructed.artifact.reference(),
            knowledge_as_of=available - timedelta(microseconds=1),
            **kwargs,
        )
        == ()
    )
    assert service.get_validation_history_as_of(
        constructed.artifact.reference(), knowledge_as_of=available, **kwargs
    ) == (identity,)


def test_repeated_content_identical_records_have_distinct_execution_occurrences() -> (
    None
):
    construction_service, constructed = _construction()
    service = _validation_service(construction_service, constructed, constant=True)
    first = _by_concern(service.execute_profile(_request(constructed)))[
        EvidenceValidationConcern.IDENTITY
    ]
    second = _by_concern(service.execute_profile(_request(constructed)))[
        EvidenceValidationConcern.IDENTITY
    ]
    history = service.get_validation_history(
        constructed.artifact.reference(),
        construction_execution_id=constructed.receipt.execution_id,
        concern=EvidenceValidationConcern.IDENTITY,
    )

    assert first.validation_record == second.validation_record
    assert first.validation_record.fingerprint == second.validation_record.fingerprint
    assert first.companion.execution_id != second.companion.execution_id
    assert first.companion.history_sequence < second.companion.history_sequence
    assert history == (first, second)


def test_failed_final_publication_exposes_neither_record_nor_companion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    construction_service, constructed = _construction()
    service = _validation_service(construction_service, constructed)

    def fail_publication(
        self: validation._InMemoryPolygonCompletedDailyValidationHistory,
        staged: validation.PolygonCompletedDailyProductionValidationResult,
    ) -> None:
        self._pending = staged
        raise RuntimeError("simulated final publication failure")

    monkeypatch.setattr(
        validation._InMemoryPolygonCompletedDailyValidationHistory,
        "_stage_publication",
        fail_publication,
    )
    with pytest.raises(
        validation.PolygonCompletedDailyValidationExecutionRefused
    ) as raised:
        service.execute_profile(_request(constructed))

    assert (
        raised.value.reason
        is _REFUSAL.HISTORY_CONFLICT_OR_CORRUPTION
    )
    assert service._history._state[1] == ()
    assert service._history._pending is None


def test_backward_availability_fails_closed_without_exposing_failed_concern() -> None:
    construction_service, constructed = _construction()
    base = constructed.receipt.available_at + timedelta(minutes=1)
    clock = _Clock(
        base,
        base + timedelta(seconds=1),
        base + timedelta(seconds=10),
        base + timedelta(seconds=2),
        base + timedelta(seconds=3),
        base + timedelta(seconds=4),
    )
    service = validation.PolygonCompletedDailyProductionValidationApplicationService(
        construction_service, execution_clock=clock
    )

    with pytest.raises(
        validation.PolygonCompletedDailyValidationExecutionRefused
    ) as raised:
        service.execute_profile(_request(constructed))

    assert (
        raised.value.reason
        is _REFUSAL.TEMPORAL_EXECUTION_FAILURE
    )
    first_concern = _DEFINITIONS[0].requirement.concern
    second_concern = _DEFINITIONS[1].requirement.concern
    assert (
        len(
            service.get_validation_history(
                constructed.artifact.reference(),
                construction_execution_id=constructed.receipt.execution_id,
                concern=first_concern,
            )
        )
        == 1
    )
    assert (
        service.get_validation_history(
            constructed.artifact.reference(),
            construction_execution_id=constructed.receipt.execution_id,
            concern=second_concern,
        )
        == ()
    )


def test_untrusted_construction_occurrence_and_artifact_reference_are_refused() -> None:
    construction_service, constructed = _construction()
    service = _validation_service(construction_service, constructed)
    fake_id = "polygon_completed_daily_construction:" + ("0" * 32)

    with pytest.raises(
        validation.PolygonCompletedDailyValidationExecutionRefused
    ) as missing:
        service.execute_profile(
            validation.PolygonCompletedDailyValidationRequest(
                constructed.artifact.reference(), fake_id
            )
        )
    assert (
        missing.value.reason
        is _REFUSAL.TRUSTED_CONSTRUCTION_UNAVAILABLE
    )

    reference = constructed.artifact.reference()
    forged = evidence.EvidenceArtifactReference(
        artifact_id=reference.artifact_id,
        artifact_version=reference.artifact_version,
        artifact_fingerprint="sha256:" + ("0" * 64),
        information_class=reference.information_class,
        authority=reference.authority,
    )
    with pytest.raises(validation.PolygonCompletedDailyValidationExecutionRefused):
        service.execute_profile(
            validation.PolygonCompletedDailyValidationRequest(
                forged, constructed.receipt.execution_id
            )
        )


def test_history_and_result_types_cannot_be_imported_or_publicly_minted() -> None:
    construction_service, constructed = _construction()
    service = _validation_service(construction_service, constructed)

    with pytest.raises(TypeError, match="issued only"):
        validation.PolygonCompletedDailyValidationExecutionCompanion()
    with pytest.raises(TypeError, match="created only"):
        validation.PolygonCompletedDailyProductionValidationResult()
    for forbidden in ("append", "retain", "import_history", "import_record"):
        assert not hasattr(service, forbidden)


def test_history_detects_conflicting_or_corrupt_retained_outcomes() -> None:
    construction_service, constructed = _construction()
    service = _validation_service(construction_service, constructed)
    identity = _by_concern(service.execute_profile(_request(constructed)))[
        EvidenceValidationConcern.IDENTITY
    ]
    object.__setattr__(
        identity.validation_record,
        "disposition",
        EvidenceValidationDisposition.REJECTED,
    )

    with pytest.raises(validation.PolygonCompletedDailyValidationHistoryError):
        service.get_validation_history(
            constructed.artifact.reference(),
            construction_execution_id=constructed.receipt.execution_id,
            concern=EvidenceValidationConcern.IDENTITY,
        )


def test_slice_boundaries_and_frozen_public_identities_are_unchanged() -> None:
    source = Path(validation.__file__).read_text(encoding="utf-8")
    forbidden = (
        "create_evidence_admission_record",
        "create_evidence_validity_event",
        "evaluate_evidence_admission_as_of",
        "prepare_completed_daily_price_series",
        "CompletedDailyPriceSeries",
        "analyze_daily_technical_snapshot",
        "consumer qualification",
        "binary64 conversion",
    )

    assert all(item not in source for item in forbidden)
    assert (
        _POLYGON_COMPLETED_DAILY_PRODUCTION_PROFILE.fingerprint == _PROFILE_FINGERPRINT
    )
    assert (
        _POLYGON_COMPLETED_DAILY_PRODUCTION_PROFILE.construction_authorization.fingerprint
        == _AUTHORIZATION_FINGERPRINT
    )
    assert len(evidence.__all__) == 69
    assert tuple(evidence.__all__) == tuple(dict.fromkeys(evidence.__all__))


def test_validation_success_does_not_issue_other_lifecycle_or_use_authority() -> None:
    construction_service, constructed = _construction()
    result = _by_concern(
        _validation_service(construction_service, constructed).execute_profile(
            _request(constructed)
        )
    )[EvidenceValidationConcern.IDENTITY]
    forbidden = {
        "admission",
        "validity",
        "consumability",
        "consumable",
        "research_permission",
        "freshness_result",
    }

    assert result.validation_record.disposition is EvidenceValidationDisposition.PASSED
    assert forbidden.isdisjoint(result.validation_record.__dataclass_fields__)
    assert forbidden.isdisjoint(result.companion.__dataclass_fields__)


def test_freshness_true_and_construction_success_are_not_validation_authority() -> None:
    source = inspect.getsource(
        validation.PolygonCompletedDailyProductionValidationApplicationService
    )
    module_source = Path(validation.__file__).read_text(encoding="utf-8")

    assert "freshness" not in source.lower()
    assert "create_evidence_validation_record" in module_source
    assert "_evaluate_definition" in module_source
    assert "construction success" not in module_source.lower()


def test_actual_freshness_true_does_not_force_validation_pass() -> None:
    session = date(2026, 8, 28)
    construction_service, constructed = _construction(
        (_row(session, open_value="0", low="0"),)
    )
    freshness_start = constructed.receipt.available_at + timedelta(minutes=1)
    freshness_service = (
        freshness.PolygonCompletedDailyProductionFreshnessApplicationService(
            construction_service,
            execution_clock=_Clock(
                freshness_start,
                freshness_start + timedelta(seconds=1),
                freshness_start + timedelta(seconds=2),
            ),
        )
    )
    freshness_result = freshness_service.execute_task(
        freshness.PolygonCompletedDailyTaskFreshnessRequest(
            artifact_reference=constructed.artifact.reference(),
            construction_execution_id=constructed.receipt.execution_id,
            evaluation_as_of=_ny_instant(date(2026, 8, 30)),
        )
    )
    validation_results = _by_concern(
        _validation_service(
            construction_service,
            constructed,
            start=freshness_result.companion.available_at,
        ).execute_profile(_request(constructed))
    )

    assert freshness_result.freshness_record.result is True
    assert (
        validation_results[
            EvidenceValidationConcern.SOURCE_QUALITY
        ].validation_record.disposition
        is EvidenceValidationDisposition.REJECTED
    )
