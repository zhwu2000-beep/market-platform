# Market Platform status ledger

## Current-state checkpoint

This compact index describes the verified `main` checkpoint
`541cfa0b659947760279ec77e6f639871c7cbca5` and accepted runtime closure. It links
evidence rather than replacing it. Local refs were inspected without fetching.
Reinspect actual state before a new Slice. Future direction is in the
[roadmap](market-platform-roadmap.md); operating rules are in the
[bootstrap](market-platform-work-bootstrap.md) and [boundaries](market-platform-boundaries.md).

Status vocabulary: **PLANNED**, **IN_PROGRESS**, **IMPLEMENTED**, **VALIDATED**,
**RELEASED**, **DEFERRED**, **SUPERSEDED**, **CANCELLED**. Status describes the
specific item and scope, not automatic production activation. The Release column
separately records release context for validation-only items.

| Item | Planned In | Status | Implementation Evidence | Validation Evidence | Release | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| v0.83 Radar observation/state foundation | [Radar ADR0049](../adr/0049_radar_lightweight_observation_and_meaningful_change_policy.md) | RELEASED | [v0.83 handoff](../handoffs/v0.83.0-radar-handoff.md) | Handoff's retained focused evidence | v0.83.0; superseded as latest release by v0.85.0 | Foundation for meaningful-change/Candidate work; not full future Monitoring Topology. |
| v0.84 Candidate Escalation Foundation | [ADR0050](../adr/0050_radar_candidate_and_escalation_boundary.md), [ADR0051](../adr/0051_radar_candidate_delivery_and_recovery_boundary.md) | RELEASED | [v0.84 handoff](../handoffs/v0.84.0-radar-candidate-escalation-handoff.md); merge `1088b274131c71b7545ffa22eea9fbce3cb12d9e` | Handoff: 599 focused passes, retained elevated native evidence | v0.84.0 | Passive Candidate / recoverable Pending capability; automatic production activation deferred. |
| v0.85 Governed Research Escalation Readiness | [ADR0052](../adr/0052_governed_research_escalation_readiness_boundary.md) | RELEASED | [v0.85 handoff](../handoffs/v0.85.0-governed-research-escalation-handoff.md); Slice 1–4; merge `ba58b419d637be81f6f0a0887a99282175160132` | Handoff: 634 focused passes, retained elevated native evidence; [runtime closure](../test-evidence/v0.85-runtime-test-closure.md) | v0.85.0, released/frozen | READY/BLOCKED/REFUSED; stops at readiness; grants no research authority. |
| v0.85 runtime validation closure | Frozen v0.85 contract; [closure](../test-evidence/v0.85-runtime-test-closure.md) | VALIDATED | Existing released implementation; no new implementation | Complete real-data/recovery/governance evidence chain; five READY runs; 67/67 semantic checks | RELEASED context: v0.85.0 remains released/frozen | Remaining runtime acceptance = **none**; reopen required = **no**; +5 Qualification/+5 Bridge occurrences are expected append-only variance. |
| Core Radar | [Current roadmap](market-platform-roadmap.md) | PLANNED | None for this Monitoring Topology scope | None | Unassigned future version | Small user-selected set, persistent richer monitoring; daily cadence respects completed sessions. |
| Broad Sentry | [Current roadmap](market-platform-roadmap.md) | PLANNED | None | None | Unassigned future version | Larger cheaper universe; governed low-cost anomaly triggers, not continuous full research. |
| Escalation/Cooldown | [Current roadmap](market-platform-roadmap.md) | PLANNED | None for future monitoring lifecycle | None | Unassigned future version | Define entry, persistence, cooldown, de-escalation and re-escalation; distinct from delivered Candidate/Pending. |
| Governed research invocation | ADR0052 deferred boundary; [roadmap](market-platform-roadmap.md) | PLANNED | None for invocation from readiness | None | Unassigned future version | Revalidation, identity, interruption/recovery, idempotence, provenance and freshness require future decisions. Existing Technical capability is not this invocation boundary. |
| Bounded autonomous execution | [Current roadmap](market-platform-roadmap.md) | PLANNED | None for autonomous operation; older offline foundations are separate | None for autonomous operation | Unassigned future version | Small isolated allocation inside approved risk envelope; no current trading authorization. |
| Shadow Observer | [Historical architecture kickoff](../handoffs/v0.83.0-radar-architecture-kickoff-handoff.md); [current roadmap](market-platform-roadmap.md) | PLANNED | None | None | Historical v0.86 suggestion was provisional; no current assignment | Independent ex-ante process audit; no hindsight optimization. |
| O1 historical inventory/unresolved scanning optimization | [v0.84 handoff](../handoffs/v0.84.0-radar-candidate-escalation-handoff.md), [v0.85 handoff](../handoffs/v0.85.0-governed-research-escalation-handoff.md) | DEFERRED | No optimization delivered by this task | Not an acceptance prerequisite | Not release-blocking for v0.85.0 | Optional future work; not a remaining runtime acceptance item. |

The v0.84/v0.85 handoffs preserve pre-release drafting language; subsequent local
release merge/tag identities establish released state. Their history and ADR
semantics remain unchanged. Earlier provisional version assignments are preserved
as history rather than relabeled completed or silently rewritten. No future item
above is marked IN_PROGRESS, IMPLEMENTED, VALIDATED or RELEASED.

After each frozen implementation Slice, Work should independently inspect the
repository, write the planned-versus-delivered alignment review in
`docs/reviews/<version-or-slice>-alignment-review.md`, then update this ledger
using actual evidence. See the bootstrap's three-track model.
