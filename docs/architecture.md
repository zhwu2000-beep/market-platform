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
## Replay Specification and Windows
- `HistoricalReplaySpecification` is the immutable application request for one
  symbol and interval with explicit UTC `context_start`, `evaluation_start`, and
  `evaluation_end` values. It enforces
  `context_start <= evaluation_start <= evaluation_end`.
- `HistoricalReplayService.run_with_specification()` retains analytical data only
  inside `[context_start, evaluation_end]`, precomputes signals and default price
  structure across that complete retained context, and creates steps only inside
  the inclusive evaluation window.
- Requested boundaries do not imply exact bar coverage. A context window may have
  no returned pre-evaluation bars; execution requires only eligible evaluation
  rows.
- Legacy `HistoricalReplayService.run()` continues to treat its complete supplied
  DataFrame as context and optional `start`/`end` as inclusive evaluation bounds.
- The CLI keeps `--start`/`--end` as evaluation dates and adds optional
  `--context-start`, defaulting to `--start`. `--max-bars` counts evaluation rows,
  not retained context rows.
- Acquisition policy and provider selection remain interface concerns. Actual
  dataset coverage, run manifests, persistence, automatic warm-up, and exchange
  calendars are not part of this boundary.
- See `docs/adr/0005-replay-specification-context-window.md`.

## Replay Run Identity and Provenance
- `HistoricalReplaySpecification.fingerprint` identifies normalized requested
  instrument and temporal intent without changing its existing serialization.
- `HistoricalPriceSeries.content_fingerprint` identifies retained canonical
  symbol/timestamp/OHLCV contents. Provider and interval remain separate: provider
  is an actual provenance fact and interval belongs to Replay intent.
- `HistoricalReplayService.run_execution()` returns `HistoricalReplayExecution`,
  which wraps the unchanged result with immutable `HistoricalReplayRunProvenance`
  and a deterministic run fingerprint.
- Provenance records requested specification, actual retained context and evaluated
  bounds/counts, actual provider, signal/structure derivations, state model, ordered
  strategies, and caller-supplied software revision.
- The run fingerprint covers canonical execution inputs and resolved facts only.
  It excludes Replay outputs, timing, rendering, cache paths, and random values.
- Custom structure services require explicit derivation identity only through the
  provenance-producing API; legacy replay remains compatible.
- Provenance is an in-memory audit boundary, not a manifest, persisted artifact, or
  guarantee that provider data can later be recovered.
- See `docs/adr/0006-replay-run-identity-provenance.md`.
