# ADR 0028: Daily Technical Research Application and CLI Boundary

## Status

Accepted for v0.71.0 implementation.

## Context

v0.70 established the frozen, pure completed-daily evidence and technical
snapshot foundation. v0.71 provides the first daily-usable vertical slice
without changing those computations or the historical research workflow.

## Decision

`DailyTechnicalResearchWorkflow` explicitly requests Polygon daily aggregates
with no fallback. Polygon sends `adjusted=true`, `sort=asc`, and `limit=50000`,
and accepts a daily response only when its `adjusted` member is exact boolean
`true`. Provider label alone is not adjusted-data attestation. Before I/O,
every run requires the exact supported `MarketDataService` route, exact
production `PolygonProvider`, and their production daily acquisition methods.
Fake/custom providers merely named polygon, provider subclasses, and service
subclasses are rejected. The supported offline path is the real
`PolygonProvider` with an injected fake HTTP client. No global
`MarketDataService` behavior changed.

The request requires an exact datetime whose `tzinfo` and `utcoffset()` both
prove awareness, then normalizes deterministically to UTC. CLI `--as-of` uses
a frozen extended calendar grammar before parsing: full seconds, optional dot
fractions, and uppercase Z or a valid numeric offset. Complete retained request
validation occurs before provider inspection or I/O.

### Polygon daily timestamp semantics

A Polygon daily aggregate raw timestamp is interpreted as a UTC instant and
converted to America/New_York. The resulting New York calendar date is the
provider session-date label, represented as midnight UTC. This applies only to
daily aggregates; intraday timestamps retain their original instant semantics.

Acquisition uses an internal 450-calendar-day lookback: the inclusive end is
the New York date containing caller-supplied `analysis_as_of`, and the start is
450 days earlier. This can span 451 calendar dates; returned and admitted bar
counts remain authoritative and 250 bars are not guaranteed.

The additive request retains instrument, daily timeframe, canonical Polygon
provider, canonical UTC analysis time, and the exact fixed v1 profile. The
additive result retains only that request and the released snapshot. The
workflow reconstructs `HistoricalPriceSeries`, prepares completed adjusted
daily evidence, and invokes the released analyzer. It adds no schema or
fingerprint family. Historical `ResearchRequest`, `ResearchAnalysis`,
`ResearchResult`, `MarketView`, `DefaultResearchWorkflow`, and `research run`
remain unchanged.

The direct Polygon provider continues to raise `ConfigurationError` when its
API key is missing. Existing `MarketDataService` normalization may expose that
failure as `DataProviderError`; v0.71 accepts this established boundary and
does not change `data/service.py`. The CLI maps either acquisition failure to
exit code 1.

### CLI / rendering semantics

The CLI owns the optional current-time read. When `--as-of` is omitted,
`research analyze` resolves current UTC exactly once; downstream components
read no clock. Service construction is inside the exit-1 boundary;
parser/input failures remain exit 2. Table rendering validates through the
same complete result projection used by JSON before semantic field access, so
malformed retained state and request/snapshot mismatch cannot render.

The CLI renders one deterministic table or the semantic result JSON and can
write either through the existing output helper. Semantic request, result, and
snapshot values are not presentation-rounded, and JSON preserves those
semantic values. Human table output may apply deterministic presentation-only
formatting. Table formatting never changes fingerprints or retained semantic
values.

Support/resistance, `PriceContext`, composite `MarketView`, comparison, and
watchlists are deferred. Outputs remain descriptive and non-actionable: no
BUY/SELL, confidence percentage, `TradingSignal`, risk decision, broker object,
execution plan, or submission behavior is introduced.

## Consequences

Polygon is the only v0.71 acquisition route. Daily usability gains explicit
provenance and deterministic presentation while v0.70 purity and historical
research serialization remain compatible.
