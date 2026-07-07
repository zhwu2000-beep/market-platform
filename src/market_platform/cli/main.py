"""Command line entrypoint."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol, cast

import pandas as pd

from market_platform.data.exceptions import DataProviderError
from market_platform.data.factory import create_default_market_data_service
from market_platform.logging import configure_logging, get_logger


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
    fetch_parser.add_argument("--start", required=True, help="Start date, YYYY-MM-DD.")
    fetch_parser.add_argument("--end", required=True, help="End date, YYYY-MM-DD.")
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
    fetch_parser.set_defaults(handler=_handle_data_fetch)

    return parser


def run(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return an exit code."""

    parser = build_parser()
    args = parser.parse_args(argv)

    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 0

    return cast(CommandHandler, handler)(args)


def main(argv: Sequence[str] | None = None) -> None:
    """Run the command line interface."""

    configure_logging()
    raise SystemExit(run(argv))


def _handle_data_fetch(args: argparse.Namespace) -> int:
    logger = get_logger(__name__)
    service = create_default_market_data_service()

    try:
        frame = asyncio.run(
            service.get_daily_prices(
                symbol=args.symbol,
                start=args.start,
                end=args.end,
                provider=args.provider,
            )
        )
    except DataProviderError as exc:
        logger.error("Failed to fetch daily prices: %s", exc)
        print(f"error: {exc}", file=sys.stderr)
        return 1

    rendered_output = _render_daily_prices(frame, args.format)
    if args.output is not None:
        _write_output(Path(args.output), rendered_output)
        print(f"Wrote {len(frame)} rows to {args.output} as {args.format}.")
        return 0

    print(rendered_output, end="" if rendered_output.endswith("\n") else "\n")
    return 0


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


def _write_output(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _json_default(value: object) -> object:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return str(value)
