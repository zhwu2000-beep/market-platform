# ADR 0029: Daily Research Instrument-History Integrity

## Decision

A ticker string is not a security identity. Verified daily research reuses the
v0.57 canonical, external, effective-dated mapping, source, and resolver model.
Its trust boundary is an explicit local strict-JSON metadata document; it does
not perform live lifecycle lookup, ticker-name inference, or environment/path
expansion.

The codec converts exact provider-session dates to midnight UTC. Mapping
admission is the half-open interval `[valid_from, expires_at)`. After released
completed-day filtering, `trim_to_mapping_interval` classifies every row and
reconstructs the admitted dataset before technical analysis.

Verified mode fails closed for absent, inactive, ambiguous, conflicting, or
corrupt metadata before provider I/O. Registry, mapping, and source
fingerprints retain metadata provenance. Integrity evidence separately retains
the original and admitted dataset fingerprints, counts, ranges, and a
fingerprint covering that evidence.

## Consequences

Only the requested current Polygon symbol is fetched. There is no alias
stitching or former-ticker fetch. Newly listed or renamed instruments may
therefore be DEGRADED after deterministic trimming. The legacy `research
analyze` command remains unchanged.

A future release may migrate verified analysis to the default. Automated
reference-data acquisition, alias history, interpretation work, and v0.73
presentation changes remain deferred.
