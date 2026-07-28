# ADR 0009: Observation Fingerprint Precomputation

## Status

Accepted

## Context

Historical observation identity is an established compatibility contract. Its
compact sorted JSON payload contains top-level `as_of`, `interval`, `provider`,
`rows`, and `symbol` fields. Every ordered row contains symbol, timestamp, OHLCV,
and provider. Row numerics use `repr(float(value))`, including distinct `0.0` and
`-0.0` spellings. Signal and structure snapshots, price facts, methodology,
provider-specific extra columns, and dataset identity are excluded.

Replay previously projected and JSON-encoded every complete prefix independently.
For N full-prefix steps this performed N(N+1)/2 row projections and encodings.
The changing `as_of` value precedes `rows` in the canonical byte stream, so a
single rolling SHA-256 state cannot preserve the existing digests.

## Decision

- `market_platform.observation` owns an immutable
  `HistoricalObservationFingerprintPrecompute`.
- Replay prepares it once for the exact ordered evaluation positions and performs
  one bound lookup per step.
- Preparation projects and encodes every required source row once through the
  maximum requested position. It builds one transient comma-separated row-byte
  stream with prefix offsets.
- Each requested digest hashes the exact legacy header, a view of the row stream,
  and the exact legacy suffix. Only final fingerprint strings and binding metadata
  remain after construction.
- Shared private helpers own row projection, row JSON bytes, envelope bytes, and
  SHA-256 finalization for both optimized and standalone fallback paths.
- The precompute binds to the exact `HistoricalPriceSeries` instance plus symbol,
  interval, provider, position, prefix length, endpoint, and observation `as_of`.
  The series reference is neither represented, compared, hashed, nor serialized.
- The retained dataset content fingerprint is diagnostic only. It is not
  sufficient binding because it excludes provider and has different signed-zero
  semantics.

## Compatibility Proof

The helper sequence emits the same escaped strings, sorted row keys, compact
separators, timestamp text, numeric text, row order, commas, delimiters, UTF-8
encoding, and SHA-256 input bytes as the prior full `json.dumps` call. Golden
canonical-byte and digest fixtures independently freeze that prior behavior.

Observation fingerprints, Replay results and identities, Replay Artifact result
fingerprints/checksums/bytes, and experiment compatibility/fingerprints therefore
remain unchanged.

## Consequences

- Row projection, numeric/timestamp conversion, and row JSON encoding become
  O(maximum requested position + 1), not O(sum of prefix lengths).
- Exact legacy SHA-256 input remains O(sum of prefix lengths), normally O(N²).
  This release does not claim complete linear-time fingerprint generation.
- Memory is linear and transient for row bytes; no prefix payloads, hash objects,
  or global/cross-run cache are retained.
- Raw DataFrame construction and validated-prefix construction without a
  precompute retain the standalone fallback.
- Mismatched or unprepared prefixes fail before `MarketObservation` construction.

## Rejected Alternatives

- A nested prefix fingerprint, Merkle tree, or chained row hash changes the
  observation digest and is a schema migration.
- `hashlib.copy()` cannot reuse the row-prefix state because each changing header
  is hashed first.
- Dataset fingerprint binding alone loses provider and observation signed-zero
  distinctions.
- Raw fingerprint injection, trust/skip flags, global caches, persisted caches,
  and mutable hash-state exposure weaken the construction boundary.
