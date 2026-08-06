# ADR 0023: Broker-Neutral Order Specification Foundation

## Status

Accepted for the v0.66.0 implementation.

## Context

V0.61-v0.65 provide one actionable broker-neutral instruction, an exact
canonical instrument descriptor, and explicit style, conditional LIMIT price,
time-in-force, and session-participation choices. Those are now sufficient to
assemble the first complete broker-neutral order request. Authorization and
broker capability cannot sensibly precede a stable complete request identity.

## Decision

`market_platform.execution_planning` adds exactly
`BrokerNeutralOrderSpecification`,
`construct_broker_neutral_order_specification()`, and
`BROKER_NEUTRAL_ORDER_SPECIFICATION_SCHEMA`. The schema and sole new
fingerprint family are `broker_neutral_order_specification/v1`.

The keyword-only factory requires all six arguments:

```python
construct_broker_neutral_order_specification(
    instruction=instruction,
    canonical_instrument=canonical_instrument,
    order_style_choice=style,
    limit_price_choice=price_or_none,
    time_in_force_choice=tif,
    session_participation_choice=session,
)
```

There are no defaults. The price argument itself is required: MARKET requires
exact `None`, while LIMIT requires one exact `LimitPriceChoice`. A supplied
MARKET price is rejected rather than ignored. LIMIT price currency must equal
the canonical instrument trading currency after both sources are validated.
No price is derived, rounded, converted, clamped, or tick-aligned.

## Model, ownership, and projection

The frozen, slotted, `init=False` specification is factory-owned. Its eight
public fields are the exact instruction, canonical instrument, style choice,
conditional price choice, TIF choice, session choice, derived schema, and
derived fingerprint. It retains no flattened duplicate fields.

Its exact projection keys are `schema_version`, `instruction`,
`canonical_instrument`, `order_style_choice`, `limit_price_choice`,
`time_in_force_choice`, `session_participation_choice`, and `fingerprint`.
Every non-null nested value is its complete validated JSON-safe source
projection. MARKET projects an explicit JSON null for price.

The fingerprint payload contains exactly schema and the six source
fingerprints. MARKET contributes exact null as its price fingerprint. The
separately supplied canonical descriptor fingerprint is included even though
the instruction references it, because the specification binds that exact
descriptor source.

## Factory attestation and retained-state boundary

Private construction evidence consists of one factory-created per-instance
attestation, a primitive constructor-state tuple, and an exact bounded identity
binding. Frozen attestation attributes alone are not authoritative under the
retained-state threat model because low-level assignment can replace them. The
authoritative construction origin is therefore an immutable tuple-backed
record held in a private module-closure identity registry. It anchors the exact
owner, attestation, original state tuple, original binding tuple, and all six
original source references, including exact `None` for MARKET.

The registry keys exact specification identity and retains the owner only by a
weak reference. Lookup verifies that the weak reference resolves to the exact
current specification. Cleanup removes an entry only when its callback weak
reference is the exact reference stored for that entry, so a stale callback
cannot remove a newer live record. Registration is one-time and never rebuilt
from retained state. The attestation remains an identity handle, not the sole
authority: replaced, reconstructed, mutated, or cross-instance attestations
cannot redefine the registered origin.

Serialization retrieves every required slot through the narrow retained-slot
helper, obtains the external origin first, then checks exact owner, attestation,
state, binding, and source identities. It validates every constructor-state
element's exact built-in type before any equality, validates exact source
runtime types, revalidates every nested source, rechecks cross-source rules,
and recomputes state and fingerprint before projection.

This process-local registry provides repository-model correspondence hardening,
not cryptographic authenticity or protection from modification of private
module closures, interpreter internals, process memory, or the Python runtime.
Registry state is neither serialized nor fingerprinted. No public deserializer
exists, so a deserialized object cannot acquire a valid origin; future
persistence requires a separate trusted reconstruction boundary.
Retained schema and fingerprint require exact built-in strings before equality.
Missing or malformed retained specification state raises
`ExecutionPlanningCorrespondenceError`; invalid direct factory relationships
raise `ExecutionPlanningValidationError`. Unexpected exceptions outside these
boundaries are not broadly masked.

## Canonical instrument correspondence

`CanonicalInstrument.to_dict()` alone is not a retained-state validator. The
specification therefore independently retrieves and exact-type checks its ID,
released `TradingInstrumentIdentity`, asset class, currency, schema, and
fingerprint. It reconstructs the ID, complete trading identity, and descriptor
through their released constructors and requires complete projection and
fingerprint correspondence.

The reconstructed canonical ID and descriptor fingerprint must exactly equal
the instruction's retained instrument evidence. This rejects stale IDs,
symbols, venues, asset classes, currencies, nested schemas/fingerprints,
equality-spoofing values, string subclasses, and deleted state. No
`InstrumentResolution` is needed because the instruction already transitively
binds the resolution-derived canonical evidence.

## Method and temporal boundaries

One exact TIF and one exact session choice are mandatory. Construction declares
no MARKET/LIMIT, DAY/GTC/IOC/FOK, or regular/extended compatibility matrix.
Those combinations remain structurally expressible and may later be rejected
by broker capability rules. DAY does not imply regular-only, TIF does not select
sessions, and session participation does not determine duration.

No timestamp is added. The instruction's `plan_as_of` remains transitively
bound, and identical source inputs produce identical specification identity.
No-action translation still yields no instruction and therefore no
specification.

## Authority and downstream boundaries

The specification is complete order intent, not structural, financial,
compliance, short-sale, human, system, or submission authorization. It proves
neither buying power nor permission to trade. A future authorization artifact
is expected to bind the exact specification fingerprint.

Capability validation remains responsible for supported styles, TIFs, sessions,
combinations, quantities, lots, ticks, price collars, GTC limits, products,
venues, accounts, and extended-hours restrictions. A coherent specification may
be unsupported.

Broker mapping and submission remain future. The specification contains no
broker symbol/account, client or request ID, broker codes or flags, API payload,
endpoint, submission timestamp, acknowledgement, status, routing, fill,
cancellation, persistence, or reconciliation state.

## Consequences

Execution planning now exposes one complete deterministic broker-neutral order
request and exactly seven fingerprint families. The next boundary can address
authorization/application ownership without weakening the separation between
complete intent, broker capability, and execution.
