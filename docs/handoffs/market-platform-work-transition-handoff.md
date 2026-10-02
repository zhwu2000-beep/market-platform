# Market Platform Work Transition Handoff

**Status:** FINAL TRANSITION HANDOFF  
**Purpose:** One-time project-context transfer from the historical Chat/Codex-centered workflow to ChatGPT Work  
**Current coordination baseline:** post-v0.85 runtime-validation closure  
**Implementation status of next architecture phase:** not started

---

## 1. Purpose of This Handoff

This document exists to transfer the accumulated operating context of Market
Platform into ChatGPT Work.

It is intentionally different from:

- an ADR;
- a release handoff;
- a runtime-test report;
- a roadmap;
- a changelog.

Those documents remain authoritative for their own scopes.

This handoff explains:

1. how the project evolved into its current architecture;
2. the engineering workflow that proved effective;
3. the important architectural lessons already learned;
4. the boundaries that must continue to hold;
5. the current exact project position;
6. the intended future direction;
7. how Work and Codex should cooperate from this point onward.

Work must not treat this document as a replacement for repository inspection.

Its purpose is to provide the historical and operational mental model needed to
interpret the authoritative repository correctly.

---

## 2. Authority Model

When information conflicts, use the following precedence:

1. released repository state;
2. accepted ADRs;
3. frozen implementation and tests;
4. release handoffs and accepted runtime-test evidence;
5. alignment reviews;
6. current roadmap;
7. this transition handoff;
8. conversational recollection.

Conversation history is useful context but is not the engineering system of
record.

Work should independently inspect the repository before making architecture,
implementation, release, or status conclusions.

---

## 3. Current Repository / Release Position

The released v0.85 implementation remains frozen.

v0.85 release merge:

`ba58b419d637be81f6f0a0887a99282175160132`

v0.85 annotated tag object:

`c760531c1abe80b9dfed8663c79823ced8fb5fe9`

`v0.85.0^{}` resolves to:

`ba58b419d637be81f6f0a0887a99282175160132`

The v0.85 post-release handoff/main commit before the Work documentation set was:

`541cfa0b659947760279ec77e6f639871c7cbca5`

The documentation/bootstrap commit immediately preceding this transition
handoff is:

`60c2f0331d2d5bc249405f6a4c967ec5a665d2c4`

This is the repository baseline from which this transition handoff was prepared.
The commit that ultimately adds this handoff will advance `main` beyond this
baseline.

Do not treat the SHA recorded here as a permanent current-HEAD pointer.

For the current repository position, Work must inspect Git directly. Release
identity continues to come from the frozen release merge/tag described above.

At the point this transition handoff was prepared:

- v0.85 implementation was released and frozen;
- v0.85 runtime validation was complete;
- v0.85 required no reopening;
- no runtime acceptance item remained;
- the next architecture phase had not begun implementation.

The release tag intentionally remains on the v0.85 release merge rather than on
later post-release documentation commits.

---

## 4. Where the Project Came From

Market Platform evolved incrementally rather than being designed as one large
autonomous-trading system from the beginning.

The important architectural progression was approximately:

**Market-data/provider foundation**

→ provider selection and fallback

→ normalized completed-daily market data

→ instrument identity/mapping

→ evidence and provenance

→ validation/admission/governance boundaries

→ technical observation

→ Radar

→ meaningful-change detection

→ passive Candidate

→ Candidate delivery/recovery

→ governed research-escalation readiness

→ authentic READY boundary

The project deliberately separated these concerns instead of allowing a market
signal to flow directly into strategy or execution.

That separation is now one of the project's most important durable properties.

---

## 5. Important Historical Milestones

This section is intentionally an orientation summary rather than an exhaustive
version changelog.

Exact historical facts should be read from the relevant handoffs, ADRs, Git
history and tests.

### Daily technical foundation

By the v0.71-v0.73 period, the project had established the completed-daily
technical-analysis / interpretation architecture and the necessary deterministic
data-processing behavior.

This created a governed technical observation layer rather than an ad-hoc
indicator script.

### Strategy foundation

v0.74 established Strategy as an explicit architectural domain rather than
allowing technical observations to become implicit trading instructions.

A central long-term distinction became:

**observation is not strategy**

and:

**strategy is not execution authority**

### Radar evolution

Subsequent versions developed Radar into the layer responsible for observing
market state and identifying meaningful changes without granting downstream
trading authority.

Radar became responsible for questions such as:

- Has a completed market observation changed meaningfully?
- Is that change eligible to become a Candidate?
- Can that Candidate be retained and recovered truthfully?

Radar was deliberately not allowed to become an implicit Strategy engine.

### v0.84 — Radar Candidate Escalation Foundation

v0.84 established the Candidate and delivery/recovery boundary.

The resulting conceptual chain included:

Radar observation

→ meaningful change

→ passive Candidate

→ Prepared

→ Accepted

→ eligible Decision

→ Pending

Important properties included:

- Candidate identity preservation;
- recoverability;
- delivery-store ownership;
- restart recovery;
- no automatic downstream research activation.

v0.84 was formally released and frozen before v0.85 work began.

### v0.85 — Governed Research Escalation Readiness

v0.85 added the next boundary:

Can a retained Radar Candidate be shown to correspond exactly to governed,
current, task-appropriate market material strongly enough to return a bounded
readiness assessment?

The answer is represented as:

- READY;
- BLOCKED;
- REFUSED.

v0.85 intentionally stops there.

READY does not invoke research.

READY does not invoke Strategy.

READY does not invoke Execution.

READY is not a bearer token.

---

## 6. The v0.85 Conceptual Chain

The final v0.85 conceptual chain is:

Radar observation

→ meaningful change

→ Candidate

→ recoverable Pending

→ trusted Pending resolution

→ governed material

→ exact Candidate/material correspondence

→ current task and governance evaluation

→ bounded readiness assessment

→ STOP

The word **STOP** is important.

The v0.85 architecture deliberately did not implement:

READY

→ automatic research

or:

READY

→ Strategy

or:

READY

→ Execution.

That separation must not be accidentally erased in future versions.

---

## 7. v0.85 Development Structure

v0.85 was developed in bounded slices rather than one large implementation.

### Slice 1

Governed Research Escalation Readiness contract.

This established the non-activating readiness model and basic boundaries.

### Slice 2

Trusted Pending resolution.

This connected readiness to retained/recoverable Candidate delivery authority.

### Slice 3

Governed material / task-context resolution and exact correspondence.

A significant correctness issue discovered here was precedence between:

- ordinary missing/stale governance; and
- integrity contradictions.

The frozen behavior requires integrity contradictions to outrank ordinary
missing/stale conditions where the contract specifies this.

In practical terms:

ordinary absent/stale governance may result in:

**BLOCKED**

but an actual integrity contradiction may require:

**REFUSED**

even when an ordinary missing condition also exists.

### Slice 4

Final bounded readiness composition.

This completed the v0.85 readiness assessment without introducing research or
execution activation.

---

## 8. One of the Most Important v0.85 Lessons: Time Is Evidence

A major architecture lesson came from same-day / chronology analysis.

The project discovered that a completed market session may be valid for Radar
observation while an already-completed earlier provider response cannot simply
be retroactively inserted into a new Construction execution.

The system must preserve real chronology.

Invalid workarounds include:

- backdating;
- rewriting request timestamps;
- rewriting receipt timestamps;
- pretending a later execution owned an earlier acquisition;
- removing rows to force an older scope;
- representing a later refetch as the original response;
- allowing elapsed wall time to retroactively legitimize old provenance.

This produced an important supported architecture:

### Path D — later independent matching acquisition

A Candidate may originate from acquisition **X**.

A later governance/Construction execution may independently acquire **Y**.

X and Y do not need to share:

- provider request identity;
- HTTP receipt identity;
- acquisition occurrence identity.

But they must establish exact required semantic/material correspondence under
their own truthful provenance.

This means the platform can legitimately say:

> Radar saw this market state in X.  
> Governance later independently acquired Y.  
> Y exactly corresponds to the Candidate's governed market content.

It must never say:

> Y was actually X

when it was not.

---

## 9. Evidence and Provenance Philosophy

The project has repeatedly chosen provenance correctness over convenient
shortcuts.

Durable principles include:

- Evidence must be truthful.
- Provenance must be auditable.
- Chronology must reflect what actually occurred.
- Identity must not be rewritten during recovery.
- A later refetch must not be disguised as an earlier acquisition.
- Recovery should preserve authority rather than reconstructing a convenient
  approximation.
- Validation cannot silently upgrade unknown provenance into trusted provenance.

When a required truth cannot be established, the preferred behavior is
fail-closed.

---

## 10. Validation, Admission and Readiness Are Different

These concepts must remain separate.

**Validation != Admission**

Validation determines whether something satisfies validation concerns.

It does not automatically grant admission.

**Admission != Readiness**

An admitted governed material does not automatically mean the exact Candidate,
task, freshness, correspondence and context requirements are currently satisfied.

**Readiness != Research Authority**

A READY assessment says that the bounded readiness contract passed for the
evaluated context.

It does not grant downstream invocation authority.

The permanent wording established during runtime validation is:

**READY IS DESCRIPTIVE, CONTEXT-BOUND, AND NON-AUTHORITATIVE.**

Future architecture must preserve the substance of this rule even if terminology
evolves.

---

## 11. v0.85 Runtime Validation

v0.85 received extensive post-release real-data runtime validation.

The authoritative detailed record is:

`docs/test-evidence/v0.85-runtime-test-closure.md`

The important outcome is:

**V0.85 RUNTIME VALIDATION COMPLETE WITH EXPECTED OCCURRENCE VARIANCE**

v0.85 remains:

- valid;
- released;
- frozen;
- not reopened.

Remaining v0.85 runtime acceptance items:

**none**

---

## 12. Real-Market Evidence Obtained During Runtime Validation

Runtime validation was not limited to synthetic fixtures.

Real Polygon completed-daily data was used.

The project demonstrated:

- stable acquisition fingerprints across repeated real acquisitions where market
  content was unchanged;
- deterministic EMA calculations;
- deterministic frozen-input Radar behavior;
- authentic meaningful-change transitions;
- Candidate production;
- delivery and recovery;
- independent-governance acquisition correspondence;
- authentic READY;
- BLOCKED;
- REFUSED;
- precedence behavior;
- repeated semantic readiness stability.

A particularly useful current-session event was found in TSLA.

The released EMA8/EMA20 semantics produced:

2026-09-30:

`ABOVE`

2026-10-01:

`BELOW`

This yielded an authentic current-session transition rather than a fabricated
fixture.

That transition was used to exercise the live Candidate-to-readiness path.

---

## 13. Authentic Live v0.85 READY

The runtime path successfully demonstrated:

real market data X

→ Radar

→ STATE_TRANSITION

→ meaningful_change = true

→ Eligible Candidate

→ Prepared

→ Accepted

→ eligible Decision

→ Pending

→ independent acquisition Y

→ Construction

→ Validation

→ admission Freshness

→ Admission

→ ACTIVE Validity

→ exact task Freshness

→ Qualification

→ Bridge

→ READY

X and Y matched the required normalized historical content exactly while
preserving independent honest provenance.

No downstream research, Strategy or execution activation occurred.

---

## 14. Fail-Closed Runtime Evidence

The runtime tests also exercised negative controls.

### Missing required governance/context

The system returned:

**BLOCKED**

This demonstrated that ordinary missing governance does not silently become
authority.

### Integrity contradiction

A contradictory context returned:

**REFUSED**

even when an ordinary missing condition was also present.

This demonstrated the intended integrity-precedence behavior.

The project should continue to distinguish:

cannot currently prove enough

from:

evidence says the context is internally contradictory.

---

## 15. Readiness Repeatability and Occurrence Semantics

One late runtime-test lesson is important for future Work reviews.

Initially, the acceptance test incorrectly assumed repeated readiness assessments
should reuse exactly the same Qualification and Bridge occurrence identities.

Repository inspection established that this is not the released contract.

Each successful readiness assessment legitimately performs a new Qualification
evaluation and publishes a new Bridge occurrence.

Therefore repeated assessments may produce new:

- Qualification execution IDs;
- Qualification sequences;
- Bridge execution IDs;
- Bridge sequences;
- operation timestamps;
- occurrence fingerprints.

This is expected occurrence variance.

The correct repeatability invariant is semantic.

For the same retained authority and fixed context, stable semantics must remain
stable while legitimate append-only evaluation occurrences may differ.

The final single-process acceptance demonstrated:

- five sequential assessments;
- five READY results;
- all five concern families PASSED every time;
- empty unperformed checks every time;
- 67/67 semantic checks passed;
- Qualification history grew exactly +5;
- Bridge history grew exactly +5;
- sequences remained coherent;
- old history remained an unchanged prefix;
- source authority was not rewritten;
- retained task Freshness remained stable;
- no provider call occurred during the five-assessment loop;
- no Candidate regeneration occurred;
- no Construction occurred during the loop;
- no Technical/research/Strategy/execution activation occurred.

This distinction matters:

**append-only assessment occurrence creation is not source-authority mutation.**

---

## 16. Another Important Runtime Lesson: Process Ownership Matters

Some governance owners in the current architecture are in-memory owners.

A TEMP JSON snapshot of such state is diagnostic evidence.

It is not automatically importable trusted authority.

A runtime test originally attempted to continue five-run assessment validation
after the process that owned Qualification/Bridge state had exited.

The test correctly stopped.

The project deliberately did not reconstruct trusted authority from diagnostic
JSON.

The final test was therefore run in one continuous Python process:

create/authenticate owners

→ retain owners

→ perform five assessments

→ inspect histories

→ perform final assertions

→ generate report

before the owner process exited.

Future tests must continue to distinguish:

**diagnostic serialization**

from:

**trusted runtime ownership**.

---

## 17. Engineering Workflow That Worked

The project converged on a disciplined bounded-Slice workflow.

The preferred development loop is:

### 1. Architecture / scope definition

Before implementation:

- define the boundary;
- identify owners;
- define what authority is and is not being granted;
- identify non-goals;
- define fail-closed behavior;
- identify provenance/time semantics;
- determine the smallest coherent Slice.

### 2. Codex implementation

Codex performs the bounded implementation.

The task should explicitly identify:

- exact baseline;
- allowed files/scope;
- prohibited changes;
- tests;
- static analysis;
- expected report;
- whether commit is authorized.

### 3. Focused validation

Run the smallest tests that meaningfully validate the Slice first.

Avoid automatically running the entire repository suite after every tiny change.

The project has a substantial suite and full validation can be expensive.

### 4. Independent review

After implementation, perform a review that is independent from the implementing
reasoning.

Review:

- architecture compliance;
- scope;
- fail-closed semantics;
- provenance;
- temporal behavior;
- tests;
- unexpected authority expansion.

### 5. Freeze the Slice

Once accepted, treat the Slice as frozen before beginning the next Slice.

Do not casually mutate previously accepted behavior while implementing a later
Slice.

### 6. Release closure

Before release:

- inspect exact diff;
- perform appropriate release validation;
- conduct release review;
- perform preflight;
- merge using the established convention;
- create annotated release tag;
- write handoff;
- push and verify refs.

### 7. Runtime acceptance

Where architecture depends on real provider behavior, timing, persistence or
process semantics, supplement unit tests with bounded real runtime evidence.

### 8. Alignment review

After the implementation is frozen, compare:

**planned direction**

against:

**delivered reality**

before deciding the next Slice.

### Close Known Small Gaps Before Moving On

The project should not rely on the user remembering small deferred cleanup,
clarifications, validation gaps or documentation corrections later.

When a problem is already known and can be resolved now in a bounded, safe and
low-cost way, prefer resolving it before closing the current Slice, review,
handoff or commit.

Examples include:

- documentation ambiguity;
- missing handoff context;
- stale status;
- small validation omissions;
- known reference/link problems;
- unrecorded architecture conclusions;
- cleanup required to make the next project state unambiguous.

"Not a blocker" must not automatically mean "leave it for later."

Do NOT interpret this rule as permission to pull future features into the current
Slice.

Deferral is appropriate when:

1. the work genuinely depends on future information, architecture or runtime
   conditions; or
2. doing it now would materially expand the current bounded scope.

When something must be deferred, do not rely on conversational memory.

Record explicitly:

- what is deferred;
- why it is deferred;
- where it is tracked;
- what condition or future Slice should revisit it.

Work should actively help the user identify and close these small known gaps,
because the user should not be expected to remember every engineering follow-up
manually.

---

## 18. Release / Git Lessons

The Codex sandbox has previously been unable to mutate `.git`.

The observed Windows sandbox identity could read the repository but creation of
Git lock files failed.

Therefore:

- Codex can perform read-only Git inspection;
- Codex can prepare repository file changes;
- Git metadata mutation may need to be performed manually by the user in normal
  PowerShell.

Do not treat this as a repository defect.

Do not attempt unsafe permission workarounds merely so Codex can perform Git
metadata writes.

The established release convention has included:

- reviewed frozen feature state;
- explicit non-fast-forward merge where required by the release flow;
- annotated release tag on the release merge;
- post-release handoff/documentation commits may occur after the tagged release;
- verify local and remote refs afterward.

Release tags should not be silently moved to later documentation commits.

---

## 19. Testing Lessons

Several testing practices are now part of the project's operating culture.

### Prefer staged validation

Use focused tests first.

Escalate validation breadth according to architectural risk.

Do not use a multi-hour full suite merely as a substitute for understanding the
changed boundary.

### Distinguish harness failure from product failure

One v0.85 validation attempt failed because a broad socket monkeypatch also
blocked local Windows asyncio behavior.

That was a test-harness problem, not a product defect.

Correct the harness and rerun rather than misclassifying the architecture.

### Respect provider limits

Real-data tests should use conservative pacing.

Retries must preserve truthful acquisition semantics.

### Never fabricate a positive runtime condition

If no authentic current crossover exists:

stop and record that the acceptance condition is unavailable.

Do not:

- change thresholds;
- broaden the universe secretly;
- synthesize OHLCV;
- fabricate a Candidate.

The eventual TSLA transition was used only when a genuine eligible transition
became available.

---

## 20. Reuse Before Reinvention

Market Platform does not require commodity functionality to be rebuilt from
scratch when a mature capability already exists.

The preferred principle is:

**reuse mature capabilities where appropriate, but keep Market Platform's
authority model platform-owned.**

External libraries, provider APIs, SDKs, services and established internal
components may be reused when they can be placed behind explicit contracts and
their behavior can be governed appropriately.

Reuse must not outsource or bypass:

- Evidence ownership;
- provenance;
- identity;
- chronology;
- governance;
- fail-closed semantics;
- Strategy authority;
- execution authority;
- auditability.

A useful distinction is:

**external or reusable components may provide capability; Market Platform owns
the authority boundary around that capability.**

This principle has already been applied in the project.

Examples include:

### External mature capability

Real completed-daily market data has been obtained through the existing
Polygon/Massive provider capability rather than attempting to build an exchange
market-data infrastructure from scratch.

The provider supplies market data capability.

Market Platform remains responsible for:

- acquisition identity;
- receipt chronology;
- normalization;
- Evidence/provenance;
- Construction;
- Validation;
- Admission;
- Qualification;
- downstream authority semantics.

### Existing internal capability

Later versions have repeatedly reused established internal abstractions rather
than rebuilding them for every new Slice.

Examples include reuse of:

- completed-daily acquisition;
- instrument identity and mapping;
- normalized numeric/canonical representations;
- Evidence and provenance conventions;
- validation/governance owners;
- technical-analysis components;
- fingerprint/projection conventions;
- existing application/service protocols;
- Candidate delivery/recovery infrastructure;
- Construction, Qualification and Bridge capabilities.

New architecture should prefer composition and explicit adapters over duplicate
implementations when an existing capability already satisfies the required
contract.

### Future third-party reuse

Future architecture may legitimately reuse mature external capabilities such as:

- broker SDKs;
- execution APIs;
- news/event feeds;
- technical-analysis libraries;
- portfolio/risk libraries;
- retrieval systems;
- event parsers;
- other specialized infrastructure.

However, integrating an external component must not automatically grant that
component Market Platform authority.

For example:

a broker SDK may provide order-submission capability,

but it must not independently decide that a Strategy is authorized to execute.

Similarly:

a news parser may produce structured event information,

but its output must still enter Market Platform through an explicit provenance
and governance boundary before it gains downstream significance.

Before implementing a commodity subsystem internally, Work should therefore ask:

1. Does a mature capability already exist?
2. Can it be isolated behind a clear adapter or contract?
3. Can provenance and identity be preserved?
4. Can failure behavior remain fail-closed?
5. Does reuse accidentally transfer authority outside Market Platform?
6. Is building internally actually necessary for correctness, control or
   architecture?

The project should avoid both extremes:

**not-invented-here engineering**

and:

**uncritical dependency outsourcing**.

Reuse should reduce unnecessary engineering while preserving the platform's
architectural control.

---

## 21. Durable Architectural Boundaries

The complete durable-boundary document is:

`docs/project/market-platform-boundaries.md`

The most important principles are summarized here.

### Evidence / provenance

- immutable and auditable;
- truthful chronology;
- no backdating;
- no timestamp rewriting;
- no refetch represented as the original acquisition;
- recovery preserves identity/provenance.

### Governance

- Validation != Admission;
- Admission != readiness;
- readiness != research authority;
- READY is descriptive, context-bound and non-authoritative.

### Radar

Radar observes and detects meaningful change.

Radar may produce a passive Candidate.

Candidate != Strategy.

### Strategy / Execution

Strategy authority must remain separate from execution authority.

Execution should ultimately be bounded and mechanically constrained.

Unknown or unsupported cases should pause or escalate rather than invent
authority.

### Shadow Observer

Shadow Observer is intended as an ex-ante process auditor.

It evaluates a historical decision using only the information legitimately
available at that decision time.

It must not:

- optimize by hindsight;
- search history for perfect tops/bottoms;
- label an earlier decision wrong merely because a later outcome was poor.

Its purpose is to identify process failures such as:

- missing evidence;
- incomplete observation;
- inconsistent reasoning;
- unsupported assumptions;
- discipline violations;
- boundary violations.

---

## 22. Why the Project Has Not Jumped Directly to Autonomous Trading

The long-term project goal includes substantial automation and potentially
autonomous execution.

However, the architecture intentionally builds the authority chain in stages.

The project is trying to prevent a common failure mode:

market signal

→ model opinion

→ immediate trade

without clear authority, provenance, risk containment or recoverability.

The expected long-term chain is closer to:

Radar

→ Research

→ Strategy

→ Risk Governor

→ Execution Agent

→ Shadow Observer / audit

Each boundary should define:

- what information it receives;
- what authority it holds;
- what it cannot do;
- how identity/provenance is preserved;
- how it fails closed;
- how it is interrupted/recovered.

---

## 23. Current Forward Architecture Direction

The next planned architecture area is:

### Monitoring Topology

Implementation has NOT begun.

The exact next version number / Slice structure should be decided by Work after
repository review.

Do not assume that a previously discussed version number is already frozen.

The intended topology has several parts.

---

## 24. Core Radar

Core Radar is intended for a relatively small user-selected set of high-interest
instruments.

Core instruments may receive:

- persistent monitoring;
- richer maintained state;
- faster reassessment;
- higher-frequency observation where the underlying information actually
  changes;
- more immediate escalation into deeper processing.

Important efficiency rule:

A completed-daily indicator does not become more informative merely because it is
recomputed every few minutes.

Completed-daily signals should remain governed by completed sessions.

Higher-frequency monitoring should later focus on information that can genuinely
change intraday, such as:

- price;
- volume;
- intraday technical state;
- volatility;
- events;
- news;
- other explicitly governed real-time inputs.

---

## 25. Broad Sentry

Broad Sentry is intended to monitor a much larger universe at lower cost and
lower observation density.

Its purpose is not to continuously run expensive research over the whole market.

Possible future triggers include:

- large upward price move;
- large downward move;
- gap;
- abnormal volume;
- volatility expansion;
- breakout;
- breakdown;
- material event;
- other explicitly defined anomaly conditions.

A trigger may elevate an instrument temporarily.

---

## 26. Temporary Escalation

A future architecture should define a state transition similar to:

Broad monitoring

→ qualifying trigger

→ temporary escalation

→ richer monitoring / Radar attention

→ possible deeper research consideration

This needs explicit owner and lifecycle semantics.

Escalation must not become an accidental permanent upgrade.

---

## 27. Cooldown and De-escalation

The monitoring topology needs explicit rules for:

- escalation entry;
- escalation persistence;
- cooldown;
- de-escalation;
- re-escalation;
- repeated-trigger behavior;
- restart/recovery;
- state identity.

Without this, a broad-universe alert system can gradually turn into uncontrolled
high-cost permanent monitoring.

The future architecture should make escalation reversible and auditable.

---

## 28. Future Governed Research Invocation

v0.85 proves readiness.

It does not invoke research.

A future version may define the actual governed transition from:

READY

to:

Research invocation.

That boundary should likely consider:

- invocation identity;
- authority revalidation;
- current task/context;
- freshness;
- interruption;
- restart recovery;
- idempotence;
- provenance;
- duplicate invocation behavior;
- failure behavior;
- cancellation;
- fail-closed semantics.

Do not implement this merely by adding:

`if ready: run_research()`.

That would erase the authority boundary v0.85 was created to establish.

---

## 29. Future Bounded Autonomous Execution

Long-term direction includes allowing a limited allocation of capital to operate
autonomously.

The intended concept is:

**autonomy inside a strict risk envelope**

rather than unrestricted trading authority.

Potential future initial constraints include:

- dedicated small capital pool or account;
- allowlisted instruments;
- maximum position size;
- maximum concurrent positions;
- maximum total exposure;
- per-trade loss limit;
- daily loss limit;
- no unrestricted leverage;
- no naked options initially;
- explicit unsupported-case escalation;
- global kill switch.

These are planning concepts, not current implementation.

Do not mark them IMPLEMENTED or VALIDATED.

---

## 30. Human Re-entry Remains Important

The long-term goal is not to eliminate all human intervention.

A useful division is expected to be:

standard, explicitly governed cases

→ automated handling

out-of-model / unsupported / contradictory cases

→ stop or escalate for human review

The platform should not invent behavior merely because full autonomy is a future
goal.

---

## 31. Work's New Role

ChatGPT Work now becomes the main project-coordination environment.

Work should act as:

- long-running project coordinator;
- architecture/planning layer;
- roadmap steward;
- independent reviewer;
- runtime-test planner;
- release-evidence reviewer;
- cross-document context layer.

Work should not silently become the primary code-editing agent when the task is
better handled by Codex.

---

## 32. Codex's Role

Codex remains the engineering implementation environment.

Use Codex for:

- source implementation;
- test implementation;
- bounded repository changes;
- static analysis;
- focused validation;
- diff inspection;
- engineering commits when permitted;
- release preparation tasks.

Work should define the problem and boundary.

Codex should implement that bounded scope.

Work should then independently inspect the actual result.

---

## 33. Work Must Not Depend on Codex Conversation History

Codex conversation history is not the project authority.

Important architecture conclusions must land in repository documents.

When a Codex task completes, Work should inspect:

- actual Git state;
- changed files;
- tests;
- handoff;
- evidence;
- commits.

Do not accept:

"Codex said it completed X"

as sufficient evidence that X exists.

---

## 34. The Work ↔ Codex Operating Loop

The preferred loop from this point onward is:

### Work

read current repository authority

→ inspect roadmap

→ inspect boundaries

→ inspect status ledger

→ inspect latest handoffs/evidence

→ reason about next architecture problem

→ define a bounded Slice

→ decide whether implementation is required

If implementation is required:

Work should explicitly tell the user to switch to Codex.

### Codex

implement the bounded Slice

→ run focused tests

→ run static analysis as appropriate

→ inspect diff

→ report exact state

→ commit/freeze when authorized

→ update handoff/evidence as required

### Work

return to repository

→ independently inspect delivered implementation

→ compare it with planned direction

→ identify drift/deferred work/new learning

→ write/update alignment review

→ update status ledger

→ decide the next Slice

---

## 35. Codex Handoff Format

When Work asks the user to switch to Codex, the handoff should normally state:

- whether a new Codex session should be opened;
- model;
- reasoning level;
- exact baseline;
- exact task scope;
- allowed changes;
- prohibited changes;
- validation requirements;
- expected final report;
- commit/push authorization.

Current user preference:

**GPT-6.1 Sol**

General guideline:

Routine bounded implementation:

**Medium reasoning**

Architecture-critical work, complex reviews, runtime acceptance, release-critical
work:

**High reasoning**

Do not turn this into an inflexible rule; use the task's real difficulty.

---

## 36. Documentation Model Going Forward

The project now uses three complementary tracks.

### Track 1 — Planned Direction

Primary documents:

`docs/project/market-platform-roadmap.md`

`docs/project/market-platform-boundaries.md`

These describe intended direction and durable constraints.

Do not rewrite historical planning merely so it appears to match later
implementation.

### Track 2 — Delivered Reality

Primary location:

`docs/handoffs/`

Handoffs describe what was actually delivered:

- implementation;
- commits;
- tests;
- limitations;
- deferred scope;
- release facts.

### Track 3 — Alignment Review

Primary location:

`docs/reviews/`

**After every frozen implementation Slice, Work must perform an alignment
review.**

A larger milestone-level alignment review may additionally be performed when
useful.

Compare:

planned direction

vs

delivered reality.

A typical alignment review should examine:

- planned objective;
- delivered implementation;
- completed requirements;
- partial requirements;
- deferred requirements;
- unexpected additions;
- architecture-boundary compliance;
- scope drift;
- new information learned;
- roadmap impact;
- next-Slice recommendation.

The purpose is not to force the project to obey an obsolete plan.

The purpose is to distinguish:

**intentional architecture evolution**

from:

**accidental scope drift**.

---

## 37. Status Ledger Discipline

The current compact project-state index is:

`docs/project/market-platform-status-ledger.md`

Use statuses such as:

- PLANNED
- IN_PROGRESS
- IMPLEMENTED
- VALIDATED
- RELEASED
- DEFERRED
- SUPERSEDED
- CANCELLED

Do not mark:

IMPLEMENTED

when there is only a plan.

Do not mark:

VALIDATED

without accepted validation evidence.

Do not mark:

RELEASED

without release evidence.

Historical entries should remain visible when useful rather than being rewritten
to make the project look cleaner than it actually was.

---

## 38. Current Starting Point for Work

Work should begin from the following facts:

### Complete

v0.85 implementation:

**released and frozen**

v0.85 runtime acceptance:

**complete**

v0.85 reopening:

**not required**

Remaining v0.85 runtime acceptance:

**none**

Work bootstrap documentation:

**created**

Roadmap:

**created**

Durable boundaries:

**created**

Status ledger:

**created**

### Not started

Monitoring Topology implementation:

**not started**

Core Radar implementation:

**not started**

Broad Sentry implementation:

**not started**

Temporary Escalation implementation:

**not started**

Cooldown/de-escalation implementation:

**not started**

Governed research invocation:

**not started**

Bounded autonomous execution:

**not started**

Shadow Observer implementation:

**not started**

Do not collapse "discussed" into "implemented".

---

## 39. What Work Should Read First

At the start of the first serious Work session, read:

1. `docs/project/market-platform-work-bootstrap.md`
2. `docs/project/market-platform-roadmap.md`
3. `docs/project/market-platform-boundaries.md`
4. `docs/project/market-platform-status-ledger.md`
5. `docs/test-evidence/v0.85-runtime-test-closure.md`
6. this transition handoff
7. latest relevant release handoffs
8. relevant ADRs
9. actual source/tests when architecture questions depend on them

Do not attempt to understand the current system from this transition handoff
alone.

---

## 40. First Work Objective

The first Work objective should NOT be:

"implement v0.86."

The first objective should be:

**establish an accurate repository-grounded model of the current system and then
define the next bounded Monitoring Topology architecture Slice.**

Work should determine:

- what existing Radar abstractions can legitimately be reused;
- what monitoring responsibilities belong outside Radar;
- what state must be persistent;
- how Core and Broad monitoring identities differ;
- how escalation authority works;
- how cooldown/de-escalation works;
- what data cadence belongs to each signal family;
- what is deliberately deferred;
- whether a new ADR is required.

Only after that architecture is sufficiently bounded should Work issue a Codex
implementation handoff.

---

## 41. Questions the Next Architecture Should Answer

Before implementation, the Monitoring Topology design should answer at least:

1. What makes an instrument Core versus Broad?
2. Who owns that classification?
3. Is classification static, dynamic, or both?
4. What state survives restart?
5. What constitutes an escalation trigger?
6. Are triggers observations, authority, or both?
7. What transitions an instrument into elevated monitoring?
8. What transitions it out?
9. What is the cooldown model?
10. How does re-escalation behave?
11. What happens if multiple triggers overlap?
12. Which observations are completed-session-only?
13. Which observations can legitimately run intraday?
14. How are provider cost and rate limits controlled?
15. How are duplicate observations suppressed?
16. How is provenance retained across escalation?
17. What is recoverable after process restart?
18. Does escalation create a Candidate or merely alter observation intensity?
19. Where does future research invocation enter?
20. What remains explicitly out of scope?

The architecture does not need to answer every future trading-system question in
the first Slice.

It does need to avoid creating an ambiguous authority boundary.

---

## 42. Principles for Future Architecture Evolution

Future Work may change the roadmap when new information justifies it.

However, changes should be explicit.

When a new discovery changes the intended design:

1. identify the new information;
2. identify which assumption changed;
3. determine whether an ADR is affected;
4. determine whether a boundary is affected;
5. update the roadmap prospectively;
6. preserve the historical plan;
7. explain the change in the alignment review.

This prevents accidental architecture drift while still allowing the project to
learn.

---

## 43. Things Work Should Avoid

Do not:

- jump directly from READY to research without a governed invocation boundary;
- collapse Candidate into Strategy;
- collapse Strategy into Execution;
- treat a later market outcome as proof that an earlier process decision was
  irrational;
- backdate evidence;
- silently refetch data and represent it as an earlier acquisition;
- repair missing authority by editing timestamps;
- treat diagnostic JSON as trusted runtime authority without an authentic import
  contract;
- fabricate runtime market conditions merely to pass acceptance;
- run the full test suite reflexively when focused validation is sufficient;
- treat a test-harness failure as a product defect without investigation;
- treat conversational recollection as stronger than repository evidence;
- silently broaden implementation scope;
- mark future autonomous-trading concepts as implemented.

---

## 44. Things Work Should Preserve

Preserve:

- explicit authority boundaries;
- truthful provenance;
- exact identity;
- recovery semantics;
- fail-closed behavior;
- deterministic processing where expected;
- separation of observation/research/strategy/execution;
- bounded Slices;
- independent review;
- evidence-backed status;
- architecture history;
- human re-entry for unsupported cases.

These properties are more important than maximizing short-term feature speed.

---

## 45. Current Long-Term Vision

The project is moving toward a system capable of:

- continuously observing selected markets;
- cheaply watching a broader universe;
- detecting meaningful changes and anomalies;
- escalating observation intelligently;
- initiating governed research;
- forming strategies through an explicit authority boundary;
- applying an independent risk envelope;
- executing bounded actions;
- auditing decision quality ex ante.

The goal is not merely an automated trading bot.

The intended end state is a layered market decision system in which:

**information quality, provenance, authority, risk, execution and audit remain
distinguishable.**

---

## 46. Transition Decision

The Chat/Codex-centered phase that carried the project through v0.85 is complete.

Project coordination now transitions to Work.

This does not invalidate previous conversations.

It changes where durable project coordination happens.

From this point forward:

**Work is the coordinating architecture/review layer.**

**Codex is the bounded implementation layer.**

**The repository is the engineering authority.**

---

## 47. Immediate Next Step

After reading the repository documents listed above, Work should produce a
repository-grounded summary of:

1. the currently released/frozen system;
2. the major authority boundaries;
3. the validated v0.85 runtime state;
4. the current roadmap;
5. the first unresolved Monitoring Topology architecture questions.

Then stop.

Do not begin implementation.

The next implementation Slice should be defined only after that review.

---

## 48. Final Transition State

At transition:

- v0.85 is released;
- v0.85 is frozen;
- v0.85 runtime validation is complete;
- no v0.85 runtime acceptance remains;
- READY remains non-authoritative;
- no research activation has been added;
- no autonomous execution has been added;
- Work documentation exists;
- Monitoring Topology is the next planned architecture area;
- implementation of that next area has not begun.

This is the starting state from which Work should continue Market Platform.
