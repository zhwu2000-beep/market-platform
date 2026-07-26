# ADR 0006: Replay Run Identity and Provenance

## Status
Accepted

## Context
Historical replay has an explicit request specification and canonical retained
price series, but `HistoricalReplayResult` intentionally contains only evaluated
outputs. It does not identify requested windows, actual context coverage, the
retained dataset, selected provider, analytical derivations, or software revision.
Observation fingerprints bind each observation to its prefix, but they are not a
dataset or execution identity.

Identity, provenance, replay output, and a future durable artifact are distinct:

- specification describes requested replay intent;
- provenance describes requested and resolved execution facts;
- run fingerprint identifies those canonical facts;
- result contains derived replay output;
- a future artifact may persist provenance, result, and canonical data references.

## Decision
- `HistoricalReplaySpecification.fingerprint` identifies normalized symbol,
  interval, context start, evaluation start, and evaluation end.
- `HistoricalPriceSeries.content_fingerprint` identifies every retained canonical
  symbol/timestamp/OHLCV row in canonical order. Provider and interval are excluded.
- Provider remains a separate provenance fact. Identical contents from different
  providers have equal content fingerprints but different run fingerprints.
- `ReplaySignalDerivationIdentity` and `ReplayStructureDerivationIdentity` identify
  methodology, version, and effective configuration fingerprint. Built-in Replay
  derivations resolve stable identities from their effective constants/config.
- Custom structure services require an explicit identity only when using the new
  provenance-producing API. Existing Replay methods remain compatible.
- `SoftwareRevision` is caller-supplied and contains revision plus dirty state.
  Replay models do not run Git commands or discover package/build metadata.
- `HistoricalReplayRunProvenance` records the normalized specification and its
  fingerprint, dataset content fingerprint, actual provider, actual context and
  evaluation bounds/counts, derivation identities, state-model identity, ordered
  strategy identities, and software revision.
- `HistoricalReplayExecution` contains the unchanged `HistoricalReplayResult`, its
  provenance, and the provenance-derived run fingerprint.
- `HistoricalReplayService.run_execution()` is additive. `run()` and
  `run_with_specification()` retain their signatures and return types.

## Fingerprint Contract
New v0.49.0 fingerprints use compact UTF-8 JSON with sorted keys, finite values,
an explicit family schema version, and SHA-256 formatted as `sha256:<hex>`.
Unsupported canonical values are rejected. Existing observation, strategy,
research, and benchmark fingerprint implementations are deliberately unchanged.
Canonical floating-point zero is encoded as `0.0`, including negative zero.

The run fingerprint includes execution inputs and resolved facts, not Replay
result contents. Requested bounds and actual bounds are both retained: requested
bounds express intent, while actual bounds describe sparse/provider-returned data.
Strategy order and duplicates are significant because Replay preserves execution
order.

The deterministic payload excludes wall-clock timing, output paths/formats, cache
paths, logging, random identifiers, and step/result content.

## Consequences
Executions with the same declared identities and resolved facts have the same run
fingerprint. A retained middle-row change, provider change, derivation change,
state/strategy identity change, software revision change, or dirty-state change
changes it. Rows filtered before `context_start` or after `evaluation_end` do not.

Current result, summary, CLI table/JSON/CSV, observation fingerprints, and benchmark
result fingerprints remain unchanged. The execution envelope is opt-in and is not
used by the CLI in this release.

Identity is not persistence or guaranteed replayability. The fingerprint can
verify subsequently supplied canonical data but cannot recover it. Provider
historical revisions, corporate actions, exchange calendars, entitlements,
dependency environments, and custom component code remain outside this release.

## Alternatives Considered
- Adding provenance to `HistoricalReplayResult`, rejected to preserve serialization,
  equality, CLI output, and benchmark compatibility.
- A separate run-identity model, rejected because the provenance-derived fingerprint
  is sufficient.
- A resolved plan plus manifest/artifact, deferred until durable persistence exists.
- Including provider inside the content fingerprint, rejected because it prevents
  source-independent content comparison; provider still changes run identity.
- Including Replay output in the run fingerprint, rejected because execution
  identity and output verification have different responsibilities.
- Git or callable introspection inside models, rejected as fragile and environment
  dependent.
- Unifying older fingerprint families, rejected as unnecessary compatibility risk.
