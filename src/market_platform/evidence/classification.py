"""Bounded semantic classifications shared by Evidence contracts."""

from enum import StrEnum


class EvidenceInformationClass(StrEnum):
    """The source-information classes that an Evidence Artifact may represent."""

    SOURCE_OBSERVATION = "source_observation"
    SOURCE_MEASUREMENT = "source_measurement"
    SOURCE_ASSERTION = "source_assertion"


class EvidenceAuthority(StrEnum):
    """The two and only two source-origin authority classifications."""

    PLATFORM_ORIGIN = "platform_origin"
    EXTERNAL_ORIGIN = "external_origin"


__all__ = ["EvidenceAuthority", "EvidenceInformationClass"]
