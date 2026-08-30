# ADR 0036: Personal Intelligence Boundary Architecture

## Status

Accepted for v0.77.0 Evidence Foundation.

This decision defines the boundary between Market Intelligence system
knowledge and user-specific Personal Intelligence. It approves no storage,
memory, portfolio connector, Agent runtime, or other implementation.

## Context

ADR 0032 establishes the application boundary and preserves domain semantic
authority. ADR 0033 makes an Agent an external consumer of explicitly exposed
application capabilities and prevents Agent memory from becoming implicit
platform input. ADR 0034 separates personal context from the canonical Market
Intelligence artifact flow and leaves final decision authority with the human.
ADR 0035 defines Evidence and expressly excludes user statements, preferences,
holdings, and memory from that information class.

A private personal investment intelligence system must relate market
intelligence to a user's objectives, risk context, portfolio, and prior
decisions. Without a further boundary, that context could be mistaken for
market fact, leak into Evidence Validation or deterministic policy behavior,
become hidden shared Agent memory, or make generic infrastructure inseparable
from private information.

This decision defines Personal Intelligence as a separate information and
authority boundary. It permits authorized personal context and a separately
labeled Personalized Explanation to be displayed alongside a completed
reviewed Decision Brief during human decision review while preserving the
possibility that generic architecture and infrastructure may be published
independently in the future.

## Decision

### Personal Intelligence definition

Personal Intelligence is user-specific context that helps the human assess how
otherwise governed market intelligence relates to the user's situation after a
reviewed Decision Brief is complete. It may inform presentation, comparison,
and the human's assessment of personal relevance during decision review, but it
does not redefine external reality.

Personal Intelligence is not:

- Evidence;
- market truth;
- domain policy;
- financial recommendation authority; or
- Agent-owned memory truth.

An Agent may receive authorized personal context for a declared purpose, but
neither the Agent nor its memory owns the truth of that context. Remembering,
repeating, summarizing, or inferring a personal value does not increase its
authority.

The governing principle is:

> Personal context influences decisions but cannot alter facts.

Personalization may affect only presentation ordering, user-specific
explanation through a separately labeled Personalized Explanation, and the
display of explicitly authorized user-specific context during human decision
review. It must not alter or influence source selection, Evidence admission,
validation scope or disposition, uncertainty, objections, conclusions,
preservation of dissent, or mandatory Decision Brief content. It cannot change
the content, provenance, validation status, policy identity, effective time, or
authority of any governed artifact.

### Information classification

Personal Intelligence contains four separate classes. Classification states
what the information describes; it does not prescribe a storage model or grant
authority outside this boundary.

#### A. Personal Objectives

Personal Objectives describe what the user is trying to accomplish, including:

- investment goals;
- time horizon; and
- personal constraints.

Objectives express user intent. They do not establish market conditions,
select or redefine a domain policy, or authorize a recommendation or action.

#### B. Risk Profile Context

Risk Profile Context describes the user's stated or otherwise explicitly
authorized circumstances and preferences, including:

- risk tolerance;
- liquidity needs; and
- drawdown preferences.

This context may be displayed alongside the completed reviewed Decision Brief
to help the human assess the personal relevance of its scenarios and
limitations. It cannot influence which scenarios or limitations the brief
contains. It is not a platform risk decision, suitability finding, risk
approval, or permission to size or execute a position.

#### C. Portfolio State

Portfolio State describes the user's situation as **Personal Portfolio
Context**, including:

- holdings;
- cost basis;
- exposure; and
- allocation.

Holdings supplied by the user are Personal Intelligence. An authorized copy of
a broker, custodian, account, or other portfolio snapshot is also Personal
Portfolio Context. It may retain source references, lineage, account identity,
and applicable source times, but retaining that provenance does not grant the
copy Evidence authority.

A **Portfolio Evidence Artifact** is a separate future artifact: an exact,
provenance-bearing, typed, and versioned broker, custodian, or account snapshot
governed as Evidence under ADR 0035. Only that separately governed Evidence
Artifact receives ADR 0035's External-Origin Authority and classification as
External-Origin Evidence. Its validation or admission does not grant Evidence
authority to Personal Portfolio Context, user statements, remembered holdings,
or personal projections of the snapshot. The personal-context artifact and the
Evidence Artifact remain separately identified, classified, and referenced;
one artifact is not silently assigned both roles.

#### D. Decision History

Decision History describes the user's prior decision process, including:

- previous decisions;
- recorded rationale;
- observed outcomes; and
- personal lessons.

Decision History may help the user compare current circumstances with prior
choices. It does not turn a prior choice, rationale, outcome summary, or lesson
into Evidence, policy, recommendation authority, or precedent that binds a new
decision. Any market fact used to evaluate a historical outcome must remain a
separately governed and referenced input.

### Personal context authority

Personal Intelligence has contextual authority only: it may represent the
user's authorized context for the declared decision-support purpose. It has no
Evidence, market, domain-policy, validation, recommendation, or execution
authority.

Personal Intelligence cannot:

- create or modify Evidence;
- admit, reject, repair, reclassify, or override Evidence Validation;
- influence source selection, Evidence admission, validation scope, validation
  disposition, or review outcomes;
- change domain policies, application profiles, policy defaults, or domain
  results;
- create a Specialist Interpretation or modify an existing Interpretation;
- create or modify Synthesis;
- create or modify a market conclusion;
- bypass application, Agent exposure, validation, or capability boundaries;
- supply hidden inputs to deterministic processing or independent Specialist
  Intelligence; or
- turn descriptive intelligence into a financial instruction or authorization.

Human decision-review presentation may consume explicitly authorized Personal
Intelligence through a declared personal-context boundary after the reviewed
Decision Brief is complete. If a personal constraint would appropriately and
materially affect platform semantics, it may do so only through a separately
approved, explicit, typed, and versioned application input as required by ADR
0033 and ADR 0034. The applicable application and domain contracts must own the
input's validation and meaning. That path is not Decision Support
personalization. This ADR defines no such input and creates no path directly to
domain policies or runners.

### Memory boundary

Memory is a contextual-assistance mechanism, not an authority source. Any
future memory boundary must distinguish at least:

- **stable personal facts**, such as an explicitly supplied long-term objective
  or constraint;
- **preferences**, such as presentation, comparison, or communication
  preferences; and
- **historical interaction context**, such as earlier questions, explanations,
  stated holdings, or decision discussions.

These classes may have different expected stability, but none becomes more
authoritative merely because it is retained. Remembered context can be stale,
incomplete, incorrectly inferred, or no longer applicable. It must remain
identifiable as memory-derived context when used.

Every remembered item must retain a memory-recorded timestamp and, where
applicable, its source time, effective or as-of time, and last-confirmed
timestamp. These timestamps identify the context available to the review; they
do not validate it or increase its authority.

A future memory contract must define confirmation requirements and a
confirmation interval appropriate to each memory class and declared use.
Stable personal facts and preferences must be reconfirmed before materially
decision-relevant use when their current applicability matters. Historical
interaction context remains historical and cannot be treated as current merely
because it was recently retrieved.

Memory is stale or unconfirmed for a use when its required confirmation
interval has elapsed, a required source or effective time is absent or
incompatible with the review, it has been superseded, or its current
applicability cannot be established. Such context must be visibly labeled as
memory-derived and stale or unconfirmed. Materially decision-relevant stale or
unconfirmed context fails closed: it must not personalize the current review,
be presented as current, or be used as an implicit assumption. The system must
obtain a fresh authorized input or proceed without that personalization while
disclosing the limitation. Stale context may remain visible as labeled
historical context for reflection.

Memory must not become:

- authoritative market input;
- portfolio truth;
- Evidence Validation input;
- policy configuration; or
- implicit approval of a recommendation, order, or other action.

A remembered market result retains its original provenance, version, and
applicable time. Recalling it neither refreshes it nor makes it current. A
remembered holding remains historical interaction context until an authorized
current portfolio-state input establishes otherwise; even then, the resulting
personal state is not Evidence unless separately governed under ADR 0035.

### Portfolio boundary

Personal Portfolio Context answers questions about the user's situation for an
authorized personal purpose. A future Portfolio Evidence Artifact represents a
governed external source observation or assertion. The two may be displayed
together during human decision review but must not be merged into one artifact
or authority class.

A personal portfolio copy retains contextual authority only. Authorization,
transport, normalization, copying, provenance retention, or use in a personal
portfolio view does not give it Evidence authority. Only an exact Portfolio
Evidence Artifact governed under ADR 0035 receives External-Origin Authority;
transport or admission cannot promote it to Platform-Origin Authority. A
personal calculation over portfolio data, such as allocation or exposure, is
derived Personal Intelligence unless a separately approved contract classifies
another result differently.

Personal portfolio context must not be fed back as market Evidence, used to
alter market observations, or treated as proof that an external condition
exists. Conversely, market Evidence does not establish what the user owns or
authorize a portfolio change.

### Decision support integration

ADR 0034's complete canonical flow remains mandatory through validated
Synthesis and production of a reviewed Decision Brief. In this ADR, a
**reviewed Decision Brief** is ADR 0034's Decision Brief after all admission
conditions and mandatory content requirements have been satisfied. Personal
Intelligence does not enter Evidence selection, Evidence Validation,
Specialist Interpretation, Interpretation Validation, Synthesis, Synthesis
Validation, or Decision Brief production.

The only allowed conceptual integration is after that flow is complete:

```text
Reviewed Decision Brief -----+
                              +-> Human decision review -> Human Decision
Authorized Personal Context -+
```

Authorized Personal Context may help the human understand how the completed
validated intelligence relates to Personal Objectives, Risk Profile Context,
Personal Portfolio Context, and Decision History. It may affect presentation
ordering, support a Personalized Explanation, and display user-specific context
alongside the immutable reviewed Decision Brief.

A **Personalized Explanation** is a separately labeled presentation artifact
derived only from an immutable reviewed Decision Brief and explicitly
authorized Personal Context. It may explain the implications of the completed
brief for the user's situation, reorder presentation, and provide
user-specific context. It is not part of, an amendment to, or a replacement for
the reviewed Decision Brief.

A Personalized Explanation must not:

- filter, modify, replace, or append content to the reviewed Decision Brief;
- remove or suppress uncertainty, dissent, limitations, unresolved objections,
  or any other mandatory Decision Brief content;
- introduce a market conclusion;
- create a recommendation;
- acquire or claim Evidence authority; or
- acquire or claim execution authority.

The personalized review view must preserve the identity and authority of its
inputs, visibly distinguish the reviewed Decision Brief, Personalized
Explanation, and Personal Intelligence, and retain access to all mandatory
Decision Brief content. Joining these artifacts for human review does not
reclassify an input, transfer authority, or create an alternate path around ADR
0034 validation or Synthesis.

The human remains the final decision authority. This architecture creates no:

- autonomous trading;
- execution path;
- order creation; or
- broker authority.

It also creates no recommendation, Trade Plan, risk approval, portfolio action,
or inferred human consent.

### Privacy and publication boundary

The private Personal Intelligence layer includes:

- personal context;
- portfolio state;
- decision history; and
- personal decision-support preferences, reflection frameworks, or
  configurations.

Personal decision-support preferences, reflection frameworks, and
configurations describe private user-specific presentation or reflection
context. They are not deterministic domain Strategy policies, executable
financial rules, recommendations, or instructions. They cannot replace or
modify domain policies and carry no recommendation or execution authority.

The following may be published separately after an applicable publication
decision and review:

- generic architecture;
- reusable framework components; and
- non-personal tooling.

Dependency direction runs from the private layer toward generic
infrastructure. Generic infrastructure must not depend on personal records,
identifiers, portfolio values, decision history, private personal
decision-support configurations, or defaults inferred from them. Generic
examples, fixtures, documentation, logs, and release artifacts must not embed
private information. Shared deployment or common libraries do not collapse
this boundary.

This separation preserves the ability to operate a private personal investment
intelligence system while publishing generic infrastructure independently. It
does not itself authorize publication or define a security, redaction,
licensing, or release process.

### Relationship to previous ADRs

#### ADR 0032: domain semantic authority

ADR 0032 remains authoritative for application orchestration and the semantic
authority of the Daily Technical Strategy domain chain. Personal Intelligence
cannot modify its verified input lineage, policy behavior, correspondence, or
results, and it cannot call domain stages around the application boundary.

#### ADR 0033: Agent exposure boundary

ADR 0033 remains authoritative for Agent access and memory. Exposure of an
application capability does not expose Personal Intelligence. Personal context
may cross an Agent boundary only through an explicit, purpose-limited contract
and authorization; it is not automatically available to an Agent, capability,
prompt, or tool.

#### ADR 0034: operating-system roles and flow

ADR 0034 remains authoritative for the canonical artifact DAG, role
independence, validation, synthesis, Decision Support, and human decision
authority. Personal Intelligence joins only the human decision-review path
after a reviewed Decision Brief is complete. It is a separate context
boundary, not an additional Intelligence Agent, Specialist, shared multi-Agent
memory, or new stage in the market-intelligence DAG.

#### ADR 0035: Evidence boundary

ADR 0035 remains authoritative for Evidence definition, authority,
validation, admission, freshness, and lifecycle. Personal Intelligence is not
Evidence. Only a separately identified Evidence Artifact may enter that lane;
provenance or repetition cannot promote personal context into it.

### Invariants

- Personal context is not Evidence.
- Memory is not authority.
- Portfolio state is not market truth.
- Decision History is neither Evidence nor precedent.
- Personalization changes presentation and displays authorized context; it
  may create a separately labeled Personalized Explanation but changes neither
  governed intelligence nor reality.

## Consequences

- Market facts, deterministic domain semantics, validated intelligence, and
  user-specific context retain distinct authority and lineage.
- Human decision review can display authorized Personal Intelligence alongside
  a reviewed Decision Brief without changing Evidence, validation, Synthesis,
  Decision Brief content, domain results, or human decision authority.
- Portfolio data can describe the user's situation without becoming an
  alternate source of market truth.
- Memory can improve continuity while remaining non-authoritative and visibly
  separate from current portfolio state and governed inputs.
- Private personal information and personal decision-support configurations can
  remain outside generic components, preserving a future publication boundary.
- Future implementations will need explicit contracts for context access,
  authorization, retention, security, and any materially semantic personal
  input.

## Non-goals

This decision does not design, approve, or implement:

- memory implementation or retrieval;
- storage, persistence, a database, cache, or index;
- encryption or key management;
- portfolio, broker, custodian, account, or market-data connectors;
- authentication or authorization mechanisms;
- multi-user identity, tenancy, or isolation design;
- an Agent, LLM, orchestration, or other runtime;
- deployment, hosting, operations, or publication mechanics;
- portfolio allocation, rebalancing, recommendation, Trade Planning, Risk,
  Execution, order lifecycle, or broker control; or
- source-code changes of any kind.

Any future implementation requires separately approved contracts and must
preserve the information classification, authority, privacy, application, and
human-decision boundaries defined here.
