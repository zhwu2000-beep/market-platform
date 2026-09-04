from __future__ import annotations

import ast
import json
import logging
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

import market_platform.cli.main as cli_main
from market_platform.data import DataProviderError
from market_platform.data.providers.polygon import PolygonCompletedDailyAcquisition
from market_platform.evidence_ingress import (
    PolygonCompletedDailyOhlcvEvidenceIngressResult,
    create_polygon_completed_daily_ohlcv_evidence,
)
from market_platform.instruments import (
    CanonicalInstrument,
    CanonicalInstrumentId,
    ExternalInstrumentIdentity,
    InstrumentAssetClass,
    InstrumentMapping,
    InstrumentMappingNotFoundError,
    InstrumentMappingSourceIdentity,
)
from market_platform.trading import TradingInstrumentIdentity

_QUERY = datetime(2026, 8, 24, 10, tzinfo=UTC)
_RECEIVED = datetime(2026, 8, 24, 12, tzinfo=UTC)
_CREATED = datetime(2026, 8, 24, 13, tzinfo=UTC)
_WARNING = "UNVALIDATED, UNADMITTED CANDIDATE — NOT PERMITTED FOR RESEARCH"


@pytest.fixture(autouse=True)
def _keep_test_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_main, "configure_logging", lambda *args: None)


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


def _result() -> PolygonCompletedDailyOhlcvEvidenceIngressResult:
    acquisition = PolygonCompletedDailyAcquisition(
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
        response_received_at=_RECEIVED,
    )
    return create_polygon_completed_daily_ohlcv_evidence(
        acquisition=acquisition,
        external_identity=_external(),
        mappings=(_mapping(),),
        query_as_of=_QUERY,
        artifact_created_at=_CREATED,
    )


def _args(*extra: str) -> list[str]:
    return [
        "evidence",
        "candidate",
        "polygon-daily",
        "--ticker",
        "AAPL",
        "--venue",
        "NASDAQ",
        "--instrument-mappings",
        "operator.json",
        "--requested-from",
        "2026-08-20",
        "--requested-to",
        "2026-08-24",
        "--query-as-of",
        "2026-08-24T10:00:00Z",
        *extra,
    ]


def _configure_success(
    monkeypatch: pytest.MonkeyPatch,
    *,
    result: PolygonCompletedDailyOhlcvEvidenceIngressResult | None = None,
    events: list[str] | None = None,
) -> list[object]:
    observed: list[object] = []
    ordered = [] if events is None else events
    registry = SimpleNamespace(mappings=(_mapping(),))
    provider = object()

    def load(path: str) -> object:
        ordered.append("mapping")
        observed.append(path)
        return registry

    def create_provider() -> object:
        ordered.append("provider")
        return provider

    class Service:
        def __init__(self, acquirer: object) -> None:
            ordered.append("service")
            assert acquirer is provider

        async def execute(self, request: object) -> object:
            ordered.append("execute")
            observed.append(request)
            return _result() if result is None else result

    monkeypatch.setattr(cli_main, "load_trusted_instrument_mapping_registry", load)
    monkeypatch.setattr(cli_main, "create_polygon_provider", create_provider)
    monkeypatch.setattr(
        cli_main,
        "PolygonCompletedDailyEvidenceCandidateApplicationService",
        Service,
    )
    return observed


def test_exact_nested_command_defaults_to_summary_table(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    observed = _configure_success(monkeypatch)

    assert cli_main.run(_args()) == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    assert "Section" in captured.out
    assert "Lifecycle State" in captured.out
    assert "candidate" in captured.out
    assert _WARNING in captured.out
    request = observed[1]
    assert request.external_identity == _external()
    assert request.requested_from == date(2026, 8, 20)
    assert request.requested_to == date(2026, 8, 24)
    assert request.query_as_of == _QUERY


@pytest.mark.parametrize(
    "option",
    (
        "--ticker",
        "--venue",
        "--instrument-mappings",
        "--requested-from",
        "--requested-to",
        "--query-as-of",
    ),
)
def test_required_arguments_are_required(option: str) -> None:
    argv = _args()
    index = argv.index(option)
    del argv[index : index + 2]
    with pytest.raises(SystemExit) as caught:
        cli_main.run(argv)
    assert caught.value.code == 2


@pytest.mark.parametrize(
    ("option", "value", "prefix"),
    (
        ("--ticker", "MSFT", ()),
        ("--venue", "NYSE", ()),
        ("--instrument-mappings", "other.json", ()),
        ("--requested-from", "2026-08-19", ()),
        ("--requested-to", "2026-08-25", ()),
        ("--query-as-of", "2026-08-24T11:00:00Z", ()),
        ("--format", "json", ("--format", "table")),
        ("--view", "full", ("--view", "summary")),
    ),
)
def test_singleton_arguments_reject_duplicates(
    option: str, value: str, prefix: tuple[str, ...]
) -> None:
    with pytest.raises(SystemExit) as caught:
        cli_main.run(_args(*prefix, option, value))
    assert caught.value.code == 2


def test_date_and_aware_datetime_parsers_are_exact_and_utc_normalized() -> None:
    assert cli_main._parse_iso_date("2026-08-24") == date(2026, 8, 24)
    with pytest.raises(cli_main.argparse.ArgumentTypeError):
        cli_main._parse_iso_date("2026-02-30")
    parsed = cli_main._parse_aware_iso_datetime("2026-08-24T18:00:00+08:00")
    assert parsed == _QUERY
    assert parsed.tzinfo is UTC
    with pytest.raises(cli_main.argparse.ArgumentTypeError):
        cli_main._parse_aware_iso_datetime("2026-08-24T10:00:00")


def test_reversed_range_fails_before_mapping_or_provider(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        cli_main,
        "load_trusted_instrument_mapping_registry",
        lambda path: calls.append("mapping"),
    )
    monkeypatch.setattr(
        cli_main, "create_polygon_provider", lambda: calls.append("provider")
    )
    argv = _args()
    argv[argv.index("--requested-from") + 1] = "2026-08-25"

    assert cli_main.run(argv) == 2
    assert calls == []
    assert "requested-from" in capsys.readouterr().err


@pytest.mark.parametrize(("option", "value"), (("--ticker", " AAPL"), ("--venue", "")))
def test_invalid_identity_scalar_fails_before_mapping_or_provider(
    option: str,
    value: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        cli_main,
        "load_trusted_instrument_mapping_registry",
        lambda path: calls.append("mapping"),
    )
    monkeypatch.setattr(
        cli_main, "create_polygon_provider", lambda: calls.append("provider")
    )
    argv = _args()
    argv[argv.index(option) + 1] = value

    assert cli_main.run(argv) == 2
    assert calls == []
    assert "exact canonical values" in capsys.readouterr().err


def test_mapping_load_precedes_provider_and_application_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    _configure_success(monkeypatch, events=events)

    assert cli_main.run(_args("--format", "json")) == 0
    assert events == ["mapping", "provider", "service", "execute"]


@pytest.mark.parametrize(
    "extra",
    (
        ("--provider", "polygon"),
        ("--format", "csv"),
        ("--output", "artifact.json"),
    ),
)
def test_forbidden_options_are_not_supported(extra: tuple[str, str]) -> None:
    with pytest.raises(SystemExit) as caught:
        cli_main.run(_args(*extra))
    assert caught.value.code == 2


def test_full_table_is_a_usage_error_before_mapping_or_provider(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        cli_main,
        "load_trusted_instrument_mapping_registry",
        lambda path: calls.append("mapping"),
    )
    monkeypatch.setattr(
        cli_main, "create_polygon_provider", lambda: calls.append("provider")
    )

    assert cli_main.run(_args("--view", "full")) == 2
    assert calls == []
    assert "only supports --format json" in capsys.readouterr().err


def test_json_summary_has_exact_candidate_labels_and_empty_material(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _configure_success(monkeypatch)

    assert cli_main.run(_args("--format", "json")) == 0

    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {"candidate_summary"}
    summary = payload["candidate_summary"]
    assert summary["candidate"] == {
        "lifecycle_state": "candidate",
        "semantic_authorization": "exact_production_membership",
        "validation": "not_performed",
        "admission": "absent",
        "validity": "not_evaluated",
        "freshness": "not_evaluated",
        "consumable": False,
        "research_permitted": False,
        "warning": _WARNING,
    }
    assert summary["material"]["row_count"] == 0
    assert summary["material"]["latest_retained_session_date"] is None
    assert summary["source"]["api_base"] == "https://api.polygon.io"
    assert "apiKey" not in json.dumps(payload)


def test_full_json_uses_exact_artifact_and_material_projections(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    result = _result()
    _configure_success(monkeypatch, result=result)

    assert cli_main.run(_args("--format", "json", "--view", "full")) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["artifact"] == result.artifact.to_dict()
    assert payload["material"] == result.material.to_dict()
    assert payload["candidate_summary"]["artifact"]["artifact_id"] == (
        result.artifact.artifact_id
    )


def test_table_is_ordered_candidate_summary_without_material_rows(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _configure_success(monkeypatch)

    assert cli_main.run(_args()) == 0

    output = capsys.readouterr().out
    assert output.index("Warning") < output.index("Lifecycle State")
    assert "Latest Retained Session Date" in output
    assert "-" in output
    assert "session_date" not in output
    positive_phrases = (
        "lifecycle_state: validated",
        "lifecycle_state: admitted",
        "lifecycle_state: active",
        "research-ready",
        "approved Evidence",
    )
    assert all(phrase not in output for phrase in positive_phrases)


@pytest.mark.parametrize(
    ("stage", "failure", "expected"),
    (
        (
            "mapping",
            RuntimeError("POLYGON API secret text"),
            "trusted instrument mapping configuration failed",
        ),
        (
            "provider",
            RuntimeError("apiKey=SUPER_SECRET"),
            "Polygon provider configuration failed",
        ),
        (
            "service",
            DataProviderError("Authorization: Bearer SUPER_SECRET"),
            "Polygon completed-daily acquisition failed",
        ),
        (
            "service",
            InstrumentMappingNotFoundError(
                "https://api.polygon.io/path?apiKey=SUPER_SECRET"
            ),
            "canonical instrument resolution failed",
        ),
        (
            "service",
            ValueError("POLYGON API secret text SUPER_SECRET"),
            "Candidate construction failed",
        ),
        (
            "service",
            RuntimeError("POLYGON API secret text SUPER_SECRET"),
            "unexpected Candidate command failure",
        ),
    ),
)
def test_arbitrary_failure_text_is_never_rendered(
    stage: str,
    failure: Exception,
    expected: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.ERROR)

    def raise_failure(*args: object, **kwargs: object) -> object:
        raise failure

    if stage == "mapping":
        monkeypatch.setattr(
            cli_main, "load_trusted_instrument_mapping_registry", raise_failure
        )
        monkeypatch.setattr(
            cli_main,
            "create_polygon_provider",
            lambda: pytest.fail("provider must not be constructed"),
        )
    else:
        monkeypatch.setattr(
            cli_main,
            "load_trusted_instrument_mapping_registry",
            lambda path: SimpleNamespace(mappings=(_mapping(),)),
        )
        if stage == "provider":
            monkeypatch.setattr(cli_main, "create_polygon_provider", raise_failure)
        else:
            monkeypatch.setattr(cli_main, "create_polygon_provider", object)

            class FailingService:
                def __init__(self, provider: object) -> None:
                    pass

                async def execute(self, request: object) -> object:
                    raise failure

            monkeypatch.setattr(
                cli_main,
                "PolygonCompletedDailyEvidenceCandidateApplicationService",
                FailingService,
            )

    assert cli_main.run(_args()) == 1

    captured = capsys.readouterr()
    exposed = captured.out + captured.err + caplog.text
    assert expected in exposed
    for sentinel in (
        "POLYGON API secret text",
        "SUPER_SECRET",
        "apiKey=",
        "Authorization: Bearer",
        "https://api.polygon.io/path?",
    ):
        assert sentinel not in exposed
    assert "Traceback" not in exposed


def test_request_construction_failure_is_secret_safe(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(
        cli_main,
        "load_trusted_instrument_mapping_registry",
        lambda path: SimpleNamespace(mappings=(_mapping(),)),
    )
    monkeypatch.setattr(cli_main, "create_polygon_provider", object)

    def fail_request(**kwargs: object) -> object:
        raise ValueError("apiKey=SUPER_SECRET")

    monkeypatch.setattr(
        cli_main,
        "PolygonCompletedDailyEvidenceCandidateApplicationRequest",
        fail_request,
    )
    caplog.set_level(logging.ERROR)

    assert cli_main.run(_args()) == 1
    exposed = capsys.readouterr().err + caplog.text
    assert "Candidate construction failed" in exposed
    assert "SUPER_SECRET" not in exposed


def test_cli_candidate_path_has_no_later_lifecycle_calls_or_persistence() -> None:
    source = Path(cli_main.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "evaluate_evidence_admission_as_of" not in called_names
    assert "create_evidence_validation_record" not in called_names
    assert "create_evidence_admission_record" not in called_names
    handler_source = ast.get_source_segment(
        source,
        next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "_handle_evidence_candidate_polygon_daily"
        ),
    )
    assert handler_source is not None
    for forbidden in (
        "research workflow",
        "agent_exposure",
        "CompletedDailyPriceSeries",
        "_write_output",
    ):
        assert forbidden not in handler_source
