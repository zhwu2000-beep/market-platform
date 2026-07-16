"""Research interpretation mode selection."""

from enum import StrEnum


class ResearchInterpretationMode(StrEnum):
    """Select the source used to interpret market facts."""

    STATE = "state"
    LEGACY = "legacy"


__all__ = ["ResearchInterpretationMode"]
