"""Command line entrypoint."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Protocol, cast

import pandas as pd

from market_platform.data.cache import (
    DEFAULT_MARKET_DATA_CACHE_DIR,
    MarketDataCache,
    MarketDataCacheKey,
)
from market_platform.data.capabilities import normalize_provider_name
from market_platform.data.diagnostics import (
    ProviderDiagnosticsReport,
    build_provider_diagnostics_report,
    render_provider_diagnostics_report,
)
from market_platform.data.exceptions import ConfigurationError, DataProviderError
from market_platform.data.factory import create_default_market_data_service
from market_platform.data.health import (
    ProviderHealthReport,
    build_provider_health_report,
    render_provider_health_report,
)
from market_platform.logging import configure_logging, get_logger
from market_platform.replay import (
    HistoricalReplayResult,
    HistoricalReplayService,
    HistoricalReplaySummary,
    summarize_historical_replay,
)
from market_platform.research import (
    DefaultResearchWorkflow,
    ResearchRequest,
    ResearchResult,
)
from market_platform.signals.batch import (
    SignalClassificationSnapshot,
    classify_composite_signals,
)
from market_platform.signals.models import MarketSignal
from market_platform.signals.ranking import (
    SignalClassificationSort,
    sort_signal_classifications,
)
from market_platform.state import BaselineMarketStateModel
from market_platform.strategy import (
    BaselineTrendRegimeStrategy,
    create_strategy_collection,
)

_REPLAY_DAILY_INTERVAL = "1day"
_DEFAULT_REPLAY_MAX_BARS = 500


class CommandHandler(Protocol):
    """Callable command handler."""

    def __call__(self, args: argparse.Namespace) -> int:
        """Run a parsed command."""
        ...


def build_parser() -> argparse.ArgumentParser:
    """Build the command line parser."""

    parser = argparse.ArgumentParser(
        prog="market-platform",
        description="AI investment research platform CLI.",
    )
    subparsers = parser.add_subparsers(dest="command")

    data_parser = subparsers.add_parser("data", help="Market data commands.")
    data_subparsers = data_parser.add_subparsers(dest="data_command")

    fetch_parser = data_subparsers.add_parser(
        "fetch",
        help="Fetch daily market prices.",
    )
    fetch_parser.add_argument("--symbol", required=True, help="Ticker symbol.")
    fetch_parser.add_argument(
        "--start",
        type=_parse_iso_date,
        required=True,
        help="Start date, YYYY-MM-DD.",
    )
    fetch_parser.add_argument(
        "--end",
        type=_parse_iso_date,
        required=True,
        help="End date, YYYY-MM-DD.",
    )
    fetch_parser.add_argument(
        "--format",
        choices=["table", "json", "csv"],
        default="table",
        help="Output format.",
    )
    fetch_parser.add_argument(
        "--output",
        default=None,
        help="Write formatted output to a file instead of stdout.",
    )
    fetch_parser.add_argument(
        "--provider",
        choices=["polygon", "twelvedata", "twelve_data"],
        default=None,
        help="Explicit provider. Defaults to configured provider fallback order.",
    )
    _add_cache_options(fetch_parser)
    fetch_parser.set_defaults(handler=_handle_data_fetch)

    latest_parser = data_subparsers.add_parser(
        "latest",
        help="Fetch the latest market price.",
        parents=[_build_output_options_parser(["table", "json", "csv"])],
    )
    latest_parser.add_argument("--symbol", required=True, help="Ticker symbol.")
    latest_parser.add_argument(
        "--provider",
        choices=["polygon", "twelvedata", "twelve_data"],
        default=None,
        help="Explicit provider. Defaults to configured provider fallback order.",
    )
    _add_cache_options(latest_parser)
    latest_parser.set_defaults(handler=_handle_data_latest)

    intraday_parser = data_subparsers.add_parser(
        "intraday",
        help="Fetch intraday market prices.",
        parents=[_build_output_options_parser(["table", "json", "csv"])],
    )
    intraday_parser.add_argument("--symbol", required=True, help="Ticker symbol.")
    intraday_parser.add_argument(
        "--interval",
        choices=["1min", "5min", "15min", "30min", "1h"],
        default="1min",
        help="Intraday interval.",
    )
    intraday_parser.add_argument(
        "--provider",
        choices=["polygon", "twelvedata", "twelve_data"],
        default=None,
        help="Explicit provider. Defaults to configured provider fallback order.",
    )
    _add_cache_options(intraday_parser)
    intraday_parser.set_defaults(handler=_handle_data_intraday)

    providers_parser = data_subparsers.add_parser(
        "providers",
        help="Show provider diagnostics.",
        parents=[_build_output_options_parser(["table", "json"])],
    )
    providers_parser.set_defaults(handler=_handle_data_providers)

    providers_subparsers = providers_parser.add_subparsers(dest="providers_command")
    health_parser = providers_subparsers.add_parser(
        "health",
        help="Run provider health checks.",
        parents=[
            _build_output_options_parser(
                ["table", "json"],
                default=argparse.SUPPRESS,
            )
        ],
    )
    health_parser.add_argument(
        "--provider",
        default=None,
        type=_normalize_provider_name_arg,
        help="Explicit provider to check. Defaults to configured provider order.",
    )
    health_parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress informational output from provider health checks.",
    )
    health_parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default=None,
        help="Set the provider health logging level.",
    )
    health_parser.add_argument(
        "--fail-on",
        choices=["never", "failed", "degraded", "unknown"],
        default="never",
        help=(
            "Exit with a non-zero status when the overall health report reaches "
            "the selected severity."
        ),
    )
    health_parser.set_defaults(handler=_handle_data_provider_health)

    signals_parser = subparsers.add_parser(
        "signals",
        help="Signal classification commands.",
    )
    signals_subparsers = signals_parser.add_subparsers(dest="signals_command")
    classify_parser = signals_subparsers.add_parser(
        "classify",
        help="Classify explicit composite scores.",
        parents=[_build_output_options_parser(["table", "json"])],
    )
    classify_parser.add_argument(
        "--signal",
        action="append",
        required=True,
        metavar="SYMBOL=SCORE",
        type=_parse_signal_argument,
        help="Explicit composite score to classify.",
    )
    classify_parser.add_argument(
        "--sort",
        choices=[sort.value for sort in SignalClassificationSort],
        default=SignalClassificationSort.INPUT.value,
        help="Sort classifications before rendering.",
    )
    classify_parser.set_defaults(handler=_handle_signals_classify)

    research_parser = subparsers.add_parser(
        "research",
        help="Research workflow commands.",
    )
    research_subparsers = research_parser.add_subparsers(dest="research_command")
    run_parser = research_subparsers.add_parser(
        "run",
        help="Run the end-to-end research workflow.",
        parents=[_build_output_options_parser(["table", "json"])],
    )
    run_parser.add_argument("--symbol", required=True, help="Ticker symbol.")
    run_parser.add_argument(
        "--horizon-days",
        type=_parse_positive_int,
        default=20,
        help="Requested research horizon in days.",
    )
    run_parser.add_argument(
        "--provider",
        default=None,
        type=_normalize_provider_name_arg,
        help="Explicit provider. Defaults to configured provider fallback order.",
    )
    run_parser.add_argument(
        "--as-of",
        type=_parse_iso_date,
        default=None,
        help="Research as-of date, YYYY-MM-DD.",
    )
    run_parser.add_argument(
        "--lookback-days",
        type=_parse_positive_int,
        default=120,
        help="Daily lookback window in calendar days.",
    )
    run_parser.set_defaults(handler=_handle_research_run)

    replay_parser = subparsers.add_parser(
        "replay",
        help="Historical replay commands.",
    )
    replay_subparsers = replay_parser.add_subparsers(dest="replay_command")
    replay_run_parser = replay_subparsers.add_parser(
        "run",
        help="Run point-in-time historical replay over daily prices.",
        parents=[_build_output_options_parser(["table", "json", "csv"])],
    )
    replay_run_parser.add_argument("--symbol", required=True, help="Ticker symbol.")
    replay_run_parser.add_argument(
        "--start",
        type=_parse_iso_date,
        required=True,
        help="Replay start date, YYYY-MM-DD, inclusive.",
    )
    replay_run_parser.add_argument(
        "--end",
        type=_parse_iso_date,
        required=True,
        help="Replay end date, YYYY-MM-DD, inclusive.",
    )
    replay_run_parser.add_argument(
        "--provider",
        default=None,
        type=_normalize_provider_name_arg,
        help="Explicit provider. Defaults to configured provider fallback order.",
    )
    replay_run_parser.add_argument(
        "--view",
        choices=["summary", "steps"],
        default="summary",
        help="Replay output view.",
    )
    replay_run_parser.add_argument(
        "--max-bars",
        type=_parse_positive_int,
        default=_DEFAULT_REPLAY_MAX_BARS,
        help="Maximum number of replay bars before refusing O(n²) replay.",
    )
    replay_run_parser.set_defaults(handler=_handle_replay_run)

    return parser


def run(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return an exit code."""

    parser = build_parser()
    raw_argv = sys.argv[1:] if argv is None else argv
    normalized_argv = _normalize_data_providers_health_argv(raw_argv)
    args = parser.parse_args(normalized_argv)
    if getattr(args, "refresh", False) and not getattr(args, "cache", False):
        parser.error("--refresh requires --cache")
    _configure_logging_for_args(args)

    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 0

    return cast(CommandHandler, handler)(args)


def main(argv: Sequence[str] | None = None) -> None:
    """Run the command line interface."""

    raise SystemExit(run(argv))


def _handle_data_fetch(args: argparse.Namespace) -> int:
    logger = get_logger(__name__)
    symbol = args.symbol.strip().upper()
    if args.start > args.end:
        print(
            "error: start date must be earlier than or equal to end date.",
            file=sys.stderr,
        )
        return 2

    cache = _create_market_data_cache()
    cache_key = MarketDataCacheKey.for_daily(
        symbol=symbol,
        provider=args.provider,
        start=args.start.isoformat(),
        end=args.end.isoformat(),
    )
    frame = _load_cached_market_data_frame(
        cache=cache,
        cache_key=cache_key,
        cache_enabled=args.cache,
        refresh=args.refresh,
    )
    if frame is None:
        service = create_default_market_data_service()
        try:
            frame = asyncio.run(
                service.get_daily_prices(
                    symbol=symbol,
                    start=args.start,
                    end=args.end,
                    provider=args.provider,
                )
            )
        except DataProviderError as exc:
            logger.error("Failed to fetch daily prices: %s", exc)
            print(f"error: {exc}", file=sys.stderr)
            return 1
        if args.cache:
            _save_market_data_frame(cache=cache, cache_key=cache_key, frame=frame)

    rendered_output = _render_daily_prices(frame, args.format)
    if args.output is not None:
        _write_output(Path(args.output), rendered_output)
        print(f"Wrote {len(frame)} rows to {args.output} as {args.format}.")
        return 0

    print(rendered_output, end="" if rendered_output.endswith("\n") else "\n")
    return 0


def _handle_data_latest(args: argparse.Namespace) -> int:
    logger = get_logger(__name__)
    symbol = args.symbol.strip().upper()
    output_format = getattr(args, "format", "table")
    output_path = getattr(args, "output", None)

    cache = _create_market_data_cache()
    cache_key = MarketDataCacheKey.for_latest(symbol=symbol, provider=args.provider)
    frame = _load_cached_market_data_frame(
        cache=cache,
        cache_key=cache_key,
        cache_enabled=args.cache,
        refresh=args.refresh,
    )
    if frame is None:
        service = create_default_market_data_service()
        try:
            frame = asyncio.run(
                service.get_latest_price(
                    symbol=symbol,
                    provider=args.provider,
                )
            )
        except ConfigurationError as exc:
            logger.error("Failed to fetch latest price: %s", exc)
            print(f"error: {exc}", file=sys.stderr)
            return 1
        except DataProviderError as exc:
            logger.error("Failed to fetch latest price: %s", exc)
            print(f"error: {exc}", file=sys.stderr)
            return 1
        if args.cache:
            _save_market_data_frame(cache=cache, cache_key=cache_key, frame=frame)

    rendered_output = _render_daily_prices(frame, output_format)
    if output_path is not None:
        _write_output(Path(output_path), rendered_output)
        print(f"Wrote 1 row to {output_path} as {output_format}.")
        return 0

    print(rendered_output, end="" if rendered_output.endswith("\n") else "\n")
    return 0


def _handle_data_intraday(args: argparse.Namespace) -> int:
    logger = get_logger(__name__)
    symbol = args.symbol.strip().upper()
    output_format = getattr(args, "format", "table")
    output_path = getattr(args, "output", None)

    cache = _create_market_data_cache()
    cache_key = MarketDataCacheKey.for_intraday(
        symbol=symbol,
        provider=args.provider,
        interval=args.interval,
    )
    frame = _load_cached_market_data_frame(
        cache=cache,
        cache_key=cache_key,
        cache_enabled=args.cache,
        refresh=args.refresh,
    )
    if frame is None:
        service = create_default_market_data_service()
        try:
            frame = asyncio.run(
                service.get_intraday_prices(
                    symbol=symbol,
                    provider=args.provider,
                    interval=args.interval,
                )
            )
        except ConfigurationError as exc:
            logger.error("Failed to fetch intraday prices: %s", exc)
            print(f"error: {exc}", file=sys.stderr)
            return 1
        except DataProviderError as exc:
            logger.error("Failed to fetch intraday prices: %s", exc)
            print(f"error: {exc}", file=sys.stderr)
            return 1
        if args.cache:
            _save_market_data_frame(cache=cache, cache_key=cache_key, frame=frame)

    rendered_output = _render_daily_prices(frame, output_format)
    if output_path is not None:
        _write_output(Path(output_path), rendered_output)
        print(f"Wrote {len(frame)} rows to {output_path} as {output_format}.")
        return 0

    print(rendered_output, end="" if rendered_output.endswith("\n") else "\n")
    return 0


def _handle_data_providers(args: argparse.Namespace) -> int:
    logger = get_logger(__name__)

    try:
        report = build_provider_diagnostics_report()
    except ConfigurationError as exc:
        logger.error("Failed to build provider diagnostics: %s", exc)
        print(f"error: {exc}", file=sys.stderr)
        return 1

    rendered_output = _render_provider_diagnostics_report(report, args.format)
    if args.output is not None:
        _write_output(Path(args.output), rendered_output)
        print(f"Wrote provider diagnostics to {args.output} as {args.format}.")
        return 0

    print(rendered_output, end="" if rendered_output.endswith("\n") else "\n")
    return 0


def _handle_data_provider_health(args: argparse.Namespace) -> int:
    logger = get_logger(__name__)
    output_format = getattr(args, "format", "table")
    output_path = getattr(args, "output", None)
    fail_on = getattr(args, "fail_on", "never")

    try:
        report = build_provider_health_report(args.provider)
    except ConfigurationError as exc:
        logger.error("Failed to build provider health report: %s", exc)
        print(f"error: {exc}", file=sys.stderr)
        return 1

    rendered_output = _render_provider_health_report(report, output_format)
    if output_path is not None:
        _write_output(Path(output_path), rendered_output)
        print(
            f"Wrote provider health report to {output_path} as {output_format}."
        )
        return _provider_health_exit_code(report.status, fail_on)

    print(rendered_output, end="" if rendered_output.endswith("\n") else "\n")
    return _provider_health_exit_code(report.status, fail_on)


def _handle_signals_classify(args: argparse.Namespace) -> int:
    timestamp = datetime.now(UTC)
    signals = [
        MarketSignal(
            symbol=symbol,
            name="composite_score",
            value=score,
            timestamp=timestamp,
            parameters={"source": "cli.signals.classify"},
        )
        for symbol, score in args.signal
    ]
    snapshot = classify_composite_signals(signals)
    snapshot = sort_signal_classifications(
        snapshot, SignalClassificationSort(args.sort)
    )
    rendered_output = _render_signal_classifications(snapshot, args.format)
    if args.output is not None:
        _write_output(Path(args.output), rendered_output)
        print(
            f"Wrote {len(snapshot.classifications)} rows to {args.output} "
            f"as {args.format}."
        )
        return 0

    print(rendered_output, end="" if rendered_output.endswith("\n") else "\n")
    return 0


def _handle_research_run(args: argparse.Namespace) -> int:
    logger = get_logger(__name__)
    request = ResearchRequest(
        symbol=args.symbol,
        horizon_days=args.horizon_days,
        provider=args.provider,
        as_of=_as_of_datetime(args.as_of),
    )
    service = create_default_market_data_service()
    workflow = DefaultResearchWorkflow(
        service,
        lookback_calendar_days=args.lookback_days,
    )
    try:
        result = asyncio.run(workflow.run(request))
    except ConfigurationError as exc:
        logger.error("Failed to run research workflow: %s", exc)
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except DataProviderError as exc:
        logger.error("Failed to run research workflow: %s", exc)
        print(f"error: {exc}", file=sys.stderr)
        return 1

    rendered_output = _render_research_result(result, args.format)
    if args.output is not None:
        _write_output(Path(args.output), rendered_output)
        return 0

    print(rendered_output, end="" if rendered_output.endswith("\n") else "\n")
    return 0


def _handle_replay_run(args: argparse.Namespace) -> int:
    logger = get_logger(__name__)
    symbol = args.symbol.strip().upper()
    if not symbol:
        print("error: symbol must not be empty.", file=sys.stderr)
        return 2
    if args.start > args.end:
        print(
            "error: start date must be earlier than or equal to end date.",
            file=sys.stderr,
        )
        return 2
    if args.view == "steps" and args.format != "json":
        print(
            "error: replay steps view only supports --format json.",
            file=sys.stderr,
        )
        return 2

    replay_start = _start_of_utc_day(args.start)
    replay_end = _end_of_utc_day(args.end)
    fetch_end = args.end + timedelta(days=1)
    service = create_default_market_data_service()
    try:
        frame = asyncio.run(
            service.get_daily_prices(
                symbol=symbol,
                start=args.start,
                end=fetch_end,
                provider=args.provider,
            )
        )
        replay_frame = _filter_replay_price_window(
            frame,
            start=replay_start,
            end=replay_end,
        )
        if len(replay_frame) > args.max_bars:
            print(
                "error: replay would process "
                f"{len(replay_frame)} bars, exceeding --max-bars {args.max_bars}.",
                file=sys.stderr,
            )
            return 2
        replay_result = HistoricalReplayService().run(
            replay_frame,
            symbol=symbol,
            interval=_REPLAY_DAILY_INTERVAL,
            strategies=create_strategy_collection([BaselineTrendRegimeStrategy()]),
            state_model=BaselineMarketStateModel(),
            start=replay_start,
            end=replay_end,
        )
    except ConfigurationError as exc:
        logger.error("Failed to run historical replay: %s", exc)
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except DataProviderError as exc:
        logger.error("Failed to run historical replay: %s", exc)
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        logger.error("Failed to run historical replay: %s", exc)
        print(f"error: {exc}", file=sys.stderr)
        return 1

    summary = summarize_historical_replay(replay_result)
    rendered_output = _render_replay_output(
        replay_result=replay_result,
        summary=summary,
        view=args.view,
        output_format=args.format,
    )
    if args.output is not None:
        try:
            _write_output(Path(args.output), rendered_output)
        except OSError as exc:
            logger.error("Failed to write replay output: %s", exc)
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(
            f"Wrote replay {args.view} to {args.output} as {args.format}.",
            file=sys.stderr,
        )
        return 0

    print(rendered_output, end="" if rendered_output.endswith("\n") else "\n")
    return 0


def _render_signal_classifications(
    snapshot: SignalClassificationSnapshot,
    output_format: str,
) -> str:
    if output_format == "table":
        return _render_signal_classifications_table(snapshot)
    if output_format == "json":
        return _render_signal_classifications_json(snapshot)
    raise ValueError(f"Unsupported output format: {output_format}")


def _render_signal_classifications_table(
    snapshot: SignalClassificationSnapshot,
) -> str:
    frame = pd.DataFrame(
        [
            {
                "symbol": classification.symbol,
                "score": classification.score,
                "classification": classification.level.value,
                "timestamp": classification.timestamp.isoformat(),
            }
            for classification in snapshot.classifications
        ]
    )
    if frame.empty:
        return "No data returned.\n"
    return f"{frame.to_string(index=False)}\n"


def _render_signal_classifications_json(
    snapshot: SignalClassificationSnapshot,
) -> str:
    payload = {
        "thresholds": {
            "strong_bearish": snapshot.thresholds.strong_bearish,
            "bearish": snapshot.thresholds.bearish,
            "bullish": snapshot.thresholds.bullish,
            "strong_bullish": snapshot.thresholds.strong_bullish,
        },
        "classifications": [
            {
                "symbol": classification.symbol,
                "score": classification.score,
                "classification": classification.level.value,
                "timestamp": classification.timestamp.isoformat(),
                "source_signal_name": classification.source_signal_name,
            }
            for classification in snapshot.classifications
        ],
    }
    return json.dumps(payload, ensure_ascii=False) + "\n"


def _render_research_result(result: ResearchResult, output_format: str) -> str:
    if output_format == "table":
        return _render_research_result_table(result)
    if output_format == "json":
        return _render_research_result_json(result)
    raise ValueError(f"Unsupported output format: {output_format}")


def _render_research_result_table(result: ResearchResult) -> str:
    analysis = result.analysis
    market_view = result.market_view
    composite = analysis.composite if analysis is not None else None
    as_of = result.request.as_of
    if as_of is None and analysis is not None:
        as_of = analysis.timestamp
    row = {
        "Symbol": result.request.symbol,
        "Status": result.status.value,
        "Requested Horizon": result.request.horizon_days,
        "As Of": _format_datetime_for_table(as_of),
        "Direction": _placeholder_if_none(
            market_view.direction if market_view is not None else None
        ),
        "Strength": _placeholder_if_none(
            market_view.strength if market_view is not None else None
        ),
        "Trend State": _placeholder_if_none(
            market_view.trend_state if market_view is not None else None
        ),
        "Momentum State": _placeholder_if_none(
            market_view.momentum_state if market_view is not None else None
        ),
        "Volatility State": _placeholder_if_none(
            market_view.volatility_state if market_view is not None else None
        ),
        "Composite Score": _placeholder_if_none(
            composite.score if composite is not None else None
        ),
        "Classification": _placeholder_if_none(
            composite.classification if composite is not None else None
        ),
        "Summary": result.summary or "-",
        "Warnings": _render_warning_summary(result.warnings),
    }
    frame = pd.DataFrame([row])
    return f"{frame.to_string(index=False)}\n"


def _render_research_result_json(result: ResearchResult) -> str:
    return json.dumps(result.to_dict(), ensure_ascii=False) + "\n"


def _render_replay_output(
    *,
    replay_result: HistoricalReplayResult,
    summary: HistoricalReplaySummary,
    view: str,
    output_format: str,
) -> str:
    if view == "summary":
        return _render_replay_summary(summary, output_format)
    if view == "steps" and output_format == "json":
        return json.dumps(replay_result.to_dict(), ensure_ascii=False) + "\n"
    raise ValueError(f"Unsupported replay view/format: {view}/{output_format}")


def _render_replay_summary(
    summary: HistoricalReplaySummary,
    output_format: str,
) -> str:
    if output_format == "table":
        return _render_replay_summary_table(summary)
    if output_format == "json":
        return json.dumps(summary.to_dict(), ensure_ascii=False) + "\n"
    if output_format == "csv":
        return _render_replay_summary_csv(summary)
    raise ValueError(f"Unsupported output format: {output_format}")


def _render_replay_summary_table(summary: HistoricalReplaySummary) -> str:
    frame = pd.DataFrame(_replay_summary_rows(summary))
    if frame.empty:
        return "No replay strategies returned.\n"
    return f"{frame.to_string(index=False)}\n"


def _render_replay_summary_csv(summary: HistoricalReplaySummary) -> str:
    frame = pd.DataFrame(_replay_summary_rows(summary))
    return frame.to_csv(index=False)


def _replay_summary_rows(summary: HistoricalReplaySummary) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for strategy in summary.strategies:
        rows.append(
            {
                "symbol": summary.symbol,
                "interval": summary.interval,
                "start_as_of": _format_datetime_for_table(summary.start_as_of),
                "end_as_of": _format_datetime_for_table(summary.end_as_of),
                "step_count": summary.step_count,
                "strategy_id": strategy.strategy.strategy_id,
                "strategy_version": strategy.strategy.strategy_version,
                "configuration_fingerprint": _placeholder_if_none(
                    strategy.strategy.configuration_fingerprint
                ),
                "applicable_count": strategy.applicable_count,
                "not_applicable_count": strategy.not_applicable_count,
                "insufficient_data_count": strategy.insufficient_data_count,
                "first_applicable_as_of": _format_datetime_for_table(
                    strategy.first_applicable_as_of
                ),
                "last_applicable_as_of": _format_datetime_for_table(
                    strategy.last_applicable_as_of
                ),
                "status_transition_count": strategy.status_transition_count,
            }
        )
    return rows


def _render_provider_diagnostics_report(
    report: ProviderDiagnosticsReport,
    output_format: str,
) -> str:
    if output_format == "table":
        return render_provider_diagnostics_report(report)
    if output_format == "json":
        return _render_provider_diagnostics_json(report)
    raise ValueError(f"Unsupported output format: {output_format}")


def _render_provider_diagnostics_json(report: ProviderDiagnosticsReport) -> str:
    payload = {
        "configured_provider_order": list(report.configured_provider_order),
        "known_provider_names": list(report.known_provider_names),
        "providers": [
            {
                "name": provider.name,
                "configured": provider.configured,
                "capabilities": list(provider.capabilities),
            }
            for provider in report.providers
        ],
    }
    return json.dumps(payload, ensure_ascii=False) + "\n"


def _render_provider_health_report(
    report: ProviderHealthReport,
    output_format: str,
) -> str:
    if output_format == "table":
        return render_provider_health_report(report)
    if output_format == "json":
        return _render_provider_health_json(report)
    raise ValueError(f"Unsupported output format: {output_format}")


def _render_provider_health_json(report: ProviderHealthReport) -> str:
    return json.dumps(report.to_payload(), ensure_ascii=False) + "\n"


def _render_daily_prices(frame: pd.DataFrame, output_format: str) -> str:
    if output_format == "table":
        if frame.empty:
            return "No data returned.\n"
        return f"{frame.to_string(index=False)}\n"
    if output_format == "json":
        return _render_json(frame)
    if output_format == "csv":
        return _render_csv(frame)
    raise ValueError(f"Unsupported output format: {output_format}")


def _render_json(frame: pd.DataFrame) -> str:
    records = frame.to_dict(orient="records")
    return json.dumps(records, default=_json_default, ensure_ascii=False) + "\n"


def _render_csv(frame: pd.DataFrame) -> str:
    serializable_frame = frame.copy()
    if "timestamp" in serializable_frame.columns:
        serializable_frame["timestamp"] = serializable_frame["timestamp"].map(
            _json_default
        )
    return serializable_frame.to_csv(index=False)


def _filter_replay_price_window(
    frame: pd.DataFrame,
    *,
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame):
        raise ValueError("daily price service must return a pandas DataFrame")
    if "timestamp" not in frame.columns:
        raise ValueError("daily price data missing timestamp column")
    filtered = frame.copy(deep=True)
    timestamps: list[pd.Timestamp] = []
    for value in filtered["timestamp"]:
        timestamp = pd.Timestamp(value)
        if pd.isna(timestamp):
            raise ValueError("daily price timestamp must not be missing")
        if timestamp.tzinfo is None:
            raise ValueError("daily price timestamp must be timezone-aware")
        timestamps.append(timestamp.tz_convert(UTC))
    filtered["timestamp"] = pd.Series(
        timestamps,
        index=filtered.index,
        dtype="datetime64[ns, UTC]",
    )
    mask = (filtered["timestamp"] >= pd.Timestamp(start)) & (
        filtered["timestamp"] <= pd.Timestamp(end)
    )
    return filtered.loc[mask].copy(deep=True).reset_index(drop=True)


def _write_output(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _json_default(value: object) -> object:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return str(value)


def _parse_iso_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"invalid date {value!r}; expected format YYYY-MM-DD"
        ) from exc


def _parse_positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid integer value {value!r}") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError(
            f"invalid integer value {value!r}; expected a positive integer"
        )
    return parsed


def _start_of_utc_day(value: date) -> datetime:
    return datetime(value.year, value.month, value.day, tzinfo=UTC)


def _end_of_utc_day(value: date) -> datetime:
    return datetime(
        value.year,
        value.month,
        value.day,
        23,
        59,
        59,
        999999,
        tzinfo=UTC,
    )


def _as_of_datetime(value: date | None) -> datetime | None:
    if value is None:
        return None
    return datetime(value.year, value.month, value.day, 23, 59, 59, tzinfo=UTC)


def _format_datetime_for_table(value: datetime | None) -> str:
    if value is None:
        return "-"
    return value.isoformat()


def _placeholder_if_none(value: object) -> object:
    if value is None:
        return "-"
    return value


def _render_warning_summary(warnings: object) -> str:
    if not isinstance(warnings, tuple):
        return "-"
    if not warnings:
        return "-"
    summary_items: list[str] = []
    for warning in warnings:
        code = getattr(warning, "code", None)
        message = getattr(warning, "message", None)
        if code is None or message is None:
            continue
        summary_items.append(f"{code}: {message}")
    return ", ".join(summary_items) if summary_items else "-"


def _parse_signal_argument(value: str) -> tuple[str, float]:
    original_value = value
    if "=" not in value:
        raise argparse.ArgumentTypeError(
            f"invalid --signal {original_value!r}; expected SYMBOL=SCORE"
        )

    symbol_text, score_text = value.split("=", 1)
    symbol = symbol_text.strip().upper()
    score_text = score_text.strip()

    if not symbol:
        raise argparse.ArgumentTypeError(
            f"invalid --signal {original_value!r}; symbol must not be empty"
        )
    if not score_text:
        raise argparse.ArgumentTypeError(
            f"invalid --signal {original_value!r}; score must not be empty"
        )

    try:
        score = float(score_text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"invalid --signal {original_value!r}; score must be numeric"
        ) from exc

    if not math.isfinite(score):
        raise argparse.ArgumentTypeError(
            f"invalid --signal {original_value!r}; score must be finite"
        )
    if score < -1.0 or score > 1.0:
        raise argparse.ArgumentTypeError(
            f"invalid --signal {original_value!r}; score must be within [-1.0, 1.0]"
        )

    return symbol, score


def _build_output_options_parser(
    formats: list[str],
    *,
    default: object = "table",
) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--format",
        choices=formats,
        default=default,
        help="Output format.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Write formatted output to a file instead of stdout.",
    )
    return parser


def _add_cache_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--cache",
        action="store_true",
        help="Use the local market data cache.",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Refresh the local market data cache before output.",
    )


def _create_market_data_cache() -> MarketDataCache:
    return MarketDataCache(DEFAULT_MARKET_DATA_CACHE_DIR)


def _load_cached_market_data_frame(
    *,
    cache: MarketDataCache,
    cache_key: MarketDataCacheKey,
    cache_enabled: bool,
    refresh: bool,
) -> pd.DataFrame | None:
    if not cache_enabled or refresh:
        return None

    try:
        if cache.exists(cache_key):
            return cache.load(cache_key)
    except DataProviderError as exc:
        get_logger(__name__).warning("Ignoring cache entry: %s", exc)
    return None


def _save_market_data_frame(
    *,
    cache: MarketDataCache,
    cache_key: MarketDataCacheKey,
    frame: pd.DataFrame,
) -> None:
    cache.save(cache_key, frame)


def _normalize_provider_name_arg(value: str) -> str:
    return normalize_provider_name(value)


def _normalize_data_providers_health_argv(
    argv: Sequence[str] | None,
) -> Sequence[str] | None:
    if argv is None:
        return None

    tokens = list(argv)
    try:
        data_index = tokens.index("data")
        providers_index = tokens.index("providers", data_index + 1)
        health_index = tokens.index("health", providers_index + 1)
    except ValueError:
        return argv

    move_options = {
        "--format": True,
        "--output": True,
        "--provider": True,
        "--fail-on": True,
        "--log-level": True,
        "--quiet": False,
    }
    moved_tokens: list[str] = []
    retained_tokens = tokens[: providers_index + 1]
    index = providers_index + 1
    while index < health_index:
        token = tokens[index]
        if token not in move_options:
            retained_tokens.append(token)
            index += 1
            continue

        moved_tokens.append(token)
        if move_options[token] and index + 1 < len(tokens):
            moved_tokens.append(tokens[index + 1])
            index += 2
            continue
        index += 1

    if not moved_tokens:
        return argv

    return [
        *retained_tokens,
        tokens[health_index],
        *tokens[health_index + 1 :],
        *moved_tokens,
    ]


def _provider_health_exit_code(status: str, fail_on: str) -> int:
    normalized_status = status.strip().lower()
    normalized_fail_on = fail_on.strip().lower()

    if normalized_fail_on == "never":
        return 0
    if normalized_fail_on == "failed":
        return int(normalized_status == "failed")
    if normalized_fail_on == "degraded":
        return int(normalized_status in {"degraded", "failed"})
    if normalized_fail_on == "unknown":
        return int(normalized_status in {"unknown", "degraded", "failed"})

    raise ValueError(f"Unsupported fail-on policy: {fail_on}")


def _configure_logging_for_args(args: argparse.Namespace) -> None:
    if (
        getattr(args, "data_command", None) == "providers"
        and getattr(
            args,
            "providers_command",
            None,
        )
        == "health"
    ):
        if getattr(args, "quiet", False):
            configure_logging("ERROR")
            return
        log_level = getattr(args, "log_level", None)
        configure_logging(log_level or "WARNING")
        return

    configure_logging()
