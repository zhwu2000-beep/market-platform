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
