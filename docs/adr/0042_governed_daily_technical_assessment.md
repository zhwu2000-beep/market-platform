# ADR 0042: Governed Daily Technical Assessment

## Status

Accepted

ADR0042 is the accepted architecture contract for v0.81.0. Implementation
remains separately authorized and review-gated. Released v0.80 and all prior
public/serialized contracts remain frozen. ADR0040, ADR0041 and the v0.80
handoff remain unchanged.

## Context and inspected baseline

The released governed path ends at an authentic retained Interpretation
occurrence. Legacy Assessment already supplies classic findings and outcome
rules, but its public runner requires legacy Interpretation provenance that the
governed path does not have. v0.81 composes those released rules over an exact
authenticated governed Interpretation publication without inventing provenance
or changing Interpretation semantics.

Baseline verified before branch creation:

- Branch: `main`.
- HEAD and local `origin/main`:
  `f89319845602edc7d704859eb59046ca1bcdbc9e`.
- Working tree and index: clean.
- Released v0.80.0 merge, verified as an ancestor:
  `7001b0bb683c245c989c1ce148427f51b27d5391`.
- Package: `0.1.0`.
- Evidence root: 69 ordered unique exports.
- Documentation branch:
  `feature/v0.81.0-governed-daily-technical-assessment`.

Released source anchors, relative to the repository root:

- [ADR0040](0040_governed_daily_technical_interpretation.md): governed
  Interpretation content, execution, provenance, chronology and lock contracts.
- [ADR0041](0041_publication_time_technical_issuance_authority_and_governed_interpretation_value_isolation.md):
  B1 technical publication authority, B2 zero-Enum governed values and complete
  immutable Interpretation retention.
- [v0.80 handoff](../handoffs/v0.80.0-governed-daily-technical-interpretation-handoff.md):
  released B-01 pinned pending cleanup and B-02 pinned authority locking.
- `src/market_platform/application/polygon_completed_daily_production_interpretation.py`:
  pinned owner/state, canonical result reconstruction, `_check_history`, private
  technical authentication, public history and publication.
- `src/market_platform/application/polygon_completed_daily_production_technical.py`:
  existing private publication authentication and original upstream support.
- `src/market_platform/research/governed_daily_technical_interpretation.py`:
  released scalar source, artifact and Interpretation-specific policy wrappers.
- `src/market_platform/research/daily_technical_assessment.py`:
  `build_classic_assessment_findings(...)`, `classic_assessment_outcome(...)`
  and the separate legacy runner.
- `src/market_platform/research/classic_daily_technical.py`,
  `src/market_platform/research/technical_policy.py` and
  `src/market_platform/_fingerprint.py`: fixed Assessment policy, empty
  configuration and canonical fingerprint semantics. The complete policy
  projection/digest below was verified using the released policy in the project
  environment; no tests or implementation were added.

## Scope and architecture decision

Freeze this complete v0.81 release boundary:

```text
authenticated released v0.80 governed Interpretation occurrence
→ Governed Daily Technical Assessment
→ governed Assessment result/history
```

Use distinct governed Assessment content/provenance, the released classic
Assessment helper pair, and a distinct Assessment execution envelope. The
research layer owns deterministic value correspondence; the application layer
owns source authentication, chronology, publication and history authority.
Content construction and coherent fingerprints alone establish no occurrence
authority.

The only additive integration with v0.80 is the narrow private Interpretation
authentication capability specified below. It is not a public v0.80 redesign.
No provider acquisition, Evidence lifecycle execution, qualification, bridge
conversion or technical analysis is performed by Assessment.

v0.81 stops at governed Assessment result/history. Explicitly exclude Strategy,
recommendation, buy-point, target, stop, signal, order intent, Agent authority
and trading automation. Also exclude runtime policy registration, a generic
multi-provider framework, durable storage/migration, new package-root exports
without separate justification, and unrelated refactoring.

## Decision 1: Exact Interpretation source request

Freeze `PolygonCompletedDailyAssessmentRequest` with exactly five selectors:

| Field | Exact meaning |
| --- | --- |
| `artifact_reference` | Complete governed artifact reference retained by the selected v0.80 Interpretation source occurrence |
| `interpretation_history_namespace_id` | Original `polygon_completed_daily_interpretation_history:<32 lowercase hex>` namespace |
| `interpretation_history_sequence` | Positive exact built-in `int`; reject `bool` and integer subclasses |
| `interpretation_execution_id` | Original `polygon_completed_daily_interpretation:<32 lowercase hex>` execution ID |
| `interpretation_fingerprint` | COMPLETE selected v0.80 Interpretation RESULT ENVELOPE fingerprint |

The request retains a fresh exact zero-Enum `GovernedTechnicalArtifactReference`
with its released complete projection: `schema_version`, `artifact_id`,
`artifact_version`, `artifact_fingerprint`, `information_class`, `authority`
and reference `fingerprint`. Preserve `evidence_artifact_reference/v2` and
distinguish artifact fingerprint from reference fingerprint. Reusing this
released scalar value does not widen its contract. Validate exact scalar leaves
and detach the entire request, including the nested reference.

`interpretation_fingerprint` is NOT
`GovernedDailyTechnicalInterpretation.fingerprint`, `source_content_fingerprint`
or a technical snapshot fingerprint. It denotes the envelope containing the
selected Interpretation and its execution/history facts.

All five selectors must conjunctively identify exactly one committed authentic
Interpretation occurrence. Compare the complete artifact-reference projection,
not only an artifact ID or digest. No selector individually grants authority;
neither a latest-result search nor content-equivalence selection is permitted.
No caller-supplied source object, bytes, fingerprint, execution timestamp,
analysis cutoff override, policy or configuration becomes bearer authority.

## Decision 2: Private additive v0.80 authentication capability

Authorize one narrow PRIVATE additive capability in
`PolygonCompletedDailyProductionInterpretationApplicationService`, for future
implementation under this ADR: authenticate an exact already-published
Interpretation occurrence for a downstream governed consumer. Its private name
and small helper layout remain implementation choices. It creates no public
registration, import, append or authority-creation API.

The capability runs under the already-acquired full lock chain through the
original pinned Interpretation owner. It assumes those upstream locks are held;
it must not call `_lock_inputs` itself. It must:

1. Require the original pinned Interpretation history owner. Preserve existing
   owner/compatibility-view correspondence checks without letting a replaceable
   view select the owner or its lock.
2. Require correspondence with the original namespace, including empty history.
3. Require current owner state identity to equal the independently pinned
   current committed state. Equality of a replacement state is insufficient.
4. Validate the complete canonical immutable committed-byte inventory: exact
   `bytes`, complete projections and both fingerprints, count/next-sequence
   correspondence, contiguous positive exact integer sequences, namespace,
   unique execution IDs, per-occurrence chronology and nondecreasing
   publication availability. Reject missing, duplicated, reordered, replaced,
   truncated or rolled-back inventory/state against the independent commitment.
5. Reconstruct committed facts only from those bytes; round-trip canonical
   encoding must equal the original complete fact. Typed public graphs and
   caller-supplied bytes do not provide reconstruction authority.
6. Authenticate every retained Interpretation occurrence's original technical
   and provenance support through existing private upstream authentication.
   Preserve B1 original technical issuance and its retained occurrence identity
   requirements, original technical execution context, retained bridge and
   qualification context, and complete historical lineage. Validate the entire
   committed inventory before selecting one occurrence.
7. Verify nonsemantic source-lineage correspondence: complete five technical
   selectors, technical envelope availability, canonical instrument/mapping
   subject, source trading identity, historical `analysis_as_of`, snapshot,
   governed dataset and research dataset fingerprints, and exact source quality
   and ordered warnings. Check original source availability at Interpretation
   start. Validate released scalar schemas/projections and fixed policy
   identity. Do not recompute expected Interpretation states or expected
   comparison inventory/truth from the upstream technical snapshot and
   Interpretation policy.
8. Match all five Assessment source selectors conjunctively to exactly one
   authentic reconstructed occurrence, and require its availability by the
   Assessment start for execution.
9. Return a fresh reconstructed authentic occurrence, optionally with its exact
   committed fact/provenance projection for rechecking. Expose no mutable
   authority handle; Python identity with a public Interpretation result is
   neither required nor sufficient.
10. Recheck pinned owner, namespace, current committed state identity, complete
    inventory and original historical support after fallible work. Compare
    source projections with the independently authenticated pre-work facts.
    Persistent drift fails closed; observation must not adopt changed facts.

Authority comes from exact membership in the publisher-owned committed bytes.
An authentic publication predating downstream service construction is eligible;
first observation supplies no publication authority. Empty or pending history
authorizes no occurrence. Missing original committed facts or historical support
causes refusal without backfill, repair, reissue or first-observation adoption.

This private capability must NOT call public Interpretation execute/history
APIs, `_check_content`, `validate_governed_daily_technical_interpretation`,
`classic_states` or `build_classic_comparison_evidence`. It must not directly or
indirectly rerun Interpretation semantics, provider acquisition, Evidence
lifecycle, qualification, bridge conversion or technical analysis. This
prohibition includes deriving expected trend/momentum/volatility/extension
states from the technical snapshot, deriving the expected comparison
inventory from snapshot/policy, independently determining which comparisons
should exist from technical inputs, or otherwise recomputing expected
Interpretation semantic output from upstream technical facts.

Reuse of a private reconstruction helper is permitted when its complete call
path meets that semantic no-rerun restriction. Preserve normal released v0.80
structural reconstruction and value validation: canonical byte decoding and
re-encoding, schema and fingerprint validation, exact scalar/category
validation, and complete retained projection validation. This includes local
self-consistency validation of an already-retained governed comparison
value's operator, left operand, right operand and satisfied Boolean
relationship wherever the released value type already requires it. These
retained-value checks remain allowed and must not be bypassed or weakened.
They must not become alternate Interpretation semantic execution: they do
not derive expected states or comparison inventory/truth from upstream
snapshot/policy. The committed Interpretation bytes remain publication
authority for the already-issued Interpretation semantic result.

Released public Interpretation history validation currently includes semantic
correspondence. This private path does not weaken, replace or bypass validation
for those public APIs. Their behavior, schemas, serialization, fingerprints and
API remain unchanged. The new consumer authenticates an already-committed
Interpretation decision, then independently validates Assessment semantics.

## Decision 3: Sole Assessment semantic source

Freeze exactly these released helpers from `daily_technical_assessment.py` as
the sole Assessment rule source:

- `build_classic_assessment_findings(...)`
- `classic_assessment_outcome(...)`

Findings are computed first; the resulting findings are passed to the outcome
helper. Do not use `assess_daily_technical_interpretation(...)` as the governed
execution boundary, call caller-supplied `policy.assess(...)`, or duplicate
finding/outcome formulas in the governed layer or its validator.

A private detached semantic adapter may expose only the authenticated facts
needed by the pair:

- `trend_direction`, `momentum_direction`, `volatility_state`, `extension_state`;
- `comparison_evidence[*].evidence_id` and `.satisfied`;
- `source_quality` and ordered `source_warnings`.

It may map governed exact-string categories to the released legacy Enum members
only inside the private computation boundary required by the helpers' identity
comparisons. Intermediate legacy finding/outcome values stay there and are
immediately projected to fresh governed scalar values. Do not fabricate a
`DailyTechnicalInterpretation`,
`source_daily_instrument_integrity_evidence_fingerprint`, or any other legacy
provenance fact absent from v0.80. The adapter is a minimal semantic view, not a
legacy provenance carrier. No legacy Enum or carrier is retained or returned in
a governed public graph.

Assessment rule computation consumes released comparison truth. It does not
derive expected Interpretation states or comparison inventory/truth from
upstream snapshot/policy; Decision 2 preserves released retained-value
structural/self-consistency validation.
The governed semantic validator independently constructs a fresh detached
authenticated source and fresh expected findings/outcome using this same helper
pair. It compares complete governed content correspondence: all source facts,
occurrence selectors, policy identity/configuration, finding fields/order,
outcome, schema and fingerprint. It must not reuse candidate findings as its
expected findings. Fingerprint coherence alone is insufficient. Recheck source,
policy and complete output correspondence after fallible computation and
publication preparation.

## Decision 4: Fixed Assessment policy identity

Freeze the complete classic Assessment policy:

| Field | Frozen value |
| --- | --- |
| `schema_version` | `technical_policy_identity/v1` |
| `policy_kind` | `daily_technical_assessment` |
| `policy_id` | `classic_daily_technical_coherence` |
| `behavioral_revision` | `1.0.0` |
| `configuration_schema` | `classic_daily_technical_assessment_configuration/v1` |
| `configuration` | `{}` |
| `fingerprint` | `sha256:dbdf4bdb4eeb3880d5a6ad4f90d17d9934782f6e1d0d455cb3af93a20d74874f` |

The underlying released policy is `ClassicDailyTechnicalAssessmentPolicy` and
the underlying configuration is `ClassicDailyTechnicalAssessmentConfiguration`.
Validate every fixed identity field and the empty configuration, as well as the
complete fingerprint. No runtime Assessment policy selection or registration is
introduced. Internal policy/configuration objects are fresh and separate from
public values; their existence does not make `policy.assess(...)` the governed
execution boundary.

Introduce an Assessment-specific scalar policy wrapper with exactly the seven
fields in the table. Its Python name is a local implementation choice. Do not
widen or repurpose released `GovernedTechnicalPolicyIdentity`, whose kind is
Interpretation-specific. Preserve the released serialized `TechnicalPolicyIdentity`
projection and fingerprint semantics: complete identity payload excluding its
own fingerprint, canonical SHA-256 machinery, and configuration serialized as
`{}` without invented nested fields. All identity fields except configuration
are exact built-in strings, including `policy_kind`; expose no
`TechnicalPolicyKind` Enum or backing `TechnicalPolicyIdentity`/classic policy.
If an empty configuration object is retained publicly, it must be fresh,
nonshared and zero-Enum. Serialized dictionaries must also be detached.

## Decision 5: Governed Assessment content

Freeze:

```text
GOVERNED_DAILY_TECHNICAL_ASSESSMENT_SCHEMA =
    "governed_daily_technical_assessment/v1"
```

`GovernedDailyTechnicalAssessment` deterministic content has exactly these
fields; all are mandatory:

| Field | Binding |
| --- | --- |
| `source_interpretation_occurrence` | Complete five-selector `PolygonCompletedDailyAssessmentRequest` value |
| `source_interpretation_content_fingerprint` | Selected authentic `result.interpretation.fingerprint` |
| `canonical_instrument_id` | Exact authenticated Interpretation content identity |
| `source_trading_identity` | Exact authenticated Interpretation content trading identity |
| `analysis_as_of` | Exact authenticated historical market-analysis time |
| `assessment_policy_identity` | Complete fixed Assessment-specific scalar policy identity above |
| `source_quality` | Exact authenticated Interpretation quality string |
| `source_warnings` | Complete exact ordered tuple of authenticated Interpretation warning strings |
| `outcome` | Exact closed outcome string below |
| `findings` | Exact tuple of fresh governed findings in frozen relative order |
| `schema_version` | `governed_daily_technical_assessment/v1` |
| `fingerprint` | Canonical deterministic fingerprint over all other content fields |

The source content fingerprint is distinct from the selected source envelope
fingerprint in `source_interpretation_occurrence.interpretation_fingerprint`.
Canonical/trading identities, analysis time, quality and warnings must correspond
exactly to the authenticated Interpretation content, with detached zero-Enum
values. Preserve released identity projections. Quality is `complete` or
`degraded`; warnings are `insufficient_profile_history`, then `stale_evidence`
when present. No addition, omission, sorting, quality promotion or renaming is
permitted.

Do NOT directly duplicate `source_technical_occurrence`,
`source_technical_analysis_snapshot_fingerprint`,
`source_governed_dataset_fingerprint`,
`source_research_dataset_content_fingerprint`, `interpretation_policy_identity`,
`trend_direction`, `momentum_direction`, `volatility_state`, `extension_state`
or `comparison_evidence`. They remain transitively bound by the authenticated
Interpretation occurrence and its content fingerprint; the finding references
identify comparisons in that retained Interpretation.

Do not add any legacy integrity fingerprint, score, confidence, severity,
recommendation, Strategy, buy-point, target, stop, signal or action field.
Descriptive source quality, warnings, findings and outcome confer no Evidence
lifecycle permission or downstream execution authority.

## Decision 6: Governed findings and released outcome

Freeze a zero-Enum governed finding value with exactly:

| Field | Contract |
| --- | --- |
| `kind` | Exact built-in `str`, closed to `conflict` and `caution` |
| `code` | Exact built-in `str`, closed to the nine-code inventory below |
| `comparison_evidence_ids` | Exact tuple of exact built-in strings, with exact support and order below |

No Enum/string subclass, extra field, arbitrary code, duplicate finding or
arbitrary comparison reference is accepted. Freeze these possible findings in
this relative order. This table documents released helper behavior; it is not
authorization to reimplement its formulas.

| Order | Code | Kind | Released trigger/support |
| --- | --- | --- | --- |
| 1 | `direction_opposition` | `conflict` | Opposite positive/negative trend and momentum; complete satisfied support tuple below |
| 2 | `rsi_elevated` | `caution` | Satisfied `rsi_at_or_above_elevated`; that single reference |
| 3 | `rsi_depressed` | `caution` | Satisfied `rsi_at_or_below_depressed`; that single reference |
| 4 | `ema20_above_reference_band` | `caution` | Satisfied `extension_above_positive_band`; that single reference |
| 5 | `ema20_below_reference_band` | `caution` | Satisfied `extension_below_negative_band`; that single reference |
| 6 | `high_realized_volatility` | `caution` | Satisfied `volatility_at_or_above_high`; that single reference |
| 7 | `source_quality_degraded` | `caution` | Source quality `degraded`; empty references `()` |
| 8 | `source_warning_insufficient_profile_history` | `caution` | Corresponding source warning present; empty references `()` |
| 9 | `source_warning_stale_evidence` | `caution` | Corresponding source warning present; empty references `()` |

Non-triggered findings are omitted while this relative ordering is retained.
For positive trend and negative momentum, `direction_opposition` references are
exactly, in order:

1. `trend_ema8_above_ema20`
2. `trend_close_above_ema144`
3. `trend_close_above_ema169`
4. `momentum_macd_line_below_signal`
5. `momentum_rsi_below_neutral`

For negative trend and positive momentum, they are exactly, in order:

1. `trend_ema8_below_ema20`
2. `trend_close_below_ema144`
3. `trend_close_below_ema169`
4. `momentum_macd_line_above_signal`
5. `momentum_rsi_at_or_above_neutral`

If an opposition state exists but any required reference is absent or not
satisfied, execution fails closed with semantic refusal; it must not silently
omit the conflict. Preserve the released helper's failure. The other five
comparison-backed findings each retain exactly their listed single reference.
Source-quality and source-warning findings retain empty references.

Governed outcome is an exact built-in string, closed to `aligned`, `mixed`,
`caution` and `insufficient_data`. Freeze released precedence exactly:

1. `insufficient_data` if any required trend, momentum, volatility or extension
   state is `unavailable`.
2. Otherwise `mixed` if trend or momentum is `mixed`, or a
   `direction_opposition` conflict exists.
3. Otherwise `caution` if any caution finding exists.
4. Otherwise `aligned`.

Findings are computed before outcome. An `insufficient_data` or `mixed` outcome
does not delete otherwise valid caution findings. Missing state data remains a
descriptive Assessment outcome; missing authentic publication/provenance support
is an authentication refusal, not a substitute `insufficient_data` result.

## Decision 7: Content identity versus execution occurrence

The content fingerprint covers the complete content projection except its own
`fingerprint`. Use existing canonical compact JSON SHA-256 conventions, complete
nested scalar identity projections, canonical UTC timestamps, ordered arrays
for tuples and exact scalar values. Do not serialize Python object identity or
substitute a legacy Assessment schema/fingerprint payload.

The complete five-selector source occurrence remains inside Assessment content
identity. Do not collapse different authentic Interpretation publications merely
because their deterministic Interpretation content fingerprints are equal.
Repeated Assessment of the same authentic Interpretation occurrence with the
same fixed policy/semantics has the same Assessment content fingerprint.

Assessment execution ID, Assessment namespace/sequence, start, completion,
publication availability and `interpretation_available_at` belong to the
separate execution envelope. Repeated Assessment publications have distinct
execution occurrences and envelope identities even when content is identical.
Public reconstruction or coherent refingerprinting grants no publication right.

## Decision 8: Assessment result envelope

Freeze `PolygonCompletedDailyAssessmentResult` and its serialized constants:

| Serialized field | Frozen value |
| --- | --- |
| `schema_version` | `polygon_completed_daily_assessment_result/v1` |
| `operation` | `production.polygon_completed_daily.daily_technical_assessment.application` |
| `operation_version` | `1.0.0` |
| `executor` | `market_platform.application/polygon_completed_daily_production_assessment/v1` |

The result binds exactly the following value fields, plus those constants in
the serialized projection:

| Field | Contract |
| --- | --- |
| `assessment` | Complete governed Assessment content, including its fingerprint |
| `interpretation_available_at` | Selected authenticated Interpretation envelope `available_at` |
| `execution_id` | Unique `polygon_completed_daily_assessment:<32 lowercase hex>` ID |
| `history_namespace_id` | Pinned `polygon_completed_daily_assessment_history:<32 lowercase hex>` namespace |
| `history_sequence` | Positive exact built-in integer, contiguous from 1 within that namespace; `bool` rejected |
| `execution_started_at` | Assessment start S |
| `execution_completed_at` | Assessment completion C |
| `available_at` | Final Assessment publication availability R |
| `fingerprint` | Canonical fingerprint of the complete final serialized projection excluding itself |

Freeze execution ID prefix `polygon_completed_daily_assessment` and history
namespace prefix `polygon_completed_daily_assessment_history`. Execution IDs must
be unique within the committed inventory; next sequence equals committed
count plus one. The envelope fingerprint includes schema, operation, version,
executor, complete content with its fingerprint, source availability and every
execution/history value. Pending or provisional availability is not the final
fingerprinted publication value.

## Decision 9: Zero-Enum public contract and isolation

Every new governed Assessment public graph must contain ZERO reachable Python
`Enum`, `StrEnum` or `IntEnum` instances. This includes request/reference,
content, policy/configuration, finding values, outcome, source quality/warnings,
result, execute returns, every history read, refusal reason, properties and
hidden backing values. Validation covers actual reachable values, not merely
serialized strings. Reject categorical subclasses rather than applying arbitrary
`str(...)` coercion.

All public categorical values use exact built-in strings with the closed
vocabularies specified here or the unchanged artifact vocabulary in ADR0041:
`source_observation`, `source_measurement`, `source_assertion` for information
class; `platform_origin`, `external_origin` for authority. These vocabularies do
not relax exact authentic source selection.

Do not retain `DailyTechnicalAssessment`, `DailyTechnicalAssessmentFinding`,
`TechnicalPolicyIdentity`, `TechnicalPolicyKind`, legacy Interpretation Enum
instances or private semantic adapters anywhere in governed public graphs.
Fresh scalar `CanonicalInstrumentId`, `TradingInstrumentIdentity`, governed
artifact references and canonical UTC datetimes may preserve their released
projections without introducing Enum-bearing descriptors.

Public mutation, including nested mutation, `object.__setattr__`, shallow/deep
copies and coherent refingerprinting, must not affect authoritative history,
future reads, future executions, classic policy objects or legacy Enum
definitions. Reconstruct independent wrapper/configuration graphs for each
execute return and history read. Only safe exact immutable scalar leaves may
be shared. A frozen dataclass alone is not proof of isolation; no property,
backing value or cache may expose a shared legacy object or mutable authority.

The trust boundary preserves ADR0041: trusted publisher code, independently
pinned private commitments and lock discipline are trust anchors. This does
not claim protection against simultaneous arbitrary replacement of all trusted
executable code and every private trust root, or introduce cryptographic signing
or durable authority continuity.

## Decision 10: Assessment history authority and atomic publication

Assessment adopts the corrected authority model from its first implementation:

```text
authority owner == lock owner == staging owner == commit owner == cleanup owner
```

Use one independently pinned Assessment history owner and original namespace.
Independently pin the current committed state, including next sequence and the
ordered complete immutable fact inventory. Require current owner state identity
to be that independently pinned committed state before and after fallible work.
An equal replacement, namespace substitution, rollback or truncation must not
establish a new commitment. Do NOT introduce a replaceable `_history`
compatibility alias unless a concrete compatibility requirement is separately
approved. v0.81 has no existing Assessment compatibility requirement.

Authoritative retained facts are the complete canonical immutable built-in
`bytes` of each FINAL `PolygonCompletedDailyAssessmentResult.to_dict()`
projection, including Assessment content fingerprint and result envelope
fingerprint. Typed public graphs, mutable decoded dictionaries/lists, Enum
members, caller buffers and pending staging are not authority. Equal immutable
byte values denote the same fact; byte object identity is not content identity.
Only successful publisher commit adds occurrence membership.

Use canonical UTF-8 compact JSON with sorted keys, `ensure_ascii=False`, no
nonfinite numbers or insignificant whitespace, complete key presence, canonical
UTC timestamp strings and preserved array order/scalar types. Decode only exact
bytes and require canonical re-encoding to reproduce them. Validate full schemas,
content/envelope fingerprints and exact complete projection correspondence;
never replace the final projection with a digest-only inventory or a fingerprint
payload that omits the envelope fingerprint.

`execute()` and every history read reconstruct fresh zero-Enum public graphs
from canonical bytes. Before a read returns, validate the entire committed
Assessment inventory, original owner/namespace/current state, sequence and ID
inventory, chronology, authentic Interpretation sources and original historical
support. Independently validate Assessment semantic/content correspondence
against those detached authenticated sources, then recheck authority and support
after fallible reconstruction/validation. Filtering an as-of read must not hide
corruption in the complete inventory. No history read can append, repair,
adopt or import facts. Retained bytes do not excuse lost upstream support.

Publication is one transaction under the complete common lock chain:

1. Validate the pinned Assessment commitment and entire history. Authenticate
   the exact source occurrence and capture detached committed/source projections.
2. Compute findings, outcome and content through the frozen helper boundary;
   independently validate full semantic and source correspondence.
3. Stage on the pinned owner. Sample/validate all clocks, select the next
   sequence and unique execution ID, and prepare final availability and envelope
   fingerprint. Staging confers no occurrence authority.
4. Encode final canonical bytes, reconstruct the defensive public return from
   those bytes and prepare the entire next committed state. Validate complete
   byte/projection correspondence and graph detachment.
5. Complete every fallible callback, allocation, codec, validation, copy and
   provenance operation. Reauthenticate the source and original historical
   support and recheck owner, namespace, current state identity, pending staging,
   complete prior inventory, temporal order, semantics and final prepared
   projections after fallible seams. Require public-return encoding to equal
   the exact final fact to be committed.
6. Atomically advance the independently pinned commitment and that same owner's
   state under its lock. Clear pending on that owner and return the already
   prepared public result.

Every fallible operation precedes authoritative state advancement. After commit
there must be no fallible callback, codec, validation, provenance or public-copy
operation. Commit and pending cleanup must not dispatch fallible extension
behavior. Observers under the shared chain see the complete previous or complete
new state, never a partial commit.

Any failed publication appends no fact, consumes no sequence, preserves the
previous commitment and previous owner state, and clears pending on the pinned
owner. Earlier successful publications survive later failures. Cleanup must
not consult a replaceable attribute to choose its owner. A failed read changes
no commitment. Loss of authority/history/support causes refusal; no durable
persistence or restart recovery is specified by this release.

## Decision 11: Temporal and lock contract

Freeze `I <= S <= C <= R`:

| Symbol | Meaning |
| --- | --- |
| I | Authenticated source Interpretation `available_at` |
| S | Assessment `execution_started_at` |
| C | Assessment `execution_completed_at` |
| R | Assessment publication `available_at` |

The source must be available by S, inclusive. Use the existing canonical UTC
convention. R is nondecreasing across complete Assessment history. History
visibility is inclusive, `R <= knowledge_as_of`. `analysis_as_of` remains the
historical market-analysis time; it is not relabeled as execution, source
availability or publication time. Preserve all original Interpretation,
technical, bridge and qualification contexts and chronology; later upstream
records do not rewrite the original source's historical support.

Freeze the exact lock order:

```text
construction
→ validation
→ freshness
→ admission
→ validity
→ qualification
→ bridge
→ technical
→ governed interpretation
→ governed assessment
```

The Interpretation position uses its original pinned authority-owner lock;
the final lock is the pinned Assessment authority-owner lock. Compose the
upstream chain exactly once, then acquire Assessment. Execute and every history
read use the same order and hold the complete chain through final source checks,
publication preparation and commit, or final read validation.

Never call public Interpretation execute/history while holding the chain, or
recursively reacquire non-reentrant locks. Private Interpretation authentication
assumes appropriate upstream locks are already held and must not call
`_lock_inputs` itself. A replaceable history/view cannot redirect either pinned
authority lock, staging, commit or pending cleanup.

## Decision 12: Assessment refusal contract

Freeze refusal reasons as exact built-in strings, never an Enum or string
subclass. Preserve the distinct failure categories:

| Constant | Exact value | Meaning |
| --- | --- | --- |
| `INTERPRETATION_UNAVAILABLE` | `interpretation_occurrence_unavailable` | No exact authentic source occurrence available by Assessment start |
| `HISTORY_INVALID` | `history_incomplete_or_corrupt` | Invalid owner/namespace/commitment, inventory or historical support |
| `SOURCE_MISMATCH` | `source_lineage_mismatch` | Authenticated lineage or retained source correspondence differs |
| `SEMANTIC_FAILED` | `semantic_execution_or_correspondence_failed` | Helper execution, complete opposition support or governed semantic correspondence fails |
| `TEMPORAL_FAILURE` | `temporal_failure` | Invalid execution/publication timestamps or temporal ordering |
| `PUBLICATION_FAILED` | `assessment_publication_or_copy_failed` | Staging, canonical encoding, publication preparation or defensive reconstruction fails |

Authentication/structural failure must not be converted into an Assessment
outcome or partial result. Source not yet available at S remains unavailable;
invalid Assessment clocks/order are temporal failures. All publication refusals
obey the unchanged-state and pinned pending-cleanup guarantees above.

## Decision 13: Module placement and release preservation

Freeze these planned modules for separately authorized implementation:

| Path | Responsibility |
| --- | --- |
| `src/market_platform/research/governed_daily_technical_assessment.py` | Governed content, scalar policy/finding values, detached helper adapter and independent semantic correspondence |
| `src/market_platform/application/polygon_completed_daily_production_assessment.py` | Source-specific execution, temporal/refusal envelope, pinned authority and history |
| `tests/unit/test_governed_daily_technical_assessment.py` | Future governed contract and semantic/isolation coverage |
| `tests/unit/test_polygon_completed_daily_production_assessment.py` | Future authentication, publication/history, time and lock coverage |

Private additive v0.80 authentication work remains in
`src/market_platform/application/polygon_completed_daily_production_interpretation.py`.
Keep this bounded integration separate from any public redesign or semantic
change. Do not pre-split a generic history/policy framework or change unrelated
modules. Do not add package-root exports unless separately justified; Evidence
exports remain exactly 69.

Explicitly preserve every released v0.80 non-negotiable:

| Released contract | v0.81 preservation |
| --- | --- |
| B1 technical publication authority | Original publisher-owned committed issuance and retained technical occurrence checks remain required |
| No first-observation authority | No downstream observation, coherent fingerprint, pending value or supplied graph establishes issuance |
| B2 zero-Enum governed Interpretation graphs | All released public scalar values, isolation and legacy-definition protection remain unchanged |
| B-01 pinned pending cleanup | Original Interpretation owner remains staging, publication and cleanup owner |
| B-02 pinned Interpretation authority lock | Original pinned owner supplies the Interpretation lock, including replacement/swap-back scenarios |
| Interpretation content schema | `governed_daily_technical_interpretation/v1` unchanged |
| Interpretation result schema | `polygon_completed_daily_interpretation_result/v1` unchanged |
| Interpretation operation | `production.polygon_completed_daily.daily_technical_interpretation.application` unchanged |
| Interpretation version/executor | `1.0.0` and `market_platform.application.polygon_completed_daily_production_interpretation/v1` unchanged |
| Existing five technical source selectors | `artifact_reference`, `technical_history_namespace_id`, `technical_history_sequence`, `technical_execution_id`, `technical_fingerprint` unchanged |
| Fixed Interpretation policy | Complete released identity/configuration and `sha256:9d81e49a6d45d27071e804b46486ae247d71f650184e8032a792586807fc3d02` unchanged |
| Classic Interpretation formulas and 18 comparisons | Rules, thresholds, operand/operator facts, true/false retention, omission conditions and ordered inventory unchanged |
| Serialized/fingerprint compatibility | Every released public projection and content/envelope fingerprint semantic remains unchanged |
| Public Interpretation history behavior | Complete existing validation, including semantic correspondence, freshness of public graphs and as-of behavior remain unchanged |
| Complete canonical Interpretation bytes | Final complete result projections including both fingerprints remain authority; no typed-object substitution |
| Chronology/as-of | Released source availability, original contexts, canonical UTC, nondecreasing availability and inclusive visibility unchanged |
| Lock order through pinned Interpretation | Existing upstream chain and owner lock unchanged; Assessment appends one final position |
| Package/Evidence inventory | Package `0.1.0`; 69 ordered unique Evidence exports |

All prior released public/serialized contracts, including legacy Assessment,
remain frozen. ADR0040, ADR0041, the v0.80 handoff and `pyproject.toml` are not
modified. v0.80's released stop at Interpretation remains historical fact;
v0.81 is a new downstream composition ending at Assessment.

## Required future implementation verification

These are requirements for separately authorized implementation, not tests
implemented or run by this documentation task. Prefer mocked provider/HTTP
boundaries and controlled clocks; run `pytest`, `ruff` and `mypy` before a future
implementation commit in accordance with AGENTS.md.

1. Verify exact request fields, built-in types, ID grammars, complete artifact
   correspondence and each selector mismatch; distinguish source envelope and
   content fingerprints. Cover no/ambiguous matches and availability equality.
2. Accept original authentic Interpretation publications before downstream
   construction and authentic later publications after an initially empty
   history. Refuse first-observation adoption, coherent source substitution,
   namespace/owner replacement, equal-but-replaced state, truncation, rollback,
   inventory changes, lost support and pending-only values.
3. Validate complete Interpretation bytes and every occurrence's original
   technical/provenance support, with rechecks after fallible work. Prove that
   fresh source reconstruction needs no public result object identity and that
   original B1 technical occurrence identity remains enforced internally.
4. Use spies to prove downstream authentication never calls public Interpretation
   execute/history, `_check_content`,
   `validate_governed_daily_technical_interpretation`, `classic_states` or
   `build_classic_comparison_evidence`; no provider, Evidence lifecycle,
   qualification, bridge or analyzer execution is rerun. Preserve public v0.80
   history's existing semantic validation independently.
5. Compare helper-derived expected findings for all nine codes, both ordered
   opposition tuples and missing/false support refusal, exact single/empty
   references and all omission/order cases. Verify outcome precedence and
   retention of caution findings under `mixed` and `insufficient_data`.
6. Verify the adapter accesses only the permitted source facts, translates Enum
   values privately, fabricates no legacy provenance, and never invokes a
   legacy runner or caller policy. Independently reject coherent altered
   content, finding support/order, outcome, source facts or policy identity.
7. Verify the complete fixed policy projection/digest and fresh empty public
   configuration. Assert released `GovernedTechnicalPolicyIdentity` remains
   Interpretation-specific and no runtime Assessment policy selection exists.
8. Recursively inspect all new public graphs, properties/backing values and
   refusals for zero Enum instances and exact closed strings. Mutate/refingerprint
   public values and shallow/deep copies; prove authoritative bytes, other/future
   reads, future executions, classic policy objects and legacy Enum definitions
   remain unchanged without resetting definitions to hide a failure.
9. Verify repeated same-source Assessment has equal content identity and unique
   execution identity. Different authentic Interpretation publications with
   equal Interpretation content remain distinct Assessment content sources.
10. Verify complete content/envelope projections, canonical round trips, both
    fingerprints, contiguous sequence/unique ID inventory, fresh read/return
    graphs and complete historical source/semantic validation on every read.
11. Inject failures at staging, clocks, callbacks, semantic/source checks, codec,
    public reconstruction and next-state preparation. Assert no fact/sequence
    advancement, prior commitment/owner-state preservation and pinned pending
    cleanup. Prove no fallible operation remains after authoritative advancement.
12. Exercise `I <= S <= C <= R`, equal boundaries, nondecreasing R, inclusive
    `R <= knowledge_as_of`, invalid clocks and original historical contexts.
    Verify exact lock acquisition order, one upstream composition, pinned final
    owners, no recursive non-reentrant acquisition and atomic read/publication
    visibility, including attempted owner redirection during fallible seams.
13. Preserve B1, B2, B-01, B-02 and all frozen v0.80 public behavior, serialized
    fixtures/fingerprints, 18 comparisons, package version and export inventory.
    Assert v0.81 publishes only Assessment result/history with no downstream
    Strategy, recommendation or execution authority.

## Rationale and rejected alternatives

| Alternative | Reason rejected |
| --- | --- |
| Direct reuse of legacy Assessment runner | Its legacy carrier/provenance boundary does not represent a governed v0.80 occurrence |
| Fabricated legacy Interpretation/integrity provenance | Introduces facts absent from the authentic source and conflates distinct provenance identities |
| Caller-supplied policy or `policy.assess(...)` | Violates the fixed classic governed semantic boundary and adds caller-controlled execution |
| Assessment formula duplication | Creates a second rule source and permits drift from released finding/outcome semantics |
| Content-fingerprint-only source selection | Erases distinct authentic publications and fails the conjunctive occurrence contract |
| First-observation authority | Cannot prove original publisher commit and can adopt substituted coherent history |
| Typed-object authoritative history | Public mutation and coherent refingerprinting can change retained meaning; independent complete bytes are required |
| Legacy Enum-bearing governed outputs | Exposes shared mutable Enum/policy state through public graphs and violates zero-Enum isolation |
| Reusing/widening the Interpretation policy wrapper | Changes a frozen Interpretation-specific public contract to support a different policy kind |
| Replaceable Assessment history determining authority lock | Separates the lock owner from the authority/staging/commit/cleanup owner and repeats the B-02 failure mode |
| Recursive public Interpretation history acquisition | Reacquires non-reentrant locks and reruns semantics outside the private authentication contract |
| Weaker public v0.80 history validation | A new downstream capability does not justify changing released public guarantees |
| Proceeding into Strategy in v0.81 | Exceeds the governed Assessment result/history release boundary |

The design preserves a single released Assessment rule source and exact original
publication membership. Costs are complete inventory/provenance validation,
fresh reconstruction and occupancy of the existing lock chain. In-memory
retention and upstream support remain prerequisites; persistence, signing and
migration require a separate design. Private names and local codec/adapter
layout remain implementation choices; source authority, public fields,
semantics, fingerprints, chronology and publication guarantees are not deferred.

## Architecture review checklist and stop boundary

| Review question | Proposed frozen answer |
| --- | --- |
| What selects the source? | All five request selectors conjunctively, including the complete Interpretation envelope fingerprint |
| What authenticates it? | Exact membership in the original publisher's independently committed complete canonical bytes, plus original historical support |
| Is Interpretation recomputed? | No in the new private consumer path; released public history validation remains unchanged |
| What computes Assessment? | Only `build_classic_assessment_findings(...)` then `classic_assessment_outcome(...)`, through a detached private boundary |
| How is content validated? | Fresh helper-derived expectations from authenticated detached source and complete governed content correspondence |
| Can equal Interpretation content erase occurrences? | No; all five source occurrence selectors remain in Assessment content identity |
| What is public? | Fresh zero-Enum scalar governed request/content/policy/findings/result/history and exact string refusal reasons |
| What is authority? | Final complete committed result bytes under one pinned owner and independently pinned current state |
| When is commit safe? | After all fallible work, source/support rechecks and public reconstruction, under the full chain ending at pinned Assessment |
| What remains frozen? | All released v0.80 and prior public/serialized contracts, B1/B2/B-01/B-02, package `0.1.0` and Evidence exports 69 |
| Where does v0.81 stop? | Governed Assessment result/history |

This ADR grants no Strategy, recommendation, buy-point, target, stop, signal,
order intent, Agent authority or trading automation. This documentation task
creates only the feature branch and this Proposed ADR: no implementation,
tests, staging, commit, push, merge, tag or release.
