# ADR 0052: Governed Research Escalation Readiness Boundary

## Status

Proposed for v0.85 Governed Research Escalation; draft for independent review.

This ADR freezes the proposed **NON-ACTIVATING GOVERNED ESCALATION READINESS**
boundary. The decisions below specify the minimum future implementation; this
document implements nothing and authorizes neither research nor production
activation. ADR0050, ADR0051 and released artifacts remain unchanged.

## Context and inspected baseline

Local verification before drafting established:

- Branch: `main`; HEAD, `main` and local `origin/main`:
  `b68c74c3e63bf1d395ed62d7846e6d39f5c77c99`.
- v0.84.0 release merge and peeled tag target:
  `1088b274131c71b7545ffa22eea9fbce3cb12d9e`.
- v0.84.0 annotated tag object:
  `17ae5273e1851d641dc58a44a6a5ec8d0114d173`.
- Clean worktree/index and no untracked repository files. Remote-tracking refs
  were inspected locally; no fetch or network request was performed.
- ADR0051 was the highest existing ADR number; 0052 was available.
- Draft branch: `feature/v0.85.0-governed-research-escalation`, created from the
  exact main baseline above.

The completed read-only reconnaissance selects governed escalation readiness as
the next boundary. It answers only:

> Does this authentic Pending Candidate currently have the exact governed
> material and governance state required to be considered ready for a bounded
> technical-research operation?

The minimum flow is:

```text
Radar observation -> meaningful change -> passive Candidate
-> recoverable Pending delivery -> authenticated governed-material correspondence
-> current escalation-readiness assessment -> STOP
```

### Existing contracts

| Inspected source | Contract retained by this decision |
| --- | --- |
| [ADR0050](0050_radar_candidate_and_escalation_boundary.md) | Candidate binds accepted observation and eligibility policy; its fingerprint is not bearer authority or Evidence. |
| [ADR0051](0051_radar_candidate_delivery_and_recovery_boundary.md), [delivery coordinator](../../src/market_platform/application/radar_candidate_delivery.py) and [delivery store](../../src/market_platform/application/radar_candidate_delivery_store.py) | Prepared, Accepted, Decision and Pending are distinct retained records. Individual reads do not alone prove the complete delivery graph; owned link validation and retained source correspondence remain necessary. |
| [Radar current content](../../src/market_platform/radar/current_content.py) and [Evidence ingress](../../src/market_platform/evidence_ingress/polygon_completed_daily_ohlcv.py) | Radar retains an exact 250-session observation scope. Evidence ingress excludes the New York query civil date and requires query time no later than response receipt. |
| [Canonical Evidence evaluation](../../src/market_platform/evidence/evaluation.py) and [production Qualification](../../src/market_platform/application/polygon_completed_daily_production_qualification.py) | Consumability uses authenticated validation, freshness, admission and validity histories with separate knowledge/effective cutoffs. Qualification also establishes exact task freshness, approved use and whole-material mapping coverage. |
| [Production Bridge](../../src/market_platform/application/polygon_completed_daily_production_bridge.py) and [DailyResearchEvidence](../../src/market_platform/research/daily_evidence.py) | Bridge authenticates retained Qualification and proves transformation, row correspondence and no-drop representation. Its dataset fingerprint differs from normalized historical-series content identity. |
| [Production Technical](../../src/market_platform/application/polygon_completed_daily_production_technical.py) | The eventual target resolves an authentic retained Bridge before running the analyzer. Its invocation is outside this release. |

## Decision 1: Trusted Pending boundary

An assessment MUST resolve authentic retained Pending work through its trusted
delivery owner and the complete graph:

```text
Prepared -> Accepted -> Decision (ELIGIBLE) -> Pending
```

Require exact source recovery identity, accepted publication, retained eligibility
policy, decision and Candidate correspondence. Validate existing records and
their links, not merely individual JSON shapes or matching hashes. Malformed,
orphaned, contradictory or mismatched graphs cannot yield readiness. Preserve
ADR0051's trusted-root, exclusive-owner and no-bypass assumptions; no new
cryptographic attestation or malicious-filesystem guarantee is claimed.

Use Pending/Candidate and source recovery references to resolve existing owned
records. A detached Candidate, copied application value or Candidate JSON is not
authority. Do not create a new Candidate schema, duplicate its identity/provenance
in a parallel lifecycle, regenerate its transition, or infer it from the latest
Radar checkpoint. Readiness does not write or consume Pending work, complete
unfinished delivery publication, or create a recovery root.

## Decision 2: Exact independently governed material

The first closed policy MUST require all of:

1. The same canonical instrument, with authenticated mapping coverage.
2. The exact complete Candidate observation window under its retained scope.
3. Exactly 250 completed exchange sessions, with the triggering completed session
   included and the complete ordered session set corresponding to the Candidate
   scope. Equal row count or matching endpoints alone are insufficient.
4. Matching normalized historical-series content identity under the existing
   normalization semantics.
5. Authentic EvidenceArtifact/material and acquisition provenance, approved
   transformation, and retained Bridge correspondence with no dropped rows.
6. Current governance qualification, lifecycle consumability and task freshness
   for the exact intended technical use, analysis context and profile.

Resolve the explicitly referenced material through its trusted owners. Candidate
content identity is a correspondence check, not authenticated storage or
governance proof. No Candidate-to-DataFrame shortcut is permitted. A larger,
smaller, rolling or partially overlapping governed window is not this policy's
positive path; do not slice, pad or silently substitute it.

Independent governed acquisition may establish matching content without being
the Radar acquisition. Equality of normalized data does not prove that records
came from the same HTTP response. Retain the actual acquisition provenance and
make no same-response claim without separately authenticated evidence. This
policy establishes exact material correspondence, not acquisition identity.

## Decision 3: Preserve fingerprint meanings

| Identity | Meaning and permitted use |
| --- | --- |
| Radar normalized content identity / `DailyResearchEvidence.dataset_content_fingerprint` | Existing normalized historical-series content meaning; compare these only after instrument, scope and normalization correspondence are established. |
| Bridge `dataset_fingerprint` | Governed representation identity binding canonical subject, transformation, provider/session/adjustment semantics and ordered binary64 rows. It is not the normalized historical-series fingerprint. |
| Source/acquisition provenance | Authenticated request, receipt and retained construction/material lineage. Content equality does not establish this lineage. |

Retain each existing identity for its own purpose. Do not compare unrelated
fingerprints as if their semantics were identical, or add a duplicate normalized
content fingerprint. Use existing canonical identity conventions for new policy
identity; no new hashing or attestation system is needed.

## Decision 4: Reuse governance and its owners

Reuse EvidenceArtifact identity, EvidenceValidationRecord,
EvidenceAdmissionRecord, EvidenceValidityEvent/state,
EvidenceFreshnessEvaluationRecord, canonical evidence consumability evaluation,
production Qualification, task-time freshness, mapping coverage, Bridge
correspondence and the existing technical profile identity.

Validation remains distinct from Admission; Admission remains distinct from
readiness; readiness remains distinct from research activation. No second
consumability engine or duplicate Admission, Freshness or Validity semantics is
allowed. Delegate governance decisions to existing owners and retain their
references/findings rather than reimplementing them as readiness booleans.

An authentic historical Qualification or Bridge proves its recorded context,
not current qualification. Assess current conditions for the requested task
using existing governance evaluation. Existing Qualification/task-freshness
operations may evaluate already retained material under their owned contracts;
this is not acquisition or data refresh and does not repair missing governance.
Their actual execution/availability times must be retained. Missing Validation,
Admission, Validity or source histories cannot be synthesized by readiness.

The retained Bridge must authenticate its original Qualification and exact
material/analysis/profile correspondence. Current assessment must also establish
current consumability and task freshness for that same intended context. A stale
Bridge snapshot cannot replace those checks, and a different analysis context
cannot silently reuse an incompatible Bridge.

## Decision 5: Separate times and availability

| Time | Required interpretation |
| --- | --- |
| Candidate observation time | Original Radar `as_of`, `observed_at` and completed-session context; preserve them unchanged. They are not provider receipt or Evidence availability. |
| Source query/response timing | Actual acquisition query cutoff and response receipt; retain ingress constraints and original provenance. |
| Analysis/effective time | Intended task's analysis cutoff and governance effective-state evaluation; not automatically Radar `as_of`. |
| Knowledge time | Cutoff for records actually available to the assessment; no future knowledge or hindsight. |
| Readiness execution time | Actual assessment start/completion and the recorded governance-check context; not source availability. |
| Task-freshness evaluation time | Exact task evaluation cutoff, plus the freshness operation's execution and availability times; not interchangeable with assessment time. |

Use existing aware-UTC conventions and temporal validation. Required records must
be available by the applicable knowledge cutoff and assessment execution; current
readiness cannot be asserted by selecting an earlier favorable governance
snapshot. Historical contexts remain historical. Preserve separate effective,
recorded and available times from owned histories, including current lifecycle
changes relevant to the requested use.

A later readiness time MUST NOT rewrite historical source availability, backdate
Evidence governance, alter query/receipt timestamps or turn a formerly positive
assessment into current authorization. Do not stamp every stage with Radar time.

## Decision 6: Same-response post-close limitation

Radar may include the just-completed current exchange session immediately after
actual exchange close, including early closes. Existing Evidence ingress excludes
rows on the New York query civil date and requires `query_as_of` no later than
response receipt. The same source response may therefore not be legitimately
governable with that triggering session included.

For v0.85, unsupported exact-source/timing correspondence MUST produce a bounded
BLOCKED or REFUSED result. Explicitly forbidden workarounds are:

- Backdating governance.
- Altering source query or receipt time.
- Silently dropping the triggering row.
- Researching only the preceding 249 rows.
- Refetching later data and claiming it is the triggering observation.
- Treating passage of time as proof that originally missing source material
  became valid.

Supporting same-response post-close escalation requires a separate future
architecture decision. This ADR does not change ingress, solve raw-response
reuse, or require every authentic Pending Candidate to become ready.

## Decision 7: Closed identity-bearing readiness policy and result

Define one closed policy for exact governed 250-session technical readiness:

- `policy_id`: `exact_governed_250_session_technical_readiness`.
- `behavioral_revision`: `"1"`, using the repository's string revision convention.
- Schema: `radar_research_escalation_readiness_policy/v1`.
- Fingerprint: existing canonical fingerprint of that schema-bearing identity.

This identity is separate from Candidate eligibility, Radar Profile and the
existing technical profile. Exact type names are implementation details;
supported behavior is Decisions 1-6. Unsupported identities fail closed without
default fallback. Behavior changes require an explicit policy revision and
architecture decision. No caller callbacks, scoring knobs or generic
authorization framework belong here.

The application result MUST express these bounded outcomes:

| Outcome | Meaning |
| --- | --- |
| `READY` | Every required trust, correspondence, timing and current governance prerequisite held for the recorded context. |
| `BLOCKED` | A required owned source/material/history or current prerequisite is unavailable or unsatisfied, such as missing material, inactive/invalid lifecycle state or stale task evidence. No repair, wait or retry is scheduled. |
| `REFUSED` | The request, policy, graph, provenance, correspondence or timing is malformed, contradictory or unsupported. |

Authenticate and validate correspondence before reporting READY. If a graph or
authority invariant is contradicted, report REFUSED rather than disguising it as
ordinary missing work. Known absence/loss of an owner blocks readiness; corrupt
purported authority is refused. Unsupported post-close timing is refused; missing
admissible material is blocked. Preserve bounded reasons and canonical governance
findings; operational failure can never become READY. Implementation may preserve
existing typed errors while exposing their bounded failure category.

Record enough explicit context to explain:

- Pending/Candidate fingerprint, source recovery reference and the authenticated
  delivery graph evaluated; distinguish supplied from authenticated references
  when resolution fails.
- Exact EvidenceArtifact, construction/material lineage, governance/history,
  Qualification, task-freshness and Bridge references actually evaluated.
- Applied readiness policy and intended consumer/use, task/analysis context and
  existing technical profile identity.
- Original source times and relevant effective, knowledge and availability
  cutoffs through retained references; actual readiness execution times.
- Outcome, bounded reasons, checked prerequisites and unavailable/unperformed
  checks. An early failure must not imply later checks passed.

Use references where existing owners already retain canonical provenance; do not
copy whole histories or Candidate fields into a second lifecycle. Name the result
an assessment, not an Authorization. READY is neither research authorization nor
an execution permit, durable bearer token, Strategy, broker or execution authority.
It states only that checked prerequisites held for that recorded context.

## Decision 8: No acquisition, refresh or repair

The readiness service MUST NOT call a provider, invoke Construction as an
acquisition shortcut, invoke legacy research workflows that fetch data, repair
missing Evidence, substitute a newer artifact or regenerate Candidate
transitions. It may use only already available, independently authenticated
governed material. Missing material fails closed.

References to construction receipts/history are reads of existing authority, not
permission to execute Construction. Current task-freshness evaluation is not
permission to refresh source data. No provider or downstream research executor
is required as a readiness-service dependency.

## Decision 9: Recovery and result retention

After restart, proceed only if trusted owners can authenticate the retained
Pending graph, corresponding governed material/history, current lifecycle state,
current task freshness and current policy identity. Candidate JSON alone cannot
restore lost governance authority. Recreating an empty service root does not
restore its old authentic occurrences; do not reacquire data to repair authority.

Repeated assessments may differ because time, freshness, validity or available
owned histories changed. A prior positive result is never a cache of current
permission. No research-execution idempotency mechanism is required because no
research execution occurs.

The minimum v0.85 deliverable is an application result. ADR inspection establishes
no semantic need for a durable readiness-assessment store. Its references support
explanation only while the caller retains the result and the referenced trusted
owners retain their histories; neither cross-restart result recovery nor complete
audit retention is guaranteed. Do not add a readiness queue, claim, lease,
acknowledgment, worker, retry journal, dispatch journal or execution journal.
Existing Pending persistence is reused, not extended into an execution lifecycle.

## Decision 10: Production non-activation and future invocation

Direct application-level readiness assessment may exist as a callable capability
once implemented. Production remains non-activating:

- No Candidate production from single-symbol Radar or batch Radar.
- No automatic Pending writes or recovery-root creation.
- No automatic readiness invocation from Radar.
- No Technical research, Interpretation, Assessment or Strategy invocation.
- No scenario/action-plan generation, ranking or portfolio action.
- No broker or execution authority.

Radar remains unaware of research decisions. The eventual technical target is
the existing governed Polygon-completed-daily Technical application path over an
authentic retained Bridge. v0.85 MUST NOT invoke that service or its analyzer:

```text
Readiness != Technical invocation
```

Future actual activation must revalidate current Pending trust, material,
governance, task freshness, policy and timing at its own invocation boundary,
rather than trust a portable historical readiness result. Invocation authority,
delivery acknowledgment and execution/retry semantics require separate future
work. This ADR grants none of them.

## Decision 11: Minimum implementation shape and authentic positive path

Begin with one focused application module, likely
`src/market_platform/application/radar_research_escalation.py`, containing small
request/policy/result types and an owned readiness assessment service. Inject
trusted owners and execution timing as needed. Keep boundaries narrow and types
together until a concrete responsibility warrants separation.

Reuse existing store reads and graph validation. Add a minimal trusted
Pending-resolution seam only if existing APIs cannot safely express that read;
do not expose a general JSON-to-authority importer or redesign delivery storage.
Reuse Qualification, Bridge and governance identities and owned checks. No new
durable queue or execution store is justified.

The future implementation MUST demonstrate at least one authentic READY path.
For example, a retained Pending observation whose full 250-session window ends
before the governed acquisition's New York query date can correspond to already
available governed material including that trigger session. Authentic owned
Validation, Admission, ACTIVE Validity, exact task freshness, current
Qualification and retained Bridge must all satisfy the intended analysis and
knowledge context. Actual acquisition/governance availability must precede the
applicable checks; no timestamps or authorities are fabricated.

The fixture/setup may establish these prerequisites through existing trusted
owners before assessment. The assessment itself acquires nothing and invokes no
research. Separate acquisitions retain their separate provenance even where
normalized content matches. The positive path must use authentic owned histories
and material, not mocked-away authority. A release where every assessment is
blocked/refused is insufficient; solving the post-close same-response case is
not required to obtain a legitimate positive path.

## Decision 12: Future supervision compatibility

Preserve sufficient references and times for a future ex-ante process auditor to
reconstruct source identity, Candidate/Pending identity, policy identity,
governance evidence, knowledge/effective/availability times and readiness
findings, subject to Decision 9's retention limits. Future supervision evaluates
decision-time process quality without hindsight optimization. No supervisor
structures, audit engine or additional persistence are implemented or required.

## Alternatives rejected and over-complexity exclusions

| Alternative | Rejection reason |
| --- | --- |
| Detached Candidate or Candidate-to-DataFrame shortcut | Bypasses authentic Pending and independently governed material. |
| Duplicate Admission/Freshness/Validity or a second consumability engine | Conflicts with existing governance ownership and temporal semantics. |
| Generic escalation authority framework or portable bearer authorization token | A context-bound readiness finding enforces no actual invocation authority. |
| New scheduler/worker, durable readiness queue or research execution journal | No dispatch or execution occurs in v0.85. |
| Supervisor scaffolding or broker abstractions | No present readiness responsibility. |
| Additional architecture layers without a current semantic responsibility | Obscures the small application boundary and duplicates existing owners. |
| O1 historical inventory/unresolved scanning optimization in `radar_candidate_delivery_store.py` | OPTIONAL / DEFERRED; not necessary to specify or implement readiness. |

## Consequences and tradeoffs

Readiness is useful but deliberately conditional: it explains a particular
Pending/material/task correspondence without starting research. Missing owned
history, expired freshness or unsupported timing prevents READY even when a
Candidate is authentic. The strict full-window policy can refuse material that
would support a different research task; that is not permission to weaken it.

Reusing trusted governance limits new machinery and keeps positive-path authority
real. It also preserves existing service-root retention limits and requires
careful context matching. No new durable readiness store solves lost source
authority. A later invocation boundary still bears the responsibility for current
revalidation and actual execution semantics.

## Future implementation test obligations

Use focused application and boundary tests with controlled clocks, local retained
histories and mocked external HTTP boundaries. Do not mock away governance-owner
authentication in the positive path. Cover:

- Authentic Pending resolution and malformed/orphaned/mismatched delivery graphs.
- Exact 250-session correspondence and triggering-session inclusion; wrong
  canonical instrument, window or normalized content.
- Missing/lost governance owner; inactive, invalid or stale governed material;
  mapping mismatch and authentic but historical-only qualification.
- Timing mismatch and unsupported same-day post-close correspondence, without
  dropping rows or altering query/receipt/governance times.
- An authentic READY path using owned histories and matching retained Bridge.
- No provider, Construction, Technical/analyzer, Strategy or downstream call.
- Repeated assessments under changed task time, freshness, validity or retained
  history; an old READY result does not control the new outcome.
- Unchanged production single-symbol and batch non-activation, including no
  automatic Candidate/Pending, recovery-root or readiness activity.

These are future implementation obligations only. No tests, Ruff, mypy or full
suite are run for this ADR-only draft; a full-suite run is not justified merely
by this document.

## Non-goals

- Implementing code/tests, a handoff, production activation or version changes.
- Technical research execution, Interpretation, Assessment or Strategy
  re-evaluation.
- Scenario planning, entry/target/stop generation, ranking, portfolio context,
  broker/execution or a supervisory agent.
- Same-response post-close support, source acquisition/refresh or repair of
  missing Evidence/governance authority.
- Generic authorization, new Candidate schemas, parallel Candidate lifecycles,
  durable readiness/execution infrastructure or execution idempotency.
- O1 optimization or changes to released ADRs and contracts.
