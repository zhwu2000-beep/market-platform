# ADR 0051: Recoverable Radar Source Publication and Candidate Delivery Boundary

## Status

Accepted for v0.84 Candidate / Escalation Boundary.

This ADR accepts the **Recoverable Radar Source and Candidate Delivery Foundation**
as the architecture checkpoint for the second v0.84 Candidate / Escalation slice.
The decisions below are normative. This is a **NON-ACTIVATING v0.84 architecture
slice**: the recovery/delivery foundation is not yet implemented. Implementation
remains a future slice; architecture acceptance does not create runtime capability.
Current production single-symbol and batch paths remain unchanged and non-activating.

## Context and inspected baseline

Local inspection before drafting established:

- Branch: `feature/v0.84.0-candidate-escalation`.
- HEAD and local origin feature:
  `7d2d6e7ddcab8c2874a1cf7c3db768877327e4a5`.
- HEAD subject: `feat: add passive Radar Candidate decision boundary`.
- Parent: `089d93651e1dba6781007fc623785056fc95547c`.
- `main` and local `origin/main`:
  `b13b5a044909b8085b3bf54ebdfcafba3f213a5c`.
- Clean worktree/index and no untracked files before drafting. Remote-tracking
  refs were inspected locally without fetching or network requests.
- ADR0050 was the highest existing ADR number; 0051 was available.

### EXISTING CONTRACT

| Inspected source | Relevant existing behavior |
| --- | --- |
| [ADR0050](0050_radar_candidate_and_escalation_boundary.md) and [passive evaluator](../../src/market_platform/application/radar_candidate.py) | Candidate is a detached source/policy correspondence value, not bearer authority. The pure evaluator consumes a trusted normal `RadarApplicationResult`; production activation and recovery remain deferred. |
| [Radar application](../../src/market_platform/radar/application.py) | `evaluate` retains the actual Pipeline, loads the prior state, prepares state and validates result correspondence before calling `save_state`. It returns a normal `SAVED` result only after publication succeeds. |
| [Pipeline](../../src/market_platform/radar/pipeline.py) and [core contracts](../../src/market_platform/radar/core.py) | Full Profile, ordered occurrences, actual executed prefix and failure determine the outcome. Configured-but-skipped Gates do not prove execution. |
| [Observation state](../../src/market_platform/radar/observation_state.py) | Retains checkpoint, lightweight observation, committed MeaningfulChange, Profile fingerprint and SELECTED/FILTERED outcome. It does not retain the full executed Pipeline or Candidate policy. |
| [Checkpoint store](../../src/market_platform/radar/checkpoint_store.py) | One latest record per instrument; `os.replace` is the process-visible commit point. Temp-file flush/fsync does not include directory fsync, locking or stale-writer protection. |
| [Single-symbol](../../src/market_platform/application/radar_single_symbol.py) and [batch](../../src/market_platform/application/radar_batch.py) | Production paths do not create Candidates. Batch is sequential with caller order and per-symbol failure isolation. |
| [Canonical fingerprint](../../src/market_platform/_fingerprint.py) | Deterministic schema-bearing canonical JSON fingerprint; no authentication or durable uniqueness registry. |
| [Replay file publication](../../src/market_platform/replay/artifact_file.py) | Local temp/flush/fsync and replace or no-clobber hard-link publication techniques; the API is specific to replay artifacts, not a Candidate store. |

[ADR0049](0049_radar_lightweight_observation_and_meaningful_change_policy.md)
requires the post-commit Candidate delivery window to be addressed before
activation. The exact remaining failure is:

```text
accepted observation checkpoint publication
-> process interruption
-> Candidate decision/pending work may never be materialized
-> later Radar observation overwrites latest-only state
-> original eligible transition can no longer be safely reconstructed
```

A deterministic Candidate fingerprint does not close this window. Neither does
a Candidate file written only after checkpoint commit. A newer state's retained
prior lightweight observation cannot establish the lost event's complete
comparison, executed Profile, acceptance or eligibility-policy context.

### ADR0051 ACCEPTED DECISION

Retain trusted execution/source/policy context **before** checkpoint publication,
then reconcile publication and materialize the original decision and any pending
work before another evaluation can supersede that source. This foundation stops
at durable pending work; it does not activate production creation or delivery.

The following remain constraints, not topics for redesign:

- Released v0.83 Radar semantics and accepted ADR0050.
- Passive `RadarCandidate`, its complete source snapshot and fingerprint.
- `selected_meaningful_transition / 1 / radar_candidate_eligibility_policy/v1`,
  with the repository's string revision `"1"`.
- Candidate is not bearer authority; FILTERED meaningful transitions are
  ineligible.
- No Candidate persistence inside `radar_observation_state/v1`.
- Radar normalized history is not Evidence; no
  `Candidate -> DataFrame -> governed Research` shortcut.

All numbered decisions below are **ADR0051 ACCEPTED DECISION**. Historical ADRs
and released artifacts are not amended.

## Decision 1: Recoverable process-interruption safety

The initial guarantee target is **RECOVERABLE PROCESS-INTERRUPTION SAFETY** under
retained trusted local filesystem contents, one non-overlapping owner per
instrument, and no bypass writer for the coordinated instrument while an intent
is unresolved.

It MUST cover interruption:

- Before checkpoint publication.
- After checkpoint publication but before Accepted Source persistence.
- After acceptance but before Candidate decision materialization.
- After an eligible decision but before Pending Candidate materialization.

Recovery preserves the original event and permits idempotent completion once
storage is available. It does not guarantee progress through permanent I/O
failure; unresolved work blocks superseding evaluation/publication.

This guarantee does **not** claim universal power-loss or device-loss durability,
directory-entry durability beyond proven filesystem behavior, distributed
consensus, cross-host exactly-once behavior, malicious filesystem tamper
resistance, concurrent writers, exactly-once Candidate delivery or exactly-once
governed research. Current file fsync semantics justify none of those claims.

## Decision 2: Four distinct concepts

| Concept | Meaning | Does not establish |
| --- | --- | --- |
| Prepared Source Intent | Durable immutable pre-publication recovery record. | Accepted observation, Candidate, pending Candidate work or Evidence authority. |
| Accepted Source | Owned protocol establishes that the exact proposed state became authoritative through checkpoint publication. | Candidate eligibility. |
| Candidate Decision | Existing ADR0050 evaluator result under policy recorded before publication; negative or ELIGIBLE. | Delivery, Evidence admission or successful research. |
| Pending Candidate Work | Durable eligible work awaiting a future delivery consumer, after acceptance and decision materialization. | Delivery, acknowledgment, research start/success or trading authority. |

These are separate semantic records, not one Candidate lifecycle enum. Physical
co-location in an envelope is allowed only if their publication distinctions
remain explicit. `PREPARED`, `ACCEPTED` and `PENDING` below name these concepts,
not additions to `RadarCandidate` or the observation-state schema.

## Decision 3: Prepared Source Intent content

Before authoritative checkpoint replacement is attempted, persist a strict,
detached, immutable Prepared Source Intent binding at least:

- Schema identity and canonical instrument identity.
- Exact completed `RadarPipelineResult`: full Profile, ordered Gate occurrences,
  actual executed-result prefix, failure if applicable, instrument and `as_of`.
- Exact proposed `RadarObservationState`.
- Exact proposed checkpoint and committed MeaningfulChange correspondence.
- Exact expected predecessor witness from Decision 4.
- Candidate eligibility policy identity selected for this run.

Checkpoint and MeaningfulChange may be retained through their canonical fields
inside the proposed state rather than independently writable duplicates; their
correspondence to the completed Pipeline MUST be validated. Derived outcome and
fingerprints must be recomputed/checked, not trusted as independent claims.

This is a publication protocol for sources eligible for observation advancement,
not a log of every failed/non-advancing evaluation. Existing rules still prohibit
publication for ATTENTION/FAILED and other non-advancing results. Retaining the
Pipeline failure field must not permit a failed Pipeline to become accepted.

Do not retain raw Polygon acquisition/OHLCV, a DataFrame, broker information,
research results, Strategy or trading authority. The source record recovers the
observation/Candidate handoff, not market data or Evidence provenance.

## Decision 4: Exact expected predecessor witness

Bind the authoritative predecessor actually used by the existing preparation
logic, distinguishing:

| Predecessor | Required witness |
| --- | --- |
| `ABSENT` | Explicit absence under a readable authoritative root; no checkpoint/state payload. |
| `LEGACY_CONTENT_ONLY` | Exact detached legacy checkpoint and its schema. |
| `PRESENT_COMPLETE_STATE` | Exact detached complete state and its schema. |

`UNAVAILABLE`, unreadable or corrupt predecessor cannot begin coordinated
publication. Missing root/access failure must not be converted to `ABSENT`.

Do not invent a `RadarObservationState.fingerprint`. A recovery-envelope
fingerprint may bind strict predecessor snapshots, but a symbol/session/hash
alone is insufficient. Comparison means exact validated canonical payload and
lookup shape, not incidental JSON whitespace or only digest text.

The intent must preserve the relationship between this predecessor and the
proposed state's comparison basis. It cannot silently substitute a newly read
baseline for the one used during preparation. Recheck the authoritative witness
before publication under the ownership protocol; mismatch blocks publication.

## Decision 5: Source-publication identity

Use a deterministic source-intent recovery identity derived with the existing
`canonical_fingerprint` mechanism from the complete schema-bearing prepared
payload, including proposed source, expected predecessor and selected Candidate
policy, excluding the identity itself.

No new random UUID or current-time entropy is added. Original retained Radar
`as_of` and `observed_at` remain part of the source and are not resampled on
recovery. This identity identifies source publication/recovery only. It is not
a second Candidate identity, Candidate fingerprint, Evidence ID, research
execution ID, acknowledgment or authority by itself.

Candidate fingerprint remains the sole Candidate identity. Acceptance and
decision records bind the immutable prepared identity and exact correspondence;
none may silently rebind it to another source or policy.

## Decision 6: Required write order

1. Existing Radar logic prepares the proposed state and validates all existing
   result/state/decision correspondence before authoritative publication.
2. Persist Prepared Source Intent durably within Decision 1's failure model.
3. Only after successful Prepared persistence may checkpoint publication begin.
4. After successful checkpoint publication, persist Accepted Source binding the
   exact prepared identity and accepted-state correspondence.
5. Only from Accepted Source may Candidate decision be materialized using the
   policy retained in Prepared Source Intent.
6. For ELIGIBLE only, persist Pending Candidate keyed by Candidate fingerprint.
7. Permit later evaluation/overwrite only after the durable decision and, for
   ELIGIBLE, its durable Pending Candidate exist.

No Candidate may be created or persisted as accepted work before acceptance is
established. A pre-publication validation object is not a trusted successful
application return. A write attempt or prepared temporary file is not durable
publication. Each completed step must remain discoverable after restart.

## Decision 7: Recovery before new evaluation or overwrite

For a coordinated instrument, reconcile unresolved Prepared/Accepted Source
before invoking a new Radar evaluation that could supersede the checkpoint.
Recovery uses the original retained source and policy; it must not reacquire
market data, rerun Gates, recalculate the historical observation using current
data, infer an event from newer state or apply today's Candidate policy.

At most one unresolved source publication may own an instrument. Recovery also
completes missing decision/pending steps after a durable Accepted Source. No
consumer, scheduler or background worker is required for this recovery boundary.

## Decision 8: Publication recovery matrix

For an unresolved valid Prepared Source Intent without durable Accepted Source,
read the authoritative checkpoint through the strict existing lookup contract:

| Case | Exact authoritative comparison | Required action |
| --- | --- | --- |
| A | Current complete state equals the exact proposed state. | Under exclusive ownership/no bypass, publication succeeded. Establish Accepted Source, then materialize the original decision/pending work idempotently. Do not republish or invent another market evaluation. |
| B | Current lookup equals the exact expected predecessor. | Proposed source has not become authoritative. Resume/retry publication of the **exact retained proposed state**, then establish Accepted Source. Do not reacquire, recompute, abandon in favor of a newer event or resample source times. |
| C | Neither comparison matches, or authoritative state is corrupt, unreadable or unexpected. | Fail closed; block later evaluation/overwrite. Do not guess acceptance. Explicit recovery/manual resolution is outside this slice. |

For an `ABSENT` predecessor, B requires actual absence under a readable root.
For `LEGACY_CONTENT_ONLY`, B requires that exact legacy checkpoint, not merely
matching content/session or a complete-state projection. For
`PRESENT_COMPLETE_STATE`, B requires the complete original state. A always
requires the exact complete proposed state. The valid advancement rules must
not admit an intent whose predecessor and proposal are indistinguishable;
ambiguous or contradictory intent fails closed.

A failed acceptance-record write after `os.replace` is not observation rollback.
The new state may already be authoritative; recover through A. A completed
Accepted Source is an owned durable fact, not an instruction to replay the
checkpoint on every restart. Missing decision/pending work resumes from it; an
unexpected authoritative change while it remains unresolved is a protocol
violation, not authorization to overwrite that change.

## Decision 9: Application-owned trusted recovery source

Introduce a new application-owned recovery boundary. Only after it establishes
Accepted Source may retained Pipeline/state/checkpoint/decision bytes be
reconstructed into the trusted application source consumed by
`evaluate_radar_candidate`. Prepared Source alone MUST NOT be promoted into a
successful `SAVED` application source.

Re-run all existing strict decoders and constructors/correspondence checks:
checkpoint/state decoding, instrument and Profile/Gate identity reconstruction,
actual executed prefix/failure validation, and application result invariants.
The existing Pipeline/Profile contracts do not expose a complete general import
API; a narrow recovery codec must reconstruct their exact types with strict
keys/schemas and invoke those existing validators. This is not a public generic
JSON-to-authority deserializer. Candidate evaluation retains its own revalidation.

Accepted Source derives trust from durable owned Prepared Intent,
expected-predecessor binding, exact publication reconciliation, exclusive
ownership and strict reconstruction together. Normal uninterrupted publication
success provides the acceptance observation; interrupted publication uses
Decision 8. Caller-supplied source JSON or a matching fingerprint cannot claim
either path. Loading a well-formed record alone is not authentication.

The trusted local root/producer and no-bypass assumptions are explicit; this is
not cryptographic attestation or malicious filesystem tamper resistance. The
passive Candidate/evaluator contracts remain unchanged and non-bearer.

## Decision 10: Policy activation binding

Persist `selected_meaningful_transition / "1" /
radar_candidate_eligibility_policy/v1` in Prepared Source Intent before
publication. This records the policy selected for the run even if Candidate
evaluation never starts. Selection for evaluation and completed evaluation are
distinct facts.

Recovery MUST use this retained identity. Missing, malformed or unsupported
policy fails closed, without fallback to the current default. Pre-activation
historical checkpoints lacking an owned prepared policy record are not
Candidate backfill sources. They may remain ordinary Radar comparison baselines;
they must not be reinterpreted as past Candidate events.

## Decision 11: Durable decision materialization

After acceptance, reconstruct the exact trusted application source, invoke the
existing `evaluate_radar_candidate`, and persist the exact
`RadarCandidateDecision` projection bound to the source recovery identity.
Persist negative decisions too, so completion cannot later be reinterpreted
under another policy or replay basis.

Reasons remain exactly `NOT_SELECTED`, `NOT_ADVANCED`,
`NO_MEANINGFUL_TRANSITION`, `ELIGIBLE`. No delivery `ERROR` reason is added.
Accepted publications reconstruct a `SAVED` source, so `NOT_ADVANCED` is not an
expected accepted-publication result; preserving the existing reason vocabulary
does not invent an accepted record for a non-advancing run.

On repeat materialization, verify exact retained decision/source/policy
correspondence. A contradiction is an invariant error, not a new negative
decision or permission to replace history. Operational persistence/recovery
errors belong to the new layer.

## Decision 12: Pending Candidate work

Only an ELIGIBLE decision may produce a separate Pending Candidate record. Its
sole Candidate key is `RadarCandidate.fingerprint`. Bind at least:

- Candidate fingerprint and complete detached Candidate projection.
- Source-event recovery identity/reference.
- Exact Candidate decision correspondence.

The complete Candidate includes its full detached source observation snapshot;
never replace it with a pointer to latest checkpoint state. The referenced
prepared/accepted/decision records also remain retained. Later checkpoint
overwrite cannot erase this work or its source correspondence.

Do not add pending/delivery fields to `RadarCandidate`. Negative decisions have
no Pending Candidate. A partial pending write is not a pending publication.

## Decision 13: Durable uniqueness and conflicts

Candidate fingerprint is the durable Candidate persistence/deduplication key:

| Existing key | Result |
| --- | --- |
| Absent | Publish Pending Candidate. |
| Present with exact same canonical record payload | Idempotent success. |
| Present with different payload | Fail closed as identity/content conflict. |

Compare full payloads, including source/decision correspondence, not only hash
text. Apply the same create-if-absent/equality/conflict principle to source
intent identity and its immutable associated facts. Conflicts are not updates.

Do not substitute Candidate fingerprint for EvidenceArtifact ID, construction
`execution_id`, qualification identity, technical/research occurrence identity
or research request identity. Durable uniqueness does not imply idempotent
dispatch, result reuse or idempotent governed execution.

## Decision 14: Stop at pending work

The foundation stops at durable PENDING Candidate work. It implements no
DELIVERED, ACKNOWLEDGED, CONSUMED, CLAIMED, leases, worker ownership, retry
counters, cancellation or expiry. Resuming an incomplete local publication is
part of recovery, not a consumer retry/claim lifecycle.

Future acknowledgment requires a named downstream consumer durably owning the
next action; it must not mean governed research succeeded. Later delivery may
repeat. Exactly-once delivery is not claimed.

## Decision 15: Overwrite interlock

A later state MUST NOT overwrite the same coordinated instrument while an
earlier Prepared/Accepted Source remains unresolved. Resolution requires:

1. Accepted Source is established and retained.
2. Candidate decision is durably materialized, including negative decisions.
3. If ELIGIBLE, corresponding Pending Candidate is durably present.

Only then may a new evaluation proceed. Pending work itself need not be
delivered to permit the next observation. The original source, decision and
pending work survive independently of the latest-state file. Do not use the
latest checkpoint as a garbage-collection signal for these records.

## Decision 16: Single-owner scope

One local non-overlapping owner per instrument covers:

```text
recovery -> evaluation -> prepared-intent publication -> checkpoint publication
-> acceptance -> Candidate decision -> pending materialization
```

There are no concurrent workers, claims or interprocess leases in this slice.
Future overlapping schedulers/batches require a separate locking/fencing
decision. Atomic replace prevents torn publication, not stale-writer overwrite.

A bypass writer invalidates automatic reconciliation. Later activation must
ensure the coordinated instrument root is not concurrently written through an
uncoordinated legacy path. This foundation does not prevent arbitrary external
writes. Different instruments remain independent; no cross-symbol transaction,
rollback, ranking or priority is introduced.

## Decision 17: Opt-in pre-publication coordination seam

An **opt-in application-owned pre-publication coordination seam is REQUIRED**.
It has two required semantic boundaries in the existing Radar application flow:

1. Before a coordinated evaluation loads facts or executes its Pipeline,
   perform recovery/interlock for that instrument. An unresolved source prevents
   the new evaluation.
2. After existing preparation and correspondence validation, but **before** the
   direct `save_state` call, expose/transfer the completed Pipeline, exact
   proposed state and exact retained predecessor, together with the selected
   Candidate policy context owned by the outer Candidate recovery composition.
   Give the coordinated path sole control of authoritative checkpoint
   publication and acceptance/decision/pending completion: persist Prepared
   Intent before publication, then complete the remaining steps in the required
   order or report unresolved failure.

Coordination belongs to the application-layer Candidate recovery composition;
Radar supplies observation context through a narrow observation-publication
boundary. Radar application code MUST NOT import the Candidate policy/evaluator
or decide eligibility. The outer recovery composition owns that policy and
invokes Candidate evaluation only after Accepted Source is established. The
seam is not a generic event bus or a new Gate; a post-save-only callback cannot
satisfy it.

Existing `RadarApplicationService.evaluate` currently holds the needed
observation context: `retained` from `prior_state()`, actual Pipeline `result`,
and `_prepare_state`'s validated `state`, immediately before
`self._checkpoint_store.save_state(state)`. It also constructs a provisional
`SAVED`-shaped object to validate return invariants before publication. Preserve
that validation behavior; do not expose that provisional object as accepted
recovery input or call Candidate on it.

The coordinated path is the sole path to the actual checkpoint write in this
mode; the service must not perform a second unconditional save afterward.
When coordination is absent, retain the existing lookup/evaluation/
preparation/save/return path, exception distinctions, clock behavior and lazy
fact loading. Non-advancing results remain non-advancing and create no prepared
publication. The recovery check still precedes any new coordinated evaluation.

A post-result wrapper is insufficient: `evaluate` returns only after save, and
`save_state` itself receives no Pipeline or selected policy context. A state-only
store decorator also cannot provide the missing execution witness. Therefore a
small shared-code change in `radar/application.py` is required in the future
implementation to expose these two boundaries. Do not duplicate the evaluation
algorithm or move eligibility into Pipeline, Gates, observation state or the
checkpoint schema.

An injected coordinator is the preferred current implementation shape because
it fits the existing composition, but this ADR freezes the semantic boundaries
above rather than requiring that exact mechanism. An injected coordinator
object, an explicit prepared/publication protocol object, callback/interface
naming, concrete class names, method names and parameter spelling remain
implementation-review choices. Any chosen form MUST provide pre-evaluation
recovery and pre-save publication control; neither a pure post-result wrapper
nor a post-save-only callback is sufficient. This ADR does not implement the
seam.

## Decision 18: Legacy runtime remains unchanged

The immediate foundation remains NON-ACTIVATING. Existing
`run_single_symbol_radar` and `run_radar_batch` remain unwired: no Candidate in
responses, no pending writes, no implicit coordination of their checkpoint roots.
Existing constructors/callers without the optional seam retain legacy behavior.

Future production activation must be explicit/opt-in and must exclude overlapping
uncoordinated writers for a coordinated instrument. Merely importing new types
or creating storage directories does not activate a root. Preserve
`radar_observation_state/v1` exactly. No batch response, ordering, isolation or
cross-symbol semantics change is authorized here.

## Decision 19: Narrow local persistence

Use domain-specific local persistence. Introduce no SQLite, Postgres, Redis,
message broker, generic event-sourcing framework, generic repository abstraction
or generic Evidence database.

Reuse existing techniques where appropriate: strict JSON/schema validation,
detached canonical projections, same-filesystem temp writes, flush/fsync, atomic
replace and suitable no-clobber immutable publication. The replay file module's
hard-link technique is a publication precedent, not permission to reuse
`HistoricalReplayArtifact` objects. Evidence lifecycle types likewise must not
become recovery records.

Prepared intents must be durably discoverable by instrument before checkpoint
publication is attempted. Recovery cannot depend on an in-memory list or an
uncommitted secondary index. The owner must enumerate/resolve incomplete work
before admitting another intent. Unexpected multiple unresolved intents,
corrupt/partial authoritative records, unknown schemas, duplicate JSON keys or
incoherent links fail closed; they must not be treated as an empty queue.
Unpublished temporary files confer no acceptance or pending-work authority.

Physical layout, exact new schema labels and file names are implementation
details. Semantic records remain distinct even in one envelope. Atomicity of
one file is not atomicity of multiple files: the ordering, matrix and interlock
provide recoverability. Retain complete prepared/accepted/decision/pending
correspondence; no automatic expiry, deletion or compaction is implemented.

## Decision 20: Failure taxonomy

| Failure/outcome | Required interpretation |
| --- | --- |
| Prepared persistence failure | Checkpoint publication MUST NOT begin. If publication of the intent itself is uncertain, reconcile the retained store before new work. |
| Checkpoint publication failure or uncertain interruption | Source remains unresolved; inspect exact predecessor/proposal through Decision 8 before proceeding. |
| Acceptance persistence failure after checkpoint publication | Observation may already be authoritative. Recover; never report rollback merely because the acceptance record failed. |
| Recovery mismatch/corruption/unreadable authority | Fail closed and block later evaluation/overwrite; manual resolution is outside this slice. |
| Candidate evaluation contradiction | Invariant failure, not `NOT_SELECTED`; accepted source remains unresolved. |
| Negative Candidate decision | Normal decision, durably retained, no Pending Candidate. |
| Decision persistence failure | Accepted source remains unresolved and blocks supersession. |
| Pending Candidate persistence conflict/failure | Eligible work remains unresolved; block overwrite until reconciled. Do not overwrite conflicting content. |

Preserve the original Pipeline/observation outcome and failing publication
stage. Operational recovery/persistence errors must not become additional
`RadarCandidateDecision` reasons or disappear behind a normal negative result.
The opt-in coordinator must distinguish post-commit unresolved completion from
pre-commit failure without changing default legacy error behavior.

## Decision 21: Governed research remains deferred

This ADR does not activate Candidate-to-governed-research orchestration. Defer:

- Research acquisition window/lookback and trusted mapping request construction.
- `query_as_of`, `analysis_as_of`, `knowledge_as_of` selection.
- Immediate older material versus waiting for trigger-session inclusion.
- Governed service-root lifetime and restart restoration.
- Research execution idempotency and research acknowledgment.
- Raw Radar acquisition reuse/no-refetch orchestration.

The deferral is substantive: the
[Radar calendar](../../src/market_platform/radar/calendar.py) recognizes completion
at actual exchange close, whereas
[Evidence ingress](../../src/market_platform/evidence_ingress/polygon_completed_daily_ohlcv.py)
excludes rows on the New York query civil date and requires query time no later
than response receipt.
[ACTIVE issuance](../../src/market_platform/application/polygon_completed_daily_production_validity.py)
sets effective/recorded time to actual completion;
[qualification](../../src/market_platform/application/polygon_completed_daily_production_qualification.py)
requires authentic available history, separate knowledge/effective cutoffs and
task freshness. Radar `as_of` cannot simply become all later research cutoffs.

[Production construction](../../src/market_platform/application/polygon_completed_daily_production_construction.py)
and downstream services retain authentic occurrences inside their service roots.
A durable Candidate record is not restoration of those roots or execution
idempotency. Candidate recovery can be correct without settling research timing
or claiming later research must succeed.

## Decision 22: No-refetch remains deferred

Radar's normalized 250-row history is not Evidence. The recovery journal MUST NOT
retain or convert that history into Evidence; it retains only bounded execution,
observation and policy correspondence. No direct DataFrame research shortcut is
permitted.

A future no-refetch design requires preserved raw acquisition provenance and a
separate timing/authority review. In particular, an earlier response receipt
cannot be assigned a later query cutoff to include its same-day row. Fresh
governed acquisition through the existing full construction/governance chain is
the safest eventual first research path; this ADR does not activate it.

## Decision 23: One smallest future implementation slice

The first future implementation under this accepted ADR is the
**Recoverable Radar Source and Candidate Delivery Foundation**, NON-ACTIVATING.
It must demonstrate the whole protocol with actual application preparation and
local checkpoint publication, not merely store a post-result Candidate file:

```text
PREPARED -> checkpoint publication -> interruption/restart reconciliation
-> ACCEPTED -> deterministic Candidate decision -> durable PENDING if eligible
-> release overwrite interlock
```

Proposed exact implementation path set, not edits performed by this ADR:

| Path | Future change and narrow purpose |
| --- | --- |
| `src/market_platform/application/radar_candidate_delivery.py` | New exact source/acceptance/decision/pending contracts, strict recovery reconstruction, application coordinator and interlock. Reuse passive evaluator unchanged. |
| `src/market_platform/application/radar_candidate_delivery_store.py` | New dedicated local record publication/lookup layer. Its distinct filesystem failure boundary and strict immutable-record handling justify separating it from orchestration; no generic repository layer. |
| `src/market_platform/radar/application.py` | Small existing-file change: opt-in observation publication interface plus pre-evaluation recovery and validated pre-save delegation from Decision 17. Default path remains unchanged. |
| `tests/unit/test_radar_candidate_delivery.py` | New pure/application coordinator, eligibility, trusted reconstruction and interlock tests using actual Radar preparation with injected facts/clocks. |
| `tests/unit/test_radar_candidate_delivery_store.py` | New temporary-directory publication, conflict, interruption and fresh-instance recovery tests. |
| `tests/unit/test_radar_application.py` | Focused existing-file changes for opt-in seam ordering and default-path regression coverage. |

The store module separation is for a concrete durability boundary, not a generic
pre-split framework. Do not introduce additional layers or existing-file edits
without a specific contract conflict and implementation review.

A shared Radar application change is necessary: today neither a post-result
adapter nor the injected state-only checkpoint store can bind actual execution
and predecessor context durably before save. The required pre-evaluation /
pre-save coordination seam exposes those already-computed values without
redesigning advancement or acquisition. It also places recovery before new
evaluation, which a post-save hook cannot do.

No current single/batch composition is wired to this seam. No production response
or default runtime behavior changes. No changes to passive Candidate, Pipeline,
Gates, checkpoint schema/store, package-root exports, providers, research services,
dependencies, ADR0050 or released artifacts are pre-authorized. These are future
implementation paths only; this architecture checkpoint implements none of them.

## Decision 24: Future test obligations

Use temporary directories, injected facts/clocks and fault injection; no real
provider network. At minimum verify:

1. Prepared persistence precedes any checkpoint publication.
2. Prepared write failure prevents checkpoint publication.
3. Fresh-instance restart with predecessor still current resumes the exact
   retained proposal, including ABSENT and legacy predecessor shapes.
4. Restart with proposed state already current establishes acceptance without
   another publication, acquisition, clock-resampled source or market evaluation.
5. Unexpected/corrupt/unreadable current checkpoint fails closed and blocks
   later evaluation/overwrite.
6. Accepted Source with missing decision reconstructs the trusted source and
   materializes the exact evaluator decision.
7. Eligible decision with missing Pending Candidate creates the same Candidate
   idempotently.
8. Candidate key absent creates; same key/same payload succeeds idempotently;
   same key/different payload conflicts. Apply equivalent source-identity checks.
9. Negative decisions persist and create no Pending Candidate.
10. FILTERED meaningful transition stays negative.
11. Baseline, incomparable baseline and unchanged remain negative; preserve
    complete-state UNCHANGED and legacy bootstrap semantics.
12. Unsupported, missing or malformed historical Candidate policy fails closed.
13. Pre-activation checkpoint without owned activation record cannot be backfilled.
14. Unresolved S1 prevents new S2 evaluation/overwrite.
15. After S1 decision and eligible pending work are durable, S2 checkpoint
    replacement cannot erase S1 source or work.
16. Restart uses fresh components and retained filesystem contents, not hidden
    in-memory authority or monkeypatched old objects.
17. Corrupt/partial authoritative source records, broken references or an
    undiscoverable/incoherent inventory fail closed.
18. No Candidate creation or successful `SAVED` recovery source from PREPARED
    alone; arbitrary JSON/dataclass input does not authenticate acceptance.
19. Current single-symbol/batch behavior and responses remain non-activating;
    default application path retains existing clocks, laziness and error semantics.
20. Recovery/Candidate materialization never executes governed research or provider
    network activity; injected test facts avoid real acquisition.

Cover interruption at every write/publication boundary, including successful
checkpoint replace followed by acceptance-write failure. Verify that it is
recovered as accepted, never described as rollback. Test full source/predecessor/
policy correspondence, equality-versus-conflict, detached projections and
repeated restart before each missing downstream record is completed.

Reuse focused
[application](../../tests/unit/test_radar_application.py),
[checkpoint](../../tests/unit/test_radar_checkpoint_store.py),
[Candidate](../../tests/unit/test_radar_candidate.py),
[single-symbol](../../tests/unit/test_radar_single_symbol.py) and
[batch](../../tests/unit/test_radar_batch.py) regressions. The shared application
seam justifies those focused regressions; full suite is not automatic unless
implementation review finds broader shared-core/release risk. Future commits
follow repository pytest/Ruff/mypy requirements. This documentation task runs
none of them; only non-mutating documentation/diff checks apply.

## Alternatives rejected

| Alternative | Reason |
| --- | --- |
| Best-effort Candidate return or post-result Candidate file | Leaves commit-to-retention loss and latest-only overwrite unresolved. |
| State-only store wrapper or post-save callback | Lacks pre-publication executed Pipeline/policy context and cannot close the gap. |
| Treat PREPARED as SAVED or Candidate authority | Confuses intent with successful observation publication. |
| Recover from latest/newer state or today's provider/policy | Reconstructs historical facts without original execution/activation provenance. |
| Put Candidate lifecycle in the checkpoint | Changes frozen observation schema and mixes observation with delivery ownership. |
| Let S2 overwrite while S1 decision/pending is missing | Removes the reconciliation witness before handoff completion. |
| Database/broker, workers or generic event sourcing first | Adds infrastructure/concurrency without being needed for this single-owner local protocol. |
| Candidate hash as research execution identity | Confuses deterministic correspondence with authority, timing and execution idempotency. |

## Consequences and tradeoffs

The accepted architecture makes post-publication interruption recoverable before another
observation destroys its witness. It adds local records and deliberate blocking
when completion is uncertain. Storage failure can prevent newer observation
publication for that instrument; this is the cost of preserving the original
event instead of silently losing consideration. Other instruments remain
independent.

Strict source retention is broader than the Candidate snapshot because recovery
must preserve actual execution and pre-publication policy context. It still
excludes raw market data and all Evidence/research authority. Source and
Candidate identity remain distinct. Records may accumulate until a later
consumer/retention decision; this foundation does not silently delete them.

The protocol requires a small opt-in shared application seam, but current
production compositions remain unwired. It proves a recovery foundation rather
than claiming live production delivery, consumer acknowledgment or research
execution already exists.

## Non-goals

- Production Candidate activation or current single-symbol/batch response changes.
- Delivery consumer, acknowledgment implementation, concurrent workers, claims,
  leases/fencing, cancellation or expiry.
- Durable watchlist, scheduler, ranking/scoring or opportunity prioritization.
- Governed research execution, timing policy, durable governed Evidence history,
  research execution idempotency or no-refetch optimization.
- Scenario/Risk/Plan, trading/execution, broker integration or portfolio construction.
- Shadow Observer, agent autonomy or UI.
- Generic event sourcing, repository framework, database or message broker.
- Rewriting ADR0050, released v0.83 artifacts, Candidate policy or observation schema.

## Open questions beyond this foundation

1. Should future research run immediately on older permitted material or wait
   for trigger-session inclusion?
2. Should governed execution restart as independent fresh attempts, or support
   durable old-authority resume/reuse?
3. Must eventual durability cover power/device loss beyond retained-filesystem
   process interruption, and on which supported filesystem contract?
4. What named consumer acknowledgment, retention and compaction contract should
   future Candidate delivery use?

Publication ordering, reconciliation, trusted source reconstruction and the
interlock are decided by this accepted ADR, not deferred open questions. This ADR
adds no implementation, test modification or production activation.
