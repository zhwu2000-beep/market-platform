"""Central logging configuration."""

import logging

from rich.logging import RichHandler

from market_platform.config import get_settings


def configure_logging() -> None:
    """Configure application logging once at process startup."""

    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)],
    )


def get_logger(name: str) -> logging.Logger:
    """Return a named logger."""

    return logging.getLogger(name)
