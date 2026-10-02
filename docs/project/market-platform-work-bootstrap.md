# Market Platform Work bootstrap

## Start here

This is the primary project entry document for ChatGPT Work. Work must not assume
access to Codex conversation history. Establish engineering facts from repository
state, ADRs, frozen implementation/tests, handoffs, test evidence and
commits/diffs/releases. Conversation memory is useful context, not the
authoritative system of record.

Read the [status ledger](market-platform-status-ledger.md),
[roadmap](market-platform-roadmap.md) and [boundaries](market-platform-boundaries.md),
then inspect the relevant delivered artifacts and evidence before proposing work.
At this bootstrap's checkpoint, v0.85.0 is **released/frozen**, runtime validation
is **COMPLETE**, and remaining runtime acceptance items are **none**. See the
[authoritative runtime closure](../test-evidence/v0.85-runtime-test-closure.md).
The next architecture phase is **MONITORING TOPOLOGY**, planned only.

The verified baseline is `main`, with HEAD/main/local origin/main at
`541cfa0b659947760279ec77e6f639871c7cbca5`; the v0.85.0 release merge and peeled
tag target are `ba58b419d637be81f6f0a0887a99282175160132`, and its tag object is
`c760531c1abe80b9dfed8663c79823ced8fb5fe9`. These are a historical bootstrap
checkpoint, not permission to assume that future sessions have the same HEAD.
Inspect the actual repository each time; local remote-tracking refs alone do not
prove current remote state.

## Roles

| Work | Codex |
| --- | --- |
| Long-running project coordinator | Repository implementation |
| Architecture/planning layer | Bounded engineering Slices |
| Runtime-test planner | Tests |
| Independent implementation/release reviewer | Static analysis |
| Roadmap/status coordinator | Diff review |
| Cross-file/project-context layer | Git-oriented engineering work |

When repository implementation is required, Work should stop that implementation
step and explicitly tell the user to **switch to Codex**, with a bounded handoff.
Work's review must inspect delivered repository facts rather than rely on Codex's
conversational account. Neither role acquires runtime trading authority through
coordination, review or memory.

## Authority order

When sources conflict, apply this precedence:

1. Released repository state.
2. Accepted ADR.
3. Frozen implementation + tests.
4. Release handoff / runtime test evidence.
5. Alignment review.
6. Roadmap.
7. Conversational recollection.

Check source dates, scope and checkpoint before treating wording as a conflict.
For example, the [v0.85 handoff](../handoffs/v0.85.0-governed-research-escalation-handoff.md)
still says pre-release at drafting, and ADR0052 retains its proposed authoring
status; verified released refs and frozen implementation establish later delivery
without silently editing their history or labeling every ADR accepted. A real
semantic conflict should be recorded and reviewed, not resolved by inventing
authority or rewriting evidence.

## Three-track documentation model

| Track | Location | Purpose |
| --- | --- | --- |
| TRACK 1 — PLANNED DIRECTION | [Roadmap](market-platform-roadmap.md), [boundaries](market-platform-boundaries.md) | Current intended direction and durable constraints; no delivery claim. |
| TRACK 2 — DELIVERED REALITY | `docs/handoffs/`; entry: [v0.85 handoff](../handoffs/v0.85.0-governed-research-escalation-handoff.md) | Frozen delivered scope, implementation checkpoints, validation and explicit deferrals. |
| TRACK 3 — ALIGNMENT REVIEW | `docs/reviews/` | Independent comparison of planned direction with delivered implementation after each frozen Slice. |

After **every frozen implementation Slice**, Work should compare planned direction
against delivered implementation and create
`docs/reviews/<version-or-slice>-alignment-review.md`. This is a future review
location/convention; this documentation task does not create an alignment review
or claim earlier reviews exist.

Each alignment review must cover:

- Planned objective and delivered implementation.
- Completed, partial and deferred requirements.
- Unexpected additions.
- Architecture-boundary compliance and scope drift.
- New information learned and roadmap impact.
- Next-Slice recommendation.

The purpose is to distinguish intentional architecture evolution from accidental
scope drift, not to force old plans forever. Preserve old planning checkpoints;
record a changed direction and its rationale in new reviews/current planning.
The status ledger is the compact current-state index linking these tracks and
test evidence; it is not a substitute for any of them.

## Work ↔ Codex operating loop

```text
Work: inspect roadmap/status/boundaries
   → architecture analysis
   → define next bounded Slice
   → prepare Codex handoff

Codex: implement
    → test
    → static analysis
    → review diff
    → commit/freeze when authorized
    → write/update handoff/evidence

Work: inspect actual repository
   → independent review
   → compare planned vs delivered
   → alignment review
   → status-ledger update
   → decide next step
```

A Codex handoff must specify:

- Whether a new session is required.
- Model and reasoning level.
- Exact baseline: branch, commit/refs, release identities as relevant, expected
  worktree/index state, and stop conditions for mismatch.
- Exact bounded scope and prohibited changes.
- Validation commands, acceptance criteria and evidence to retain.
- Expected report, including changed paths, checks/results, limitations and Git state.

Current user preference: **GPT-6.1 Sol**. **Medium** reasoning is generally
preferred for routine bounded implementation. Use **High** reasoning for
architecture-critical, complex, review or release-critical work. These are user
preferences, not a claim about model availability in every future session.

## Immediate planning guardrails

v0.85 **STOPS AT READINESS**.
**READY IS DESCRIPTIVE, CONTEXT-BOUND, AND NON-AUTHORITATIVE.**
READY must not automatically imply `READY → research`.

Monitoring Topology, a governed research-invocation boundary, bounded autonomous
execution and Shadow Observer remain future work. No v0.86 implementation or
version assignment is established here. Use the roadmap to plan and the ledger
to confirm delivery; do not mistake architectural direction for running behavior.
