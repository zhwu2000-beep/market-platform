# Market Platform durable boundaries

## Purpose and authority

This **TRACK 1 — PLANNED DIRECTION** consolidation carries durable constraints
into future planning. It summarizes existing contracts and labels future design
requirements; it does not amend ADR semantics, activate capabilities or grant
authority. Use the [bootstrap authority order](market-platform-work-bootstrap.md)
and [status ledger](market-platform-status-ledger.md) when reconciling sources.

## Evidence and provenance

Evidence and its retained records must be immutable/auditable under their owning
contracts. Preserve truthful chronology: query, receipt, observation, effective,
knowledge, execution and availability times retain their distinct meanings.
No backdating, timestamp rewriting or hidden refetch represented as original
evidence is permitted. A later independent acquisition retains its own provenance
even when exact normalized content matches an earlier acquisition.

Recovery preserves identity, provenance and owned graph relationships; it cannot
promote detached JSON, a matching fingerprint or an empty replacement root into
lost authority. Historical Pending can remain resolvable after checkpoint
replacement through its retained source graph. Delivery recovery does not promise
durable governance-root restoration or readiness-result recovery.

Sources: [ADR0035: Evidence](../adr/0035-evidence-foundation-architecture.md),
[ADR0039: production governance](../adr/0039_production_evidence_governance_and_governed_daily_technical_consumption.md),
[ADR0051: recovery](../adr/0051_radar_candidate_delivery_and_recovery_boundary.md)
and [ADR0052](../adr/0052_governed_research_escalation_readiness_boundary.md).

## Governance separation

- Validation != Admission.
- Admission != readiness.
- Readiness != research authority.
- **READY IS DESCRIPTIVE, CONTEXT-BOUND, AND NON-AUTHORITATIVE.**

Each owner retains its contract. Readiness uses authenticated retained material,
current governance and exact task Freshness; it cannot synthesize missing history,
reacquire inputs or convert an old result into permission. Exact normalized
content correspondence is distinct from acquisition provenance and Bridge
representation identity. Fresh Qualification/Bridge assessment occurrences may
append legitimately without changing source authority.

v0.85 is released/frozen and **STOPS AT READINESS**. A future invoker must
independently revalidate authority, context and timing; `READY → research` is not
an automatic edge. See [ADR0052](../adr/0052_governed_research_escalation_readiness_boundary.md)
and the [runtime closure](../test-evidence/v0.85-runtime-test-closure.md).

## Radar

Radar owns observation and meaningful-change detection. A passive Candidate
means eligibility for governed research consideration, not a Strategy,
recommendation, trade instruction or Evidence admission. **Candidate != Strategy**.
Meaningful change does not itself establish eligibility, and Pending does not
mean research started. Production Candidate/delivery/readiness activation remains
unwired under released v0.84/v0.85 contracts despite explicit test capability.

Sources: [ADR0049](../adr/0049_radar_lightweight_observation_and_meaningful_change_policy.md),
[ADR0050](../adr/0050_radar_candidate_and_escalation_boundary.md), ADR0051 and
ADR0052. Future Monitoring Topology must retain these authority boundaries.

## Strategy and execution

Strategy authority is distinct from execution authority. Existing descriptive
Strategy and offline execution-planning foundations are not autonomous broker
operation. Future execution should remain constrained/mechanical inside an
explicitly approved risk envelope. Unknown, unsupported or out-of-scope cases
pause/escalate rather than silently broaden authority.

The [future autonomous direction](market-platform-roadmap.md) requires separate
contracts and approval. It does not override current human decision authority or
authorize trading. Sources:
[ADR0034: operating-system architecture](../adr/0034-market-intelligence-operating-system-architecture.md),
[ADR0026: execution authorization](../adr/0026-broker-neutral-execution-authorization-foundation.md)
and [ADR0043: governed Strategy](../adr/0043_governed_daily_technical_strategy.md).

## Shadow Observer

Future Shadow Observer is an independent **ex-ante process auditor** using only
information actually available at decision time. It must not perform hindsight
optimization or search historical perfect tops/bottoms. Later outcome alone does
not make an earlier decision invalid. Outcome-based aggregate learning cannot
rewrite the original decision context, evidence or authority.

This is a future requirement, not an implemented auditor. Sources:
[v0.83 architecture kickoff](../handoffs/v0.83.0-radar-architecture-kickoff-handoff.md)
and ADR0052 Decision 12.

## Fail-closed behavior

Ambiguity or contradiction must not silently become authority. Missing ordinary
governance prerequisites block readiness; demonstrable integrity contradictions
take precedence over weaker missing/stale governance **where the frozen contract
says so**, producing refusal. B1 does not turn mere absence into a contradiction.
Early failure must not label later unperformed checks as passed; unexpected errors
must not be converted into a misleading READY result.

Sources: ADR0052 and the
[frozen readiness implementation](../../src/market_platform/application/radar_research_escalation.py),
[tests](../../tests/unit/test_radar_research_escalation.py) and runtime closure.
Any changed failure policy requires an explicit future decision, not a wording
change in this consolidation.

## Engineering boundaries

Keep layers explicit, narrow and composable. Validate provider configuration
lazily and keep provider HTTP access behind injected clients. Future planning must
not introduce hidden inputs or let conversational memory become platform truth.
These constraints follow [AGENTS.md](../../AGENTS.md); bounded Slices should
preserve them without unrelated cleanup or premature splitting.
