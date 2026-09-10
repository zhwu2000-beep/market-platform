# ADR 0040: Governed Daily Technical Interpretation

## Status

Accepted. The contracts below are frozen for v0.80 governed Daily Technical
Interpretation. Implementation requires separate authorization. ADR0039 remains
Accepted; ADR0039 and released v0.79 remain frozen and unchanged.

## Context and inspected baseline

The released Polygon Daily Technical path stops at an authentic retained
technical result. Its snapshot contains the classic scalar inputs, but its
governance provenance is not the legacy instrument-integrity provenance required
by [ADR0030](0030-daily-technical-interpretation-assessment-foundation.md).
A new composition must describe that technical occurrence truthfully without
changing either released upstream governance or legacy Interpretation.

Baseline verified for this draft:

- Branch: `feature/v0.80.0-governed-daily-technical-interpretation`.
- HEAD/released main: `2a3c90707f44433e15367367a8d73d7e68d34cdc`.
- Tree: `5770cb249afa4fbbeed387edb4d92ec48aa13627`.
- Annotated `v0.79.0` tag object:
  `2dfe41bf401f6ab7af4da0cc616591ecb8f786a1`; peeled target equals HEAD.
- Initial working tree clean; package remains `0.1.0`; Evidence root has
  exactly 69 ordered unique exports, matching its released public API inventory.
- [ADR0039](0039_production_evidence_governance_and_governed_daily_technical_consumption.md)
  is byte-identical to its tagged Git blob. ADR0039 was the highest ADR number;
  this filename continues its numbered snake_case convention and AGENTS.md.

Source anchors, relative to the repository root:

- `src/market_platform/application/polygon_completed_daily_production_technical.py`:
  Slice 8 request, result, `_check_snapshot`, `_source_lineage`, `_resolve`,
  `_lock_inputs`, publication, and defensive history reads.
- `src/market_platform/application/polygon_completed_daily_production_bridge.py`:
  Slice 7 dataset identity, retained mapping, and historical `_resolve`.
- `src/market_platform/application/polygon_completed_daily_production_qualification.py`:
  complete historical `_snapshot`, retained qualification, and upstream locks.
- `src/market_platform/research/daily_technical_interpretation.py`:
  closed operands, comparisons, `classic_states`, and detached source checks.
- `src/market_platform/research/classic_daily_technical.py` and
  `src/market_platform/research/technical_policy.py`: released default identity.
- `src/market_platform/research/technical_analysis.py`,
  `src/market_platform/research/daily_evidence.py`, and
  `src/market_platform/_fingerprint.py`: snapshot, dataset, and canonical identity.
- `tests/unit/test_evidence_public_api.py` and
  `tests/unit/test_daily_technical_interpretation_assessment.py`: released
  inventory and legacy compatibility expectations; no new tests run or added.

## Scope and explicit non-goals

This is source-specific governed composition over released Polygon completed
daily Technical results. It adds descriptive Interpretation content and, in a
second slice, authentic execution/history. It is not a multi-provider or generic
Interpretation framework, policy registry, or caller-extensible execution engine.

No provider acquisition, Evidence construction or governance execution, bridge
conversion, or technical analyzer execution belongs to this operation. No
Assessment, Strategy, Agent capability, trading instruction, CLI, scheduling,
or autonomous authority is introduced. No new source Evidence is created.
Durable storage technology and retention duration are not selected here.

## Frozen v0.79 boundary and legacy incompatibility

Preserve ADR0039, all released Slice 1-8 identities, profiles, transformation,
history semantics, analyzer formulas, package version, and Evidence exports.
The new stage consumes Slice 8; it does not revise v0.79's historical stop point.

`DailyTechnicalInterpretation` and `interpret_daily_technical_research(...)`
require a genuine `IntegrityCheckedDailyTechnicalResearchResult`, including
`DailyInstrumentIntegrityEvidence` and its
`source_daily_instrument_integrity_evidence_fingerprint`. The governed path has
no such legacy occurrence. Do not fabricate a carrier, steal a construction
seal, make integrity optional, or cast/relabel a governed result into it.

Governance, qualification, bridge, dataset, snapshot, and technical-envelope
fingerprints identify different facts. None can replace the legacy integrity
fingerprint, even if structurally accepted as a SHA-256 string. Likewise,
authenticated source trading identity must not be called a legacy
`requested_trading_identity` or invented requested-research identity.

## Architecture decision

Freeze **common classic semantic core + distinct governed Interpretation
content/provenance + distinct execution envelope**.

Reuse the released scalar semantics, state enums, typed policy configuration,
and comparison value contracts. Introduce a new content type
`GovernedDailyTechnicalInterpretation` with schema
`governed_daily_technical_interpretation/v1`. It has no legacy integrity field.
Its construction proves semantic/value consistency, not execution authority.

The source-specific application owns authentication, execution chronology,
and publication of `PolygonCompletedDailyInterpretationResult`, schema
`polygon_completed_daily_interpretation_result/v1`. Neither a content factory
nor a self-consistent envelope establishes membership in trusted history.

## Exact source authority and reference contract

Freeze `PolygonCompletedDailyInterpretationRequest` as exactly these five facts,
also retained as the content's `source_technical_occurrence` value:

| Field | Exact meaning |
| --- | --- |
| `artifact_reference` | Detached exact `EvidenceArtifactReference`, including artifact ID, version, and fingerprint |
| `technical_history_namespace_id` | Original Slice 8 namespace; released `polygon_completed_daily_technical_history:<32 lowercase hex>` grammar |
| `technical_history_sequence` | Original positive exact integer sequence; booleans are invalid |
| `technical_execution_id` | Original `polygon_completed_daily_technical:<32 lowercase hex>` occurrence ID |
| `technical_fingerprint` | Original complete Slice 8 result/envelope fingerprint |

Validate and detach the request, including its nested reference. Match all five
facts conjunctively against exactly one retained occurrence, never a latest
result, approximate match, or snapshot-equivalence search. These are selectors;
authority comes solely from the trusted injected Slice 8 service and history.

Do not accept `PolygonCompletedDailyTechnicalResult`,
`TechnicalAnalysisSnapshot`, snapshot fingerprint alone, governed dataset
fingerprint alone, Interpretation object, policy, or configuration as bearer
authority. No caller execution time, analysis cutoff override, policy choice,
or configuration choice is present in this request.

## Trusted technical occurrence resolution

Under one complete lock acquisition chain, the future application must:

1. Validate complete Slice 8 history, including its namespace, contiguous
   sequence/counter, unique execution IDs, envelopes, and availability order.
2. Resolve exactly one retained result matching all request facts and require
   its `available_at <= execution_started_at` for this Interpretation.
3. Validate the exact retained result type, envelope, snapshot, research
   evidence, fixed released analysis/production profile, and occurrence identity.
4. Resolve its original bridge with the technical result's retained
   `source.bridge_reference` and **technical `execution_started_at`**. Reuse
   the released bounded internal technical `_resolve` behavior: it authenticates
   bridge prerequisites at the bridge's original execution time and retained
   qualification context, not at the new Interpretation time.
5. Reconstruct technical `_source_lineage` from that authentic bridge and require
   complete equality with the retained technical lineage. Derive the canonical
   instrument from the retained material's canonical mapping, check its subject
   correspondence, and require source trading identity to equal the mapped
   trading identity and retained research evidence instrument.
6. Capture detached complete source projections before semantic work; validate
   exact snapshot/evidence/profile and lineage correspondence after computation
   and again after fallible publication seams. Coherent refingerprinting does
   not excuse a difference from the authenticated pre-call source.

This is read-only provenance authentication. Structural validation of retained
objects is required; it does not execute the Evidence validation stage. Never
rerun provider acquisition, Evidence construction, validation issuance,
freshness evaluation, admission, validity, canonical lifecycle evaluation,
qualification, bridge conversion, or the technical analyzer. Historical checks
read the original records and context; modern requalification is not a repair.

## Governed content contract

All rows below are mandatory, exact retained facts or deterministic outputs.

| Field | Binding |
| --- | --- |
| `schema_version` | `governed_daily_technical_interpretation/v1` |
| `source_technical_occurrence` | Complete five-field reference above |
| `canonical_instrument_id` | Canonical ID from the authenticated governed mapping/subject |
| `source_trading_identity` | Exact typed `TradingInstrumentIdentity` from authenticated lineage |
| `analysis_as_of` | Retained research evidence/snapshot historical analysis time |
| `source_technical_analysis_snapshot_fingerprint` | Exact retained snapshot fingerprint |
| `source_governed_dataset_fingerprint` | Slice 7 `dataset_fingerprint`, retained in technical source lineage |
| `source_research_dataset_content_fingerprint` | `DailyResearchEvidence.dataset_content_fingerprint` |
| `interpretation_policy_identity` | Complete fixed `TechnicalPolicyIdentity`, including typed configuration and fingerprint |
| `source_quality` | Exact snapshot quality |
| `source_warnings` | Exact ordered snapshot warning tuple |
| `trend_direction`, `momentum_direction` | Released `DailyTechnicalDirectionalState` values |
| `volatility_state` | Released `VolatilityState` value |
| `extension_state` | Released `DailyTechnicalExtensionState` value |
| `comparison_evidence` | Complete ordered tuple of released `TechnicalComparisonEvidence` values |
| `fingerprint` | Deterministic governed content fingerprint |

The three data identities remain distinct: snapshot, governed dataset, and
research dataset content. The occurrence reference transitively binds the full
upstream governance chain; do not duplicate every upstream record in content.
Hashes alone do not make lost provenance resolvable. Content and envelope must
remain revalidatable against retained upstream facts within the retention boundary.

## Fixed classic policy binding

The governed path internally constructs and validates exactly the released
default; no caller-selected policy/configuration or runtime registration exists.

| Identity/configuration field | Frozen value |
| --- | --- |
| Identity schema | `technical_policy_identity/v1` |
| Policy kind | `daily_technical_interpretation` |
| Policy ID | `classic_daily_technical` |
| Behavioral revision | `1.0.0` |
| Configuration schema | `classic_daily_technical_interpretation_configuration/v1` |
| Configuration type | `ClassicDailyTechnicalInterpretationConfiguration` |
| `rsi_neutral` | `50.0` |
| `rsi_elevated` | `70.0` |
| `rsi_depressed` | `30.0` |
| `realized_volatility_low` | `0.15` |
| `realized_volatility_high` | `0.30` |
| `ema20_extension_band_percent` | `5.0` percent |

Expected identity fingerprint, verified by constructing
`ClassicDailyTechnicalInterpretationPolicy().identity` from released source:

`sha256:9d81e49a6d45d27071e804b46486ae247d71f650184e8032a792586807fc3d02`

Check the full identity and exact typed default values as well as this digest.
Retain the configuration within the complete policy identity, not as an
independently selectable duplicate. The legacy configurable API remains valid
and unchanged for alternative policies/configurations under its own contract.

## Narrow domain entry point and reused calculations

Freeze the function name `interpret_governed_daily_technical_snapshot(...)`,
following the released `interpret_daily_technical_research(...)` naming style.
It accepts an exact authenticated `TechnicalAnalysisSnapshot` semantic source
and detached provenance values needed by the content contract, supplied by the
application only after resolution. It accepts no policy or configuration input.
Slice 1 value-level callers cannot turn this function into execution authority.

The function validates/detaches the complete source and internally constructed
fixed policy before policy computation. Use `classic_states(...)` and
`build_classic_comparison_evidence(...)` on detached pre-call semantics; do not
invoke the legacy carrier-dependent `policy.interpret(...)` or duplicate its
formulas. Construct the new content, revalidate live and detached source/policy,
reject persistent drift, and validate complete result correspondence against
the pre-call projection, including every operand, boolean, state, and source fact.
Recomputing a fingerprint alone is insufficient correspondence validation.

The function contains no history resolution, provider access, Evidence governance
execution, technical analysis execution, Assessment, Strategy, or Agent authority.
Exact keyword grouping and private module decomposition remain implementation
details; the semantic/source and application-authority separation is frozen.

The released helper rules remain authoritative:

- Trend positive requires `EMA8 > EMA20`, `close > EMA144`, and `close > EMA169`;
  negative requires all three inverse inequalities. Otherwise it is mixed when
  inputs exist, unavailable when required EMA inputs are absent. A valid released
  snapshot requires `latest_close`; do not invent a nullable-close variant.
- Momentum positive requires MACD line above signal and RSI at least neutral;
  negative requires line below signal and RSI below neutral. Otherwise mixed,
  or unavailable when a required operand is absent.
- Volatility is low below the low threshold, normal from low inclusive to high
  exclusive, high from high inclusive, and unavailable when missing.
- Extension is above/below only strictly outside the positive/negative band;
  equality is within the band, and a missing distance is unavailable.

Snapshot descriptive states are not Interpretation directional results.
ADR0030's closed operand grammar is incorporated unchanged: its ten snapshot
fields, six configuration fields, and sole derived
`negative_ema20_extension_band_percent = 0.0 - ema20_extension_band_percent`.
There is no arbitrary expression, field path, callback, or derivation language.

Freeze this complete comparison ID order, with exact operands/operators from
ADR0030's Classic comparison inventory and the released builder:

1. `trend_ema8_above_ema20`
2. `trend_ema8_below_ema20`
3. `trend_close_above_ema144`
4. `trend_close_below_ema144`
5. `trend_close_above_ema169`
6. `trend_close_below_ema169`
7. `momentum_macd_line_above_signal`
8. `momentum_macd_line_below_signal`
9. `momentum_rsi_at_or_above_neutral`
10. `momentum_rsi_below_neutral`
11. `rsi_at_or_above_elevated`
12. `rsi_at_or_below_depressed`
13. `volatility_below_low`
14. `volatility_at_or_above_low`
15. `volatility_below_high`
16. `volatility_at_or_above_high`
17. `extension_above_positive_band`
18. `extension_below_negative_band`

Retain both true and false comparisons with their complete operand source,
field, value, operator, and satisfied value. Omit only a comparison with an
unavailable required snapshot operand; preserve the remaining relative order.
An unavailable state does not remove otherwise available comparisons.

## Exact source quality and warnings

Copy quality and the complete ordered warnings exactly from the authenticated
snapshot. No addition, omission, sorting, reinterpretation, or quality promotion
is permitted. Released canonical warning order is
`insufficient_profile_history`, then `stale_evidence`, when present.

Warnings and DEGRADED quality are descriptive research facts. They grant or
deny no Evidence freshness, admission, validity, consumability, or trading
permission. Unavailable operands affect only the released states and comparison
omissions; they are not an invented governance refusal.

## Content fingerprint versus execution occurrence

The content fingerprint binds every content table field except `fingerprint`
itself. Use the released canonical SHA-256 compact JSON machinery, canonical
finite float representation for policy/comparison values, enum values, complete
typed identity projections, canonical timestamps, and order-preserving arrays
for warnings and comparisons. Do not serialize object identity, display-rounded
numbers, or omit false comparisons. Freeze a complete canonical payload in
Slice 1 before releasing its schema; Python serialization helper layout is not
part of this ADR.

Exclude Interpretation execution ID, Interpretation history namespace/sequence,
start, completion, and publication availability from content. The *source
technical* occurrence namespace/sequence/ID/fingerprint remain included: their
exclusion would erase provenance. Repeated deterministic Interpretation of the
same authenticated occurrence and fixed policy has identical content identity;
different technical occurrences remain distinct even for identical snapshots.
Never reuse legacy `daily_technical_interpretation/v1` as this schema.

The separate trusted envelope binds complete content (including its fingerprint),
its own schema, and the following fixed/occurrence fields:

| Field | Contract |
| --- | --- |
| `operation` | `production.polygon_completed_daily.daily_technical_interpretation.application` |
| `operation_version` | `1.0.0` |
| `executor` | `market_platform.application.polygon_completed_daily_production_interpretation/v1` |
| `execution_id` | Unique service-issued Interpretation occurrence ID |
| `history_namespace_id` | Trusted Interpretation history namespace |
| `history_sequence` | Positive contiguous sequence in that namespace |
| `execution_started_at` | Actual Interpretation start S |
| `execution_completed_at` | Actual Interpretation completion C |
| `available_at` | Final publication availability R |
| `fingerprint` | Canonical envelope digest over the complete payload except itself |

Freeze Interpretation ID prefixes `polygon_completed_daily_interpretation` and
`polygon_completed_daily_interpretation_history`, respectively, using the
released colon plus 32 lowercase hex grammar. Equal content fingerprints may
appear in multiple executions; occurrence IDs and envelope fingerprints differ.
Public construction or coherent envelope refingerprinting is never issuance.

## Temporal and replay contract

| Symbol | Meaning |
| --- | --- |
| A | Historical `analysis_as_of` |
| K | Original qualification `knowledge_as_of` |
| B | Original bridge `available_at` |
| T | Source technical result `available_at` |
| S | Interpretation `execution_started_at` |
| C | Interpretation `execution_completed_at` |
| R | Interpretation `available_at` |

Require `T <= S <= C <= R`, using the released canonical UTC timestamp rules.
Preserve existing upstream chronology without conflating A, K, B, T, or R.
The result may describe historical A but must not imply that Interpretation
existed at A, K, B, or T. History visibility uses `R <= knowledge_as_of`.
R cannot move backward relative to previously published Interpretation entries.

Historical replay uses retained historical facts and the original qualification,
bridge, and technical contexts. It never refetches modern source data, reruns
upstream governance, or substitutes a current, caller-selected, or otherwise
different policy/configuration. A new Interpretation execution at S applies
exactly the frozen `classic_daily_technical` / `1.0.0` default policy semantics
to the authenticated historical `TechnicalAnalysisSnapshot` and receives its own
S, C, and R.
Later governance changes do not rewrite a prior occurrence. This read-only
historical interpretation creates no current Evidence freshness or lifecycle
permission. A new execution describing old A still receives new S, C, and R.

## Trusted history, alias isolation, and atomic publication

Follow the released Slice 8 alias-isolation rule beyond `frozen=True`:

- The authoritative retained result graph is never directly exposed. Detach
  requests, semantic sources, policy configuration, content, and nested values.
- Staged, authoritative retained, and returned public result graphs are distinct.
  History reads return validated defensive copies, including nested content.
- Public mutation, including coherent `object.__setattr__` plus refingerprinting,
  cannot alter history or establish authority. Check complete correspondence,
  not only digests, across fallible semantic/copy/publication seams.
- Sample final R at the publication boundary, set the final envelope identity,
  validate chronology and all copied facts, and prepare/validate the public copy
  before atomically appending authoritative state and advancing the sequence.
- Reauthenticate source lineage and unchanged history immediately before append.
  Any copy, validation, staging, clock, or correspondence failure publishes
  nothing, consumes no history sequence, and clears pending state.

Validate history completeness before selection and reads; retain unique IDs,
namespace identity, contiguous sequence/counter, and monotone availability.
Revalidate selected content/envelopes against authenticated upstream provenance
on history reads. Missing technical, bridge, qualification, governance, mapping,
or material support requires refusal, not a hash-only replay or legacy fallback.
Complete in-memory retention is acceptable; loss/restart cannot claim durable
replay, and a replacement store must not masquerade as the old namespace.

## Lock ordering

Freeze the exact order:

`construction -> validation -> freshness -> admission -> validity -> qualification
-> bridge -> technical -> governed interpretation`

The application composes the released technical `_lock_inputs` chain once and
then acquires its own history lock. Resolve, execute semantics, recheck, and
publish under that coherent chain. History reads use the same order. Never call
public upstream history APIs that reacquire non-reentrant locks from inside it.
Use bounded internal resolution with explicit original contexts, no recursive
public execution, provider callback, or lock-order inversion. This additive
composition must not change released lock semantics.

## Refusal and downstream stop boundaries

Fail closed with stable machine-readable categories distinguishing invalid
reference input, technical occurrence unavailable/not yet available, incomplete
or corrupt history, source/profile/lineage mismatch, fixed policy mismatch or
drift, persistent source mutation, semantic correspondence/computation failure,
temporal failure, and publication/copy failure. Exact exception class and enum
layout remain implementation choices. Preserve upstream cause/context rather
than parsing message text or translating an unknown failure into success.

Every refusal yields no published Interpretation occurrence; no automatic
acquisition, governance rerun, analyzer rerun, legacy adaptation, or repair is
allowed. A semantically valid unavailable state is distinct from a failed
authority/correspondence check.

Stop after governed Interpretation. Do not execute or modify
`DailyTechnicalAssessment`, adapt the content into its legacy runner, execute
Strategy, expose Agent authority, or produce trading instructions. Retained
states/comparisons can support a future governed Assessment design, but that
boundary requires separate authorization. Neither slice includes Assessment.

## Compatibility

ADR0030's legacy models, required integrity facts, configurable policy API,
fingerprint families, runners, and Assessment compatibility stay unchanged.
Reuse the existing semantic helpers directly; no pre-splitting or unrelated
refactoring is required. ADR0027 analyzer semantics and ADR0039 governance remain
unchanged. No Evidence root export or package-version change is authorized.

## Implementation slicing and future testing requirements

### Slice 1: Governed Daily Technical Interpretation Contract/Foundation

Implement only reference/value/content contracts, fixed policy binding, the
narrow domain semantic entry point, and deterministic content fingerprint.
Add semantic/provenance/mutation tests. No trusted execution envelope issuance,
history publication, provider/governance execution, or Assessment belongs here.

Required future coverage:

- Exact reference types/facts and provenance/data-identity correspondence;
  no legacy integrity fingerprint substitution or invented requested identity.
- Fixed default identity, exact fingerprint and configuration; refusal of caller
  policy/configuration selection and policy/source persistent mutation even with
  coherent refingerprinting, including nested/detached source mutation.
- Equivalence with both released helpers; all 18 comparisons and exact order,
  complete operands/operators, true/false retention, omission rules, equality
  thresholds, and mixed/unavailable cases without descriptive-state substitution.
- Exact source warning tuple/order and quality, including DEGRADED preservation.
- Deterministic canonical content identity; sensitivity to every bound fact,
  distinct technical occurrences with equal snapshots, and independence from
  Interpretation execution metadata. Legacy fingerprint schema separation.
- No technical Analysis, Assessment, Strategy, provider, or governance execution
  from the semantic entry point; value-level construction grants no authority.

### Slice 2: Trusted Governed Interpretation Execution + History

Implement authentic Slice 8 resolution, full upstream lock composition, fixed
semantic execution, occurrence envelope, trusted history, final availability,
and defensive public copies. Add replay/history-loss/refusal tests.

Required future coverage:

- Positive retained full-chain authentication and mismatch of each of the five
  selectors independently; zero/multiple matches and unavailable source refusal.
- No bearer snapshot/result/content authority, including copied/fabricated or
  coherently mutated/refingerprinted objects; original execution-context resolution
  and full reconstructed lineage equality before and after semantic execution.
- Complete history checks, missing/truncated/corrupt/replaced histories and
  namespace loss, upstream retention loss, and honest restart/replay refusal.
- `T <= S <= C <= R`, equal-time boundaries, backward clocks, history cutoff at R,
  historical A distinct from actual execution, and retained historical contexts
  despite later governance records. No modern refetch or lifecycle reevaluation.
- Repeated equal-content executions with distinct occurrence/envelope identities.
- Atomic publication, failures at each staging/copy/validation seam, pending
  cleanup, no sequence advance on refusal, and final provenance reauthentication.
- Public alias isolation for returned results and history reads at every nested
  mutable seam; staged/public graphs cannot mutate authoritative retained graphs.
- Lock order, concurrent execution/read consistency, no upstream non-reentrant
  reacquisition, and no provider/governance/bridge/analyzer re-execution.
- No Assessment, Strategy, Agent exposure, or trading instruction execution.

Prefer mocked provider/HTTP boundaries and controlled clocks. Implementation
work must run applicable tests and repository `pytest`, `ruff`, and `mypy`
checks before any separately authorized commit. This ADR task adds no feature
tests, executes no full pytest suite or unnecessary mypy, and uses documentation
and diff review only, plus read-only baseline/identity verification.

## Consequences, limitations, and remaining choices

The design reuses proven semantics without inventing legacy provenance. Content
is deterministic yet bound to an exact source occurrence; repeated execution
has a separately auditable chronology. Authority still depends on trusted
retention, complete upstream resolution, and defensive graph isolation, not
Python immutability or fingerprints alone. Holding the upstream chain through
semantic execution/publication limits concurrency in this bounded composition.

Frozen by this proposal are scope, authority selectors, named schemas and domain
entry point, content fields, fixed policy, semantic core and inventory, identity
boundaries, operation/executor identity, chronology, history/mutation/lock rules,
refusal distinctions, downstream stop, and two implementation slices.

Private Python decomposition, exact keyword grouping, copy-helper mechanics,
exception/enum layout, and clock wiring remain implementation details within
these constraints. Slice 1 must materialize and test the complete canonical
payload before its schema ships; none of those details permits changing a bound
fact or accepting caller-selected policy. Durable storage/lifetime and governed
Assessment remain optional later designs requiring separate authorization.

No architectural blocker was found in the inspected released source. Approval
of this proposed ADR and separate implementation authorization remain required
before either implementation slice begins. This draft itself implements nothing.
