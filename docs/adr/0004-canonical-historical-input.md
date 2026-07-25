# ADR 0004: Canonical Historical Input

## Status
Accepted

## Context
- Historical replay and historical observation construction both accepted raw
  `pandas.DataFrame` inputs.
- Replay normalized the full frame once, then copied and revalidated every
  historical prefix during observation construction.
- Raw `.iloc` slices cannot express validated identity, UTC ordering, endpoint
  semantics, or mutation safety as a package boundary.
- v0.46.0 attribution identified repeated prefix preparation as the largest
  measured observation-construction cost.

## Decision
- Canonical historical-price validation belongs to
  `market_platform.data.historical`.
- `HistoricalPriceSeries` defensively owns one normalized, ordered, single-symbol,
  single-provider OHLCV series.
- `HistoricalPricePrefix` owns an inclusive full-frame position and derives its
  symbol, provider, `as_of`, and ordered rows from that series.
- `HistoricalPricePrefix.as_of` is the historical data endpoint. Observation
  `as_of` is the evaluation time; it may be later than the endpoint, with the
  invariant `HistoricalPricePrefix.as_of <= MarketObservation` evaluation
  `as_of`.
- Prefix row iteration is immutable. DataFrame compatibility is explicit and
  always returns a defensive copy.
- Historical replay remains an application workflow. It constructs one canonical
  series, selects prefix positions, and coordinates signal, structure, state, and
  strategy evaluation.
- Observation exposes a public validated-prefix builder. The existing DataFrame
  builder remains compatible by adapting raw input to the canonical boundary and
  delegating to the same construction path.
- Observation identity, price facts, provenance, fingerprinting, signal/structure
  conversion, and final model construction are shared by both entry points.

## Consequences
- Replay-grade OHLCV, identity, timestamp, ordering, and mutation validation has
  one owner.
- Default replay avoids per-step prefix DataFrame copies and full-prefix
  normalization.
- Custom structure services may request an explicit copied DataFrame prefix
  without exposing or mutating the canonical owner.
- Historical observation fingerprints and replay serialization remain compatible
  with v0.46.0 for equivalent normalized data and metadata.
- Fingerprint row traversal remains cumulative and is not optimized by this
  decision.
- The raw DataFrame observation adapter now applies replay-grade positive-OHLC and
  nonnegative-volume validation. Its supplied evaluation `as_of` may equal or
  follow the final canonical prefix timestamp, preserving v0.46.0 temporal
  behavior.

## Alternatives Considered
- Replay importing a private prepared observation helper, rejected because replay
  would own undocumented observation preconditions.
- Passing raw `.iloc` slices as trusted prefixes, rejected because mutation,
  identity, ordering, and endpoint invariants would remain implicit.
- Function-identity or monkeypatch detection, rejected because optimization
  selection should not depend on runtime binding identity.
- A generalized dataset or repository framework, rejected as unnecessary for the
  current in-memory boundary.
- Broad package restructuring, rejected because the required ownership can be
  established with one focused market-data module and public adapters.
