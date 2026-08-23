# ADR 0033: Market Intelligence Agent Boundary

## Status

Proposed.

This decision is not part of the v0.75.0 implementation scope. It constrains
future Agent exposure work only.

## Context

`market-platform` provides deterministic, provenance-bearing financial research
and related infrastructure. V0.74 established a descriptive daily technical
pipeline:

```text
Verified Research
    -> Interpretation
    -> Assessment
    -> Strategy
```

Interpretation determines what market state exists. Assessment determines how
coherent, conflicting, incomplete, or cautionary that state is. Strategy
determines what descriptive strategy logic is applicable. None of these values
is a trade instruction, portfolio decision, risk approval, or execution
authorization.

ADR 0032 proposes a transport-neutral application boundary that composes this
pipeline while preserving domain authority and correspondence. It also
establishes that future CLI, HTTP, UI, and Agent consumers must use the
application service rather than reproduce domain orchestration.

A future AI Agent may make these capabilities easier to discover and use
through natural-language interaction. Without an explicit boundary, however,
the Agent could become a second source of financial semantics, call internal
runners directly, reinterpret descriptive Strategy as trading action, or
connect intelligence output to execution authority.

This decision defines the dependency direction and semantic limits for such an
Agent. It does not implement the Agent or any Agent-facing API.

## Decision

### Platform identity

This decision defines only the Agent-visible intelligence boundary as a
financial intelligence infrastructure surface. It does not classify the
entire `market-platform` permanently as only a financial intelligence
platform. Separately governed future Trade Planning, Risk, Execution, broker
integration, and operational service layers remain possible, but they remain
outside this Agent intelligence boundary.

`market-platform` is not an AI assistant and does not acquire an assistant
persona, conversation model, prompt framework, memory system, or LLM runtime
through this decision.

The platform owns deterministic financial capabilities, their domain
semantics, validation, provenance, policy identity, correspondence, and
versioned application contracts.

An Agent is an external consumer of those capabilities.

"External" is an architectural distinction. The Agent may eventually run in
another process or in the same deployment, but it remains outside the
platform's domain and application ownership. Dependencies point from the Agent
toward explicitly exposed application capabilities and never from
`market-platform` toward the Agent.

### Responsibility boundary

The Agent may:

- interpret natural-language requests;
- select an exposed application capability;
- collect caller intent for that capability;
- invoke the Agent Exposure Boundary;
- combine or summarize completed application responses for presentation; and
- explain limitations, provenance, and uncertainty already represented by
  returned results.

The Agent must not:

- own or redefine financial semantics;
- canonicalize or validate financial inputs;
- normalize timestamps or resolve instrument identities;
- calculate authoritative indicators, interpretations, assessments,
  strategies, exposures, or findings;
- recompute domain logic to verify, repair, enrich, or override a result;
- infer a trading action from descriptive Strategy vocabulary;
- fabricate missing domain values;
- replace deterministic policy behavior with prompt instructions; or
- treat generated prose as an authoritative platform result.

Prompt text, tool descriptions, retrieval content, and model reasoning are not
financial policy implementations.

### Agent Exposure Boundary

The Agent does not access the generic application surface directly. Agent
access passes through an explicit exposure boundary:

```text
Agent
    -> Agent Exposure Adapter / Facade
        -> allow-listed application capabilities
            -> domain composition boundaries
                -> domain policies and values
```

An application service is not Agent-accessible merely because it is public or
exists in `market_platform.application`. Only application capabilities
explicitly included in the Agent exposure allow-list may be invoked through
the facade. Reflection, generic service invocation, and automatic exposure of
new application services are prohibited.

The Agent Exposure Adapter or Facade owns only transport adaptation, Agent tool
schemas, capability discovery metadata, and the explicit capability
allow-list. It owns no financial semantics, policy selection logic, domain
orchestration, canonicalization, or result reinterpretation. Capability
metadata describes availability and request and response shapes; it does not
duplicate financial rules.

Application adapters receive caller intent and own request decoding,
canonicalization, validation, timestamp normalization, and identity resolution
where required by the capability. The Agent supplies intent and does not repair
or normalize rejected inputs.

The exposure facade delegates to application operations. It must never invoke
internal domain runners, policies, factories, or orchestration sequences
directly.

### Agent memory and user preferences

Conversation history, short- or long-term memory, user profiles, and
presentation preferences belong to the Agent host. `market-platform` does not
store, retrieve, interpret, or implicitly depend on them.

Agent memory and preferences may influence presentation and the selection of
an exposed capability. They must not silently alter application profiles,
policy behavior, validation, financial defaults, or domain results.

A financially material preference or constraint, including an investment
horizon, objective, risk tolerance, allocation constraint, or scenario
assumption, can affect platform semantics only after it becomes an explicit,
typed, versioned application input. The relevant application and domain
contracts then own its validation and meaning. The Agent's remembered form is
not authoritative input.

Results retained in Agent history or memory keep their original provenance,
policy identity, and effective or evaluation time. Remembering a result does
not refresh it, make it current, or create new platform evidence.

### Application boundary

The application layer remains the stable interface between exposed Agent
capabilities and the platform's domain capabilities. The Agent Exposure
Boundary narrows access to that interface; it does not replace it.

Application services remain responsible for:

- ordering domain operations;
- selecting or enforcing an approved application profile;
- invoking released domain boundaries;
- validating result correspondence;
- preserving lineage and policy identities; and
- returning a complete success result or the defined failure.

Domain policies and runners remain the sole authorities for financial
semantics. The application layer coordinates them but does not recompute their
decisions. Agent-facing adapters translate transport representations but own
no financial semantics.

Public Python availability does not make an internal domain operation or an
application service an Agent-supported interface.

### Capability model

The initial planned Agent-accessible intelligence families are Daily Technical
Intelligence, Options Intelligence, Macro Intelligence, and Portfolio
Intelligence. These are an initial taxonomy, not an exhaustive or permanently
closed set. A new family requires its own explicit domain, application, and
Agent exposure decisions.

Each capability family remains a distinct semantic family rather than a mode
of a catch-all analysis operation. Families may evolve and version
independently. Cross-capability synthesis performed by an Agent is explanatory
unless a platform application service explicitly owns and validates the
combined semantics.

#### Daily Technical Intelligence

Daily Technical Intelligence exposes the verified daily technical research,
Interpretation, Assessment, and Strategy semantic family through an approved
application boundary.

Its outputs remain descriptive and non-actionable. In particular:

- `NO_ACTIVE_STRATEGY` is not hold, exit, close, or remain flat;
- positive directional continuation is not buy or open long; and
- negative directional continuation is not sell, short, or exit long.

ADR 0032's application service is the intended initial composition pattern.
Any Agent-accessible transport projection is a separate contract and must not
bypass that service or recreate its orchestration.

#### Options Intelligence

Options Intelligence may eventually provide validated options-market
observations and deterministic options analytics through its own application
contracts.

It must define its own canonical inputs, temporal rules, provenance, policies,
schemas, and bounded outputs. It must not be implemented as Agent-side
calculations over raw chains or as an unversioned extension of Daily Technical
Intelligence.

Options Intelligence does not imply an option trade, contract selection,
position size, risk approval, or order.

#### Macro Intelligence

Macro Intelligence may eventually provide normalized macroeconomic evidence,
releases, regimes, or deterministic interpretations through dedicated
application contracts.

It must preserve source identity, release and observation times, revisions,
provenance, and policy identity where applicable. Agent narrative must not
become the authoritative macro interpretation.

Macro Intelligence does not determine portfolio allocation or trade timing.

#### Portfolio Intelligence

Portfolio Intelligence may eventually describe caller-authorized portfolio
evidence, including holdings, exposure, concentration, attribution,
performance, or explicitly defined scenarios. It may consume authoritative
portfolio or account snapshots, but it does not own the holdings ledger or
account system of record.

Portfolio Intelligence is observational and analytical. It does not:

- choose investments;
- allocate capital;
- recommend or perform rebalancing;
- determine target positions;
- size trades;
- approve risk; or
- create portfolio actions.

Scenario assumptions that affect results must be explicit application inputs.
Scenario outputs remain descriptive and are not recommendations. Portfolio
Intelligence output does not automatically become Trade Planning input or Risk
evidence.

Any future portfolio decision capability requires a separate architectural
decision and must not be introduced under the name Portfolio Intelligence.

### Separation from the trading path

The Market Intelligence Agent boundary is separate from:

- Trade Planning;
- Risk;
- Execution;
- broker integration; and
- order lifecycle management.

```text
Intelligence capabilities -> Agent-visible descriptive results

Trade Planning -> concrete trade parameters or proposed actions
Risk           -> evaluation or approval of defined intent
Execution      -> instruction, authorization, submission, and lifecycle
Broker adapter -> broker-specific mapping and communication
```

No arrow is established from the Agent-facing intelligence boundary into Trade
Planning, Risk, Execution, or broker integration.

An intelligence response cannot be treated as:

- an Order Intent;
- a position target;
- a risk decision;
- an execution instruction;
- an execution authorization;
- a broker-native order;
- an order-submission request; or
- evidence of broker acceptance.

The existence of separately bounded trading, risk, and execution models
elsewhere in `market-platform` does not grant the Agent access to them. Any
future exposure of a non-intelligence capability requires its own explicit
application contract, exposure allow-list decision, authorization model,
threat review, and ADR.

### Legacy Strategy separation

The historical `market_platform.strategy.Strategy` family remains separate
from Daily Technical Intelligence and its descriptive
`DailyTechnicalStrategy` value. The Agent Exposure Boundary defines no adapter,
conversion, fallback, or compatibility path between them.

The Agent must not populate or consume `ResearchResult.strategy_candidates` or
`ResearchResult.position_actions` as substitutes for the Daily Technical
Intelligence application response.

### Parallel research workflow separation

The existing `DefaultResearchWorkflow`, `research-workflow-v1` ontology,
`research run` command, and `ResearchResult` contract remain parallel and
untouched. Under this decision, they are not Agent exposure targets, migration
sources, compatibility adapters, or alternate inputs for Intelligence
capabilities.

### TradingView positioning

TradingView outbound visualization and TradingView inbound event ingestion are
separate integrations with different trust boundaries.

#### Outbound visualization

TradingView may eventually display platform-produced intelligence or render
charts, overlays, annotations, and summaries. It is a visualization and
user-interaction layer, not an authoritative market-data, instrument-identity,
policy, or semantic layer.

TradingView symbols must not replace canonical instrument identity or
effective-dated mapping. TradingView indicators, scripts, alerts, chart values,
and user annotations must not replace verified provider evidence or
platform-owned calculations. Displaying a platform result in TradingView does
not transfer semantic authority to TradingView.

#### Inbound webhook and event ingestion

A TradingView webhook is an untrusted external event and does not enter through
the outbound visualization adapter or the Agent Exposure Boundary. The Agent
must not act as its receiver, relay, validator, authentication proxy, or
semantic interpreter.

```text
TradingView webhook
    -> dedicated untrusted-event ingress gateway
        -> separately approved application boundary
```

The ingress gateway requires its own explicit schema, authentication,
authorization, bounded resource limits, instrument identity mapping,
idempotency, expiry, and replay protection. It acknowledges and handles ingress
independently of downstream financial processing. Authentication establishes
only the accepted origin of an event; it does not establish market-data
authority, semantic validity, trading authority, risk approval, or execution
permission.

The ingress gateway must not call domain runners directly. Any downstream
capability requires a separately approved application boundary. TradingView
ingress must not bypass the existing Trading Signal and Order Intent separation
or create a path from webhook delivery to Trade Planning, Risk, Execution, or
broker activity. Detailed ingress behavior requires a separate ADR.

### Future API capability principles

Future Agent-facing APIs follow these principles:

1. **Explicit exposure**
   Only allow-listed intelligence capabilities are available through the Agent
   Exposure Boundary. Generic application services are not automatically
   exposed.

2. **Capability-specific operations**
   Expose named financial capabilities rather than a generic domain executor or
   catch-all analysis endpoint.

3. **Application-owned orchestration**
   Every exposed operation delegates to a public application service. Transport
   adapters and Agent tools do not call domain runners or reproduce their
   sequencing.

4. **Versioned contracts**
   Requests, responses, and external projections use explicit schemas and
   versions. A semantic-family change requires an explicit compatibility
   decision.

5. **Bounded transport projections**
   Remote APIs expose deliberate bounded projections rather than automatically
   serializing complete in-memory domain graphs.

6. **Explicit inputs**
   Material inputs, including identity and effective or evaluation time where
   required by the capability, are explicit. Hidden clocks, provider fallbacks,
   policy defaults, implicit Agent memory, and inferred trading intent are not
   introduced at the Agent boundary.

7. **Platform-owned normalization**
   Application adapters and contracts own canonicalization, validation,
   timestamp normalization, and identity resolution. Agent reasoning is not an
   input normalization boundary.

8. **Deterministic provenance**
   Responses preserve the fingerprints, source lineage, policy identities,
   timestamps, and correspondence needed to identify the authoritative result.

9. **Single semantic authority**
   Financial rules live in domain policies and composition boundaries. They are
   not duplicated in prompts, API adapters, tool schemas, presentation code, or
   Agent workflows.

10. **Approved application profiles**
    Agent callers cannot provide policy implementations, arbitrary policy
    identities, or unregistered configurations. An application contract may
    expose explicitly supported, application-owned, versioned profiles when
    profile selection is part of the approved capability semantics.

11. **Fail-closed behavior**
    Invalid, incomplete, or incoherent inputs, and stale inputs where the
    capability defines freshness semantics, fail through defined application
    behavior. The Agent does not repair them by inventing values or falling back
    to its own calculation.

12. **Presentation neutrality**
    Natural-language summaries, tables, charts, and TradingView views cannot
    alter domain values or fingerprints. Generated explanations remain derived
    presentation.

13. **Side-effect separation**
    Intelligence operations are read-only with respect to trading authority.
    They expose no implicit transition to planning, risk, execution, or broker
    submission.

14. **Transport concerns remain outside semantics**
    Authentication, authorization, rate limiting, correlation identifiers, and
    protocol error mapping belong to external adapters. Retries are permitted
    only when the invoked application contract and its idempotency semantics
    allow them. None of these concerns changes application or domain meaning.

15. **Replaceable consumers**
    An application capability remains transport-neutral and can support an
    Agent, CLI, UI, or conventional service client through separately approved
    exposure adapters. No application contract assumes that its caller is an
    LLM.

16. **No silent cross-capability synthesis**
    An Agent may present results from several capabilities together, but it
    cannot claim a new authoritative combined conclusion unless a dedicated
    application capability owns and validates that conclusion.

## Consequences

- AI models and Agent frameworks can evolve or be replaced without changing
  platform financial semantics.
- The Agent Exposure Boundary provides an explicit allow-list rather than
  exposing the generic application surface.
- Application capabilities remain the sole supported composition surface
  behind exposed Agent tools.
- Domain exports remain available to trusted application composition but are
  not Agent contracts.
- Agent memory and preferences remain outside the platform and cannot become
  hidden financial inputs.
- New intelligence families require explicit domain, application, and exposure
  boundaries before Agent access.
- Agent explanations remain useful presentation while authoritative values
  remain deterministic platform outputs.
- Provenance can be carried into conversations without treating conversational
  history as a source of truth or refreshing remembered results.
- The architecture prevents descriptive intelligence from silently becoming
  trade intent or execution authority.
- TradingView visualization and untrusted event ingress cannot share an
  authority boundary.
- Agent-facing transport work requires separate versioned projections,
  authentication, resource limits, and operational design.
- This decision does not make ADR 0032's proposed v0.75 service externally
  accessible and does not alter its request, response, policy, or failure
  contracts.

## Rejected alternatives

### Embed an LLM inside `market-platform`

Rejected because it would reverse the dependency direction, introduce
nondeterministic assistant behavior into the infrastructure layer, and blur
semantic authority.

### Allow the Agent to access generic application services

Rejected because public application availability is broader than approved
Agent exposure. A dedicated allow-list is required to prevent accidental access
to current or future non-intelligence capabilities.

### Allow the Agent to call domain runners directly

Rejected because it would duplicate orchestration, permit invalid stage
ordering, weaken correspondence guarantees, and couple the Agent to internal
domain evolution.

### Allow Agent memory to act as platform input

Rejected because implicit memory is not a typed, versioned, provenance-bearing
financial contract and could silently alter results.

### Encode financial rules in prompts or tool descriptions

Rejected because prompts are not versioned domain policies and cannot provide
deterministic validation, provenance, or semantic integrity.

### Use TradingView as the canonical analytical source

Rejected because visualization and alerting representations do not replace
canonical instruments, verified evidence, platform policies, or application
correspondence.

### Route TradingView webhooks through the Agent

Rejected because an Agent is not an ingress trust boundary, authentication
gateway, idempotency authority, or event validation layer.

### Expose one endpoint spanning intelligence through execution

Rejected because it would collapse descriptive analysis, planning, risk,
authorization, broker mapping, and submission into one authority boundary.

## Non-goals

This decision introduces:

- no LLM dependency inside `market-platform`;
- no Agent implementation;
- no Agent memory or user-profile storage;
- no conversational interface;
- no autonomous trading;
- no Trade Planning;
- no risk decision or risk approval;
- no order intent;
- no order execution;
- no broker integration;
- no order submission;
- no portfolio allocation, rebalancing, or investment decision;
- no TradingView visualization integration;
- no TradingView webhook ingress;
- no new API transport;
- no changes to existing domain semantics;
- no compatibility bridge to the legacy Strategy family; and
- no code or application behavior.
