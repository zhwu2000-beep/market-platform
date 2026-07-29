# ADR 0013: Trading Signal Application Boundary

## Status

Accepted for v0.56.0 implementation.

## Context

V0.55 defines deterministic `TradingSignal` and pre-risk `OrderIntent` domain
models, but external adapters would otherwise need to construct those models
directly. The platform still has no authenticated ingress, persistence, account
state, risk decision, or execution layer.

## Decision

- `market_platform.application` exposes two synchronous operations: create one
  signal, or reconstruct one complete signal and create one intent at an
  explicit decision time. They are not combined by a flag or dispatcher.
- Requests use `trading_signal_application_request/v1` and
  `order_intent_application_request/v1`; responses use
  `trading_signal_application_response/v1` and
  `order_intent_application_response/v1`. Each request derives its own
  fingerprint. Responses do not have fingerprints.
- Both requests share one nested source/event/instrument/timeframe/target/time
  input. No nested schema or fingerprint family is introduced. Exact-key manual
  codecs reject missing and unknown fields at every level.
- Application identifiers accept only nonempty visible ASCII without
  whitespace. Fixed v1 limits are: source ID 128, source version 64, event ID
  256, symbol 64, venue 32, and timeframe 32 characters.
- External units use nonnegative fixed-point text matching
  `[0-9]+(?:\.[0-9]+)?`. Leading and trailing zeros are accepted and normalize
  semantically; signs, exponent notation, whitespace, commas, non-string JSON
  numerics, NaN, and infinity are rejected. Text is limited to 256 characters,
  128 total digits, and 64 fractional digits. There is no rounding or float
  conversion. Direct typed `Decimal` inputs are sized from tuple state before
  fixed-point materialization, so pathological exponents are rejected without
  constructing exponent-sized strings; positive zero is canonicalized before
  exponent sizing and signed negative zero remains invalid.
- External timestamps use a strict RFC-3339 subset with `T`, seconds, optional
  one-to-six digit fractions, and mandatory `Z` or numeric `±HH:MM`. Text is
  limited to 64 characters. Accepted instants normalize to the released UTC
  `+00:00` projection. Numeric offset hours are limited to 00–23 and minutes to
  00–59. `Z` and `+00:00` declare UTC; `-00:00` is rejected because it denotes
  an unknown rather than affirmative UTC offset.
- Request identity covers normalized semantic values, not raw syntax. Thus
  equivalent Decimal spellings, timestamp offsets, and instrument case produce
  equal requests and fingerprints. Raw transport bytes belong to future ingress
  evidence.
- The signal service constructs one source identity, instrument identity, and
  signal. The intent service reconstructs one signal, constructs the fixed
  exact-target policy, and invokes the released conversion once. Temporal domain
  errors propagate unchanged.
- Factory-only responses retain the complete domain object and serialize bounded
  JSON-safe domain projections. Complete typed correspondence checks bind every
  requested source, event, instrument, target, time, policy, and derived identity
  to the returned object. Decimal correspondence requires exact canonical tuple
  and fixed-point state; numeric or fingerprint equality alone is insufficient.
- The application boundary is trusted and local. Accepted source fields do not
  prove authentication, and accepted instruments do not prove existence,
  tradability, account permission, or broker mapping.
- An idempotency key is deterministic event identity, not idempotent processing.
  No seen-set, repository, cache, durable deduplication, conflict operation,
  queue, or outbox is added.

## Deferred Transport and Trading Layers

A future adapter owns payload-byte limits, authentication, authorization, TLS,
rate limiting, timeout, IP policy, replay protection, durable receipt, and raw
payload evidence. It maps external tickers such as `NASDAQ:AAPL` into separate
canonical venue and symbol fields before invoking this boundary.

TradingView schemas, HTTP, webhooks, credentials, Pine Script, browser
automation, accounts, positions, market snapshots, risk decisions, execution
plans, broker orders, persistence, CLI, Agent, and UI integrations remain
outside v0.56. An OrderIntent remains a pre-risk target proposal, not approval
or an executable broker instruction.

## Consequences

Future adapters gain one strict deterministic Python boundary without changing
v0.55 domain identities. Operational authentication, deduplication, and trading
authorization remain explicit future responsibilities rather than implicit
claims of request acceptance.
