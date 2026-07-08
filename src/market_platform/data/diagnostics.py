"""Offline provider diagnostics for CLI reporting."""

from __future__ import annotations

from dataclasses import dataclass

from market_platform.config import get_settings
from market_platform.data.capabilities import (
    DEFAULT_PROVIDER_CAPABILITIES,
    DataCapability,
    parse_provider_order,
)


@dataclass(frozen=True, slots=True)
class ProviderDiagnosticsEntry:
    """Diagnostics for a single known provider."""

    name: str
    configured: bool
    capabilities: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProviderDiagnosticsReport:
    """Offline diagnostics for configured providers."""

    configured_provider_order: tuple[str, ...]
    known_provider_names: tuple[str, ...]
    providers: tuple[ProviderDiagnosticsEntry, ...]


def build_provider_diagnostics_report() -> ProviderDiagnosticsReport:
    """Build a provider diagnostics report without touching any network APIs."""

    settings = get_settings()
    configured_provider_order = tuple(
        parse_provider_order(settings.data_provider_order)
    )
    providers = tuple(
        ProviderDiagnosticsEntry(
            name=provider_name,
            configured=_provider_is_configured(provider_name, settings),
            capabilities=_format_capabilities(
                DEFAULT_PROVIDER_CAPABILITIES[provider_name]
            ),
        )
        for provider_name in DEFAULT_PROVIDER_CAPABILITIES
    )
    return ProviderDiagnosticsReport(
        configured_provider_order=configured_provider_order,
        known_provider_names=tuple(DEFAULT_PROVIDER_CAPABILITIES),
        providers=providers,
    )


def render_provider_diagnostics_report(report: ProviderDiagnosticsReport) -> str:
    """Render a provider diagnostics report as human-readable text."""

    lines = [
        "Provider diagnostics",
        (
            "Configured provider order: "
            f"{_format_provider_order(report.configured_provider_order)}"
        ),
        f"Known providers: {', '.join(report.known_provider_names)}",
        "",
    ]
    for provider in report.providers:
        configured = "yes" if provider.configured else "no"
        capabilities = ", ".join(provider.capabilities)
        lines.append(f"{provider.name}:")
        lines.append(f"  configured: {configured}")
        lines.append(f"  capabilities: {capabilities}")
    return "\n".join(lines) + "\n"


def _provider_is_configured(provider_name: str, settings: object) -> bool:
    if provider_name == "polygon":
        return bool(getattr(settings, "polygon_api_key", "").strip())
    if provider_name == "twelvedata":
        return bool(getattr(settings, "twelve_data_api_key", "").strip())
    return False


def _format_capabilities(capabilities: frozenset[DataCapability]) -> tuple[str, ...]:
    ordered_capabilities = (
        DataCapability.DAILY_PRICES,
        DataCapability.INTRADAY_PRICES,
        DataCapability.LATEST_PRICE,
        DataCapability.HEALTH_CHECK,
    )
    return tuple(
        capability.value
        for capability in ordered_capabilities
        if capability in capabilities
    )


def _format_provider_order(provider_order: tuple[str, ...]) -> str:
    if not provider_order:
        return "<default>"
    return ", ".join(provider_order)
