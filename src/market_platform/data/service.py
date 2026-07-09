"""Market data service with provider fallback policy."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pandas as pd

from market_platform.data.capabilities import (
    DataCapability,
    normalize_provider_name,
    provider_supports_capability,
)
from market_platform.data.exceptions import (
    AuthenticationError,
    ConfigurationError,
    DataProviderError,
    NetworkError,
    RateLimitError,
)
from market_platform.data.selection import ProviderCandidate, ProviderSelectionPolicy


class MarketDataService:
    """Fetch market data through a provider selection policy."""

    def __init__(
        self,
        policy: ProviderSelectionPolicy,
        fallback_on_auth_error: bool = False,
    ) -> None:
        self._policy = policy
        self._fallback_on_auth_error = fallback_on_auth_error

    async def get_daily_prices(
        self,
        symbol: str,
        start: date | str,
        end: date | str,
        provider: str | None = None,
    ) -> pd.DataFrame:
        """Return daily prices using explicit or configured provider routing."""

        start_date = _coerce_date_like(start)
        end_date = _coerce_date_like(end)
        attempts: list[str] = []

        if provider is not None:
            candidates = [
                self._resolve_explicit_candidate(
                    provider,
                    DataCapability.DAILY_PRICES,
                )
            ]
        else:
            candidates = self._policy.ordered_providers(
                capability=DataCapability.DAILY_PRICES
            )

        for candidate in candidates:
            provider_name = candidate.name
            if not _candidate_supports_daily_prices(candidate):
                attempts.append(
                    f"{provider_name}: does not support daily_prices capability"
                )
                continue

            try:
                frame = await candidate.provider.get_daily_prices(
                    symbol,
                    start_date,
                    end_date,
                )
            except AuthenticationError as exc:
                attempts.append(f"{provider_name}: authentication error: {exc}")
                if provider is None and self._fallback_on_auth_error:
                    continue
                if provider is not None:
                    break
                raise
            except NetworkError as exc:
                attempts.append(f"{provider_name}: network error: {exc}")
                if provider is not None:
                    break
                continue
            except RateLimitError as exc:
                attempts.append(f"{provider_name}: rate limit error: {exc}")
                if provider is not None:
                    break
                continue
            except DataProviderError as exc:
                attempts.append(f"{provider_name}: data provider error: {exc}")
                if provider is not None:
                    break
                continue

            if not isinstance(frame, pd.DataFrame):
                attempts.append(
                    f"{provider_name}: invalid response type {type(frame).__name__}"
                )
                if provider is not None:
                    break
                continue
            if frame.empty:
                attempts.append(f"{provider_name}: empty response")
                if provider is not None:
                    break
                continue
            return frame

        attempts_text = "; ".join(attempts) if attempts else "no providers available"
        if provider is not None:
            raise DataProviderError(
                "Unable to retrieve daily prices for "
                f"{symbol!r} from provider {provider!r}. Attempts: {attempts_text}"
            )

        raise DataProviderError(
            "Unable to retrieve daily prices for "
            f"{symbol!r} from available providers. Attempts: {attempts_text}"
        )

    async def get_latest_price(
        self,
        symbol: str,
        provider: str | None = None,
    ) -> pd.DataFrame:
        """Return the latest price using explicit or configured provider routing."""

        attempts: list[str] = []

        if provider is not None:
            candidates = [
                self._resolve_explicit_candidate(
                    provider,
                    DataCapability.LATEST_PRICE,
                )
            ]
        else:
            candidates = self._policy.ordered_providers(
                capability=DataCapability.LATEST_PRICE
            )

        for candidate in candidates:
            provider_name = candidate.name
            if not _candidate_supports_latest_price(candidate):
                attempts.append(
                    f"{provider_name}: does not support latest_price capability"
                )
                continue

            try:
                frame = await candidate.provider.get_latest_price(symbol)
            except AuthenticationError as exc:
                attempts.append(f"{provider_name}: authentication error: {exc}")
                if provider is not None:
                    break
                if self._fallback_on_auth_error:
                    continue
                raise
            except NetworkError as exc:
                attempts.append(f"{provider_name}: network error: {exc}")
                if provider is not None:
                    break
                continue
            except RateLimitError as exc:
                attempts.append(f"{provider_name}: rate limit error: {exc}")
                if provider is not None:
                    break
                continue
            except DataProviderError as exc:
                attempts.append(f"{provider_name}: data provider error: {exc}")
                if provider is not None:
                    break
                continue

            if not isinstance(frame, pd.DataFrame):
                attempts.append(
                    f"{provider_name}: invalid response type {type(frame).__name__}"
                )
                if provider is not None:
                    break
                continue
            if frame.empty:
                attempts.append(f"{provider_name}: empty response")
                if provider is not None:
                    break
                continue
            return frame

        attempts_text = "; ".join(attempts) if attempts else "no providers available"
        if provider is not None:
            raise DataProviderError(
                "Unable to retrieve latest price for "
                f"{symbol!r} from provider {provider!r}. Attempts: {attempts_text}"
            )

        raise DataProviderError(
            "Unable to retrieve latest price for "
            f"{symbol!r} from available providers. Attempts: {attempts_text}"
        )

    async def get_intraday_prices(
        self,
        symbol: str,
        provider: str | None = None,
        interval: str = "1min",
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> pd.DataFrame:
        """Return intraday prices using explicit or configured provider routing."""

        start_dt, end_dt = _resolve_intraday_window(start=start, end=end)
        attempts: list[str] = []

        if provider is not None:
            candidates = [
                self._resolve_explicit_candidate(
                    provider,
                    DataCapability.INTRADAY_PRICES,
                )
            ]
        else:
            candidates = self._policy.ordered_providers(
                capability=DataCapability.INTRADAY_PRICES
            )

        for candidate in candidates:
            provider_name = candidate.name
            if not _candidate_supports_intraday_prices(candidate):
                attempts.append(
                    f"{provider_name}: does not support intraday_prices capability"
                )
                continue

            try:
                frame = await candidate.provider.get_intraday_prices(
                    symbol,
                    start_dt,
                    end_dt,
                    interval=interval,
                )
            except AuthenticationError as exc:
                attempts.append(f"{provider_name}: authentication error: {exc}")
                if provider is None and self._fallback_on_auth_error:
                    continue
                if provider is not None:
                    break
                raise
            except NetworkError as exc:
                attempts.append(f"{provider_name}: network error: {exc}")
                if provider is not None:
                    break
                continue
            except RateLimitError as exc:
                attempts.append(f"{provider_name}: rate limit error: {exc}")
                if provider is not None:
                    break
                continue
            except DataProviderError as exc:
                attempts.append(f"{provider_name}: data provider error: {exc}")
                if provider is not None:
                    break
                continue

            if not isinstance(frame, pd.DataFrame):
                attempts.append(
                    f"{provider_name}: invalid response type {type(frame).__name__}"
                )
                if provider is not None:
                    break
                continue
            if frame.empty:
                attempts.append(f"{provider_name}: empty response")
                if provider is not None:
                    break
                continue
            return frame

        attempts_text = (
            "; ".join(attempts)
            if attempts
            else "no provider succeeded for intraday prices"
        )
        if provider is not None:
            raise DataProviderError(
                "Unable to retrieve intraday prices for "
                f"{symbol!r} from provider {provider!r}. Attempts: {attempts_text}"
            )

        raise DataProviderError(
            "Unable to retrieve intraday prices for "
            f"{symbol!r} from available providers. Attempts: {attempts_text}"
        )

    def _resolve_explicit_candidate(
        self,
        provider: str,
        capability: DataCapability,
    ) -> ProviderCandidate:
        provider_name = normalize_provider_name(provider)

        for candidate in self._policy.candidates:
            if normalize_provider_name(candidate.name) != provider_name:
                continue
            if not candidate.enabled:
                raise ConfigurationError(f"Provider is disabled: {provider_name}")
            if not _candidate_supports_capability(candidate, capability):
                raise ConfigurationError(
                    f"Provider does not support {capability}: {provider_name}"
                )
            return candidate

        raise ConfigurationError(f"Unknown provider: {provider_name}")


def _coerce_date_like(value: date | str) -> date:
    if isinstance(value, date):
        return value
    return pd.Timestamp(value).date()


def _candidate_supports_daily_prices(candidate: ProviderCandidate) -> bool:
    return _candidate_supports_capability(candidate, DataCapability.DAILY_PRICES)


def _candidate_supports_latest_price(candidate: ProviderCandidate) -> bool:
    return _candidate_supports_capability(candidate, DataCapability.LATEST_PRICE)


def _candidate_supports_intraday_prices(candidate: ProviderCandidate) -> bool:
    return _candidate_supports_capability(candidate, DataCapability.INTRADAY_PRICES)


def _candidate_supports_capability(
    candidate: ProviderCandidate,
    capability: DataCapability,
) -> bool:
    if candidate.capabilities is not None:
        return capability in candidate.capabilities
    return provider_supports_capability(candidate.name, capability)


def _resolve_intraday_window(
    *,
    start: datetime | None,
    end: datetime | None,
) -> tuple[datetime, datetime]:
    end_dt = _coerce_datetime_like(end) if end is not None else datetime.now(UTC)
    start_dt = (
        _coerce_datetime_like(start)
        if start is not None
        else end_dt - timedelta(days=1)
    )
    return start_dt, end_dt


def _coerce_datetime_like(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
