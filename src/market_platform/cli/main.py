"""Command line entrypoint."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import re
import sys
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol, cast

import pandas as pd

from market_platform.application import (
    PolygonCompletedDailyEvidenceCandidateApplicationRequest,
    PolygonCompletedDailyEvidenceCandidateApplicationService,
)
from market_platform.application.instrument_mapping_codec import (
    load_trusted_instrument_mapping_registry,
)
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
from market_platform.data.factory import (
    create_default_market_data_service,
    create_polygon_provider,
)
from market_platform.data.health import (
    ProviderHealthReport,
    build_provider_health_report,
    render_provider_health_report,
)
from market_platform.instruments import (
    ExternalInstrumentIdentity,
    InstrumentMappingError,
)
from market_platform.logging import configure_logging, get_logger
from market_platform.replay import (
    HistoricalReplayResult,
    HistoricalReplayService,
    HistoricalReplaySpecification,
    HistoricalReplaySummary,
    summarize_historical_replay,
)
from market_platform.research import (
    DailyTechnicalResearchRequest,
    DailyTechnicalResearchResult,
    DailyTechnicalResearchWorkflow,
    DefaultResearchWorkflow,
    IntegrityCheckedDailyTechnicalResearchResult,
    IntegrityCheckedDailyTechnicalResearchWorkflow,
    ResearchRequest,
    ResearchResult,
    ResearchTimeframe,
    TechnicalAnalysisWarning,
    construct_daily_technical_analysis_profile,
)
from market_platform.research.daily_instrument_integrity import (
    _preflight_daily_instrument_resolution,
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
    BaselineVolatilityRegimeStrategy,
    StrategyCollection,
    create_strategy_collection,
)
from market_platform.trading.instrument import TradingInstrumentIdentity

_REPLAY_DAILY_INTERVAL = "1day"
_DEFAULT_REPLAY_MAX_BARS = 500
_CANDIDATE_WARNING = "UNVALIDATED, UNADMITTED CANDIDATE — NOT PERMITTED FOR RESEARCH"


class CommandHandler(Protocol):
    """Callable command handler."""

    def __call__(self, args: argparse.Namespace) -> int:
        """Run a parsed command."""
        ...


class _StoreOnceAction(argparse.Action):
    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: object,
        option_string: str | None = None,
    ) -> None:
        seen: set[str] = getattr(namespace, "_research_analyze_seen", set())
        if self.dest in seen:
            parser.error(f"argument {option_string}: may not be repeated")
        namespace._research_analyze_seen = {*seen, self.dest}
        setattr(namespace, self.dest, values)


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

    evidence_parser = subparsers.add_parser(
        "evidence",
        help="Evidence inspection commands.",
    )
    evidence_subparsers = evidence_parser.add_subparsers(dest="evidence_command")
    candidate_parser = evidence_subparsers.add_parser(
        "candidate",
        help="Candidate construction commands.",
    )
    candidate_subparsers = candidate_parser.add_subparsers(dest="candidate_command")
    polygon_daily_parser = candidate_subparsers.add_parser(
        "polygon-daily",
        help="Construct and inspect one Polygon completed-daily Candidate.",
    )
    polygon_daily_parser.add_argument(
        "--ticker",
        required=True,
        action=_StoreOnceAction,
        help="Exact Polygon ticker.",
    )
    polygon_daily_parser.add_argument(
        "--venue",
        required=True,
        action=_StoreOnceAction,
        help="Exact external venue.",
    )
    polygon_daily_parser.add_argument(
        "--instrument-mappings",
        required=True,
        action=_StoreOnceAction,
        metavar="PATH",
        help="External trusted instrument-mapping document.",
    )
    polygon_daily_parser.add_argument(
        "--requested-from",
        required=True,
        type=_parse_iso_date,
        action=_StoreOnceAction,
        metavar="YYYY-MM-DD",
    )
    polygon_daily_parser.add_argument(
        "--requested-to",
        required=True,
        type=_parse_iso_date,
        action=_StoreOnceAction,
        metavar="YYYY-MM-DD",
    )
    polygon_daily_parser.add_argument(
        "--query-as-of",
        required=True,
        type=_parse_aware_iso_datetime,
        action=_StoreOnceAction,
        metavar="AWARE_ISO_8601_DATETIME",
    )
    polygon_daily_parser.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        action=_StoreOnceAction,
        help="Output format.",
    )
    polygon_daily_parser.add_argument(
        "--view",
        choices=["summary", "full"],
        default="summary",
        action=_StoreOnceAction,
        help="Inspection view.",
    )
    polygon_daily_parser.set_defaults(handler=_handle_evidence_candidate_polygon_daily)

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

    analyze_parser = research_subparsers.add_parser(
        "analyze",
        help="Analyze one instrument with adjusted Polygon daily data.",
    )
    analyze_parser.add_argument(
        "--symbol", required=True, action=_StoreOnceAction, help="Ticker symbol."
    )
    analyze_parser.add_argument(
        "--venue", required=True, action=_StoreOnceAction, help="Trading venue."
    )
    analyze_parser.add_argument(
        "--timeframe",
        choices=["1d"],
        default="1d",
        action=_StoreOnceAction,
        help="Research timeframe.",
    )
    analyze_parser.add_argument(
        "--provider",
        choices=["polygon"],
        default="polygon",
        action=_StoreOnceAction,
        help="Data provider.",
    )
    analyze_parser.add_argument(
        "--as-of",
        type=_parse_aware_iso_datetime,
        default=None,
        action=_StoreOnceAction,
        help="Aware ISO-8601 analysis timestamp.",
    )
    analyze_parser.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        action=_StoreOnceAction,
        help="Output format.",
    )
    analyze_parser.add_argument(
        "--output",
        default=None,
        action=_StoreOnceAction,
        help="Write formatted output to a file instead of stdout.",
    )
    analyze_parser.set_defaults(handler=_handle_research_analyze)

    verified_parser = research_subparsers.add_parser(
        "analyze-verified",
        help="Analyze Polygon daily data with trusted lifecycle metadata.",
    )
    verified_parser.add_argument("--symbol", required=True, action=_StoreOnceAction)
    verified_parser.add_argument("--venue", required=True, action=_StoreOnceAction)
    verified_parser.add_argument(
        "--instrument-mappings", required=True, action=_StoreOnceAction
    )
    verified_parser.add_argument(
        "--timeframe", choices=["1d"], default="1d", action=_StoreOnceAction
    )
    verified_parser.add_argument(
        "--provider", choices=["polygon"], default="polygon", action=_StoreOnceAction
    )
    verified_parser.add_argument(
        "--as-of", type=_parse_aware_iso_datetime, default=None, action=_StoreOnceAction
    )
    verified_parser.add_argument(
        "--format", choices=["table", "json"], default="table", action=_StoreOnceAction
    )
    verified_parser.add_argument("--output", default=None, action=_StoreOnceAction)
    verified_parser.set_defaults(handler=_handle_research_analyze_verified)

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
        "--context-start",
        type=_parse_iso_date,
        default=None,
        help=(
            "Context acquisition start date, YYYY-MM-DD, inclusive. "
            "Defaults to --start."
        ),
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


def _handle_evidence_candidate_polygon_daily(args: argparse.Namespace) -> int:
    logger = get_logger(__name__)
    if args.view == "full" and args.format != "json":
        print(
            "error: Candidate full view only supports --format json.",
            file=sys.stderr,
        )
        return 2
    try:
        external_identity = ExternalInstrumentIdentity(
            namespace="polygon",
            external_symbol=args.ticker,
            external_venue=args.venue,
        )
    except TypeError, ValueError:
        print(
            "error: ticker and venue must be exact canonical values.", file=sys.stderr
        )
        return 2
    if args.requested_from > args.requested_to:
        print(
            "error: requested-from must be earlier than or equal to requested-to.",
            file=sys.stderr,
        )
        return 2

    try:
        registry = load_trusted_instrument_mapping_registry(args.instrument_mappings)
    except Exception:
        return _candidate_command_error(
            logger,
            "trusted instrument mapping configuration failed",
        )

    try:
        provider = create_polygon_provider()
    except Exception:
        return _candidate_command_error(
            logger,
            "Polygon provider configuration failed",
        )

    try:
        request = PolygonCompletedDailyEvidenceCandidateApplicationRequest(
            external_identity=external_identity,
            mappings=registry.mappings,
            requested_from=args.requested_from,
            requested_to=args.requested_to,
            query_as_of=args.query_as_of,
        )
        service = PolygonCompletedDailyEvidenceCandidateApplicationService(provider)
    except TypeError, ValueError:
        return _candidate_command_error(logger, "Candidate construction failed")
    except Exception:
        return _candidate_command_error(
            logger,
            "unexpected Candidate command failure",
        )

    try:
        result = asyncio.run(service.execute(request))
    except InstrumentMappingError:
        return _candidate_command_error(
            logger,
            "canonical instrument resolution failed",
        )
    except DataProviderError:
        return _candidate_command_error(
            logger,
            "Polygon completed-daily acquisition failed",
        )
    except TypeError, ValueError:
        return _candidate_command_error(logger, "Candidate construction failed")
    except Exception:
        return _candidate_command_error(
            logger,
            "unexpected Candidate command failure",
        )

    try:
        rendered_output = _render_polygon_daily_candidate(
            result,
            view=args.view,
            output_format=args.format,
        )
    except Exception:
        return _candidate_command_error(
            logger,
            "unexpected Candidate command failure",
        )
    print(rendered_output, end="" if rendered_output.endswith("\n") else "\n")
    return 0


def _candidate_command_error(logger: Any, category: str) -> int:
    message = f"error: {category}."
    logger.error(message)
    print(message, file=sys.stderr)
    return 1


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
        print(f"Wrote provider health report to {output_path} as {output_format}.")
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


def _handle_research_analyze(args: argparse.Namespace) -> int:
    logger = get_logger(__name__)
    try:
        instrument = _parse_research_instrument(args.symbol, args.venue)
        analysis_as_of = args.as_of
        if analysis_as_of is None:
            analysis_as_of = datetime.now(UTC)
        request = DailyTechnicalResearchRequest(
            instrument=instrument,
            timeframe=ResearchTimeframe(args.timeframe),
            provider=args.provider,
            analysis_as_of=analysis_as_of,
            profile=construct_daily_technical_analysis_profile(),
        )
    except (TypeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        service = create_default_market_data_service()
        workflow = DailyTechnicalResearchWorkflow(service)
        result = asyncio.run(workflow.run(request))
        rendered_output = _render_daily_technical_research_result(result, args.format)
        if args.output is not None:
            _write_output(Path(args.output), rendered_output)
            return 0
    except (ConfigurationError, DataProviderError, ValueError, OSError) as exc:
        logger.error("Failed to analyze daily technical research: %s", exc)
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(rendered_output, end="" if rendered_output.endswith("\n") else "\n")
    return 0


def _handle_research_analyze_verified(args: argparse.Namespace) -> int:
    logger = get_logger(__name__)
    try:
        instrument = _parse_research_instrument(args.symbol, args.venue)
        analysis_as_of = args.as_of
        if analysis_as_of is None:
            analysis_as_of = datetime.now(UTC)
        request = DailyTechnicalResearchRequest(
            instrument=instrument,
            timeframe=ResearchTimeframe(args.timeframe),
            provider=args.provider,
            analysis_as_of=analysis_as_of,
            profile=construct_daily_technical_analysis_profile(),
        )
    except (TypeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    try:
        registry = load_trusted_instrument_mapping_registry(args.instrument_mappings)
        _preflight_daily_instrument_resolution(request, registry)
        service = create_default_market_data_service()
        workflow = IntegrityCheckedDailyTechnicalResearchWorkflow(service)
        result = asyncio.run(workflow.run(request, registry))
        rendered_output = _render_integrity_checked_daily_research_result(
            result, args.format
        )
        if args.output is not None:
            _write_output(Path(args.output), rendered_output)
            return 0
    except (
        ConfigurationError,
        DataProviderError,
        InstrumentMappingError,
        TypeError,
        ValueError,
        OSError,
    ) as exc:
        logger.error("Failed to analyze verified daily research: %s", exc)
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(rendered_output, end="" if rendered_output.endswith("\n") else "\n")
    return 0


def _handle_replay_run(args: argparse.Namespace) -> int:
    logger = get_logger(__name__)
    symbol = args.symbol.strip().upper()
    if not symbol:
        print("error: symbol must not be empty.", file=sys.stderr)
        return 2
    context_start_date = (
        args.start if args.context_start is None else args.context_start
    )
    if context_start_date > args.start:
        print(
            "error: context start date must be earlier than or equal to start date.",
            file=sys.stderr,
        )
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

    context_start = _start_of_utc_day(context_start_date)
    replay_start = _start_of_utc_day(args.start)
    replay_end = _end_of_utc_day(args.end)
    fetch_end = args.end + timedelta(days=1)
    specification = HistoricalReplaySpecification(
        symbol=symbol,
        interval=_REPLAY_DAILY_INTERVAL,
        context_start=context_start,
        evaluation_start=replay_start,
        evaluation_end=replay_end,
    )
    service = create_default_market_data_service()
    try:
        frame = asyncio.run(
            service.get_daily_prices(
                symbol=symbol,
                start=context_start_date,
                end=fetch_end,
                provider=args.provider,
            )
        )
        context_frame = _filter_replay_price_window(
            frame,
            start=context_start,
            end=replay_end,
        )
        evaluation_frame = _filter_replay_price_window(
            context_frame,
            start=replay_start,
            end=replay_end,
        )
        if len(evaluation_frame) > args.max_bars:
            print(
                "error: replay would process "
                f"{len(evaluation_frame)} bars, exceeding --max-bars {args.max_bars}.",
                file=sys.stderr,
            )
            return 2
        replay_result = HistoricalReplayService().run_with_specification(
            context_frame,
            specification,
            strategies=_default_replay_strategy_collection(),
            state_model=BaselineMarketStateModel(),
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


def _default_replay_strategy_collection() -> StrategyCollection:
    return create_strategy_collection(
        (
            BaselineTrendRegimeStrategy(),
            BaselineVolatilityRegimeStrategy(),
        )
    )


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


def _render_daily_technical_research_result(
    result: DailyTechnicalResearchResult,
    output_format: str,
) -> str:
    if output_format == "table":
        return _render_daily_technical_research_table(result)
    if output_format == "json":
        return json.dumps(result.to_dict(), ensure_ascii=False) + "\n"
    raise ValueError(f"Unsupported output format: {output_format}")


def _render_daily_technical_research_table(
    result: DailyTechnicalResearchResult,
    *,
    additional_rows: tuple[tuple[str, str, str], ...] = (),
) -> str:
    result.to_dict()
    snapshot = result.snapshot
    evidence = snapshot.evidence
    references = snapshot.volatility_references
    rows = [
        ("Identity", "Symbol", result.request.instrument.symbol),
        ("Identity", "Venue", result.request.instrument.venue),
        ("Identity", "Timeframe", result.request.timeframe.value),
        ("Data", "Provider", result.request.provider),
        ("Data", "Adjustment", evidence.adjustment_policy.value),
        ("Data", "Analysis As Of", evidence.analysis_as_of.isoformat()),
        (
            "Data",
            "Latest Completed Session",
            evidence.latest_completed_bar_session_date.isoformat(),
        ),
        ("Data", "Bars", str(evidence.bar_count)),
        ("Data", "Calendar Lag Days", str(evidence.calendar_lag_days)),
        ("Data", "Quality", snapshot.quality.value),
        ("Trend", "Latest Close", _format_analysis_number(snapshot.latest_close, 4)),
        ("Trend", "EMA8", _format_analysis_number(snapshot.ema_8, 4)),
        ("Trend", "EMA20", _format_analysis_number(snapshot.ema_20, 4)),
        ("Trend", "EMA144", _format_analysis_number(snapshot.ema_144, 4)),
        ("Trend", "EMA169", _format_analysis_number(snapshot.ema_169, 4)),
        ("Trend", "EMA Alignment", snapshot.ema_alignment.value),
        ("Trend", "Tunnel Position", snapshot.tunnel_position.value),
        ("Momentum", "MACD", _format_analysis_number(snapshot.macd_line, 4)),
        ("Momentum", "MACD Signal", _format_analysis_number(snapshot.macd_signal, 4)),
        (
            "Momentum",
            "MACD Histogram",
            _format_analysis_number(snapshot.macd_histogram, 4),
        ),
        ("Momentum", "RSI14", _format_analysis_number(snapshot.rsi_14, 2)),
        (
            "Volatility",
            "Wilder ATR14",
            _format_analysis_number(snapshot.wilder_atr_14, 4),
        ),
        ("Volatility", "ATR%", _format_analysis_number(snapshot.atr_percent_14, 4)),
        (
            "Volatility",
            "Realized Volatility",
            _format_analysis_number(snapshot.realized_volatility, 4),
        ),
        (
            "Volatility",
            "Current Drawdown",
            _format_analysis_number(snapshot.current_drawdown, 4),
        ),
        ("References", "-1 ATR", _format_analysis_number(references.one_atr_below, 4)),
        ("References", "+1 ATR", _format_analysis_number(references.one_atr_above, 4)),
        (
            "References",
            "-1.5 ATR",
            _format_analysis_number(references.one_and_half_atr_below, 4),
        ),
        (
            "References",
            "+1.5 ATR",
            _format_analysis_number(references.one_and_half_atr_above, 4),
        ),
        ("References", "-2 ATR", _format_analysis_number(references.two_atr_below, 4)),
        ("References", "+2 ATR", _format_analysis_number(references.two_atr_above, 4)),
        (
            "References",
            "EMA20 Distance %",
            _format_analysis_number(references.distance_from_ema20_percent, 4),
        ),
        ("Conclusion", "Trend State", snapshot.trend_state.value),
        ("Conclusion", "Momentum State", snapshot.momentum_state.value),
        ("Conclusion", "Volatility State", snapshot.volatility_state.value),
        ("Warnings", "Warnings", _render_technical_warnings(snapshot.warnings)),
        (
            "Warnings",
            "Unavailable Components",
            ", ".join(item.component.value for item in snapshot.unavailable) or "-",
        ),
        (
            "Provenance",
            "Dataset Fingerprint",
            evidence.dataset_content_fingerprint,
        ),
        ("Provenance", "Evidence Fingerprint", evidence.fingerprint),
        ("Provenance", "Profile Fingerprint", snapshot.profile.fingerprint),
        ("Provenance", "Snapshot Fingerprint", snapshot.fingerprint),
    ]
    rows.extend(additional_rows)
    table = pd.DataFrame(rows, columns=["Section", "Field", "Value"])
    return f"{table.to_string(index=False)}\n"


def _render_integrity_checked_daily_research_result(
    result: IntegrityCheckedDailyTechnicalResearchResult,
    output_format: str,
) -> str:
    if output_format == "json":
        return json.dumps(result.to_dict(), ensure_ascii=False) + "\n"
    if output_format != "table":
        raise ValueError(f"Unsupported output format: {output_format}")
    result.to_dict()
    integrity = result.integrity
    rows = [
        ("Integrity", "Verification", "verified"),
        ("Integrity", "Policy", integrity.integrity_policy.value),
        (
            "Integrity",
            "Canonical Instrument ID",
            integrity.canonical_instrument_id.instrument_id,
        ),
        (
            "Integrity",
            "External Identity",
            f"{integrity.resolved_external_identity.namespace}:{integrity.resolved_external_identity.external_symbol}@{integrity.resolved_external_identity.external_venue}",
        ),
        ("Integrity", "Mapping Valid From", integrity.mapping_valid_from.isoformat()),
        (
            "Integrity",
            "Mapping Expires At",
            "-"
            if integrity.mapping_expires_at is None
            else integrity.mapping_expires_at.isoformat(),
        ),
        (
            "Integrity",
            "Original Completed Bars",
            str(integrity.original_completed_bar_count),
        ),
        ("Integrity", "Admitted Bars", str(integrity.admitted_bar_count)),
        (
            "Integrity",
            "Excluded Before Valid From",
            str(integrity.excluded_before_valid_from_count),
        ),
        (
            "Integrity",
            "Excluded At/After Expires At",
            str(integrity.excluded_at_or_after_expires_at_count),
        ),
        (
            "Integrity",
            "Original Completed Range",
            f"{integrity.original_first_session_date.isoformat()}..{integrity.original_last_session_date.isoformat()}",
        ),
        (
            "Integrity",
            "Admitted Range",
            f"{integrity.admitted_first_session_date.isoformat()}..{integrity.admitted_last_session_date.isoformat()}",
        ),
        (
            "Integrity",
            "Mapping Source Fingerprint",
            integrity.mapping_source_fingerprint,
        ),
        ("Integrity", "Mapping Fingerprint", integrity.mapping_fingerprint),
        ("Integrity", "Registry Fingerprint", integrity.registry_fingerprint),
        ("Integrity", "Integrity Evidence Fingerprint", integrity.fingerprint),
    ]
    return _render_daily_technical_research_table(
        result.research,
        additional_rows=tuple(rows),
    )


def _format_analysis_number(value: float | None, places: int) -> str:
    if value is None:
        return "-"
    rendered = f"{value:.{places}f}".rstrip("0").rstrip(".")
    if rendered in {"-0", ""}:
        rendered = "0"
    if rendered == "0" and value != 0:
        rendered = f"{value:.{places}g}"
    return rendered


def _render_technical_warnings(
    warnings: tuple[TechnicalAnalysisWarning, ...],
) -> str:
    labels = {
        TechnicalAnalysisWarning.INSUFFICIENT_PROFILE_HISTORY: (
            "Insufficient history for the complete fixed profile"
        ),
        TechnicalAnalysisWarning.STALE_EVIDENCE: "Latest completed session is stale",
    }
    return "; ".join(labels[warning] for warning in warnings) or "-"


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


def _render_polygon_daily_candidate(
    result: Any,
    *,
    view: str,
    output_format: str,
) -> str:
    summary = _polygon_daily_candidate_summary(result)
    if view == "summary" and output_format == "table":
        return _render_polygon_daily_candidate_table(summary)
    if output_format != "json":
        raise ValueError("unsupported Candidate output format")
    projection: dict[str, object] = {"candidate_summary": summary}
    if view == "full":
        projection["artifact"] = result.artifact.to_dict()
        projection["material"] = result.material.to_dict()
    elif view != "summary":
        raise ValueError("unsupported Candidate view")
    return json.dumps(projection, ensure_ascii=False) + "\n"


def _polygon_daily_candidate_summary(result: Any) -> dict[str, object]:
    artifact = result.artifact
    material = result.material
    authorization = artifact.contract_authorization
    temporal = artifact.temporal_identity
    resolution = material.mapping_resolution_provenance
    request_provenance = material.request_provenance
    latest_session_date = None if not material.rows else material.rows[-1].session_date
    return {
        "candidate": {
            "lifecycle_state": "candidate",
            "semantic_authorization": "exact_production_membership",
            "validation": "not_performed",
            "admission": "absent",
            "validity": "not_evaluated",
            "freshness": "not_evaluated",
            "consumable": False,
            "research_permitted": False,
            "warning": _CANDIDATE_WARNING,
        },
        "artifact": {
            "schema_version": artifact.schema_version,
            "artifact_id": artifact.artifact_id,
            "artifact_version": artifact.artifact_version,
            "artifact_fingerprint": artifact.fingerprint,
            "evidence_type": artifact.evidence_type,
            "authority": artifact.authority.value,
            "information_class": artifact.information_class.value,
        },
        "contract_authorization": {
            "governing_contract_reference": artifact.governing_contract.to_dict(),
            "authorization_id": authorization.authorization_id,
            "authorization_version": authorization.authorization_version,
            "authorization_fingerprint": authorization.fingerprint,
            "material_schema": material.material_schema.to_dict(),
        },
        "source": {
            "vendor_service": material.vendor_service,
            "source_identity": material.source_reference.to_dict(),
            "api_base": material.api_base,
            "resolved_route": request_provenance.resolved_route,
            "multiplier": request_provenance.multiplier,
            "timespan": request_provenance.timespan,
            "adjusted": request_provenance.adjusted,
            "sort": request_provenance.sort,
            "limit": request_provenance.limit,
        },
        "subject_mapping": {
            "external_identity": material.external_instrument_identity.to_dict(),
            "canonical_subject": material.canonical_subject.to_dict(),
            "selected_mapping_fingerprint": resolution.mapping.fingerprint,
            "mapping_source": resolution.mapping.source.to_dict(),
            "resolved_as_of": resolution.resolved_as_of.isoformat(),
        },
        "range_time": {
            "requested_from": material.start_session_date,
            "requested_to": material.end_session_date,
            "query_as_of": material.query_as_of.isoformat(),
            "observation_period_start": (temporal.observation_period_start.isoformat()),
            "observation_period_end": temporal.observation_period_end.isoformat(),
            "response_received_at": temporal.platform_received_at.isoformat(),
            "artifact_created_at": temporal.artifact_created_at.isoformat(),
        },
        "material": {
            "material_fingerprint": material.fingerprint,
            "row_count": material.row_count,
            "latest_retained_session_date": latest_session_date,
        },
    }


def _render_polygon_daily_candidate_table(summary: dict[str, object]) -> str:
    rows: list[tuple[str, str, object]] = []
    for section, raw_fields in summary.items():
        fields = cast(dict[str, object], raw_fields)
        ordered_fields = (
            {"warning": fields["warning"], **fields}
            if section == "candidate"
            else fields
        )
        for field_name, value in ordered_fields.items():
            rows.append(
                (
                    section.replace("_", " ").title(),
                    field_name.replace("_", " ").title(),
                    _candidate_table_value(value),
                )
            )
    table = pd.DataFrame(rows, columns=["Section", "Field", "Value"])
    return f"{table.to_string(index=False)}\n"


def _candidate_table_value(value: object) -> object:
    if value is None:
        return "-"
    if type(value) is bool:
        return "true" if value else "false"
    if type(value) is dict:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value


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


def _parse_aware_iso_datetime(value: str) -> datetime:
    grammar = (
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
        r"(?:\.\d+)?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)"
    )
    if re.fullmatch(grammar, value) is None:
        raise argparse.ArgumentTypeError(
            f"invalid datetime {value!r}; expected extended aware ISO-8601"
        )
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"invalid datetime {value!r}; expected extended aware ISO-8601"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError(
            f"invalid datetime {value!r}; timezone is required"
        )
    return parsed.astimezone(UTC)


def _parse_research_instrument(
    symbol_value: object,
    venue_value: object,
) -> TradingInstrumentIdentity:
    if type(symbol_value) is not str or type(venue_value) is not str:
        raise TypeError("symbol and venue must be strings")
    symbol = symbol_value.strip().upper()
    venue = venue_value.strip().upper()
    if not symbol:
        raise ValueError("symbol must not be empty")
    if not venue:
        raise ValueError("venue must not be empty")
    if any(character.isspace() for character in symbol):
        raise ValueError("symbol must not contain internal whitespace")
    if any(character.isspace() for character in venue):
        raise ValueError("venue must not contain internal whitespace")
    return TradingInstrumentIdentity(symbol=symbol, venue=venue)


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
