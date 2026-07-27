# ADR 0008: Historical Replay Experiment and Comparison

## Status

Accepted for v0.51.0.

## Context

Versioned Historical Replay Artifacts preserve verified execution provenance and
complete Replay output, but the platform has no deterministic boundary for
organizing a baseline and candidates or describing their structural differences.
Replay output contains market-state and strategy-applicability evaluations, not
portfolio returns, orders, fills, positions, P&L, or investment performance.

## Decision

Add an immutable in-memory Historical Replay experiment foundation. One
`HistoricalReplayExperimentSpecification` owns a verified baseline Artifact, one
or more ordered verified candidate Artifacts, and caller-supplied
`SoftwareRevision`. `create_historical_replay_experiment()` produces one ordered
pairwise `HistoricalReplayComparisonResult` per candidate without executing Replay
or performing filesystem I/O.

The schema families are:

- `historical_replay_experiment/v1`;
- `historical_replay_comparison_policy/v1`;
- `historical_replay_comparison/v1`.

The experiment fingerprint covers baseline run/result fingerprints, ordered
candidate run/result fingerprints and indices, the complete fixed policy, and the
comparison software revision. It excludes paths, labels, wall-clock timestamps,
rendering, and runtime duration.

### Strict compatibility

V1 detailed comparison requires exact equality of:

- symbol;
- interval;
- retained dataset content fingerprint;
- ordered evaluation timestamps;
- ordered per-step observation fingerprints.

There is no timestamp intersection or union. Valid but incompatible Artifacts
produce structured ordered reason codes, execution differences, and no aligned
state/strategy detail or aggregate counts.

Provider is reported but is not an independent rejection rule. Current
observation fingerprints include provider and prefix rows, so different providers
ordinarily cause observation incompatibility even when provider-independent
dataset contents match. V1 does not redefine observation identity.

### Structural comparison

Compatible steps are aligned by their exact ordered timestamp. Market state is
compared through the explicit regime, quality, and missing-input fields. State
provenance and evaluation evidence use separate change indicators. Supporting-only
changes still make a step structurally changed.

Strategies align by `(strategy_id, zero-based occurrence index for that ID)`.
Version and configuration fingerprint are compared properties, not alignment
keys. This preserves duplicate IDs, supports reordering, and represents added or
removed members without a user-supplied mapping.

Strategy comparison covers identity, status, rationale, required/missing inputs,
typed evidence, and evaluation provenance. Changed-step detail contains complete
immutable changed state/evaluation values. Unchanged step detail is omitted;
complete deterministic aggregate counts and per-member status distributions are
retained.

The comparison fingerprint covers the full versioned compatibility, execution
difference, aggregate, and changed-step payload. It excludes member Artifact bytes
and checksums because run/result identities already identify the semantic members.
The fingerprint is experiment-contextual because it includes the experiment
fingerprint; the same baseline/candidate pair may therefore have a different
comparison fingerprint in a differently ordered or larger experiment.

All comparison statements describe structural output differences. They do not
assign causality to a configuration, model, data, provider, or software change.

### Boundaries

Comparison APIs accept already loaded and verified `HistoricalReplayArtifact`
objects. Artifact loading remains the v0.50 filesystem boundary. Comparison
requires caller-supplied software revision and does not discover Git state.

V1 retains changed steps in memory and is intended for trusted-size local research
workloads. Complexity is proportional to candidates, aligned steps, and aligned
strategy members. No resource-limit, streaming, parallel, or scheduling framework
is introduced.

## Compatibility

The release is additive. Replay service APIs, Artifact schemas and bytes, result
serialization, run/result/observation/dataset/specification/strategy/Research
fingerprints, CLI behavior, and benchmark fingerprints remain unchanged.

## Rejected Alternatives

- Timestamp intersection or union: obscures missing bars and changes denominators.
- Provider-neutral observation identity: changes an established fingerprint.
- Multiple causal comparison modes: exceeds the evidence represented by Replay.
- Strategy alignment by ID only: loses duplicate members.
- Position-only strategy alignment: makes reordering appear as unrelated changes.
- Generic recursive dictionary diff: weakens field ownership and versioning.
- Durable experiment Artifact: deferred until comparison semantics stabilize.
- Embedded member Artifacts or file paths: duplicates results or creates fragile
  path identity.
- CLI, Replay batches, grids, optimization, and parallelism: separate workflows.
- Financial performance and significance metrics: current Replay has no portfolio
  or return model.
