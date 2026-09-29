# ADR 0050: Radar Candidate and Escalation Boundary

## Status

Accepted for v0.84 Candidate / Escalation Boundary.

This ADR accepts the **Passive Candidate Decision Boundary** as the architecture
checkpoint for v0.84. The decisions below are normative. Candidate implementation
and production activation remain separate future work; neither is claimed or
authorized by this architecture acceptance. Released v0.83 ADRs and handoffs
remain frozen.

## Context and inspected baseline

Local, read-only verification before drafting established:

- HEAD, `main` and local `origin/main`:
  `b13b5a044909b8085b3bf54ebdfcafba3f213a5c`.
- Released annotated tag: `v0.83.0`; tag object:
  `5bfe1dc92d8e2dba8e0b30c3962584036e70d3f3`.
- Peeled release merge: `99e9986757a73df90a3200e9acaab9482bfcc06c`.
- Clean worktree, empty index and no untracked paths. No fetch or network request
  was performed; `origin/main` here means the locally retained remote-tracking ref.
- ADR0049 was the highest existing ADR number; 0050 was available.

The supplied next-phase reconnaissance recommends a passive RadarCandidate,
fixed versioned eligibility policy and pure decision function. The following
important premises were reconfirmed against the released repository.

### EXISTING v0.83 CONTRACT

| Inspected source | Existing contract relevant to this decision |
| --- | --- |
| [Radar application](../../src/market_platform/radar/application.py) | A normal `RadarApplicationResult` retains the actual Pipeline and advancement. `SAVED` requires corresponding checkpoint, complete state and MeaningfulChange decision. The application validates the result before publication and returns it after `save_state` succeeds. Preparation/publication failures raise separately. |
| [Pipeline](../../src/market_platform/radar/pipeline.py) | The actual executed Profile prefix and failure determine outcome; selection alone grants no authority. |
| [Observation state](../../src/market_platform/radar/observation_state.py) | `radar_observation_state/v1` retains market/lightweight observations, committed decision, Profile fingerprint and SELECTED/FILTERED outcome. Structural validation cannot prove execution or commit. |
| [MeaningfulChange](../../src/market_platform/radar/meaningful_change.py) and [lightweight observation](../../src/market_platform/radar/lightweight_observation.py) | Revision-1 EMA8/EMA20 relation comparison recognizes all six changed relation pairs. Passive observation identity tokens alone do not establish an approved producer. |
| [Checkpoint store](../../src/market_platform/radar/checkpoint_store.py) | One latest record per instrument is replaced at `os.replace`; no Candidate log, delivery record, directory-fsync guarantee or concurrent-writer protocol exists. |
| [Single-symbol](../../src/market_platform/application/radar_single_symbol.py) and [batch](../../src/market_platform/application/radar_batch.py) compositions | Production returns observation/application results; batch is sequential with per-symbol failure isolation. Neither creates Candidates. |
| [Canonical fingerprint](../../src/market_platform/_fingerprint.py) | `canonical_fingerprint` hashes a schema-bearing canonical JSON payload; it provides deterministic correspondence, not authority. |

Ordinary advancement permits SELECTED or downstream FILTERED after an actually
executed qualifying Session/Content Trigger PASS. A FILTERED observation can
therefore retain a meaningful transition. Legacy content-only `UNCHANGED` is a
distinct application-owned bootstrap: FILTERED/SAVED with a real current
observation and `BASELINE_INITIALIZED`, never a synthetic EMA execution or
historical transition. Complete-state Level-0 `UNCHANGED` is NOT_ADVANCED.

[ADR0049](0049_radar_lightweight_observation_and_meaningful_change_policy.md),
especially Decisions 12, 14 and 15, defers Candidate lifecycle and governed
escalation and requires the post-commit delivery window to be addressed before
Candidate creation/delivery is enabled. The
[released handoff](../handoffs/v0.83.0-radar-handoff.md) confirms these exclusions.

### v0.84 PROPOSED DECISION

The decisions below freeze the proposed boundary between accepted Radar
observation state and future governed research escalation. Candidate means only
**eligible for governed research consideration**. It is not an approved
investment, recommendation, research conclusion, Evidence admission, permission
to trade or broker instruction.

Radar observes. Candidate records bounded escalation eligibility. Governed
Research separately authenticates and reasons. Candidate grants no authority
beyond consideration.

## Decision 1: Separate application ownership

Candidate creation MUST be a separate application-layer concern, initially in
`src/market_platform/application/radar_candidate.py`. It MUST NOT belong to
RadarPipeline, Gates, `radar/application.py` observation advancement, the
checkpoint store, governed Evidence admission or batch ranking.

The existing v0.83 runtime remains unchanged until a later explicit activation
decision. A passive decision function is not activation of production creation.

## Decision 2: Passive RadarCandidate

The future `RadarCandidate` MUST retain only the following canonical basis and
its derived fingerprint:

| Field | Contract |
| --- | --- |
| `source_observation_state` | Detached, revalidated `RadarObservationState` snapshot. |
| `eligibility_policy` | `RadarCandidateEligibilityPolicyIdentity` actually applied. |
| `schema_version` | `radar_candidate/v1`. |
| `fingerprint` | Derived through existing `canonical_fingerprint`, excluding itself. |

Do not duplicate independently writable instrument, Profile, outcome, time,
observation or decision fields already retained in the source state. Read-only
convenience accessors may be added later; canonical identity comes from the
complete source snapshot and policy. Projections MUST be detached.

Candidate MUST NOT contain BUY/SELL/HOLD, target, stop, sizing, recommendation,
broker/order instruction, research conclusion, Evidence admission/validity or
consumability claims, OHLCV/DataFrame, credentials, ranking/score, delivery
status, retry count or scheduler state. It MUST NOT add wall-clock `created_at`
or `accepted_at`, or a random UUID. Existing source `observed_at` and `as_of`
remain provenance and participate in the retained snapshot.

## Decision 3: Candidate is not bearer authority

A RadarCandidate value, JSON projection or fingerprint does NOT prove:

- Radar execution actually happened or observation state was committed;
- the qualifying Trigger actually ran;
- Candidate was durably accepted or delivered;
- Evidence is consumable or governed research must execute;
- trading is authorized.

Passive types and fingerprints establish bounded correspondence and
reproducibility, not authority. Production creation MUST use a trusted
application-owned source boundary. The first slice consumes a normal trusted
`RadarApplicationResult`; caller-constructed dataclasses and JSON objects are
not portable authority tokens. Structural revalidation cannot authenticate an
internally consistent fabrication or replace trusted source ownership.

## Decision 4: Fixed, closed eligibility policy

`RadarCandidateEligibilityPolicyIdentity` is separate from Profile selection,
MeaningfulChange policy and observation calculation identity. Its closed v1
identity is:

- `policy_id`: `selected_meaningful_transition`;
- `behavioral_revision`: `1` (the repository's string revision convention);
- schema: `radar_candidate_eligibility_policy/v1`.

There are no configuration knobs in v1. Profile is NOT escalation policy.
Directional preferences, price/volume thresholds, ranking, regime conditions and
arbitrary callbacks MUST NOT be silently added. A later behavior change requires
an explicit policy revision and architecture decision. Unsupported identities
fail closed rather than falling back to this policy.

## Decision 5: Eligibility requires accepted selection and transition

All of the following MUST hold together:

1. Actual Pipeline outcome is `SELECTED`.
2. Actual application advancement is `SAVED`.
3. A corresponding `RadarObservationState` is present.
4. Its committed MeaningfulChange classification is `STATE_TRANSITION`.
5. Its derived `meaningful_change` is true.
6. The decision and observations use approved MeaningfulChange/observation
   semantics.
7. The actual executed Pipeline results contain the Session/Content Trigger
   with disposition `PASS` and reason `BASELINE_REQUIRED`,
   `NEW_COMPLETED_SESSION` or `MARKET_CONTENT_CHANGED`.
8. Existing instrument, exact Profile, outcome, `as_of`, checkpoint, state and
   decision correspondence all validate.

The qualifying Trigger is the existing
`session_content_trigger / 1 / session_content_trigger/v1` identity with empty
configuration, matched to its actual Profile occurrence and executed result.
A configured-but-skipped Trigger, unrelated Gate with the same reason text or
synthetic substitute does not qualify.

Approved transition semantics in v1 are
`ema8_ema20_relation_transition / 1 / radar_meaningful_change_decision/v1`
over comparable `ema8_ema20_relation_observation / 1 /
radar_ema8_ema20_observation/v1` observations with approved
`radar_market_content_scope/v1` semantics. All six changes among ABOVE, EQUAL
and BELOW qualify without directional preference. Gate configuration does not
redefine observation mathematics.

Under normal v1 semantics a STATE_TRANSITION cannot arise from BASELINE_REQUIRED.
The Trigger reason requirement is execution provenance, not a way to infer the
MeaningfulChange result. Revalidate the committed decision and available
comparison provenance; do not infer eligibility from reason strings alone or
parse EMA Gate reason strings.

## Decision 6: FILTERED transitions remain observations

A FILTERED observation may be SAVED and meaningful. It is nevertheless
ineligible for Candidate creation. It MUST NOT be resurrected because a Profile
changes, a later execution is SELECTED but unchanged, a later policy would have
selected it, or historical replay knows the outcome.

A genuinely later accepted SELECTED transition is evaluated on its own source
basis. No historical selection or transition is reconstructed.

## Decision 7: Baseline, unchanged and failure exclusions

No Candidate is created for BASELINE_INITIALIZED,
INCOMPARABLE_BASELINE_INITIALIZED, STATE_UNCHANGED, true complete-state Level-0
UNCHANGED retry, legacy UNCHANGED bootstrap, ATTENTION, FAILED or earlier
FILTERED. Prepared-but-uncommitted state and failed publication are not accepted
sources; neither a preparation result nor an advancement exception is a normal
successful application result.

No historical relation reconstruction, hindsight or backfill is implied.
Recognized incompatible prior identity retained by a valid incomparable baseline
is non-comparison provenance, not approval of that prior's semantics for a
transition. Unsupported current observation or applied policy semantics fail
closed; a valid incomparable baseline remains an ordinary negative decision.

## Decision 8: Pure decision contract and precedence

The future `RadarCandidateDecision` contains the applied eligibility policy, a
bounded reason and an optional RadarCandidate. Eligibility is derived from
Candidate presence; there MUST NOT be an independently writable `eligible`
boolean. Candidate presence MUST agree with ELIGIBLE and its applied policy;
negative reasons MUST carry no Candidate.

For **valid application results**, freeze this deterministic precedence:

| Order | Condition | Reason / payload |
| --- | --- | --- |
| 1 | Pipeline outcome is not SELECTED | `NOT_SELECTED`, no Candidate. |
| 2 | SELECTED, but advancement is not SAVED | `NOT_ADVANCED`, no Candidate. |
| 3 | SELECTED + SAVED, but committed decision is not a meaningful STATE_TRANSITION | `NO_MEANINGFUL_TRANSITION`, no Candidate. |
| 4 | All eligibility conditions hold | `ELIGIBLE` with Candidate. |

Malformed or contradictory input is an error, not a negative reason or an
additional ordinary `ERROR` decision value. Validate input invariants before
applying negative-result precedence; an early NOT_SELECTED must not hide an
impossible SAVED claim. A purported ordinary SAVED source lacking the required
actual qualifying Trigger execution is an error, as are mismatched source
correspondence and contradictory Trigger/decision provenance.

The existing valid legacy FILTERED/SAVED UNCHANGED bootstrap is an explicit
exception to ordinary advancement, not malformed input: preserve its baseline
semantics and return NOT_SELECTED. It never satisfies Candidate eligibility.
Complete-state UNCHANGED retry is likewise NOT_SELECTED under its actual
FILTERED outcome, without manufacturing a fresh decision.

## Decision 9: Pure evaluator

The first-slice interface is conceptually:

```text
evaluate_radar_candidate(application_result, *, policy) -> RadarCandidateDecision
```

It MUST be synchronous and pure, consuming the actual RadarApplicationResult
from the trusted application boundary. It MUST inspect actual Pipeline executed
results for qualifying Trigger execution, revalidate exact existing types and
nested result/state correspondence, and detach the retained source. Loose
duck-typed input or matching summary strings are insufficient.

It has no provider, calendar, filesystem/store, clock, network, Context fact
loading, governed research service, Candidate persistence or delivery dependency.
It neither reruns Gates nor reacquires data to establish the prior relation.
Calendar/acquisition acceptance remains the trusted source boundary's
responsibility; passive validation does not independently prove it.

## Decision 10: Identity and fingerprint

Reuse `market_platform._fingerprint.canonical_fingerprint`; introduce no new
hashing system. The fingerprint payload binds `schema_version = radar_candidate/v1`,
the complete detached `source_observation_state` projection and the
`eligibility_policy` projection. Exclude the fingerprint itself.

The snapshot transitively binds canonical instrument, evaluation `as_of`, source
`observed_at`, Profile fingerprint, actual Pipeline outcome, market content
identity/scope/session, current/prior lightweight observations, observation
definition/revision/schema and MeaningfulChange policy/classification/reason/
comparison provenance.

The fingerprint is a correspondence/deduplication identity, deterministic for
the exact same accepted source snapshot and policy. It does not imply a
deduplication registry. It is not a commit receipt, delivery acknowledgment,
Evidence identifier, research execution ID or investment authority token.
Do not include new current time, random UUID, batch position or later research
identity. Equality of relation alone does not imply Candidate identity equality.

## Decision 11: Persistence and delivery are deferred

The first slice has NO durable Candidate lifecycle. Do not extend
`radar_observation_state/v1`, add Candidate to the v0.83 checkpoint file, add a
Candidate store/queue/outbox or delivery acknowledgment, claim at-least-once or
exactly-once behavior, or activate Candidate return in current production APIs.

The existing post-commit window remains:

```text
observation commits -> process may terminate -> Candidate may never be produced/delivered
```

The committed state can deterministically reconstruct the passive Candidate
value only while the exact eligible source snapshot remains retained and the
same approved policy applies. That statement does not authorize a state-only
production evaluator or turn stored bytes into proof of qualifying execution.
The first evaluator still requires the trusted application result. Any recovery
boundary must separately establish trusted source provenance.

The current latest-only store can overwrite the source later. Deterministic
identity therefore does NOT solve reliable delivery. ADR0049's requirement
remains: delivery/recovery semantics MUST be addressed BEFORE production
Candidate creation/delivery is activated. No new lifecycle guarantee is added
to the existing single-owner observation publication contract.

## Decision 12: Research and Evidence boundary

Radar's normalized 250-session history is NOT Evidence. RadarCandidate is
distinct from the existing governed Evidence Candidate construction contracts;
it carries no EvidenceArtifact or consumability claim. The authority shortcut
`Candidate -> DataFrame -> governed Research` is forbidden.

A future research escalation application MUST establish the existing chain:

```text
Construction -> Validation -> Freshness -> Admission -> Validity
-> Qualification -> Bridge -> Technical -> Interpretation -> Assessment -> Strategy
```

Existing authenticity, history, availability, freshness and consumption checks
remain in force. Research services may refuse a valid Candidate. The current
[Qualification](../../src/market_platform/application/polygon_completed_daily_production_qualification.py)
to [Bridge](../../src/market_platform/application/polygon_completed_daily_production_bridge.py)
conversion is a downstream governed representation adapter, not Radar ingress.
See [ADR0039](0039_production_evidence_governance_and_governed_daily_technical_consumption.md)
and the later governed Interpretation, Assessment and Strategy ADRs.

## Decision 13: Research bridge timing

| Capability | Planning classification |
| --- | --- |
| Candidate identity/reason to governed research orchestration | LATER v0.84 SLICE; requires its own reviewed orchestration/activation decisions. |
| Radar raw-acquisition reuse / no-refetch Evidence bridge | DEFERRED BEYOND the minimal v0.84 milestone unless separately justified. |

No no-refetch promise is frozen here. The current temporal mismatch is material:

- [Radar calendar](../../src/market_platform/radar/calendar.py) completes a
  session at its actual exchange close, including early closes.
- [Evidence ingress](../../src/market_platform/evidence_ingress/polygon_completed_daily_ohlcv.py)
  restricts completed rows to session dates before the New York query date;
  query time must not exceed response receipt. Research analysis applies its
  own session-date cutoff, and qualification separately binds analysis/effective
  and knowledge cutoffs.
- [ACTIVE validity issuance](../../src/market_platform/application/polygon_completed_daily_production_validity.py)
  sets recorded/effective time to actual issuance completion.

Radar `as_of` MUST NOT simply be copied into a newly executed governed chain.
Timing/cutoff and acquisition provenance need a separate decision before such
orchestration or reuse; Candidate eligibility does not resolve them.

## Decision 14: Batch and watchlist boundary

The first slice changes neither `run_single_symbol_radar` nor `run_radar_batch`.
Batch remains sequential and does not collect Candidate outputs, rank,
prioritize or dispatch research. No durable watchlist, universe or scheduler is
required. Future outer orchestration may apply Candidate evaluation to each
successful Radar response while preserving per-instrument source correspondence.

## Decision 15: First implementation slice

The first v0.84 implementation slice is NON-ACTIVATING and is limited to adding:

- `src/market_platform/application/radar_candidate.py`;
- `tests/unit/test_radar_candidate.py`.

Intended contracts are `RadarCandidateEligibilityPolicyIdentity`,
`RadarCandidate`, `RadarCandidateDecision`, a bounded Candidate decision reason
enum and `evaluate_radar_candidate(...)`.

No existing production/test file modification should be required unless a
genuine contract conflict is discovered and reviewed. There is no runtime
composition activation, persistence, research execution, required package-root
re-export or dependency change. These paths describe future implementation;
this ADR creates neither file and authorizes no implementation in this task.

## Decision 16: Future implementation test obligations

Use cheap pure Candidate tests plus focused pure/application regressions:

- SELECTED/SAVED new-session and corrected-content transitions yield ELIGIBLE;
  cover all six changed relation pairs without directional preference.
- SELECTED/SAVED baseline, incomparable baseline and unchanged decisions yield
  NO_MEANINGFUL_TRANSITION.
- FILTERED meaningful transitions, ATTENTION and FAILED yield NOT_SELECTED;
  valid SELECTED/NOT_ADVANCED yields NOT_ADVANCED.
- Complete-state UNCHANGED retry and legacy bootstrap produce no Candidate;
  preserve the actual outcome and the valid legacy advancement exception.
- Malformed correspondence and missing, nonqualifying or synthetic Trigger
  substitutions on purported ordinary SAVED sources raise errors. Distinguish
  detectable contradiction from the inability to authenticate a fully coherent
  caller fabrication; no test may imply portable bearer authority.
- Unsupported applied policy/current observation semantics fail closed;
  incompatible-prior baseline provenance does not become a transition.
- Exact source/policy repetition gives the same fingerprint. Corresponding
  source, Profile, instrument and decision changes affect identity; policy
  identity is bound in the payload. Unknown policy revisions are rejected,
  not enabled merely to exercise fingerprint variation.
- Source and JSON projections are detached; prohibited authority-bearing and
  operational fields are absent. Eligibility derives only from Candidate
  presence, with reason/policy consistency enforced.
- No clock, provider, calendar, store, Context loading or research service is
  needed. Negative-reason precedence applies only after invariant validation.

A full suite is NOT required for the non-activating first slice unless review
finds a shared-core/high-risk reason. This documents future validation; no
pytest, Ruff, mypy or runtime tests are run for this architecture-only draft.

## Alternatives rejected

| Alternative | Rejection reason |
| --- | --- |
| Candidate creation inside Pipeline, Gate or observation commit | Mixes execution/observation ownership with escalation policy and activates the existing runtime. |
| SELECTED, Trigger reason or content difference alone implies eligibility | Includes baselines/unchanged observations and omits accepted transition correspondence. |
| Duplicate source fields or a writable eligible flag | Permits contradictory identity and decision representations. |
| Treat Candidate fingerprint as execution/commit authority | Passive deterministic values cannot authenticate issuance or publication. |
| Recover FILTERED transitions through later selection or replay | Rewrites the actual accepted selection basis using hindsight. |
| Extend the current checkpoint with Candidate delivery state now | Prematurely chooses a lifecycle beyond the passive slice. |
| Direct Radar history injection into Research | Bypasses the governed Evidence chain and ignores cutoff differences. |

## Consequences and tradeoffs

The passive boundary can be implemented and tested without activating the
production runtime or coupling Candidate to providers and research services.
Retaining the complete source snapshot avoids independent copies of provenance
and preserves the actual bounded comparison basis. It also binds source
acceptance time and Profile identity, not merely a market relation.

Eligibility stays narrow: baselines and filtered transitions are remembered
without escalation, and all approved relation changes are treated equally.
Callers must retain trusted execution context; neither JSON portability nor
deterministic identity solves authentication or delivery. Latest-only storage
leaves recovery limits that must be addressed before activation.

The following are later activation questions, not blockers for the passive
slice. This ADR does not decide them:

1. Is delivery best-effort, or does it require a recoverable/at-least-once style
   lifecycle?
2. How do eligible source events survive latest-only state overwrite?
3. What governed research timing and cutoffs apply after a Radar event?
4. What service-history lifetime and research execution idempotency are required?
5. What policy-version context governs historical recovery/backfill?
6. Is no-refetch acquisition reuse worth a separate provenance contract?

## Non-goals

- Production Candidate activation, persistence or deduplication registry.
- Delivery/recovery, acknowledgment, queue or outbox.
- Governed research execution, Evidence creation/admission shortcut or no-refetch
  bridge.
- New indicator Gates, Profile rewriting, ranking or scoring.
- Watchlist/universe/scheduler, async redesign or CLI/agent facade.
- Scenario/Risk/Plan, trading/execution or Shadow Observer.

This decision-document slice changes no existing production code, tests, ADRs,
handoffs, storage schema or runtime behavior.
