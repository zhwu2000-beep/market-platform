# Architecture

## Data Layer
- `HTTPClient` is the shared network boundary for providers.
- `DataProvider` defines the common provider interface.
- `ProviderRegistry` resolves provider factories by normalized name.
- Concrete providers implement provider-specific endpoints and normalization.
- All provider methods return normalized `pandas.DataFrame` output.
- Provider configuration is validated lazily when a request is made, not at construction time.

The preferred flow is `HTTPClient` -> `DataProvider` -> `ProviderRegistry` ->
concrete providers such as `PolygonProvider`.

## Boundaries
- Providers do not call `httpx` directly.
- Providers do not expose vendor-specific response formats to the rest of the app.
- Downstream code depends on the standardized DataFrame schema and project exceptions.

## Canonical Historical Inputs
- `HistoricalPriceSeries` in `market_platform.data.historical` owns replay-grade
  validation, UTC normalization, stable ordering, identity, and defensive isolation
  for one historical OHLCV series.
- `HistoricalPricePrefix` represents a nonempty inclusive position in that series.
  Immutable row iteration is the analytical boundary; `to_dataframe()` is an
  explicit copy-producing compatibility path.
- `HistoricalPricePrefix.as_of` is the final included historical-data timestamp,
  while a `MarketObservation` `as_of` is its evaluation time. The temporal
  invariant is `HistoricalPricePrefix.as_of <= MarketObservation` evaluation
  `as_of`; exact equality is not required.
- Historical replay is an application workflow over canonical positions. It does
  not own historical-price validation or observation construction.
- Historical observation construction accepts either the existing raw DataFrame
  API or the public validated-prefix API. Both share identity, price facts,
  provenance, fingerprinting, and final model construction.
- See `docs/adr/0004-canonical-historical-input.md`.

## Observation Fingerprint Precomputation
- Historical observation fingerprint semantics remain the legacy compact sorted
  JSON contract. Provider and every ordered prefix OHLCV row participate; signal
  and structure snapshots do not. Row numerics retain `repr(float(value))`, so
  observation identity continues to distinguish `0.0` from `-0.0`.
- `HistoricalObservationFingerprintPrecompute` is a short-lived immutable
  observation-domain value bound to one exact `HistoricalPriceSeries`, interval,
  provider, and ordered set of evaluation positions. It is not serialized or
  included in any identity.
- Preparation projects and JSON-encodes required rows once into one transient
  linear byte stream. Each evaluation digest hashes the exact legacy header, the
  applicable byte-stream prefix, and the exact legacy suffix; Replay then performs
  one validated lookup per step.
- Standalone raw and validated-prefix observation construction retain the shared
  fallback. The optimized and fallback paths use one canonical byte-generation
  source of truth and produce identical observations.
- Row projection and encoding are linear through the maximum evaluation position.
  Total exact legacy SHA-256 input remains quadratic across full-prefix Replay
  because changing `as_of` precedes `rows` in the canonical stream.
- See `docs/adr/0009-observation-fingerprint-precomputation.md`.

## Replay Specification and Windows
- `HistoricalReplaySpecification` is the immutable application request for one
  symbol and interval with explicit UTC `context_start`, `evaluation_start`, and
  `evaluation_end` values. It enforces
  `context_start <= evaluation_start <= evaluation_end`.
- `HistoricalReplayService.run_with_specification()` retains analytical data only
  inside `[context_start, evaluation_end]`, precomputes signals and default price
  structure across that complete retained context, and creates steps only inside
  the inclusive evaluation window.
- Requested boundaries do not imply exact bar coverage. A context window may have
  no returned pre-evaluation bars; execution requires only eligible evaluation
  rows.
- Legacy `HistoricalReplayService.run()` continues to treat its complete supplied
  DataFrame as context and optional `start`/`end` as inclusive evaluation bounds.
- The CLI keeps `--start`/`--end` as evaluation dates and adds optional
  `--context-start`, defaulting to `--start`. `--max-bars` counts evaluation rows,
  not retained context rows.
- Acquisition policy and provider selection remain interface concerns. Actual
  dataset coverage, run manifests, persistence, automatic warm-up, and exchange
  calendars are not part of this boundary.
- See `docs/adr/0005-replay-specification-context-window.md`.

## Replay Run Identity and Provenance
- `HistoricalReplaySpecification.fingerprint` identifies normalized requested
  instrument and temporal intent without changing its existing serialization.
- `HistoricalPriceSeries.content_fingerprint` identifies retained canonical
  symbol/timestamp/OHLCV contents. Provider and interval remain separate: provider
  is an actual provenance fact and interval belongs to Replay intent.
- `HistoricalReplayService.run_execution()` returns `HistoricalReplayExecution`,
  which wraps the unchanged result with immutable `HistoricalReplayRunProvenance`
  and a deterministic run fingerprint.
- Provenance records requested specification, actual retained context and evaluated
  bounds/counts, actual provider, signal/structure derivations, state model, ordered
  strategies, and caller-supplied software revision.
- The run fingerprint covers canonical execution inputs and resolved facts only.
  It excludes Replay outputs, timing, rendering, cache paths, and random values.
- Custom structure services require explicit derivation identity only through the
  provenance-producing API; legacy replay remains compatible.
- Provenance is an in-memory audit boundary, not a manifest, persisted artifact, or
  guarantee that provider data can later be recovered.
- See `docs/adr/0006-replay-run-identity-provenance.md`.

## Versioned Historical Replay Artifacts
- `HistoricalReplayArtifact` is the immutable durable envelope for one
  `HistoricalReplayExecution`. It stores the complete typed Replay result once,
  execution provenance, the existing run fingerprint, a production result
  fingerprint, and a semantic integrity checksum.
- The artifact codec is separate from `HistoricalReplayResult.to_dict()`, whose
  presentation and CLI contract remains unchanged. Strict field-directed decoding
  reconstructs public immutable Replay, state, and strategy models.
- Run, result, dataset, and integrity identities remain distinct. The result
  fingerprint covers typed output content; the integrity checksum covers the
  complete semantic envelope except its own value.
- V1 artifacts are result-only: provider and dataset content identity remain in
  provenance, but canonical OHLCV rows are not stored and cannot be recovered.
- Local persistence writes deterministic UTF-8 JSON through an fsynced temporary
  file and atomic replacement. Loading always verifies schemas, checksum,
  fingerprints, and execution consistency.
- Checksums detect corruption and inconsistent edits, not authenticity. V1 is
  intended for locally generated, trusted-size files and provides no signatures or
  denial-of-service limits.
- Artifact CLI commands, repositories, dataset storage, and migrations are
  deferred. See `docs/adr/0007-versioned-historical-replay-artifact.md`.

## Historical Replay Experiments and Structural Comparison
- `HistoricalReplayExperimentSpecification` owns one verified baseline Artifact,
  one or more ordered verified candidates, caller-supplied comparison software
  revision, and a deterministic experiment fingerprint.
- V1 compatibility requires exact symbol, interval, retained dataset content
  fingerprint, ordered evaluation timestamps, and ordered per-step observation
  fingerprints. Incompatible valid Artifacts return ordered reason codes and no
  aligned detail.
- Compatible state comparison is field-directed across regimes, quality, and
  missing inputs, with separate provenance and evaluation-evidence indicators.
  Strategies align by strategy ID plus occurrence index so reordered and duplicate
  IDs remain deterministic.
- Pairwise comparison retains changed steps only and complete aggregate counts.
  Results describe structural output differences without attributing causality or
  representing returns, P&L, portfolios, orders, fills, or execution quality.
- Experiment comparison accepts loaded Artifacts and performs no Replay execution,
  filesystem I/O, persistence, CLI behavior, or batch orchestration. See
  `docs/adr/0008-historical-replay-experiment-comparison.md`.

## Historical Replay Research Workflows
- The existing async `ResearchWorkflow` remains the provider-facing market
  interpretation boundary. `HistoricalReplayResearchWorkflowService` is a
  separate synchronous domain composition API over already supplied canonical
  historical data.
- A workflow specification owns one `HistoricalPriceSeries`, one baseline member,
  zero or more ordered position-sensitive candidate members, and separate
  caller-supplied Replay, comparison, and workflow software revisions.
- Member identities snapshot Replay intent, a re-derivable state-model identity,
  structure derivation, and ordered `StrategyInstance` identities. Executable
  identities are re-derived immediately before and after every Replay; stale or
  execution-mutated configuration is an invariant failure. Produced execution provenance is checked before
  Artifact construction. Ordinary Replay retains its broader executable APIs.
- Baseline failure skips all dependent work. After baseline success, candidates
  continue independently. Successful candidate Artifacts are retained, but any
  failed candidate prevents Experiment construction; the requested set is never
  reduced.
- Terminal status and the fixed Replay/Artifact/Experiment step projection are
  derived. Only the dedicated `StrategyRunnerError` execution boundary is
  captured; validation, invariant, Artifact, Experiment, and control-flow errors
  propagate.
- The result owns complete in-memory Replay Artifacts and an optional existing
  Experiment. It performs no provider access, persistence, CLI behavior, async
  work, retries, parallelism, scheduling, generic DAG, or Agent work. See
  `docs/adr/0010-historical-replay-research-workflow.md`.

## Historical Research Application Boundary
- `market_platform.application` is an additive transport-neutral layer over the
  v0.53 workflow. Domain modules do not import it.
- Its strict versioned request carries inline normalized OHLCV rows, exact Replay
  member intent, passive strategy/state configuration, structure identities, and
  three explicit software revisions. The existing `HistoricalPriceSeries`
  constructor and v0.53 models remain authoritative after decoding.
- Immutable injected resolvers use allow-listed factories and return fresh
  executable instances. The service independently verifies runtime IDs, versions,
  and configuration fingerprints before constructing domain members.
- Application-request identity records normalized submitted intent; workflow
  specification and result fingerprints retain their separate resolved-domain
  meanings.
- The typed response owns the complete in-memory workflow result while its
  dictionary projection contains bounded status and identity summaries only.
- This trusted local boundary adds no HTTP, CLI, persistence, Agent, TradingView,
  broker, or provider integration. A future TradingView Signal Gateway must use a
  separate live-event schema, authenticate ingress, acknowledge quickly, enforce
  idempotency/expiry/replay protection, and remain separated from Order Intent,
  Risk, and Broker Execution layers. See
  `docs/adr/0011-research-application-boundary.md`.

## Trading Signal and Order Intent Domain
- `market_platform.trading` is a separate domain from analytical
  `market_platform.signals`. It defines immutable venue-qualified instruments,
  signal producers, time-bounded exact target-position signals, and pre-risk
  Order Intents.
- A producer-owned source event ID plus source identity derives an idempotency
  key. The complete canonical event derives a separate signal fingerprint, so
  repeat delivery and conflicting content can be distinguished without storage.
- Targets use long, flat, or short direction with exact canonical `Decimal`
  units. Signals require a finite UTC validity window and are evaluated only at
  an explicit caller-supplied time under `[valid_from, expires_at)` semantics.
- The fixed exact-target policy copies one active signal target into a
  factory-only Order Intent. The decision time participates in identity and the
  intent expires with its signal.
- Order Intent has no lifecycle status and is not risk authorization, a
  transaction, or a broker order. Accounts, positions, risk decisions, broker
  instructions, ingress receipts, persistence, TradingView/HTTP adapters, and
  execution remain future layers. See
  `docs/adr/0012-trading-signal-and-order-intent.md`.

## Trading Signal Application Boundary
- `market_platform.application` exposes separate synchronous operations for
  constructing one canonical TradingSignal and for reconstructing one signal
  and creating one pre-risk OrderIntent at an explicit decision time.
- Strict exact-key dictionaries normalize fixed-point Decimal text, aware
  RFC-3339 timestamps, visible-ASCII identities, canonical instruments, and
  fixed resource limits before deriving operation-specific request fingerprints.
- Factory-only responses retain complete domain objects while emitting bounded
  JSON-safe projections. Complete correspondence validation prevents a request
  fingerprint from being paired with an unrelated signal or intent.
- Source identity remains trusted-local rather than authenticated. Idempotency
  keys expose logical event identity without persistence or duplicate
  suppression. TradingView/HTTP ingress, mapping, authentication, account and
  market state, risk, persistence, and broker execution remain future layers.
  See `docs/adr/0013-trading-signal-application-boundary.md`.

## Instrument Identity and Mapping Domain
- `market_platform.instruments` adds stable opaque canonical instrument IDs
  without changing the released symbol/venue `TradingInstrumentIdentity`.
  Canonical descriptors are equity/ETF-only, retain that exact released
  identity, and carry one explicit trading currency.
- Exact external namespace identities map through immutable source-attributed
  records with caller-supplied canonical UTC validity. Resolution is pure,
  explicit-time, input-order-neutral, and fail-closed for duplicates, missing
  or inactive records, ambiguity, and conflicts.
- The boundary is additive:
  external identity -> temporal mapping -> canonical instrument -> released
  trading identity -> existing v0.56 application request. Mapping provenance
  remains separate from released signal and application fingerprints.
- No registry, persistence, provider/broker lookup, TradingView/HTTP adapter,
  account or snapshot state, risk, execution, CLI, or Agent behavior is added.
  See
  `docs/adr/0014-instrument-identity-and-mapping.md`.

## Trading State Snapshot Domain
- `market_platform.trading_state` adds four independent immutable evidence
  families for account cash, positions, open-order exposure, and market quotes.
  Account-owned snapshots retain a trusted-orchestration account identity with
  exact `paper` or `live` environment; every snapshot retains separate source
  provenance and one caller-supplied canonical UTC `as_of`.
- Passive nested records use stable `CanonicalInstrumentId` values and exact
  bounded fixed-point `Decimal` strings. Decimal size is projected before
  formatting. Collection inputs are exact built-in lists or tuples, counts are
  bounded, duplicates fail closed, and semantic sorting makes fingerprints
  independent of caller insertion order.
- Cash may be negative or zero. Position and open-order quantities are signed
  and nonzero. Quotes contain at least one strictly positive bid, ask, or last;
  bid cannot exceed ask. Empty snapshots are valid source-reported facts but do
  not claim risk sufficiency.
- Freshness and temporal skew are pure evaluations over explicit times and
  caller-supplied nonnegative limits. Separate snapshot arrows do not imply
  atomic capture:

  broker/provider adapters
      +-> AccountCashSnapshot -----------+
      +-> PositionCollectionSnapshot ----+
      +-> OpenOrderExposureSnapshot -----+
      +-> MarketQuoteCollectionSnapshot -+
                                        +-> explicit freshness/skew evaluation
                                        +-> future RiskDecision boundary

  These are parallel inputs, not a capture sequence.

- V0.58 adds no bundle or atomicity flag, cross-snapshot risk correspondence,
  application service, persistence, adapter implementation, provider/broker
  access, TradingView/HTTP behavior, authentication, risk decision, execution,
  CLI, or Agent behavior. See
  `docs/adr/0015-trading-state-snapshot-foundation.md`.


## Structural Risk Decision Domain
- `market_platform.risk` composes released Order Intent, instrument mapping, and
  trading-state evidence into one deterministic structural decision. It owns no
  application, persistence, adapter, provider, broker, execution, CLI, or Agent
  boundary.
- The four snapshots are parallel evidence inputs. Account cash, positions, and
  open orders carry separately audited account fingerprints; quotes remain
  account-independent. No edge implies atomic capture:

  OrderIntent ------------------------------+
  InstrumentResolution --------------------+
  StructuralRiskPolicy --------------------+
  AccountCashSnapshot ---------------------+
  PositionCollectionSnapshot --------------+-> RiskEvaluationContext
  OpenOrderExposureSnapshot ---------------+       -> stage-gated evaluator
  MarketQuoteCollectionSnapshot -----------+       -> RiskDecision

- Evaluation reconstructs all released inputs, then applies intent timing;
  resolution, mapping, and instrument correspondence; account correspondence;
  four-snapshot freshness and skew; coverage; and target quote sufficiency.
  Intent findings reject and stop. Resolution/instrument or account findings are
  indeterminate and stop. Later stages collect all applicable bounded findings.
- The only outcomes are `approved`, `rejected`, and `indeterminate`. Findings use
  21 fixed reason codes, fixed reason/subject ordering, at most four evidence
  fingerprints each, and a maximum of 32 per decision.
- V0.59 adds exactly `structural_risk_policy/v1`,
  `risk_evaluation_context/v1`, and `risk_decision/v1` fingerprints. Coverage
  and findings remain unfingerprinted.
- Structural approval proves neither financial sufficiency nor execution
  authority. There is no target delta, open-order netting, notional, buying
  power, cash sufficiency, FX, margin, leverage, concentration, short
  authorization, `valid_until`, or revalidation helper. A later answer requires
  a new context and evaluator run. See
  `docs/adr/0016-structural-risk-decision-foundation.md`.

## Position Target Translation Domain
- `market_platform.execution_planning` converts one exactly corresponding
  approved structural-risk context and decision into one bounded signed
  target/current/delta translation at the same explicit UTC evaluation time.
- Complete-account position coverage makes an absent target row mean zero. Any
  exact target-instrument open-order exposure blocks translation; v0.60 never
  sums or nets exposure.
- Exact fixed-point arithmetic is limited to direction signing, absent-position
  zero, target-minus-current subtraction, and sign classification. A zero delta
  is a normal fingerprinted `no_action` result.
- The released and future flow is:

  TradingSignal -> OrderIntent ------------------------+
  InstrumentResolution -------------------------------+
  AccountCashSnapshot --------------------------------+
  PositionCollectionSnapshot -------------------------+-> RiskEvaluationContext
  OpenOrderExposureSnapshot ---------------------------+       -> RiskDecision
  MarketQuoteCollectionSnapshot ----------------------+              |
                                                                     v
                                                        PositionTargetTranslation
                                                               | actionable
                          no_action -> terminal audit           v
                                                BrokerNeutralExecutionInstruction
                                                               :
                                      future Order Specification / Authorization
                                                               :
                                                future Broker Request / Submission
                                                               :
                                                future Live Order Reconciliation

  Dotted `:` edges are future boundaries. Neither structural approval, a
  `buy`/`sell` translation, nor an instruction triggers approval, submission,
  or broker activity.
- V0.60 adds only `position_target_translation/v1`. It adds no order instruction,
  order style, price, financial or short authorization, application operation,
  persistence, adapter, CLI, network, or execution behavior. See
  `docs/adr/0017-position-target-translation-foundation.md`.

## Broker-Neutral Execution Instruction Domain
- V0.61 converts one exact validated actionable `PositionTargetTranslation` into
  one non-executable buy/sell instruction. Its positive quantity is the exact
  absolute delta. A canonical `no_action` translation returns `None` and remains
  the terminal audit artifact.
- The instruction copies only the translation fingerprint, canonical instrument
  evidence, account fingerprint, and exact `plan_as_of`. It adds exactly
  `broker_neutral_execution_instruction/v1` and no plan wrapper or policy.

## Explicit Order Style Choice Domain

- V0.62 adds one reusable caller-authored `OrderStyleChoice` with an explicit
  exact `market` or `limit` label. Missing input, strings, foreign enums,
  `None`, and unknown values fail; absence never means market.
- The choice contains only style, `order_style_choice/v1` schema, and
  fingerprint. It is independent of instructions, accounts, instruments, and
  time. MARKET is not execution authority; LIMIT intentionally has no price.
- Unlike factory-derived translations and instructions, the caller-authored
  choice has no guarded token, constructor-state tuple, identity binding, or
  retained source. Context-free projection still rejects stale or malformed
  retained public state.
- The released and future boundary is:

  PositionTargetTranslation(no_action) -> None instruction -> no specification

  BrokerNeutralExecutionInstruction ----+
                                         +-> Explicit OrderStyleChoice
                                               :
                               future Price / TIF / Session Constraint Choice
                                               :
                               future BrokerNeutralOrderSpecification
                                               :
                               future Authorization / Application Boundary
                                               :
                               future Broker Capability + Mapping Validation
                                               :
                               future Broker Request / Submission
                                               :
                               future Lifecycle / Reconciliation

  Dotted `:` edges remain future boundaries. The style choice never connects
  directly to a broker.

## Explicit Limit Price Choice Domain

- V0.63 adds one reusable caller-authored `LimitPriceChoice` containing an exact
  strictly positive canonical `Decimal` and exact uppercase ASCII
  three-letter trading currency.
- The price mirrors the released v0.58 public price resource contract: at most
  128 digit characters, 64 fractional digits, and 256 fixed-point characters.
  Tuple-based preflight precedes formatting, insignificant fractional zeros are
  removed, and no rounding or ambient-context arithmetic occurs.
- Canonical means bounded, deterministic, fixed-point, and currency-denominated.
  It does not mean instrument-matched, tick-aligned, venue-valid,
  broker-acceptable, executable, or authorized.
- The released and future boundary is:

  PositionTargetTranslation(no_action) -> None instruction -> no constraints

  BrokerNeutralExecutionInstruction ---+
                                      OrderStyleChoice ---+
                  LIMIT only: LimitPriceChoice -----------+
                                                          :
                                  future TIF / Session Choices
                                                          :
                         future BrokerNeutralOrderSpecification
                                                          :
                       future Authorization / Application Boundary
                                                          :
                     future Broker Capability + Mapping Validation
                                                          :
                         future Broker Request / Submission
                                                          :
                         future Lifecycle / Reconciliation

  MARKET consumes no `LimitPriceChoice`. All `:` edges remain future
  boundaries; no released choice connects directly to a broker.

## Explicit Time-in-Force Choice Domain

- V0.64 adds one reusable caller-authored `TimeInForceChoice` containing
  exactly one explicit DAY, GTC, IOC, or FOK label. Missing input and strings
  fail; absence never means DAY.
- DAY requests eligibility through a downstream-resolved order day. GTC
  requests persistence across days or sessions until canceled, subject to
  later rules. IOC requests immediate matching to the available extent and
  remainder cancellation. FOK requests immediate full execution or
  cancellation without partial fill. These are requests, not fulfillment or
  broker-support guarantees.
- The choice contains only TIF, `time_in_force_choice/v1` schema, and
  fingerprint. It is timeless and independent of style, price, instruction,
  account, instrument, session, authorization, and capability.
- GTD is unavailable. It requires a future explicit expiry source, canonical
  timestamp representation, comparison anchor, and broker/calendar contract.
- The released and future boundary is:

  PositionTargetTranslation(no_action) -> None instruction -> no choices consumed

  BrokerNeutralExecutionInstruction ---+
  OrderStyleChoice ---------------------+
  LIMIT only: LimitPriceChoice ---------+
  exactly one TimeInForceChoice --------+
                                        :
                            future Session Choice, if required
                                        :
                            future BrokerNeutralOrderSpecification
                                        :
                            future Authorization / Application Boundary
                                        :
                            future Broker Capability + Mapping Validation
                                        :
                            future Broker Request / Submission
                                        :
                            future Lifecycle / Reconciliation

  MARKET consumes no `LimitPriceChoice`. Every future specification consumes
  exactly one `TimeInForceChoice`; no TIF is incomplete rather than DAY.
  Dotted `:` edges remain future, and no released choice connects to a broker.

## Explicit Session Participation Choice Domain

- V0.65 adds one timeless caller-authored `SessionParticipationChoice` with
  exactly `REGULAR_ONLY` or `REGULAR_AND_EXTENDED`. Missing input is incomplete;
  it never means regular-only, extended participation, or a broker default.
- `REGULAR_ONLY` requests the applicable downstream-resolved regular session.
  `REGULAR_AND_EXTENDED` additionally requests eligible downstream-resolved
  non-regular continuous sessions. Neither value defines exact windows,
  calendars, timezones, auctions, current-open state, or guaranteed routing.
- The choice is independent of instrument, venue, style, price, TIF,
  instruction, account, authorization, and capability. DAY does not imply
  regular-only; no-action terminates before any order choices are consumed.
- The released and future boundary is:

  BrokerNeutralExecutionInstruction -----+
  OrderStyleChoice -----------------------+
  LIMIT only: LimitPriceChoice -----------+
  exactly one TimeInForceChoice ----------+
  exactly one SessionParticipationChoice -+
                                          :
                      future BrokerNeutralOrderSpecification
                                          :
                      future Authorization / Application Boundary
                                          :
                      future Broker Capability + Mapping Validation
                                          :
                      future Broker Request / Submission
                                          :
                      future Lifecycle / Reconciliation

  MARKET consumes no `LimitPriceChoice`; future LIMIT specifications require
  one. Every future specification consumes exactly one TIF and one session
  choice. All `:` edges remain future.

## Broker-Neutral Order Specification Domain

- V0.66 adds factory-owned `BrokerNeutralOrderSpecification`, the first complete
  internally coherent broker-neutral order request. It binds one exact
  instruction, its independently reconstructed canonical instrument, explicit
  style, conditional price, TIF, and session sources.
- The keyword-only factory requires all six arguments. MARKET requires explicit
  `None` and projects JSON null; LIMIT requires exactly one `LimitPriceChoice`
  whose trading currency equals `CanonicalInstrument.trading_currency`.
- The public model retains the six complete bounded source artifacts plus schema
  and fingerprint. Private token, constructor state, and identity binding reject
  equal-but-distinct source replacement and coherent retained-state fabrication.
- No new timestamp exists. The instruction's `plan_as_of` remains transitively
  bound. No-action ends before specification construction.
- The released and future boundary is:

  ```text
  BrokerNeutralExecutionInstruction -----+
  CanonicalInstrument -------------------+
  OrderStyleChoice ----------------------+
  conditional LimitPriceChoice ----------+--> BrokerNeutralOrderSpecification
  TimeInForceChoice ----------------------+
  SessionParticipationChoice ------------+
                                                   :
                              future Authorization/Application Boundary
                                                   :
                              future Capability and Broker Mapping
                                                   :
                              future Broker Request/Submission
                                                   :
                              future Lifecycle/Reconciliation
  ```

  The solid edge is released. Every `:` edge remains future. Complete intent is
  not authorization or broker support. Every specification requires TIF and
  session choices; style/TIF/session compatibility remains downstream.
## Broker Execution Structural Capability Domain

- V0.67 adds one factory-owned `BrokerExecutionCapabilityProfile` for an opaque
  execution target and one evaluator-owned
  `BrokerExecutionStructuralCompatibilityResult`.
- The profile declares independent supported asset-class, trading-currency, and
  venue domains plus exact supported style/TIF/session combinations. All are
  nonempty exact canonical tuples; the factory rejects coercion, duplicates, and
  noncanonical order.
- Compatibility validates the complete v0.66 specification and profile, then
  emits fixed-order reasons for unsupported asset class, currency, venue, style,
  TIF, session, or an otherwise unsupported exact combination.
- The result is self-contained fingerprint-bound value evidence. It retains no
  source objects, registry, attestation, weak references, timestamps, accounts,
  credentials, or process-local identity.
- `compatible` means only that the specification fits the bounded dimensions
  declared by the profile. It does not mean broker acceptance, authorization,
  risk approval, mapping, routing, submission, or executability.
- Asset, currency, and venue sets are intentionally independent in v1. Exact
  order-policy combinations cover only style, TIF, and session. Product,
  account, quantity, lot, tick, collar, price-band, live-state, and cross-matrix
  rules remain downstream.
- The released and future boundary is:

  ```text
  BrokerNeutralOrderSpecification -----------+
  BrokerExecutionCapabilityProfile ----------+-->
      BrokerExecutionStructuralCompatibilityResult
                                                   :
                                  future Broker-Native Order Mapping
                                                   :
                                  future Authorization / Submission
                                                   :
                                  future Lifecycle / Reconciliation
  ```

  The solid evaluation is deterministic and offline. Every dotted edge remains
  future work.

## Broker-Native Order Mapping Domain

- V0.68 adds the outbound `BrokerNativeOrderMapper` port, a bounded
  `BrokerNativeOrderRepresentation`, and self-contained
  `BrokerNativeOrderMapping` provenance in `execution_planning`.
- Mapping requires an exact specification, matching capability profile, exact
  compatible structural result, and one caller-supplied active
  `InstrumentMapping`. The mapping is used canonical-to-external; there is no
  lookup, search, resolver, route selection, or live contract discovery.
- Mapper target, ID, version, policy fingerprint, and namespace are captured
  exactly once. The operation is bound once and invoked once only after all
  independently checkable preconditions pass.
- Native side, order-type, TIF, and session tokens are opaque bounded adapter
  vocabulary. The platform proves token shape and reconstructible source,
  instrument, quantity, and price correspondence, not target-token meaning or
  mapper correctness.
- Decimal scale is non-semantic and reuses existing instruction and limit-price
  canonicalization. MARKET maps no price; LIMIT maps its exact canonical price
  and currency without rounding, ticks, collars, or conversion.
- `native_order` is owned nested semantic state. The mapping retains no upstream
  sources or mapper, and enforces parent/child namespace consistency without a
  registry, attestation, weak reference, or process-local identity.
- The boundary remains pure and offline:

  ```text
  BrokerNeutralOrderSpecification -------------------+
  BrokerExecutionCapabilityProfile ------------------+
  compatible StructuralCompatibilityResult ----------+--> BrokerNativeOrderMapping
  caller-supplied active InstrumentMapping -----------+             :
  BrokerNativeOrderMapper ----------------------------+    future Authorization
                                                                    :
                                                           future Submission
                                                                    :
                                                      future Lifecycle/Reconciliation
  ```

  Mapping is not authorization, submission, broker acceptance, or complete
  executability. Dotted edges remain future work.
