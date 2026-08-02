# ADR 0016: Structural Risk Decision Foundation

## Status

Accepted for the unreleased v0.59.0 implementation.

## Context

The released Order Intent, instrument mapping, and four independently timed
trading-state snapshots provide the inputs for structural eligibility, but no
repository-owned domain boundary yet records which exact evidence was evaluated.
A decision must fail closed when released objects are malformed, retain bounded
audit identity, and avoid implying financial risk analysis or broker authority.

Structural risk means correspondence, timing, freshness, coverage, and quote
sufficiency only. It does not mean cash sufficiency, buying power, margin,
leverage, concentration, FX conversion, short authorization, target-position
delta, order netting, notional calculation, or execution approval.

## Decision

- `market_platform.risk` is a domain-only package. The repository owns its pure
  evaluator and all decision semantics. It adds no application operation,
  persistence, adapter, provider/broker access, TradingView/HTTP behavior, CLI,
  Agent, human approval, execution plan, or submission behavior.
- `RiskEvaluationContext` requires one released Order Intent, one released
  Instrument Resolution and mapping, all four v0.58 snapshots, an explicit
  coverage assertion, one structural policy, and a caller-supplied evaluation
  time. Retained released objects are independently reconstructed and compared
  by exact runtime type, fields, schemas, fingerprints, and full projections.
- Valid cross-object mismatches remain constructible. The evaluator, rather than
  context construction, reports instrument, account, temporal, freshness,
  coverage, and quote findings.
- Evaluation is deterministic, clock-free, stage-gated, and side-effect-free.
  A later evaluation requires a newly constructed context and a fresh evaluator
  run; there is no `valid_until`, expiry field, or revalidation helper.

## Identity Families

V0.59 adds exactly three fingerprint families:

1. `structural_risk_policy/v1`;
2. `risk_evaluation_context/v1`;
3. `risk_decision/v1`.

`RiskEvidenceCoverage`, `RiskFinding`, finding collections, enums, errors,
evaluator inputs, and a separate policy-identity model have no fingerprint.

## Structural Risk Policy

`StructuralRiskPolicy` is frozen and slotted. It contains:

- `policy_id`, matching `[a-z][a-z0-9._-]{0,63}`;
- `policy_version`, visible non-whitespace ASCII of length 1-64;
- an optional exact lowercase repository SHA-256 configuration fingerprint;
- nonnegative exact-`timedelta` maximum ages for cash, positions, open orders,
  and quotes;
- one nonnegative exact-`timedelta` maximum state skew;
- an exact quote requirement: `any_price`, `last`, or `bid_and_ask`.

There are no threshold defaults. Every field participates in the policy
fingerprint. Durations project as exact total-microsecond decimal strings without
floating-point conversion.

## Evidence Coverage

`RiskEvidenceCoverage` is a trusted-orchestration assertion, not authenticated
truth. Cash, positions, and open orders accept only `unverified` or
`complete_account`; quotes accept only `unverified` or `target_instrument`.
Adequate structural coverage requires complete-account coverage for all three
account snapshots and target-instrument coverage for quotes. Coverage has no
schema or fingerprint.

All four snapshots are required even when empty. They remain parallel evidence
inputs with independent sources and times; their composition makes no atomicity
claim.

## Evaluation Stages

The evaluator applies the following stages and stops where specified:

1. Reconstruct every retained input. Malformed or fabricated state raises a
   narrow correspondence error and produces no decision.
2. Evaluate intent timing under `[valid_from, expires_at)`. Before validity is
   `intent_not_yet_valid`; exact expiry or later is `intent_expired`. Either is
   `rejected`, and downstream evaluation stops.
3. Evaluate `resolution_future_dated`, half-open `mapping_inactive`, and exact
   `instrument_mismatch`. Any result is `indeterminate`, and later stages stop.
4. Compare complete cash, position, and open-order account identities. An
   `account_mismatch` is `indeterminate`, and later stages stop. Quotes remain
   account-independent.
5. Use the released v0.58 freshness evaluator for all four snapshots and collect
   every future-dated or stale result. Evaluate skew over the four snapshot
   `as_of` values only.
6. Collect every inadequate coverage result.
7. When quote coverage is adequate, locate the mapped canonical instrument ID.
   Missing target evidence is `quote_missing`; missing required fields are
   `quote_insufficient`. `any_price` accepts any valid matching quote, `last`
   requires last, and `bid_and_ask` requires both sides.
8. Produce `approved` only with no findings, `rejected` only for one intent
   temporal finding, otherwise a nonempty `indeterminate` decision.

## Reason Codes and Findings

The canonical reason order is:

1. `intent_not_yet_valid`;
2. `intent_expired`;
3. `resolution_future_dated`;
4. `mapping_inactive`;
5. `instrument_mismatch`;
6. `account_mismatch`;
7. `cash_future_dated`;
8. `cash_stale`;
9. `position_future_dated`;
10. `position_stale`;
11. `open_order_future_dated`;
12. `open_order_stale`;
13. `quote_future_dated`;
14. `quote_stale`;
15. `excessive_state_skew`;
16. `cash_coverage_inadequate`;
17. `position_coverage_inadequate`;
18. `open_order_coverage_inadequate`;
19. `quote_coverage_inadequate`;
20. `quote_missing`;
21. `quote_insufficient`.

`RiskFinding` is evaluator-owned, frozen, slotted, unversioned, and
unfingerprinted. Subjects are limited to `intent`, `mapping`, `instrument`,
`account`, `cash`, `positions`, `open_orders`, `quotes`, and `state`. Each
finding retains zero to four unique, lexicographically sorted repository
fingerprints. Decisions contain at most 32 findings, reject duplicate
`(reason_code, subject)` keys, and sort first by the fixed reason order and then
by subject. Caller order cannot affect decision identity.

## Decision Evidence

`RiskDecision` is factory-only, frozen, and slotted. It retains the outcome,
context, Order Intent, source signal, mapping, canonical descriptor, policy, four
snapshot, and evaluation-time identities. It also retains separate cash,
position, and open-order account fingerprints. The common account fingerprint
is the shared value when those three match and null otherwise, including when an
earlier stage stops before account evaluation.

The bounded projection contains only these identities, the canonical instrument
ID, the ordered bounded findings, schema, and decision fingerprint. It never
reproduces full snapshots or the full context. Correspondence validation rejects
impossible outcomes, stage mixtures, subjects, evidence references, account
relationships, ordering, schemas, timestamps, and stale fingerprints.

Each decision privately retains the exact canonical stage result used by guarded
construction. That result also retains an independent built-in tuple snapshot of
its constructor-time context fingerprint, outcome, findings, and common-account
state. Context-free validation compares current retained semantics against this
private record; context-aware validation also recomputes the result from the
canonical context. The tuple is unprojected, unfingerprinted, unversioned, and is
correspondence hardening rather than cryptographic protection. Guarded
construction also binds that original tuple by object identity in a separate
private immutable record, so replacing it with a new equal or forged tuple is
rejected. The binding is likewise unprojected, unfingerprinted, and unversioned.

## Consequences and Exclusions

A structurally approved short target is only structurally complete evidence; it
is not short authorization. An approved decision does not authorize broker
execution, reserve cash, calculate a target delta, net pending orders, or prove
that market or account facts remain current after `evaluation_as_of`.

Callers that need a later answer must acquire the required evidence, construct a
new context with the later explicit time, and run the evaluator again. Future
financial policy, application orchestration, persistence, human approval, and
broker execution remain separate releases and must not reinterpret this
structural decision as authority.
