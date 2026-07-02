"""Command line entrypoint."""

from market_platform.logging import configure_logging, get_logger


def main() -> None:
    """Run the command line interface."""

    configure_logging()
    logger = get_logger(__name__)
    logger.info("market-platform CLI is installed.")
