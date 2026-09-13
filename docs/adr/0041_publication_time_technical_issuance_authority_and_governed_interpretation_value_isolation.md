# ADR 0041: Publication-Time Technical Issuance Authority and Governed Interpretation Value Isolation

## Status

Accepted. The corrective, additive architecture contract is frozen for the v0.80
corrective work. Acceptance does not itself authorize production-code or test
implementation; implementation requires separate authorization.
[ADR0040](0040_governed_daily_technical_interpretation.md) remains Accepted except
for the narrow supersession explicitly defined by this ADR.
The v0.80 release remains **BLOCKED** by B1 and B2 until separately authorized
implementations and their required tests pass review.

## Context and inspected baseline

Verified authoring baseline:

- Branch: `feature/v0.80.0-governed-daily-technical-interpretation`.
- HEAD: `7aac390592b696d3041ebbb03a11aa4676808631`.
- Initial working tree: clean.
- Released `v0.79.0` peeled commit:
  `2a3c90707f44433e15367367a8d73d7e68d34cdc`; annotated tag object:
  `2dfe41bf401f6ab7af4da0cc616591ecb8f786a1`.
- ADR0040: Accepted; its file remains unchanged by this correction.

Two independently reproduced defects motivate this contract. B1 is the absence
of independent publication-time original-issuance truth in released Slice 8.
A coherently substituted technical result can pass structural and provenance
checks when first observed by Interpretation. B2 is the exposure of Python Enum
singletons in governed public graphs. `deepcopy` preserves those singletons;
`object.__setattr__` through a public value can therefore change objects reachable
from retained authority and canonical legacy definitions. These reproductions
are the supplied defect baseline, not tests rerun during this documentation task.

Inspected source anchors, relative to the repository root:

- `src/market_platform/application/polygon_completed_daily_production_technical.py`:
  `_TechnicalHistory`, complete result projection, `_publish`, `_resolve`,
  `_source_lineage`, `_lock_inputs`, and public history copies.
- `src/market_platform/application/polygon_completed_daily_production_interpretation.py`:
  downstream observations, retained typed graphs, envelope and copy checks.
- `src/market_platform/research/governed_daily_technical_interpretation.py`:
  exact five-field request, public content, projections and correspondence.
- `src/market_platform/evidence/references.py` and `classification.py`:
  artifact reference v2 and its two Enum classifications.
- `src/market_platform/research/technical_policy.py`, `classic_daily_technical.py`,
  `daily_technical_interpretation.py`, `technical_analysis.py`, and
  `interpretation.py`: policy, classic helpers, comparisons and categorical values.
- `src/market_platform/instruments/identity.py`,
  `src/market_platform/trading/instrument.py`, and
  `src/market_platform/_fingerprint.py`: reusable scalar identities and canonical
  serialized/fingerprint conventions.

## Scope and narrow ADR0040 supersession

This correction is **INTERNAL ADDITIVE AUTHORITY HARDENING** for Slice 8 plus
governed-specific Python value isolation. It supplements ADR0040 and narrowly
supersedes only these assumptions:

1. Released Slice 8 internals must remain completely unchanged, even where
   private issuance authority is required. This qualifies ADR0040's Status,
   Frozen v0.79 boundary, and Compatibility statements only to permit the
   publication root and private authentication defined here.
2. Governed public values must reuse legacy Enum-bearing exact types. This
   qualifies ADR0040's Architecture decision, Exact source authority and
   reference contract, Governed content contract, Fixed classic policy binding,
   and Trusted history/alias-isolation representation requirements. Scalar
   wrappers replace Enum-bearing values, and immutable bytes replace typed
   public graphs as Interpretation retention authority. Any exception Enum
   layout choice is also subject to the zero-Enum public-value requirement.

These are representation and authority corrections, not permission to revise
classic semantics. All other ADR0040 semantic, temporal, provenance, locking,
fingerprint, refusal and downstream-stop contracts remain in force. In
particular, there is no fabricated legacy integrity carrier or fingerprint,
caller-selected policy, hash-only provenance replay, or new execution authority
from value construction. ADR0039 and legacy research behavior remain in force.

## Decision 1: Slice 8 publication-time issuance authority

### Publisher-owned committed root

Freeze the direction of authority:

`successful Slice 8 publication -> independently committed issuance fact -> downstream authentication of original issuance`

The trusted technical application service owns a private authoritative committed
root independent from replaceable history/store and issuance compatibility views.
It is established by trusted publisher construction, before any publication or
downstream observation, and advances only through successful technical
publication. The logical root binds:

- Original trusted technical history owner identity, including the original
  store identity if represented separately.
- Original technical history namespace, including when the history is empty.
- Next history sequence: initially 1, thereafter committed occurrence count + 1.
- Ordered retained technical occurrence inventory.
- Ordered immutable issuance facts, exactly one per successful occurrence.

The occurrence inventory pins the identity of each original retained occurrence
as well as its position. Replacing one with an equal-content object is therefore
refused. Strong private identity bindings or equivalent non-reusable identity
tokens must not depend on equality alone or a bare object ID whose lifetime can
expire. Identity bindings are distinct from the immutable issuance facts; a
retained result graph is never the issuance fact.

The narrowest repository-consistent private representation is permitted. The
root's current commitment, original owner/namespace bindings, inventory and
append-only progression must remain independently checkable. A tuple stored
only in the current `_history._state` is not issuance authority. Neither a newly
supplied structurally valid store nor a separately replaceable issuance mirror
can become the root. Simultaneously substituting both compatibility views must
still fail against the publisher-owned commitment. A rollback to an earlier
compatible state must fail against the current committed root.

An empty root authorizes no occurrence. First observation, a downstream cache,
a staging record, and a coherent fingerprint establish no issuance authority.

### Exact issuance fact and canonical serialization

For each successfully published occurrence, freeze the issuance fact as the
**exact complete canonical serialization bytes of the FINAL validated
`PolygonCompletedDailyTechnicalResult.to_dict()` projection, including its
existing envelope fingerprint**. Its exact Python type is built-in `bytes`.
Do not retain a mutable dictionary/list, dataclass/result graph, Enum member,
bytearray, or caller-owned buffer as this fact. Do not introduce a new public
fingerprint family or separately duplicate fields already bound by the complete
projection.

That projection binds history namespace and sequence, execution ID and
timestamps, `available_at`, complete `TechnicalAnalysisSnapshot`, source
Evidence/research projection, bridge reference and lineage, artifact reference,
construction and qualification identities, governed dataset and proof
identities, production profile, transformation, analyzer, operation/version/
executor, and technical envelope fingerprint. Namespace is additionally pinned
at the root to detect substitution even before the first occurrence exists.

Use deterministic internal canonical scalar serialization consistent with the
repository's compact JSON conventions: UTF-8, sorted object keys, no insignificant
whitespace, `ensure_ascii=False`, and rejection of nonfinite numbers. Preserve
array order, complete key presence, nulls, exact scalar types/values, canonical
timestamp strings, and the existing finite-number representation. The encoder
accepts only validated built-in scalar projections and containers; it must not
silently stringify objects, accept Enum/string subclasses, or omit a field.

Equal complete projections must produce identical bytes regardless of dictionary
insertion order. Any difference in a bound projected fact, scalar type, ordered
array, or fingerprint must change the canonical bytes or cause refusal.
Decoding must recover the complete same typed scalar projection, and canonical
re-encoding must reproduce the identical bytes. This is an internal encoding of
the existing final `to_dict()` projection, not a new externally visible schema.
Do not substitute a fingerprint payload that excludes the envelope fingerprint,
or alter existing snapshot/policy float-to-string fingerprint projections.

### Atomic publication

Publication is one authority transaction under the existing lock chain, at its
technical position. Conceptually:

1. Validate the current publisher-owned committed root and its integrity.
2. Validate compatibility history/store and issuance views against that root.
3. Perform the existing source/provenance/semantic work.
4. Construct and validate the final technical result, including final publication
   availability and envelope fingerprint.
5. Construct and validate the defensive public result.
6. Produce canonical immutable issuance bytes from the complete final projection.
7. Prepare the complete next root and corresponding retained-history view.
8. Perform all final source/provenance, complete projection/copy correspondence,
   identity, unchanged-root, sequence and chronology checks. Require canonical
   encodings of final retained and public projections to equal the prepared
   issuance bytes.
9. Atomically advance the publisher-owned root and compatible retained-history
   view, including the occurrence, its fact, and next sequence.
10. Clear pending state and return the already prepared public result.

All fallible preparation, allocation, serialization, copying, clock sampling,
validation and provenance work occurs before authoritative advancement. The
commit and pending cleanup contain no fallible callback or later validation that
can turn an advanced publication into a reported failure. Atomicity is
observational under the common locks: readers see either the complete old
commitment or complete new occurrence-plus-fact transaction, never half of it.

A failed publication creates no issuance fact, consumes no sequence, changes no
committed inventory, preserves all prior commitments, and clears pending state.
A staged/prepared fact is not authority; only membership in a successfully
committed publisher root is authority. Validation of a corrupt view must refuse,
not repair it by adopting that view.

### Private authentication and downstream rule

Freeze a narrow PRIVATE Slice 8 capability for trusted downstream application
composition under the already acquired lock chain. Its exact private method
name is an implementation choice. It validates the whole committed inventory
before exact occurrence selection, including:

- Original history/store owner and original namespace, committed-root integrity,
  and compatibility retained-history/issuance-view correspondence.
- Exact one-to-one occurrence-to-fact inventory, equal counts and fixed order;
  contiguous positive exact integer sequences and next-sequence correspondence.
- Unique execution IDs, monotone availability, complete existing result
  validation, and each occurrence's exact canonical bytes equal to its fact.
- No missing, duplicate, reordered, truncated, rolled-back or replaced
  occurrence; no missing, duplicate, reordered or replaced issuance fact.
  Equal-content occurrence replacement also fails its pinned identity check.

An equal immutable byte value denotes the same fact; byte object identity is not
a new serialized identity. Replacing a fact inventory or compatibility store
cannot replace the independently bound committed inventory, even if proposed
values are structurally valid.

Then select exactly one occurrence by conjunction of all five v0.80 selectors:
`artifact_reference`, `technical_history_namespace_id`,
`technical_history_sequence`, `technical_execution_id`, and
`technical_fingerprint`. The complete artifact-reference scalar projection must
correspond, not just its artifact ID or a snapshot digest. Preserve source
availability checks and all original bridge/provenance resolution: use the
technical occurrence's ORIGINAL `execution_started_at`, retained bridge
reference, original qualification context, and reconstructed complete lineage.
No current-time requalification may substitute for that context.

This capability creates no occurrence or issuance authority and exposes no
append/import/register/mint operation. It performs no provider acquisition,
governance issuance, qualification execution, bridge conversion, or technical
analyzer execution. Provenance resolution is read-only historical validation.
It must not return a root, mutable authority handle, or authority-creation token
to public callers.

Governed Interpretation MUST authenticate through this publisher capability,
including the first time it sees an occurrence. Interpretation-local
observations/projections may add corruption/loss checks, but cannot confer
authority, initialize missing issuance facts, or substitute for authentication.
Constructing Interpretation before the first technical append must neither
disable later authentic consumption nor authorize later substituted content.

## Decision 2: Released Slice 8 compatibility

For authentic executions preserve exactly: `PolygonCompletedDailyTechnicalResult`
public schema and public methods; technical request schema; result fingerprint
and snapshot semantics; analyzer formulas; source selection; operation/version/
executor identities; execution/history ID grammars; chronology and availability;
lock order; repeated execution behavior; package version; and Evidence exports.
The technical result schema remains `polygon_completed_daily_technical_result/v1`.
No version/schema bump is required solely for this private authority root.

Previously accepted corrupt/substituted histories may now refuse. This is
intended hardening, not a semantic change to valid released research results.
The existing v0.79.0 tag remains unchanged. This correction does not remove Enums
from legacy Slice 8 public schemas or authorize general legacy Enum cleanup.
Missing pre-hardening issuance authority requires refusal as specified below.

## Decisions 3 and 4: Governed Enum-free public scalar values

Every publicly reachable value graph introduced by governed v0.80 Interpretation
MUST contain ZERO Python Enum instances, including `StrEnum` and `IntEnum`.
This covers `interpret_governed_daily_technical_snapshot(...)` content,
`PolygonCompletedDailyInterpretationResult`, execute returns, every history-read
result, nested request/selectors/references, policy/configuration, quality,
warnings, states, comparison evidence/operators/operands/sources, and public
value properties. Public refusal reason values must also be exact strings with
the existing closed machine-readable categories, not exposed Enum singletons.

Categorical fields are validated **exact built-in `str`** values with closed
allowed-value sets, never Python Enum subclasses or custom string subclasses.
Reject unsupported inputs instead of applying arbitrary `str(...)` conversion.
Normalize validated legacy values only at explicit trusted boundaries. All
governed wrappers are immutable by ordinary API contract and defensively
reconstructed; `frozen=True` alone is not an adversarial isolation guarantee.
Tuples retain warning/comparison order. No wrapper, hidden backing field, cache,
or public property may retain/expose a legacy Enum-bearing object.

Freeze these Python value names and complete field sets. These names change
Python representation only; they do not rename existing serialized schemas.

| Governed Python type | Complete fields |
| --- | --- |
| `GovernedTechnicalArtifactReference` | `schema_version`, `artifact_id`, `artifact_version`, `artifact_fingerprint`, `information_class`, `authority`, `fingerprint` |
| `GovernedTechnicalPolicyIdentity` | `schema_version`, `policy_kind`, `policy_id`, `behavioral_revision`, `configuration_schema`, `configuration`, `fingerprint` |
| `GovernedTechnicalComparisonOperand` | `source`, `field`, `value` |
| `GovernedTechnicalComparisonEvidence` | `evidence_id`, `left_operand`, `operator`, `right_operand`, `satisfied` |

The artifact fields are exact strings. Policy fields are exact strings except
`configuration`, which is an independently reconstructed exact
`ClassicDailyTechnicalInterpretationConfiguration`. Inspection confirms this
configuration retains only six floats, with no Enum or shared mutable default
instance. Its exact fields are frozen in Decision 6. Comparison operands use
exact strings plus canonical finite exact float `value`, rejecting negative
zero as the released contract does. Comparison evidence uses an exact string
ID/operator, two separately reconstructed exact governed operands, and exact
built-in `bool` `satisfied`.

Retain the names `PolygonCompletedDailyInterpretationRequest`,
`GovernedDailyTechnicalInterpretation`, and
`PolygonCompletedDailyInterpretationResult` with their existing complete
serialized field sets. The request still has exactly five selectors; only its
artifact-reference Python field type changes. Content uses the governed policy
and comparison types above, exact strings for all categorical states/quality,
and a tuple of exact strings for warnings.

Inspection also permits fresh exact `CanonicalInstrumentId` (only
`instrument_id`) and `TradingInstrumentIdentity` (`symbol`, `venue`,
`schema_version`, `instrument_fingerprint`): their retained fields are scalar
strings without Enum state. Validate exact built-in leaves, reconstruct each
instance independently, and preserve existing projections. Do not retain the
Enum-bearing `CanonicalInstrument` descriptor in public content. Canonical UTC
timestamps may remain exact immutable built-in `datetime` values. None of these
permissions allows a shared mutable instance between caller, authority,
computation, returned result or separate history reads.

Freeze the categorical vocabulary by serialized value, independent of legacy
Enum membership objects:

| Former Enum class / governed path | Closed string values |
| --- | --- |
| `EvidenceInformationClass` / artifact `information_class` | `source_observation`, `source_measurement`, `source_assertion` |
| `EvidenceAuthority` / artifact `authority` | `platform_origin`, `external_origin` |
| `TechnicalPolicyKind` / policy `policy_kind` | `daily_technical_interpretation` only |
| `TechnicalAnalysisQuality` / `source_quality` | `complete`, `degraded` |
| `TechnicalAnalysisWarning` / `source_warnings` | `insufficient_profile_history`, `stale_evidence`, preserving this order when present |
| `DailyTechnicalDirectionalState` / trend and momentum | `positive`, `negative`, `mixed`, `unavailable` |
| `VolatilityState` / `volatility_state` | `low`, `normal`, `high`, `unavailable` |
| `DailyTechnicalExtensionState` / `extension_state` | `above_reference_band`, `within_reference_band`, `below_reference_band`, `unavailable` |
| `TechnicalComparisonOperator` / comparison `operator` | `greater_than`, `greater_than_or_equal`, `less_than`, `less_than_or_equal` |
| `TechnicalComparisonOperandSource` / operand `source` | `technical_analysis_snapshot`, `interpretation_policy_configuration`, `interpretation_policy_derived` |

These ten legacy Enum classes remain unchanged. The allowed artifact vocabulary
does not relax authentic source selection or grant authority to other artifacts.
Public reason strings retain the existing six values:
`technical_occurrence_unavailable`, `history_incomplete_or_corrupt`,
`source_lineage_mismatch`, `semantic_execution_or_correspondence_failed`,
`temporal_failure`, and `interpretation_publication_or_copy_failed`.
This projection preserves ADR0040's refusal distinctions and upstream context.

## Decision 5: Artifact reference normalization boundary

A caller/application may supply exact legacy `EvidenceArtifactReference` as
trusted construction input where existing composition requires it. Validate its
complete canonical projection, then immediately normalize it to a fresh exact
`GovernedTechnicalArtifactReference`. The governed request retains only that
Enum-free value, never the supplied legacy object or its Enum fields. Request
reconstruction may accept the exact governed reference, validate all fields,
and detach it again; arbitrary mappings/subclasses are not bearer inputs.

Preserve `schema_version = evidence_artifact_reference/v2`, all seven fields in
the table above, existing artifact ID/version/fingerprint validation, and the
reference fingerprint over the existing six-field payload excluding its own
`fingerprint`. `artifact_fingerprint` and reference `fingerprint` remain distinct.
The exact serialized information class and authority are retained as strings.

If a frozen upstream resolver requires an exact legacy reference, trusted
internal resolution may reconstruct one privately using only validated governed
scalar facts and closed mappings to existing legacy members. Validate complete
projection correspondence, including fingerprint, before use. This conversion
grants no authority and is not import, registration, or issuance. It must not be
retained in governed results, returned to callers, or hidden in a governed
wrapper. The caller's pre-existing legacy input is not made part of the governed
public graph by accepting it at this boundary.

## Decision 6: Fixed policy execution and scalar policy identity

Semantic execution continues to use the frozen released classic policy
internally. Freeze the complete public `GovernedTechnicalPolicyIdentity`:

| Field | Exact value |
| --- | --- |
| `schema_version` | `technical_policy_identity/v1` |
| `policy_kind` | `daily_technical_interpretation` as an exact string |
| `policy_id` | `classic_daily_technical` |
| `behavioral_revision` | `1.0.0` |
| `configuration_schema` | `classic_daily_technical_interpretation_configuration/v1` |
| `configuration.rsi_neutral` | `50.0` |
| `configuration.rsi_elevated` | `70.0` |
| `configuration.rsi_depressed` | `30.0` |
| `configuration.realized_volatility_low` | `0.15` |
| `configuration.realized_volatility_high` | `0.30` |
| `configuration.ema20_extension_band_percent` | `5.0` percent |
| `fingerprint` | `sha256:9d81e49a6d45d27071e804b46486ae247d71f650184e8032a792586807fc3d02` |

Configuration has exactly the six numeric fields above, without an additional
nested schema field. Preserve the policy's serialized projection and canonical
float fingerprint payload exactly. Validate complete fixed identity/configuration
correspondence, not only the digest. Public construction cannot select another
policy or configuration. Internal execution owns fresh policy/configuration
objects, separate from the public scalar identity; public mutation must not
change internal definitions or any future semantic execution. Do not expose
`TechnicalPolicyIdentity`, `TechnicalPolicyKind`, or a backing classic policy.

## Decision 7: Semantic state and comparison normalization

The released `classic_states(...)` and
`build_classic_comparison_evidence(...)` remain the ONLY semantic formula source.
Their legacy Enum-bearing outputs may exist inside trusted computation only.
Normalize them into the governed scalar contract before exposing content or
preparing retained authority. Do not create a second semantic model, rewrite
formulas, or invoke a legacy carrier-dependent Interpretation runner.

Preserve the same categorical strings, comparison IDs and exact order, omission
rules, complete operands and values, serialized operators, and exact satisfied
Boolean. Retain both true and false comparisons. Omit a comparison only when a
required snapshot operand is unavailable; preserve other comparisons even when
a related state is unavailable. Preserve exact quality and ordered warnings,
including degraded quality without promotion or governance reinterpretation.

The 18-ID order remains ADR0040's complete inventory, from
`trend_ema8_above_ema20` through `extension_below_negative_band`. The closed
operand field sets are:

- `technical_analysis_snapshot`: `ema_8`, `ema_20`, `ema_144`, `ema_169`,
  `latest_close`, `macd_line`, `macd_signal`, `rsi_14`, `realized_volatility`,
  `volatility_references.distance_from_ema20_percent`.
- `interpretation_policy_configuration`: the six configuration fields in
  Decision 6.
- `interpretation_policy_derived`: only
  `negative_ema20_extension_band_percent`, derived by the released helper as
  `0.0 - ema20_extension_band_percent`.

The governed domain correspondence validator compares the COMPLETE governed
scalar output with freshly derived released classic expectations from the
authenticated detached snapshot and fixed internal policy. It compares all
source facts, policy facts, quality/warnings, states and ordered comparisons,
including both operands, operator and Boolean. A coherent new fingerprint alone
does not satisfy correspondence. Keep ADR0040's checks before/after computation
and across all fallible publication/copy seams.

Serialized schemas remain `governed_daily_technical_interpretation/v1` and
`polygon_completed_daily_interpretation_result/v1`. No governed field is added,
removed or renamed. Public `to_dict()` continues emitting numeric policy and
operand values; governed content fingerprint payloads continue using the
existing canonical float strings where specified. The envelope continues to
bind the complete existing content projection, `technical_available_at`, and
all its existing execution fields. Do not conflate that payload with the content
fingerprint payload or the new private authority serialization.

## Decision 8: Authoritative Interpretation retention

Freeze governed Interpretation authoritative retention as an ordered immutable
inventory of **complete canonical built-in `bytes` serializations** sufficient
to reconstruct and validate the exact content and execution envelope. Each entry
encodes the final existing result `to_dict()` projection, including content and
envelope fingerprints, selector, policy/configuration, comparisons, provenance
identities, `technical_available_at`, and all execution/history metadata. Use
the deterministic encoding/correspondence rules of Decision 1 without a new
serialized schema or fingerprint family.

The Interpretation service's independent committed state continues to bind its
original history owner/namespace, current next sequence and complete inventory.
Neither a mutable decoded projection nor a public typed result graph is retained
as authority. No Enum, caller-owned alias, mutable dictionary/list or shared
mutable global/singleton can occur in retained authoritative facts. Temporary
decoded dictionaries/lists are permissible preparation values, never authority.
Replacing/truncating/rolling back compatibility views must not reset commitment.

Build a fresh validated governed graph from bytes for every public history read
and execute return. Prepare the execute return by reconstruction from the staged
final bytes before commit, validate its complete correspondence and detachment,
then atomically commit those same bytes. Reconstruction from staged bytes does
not itself confer authority. Repeated reads and the execute return must be
independent of each other, authority, source inputs and internal policy instances.
Only safe exact immutable scalar leaves may be shared.

On reads, retain complete history validation, private Slice 8 issuance
authentication and historical upstream provenance/semantic correspondence.
Bytes alone do not excuse missing upstream support. Public coherent
refingerprinting cannot rewrite retained bytes or publish a new occurrence.
All Interpretation fallible reconstruction and correspondence checks precede
authoritative advancement, preserving ADR0040's failure and pending cleanup
contract. Python wrapper changes do not change serialized schema identity.

## Decision 9: Mutation threat model and trust boundary

The supported adversary can use `object.__setattr__`, mutate nested public
objects, coherently refingerprint them, shallow/deep copy public graphs, attempt
Enum singleton mutation through public values, replace history/store views or
occurrences, and truncate/roll back retained compatibility state. Defend even
before any downstream observation. Copying a frozen dataclass is not proof of
isolation; fingerprints prove correspondence only when compared with independent
authority.

Governed public mutation must not alter authoritative retained facts, committed
issuance facts, subsequent public reads, classic policy definitions, legacy Enum
names/values/behavior, or future semantics. Prevent the shared-state route:
public categorical leaves are immutable exact strings, wrappers/configuration
are independently reconstructed, no backing Enum objects are exposed, and
retained authority is immutable bytes. A caller may corrupt its own writable
wrapper; that cannot mutate another graph or authoritative facts. Later detection
alone is insufficient for these prevention/isolation requirements. Direct
corruption of a compatibility history is instead detected and refused against
the independent commitment; it must never be adopted as new issuance truth.

Public value reachability includes nested fields, containers, properties and
hidden backing values. It is not a claim that Python blocks arbitrary inspection
or rewriting of executable modules via reflection. The trust model does not
claim defense against arbitrary replacement of all trusted executable code and
every publisher-owned trust root simultaneously. Trusted publisher code,
private committed roots and lock discipline remain trust anchors. Direct global
monkeypatching of imported legacy Enum classes is outside the guarantee against
mutation *through governed public values*. Legacy input graphs and unchanged
legacy APIs remain their existing boundary; they must not leak into new governed
outputs. No signing or durable tamper-proof storage is implied.

## Decision 10: Temporal, lock and downstream contracts

Preserve ADR0040 `T <= S <= C <= R`: technical availability T, Interpretation
start S, completion C, and publication availability R. Require source visibility
at S, exact inclusive history visibility `R <= knowledge_as_of`, canonical UTC,
nondecreasing publication availability, and distinct historical analysis time.
Preserve original qualification, bridge and technical contexts and all upstream
chronology. Later governance records do not rewrite a prior occurrence.

Preserve the exact lock order:

`construction -> validation -> freshness -> admission -> validity -> qualification -> bridge -> technical -> governed interpretation`

The new Slice 8 transaction occupies the existing technical position. Compose
the upstream chain once, then acquire governed Interpretation; authentication
must not introduce inversion or recursive public history calls that reacquire
non-reentrant locks. Concurrent reads/publications use this same coherent chain.

v0.80 still terminates at governed Interpretation, before Assessment. No
Assessment, Strategy, recommendation, signal, order intent, Agent authority or
trading automation is introduced. Descriptive quality, states and comparisons
grant no trading or Evidence lifecycle permission.

## Decision 11: Migration and continuity

An old in-memory Slice 8 occurrence without a publication-time issuance fact is
NOT retrospectively authenticatable from `_history._state`, even when its
retained result is complete, coherent and valid under old checks. Missing
issuance authority means refusal. Do not backfill, import, silently mint,
silently reissue, or derive historical issuance truth from mutable retained
results. There is no import/reissue shortcut for continuing old authority.

This remains an in-memory system without durable authority continuity across
process restart. A new trusted service may issue genuinely new executions in
its own namespace, but cannot claim those are historical issuances. Future
durable migration would require independent original issuance evidence and a
separate design; persistence and that migration are out of scope.

## Decision 12: Release structure

Correct v0.80 on the existing
`feature/v0.80.0-governed-daily-technical-interpretation` branch and release the
combined result as v0.80.0. Do not create a prerequisite v0.79.x release. Preserve
the existing v0.79.0 tag and released commit unchanged.

Plan three separate future reviewable checkpoints:

1. ADR0041 architecture review and acceptance.
2. Slice 8 publication authority hardening, after separate implementation
   authorization, with B1 and compatibility coverage.
3. Governed value isolation plus Interpretation integration, after separate
   implementation authorization, with B2 and combined end-to-end coverage.

Authoring this ADR does not authorize either implementation checkpoint. Both
defects remain release blockers until corrected and verified; acceptance alone
does not make v0.80 releasable.

## Required future implementation test contract

These tests are requirements for separately authorized implementation, not tests
added or executed by this documentation task. Preserve all applicable ADR0040
coverage. Prefer mocked provider/HTTP boundaries and controlled clocks; run
`pytest`, `ruff`, and `mypy` before any separately authorized implementation commit.

### B1: Publication authority and original issuance

1. Publish an authentic technical occurrence before downstream construction;
   first-seen authentication accepts it using the publisher commitment.
2. Coherently replace that occurrence before downstream construction, including
   snapshot and envelope refingerprinting; authentication refuses it.
3. Construct downstream on empty technical history; empty state grants no
   occurrence authority. A later authentic Slice 8 append is accepted.
4. After that append but before first downstream observation, substitute a
   coherent occurrence; refuse it. Also refuse replacement after an earlier
   successful authentication.
5. Mutate the retained snapshot/envelope in place and coherently recompute all
   relevant fingerprints; canonical issuance-byte comparison refuses it.
6. Replace the technical history object or separate store, including empty and
   structurally valid replacements; refuse against original owner identity.
7. Replace the namespace, truncate history, or roll back to an earlier complete
   state with a coherent counter; refuse against the original/current root.
8. Replace a retained occurrence with a distinct equal-content object; refuse
   because this ADR pins retained occurrence identity as well as complete bytes.
9. Remove, duplicate, reorder or replace issuance facts/inventories; refuse any
   mismatch, including when corresponding mutable occurrence views are changed.
10. Simultaneously substitute coherent mutable history and issuance compatibility
    views; prove they cannot replace the publisher-owned committed root.
11. Inject failures at source work, staging, clock, final validation, copy,
    canonical encoding, root preparation and final correspondence/provenance
    seams. Each failure creates no fact, consumes no sequence, changes no
    committed inventory and clears pending state. Prior successful commitments
    survive every later failure; staged facts cannot authenticate.
12. Concurrent publication/read sees an entire occurrence-plus-issuance
    transaction and coherent next sequence. Verify lock order and no recursive
    public history calls or intermediate committed visibility.
13. Reject mismatches of each of the five selectors independently, zero/multiple
    matches, invalid inventory/count/order/IDs, backward availability and a
    technical occurrence not yet available at Interpretation start.
14. Verify private authentication exposes no public authority-creation API and
    cannot append/import/register/mint. Use spies to prove authentication and
    Interpretation do not reacquire providers, issue governance, execute
    qualification, convert bridges or rerun the analyzer. Verify original
    execution-context provenance resolution despite later governance changes.
15. Old coherent in-memory histories lacking issuance facts and restart/loss
    scenarios refuse without backfill, silent reissue or observation-based minting.
16. For authentic Slice 8 executions, compare complete serialized fixtures and
    existing fingerprints byte-for-byte under the same canonical encoding;
    preserve public API/schema, chronology, IDs, repeated executions, formulas,
    identities, package version and Evidence export inventory.

### B2: Governed public isolation and serialized compatibility

1. Recursively prove zero reachable `Enum` instances in domain entry-point
   content, execute result, every history-read result, nested selector/request,
   public value properties/backing fields and refusal reason values. Traverse
   actual dataclass fields/slots, tuples, containers and nested wrappers, not
   just `to_dict()` output. Cover all ten former Enum classes/paths in the table.
2. For every public categorical field and wrapper, use `object.__setattr__`
   where Python permits, nested mutation, and replacement by plausible or
   invalid values. Exercise original, shallow-copied and deep-copied graphs and
   attempted Enum `_name_`/`_value_` mutation through all former public paths.
   Exact strings must resist leaf mutation; no path may expose a singleton.
3. Capture authoritative Interpretation and Slice 8 issuance bytes before these
   attacks and prove they remain unchanged. Subsequent reads must be canonical,
   independent fresh graphs, and new semantic executions must remain canonical.
   Test mutation of one read against another and against the execute return.
4. Verify legacy Enum names, values, iteration/identity behavior and released
   semantic behavior remain unchanged after each attack, without resetting
   mutated definitions to disguise a failure. Prove internal policy/configuration
   and future policy construction remain canonical.
5. Coherently mutate/refingerprint public content and execution envelopes;
   retained authority and future reads remain unchanged, and altered values
   cannot gain occurrence authority through reconstruction or history views.
6. Exercise both comparison operands, their field/value/source and operator,
   satisfied Boolean, tuple replacement and nested wrapper mutation. Prove full
   isolation and complete correspondence checks, including coherent alterations.
7. Exercise the complete artifact reference, both former Enum fields, all identity
   and fingerprint fields, original legacy construction input, normalized
   request and private reconstruction. Assert no backing legacy object/Enum leak
   and no aliasing; reject subclasses and invalid scalar facts.
8. Exercise complete policy identity/configuration isolation, all six thresholds,
   kind and fingerprint. Prove caller mutation cannot change the fixed internal
   policy or future execution, even after coherent public refingerprinting.
9. Preserve warning order for every allowed combination and exact source quality.
   Compare all 18 comparisons, exact order, true/false retention, every operand
   omission case, threshold equality, mixed and unavailable states with freshly
   derived released helper expectations. Verify closed categorical/operand sets.
10. Require byte-for-byte serialized compatibility for identical valid inputs
    using the same serializer, including artifact/policy/configuration and
    comparison projections. Separately assert content fingerprint payload/digest
    compatibility and envelope payload/digest compatibility; do not compare only
    display values or recalculate baselines from the changed implementation.
11. Inject failures in scalar normalization, byte encoding/decoding and public
    reconstruction; require no publication/sequence advance and pending cleanup.
    Verify complete round-trip correspondence and no mutable decoded authority.
12. Retain ADR0040 temporal/as-of, complete provenance, repeated execution, locking,
    history-loss and downstream-stop coverage after integration. No Assessment,
    Strategy, signal/order intent, Agent authority or trading action may occur.

## Non-goals and consequences

Do not introduce durable persistence, cryptographic signing infrastructure, a
generic history framework, multi-provider Interpretation architecture, generic
Evidence changes, broader legacy Enum cleanup, a v0.79.x release, Assessment or
Strategy. Keep private implementation small and repository-consistent; no
unrelated module splitting, refactoring, export or package-version changes.

The correction adds independent original issuance evidence and removes shared
Enum state from new governed value graphs while retaining released semantics.
Costs are complete serialization/validation, fresh reconstruction, in-memory
retention and existing lock-chain occupancy. It intentionally refuses corrupt
or unauthenticated historical states that earlier checks could accept. Private
root layout, internal method names and copy/codec helper placement remain
implementation choices within these frozen contracts, not unresolved authority
or semantic decisions.

## Architecture review checklist

| Review question | Frozen answer |
| --- | --- |
| 1. What proves original Slice 8 issuance? | Complete final technical `to_dict()` canonical bytes, including envelope fingerprint, present as the occurrence's fact in a successfully committed publisher root. |
| 2. Why cannot first observation establish authority? | Only successful technical publication advances that root; downstream observations have no mint or adoption capability. |
| 3. What is the independent publisher trust root? | Service-owned current commitment binding original owner/store, namespace, next sequence, ordered retained occurrence identities and ordered issuance bytes, independent of compatibility views. |
| 4. What is atomic with publication? | Occurrence retention, its issuance fact, root/history correspondence and sequence advancement; all fallible preparation precedes commit. |
| 5. What happens to missing pre-hardening facts? | Refusal without backfill/import/reissue or derivation from mutable history. |
| 6. How is a first-seen occurrence authenticated? | Private Slice 8 whole-inventory/root authentication, exact five-selector match and original-context historical provenance resolution under the existing locks. |
| 7. Why can public Enum mutation no longer affect authority? | No Enum is reachable in governed public graphs; independent canonical immutable bytes retain facts. |
| 8. Why are future reads and legacy Enum definitions protected? | Fresh scalar reconstruction and separate internal policies expose no shared Enum/backing object; mutation of a public wrapper has no path to those definitions or later graphs. |
| 9. Which ADR0040 assumptions are superseded? | Absolute prohibition on Slice 8 internal hardening and mandatory reuse of unsafe legacy Enum-bearing public/retained Python representations, only as specified above. |
| 10. Which ADR0040 contracts remain? | All other semantics, provenance, identities, fingerprints, temporal/as-of, locking, refusal/publication and downstream-stop contracts. |
| 11. Are Slice 8 schemas/fingerprints unchanged? | Yes, for authentic executions; private issuance encoding adds no public schema or fingerprint family. |
| 12. Are governed schema/fingerprint semantics preserved? | Yes; new Python scalar wrapper names preserve complete serialized projections and both distinct fingerprint payloads. |
| 13. Is the trust boundary explicit? | Yes; public mutation and compatibility-view substitution are covered, arbitrary replacement of all trusted code and every publisher root simultaneously is not. |
| 14. Does the system stop before Assessment? | Yes; governed Interpretation is the terminal v0.80 stage, without Strategy or trading/Agent authority. |
