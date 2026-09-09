# ADR 0039: Production Evidence Governance and Governed Daily Technical Consumption

## Status

Accepted.

This document specifies the v0.79 semantic contract accepted after architecture
review. Acceptance does not authorize implementation or issue production
governance records; the required-before-implementation prerequisites remain.
All work through v0.78.0 remains frozen.

## Context: observed existing architecture

The inspected baseline is local `main == origin/main` at
`0f10809ec6b587c523e6357f74059f98c834934a`, the v0.78.0 release handoff commit.
Its parent is release merge `2e20f8bf87d4103df188bf113ef6a211973cbb7a`, with
release tree `039b0aeaa19af92826525c9e23ca4511f1939979`. Package version is
`0.1.0`. The handoff records 4,167 passed, 4 skipped, Ruff passing, mypy passing
across 207 source files, 69 ordered unique Evidence exports, and release review
`BLOCKER 0`, `REQUIRED 0`. These are recorded release checks, not checks rerun
by this drafting checkpoint or evidence of source truth.

ADR0038 is the highest existing ADR number. Existing ADR filenames use numbered
hyphenated names; this new document retains the number and ADR heading pattern
and uses snake_case in accordance with the current AGENTS.md documentation rule.

### Existing mechanisms, not v0.79 inventions

[ADR0035](0035-evidence-foundation-architecture.md) and the released Evidence
package already provide immutable `EvidenceArtifact`, validation and admission
records, freshness evaluation records, append-only validity and supersession
history, exact policy/version references, recorded/effective time semantics,
and full-record lifecycle evaluation. In particular:

- `evaluate_evidence_admission_as_of(...)` resolves full records for an exact
  artifact, scope, ruleset, `knowledge_as_of`, and `effective_as_of`.
- `EvidenceAdmissionState.is_consumable` is the resulting lifecycle conclusion.
  `is_admitted` is explicitly not a consumability guarantee.
- The released `EvidenceAdmissionRuleSet` requires the foundation concern
  floor, admission-time freshness, task-time freshness, and active validity.
  Those requirements cannot be disabled by production profile selection.
- Record factories enforce correspondence and structural consistency. For
  example, the freshness factory accepts a result boolean, and the admission
  factory accepts validation/freshness references. These APIs are not proof
  of approved production execution or complete production history.
- The current freshness record retains rule, artifact, evaluated temporal
  values, `evaluation_as_of`, result, and findings. It has no separate actual
  execution/result-availability timestamp. Its factory and full evaluator
  derive/check temporal anchors against `EvidenceArtifact.temporal_identity`.
  They do not derive usable market-session facts from retained Polygon rows.
- The full evaluator receives record tuples. A self-consistent supplied tuple
  alone does not establish that the caller supplied every adverse known record
  or that the underlying material was available at the requested knowledge time.

[ADR0037](0037-polygon-completed-daily-ohlcv-evidence-ingress.md) and
[ADR0038](0038-polygon-completed-daily-evidence-material-and-candidate-construction.md)
define the sole released production ingress: Massive.com, formerly Polygon.io,
Stocks Custom Bars, through the exact `api.polygon.io` profile. Exact JSON
acquisition, trusted canonical mapping, governed material, and exact production
membership produce an immutable Candidate for read-only inspection.

The production gap is approved execution of that Candidate through the existing
lifecycle, followed by an authorized representation bridge into Daily Technical.
It is not a missing generic Evidence lifecycle.

### Inspection evidence

The decisions below were checked against these implementation boundaries and
their unit tests, in addition to the linked ADRs:

- `src/market_platform/evidence/{models,validation,admission,policy,temporal,evaluation,validity,supersession}.py`;
- `src/market_platform/evidence/__init__.py` and
  `tests/unit/test_evidence_public_api.py`;
- `tests/unit/test_evidence_evaluation.py`, including full-record correspondence,
  missing prerequisites, task freshness independence, terminal validity,
  supersession, bitemporal replay, and fabricated temporal-anchor rejection;
- `src/market_platform/evidence_ingress/polygon_completed_daily_ohlcv.py` and
  `src/market_platform/application/polygon_completed_daily_evidence_candidate.py`;
- `src/market_platform/research/{daily_evidence,daily_instrument_integrity,technical_analysis}.py`.

The existing public `prepare_completed_daily_price_series(...)` owns legitimate
`CompletedDailyPriceSeries` construction and can exclude current-date rows.
The legacy verified workflow additionally trims to its mapping interval and
acquires prices. `analyze_daily_technical_snapshot(...)` is the pure deterministic
analyzer and already produces an identified `TechnicalAnalysisSnapshot`.

## Frozen contracts preserved

The following distinctions are mandatory throughout the production operation,
its inspection projections, and its result:

```text
Evidence construction != validation
validation != admission
admission != validity
admission != freshness
admission != consumability
Candidate != research input
construction authorization != downstream research permission
```

The v0.78 construction authorization remains exactly:

```text
production.polygon_completed_daily_ohlcv / 1.0.0
sha256:e9d8057dde8e20c5fb297ea08be7bcc723131cea42fab0e8a528f5b40c343387
```

It permits construction of this exact Candidate only. It establishes neither
validation, admission, validity, freshness, consumability, nor Daily Technical
permission. Source authority remains `EXTERNAL_ORIGIN` and information class
remains `SOURCE_MEASUREMENT`; processing never promotes external measurements
to platform-origin observations.

ADR0038's material schema, exact decimal strings, fingerprints, source vintage,
mapping provenance, requested bounds, completion filtering, and temporal
identity remain unchanged. In particular, its observation interval is the
requested half-open New York civil-date interval, not the actual returned-row
range. `observed_at`, `published_at`, and unavailable effective source times
remain null. Receipt and creation remain separate, with
`query_as_of <= platform_received_at <= artifact_created_at`.

The released Candidate inspection remains:

```text
lifecycle_state = candidate
semantic_authorization = exact_production_membership
validation = not_performed
admission = absent
validity = not_evaluated
freshness = not_evaluated
consumable = false
research_permitted = false
UNVALIDATED, UNADMITTED CANDIDATE — NOT PERMITTED FOR RESEARCH
```

These are inspection projections, not mutable fields of `EvidenceArtifact`.
The Candidate construction/inspection operation remains separate from the new
governed operation. Neither a projection boolean nor a changed display label
can issue lifecycle state or research permission.

## New v0.79 decisions

### 1. One bounded production vertical slice

The supported new operation composes these distinct authority steps:

```text
Exact production-authorized Polygon Candidate and retained material
    -> trusted approved validation execution
    -> admission-time freshness execution
    -> trusted admission decision
    -> distinct validity activation / append-only history
    -> task-time freshness execution
    -> canonical full lifecycle evaluation
    -> exact Daily Technical use qualification
    -> governed representation adapter
    -> unchanged deterministic Daily Technical analysis
    -> technical snapshot with governance/provenance envelope
```

An existing authentic prerequisite may be resolved from trusted history when
its exact policy, scope, time, and lineage permit reuse. Orchestration does not
automatically reissue decisions or select favorable replacements. Every use
requires the full canonical evaluation at its declared cutoffs.

There is no Candidate-to-research bypass and no governance-refusal-to-legacy
acquisition fallback. No second Evidence source is added. The v0.79 terminal
milestone is an Evidence-backed Daily Technical analysis result, not
Interpretation, Assessment, Strategy, an Agent response, or a trading action.

### 2. Trusted execution and history are the production authority boundary

Platform-controlled production operations must execute approved validation,
freshness, admission, and validity rules and issue the resulting immutable
records through the existing lifecycle model. Application orchestration orders
those operations and verifies correspondence; it does not own their semantics.

Production callers supply permitted intent and exact input references. They
cannot gain issuance authority by choosing `PASSED`, `ADMITTED`, freshness
`true`, or `ACTIVE`; supplying a coherent policy or favorable history; naming
an actor/capability; holding a hash or private-looking constructor; or changing
an inspection boolean. Actor/capability references describe accountable
execution. Naming them does not execute or authorize that operation.

Hashes establish identity and correspondence, not authorization. Record
factories and private seals remain implementation integrity mechanisms; their
possession or invocation is not production permission. Caller-created records
and reconstructed references must not be imported as authentic production
history merely because they validate structurally.

The supported boundary must resolve records to their approved execution and
retained inputs. An in-process platform-controlled execution/history boundary
is sufficient for the first slice. This is a supported-call authority boundary,
not a claim of isolation from arbitrary malicious code already controlling the
process. Cryptographic signatures, remote issuers, and a database are not
required. Dependency injection remains appropriate for external clients and
clocks at trusted composition seams; it is not a caller-controlled way to
replace production authority or return invented outcomes.

### 3. Exact additive governance and consumer policies

Production governance and the Daily Technical use profile must have approved,
immutable identity/version/configuration correspondence. Validation requirements,
admission rules, admission/task freshness rules, validity issuance rules, use
scope, and the bridge transformation must resolve to approved platform-owned
semantics. Each separately governed policy/contract has its own identity and
version; an approved profile binds their exact combination.

The existing construction authorization is not extended, renamed, or reused as
this approval. A policy-shaped value, matching ID text, arbitrary configuration,
compatible version range, or caller-selected reduced concern set is insufficient.
Scope is exact; no implicit widening or inheritance is introduced. Generic
lifecycle authority must remain independent of Polygon transport, HTTP, pandas,
provider acquisition, application, and Agent layers. Source-specific execution
and adaptation depend inward on those generic contracts.

### 4. Validation executes the existing concerns

Use `EvidenceValidationRecord` and the released concern taxonomy:
`IDENTITY`, `INTEGRITY`, `PROVENANCE`, `AUTHORITY`, `SCHEMA`,
`TEMPORAL_COHERENCE`, `FRESHNESS_CONTRACT`, and `SOURCE_QUALITY`.
Preserve the mandatory foundation floor and require the approved source-quality
checks necessary for this exact production research use. There is no parallel
ValidationAttestation architecture.

Approved rules must evaluate the exact Candidate, retained material, and
available provenance for artifact/material correspondence; source, contract,
and construction authorization; canonical subject and retained mapping coherence;
schema and canonical rows; temporal and availability-provenance coherence; and
contract-defined OHLCV/source-quality conditions. Validation cannot assume a
construction gate proves every later concern. Construction-only/transient
facts omitted under ADR0038 must not be fabricated or claimed to be retained.
An approved rule must identify its admissible support, including trusted
construction execution where sufficient; unavailable mandatory support fails
closed rather than silently changing material v1 or acquiring a new vintage.

Carried artifact/lifecycle timestamps are evidence inputs. Validation may
establish their structural and provenance coherence within an approved concern;
it does not make those values self-authenticating. Actual supported-production
availability requires the distinct trusted execution/history/retention basis
in Section 8, not merely a coherent timestamp or validation pass.

`PASSED` means that the declared concern/ruleset was satisfied for this exact
version and scope. `REJECTED` records an established failure.
`UNABLE_TO_VALIDATE` records insufficient admissible support or capability to
establish pass or rejection. Unknown is never an implicit pass, and inability
does not assert that the source claim is false.

Validation establishes no source truth beyond available evidence, investment
merit, future correctness, strategy suitability, ranking, trading significance,
or later market outcome. It does not repair or mutate source material.
`FRESHNESS_CONTRACT` checks supported rule/scope and required temporal facts;
temporal coherence checks their consistency. Neither declares the Evidence
fresh at admission or for a later task.

### 5. Freshness evaluates retained completed market-period facts

Admission-time and task-time freshness are separate executions/results under
approved versioned rules, retained through the existing freshness lifecycle.
Admission-time success does not guarantee later task freshness. The production
profile must retain both requirements and exact rule/scope correspondence.

For completed-daily use, freshness answers only whether retained completed
market-period facts satisfy the approved freshness rule. Its support must derive
from the exact material, including the latest retained completed session eligible
under that rule and the facts supporting that freshness eligibility. Preserve
requested bounds separately from actual retained completed session counts/ranges
and any rule-specific freshness eligibility. Empty material or insufficient
support for the approved rule cannot prove freshness for this use.
A recent requested end does not prove recent returned data. Receipt, Candidate
creation, or admission recency is not a substitute for market-period recency.

Freshness does not determine historical instrument mapping coverage, Daily
Technical consumer authorization, bridge numeric convertibility, research-history
sufficiency, analyzer DEGRADED/full quality, or lifecycle consumability as a
whole. These remain separate authorities/checks. Binding freshness to an exact
artifact/material/scope and approved rule does not make it a consumer-
qualification or consumability engine. Rule-specific freshness eligibility
does not authorize row selection or removal from the whole-Candidate research
input; Sections 10 and 11 still require every retained governed row to survive.

Thresholds, expected-session treatment, calendar coverage, publication-lag
assumptions where supported, and handling of absent or unusual sessions belong
in the approved versioned production policy/profile. This ADR fixes no global
threshold or permanent calendar implementation. The analyzer's seven-calendar-
day stale warning remains descriptive and is never Evidence freshness policy.
Neither its presence nor its absence grants or denies lifecycle authority.

Each production freshness execution must retain correspondence to exact
artifact/material, rule/version/scope, material-derived retained completed
market-period facts, `evaluation_as_of`, result/findings, accountable execution,
and when the execution/result actually became available. Requested observation bounds,
response receipt/acquisition, Candidate creation, and result availability remain
distinct from the evaluation time.

The released temporal-anchor checks must not be bypassed, weakened, or satisfied
by relabeling requested `observation_period_end` as the latest retained completed
session eligible under the approved freshness rule.
The existing freshness record does not express all required material-derived
and execution-availability provenance. A narrow additive, versioned integration
must preserve that provenance and its binding to canonical lifecycle resolution.
Whether this uses a companion execution record, an additive envelope, or an
appropriately versioned extension is left open; no exact class decomposition is
mandated. It must neither rewrite existing record meaning nor create a parallel
freshness/consumability engine. This integration must be resolved before the
dependent production implementation can claim historical correctness.

### 6. Admission resolves authentic prerequisites

Validation success makes admission possible; it does not perform admission.
Trusted admission executes the exact approved `EvidenceAdmissionRuleSet` and
appends a distinct immutable `EvidenceAdmissionRecord` with its actual
recorded/effective times and accountable actor/capability.

The decision must bind the exact artifact/version/material, subject and scope,
approved admission policy identity/version, authentic mandatory validation
results and their policies, required admission-time freshness, and the exact
construction authorization. Existing artifact and policy references may carry
these bindings transitively; this ADR does not require duplicating their fields.

Reference integrity proves that resolved content corresponds to a reference.
Trusted prerequisite resolution additionally proves that approved execution
occurred and the prerequisites were actually available when the decision was
issued, with compatible effective chronology. Caller-created references prove
neither. Admission must resolve complete relevant history, including adverse
and superseding records, rather than admit against a caller-selected subset.
Later revalidation does not silently rebind an earlier admission; canonical
reference/supersession requirements continue to apply.

### 7. Validity is an independent governance event history

Validity concerns whether the exact governed Evidence version remains eligible
under known governance events for its declared scope. It does not describe
whether an investment thesis succeeded. The production slice requires a
distinct trusted `ACTIVE` issuance after admission with authentic prerequisite
availability; admission itself must not imply or manufacture activation.

Preserve ADR0035 append-only events, recorded/effective timing, explicit lineage,
conflict behavior, and terminal protections. `EXPIRED`, `WITHDRAWN`, and `REVOKED`
cannot be reversed by appending `ACTIVE` to the same version; reactivation needs
a new Evidence version under the frozen model. Supersession alone does not
expire, withdraw, or revoke the predecessor. A temporary task freshness failure
must not automatically create terminal `EXPIRED` validity.

### 8. Complete history and point-in-time availability

The supported production boundary resolves a trusted complete lifecycle history
for the exact Evidence version/scope and requested knowledge cutoff, including
the predecessor closure needed for canonical resolution. Callers cannot omit
adverse known records, choose a favorable store snapshot, or present selected
references as completeness proof. Completeness is an execution/history contract,
not a property established by hashing a supplied list.

Preserve canonical recorded/effective selection, explicit supersession, latest
effective then recorded precedence, conflict refusal, and validation-before-
admission-before-validity-before-task-freshness evaluation. Retain full authentic
records and resolution provenance. Do not prefilter away conflicts or lineage
needed by the full resolver. A historical cutoff legitimately excludes later
knowledge; it does not authorize selective omission within that cutoff.

Knowledge-time filtering of lifecycle records is insufficient on its own.
The exact Candidate and material must actually have existed and been available
by `knowledge_as_of`. The production boundary must establish actual receipt,
creation, and trusted retention provenance; it cannot trust a caller-backdated
creation field. The same availability requirement applies to lifecycle records
and execution results used by the operation.

```text
declared timestamp value != timestamp structural/coherence validation
timestamp structural/coherence validation != trusted production availability
```

An artifact's `artifact_created_at`, a lifecycle record's `recorded_at`, or any
other carried timestamp does not by itself authenticate that the platform
actually possessed the artifact, material, or result at that time. Actual
availability must be established by the supported boundary's trusted production
execution/history/retention provenance. Coherence validation may check that
provenance under its approved concern; neither validation nor a carried timestamp
replaces the trusted basis for it.

Injected clocks remain legitimate deterministic/test seams. In supported
production composition, platform-controlled execution supplies those seams and
retains corresponding execution/result-availability provenance. Caller possession
of an injectable clock, or the ability to construct structurally coherent
timestamps, grants no historical availability authority. ADR0038's explicit
Candidate timestamp inputs and temporal identity remain unchanged. This distinct
trusted basis requires neither cryptographic signing nor a database.

Keep these meanings separate:

| Time/fact | Meaning |
| --- | --- |
| Source market period | Actual material session dates and requested reference bounds, separately |
| Publication/observation instant | Source fact only where actually known; unavailable Polygon values stay null |
| Acquisition/receipt | When this exact response was received, not when it was published |
| Candidate creation | When this immutable version actually came into existence |
| Lifecycle recorded time | When the platform recorded/learned that conclusion |
| Lifecycle effective time | When that conclusion applies to its scope |
| Freshness evaluation time | The time for which the predicate was evaluated |
| Freshness result availability | When execution produced the result and it became available |
| Research as-of | The declared analytical cutoff, bound to task effective evaluation |
| Research/result production time | When the later computation/result was actually produced |

The governed use binds research `analysis_as_of` to lifecycle `effective_as_of`
and task freshness `evaluation_as_of`, and retains `knowledge_as_of` separately.
The current full evaluator requires task freshness at that exact effective time
and no later than knowledge time; production additionally requires actual result
availability by knowledge time. Admission prerequisites must have existed by
actual admission issuance. No equal-clock shortcut substitutes for chronology.

A later computation about an earlier effective time may be identified as such,
but cannot claim that its result or later governance existed earlier. Future
Temporal-Blind replay at T can use only the exact source vintage/material,
governance, mappings, policies/versions, and other context actually available
by T. If a necessary result did not exist by T, historical permission fails
closed; executing a new rule today with `evaluation_as_of=T` cannot repair it.
Never refetch today's adjusted history and call it knowledge at T, invent an
unobserved publication time, or backdate Candidate availability.

### 9. Canonical consumability and exact consumer correspondence

`evaluate_evidence_admission_as_of(...)` remains the sole canonical full
lifecycle resolver, and its `EvidenceAdmissionState.is_consumable` remains the
lifecycle conclusion. Production invokes it with full authentic records/history,
the actual artifact, approved ruleset, exact scope, and correct temporal cutoffs.
The reference-only `evaluate_evidence_admission_state(...)` is insufficient.
There is no new generic `ConsumabilityDecision` authority.

Validation pass, `is_admitted`, an admission record, `ACTIVE`, or freshness true
alone is never research permission. Missing, ambiguous, incomplete, mismatched,
unavailable, or unauthorized prerequisites fail closed. The trusted boundary
establishes authenticity/completeness/availability for canonical evaluation;
it must not turn a canonical refusal into permission or independently recompute
the lifecycle conclusion.

A consumer-specific use envelope binds the resolved state and its constituents
to the exact artifact/material, canonical subject, approved Daily Technical
consumer/profile, governance policies/scope, and cutoffs. It records the
transformation and research dataset identity when those are produced. It can
enforce additional use correspondence and refuse an unsupported use of otherwise
consumable Evidence. It cannot duplicate, replace, broaden, or override lifecycle
authority. A caller-supplied envelope or cached success boolean is not a reusable
permission token for another artifact, profile, scope, or time.

History resolution and consumption must share a coherent trusted evaluation
context. If new known governance changes that context before use, re-resolve or
refuse; do not consume under a silently stale qualification. Retain the actual
context and result production time without rewriting prior evaluations.

### 10. Every consumed row must have historical instrument coverage

Current mapping resolution at Candidate `query_as_of` is not proof that the same
canonical instrument identity covers every historical row. For this first use,
each consumed row must be covered by the exact trusted, effective-dated mapping
retained for the Candidate, corresponding to the same canonical subject and
available at the requested knowledge cutoff.

Preserve the existing daily mapping convention: a session date maps to a
midnight-UTC date label and the trusted mapping interval is half-open
`[valid_from, expires_at)`. This label is an identity/date convention, not an
assertion of market-event time. Arbitrary partial-day or otherwise unsupported
mapping semantics cannot be accepted by silently taking `.date()` and widening
coverage. Approved use rules must establish coverage for each row or refuse.

Prefer acquisition/construction with appropriately bounded requested dates.
If retained governed material contains rows outside supported historical
coverage, refuse this use of the whole Candidate. The bridge must not trim,
stitch aliases, fetch former tickers, or silently select a supported subset.
ADR0029's legacy `trim_to_mapping_interval` stays unchanged in its own workflow
and does not constitute Evidence admission.

A future subset feature would require an explicit governed transformation with
original/selected fingerprints, counts, ranges, mapping and provenance. This ADR
does not introduce that generalized architecture. ADR0038's already-governed
construction filtering remains valid and is distinct from prohibited post-
governance silent selection.

### 11. The bridge is a representation adapter after qualification

Only after successful lifecycle and exact-use qualification may the bridge
consume retained governed material. It owns conversion and correspondence,
not validation, admission, validity, freshness, consumability, or source access.
It performs no price refetch and invokes no legacy acquisition/verified workflow.
Daily Technical remains independent of Polygon-specific transport semantics.

Preserve `CompletedDailyPriceSeries` as the unchanged analyzer input. The
adapter may use legitimate pure representation factories, including
`prepare_completed_daily_price_series(...)`, where their contracts fit. Before
conversion it must establish that all governed rows are completed for the exact
research as-of. The authoritative no-drop correspondence proof must be end-to-end
between the retained governed Evidence material and the final
`CompletedDailyPriceSeries` supplied to the deterministic analyzer. It must prove
one-for-one correspondence, order, count, dates, and approved converted values
against that original retained material.

Proof only between an intermediate `HistoricalPriceSeries` and its output, a
prefiltered sequence and its output, the input/output of
`prepare_completed_daily_price_series(...)`, or any other intermediate objects
after governed rows have already been dropped is insufficient.

Any intermediate research cutoff, completion/date filtering, trimming,
deduplication, truncation, substitution, row selection, or other transformation
that removes a retained governed row requires refusal of this v0.79
whole-Candidate use. Row selection would require its own explicit governance;
ADR0039 authorizes no such subset selection. The future governed-subset decision
in Section 10 remains separate.

Choose `analysis_as_of`, requested Candidate bounds, and bridge composition so
that all retained governed rows survive the legitimate representation factories.
If any reused legitimate factory would filter even one retained governed row,
refuse this use; its reduced output is not permitted research input. Do not
repair that refusal by inserting a replacement row or moving the proof baseline
past the filtering step.
Empty material cannot become the nonempty completed series the analyzer requires.

Using `HistoricalPriceSeries` or `DailyResearchEvidence` as internal research
representation through legitimate factories confers no Evidence lifecycle
authority. Neither `DailyResearchEvidence` nor `DailyInstrumentIntegrityEvidence`
is production Evidence admission. Do not forge, import, or opportunistically
reuse private seals, fabricate a verified workflow result, or bypass factory
contracts to make the new composition fit.

### 12. Versioned numeric and date transformation

The bridge has an explicit approved transformation identity/version. Preserve
the original exact decimal-string material and its fingerprint, and separately
identify the output research dataset with the released research fingerprint
conventions. Floating-point values have neither the identity nor the precision
of the original decimal strings. Ordinary supported rounding must be declared;
the bridge must not claim exact decimal preservation in float output.

The transformation contract specifies conversion of each OHLCV field, supported
numeric range/precision behavior, session-date labels, metadata correspondence,
canonical row order, and output fingerprinting. Reject non-finite, overflow,
destructive-underflow (including nonzero-to-zero), and other unsupported results
under approved bridge rules. Do not clip, repair, impute, rescale, round for
display before analysis, or alter indicator algorithms to accommodate bad input.

The material's canonical `session_date` is represented as that same calendar
date at midnight UTC, as the existing research boundary expects. Do not convert
that label back to New York to derive a different date. It is not the source
publication, observation, aggregate-start, close, or availability instant.
Provider-daily aggregate research metadata must preserve provenance back to the
exact Polygon all-session, split-adjusted-not-dividend-adjusted semantics; the
research representation does not claim exchange-certified regular-hours bars.

### 13. Governed research result and downstream stop

The deterministic analyzer is an authorized-input computation engine, not
semantic permission authority. It runs unchanged with the fixed approved
Daily Technical analysis profile. Its indicator formulas, warm-up availability,
DEGRADED behavior, descriptive warnings, and snapshot identity remain governed
by ADR0027. Degraded analytics do not excuse failed Evidence governance.

The authoritative governed research operation preserves its technical snapshot
and an immutable governance/provenance envelope sufficient to resolve:

- exact Evidence artifact ID/version/fingerprint and retained material;
- the canonical lifecycle state/evaluation, its resolved constituents, complete
  history context, and authentic execution provenance permitting that use;
- canonical subject/mapping, approved policies, consumer/profile, and scope;
- research as-of, lifecycle knowledge/effective cutoffs, and actual production
  time;
- bridge/transformation identity/version and source material fingerprint;
- resulting research dataset fingerprint and exact row correspondence; and
- the existing `TechnicalAnalysisSnapshot` fingerprint and profile identity.

References must remain resolvable within the declared retention boundary;
detached hashes do not preserve lineage by themselves. A bare technical snapshot
is not sufficient proof of this governed operation. The derived dataset and
technical result are not new source Evidence; deterministic computation and
complete provenance do not reclassify them under ADR0035.

V0.79 stops here. It defines no bridge to Interpretation, Assessment, Strategy,
Agent exposure/execution, or autonomous trading. ADR0032's exact
`IntegrityCheckedDailyTechnicalResearchResult` input and closed policy tuple
remain mandatory for that separate Strategy application. The new result cannot
be cast, resealed, or relabeled as that input. A later legitimate composition
must satisfy those frozen contracts through separately approved architecture.

### 14. Stable refusals, not a permission boolean or message parser

The production operation must expose stable machine-readable refusal categories
with exact context and supporting findings. Multiple causes may coexist; a
structured refusal may retain all established causes without inventing results
for stages that did not execute. Human text supplements this contract and must
not be parsed to recover category semantics.

At minimum, categories must distinguish validation missing, validation failed,
unable to validate, admission missing, admission denied, inactive/terminal
validity, admission-time freshness failure, task-time freshness failure,
policy/profile mismatch, incomplete history, artifact/material mismatch,
historical instrument coverage failure, Evidence unavailable at requested
knowledge time, and consumer/use not authorized. Missing or unavailable
freshness support must be distinguishable from an established stale result.
Conversion/representation refusal must remain identifiable as a bridge failure,
not a newly invented lifecycle decision.

The representation may follow existing typed exceptions and structured-result
conventions; this ADR does not freeze an expansive enum or permanent CLI UX.
A canonical resolver refusal remains decisive and retains its original
constituents/findings. Structured reporting must not become a second evaluator
or translate unknown causes into an apparent pass. Refusal produces no governed
research success and triggers no automatic legacy acquisition fallback.

### 15. Retention, historical immutability, and future boundaries

Retain exact source material/vintage, artifacts, immutable lifecycle records,
execution provenance, mapping/policy versions, transformations, and result
references for the declared operational/audit lifetime. Fingerprints do not
replace those contents. A trusted in-memory implementation is acceptable if it
can establish complete relevant history and availability for the supported use.
After required material/history is lost, the operation must refuse claims it
can no longer substantiate. Ephemeral retention must not claim durable replay.

The complete-history interface must permit future durable retention without
changing these semantics. Storage technology, database schema, retention period,
and replay implementation remain separate decisions. New source vintages and
artifact revisions retain distinct versions; lifecycle changes append records.
Prior use is not erased by later correction, withdrawal, revocation, or outcome.

Temporal-Blind/Shadow Observer readiness means preserving provenance and time
boundaries only. Good process with a bad outcome may remain good process; bad
process with a good outcome may remain bad process. Future market outcome must
not redefine historical Evidence validity.

A future intelligent Agent may request approved governance/research capabilities
only through legitimate exposure. Intelligence, model name, capability discovery,
and mechanical orchestration never confer semantic issuance authority. Primary
intelligence may eventually be unified, but oversight must remain independent;
this is not a revision of ADR0034's currently frozen role boundaries or human
authority. ADR0033's allow-list and ADR0036's personal-context isolation remain
intact. This ADR adds no Agent capability.

The project's long-term trading-discipline North Star remains unchanged and is
non-normative for v0.79 implementation. This ADR grants no planning, capital, or
execution authority. ADR0033/ADR0034/ADR0036 remain unchanged; future autonomous
capital authority requires separate explicit ADR work.

## Relationship to existing ADRs

| ADR | Preserved contract and additive relationship |
| --- | --- |
| [0035](0035-evidence-foundation-architecture.md) | Reuses immutable Evidence, authority classification, validation taxonomy, append-only lifecycle, bitemporal precedence and canonical consumability; adds trusted production execution/history and exact use binding |
| [0037](0037-polygon-completed-daily-ohlcv-evidence-ingress.md) | Preserves the exact sole source/profile and construction membership; specifies the separately governed downstream work explicitly deferred to v0.79 |
| [0038](0038-polygon-completed-daily-evidence-material-and-candidate-construction.md) | Preserves every material/Candidate identity and construction rule; adds no lifecycle fields or new source version merely for a lifecycle transition |
| [0027](0027-daily-technical-analysis-foundation.md) | Reuses the pure completed-series analyzer, fixed profile, formulas, warnings and snapshot fingerprints |
| [0028](0028-daily-technical-research-application-cli-boundary.md) | Leaves its acquisition/CLI workflow intact and separate; never invokes it as the governed adapter or fallback |
| [0029](0029-daily-research-instrument-history-integrity.md) | Preserves legacy verified trimming; the first governed use adds whole-material historical coverage and no silent selection |
| [0032](0032-daily-technical-strategy-application-boundary.md) | Preserves exact verified input, policy tuple and application-owned downstream orchestration; no new composition into it |
| [0033](0033-market-intelligence-agent-boundary.md) | Preserves explicit capability exposure, platform authority, and Agent restrictions; no allow-list expansion |
| [0034](0034-market-intelligence-operating-system-architecture.md) / [0036](0036-personal-intelligence-boundary-architecture.md) | Preserves independent oversight, information isolation, canonical decision-support flow and human authority; adds no autonomous action path |

## Alternatives rejected or constrained

| Alternative | Decision and reason |
| --- | --- |
| Mutable Candidate-to-admitted `EvidenceArtifact` | Reject: lifecycle conclusions come from append-only records, never artifact mutation |
| New source artifact for every lifecycle transition | Reject: transitions refer to the exact source version; only a genuine revision or frozen terminal-reactivation requirement needs a new version |
| Parallel generic `ConsumabilityDecision` engine | Reject: full canonical evaluation and `is_consumable` already own the conclusion |
| Caller-issued self-consistent lifecycle records | Reject as production authority: correspondence cannot prove authorized execution, availability, or complete history |
| Construction approval as research approval | Reject: the exact v0.78 fingerprint authorizes Candidate construction only |
| Candidate material directly into completed-series research | Reject: trusted lifecycle resolution and use qualification must precede conversion |
| Legacy acquisition/verified workflow as bridge | Reject: it acquires data and applies legacy integrity semantics; only legitimate pure representation factories may be reused after qualification |
| Refetch prices after governance | Reject: new response/vintage breaks the authorized input correspondence |
| Silent trimming of unsupported historical rows | Reject: v0.79 requires all-row coverage; bounded construction or whole-use refusal is sufficient |
| Requested end or acquisition recency as freshness | Reject: neither proves the actual usable material is recent |
| Seven-day analyzer warning as Evidence policy | Reject: descriptive analysis and production Evidence freshness have separate authority |
| Direct Strategy/Agent integration through weakened or forged verified input | Reject: those exact contracts remain frozen and need separate legitimate composition |
| Database before the first slice | Reject as a prerequisite: trusted complete in-memory history is sufficient within an honest retention lifetime |

## Consequences

- The first production Evidence lifecycle becomes operable without duplicating
  its domain model or broadening source authorization.
- Authority, authenticity, complete history, and actual availability require
  explicit production guarantees beyond self-consistent record factories.
- Material-derived freshness and execution availability need a narrow additive
  integration; current artifact requested bounds are insufficient on their own.
- Some v0.78 Candidates are constructible yet unusable for research, including
  empty, stale, numerically unsupported, or historically uncovered material.
- The bridge preserves source precision and identifies the lossy research
  representation separately; existing indicators stay unchanged.
- Governed results carry additional provenance but do not automatically enter
  the frozen downstream Strategy/Agent pipeline or become source Evidence.
- A future implementation must verify positive full-chain use and adversarial
  refusal/chronology cases with mocked external boundaries. This checkpoint
  introduces no source, tests, exports, generated artifacts, or CLI behavior.

## Deliberately deferred questions and non-goals

The following remain **REQUIRED-BEFORE-IMPLEMENTATION** for the dependent
production boundary, rather than being silently chosen by this architecture:

1. Approve the concrete versioned production policy/profile definitions and
   identities: concern rules and source-quality support, admission/task
   freshness thresholds and calendar assumptions, validity issuance, exact
   consumer scope, and supported numeric/date conversion limits. Approval of
   this ADR alone does not approve arbitrary rules supplied later by callers.
2. Choose the narrow additive representation/integration for material-derived
   freshness support and actual execution/result availability, including how
   canonical full resolution checks its correspondence without weakening
   existing anchor and history semantics. Freeze the affected versioned
   contracts before implementing that integration.

There is no unresolved **BLOCKER** to this ADR proposal's semantic direction.
Python class decomposition, the typed refusal representation, trusted in-memory
history mechanics, and execution clock wiring are implementation choices within
these constraints, not additional lifecycle authorities.

**OPTIONAL-LATER** decisions include durable retention technology and lifetime,
generalized governed subset selection, and a legitimate composition into later
research/application layers. They are not prerequisites for this bounded slice.

This ADR deliberately does not freeze or implement a second Evidence source,
provider registry/framework, arbitrary global freshness thresholds, permanent
exchange-calendar technology, physical storage/database design, exact Python
class layout, permanent CLI UX, generalized subsets, strategy algorithms,
Eligible Trading Universe, GPT-6 Agent topology, Primary or RI implementation,
Shadow Observer, Trade Plan schema, scheduling, autonomous order execution, or
downstream Interpretation/Assessment/Strategy/Agent integration.
