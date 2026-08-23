"""Metadata-only contracts for explicitly exposed Agent capabilities."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from market_platform.agent_exposure.daily_technical_strategy_response import (
    DAILY_TECHNICAL_STRATEGY_AGENT_RESPONSE_PROJECTION_SCHEMA_VERSION,
)
from market_platform.application.daily_technical_strategy import (
    DAILY_TECHNICAL_STRATEGY_APPLICATION_REQUEST_SCHEMA_VERSION,
    DAILY_TECHNICAL_STRATEGY_APPLICATION_RESPONSE_SCHEMA_VERSION,
)

AGENT_CAPABILITY_DESCRIPTOR_SCHEMA_VERSION = "agent_capability_descriptor/v1"
DAILY_TECHNICAL_INTELLIGENCE_CAPABILITY_ID = "daily_technical_intelligence/v1"

_VERSIONED_IDENTIFIER_PATTERN = re.compile(
    r"[a-z][a-z0-9_]*(?:/[a-z][a-z0-9._-]*)", re.ASCII
)


@dataclass(frozen=True, slots=True)
class AgentCapabilityDescriptor:
    """Non-executable metadata for one candidate Agent capability."""

    capability_id: str
    display_name: str
    description: str
    application_request_schema_version: str
    application_response_schema_version: str
    agent_response_projection_schema_version: str
    read_only: bool = field(init=False, default=True)
    schema_version: str = field(
        init=False,
        default=AGENT_CAPABILITY_DESCRIPTOR_SCHEMA_VERSION,
    )

    def __post_init__(self) -> None:
        _require_versioned_identifier(self.capability_id, "capability_id")
        _require_text(self.display_name, "display_name")
        _require_text(self.description, "description")
        _require_versioned_identifier(
            self.application_request_schema_version,
            "application_request_schema_version",
        )
        _require_versioned_identifier(
            self.application_response_schema_version,
            "application_response_schema_version",
        )
        _require_versioned_identifier(
            self.agent_response_projection_schema_version,
            "agent_response_projection_schema_version",
        )


def _require_versioned_identifier(value: object, field_name: str) -> None:
    if type(value) is not str or _VERSIONED_IDENTIFIER_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be an exact versioned identifier")


def _require_text(value: object, field_name: str) -> None:
    if type(value) is not str or not value or value.strip() != value:
        raise ValueError(f"{field_name} must be exact nonempty trimmed text")


DAILY_TECHNICAL_INTELLIGENCE_CAPABILITY = AgentCapabilityDescriptor(
    capability_id=DAILY_TECHNICAL_INTELLIGENCE_CAPABILITY_ID,
    display_name="Daily Technical Intelligence",
    description=(
        "Descriptive daily technical research, interpretation, assessment, "
        "and strategy."
    ),
    application_request_schema_version=(
        DAILY_TECHNICAL_STRATEGY_APPLICATION_REQUEST_SCHEMA_VERSION
    ),
    application_response_schema_version=(
        DAILY_TECHNICAL_STRATEGY_APPLICATION_RESPONSE_SCHEMA_VERSION
    ),
    agent_response_projection_schema_version=(
        DAILY_TECHNICAL_STRATEGY_AGENT_RESPONSE_PROJECTION_SCHEMA_VERSION
    ),
)

AGENT_EXPOSURE_CAPABILITY_ALLOW_LIST = (DAILY_TECHNICAL_INTELLIGENCE_CAPABILITY,)
_AGENT_EXPOSURE_CAPABILITY_IDS = frozenset(
    descriptor.capability_id for descriptor in AGENT_EXPOSURE_CAPABILITY_ALLOW_LIST
)


def is_agent_capability_allowed(capability_id: object) -> bool:
    """Return whether an exact capability ID is explicitly exposed to Agents."""

    return (
        type(capability_id) is str and capability_id in _AGENT_EXPOSURE_CAPABILITY_IDS
    )


__all__ = [
    "AGENT_CAPABILITY_DESCRIPTOR_SCHEMA_VERSION",
    "AGENT_EXPOSURE_CAPABILITY_ALLOW_LIST",
    "DAILY_TECHNICAL_INTELLIGENCE_CAPABILITY",
    "DAILY_TECHNICAL_INTELLIGENCE_CAPABILITY_ID",
    "AgentCapabilityDescriptor",
    "is_agent_capability_allowed",
]
