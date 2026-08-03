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
