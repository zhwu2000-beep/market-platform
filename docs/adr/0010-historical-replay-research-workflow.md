# ADR 0010: Historical Replay Research Workflow

## Status

Accepted

## Context

The platform has two distinct Research concerns. The existing asynchronous
`ResearchWorkflow` and `DefaultResearchWorkflow` acquire provider data and
produce market interpretation. Historical Replay separately produces
deterministic executions, durable Replay Artifacts, and in-memory structural
Experiments. There was no domain object that recorded a complete, ordered
composition of those historical capabilities.

Historical workflow intent includes process-local strategy and state-model
components that are not owned by `HistoricalReplaySpecification`. Replay,
comparison, and workflow composition are separate derived software operations
and require separate caller-supplied revision identities.

## Decision

- The new family is explicitly named `HistoricalReplayResearchWorkflow*`; it
  neither implements nor replaces the existing asynchronous Research protocol.
- `HistoricalReplayResearchMemberSpecification` captures one Replay
  specification, ordered `StrategyInstance` values, a
  `HistoricalReplayResearchStateModelInstance`, structure identity, and an
  immutable semantic identity snapshot. The workflow intentionally accepts a
  narrower deterministic executable subset than ordinary Replay.
- `HistoricalReplayResearchWorkflowSpecification` owns one exact
  `HistoricalPriceSeries`, one baseline, zero or more position-sensitive ordered
  candidates, and explicit Replay, comparison, and workflow
  `SoftwareRevision` values.
- The fixed v1 policy permits baseline-only workflows and duplicate candidates.
  Baseline failure skips every dependent step. After baseline success,
  candidates continue independently. A failed candidate is never removed and no
  reduced Experiment is created.
- Only `StrategyRunnerError` is captured as an expected Replay execution-domain
  failure. Validation errors, invariant failures, control-flow exceptions,
  Artifact failures, and Experiment failures propagate.
- The synchronous service composes `HistoricalReplayService.run_execution()`,
  `HistoricalReplayArtifact.from_execution()`, and
  `create_historical_replay_experiment()`. It materializes one isolated source
  DataFrame per member through the existing public compatibility boundary.
- Execution provenance is checked against the member identity snapshot, source
  context, provider, dataset identity, and Replay software revision before
  Artifact construction.
- Terminal workflow status and the complete fixed step sequence are derived.
  Pending, running, retrying, and cancellation states do not exist in v1.
- The result owns complete in-memory Replay Artifacts and the optional existing
  Experiment. Step records retain only run/result or Experiment/comparison
  identities.

## Identity

The member, workflow, policy, and result schemas are:

- `historical_replay_research_workflow_member/v1`;
- `historical_replay_research_workflow/v1`;
- `historical_replay_research_workflow_policy/v1`;
- `historical_replay_research_workflow_result/v1`.

Workflow specification identity covers canonical source content, symbol,
interval, provider, baseline member, indexed candidates, the fixed policy, and
all three software revisions including dirty flags. Candidate order and
duplicates are significant.

Result identity covers the specification fingerprint, derived terminal status,
complete ordered steps, successful run/result identities, stable failure and
skip codes, indexed candidate outcomes, and optional Experiment/comparison
fingerprints. Artifact integrity checksums are excluded because they identify a
durable envelope rather than the semantic historical workflow result. Paths,
messages, tracebacks, wall-clock timestamps, durations, rendering, and object
identity are also excluded.

## Consequences

- Replay-only success owns one baseline Artifact and no Experiment.
- Complete candidate success creates the exact existing Experiment, including
  structured incompatible comparisons when applicable.
- Candidate failures retain successful Artifacts and original positions but
  produce a partial result with no Experiment.
- Strategy and state-model identities are derived from their runtime objects at
  member construction and immediately before and after every member execution.
  Strategy
  implementers must include every behavior-affecting value in immutable
  `StrategyInstance.configuration`; state-model implementers must expose a
  complete re-derivable configuration fingerprint, using `None` only for truly
  stateless models. Stale or mutated executable identity is an invariant failure,
  not a captured Replay failure. Produced provenance is verified afterward.
- Object identity, `repr`, arbitrary executable serialization, and filesystem
  state never participate in executable identity.
- A workflow with K candidates performs K+1 sequential Replays and retains K+1
  Artifact results. The workflow and Experiment share member object references.

## Deferred and Rejected

A durable Workflow Artifact is deferred. Embedding Replay Artifacts would
duplicate large outputs, while an identity-only manifest requires repository or
locator semantics that do not exist. The core performs no save/load or other
filesystem I/O.

CLI configuration, automatic Git discovery, provider fetching, async execution,
parallel candidates, retries, cancellation, progress, generic DAGs, schedulers,
parameter grids, optimization, portfolio simulation, financial-performance
metrics, UI, Agent integration, and database/cloud repositories are outside this
foundation.
