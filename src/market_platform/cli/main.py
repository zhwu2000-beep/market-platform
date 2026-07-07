"""Command line entrypoint."""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from typing import Protocol, cast

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

    if frame.empty:
        print("No rows returned.")
        return 0

    print(frame.to_string(index=False))
    return 0