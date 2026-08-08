# ADR 0025: Broker-Native Order Mapping Foundation

## Status

Accepted for the v0.68.0 implementation.

## Context

V0.67 proves only structural compatibility between one broker-neutral order
specification and one declared capability profile. The next offline boundary
must let a replaceable adapter translate that order into bounded target-native
semantic data without importing an SDK, locating an instrument mapping,
authorizing the order, or submitting it.

Here, "broker-native" means adapter-native semantic representation. It does not
mean a broker SDK request object, broker acceptance, or executable authority.

## Decision

`market_platform.execution_planning` owns an outbound runtime-checkable
`BrokerNativeOrderMapper` protocol, factory-owned
`BrokerNativeOrderRepresentation`, evaluator-owned `BrokerNativeOrderMapping`,
and `map_broker_native_order`. Their schemas are
`broker_native_order_representation/v1` and `broker_native_order_mapping/v1`.

The caller supplies exact validated specification, capability profile,
compatible structural result, and one `InstrumentMapping`. No persistent
mapping-request artifact and no generic dictionary payload are introduced.

## Mapper provenance and invocation

The protocol supplies `execution_target_id`, `mapper_id`, `mapper_version`,
`mapping_policy_fingerprint`, `instrument_namespace`, and one keyword-only
`map_order` operation. `mapper_version` is explicit protocol metadata: visible
ASCII of length 1-64. It is not derived from module, class, function, object ID,
file path, or installed-package location.

Runtime protocol checking establishes structural member availability only. It
does not prove metadata types, stability, purity, mapper correctness, or token
meaning. After all domain preconditions pass, evaluation captures each metadata
property exactly once in declared order, validates the immutable local values,
binds `map_order` once, and invokes it exactly once. Metadata is never reread
after invocation. Exceptions raised by property access or mapper execution
propagate unchanged; successfully returned malformed values are rejected at the
bounded mapping boundary.

The result binds mapper ID, mapper version, and mapping-policy fingerprint.
This provenance identifies declared translation rules but does not authenticate
mapper code or prove correct translation.

## Opaque tokens and independently verifiable correspondence

Side, order-type, time-in-force, and session-participation tokens are exact
visible-ASCII strings of length 1-128. The platform validates only their bounded
shape. It does not assume BUY maps to `BUY`, LIMIT to `LMT`, DAY to `DAY`, or any
particular session token. Opaque token interpretation is a mapper-conformance
responsibility; a malicious or defective mapper may return shape-valid but
semantically incorrect tokens.

The platform independently verifies what it can reconstruct: all source
fingerprint bindings; target and namespace correspondence; exact external
instrument identity; quantity; MARKET price absence; LIMIT numeric price and
currency; and mapping temporal applicability. A successful result is not proof
of broker acceptance or complete semantic correctness of an external mapper.

## Decimal semantics

Quantity reuses the execution-instruction canonical quantity helper and its
delta-result digit, fractional-digit, and text bounds. Limit price and currency
reuse `LimitPriceChoice` canonical rules. Exact `Decimal` input is required;
scale is non-semantic. `Decimal("1")`, `Decimal("1.0")`, and `Decimal("1.00")`
retain as `Decimal("1")`, project as `"1"`, and fingerprint identically when all
other fields match. Zero and negative zero quantities, non-finite values,
negative quantities, floats, integers, and proxies fail. Retained Decimal state
must already be canonical, even after top-level refingerprinting.

No rounding, lot, fractional-share, tick, collar, band, or currency-conversion
behavior is added.

## Supplied instrument relation

`InstrumentMapping` remains the immutable external-to-canonical relation from
the instrument domain. V0.68 uses exactly one caller-supplied relation in the
canonical-to-external direction. It fully validates that relation, proves its
canonical side corresponds to the specification, and applies the existing
half-open interval at the instruction's `plan_as_of`: `valid_from <= plan_as_of`
and, when present, `plan_as_of < expires_at`.

The mapper namespace must equal the mapping external namespace. Evaluation
independently reconstructs the `ExternalInstrumentIdentity` and passes that
fresh semantic value to the mapper. It performs no reverse lookup, repository
search, ambiguity resolution, preferred-route selection, or live symbol or
contract lookup.

## Owned values and threat boundary

`BrokerNativeOrderMapping.native_order` is owned nested semantic state, not
retained upstream evidence. Parent validation independently reconstructs the
complete child and includes its full projection in the parent fingerprint. The
mapping retains no specification, capability profile, compatibility result,
instrument mapping, or mapper instance.

Parent `instrument_namespace` must equal the nested external identity namespace.
That internal invariant is checked before the parent fingerprint and remains
enforced after coherent refingerprinting of either side. No registry,
attestation, weak reference, or process-local owner identity is needed.

Representation and mapping are self-contained canonical value artifacts. They
validate current exact types, Decimal canonicality, nested state, schemas,
internal invariants, and fingerprints. Fingerprints bind current semantic
values, not original factory provenance, mapper authenticity, or mapper code
identity. A coherent rewrite into another completely valid artifact with every
invariant satisfied and fingerprint recomputed remains outside construction-
origin authenticity.

## Errors and sequencing

Malformed public inputs, ineligible preconditions, cross-source contradictions,
target or namespace mismatches, inactive relations, and malformed mapper output
raise `ExecutionPlanningValidationError`. Corrupted retained source or result
state and internal parent/child contradictions raise
`ExecutionPlanningCorrespondenceError`. Direct construction raises `TypeError`.
Normal structural incompatibility is rejected before mapper metadata access or
mapper invocation.

Pure mapping precedes authorization because authorization may bind the exact
mapped artifact and its translation provenance. Mapping consumes no risk
decision and grants no authority. A future authorization boundary should bind
the specification, compatible capability result, structural-risk evidence,
mapped order, and explicit authorization policy identity before submission.

## Exclusions

V0.68 adds no concrete adapter, SDK object or call, credential, API key, account
input, balance, buying power, live discovery or broker state, market-open or
calendar decision, current-time decision, authorization, risk approval,
submission, cancellation, replacement, acknowledgement, broker order ID,
lifecycle, fill, execution, commission, retry, network, rate limit, persistence,
configuration or environment loading, secret logging, routing or venue
optimization, mapping search, reverse resolver, live lookup, quantity rounding,
lot rule, fractional-share rule, tick mapping, collar, price band, or native-
token semantic verification.

## Consequences

Execution planning gains exactly seven exports and two fingerprint families.
The boundary is useful to future concrete adapters while remaining deterministic,
offline, non-authorizing, and non-submitting.
