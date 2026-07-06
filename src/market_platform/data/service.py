"""Market data service with provider fallback policy."""

from __future__ import annotations

from datetime import date

import pandas as pd

from market_platform.data.exceptions import (
    AuthenticationError,
    DataProviderError,
    NetworkError,
    RateLimitError,
)
from market_platform.data.selection import ProviderSelectionPolicy


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
    ) -> pd.DataFrame:
        """Return the first successful daily price frame from the policy."""

        start_date = _coerce_date_like(start)
        end_date = _coerce_date_like(end)
        attempts: list[str] = []

        for candidate in self._policy.ordered_providers():
            provider_name = candidate.name
            try:
                frame = await candidate.provider.get_daily_prices(
                    symbol,
                    start_date,
                    end_date,
                )
            except AuthenticationError as exc:
                attempts.append(f"{provider_name}: authentication error: {exc}")
                if self._fallback_on_auth_error:
                    continue
                raise
            except NetworkError as exc:
                attempts.append(f"{provider_name}: network error: {exc}")
                continue
            except RateLimitError as exc:
                attempts.append(f"{provider_name}: rate limit error: {exc}")
                continue
            except DataProviderError as exc:
                attempts.append(f"{provider_name}: data provider error: {exc}")
                continue

            if not isinstance(frame, pd.DataFrame):
                attempts.append(
                    f"{provider_name}: invalid response type {type(frame).__name__}"
                )
                continue
            if frame.empty:
                attempts.append(f"{provider_name}: empty response")
                continue
            return frame

        attempts_text = "; ".join(attempts) if attempts else "no providers available"
        raise DataProviderError(
            "Unable to retrieve daily prices for "
            f"{symbol!r} from available providers. Attempts: {attempts_text}"
        )


def _coerce_date_like(value: date | str) -> date:
    if isinstance(value, date):
        return value
    return pd.Timestamp(value).date()
