# ADR 0047: Radar Core Gate, Profile and Pipeline Contracts

## Status

Accepted

This ADR freezes the architectural contracts for RadarGate, RadarProfile and
RadarPipeline based on the completed v0.83 Radar core reconnaissance. It records
decisions only; production implementation, concrete Python contracts and module
locations remain separate work. It adds no dependency and changes no frozen
v0.82 semantics.

## Context and inspected baseline

- Branch: `feature/v0.83.0-radar`.
- HEAD: `097eba9a81818aa44e43bac8dc718c142240f0dd`.
- Parent: `944865b9732af3fd7f4624c1f08a993249abf178`.
- Local `main` and local `origin/main`:
  `1e60406a153105eca2b76db735635b8553108827`.
- Worktree and index were clean before drafting; refs were inspected without
  fetching.
- ADR0046 exists and is Accepted and frozen; ADR0047 is the next available number.

Radar is wide, shallow, inexpensive, non-authoritative, configurable and
multi-symbol. It sits upstream of existing Governed Research and answers:

> Which instruments deserve deeper research?

Radar does not create investment recommendations, BUY/SELL/HOLD, target, stop,
sizing, order intent or execution authority.

[ADR0046](0046_radar_exchange_session_calendar_foundation.md) remains unchanged.
Its ExchangeSessionCalendar supplies session facts; session completion does not
establish provider availability, meaningful change or governed Evidence
Freshness. Its public NASDAQ identity and private backend mapping remain intact.

The reconnaissance found useful small architectural patterns, but no existing
abstraction fits the complete Radar filtering contract. The
[Radar kickoff handoff](../handoffs/v0.83.0-radar-architecture-kickoff-handoff.md)
provides the prior architectural and testability context; this ADR resolves the
core decisions below without freezing its other provisional directions.

## Decision 1: No new core pipeline dependency

RadarGate, RadarProfile and RadarPipeline are small market-platform-owned domain
contracts. No additional pipeline or orchestration dependency is justified for
the core.

The prior reconnaissance considered StrategyRunner/StrategyCollection,
historical replay workflow, provider fallback, scikit-learn Pipeline and Prefect.
None supplies Radar's required combination of normal filtering disposition,
attention semantics, ordered profile identity, early termination, executed-prefix
audit and non-authoritative market-domain meaning. Their specific patterns remain
useful where they fit; none is adopted as the complete core abstraction.

This decision permits a future outer scheduler or orchestrator to use an external
framework. ADR0046's calendar dependency decision is separate and unchanged.

## Decision 2: Evaluation context and lazy fact access

Every Gate evaluates against one per-instrument RadarEvaluationContext, or an
equivalently named market-platform-owned context contract. Gates do not
communicate through hidden mutable outputs consumed by later Gates. Exact
concrete class and module names are not frozen.

The context conceptually owns canonical instrument identity, evaluation/as-of
context, access to required Radar facts, per-execution lazy fact calculation or
acquisition, and per-execution memoization where safe.

1. A Gate requests only facts it requires through explicitly supported access.
2. Expensive facts must not be eagerly constructed merely because a later Gate
   might need them. When an earlier Gate terminates evaluation, facts needed only
   by later Gates should remain uncomputed where architecture permits.
3. Fact calculation/acquisition is separate from Gate decision semantics.
4. A Gate must not silently mutate the context for later Gates. Context-owned
   memoization is an execution-local optimization, not a Gate output channel.
5. Shared memoization may avoid recalculating the same deterministic fact within
   one execution. It grants no authority and is not durable trusted state.
6. Existing observations, historical prices, signals and indicators may supply
   facts where their semantics fit; no existing object is the universal input.
7. Governed Technical, Interpretation, Assessment and Strategy results must not
   become ordinary Radar prerequisites.

This boundary preserves coarse-to-fine cost savings and profile reorderability.
Skipping later Gate calls is insufficient if context construction has already
performed all their expensive work. External acquisition remains behind injected
integrations rather than arbitrary provider access inside Gate decisions.

## Decision 3: RadarGate

RadarGate is a narrow non-authoritative evaluator with stable Gate definition
identity, a resolvable implementation, deterministic/configured behavior over
supplied context, and one bounded evaluation result:

```text
RadarGate.evaluate(context) -> RadarGateResult
```

This is conceptual notation, not frozen Protocol/class syntax. A Gate may request
an explicitly supported fact through the context. It must not itself perform
arbitrary provider selection, create Evidence, establish governed Freshness,
admit or qualify Evidence, invoke Governed Research, publish governed Technical,
Interpretation, Assessment or Strategy, create investment recommendations, or
create execution authority.

## Decision 4: Gate definition identity

Use TechnicalPolicyIdentity as the strongest identity precedent without reusing
its technical-research enums or configuration types. A Gate definition identity
conceptually separates:

- `gate_id`;
- `behavioral_revision`;
- `configuration_schema`;
- typed/passive configuration;
- identity schema version;
- deterministic fingerprint.

Behavior revision is distinct from configuration, and configuration
interpretation is versioned. The fingerprint binds serialized identity and
configuration content for reproducibility/correspondence; it grants no authority.
Configuration must not embed arbitrary executable code. Exact field names and
schema identifiers remain production-contract details.

## Decision 5: Gate dispositions

Radar owns a distinct disposition vocabulary. Do not reuse
EvidenceValidationDisposition, RiskDecisionOutcome or StrategyEvaluationStatus
as the Radar Gate enum.

| Gate disposition | Meaning | v1 continuation |
| --- | --- | --- |
| `PASS` | This Gate's condition permits evaluation to continue. | Continue to the next occurrence, if any. |
| `DROP` | Normal Radar filtering outcome. | Terminate this instrument's remaining Gate sequence. |
| `ATTENTION` | An expected operational/data condition prevents an ordinary filtering decision and requires attention. | Terminate this instrument's remaining Gate sequence. |

DROP does not mean invalid Evidence, investment rejection, SELL, avoid, failed
strategy or error. ATTENTION may later cover unavailable, stale or incomplete
required observations; these examples do not define a freshness policy.
ATTENTION is neither a RadarCandidate nor an investment conclusion.

Unexpected programming/runtime exceptions are not converted to ATTENTION. They
belong to execution failure handling.

## Decision 6: Execution failure

An unexpected Gate exception terminates the current instrument execution and
produces an execution `FAILED` outcome at the Pipeline/application boundary.
Failure is separate from Gate disposition: it must not be rewritten as DROP or
ATTENTION and must not create a RadarCandidate.

In multi-instrument orchestration, failure of one instrument does not by itself
require terminating unrelated instruments. Exact batch orchestration, scheduling
and continuation mechanisms are later contracts.

## Decision 7: RadarProfile

RadarProfile is the primary versioned definition of Radar behavior. Use
TechnicalPolicyIdentity and StrategyCollection as architectural precedents, not
direct Radar domain types.

A Profile conceptually binds profile ID, behavioral revision, configuration
schema/version, profile-level configuration if needed, an exact ordered sequence
of Gate specifications, and a deterministic profile fingerprint.

Gate order is behavior. Serialization and fingerprinting must preserve that exact
order; Gate definitions must not be sorted before fingerprinting. A mutable
display name alone is insufficient identity. Changing Gate order or behaviorally
relevant Gate configuration changes Profile identity/fingerprint.

The selected Profile identity remains stable throughout an instrument evaluation.
The Profile cannot silently mutate midway through execution, including through
nested configuration. A frozen outer object alone does not guarantee this.

## Decision 8: Profile resolution and pluggability

Resolve Profiles and Gate implementations through code-owned, known, allow-listed
implementations/factories, following the historical replay resolver precedent.
Configuration is passive. Do not use arbitrary configuration import strings,
`eval`/`exec`, model-authored executable Python or uncontrolled runtime plugin
mutation.

A future Agent may request/select among approved Profiles subject to higher-level
policy. It may not silently register arbitrary executable behavior or modify the
selected Profile during a run. Exact approval/governance for Profile registration
remains later work.

## Decision 9: Gate occurrences and duplicates

A Profile may use the same Gate implementation, or even equivalent Gate
definitions, more than once when genuinely required. Every ordered occurrence
must have a unique profile-local step/occurrence identity. Gate definition
identity and occurrence identity within a Profile are distinct.

For example, `step_1` may be RSI configuration A, `step_2` MACD, and `step_3` RSI
configuration B. These are illustrative identities, not concrete Gates or a
frozen step identifier schema. Distinct occurrences prevent ambiguous audit
records even when their Gate definitions are equivalent.

## Decision 10: Ordering dependencies

Core v1 avoids hidden Gate-to-Gate produced-data dependencies. Order primarily
controls filtering sequence, fact acquisition/calculation cost, termination and
behavior identity. Gates should request shared facts from the context rather than
require outputs produced by earlier Gates.

A tuple does not make every arbitrary ordering valid. Profile construction or
resolution must be able to reject combinations that violate explicit Gate
requirements or other Profile constraints. The requirement-declaration schema
and minimum Profile completeness remain implementation-design details.

## Decision 11: RadarPipeline

RadarPipeline deterministically executes one already-resolved Profile against
one instrument evaluation context. It executes occurrences in exact Profile
order, applies termination semantics, preserves actual executed result order,
records why evaluation terminated, and preserves correspondence to Profile and
input identity. It never invents outcomes for unexecuted Gates.

The Pipeline does not choose or mutate the Profile during execution. The core
executor remains non-authoritative.

## Decision 12: Executed-prefix audit

Pipeline results contain actual executed Gate results only. Later unexecuted
Gates remain known from the selected Profile but receive no synthetic
PASS/DROP/ATTENTION result.

The execution record must distinguish full successful traversal, termination by
DROP, termination by ATTENTION, and execution failure. It identifies the Gate
occurrence that terminated execution, where applicable, and preserves completed
results in their actual order. If a Gate raises instead of returning a result,
record that occurrence as the failure location without fabricating a Gate
disposition for it.

Minimum audit correspondence includes selected Profile identity, instrument and
input/evaluation context, executed occurrence identities and their bounded
descriptive results, and final outcome/termination reason. Exact envelope fields,
failure representation and serialization remain production-contract work.

## Decision 13: Final Pipeline outcomes

Pipeline outcomes are separate from Gate dispositions and distinguish at least:

| Pipeline outcome | Meaning |
| --- | --- |
| `SELECTED` | All required Gate occurrences completed with PASS under the selected Profile. |
| `FILTERED` | A Gate returned DROP. |
| `ATTENTION` | A Gate returned ATTENTION. |
| `FAILED` | Unexpected execution failure occurred. |

These are Radar execution outcomes only. SELECTED means the instrument survived
the selected Profile and may be considered by the next Radar/application step.
It does not mean BUY, recommendation, approved trade, valid/admitted Evidence or
positive Strategy. Exact enum/type names are not frozen.

## Decision 14: RadarCandidate boundary

RadarGate does not create RadarCandidate. Core RadarPipeline need not create a
RadarCandidate value directly. A future application layer may create one from a
SELECTED Pipeline result, separating evaluation from candidate lifecycle,
deduplication, persistence and escalation.

The RadarCandidate contract remains undefined. Prefer that domain term to bare
Candidate because the repository already has Evidence Candidate,
StrategyCandidate, ProviderCandidate, PriceLevelCandidate and replay Candidate
concepts. No existing frozen object is renamed.

## Decision 15: Identity and fingerprint boundaries

| Subject | Boundary |
| --- | --- |
| Gate definition | Strong deterministic identity is useful; follow Decision 4. |
| Profile | Strong deterministic identity is required and binds ordered composition. |
| Pipeline execution/result | May carry a deterministic content/result fingerprint where comparison, persistence or deduplication requires it. |
| Observation/input | Identity must establish result correspondence; the final input/LightweightObservation identity schema is deferred. |
| RadarCandidate | Identity is deferred to its future contract. |

Keep these distinctions explicit:

```text
content identity != execution occurrence identity
fingerprint != authority
fingerprint inequality != economically meaningful change
```

Wall-clock start/completion time and execution duration must not alter the
semantic behavior identity of the selected Profile. These identity decisions do
not define observation equivalence or MeaningfulChangePolicy.

## Decision 16: No separate Pipeline behavior identity in v1

Do not create a second independent Pipeline behavior definition/fingerprint in
v1 when semantics are fully determined by the frozen engine contract, selected
Profile and input/context. RadarProfile remains the primary behavior identity.
An implementation/executor version may appear in diagnostics.

If Pipeline behavior becomes configurable or independently semantic, introduce
a separately reviewed versioning decision. An optional execution/result content
fingerprint is not a second behavior definition.

## Decision 17: Observation input boundary

No universal LightweightObservation schema is frozen. Useful precedents include
MarketObservation and observation builders, HistoricalPriceSeries and
HistoricalPricePrefix, MarketSignal and MarketSignalSnapshot,
SignalClassification, indicator functions, comparison results, and ADR0046
session/calendar facts.

The core permits bounded, explicitly supplied or lazily resolved facts without
requiring the full governed chain. MarketObservation may be used where
appropriate but is not mandatory for every Gate. Full TechnicalAnalysisSnapshot
must not become a universal Radar prerequisite. Meaningful observation
equivalence remains later work.

## Decision 18: Telemetry

Cost/selectivity telemetry belongs to diagnostics, separate from deterministic
Radar behavior. Future diagnostics may record Gate input count, PASS/DROP/
ATTENTION counts, FAILED execution count and execution duration. FAILED remains
an execution outcome, not an additional Gate disposition.

Telemetry must bind to exact Profile/Gate identity and distinguish occurrences
where the same definition appears more than once. Skipped/unexecuted Gates must
not inflate disposition counts. Timing must not alter semantic Profile identity.
Automatic Gate reordering from telemetry is out of scope for v0.83 v1.

## Decision 19: Testability

Core contracts must remain testable primarily as FAST PURE and LOCAL APPLICATION.
Gate/Profile/Pipeline tests must not require authentic v0.82 retained authority
chains. Use supplied facts, fake Gates and injected external integrations to
exercise the boundaries without constructing governed research authority.

Expected fast coverage includes configuration validation, identity/fingerprints,
dispositions, Profile ordering, duplicate occurrence identity, resolver behavior,
lazy fact use, short-circuiting, executed-prefix recording, final Pipeline outcome
and result correspondence. Lazy-use coverage must demonstrate that terminating
early avoids requesting facts needed only by later Gates.

Focused AUTHENTIC CHAIN tests belong only at the later escalation boundary into
existing Governed Research. Broad certification remains RELEASE ONLY where
warranted. These are future implementation requirements; this ADR adds or runs
no tests.

## Decision 20: Authority boundary

RadarGate, RadarProfile and RadarPipeline are NON-AUTHORITATIVE. They must not by
themselves:

- create Evidence authority or establish Evidence validity/admission;
- establish governed Freshness or qualify Evidence;
- publish governed Technical, Interpretation, Assessment or Strategy;
- approve a Scenario/Risk/Plan;
- create investment recommendations, BUY/SELL/HOLD, target, stop or sizing;
- create order intent or authorize execution.

Radar SELECTED means only:

> This instrument survived the selected Radar Profile and deserves the next
> Radar/application consideration.

Neither selection, a fingerprint nor memoized facts grant authority. Existing
Governed Research retains its own escalation, admission and publication
boundaries; frozen v0.82 semantics are unchanged.

## Design precedents

These are pattern precedents, not coupling to the corresponding domain types or
permission to copy private authority machinery. Paths are relative to
`src/market_platform/`.

| Module and symbol | Applicable precedent |
| --- | --- |
| `state/protocol.py`: `MarketStateModel` | Narrow Protocol/evaluator interface. |
| `research/technical_policy.py`: `TechnicalPolicyIdentity` | Separate behavior, configuration interpretation, identity schema and fingerprint. |
| `strategy/collection.py`: `StrategyCollection` | Explicit ordered composition. |
| `strategy/runner.py`: `StrategyRunner` | Ordered invocation and result correspondence; its ordinary evaluation does not supply Radar short-circuit semantics. |
| `application/historical_replay_research_resolvers.py`: `HistoricalReplayResearchStrategyResolver`, `BuiltInHistoricalReplayResearchStrategyResolver` | Code-owned allow-listed factory resolution. |
| `strategy/models.py`: `StrategyRunResult` | Descriptive result accounting. |
| `research/historical_replay_workflow.py` and `research/historical_replay_workflow_service.py`: workflow results and `HistoricalReplayResearchWorkflowService` | Retained outcomes, termination/dependency accounting and sibling continuation precedent. |
| `_fingerprint.py`: `canonical_fingerprint` | Deterministic correspondence, not authority. |

Do not import authority-bearing vocabulary merely because its structure looks
similar. No existing runner, replay workflow or provider fallback is adopted as
the complete Radar executor.

## Consequences

Radar owns a small domain contract with explicit filtering, attention and failure
semantics. Stable ordered Profiles and occurrence identity make executed-prefix
audits unambiguous. Lazy shared facts permit early-work avoidance without hidden
Gate output dependencies. These benefits require deliberate context ownership,
safe memoization and Profile validation in later implementation.

The core can be tested independently of governed authority construction.
Candidate lifecycle, acquisition details and outer orchestration remain separate
work rather than becoming incidental Pipeline responsibilities.

## Non-goals

This ADR does not define or implement:

- concrete Gates such as MACD/RSI/ATR or concrete Radar Profiles;
- final class/module names or concrete production schemas;
- LightweightObservation, observation equivalence, MeaningfulChangePolicy or
  `material_numeric_movement` thresholds;
- RadarCandidate schema, identity, persistence or deduplication;
- watchlist persistence, scheduler or batch orchestration;
- Profile registration approval authority or sector/regime selection policy;
- automatic Gate reordering;
- the Governed Research escalation contract;
- Signal Study, backtesting, Scenario/Risk/Plan, execution or Shadow Observer.

No production code, tests, dependencies, `pyproject.toml`, `uv.lock`, ADR0046 or
frozen v0.82 behavior are changed by this decision-record task.
