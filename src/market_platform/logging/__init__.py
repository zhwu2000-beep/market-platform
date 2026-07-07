"""Logging helpers for market-platform."""

from __future__ import annotations

import logging

from rich.logging import RichHandler

from market_platform.config import get_settings


def configure_logging(log_level: str | None = None) -> None:
    """Configure application logging."""

    settings = get_settings()
    resolved_log_level = log_level or settings.log_level

    logging.basicConfig(
        level=resolved_log_level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)],
        force=True,
    )

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a logger by name."""

    return logging.getLogger(name)