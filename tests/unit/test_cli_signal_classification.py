from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from market_platform.cli import main as cli_main
from market_platform.signals import (
    SignalClassificationSnapshot,
    classify_composite_signals,
)

_FIXED_TIMESTAMP = datetime(2026, 1, 2, 15, 30, tzinfo=UTC)


class _FixedDateTime:
    @classmethod
    def now(cls, tz: object = None) -> datetime:
        return _FIXED_TIMESTAMP


class _FailingServiceFactory:
    def __call__(self) -> object:
        raise AssertionError("should not be called")


def _run_signals_classify(
    argv: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, str, str]:
    monkeypatch.setattr(cli_main, "datetime", _FixedDateTime)
    exit_code = cli_main.run(["signals", "classify", *argv])
    captured = capsys.readouterr()
    return exit_code, captured.out, captured.err


def test_signals_classify_command_is_registered() -> None:
    parser = cli_main.build_parser()

    args = parser.parse_args(["signals", "classify", "--signal", "AAPL=0.72"])

    assert args.command == "signals"
    assert args.signals_command == "classify"
    assert args.signal == [("AAPL", 0.72)]
    assert callable(args.handler)


def test_signals_classify_help_shows_required_arguments(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli_main.run(["signals", "classify", "--help"])

    captured = capsys.readouterr()

    assert excinfo.value.code == 0
    assert "--signal SYMBOL=SCORE" in captured.out
    assert "--format" in captured.out


def test_signals_classify_table_output_preserves_input_order(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code, stdout, stderr = _run_signals_classify(
        ["--signal", "MSFT=0.10", "--signal", "AAPL=0.72"],
        monkeypatch,
        capsys,
    )

    assert exit_code == 0
    assert stdout.index("MSFT") < stdout.index("AAPL")
    assert "bullish" in stdout
    assert "strong_bullish" in stdout
    assert stderr == ""


def test_signals_classify_normalizes_symbol_and_uses_shared_timestamp(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code, stdout, stderr = _run_signals_classify(
        ["--signal", " aapl = 0.72 ", "--signal", " msft = 0.10 "],
        monkeypatch,
        capsys,
    )

    assert exit_code == 0
    assert "AAPL" in stdout
    assert "MSFT" in stdout
    assert " aapl " not in stdout
    assert stdout.count(_FIXED_TIMESTAMP.isoformat()) == 2
    assert stderr == ""


def test_signals_classify_json_output_is_structured(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code, stdout, stderr = _run_signals_classify(
        [
            "--signal",
            "AAPL=0.72",
            "--signal",
            "MSFT=0.10",
            "--format",
            "json",
        ],
        monkeypatch,
        capsys,
    )

    payload = json.loads(stdout)

    assert exit_code == 0
    assert payload["thresholds"] == {
        "strong_bearish": -0.60,
        "bearish": -0.20,
        "bullish": 0.20,
        "strong_bullish": 0.60,
    }
    assert payload["classifications"] == [
        {
            "symbol": "AAPL",
            "score": 0.72,
            "classification": "strong_bullish",
            "timestamp": _FIXED_TIMESTAMP.isoformat(),
            "source_signal_name": "composite_score",
        },
        {
            "symbol": "MSFT",
            "score": 0.10,
            "classification": "neutral",
            "timestamp": _FIXED_TIMESTAMP.isoformat(),
            "source_signal_name": "composite_score",
        },
    ]
    assert stderr == ""


def test_signals_classify_writes_output_file_and_parent_directories(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "nested" / "reports" / "signals.json"

    exit_code, stdout, stderr = _run_signals_classify(
        [
            "--signal",
            "AAPL=0.72",
            "--signal",
            "MSFT=0.10",
            "--format",
            "json",
            "--output",
            str(output_path),
        ],
        monkeypatch,
        capsys,
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert output_path.exists()
    assert output_path.parent.exists()
    assert payload["classifications"][0]["symbol"] == "AAPL"
    assert "Wrote 2 rows" in stdout
    assert stderr == ""


@pytest.mark.parametrize(
    ("signal_arg", "expected_message"),
    [
        (None, "the following arguments are required: --signal"),
        ("AAPL", "expected SYMBOL=SCORE"),
        ("=0.10", "symbol must not be empty"),
        ("AAPL=", "score must not be empty"),
        ("AAPL=abc", "score must be numeric"),
        ("AAPL=True", "score must be numeric"),
        ("AAPL=nan", "score must be finite"),
        ("AAPL=inf", "score must be finite"),
        ("AAPL=-inf", "score must be finite"),
        ("AAPL=-1.01", "score must be within [-1.0, 1.0]"),
        ("AAPL=1.01", "score must be within [-1.0, 1.0]"),
    ],
)
def test_signals_classify_rejects_invalid_input_cleanly(
    signal_arg: str | None,
    expected_message: str,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    argv = ["signals", "classify", "--output", str(tmp_path / "out.json")]
    if signal_arg is not None:
        argv.extend(["--signal", signal_arg])

    with pytest.raises(SystemExit) as excinfo:
        cli_main.run(argv)

    captured = capsys.readouterr()

    assert excinfo.value.code == 2
    assert expected_message in captured.err
    if signal_arg is not None:
        assert signal_arg.strip() in captured.err
    assert "Traceback" not in captured.err
    assert not (tmp_path / "out.json").exists()


def test_signals_classify_runs_without_provider_configuration_or_network_access(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        cli_main,
        "create_default_market_data_service",
        _FailingServiceFactory(),
    )

    exit_code, stdout, stderr = _run_signals_classify(
        ["--signal", "AAPL=0.72"],
        monkeypatch,
        capsys,
    )

    assert exit_code == 0
    assert "AAPL" in stdout
    assert stderr == ""


def test_batch_classification_api_is_available_from_package_import() -> None:
    snapshot = classify_composite_signals([])

    assert isinstance(snapshot, SignalClassificationSnapshot)
    assert snapshot.classifications == ()


def test_signals_classify_help_shows_sort_argument(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli_main.run(["signals", "classify", "--help"])

    captured = capsys.readouterr()

    assert excinfo.value.code == 0
    assert "--sort" in captured.out
    assert "score-desc" in captured.out
    assert "score-asc" in captured.out


def test_signals_classify_score_desc_table_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code, stdout, stderr = _run_signals_classify(
        [
            "--signal",
            "MSFT=0.10",
            "--signal",
            "AAPL=0.72",
            "--signal",
            "GOOG=0.72",
            "--sort",
            "score-desc",
        ],
        monkeypatch,
        capsys,
    )

    assert exit_code == 0
    assert stdout.index("AAPL") < stdout.index("GOOG") < stdout.index("MSFT")
    assert stderr == ""


def test_signals_classify_score_asc_table_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code, stdout, stderr = _run_signals_classify(
        [
            "--signal",
            "MSFT=0.10",
            "--signal",
            "AAPL=0.72",
            "--signal",
            "GOOG=0.72",
            "--sort",
            "score-asc",
        ],
        monkeypatch,
        capsys,
    )

    assert exit_code == 0
    assert stdout.index("MSFT") < stdout.index("AAPL") < stdout.index("GOOG")
    assert stderr == ""


def test_signals_classify_score_desc_json_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code, stdout, stderr = _run_signals_classify(
        [
            "--signal",
            "MSFT=0.10",
            "--signal",
            "AAPL=0.72",
            "--signal",
            "GOOG=0.72",
            "--format",
            "json",
            "--sort",
            "score-desc",
        ],
        monkeypatch,
        capsys,
    )

    payload = json.loads(stdout)

    assert exit_code == 0
    assert [item["symbol"] for item in payload["classifications"]] == [
        "AAPL",
        "GOOG",
        "MSFT",
    ]
    assert stderr == ""


def test_signals_classify_score_asc_json_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code, stdout, stderr = _run_signals_classify(
        [
            "--signal",
            "MSFT=0.10",
            "--signal",
            "AAPL=0.72",
            "--signal",
            "GOOG=0.72",
            "--format",
            "json",
            "--sort",
            "score-asc",
        ],
        monkeypatch,
        capsys,
    )

    payload = json.loads(stdout)

    assert exit_code == 0
    assert [item["symbol"] for item in payload["classifications"]] == [
        "MSFT",
        "AAPL",
        "GOOG",
    ]
    assert stderr == ""


def test_signals_classify_equal_scores_preserve_input_order(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code, stdout, stderr = _run_signals_classify(
        [
            "--signal",
            "AAPL=0.50",
            "--signal",
            "MSFT=0.50",
            "--signal",
            "GOOG=0.20",
            "--sort",
            "score-desc",
            "--format",
            "json",
        ],
        monkeypatch,
        capsys,
    )

    payload = json.loads(stdout)

    assert exit_code == 0
    assert [item["symbol"] for item in payload["classifications"]] == [
        "AAPL",
        "MSFT",
        "GOOG",
    ]
    assert stderr == ""


def test_signals_classify_rejects_invalid_sort_value_cleanly(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli_main.run(
            [
                "signals",
                "classify",
                "--signal",
                "AAPL=0.72",
                "--sort",
                "unknown",
                "--output",
                str(tmp_path / "out.json"),
            ]
        )

    captured = capsys.readouterr()

    assert excinfo.value.code == 2
    assert "invalid choice" in captured.err
    assert "Traceback" not in captured.err
    assert not (tmp_path / "out.json").exists()


def test_signals_classify_output_file_reflects_requested_order(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "nested" / "reports" / "signals.json"

    exit_code, stdout, stderr = _run_signals_classify(
        [
            "--signal",
            "MSFT=0.10",
            "--signal",
            "AAPL=0.72",
            "--signal",
            "GOOG=0.72",
            "--sort",
            "score-desc",
            "--format",
            "json",
            "--output",
            str(output_path),
        ],
        monkeypatch,
        capsys,
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert [item["symbol"] for item in payload["classifications"]] == [
        "AAPL",
        "GOOG",
        "MSFT",
    ]
    assert output_path.exists()
    assert output_path.parent.exists()
    assert "Wrote 3 rows" in stdout
    assert stderr == ""
