# ADR 0027: Completed Daily Research Evidence and Technical Analysis Foundation

## Status

Accepted for v0.70.0 implementation.

## Context

Daily technical research needs reproducible completed-bar evidence before a
provider or CLI workflow presents it. v0.70 establishes that pure computation
boundary. v0.71 will own acquisition, application integration, and human
presentation.

## Decision

market_platform.research owns completed-daily evidence, one fixed v1 profile,
and an immutable technical snapshot. Generic EMA, MACD, Wilder RSI, Wilder ATR,
and ATR-percent formulas live in market_platform.indicators. The computation is
provider-independent, CLI-independent, replay-compatible, and reads no clock;
callers supply an aware analysis_as_of.

Provider daily aggregates are labelled by their canonical midnight-UTC calendar
date. The label is not converted to New York before its date is taken. The
initial supported timeframe is 1d, the analysis timezone is
America/New_York, and the session claim is only provider_daily_aggregate, never
exchange-calendar-certified RTH.

A label is completed only when it is earlier than the local New York calendar
date containing analysis_as_of. The same local-date aggregate remains excluded
after the close and becomes eligible only after local midnight. Future labels
are invalid. This conservative rule requires no exchange calendar and makes no
holiday, early-close, or session-certification claim.

## Formulas and availability

EMA seeds with the arithmetic mean of its first period and then applies
alpha = 2 / (period + 1). MACD subtracts the fast and slow SMA-seeded EMAs; its
signal is another SMA-seeded EMA over available MACD observations. RSI uses
Wilder average-gain/loss seeding and recurrence. ATR uses true range, a mean
seed, and Wilder recurrence; it is distinct from the existing structural
simple-average ATR. ATR percent is exactly 100 * ATR / close.

Unavailable warm-up positions are None. A snapshot is still valid and DEGRADED
with partial history. The fixed v1 profile uses EMA 8/20/144/169, MACD 12/26/9,
RSI 14, Wilder ATR 14, 20-return realized volatility, a 250-bar completeness
threshold, a seven-calendar-day stale threshold, and realized volatility
thresholds 0.15/0.30. It has no protocol or configurable v1 variant.

## Provenance and threat boundary

Exactly three new fingerprint families exist: daily research evidence, the
fixed profile, and the technical snapshot. Evidence fingerprints only rows
admitted after cutoff filtering. Normal projections contain finite JSON
numbers; fingerprint payloads replace float leaves with canonical_float strings
before canonical hashing. No display rounding occurs.

Retained values are revalidated for current canonical consistency. Evidence and
snapshots are self-contained value-semantic records: a coherent rewrite with
all invariants and fingerprints updated can remain valid. The fixed v1 profile
cannot be rewritten to another configuration. The snapshot retains no
DataFrame, provider, historical-price series, completed-series carrier, clock,
or service.

ATR-derived prices and EMA20 distance are research references only. They are not
executable stops, risk limits, approvals, position sizing, or order semantics.
The snapshot has descriptive trend, momentum, and volatility states and
introduces no BUY/SELL state, confidence percentage, TradingSignal, risk
artifact, or execution behavior.

## Consequences

v0.70 adds no provider call, Polygon behavior, CLI, workflow integration,
market-calendar dependency, rendering, persistence, or live behavior. v0.71
will acquire daily data, invoke this pure boundary, and own table/JSON and
human-readable warning presentation, including any `Vegas Tunnel` label.
