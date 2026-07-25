# Architecture

## Data Layer
- `HTTPClient` is the shared network boundary for providers.
- `DataProvider` defines the common provider interface.
- `ProviderRegistry` resolves provider factories by normalized name.
- Concrete providers implement provider-specific endpoints and normalization.
- All provider methods return normalized `pandas.DataFrame` output.
- Provider configuration is validated lazily when a request is made, not at construction time.

The preferred flow is `HTTPClient` -> `DataProvider` -> `ProviderRegistry` ->
concrete providers such as `PolygonProvider`.

## Boundaries
- Providers do not call `httpx` directly.
- Providers do not expose vendor-specific response formats to the rest of the app.
- Downstream code depends on the standardized DataFrame schema and project exceptions.

## Canonical Historical Inputs
- `HistoricalPriceSeries` in `market_platform.data.historical` owns replay-grade
  validation, UTC normalization, stable ordering, identity, and defensive isolation
  for one historical OHLCV series.
- `HistoricalPricePrefix` represents a nonempty inclusive position in that series.
  Immutable row iteration is the analytical boundary; `to_dataframe()` is an
  explicit copy-producing compatibility path.
- `HistoricalPricePrefix.as_of` is the final included historical-data timestamp,
  while a `MarketObservation` `as_of` is its evaluation time. The temporal
  invariant is `HistoricalPricePrefix.as_of <= MarketObservation` evaluation
  `as_of`; exact equality is not required.
- Historical replay is an application workflow over canonical positions. It does
  not own historical-price validation or observation construction.
- Historical observation construction accepts either the existing raw DataFrame
  API or the public validated-prefix API. Both share identity, price facts,
  provenance, fingerprinting, and final model construction.
- See `docs/adr/0004-canonical-historical-input.md`.

