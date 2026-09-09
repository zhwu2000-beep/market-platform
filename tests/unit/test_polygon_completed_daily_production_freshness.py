from __future__ import annotations

import asyncio
import inspect
from dataclasses import FrozenInstanceError, fields, replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import market_platform.evidence as evidence
import market_platform.evidence.temporal as evidence_temporal
from market_platform.application import (
    polygon_completed_daily_production_freshness as freshness,
)
from market_platform.application.polygon_completed_daily_evidence_candidate import (
    PolygonCompletedDailyEvidenceCandidateApplicationRequest,
)
from market_platform.application.polygon_completed_daily_production_construction import (  # noqa: E501
    PolygonCompletedDailyProductionConstructionApplicationService,
    PolygonCompletedDailyProductionConstructionResult,
)
from market_platform.data.providers.polygon import (
    PolygonCompletedDailyAcquisition,
    PolygonCompletedDailyAggregate,
)
from market_platform.evidence import evaluation as evidence_evaluation
from market_platform.evidence.temporal import (
    EvidenceFreshnessRule,
    create_evidence_freshness_evaluation_record,
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
_SUPERSEDED_PROFILE_FINGERPRINT = (
    "sha256:6bff0d17036920f657e44816f434ca357c803d99d77a06bd877b3c00aa64036f"
)
_AUTHORIZATION_FINGERPRINT = (
    "sha256:e9d8057dde8e20c5fb297ea08be7bcc723131cea42fab0e8a528f5b40c343387"
)


class _Clock:
    def __init__(self, *values: datetime) -> None:
        self._values = iter(values)
        self.calls = 0

    def __call__(self) -> datetime:
        self.calls += 1
        return next(self._values)


class _Acquirer:
    def __init__(self, acquisition: PolygonCompletedDailyAcquisition) -> None:
        self.acquisition = acquisition
        self.calls = 0

    async def get_completed_daily_acquisition(
        self,
        ticker: str,
        start: date,
        end: date,
    ) -> PolygonCompletedDailyAcquisition:
        self.calls += 1
        return self.acquisition


def _ny_instant(session_date: date, hour: int = 12) -> datetime:
    return datetime.combine(
        session_date,
        time(hour=hour),
        tzinfo=_NY,
    ).astimezone(UTC)


def _unix_milliseconds(session_date: date) -> int:
    instant = _ny_instant(session_date)
    return (instant - _EPOCH) // timedelta(milliseconds=1)


def _row(session_date: date) -> PolygonCompletedDailyAggregate:
    return PolygonCompletedDailyAggregate(
        timestamp=_unix_milliseconds(session_date),
        open=Decimal("100.00"),
        high=Decimal("102.00"),
        low=Decimal("99.00"),
        close=Decimal("101.00"),
        volume=Decimal("1000.00"),
    )


def _external() -> ExternalInstrumentIdentity:
    return ExternalInstrumentIdentity("polygon", "AAPL", "NASDAQ")


def _mapping() -> InstrumentMapping:
    return InstrumentMapping(
        _external(),
        CanonicalInstrument(
            CanonicalInstrumentId("us_equity.AAPL"),
            TradingInstrumentIdentity("AAPL", "NASDAQ"),
            InstrumentAssetClass.EQUITY,
            "USD",
        ),
        InstrumentMappingSourceIdentity("operator_registry", "1.0.0"),
        datetime(2020, 1, 1, tzinfo=UTC),
    )


def _construction(
    session_dates: tuple[date, ...],
    *,
    requested_from: date | None = None,
    requested_to: date | None = None,
) -> tuple[
    PolygonCompletedDailyProductionConstructionApplicationService,
    PolygonCompletedDailyProductionConstructionResult,
]:
    start_date = (
        requested_from
        if requested_from is not None
        else (min(session_dates) if session_dates else date(2026, 8, 20))
    )
    end_date = (
        requested_to
        if requested_to is not None
        else (max(session_dates) if session_dates else date(2026, 8, 28))
    )
    query_as_of = _ny_instant(end_date + timedelta(days=1))
    response_received_at = query_as_of + timedelta(minutes=1)
    artifact_created_at = query_as_of + timedelta(minutes=2)
    rows = tuple(_row(item) for item in reversed(session_dates))
    acquisition = PolygonCompletedDailyAcquisition(
        requested_ticker="AAPL",
        requested_from=start_date.isoformat(),
        requested_to=end_date.isoformat(),
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
        response_received_at=response_received_at,
    )
    service = PolygonCompletedDailyProductionConstructionApplicationService(
        _Acquirer(acquisition),
        creation_clock=lambda: artifact_created_at,
        execution_clock=_Clock(
            query_as_of,
            query_as_of + timedelta(minutes=3),
            query_as_of + timedelta(minutes=4),
        ),
    )
    request = PolygonCompletedDailyEvidenceCandidateApplicationRequest(
        external_identity=_external(),
        mappings=(_mapping(),),
        requested_from=start_date,
        requested_to=end_date,
        query_as_of=query_as_of,
    )
    result = asyncio.run(service.execute(request))
    return service, result


def _task_service(
    construction_service: PolygonCompletedDailyProductionConstructionApplicationService,
    construction_result: PolygonCompletedDailyProductionConstructionResult,
    *,
    execution_times: tuple[datetime, ...] | None = None,
) -> freshness.PolygonCompletedDailyProductionFreshnessApplicationService:
    if execution_times is None:
        started = construction_result.receipt.available_at + timedelta(days=10)
        execution_times = (
            started,
            started + timedelta(minutes=1),
            started + timedelta(minutes=2),
        )
    return freshness.PolygonCompletedDailyProductionFreshnessApplicationService(
        construction_service,
        execution_clock=_Clock(*execution_times),
    )


def _task_request(
    construction_result: PolygonCompletedDailyProductionConstructionResult,
    evaluation_as_of: datetime,
) -> freshness.PolygonCompletedDailyTaskFreshnessRequest:
    return freshness.PolygonCompletedDailyTaskFreshnessRequest(
        artifact_reference=construction_result.artifact.reference(),
        construction_execution_id=construction_result.receipt.execution_id,
        evaluation_as_of=evaluation_as_of,
    )


def _execute_task(
    session_dates: tuple[date, ...],
    evaluation_as_of: datetime,
    *,
    requested_from: date | None = None,
    requested_to: date | None = None,
) -> freshness.PolygonCompletedDailyProductionFreshnessResult:
    construction_service, construction_result = _construction(
        session_dates,
        requested_from=requested_from,
        requested_to=requested_to,
    )
    service = _task_service(construction_service, construction_result)
    return service.execute_task(_task_request(construction_result, evaluation_as_of))


def _fake_construction_execution_id() -> str:
    return "polygon_completed_daily_construction:" + ("0" * 32)


def test_admission_and_task_use_exact_distinct_approved_rules() -> None:
    construction_service, construction_result = _construction((date(2026, 8, 28),))
    start = construction_result.receipt.available_at + timedelta(hours=1)
    clock = _Clock(
        start,
        start + timedelta(minutes=1),
        start + timedelta(minutes=2),
        start + timedelta(minutes=3),
        start + timedelta(minutes=4),
        start + timedelta(minutes=5),
        start + timedelta(minutes=6),
    )
    service = freshness.PolygonCompletedDailyProductionFreshnessApplicationService(
        construction_service,
        execution_clock=clock,
    )
    admission = service.execute_admission(
        freshness.PolygonCompletedDailyAdmissionFreshnessRequest(
            artifact_reference=construction_result.artifact.reference(),
            construction_execution_id=construction_result.receipt.execution_id,
        )
    )
    task = service.execute_task(
        _task_request(construction_result, start + timedelta(minutes=4))
    )

    assert admission.freshness_record.freshness_rule == (
        freshness._PROFILE.admission_freshness.rule
    )
    assert task.freshness_record.freshness_rule == (
        freshness._PROFILE.task_freshness.rule
    )
    assert admission.freshness_record.freshness_rule.rule_id == (
        "production.polygon_completed_daily.freshness.admission"
    )
    assert task.freshness_record.freshness_rule.rule_id == (
        "production.polygon_completed_daily.freshness.daily_technical"
    )
    assert (
        admission.freshness_record.freshness_rule.declared_temporal_anchor
        == "observation_period_end"
    )
    assert (
        task.freshness_record.freshness_rule.declared_temporal_anchor
        == "observation_period_end"
    )
    assert admission.freshness_record.freshness_rule != (
        task.freshness_record.freshness_rule
    )
    assert admission.companion.freshness_definition_fingerprint == (
        freshness._PROFILE.admission_freshness.fingerprint
    )
    assert task.companion.freshness_definition_fingerprint == (
        freshness._PROFILE.task_freshness.fingerprint
    )
    assert admission.companion.operation != task.companion.operation
    assert (
        freshness._PROFILE.admission_freshness._configuration_payload()
        == freshness._PROFILE.task_freshness._configuration_payload()
    )
    configuration = freshness._PROFILE.admission_freshness._configuration_payload()
    assert configuration["market_timezone"] == "America/New_York"
    assert configuration["expected_session_calendar"] is None
    assert configuration["publication_time_inference"] == "prohibited"
    assert configuration["holiday_exception_extension"] is None
    assert configuration["minimum_calendar_lag_days"] == 1
    assert configuration["maximum_calendar_lag_days"] == 4
    assert service.get_admission_freshness_history(
        construction_result.artifact.reference(),
        construction_execution_id=construction_result.receipt.execution_id,
    ) == (admission,)
    assert service.get_task_freshness_history(
        construction_result.artifact.reference(),
        construction_execution_id=construction_result.receipt.execution_id,
    ) == (task,)


def test_requests_expose_no_policy_result_availability_or_history_authority() -> None:
    admission_fields = set(
        freshness.PolygonCompletedDailyAdmissionFreshnessRequest.__dataclass_fields__
    )
    task_fields = set(
        freshness.PolygonCompletedDailyTaskFreshnessRequest.__dataclass_fields__
    )
    forbidden = {
        "available_at",
        "calendar",
        "calendar_lag_days",
        "companion",
        "freshness_record",
        "freshness_result",
        "freshness_rule",
        "history",
        "material",
        "predicate",
        "production_profile",
        "result",
        "threshold",
        "timezone",
    }

    assert admission_fields == {"artifact_reference", "construction_execution_id"}
    assert task_fields == {
        "artifact_reference",
        "construction_execution_id",
        "evaluation_as_of",
    }
    assert forbidden.isdisjoint(admission_fields | task_fields)
    assert "evaluation_as_of" not in admission_fields


def test_lookalike_policy_and_companion_bindings_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    construction_service, construction_result = _construction((date(2026, 8, 28),))
    service = _task_service(construction_service, construction_result)
    lookalike_rule = EvidenceFreshnessRule(
        rule_id=freshness._TASK_DEFINITION.rule.rule_id,
        rule_version=freshness._TASK_DEFINITION.rule.rule_version,
        declared_temporal_anchor=freshness._TASK_DEFINITION.rule.declared_temporal_anchor,
        evaluation_scope="research.daily_technical.lookalike",
    )
    monkeypatch.setattr(
        freshness,
        "_TASK_DEFINITION",
        replace(freshness._TASK_DEFINITION, rule=lookalike_rule),
    )

    with pytest.raises(
        freshness.PolygonCompletedDailyFreshnessExecutionRefused
    ) as raised:
        service.execute_task(
            _task_request(construction_result, _ny_instant(date(2026, 9, 1)))
        )

    assert raised.value.reason is (
        freshness.PolygonCompletedDailyFreshnessRefusalReason.POLICY_RULE_MISMATCH
    )
    assert (
        service.get_task_freshness_history(
            construction_result.artifact.reference(),
            construction_execution_id=construction_result.receipt.execution_id,
        )
        == ()
    )


@pytest.mark.parametrize(
    ("lag_days", "expected"),
    ((1, True), (4, True), (5, False)),
)
def test_calendar_lag_boundaries_are_inclusive(
    lag_days: int,
    expected: bool,
) -> None:
    evaluation_date = date(2026, 9, 10)
    latest = evaluation_date - timedelta(days=lag_days)

    result = _execute_task(
        (latest,),
        _ny_instant(evaluation_date),
    )

    assert result.freshness_record.result is expected
    assert result.freshness_record.evaluated_temporal_values == (
        (
            "observation_period_end",
            result.artifact.temporal_identity.observation_period_end,
        ),
    )
    assert result.companion.result is expected
    assert result.companion.calendar_lag_days == lag_days
    assert result.companion.latest_eligible_completed_session_date == latest


@pytest.mark.parametrize(
    ("evaluation_date", "expected"),
    (
        (date(2026, 8, 29), True),
        (date(2026, 8, 30), True),
        (date(2026, 8, 31), True),
        (date(2026, 9, 1), True),
        (date(2026, 9, 2), False),
    ),
)
def test_friday_material_uses_calendar_days_without_exchange_calendar(
    evaluation_date: date,
    expected: bool,
) -> None:
    result = _execute_task(
        (date(2026, 8, 28),),
        _ny_instant(evaluation_date),
    )

    assert result.freshness_record.result is expected
    assert (
        result.companion.calendar_lag_days == (evaluation_date - date(2026, 8, 28)).days
    )


def test_new_york_civil_date_changes_exactly_at_utc_boundary() -> None:
    before_midnight = _execute_task(
        (date(2026, 8, 28),),
        datetime(2026, 9, 2, 3, 59, tzinfo=UTC),
    )
    at_midnight = _execute_task(
        (date(2026, 8, 28),),
        datetime(2026, 9, 2, 4, 0, tzinfo=UTC),
    )

    assert before_midnight.companion.new_york_evaluation_date == date(2026, 9, 1)
    assert before_midnight.companion.calendar_lag_days == 4
    assert before_midnight.freshness_record.result is True
    assert at_midnight.companion.new_york_evaluation_date == date(2026, 9, 2)
    assert at_midnight.companion.calendar_lag_days == 5
    assert at_midnight.freshness_record.result is False


def test_requested_observation_end_is_not_latest_retained_session() -> None:
    result = _execute_task(
        (date(2026, 8, 28),),
        _ny_instant(date(2026, 9, 2)),
        requested_from=date(2026, 8, 20),
        requested_to=date(2026, 9, 1),
    )
    temporal = result.artifact.temporal_identity

    assert result.freshness_record.result is False
    assert result.companion.latest_retained_session_date == date(2026, 8, 28)
    assert result.companion.latest_eligible_completed_session_date == (
        date(2026, 8, 28)
    )
    assert result.companion.calendar_lag_days == 5
    assert result.companion.observation_period_end == (temporal.observation_period_end)
    assert dict(result.freshness_record.evaluated_temporal_values) == {
        "observation_period_end": temporal.observation_period_end
    }
    assert datetime(2026, 8, 28, tzinfo=UTC) not in (
        dict(result.freshness_record.evaluated_temporal_values).values()
    )


def test_sparse_history_passes_when_latest_session_is_recent() -> None:
    result = _execute_task(
        (date(2026, 8, 1), date(2026, 8, 28)),
        _ny_instant(date(2026, 9, 1)),
        requested_from=date(2026, 8, 1),
    )

    assert result.freshness_record.result is True
    assert result.companion.retained_material_row_count == 2
    assert result.companion.first_retained_session_date == date(2026, 8, 1)
    assert result.companion.latest_retained_session_date == date(2026, 8, 28)
    assert result.companion.eligible_completed_session_count == 2
    assert result.companion.calendar_lag_days == 4


def test_authentic_empty_material_is_established_no_session_failure() -> None:
    result = _execute_task((), _ny_instant(date(2026, 9, 1)))

    assert result.freshness_record.result is False
    assert result.freshness_record.evaluated_temporal_values == (
        (
            "observation_period_end",
            result.artifact.temporal_identity.observation_period_end,
        ),
    )
    assert result.companion.outcome is (
        freshness.PolygonCompletedDailyFreshnessOutcome.NO_ELIGIBLE_RETAINED_COMPLETED_SESSION
    )
    assert result.companion.retained_material_row_count == 0
    assert result.companion.first_retained_session_date is None
    assert result.companion.latest_retained_session_date is None
    assert result.companion.eligible_completed_session_count == 0
    assert result.companion.latest_eligible_completed_session_date is None
    assert result.companion.calendar_lag_days is None
    assert "No eligible retained" in result.freshness_record.findings[0]


def test_nonempty_material_with_no_eligible_session_is_established_failure() -> None:
    result = _execute_task(
        (date(2026, 8, 28),),
        _ny_instant(date(2026, 8, 28)),
    )

    assert result.companion.retained_material_row_count == 1
    assert result.companion.latest_retained_session_date == date(2026, 8, 28)
    assert result.companion.eligible_completed_session_count == 0
    assert result.companion.latest_eligible_completed_session_date is None
    assert result.companion.outcome is (
        freshness.PolygonCompletedDailyFreshnessOutcome.NO_ELIGIBLE_RETAINED_COMPLETED_SESSION
    )
    assert result.freshness_record.result is False
    assert result.freshness_record.evaluated_temporal_values == (
        (
            "observation_period_end",
            result.artifact.temporal_identity.observation_period_end,
        ),
    )


def test_missing_exact_construction_occurrence_refuses_without_record() -> None:
    construction_service, construction_result = _construction((date(2026, 8, 28),))
    service = _task_service(construction_service, construction_result)
    request = freshness.PolygonCompletedDailyTaskFreshnessRequest(
        artifact_reference=construction_result.artifact.reference(),
        construction_execution_id=_fake_construction_execution_id(),
        evaluation_as_of=_ny_instant(date(2026, 9, 1)),
    )

    with pytest.raises(
        freshness.PolygonCompletedDailyFreshnessExecutionRefused
    ) as raised:
        service.execute_task(request)

    assert raised.value.reason is (
        freshness.PolygonCompletedDailyFreshnessRefusalReason.TRUSTED_CONSTRUCTION_UNAVAILABLE
    )
    assert (
        service.get_task_freshness_history(
            construction_result.artifact.reference(),
            construction_execution_id=construction_result.receipt.execution_id,
        )
        == ()
    )


def test_material_artifact_corruption_refuses_without_freshness_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    construction_service, construction_result = _construction((date(2026, 8, 28),))
    service = _task_service(construction_service, construction_result)
    request = _task_request(
        construction_result,
        _ny_instant(date(2026, 9, 1)),
    )
    object.__setattr__(
        construction_result.material,
        "fingerprint",
        "sha256:" + ("0" * 64),
    )
    monkeypatch.setattr(
        PolygonCompletedDailyProductionConstructionApplicationService,
        "get_construction_history",
        lambda self, artifact_reference: (construction_result,),
    )

    with pytest.raises(
        freshness.PolygonCompletedDailyFreshnessExecutionRefused
    ) as raised:
        service.execute_task(request)

    assert raised.value.reason is (
        freshness.PolygonCompletedDailyFreshnessRefusalReason.ARTIFACT_MATERIAL_MISMATCH
    )
    assert service._history._state[1] == ()


def test_admission_evaluation_time_is_captured_by_platform_clock() -> None:
    construction_service, construction_result = _construction((date(2026, 8, 28),))
    started = datetime(2026, 8, 29, 17, 0, tzinfo=UTC)
    evaluated = started + timedelta(minutes=1)
    completed = started + timedelta(minutes=2)
    available = started + timedelta(minutes=3)
    clock = _Clock(started, evaluated, completed, available)
    service = freshness.PolygonCompletedDailyProductionFreshnessApplicationService(
        construction_service,
        execution_clock=clock,
    )
    request = freshness.PolygonCompletedDailyAdmissionFreshnessRequest(
        artifact_reference=construction_result.artifact.reference(),
        construction_execution_id=construction_result.receipt.execution_id,
    )

    result = service.execute_admission(request)

    assert clock.calls == 4
    assert result.freshness_record.evaluation_as_of == evaluated
    assert result.companion.evaluation_as_of == evaluated
    assert result.companion.execution_started_at == started
    assert result.companion.execution_completed_at == completed
    assert result.companion.available_at == available
    assert result.companion.execution_kind is (
        freshness.PolygonCompletedDailyFreshnessExecutionKind.ADMISSION
    )


def test_freshness_cannot_start_before_construction_is_available() -> None:
    construction_service, construction_result = _construction((date(2026, 8, 28),))
    too_early = construction_result.receipt.available_at - timedelta(microseconds=1)
    service = _task_service(
        construction_service,
        construction_result,
        execution_times=(
            too_early,
            too_early + timedelta(seconds=1),
            too_early + timedelta(seconds=2),
        ),
    )

    with pytest.raises(
        freshness.PolygonCompletedDailyFreshnessExecutionRefused
    ) as raised:
        service.execute_task(
            _task_request(construction_result, _ny_instant(date(2026, 9, 1)))
        )

    assert raised.value.reason is (
        freshness.PolygonCompletedDailyFreshnessRefusalReason.TEMPORAL_EXECUTION_FAILURE
    )
    assert service._history._state[1] == ()


def test_task_evaluation_uses_declared_permitted_historical_instant() -> None:
    construction_service, construction_result = _construction((date(2026, 8, 28),))
    historical = _ny_instant(date(2026, 9, 1))
    service = _task_service(construction_service, construction_result)

    result = service.execute_task(_task_request(construction_result, historical))

    assert result.freshness_record.evaluation_as_of == historical
    assert result.companion.evaluation_as_of == historical
    assert result.companion.execution_kind is (
        freshness.PolygonCompletedDailyFreshnessExecutionKind.DAILY_TECHNICAL
    )
    assert result.companion.freshness_rule == (freshness._PROFILE.task_freshness.rule)


def test_retrospective_evaluation_is_not_backdated_availability() -> None:
    construction_service, construction_result = _construction((date(2026, 8, 28),))
    historical = _ny_instant(date(2026, 9, 1))
    started = datetime(2026, 9, 10, 12, tzinfo=UTC)
    completed = started + timedelta(minutes=1)
    available = started + timedelta(minutes=2)
    service = _task_service(
        construction_service,
        construction_result,
        execution_times=(started, completed, available),
    )

    result = service.execute_task(_task_request(construction_result, historical))
    immediately_before = available - timedelta(microseconds=1)

    assert result.companion.evaluation_as_of == historical
    assert result.companion.available_at == available
    assert result.companion.available_at > result.companion.evaluation_as_of
    assert (
        service.get_task_freshness_history_as_of(
            construction_result.artifact.reference(),
            construction_execution_id=construction_result.receipt.execution_id,
            knowledge_as_of=historical,
        )
        == ()
    )
    assert (
        service.get_task_freshness_history_as_of(
            construction_result.artifact.reference(),
            construction_execution_id=construction_result.receipt.execution_id,
            knowledge_as_of=immediately_before,
        )
        == ()
    )
    assert service.get_task_freshness_history_as_of(
        construction_result.artifact.reference(),
        construction_execution_id=construction_result.receipt.execution_id,
        knowledge_as_of=available,
    ) == (result,)


def test_pending_stage_is_not_query_visible_before_final_publication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    construction_service, construction_result = _construction((date(2026, 8, 28),))
    service = _task_service(construction_service, construction_result)
    observed_published: list[
        tuple[freshness.PolygonCompletedDailyProductionFreshnessResult, ...]
    ] = []
    history_type = freshness._InMemoryPolygonCompletedDailyFreshnessHistory
    original = history_type._stage_publication

    def observe_hidden_stage(
        history: freshness._InMemoryPolygonCompletedDailyFreshnessHistory,
        staged: freshness.PolygonCompletedDailyProductionFreshnessResult,
    ) -> None:
        observed_published.append(history._state[1])
        original(history, staged)

    monkeypatch.setattr(history_type, "_stage_publication", observe_hidden_stage)

    result = service.execute_task(
        _task_request(construction_result, _ny_instant(date(2026, 9, 1)))
    )

    assert observed_published == [()]
    assert service._history._pending is None
    assert service.get_task_freshness_history(
        construction_result.artifact.reference(),
        construction_execution_id=construction_result.receipt.execution_id,
    ) == (result,)


def test_failed_final_publication_exposes_neither_record_nor_companion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    construction_service, construction_result = _construction((date(2026, 8, 28),))
    service = _task_service(construction_service, construction_result)

    def fail_publication(
        history: freshness._InMemoryPolygonCompletedDailyFreshnessHistory,
        staged: freshness.PolygonCompletedDailyProductionFreshnessResult,
    ) -> None:
        history._pending = staged
        raise RuntimeError("simulated final publication failure")

    monkeypatch.setattr(
        freshness._InMemoryPolygonCompletedDailyFreshnessHistory,
        "_stage_publication",
        fail_publication,
    )

    with pytest.raises(
        freshness.PolygonCompletedDailyFreshnessExecutionRefused
    ) as raised:
        service.execute_task(
            _task_request(construction_result, _ny_instant(date(2026, 9, 1)))
        )

    assert raised.value.reason is (
        freshness.PolygonCompletedDailyFreshnessRefusalReason.HISTORY_CONFLICT_OR_CORRUPTION
    )
    assert service._history._pending is None
    assert service._history._state[1] == ()
    assert (
        service.get_task_freshness_history(
            construction_result.artifact.reference(),
            construction_execution_id=construction_result.receipt.execution_id,
        )
        == ()
    )


def test_failed_final_binding_after_availability_capture_is_not_published(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    construction_service, construction_result = _construction((date(2026, 8, 28),))
    started = datetime(2026, 9, 10, 12, tzinfo=UTC)
    clock = _Clock(
        started,
        started + timedelta(minutes=1),
        started + timedelta(minutes=2),
    )
    service = freshness.PolygonCompletedDailyProductionFreshnessApplicationService(
        construction_service,
        execution_clock=clock,
    )

    def fail_final_binding(
        cls: type[freshness.PolygonCompletedDailyFreshnessExecutionCompanion],
        staged: freshness.PolygonCompletedDailyFreshnessExecutionCompanion,
        *,
        available_at: datetime,
        seal: object,
    ) -> freshness.PolygonCompletedDailyFreshnessExecutionCompanion:
        del cls, staged, available_at, seal
        raise RuntimeError("simulated final binding failure")

    monkeypatch.setattr(
        freshness.PolygonCompletedDailyFreshnessExecutionCompanion,
        "_with_available_at",
        classmethod(fail_final_binding),
    )

    with pytest.raises(
        freshness.PolygonCompletedDailyFreshnessExecutionRefused
    ) as raised:
        service.execute_task(
            _task_request(construction_result, _ny_instant(date(2026, 9, 1)))
        )

    assert clock.calls == 3
    assert raised.value.reason is (
        freshness.PolygonCompletedDailyFreshnessRefusalReason.HISTORY_CONFLICT_OR_CORRUPTION
    )
    assert service._history._pending is None
    assert service._history._state[1] == ()


def test_backward_availability_fails_closed_without_manufactured_monotonicity() -> None:
    construction_service, construction_result = _construction((date(2026, 8, 28),))
    first_started = datetime(2026, 9, 10, 12, tzinfo=UTC)
    second_started = datetime(2026, 9, 9, 12, tzinfo=UTC)
    clock = _Clock(
        first_started,
        first_started + timedelta(minutes=1),
        first_started + timedelta(minutes=2),
        second_started,
        second_started + timedelta(minutes=1),
        second_started + timedelta(minutes=2),
    )
    service = freshness.PolygonCompletedDailyProductionFreshnessApplicationService(
        construction_service,
        execution_clock=clock,
    )
    request = _task_request(
        construction_result,
        _ny_instant(date(2026, 9, 1)),
    )
    first = service.execute_task(request)

    with pytest.raises(
        freshness.PolygonCompletedDailyFreshnessExecutionRefused
    ) as raised:
        service.execute_task(request)

    assert raised.value.reason is (
        freshness.PolygonCompletedDailyFreshnessRefusalReason.TEMPORAL_EXECUTION_FAILURE
    )
    assert service.get_task_freshness_history(
        construction_result.artifact.reference(),
        construction_execution_id=construction_result.receipt.execution_id,
    ) == (first,)


def test_repeated_execution_retains_distinct_companions_for_one_record_identity() -> (
    None
):
    construction_service, construction_result = _construction((date(2026, 8, 28),))
    first_started = datetime(2026, 9, 10, 12, tzinfo=UTC)
    second_started = datetime(2026, 9, 10, 13, tzinfo=UTC)
    service = freshness.PolygonCompletedDailyProductionFreshnessApplicationService(
        construction_service,
        execution_clock=_Clock(
            first_started,
            first_started + timedelta(minutes=1),
            first_started + timedelta(minutes=2),
            second_started,
            second_started + timedelta(minutes=1),
            second_started + timedelta(minutes=2),
        ),
    )
    request = _task_request(
        construction_result,
        _ny_instant(date(2026, 9, 1)),
    )

    first = service.execute_task(request)
    second = service.execute_task(request)
    history = service.get_task_freshness_history(
        construction_result.artifact.reference(),
        construction_execution_id=construction_result.receipt.execution_id,
    )

    assert history == (first, second)
    assert first.freshness_record == second.freshness_record
    assert first.freshness_record.fingerprint == second.freshness_record.fingerprint
    assert first.companion.execution_id != second.companion.execution_id
    assert first.companion.history_sequence == 1
    assert second.companion.history_sequence == 2
    assert first.companion.fingerprint != second.companion.fingerprint


def test_history_retains_adverse_false_execution_without_favorable_selection() -> None:
    construction_service, construction_result = _construction((date(2026, 8, 28),))
    first_started = datetime(2026, 9, 10, 12, tzinfo=UTC)
    second_started = datetime(2026, 9, 10, 13, tzinfo=UTC)
    service = freshness.PolygonCompletedDailyProductionFreshnessApplicationService(
        construction_service,
        execution_clock=_Clock(
            first_started,
            first_started + timedelta(minutes=1),
            first_started + timedelta(minutes=2),
            second_started,
            second_started + timedelta(minutes=1),
            second_started + timedelta(minutes=2),
        ),
    )

    passed = service.execute_task(
        _task_request(construction_result, _ny_instant(date(2026, 9, 1)))
    )
    failed = service.execute_task(
        _task_request(construction_result, _ny_instant(date(2026, 9, 2)))
    )
    history = service.get_task_freshness_history(
        construction_result.artifact.reference(),
        construction_execution_id=construction_result.receipt.execution_id,
    )

    assert history == (passed, failed)
    assert tuple(item.freshness_record.result for item in history) == (True, False)
    assert failed.companion.outcome is (
        freshness.PolygonCompletedDailyFreshnessOutcome.STALE_CALENDAR_LAG
    )


def test_caller_cannot_mint_or_append_companion_record_or_history() -> None:
    construction_service, construction_result = _construction((date(2026, 8, 28),))
    service = _task_service(construction_service, construction_result)

    with pytest.raises(TypeError, match="issued only"):
        freshness.PolygonCompletedDailyFreshnessExecutionCompanion()
    with pytest.raises(TypeError, match="created only"):
        freshness.PolygonCompletedDailyProductionFreshnessResult()
    with pytest.raises(TypeError, match="retention is private"):
        service._history._retain(
            execution_id="polygon_completed_daily_freshness:" + ("0" * 32),
            execution_kind=(
                freshness.PolygonCompletedDailyFreshnessExecutionKind.DAILY_TECHNICAL
            ),
            construction_result=construction_result,
            freshness_definition=freshness._TASK_DEFINITION,
            freshness_record=object(),  # type: ignore[arg-type]
            support=object(),  # type: ignore[arg-type]
            execution_started_at=datetime(2026, 9, 10, tzinfo=UTC),
            completion_clock=lambda: datetime(2026, 9, 10, tzinfo=UTC),
            availability_clock=lambda: datetime(2026, 9, 10, tzinfo=UTC),
            seal=object(),
        )

    assert not hasattr(service, "append")
    assert not hasattr(service, "import_history")
    assert service._history._state[1] == ()


def test_caller_created_lifecycle_record_is_not_trusted_freshness_history() -> None:
    construction_service, construction_result = _construction((date(2026, 8, 28),))
    service = _task_service(construction_service, construction_result)
    lookalike_rule = EvidenceFreshnessRule(
        rule_id="caller.lookalike",
        rule_version="1.0.0",
        declared_temporal_anchor="observation_period",
        evaluation_scope="research.daily_technical.completed_daily",
    )
    caller_record = create_evidence_freshness_evaluation_record(
        artifact=construction_result.artifact,
        freshness_rule=lookalike_rule,
        evaluation_as_of=_ny_instant(date(2026, 9, 1)),
        result=True,
        findings=("Caller-selected favorable result.",),
    )

    with pytest.raises(TypeError, match="exact PolygonCompletedDailyTask"):
        service.execute_task(caller_record)  # type: ignore[arg-type]

    assert (
        service.get_task_freshness_history(
            construction_result.artifact.reference(),
            construction_execution_id=construction_result.receipt.execution_id,
        )
        == ()
    )


def test_conflicting_or_incomplete_retained_history_fails_closed() -> None:
    construction_service, construction_result = _construction((date(2026, 8, 28),))
    service = _task_service(construction_service, construction_result)
    result = service.execute_task(
        _task_request(construction_result, _ny_instant(date(2026, 9, 1)))
    )
    service._history._state = (3, (result, result))

    with pytest.raises(freshness.PolygonCompletedDailyFreshnessHistoryError):
        service.get_task_freshness_history(
            construction_result.artifact.reference(),
            construction_execution_id=construction_result.receipt.execution_id,
        )


def test_companion_binds_exact_construction_material_record_and_profile() -> None:
    construction_service, construction_result = _construction(
        (date(2026, 8, 25), date(2026, 8, 28)),
    )
    service = _task_service(construction_service, construction_result)
    result = service.execute_task(
        _task_request(construction_result, _ny_instant(date(2026, 9, 1)))
    )
    companion = result.companion

    assert result.construction_result is construction_result
    assert result.artifact is construction_result.artifact
    assert result.material is construction_result.material
    assert companion.schema_version == (
        "polygon_completed_daily_freshness_execution/v1"
    )
    assert companion.construction_history_namespace_id == (
        construction_result.receipt.history_namespace_id
    )
    assert companion.construction_history_sequence == (
        construction_result.receipt.history_sequence
    )
    assert companion.construction_execution_id == (
        construction_result.receipt.execution_id
    )
    assert companion.construction_receipt_fingerprint == (
        construction_result.receipt.fingerprint
    )
    assert companion.artifact_reference == construction_result.artifact.reference()
    assert companion.material_fingerprint == construction_result.material.fingerprint
    assert companion.production_profile_fingerprint == _PROFILE_FINGERPRINT
    assert companion.freshness_evaluation_reference == (
        result.freshness_record.reference()
    )
    assert companion.result is result.freshness_record.result
    assert companion.executor.identity_id == "market_platform"
    assert companion.executor.identity_version == "0.1.0"
    projection = companion.to_dict()
    assert projection["fingerprint"] == companion.fingerprint
    assert not hasattr(companion, "__dict__")
    with pytest.raises(FrozenInstanceError):
        companion.result = False  # type: ignore[misc]


def test_companion_tampering_and_mismatched_record_fail_closed() -> None:
    construction_service, construction_result = _construction((date(2026, 8, 28),))
    service = _task_service(construction_service, construction_result)
    result = service.execute_task(
        _task_request(construction_result, _ny_instant(date(2026, 9, 1)))
    )

    object.__setattr__(
        result.companion,
        "material_fingerprint",
        "sha256:" + ("0" * 64),
    )
    with pytest.raises(ValueError):
        result._validate()
    with pytest.raises(freshness.PolygonCompletedDailyFreshnessHistoryError):
        service.get_task_freshness_history(
            construction_result.artifact.reference(),
            construction_execution_id=construction_result.receipt.execution_id,
        )


def test_public_freshness_factory_remains_artifact_anchored_and_unchanged() -> None:
    construction_service, construction_result = _construction((date(2026, 8, 28),))
    del construction_service
    parameters = inspect.signature(
        create_evidence_freshness_evaluation_record
    ).parameters

    assert tuple(parameters) == (
        "artifact",
        "freshness_rule",
        "evaluation_as_of",
        "result",
        "findings",
    )
    record = create_evidence_freshness_evaluation_record(
        artifact=construction_result.artifact,
        freshness_rule=freshness._PROFILE.task_freshness.rule,
        evaluation_as_of=_ny_instant(date(2026, 9, 1)),
        result=False,
        findings=("No eligible session.",),
    )

    assert record.evaluated_temporal_values == (
        (
            "observation_period_end",
            construction_result.artifact.temporal_identity.observation_period_end,
        ),
    )
    assert (
        evidence_evaluation._freshness_correspondence_failure(
            construction_result.artifact,
            record,
            "Task-time",
        )
        is None
    )
    assert not hasattr(
        evidence_temporal,
        "_create_retained_freshness_evaluation_record",
    )
    source = Path(freshness.__file__).read_text(encoding="utf-8")
    assert "create_evidence_freshness_evaluation_record(" in source
    assert "EvidenceFreshnessEvaluationRecord._create" not in source
    assert "_create_retained_freshness_evaluation_record" not in source


def test_slice_boundaries_exports_and_corrected_profile_are_exact() -> None:
    source = Path(freshness.__file__).read_text(encoding="utf-8")
    forbidden = {
        "EvidenceAdmissionRecord",
        "EvidenceAdmissionState",
        "EvidenceValidationRecord",
        "EvidenceValidityEvent",
        "analyze_daily_technical_snapshot",
        "evaluate_evidence_admission_as_of",
        "is_consumable",
    }

    assert len(evidence.__all__) == 69
    assert len(set(evidence.__all__)) == 69
    assert freshness._PROFILE.fingerprint == _PROFILE_FINGERPRINT
    assert freshness._PROFILE.fingerprint != _SUPERSEDED_PROFILE_FINGERPRINT
    assert freshness._PROFILE.construction_authorization.fingerprint == (
        _AUTHORIZATION_FINGERPRINT
    )
    assert forbidden.isdisjoint(source)
    assert "market_platform.agent_exposure" not in source
    companion_fields = {
        item.name
        for item in fields(freshness.PolygonCompletedDailyFreshnessExecutionCompanion)
    }
    assert companion_fields
    assert all(
        name not in companion_fields
        for name in (
            "admitted",
            "active",
            "consumable",
            "mapping_coverage",
            "research_permitted",
            "validated",
        )
    )
