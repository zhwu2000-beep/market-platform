# ADR 0007: Versioned Historical Replay Artifact

## Status

Accepted for v0.50.0.

## Context

`HistoricalReplayExecution` preserves an in-memory result and deterministic run
provenance, but it cannot be saved and reconstructed as a validated public model.
The existing `HistoricalReplayResult.to_dict()` is a presentation contract used by
the CLI and does not preserve every runtime type needed for lossless decoding.

Replay needs a small local artifact boundary without introducing a repository,
database, dataset store, or changing existing result serialization.

## Decision

Add immutable `HistoricalReplayArtifact` as a versioned durable envelope around one
`HistoricalReplayExecution`. The v1 serialized form stores the complete result
exactly once, alongside provenance, the existing run fingerprint, a new production
result fingerprint, and a semantic integrity checksum.

The exact schema families are:

- `historical_replay_artifact/v1`
- `historical_replay_result/v1`
- `historical_replay_artifact_integrity/v1`

The v1 writer emits only these schemas. The reader accepts only these schemas,
requires exact fields, and rejects unknown fields. The version dispatch boundary
is explicit; migrations are deferred.

### Result codec

Artifact serialization uses a field-directed typed codec rather than changing
`HistoricalReplayResult.to_dict()`. It reconstructs public immutable models and
reruns their validation. Tuple ordering, enums, optional values, aware UTC
timestamps, state evidence, strategy evidence, and nested provenance are retained.

`StrategyEvidence.observed_value` uses an explicit tagged representation for
string, integer, float, boolean, datetime, and null. This prevents an ISO-looking
string from becoming a datetime and prevents booleans from becoming integers.
Finite floats use canonical numeric encoding; every floating-point zero, including
negative zero, is represented as `0.0`.

### Three distinct identities

- The existing run fingerprint identifies canonical execution inputs and resolved
  facts. Its v0.49.0 semantics are unchanged.
- The production result fingerprint identifies the complete typed result payload
  under `historical_replay_result/v1`. It is deliberately separate from the
  historical benchmark fingerprint family.
- The integrity checksum covers the complete canonical artifact semantic envelope
  except the checksum value itself, including schema identifiers and algorithms.

Canonical semantic checksum verification ignores JSON key order, whitespace, final
newlines, and LF versus CRLF. Any semantic payload change invalidates it. This is
corruption and inconsistent-edit detection, not authentication: a party able to
edit the payload and recompute the checksum can forge a consistent artifact.

### Result-only artifact

The artifact stores the dataset content fingerprint and actual provider through
run provenance, but no canonical OHLCV rows. It preserves and verifies the result;
it cannot recover the original dataset or rerun the calculation.

### Local file adapter

The adapter writes deterministic compact sorted JSON as UTF-8 without BOM and with
one final LF. It creates parent directories, refuses overwrite by default, writes
and fsyncs a temporary file in the target directory, then atomically replaces the
destination. Temporary files are cleaned after failure where possible. Native
filesystem errors remain visible.

Loading always verifies. It rejects BOM, invalid UTF-8/JSON, unsupported schemas,
invalid shapes, checksum mismatches, run/result fingerprint mismatches, and
execution inconsistencies. V1 reads the complete document into memory and is
intended for locally generated, trusted-size files; denial-of-service limits are
not provided.

## Compatibility

This change is additive. Existing replay service methods, replay result and summary
models, `HistoricalReplayResult.to_dict()`, CLI table/JSON/CSV schemas, observation
fingerprints, run fingerprints, and benchmark fingerprints remain unchanged.
There is no CLI integration in v0.50.0.

## Rejected Alternatives

- Modifying `HistoricalReplayResult.to_dict()`: breaks its presentation contract.
- Embedding OHLCV: increases size, licensing/privacy scope, and dataset schema
  ownership.
- External dataset locator: requires a dataset registry not yet present.
- Exact-file-byte checksum: makes harmless formatting and line-ending changes fail.
- Dual semantic and byte checksums: adds no required v1 value.
- Generic serializer, artifact base class, or repository abstraction: unnecessary
  architecture ceremony.
- Signatures, HMAC, encryption, or PKI: authentication is outside this foundation.
- CLI artifact commands: deferred until software-revision acquisition policy is
  approved.
