# ADR 0017: Position Target Translation Foundation

## Status

Accepted for the unreleased v0.60.0 implementation.

## Context

V0.59 proves that one exact Order Intent, instrument resolution, account state,
and quote evidence are structurally coherent at an explicit evaluation time. Its
bounded `RiskDecision` intentionally omits snapshot rows and grants no execution
authority. A broker-neutral execution plan would therefore be premature: order
type, price, time in force, lot size, short authorization, and submission policy
have no released source of truth.

The smallest coherent next boundary is mechanical translation of the released
desired final position into an exact signed target-minus-current quantity while
retaining the canonical context as the source of full position and open-order
rows.

## Decision

- `market_platform.execution_planning` owns a pure, domain-only translation.
- `translate_position_target(context, decision, plan_as_of)` independently
  reconstructs the complete `RiskEvaluationContext`, re-evaluates it through the
  public structural-risk evaluator, and requires the supplied decision to equal
  that canonical decision completely.
- Only an exact `approved` decision with empty findings, one common account, and
  complete-account position and open-order coverage can translate.
- `plan_as_of` is an exact canonical UTC datetime and must equal both risk
  evaluation times. There is no clock, `valid_until`, expiry duration, or
  revalidation helper. Later planning requires new evidence, context, decision,
  and translation.
- The resolved `CanonicalInstrumentId` is the only lookup key. Under approved
  complete-account coverage, an absent target position means canonical positive
  zero. A matching position contributes its exact signed quantity.
- Any target-instrument open-order exposure makes translation unavailable.
  Exposure sign and multiplicity are irrelevant: v0.60 performs no summation,
  offsetting, netting, or fill inference. Unrelated exposure does not block.

## Exact Translation

The released signal target is a desired final position, not an order quantity.
Its unsigned magnitude becomes `+U` for `long`, positive zero for `flat`, and
`-U` for `short`. The only arithmetic is:

```text
delta_quantity = target_quantity - current_quantity
```

Positive delta is `buy`, negative delta is `sell`, and zero is `no_action`.
Zero produces a normal, fingerprinted, auditable translation; it does not return
`None` and does not create an order.

Arithmetic is exact and independent of ambient `Decimal` precision or rounding.
Bounded fixed-point operands follow the released v0.58 contract: at most 128
digit characters, 64 fractional digits, and 256 fixed-point characters. The
derived delta permits the necessary carry digit, for at most 129 digit
characters and 64 fractional digits. Oversized released targets or unrepresentable
derived results are canonical but unavailable to v0.60. No float, rounding,
price multiplication, notional, cash, margin, FX, or other financial arithmetic
exists.

## Identity and Projection

V0.60 adds exactly one fingerprint family:

1. `position_target_translation/v1`.

The constant-sized projection covers action; risk context, decision, and intent
fingerprints; canonical instrument ID and descriptor fingerprint; common account
fingerprint; position and open-order snapshot fingerprints; exact plan time; and
canonical target, current, and delta strings. Full source objects and rows are
not retained publicly.

`PositionTargetTranslation` is factory-owned. It privately retains independent
canonical primitive constructor state and a separate immutable binding to the
exact original state tuple. Context-free validation checks token, binding
identity, state correspondence, arithmetic, action, schema, and fingerprint.
The token, state, and binding are private, unprojected, unfingerprinted,
unversioned, and non-cryptographic. This detects repository-model retained-state
fabrication; it is not authenticity, durable tamper-proof storage, or protection
against arbitrary simultaneous process-memory rewriting.

Before public context reconstruction, the execution-planning boundary performs
an exact-type and required-slot preflight over all four retained snapshot
headers, their exact tuple collections, and every cash, position, open-order,
and quote row. The preflight translates only missing or structurally fabricated
retained snapshot state into an execution-planning correspondence error. Public
released constructors remain authoritative for values, ordering, schemas,
fingerprints, and semantic correspondence; unexpected programming exceptions
continue to propagate.

## Explicit Exclusions

This release adds no broker-neutral order instruction, market/limit/stop style,
price, time in force, extended-hours flag, reduce-only or short permission,
routing, order identifier, submission, cancellation, replacement, fill,
persistence, repository, application service, CLI, TradingView, webhook,
approval workflow, compliance, buying power, cash sufficiency, margin, leverage,
FX, notional, commission, slippage, market impact, scheduling, slicing,
TWAP/VWAP, smart routing, retry, idempotency, or reconciliation. A future
Broker-Neutral Execution Plan may consume this translation only after its own
instructions and authorization boundaries are specified.

## Consequences

Structural approval remains evidence sufficiency, not permission to trade or
short. A `buy` or `sell` translation records the mechanical sign of a position
gap and is not an executable order. The new package depends only on public
trading, instrument, trading-state, and risk APIs plus the repository fingerprint
function; none of those packages imports it.
