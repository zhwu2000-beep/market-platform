# ADR 0022: Explicit Session Participation Choice Foundation

## Status

Accepted for v0.65.0.

## Context

The released execution-planning boundary already provides an instruction, an
explicit order style, an explicit LIMIT price, and an explicit time in force.
Session participation is the last caller-authored method choice needed before a
future broker-neutral order specification can be assembled. Omitting it would
silently delegate regular-versus-extended participation to a broker default.

The choice must remain useful without pretending that the platform already owns
venue calendars, time zones, exact session windows, current-open state, or broker
capabilities.

## Decision

`market_platform.execution_planning` adds exactly:

- `SessionParticipation`
- `SessionParticipationChoice`
- `SESSION_PARTICIPATION_CHOICE_SCHEMA`

The enum inventory and order are exact:

- `REGULAR_ONLY = regular_only`
- `REGULAR_AND_EXTENDED = regular_and_extended`

Absence is never a default. A future order specification without exactly one
session-participation choice is incomplete.

`REGULAR_ONLY` requests eligibility only within the applicable regular trading
session. Exact boundaries, venue time zone, holidays, daylight-saving behavior,
auctions, and broker cutoffs are resolved downstream. It does not prove that a
market is open or that an order will be eligible or execute.

`REGULAR_AND_EXTENDED` requests regular-session participation plus eligible
non-regular continuous-session participation. Downstream capability and mapping
remain authoritative for which pre-market, after-hours, overnight, or other
continuous sessions exist and are supported. The value does not include auctions,
every venue-defined session, future session classes, continuous 24-hour access, or
guaranteed extended-hours routing by implication.

The following values are deliberately absent:

- `EXTENDED_ONLY`, because its scheduling and eligibility semantics need a
  separate contract.
- `ALL_ELIGIBLE_SESSIONS`, because it could silently absorb auctions or future
  session classes.
- `BROKER_DEFAULT` and `UNSPECIFIED`, because they reintroduce hidden behavior.
- `DEFAULT`, `UNKNOWN`, and `NO_ACTION`, because none is a canonical session
  request; no-action terminates upstream.

A boolean extended-hours flag is also rejected because it obscures the canonical
requested category.

## Value and identity contract

`SessionParticipationChoice(session_participation)` is frozen, slotted, timeless,
bounded, deterministic, and directly caller-constructible. Its exact fields are
`session_participation`, derived `schema_version`, and derived `fingerprint`.
The input must have exact runtime type `SessionParticipation`; strings, foreign
enums, booleans, mappings, arbitrary objects, and `None` are invalid.

The schema is `session_participation_choice/v1`. Its fingerprint payload contains
the schema and canonical lowercase enum value exactly once. The projection has
exact keys `schema_version`, `session_participation`, and `fingerprint` and is
JSON-safe.

The value is caller-authored, not factory-derived. It has no guarded token,
constructor-state tuple, identity binding, retained source, or factory. Directly
constructing either valid choice is legitimate and claims no provenance,
cryptographic authenticity, calendar resolution, broker support, routing,
acceptance, or execution.

`to_dict()` validates all retained slots. The enum must retain its exact enum
type. Schema and fingerprint must be exact built-in strings and are type-checked
before equality, so equality-spoofing objects and exact-value string subclasses
cannot reach projection. Missing or malformed retained state raises
`ExecutionPlanningCorrespondenceError`; invalid direct input raises
`ExecutionPlanningValidationError`. Unexpected exceptions outside that narrow
contract are not masked.

## Boundaries

The choice has no calendar, timezone, session date, timestamp, wall clock,
current-open calculation, or exact session boundary. It is not bound to an
instrument, venue, style, price, time in force, instruction, account, or capability
profile. In particular, DAY does not imply `REGULAR_ONLY`, GTC does not imply
`REGULAR_AND_EXTENDED`, and IOC/FOK do not imply that a market is open.

The value is non-executable and is not structural, financial, compliance, human,
or system approval. It is not permission to trade or short, broker approval,
submission authority, a routing instruction, or a cancellation command. Future
capability and mapping own exact calendars and windows, supported non-regular
sessions, auctions, overnight support, product/account restrictions, and
style/TIF/session compatibility.

v0.65.0 does not introduce `BrokerNeutralOrderSpecification`. A future factory is
expected to require all six explicit arguments:

```python
construct_broker_neutral_order_specification(
    instruction: BrokerNeutralExecutionInstruction,
    canonical_instrument: CanonicalInstrument,
    order_style_choice: OrderStyleChoice,
    limit_price_choice: LimitPriceChoice | None,
    time_in_force_choice: TimeInForceChoice,
    session_participation_choice: SessionParticipationChoice,
) -> BrokerNeutralOrderSpecification
```

MARKET will require explicit `None` for the limit price; LIMIT will require exactly
one `LimitPriceChoice`. The future specification will own correspondence among
those inputs. Authorization, capability validation, broker mapping, request
creation, submission, persistence, and lifecycle remain later boundaries.

## Consequences

Session intent is explicit without inventing a calendar model or broker default.
The execution-planning fingerprint inventory grows by exactly one family,
`session_participation_choice/v1`. The next coherent milestone may construct the
broker-neutral specification from the released ingredients.
