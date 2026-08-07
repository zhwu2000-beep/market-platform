# Roadmap

## Releases
- v0.2.0: Provider foundation
- v0.3.0: Unified Provider Architecture

## v0.3.0 Planned Work
- `ProviderRegistry`
- `ProviderNotFoundError`
- default `get_provider()`
- Polygon Provider improvements
- real-time latest trade support
- future Twelve Data provider
- documentation and ADRs

## v0.3.0 Completed Work
- Polygon intraday prices

## v0.4.0 Completed Work
- TwelveDataProvider skeleton
- Twelve Data daily prices
- default registry registration
- provider switching through `get_provider()`

## v0.5.0 Completed Work
- provider comparison ADR
- daily price DataFrame comparison
- provider-level daily price comparison
- no fallback yet

## Trading Domain Sequence

- v0.55.0: Trading Signal and Order Intent Foundation
- v0.56.0: Trading Signal Application Boundary
- v0.57.0: Instrument Identity and Mapping
- v0.58.0: Trading State Snapshot Foundation
- v0.59.0: Structural Risk Decision Foundation
- v0.60.0: Position Target Translation Foundation
- v0.61.0: Broker-Neutral Execution Instruction Foundation
- future: Order Specification, explicit authorization/application, broker request,
  submission, and live reconciliation boundaries

V0.60 deliberately stops at exact target/current/delta translation. Broker order
style, price, time in force, financial and short authorization, approval,
submission, persistence, and lifecycle reconciliation require later milestones.

V0.61 converts only actionable deltas into one non-executable side plus positive

- v0.62.0: Explicit Order Style Choice Foundation
- future: Price/TIF/Session Constraint Choice
- future: Broker-Neutral Order Specification
- future: Authorization/Application, broker capability and mapping, broker
  request, submission, and lifecycle reconciliation

V0.62 requires an explicit canonical MARKET or LIMIT choice. Absence never means
market. The choice is reusable and caller-authored; it contains no instruction,
price, TIF, session, time, authorization, capability, broker, submission, or
lifecycle semantics.

- v0.63.0: Explicit Limit Price Choice Foundation
- future: Explicit TIF and Session Choices
- future: Broker-Neutral Order Specification

V0.63 adds a timeless caller-authored positive limit price with an explicit
three-letter trading currency. It carries no style, instrument, quote, tick-size,
authorization, capability, broker, submission, or lifecycle semantics. MARKET
consumes no limit-price choice; future LIMIT specification construction must
require one and validate instrument-currency correspondence separately.

- v0.64.0: Explicit Time-in-Force Choice Foundation
- future: Explicit Session Choice, if required
- future: Broker-Neutral Order Specification
- future: Authorization/Application, broker capability and mapping, broker
  request, submission, and lifecycle reconciliation

V0.64 adds one timeless caller-authored DAY, GTC, IOC, or FOK choice. Absence
never means DAY. These labels express requested order-duration or immediate-fill
behavior without promising support or fulfillment. GTD remains unavailable
until a separate expiry contract defines its source, timestamp, comparison
anchor, and broker/calendar boundaries. V0.64 adds no session, compatibility,
authorization, capability, specification, submission, or lifecycle semantics.

- v0.65.0: Explicit Session Participation Choice Foundation
- future: Broker-Neutral Order Specification
- future: Authorization/Application, broker capability and mapping, broker
  request, submission, and lifecycle reconciliation

V0.65 adds one timeless caller-authored `REGULAR_ONLY` or
`REGULAR_AND_EXTENDED` choice. Absence never means regular-only or broker
default. Exact session windows, calendars, timezone rules, current-open state,
auctions, and supported non-regular sessions remain downstream. The choice has
no instrument, venue, style, price, TIF, instruction, account, compatibility,
capability, authorization, specification, broker, submission, or lifecycle
semantics.

- v0.66.0: Broker-Neutral Order Specification Foundation
- future: Authorization/Application Boundary
- future: Capability and Broker Mapping
- future: Broker Request/Submission and Lifecycle/Reconciliation

V0.66 factory-binds the exact instruction, corresponding canonical descriptor,
style, explicit conditional price, TIF, and session choice. MARKET requires an
explicit null price; LIMIT requires one matching-currency price. The complete
specification remains unauthorized, capability-unvalidated, broker-unmapped,
unsubmitted, and non-live.
- v0.67.0: Broker Execution Capability Foundation
- future: Broker-Native Order Mapping Foundation
- future: Authorization, Submission, and Lifecycle/Reconciliation

V0.67 declares one opaque execution target's independent asset, currency, and
venue support plus exact style/TIF/session combinations. It evaluates a complete
v0.66 specification offline and returns deterministic structural compatibility
with bounded machine-readable reasons. Compatibility is not broker acceptance,
authorization, risk approval, mapping, routing, submission, or executability.
The result retains only source fingerprints and canonical value state; it has no
source registry, attestation, weak-reference lifecycle, or process-local owner
identity.
