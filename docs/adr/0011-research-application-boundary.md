# ADR 0011: Research Application Boundary

## Status

Accepted

## Context

V0.53 provides deterministic historical Replay research, but its specification
owns runtime strategy and state-model objects. External callers need a
serializable boundary that resolves those objects safely without weakening
domain validation. The repository has no HTTP server, Agent tool runtime,
dataset repository, or externally safe executable registry.

## Decision

- `market_platform.application` owns a synchronous, transport-neutral facade.
  Domain packages never import the application layer.
- `historical_replay_research_application_request/v1` contains one inline
  source, exact Replay member projections, ordered strategies and candidates,
  one state-model request, structure identity, and three software revisions.
- Strict manual decoding rejects missing, unknown, malformed, non-finite, and
  timezone-naive values. Accepted timestamps normalize to UTC before identity
  is calculated. `HistoricalPriceSeries` remains authoritative for market-data
  validation.
- Public constructors and dictionary decoding share one recursive passive-JSON
  contract. Mappings freeze deterministically, sequences become tuples, and
  sets, runtime objects, custom serialization, and non-finite floats are
  rejected at every nesting depth.
- Application numerics retain their submitted JSON type and exact value:
  integers remain integers, floats remain floats, `1` differs from `1.0`, and
  `0.0` differs from `-0.0`. Large integers are not rounded. Distinct external
  numeric representations may intentionally resolve to equal domain intent
  after canonical price-series construction.
- The application request fingerprint identifies normalized external intent.
  The workflow specification fingerprint identifies resolved executable domain
  intent; the workflow result fingerprint identifies the terminal result.
- Injected strategy and state-model resolver protocols accept passive JSON-safe
  requests. Built-in resolvers use immutable allow-listed factory mappings and
  return fresh instances. They expose only the two baseline `StrategyInstance`
  implementations and stateless `BaselineMarketStateModel`.
- The application service independently checks returned IDs, versions, and
  configuration fingerprints before constructing v0.53 members.
- Expected allow-listed configuration failures become dedicated resolver
  errors. Built-in factories run outside that translation boundary, so their
  unexpected `TypeError`, `ValueError`, and other programming defects propagate.
- Expected request, source, and resolution failures use narrow typed
  exceptions. The facade does not catch workflow execution, invariant,
  Artifact, Experiment, programming, or control-flow failures.
- `historical_replay_research_application_response/v1` retains the complete
  in-memory workflow result but serializes bounded status and identity summaries
  only. It embeds no source rows, Replay steps, Artifact bodies/checksums,
  DataFrames, or executable objects. No response fingerprint is added.
- Response construction verifies the exact executed specification/result
  binding and the complete submitted-request-to-resolved-workflow projection:
  canonical source content, ordered members and executable identities,
  structures, Replay windows, fixed policy, and all revisions. An unrelated
  request fingerprint cannot be paired with a workflow result. Different
  requests may still resolve to equal workflow intent while retaining their
  distinct application request fingerprints.
- Dataclass representations suppress complete sources, row tuples, member
  collections, and configurations so routine logging stays bounded.
- The boundary is trusted and local. Requests cannot contain import paths,
  executable strings, pickle, shell commands, filesystem paths, URLs,
  credentials, or provider/broker access.

## Transport and Agent Deferral

HTTP, FastAPI, Flask, Starlette, OpenAPI, JSON Schema, authentication, rate
limits, CLI integration, asynchronous work, and Agent SDK/tool registration are
deferred. A future adapter must decode its own strict schema and invoke this
public facade rather than private Replay or workflow construction.

## Future TradingView Boundary

TradingView integration is a separate future operation:

```text
TradingView / Pine alert
        -> TradingView Signal Gateway
        -> Trading Signal application operation
        -> Order Intent and Risk layers
        -> Paper or Broker Execution adapter
```

A TradingView alert is a live signal event, not an inline historical research
dataset. No TradingView field is reserved in the v1 research request. A future
gateway must provide HTTPS ingress, bounded versioned payloads, authentication,
fast acknowledgement, idempotency and duplicate suppression, durable/auditable
receipt, timestamp and expiry validation, symbol/timeframe mapping, replay
protection, and failure-safe behavior. Passwords and broker credentials must
never appear in alert payloads. Browser automation is rejected. Signal
acceptance must remain separate from trade authorization, and broker execution
must remain behind explicit order-intent and risk controls.

## Consequences

The application boundary is reusable by future HTTP, UI, TradingView, or Agent
adapters while preserving one domain execution path. Inline requests can be
large; transport byte limits, authentication, timeouts, and rate limits belong
to a future ingress adapter. Artifact persistence, dataset references, generic
registries/plugins, live signals, orders, risk, and execution remain deferred.
