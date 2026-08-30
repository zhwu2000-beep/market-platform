# ADR 0035: Evidence Foundation Architecture

## Status

Accepted for v0.77.0 Evidence Foundation.

This decision defines the foundational Evidence architecture for the Market
Intelligence Operating System. It does not approve or implement acquisition,
storage, ingestion, transport, an API, an Agent runtime, or connectors.

## Context

ADR 0032 establishes the transport-neutral application boundary for the
deterministic Daily Technical Strategy pipeline. Verified research enters that
boundary through an explicit application contract, and application
orchestration preserves the authority and lineage of released domain values.

ADR 0033 establishes that Agents are external consumers of explicitly
allow-listed platform capabilities. Agent memory, user preferences, generated
prose, and model reasoning are not authoritative platform inputs or results.

ADR 0034 establishes the canonical Market Intelligence Operating System
artifact flow:

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

That decision separates Source Evidence from derived intelligence and requires
Evidence Validation before independent Specialist Intelligence begins. A
foundational Evidence contract is needed so future capabilities preserve that
separation without prematurely choosing storage, ingestion, API, connector, or
runtime designs.

## Decision

### Evidence definition

Evidence is a provenance-bearing artifact representing a source observation,
measurement, or source assertion.

The represented source observation, measurement, or assertion is distinct from
the Evidence artifact that records it. The artifact identifies and preserves
the source material and its provenance; it does not make the represented claim
true. Evidence is not truth.

The information classes remain separate:

- a **Source Observation** is the observation, measurement, or assertion made
  by a source. It exists conceptually before and independently of the platform
  artifact that represents it;
- an **Evidence Artifact** is the identified, versioned, provenance-bearing
  representation of one or more Source Observations;
- **Validated Evidence** is a contextual status for an exact Evidence Artifact
  version that has `Passed` every mandatory Evidence Validation scope under an
  identified ruleset. It is not a new artifact or authority class, and the
  status is always qualified by scope and evaluation time;
- an **Authoritative Platform Result** is a versioned result whose semantics
  are owned by an approved deterministic platform capability. An
  **Authoritative Domain Result** is the domain-semantic form of that class;
- a **derived intelligence artifact** explains, challenges, or combines
  Evidence or Authoritative Platform Results without acquiring their
  authority;
- a **recommendation** proposes a course of action; and
- **task or personal context** supplies user statements, preferences,
  objectives, assumptions, constraints, memory, or other task-specific input.

Validation establishes identity, provenance, contract compliance, and
eligibility for admission for an exact Evidence Artifact version and declared
scope. It does not establish truth, eliminate uncertainty, authorize a
decision, or itself admit the artifact.

ADR 0032's `DailyTechnicalInterpretation`, `DailyTechnicalAssessment`, and
`DailyTechnicalStrategy` are Authoritative Domain Results. They are derived by
deterministic domain policies, but they are not Evidence. Deterministic
computation, platform production, complete lineage, validation, or exposure
through an approved capability never turns a computed result into Evidence.
Specialist Interpretations, validation findings, confidence scores, rankings,
Synthesis, Decision Briefs, recommendations, and generated summaries are
derived intelligence or presentation artifacts. Their provenance may refer to
Evidence or Authoritative Domain Results, but that lineage does not reclassify
them. Task and personal context are not Evidence, even when they are explicit,
typed, retained, or repeated.

### Terminology alignment with ADR 0034

ADR 0034 remains unchanged, but its terminology is read through these more
precise distinctions:

- **Authoritative platform Evidence**, when ADR 0034 is referring to a
  deterministic platform output such as an ADR 0032 Interpretation,
  Assessment, or Strategy, means **Authoritative Platform Result**, not
  Evidence;
- **Externally sourced Evidence** means **External-Origin Evidence** under this
  ADR; and
- a Source Observation originating in a platform-owned system of record and
  represented by an Evidence Artifact is **Platform-Origin Evidence**. Platform
  origin applies only to the observation and does not make a deterministic
  calculation Evidence.

This mapping resolves terminology; it does not change ADR 0034's dependency
direction, Agent boundaries, validation stages, or human decision authority.

### Evidence authority classes

Every Evidence Artifact has exactly one Evidence authority classification:

1. **Platform-Origin Authority.** The represented observation originates in a
   platform-owned system of record. The artifact preserves the identity and
   lineage that establish that origin.
2. **External-Origin Authority.** The represented observation, measurement, or
   assertion originates outside a platform-owned system of record, including
   data supplied by providers, publications, brokers, custodians, accounts, or
   other external systems. The artifact preserves that external origin after
   admission.

An Evidence Artifact with Platform-Origin Authority is Platform-Origin
Evidence. An Evidence Artifact with External-Origin Authority is
External-Origin Evidence. Neither phrase asserts that the represented
observation is true.

Evidence authority describes origin. It is separate from information
classification, access authorization, validation disposition, and admissible
use. Transport through an approved capability, canonicalization, identity
resolution, schema validation, deterministic processing, Agent receipt, or
republication cannot promote External-Origin Authority to Platform-Origin
Authority. Authorization permits an actor or capability to access or use
information for a scope; it does not create platform authority.

User-provided statements, holdings, preferences, objectives, assumptions,
constraints, conversation history, profiles, and memory are task or personal
context. They are not Evidence and therefore have no Evidence authority class.
A financially material user constraint may affect platform semantics only
through an approved, explicit, typed, and versioned application input; its use
as application context still does not reclassify it as Evidence.

Information that does not satisfy the Evidence definition remains source
material, derived information, or task or personal context as applicable. It
must not be presented, cited, or consumed as admitted Evidence.

### Evidence Artifact identity

An Evidence Artifact is an explicitly identified and versioned conceptual
artifact. Its identity must preserve at least:

- **evidence type:** the declared kind and semantic scope of the observation or
  assertion;
- **subject identity:** the canonical entity or entities to which the Evidence
  applies;
- **source identity:** the platform capability, producer, publication, or
  authorized external source responsible for the represented material;
- **temporal identity:** the applicable source and artifact times, preserved as
  separate values rather than collapsed into one timestamp;
- **provenance:** the traceable origin, producer, source references, contract
  and version lineage, and transformations preceding admission;
- **authority classification:** Platform-Origin Authority or External-Origin
  Authority, without implicit promotion between them; and
- **validation references:** references to immutable validation records for the
  exact Evidence Artifact version and declared validation scopes.

Where applicable, temporal identity and evaluation context preserve separately:

- observation or event time, or the reference interval;
- effective or valid time;
- publication or release time;
- source revision or vintage;
- receipt or admission time;
- artifact creation time; and
- task evaluation or as-of time.

The governing Evidence contract determines which temporal fields are mandatory
for its evidence type and use. A field that is inapplicable must not be invented
or silently substituted with another time. In particular, receipt, admission,
or artifact creation time does not stand in for source observation, effective,
publication, or revision time.

These are semantic identity requirements, not a storage schema. This ADR does
not prescribe identifiers, field names, serialization, indexes, tables,
databases, repositories, or physical retention.

An artifact revision creates a new version with its own validation records. It
does not edit, replace, or rebind the identity or provenance of a prior version.

### Freshness evaluation

Freshness is a task-time predicate evaluated for an exact Evidence Artifact
version. It is not a mutable boolean property stored on or toggled within the
Evidence Artifact.

Each freshness evaluation preserves:

- the freshness rule identity and ruleset version;
- the temporal anchor used by that rule;
- the task or use scope;
- the evaluation or as-of time; and
- the resulting disposition and findings.

The same Evidence version may be fresh for one scope or evaluation time and
not fresh for another. A later evaluation appends a new result; it does not
rewrite the Evidence Artifact or an earlier freshness result.

Evidence Validation checks freshness-contract compatibility: the artifact
must contain the temporal anchors required by the declared freshness rule, and
the rule identity, version, and scope must be supported by the governing
Evidence contract. Evidence Validation does not decide that an artifact is
fresh for all future tasks.

When freshness is required for admission, the admission record references the
exact freshness evaluation, including its rule identity, ruleset version,
scope, evaluation `as_of`, and result. Downstream consumption evaluates
freshness again at task time when the governing contract requires a different
scope or later `as_of`.

### Canonical information flow

The mandatory information flow remains the complete ADR 0034 canonical flow:

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

Within that flow, `Source Evidence` is a candidate Evidence Artifact and the
output eligible for admission after Evidence Validation is Validated Evidence.
Where a validation or synthesis contract needs both observed source material
and deterministic platform semantics, the allowed inputs are explicit and
remain separately classified:

```text
Validated Evidence -----------+
                               +-> applicable validation or synthesis
Authoritative Domain Results --+
```

An Authoritative Domain Result does not enter the Source Evidence lane and is
not subject to Evidence Validation as though it were an Evidence Artifact. Its
own domain and application contracts govern its validity and correspondence.
Interpretation Validation and Synthesis may cite both classes where their
contracts permit it and must preserve the authority, version, time, and lineage
of each input.

Specialists consuming Evidence must never describe an Authoritative Domain
Result as Evidence or relabel one as Source Evidence. The additional input
path above applies only to validation or synthesis contracts that explicitly
declare both classes; it does not add a domain result to an Evidence-only
specialist first pass.

Only an exact Evidence Artifact version that has passed every mandatory
Evidence Validation concern may be considered Validated Evidence or be
eligible for admission for the declared scope. Evidence Validation owns only:

- **identity:** evidence type, subject, source, artifact version, and governing
  contract identities;
- **integrity:** completeness as an exact artifact version and detection of
  silent alteration or rebinding;
- **provenance:** origin, producer, source references, lineage, and material
  transformations;
- **schema completeness:** presence and structural compliance of contractually
  required material;
- **authority:** correct Evidence authority classification and its admissibility
  for the declared scope;
- **temporal coherence:** consistency of the required temporal identities and
  reference intervals; and
- **contract-defined source quality:** only the source-quality checks explicitly
  required by the governing Evidence contract.

Evidence Validation does not own market interpretation, financial
significance, confidence, ranking, recommendations, or any other derived
judgment. Freshness may be required for admission or consumption, but it is
evaluated as the separately recorded task-time predicate defined above.

Every validation result is an immutable validation record containing at least:

- a stable validation-record identity;
- the exact Evidence Artifact identity and version validated;
- the validation concern and `scope`;
- the `disposition`;
- the validator `actor` and, when invoked through one, `capability` identity;
- the validation rule identity and ruleset version;
- `recorded_at`, when the record was appended;
- `effective_at`, when the disposition applies for its scope;
- a required `reason`, with structured findings or source references where
  applicable; and
- references to any prior record that it explicitly supersedes.

Evidence Validation uses exactly three dispositions:

- **`Passed`** means the exact artifact version satisfied the declared concern
  and ruleset for the scope. It makes the version eligible for admission only
  after every mandatory scope has `Passed`; it does not itself admit Evidence.
- **`Rejected`** means the reviewer established a contract, integrity,
  provenance, authority, temporal, or source-quality failure. The artifact
  fails closed and cannot be admitted for that scope.
- **`UnableToValidate`** means the reviewer lacked sufficient admissible
  material or capability to establish either `Passed` or `Rejected`. It is not
  a pass and also fails closed for admission, but it does not assert that the
  source claim is false or that a specific defect was established.

For Evidence Validation only, ADR 0034's `challenged` disposition maps to
`Rejected`; its `unable to validate` disposition maps to
`UnableToValidate`. A later validation or revalidation appends a record and
does not alter an earlier record. Evidence Validation does not repair the
artifact, invent missing facts, create authority, reinterpret source meaning,
or promote External-Origin Evidence to Platform-Origin Evidence.

### Evidence lifecycle and as-of evaluation

Evidence has no mutable lifecycle field. Lifecycle conclusions are evaluated
from immutable, append-only records for an exact artifact version and scope.
The absence of an admission record means `Candidate`; `Candidate` is not a
stored state transition.

Every admission decision is an immutable admission record containing at least:

- a stable admission-record identity and the exact Evidence Artifact identity
  and version;
- the admission `disposition`, either `Admitted` or `Rejected`;
- `scope` and the governing admission rule and version;
- references to the exact mandatory validation records used;
- when freshness is required, the exact freshness rule identity, ruleset
  version, scope, evaluation `as_of`, result, and evaluation-record reference;
- the deciding `actor` and, when invoked through one, `capability` identity;
- `recorded_at` and `effective_at`;
- a required `reason`; and
- a reference to any prior admission record it explicitly supersedes.

An `Admitted` record may be appended only when all mandatory validation
dispositions referenced by that decision are `Passed` and every required
freshness evaluation passes. `Rejected` records admission failure. Neither
disposition modifies validation history or the Evidence Artifact.

Every validity change is an immutable validity event containing at least:

- a stable event identity and the exact Evidence Artifact identity and
  version;
- the validity disposition: `Active`, `Expired`, `Withdrawn`, or `Revoked`;
- `scope`;
- the responsible `actor` and, when invoked through one, `capability` identity;
- `recorded_at` and `effective_at`;
- a required `reason`; and
- a reference to any earlier validity event it explicitly supersedes.

`Expired` records the end of temporal usability. `Withdrawn` records that the
source or owning authority withdrew the observation. `Revoked` records that
previously admitted Evidence must no longer be relied upon for its scope from
the event's `effective_at`. Withdrawal and revocation do not erase prior
admission or prior use. Reactivation after `Expired`, `Withdrawn`, or `Revoked`
requires a new Evidence Artifact version rather than mutation or a new
`Active` event for the old version.

Deterministic as-of evaluation applies this precedence:

1. Select records for the exact Evidence Artifact version and exact requested
   scope, partitioned by record kind and, for validation, by mandatory concern.
   Scope is never widened implicitly; any governed scope-inheritance rule must
   be identified and versioned.
2. Exclude records with `recorded_at` after the evaluation's
   `knowledge_as_of` or `effective_at` after its `effective_as_of`. If a
   contract supplies one `as_of`, that value is used for both.
3. Within each partition, follow explicit supersession references, then choose
   the remaining record with the latest `effective_at`, followed by the latest
   `recorded_at`.
4. Fail closed on conflicting co-precedent records. For validation this yields
   `UnableToValidate`; for admission or validity it yields not admissible.
5. Evaluate mandatory validation scopes first, admission second, validity
   third, and task-time freshness last. Evidence is consumable only when every
   mandatory validation scope is `Passed`, the effective admission is
   `Admitted`, validity is `Active`, and the task-time freshness predicate
   passes.

`recorded_at` answers when the platform learned or recorded a conclusion;
`effective_at` answers when that conclusion applies. This separation prevents
a later-recorded correction or revocation from silently rewriting what was
known in an earlier as-of evaluation.

Lineage is also append-only. Supersession links identify predecessor and
successor artifact versions and preserve the supersession reason, scope,
`recorded_at`, `effective_at`, and responsible actor or capability.
Supersession does not silently expire, withdraw, or revoke a predecessor and
does not retroactively replace its provenance.

Historical Evidence provenance is immutable. Prior versions, validation
records, admission and validity events, supersession links, and downstream
references remain traceable. Revalidation, rejection, correction, refresh,
source revision, withdrawal, revocation, or supersession creates a new artifact
version or append-only record as applicable; it never rewrites history.

### Specialist consumption rules

Specialist Intelligence may consume only:

- admitted, active Evidence versions whose freshness predicate passes for the
  task's identity, temporal, authority, and contract-defined scope at the task
  evaluation time; and
- explicit task context declared by the task contract and visibly separated
  from Evidence.

For independent first-pass analysis, a Specialist must not consume:

- peer interpretations;
- peer confidence;
- peer conclusions; or
- synthesis artifacts.

Those derived artifacts may be used only in the downstream Interpretation
Validation, adversarial review, or Synthesis stages permitted by ADR 0034.
They must not be relabeled, quoted, summarized, or fed back as Evidence.

Derived intelligence and Authoritative Domain Results cannot become Evidence.
Repetition, consensus, a validation pass on an Interpretation, deterministic
production, or retention of complete lineage does not change that rule. If new
observable source material is required, it must enter as a separately
identified candidate Evidence Artifact through the applicable Evidence
authority and validation boundaries.

### Portfolio distinction

User-stated or remembered holdings, portfolio preferences, objectives, and
constraints are user-provided context. They are not Evidence and do not become
authoritative through Agent memory, conversation, inference, or repeated use.

A provenance-bearing, typed, and versioned broker, custodian, or account
snapshot is External-Origin Evidence and retains External-Origin Authority.
Transport through an approved capability, capability authorization,
canonicalization, identity resolution, schema or contract validation, and
Evidence admission cannot promote that authority. Only an observation that
originates in a platform-owned system of record may be Platform-Origin
Evidence. A platform copy, normalized projection, or deterministic calculation
over an external snapshot is not a new platform-origin observation.

An admitted snapshot retains its external source, account or portfolio subject
identity, applicable temporal identities, Evidence authority, validation-record
references, and task-time freshness evaluations. It does not grant authority to
user-stated holdings or approve Portfolio Intelligence, allocation,
rebalancing, recommendation, Trade Planning, Risk, or Execution.

### Classification examples

- **Platform-origin observation:** an effective-dated instrument-status change
  authored in a platform-owned instrument master is a Source Observation. Its
  identified, versioned, provenance-bearing representation may be
  Platform-Origin Evidence and becomes Validated Evidence only for scopes in
  which all mandatory validation concerns `Passed`.
- **External broker snapshot:** a typed holdings snapshot obtained from a
  broker or custodian is External-Origin Evidence. Approved transport,
  canonicalization, validation, and admission preserve rather than promote its
  External-Origin Authority.
- **ADR 0032 deterministic domain result:** a
  `DailyTechnicalInterpretation`, its corresponding
  `DailyTechnicalAssessment`, and the resulting `DailyTechnicalStrategy` are
  Authoritative Domain Results. They may be cited as such in an applicable
  validation or synthesis contract, but none is Evidence.

### Relationship to prior decisions

ADR 0032 remains authoritative for the Daily Technical Strategy application
boundary and its verified-research lineage. This ADR neither changes its
contracts nor turns its derived Interpretation, Assessment, or Strategy values
into Evidence. Evidence and Evidence Validation do not own financial semantics,
domain policies, application orchestration, or strategy decisions.

ADR 0033 remains authoritative for Agent exposure, memory, preference, and
application-access boundaries. This ADR creates no Agent path to generic
application services, domain runners, providers, or platform internals.

ADR 0034 remains authoritative for multi-Agent independence, the complete
artifact DAG, validation admission, personal-context isolation, synthesis, and
human decision authority. This ADR specializes only the foundational Source
Evidence and Evidence Validation portions of that architecture.

### Invariants

- Evidence is not truth.
- Deterministic domain results are not Evidence.
- Validation is not interpretation.
- Authorization is not platform authority.
- Freshness is evaluated as-of.

## Consequences

- Future Evidence capabilities share one semantic definition, authority
  classification, identity minimum, validation-record boundary, freshness
  evaluation, and lifecycle.
- Specialists receive admissible source material without inheriting peer
  reasoning or hidden personal context.
- Historical provenance remains auditable when Evidence expires, is corrected,
  or is superseded.
- External assertions can retain explicit external authority without being
  mistaken for deterministic platform output.
- Future implementation decisions must preserve these boundaries while making
  separate choices for acquisition, ingress, persistence, transport, runtime,
  and operations.

## Non-goals

This decision does not design, approve, or implement:

- data acquisition or provider access;
- Evidence storage, persistence, a database, cache, index, or retention system;
- Evidence ingestion, canonicalization machinery, or an ingress service;
- serialization, transport, messaging, an API, MCP, CLI, or UI;
- an LLM runtime, Agent runtime, scheduler, supervisor, or Agent
  implementation;
- source, broker, portfolio, market-data, document, or other connectors;
- a new application or Agent capability, or a change to the ADR 0033
  capability allow-list;
- Interpretation, Synthesis, recommendation, Trade Planning, Risk, Execution,
  or human-decision implementation; or
- source-code changes of any kind.

Any future implementation requires separately approved contracts and must
preserve the Evidence authority, validation, lifecycle, provenance, and
specialist-isolation rules defined here.
