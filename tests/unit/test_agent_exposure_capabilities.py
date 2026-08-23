"""Focused tests for the v0.76 Agent exposure architecture contract."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields

import pytest

import market_platform.agent_exposure as agent_exposure
from market_platform.agent_exposure import (
    AGENT_CAPABILITY_DESCRIPTOR_SCHEMA_VERSION,
    AGENT_EXPOSURE_CAPABILITY_ALLOW_LIST,
    DAILY_TECHNICAL_INTELLIGENCE_CAPABILITY,
    DAILY_TECHNICAL_INTELLIGENCE_CAPABILITY_ID,
    DAILY_TECHNICAL_STRATEGY_AGENT_RESPONSE_PROJECTION_SCHEMA_VERSION,
    AgentCapabilityDescriptor,
    is_agent_capability_allowed,
)
from market_platform.application import (
    DAILY_TECHNICAL_STRATEGY_APPLICATION_REQUEST_SCHEMA_VERSION,
    DAILY_TECHNICAL_STRATEGY_APPLICATION_RESPONSE_SCHEMA_VERSION,
)


class _StringSubclass(str):
    pass


def _descriptor(**overrides: object) -> AgentCapabilityDescriptor:
    values: dict[str, object] = {
        "capability_id": "other_intelligence/v1",
        "display_name": "Other Intelligence",
        "description": "A separate descriptive intelligence capability.",
        "application_request_schema_version": "other_request/v1",
        "application_response_schema_version": "other_response/v1",
        "agent_response_projection_schema_version": "other_agent_projection/v1",
    }
    values.update(overrides)
    return AgentCapabilityDescriptor(**values)  # type: ignore[arg-type]


def test_public_api_is_exact() -> None:
    assert agent_exposure.__all__ == [
        "AGENT_CAPABILITY_DESCRIPTOR_SCHEMA_VERSION",
        "AGENT_EXPOSURE_CAPABILITY_ALLOW_LIST",
        "DAILY_TECHNICAL_INTELLIGENCE_CAPABILITY",
        "DAILY_TECHNICAL_INTELLIGENCE_CAPABILITY_ID",
        "DAILY_TECHNICAL_STRATEGY_AGENT_RESPONSE_PROJECTION_SCHEMA_VERSION",
        "AgentCapabilityDescriptor",
        "DailyTechnicalStrategyAgentExposureFacade",
        "DailyTechnicalStrategyAgentResponseProjection",
        "is_agent_capability_allowed",
    ]


def test_descriptor_contract_is_frozen_slotted_metadata() -> None:
    descriptor = _descriptor()
    assert [item.name for item in fields(descriptor)] == [
        "capability_id",
        "display_name",
        "description",
        "application_request_schema_version",
        "application_response_schema_version",
        "agent_response_projection_schema_version",
        "read_only",
        "schema_version",
    ]
    assert not hasattr(descriptor, "__dict__")
    with pytest.raises(FrozenInstanceError):
        descriptor.display_name = "Changed"  # type: ignore[misc]


def test_descriptor_schema_and_read_only_semantics_are_fixed() -> None:
    descriptor = _descriptor()
    assert (
        AGENT_CAPABILITY_DESCRIPTOR_SCHEMA_VERSION == "agent_capability_descriptor/v1"
    )
    assert descriptor.schema_version == AGENT_CAPABILITY_DESCRIPTOR_SCHEMA_VERSION
    assert descriptor.read_only is True


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("capability_id", "other_intelligence"),
        ("capability_id", "Other_Intelligence/v1"),
        ("capability_id", _StringSubclass("other_intelligence/v1")),
        ("application_request_schema_version", "request"),
        ("application_response_schema_version", "response/v 1"),
        ("agent_response_projection_schema_version", "projection"),
    ],
)
def test_versioned_identifier_fields_fail_closed(
    field_name: str, value: object
) -> None:
    with pytest.raises(ValueError, match="exact versioned identifier"):
        _descriptor(**{field_name: value})


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("display_name", ""),
        ("display_name", " Daily Technical Intelligence"),
        ("description", "Description "),
        ("description", 1),
    ],
)
def test_text_metadata_requires_exact_nonempty_trimmed_strings(
    field_name: str, value: object
) -> None:
    with pytest.raises(ValueError, match="exact nonempty trimmed text"):
        _descriptor(**{field_name: value})


def test_daily_technical_intelligence_metadata_is_fixed() -> None:
    descriptor = DAILY_TECHNICAL_INTELLIGENCE_CAPABILITY
    assert DAILY_TECHNICAL_INTELLIGENCE_CAPABILITY_ID == (
        "daily_technical_intelligence/v1"
    )
    assert descriptor.capability_id == DAILY_TECHNICAL_INTELLIGENCE_CAPABILITY_ID
    assert descriptor.display_name == "Daily Technical Intelligence"
    assert descriptor.description == (
        "Descriptive daily technical research, interpretation, assessment, "
        "and strategy."
    )
    assert descriptor.read_only is True


def test_daily_technical_metadata_distinguishes_all_three_contracts() -> None:
    descriptor = DAILY_TECHNICAL_INTELLIGENCE_CAPABILITY
    assert descriptor.application_request_schema_version == (
        DAILY_TECHNICAL_STRATEGY_APPLICATION_REQUEST_SCHEMA_VERSION
    )
    assert descriptor.application_response_schema_version == (
        DAILY_TECHNICAL_STRATEGY_APPLICATION_RESPONSE_SCHEMA_VERSION
    )
    assert descriptor.agent_response_projection_schema_version == (
        DAILY_TECHNICAL_STRATEGY_AGENT_RESPONSE_PROJECTION_SCHEMA_VERSION
    )
    assert len(
        {
            descriptor.application_request_schema_version,
            descriptor.application_response_schema_version,
            descriptor.agent_response_projection_schema_version,
        }
    ) == 3


def test_allow_list_contains_exactly_daily_technical_intelligence() -> None:
    assert type(AGENT_EXPOSURE_CAPABILITY_ALLOW_LIST) is tuple
    assert AGENT_EXPOSURE_CAPABILITY_ALLOW_LIST == (
        DAILY_TECHNICAL_INTELLIGENCE_CAPABILITY,
    )


def test_allow_list_is_explicit_and_does_not_auto_expose_descriptors() -> None:
    assert is_agent_capability_allowed(DAILY_TECHNICAL_INTELLIGENCE_CAPABILITY_ID)
    assert not is_agent_capability_allowed(_descriptor().capability_id)
    assert not is_agent_capability_allowed("historical_replay_research/v1")
    assert not is_agent_capability_allowed("trading_signal/v1")


@pytest.mark.parametrize(
    "value",
    [
        None,
        1,
        True,
        DAILY_TECHNICAL_INTELLIGENCE_CAPABILITY,
        _StringSubclass(DAILY_TECHNICAL_INTELLIGENCE_CAPABILITY_ID),
    ],
)
def test_allow_list_membership_requires_an_exact_string_id(value: object) -> None:
    assert not is_agent_capability_allowed(value)


def test_descriptor_contains_no_execution_or_transport_hook() -> None:
    descriptor = DAILY_TECHNICAL_INTELLIGENCE_CAPABILITY
    assert all(
        not callable(getattr(descriptor, item.name)) for item in fields(descriptor)
    )
