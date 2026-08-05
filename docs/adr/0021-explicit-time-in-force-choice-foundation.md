# ADR 0021: Explicit Time-in-Force Choice Foundation

## Status

Accepted for the unreleased v0.64.0 implementation.

## Context

V0.61 provides a non-executable broker-neutral buy/sell instruction, v0.62
requires an explicit MARKET or LIMIT style, and v0.63 provides an explicit
canonical limit price and currency for future LIMIT specifications. A complete
order specification remains premature because time in force and session
participation are still unresolved independent choices.

Time in force is the next smallest invariant. Absence must never imply DAY.
The repository has canonical timestamps for signal, mapping, risk, and planning
evidence, but none is an authoritative order expiry. GTD therefore cannot be a
bare label and remains unavailable until a separate expiry contract exists.

## Decision

Extend `market_platform.execution_planning` with:

- `TimeInForce`, containing exactly DAY, GTC, IOC, and FOK in that order;
- `TimeInForceChoice(time_in_force)`, containing only the exact enum value,
  derived schema, and derived fingerprint;
- `TIME_IN_FORCE_CHOICE_SCHEMA = "time_in_force_choice/v1"`.

The caller must supply an exact `TimeInForce`. Strings, foreign enums, missing
values, `None`, and arbitrary objects are rejected. There is no parser,
fallback, alias, or default, and absence never means DAY.

## Requested semantics

DAY requests order eligibility through the applicable broker or venue order
day, with the exact boundary resolved downstream. It identifies no timestamp,
regular- or extended-session boundary, timezone, calendar, or broker cutoff.

GTC requests persistence across trading days or sessions until canceled,
subject to broker, venue, product, corporate-action, maximum-age, and
forced-cancellation rules. It does not guarantee indefinite persistence or
broker acceptance.

IOC requests immediate matching to the available extent and cancellation of
any unfilled remainder. Partial fill is permitted requested behavior, not a
guarantee of liquidity or execution. Immediate is relative to future
submission and matching, not construction time.

FOK requests immediate execution of the full order quantity; otherwise
cancellation without a partial fill. It does not prove liquidity, lot
compatibility, support, or successful execution.

These are canonical requested behaviors, not fulfillment results. The model
implements no matching, persistence, fill, or cancellation logic.

## GTD and temporal boundary

GTD is excluded from v1. A correct GTD artifact requires a separate future
milestone defining the explicit expiry source, canonical timestamp
representation, comparison anchor, and broker/calendar constraints.

Signal or intent `expires_at`, instruction `plan_as_of`, and the current wall
clock are not order expiry sources. The v0.64 choice is timeless and contains no
timestamp, date, duration, expiry, or clock access.

## Caller-authored and correspondence boundary

The frozen, slotted value is directly caller-authored. It has no construction
token, constructor-state tuple, identity binding, retained source, or factory.
A caller may legitimately construct any of the four choices; no provenance,
cryptographic authenticity, broker support, persistence, fill, or cancellation
guarantee is claimed.

Projection validates every required retained slot. The TIF must retain the
exact enum type. Schema and fingerprint must each retain exact built-in `str`
types before equality comparison, so equality-spoofing objects and exact-value
string subclasses are rejected. Missing or malformed retained state raises
`ExecutionPlanningCorrespondenceError`; unrelated programming exceptions
propagate.

The projection contains exactly `schema_version`, lowercase
`time_in_force`, and `fingerprint`. The `time_in_force_choice/v1`
fingerprint payload covers schema and canonical lowercase TIF value exactly
once.

## Independence and future compatibility

The choice retains no order style, limit price, instruction, instrument,
account, side, quantity, plan time, session, or capability profile. V0.64
implements no MARKET/TIF or LIMIT/TIF compatibility matrix.

A future broker-neutral specification factory must require exactly one
`TimeInForceChoice`, conditionally require a `LimitPriceChoice` for LIMIT,
and validate style, price, instrument currency, and any explicit session
correspondence. Later capability validation owns supported TIFs, style/TIF
combinations, maximum GTC age, IOC/FOK support, session compatibility, venue
restrictions, and forced-cancellation conditions.

## Authority boundary

A TIF choice is non-executable. It is not structural, financial, compliance,
human, system, or broker approval; permission to trade or short; order
acceptance; submission authority; or a live cancellation command.

## Explicit exclusions

V0.64 adds no GTD, expiry model, timestamp, date, duration, wall clock, session,
extended hours, style or price coupling, instruction or identity binding,
compatibility matrix, broker capability, authorization, order specification,
broker request, submission, persistence, cancellation operation, fill,
replacement, retry, or lifecycle behavior.

## Consequences

Every future broker-neutral order specification must bind one explicit
canonical DAY, GTC, IOC, or FOK choice. Missing TIF is incomplete, not DAY. The
release adds exactly one fingerprint family and no executable behavior.
