"""Offline provider health smoke checks."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import perf_counter
from typing import Any

import pandas as pd

from market_platform.config import get_settings
from market_platform.data.capabilities import (
    DataCapability,
    normalize_provider_name,
    parse_provider_order,
    provider_supports_capability,
)
from market_platform.data.exceptions import ConfigurationError
from market_platform.data.provider import DataProvider
from market_platform.data.registry import ProviderRegistry, create_default_registry


@dataclass(frozen=True, slots=True)
class ProviderHealthResult:
    """Health result for a single provider."""

    provider: str
    status: str
    healthy: bool | None
    latency_ms: int | None
    error_type: str | None
    error_message: str | None


@dataclass(frozen=True, slots=True)
class ProviderHealthReport:
    """Aggregate health results for the checked providers."""

    status: str
    providers: tuple[ProviderHealthResult, ...]

    def to_payload(self) -> dict[str, Any]:
        """Return a JSON-serializable payload."""

        return {
            "status": self.status,
            "providers": [
                {
                    "provider": provider.provider,
                    "status": provider.status,
                    "healthy": provider.healthy,
                    "latency_ms": provider.latency_ms,
                    "error_type": provider.error_type,
                    "error_message": provider.error_message,
                }
                for provider in self.providers
            ],
        }


def build_provider_health_report(provider: str | None = None) -> ProviderHealthReport:
    """Build a provider health report without surfacing tracebacks."""

    settings = get_settings()
    registry = create_default_registry()
    provider_names = _resolve_provider_names(provider, registry, settings)
    results = asyncio.run(
        _collect_provider_health_results(registry, provider_names, settings)
    )
    return ProviderHealthReport(
        status=_overall_status(results),
        providers=tuple(results),
    )


def render_provider_health_report(report: ProviderHealthReport) -> str:
    """Render a provider health report as text."""

    lines = [
        "Provider health",
        f"Overall status: {report.status}",
    ]
    if not report.providers:
        lines.append("No providers checked.")
        return "\n".join(lines) + "\n"

    lines.append("")
    frame = pd.DataFrame(
        [_result_to_table_row(result) for result in report.providers]
    )
    lines.append(frame.to_string(index=False))
    return "\n".join(lines) + "\n"


async def _collect_provider_health_results(
    registry: ProviderRegistry,
    provider_names: list[str],
    settings: object,
) -> list[ProviderHealthResult]:
    results: list[ProviderHealthResult] = []
    for provider_name in provider_names:
        provider = _create_provider(registry, provider_name, settings)
        start = perf_counter()
        try:
            raw_result = await provider.health_check()
        except Exception as exc:  # pragma: no cover - exercised in tests
            latency_ms = _elapsed_ms(start)
            results.append(
                ProviderHealthResult(
                    provider=provider_name,
                    status="failed",
                    healthy=False,
                    latency_ms=latency_ms,
                    error_type=type(exc).__name__,
                    error_message=str(exc) or None,
                )
            )
            continue

        latency_ms = _elapsed_ms(start)
        results.append(
            _normalize_health_result(provider_name, raw_result, latency_ms)
        )

    return results


def _resolve_provider_names(
    provider: str | None,
    registry: ProviderRegistry,
    settings: object,
) -> list[str]:
    if provider is not None:
        provider_name = normalize_provider_name(provider)
        if provider_name not in registry:
            raise ConfigurationError(f"Unknown provider: {provider_name}")
        if not _provider_is_capability_enabled(provider_name):
            raise ConfigurationError(
                f"Provider does not support health_check: {provider_name}"
            )
        return [provider_name]

    configured_order = parse_provider_order(
        str(getattr(settings, "data_provider_order", ""))
    )
    if configured_order:
        return [
            name
            for name in configured_order
            if name in registry and _provider_is_capability_enabled(name)
        ]
    return [
        name
        for name in registry.names()
        if _provider_is_capability_enabled(name)
    ]


def _create_provider(
    registry: ProviderRegistry,
    provider_name: str,
    settings: object,
) -> DataProvider:
    provider_kwargs = _provider_kwargs_from_settings(settings)
    return registry.create(provider_name, **provider_kwargs.get(provider_name, {}))


def _provider_kwargs_from_settings(settings: object) -> dict[str, dict[str, str]]:
    return {
        "polygon": {
            "api_key": str(getattr(settings, "polygon_api_key", "")),
        },
        "twelvedata": {
            "api_key": str(getattr(settings, "twelve_data_api_key", "")),
        },
    }


def _normalize_health_result(
    provider_name: str,
    raw_result: object,
    latency_ms: int,
) -> ProviderHealthResult:
    if isinstance(raw_result, pd.DataFrame):
        return _normalize_dataframe_health_result(
            provider_name,
            raw_result,
            latency_ms,
        )
    if isinstance(raw_result, bool):
        return ProviderHealthResult(
            provider=provider_name,
            status="ok" if raw_result else "failed",
            healthy=raw_result,
            latency_ms=latency_ms,
            error_type=None if raw_result else "HealthCheckFailed",
            error_message=None if raw_result else "provider reported unhealthy",
        )
    if isinstance(raw_result, dict):
        return _normalize_mapping_health_result(
            provider_name,
            raw_result,
            latency_ms,
        )
    if isinstance(raw_result, str):
        status = _normalize_status_label(raw_result)
        healthy = _status_is_healthy(status)
        return ProviderHealthResult(
            provider=provider_name,
            status=status,
            healthy=healthy,
            latency_ms=latency_ms,
            error_type=None if healthy else "HealthCheckFailed",
            error_message=None if healthy else raw_result,
        )

    return ProviderHealthResult(
        provider=provider_name,
        status="unknown",
        healthy=None,
        latency_ms=latency_ms,
        error_type=type(raw_result).__name__,
        error_message=str(raw_result) or "unsupported health_check result",
    )


def _normalize_dataframe_health_result(
    provider_name: str,
    frame: pd.DataFrame,
    latency_ms: int,
) -> ProviderHealthResult:
    if frame.empty:
        return ProviderHealthResult(
            provider=provider_name,
            status="failed",
            healthy=False,
            latency_ms=latency_ms,
            error_type="DataProviderError",
            error_message="health_check returned no rows",
        )

    row = {
        str(key): value
        for key, value in frame.iloc[0].to_dict().items()
    }
    return _normalize_mapping_health_result(provider_name, row, latency_ms)


def _normalize_mapping_health_result(
    provider_name: str,
    payload: dict[str, Any],
    latency_ms: int,
) -> ProviderHealthResult:
    status = _normalize_status_label(payload.get("status"))
    healthy = payload.get("healthy")
    healthy_value: bool | None = (
        healthy if isinstance(healthy, bool) else _status_is_healthy(status)
    )

    message = payload.get("message") or payload.get("error_message")
    error_type = payload.get("error_type")

    if healthy_value is True:
        return ProviderHealthResult(
            provider=provider_name,
            status=status if status != "unknown" else "ok",
            healthy=True,
            latency_ms=latency_ms,
            error_type=None,
            error_message=None,
        )

    if healthy_value is False:
        return ProviderHealthResult(
            provider=provider_name,
            status=status if status != "unknown" else "failed",
            healthy=False,
            latency_ms=latency_ms,
            error_type=_stringify(error_type) or "HealthCheckFailed",
            error_message=_stringify(message) or "provider reported unhealthy",
        )

    return ProviderHealthResult(
        provider=provider_name,
        status=status,
        healthy=None,
        latency_ms=latency_ms,
        error_type=_stringify(error_type),
        error_message=_stringify(message),
    )


def _result_to_table_row(result: ProviderHealthResult) -> dict[str, Any]:
    return {
        "provider": result.provider,
        "status": result.status,
        "healthy": _format_healthy(result.healthy),
        "latency_ms": result.latency_ms,
        "error_type": result.error_type or "",
        "error_message": result.error_message or "",
    }


def _overall_status(results: list[ProviderHealthResult]) -> str:
    if not results:
        return "unknown"

    healthy_count = sum(1 for result in results if result.healthy is True)
    if healthy_count == len(results):
        return "ok"
    if healthy_count == 0:
        return "failed"
    return "degraded"


def _format_healthy(value: bool | None) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return "unknown"


def _normalize_status_label(value: object) -> str:
    if value is None:
        return "unknown"
    label = str(value).strip().lower()
    return label or "unknown"


def _status_is_healthy(status: str) -> bool | None:
    if status in {"ok", "healthy", "up", "pass", "passed", "success", "true"}:
        return True
    if status in {"failed", "fail", "error", "unhealthy", "down", "bad", "false"}:
        return False
    return None


def _elapsed_ms(start: float) -> int:
    return max(0, int((perf_counter() - start) * 1000))


def _stringify(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _provider_is_capability_enabled(provider_name: str) -> bool:
    return provider_supports_capability(
        provider_name,
        DataCapability.HEALTH_CHECK,
    )
