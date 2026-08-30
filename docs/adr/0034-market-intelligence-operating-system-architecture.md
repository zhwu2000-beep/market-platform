# ADR 0034: Market Intelligence Operating System Multi-Agent Architecture

## Status

Accepted for v0.77.0 Evidence Foundation.

This decision defines an architecture only. It does not approve or implement an
Agent runtime, LLM integration, API, transport, Options Intelligence, or trading
integration.

## Context

ADR 0032 establishes the transport-neutral application boundary for the
deterministic Daily Technical Strategy pipeline. The application service owns
orchestration and correspondence while domain policies and runners remain the
sole authorities for financial semantics.

ADR 0033 establishes the Market Intelligence Agent boundary. An Agent is an
external consumer of explicitly allow-listed application capabilities through
the Agent Exposure Boundary. The accepted v0.76 foundation provides capability
metadata, a capability-specific facade, and a bounded, provenance-bearing
response projection. It does not provide an Agent runtime, remote interface,
LLM, memory system, or autonomous behavior.

A future Market Intelligence Operating System may coordinate several
specialized Agents around those exposed intelligence capabilities. Without a
further decision, multi-Agent coordination could introduce shared hidden state,
allow one Agent's claims to become another Agent's evidence, duplicate
deterministic financial logic, collapse review into consensus, leak personal
context into market analysis, or present generated conclusions as decisions.

This ADR defines the logical roles, information boundaries, authority model,
and dependency rules for such a system. "Operating System" means a governed
coordination architecture for market-intelligence work. It does not mean an
operating-system kernel, a generic Agent executor, or an implemented runtime.

## Decision

### Architectural position

The Market Intelligence Operating System is a consumer architecture above the
accepted Agent Exposure Boundary:

```text
Human
    -> Market Intelligence Operating System
        -> specialized, independent Agents
            -> explicit Agent Exposure Boundary
                -> allow-listed application capabilities
                    -> application services
                        -> deterministic domain boundaries
```

The operating system may organize evidence retrieval, independent analysis,
adversarial review, synthesis, and presentation. It does not become part of
`market-platform` domain or application semantics. It does not expand the
v0.76 allow-list, expose the generic application surface, or create access to
domain runners.

ADR 0032 and ADR 0033 remain governing decisions. This ADR adds no alternate
path around them and changes none of their released contracts.

### Multi-Agent independence principle

Each Agent is an independently bounded reasoner with one declared
responsibility. Independence is semantic, not necessarily process-level: two
Agents may eventually share a deployment, model vendor, or host, but neither
may rely on another Agent's private state or become authoritative merely
because another Agent agrees.

Agents receive only the minimum explicit inputs needed for their assigned
role. By default, an Agent cannot read:

- another Agent's prompt, scratchpad, conversation history, or personal memory;
- another Agent's incomplete work;
- undeclared host state; or
- platform internals outside an allow-listed Agent projection.

Cross-Agent influence occurs only through an explicit, immutable artifact
whose producer, input references, information class, creation time, and
contract version are identifiable. Direct mutation of another Agent's output,
shared mutable analytical state, and implicit propagation through a common
conversation are prohibited.

Every interpretation-producing Specialist Intelligence Agent's first-pass
analysis MUST:

- receive only admissible Evidence and the explicit task context;
- not receive peer Interpretations;
- not receive peer confidence scores;
- not receive peer conclusions; and
- not inherit peer reasoning paths.

Peer artifacts may enter only Interpretation Validation, Synthesis, or
adversarial review. They MUST NOT enter another specialist's first-pass input.
No Interpretation, validation finding, Synthesis, Decision Brief, confidence
score, or other derived artifact may ever be reclassified as Evidence.

Model diversity may be used in a future implementation, but different model
names alone do not establish independence. Independence requires input
isolation, immutable artifact exchange, and responsibility separation.

### Canonical artifact flow

The operating system has one canonical immutable artifact DAG:

```text
Source Evidence
    -> Evidence Validation
        -> Independent Specialist Interpretation
            -> Interpretation Validation
                -> Synthesis
                    -> Synthesis Validation
                        -> Decision Brief
                            -> Human Decision
```

Each arrow is a forward dependency on identified, completed artifacts. Source
Evidence must pass Evidence Validation before it fans out to independently
produced specialist artifacts. Evidence Validation validates evidence quality
and authority. Interpretation Validation validates derived analysis and
governs its admission to Synthesis. Synthesis Validation validates the combined
decision support and governs its admission to a reviewed Decision Brief. The
Decision Brief is presented to, but does not replace, the human Decision.

The provenance DAG is immutable and acyclic. Published artifacts and their
dependency edges are append-only and MUST NOT be edited, replaced in place, or
rebound to different sources. Workflow retries, validation challenges, and
revision requests are control-plane events, not reverse artifact dependencies.
Every retry or revision creates a new, uniquely identified and versioned
artifact, retains predecessor and triggering-request references, and repeats
the required downstream validation stages. An earlier artifact remains
traceable even when a later version supersedes it.

No artifact may depend, directly or transitively, on itself. Synthesis and
validation output cannot be fed back as Source Evidence or as an input to a
specialist first pass. The control workflow may request new work, but it cannot
create a cyclic artifact dependency.

Personal context follows a separate path:

```text
Personal context
    -> presentation preferences

Personal context
    -> explicit typed application input
        -> approved application capability
```

There is no implicit arrow from personal context into Evidence, deterministic
policy behavior, or Agent conclusions. There is no arrow from Synthesis,
Synthesis Validation, or a Decision Brief into Trade Planning, Risk approval,
Execution, broker integration, or order activity.

Every cross-boundary artifact must identify, as applicable:

- its information class;
- producer role;
- source artifact identifiers and fingerprints;
- source and analysis times;
- capability and schema versions;
- policy provenance retained by the source;
- explicit assumptions;
- whether statements are quoted platform values or Agent-derived claims; and
- validation status and unresolved objections.

An Agent must not strip or rewrite source lineage. Summaries may reduce detail
for presentation, but they must retain references sufficient to trace every
material claim to its source artifact. A generated summary is a new derived
artifact, not a replacement for its sources.

Missing, invalid, stale, or mutually inconsistent inputs are preserved as
limitations or cause the affected workflow to fail closed. An Agent must not
repair them with invented data, hidden memory, an unapproved provider, or its
own calculation.

### Evidence boundary

Source Evidence that has passed every mandatory Evidence Validation scope is
the only admissible evidence input to independent specialist first-pass
analysis. The operating system distinguishes exactly these evidence classes:

1. **Authoritative platform Evidence.** A provenance-bearing, time-bounded
   artifact returned by an allow-listed deterministic platform capability
   through the ADR 0033 Agent Exposure Boundary. Platform values and retained
   lineage are quoted without semantic alteration.
2. **Externally sourced Evidence.** External information admitted only after a
   separately governed evidence-ingress boundary has canonicalized, validated,
   classified, and recorded it. Its external authority classification remains
   explicit; admission does not silently grant it platform authority.
3. **Observations that are not Evidence.** Model knowledge, retrieved prose,
   user assertions, conversational memory, peer claims, ungoverned external
   data, and generated analysis remain observations or task context. They MUST
   NOT be cited or promoted as Evidence.

Remembered holdings, holdings stated by a user, and preferences are personal
context, not Source Evidence. An authoritative portfolio snapshot is separate:
it is a provenance-bearing, typed, and versioned artifact returned by an
approved Portfolio Intelligence capability through the Agent Exposure
Boundary. Only such an authoritative portfolio snapshot may become Source
Evidence, and only after passing Evidence Validation. This ADR does not approve
that future capability or make a personal statement authoritative.

External information MUST NOT become authoritative Evidence without all of:

- a typed and versioned schema;
- canonicalization;
- validation;
- provenance;
- explicit freshness rules; and
- an explicit authority classification.

The separately governed evidence-ingress boundary must define those semantics
and its relationship to platform authority before use. This ADR does not
create, approve, or implement that ingress boundary. Until such a boundary is
approved, external information remains an observation that is not Evidence.

Evidence Agents may retrieve, select, organize, and cite evidence. They may not
calculate substitute platform values, repair rejected inputs, or treat model
knowledge and retrieved prose as equivalent to an authoritative platform
result.

The released `DailyTechnicalInterpretation`, `DailyTechnicalAssessment`, and
`DailyTechnicalStrategy` names retain their meanings from ADR 0032. When those
deterministic values are supplied through the bounded Agent projection, they
are authoritative platform outputs for this architecture. They must not be
confused with free-form Agent Interpretation merely because one domain type is
named `Interpretation`.

### Interpretation, Decision Support, and human Decision separation

#### Interpretation

Agent Interpretation is a derived hypothesis, comparison, explanation, or
scenario constructed from identified Evidence. It must distinguish source
facts from assumptions and inferences. It is not a domain result, a policy
output, a new fingerprinted platform artifact, or proof that a claim is true.

Specialist Intelligence Agents may explain uncertainty already present in
Evidence, compare separately valid results, and propose competing hypotheses.
They may not override deterministic results, silently combine incompatible
times or semantic families, invent financial policy, or claim an authoritative
cross-capability conclusion without a dedicated platform application contract.

Validation findings and Synthesis are also derived artifacts. They assess or
combine Interpretations but do not acquire Evidence authority.

#### Decision Support

Human Decision Support is a reviewed presentation of validated Synthesis,
material dissent, source limitations, and validation findings. Its artifact is
a **Decision Brief**, never a Decision Command. A Decision Support Layer or
Investment Committee Support Layer may prepare that brief, but neither name
grants decision authority.

#### Human Decision

A Decision is a human-owned judgment made after reviewing Evidence,
Interpretations, validation findings, and unresolved disagreement. Agent
ranking, voting, confidence, consensus, or recommendation is decision support,
not a Decision.

No Agent artifact may be relabeled as human approval. A human Decision must be
explicitly distinguishable from all generated artifacts and must retain the
Evidence and Interpretations considered where decision recording is later
approved. This ADR defines no decision-recording implementation.

### Agent responsibility boundaries

The architecture permits the following logical roles. A future implementation
may use more than one instance of a role, but combining roles must not collapse
their information or authority boundaries.

#### Coordinator

The Coordinator decomposes a human request, assigns bounded work, routes
artifacts, and ensures required stages are present. It owns workflow state only.
It does not own financial semantics, produce authoritative Evidence, resolve
review objections, or make a Decision.

#### Evidence Agent

An Evidence Agent selects an explicitly exposed capability, submits caller
intent through its approved boundary, and packages the returned projection as
Evidence. It does not access the generic application package, call domain
runners, normalize rejected inputs, or calculate missing outputs.

### Specialist Intelligence taxonomy

The initial Specialist Intelligence roles are listed below. Naming a role does
not approve its capability, data access, Agent contract, or implementation.
Daily Technical Intelligence is the only currently exposed semantic family;
every other family still requires the separate boundaries required by ADR
0033.

#### Technical Intelligence

- **Responsibility:** independently interpret admitted technical-market
  Evidence and the released descriptive Daily Technical outputs.
- **Allowed semantic scope:** technical state, trend, momentum, volatility,
  support or resistance context, and limitations already represented by
  approved technical capabilities.
- **Non-responsibilities:** no indicator recomputation, alternate technical
  policy, trade timing, order direction, position sizing, or execution.

#### Options Intelligence

- **Responsibility:** independently interpret admitted options-market Evidence
  and approved deterministic options analytics when such capabilities are
  separately established.
- **Allowed semantic scope:** descriptive volatility, skew, term structure,
  liquidity, positioning, and options-market conditions defined by those
  future contracts.
- **Non-responsibilities:** no raw-chain authority, contract selection, options
  strategy recommendation, position sizing, risk approval, or order creation.

#### Macro Intelligence

- **Responsibility:** independently interpret admitted macroeconomic Evidence.
- **Allowed semantic scope:** releases, revisions, regimes, policy context, and
  time-aligned macro conditions defined by approved future contracts.
- **Non-responsibilities:** no ungoverned data ingestion, authoritative macro
  policy creation, portfolio allocation, trade timing, or investment decision.

#### Fundamental Intelligence

- **Responsibility:** independently interpret admitted issuer, industry, and
  valuation Evidence when separately governed capabilities exist.
- **Allowed semantic scope:** reported fundamentals, revisions, business and
  industry context, valuation observations, and declared assumptions.
- **Non-responsibilities:** no source-of-record substitution, invented or
  normalized financial statements, price target, security selection, capital
  allocation, or trade recommendation.

#### Scenario Planning

- **Responsibility:** create conditional future states and the explicit
  assumptions under which those states apply.
- **Allowed semantic scope:** typed future-state branches, conditions, and
  consequences, with assumptions visibly separated from observations.
- **Non-responsibilities:** Scenario Planning does not perform current-state
  interpretation. It does not describe current exposure, predict a single
  outcome as fact, alter current Evidence, assign platform authority to
  assumptions, or recommend action.

#### Risk Intelligence

- **Responsibility:** apply approved scenarios to admitted current exposure and
  sensitivity observations.
- **Allowed semantic scope:** descriptive exposure, concentration, stress, and
  sensitivity observations under explicit scenario assumptions.
- **Non-responsibilities:** Risk Intelligence does not create or silently alter
  scenario assumptions and does not perform Risk approval. It does not set
  limits, accept risk, size positions, authorize intent, veto or approve a
  trade, or control execution.

An approved scenario is explicit, typed scenario task context adopted before a
Risk Intelligence assignment. If it originated from Scenario Planning, a human
must explicitly adopt the exact assumptions as a new versioned task input. Risk
Intelligence receives those assumptions and their origin reference, not the
peer's reasoning, validation findings, or conclusions. The scenario remains an
assumption rather than Source Evidence. Its adoption is not Risk approval and
does not grant Scenario Planning authority over current-state interpretation.
Risk Intelligence must preserve references to both the approved scenario and
the Source Evidence containing the exposure or sensitivity observations to
which it is applied.

Each interpretation-producing specialist labels assumptions and inference,
stays within its allowed semantic scope, and follows the first-pass
independence rules. Cross-family interpretation requires an explicit assignment
and remains derived; it cannot create authoritative combined semantics.

### Validation, synthesis, context, and presentation roles

These roles operate around or after Specialist Intelligence. They are not
members of the Specialist Intelligence taxonomy and do not gain a specialist's
semantic authority.

#### Validation Agent

A Validation Agent challenges a completed Evidence, Interpretation, or
Synthesis artifact against one declared review concern. It produces findings
and objections. It does not edit the reviewed artifact, manufacture replacement
Evidence, or silently turn a failed review into a passing result.

#### Synthesis Agent

A Synthesis Agent compares accepted artifacts, preserves material disagreement,
and creates an immutable Synthesis artifact for validation. It does not produce
the final Decision Brief, average away conflicts, promote majority agreement to
truth, or create a new authoritative financial result.

#### Decision Support Layer

The Decision Support Layer is a coordination and presentation layer after
validated Synthesis. It presents validated Synthesis, material dissent,
provenance, freshness, uncertainty, and limitations to the human as a Decision
Brief. It may compare and communicate admitted artifacts, but it performs no
Specialist Intelligence and creates no new analytical conclusion.

Decision Support is not authoritative decision making. It does not issue a
Decision Command, choose an investment, approve Risk, create trading intent,
or authorize execution. The human remains the final decision authority.

#### Personal Context Custodian

The Personal Context Custodian, if one is later introduced, supplies only the
minimum authorized context to the presentation path or maps a material user
constraint to an explicit typed application input. It cannot expose personal
context to other Agents by default and owns no financial interpretation.

No role may delegate itself broader authority. A role change requires a new,
explicit assignment and a new output artifact; it cannot occur implicitly in a
single response.

### Deterministic engine and LLM reasoning boundary

The deterministic platform remains authoritative for canonicalization,
validation, financial calculations, policy execution, orchestration,
correspondence, provenance, and versioned application results. Existing access
continues through the capability-specific Agent Exposure Boundary.

LLM reasoning, if separately approved in the future, may perform request
interpretation, evidence selection, hypothesis generation, critique,
comparison, explanation, and presentation. It is nondeterministic derived
reasoning and must remain visibly separate from platform output.

An LLM must not:

- implement or replace a financial domain policy;
- recompute indicators or authoritative financial values;
- validate, canonicalize, repair, or override platform inputs or outputs;
- mint or alter platform fingerprints, provenance, or policy identities;
- select an unapproved policy or application profile;
- turn prompt instructions, model memory, retrieval, or prose into platform
  Evidence; or
- convert descriptive intelligence into trading intent, risk approval, or
  execution authority.

The deterministic platform must not depend on LLM output, Agent prompts,
Agent memory, review votes, or synthesized prose. A future platform capability
may accept a material assumption only through an explicit, typed, versioned
application contract that defines its semantics and validation. Such a
contract requires a separate decision; this ADR creates none.

Reproducibility applies differently at the boundary: deterministic results are
identified by their released schemas, inputs, policies, and provenance, while
Agent reasoning is retained as a derived artifact tied to exact source
references and its declared reasoning configuration. Capturing reasoning
metadata does not make LLM output deterministic or authoritative.

### Validation committee and adversarial review layer

Evidence, Interpretations, and Synthesis pass through logically separate
validation stages in the canonical DAG. Evidence Validation assesses evidence
quality and authority. Interpretation Validation assesses derived analysis.
Synthesis Validation assesses combined decision support. The validation
committee supplies independent review responsibilities to all three stages. It
is an adversarial review layer, not a source of market truth and not a voting
body that can manufacture certainty.

#### Mandatory minimum validation scopes

Every artifact of the applicable class MUST pass all of its minimum scopes.
Runtime policy may select reviewers, assign one or more reviewers to each
scope, add stricter scopes, and define retry or revision mechanics. It MUST NOT
remove, waive, downgrade, or treat any mandatory scope as optional.

Evidence Validation MUST cover:

- provenance and lineage integrity, including producer, source references, and
  retained fingerprints;
- authority, admissibility, and information classification, including rejection
  of personal context and derived artifacts presented as Evidence;
- schema and contract identity, version, required fields, and integrity;
- source time, freshness, identity, and declared scope alignment; and
- material quality limitations, missing data, and conflicting source records.

Interpretation Validation MUST cover:

- claim-to-Evidence correspondence through exact Evidence versions that passed
  Evidence Validation;
- separation of quoted facts, assumptions, and inferences, including checks for
  unsupported claims and contradictory Evidence;
- time, identity, and scope alignment across every cited artifact;
- semantic-family, deterministic-policy, and specialist-responsibility boundary
  compliance; and
- authority and safety boundaries, including no implied platform authority,
  Risk approval, trading action, or human approval.

Synthesis Validation MUST cover:

- traceability of every material claim to accepted Interpretation versions and,
  through them, to validated Source Evidence;
- preservation and accurate classification of dissent, assumptions,
  limitations, exclusions, and unresolved objections;
- time, identity, scope, and semantic compatibility across combined artifacts;
- absence of unsupported cross-artifact conclusions or escalation of derived
  output into Evidence or deterministic authority; and
- decision-support and safety boundaries, including no Decision Command, Risk
  approval, trading intent, execution authority, or implied human approval.

Each reviewer receives the immutable artifact under review and the minimum
cited sources and peer artifacts needed for its declared concern. Reviewers do
not share mutable notes. Findings are append-only artifacts with severity,
rationale, source references, review scope, and exactly one disposition:

- **passed** means the reviewer found no material objection within its declared
  scope. It is an admission result for that scope, not proof of truth or general
  approval outside that scope;
- **challenged** means the reviewer found a material defect, unsupported claim,
  unresolved contradiction, provenance failure, freshness failure, semantic
  boundary violation, or authority violation; and
- **unable to validate** means the reviewer lacked sufficient admissible
  material or review capability to reach a pass. It is not equivalent to
  passed.

Only an immutable Source Evidence artifact whose exact version has passed every
required Evidence Validation scope may enter independent specialist analysis.
Evidence with any challenged or unable-to-validate required disposition MUST
NOT be admitted. Evidence Validation records quality and authority findings; it
does not repair Evidence, create missing authority, or rewrite its
classification.

Only an immutable Specialist Interpretation whose exact version is linked to
admissible Source Evidence and has passed every required Interpretation
Validation scope may enter Synthesis as accepted analytical support. An
Interpretation with any challenged or unable-to-validate required disposition
MUST NOT support a synthesized conclusion.

A challenged Interpretation may be retained and referenced in Synthesis only
as explicitly excluded dissent, together with its validation findings, when
doing so helps the human understand a material disagreement. It remains a
challenged Interpretation and MUST NOT be described as accepted support or as
"dissenting Evidence." An unable-to-validate artifact may be disclosed only as
a limitation. A provenance or authority failure cannot be cured by preserving
the artifact as dissent.

Synthesis Validation applies the same dispositions to the exact immutable
Synthesis version. Human Decision Support may be presented as a **reviewed
Decision Brief** only when all of these admission conditions hold:

- every cited Source Evidence artifact passed every required Evidence
  Validation scope, is within its declared freshness rules, and retains its
  provenance and authority classification;
- every material synthesized claim traces to accepted Specialist
  Interpretations and, through them, to Source Evidence;
- every required Interpretation Validation scope for accepted support passed;
- all excluded dissent, assumptions, limitations, and unresolved
  non-admission findings are visible and cannot be mistaken for accepted
  support;
- every required Synthesis Validation scope passed for the presented Synthesis
  version; and
- the Decision Brief is labeled as decision support, contains no Decision
  Command, and preserves its scope and review status.

If any condition fails, the workflow fails closed for reviewed decision
support. It may present a validation failure or limitation report, but it MUST
NOT label the output a reviewed Decision Brief. An objection confined to a
properly excluded dissent artifact does not invalidate otherwise accepted
support, provided the objection and exclusion remain visible.

The committee cannot modify Evidence, rewrite an Interpretation or Synthesis,
suppress a dissenting review, or approve a Decision. A Coordinator or
Synthesis Agent may request a new revision from the original role, but the
revision is a new versioned artifact, requires new validation, and leaves the
original artifact and finding traceable.

Unresolved material objections must be shown to the human. Consensus, quorum,
or majority vote cannot erase a provenance failure, an authority violation, or
a material contradiction. Exact committee composition, reviewer-to-scope
assignment, additional review scopes, and retry mechanics are runtime policy
and remain deferred. Runtime policy cannot remove a mandatory check or weaken
the admission semantics defined here.

### Personal context isolation

Personal context includes conversation history, identity, remembered holdings,
holdings stated by the user, preferences, objectives, risk tolerance, and other
user statements. It is not market Evidence and is not shared multi-Agent
memory.

An authoritative portfolio snapshot is not remembered personal context. It is
a provenance-bearing, typed, and versioned result returned by an approved
Portfolio Intelligence capability. Only that result may be considered for
Source Evidence, subject to Evidence Validation and the ADR 0033 exposure
boundary. User statements and remembered holdings never become authoritative
portfolio snapshots through repetition, summarization, or Agent inference.

Personal context is isolated by default:

- Evidence and Validation Agents receive none unless an explicit contract
  requires a specific field;
- Specialist Intelligence Agents receive none merely to make analysis feel
  personalized;
- the Decision Support Layer receives only presentation preferences that cannot
  alter meaning;
- no personal value is copied into prompts, logs, or artifacts outside its
  declared purpose; and
- one user's context, artifacts, and decisions cannot be visible to another
  user or workflow.

Presentation preferences may affect language, ordering, units, or level of
detail. They may not alter platform policies, source selection rules,
validation, financial defaults, Evidence, or review outcomes.

A financially material constraint can influence platform semantics only when
the user explicitly supplies it to an approved, typed, versioned application
input as required by ADR 0033. Until then it remains non-authoritative personal
context. Remembered results retain their original time and provenance and do
not become current by reuse.

### Human-owned decision authority

Decision authority remains exclusively human-owned. The operating system may
surface Evidence, competing Interpretations, scenarios, limitations, and
review findings. It may ask the human to resolve ambiguity. It may not decide
what the human should own, buy, sell, hold, size, rebalance, approve, submit, or
execute.

Human authority is not inferred from silence, continued conversation, a click
unrelated to explicit approval, an Agent's confidence, or previous behavior.
No Agent, Coordinator, Synthesis, Decision Support Layer, Investment Committee
Support Layer, or validation committee can grant itself delegated financial
authority under this ADR.

This architecture creates no Decision Command, Order Intent, Trade Plan, risk
decision, execution instruction, broker message, or automatic downstream
action. Any future decision or action capability requires its own application
contract, authorization model, audit rules, threat review, and ADR outside
this Market Intelligence Operating System decision.

### Future capability taxonomy

Every future operating-system capability must be classified before exposure
along independent axes:

1. **Semantic family**: the bounded market subject and ontology. Daily
   Technical Intelligence is the only currently exposed family. Macro,
   Portfolio, Options, and other names remain candidate families until each has
   separately approved domain, application, exposure, and projection contracts.
2. **Information class**: Source Evidence, Evidence Validation, Specialist
   Interpretation, Interpretation Validation, Synthesis, Synthesis Validation,
   Decision Brief, personal context, or Human Decision record.
3. **Responsibility role**: coordination, evidence access, a declared
   Specialist Intelligence role, validation, synthesis, context custody,
   decision-support presentation, or human interaction.
4. **Authority level**: authoritative deterministic platform result, explicitly
   classified external Evidence, derived decision support, or explicit human
   decision. Agent output cannot occupy the human-decision level.
5. **Effect class**: read-only intelligence, state recording, or external
   side effect. This architecture permits only read-only intelligence and
   derived presentation; it approves neither state recording nor side effects.
6. **Contract identity**: explicit capability ID, input and output schema
   versions, allowed source types, provenance requirements, and exposure status.

A capability belongs to one declared semantic family and has one primary
responsibility. "General analyst", "generic executor", and "all market
intelligence" are not valid capability identities. Cross-capability synthesis
remains derived presentation unless a separately approved deterministic
application capability owns and validates the combined semantics.

Taxonomy membership is descriptive, not authorization. A candidate family is
not available merely because it is named here or in ADR 0033. In particular,
this decision does not design or expose Options Intelligence.

### Dependency direction

Artifact dependencies are exclusively those in the canonical artifact DAG.
Access dependencies point inward toward deterministic authority:

```text
Evidence Agent
    -> Agent Exposure Boundary
        -> allow-listed application service
            -> domain composition and policies
```

Externally sourced Evidence, if separately approved in the future, depends on
its separately governed evidence-ingress boundary and not on the Agent Exposure
Boundary. This is an authority-classified source dependency, not an alternate
path to application services or domain policies. This ADR creates neither that
ingress nor an Agent path around ADR 0033.

Control dependencies may request new work but do not become artifact
dependencies. Results return as immutable artifacts; a return value, retry, or
revision request does not reverse ownership or semantic authority.

The permitted dependencies are:

- the Coordinator depends on role contracts and artifact metadata;
- specialized Agents depend on their declared input artifact contracts;
- Evidence Agents depend on capability-specific Agent exposure facades;
- Agent exposure depends on public application contracts and services;
- application services depend on released domain composition boundaries; and
- domain packages remain independent of application, exposure, Agent, and
  operating-system layers.

### Prohibited dependencies

The following dependencies and access paths are prohibited:

- domain or application code depending on Agents, LLMs, prompts, personal
  context, committee results, or synthesis;
- `market-platform` depending on the Market Intelligence Operating System;
- Agents calling domain runners, policies, factories, providers, or private
  helpers directly;
- Agents using the generic application surface, reflection, or automatic
  service discovery instead of an explicit allow-listed exposure facade;
- exposure code owning financial semantics, policy selection, domain
  orchestration, input repair, or result reinterpretation;
- deterministic platform behavior depending on Agent consensus, confidence,
  narrative, memory, or review votes;
- peer Agents reading or mutating private state or incomplete outputs;
- Evidence collection depending on personal memory or another Agent's
  unsupported claim;
- validation reviewers mutating reviewed artifacts or suppressing dissent;
- synthesis replacing provenance-bearing sources with generated prose;
- implicit conversion between Daily Technical Intelligence, the parallel
  `research-workflow-v1` ontology, or the legacy Strategy family;
- automatic cross-capability semantic composition;
- any dependency from the intelligence operating system to Trade Planning,
  Risk approval, Execution, broker integration, order lifecycle, or TradingView
  ingress; and
- any path that treats intelligence output as authorization for an external
  side effect.

Co-deployment, shared infrastructure, or common libraries must not create a
hidden semantic dependency that violates these rules.

## Consequences

- Multi-Agent work can add analytical diversity without adding a second source
  of deterministic financial semantics.
- Explicit artifacts make influence, lineage, disagreement, and responsibility
  reviewable across Agent boundaries.
- Evidence, derived reasoning, validation, and human Decisions remain visibly
  distinct.
- Independent adversarial review reduces correlated agreement and preserves
  unresolved objections, but it cannot guarantee correctness.
- Personalization is constrained to presentation or explicit application
  inputs and cannot silently change analysis.
- The architecture can accommodate future capability families without a
  generic executor, but each family requires separate approval and contracts.
- Human review remains mandatory for Decisions; the architecture provides no
  autonomous action path.
- A future implementation will need separate decisions for runtime isolation,
  artifact storage, security, model governance, transport, and operations.

## Rejected alternatives

### Shared conversational memory for all Agents

Rejected because it creates hidden inputs, cross-contaminates independent
analysis, leaks personal context, and makes claim lineage difficult to audit.

### One general-purpose market Agent

Rejected because it collapses evidence access, interpretation, validation,
synthesis, and authority into an unreviewable catch-all boundary.

### Majority vote as validation

Rejected because correlated Agents can agree on an unsupported claim and a
vote cannot repair invalid provenance, stale Evidence, or an authority breach.

### LLM reasoning as a financial policy

Rejected because generated reasoning does not provide the deterministic,
versioned, provenance-bearing semantics owned by platform domain policies.

### Personalized analysis through hidden memory

Rejected because material personal constraints must be explicit typed inputs,
while presentation preferences must not alter financial meaning.

### Automatic transition from intelligence to action

Rejected because it would collapse human decision, Trade Planning, Risk,
Execution, and broker authority into a descriptive intelligence system.

## Deferred scope and non-goals

This decision does not implement or approve:

- an Agent runtime, scheduler, supervisor, or orchestration engine;
- an LLM, model provider, prompt framework, retrieval system, or model memory;
- an API, MCP integration, CLI, UI, serialization format, or other transport;
- persistence, an artifact store, an audit database, or a personal-context
  store;
- authentication, authorization, tenancy, encryption, retention, rate limits,
  retries, quorum thresholds, or operational deployment;
- a new Agent capability or change to the v0.76 capability allow-list;
- Options Intelligence or any Options domain, application, exposure, or Agent
  contract;
- Trade Planning, Risk, Execution, broker integration, order submission,
  autonomous trading, or any other trading integration;
- portfolio allocation, rebalancing, or investment recommendation;
- TradingView visualization or webhook ingress;
- changes to Daily Technical domain semantics, ADR 0032 application contracts,
  or ADR 0033 Agent exposure contracts; or
- source-code changes of any kind.

Any implementation proposal must receive separate scope approval and preserve
the independence, information-flow, authority, and dependency rules defined
here.
