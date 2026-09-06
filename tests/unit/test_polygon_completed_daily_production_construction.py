from __future__ import annotations

import asyncio
import inspect
from dataclasses import fields, replace
from datetime import UTC, date, datetime

import pytest

import market_platform.evidence as evidence
from market_platform._fingerprint import canonical_fingerprint
from market_platform.application import (
    polygon_completed_daily_production_construction as construction,
)
from market_platform.application.polygon_completed_daily_evidence_candidate import (
    PolygonCompletedDailyEvidenceCandidateApplicationRequest,
    PolygonCompletedDailyEvidenceCandidateApplicationService,
)
from market_platform.data.providers.polygon import PolygonCompletedDailyAcquisition
from market_platform.evidence.references import EvidenceArtifactReference
from market_platform.evidence_ingress import (
    PolygonCompletedDailyOhlcvEvidenceIngressResult,
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

_QUERY = datetime(2026, 8, 24, 10, tzinfo=UTC)
_STARTED = datetime(2026, 8, 24, 11, tzinfo=UTC)
_RECEIVED = datetime(2026, 8, 24, 12, tzinfo=UTC)
_CREATED = datetime(2026, 8, 24, 13, tzinfo=UTC)
_COMPLETED = datetime(2026, 8, 24, 14, tzinfo=UTC)
_AVAILABLE = datetime(2026, 8, 24, 15, tzinfo=UTC)
_PROFILE_FINGERPRINT = (
    "sha256:6bff0d17036920f657e44816f434ca357c803d99d77a06bd877b3c00aa64036f"
)
_AUTHORIZATION_FINGERPRINT = (
    "sha256:e9d8057dde8e20c5fb297ea08be7bcc723131cea42fab0e8a528f5b40c343387"
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


def _request() -> PolygonCompletedDailyEvidenceCandidateApplicationRequest:
    return PolygonCompletedDailyEvidenceCandidateApplicationRequest(
        external_identity=_external(),
        mappings=(_mapping(),),
        requested_from=date(2026, 8, 20),
        requested_to=date(2026, 8, 24),
        query_as_of=_QUERY,
    )


def _acquisition(
    response_received_at: datetime = _RECEIVED,
) -> PolygonCompletedDailyAcquisition:
    return PolygonCompletedDailyAcquisition(
        requested_ticker="AAPL",
        requested_from="2026-08-20",
        requested_to="2026-08-24",
        response_ticker_is_present=True,
        response_ticker="AAPL",
        response_adjusted_is_present=True,
        response_adjusted=True,
        request_id_is_present=True,
        request_id="request-123",
        query_count_is_present=True,
        query_count=0,
        results_count_is_present=True,
        results_count=0,
        count_is_present=True,
        count=0,
        next_url_is_present=False,
        next_page_reference=None,
        results_is_present=True,
        rows=(),
        response_received_at=response_received_at,
    )


class _Acquirer:
    def __init__(
        self,
        result: PolygonCompletedDailyAcquisition | None = None,
        failure: Exception | None = None,
    ) -> None:
        self.result = _acquisition() if result is None else result
        self.failure = failure
        self.calls = 0

    async def get_completed_daily_acquisition(
        self, ticker: str, start: date, end: date
    ) -> PolygonCompletedDailyAcquisition:
        self.calls += 1
        if self.failure is not None:
            raise self.failure
        return self.result


class _Clock:
    def __init__(self, *values: datetime) -> None:
        self._values = iter(values)
        self.calls = 0

    def __call__(self) -> datetime:
        self.calls += 1
        return next(self._values)


def _service(
    *,
    acquirer: _Acquirer | None = None,
    created_at: datetime = _CREATED,
    execution_times: tuple[datetime, ...] = (_STARTED, _COMPLETED, _AVAILABLE),
) -> construction.PolygonCompletedDailyProductionConstructionApplicationService:
    return construction.PolygonCompletedDailyProductionConstructionApplicationService(
        _Acquirer() if acquirer is None else acquirer,
        creation_clock=lambda: created_at,
        execution_clock=_Clock(*execution_times),
    )


def _execute(
    service: construction.PolygonCompletedDailyProductionConstructionApplicationService,
) -> construction.PolygonCompletedDailyProductionConstructionResult:
    return asyncio.run(service.execute(_request()))


def test_success_retains_exact_candidate_material_and_execution_provenance() -> None:
    service = _service()

    result = _execute(service)
    history = service.get_construction_history(result.artifact.reference())

    assert history == (result,)
    assert history[0] is result
    assert service._history._pending is None
    assert result.candidate_result.artifact is result.artifact
    assert result.candidate_result.material is result.material
    assert result.artifact.material_fingerprint == result.material.fingerprint
    assert result.receipt.artifact_reference == result.artifact.reference()
    assert result.receipt.material_fingerprint == result.material.fingerprint
    assert result.receipt.resolved_mapping_fingerprint == (
        result.material.mapping_resolution_provenance.mapping.fingerprint
    )
    assert result.receipt.history_sequence == 1
    assert result.receipt.history_namespace_id.startswith(
        "polygon_completed_daily_construction_history:"
    )
    assert result.receipt.operation.identity_id == (
        "polygon_completed_daily_production_construction"
    )
    assert result.receipt.operation.identity_version == "1.0.0"
    assert result.receipt.executor.identity_id == "market_platform"
    assert result.receipt.executor.identity_version == "0.1.0"
    assert result.receipt.production_profile_fingerprint == _PROFILE_FINGERPRINT
    assert result.receipt.construction_authorization.fingerprint == (
        _AUTHORIZATION_FINGERPRINT
    )


def test_retained_output_is_exact_released_candidate_construction_result() -> None:
    request = _request()
    candidate_service = PolygonCompletedDailyEvidenceCandidateApplicationService(
        _Acquirer(), creation_clock=lambda: _CREATED
    )
    released = asyncio.run(candidate_service.execute(request))
    service = _service()

    retained = asyncio.run(service.execute(request))

    assert retained.candidate_result == released
    assert retained.artifact.to_dict() == released.artifact.to_dict()
    assert retained.material.to_dict() == released.material.to_dict()


def test_actual_availability_is_retention_time_not_artifact_creation() -> None:
    service = _service()
    result = _execute(service)
    reference = result.artifact.reference()

    assert result.artifact.temporal_identity.artifact_created_at == _CREATED
    assert result.receipt.available_at == _AVAILABLE
    assert service.get_construction_history_as_of(
        reference, knowledge_as_of=_CREATED
    ) == ()
    assert service.get_construction_history_as_of(
        reference, knowledge_as_of=_COMPLETED
    ) == ()
    assert service.get_construction_history_as_of(
        reference, knowledge_as_of=_AVAILABLE
    ) == (result,)


def test_receipt_retains_coherent_distinct_construction_times() -> None:
    result = _execute(_service())
    receipt = result.receipt

    assert receipt.execution_started_at == _STARTED
    assert receipt.response_received_at == _RECEIVED
    assert receipt.artifact_created_at == _CREATED
    assert receipt.execution_completed_at == _COMPLETED
    assert receipt.available_at == _AVAILABLE
    assert (
        receipt.execution_started_at
        <= receipt.response_received_at
        <= receipt.artifact_created_at
        <= receipt.execution_completed_at
        <= receipt.available_at
    )


def test_receipts_and_results_cannot_be_publicly_minted_or_appended() -> None:
    service = _service()

    with pytest.raises(TypeError, match="issued only"):
        construction.PolygonCompletedDailyConstructionExecutionReceipt()
    with pytest.raises(TypeError, match="created only"):
        construction.PolygonCompletedDailyProductionConstructionResult()
    assert not hasattr(service, "append")
    assert not hasattr(service, "retain")
    assert not hasattr(service, "import_history")


def test_governed_request_has_no_availability_or_authority_selection() -> None:
    request_fields = {item.name for item in fields(type(_request()))}
    execute_parameters = tuple(inspect.signature(_service().execute).parameters)

    assert request_fields == {
        "external_identity",
        "mappings",
        "requested_from",
        "requested_to",
        "query_as_of",
    }
    assert execute_parameters == ("request",)
    assert "available_at" not in request_fields
    assert "receipt" not in request_fields
    assert "history" not in request_fields
    assert "executor" not in request_fields
    assert "construction_authorization" not in request_fields


def test_caller_created_backdated_candidate_is_not_trusted_history() -> None:
    request = _request()
    candidate_service = PolygonCompletedDailyEvidenceCandidateApplicationService(
        _Acquirer(), creation_clock=lambda: _CREATED
    )
    caller_candidate = asyncio.run(candidate_service.execute(request))
    production_service = _service()

    assert caller_candidate.artifact.temporal_identity.artifact_created_at == _CREATED
    assert production_service.get_construction_history(
        caller_candidate.artifact.reference()
    ) == ()


def test_v078_candidate_only_application_creates_no_production_history() -> None:
    production_service = _service()
    candidate = asyncio.run(
        PolygonCompletedDailyEvidenceCandidateApplicationService(
            _Acquirer(), creation_clock=lambda: _CREATED
        ).execute(_request())
    )

    assert type(candidate) is PolygonCompletedDailyOhlcvEvidenceIngressResult
    assert production_service.get_construction_history(
        candidate.artifact.reference()
    ) == ()


def test_content_equivalent_executions_remain_distinct_occurrences() -> None:
    same_time = datetime(2026, 8, 24, 12, tzinfo=UTC)
    service = _service(
        acquirer=_Acquirer(_acquisition(same_time)),
        created_at=same_time,
        execution_times=(same_time,) * 6,
    )

    first = _execute(service)
    second = _execute(service)
    history = service.get_construction_history(first.artifact.reference())

    assert first.artifact == second.artifact
    assert first.material == second.material
    assert first.receipt.result_content_fingerprint == (
        second.receipt.result_content_fingerprint
    )
    assert first.receipt.execution_id != second.receipt.execution_id
    assert first.receipt.history_sequence == 1
    assert second.receipt.history_sequence == 2
    assert first.receipt.history_namespace_id == second.receipt.history_namespace_id
    assert first.receipt.fingerprint != second.receipt.fingerprint
    assert history == (first, second)


def test_exact_artifact_material_mismatch_fails_before_retention(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = asyncio.run(
        PolygonCompletedDailyEvidenceCandidateApplicationService(
            _Acquirer(), creation_clock=lambda: _CREATED
        ).execute(_request())
    )
    mismatched = PolygonCompletedDailyOhlcvEvidenceIngressResult(
        material=replace(candidate.material, provider_request_id="different-request"),
        artifact=candidate.artifact,
    )

    async def return_mismatch(
        _service: object,
        _request: PolygonCompletedDailyEvidenceCandidateApplicationRequest,
    ) -> PolygonCompletedDailyOhlcvEvidenceIngressResult:
        return mismatched

    monkeypatch.setattr(
        construction.PolygonCompletedDailyEvidenceCandidateApplicationService,
        "execute",
        return_mismatch,
    )
    service = _service()

    with pytest.raises(ValueError, match="do not correspond"):
        _execute(service)
    assert service._history._state[1] == ()


def test_knowledge_cutoff_excludes_later_available_construction() -> None:
    service = _service()
    result = _execute(service)
    reference = result.artifact.reference()

    assert service.get_construction_history_as_of(
        reference,
        knowledge_as_of=datetime(2026, 8, 24, 14, 59, 59, tzinfo=UTC),
    ) == ()
    assert service.get_construction_history_as_of(
        reference,
        knowledge_as_of=_AVAILABLE,
    ) == (result,)


def test_lookalike_reference_cannot_select_favorable_history() -> None:
    service = _service()
    result = _execute(service)
    authentic = result.artifact.reference()
    lookalike = EvidenceArtifactReference(
        artifact_id=authentic.artifact_id,
        artifact_version=authentic.artifact_version,
        artifact_fingerprint="sha256:" + ("0" * 64),
        information_class=authentic.information_class,
        authority=authentic.authority,
    )

    with pytest.raises(
        construction.PolygonCompletedDailyConstructionHistoryConflictError
    ):
        service.get_construction_history(lookalike)


def test_ambiguous_retained_execution_identity_fails_closed() -> None:
    same_time = datetime(2026, 8, 24, 12, tzinfo=UTC)
    service = _service(
        acquirer=_Acquirer(_acquisition(same_time)),
        created_at=same_time,
        execution_times=(same_time,) * 6,
    )
    first = _execute(service)
    second = _execute(service)
    object.__setattr__(second.receipt, "execution_id", first.receipt.execution_id)
    object.__setattr__(
        second.receipt,
        "fingerprint",
        canonical_fingerprint(second.receipt._fingerprint_payload()),
    )

    with pytest.raises(construction.PolygonCompletedDailyConstructionHistoryError):
        service.get_construction_history(first.artifact.reference())


def test_result_from_another_history_namespace_is_not_production_truth() -> None:
    first_service = _service()
    foreign = _execute(first_service)
    second_service = _service()
    object.__setattr__(second_service._history, "_state", (2, (foreign,)))

    with pytest.raises(construction.PolygonCompletedDailyConstructionHistoryError):
        second_service.get_construction_history(foreign.artifact.reference())


def test_corrupt_retained_material_correspondence_fails_closed() -> None:
    service = _service()
    result = _execute(service)
    reference = result.artifact.reference()
    object.__setattr__(result.material, "fingerprint", "sha256:" + ("0" * 64))

    with pytest.raises(construction.PolygonCompletedDailyConstructionHistoryError):
        service.get_construction_history(reference)


def test_failed_construction_creates_no_available_history() -> None:
    failure = RuntimeError("provider failed")
    service = _service(acquirer=_Acquirer(failure=failure))

    with pytest.raises(RuntimeError, match="provider failed"):
        _execute(service)
    assert service._history._state[1] == ()


def test_failed_retention_before_publication_exposes_no_successful_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service()

    def fail_staging(_history: object, _staged: object) -> None:
        object.__setattr__(_history, "_pending", _staged)
        raise OSError("retention failed")

    monkeypatch.setattr(
        construction._InMemoryPolygonCompletedDailyConstructionHistory,
        "_stage_retention",
        fail_staging,
    )

    with pytest.raises(OSError, match="retention failed"):
        _execute(service)
    assert service._history._state[1] == ()
    assert service._history._pending is None
    assert service._execution_clock.calls == 2


def test_failed_final_binding_after_clock_capture_is_never_published(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service()

    def fail_final_binding(
        _cls: type[construction.PolygonCompletedDailyConstructionExecutionReceipt],
        _staged: construction.PolygonCompletedDailyConstructionExecutionReceipt,
        *,
        available_at: datetime,
        seal: object,
    ) -> construction.PolygonCompletedDailyConstructionExecutionReceipt:
        raise OSError("final binding failed")

    monkeypatch.setattr(
        construction.PolygonCompletedDailyConstructionExecutionReceipt,
        "_with_available_at",
        classmethod(fail_final_binding),
    )

    with pytest.raises(OSError, match="final binding failed"):
        _execute(service)
    assert service._history._state[1] == ()
    assert service._history._pending is None
    assert service._execution_clock.calls == 3


@pytest.mark.parametrize(
    "execution_times",
    (
        (_STARTED, datetime(2026, 8, 24, 12, 30, tzinfo=UTC), _AVAILABLE),
        (_STARTED, _COMPLETED, datetime(2026, 8, 24, 13, 30, tzinfo=UTC)),
    ),
)
def test_incoherent_completion_or_availability_is_not_retained(
    execution_times: tuple[datetime, ...],
) -> None:
    service = _service(execution_times=execution_times)

    with pytest.raises(ValueError, match="chronology"):
        _execute(service)
    assert service._history._state[1] == ()


def test_history_rejects_backdated_later_retention() -> None:
    service = _service(
        execution_times=(
            _STARTED,
            _COMPLETED,
            _AVAILABLE,
            _STARTED,
            _COMPLETED,
            _COMPLETED,
        )
    )
    first = _execute(service)

    with pytest.raises(ValueError, match="must not move backward"):
        _execute(service)
    assert service.get_construction_history(first.artifact.reference()) == (first,)


def test_slice1_profile_authorization_and_evidence_exports_remain_frozen() -> None:
    profile = construction._PROFILE

    assert profile.fingerprint == _PROFILE_FINGERPRINT
    assert profile.construction_authorization.fingerprint == (
        _AUTHORIZATION_FINGERPRINT
    )
    assert len(evidence.__all__) == 69
    assert len(set(evidence.__all__)) == 69
    assert tuple(evidence.__all__) == tuple(dict.fromkeys(evidence.__all__))


def test_construction_boundary_executes_no_lifecycle_or_research_operation() -> None:
    source = inspect.getsource(construction)
    forbidden = {
        "EvidenceValidationRecord",
        "EvidenceFreshnessEvaluationRecord",
        "EvidenceAdmissionRecord",
        "EvidenceValidityEvent",
        "EvidenceAdmissionState",
        "evaluate_evidence_admission_as_of",
        "create_evidence_validation_record",
        "create_evidence_freshness_evaluation_record",
        "create_evidence_admission_record",
        "create_evidence_validity_event",
        "prepare_completed_daily_price_series",
        "analyze_daily_technical_snapshot",
        "research_permitted",
        "is_consumable",
    }

    assert all(name not in source for name in forbidden)
