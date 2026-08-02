# ADR 0018: Broker-Neutral Execution Instruction Foundation

## Status

Accepted for the unreleased v0.61.0 implementation.

## Context

V0.60 derives one exact, bounded `PositionTargetTranslation` from complete canonical structural-risk evidence. The translation proves the signed target/current/delta relationship and blocks target-instrument open-order exposure, but deliberately remains an audit translation rather than an acquisition or disposal instruction.

A full execution plan or order specification remains premature. Released intent and policy models provide no source of truth for market/limit style, price, time in force, routing, broker capability, financial authorization, short authorization, approval, or submission.

## Decision

`market_platform.execution_planning` adds one broker-neutral instruction boundary. An exact canonical actionable translation derives exactly one immutable instruction. `buy` maps to buy, `sell` maps to sell, and the instruction quantity is the exact positive absolute value of the signed delta. A canonical `no_action` translation returns `None`; the translation remains its audit artifact and no no-action instruction, empty plan, or fingerprint is created.

The instruction is a deterministic acquisition or disposal proposal. It is non-executable and grants no financial, short, compliance, human, broker, or submission authority.

## Model and Identity

`BrokerNeutralExecutionInstruction` is frozen, slotted, and factory-owned. It contains only side, positive quantity, source translation fingerprint, canonical instrument ID and descriptor fingerprint, account fingerprint, copied `plan_as_of`, schema, and fingerprint. Its constant-sized projection is JSON-safe and contains no full translation or upstream evidence object.

V0.61 adds exactly one fingerprint family: `broker_neutral_execution_instruction/v1`. The source translation fingerprint transitively commits the context, decision, intent, position, and open-order evidence, so those fingerprints are not duplicated.

## Quantity and Time

Quantity is derived by inspecting the canonical delta Decimal tuple and clearing its sign bit. Coefficient and exponent are preserved exactly. No float, multiplication, unary context-sensitive arithmetic, quantization, normalization, or rounding is used.

The instruction inherits the v0.60 delta bounds: at most 129 digit characters, 64 fractional digits, and 258 fixed-point characters. It must be strictly positive. Zero terminates through `None` before construction.

`plan_as_of` is copied exactly from the translation. There is no new creation time, wall clock, `valid_until`, grace period, or revalidation helper.

## Correspondence Boundary

Derivation requires the exact `PositionTargetTranslation` runtime type and invokes its public `to_dict()` validation before inspecting action or delta. The instruction privately retains that exact validated translation.

The instruction also retains an independent primitive constructor-state tuple, an identity binding to the original tuple object, and a guarded token. Context-free serialization validates source correspondence, side/action and quantity/delta relationships, all copied evidence, schema, and fingerprint. Private retained state is unprojected, unfingerprinted, unversioned, and non-cryptographic. It detects repository-model fabrication but does not claim protection against arbitrary simultaneous process-memory rewriting.

## Instruction, Plan, and Order Separation

This release adds no plan wrapper or instruction collection. Cardinality is expressed by the function result: actionable translation produces one instruction; no-action produces `None`.

The instruction has no market, limit, stop, price, time-in-force, extended-hours, post-only, reduce-only, allow-short, or routing field. In particular, market is not a default and there is no unspecified order-type placeholder. Future order-specification and authorization application boundaries must supply authoritative policy before any broker request exists.

## Explicit Exclusions

V0.61 adds no broker API or payload, external symbol, broker account or order ID, client ID, submission, cancellation, replacement, fill, persistence, repository, CLI, TradingView, webhook, approval, compliance, financial or short authorization, buying power, cash sufficiency, margin, leverage, FX, notional, price multiplication, commission, slippage, market impact, scheduling, slicing, TWAP/VWAP, smart routing, retry, idempotency processing, reconciliation, filesystem, network, subprocess, environment, clock, randomness, logging side effect, or mutable registry.

## Consequences

The repository gains one clear semantic step from a signed position gap to a positive-quantity acquisition or disposal proposal without pretending to know how, whether, or where it will be ordered. Later milestones own order specification, authorization/application orchestration, broker mapping and requests, submission, and live lifecycle reconciliation.
