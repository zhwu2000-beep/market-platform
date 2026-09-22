# ADR 0045: Historical Price Storage Continuity for Governed Authentication

## Status

Accepted

This is the narrow Decision B follow-up for v0.82.0 Option C Blocker 1.
Acceptance and implementation require separate authorization. This drafting
step changes architecture documentation only; it authorizes no implementation,
test execution, staging, commit, push, merge, tag or release.

## Context and inspected baseline

- Branch: `feature/v0.82.0-governed-daily-technical-strategy`.
- HEAD and local remote-tracking feature ref:
  `b903292dd64a4272a03bf849e9dceedb75aed73a`.
- Frozen local `main` and `origin/main`:
  `a94a1b49ad9eea036dab3d543e239fb82fb438e1`.
- ADR0043 and ADR0044 are Accepted and remain unchanged.
- The index is clean. Exactly six files were modified and unstaged before this
  draft: the application Interpretation, Assessment and Strategy modules named
  `polygon_completed_daily_production_<layer>.py`, and their corresponding
  `tests/unit/test_polygon_completed_daily_production_<layer>.py` files.
  Their existing bytes are preserved.
- ADR0045 was unused. Local source/document inspection, not test execution,
  supports this decision. Remote refs were inspected locally, without fetching.

The complete original-support graph includes the original Bridge result,
its `CompletedDailyPriceSeries`, its retained `HistoricalPriceSeries`, and that
series' mutable pandas `_frame`. Committed Interpretation bytes, Technical
issuance bytes, original Evidence material, Bridge converted rows, dataset/proof
fingerprints and retained owner/state identities establish expected historical
content and lineage. They do not prove that the CURRENT attached frame still
has those rows, binary values, timestamps, strings, columns, index, dtypes and
storage attachment after all mutation-capable work.

`HistoricalPriceSeries.content_fingerprint` is lazy and cached. Its existing
fingerprint is not a fresh storage read. `CompletedDailyPriceSeries` validation
and projections reconstruct prices; Historical normalization sorts, converts
and resets the index. Bridge `_prove` checks original material correspondence,
approved storage and positive stored zero, but uses validation/projection paths.
Repeating these operations cannot itself supply the final callback-free barrier.

## Decision 1: One additional production boundary

For later authorized implementation, extend production scope ONLY to
`src/market_platform/data/historical.py`, for one narrow private storage-continuity
capability on behalf of `HistoricalPriceSeries`. Its two operations are:

1. Capture a lossless immutable expectation of the current original retained
   storage during trusted transaction preparation.
2. After all mutation-capable support work, compare the current live attached
   storage against that expectation using a bounded callback-free reader.

This is continuity evidence within the existing authentication transaction. It
is not market-data authority, a dataset fingerprint, a public API, a persisted
certificate, a cache of successful authentication, an immutable replacement for
the live series, semantic validation or historical reconstruction.

ADR0044 remains the authority for Interpretation integration, which may call
this primitive. This ADR grants no new production changes in
`research/daily_evidence.py`, Bridge, Qualification, Technical, Construction,
Validation, Freshness, Admission, Validity, Governance, Evidence, Assessment or
Strategy authority semantics, domain schemas, exports, CLI, Agent or trading.
It does not introduce a generic authentication or storage framework.

## Decision 2: Private preparation-time capture

The conceptual operation is `_capture_storage_continuity(...)`; names and
private packaging are not frozen. Capture reads the original live storage under
the existing held transaction locks, before later mutation-capable support
preparation. It may allocate bounded immutable data proportional to the retained
frame. It does not normalize, reconstruct, repair or fetch prices.

The expectation is private, immutable, data-only, non-exported, non-persisted,
non-serializable as authority and transaction-local in use. No public interface
accepts it. Copying, possession, equal bytes or a previous successful comparison
cannot authenticate another independent call, even if the series is unchanged.
There is no authority serialization/import path, persistent registry or success
cache. The ADR0044 trusted transaction lifetime must govern its use; this does
not decide the separate outstanding transaction-lifecycle implementation finding.

Capture must preserve at least:

| State | Immutable expectation |
| --- | --- |
| Series scalars | Exact built-in `_symbol`, `_provider`, and retained `_content_fingerprint` field, including `None` versus exact string; read the field without invoking its lazy property |
| Frame structure | Exact shape and all eight ordered `PRICE_COLUMNS`: `symbol`, `timestamp`, `open`, `high`, `low`, `close`, `volume`, `provider` |
| Axes | Exact axis classes and names, ordered column labels, exact `RangeIndex` start/stop/step and logical values; governed row index is `range(0, row_count, 1)` |
| Dtypes | Exact concrete dtype classes and parameters for each column and backing array, including numeric width/byte order, datetime unit/timezone and string storage/missing-value policy |
| Storage | Approved manager/block/array classes, column placements, dimensions, shapes, strides, offsets and attachment/layout information needed to safely reread all logical values |
| Stored manager routing | Separate absent/materialized status of `_blknos` and `_blklocs`; when present, exact concrete ndarray type, dtype, ndim, shape/length, element values, valid block/location bounds, manager attachment and correspondence to the captured block/placement layout |
| Complete content | Every row's symbol, timestamp, open, high, low, close, volume and provider, in exact retained logical order |

Capture reads the CURRENT STORED `BlockManager._blknos` and `_blklocs` fields
directly through the audited adapter. In the approved layout, ABSENT means the
stored field is `None` (unmaterialized); a missing required field is malformed,
not an alternative absence representation. MATERIALIZED means an explicitly
approved exact ndarray is attached. Record each field's status independently;
an inconsistent partial routing pair fails closed. Do not access lazy `blknos`
or `blklocs` properties or materialize missing arrays for capture. Present arrays
must already agree with the captured blocks and placements. Immutable routing
expectations remain data only; original array attachment anchors stay separately
inside the primitive under Decision 3.

Numerics use lossless IEEE-754 binary64 content, not decimal formatting, float
equality or canonical fingerprint conversion. Preserve signed zero: Bridge's
fingerprint helper equates zeros but `_prove` rejects negative stored zero.
The governed representation admits finite numbers only; NaN and infinity are
unsupported at capture and fail closed if observed at comparison. No NaN
equality or payload-canonicalization policy may silently authorize them.

Timestamps retain exact UTC nanosecond values and their unit/timezone
representation, without conversion through Python `datetime` or strings. NaT
is unsupported. Strings retain exact built-in Python `str` logical values;
no coercion, normalization, subclass equality or object-pointer byte comparison.
Missing strings are unsupported. Equal immutable expectation bytes need not be
the same byte object.

The captured content alone does not establish its original historical validity.
Existing original Evidence/material, Bridge conversion and Technical issuance
correspondence obligations must still succeed for that same retained support.
Capture cannot bless pre-existing corruption. Any necessary lazy-fingerprint
initialization must finish before capture; a later change from `None` to a
fingerprint is not an exception to continuity and cannot cause recapture.

## Decision 3: Current live attachment and final comparison

Final comparison starts from the CURRENT retained `HistoricalPriceSeries._frame`,
reached through the original Bridge and CompletedDaily attachments. Interpretation
checks those upstream original identities under ADR0044. The primitive checks
the exact original series, frame, axes and approved storage attachments, then
rereads complete current content. Reading a saved ndarray or view alone proves
nothing about what is currently attached.

Require detection of all of the following:

- The same frame object with mutated numeric, timestamp or string buffers.
- Replacement of the series attachment, frame, index, column axis, dtype,
  manager, column/block/extension array or its backing storage.
- Detachment of an earlier block/array/view from the current frame, even when
  the detached object still has the expected content.
- Changed column placement, shape, strides or approved storage layout, including
  equal logical values with an unauthorized layout/attachment change. Logical
  equality cannot hide replacement or a breach of Bridge's storage invariants.
- Unchanged cached fingerprint alongside changed rows, or coherent replacement
  of both live content and the fingerprint field.
- Routing-only mutation, replacement or absent/materialized transition in
  `_blknos` or `_blklocs`, even with unchanged axes, blocks, placements, price
  buffers, cached fingerprint and owner/state identities.

After ALL mutation-capable support work, reread the CURRENT STORED `_blknos`
and `_blklocs` on the current retained manager. The first version requires
ABSENT to remain ABSENT and MATERIALIZED to remain MATERIALIZED for each field.
Both absent-to-materialized and materialized-to-absent transitions are continuity
drift, including materialization during S1. No materialization exception is
authorized. Do not silently rebuild arrays to compare them.

For present routing arrays, require the approved exact ndarray representation,
unchanged dtype, ndim, shape/length and complete values, and the original array
attachments to the CURRENT retained manager. Check all block numbers and
within-block locations against valid bounds before following any route. A saved
routing array or view cannot prove what is currently attached.

Block placement and live manager routing are independent continuity obligations
and must agree. For materialized routing, at EVERY logical column position `i`,
stored `_blknos[i]` must identify the expected retained block, and stored
`_blklocs[i]` must identify the
expected location within that block. Together they must match the CURRENT
approved `BlockPlacement`/column layout and exactly the storage location in the
captured expectation, with complete column coverage. Neither placements nor
routing alone prove the other. When both arrays remain absent, validate the
approved block/placement layout without constructing routing arrays; do not
claim an absent array supplies a materialized route.

Prove the stored state pandas would CURRENTLY use to route columns, not what
routing ought to be. Do not derive correct routing from placements and accept
different live routing. Inconsistent routing is never repaired, normalized or
adopted, and lazy routing accessors are not part of the comparison.

Actual original object attachment must be provable, not inferred from dtype
spelling, an address or an integer `id` that could have been reused. Necessary
attachment anchors are held alive in private transaction-scoped implementation
state encapsulated in `historical.py`, separate from immutable expectation data.
No pandas private-internal object escapes the primitive. Only immutable data and
comparison success/failure cross its boundary; the private attachment machinery
grants no publisher, owner, lock or mutation authority. Do not persist it or expose
it as a transferable capability. Raw pointer identity is never price-content
authority; content must also be reread and compared in full.

The comparator checks approved exact classes before accessing each storage
layer, checks structure before reading values, and fails closed on malformed or
unsupported storage. It performs bounded reads and permitted immutable
allocation only; it never updates the expectation or establishes another
baseline. A changed live frame must never be recaptured and accepted.

This retains ADR0043's shared-lock/trusted-code model. It does not claim memory
safety against arbitrary native-memory corruption or protection against wholesale
replacement of trusted code/roots. It introduces no new lock or locking model.

## Decision 4: Explicit supported pandas storage contract

Choose the bounded first version: support only the reviewed local governed
production backends below, subject to an implementation audit of their exact
classes and layouts. Do not generically accept arbitrary pandas storage or
assume every dependency version allowed by `pyproject.toml` has the same layout.

The inspected environment evidence is pandas **3.0.3** and NumPy **2.5.0**,
also present in local installed distribution metadata and `uv.lock`.
`pyproject.toml` declares `pandas>=2.2.0` and `numpy>=2.0.0`, not those exact
runtime versions. No project source contract pins `mode.string_storage`.
Python-backed strings are possible locally; Arrow-backed strings are possible
in other environments. The installed pandas source chooses between them.

The initial allowlist and required read paths are:

| Retained representation | Reviewed bounded read path |
| --- | --- |
| Exact `HistoricalPriceSeries` and `pandas.DataFrame` | Read native stored fields and the attached manager, without subclass dispatch, public projection or lazy fingerprint access |
| Exact `pandas.core.internals.managers.BlockManager` | Read its stored axes/blocks, exact approved `BlockPlacement` representation and direct stored `_blknos`/`_blklocs` fields; independently check placements, routing and complete column coverage under Decisions 2-3 before following values; no lazy routing rebuild, consolidation or reindexing |
| Materialized manager routing arrays | Exact `numpy.ndarray` with audited native `np.intp` dtype and one-dimensional shape `(column_count,)`; check stored attachment, complete values, block/location bounds and agreement with placements; reject subclasses and unapproved backing/layout forms before dispatch |
| Numeric columns: exact `NumpyBlock`, exact `numpy.ndarray`, native `float64` | Validate ndarray dtype, dimensions, shape, strides, ownership/base attachment and column placement; read all logical elements as binary64 bytes via audited native ndarray operations, preserving sign bits |
| Timestamp: exact `DatetimeLikeBlock`, exact `pandas.core.arrays.datetimes.DatetimeArray`, exact `DatetimeTZDtype(unit="ns", tz=UTC)` | Read the audited stored dtype and exact attached NumPy `datetime64[ns]` backing array; compare nanosecond integer bits and separately the approved UTC timezone representation; do not invoke conversion or generic ExtensionArray methods |
| Symbol/provider: exact `ExtensionBlock`, exact `pandas.core.arrays.string_.StringArray`, exact `StringDtype(storage="python", na_value=pd.NA)` | Read the exact attached object-dtype ndarray through the audited native backing field; type-check each element as exact `str` before built-in string comparison; reject missing values and arbitrary objects |
| Row axis: exact `pandas.RangeIndex` | Read the stored exact built-in `range` and approved native name/dtype metadata; compare identity, start/stop/step and implied ordered values; no `equals` or materialization through generic Index dispatch |
| Column axis: exact `pandas.Index` with Python-backed string labels | Read its audited attached exact `StringArray`/object ndarray representation; allow the local inferred-string dtype's `na_value=np.nan` metadata only for this axis, with no missing labels; compare exact `str` labels in `PRICE_COLUMNS` order and preserve the captured axis dtype/layout |

Block class names above refer to `pandas.core.internals.blocks`; BlockPlacement
refers to `pandas._libs.internals.BlockPlacement`. Exact ndarray dtype classes,
base-chain shapes, timezone objects, axis backing, placement forms and routing
array backing/layout forms must be enumerated from the supported local
construction path during implementation
review, including the installed pandas' inferred column-label representation.
This is a finite adapter for those representations, not permission for recursive
traversal of arbitrary `.base`, manager, block or ExtensionArray graphs. Any
form not explicitly audited and regression-covered is unsupported.

ArrowStringArray/Arrow-backed strings, other ExtensionArrays, storage subclasses,
alternate managers and unapproved dtype/axis/backing layouts fail closed BEFORE
their behavior is invoked. The first version need not support Arrow. Widening
support requires an explicit reviewed concrete read path and regression evidence;
it is not implicit in pandas' ability to construct the frame. This may refuse
governed authentication in another otherwise usable pandas environment. Public
HistoricalPriceSeries construction and signatures remain unchanged.

There is no fallback through `to_numpy()`, `astype()`, generic object conversion,
string conversion or arbitrary ExtensionArray dispatch. Do not change global
pandas options or dependencies to conceal an unsupported retained backend.

## Decision 5: Bounded private-internal access and callback-free meaning

No unconditional public pandas interface identified by this review proves
potentially corrupted storage without possible extension/custom dispatch.
Private pandas-internal access is therefore permitted only when ALL apply:

1. It is encapsulated entirely in `historical.py`.
2. It is used only by this private continuity capability.
3. Exact pandas/storage classes are checked before internal access at each layer.
4. Unsupported representations fail closed before invoking their behavior.
5. Each path is version-audited against the repository-supported dependencies.
6. No pandas private-internal object escapes the primitive.
7. No raw pointer identity is treated as price-content authority.
8. Object-backed strings are compared as exact strings, never pointer bytes.
9. Extension and backing arrays receive only explicit approved handling.
10. Later tests demonstrate buffer mutation, frame replacement and storage
    replacement detection.

Private pandas coupling is bounded implementation debt, not a general
architecture precedent. Implementation review must inspect concrete native
accessors/operations, not assume that a leading underscore or exact outer frame
type makes downstream dispatch safe. Trusted native slots and audited built-in
or native operations over already-approved exact storage classes are allowed.
Validating or replaceable properties are not.

This authorization includes direct stored-field inspection of
`BlockManager._blknos` and `_blklocs` ONLY inside the private `historical.py`
continuity adapter, after checking the exact approved manager class. Routing
inspection uses direct stored attribute reads, exact built-in/type checks and
audited NumPy ndarray scalar/content reads. Unsupported routing arrays or
backing representations fail closed before their behavior is invoked. No
normalization, mutation, repair or private-object escape is permitted.

Neither capture nor final routing comparison may invoke pandas routing
properties that populate/rebuild state, column extraction, Series construction,
DataFrame `__getitem__`, manager `iget`/`iget_values` as proof, arbitrary
ExtensionArray dispatch or application callbacks. Read and check the stored
routing fields themselves; do not exercise column access to infer their validity.

Specifically, the FINAL live comparison must not invoke market-platform
validators, projections or `to_dict` paths; provider/source callbacks; arbitrary
user/application Python callbacks; arbitrary ExtensionArray behavior; object
`__deepcopy__`; `__eq__` on untrusted application/domain objects; descriptors or
properties that run validation; or semantic reconstruction. Reject untrusted
objects before comparison or diagnostic formatting could dispatch to them.

Allocation of immutable comparison bytes/scalars is permitted inside this
comparison if it introduces no untrusted dispatch. This does not permit
allocation after the final fresh-support boundary. No normalization, repair,
refetch, latest-data adoption, application validation or projection is part of
the comparator. Capture likewise uses the bounded approved storage reader;
subsequent mutation-capable validation belongs to the existing preparation seam.

Implementation must be reviewed against supported dependency versions and must
regression-test the exact supported backend assumptions. Upgrades affecting
pandas storage trigger review of this private adapter. The observed version
numbers are audit evidence, not permanent semantic requirements or authorization
to edit runtime dependency constraints. Unaudited layouts fail closed.

## Decision 6: ADR0044 final-support integration

Capture happens during original trusted transaction preparation, before later
mutation-capable support work. The following S1-S4 ordering makes ADR0044
Decision 4's fresh complete original-support phase provable; it does not replace
the preceding complete preparation and inventory-wide canonical recheck:

| Step | Required ordering and authority |
| --- | --- |
| S1 | Interpretation completes ALL mutation-capable support preparation, validation and projection across the complete inventory, including Technical/Bridge/material correspondence and retention work |
| S2 | Interpretation performs complete callback-free live continuity checks over lifecycle/native retained support fields and HistoricalPriceSeries via this primitive; the final current-frame comparison occurs here against the original expectation |
| S3 | Only after ALL S2 checks succeed is complete original support accepted as freshly revalidated; this is the boundary, not a further validator/projection or new authority object |
| S4 | Direct-only authority/root/state checks against original anchors, followed only by ADR0043/0044-permitted cleanup, preallocated state advancement and return |

No mutation-capable validator or projection may run after the final S2 live
checks. Finish S1 for all entries before starting S2; do not interleave per-entry
validation and sealing. Include unrelated, unselected and invisible entries;
empty downstream selection is no exemption. S2's approved bounded allocations
occur before S3; S4 retains the prior no-allocation/no-dispatch tail restrictions.
No post-S2 recapture, reconstruction, copying or fresh support baseline is allowed.

## Preserved authority invariants and failures

The decision preserves:

1. Original Bridge occurrence identity.
2. Original HistoricalPriceSeries attachment through CompletedDailyPriceSeries.
3. Original Evidence/material lineage.
4. Complete current price rows in original logical order.
5. Exact schema and column order.
6. Exact index.
7. Exact dtypes.
8. Exact timestamp semantics and UTC nanosecond representation.
9. Binary numeric continuity, including applicable signed-zero distinction.
10. Detection of current support corruption after mutation-capable work.
11. No recapture or adoption of mutated data.
12. No semantic reconstruction in continuity comparison.
13. No provider refetch.
14. No latest-data adoption.
15. No repair.
16. No cross-transaction reuse as authority.
17. The complete ADR0043/0044 lock transaction, unchanged eleven-lock order and
    no new locks or reacquisition.
18. Failure atomicity: no append, sequence consumption or partial commitment;
    preserve prior facts and original-owner pending cleanup, without promising
    rollback of external callback side effects.
19. No public API, schema or fingerprint change.

A live HistoricalPriceSeries continuity mismatch, lost/replaced attachment or
unsupported/corrupt retained storage, including routing continuity failure or
placement/routing disagreement, is original-support corruption. Route it
through the existing private failure chain: `_InterpretationHistoryInvalid`
to `_AssessmentHistoryInvalid` to `HISTORY_INVALID` /
`history_incomplete_or_corrupt`. Classify by structured category, not message.
Only a defect purely in detached lineage/selector correspondence remains
`SOURCE_MISMATCH` / `source_lineage_mismatch`; actual retained storage corruption
must not be disguised as detached correspondence drift. Add no public refusal
string and do not classify a lost committed source as a new selector miss.

Do not redefine `HistoricalPriceSeries.content_fingerprint` or any existing
Evidence, Bridge or Technical fingerprint. A private immutable expectation
representation is permitted; no new public/persisted fingerprint or storage
snapshot authority is created. Existing support-invalidity precedence remains
binding; repairing its outstanding implementation is outside this decision.

## Later implementation test obligations

These tests are required later, not executed for this draft:

1. Accept the exact normal governed numeric frame on every approved backend.
2. Detect numeric cell/buffer mutation on the same frame object.
3. Detect signed-zero mutation, including Bridge's positive volume zero.
4. Detect timestamp value mutation at nanosecond precision.
5. Detect timezone or timestamp-unit mutation.
6. Detect symbol/provider string mutation and series scalar drift.
7. Detect column-order mutation.
8. Detect column dtype mutation, including equal logical values.
9. Detect RangeIndex value/parameter mutation and equal-value index replacement.
10. Detect frame replacement, including equal-content replacement.
11. Detect column/block/backing-storage replacement or detachment, including
    equal-content replacement and unauthorized layout changes.
12. Prove a stale detached ndarray/view cannot authenticate the current frame.
13. Detect live mutation while the cached content fingerprint stays unchanged.
14. Prove coherent fingerprint-field replacement cannot hide live mutation.
15. Accept the approved Python string backend and its audited column-axis form.
16. Fail closed on unsupported string/extension backends and subclasses before
    dispatch; reject arbitrary object elements, NaN/infinity, NaT and missing
    strings. Exercise forbidden callback traps, including equality/deepcopy.
17. Prove no provider/refetch or semantic reconstruction occurs in the primitive.
18. Prove expectation reuse across workflows grants no authority, even with no
    intervening state change; copying/serializing data cannot bypass call lifetime.
19. Prove final comparison never repairs, adopts, refreshes the expectation or
    mutates authority on failure.
20. Exercise the real ADR0044 late-support mutation regression through the actual
    Interpretation final-support seam into this primitive; mutate earlier retained
    storage during later support work and require history-invalid failure before
    publication/history return. A comparator-only unit test is insufficient.
21. Preserve public HistoricalPriceSeries behavior/signatures and all existing
    public schemas, exports and fingerprint semantics.
22. Detect `_blknos` in-place value mutation with unchanged blocks, placements,
    price buffers and fingerprints.
23. Detect `_blklocs` in-place value mutation under the same conditions.
24. Detect `_blknos` array replacement, including equal-content replacement.
25. Detect `_blklocs` array replacement, including equal-content replacement.
26. Reject unsupported routing ndarray/backing types before dispatch, including
    subclasses; trap forbidden routing properties and column-extraction paths.
27. Reject absent-to-materialized routing transitions, including during S1.
28. Reject materialized-to-absent routing transitions.
29. Reject routing values outside valid block-number or within-block bounds.
30. Reject placement/routing disagreement by changing routing alone.
31. Detect a routing swap that changes pandas logical column routing while the
    underlying buffers remain untouched.
32. Prove a stale captured routing array/view cannot authenticate replacement
    routing attached to the current manager.
33. Inject routing-only corruption through the REAL ADR0044 late-support seam;
    require `_InterpretationHistoryInvalid` through the existing failure chain
    to `HISTORY_INVALID` / `history_incomplete_or_corrupt` before publication or
    history return. A comparator-only test is insufficient.

Routing regressions must isolate routing drift: retain unchanged axes, blocks,
block placements, price buffers, cached HistoricalPriceSeries fingerprint and
owner/state identities. Detection must not depend on changes to those objects
or values. The routing-swap fixture must establish differing logical routes;
the comparator must still use only the approved direct stored-field reader.
Cover unchanged approved absent and materialized routing states as successful
continuity cases, with no materialization or rebuilding by the primitive.

Review the supported-version/backend matrix and callback-free call paths as
part of these obligations. This ADR neither claims implementation correctness
nor changes the existing separately authorized performance release gates.

## Relation to prior ADRs and outstanding work

[ADR0043](0043_governed_daily_technical_strategy.md) remains authoritative for
Strategy transaction and final-seal semantics.
[ADR0044](0044_governed_daily_technical_strategy_interpretation_authentication_optimization.md)
remains authoritative for Interpretation preparation and final revalidation.
This decision extends their production scope restrictions only enough to add
the missing callback-free HistoricalPriceSeries live-storage continuity
primitive in `historical.py`. Neither prior ADR is rewritten.

These supplied Option C findings remain implementation work OUTSIDE this ADR's
decision; no solution or completion claim is made here:

- **BLOCKER 2:** Interpretation transaction ownership, lifecycle and non-reentrancy.
- **REQUIRED 1:** Support invalidity precedence over requested Assessment absence.
- **REQUIRED 2:** Real Technical-boundary multiplicity regression.
- **REQUIRED 3:** Complete executable Interpretation AST checkpoint.

Option D remains unauthorized: no Governance resolver memoization,
policy/reference optimization, fingerprint caching, authentication checkpoints,
persistent certificates or broader lifecycle redesign. The issue decided here
is live storage continuity only.

## Architecture consistency review

Reviewed against ADR0043 Decisions 3 and 10-14; ADR0044's private preparation,
complete final support, lifetime and failure contracts; HistoricalPriceSeries
normalization, cached fingerprint and projections; CompletedDailyPriceSeries
retention/reconstruction; Bridge `_prepare`, `_prove`, conversion and signed-zero
rules; and `PRICE_COLUMNS` construction. Inspected installed pandas source for
StringDtype backend selection, StringArray backing, RangeIndex storage and
BlockManager/block classes. No tests, static-check tools or performance runs
were used, and no backend execution matrix is claimed by this source review.

The explicit Python-backed first version avoids an unreviewed Arrow dispatch
path. Exact outer AND backing-type checks, immutable built-in comparisons and
bounded native access make the final comparison implementable without repeating
application validation. Version/backend regression evidence remains mandatory
before implementation acceptance. Private internals and attachment retention stay
inside historical.py; expectation data is insufficient authority without the
original ADR0044 transaction. Existing fingerprints and history-invalid routing
are preserved. S2 allocation is inside the fresh-support operation, so the
ADR0043/0044 direct-only tail is unchanged.

Findings for this Proposed architecture: **BLOCKER: 0; REQUIRED: 0; OPTIONAL: 0**.
This does not clear the outstanding implementation findings above or establish
that Option C is correct, accepted or release-ready. Blocker 1's missing scope
decision is drafted here; acceptance, implementation and verification remain
separate work.
