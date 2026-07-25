# ADR 0005: Replay Specification and Context Window

## Status
Accepted

## Context
Historical replay already allowed `HistoricalReplayService.run()` to receive a full
historical frame and evaluate only an inclusive `start`/`end` subwindow. Signal and
default price-structure precomputation used the full supplied frame, so direct
callers could provide pre-evaluation history. The CLI instead acquired and filtered
prices beginning at `--start`, collapsing acquisition, context, and evaluation
boundaries and preventing analytical warm-up through that interface.

Five temporal concepts are distinct:

- acquisition range: provider request boundaries;
- available dataset range: returned historical rows;
- context window: rows permitted to analytical precomputation and prefixes;
- evaluation window: rows that create replay steps;
- observation evaluation `as_of`: the evaluated prefix endpoint for each step.

## Decision
- Add immutable `HistoricalReplaySpecification` in `market_platform.replay` with
  normalized `symbol`, `interval`, `context_start`, `evaluation_start`, and
  `evaluation_end`.
- Specification timestamps are timezone-aware UTC values and enforce
  `context_start <= evaluation_start <= evaluation_end`.
- `HistoricalReplayService.run_with_specification()` bounds analytical data
  inclusively to `[context_start, evaluation_end]`, precomputes over that retained
  context, and emits steps only for timestamps in the inclusive evaluation window.
- A requested boundary need not coincide with a returned bar. Zero returned rows
  before `evaluation_start` is valid when evaluation rows exist.
- Legacy `run()` remains supported: the complete supplied frame remains available
  context, while optional `start` and `end` select evaluation positions.
- CLI `--start` and `--end` remain inclusive evaluation dates. Optional
  `--context-start` controls acquisition and context; when omitted it equals
  `--start`, preserving released behavior.
- CLI day boundaries are UTC: context/evaluation starts at 00:00:00, evaluation end
  at 23:59:59.999999. Provider end remains evaluation-end date plus one calendar
  day for the existing exclusive-end compatibility policy.
- `--max-bars` limits evaluation rows, not retained context rows.
- Replay remains an in-process application workflow coordinating canonical market
  data, signals, structure, observations, state, and strategies.
- Replay result and step schemas remain unchanged.

## Consequences
Pre-evaluation rows can now reach signal and structure calculations through the
CLI without creating extra replay steps. The same explicit specification and input
produce deterministic results. Different context can legitimately change early
analytical facts for the same evaluation window.

`context_start` is an earliest requested/allowed boundary, not a coverage claim.
Provider holidays, weekends, sparse data, or limited coverage may make the first
returned bar later. Actual coverage and dataset lineage are not recorded by this
release.

## Alternatives Considered
- Warm-up bars, rejected for now because provider APIs request dates and sparse or
  missing sessions make bar acquisition nontrivial.
- Warm-up calendar duration, rejected because calendar days do not equal bars.
- Component-derived requirements, deferred because current signals and structures
  do not expose a common historical-requirement contract and some use expanding
  history or confirmation lag.
- Full available history, rejected because it creates an unstable implicit context
  and provider-dependent results.
- A public resolved execution plan or durable run manifest, deferred until actual
  coverage, component identities, software revision, and dataset lineage need
  durable representation.
- Adding context metadata to `HistoricalReplayResult`, rejected to preserve public
  serialization and deterministic fingerprints.
- Exchange-calendar infrastructure, rejected as unnecessary for the explicit daily
  boundary contract in this release.
