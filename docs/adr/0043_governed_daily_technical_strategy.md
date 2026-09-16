# ADR 0043: Governed Daily Technical Strategy

## Status

Proposed

This is the architecture draft for v0.82.0. It authorizes no implementation,
branch creation, staging, commit, push or release. v0.81.0 and every earlier
milestone remain released and frozen. New identifiers below are explicit
proposed v0.82 contracts; they are not claims about existing implementation.

## Context and verified baseline

Before drafting, branch `main`, HEAD, local `main`, local `origin/main` and
live remote `main` all identified
`a94a1b49ad9eea036dab3d543e239fb82fb438e1`. The working tree and index were clean.
The v0.81.0 release merge is `bbcfd7c78e4447230af93806e894e2a782d393d3`;
annotated tag `v0.81.0` has object
`811ed9527e58f4db46f6798e824428c9fac04557` and peels to that merge, locally and
on the live remote. Package version is `0.1.0`. Evidence has 69 ordered unique
exports.

Released evidence read and reconciled:

- [ADR0031](0031-daily-technical-strategy-foundation.md),
  [v0.74 handoff](../handoffs/v0.74.0-strategy-foundation-handoff.md) and
  [v0.75 handoff](../handoffs/v0.75.0-application-boundary-handoff.md): descriptive
  Strategy semantics, legacy exact-type contracts and separate application flow.
- [v0.80 handoff](../handoffs/v0.80.0-governed-daily-technical-interpretation-handoff.md),
  [ADR0042](0042_governed_daily_technical_assessment.md) and
  [v0.81 handoff](../handoffs/v0.81.0-governed-daily-technical-assessment-handoff.md):
  original publication authority, zero-Enum isolation, pinned owners, exact
  source selection, complete history authentication and final seals.
- `src/market_platform/research/daily_technical_strategy.py`,
  `classic_daily_technical.py` and `technical_policy.py`: exact released
  categories, `_classic_strategy_semantics`, runner restrictions and policy.
- `src/market_platform/application/daily_technical_strategy.py` and
  `daily_technical_strategy_service.py`: frozen v0.75 request/response and
  three-stage orchestration, distinct from governed publication authority.
- `src/market_platform/research/governed_daily_technical_interpretation.py` and
  `governed_daily_technical_assessment.py`: released scalar projections,
  fingerprints, occurrence selectors and independent Assessment validator.
- `src/market_platform/application/polygon_completed_daily_production_interpretation.py`
  and `polygon_completed_daily_production_assessment.py`: current private
  authentication, pinned publisher/owner, canonical bytes, execute and history.
- Relevant unit tests in `test_daily_technical_strategy.py`,
  `test_daily_technical_strategy_application.py`,
  `test_governed_daily_technical_assessment.py`,
  `test_polygon_completed_daily_production_interpretation.py` and
  `test_polygon_completed_daily_production_assessment.py`: mapping, isolation,
  structured failures, forbidden reruns, complete inventory and seal ordering.

Current code is authoritative when historical wording differs. In particular,
the released Assessment executor uses a slash after `market_platform.application`;
the Interpretation executor uses a dot. Neither released identity changes here.
The v0.81 application has no dedicated exact-Assessment downstream consumption
seam. Its `_authenticate_history_locked` performs Assessment semantic validation
and is not directly suitable as a semantic-free publication lookup.

## Decision 1: Milestone boundary and authority separation

Freeze v0.82.0 as **Governed Daily Technical Strategy**:

```text
authenticated v0.81 governed Assessment occurrence
→ authenticate the exact governed Interpretation occurrence bound by Assessment
→ deterministic governed descriptive Strategy
→ governed Strategy publication/history
```

Stop there. Keep four contracts distinct:

| Contract | Authority and preservation |
| --- | --- |
| Released Strategy semantics | The five-row mapping in `_classic_strategy_semantics` remains the sole classic rule implementation |
| Legacy exact-type runner | `derive_daily_technical_strategy` and `ClassicDailyTechnicalStrategyPolicy.determine` retain their exact legacy inputs, output, validation and exception behavior |
| New governed source/provenance | Exact committed Assessment selection and publisher-owned resolution of its bound Interpretation; no fabricated legacy provenance |
| New Strategy publication | A distinct application owns occurrence issuance, chronology, immutable committed facts and authenticated history |

Do not widen, wrap as the governed public boundary, or route governed execution
through the legacy runner, classic `determine`, v0.75 application or v0.76 Agent
exposure. A coherent domain value or fingerprint grants no publication authority.

## Decision 2: Assessment-only request

Freeze `PolygonCompletedDailyStrategyRequest` as an exact, frozen, slotted,
keyword-only value with exactly these five fields and serialized keys:

| Field | Exact contract |
| --- | --- |
| `artifact_reference` | Detached exact `GovernedTechnicalArtifactReference`, equal to the selected Assessment's retained source artifact reference |
| `assessment_history_namespace_id` | Exact built-in string `polygon_completed_daily_assessment_history:<32 lowercase hex>` |
| `assessment_history_sequence` | Positive exact built-in `int`; reject `bool` and integer subclasses |
| `assessment_execution_id` | Exact built-in string `polygon_completed_daily_assessment:<32 lowercase hex>` |
| `assessment_fingerprint` | Exact built-in `sha256:<64 lowercase hex>` string identifying the COMPLETE Assessment RESULT ENVELOPE |

There is no additional request schema, request fingerprint, policy, time override
or Interpretation selector. Preserve the complete artifact projection:
`schema_version`, `artifact_id`, `artifact_version`, `artifact_fingerprint`,
`information_class`, `authority`, `fingerprint`. Its released schema is
`evidence_artifact_reference/v2`; artifact and reference fingerprints differ.

Freeze this input order for public `execute` and public history:

1. Reject a non-exact outer input type before any clock or lock: execute requires
   `PolygonCompletedDailyStrategyRequest`; history requires
   `GovernedTechnicalArtifactReference`.
2. Defensively detach the exact caller-owned value, including the request's
   nested exact `GovernedTechnicalArtifactReference`, before invoking any
   caller-graph projection, fingerprint check or other fallible validation.
   Request construction must likewise detach its supplied exact artifact
   reference before validating that reference. Preserve supplied fingerprints
   during detachment; do not regenerate them or invoke caller-owned validation
   or projection methods to make the copy.
3. Validate the detached value's complete projection and retained fingerprints.
4. Capture the validated detached projection for later drift checks before
   proceeding to clocks, locks or other fallible workflow work.
5. Use only that detached input and captured projection; never adopt later caller
   mutation.

This adds no request fingerprint and changes none of the five selectors.

All five selectors match conjunctively against exactly one authentic committed
Assessment. Compare the entire artifact projection. Reject exact-type violations
and scalar subclasses, including string Enums; do not coerce arbitrary inputs.
Public execution accepts neither Assessment/Interpretation objects nor supplied
bytes as authority. No latest lookup, content-equivalence substitution or fallback
is permitted. The only Interpretation selector comes from authenticated
`assessment.source_interpretation_occurrence`.

## Decision 3: Private authenticated consumption pair

Specify one narrow, additive private consumption capability on the released
`PolygonCompletedDailyProductionAssessmentApplicationService`. Implementing it
later may add private helpers and private failure types in that module only;
it must preserve all v0.81 public exports, execute/history signatures, behavior,
serialization, semantic checks and fingerprints. Do not repurpose a public method
or add a public authority token, registration, import or append operation.

The contract resolves the five Assessment selectors to a private detached bundle
containing:

- the exact authenticated `PolygonCompletedDailyAssessmentResult`;
- the exact authenticated `PolygonCompletedDailyInterpretationResult` selected
  exclusively by that Assessment's retained binding;
- each complete committed canonical result fact, as exact immutable bytes, for
  correspondence checks against independently captured expectations.

The bundle has no publisher, owner, lock, pending or mutable authority handle.
It never crosses the Strategy public boundary and is never accepted from a
caller. Possession or copying of the bundle does not authenticate a subsequent
call. Private Python names/layout are implementation choices; the pair, root,
validation and failure contracts are mandatory.

The capability assumes the full upstream-through-Assessment lock chain is
already held. It acquires no locks and calls no public history or execute API.
It uses the Assessment publisher's original pinned Interpretation publisher and
the released `_authenticate_interpretation_occurrence` capability. Downstream
Strategy must not reach through public/replaceable surfaces to assemble a pair.

Before selecting, it must:

1. Validate the original Assessment owner, original namespace even when empty,
   idle pending state and independently pinned current commitment. Owner state
   must be that same committed state by identity; an equal replacement cannot
   establish authority. Capture state after acquiring the shared chain.
2. Authenticate the COMPLETE committed Assessment inventory, including facts
   unrelated to the request. Require exact bytes, canonical reconstruction and
   re-encoding, complete schemas/projections, content and envelope fingerprints,
   count/next-sequence consistency, contiguous positive sequences starting at 1,
   one namespace, unique execution IDs, valid chronology and nondecreasing
   publication availability. Reject rollback, truncation, replacement, reorder,
   missing facts and duplicate inventory against the independent commitment.
3. For every Assessment fact, use its retained five Interpretation selectors to
   authenticate the exact committed Interpretation and original historical
   support through the pinned Interpretation authority. This retains technical
   issuance, original occurrence identity, bridge, qualification, governance,
   instrument mapping and material support. Complete Interpretation inventory
   authentication remains required by the released private capability.
4. Validate nonsemantic pair correspondence: all five retained Interpretation
   selectors; complete artifact reference; Interpretation content fingerprint;
   canonical instrument; source trading identity; historical `analysis_as_of`;
   exact source quality and ordered warnings; fixed upstream policy projections;
   finding references to retained comparison IDs; exact retained
   `interpretation_available_at`; and Interpretation availability no later than
   the original Assessment execution start. Validate all released structural
   value constraints, including finding shape/order and retained comparison
   operand/operator/satisfied self-consistency.
5. Only after complete inventory/support validation, select by all five
   Assessment selectors. Return fresh reconstructions of BOTH committed results
   and their complete facts. Publications predating Strategy service construction
   are eligible; observation does not issue or adopt them.
6. Recheck complete inventory, original historical support, pair projections,
   caller selectors and pinned roots after fallible reconstruction/copy work.
   Persistent drift fails closed without repair or updating observations.

This authentication capability does not call Assessment execute, Assessment
derivation, `validate_governed_daily_technical_assessment` or the Assessment rule
helpers merely to locate/authenticate a publication. It does not call governed
Interpretation execution/semantic validation, `classic_states` or
`build_classic_comparison_evidence`. It never derives expected Interpretation
states or comparison inventory from a technical snapshot. Retained-value
structural/self-consistency validation remains mandatory, not bypassed.
It performs no provider fetch, technical analysis, lifecycle issuance,
qualification or bridge execution.

This is authentication of already-published decisions. Independent domain
validation in Decision 6 is separate, occurs after authentication, and does not
reissue or rerun either upstream application. Existing public Assessment history
continues its complete semantic validation unchanged.

Use private structured `ValueError` subclasses with these proposed names:

| Category | Meaning |
| --- | --- |
| `_AssessmentOccurrenceUnavailable` | Valid complete history has no exact selected Assessment occurrence |
| `_AssessmentHistoryInvalid` | Invalid Assessment commitment/inventory or lost required Interpretation/upstream support |
| `_AssessmentSourceMismatch` | Authenticated retained lineage or pair correspondence differs |

Translate the released `_InterpretationOccurrenceUnavailable` and
`_InterpretationHistoryInvalid` into `_AssessmentHistoryInvalid` when they concern
support for a committed Assessment. Translate `_InterpretationSourceMismatch`
into `_AssessmentSourceMismatch`. Complete-history failure takes precedence over
a selector miss. Classification uses types/categories, never exception text.

The same private capability must support a final complete source/support seal
against a preprepared inventory of expected pairs and complete facts. This is
one trusted contract with resolution and revalidation phases, not a second root
or bearer capability. Its final phase verifies every expected pair, the complete
Assessment inventory and bound Interpretation support without downstream code
performing fallible projections after the seal. Empty Strategy history still
validates the pinned Assessment root/inventory; an empty selection is not an
authentication bypass. Decision 12 specifies ordering.

## Decision 4: Released semantic mapping and zero-Enum values

Freeze the exact built-in string mapping verified against released code:

| Assessment outcome | Bound Interpretation trend / momentum | `mode` | `rule_code` |
| --- | --- | --- | --- |
| `insufficient_data` | Any valid retained directions | `no_active_strategy` | `insufficient_data_no_active_strategy` |
| `mixed` | Any valid retained directions | `no_active_strategy` | `mixed_no_active_strategy` |
| `caution` | Any valid retained directions | `no_active_strategy` | `caution_no_active_strategy` |
| `aligned` | `positive` / `positive` | `positive_directional_continuation` | `aligned_positive_continuation` |
| `aligned` | `negative` / `negative` | `negative_directional_continuation` | `aligned_negative_continuation` |

Unsupported aligned direction combinations and future/unknown outcomes or
directions fail closed. Released direction strings are exactly `positive`,
`negative`, `mixed`, `unavailable`. The first three rows do not bypass source
validation or authorize malformed Interpretation values.

Reuse `classic_daily_technical._classic_strategy_semantics` in the new research
module through minimal detached private views of `assessment.outcome` and
Interpretation `trend_direction` / `momentum_direction`. Private adaptation to
the released `DailyTechnicalAssessmentOutcome` and
`DailyTechnicalDirectionalState` Enums is permitted for helper identity checks.
Immediately project helper outputs to validated exact built-in strings. Do not
fabricate legacy source carriers or integrity fingerprints; do not modify the
helper or duplicate its five-row implementation in derivation or validation.
The application invokes domain boundaries, not private mapping helpers.

All governed public graphs contain zero reachable `Enum`, `StrEnum` or `IntEnum`
instances: request, references, content, policy/configuration, result, projections,
execute/history returns, properties, backing values and refusal reasons. All
categorical leaves are exact built-in strings. The artifact vocabulary remains
`source_observation`, `source_measurement`, `source_assertion` and
`platform_origin`, `external_origin`. No public legacy policy/adapter/Enum backing
object is allowed. Fresh detached `CanonicalInstrumentId` and canonical UTC
datetimes retain their released scalar contracts.

Every public wrapper/configuration graph is caller-owned. A frozen dataclass
alone is insufficient: nested mutation, `object.__setattr__`, shallow/deep copies
and coherent refingerprinting must not change authority, other/future returns,
internal policies or legacy Enum definitions. Only safe exact immutable leaves
may be shared. This adds no action-bearing output field.

## Decision 5: Fixed Strategy policy

Freeze a distinct scalar `GovernedDailyTechnicalStrategyPolicyIdentity` with
exactly the seven serialized fields below:

| Field | Fixed value |
| --- | --- |
| `schema_version` | `technical_policy_identity/v1` |
| `policy_kind` | `daily_technical_strategy` |
| `policy_id` | `classic_daily_technical_strategy` |
| `behavioral_revision` | `1.0.0` |
| `configuration_schema` | `classic_daily_technical_strategy_configuration/v1` |
| `configuration` | `{}` |
| `fingerprint` | `sha256:acbdd8c9ac7ba7d336f5f5e74b7484b05d0fc15b3a6f24bc81288d1fc8ea817e` |

This complete projection and digest were verified by inspecting released code
and constructing `ClassicDailyTechnicalStrategyPolicy` in the project
environment with bytecode writes disabled. The underlying configuration is
`ClassicDailyTechnicalStrategyConfiguration`. Every field and the digest must
match; a matching digest alone is insufficient. Public configuration is a fresh
exact empty dictionary and serializes as `{}`, with no invented nested schema.
All other fields are exact built-in strings.

Use the existing canonical identity fingerprint payload excluding only its own
fingerprint. Do not widen the Interpretation-specific
`GovernedTechnicalPolicyIdentity` or the Assessment policy wrapper. Production
Strategy accepts no caller policy/configuration, registry or alternative policy.

## Decision 6: Governed content and independent validation

Freeze `GOVERNED_DAILY_TECHNICAL_STRATEGY_SCHEMA` as
`governed_daily_technical_strategy/v1` and a distinct frozen, slotted
`GovernedDailyTechnicalStrategy` with exactly these mandatory fields:

| Field | Binding |
| --- | --- |
| `source_assessment_occurrence` | Complete detached `PolygonCompletedDailyStrategyRequest` five-selector value |
| `source_assessment_content_fingerprint` | Exact authenticated `result.assessment.fingerprint` |
| `source_interpretation_content_fingerprint` | Exact bound authenticated `result.interpretation.fingerprint`, also equal to Assessment's retained content fingerprint for Interpretation |
| `canonical_instrument_id` | Complete canonical instrument projection shared by the authenticated pair |
| `analysis_as_of` | Exact canonical UTC historical analysis time shared by the pair |
| `strategy_policy_identity` | Complete fixed scalar Strategy identity from Decision 5 |
| `mode` | Exact closed string from Decision 4 |
| `rule_code` | Exact closed string from Decision 4, paired with its mode |
| `schema_version` | `governed_daily_technical_strategy/v1` |
| `fingerprint` | Canonical content fingerprint over every other field |

Retain the bound Interpretation content fingerprint explicitly because its
directional semantics are direct Strategy inputs. Do not duplicate the
Interpretation occurrence selector in Strategy content: the exact Assessment
envelope commits its complete Assessment content, which commits all five
Interpretation selectors, including the Interpretation envelope fingerprint.
Authentication must traverse that binding on every execution/read. This is an
auditable transitive commitment, not permission to choose any Interpretation
with equal content.

Source trading identity, quality/warnings, Assessment outcome/findings,
Interpretation directions/comparisons and original technical/dataset provenance
remain transitively committed through those exact sources. They are checked as
required but not added as redundant Strategy fields. Do not add raw indicators,
scores, confidence, thesis approval, price/action parameters or legacy integrity
provenance.

Freeze research boundaries `derive_governed_daily_technical_strategy` and
`validate_governed_daily_technical_strategy`. They consume detached exact
governed Assessment and Interpretation contents and the Assessment occurrence
value; the validator additionally consumes candidate Strategy content. These
are deterministic value boundaries with no clock, I/O, history or authority.
They cannot authenticate an envelope by themselves. Production supplies both
contents only from Decision 3 and verifies envelope/selectors separately.

Independent validation must:

1. Validate exact source types, complete retained projections, fingerprints,
   fixed upstream identities and Assessment-to-Interpretation content/artifact,
   canonical instrument, trading identity, analysis time and quality/warnings
   correspondence. Reject replacement of one source with an unrelated value.
2. Independently validate Assessment semantics using the released
   `validate_governed_daily_technical_assessment` over the authenticated bound
   Interpretation and Assessment's own retained Interpretation selector. Its
   fresh expectations use the existing Assessment helper pair; do not duplicate
   findings/outcome rules or reuse candidate findings as expectations. This
   checks retained decision correspondence; it is not Assessment execution or
   publication, and is not part of the private lookup/seal.
   Failure to validate the committed Assessment's findings, outcome or other
   semantic correspondence against its exact bound Interpretation is invalid
   committed source authority: `HISTORY_INVALID`, never `SEMANTIC_FAILED`, even
   when encountered while preparing a new Strategy candidate.
3. Build fresh detached semantic views and obtain expected mode/rule directly
   from the single released Strategy helper. The validator must not call the
   governed Strategy derivation entry point or use candidate mode/rule as its
   expectation. Independent invocation does not mean independent rule code.
4. Compare complete expected Strategy projection, all source/content bindings,
   policy, schema and fingerprint. Recheck input, adapter, policy and output
   drift after fallible work. Coherent refingerprinting is insufficient.

Keep source Assessment validation and Strategy validation failures distinguishable
through structured categories or known validation stages, never exception-message
parsing. With authentic, valid committed sources, new Strategy derivation/helper
failure or candidate Strategy semantic correspondence failure is `SEMANTIC_FAILED`.
A committed Strategy failing that validation during history authentication is
`HISTORY_INVALID`. Authenticated source lineage/selectors/correspondence differing
from the retained relationship remains `SOURCE_MISMATCH`, as specified in
Decision 13.

The application invokes Strategy derivation once per execution and independently
validates its result, including after publication preparation. Validators may
invoke existing helpers again to form fresh expectations; they must not rerun
technical analysis, governed Interpretation execution or governed Assessment
execution. In particular, no Interpretation semantic validator may derive
expected states/comparisons from upstream technical inputs in this path.

## Decision 7: Content and occurrence identities

Use existing canonical SHA-256 conventions: compact UTF-8 JSON, sorted keys,
`ensure_ascii=False`, `allow_nan=False`, complete nested projections, exact
scalar types and ordered arrays. Serialize canonical UTC datetimes with the
released `datetime.isoformat()` convention (`+00:00`); normalize acceptable
timezone-aware boundary inputs before retention. No alternate timestamp spelling
may round-trip as the same authoritative bytes. Strategy has no float field or
alternate legacy fingerprint payload.

| Identity | Meaning |
| --- | --- |
| Assessment result envelope fingerprint | `source_assessment_occurrence.assessment_fingerprint`; complete published Assessment content plus its execution/history facts |
| Assessment content fingerprint | `source_assessment_content_fingerprint`; deterministic Assessment content including its Interpretation occurrence binding |
| Interpretation result envelope fingerprint | Assessment's retained `source_interpretation_occurrence.interpretation_fingerprint`; exact upstream publication |
| Interpretation content fingerprint | `source_interpretation_content_fingerprint`; exact bound Interpretation's deterministic semantics/provenance |
| Strategy content fingerprint | All Decision 6 fields except its own fingerprint, including the entire selected Assessment occurrence |
| Strategy result envelope fingerprint | All final Decision 8 serialized fields except its own fingerprint, including Strategy content and its fingerprint |

Repeated Strategy derivation from the same exact Assessment with fixed semantics
has the same content fingerprint. Equal semantics from distinct Assessment
publications remain distinct Strategy content because the source occurrence is
included. Repeated Strategy publication of identical content creates distinct
execution occurrences/envelope fingerprints; no deduplication by content occurs.
These digests establish deterministic integrity, not signatures or authorship.

## Decision 8: Strategy result and bounded public workflow

Freeze these new identities, following the released Assessment naming pattern:

| Serialized constant / identity | Proposed value |
| --- | --- |
| `schema_version` | `polygon_completed_daily_strategy_result/v1` |
| `operation` | `production.polygon_completed_daily.daily_technical_strategy.application` |
| `operation_version` | `1.0.0` |
| `executor` | `market_platform.application/polygon_completed_daily_production_strategy/v1` |
| Execution ID prefix | `polygon_completed_daily_strategy` |
| History namespace prefix | `polygon_completed_daily_strategy_history` |

`PolygonCompletedDailyStrategyResult` is a factory-created frozen, slotted value
with exactly these nine retained fields. The four serialized constants above
are additional mandatory keys in its complete `to_dict()` projection:

| Field | Contract |
| --- | --- |
| `strategy` | Complete governed Strategy content including its fingerprint |
| `assessment_available_at` | Exact authenticated source Assessment envelope `available_at` |
| `execution_id` | Unique `polygon_completed_daily_strategy:<32 lowercase hex>` string |
| `history_namespace_id` | Original pinned `polygon_completed_daily_strategy_history:<32 lowercase hex>` string |
| `history_sequence` | Positive exact built-in integer, contiguous from 1; no `bool`/subclass |
| `execution_started_at` | Strategy start S |
| `execution_completed_at` | Strategy completion C |
| `available_at` | Final Strategy publication availability R |
| `fingerprint` | Complete final envelope fingerprint excluding only itself |

No duplicate Interpretation availability or public source bundle is added to
the envelope; Assessment commits its original Interpretation availability and
chronology. Final R, not provisional staging availability, is fingerprinted.

Freeze `PolygonCompletedDailyProductionStrategyApplicationService` with an exact
trusted `PolygonCompletedDailyProductionAssessmentApplicationService` constructor
dependency and optional injected `execution_clock`. Pin that Assessment publisher
at construction. No separate Interpretation publisher dependency, upstream
publisher override, arbitrary Strategy policy or provider client is accepted.
Clock construction is lazy: validate callability without sampling it.

Only these public service workflows exist:

- `execute(request) -> PolygonCompletedDailyStrategyResult`, synchronous and
  accepting only the exact Strategy request;
- `get_result_history_as_of(artifact_reference, *, knowledge_as_of) -> tuple`
  of fresh `PolygonCompletedDailyStrategyResult` values in sequence order.

Freeze application module exports to the new service, result,
`PolygonCompletedDailyStrategyRefusalReason` and
`PolygonCompletedDailyStrategyRefused`. Research module exports are the Strategy
schema constant, request, content, Strategy policy identity, derivation and
validator named above. Add no package-root exports. No CLI, HTTP, Agent or other
transport integration is part of v0.82.

## Decision 9: Chronology

Freeze the inclusive order `A <= S <= C <= R`:

| Symbol | Meaning |
| --- | --- |
| A | Authenticated Assessment publication `available_at` |
| S | Strategy execution start, sampled after request detachment and before source consumption |
| C | Strategy completion, sampled after successful derivation and independent validation |
| R | Strategy publication availability sampled during publication preparation, before the final seal |

Require exact source availability at S; A later than S is source unavailability,
not a substitute descriptive mode. Equal boundaries are valid. Allocate the
execution ID only after successful completion; validate uniqueness before commit.
R is nondecreasing across the complete Strategy inventory. Invalid clock values
or reversed Strategy execution/publication order are temporal refusals.
`analysis_as_of` remains historical market-analysis time and is never relabeled
as an availability, execution or knowledge time. Preserve original upstream
chronology and historical support; later governance does not rewrite a source.

History normalizes timezone-aware `knowledge_as_of` to canonical UTC through the
released timestamp convention; invalid input is a temporal refusal. History uses
no execution clock. Visibility is inclusive `available_at <= knowledge_as_of`.

## Decision 10: Pinned authority and exactly eleven locks

Freeze the lock chain:

```text
construction
→ validation
→ freshness
→ admission
→ validity
→ qualification
→ bridge
→ technical
→ governed Interpretation
→ governed Assessment
→ governed Strategy
```

The original pinned Strategy owner is eleventh/final. Acquire the existing ten
through the same constructor-pinned Assessment publisher exactly once, then
acquire the Strategy owner lock. The Assessment publisher selects its own pinned
Interpretation publisher and original owner. Pair resolution and final seals
must use that same Assessment root and the chain actually acquired, not a
replaceable accessor or a separately chosen Interpretation service. Root
replacement must fail closed, including replacement followed by swap-back around
lock selection. Never recursively acquire the chain or call public upstream
execute/history under non-reentrant locks.

For Strategy, require:

```text
authority owner == lock owner == staging owner == commit owner == cleanup owner
```

Independently pin the original owner, namespace and current committed state.
Owner state identity must match that commitment before and after fallible work.
Capture the current state under locks so an earlier concurrent successful append
is valid. Reject equal state replacement, rollback, namespace substitution and
inventory loss. Do not introduce a Strategy `_history` compatibility alias;
none is needed. Do not add one to Assessment.

Authoritative facts are an ordered immutable inventory of complete canonical
built-in `bytes` of FINAL Strategy result projections, including both fingerprints.
Next sequence equals committed count plus one. Typed results, decoded mutable
containers, digest-only lists, caller buffers and pending staging are not authority.
Require exact bytes and complete canonical decode/re-encode equality, rejecting
extra/missing keys and noncanonical scalar/container forms. Equal immutable bytes
denote the same fact; byte object identity is not content identity. Successful
publisher commit alone grants occurrence membership.

Trust remains in publisher code, independently pinned commitments and shared
locking. This specifies in-memory authority, not durable continuity, recovery,
cryptographic signing or protection against arbitrary simultaneous replacement
of all trusted code and trust roots. Missing support causes refusal, never
backfill, first-observation adoption, repair, import or silent reissue.

## Decision 11: Atomic publication and authenticated history

Execution performs one transaction under the complete chain:

1. Detach and validate the exact request; sample S. Under the pinned chain,
   authenticate the entire committed Strategy inventory and all its source pairs,
   including independent retained Strategy correspondence. Resolve the requested
   Assessment/Interpretation pair via Decision 3 and require A <= S.
2. Capture complete detached source facts and selectors. Derive governed
   Strategy once; independently validate complete domain/source correspondence.
   Sample/validate C and allocate a unique execution ID.
3. Stage on the original Strategy owner. Select the next sequence, sample and
   validate final R, and prepare the final envelope/fingerprint. Pending state
   grants no authority and is never visible to readers.
4. Encode the final fact; reconstruct the public return from those bytes and
   preallocate the entire next committed state. Validate full projection/byte
   correspondence, zero-Enum graphs, graph disjointness and semantic/source
   correspondence. Recheck prior inventory, chronology, roots and staging after
   fallible preparation. Prepare the full expected source-pair seal inventory,
   covering prior Strategy publications and the new candidate.
5. Complete the final publication seal in Decision 12. Clear pending on the
   original owner, then directly advance that owner's state and the independently
   pinned commitment to the same preallocated state. Return the prepared graph.

All failure paths append nothing, consume no sequence, preserve prior committed
state/facts and clear pending on the original owner through non-dispatching
cleanup. An allocated but unpublished execution ID confers no authority. No
retry, alternate source, fallback, partial result or rollback of external
callbacks is promised. Earlier successful publications survive later failure.
Shared locks make the two direct commitment assignments observationally atomic:
readers see the complete old or new state, never a partial append.

History requires exact `GovernedTechnicalArtifactReference`, defensively
detaches it, validates and captures its detached complete projection/fingerprint
under Decision 2, then validates the cutoff and acquires the same eleven locks once.
Before any visibility filtering, it authenticates the COMPLETE committed Strategy
inventory: bytes, owner/namespace/state, both fingerprints, sequence/ID inventory,
chronology, every retained Assessment, every Assessment's exact Interpretation
and original historical support. Independently validate every retained Strategy
against its authenticated pair using Decision 6, and its envelope against source
availability/selectors. Invisible or unrelated corrupt entries cannot be hidden.

Only afterward select complete artifact-projection equality AND
`available_at <= knowledge_as_of`. Return fresh caller-owned graphs in sequence
order with disjoint mutable/wrapper graphs across entries and reads. Finish all
reconstruction, copy, codec, graph, domain/history and source-correspondence work,
then perform Decision 12's final complete read seal, including invisible sources.
History never appends, stages, samples clocks, allocates execution IDs, repairs
or adopts facts. Failed reads mutate no authority.

## Decision 12: Final publication and read seals

The final seal is a complete source/support authentication operation through the
same pinned Assessment root, not a digest comparison or selected-source-only
shortcut. Use the preprepared pair expectations/complete facts from Decision 3
and Decision 11; authenticate the entire Assessment inventory, each required
bound Interpretation and original upstream support, and require correspondence
with the earlier authenticated facts. Never accept a new pair after drift.

For publication, ALL fallible local clock, allocation, projection, codec,
reconstruction, copy, graph, semantic validation, history validation and
provenance preparation must precede this final complete Assessment/Interpretation
source-support seal. The seal itself performs the final trusted authentication
and must finish its own fallible preparation before its final support checks.
For multiple pairs, later reconstruction/callback work must not invalidate an
earlier check unnoticed; seal the complete prepared inventory as one operation.
Do not interleave new downstream work between individual pair checks.

After a successful publication seal, only minimal direct identity/scalar checks
against captured roots/selectors, original-owner pending cleanup, direct advancement
to the preallocated state and return remain. No property dispatch, projection,
serialization, allocation, validator, callback, clock, copy, graph traversal or
additional history/domain work may follow. If a direct check detects drift,
refuse before state advancement and clear original-owner pending state.

For reads, ALL public-copy, projection, codec, graph, domain/history validation
and result-tuple preparation precede the final complete source/support seal.
It covers every retained source, even if no results are visible. After successful
read sealing only direct identity checks against captured roots and return remain.
No authority mutation or fresh projection is permitted. Loss of committed support
at either seal is a history-invalid refusal, never a new-source miss.

## Decision 13: Bounded zero-Enum refusals

`PolygonCompletedDailyStrategyRefusalReason` is a plain constant holder, not an
Enum. `PolygonCompletedDailyStrategyRefused` is a `RuntimeError` exposing an
exact built-in `reason` string; diagnostic messages are exact strings and have
no classification semantics. Freeze:

| Constant | Exact reason string | Classification |
| --- | --- | --- |
| `ASSESSMENT_UNAVAILABLE` | `assessment_occurrence_unavailable` | Valid authenticated history has no exact requested Assessment, or its availability is later than new execution start |
| `HISTORY_INVALID` | `history_incomplete_or_corrupt` | Invalid owner/root/commitment, committed inventory or retained envelope structure/chronology; failed committed Assessment/Strategy semantic validation; or missing required Assessment/Interpretation/upstream support |
| `SOURCE_MISMATCH` | `source_lineage_mismatch` | Authenticated pair, selector, retained availability or source lineage correspondence differs |
| `SEMANTIC_FAILED` | `semantic_execution_or_correspondence_failed` | New Strategy derivation/helper failure or candidate Strategy independent semantic correspondence failure while committed sources remain authentic and valid |
| `TEMPORAL_FAILURE` | `temporal_failure` | Invalid new execution/publication clock, ordering or history cutoff |
| `PUBLICATION_FAILED` | `strategy_publication_or_copy_failed` | New staging/publication preparation, codec, reconstruction, allocation or defensive public-copy failure |

Complete committed-history invalidity takes precedence over a new selector miss.
Freeze the following distinctions for execute and history authentication:

| Failure | Classification |
| --- | --- |
| An authenticated committed Assessment fails the released independent Assessment validator against its exact bound Interpretation, including retained findings/outcome or other semantic correspondence | `HISTORY_INVALID` = `history_incomplete_or_corrupt` |
| Required committed Assessment, bound Interpretation or historical support is lost | `HISTORY_INVALID` = `history_incomplete_or_corrupt` |
| Authenticated source lineage, selectors or correspondence differ from the retained source relationship | `SOURCE_MISMATCH` = `source_lineage_mismatch` |
| New governed Strategy derivation/helper fails, or candidate Strategy fails independent Strategy semantic correspondence, while committed sources remain authentic and valid | `SEMANTIC_FAILED` = `semantic_execution_or_correspondence_failed` |
| A committed Strategy fails independent Strategy semantic validation during Strategy history authentication | `HISTORY_INVALID` = `history_incomplete_or_corrupt` |

Committed-source semantic corruption is never a new Strategy semantic execution
failure. Preserve these distinctions through structured categories or validation
stage knowledge; never parse exception messages or collapse a source Assessment
validator failure into the candidate Strategy category. Explicit authenticated
lineage mismatch must never become source unavailability. Public-copy failure on
a history read is `PUBLICATION_FAILED` and changes no authority.

Wrong exact outer request/reference types are rejected before detachment;
malformed selector values are rejected only after defensive detachment under
Decision 2. These value/boundary failures use `TypeError`/`ValueError` before
clocks or locks and are not successful workflow responses.
Within the workflow, translate structured private categories and known operation
failures into the bounded refusals. Never parse exception messages. Do not turn
authentication failures into `insufficient_data`, `no_active_strategy`, partial
content or fallback execution.

## Decision 14: Preservation and explicit downstream stop

Strategy remains descriptive research authority only:

- `no_active_strategy` does not mean hold, flat, exit, avoid or do nothing.
- `positive_directional_continuation` does not mean buy, long, add or enter.
- `negative_directional_continuation` does not mean sell, short, reduce or exit.

v0.82 stops before thesis approval, recommendation, candidate buy point, entry
action, target price, stop price, position sizing, portfolio allocation, trading
signal, order intent, risk approval, execution planning, execution authorization,
Agent authority and trading automation. Add no action-bearing fields or methods.

Do not connect this output to `StrategyCandidate`, `PositionAction`,
`PriceTarget`, `ProbabilityEstimate`, `TradingSignal`, `OrderIntent`,
`RiskDecision`, execution planning or execution authorization. Existing
downstream foundations and the parallel `research-workflow-v1` ontology remain
separate and frozen; their existence grants no integration permission.

Preserve all v0.81 and earlier public contracts, especially:

- legacy Strategy types, five-row semantics, policy identity and mapping-neutral
  runner; v0.75 application and v0.76 Agent exposure;
- Assessment/Interpretation schemas, operations, executors, fingerprints,
  exports, execute/history behavior and public semantic validators;
- zero-Enum governed isolation, original technical issuance authority, retained
  historical support, pinned owner locking and pending cleanup;
- the existing ten-lock chain, extended only with the final Strategy owner;
- package `0.1.0`, 69 ordered unique Evidence exports, frozen ADRs and handoffs.

For separately authorized implementation, keep new domain work in
`src/market_platform/research/governed_daily_technical_strategy.py` and new
application authority in
`src/market_platform/application/polygon_completed_daily_production_strategy.py`.
The sole required existing-production extension is the private additive
Assessment consumption contract. Reuse existing semantics without changing the
legacy implementation. Do not pre-split a generic history/policy framework.
Persistence, migration, policy registration and multi-provider generalization
are outside this milestone.

## Future implementation verification requirements

These are review requirements for later authorized implementation, not tests
created or executed in this drafting session:

1. Verify all five selector components, complete artifact equality, envelope vs
   content fingerprint substitution, preexisting authentic publications, no
   latest lookup and no independently selected Interpretation.
2. Verify complete Assessment inventory/support validation precedes selection,
   including unrelated corruption, lost bound Interpretation support, pending
   facts, rollback and equal-state/root substitutions. Exercise structured
   private failures with identical messages and unchanged v0.81 public behavior.
3. Prove provider/technical/Interpretation/Assessment execution is never called.
   Private lookup/seals invoke no semantic reruns; independent domain validation
   reuses released Assessment/Strategy helpers without duplicated mappings.
4. Cover all five Strategy rows, unsupported aligned/future values, exact policy
   projection/digest, independent rejection of coherent altered content and
   Assessment/Interpretation substitution, and source/policy drift.
5. Verify content/envelope canonical fixtures, occurrence distinction, exact
   scalar/zero-Enum graphs and mutation isolation across public copies/history
   and legacy definitions.
6. Exercise A <= S <= C <= R, every equality boundary, nondecreasing publication
   availability, inclusive history cutoff and exact original source availability.
7. Verify eleven locks in order exactly once, one pinned Assessment root for
   selection/authentication, owner/publisher swap-back cases and concurrent
   old-or-new atomic visibility without recursive acquisition.
8. Inject failure into each publication/read seam and after late graph, codec,
   domain/history validation or copy work. Require complete final pair/support
   seals, invisible-source coverage, no post-seal fallible local work, no append
   or sequence consumption on failure and original-owner cleanup.
9. Verify the public execute/history-only surface, unchanged released contracts
   and exports, and absence of action fields, Agent exposure and downstream
   trading connections.

## Rationale and unresolved ADR questions

The design closes governed Assessment consumption and Strategy publication while
preserving one released Strategy semantic implementation. Reusing the legacy
runner would require incorrect source/provenance adaptation. Independent
Interpretation selection would break the Assessment binding. Content-only
selection would erase occurrences. Public bearer bundles or replaceable history
views would separate trusted membership from its pinned authority. Filtering
before authentication or copying after the final seal would leave committed
support unchecked. Each alternative is rejected.

Complete inventory validation and fresh reconstruction cost grows with retained
histories, while holding the existing shared lock chain. v0.82 accepts
that bounded in-memory authority design; it does not promise retention limits,
durable recovery or a new optimized index contract.

Unresolved ADR questions: **None.** New schemas/names above are proposed decisions
based on released patterns, not unverified released identifiers. Private helper
names/layout and test slice organization remain implementation choices, not
deferred authority or semantic decisions. Acceptance and implementation require
separate review and authorization.
