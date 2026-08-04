# ADR 0020: Explicit Limit Price Choice Foundation

## Status

Accepted for v0.63.0 implementation.

## Context

V0.62 makes market or limit style explicit, but a complete broker-neutral order
specification remains premature. Price, TIF, session, instrument
correspondence, broker capability, and authorization are independent unresolved
invariants. A generic order-constraint container would hide them behind nullable
fields.

The smallest next invariant is the caller's explicit limit price and trading
currency. No released rule authorizes deriving that price from bid, ask, last,
midpoint, configuration, or broker defaults.

## Decision

Extend `market_platform.execution_planning` with
`LimitPriceChoice(limit_price, trading_currency)` and
`LIMIT_PRICE_CHOICE_SCHEMA = "limit_price_choice/v1"`.

The frozen, slotted value contains only canonical `limit_price`, exact
`trading_currency`, derived schema, and derived fingerprint. Price input must
be an exact built-in finite strictly positive `Decimal`; currency must be an
exact built-in ASCII string matching `[A-Z]{3}`. The currency token asserts
only the explicit price denomination, not ISO-registry status, settlement
currency, account currency, FX availability, or broker support.

## Price resource contract

The public v0.58 market-quote price contract is mirrored exactly: at most 128
digit characters, 64 fractional digits, and 256 fixed-point characters after
canonical trailing-zero treatment. Decimal-tuple calculations preflight all
bounds before fixed-point formatting, including exponent-driven zero expansion.
Projection is fixed-point, never scientific notation.

Insignificant trailing fractional zeros normalize, so `1.2300` and `1.23`
produce the same retained Decimal, projection, and fingerprint. No significant
digit is rounded. Canonicalization uses no float, quantize, normalize, unary
arithmetic, multiplication, division, or ambient Decimal context.

Canonical price means only exact, positive, bounded, deterministic,
fixed-point, and currency-denominated. It does not claim tick-size validity,
venue validity, price-collar compliance, broker acceptability, or
executability. Future capability validation must accept the exact price or
reject it; it must not silently round.

## Caller-authored and timeless boundary

The value is directly caller-authored. It has no guarded token,
constructor-state tuple, identity binding, retained quote, retained instruction,
retained instrument, retained style, factory, or provenance claim.
Context-free projection still rejects deleted slots, noncanonical retained
price, malformed retained currency, stale schema, and stale fingerprint.

The choice is timeless. It has no selected, created, quote, plan, validity, or
expiry time. Quote-derived pricing would require source quote and source-time
retention and belongs to another milestone.

## Style, instrument, and authority boundaries

MARKET consumes no limit-price artifact. A future specification factory must
reject LIMIT without a `LimitPriceChoice` and MARKET with one. V0.63 does not
bind or validate that relationship.

The choice is instrument-independent. A future LIMIT specification factory must
receive canonical instrument evidence and require the choice currency to equal
the instrument trading currency. V0.63 makes no current correspondence claim.

The choice is non-executable and is not risk, financial, short, compliance,
human, system, broker, or submission authorization.

## Deferred scope

V0.63 adds no generic constraint container, order specification, quote
derivation, style or instruction coupling, instrument/account binding, price
currency conversion, TIF, session, extended hours, tick size, rounding,
position effect, route, broker capability, broker payload, submission,
persistence, retry, cancellation, replacement, fills, or lifecycle behavior.

## Consequences

Every future LIMIT broker-neutral order specification must reference one
explicit canonical price/currency choice. The release adds exactly one
fingerprint family, `limit_price_choice/v1`, whose payload covers schema,
canonical fixed-point price text, and trading currency exactly once.
