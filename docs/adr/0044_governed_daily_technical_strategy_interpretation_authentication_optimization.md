# ADR 0044: Governed Daily Technical Strategy Interpretation Authentication Optimization

## Status

Accepted

This ADR proposes the narrow Option C architecture authorization for the v0.82.0
performance correction. Acceptance and implementation require separate
authorization. This drafting step authorizes no production or test changes,
staging, commit, push, merge, tag or release. Option D is not authorized.

## Context and inspected baseline

Verified authoring baseline:

- Branch: `feature/v0.82.0-governed-daily-technical-strategy`.
- HEAD: `5b73620a532d1eec7767f82b460adb69a5873e43`.
- Frozen local `main`: `a94a1b49ad9eea036dab3d543e239fb82fb438e1`.
- [ADR0043](0043_governed_daily_technical_strategy.md): Accepted and unchanged.
- Exactly four existing modified, unstaged files: the application Assessment
  and Strategy modules and their corresponding `tests/unit/` modules. Their
  existing A+B corrections are preserved byte-for-byte during this draft.
- ADR0044 was unused; the filename follows the recent snake_case ADR convention.

The supplied correctness review reports BLOCKER: 0 and REQUIRED: 0 after the
late-pair seal-ordering correction. A+B remains valid: two complete Assessment
preparations and two specialized Assessment final seals for the representative
two-execute fixture. Public/frozen behavior remains unchanged. This ADR does
not repeat that review's tests or independently reproduce its measurements.

Supplied performance evidence:

| Measurement | Result |
| --- | --- |
| Original representative uninstrumented call | 557.26s |
| Current three uninstrumented calls | 279.90s, 276.08s, 200.40s |
| Current median | 276.08s; both release gates failed |
| Profiled Strategy execute, twice | 638.319508s cumulative |
| Assessment preparation, twice | 425.521023s |
| Assessment specialized final seal, twice | 212.346518s |
| Direct Assessment to Interpretation authentication edge, 12 calls | 637.660386s; 99.896741% of Strategy cumulative time |
| Time outside that edge | Approximately 0.659122s |

The measured Strategy path performs 12 Interpretation occurrence
authentications, 48 Interpretation support authentications, 24 retention sweeps,
48 Technical occurrence authentications and approximately 11,496 source-derived
Governance profile resolutions. There are two Assessment publications and two
Interpretation publications; both Interpretations bind the same Technical
occurrence. Governance/fingerprint costs are nested beneath repeated complete
Interpretation authentication. Instrumented cumulative time is diagnostic,
not interchangeable with the uninstrumented release gate. Release remains paused.

## Decision 1: Narrow extension of ADR0043

ADR0043 remains authoritative for Governed Daily Technical Strategy. This ADR
extends/supersedes **only the v0.82 scope restriction** in Decision 14 that names
the private additive Assessment consumption contract as the sole required
existing-production extension. It additionally permits a private Interpretation
transaction-local complete preparation/final-revalidation seam, consumed only
by the pinned Assessment authority during governed Strategy execute/history.

ADR0043 Decision 3 explicitly names the released
`_authenticate_interpretation_occurrence`. Within this narrow workflow, the
additive seam may discharge that complete authentication obligation in batch
instead of calling that method separately for each selector. This is the
necessary procedural consequence of the scope extension, not a relaxation of
Decision 3's authority, correspondence, complete-support or failure requirements.
Independent callers continue to use the unchanged released capability.

ADR0043 Decisions 3, 10, 11 and 12 authority and final-seal requirements remain
binding, as do Decision 13 refusal contracts, the no-bearer/no-subsequent-call-
trust rule and all frozen public boundaries. ADR0043 is not rewritten. Existing
A+B Assessment/Strategy preparation and specialized final sealing remain valid.

For later separately authorized implementation, production changes are limited to:

- `src/market_platform/application/polygon_completed_daily_production_interpretation.py`:
  the additive private seam inside the existing authority.
- `src/market_platform/application/polygon_completed_daily_production_assessment.py`:
  already-authorized private Strategy consumption integration points.

Strategy consumes the resulting Assessment private behavior through its existing
authority model; no Strategy production change or new authority concept is
authorized here. There is no authorization to change Technical, Bridge,
Qualification, Construction, Validation, Freshness, Admission, Validity,
Governance, Evidence, domain schemas, package exports, CLI, Agent or trading
layers. Public Assessment execution/history and released Interpretation behavior
remain frozen. Do not introduce a generic authentication framework.

## Decision 2: Private complete Interpretation preparation

Authorize an additive private preparation operation, conceptually
`_prepare_interpretation_inventory...`; exact helper names/layout are not frozen.
It executes inside the already-acquired, pinned complete Strategy lock
transaction and acquires no locks. Before Assessment local selection or
correspondence uses prepared Interpretation data, it must:

1. Capture and authenticate the original Interpretation service/publisher,
   owner, namespace, lock, commitment and transaction-start committed-state
   identity through the pinned Assessment authority. Require original idle
   pending state and the existing independent owner/commitment agreement.
2. Authenticate the COMPLETE committed Interpretation inventory: reconstruct
   and validate every retained fact, exact canonical bytes and schemas,
   fingerprints, retained structural/self-consistency constraints, chronology,
   namespace, unique IDs, ordered contiguous sequences and count/next-sequence.
3. Authenticate every Interpretation's exact original Technical occurrence,
   original issuance and complete original upstream support required by the
   released capability, including retention/observation anchors. Equal values or
   a shared Technical binding do not independently establish original issuance.
4. Capture complete canonical Interpretation facts, exact retained selectors,
   exact Technical bindings and detached support expectations for continuity.
   Recheck correspondence and original roots after fallible preparation.
5. Cover unrelated, unselected and invisible entries before any selection or
   visibility filtering. Empty downstream selections do not bypass a nonempty
   Interpretation inventory; empty inventories still require root/state and
   applicable retained-support validation.

The prepared inventory is private, transaction-local, data-only,
non-authoritative by itself, non-serializable and non-exported. It may contain
detached working values, canonical bytes and scalar correspondence expectations.
It must contain no publisher authority, mutable owner authority, transferable
lock authority, pending mutation authority or callbacks capable of granting
authority. No public API accepts or returns it; copying or possession grants
nothing, and it is unusable by a later independent call.

Trusted transaction orchestration retains the original root/state/lock and
Technical occurrence identity anchors separately from the data-only inventory.
Those anchors are captured through the pinned authority under the held locks,
never reconstructed from the prepared data or supplied by an independent caller.
The implementation must enforce call lifetime even if state values and identities
are unchanged across successive calls. A type check, digest or previous success
alone cannot establish that the preparation belongs to this transaction.
Do not persist the batch, transaction authentication state or successful proof.

## Decision 3: Assessment batch resolution

During the SAME still-locked transaction, complete Assessment preparation may
resolve all retained Assessment-to-Interpretation bindings against one prepared
complete Interpretation inventory. This replaces selector-driven repeated
standalone occurrence authentication during that local preparation.

Every Assessment must resolve conjunctively to its exact committed Interpretation
selector, membership, complete canonical fact and original Technical binding.
Preserve all five Interpretation selector components, including the complete
artifact projection and envelope fingerprint, and all ADR0043 pair correspondence
requirements. There is no latest lookup, independent Interpretation choice,
selector substitution or content-equivalent replacement. Shared bindings do not
remove checks of each Assessment's retained correspondence.

Complete Assessment and Interpretation inventory/support authentication precedes
selection. A batch from another call cannot authenticate the transaction. Local
resolution does not replace the required fresh final complete authentication.

## Decision 4: Final complete Interpretation revalidation

The pinned Assessment authority invokes the private Interpretation final seal
after all fallible Assessment/Strategy local preparation and before downstream
commitment advancement or a successful history return. The seal proves continuity
from the ORIGINAL transaction state; it never treats the prepared batch alone
as authentication proof or adopts a newly observed state as the baseline.

Require an explicit inventory-wide phase boundary:

1. **Complete local preparation.** Finish ALL fallible local preparation for the
   entire Interpretation inventory and all upstream-support expectations,
   including reconstruction, copies, projections, codecs, graph checks, retained
   value validation and every Assessment-bound correspondence expectation.
   Finish downstream return/result-tuple and next-state preparation beforehand.
2. **Complete canonical recheck.** After all phase-1 work, recheck canonical
   working data, complete facts and selectors across the ENTIRE prepared
   Interpretation inventory against the original committed facts. Include every
   Assessment-bound selector and all unrelated entries. Do not restart local
   preparation in this pass or mix it with fresh support authentication. A later
   entry's fallible work must not leave an earlier entry unchecked.
3. **Fresh complete original-support revalidation.** Through the original pinned
   authority, freshly authenticate every retained Interpretation's exact original
   Technical occurrence/issuance and the complete original upstream support.
   Compare against independently captured original expectations. Detect persistent
   support loss, replacement or drift introduced during any later local work.
   This is a complete support operation, not selected-source authentication or
   equality against saved successful results. Its internal ordering must also
   prevent later-entry fallible support work from invalidating an earlier check
   unnoticed. Any preparation needed by this phase must precede its final fresh
   support boundary; its complete proof must hold when the phase finishes.
4. **Direct-only tail.** Perform only direct root/identity/scalar checks against
   original anchors. No property dispatch, callbacks, codecs, reconstruction,
   allocation, copy, clock, validator, projection, graph traversal or additional
   local history/domain work may occur after the final fresh-support boundary.
   Existing direct original-owner pending cleanup, preallocated downstream state
   advancement and return remain governed by ADR0043; reads mutate no authority.

Together these phases must prove original publisher/root/owner/namespace/lock
continuity, exact transaction-start committed-state identity, complete current
Interpretation membership, canonical bytes/facts/order/count/sequence continuity,
every retained entry (including unreferenced ones), every Assessment-bound
selector, exact original Technical binding and complete original support.
Finish with direct root/state checks. Equal-value authoritative commitment
replacement fails even if both owner state and service commitment are replaced
together. Exact equal immutable fact bytes represent equal content; byte-object
identity is not a substitute for authoritative state identity.

This preserves the A+B late-pair correction: finish fallible work for all entries,
recheck all prepared facts, freshly authenticate complete support, then perform
only direct checks. A per-entry prepare/check/seal loop alone is insufficient.

## Decision 5: Released capability, invariants and failures

The released standalone private `_authenticate_interpretation_occurrence` retains
its current signature, independent-call behavior, complete authentication,
failure semantics and return contract. It must not accept a prepared batch as
proof or become a weakened shortcut. The new seam is additive and confined to
the pinned Assessment Strategy workflow.

The following remain mandatory:

1. Complete Interpretation inventory authentication and exact committed membership.
2. Exact Assessment-to-Interpretation and Interpretation-to-Technical bindings.
3. Original Technical issuance and complete historical upstream support, including
   original retention anchors, governance, mapping, material and lifecycle support.
4. Unrelated, unselected and invisible Interpretation coverage.
5. Current-support failure precedence and persistent loss/replacement detection.
6. Complete canonical fact correspondence; fingerprints alone confer no authority.
7. Original authoritative owner/root/namespace/commitment identity continuity;
   reject equal-state replacements, rollback, loss and substitution.
8. The unchanged eleven-lock order, acquired exactly once:
   Construction -> Validation -> Freshness -> Admission -> Validity ->
   Qualification -> Bridge -> Technical -> Interpretation -> Assessment -> Strategy.
   No new locks, reacquisition or public upstream execute/history under held locks.
9. No provider/source refetch, technical analysis or upstream lifecycle execution.
10. No semantic Interpretation rerun: no governed Interpretation execution/semantic
    validation, `classic_states` or `build_classic_comparison_evidence` in source
    authentication. Retained structural/self-consistency validation remains
    mandatory; independent Assessment/Strategy domain validation remains separate.
11. No public bearer capability, cross-transaction authentication cache or persisted
    authentication state; no repair, adoption, fallback or reissuance after drift.
12. Execute/history failure atomicity: no append, sequence consumption or partial
    commitment; preserve prior committed facts and perform original-owner pending
    cleanup. Do not promise rollback of external callback side effects.
13. Existing refusal classifications and all v0.80, v0.81 and ADR0043 public/frozen
    behavior, including zero-Enum isolation, schemas, fingerprints and exports.

Preserve structured failure routing, never classification by exception text:

| Failure | Existing application-boundary mapping |
| --- | --- |
| Interpretation occurrence unavailable/history invalid when supporting a committed Assessment | `_AssessmentHistoryInvalid` -> Strategy `history_incomplete_or_corrupt` |
| Authenticated retained lineage, selector or canonical pair correspondence mismatch | `_AssessmentSourceMismatch` -> Strategy `source_lineage_mismatch` |
| Valid complete current history/support with no exact requested Assessment | `_AssessmentOccurrenceUnavailable` -> Strategy `assessment_occurrence_unavailable` |

Complete current committed-history/support invalidity takes precedence over a new
selector miss; saved preparation must never hide support loss at the final seal.
Committed-source semantic corruption remains history-invalid, not candidate
Strategy semantic failure. Preserve A+B's distinction for late working-data
codec/correspondence drift as source mismatch and invalid authority/inventory as
history-invalid. All other ADR0043 boundary, temporal, semantic and publication
classifications remain binding. A new private structured failure is permitted
only if strictly necessary and mapped identically at the application boundary;
there is no new public refusal category.

## Decision 6: Performance intent and Option D exclusion

Option C must structurally eliminate selector-driven repeated complete
Interpretation preparation. Prepare the complete inventory once per locked
Strategy transaction, resolve Assessment bindings locally and retain fresh final
complete revalidation. This does not freeze an elapsed-time promise or an exact
Technical/Governance call count. Sharing a Technical occurrence is motivation,
not authorization to weaken or cache its authentication. Multiplicity expectations
must follow from the eventual compliant seam and be verified during implementation.

This ADR does NOT authorize Option D: Governance resolver memoization, fixed-profile
caching, Evidence policy/reference optimization, fingerprint caching, changes to
frozen validation semantics, or persistent authentication certificates/checkpoints.
If C fails, those require a separate architecture decision and implementation
authorization. They do not become implicit follow-up work under this ADR.

## Future implementation tests and acceptance obligations

These are obligations for later implementation, not checks run while drafting:

1. Prove complete Interpretation preparation occurs once per transaction and all
   exact Assessment bindings resolve from that inventory without selector-driven
   complete reauthentication. Include multiple Assessments and shared Technical
   bindings; add a structural multiplicity regression.
2. Cover unrelated/unselected/invisible entries, empty selections and complete
   membership, canonical bytes, ordering, count/sequence and selector failures.
3. Inject source/support loss and replacement between preparation and final
   revalidation, including original Technical occurrence loss or replacement.
4. Have later-entry fallible work mutate an earlier entry's working data, fact,
   selector or support; require rejection before downstream commitment. Include
   late codec drift and effects within the final complete support operation.
5. Reject equal-value authoritative commitment replacement, including replacement
   of both owner state and the independent commitment, root/namespace/lock swaps
   and swap-back around lock selection. Do not repair or adopt changed authority.
6. Reject prepared-batch reuse across calls, even without an intervening append;
   prove non-export/non-serialization and data-only contents. Verify unchanged
   standalone occurrence authentication, including refusals and fresh support.
7. Prove no new lock acquisition/order, provider/source refetch, semantic
   Interpretation rerun or upstream execution. Check the direct-only post-seal
   tail for execute and history and retain independent domain validation.
8. Verify execute/history failure atomicity, original-owner cleanup, unchanged
   prior facts/sequences, current-support precedence and identical structured
   refusal mappings, including identical-message failures of distinct categories.
9. Check all public/frozen surfaces: v0.80 Interpretation, v0.81 Assessment,
   ADR0043 Strategy, schemas, fingerprints, exports, zero-Enum isolation and the
   absence of new public authority or downstream trading/Agent integration.

## Performance release gate continuity

After Option C implementation, rerun the existing representative gate **from
scratch**: three uninstrumented comparable runs, median call **<= 240s**, and
**no individual call > 270s**. Preserve fixture, comparability and measurement
conditions; do not combine prior runs with new ones or substitute cProfile times.
These are engineering release gates, not authentication semantics or a guaranteed
architecture speedup. Do not weaken either threshold. If C still fails, release
remains paused and Option D remains unauthorized.

## Architecture consistency review

Internal document/source review checked ADR0043 Decisions 3, 10, 11, 12, 13 and
14; current A+B `_prepare_assessment_inventory`, prepared fact recheck and
`_seal_prepared_assessment_inventory`; released Interpretation
`_authenticate_interpretation_occurrence`, `_authentication_retention`,
`_authenticate_interpretation_support` and original Technical issuance use;
the current upstream lock chain; and Assessment/Strategy structured failure
translation. The late-pair regression was read, not executed.

The scope conflict with ADR0043 Decision 14 is explicitly addressed by Decision 1,
including Decision 3's named per-selector mechanism. Its authority requirements
remain intact. Capturing original identities does not place authority handles in
the prepared batch: trusted transaction anchors remain separate. The four-phase
seal carries forward A+B ordering and does not treat an earlier successful
preparation as fresh support. No unresolved architecture contradiction was found.

Implementation must demonstrate the phase-ordering and lifetime obligations;
this source/document review makes no claim that Option C is implemented, tested,
accepted or fast enough. No tests, static checks or performance runs were made
for this ADR. Findings for this proposed architecture: BLOCKER: 0, REQUIRED: 0,
OPTIONAL: 0. Release remains paused pending separately authorized implementation,
review and the unchanged performance gate.
