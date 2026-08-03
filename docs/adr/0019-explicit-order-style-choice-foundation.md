# ADR 0019: Explicit Order Style Choice Foundation

## Status

Accepted for v0.62.0 implementation.

## Context

V0.61 produces a bounded non-executable buy/sell instruction, but neither the instruction nor any released intent, risk, state, or application model selects an order style. A full broker-neutral order specification remains premature because the repository has no authoritative price, time-in-force, session, position-effect, broker-capability, or authorization choices. A broad specification policy would bundle those unresolved concerns.

Absence of a style must never imply market. An implicit market default would silently choose immediacy and undefined slippage, price-protection, session, and broker behavior.

## Decision

Extend `market_platform.execution_planning` with one reusable caller-authored value:

- `OrderStyle` contains exactly `market` and `limit`;
- `OrderStyleChoice(style)` contains only style, derived schema, and derived fingerprint;
- `ORDER_STYLE_CHOICE_SCHEMA` is exactly `order_style_choice/v1`.

The caller must supply an exact `OrderStyle`. Strings, foreign enums, missing values, and `None` are rejected; there is no parser, fallback, or default. `MARKET` records only a style label and does not imply immediate execution. `LIMIT` records only a style label and intentionally carries no price.

The choice is frozen, slotted, bounded, directly constructible, deterministic, and fingerprinted. Its projection contains exactly `schema_version`, `style`, and `fingerprint`. Its fingerprint payload contains schema and style exactly once.

## Caller-authored boundary

Unlike the factory-derived v0.59-v0.61 results, this value records a legitimate caller choice. It retains no source artifact and uses no construction token, constructor-state tuple, or identity binding. Context-free projection still rejects deleted slots, wrong retained runtime types, stale schema, and stale fingerprint.

A caller may coherently construct either valid choice directly. This mechanism makes no factory-provenance or cryptographic-authenticity claim.

## Deferred semantics

V0.62 adds no instruction coupling, account, instrument, timestamp, price, quote, currency, tick size, rounding, TIF, session, extended-hours flag, route, short or position-effect field, broker capability, authorization, order specification, broker request, submission, persistence, or lifecycle behavior.

Stop and stop-limit styles require future schema evolution after trigger-price semantics exist. A later price/TIF/session constraint choice must precede a future `BrokerNeutralOrderSpecification`.

## Consequences

Every future order specification must reference an explicit canonical style choice. Missing style is invalid and never means market. The release adds exactly one fingerprint family and no executable behavior.
