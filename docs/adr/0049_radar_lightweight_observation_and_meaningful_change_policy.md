# ADR 0049: Radar Lightweight Observation and Meaningful Change Policy

## Status

Accepted

This decision-document slice specifies the semantic prerequisite for later
RadarCandidate eligibility. The decisions below are normative proposals pending
review; they do not claim that the behavior is already implemented.
RadarPipelineOutcome.SELECTED is NOT RadarCandidate eligibility by itself.
RadarCandidate creation remains out of scope.

## Context and inspected baseline

- Branch: `feature/v0.83.0-radar`.
- HEAD and local `origin/feature/v0.83.0-radar`:
  `f36585d79504637f6a3b1af9f8a41d720da94483`.
- Subject: `feat: add sequential Radar batch orchestration`.
- Local `main` and local `origin/main`:
  `1e60406a153105eca2b76db735635b8553108827`.
- Worktree and index were clean before drafting; no fetch was performed.
- [ADR0046](0046_radar_exchange_session_calendar_foundation.md),
  [ADR0047](0047_radar_core_gate_profile_and_pipeline_contracts.md), and
  [ADR0048](0048_radar_completed_daily_current_content_acquisition.md) remain
  unchanged.

The production-accepted single-symbol and sequential batch compositions acquire
fresh completed-daily Polygon history, evaluate the session/content Trigger and
configured EMA relation Gate, and advance per-instrument observation checkpoints.
The Trigger can PASS with BASELINE_REQUIRED, NEW_COMPLETED_SESSION or
MARKET_CONTENT_CHANGED. Any can lead to SELECTED if all configured Gates PASS.
None establishes materiality. A normalized content fingerprint difference and
SELECTED alone likewise establish no materiality.

The existing checkpoint records instrument, completed session, normalized content
identity, scope and observation completion time. It does not record EMA relation,
prior Gate results or a technical-observation definition. The current EMA Gate
classifies the latest relation; it does not compare prior observations. The
application can save a checkpoint after a downstream DROP, but does not advance
for ATTENTION or Pipeline FAILED. Batch envelopes preserve those semantics.

This ADR fixes one bounded transition policy without changing Pipeline outcomes,
Gate dispositions, current acquisition rules or the meaning of existing stored
checkpoints. A future implementation must satisfy the coordination requirements
below before enabling authoritative lightweight-state advancement.

## Decision 1: Separate three concepts

| Term | Meaning | Owner |
| --- | --- | --- |
| Market Content Observation | Which completed-session market content was observed, with canonical instrument, normalized content identity and scope. | Radar observation/application boundary. |
| Lightweight Technical Observation | A bounded technical state derived from that validated content under an explicit observation definition. | Radar calculation/fact boundary. |
| MeaningfulChangeDecision | A bounded comparison result retaining prior/current correspondence, policy identity and reason, including initialization or non-change. | Radar meaningful-change evaluation. |
| MeaningfulChangePolicy | A versioned rule deciding whether comparable observed state changed in an approved way. | Explicit market-platform-owned Radar policy. |

These concepts are not one fingerprint or one boolean. A decision must distinguish
initialization, incomparable-baseline handling, comparable unchanged state and an
approved transition. None grants research consumption or trading authority.

The levels are:

- LEVEL 0: no new completed session and no normalized content change under the
  existing comparable observation contract; no downstream work.
- LEVEL 1: a new valid baseline or a comparable observation without an approved
  state transition; eligible observation state advances, without Level-2 status.
- LEVEL 2: an approved transition between comparable lightweight states; later
  Candidate consideration additionally requires selection and commit conditions.

ATTENTION and FAILED are never Level-2 eligibility. Initialization is explicitly
baseline semantics within the observation-only path, not a synthetic transition.

## Decision 2: First lightweight observation

The first observation is exactly EMA8/EMA20 relation, with states ABOVE, EQUAL
and BELOW. Its proposed definition identity is:

- definition ID: `ema8_ema20_relation_observation`;
- calculation revision: `1`;
- observation schema: `radar_ema8_ema20_observation/v1`.

Revision 1 preserves the existing Radar EMA calculation: ordered closes from the
validated ADR0048 history, existing `calculate_ema` semantics with periods 8 and
20, and comparison of their latest values using greater-than, exact equality or
less-than. No tolerance, crossover inference or additional indicator is added.
Changes to these calculation semantics require a new revision.

Gate implementation identity and lightweight-observation identity MUST remain
separate namespaces and semantic identities. Gate behavioral revision and
observation calculation revision MUST remain independent version axes. Changing
Gate selection behavior, configuration validation, reason codes or other Gate-only
behavior does NOT by itself require a new observation calculation revision.
Changing EMA observation mathematics MUST receive the appropriate new observation
calculation revision even if the Gate implementation revision does not otherwise
change.

The observation definition is independent of the Gate's `accepted_relations`
selection configuration. Do not derive a durable observation by parsing
`reason_code`, and do not make Gate output its persistence authority.
A future shared calculation/fact boundary should derive this state from the same
validated execution-local completed-daily history. The Gate and comparison
machinery may consume that fact independently; no Gate-to-Gate communication,
second acquisition or cross-execution fact cache is introduced.

## Decision 3: Observation identity and correspondence

A durable comparable observation must retain at least:

- canonical instrument ID;
- observation definition ID, calculation revision and observation schema;
- observed completed-session date;
- normalized market-content identity;
- relevant content-scope schema and concrete history start/end;
- the bounded observed relation;
- aware UTC evaluation as_of and recorded/accepted time where needed to establish
  evaluation correspondence and authoritative observation ordering.

Completed session identifies the market observation. as_of identifies its
calendar evaluation cutoff; recorded time identifies recording/acceptance, not
provider retrieval, Evidence availability or a price timestamp. Wall-clock
movement is not meaningful change. Exact occurrence/reference encoding remains
an implementation-contract decision; do not invent an existing checkpoint ID.

Profile identity must not define mathematical EMA observation identity. Profiles
select how a market observation participates in evaluation. A later Candidate
must still correspond to the actual caller Profile and completed Pipeline.
Different accepted-relations configurations do not change the calculated state.

Comparison requires the same canonical instrument and compatible observation,
calculation and content-scope semantics. For a new completed session, the valid
250-session ADR0048 window rolls forward: identical history dates or content
fingerprints are NOT required across sessions. For the same completed session,
require the same concrete scope before classifying a content correction.
Current and prior observations must each be valid under their declared scope.

Completed-session progression must be nondecreasing. A future-session prior,
wrong-instrument attachment, corrupt observation or contradictory correspondence
is invalid input, not permission to reset a baseline or manufacture a transition.
Missing, known incompatible and unavailable/corrupt prior state remain distinct.

## Decision 4: Bootstrap

When no comparable prior lightweight observation exists because it is genuinely
absent, a valid current observation may initialize state at the coordinated
advancement boundary. The decision is BASELINE_INITIALIZED, not meaningful
change, even if the Pipeline is SELECTED. No prior state is invented.

An existing legacy content checkpoint does not prove a lightweight baseline
exists. Future migration/bootstrap must explicitly detect missing required
lightweight state and obtain a valid current observation before establishing it.
It must not reinterpret an existing UNCHANGED Gate result as a calculated state.
Any required bootstrap orchestration is application-owned and must be specified
before rollout; the Trigger contract itself is not silently rewritten here.

A separately named initial-research workflow is outside this ADR and is not
MeaningfulChange.

## Decision 5: Comparable new session with the same state

A new completed session with the same comparable relation, including
ABOVE -> ABOVE, is LEVEL 1: advance eligible observation state, record
STATE_UNCHANGED and MeaningfulChange = false. A new session alone is never a
meaningful-change reason.

## Decision 6: Content correction with the same state

For a comparable same-session scope, changed normalized content with an unchanged
relation updates eligible observation correspondence to that corrected content.
The decision is STATE_UNCHANGED and MeaningfulChange = false. Retain that the
observation arose from corrected content, but never use fingerprint inequality
alone as a meaningful-change reason.

## Decision 7: State transition policy v1

The first policy identity is separate from calculation identity:

- policy ID: `ema8_ema20_relation_transition`;
- behavioral revision: `1`;
- decision schema: `radar_meaningful_change_decision/v1`.

For two valid comparable observations, every change in the bounded relation is
an approved lightweight-state transition under this policy:

| Prior / Current | ABOVE | EQUAL | BELOW |
| --- | --- | --- | --- |
| ABOVE | Not meaningful | Meaningful | Meaningful |
| EQUAL | Meaningful | Not meaningful | Meaningful |
| BELOW | Meaningful | Meaningful | Not meaningful |

This means only: the approved lightweight state changed. It is not a claim of
investment significance, direction, profitability or research conclusion. Do not
label transitions bullish/bearish or attach BUY/SELL/HOLD semantics.

A policy revision may change transition acceptance only through an explicit
future decision. It must not silently alter calculation revision or fabricate
prior state. Identical calculation observations can be inputs to distinct policy
revisions; every decision retains the policy actually applied.

## Decision 8: Same-session corrections and transition reasons

For a later completed session, a comparable changed relation yields
NEW_SESSION_STATE_TRANSITION. The comparison is against the actual prior accepted
observation, even when executions skipped intervening sessions; it makes no claim
about the number or path of intermediate transitions.

For the same completed session, CORRECTED_CONTENT_STATE_TRANSITION requires all
of: comparable observations, equal concrete content scope, different normalized
content identity, and a changed recalculated relation. Thus ABOVE -> ABOVE is not
meaningful, while ABOVE -> BELOW is meaningful under policy v1.

A changed relation with identical same-session content, scope and calculation
identity is incoherent; it must not be classified as meaningful or accepted for
advancement. It requires failure/operational handling. The reason distinguishes
new-session progression from same-session correction without asserting that
either is an investment signal.

## Decision 9: Incomparable prior state

A valid prior observation with an incompatible calculation revision, definition
or observation/content semantics is not a comparison operand. Establish a valid
current baseline for the new definition when advancement is permitted, with
INCOMPARABLE_BASELINE_INITIALIZED and MeaningfulChange = false.

Retain bounded incompatibility provenance, including the relevant prior/current
definition or revision identities and incompatibility category. Do not silently
compare across revisions or infer a transition from different fingerprints.
This handling does not authorize overwriting corrupt, unavailable or wrongly
attached state as though it were a legitimate version migration.

## Decision 10: Profile and Gate outcomes

MeaningfulChange and Pipeline selection are separate dimensions. A valid state
transition can be observed even when a downstream configured policy Gate returns
DROP. The transition decision does not turn FILTERED into SELECTED.

Later Candidate eligibility requires both actual eligible selection and an actual
approved meaningful-change decision. ATTENTION and FAILED cannot acquire
eligibility from a prior or partial observation. Never infer technical state from
synthetic or skipped Gate results. If a Profile terminates before the required
fact is available, the application must not fabricate it or falsely report a
complete lightweight observation.

This ADR does not reorder Gates, insert default Gates or rewrite caller Profiles.
The future composition must explicitly provision the required observation fact
for the observation policy and fail closed if coordinated advancement cannot be
completed under that composition.

## Decision 11: Advancement semantics

Use the existing RadarApplication advancement conditions as the baseline:
SELECTED or FILTERED, with an actually executed qualifying session/content
Trigger PASS and valid current content. Qualifying reasons remain
BASELINE_REQUIRED, NEW_COMPLETED_SESSION and MARKET_CONTENT_CHANGED.

| Actual result / observation | Lightweight advancement |
| --- | --- |
| SELECTED with qualifying Trigger PASS and valid current observation | Eligible for coordinated advancement; baseline, unchanged state and transition are all remembered. |
| Downstream FILTERED after qualifying Trigger PASS with valid current observation | Also eligible; SELECTED is not required to remember state. |
| UNCHANGED Trigger DROP | No ordinary advancement or downstream calculation. Bootstrap/recovery must be handled explicitly, not inferred from this result. |
| Earlier FILTERED without qualifying Trigger PASS | Not eligible under the existing application advancement rule. |
| ATTENTION | No authoritative advancement and no Level-2 eligibility. |
| Pipeline FAILED | No authoritative advancement and no Level-2 eligibility. |
| Unavailable, missing required or incoherent current observation | No authoritative advancement of the coordinated state. |

Comparison must use the prior accepted lightweight observation before replacing
it. A decision computed before commit is provisional for escalation purposes.
Do not roll back previously completed instruments in a sequential batch. A
checkpoint-save exception is not successful advancement; preserve the completed
Pipeline according to the existing application/batch error contract.

## Decision 12: Coordinated persistence and failure recovery

One application-owned boundary must commit market-content advancement and the
required lightweight observation with a single recoverable commit semantic.
There must be one clear authoritative commit point for each instrument. Two
unrelated file writes are not atomic merely because each individual write uses
atomic replacement.

Specifically reject: save the existing market checkpoint first, then best-effort
save lightweight state. That can make the next Trigger return UNCHANGED while
the required comparison baseline or transition is missing.

Required semantics:

- Before commit, the prior authoritative state remains recoverable and a retry
  remains possible. Failed preparation must not expose a new market checkpoint
  without its required technical observation.
- After commit, readers must obtain mutually corresponding market and lightweight
  observations, or explicitly detect an incomplete/recovery state. They must
  never treat an incomplete state as an ordinary UNCHANGED success.
- A partial persistence failure must not silently lose the real transition that
  was being accepted. Recovery must preserve the prior/current comparison basis
  or its bounded committed decision where necessary to distinguish pre-commit
  failure from completed commit with interrupted result delivery.
- Orphan temporary writes may exist but have no authority. Recovery and retries
  must have a defined interpretation of the commit point; they must not require
  historical reconstruction from today's corrected provider data.

A combined versioned record or a recoverable publication protocol may be
considered in implementation design. This ADR selects neither a file layout nor
a database and adds no locking or concurrency. Existing single-owner,
non-overlapping per-instrument execution remains required. Existing v1 checkpoint
files are not retroactively declared to contain technical observations.

This observation commit guarantee is not an exactly-once Candidate delivery
promise. Candidate creation/delivery is deferred and must address its own
post-commit failure window before being enabled.

## Decision 13: Persistence ownership

Comparison state is Radar-owned observation state. It is not Evidence, admission
state, research history, Strategy state, Candidate persistence or trading
authority. Do not use logs or governed publication inventories as its implicit
source of truth.

A later implementation may introduce a versioned lightweight-observation store
or evolve an application-owned checkpoint contract. Either must preserve the
coordination, migration and recovery semantics above. Current checkpoint-store
implementation and schema are not redesigned by this decision-document slice.

## Decision 14: Relationship to RadarCandidate

Trigger PASS, SELECTED, content fingerprint change and new completed session are
individually insufficient. Future RadarCandidate eligibility requires at least:

1. an actual qualifying Radar evaluation;
2. its actual SELECTED result under the caller Profile;
3. an actual MeaningfulChange decision under the approved policy;
4. valid prior/current observation correspondence;
5. successful authoritative observation advancement, or another explicitly
   approved delivery/commit policy.

The future application-layer transformation must preserve actual results and
exclude ATTENTION, FAILED and FILTERED from Candidate eligibility. A meaningful
transition remembered during FILTERED does not grant later automatic eligibility.
Exact Candidate fields, identity/fingerprint, deduplication, delivery and
persistence remain a later decision. No RadarCandidate is created by this layer.

## Decision 15: Governed Research boundary

MeaningfulChange grants no governed research consumption authority. Future
escalation hands an identity/reason request to a separate application-layer
orchestrator. That orchestrator must establish the existing governed chain:

```text
Construction -> Validation -> Freshness -> Admission -> Validity
-> Qualification -> Bridge -> Technical -> Interpretation -> Assessment -> Strategy
```

Radar's normalized history is not governed Evidence. No direct history injection,
Evidence bypass or acquisition reuse/no-refetch workaround belongs here. Existing
v0.82 authenticity, history, availability and consumption requirements remain
unchanged.

## Alternatives rejected

| Alternative | Rejection reason |
| --- | --- |
| SELECTED equals Candidate | Includes bootstrap and ordinary observations; all-Gate PASS is not materiality. |
| New session or fingerprint change equals materiality | Neither establishes a bounded technical-state transition. |
| Gate reason_code as persisted technical state | Couples calculation identity and persistence to evaluator output/projection. |
| Parse previous results from logs | Logs do not provide the required authoritative, versioned comparison contract. |
| Recompute previous state from today's corrected history | Does not recover what was actually observed and accepted previously. |
| Compare bare ABOVE/EQUAL/BELOW strings | Loses instrument, calculation, scope and temporal correspondence. |
| Require SELECTED for all observation advancement | Leaves stale comparison state after a valid downstream policy filter. |
| Best-effort second write after checkpoint advancement | Can suppress retries with UNCHANGED while required technical state is missing. |
| Direct Radar history to governed research | Bypasses Evidence construction, governance and authentic consumption boundaries. |
| Define observation identity by Profile | Confuses mathematical state with selection policy. |

## Consequences and tradeoffs

The policy is intentionally narrow and auditable: all six changed-state pairs
are meaningful and all three unchanged-state pairs are not. EQUAL transitions
may be frequent or transient; v1 adds no hysteresis, tolerance or numeric
materiality threshold. Those costs cannot be optimized away by silently changing
revision-1 semantics.

New-session observations and corrections can update state without escalating.
The policy detects only differences between accepted bounded observations, not
every intermediate market transition. It does not detect numeric movements that
leave relation unchanged or corrections outside ADR0048's retained history.

Calculation/fact reuse avoids redundant computation and preserves execution-local
acquisition semantics. Coordinated persistence and legacy-baseline recovery add
implementation work, but prevent a false UNCHANGED result from hiding incomplete
observation state. Fingerprints support correspondence, never authority.

## Implementation implications

Implementation remains a separate reviewed slice. It must introduce explicit
observation/decision contracts, preserve existing EMA mathematics through a
shared fact/calculation boundary where practical, and implement comparison before
application-owned advancement. It must retain actual Pipeline/Profile
correspondence without making Profile part of mathematical observation identity.

Before enabling durable comparison, specify the versioned state migration,
bootstrap, commit and recovery protocol. Do not bolt an external best-effort
postprocessor onto the current checkpoint save. Preserve lazy provider validation,
injected HTTP access, fresh execution-local acquisition, original Gate order,
actual-result projections and ordinary batch failure isolation.

No production API signatures or storage file formats are frozen here. No current
module, checkpoint, test or production behavior is changed by this ADR draft.

## Future implementation test obligations

- First observation initializes baseline, including SELECTED bootstrap, with no
  meaningful change or synthetic prior state.
- ABOVE -> ABOVE on a new session advances eligible observation with no change.
- ABOVE -> BELOW and BELOW -> ABOVE on a new session are meaningful.
- All four transitions involving EQUAL are meaningful; EQUAL -> EQUAL is not.
- Same-session correction with unchanged relation is not meaningful; changed
  relation produces CORRECTED_CONTENT_STATE_TRANSITION.
- New-session transitions produce NEW_SESSION_STATE_TRANSITION, including valid
  rolling 250-session scopes and gaps between executions.
- Same-session identical content with different relation is incoherent, not a
  transition or an acceptable state advance.
- Incompatible calculation revision initializes a new baseline without a
  transition; incompatible observation semantics prevent comparison and retain
  bounded incompatibility provenance.
- Wrong instrument, corrupt/unavailable prior state and reversed session order
  cannot masquerade as legitimate baseline migration.
- Profile selection changes do not redefine mathematical observation identity;
  actual decision and eventual selection correspondence remain explicit.
- Downstream FILTERED can advance valid lightweight state; earlier DROP without
  a qualifying Trigger does not fabricate an observation.
- ATTENTION, FAILED and unavailable/incoherent observations do not advance.
- Failure injection before, at and after the authoritative commit point cannot
  expose an advanced market checkpoint with missing required lightweight state.
- Retry after persistence failure remains possible; incomplete/recovery state
  cannot return ordinary UNCHANGED and silently lose the transition.
- Legacy content-only checkpoint bootstrap is explicit and does not manufacture
  prior relation from logs, fingerprints or corrected historical data.
- No Candidate is generated; no Evidence admission, governed consumption or
  investment authority is inferred.

## Non-goals

- RadarCandidate implementation, Candidate persistence or delivery.
- Governed research execution or redesign of v0.82 governance.
- Acquisition reuse/no-refetch bridge.
- Additional indicators, numeric materiality, price-move or volume thresholds.
- Ranking, scoring, BUY/SELL/HOLD, target prices, stops or position sizing.
- CLI, scheduler, database, queue, locking or concurrency.
- Agent-selected rules or silent Profile/policy rewriting.
- Implementation-level file format selection for new state.
