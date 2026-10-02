# Market Platform roadmap

## Planned-direction checkpoint

This is **TRACK 1 — PLANNED DIRECTION**, established after released/frozen v0.85.0
runtime closure. Future items below are **PLANNED**, with no implementation begun
or version commitment implied by this document. The
[status ledger](market-platform-status-ledger.md) records delivered state; the
[boundaries](market-platform-boundaries.md) constrain future design.

Preserve [historical roadmap](../roadmap.md) and
[v0.83 architecture kickoff](../handoffs/v0.83.0-radar-architecture-kickoff-handoff.md)
as authored. The kickoff's provisional v0.84 Scenario/Risk/Plan, v0.85 Execution
and v0.86 Shadow Observer sequence differs from delivered v0.84 Candidate and
v0.85 readiness. This current direction records that evolution without making
older plans appear retrospectively consistent. It starts no v0.86 implementation.

## Next architecture phase: MONITORING TOPOLOGY

### CORE RADAR

A small user-selected set of high-interest instruments should receive persistent
monitoring, richer state and faster escalation into deeper analysis. Higher
monitoring frequency is appropriate where the underlying signal genuinely
changes. Completed-daily signals remain governed only after completed sessions;
polling more often does not create a new completed-daily signal. Future intraday,
event and news monitoring may justify higher cadence under explicit contracts.

### BROAD SENTRY

A larger, cheaper monitoring universe should use explicitly governed low-cost
triggers. Possible triggers include large price moves, large downside moves,
gaps, abnormal volume, volatility expansion, breakout/breakdown, material events
and other explicitly governed anomaly signals. Thresholds, evidence sources,
cadences and policies remain future decisions.

Broad Sentry should not continuously run full expensive research across the
whole market. A trigger creates consideration for escalation, not research or
trading authority.

### TEMPORARY ESCALATION

```text
Broad instrument → trigger → elevated monitoring
                 → deeper Radar/research consideration
```

### DE-ESCALATION / COOLDOWN

Future architecture must define the lifecycle before implementation:

| Requirement | Design question to resolve |
| --- | --- |
| Escalation entry | Which authentic governed trigger, instrument identity, policy and context permit elevated monitoring? |
| Persistence | What retained state and identity preserve an escalation across repeated observations and interruption/recovery? |
| Cooldown | What explicit policy controls repeat triggers and duplicate escalation without hiding meaningful new evidence? |
| De-escalation | Which expiry, resolution or exit conditions return the instrument to Broad Sentry while retaining history? |
| Re-escalation | Which fresh trigger/context permits renewed escalation, and how is it distinguished from the earlier occurrence? |

No thresholds, storage schema, scheduler or transition implementation is decided
here. An architecture review should define the smallest bounded Slice next.

## Future governed research activation

**v0.85 STOPS AT READINESS.**
**READY IS DESCRIPTIVE, CONTEXT-BOUND, AND NON-AUTHORITATIVE.**
READY must **NOT** automatically imply `READY → research`.

A later version may define a governed research-invocation boundary. Future
architecture should consider invocation identity, authority revalidation,
interruption/recovery, idempotence, provenance, exact task/context freshness and
fail-closed behavior. Revalidate Pending trust, material, governance, policy and
timing at invocation; a historical READY result cannot supply current authority.
Invocation, acknowledgment and execution lifecycle choices are not decided here.

## Future bounded autonomous execution

Long-term direction: a small isolated capital allocation may eventually operate
autonomously inside a strict approved risk envelope. This requires future
architecture decisions and explicit authorization; existing offline trading
foundations do not establish a live autonomous system.

Potential future chain:

```text
Radar → Research → Strategy → Risk Governor → Execution Agent
      → Shadow Observer / process audit
```

The chain is conceptual; Shadow Observer audits the process and grants no
execution authority. Potential initial constraints are:

- Dedicated small capital pool/account.
- Allowlisted instruments.
- Maximum position size, maximum concurrent positions and maximum total exposure.
- Single-trade loss limit and daily loss limit.
- No unrestricted leverage; no naked options initially.
- Explicit unsupported-case escalation.
- Kill switch.

Autonomy means freedom **INSIDE an approved envelope**. It does not mean
unrestricted trading authority. Strategy authority stays distinct from execution
authority; execution should be constrained and mechanical, with unknown or
out-of-scope cases paused/escalated. No execution is implemented by this task.

## Future Shadow Observer

Shadow Observer is a planned independent ex-ante process auditor. It uses only
decision-time information, preserves chronology and examines discipline and
boundary compliance. It must not optimize with hindsight or search for historical
perfect tops/bottoms. Later outcome alone does not invalidate an earlier decision.
Delivery, retention and audit contracts remain future decisions.

After each frozen Slice, apply the
[bootstrap alignment-review loop](market-platform-work-bootstrap.md) to record
what changed, what was learned and how the roadmap should evolve.
