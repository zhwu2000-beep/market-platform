# ADR 0002: Twelve Data Provider

## Status
Accepted

## Context
- The project currently has Polygon as the first concrete market data provider.
- The `ProviderRegistry` is intended to support multiple providers.
- A second provider is needed to validate the `DataProvider` interface and provider switching.
- Twelve Data is a suitable second provider for daily market data.

## Decision
- Add `TwelveDataProvider` as the second concrete provider.
- Place it initially in `src/market_platform/data/providers/twelvedata.py`.
- Use provider name `twelvedata`.
- Implement `get_daily_prices()` first.
- Keep `get_intraday_prices()` and `get_latest_price()` out of the initial scope.
- Register `twelvedata` in the default provider registry after the provider is implemented.
- Preserve lazy API key validation.
- Return the existing standardized historical OHLCV schema:
  - `symbol`
  - `timestamp`
  - `open`
  - `high`
  - `low`
  - `close`
  - `volume`
  - `provider`

## Consequences
- Upper layers can switch between `polygon` and `twelvedata` via `get_provider()`.
- The shared `DataProvider` interface will be tested against a second real provider.
- Provider-specific API differences must be normalized into the shared schema.
- Missing fields such as `volume` should be handled explicitly.
- The registry should remain lightweight and not become a service container.

## Alternatives Considered
- Adding a third provider immediately, rejected because the second provider is enough to validate architecture.
- Creating a `UniversalProvider`, rejected because concrete providers behind a shared `DataProvider` interface are cleaner.
- Implementing all Twelve Data methods immediately, rejected to keep v0.4.0 focused.
