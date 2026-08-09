# ADR 0026: Broker-Neutral Execution Authorization Foundation

## Status

Accepted for v0.69.0 implementation.

## Context

v0.68.0 produces a deterministic broker-native mapping, but a mapping is not
permission to submit. The platform needs a separate, auditable boundary that
combines exact approved risk evidence, the downstream planning chain, structural
compatibility, and one exact native mapping into a submission-bound permission.

Authorization remains broker-neutral because its rules are target-independent:
it binds the native mapping and execution target without interpreting opaque
adapter-native token meanings.

## Decision

The `market_platform.execution_planning` domain owns a success-only
`BrokerNeutralExecutionAuthorization`. A future submission boundary must
require the exact authorization corresponding to the exact native mapping.
There is no denied authorization result in v1.

The authorization is created only by
`authorize_broker_neutral_execution`. The evaluator consumes exact
`RiskEvaluationContext`, `RiskDecision`, `PositionTargetTranslation`,
`BrokerNeutralOrderSpecification`,
`BrokerExecutionStructuralCompatibilityResult`,
`BrokerNativeOrderMapping`,
`BrokerNeutralExecutionAuthorizationPolicyIdentity`, and an explicit
`authorization_as_of`.

## Risk and error semantics

The evaluator calls the existing deterministic `evaluate_structural_risk`
exactly once to replay and validate the supplied risk evidence. It does not
duplicate the risk engine or introduce authorization-specific risk rules.

A rejected or indeterminate risk decision cannot coherently produce the
downstream translation, specification, and mapping chain. Supplying that
combination is therefore a contradictory public input bundle and raises
`ExecutionPlanningValidationError`, not
`ExecutionPlanningUnavailableError`. v0.69 does not use
`ExecutionPlanningUnavailableError`.

Wrong runtime types and individually valid but mutually mismatched public
inputs raise `ExecutionPlanningValidationError`. Corrupted retained source
state or corrupted retained authorization state raises
`ExecutionPlanningCorrespondenceError`. Direct construction of factory-owned
models raises `TypeError`.

## Policy identity

`BrokerNeutralExecutionAuthorizationPolicyIdentity` is an immutable identity
for the platform-owned, schema-frozen authorization rule set. It is provenance,
not a behavioral policy implementation and not proof of deployed-code
authenticity. It has no protocol, callback, configuration model, or
`configuration_fingerprint`.

The authorization stores policy ID, version, and policy-identity fingerprint.
Retained-state validation reconstructs the identity from ID and version and
requires its canonical fingerprint to equal the stored identity fingerprint.
This invariant survives top-level authorization refingerprinting without a
registry or origin authority.

## Evidence and time

The common `evidence_as_of` is derived from exact correspondence among risk
context, risk decision, position translation, and nested execution instruction.
The caller supplies `authorization_as_of`; it is canonical UTC and must be
greater than or equal to `evidence_as_of`.

The evaluator never reads the system clock. v1 defines no freshness threshold,
expiry, or validity interval. Those concerns belong to a later submission or
reauthorization boundary.

## Stage-trust boundary

v0.69 independently revalidates every directly supplied artifact, replays the
structural-risk decision once, and checks risk approval, account identity,
evidence time, translation/specification correspondence, compatible structural
result, mapping correspondence, execution target, authorization time, and
policy identity.

The validated compatibility result and native mapping transitively bind the
capability profile and caller-supplied InstrumentMapping. The specification
contains the execution instruction; the risk context contains structural risk
policy and account evidence. These objects are not redundant direct inputs.
OrderIntent is accepted through the validated context/translation chain.

Mapper implementation authenticity, opaque token semantic correctness,
construction-origin authenticity, and live broker/account/market state remain
outside platform proof. Authorization binds opaque native tokens only through
the native-mapping fingerprint and never interprets strings such as BUY, SELL,
MKT, LMT, DAY, or GTC.

## Self-contained result

The authorization retains only canonical fingerprints and bounded derived
semantic values. It retains no upstream source object, mapper, policy object,
registry, attestation, weak reference, or process-local identity.

Retained-state validation proves current canonical field types, schemas,
fingerprint grammar, UTC time canonicality and ordering, policy identity
consistency, execution-target and account-fingerprint grammar, and its own
fingerprint. A coherent low-level rewrite into another fully valid canonical
authorization with every invariant and fingerprint updated remains outside
construction-origin authenticity.

## Independent value

v0.69 creates the first explicit submission-bound permission token. v0.68
mapping alone cannot proceed to a conforming future submission boundary.
Authorization freezes one exact evidence bundle under one declared platform
authorization rule-set identity, so future submission can bind the
authorization fingerprint rather than infer permission from upstream artifacts.

## Exclusions

v0.69 adds no authorization outcome/reason model, configurable rule engine,
policy protocol, configuration fingerprint, broker SDK, network access,
credentials, account-state lookup, balances, buying power, live capability
discovery, market-open or calendar check, system-clock read, freshness or
expiry rule, submission request, submission, cancellation, replacement,
acknowledgement, broker order ID, lifecycle, fill, execution, commission,
retry, rate limit, persistence, configuration/environment loading, live symbol
lookup, routing optimization, token interpretation, or post-submission
supervision.

## Consequences

The design adds an explicit permission boundary without introducing live
effects. Future submission work must consume both the exact authorization and
the exact native mapping, preserve their correspondence, and separately define
submission request and adapter behavior.
