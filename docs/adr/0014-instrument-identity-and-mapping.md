# ADR 0014: Instrument Identity and Mapping

## Status

Accepted for v0.57.0 implementation.

## Context

The released trading domain identifies instruments by symbol and venue. That
identity is appropriate for signal and Order Intent compatibility, but symbols,
venues, and external aliases can change while the underlying security remains
the same. Future account, position, open-order, market, risk, and execution
evidence needs a stable canonical key plus auditable mapping provenance.

Instrument mapping and trading-state snapshots were initially considered
together. They are split into v0.57 Instrument Identity and Mapping Foundation
and tentative v0.58 Trading State Snapshot Foundation. Releasing instrument
identity first keeps snapshot fingerprints from depending on an unsettled key
and bounds each review surface.

## Decision

- `market_platform.instruments` is a new domain-only package.
- Released `TradingInstrumentIdentity`, its
  `trading_instrument_identity/v1` schema, constructor, projection, and
  fingerprint remain unchanged.
- `CanonicalInstrumentId` is a caller-supplied, case-sensitive opaque registry
  key. It matches `[A-Za-z0-9][A-Za-z0-9._-]{0,127}` and has no schema or
  fingerprint. Core code does not generate UUIDs, hashes, timestamps, or
  symbol composites for it.
- `CanonicalInstrument` binds that stable ID to one exact released trading
  identity, the v1 `equity` or `etf` asset class, and one uppercase
  three-letter trading currency. Descriptor changes create new fingerprints
  under the same stable ID; descriptors are never mutated in place.
- `ExternalInstrumentIdentity` preserves an exact case-sensitive symbol and
  optional venue inside a lowercase opaque namespace. Namespace syntax is
  `[a-z][a-z0-9._-]{0,63}`. Symbols and venues are bounded visible ASCII and
  are never split, guessed, or normalized.
- `InstrumentMappingSourceIdentity` separately identifies mapping provenance by
  bounded source ID, version, and optional repository fingerprint. It is not a
  signal source, authentication result, market-data source, or broker account.
- `InstrumentMapping` is immutable and valid on the half-open interval
  `[valid_from, expires_at)`. `expires_at=None` is open-ended. Timestamps are
  caller supplied, truly aware, and physically stored in UTC.
- Applicability and resolution use an explicit `as_of`; domain code never reads
  the wall clock.
- The resolver accepts exact typed identities and only an exact built-in `list`
  or `tuple` of typed mappings. It rejects subclasses, arbitrary sequences and
  iterables, generators, sets, mappings, strings, and bytes before iteration.
  This concrete finite-container contract prevents hostile or infinite custom
  iteration. It validates records, orders them by mapping fingerprint, rejects
  repeated fingerprints, and is independent of caller insertion order.
- No matching record is `not found`. Matching but inactive records are
  `inactive`. Multiple active mappings agreeing on the same stable ID and exact
  descriptor are `ambiguous`; disagreement on either ID or descriptor is a
  `conflict`. All four outcomes are distinct and fail closed.
- Resolution never chooses first, ranks a source, applies priority, prefers the
  newest record, guesses case, partially matches, or infers an instrument from
  symbol text.
- `InstrumentResolution` retains the exact request identity, active mapping,
  and canonical UTC resolution time. It uses the bounded
  `instrument_resolution/v1` projection but deliberately has no fingerprint.

## Identity Families

The four public fingerprint schemas are:

- `canonical_instrument/v1`;
- `external_instrument_identity/v1`;
- `instrument_mapping_source/v1`;
- `instrument_mapping/v1`.

The canonical-instrument fingerprint covers its stable ID projection, complete
released trading-identity projection and fingerprint, asset class, and trading
currency. The external and source fingerprints cover their complete bounded
content. The mapping fingerprint covers complete external, canonical, and
source projections and fingerprints plus canonical validity timestamps.

A retained released `TradingInstrumentIdentity` must be independently
reconstructible through its public constructor. Its exact runtime type, schema,
symbol, venue, fingerprint, and complete projection must equal the reconstructed
canonical instance; a merely self-consistent fabricated fingerprint is
insufficient.

There is no fingerprint for the opaque canonical ID, a resolution, resolver
input collection, or resolver error.

## Application and Adapter Boundary

v0.56 application requests and fingerprints remain unchanged. Future trusted
orchestration follows:

```text
external adapter identity
    -> resolve_instrument_mapping(...)
    -> InstrumentResolution
    -> released TradingInstrumentIdentity
    -> existing v0.56 application boundary
```

Mapping provenance remains separate from the released signal fingerprint.
There is no mapping application service or codec in v0.57. A future operation
requires a real transport or registry boundary rather than a speculative
facade.

## Security and Operational Boundaries

All inputs are bounded passive values. Models contain no arbitrary metadata,
credentials, URLs or paths interpreted as such, callbacks, serializers, raw
provider payloads, connection objects, database handles, or mutable registries.
Construction and resolution perform no import, filesystem, environment,
network, subprocess, provider, broker, persistence, clock, UUID, or random
operation.

This release adds no TradingView behavior, HTTP, authentication, account state,
snapshot, risk decision, broker order, execution, CLI, Agent, or UI.

## Consequences

Future state and risk work can reference a stable canonical instrument and the
exact temporal mapping evidence used to obtain it. Equity and ETF are the only
v1 asset classes. Derivatives require a future schema with contract-specific
identity. Trading state snapshots remain tentative v0.58 work and are not
implemented here.
