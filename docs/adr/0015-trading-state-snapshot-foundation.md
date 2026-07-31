# ADR 0015: Trading State Snapshot Foundation

## Status

Accepted for the unreleased v0.58.0 implementation.

## Context

Released trading signals and Order Intents do not identify the account, cash,
positions, pending order exposure, or market prices that a future risk decision
will evaluate. V0.57 introduced stable canonical instrument IDs and exact
mapping evidence first, so snapshot identities can depend on a released stable
key without changing any v0.55-v0.57 identity.

Cash, position, open-order exposure, and quote facts share the same immutable
source, time, Decimal, collection, and fingerprint vocabulary. They therefore
remain one v0.58 release. A cross-snapshot bundle is deferred because it would
introduce account and instrument coverage, freshness and skew policy, and risk
correspondence while risking a false atomic-capture implication.

## Decision

- `market_platform.trading_state` is a new domain-only package. It depends on
  public `market_platform.instruments`, the platform fingerprint helper, and the
  standard library. Existing domains do not import it.
- `StateSnapshotSourceIdentity` contains a bounded visible-ASCII source ID and
  version plus an optional repository fingerprint. It has no role field and
  makes no authentication, authorization, or broker-trust claim.
- `TradingAccountIdentity` contains a lowercase institution namespace, an
  opaque visible-ASCII account ID, an exact `paper` or `live` environment, and
  one `[A-Z]{3}` base currency. The complete account ID remains in the auditable
  domain projection. Future transport layers own authorization and redaction.
- Financial values are exact `Decimal` instances. Canonical fixed-point text is
  limited to 256 characters, 128 digit characters, and 64 fractional digits.
  Projected sizes are computed from `Decimal.as_tuple()` before fixed-point
  formatting, so pathological exponents are rejected without exponent-sized
  allocation. Positive zero is special-cased; every negative zero is rejected.
- Cash is signed and may be negative or zero. Position quantity and open-order
  remaining quantity are signed and nonzero: positive means long or pending
  buy, while negative means short or pending sell. Market prices are strictly
  positive.
- All snapshot `as_of` values are caller-supplied aware datetimes physically
  stored as `datetime.UTC`. Microseconds are retained. No capture, receipt,
  generation, local-time, or wall-clock timestamp is added.
- Collection inputs accept only exact built-in `list` or `tuple` containers.
  Subclasses and arbitrary sequences or iterables are rejected before
  iteration. Count limits are checked before copying, validating, sorting,
  fingerprinting, or projection.
- Cash snapshots allow at most 32 balances. Position, open-order exposure, and
  quote snapshots each allow at most 10,000 records. All may be empty. Empty
  means exact source-reported empty state, not sufficient risk evidence.
- Cash balances sort by currency and reject duplicate currencies. Positions
  sort by canonical instrument ID and reject duplicate IDs. Open-order exposure
  sorts by external order ID then canonical instrument ID and rejects duplicate
  external order IDs. Quotes sort by canonical instrument ID and reject
  duplicate IDs. No collection silently aggregates or overwrites rows.
- `CashBalance`, `PositionRecord`, `OpenOrderExposure`, and `MarketQuote` are
  nested passive records without schemas or fingerprints. Snapshots reconstruct
  retained nested records through their public constructors and require exact
  Decimal tuple state and complete projection equality.
- A quote carries optional bid, ask, and last with at least one present. Supplied
  prices are strictly positive, and bid cannot exceed ask. Last need not lie
  inside the spread. Quote currency is owned by the separately retained
  canonical instrument used by future risk correspondence.

## Identity Families

The six public fingerprint schemas are:

- `state_snapshot_source/v1`;
- `trading_account_identity/v1`;
- `account_cash_snapshot/v1`;
- `position_collection_snapshot/v1`;
- `open_order_exposure_snapshot/v1`;
- `market_quote_collection_snapshot/v1`.

Every snapshot fingerprint covers its schema, complete source identity and
fingerprint, canonical `as_of`, and ordered record projections. Account-owned
snapshots also cover the complete account identity and fingerprint. Identical
facts from different sources therefore have different identities. Nested
records, evaluators, errors, and containers have no fingerprints.

## Temporal Evaluation

`evaluate_snapshot_freshness()` compares explicit snapshot and evaluation
times under a caller-supplied nonnegative maximum age. A snapshot after the
evaluation time is `future_dated`; age equal to the maximum is `fresh`; greater
age is `stale`. Zero maximum age is valid.

`evaluate_snapshot_skew()` accepts one through 32 timestamps in an exact
built-in list or tuple. It is `coherent` when `max(as_of) - min(as_of)` is less
than or equal to the caller-supplied nonnegative maximum skew, otherwise it is
`excessive_skew`. A singleton is coherent. Future-datedness is a freshness
question, not a skew result. Neither evaluator consults a clock or has a schema
or fingerprint.

## Atomicity and Future Risk

Every snapshot independently owns its source and `as_of`. Parallel snapshots
may have different times, and their composition does not prove atomic capture.
There is no bundle, bundle fingerprint, `is_atomic` flag, cross-snapshot account
matching, instrument coverage, or risk sufficiency claim in v0.58.

A future risk operation will combine an Order Intent, instrument mapping and
descriptor evidence, required state snapshot fingerprints, a risk-policy
fingerprint, and an explicit decision time. Any changed mapping, account,
source, cash, position, open-order, quote, or policy fingerprint invalidates
silent reuse of a prior Risk Decision or Execution Plan.

## Excluded Boundaries

V0.58 adds no application request, codec, service, response, persistence,
repository protocol, database model, cache, adapter, broker/provider access,
TradingView/HTTP behavior, authentication, Risk Policy, Risk Decision,
execution plan, CLI, Agent, filesystem access, network access, clock, UUID, or
randomness. Strings are bounded passive data and never interpreted as paths,
URLs, commands, credentials, or executable configuration.

## Consequences

Future adapters can translate independently sourced account and market facts
into exact immutable snapshots without importing provider or broker objects into
the domain. Future risk work can require the exact fingerprints it evaluated
while explicitly enforcing age and skew. Released v0.55-v0.57 schemas,
constructors, projections, fingerprints, and resolver behavior remain
unchanged.
