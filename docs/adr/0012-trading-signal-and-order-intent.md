# ADR 0012: Trading Signal and Order Intent

## Status

Accepted

## Context

The platform has deterministic historical research and a transport-neutral
research application boundary, but no canonical live trading event or pre-risk
intent. The existing `market_platform.signals` package contains analytical
indicator values; those values have no source-event, idempotency, expiry, target
position, risk, or execution semantics.

## Decision

- `market_platform.trading` is a new domain-only package. It does not replace or
  alter analytical signals.
- `TradingInstrumentIdentity` identifies a symbol and venue. Venue-qualified
  external strings are rejected; future adapters perform that mapping.
- `TradingSignalSourceIdentity` identifies a producer by ID, version, and
  optional configuration fingerprint.
- Every `TradingSignal` requires a producer-owned `source_event_id`. The
  idempotency key covers source identity plus event ID; the signal fingerprint
  separately covers the complete canonical event content.
- Targets use `long`, `flat`, or `short` position semantics with unsigned exact
  `Decimal` units. Long and short require positive units; flat requires zero.
  Negative zero, binary float, integers, strings, non-finite values, and negative
  quantities are rejected.
- Decimal trailing zeros and exponent notation normalize to one exact,
  non-exponent fixed-point representation. No rounding or speculative precision
  limit is introduced.
- Signals require caller-supplied aware `generated_at`, `valid_from`, and
  `expires_at` values and enforce
  `generated_at <= valid_from < expires_at`. Timestamps normalize to UTC.
- Temporal applicability is evaluated at an explicit caller-supplied `as_of`.
  Validity is half-open: `[valid_from, expires_at)`. Domain code never reads the
  current clock or generates UUIDs.
- Pure event comparison classifies identical, conflicting-content, and unrelated
  signals without persistence or deduplication.
- `ExactTargetPositionIntentPolicy` is the only v1 conversion policy. It copies
  an active signal's exact target into one immutable, pre-risk `OrderIntent`.
- `decision_as_of` is explicit and fingerprint-significant. Intent validity
  starts at that decision and ends at the signal expiry, so an intent cannot
  outlive its source.
- `OrderIntent` has no lifecycle status. It is neither risk authorization nor a
  transaction or broker order.
- Public dictionary projections are deterministic, bounded, and JSON-safe.
  There is no external `from_dict()` codec or application operation in v0.55.

## Identity Hierarchy

```text
source fingerprint
    -> source event ID
    -> signal idempotency key
    -> signal fingerprint
    -> exact-target policy fingerprint
    -> Order Intent fingerprint
```

Equal idempotency keys identify one logical producer event. Equal signal
fingerprints prove equal canonical content. Reuse of one idempotency key with
different content is an integrity conflict.

## Risk and Broker Separation

Order Intent does not inspect or represent accounts, positions, funds, leverage,
market hours, price freshness, permissions, approval, order types, routing,
broker IDs, submissions, or fills. A future risk layer consumes intent plus
account, market, and policy state and creates a separate decision. Only a later
account-aware and broker-specific layer may derive and submit transactions.

## TradingView and Ingress Separation

A future TradingView adapter owns authentication, strict external decoding,
symbol/timeframe mapping, delivery acknowledgement, replay protection, and
duplicate handling. It maps values such as `NASDAQ:AAPL` into a canonical venue
and symbol before constructing a `TradingSignal`.

Transport evidence such as delivery ID, receipt time, source IP, raw-payload
checksum, and authentication outcome belongs to a future `SignalIngressReceipt`;
it is not implemented and does not enter signal identity. TradingView fields,
webhooks, HTTP, Pine Script, browser automation, credentials, and raw payloads
remain outside this domain.

## Consequences

The platform gains deterministic audit identities and a safe semantic boundary
for later ingress and risk work without adding persistence, repositories,
queues, application codecs, CLI commands, Agent tools, accounts, risk decisions,
broker models, or execution.
