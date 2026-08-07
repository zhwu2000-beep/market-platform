# ADR 0024: Broker Execution Capability Foundation

## Status

Accepted for the v0.67.0 implementation.

## Context

V0.66 provides a complete, deterministic `BrokerNeutralOrderSpecification`,
but deliberately makes no claim that an execution target supports its asset,
currency, venue, style, time-in-force, session, or combined order policy. The
next pure-domain boundary must represent declared structural support and produce
stable compatibility evidence without introducing broker integration.

Structural compatibility is narrower than broker executability. It excludes
quantity, lot and fractional-share rules, tick sizes, price collars and bands,
product restrictions, account rules, live market state, authorization, mapping,
routing, and submission.

## Decision

`market_platform.execution_planning` adds a factory-owned
`BrokerExecutionCapabilityProfile` and evaluator-owned
`BrokerExecutionStructuralCompatibilityResult`. Their schemas are
`broker_execution_capability_profile/v1` and
`broker_execution_structural_compatibility_result/v1`.

The profile binds one opaque execution-target ID to nonempty canonical tuples of
supported asset classes, trading currencies, venues, and exact
`(OrderStyle, TimeInForce, SessionParticipation)` combinations. The target ID is
an identifier only; it has no credentials, account, URL, endpoint, or connection
semantics.

The evaluator accepts one exact validated profile and one exact validated
broker-neutral specification. It returns `compatible` only when every declared
structural dimension is supported. Normal incompatibility is a result, never an
exception.

## Canonical domains and ordering

All collections are exact immutable tuples. Inputs are rejected rather than
coerced, normalized, or sorted. Duplicate and noncanonical values fail.

The v1 schema freezes explicit exhaustive rank maps:

- asset classes: `EQUITY`, `ETF`;
- order styles: `MARKET`, `LIMIT`;
- time in force: `DAY`, `GTC`, `IOC`, `FOK`;
- session participation: `REGULAR_ONLY`, `REGULAR_AND_EXTENDED`;
- rejection reasons: asset class, currency, venue, style, TIF, session, then
  exact combination.

Order combinations sort by style rank, then TIF rank, then session rank. The
maximum asset-class and combination counts derive from the frozen rank spaces;
the current combination maximum is `2 * 4 * 2 = 16`. A future member of an
underlying enum does not silently enter `/v1`; accepting it requires an explicit
schema decision and may require `/v2`.

Trading currencies use the existing canonical-instrument rule: exact built-in
strings matching ASCII `[A-Z]{3}`. The duplicate-free grammar already has a
finite space, so no arbitrary configured count limit is added.

Venues reproduce exactly the state retainable by the current
`TradingInstrumentIdentity` plus `CanonicalInstrument` validation boundary:
exact built-in, nonempty, already-trimmed uppercase strings containing no
whitespace. Existing validators are private or normalize input, so the
execution-planning module mirrors the rule locally and permanent parity tests
compare a broad accepted/rejected corpus against canonical-instrument
construction. Sampled parity tests do not claim finite exhaustive proof.
Canonical venue identity currently has no principled finite cardinality bound;
v1 therefore adds no artificial maximum venue count or incompatible venue
grammar.

## Independent structural dimensions

Supported asset classes, trading currencies, and venues are independent support
domains. V1 treats values across those sets as structurally composable. It does
not express asset/venue, currency/venue, asset/currency/venue, product-specific,
or venue-specific order-policy matrices.

Style, TIF, and session support is different: it is declared by exact order
combinations. Individual support domains are derived from those combinations.
The evaluator emits an individual unsupported reason for each absent component.
It emits `unsupported_order_combination` only when style, TIF, and session are
all individually present but their exact triple is absent. Input ordering cannot
change reason ordering and reasons never duplicate.

LIMIT price value is outside capability evaluation. The source specification
must already satisfy its MARKET/LIMIT and currency-correspondence rules. V1 adds
no tick, lot, collar, quantity, conversion, or price-band capability.

## Result and provenance boundary

The result is a self-contained immutable value artifact containing only profile
fingerprint, specification fingerprint, outcome, rejection-reason tuple, schema,
and result fingerprint. Projection contains source fingerprints, not source
objects or nested projections. The result retains no source object, registry,
attestation, weak reference, owner identity, or process-local authority.

Evaluation validates and reconstructs both sources before copying their exact
fingerprints. Later result validation operates solely on exact retained field
types, canonical reason ordering, outcome/reason invariants, schema, and
recomputed fingerprint. Compatible results require exact retained `()` and
project `[]`; incompatible results require at least one reason.

The profile and result are value-semantic artifacts. They detect malformed or
incoherent retained state, including stale fingerprints, but do not attest that
their fields remain the exact values first supplied to their factory. A coherent
low-level rewrite of every semantic field and fingerprint into another valid
canonical value is outside the construction-origin threat boundary. This is why
the v0.66 external origin registry is neither necessary nor appropriate here.
Fingerprints provide deterministic identity and provenance binding, not
cryptographic authenticity or immutable construction-origin proof.

## Errors and authority

Malformed public factory inputs raise `ExecutionPlanningValidationError`.
Malformed retained model state, source corruption encountered during evaluation,
and schema or fingerprint contradictions raise
`ExecutionPlanningCorrespondenceError`. Direct construction raises `TypeError`.
Unexpected exceptions outside those bounded cases are not broadly wrapped.

A compatible result means only that the order fits the profile's declared v1
structural dimensions. It does not promise broker acceptance, execution,
authorization, risk approval, liquidity, fill, or compliance.

## Explicit exclusions

V0.67 adds no broker SDK, credentials, account data, balances, buying power,
live capability discovery, market status, calendar or current-time behavior,
network access, retries, persistence, configuration or environment loading,
broker-native mapping or payload, routing or optimization, submission,
cancellation, replacement, acknowledgement, lifecycle, fills, commissions,
rate limits, authorization, or risk approval.

The next logical boundary is a broker-native order mapping foundation: a pure,
deterministic mapping from a structurally compatible broker-neutral order to an
adapter-owned native representation. Submission and authorization remain later
boundaries. An authorization artifact must eventually bind more than
compatibility: at minimum the specification, compatible result, exact structural
risk decision, and explicit authorization policy/version identity.

## Consequences

Execution planning gains two fingerprint families and exactly eight public
exports. Existing v0.55-v0.66 projections, APIs, fingerprints, and behavioral
boundaries remain unchanged. Capability declarations are useful offline while
remaining deliberately insufficient for live execution.
