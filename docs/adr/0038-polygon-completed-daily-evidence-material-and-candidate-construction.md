# ADR 0038: Polygon Completed-Daily Evidence Material and Candidate Construction Semantics

## Status

Accepted.

This decision is a docs-only architecture checkpoint for v0.78.0. It extends
ADR 0037 by fixing the deterministic material and Candidate-construction
semantics that must be accepted before implementation begins. It authorizes no
production-code or test change by itself.

## Context

ADR 0035 defines Evidence as a provenance-bearing representation of a source
observation, measurement, or assertion. It separates semantic authorization,
validation, admission, validity, freshness, consumability, and research use.
ADR 0037 authorizes the first production Evidence contract: Massive.com,
formerly Polygon.io, Stocks Custom Bars completed-daily split-adjusted OHLCV
acquired through the exact `api.polygon.io` profile.

ADR 0037 fixes the source, material-schema, contract, authorization, authority,
information-class, temporal, and lifecycle meaning. It intentionally precedes
the source-acquisition-to-Evidence adapter. Subsequent reconnaissance found
four construction details that must be fixed before that adapter can be
implemented safely:

1. exact treatment of optional provider count metadata;
2. the exact distinction between completed-day filtering and out-of-bound
   rejection;
3. the complete canonical projections used for material, artifact identity,
   and artifact version; and
4. the ordering relationship between caller-supplied `query_as_of` and actual
   source receipt.

This ADR resolves those points without changing the accepted ADR 0037 source
authorization or widening the production trust root.

## Relationship to ADR 0037

ADR 0037 remains authoritative for the exact:

- Massive.com-formerly-Polygon.io vendor/service identity;
- `https://api.polygon.io` acquisition profile and Stocks Custom Bars route;
- `polygon_completed_daily_ohlcv` Evidence type;
- `EvidenceInformationClass.SOURCE_MEASUREMENT` classification;
- `EvidenceAuthority.EXTERNAL_ORIGIN` authority;
- `polygon_completed_daily_ohlcv_material/1.0.0` material identity;
- `market_platform.evidence/polygon_completed_daily_ohlcv/1.0.0` contract;
- `production.polygon_completed_daily_ohlcv/1.0.0` authorization;
- split-adjusted, not asserted dividend-adjusted, daily aggregate meaning; and
- Candidate, unvalidated, unadmitted, non-consumable lifecycle.

This ADR narrows which already-preserved Polygon acquisition values are
eligible for Candidate construction and fixes how an eligible acquisition is
projected. It does not modify ADR 0037, authorize another source, or reinterpret
an authorization version in place. In particular, acquisition may preserve a
`Decimal` source timestamp as an exact transport fact, but this ADR makes such
a timestamp ineligible for this Candidate-construction path.

## Decision

### Construction boundary

Candidate construction is a deterministic outer-adapter operation. Its exact
conceptual API is:

```python
create_polygon_completed_daily_ohlcv_evidence(
    *,
    acquisition: PolygonCompletedDailyAcquisition,
    external_identity: ExternalInstrumentIdentity,
    mappings: list[InstrumentMapping] | tuple[InstrumentMapping, ...],
    query_as_of: datetime,
    artifact_created_at: datetime,
) -> PolygonCompletedDailyOhlcvEvidenceIngressResult
```

The adapter computes the instrument resolution, canonical subject, material,
material fingerprint, temporal identity, Evidence provenance, artifact ID,
artifact version, and governed Candidate artifact. It accepts no authorization,
catalog, contract, source, material-schema, producer, resolver callback,
bypass/test flag, API key, provider, HTTP client, or network dependency.

The adapter requires exact released input types and defensively verifies their
retained canonical state and the fixed ADR 0037 acquisition profile before it
constructs material. Caller-supplied `artifact_created_at` remains appropriate
because the existing Evidence contract represents creation separately and
deterministic replay may need an explicit historical instant. Supplying that
instant grants no authority and cannot alter the source, material schema,
subject, producer, or authorization.

### Results and empty material

`raw_row_count` is the length of the preserved acquisition row tuple before any
completed-day filtering excludes a current or strictly future New York date.

An absent `results` field blocks Candidate construction. A present empty array
is eligible when every other construction gate passes, and produces
`row_count=0`.

Empty material does not establish market inactivity, source or interval
completeness, source correctness, validation, admission, validity,
consumability, freshness, or permission for research use.

### Count correspondence

The adapter checks `queryCount`, `resultsCount`, and `count` before completed-
day filtering. For each field independently:

- absent means unknown and is permitted;
- present JSON null means unknown and is permitted;
- present non-null must be an exact nonnegative Python `int`, never `bool`; and
- present non-null must equal `raw_row_count`.

Every supplied non-null count therefore agrees with every other supplied
non-null count. A negative or unequal value blocks Candidate construction.
Missing values remain unknown and are not synthesized into acquisition facts
or material. Counts are source-envelope correspondence gates, not Evidence
Validation or admission.

### Adjusted-response proof

The fixed request profile's `adjusted=true` value is necessary but not
sufficient. Candidate construction additionally requires:

```text
response_adjusted_is_present is True
response_adjusted is True
```

An absent, null, false, malformed, or non-exact-boolean response value blocks
construction. Successful material retains `adjusted_response=true`. This proves
only correspondence to the authorized split-adjusted response contract; it
does not assert dividend adjustment, market truth, or the provider's internal
adjustment formula.

### Ticker and external-identity correspondence

The exact supplied external identity must satisfy:

```text
external_identity.namespace == "polygon"
external_identity.external_symbol == acquisition.requested_ticker
```

Both comparisons are case-sensitive. `external_venue` remains part of the
exact external identity and mapping but is not synthesized from the Polygon
response.

For the provider response ticker:

- field absent is unavailable and permitted;
- field present-null is unavailable and permitted;
- field present with a non-null exact string must exactly and case-sensitively
  equal `requested_ticker`; and
- a non-null mismatch blocks Candidate construction.

Response-ticker correspondence is checked before instrument resolution and
canonical subject minting. No response ticker is synthesized. The absent,
null, and exact-match cases that pass do not create different material.

### Pagination

`acquisition.additional_page_indicated is True` blocks Candidate construction.
The adapter does not follow pagination and does not create partial material.
Both an absent `next_url` and a present-null `next_url` may pass. Successful
absence of a continuation is a construction condition, not Evidence
Validation, admission, or proof of global source completeness.

The raw `next_url`, sanitized `next_page_reference`, and untrusted reference
contents do not enter successful material, Evidence provenance, artifact
identity, or error text.

### Query, receipt, and creation ordering

`query_as_of` must be an exact timezone-aware `datetime`. The adapter
normalizes it physically to UTC and requires:

```text
query_as_of <= acquisition.response_received_at
```

This is a no-lookahead and construction-authority invariant. A query cutoff
after actual source receipt could classify a bar using information about a
future civil date and is therefore prohibited.

The same normalized `query_as_of` is used for instrument resolution,
completed-day filtering, and material query provenance. Receipt is not
substituted for query time.

`artifact_created_at` must also be an exact timezone-aware `datetime`, is
normalized physically to UTC, and must satisfy:

```text
artifact_created_at >= acquisition.response_received_at
```

It is not synthesized from `query_as_of` or receipt. These rules establish:

```text
query_as_of <= platform_received_at <= artifact_created_at
```

without collapsing any of the three meanings.

### Instrument resolution and subject

The adapter constructs no Polygon-specific registry. It passes the exact
supplied `ExternalInstrumentIdentity`, exact built-in finite `list` or `tuple`
of `InstrumentMapping` values, and normalized `query_as_of` to
`resolve_instrument_mapping(...)`.

Not-found, inactive, ambiguous, conflicting, duplicate, invalid, or
non-corresponding resolution fails Candidate construction. The adapter does
not import or depend on `research.daily_instrument_integrity`.

The canonical subject is exactly one `EvidenceSubjectReference`:

```text
namespace           = "canonical_instrument"
subject_id          = resolution.mapping.canonical_instrument
                      .instrument_id.instrument_id
subject_version     = "canonical_instrument/v1"
subject_fingerprint = resolution.mapping.canonical_instrument.fingerprint
```

`canonical_instrument/v1` is the existing
`CANONICAL_INSTRUMENT_SCHEMA_VERSION`; this ADR does not create another
canonical-instrument version scheme.

### Timestamp and completed-day construction

For this Candidate ingress, every source row's `t` must have exact runtime
type `int`. A `Decimal`, float, bool, string, null, subclass, or other value is
ineligible even if it is numerically integral.

`t` is Unix milliseconds for the start of the provider aggregate window. The
adapter converts it without a binary float by using exact integer division:

```text
whole_seconds, remaining_milliseconds = divmod(t, 1000)
source_utc = 1970-01-01T00:00:00+00:00
             + whole_seconds
             + remaining_milliseconds
```

The additions use integral seconds and milliseconds. Overflow or a value
outside the supported timezone-aware `datetime` range blocks construction.
There is no flooring, rounding, fractional-millisecond normalization, or float
conversion.

Candidate construction also fails when any required temporal conversion is
outside the supported platform or Python `datetime` range, including an
integer Unix-millisecond timestamp to UTC, UTC to `America/New_York` session-
date conversion, `requested_from` at New York midnight, the day after
`requested_to`, or the resulting New York-to-UTC observation-interval
conversion. The adapter does not wrap, clamp, substitute, or silently truncate
such a value. This is structural temporal representability, not market
validation.

The row's `session_date` is
`source_utc.astimezone(ZoneInfo("America/New_York")).date()`. The timestamp is
not publication, availability, close, completion, or effective time. The raw
timestamp remains only in the acquisition object and is absent from material
v1 rows.

The completed-day cutoff is:

```text
cutoff_session_date =
    query_as_of.astimezone(ZoneInfo("America/New_York")).date()
```

For every acquired row:

```text
session_date outside [requested_from, requested_to] -> fail construction
session_date >= cutoff_session_date                 -> exclude from material
session_date < cutoff_session_date                  -> retain in material
```

Duplicate session dates among any acquired source rows block construction,
including duplicates whose rows would otherwise be excluded by the completed-
day filter. The duplicate structural-correspondence gate is applied
independently from completed-day filtering. Retained rows are sorted by
strictly ascending `session_date`, independently of provider order.

The current New York calendar date and every strictly future New York calendar
date are therefore excluded. Their exclusion is solely the already-governed
v1 material-construction rule. It is not Evidence Validation, admission, proof
that future data is valid, acceptance of its market truth, or permission to
consume it. Out-of-request-bounds rows remain a construction failure. A future
material contract that instead makes strictly future rows a construction
failure requires separately versioned governance; this ADR does not
reinterpret material version `1.0.0`.

No exchange calendar, session-close rule, early-close rule, or publication lag
is used. A row is not rejected merely because its derived date is a weekend,
holiday, or unusual market day. Such source-quality questions belong to later
Evidence Validation.

### OHLCV canonical numeric text

This algorithm applies only to material `open`, `high`, `low`, `close`, and
`volume`. It does not apply to provider timestamp `t`; `t` must be an exact
Python `int` under the timestamp rule above, and an integral `Decimal`
timestamp produces no Candidate.

Each OHLCV input must have exact runtime type `int` or `Decimal`; `bool` is not
an integer for this contract. An exact `int` is converted mathematically with
`Decimal(integer_value)`, without binary float. A `Decimal` is used directly.
A non-finite `Decimal` blocks construction defensively.

The helper must not call `Decimal.normalize()`, `quantize()`, `float()`, or any
formatting or arithmetic whose result depends on the active Decimal context.
Its output is independent of `decimal.getcontext().prec`, rounding mode,
locale, and other process state. It derives the canonical text entirely from
the exact finite `Decimal.as_tuple()` sign, base-10 coefficient digits, and
integer exponent, using only integer and ASCII-string operations.

For zero, regardless of sign, coefficient spelling, or exponent, the result is
exactly `"0"`. No exponent-derived padding is allocated for zero.

For a non-zero value, let `sign`, `digits`, and `exponent` be the exact finite
Decimal tuple. The helper:

1. defensively removes leading zero digits from the base-10 coefficient;
2. removes trailing coefficient zero digits one at a time, incrementing the
   integer exponent by one for each removed digit; and
3. forms `D`, the ASCII coefficient digit string after that trimming, with
   `n = len(D)` and `e` equal to the resulting integer exponent.

The exact fixed-point body is then:

```text
if e >= 0:
    body = D followed by exactly e ASCII "0" characters
else:
    point = n + e
    if point > 0:
        body = D[:point] + "." + D[point:]
    else:
        body = "0." + exactly (-point) ASCII "0" characters + D
```

For a non-zero negative value, `canonical_text = "-" + body`; otherwise,
`canonical_text = body`. The decimal separator is always literal ASCII `.`.
Exponent notation and locale behavior are prohibited. A magnitude below one
always has a leading ASCII zero, and no insignificant trailing fractional zero
remains.

The v1 adapter freezes
`MAX_CANONICAL_NUMERIC_TEXT_LENGTH = 1024` ASCII characters, including an
optional leading minus, all digits, and an optional decimal point, applied
independently to each canonical OHLCV field. Before allocating exponent-
derived padding or the final string, the helper must calculate the exact final
length from the sign, trimmed coefficient digit count, integer exponent, and
decimal-point placement. Let `sign_length` be one for a negative non-zero value
and zero otherwise. The exact length calculation is:

```text
if e >= 0:
    body_length = n + e
elif n + e > 0:
    body_length = n + 1
else:
    body_length = 2 + (-(n + e)) + n

final_length = sign_length + body_length
```

The `2` in the last branch accounts for literal `0.`. This size check uses
bounded integer arithmetic and must not construct the output string to discover
its length. A final length greater than 1024 blocks Candidate construction
before allocating the text.

This is a deterministic canonical-serialization resource bound, not market
plausibility validation, a maximum price or volume, or a rounding rule.
Changing the bound is a governed construction-policy change; v0.78 freezes
1024 for this adapter version.

Examples:

```text
1
Decimal("1")
Decimal("1.0")
Decimal("1.000")
Decimal("1E+0")       -> "1"

Decimal("1.2300")
Decimal("123E-2")     -> "1.23"

Decimal("0.00120")    -> "0.0012"
Decimal("1E+3")       -> "1000"
Decimal("1E-3")       -> "0.001"
Decimal("-1.2300")    -> "-1.23"

0
Decimal("0")
Decimal("-0")
Decimal("-0.000")
Decimal("0E+999")     -> "0"
```

The repository `canonical_fingerprint` function receives these strings, never
`Decimal` values. V0.78 adds no generic Decimal codec.

### Canonical projection rules

All new fingerprints use the existing repository `canonical_fingerprint`
function. Maps therefore have lexicographically sorted keys in canonical JSON,
sequences project as JSON arrays in their defined order, UTF-8 and compact JSON
rules remain unchanged, and every fingerprint payload has a top-level
`schema_version`.

Dates are exact `YYYY-MM-DD` strings. Datetimes are the existing canonical
UTC `datetime.isoformat()` representation ending in `+00:00`. Unknown values
are JSON null. Booleans and integers remain JSON booleans and integers. OHLCV
numbers are the canonical strings defined above. No float or Decimal enters a
fingerprint payload.

An existing released reference or identity is embedded by its complete public
`to_dict()` projection, including its nested fingerprint. The adapter does not
reimplement the fingerprint payload of an existing model.

### Exact request-provenance projection

The material's `request_provenance` value is exactly:

```text
{
  "schema_version": "polygon_completed_daily_ohlcv_request_provenance/v1",
  "api_base": "https://api.polygon.io",
  "resolved_route": <acquisition.resolved_route>,
  "requested_ticker": <acquisition.requested_ticker>,
  "requested_from": <acquisition.requested_from as YYYY-MM-DD>,
  "requested_to": <acquisition.requested_to as YYYY-MM-DD>,
  "multiplier": 1,
  "timespan": "day",
  "adjusted": true,
  "sort": "asc",
  "limit": 50000
}
```

This nested projection has no independent fingerprint field. It is wholly
bound by the parent material fingerprint. The top-level material
`timespan="1_day"` describes the semantic bar interval; the nested
`timespan="day"` preserves the actual Polygon query parameter.

### Exact normalized-row projection

Each retained row is exactly:

```text
{
  "session_date": <YYYY-MM-DD>,
  "open": <canonical numeric string>,
  "high": <canonical numeric string>,
  "low": <canonical numeric string>,
  "close": <canonical numeric string>,
  "volume": <canonical numeric string>
}
```

There is no nested row `schema_version` or row fingerprint. ADR 0037 defines
these six fields as the exact row fields, and the parent
`polygon_completed_daily_ohlcv_material/1.0.0` schema versions their meaning.
Rows appear as one JSON array sorted by strictly ascending `session_date`.

### Exact existing source and material references

The material embeds this complete governed material-schema reference:

```text
{
  "schema_version": "evidence_material_schema_reference/v1",
  "schema_id": "polygon_completed_daily_ohlcv_material",
  "schema_version_id": "1.0.0",
  "schema_fingerprint":
    "sha256:37e1a00608ff7fb37c56e988a5472b28daa156fd434111bf26802f52ab88dfef",
  "fingerprint":
    "sha256:07a84ff0a6ba025e5e260d8f9a8b98ec011b57b933ad12992434a9390c95184b"
}
```

It also embeds this complete governed source reference:

```text
{
  "schema_version": "evidence_source_reference/v2",
  "namespace": "massive",
  "source_id": "stocks_custom_bars_1_day_adjusted_api_polygon_io",
  "source_version": "1.0.0",
  "authority": "external_origin",
  "source_fingerprint":
    "sha256:c3b76256ae621d8554fa7274f9e8b9b0f2bebe8c3a90a19b160af7be642983db",
  "fingerprint":
    "sha256:3665aff20d8bfded244d49ceb84c9bb1bebabd4f5ed79cacbd6d28c2509fb81f"
}
```

These values are the existing production-owned objects, projected with
`to_dict()`; the adapter does not reconstruct them from caller data.

### Exact external identity and mapping-resolution projection

`external_instrument_identity` is the complete existing
`ExternalInstrumentIdentity.to_dict()` value:

```text
{
  "schema_version": "external_instrument_identity/v1",
  "namespace": "polygon",
  "external_symbol": <exact requested ticker>,
  "external_venue": <exact string or null>,
  "fingerprint": <existing ExternalInstrumentIdentity fingerprint>
}
```

`mapping_resolution_provenance` is the complete existing
`InstrumentResolution.to_dict()` value, with no adapter-added or omitted
fields:

```text
{
  "schema_version": "instrument_resolution/v1",
  "external_identity": <complete ExternalInstrumentIdentity.to_dict()>,
  "mapping": {
    "schema_version": "instrument_mapping/v1",
    "external_identity": <complete ExternalInstrumentIdentity.to_dict()>,
    "canonical_instrument": {
      "schema_version": "canonical_instrument/v1",
      "instrument_id": {
        "instrument_id": <exact CanonicalInstrumentId.instrument_id>
      },
      "trading_identity": {
        "schema_version": "trading_instrument_identity/v1",
        "symbol": <exact canonical trading symbol>,
        "venue": <exact canonical trading venue>,
        "instrument_fingerprint": <trading identity fingerprint>
      },
      "asset_class": <"equity" or "etf">,
      "trading_currency": <exact uppercase currency>,
      "fingerprint": <CanonicalInstrument fingerprint>
    },
    "source": {
      "schema_version": "instrument_mapping_source/v1",
      "source_id": <exact mapping source ID>,
      "source_version": <exact mapping source version>,
      "configuration_fingerprint": <fingerprint string or null>,
      "fingerprint": <InstrumentMappingSourceIdentity fingerprint>
    },
    "valid_from": <canonical UTC datetime text>,
    "expires_at": <canonical UTC datetime text or null>,
    "fingerprint": <InstrumentMapping fingerprint>
  },
  "resolved_as_of": <the normalized query_as_of UTC datetime text>
}
```

`canonical_subject` is the complete
`EvidenceSubjectReference.to_dict()` projection:

```text
{
  "schema_version": "evidence_subject_reference/v1",
  "namespace": "canonical_instrument",
  "subject_id": <exact CanonicalInstrumentId.instrument_id>,
  "subject_version": "canonical_instrument/v1",
  "subject_fingerprint": <CanonicalInstrument fingerprint>,
  "fingerprint": <EvidenceSubjectReference fingerprint>
}
```

### Exact material projection

The material fingerprint payload is exactly the following map. No displayed
field may be omitted and no additional field may be added under material
version `1.0.0`:

```text
{
  "schema_version": "polygon_completed_daily_ohlcv_material/1.0.0",
  "material_schema": <complete governed material-schema reference above>,
  "source_reference": <complete governed source reference above>,
  "vendor_service": "massive.com_formerly_polygon.io",
  "api_base": "https://api.polygon.io",
  "route_template":
    "/v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{from}/{to}",
  "multiplier": 1,
  "timespan": "1_day",
  "adjusted": true,
  "sort": "asc",
  "limit": 50000,
  "external_instrument_identity":
    <complete ExternalInstrumentIdentity.to_dict()>,
  "canonical_subject": <complete EvidenceSubjectReference.to_dict()>,
  "mapping_resolution_provenance":
    <complete InstrumentResolution.to_dict()>,
  "start_session_date": <requested_from as YYYY-MM-DD>,
  "end_session_date": <requested_to as YYYY-MM-DD>,
  "query_as_of": <normalized UTC datetime text>,
  "market_timezone": "America/New_York",
  "session_scope": "polygon_qualifying_trades_all_sessions",
  "price_adjustment": "split_adjusted_not_dividend_adjusted",
  "adjusted_response": true,
  "request_provenance": <exact request-provenance projection above>,
  "provider_request_id": <exact provider string or null>,
  "rows": <ascending array of exact normalized-row projections>,
  "row_count": <nonnegative retained-row integer>
}
```

The material fingerprint is
`canonical_fingerprint(material_fingerprint_payload)`. A material's complete
inspection projection appends exactly one `fingerprint` field containing that
value; the fingerprint field is not part of its own fingerprint payload.

For `provider_request_id`, absent and present-null both project as JSON null.
A present non-null exact provider string is retained without an invented
length limit. Different non-null request IDs intentionally create different
material identity.

### Exact Evidence temporal identity

The adapter creates `EvidenceTemporalIdentity` with:

```text
observation_period_start = requested_from 00:00 America/New_York -> UTC
observation_period_end   = day after requested_to 00:00
                           America/New_York -> UTC
observed_at              = null
effective_from           = null
effective_until          = null
published_at             = null
source_revision          = exact material fingerprint
platform_received_at     = acquisition.response_received_at
artifact_created_at      = normalized explicit artifact_created_at
```

The half-open observation interval is DST-aware. The complete temporal
projection used by artifact versioning is the existing
`EvidenceTemporalIdentity.to_dict()` result:

```text
{
  "schema_version": "evidence_temporal_identity/v1",
  "observed_at": null,
  "observation_period_start": <canonical UTC datetime text>,
  "observation_period_end": <canonical UTC datetime text>,
  "effective_from": null,
  "effective_until": null,
  "published_at": null,
  "source_revision": <material fingerprint>,
  "platform_received_at": <canonical UTC receipt datetime text>,
  "artifact_created_at": <canonical UTC creation datetime text>,
  "fingerprint": <EvidenceTemporalIdentity fingerprint>
}
```

`query_as_of` remains material/query provenance only. No admission, evaluation,
freshness, inferred publication, or inferred effective time is created.

### Exact producer and Evidence provenance

The existing Evidence model has no `EvidenceProducerReference`. Its producer
field uses `EvidenceIdentityReference`, whose separate
`identity_fingerprint` is optional. The adapter uses this fixed code-owned
reference:

```text
{
  "schema_version": "evidence_identity_reference/v1",
  "namespace": "market_platform.evidence_ingress",
  "identity_id": "polygon_completed_daily_ohlcv",
  "identity_version": "1.0.0",
  "identity_fingerprint": null,
  "fingerprint":
    "sha256:16c2e69b6bd2727c020169f6828f3f40c354c53d96f079962419ae20d1770fcd"
}
```

No separate producer-definition fingerprint is required in v0.78. The fixed
namespace, identity, version, null optional fingerprint, and resulting
reference fingerprint are the complete producer identity. Callers cannot
select or replace it.

The adapter creates `EvidenceProvenance` with the governed source as `origin`,
the fixed reference above as `producer`, exactly one governed source reference,
no transformations, and no predecessors. Its complete projection is the
existing `EvidenceProvenance.to_dict()` result:

```text
{
  "schema_version": "evidence_provenance/v1",
  "origin": <complete governed source reference>,
  "producer": <complete fixed producer reference>,
  "source_references": [<complete governed source reference>],
  "transformations": [],
  "predecessors": [],
  "fingerprint": <EvidenceProvenance fingerprint>
}
```

No invented transformation identity represents numeric normalization or
mapping resolution. Their exact semantics and dynamic mapping provenance are
already bound by material and its governed schema.

### Exact artifact identity

The artifact-ID fingerprint payload is exactly:

```text
{
  "schema_version":
    "polygon_completed_daily_ohlcv_artifact_identity/v1",
  "governing_contract": {
    "schema_version": "evidence_contract_reference/v2",
    "namespace": "market_platform.evidence",
    "contract_id": "polygon_completed_daily_ohlcv",
    "contract_version": "1.0.0",
    "information_class": "source_measurement",
    "contract_fingerprint":
      "sha256:6a597eb424488b82eadf32e1e2fc2cbbab62bdfd4cac13816fd699fe872ea57e",
    "fingerprint":
      "sha256:e0c23300d19833cb6ed6743ae115385557e8362993adeef58a4db813afd381a0"
  },
  "canonical_subject_id": {
    "instrument_id": <exact CanonicalInstrumentId.instrument_id>
  },
  "requested_from": <exact YYYY-MM-DD>,
  "requested_to": <exact YYYY-MM-DD>
}
```

`artifact_id` is `canonical_fingerprint` of this payload. A changed material,
request ID, query time, receipt, creation time, mapping provenance, or source
correction does not change `artifact_id` while the contract, canonical stable
subject ID, and requested interval remain unchanged.

### Exact artifact version

The artifact-version fingerprint payload is exactly:

```text
{
  "schema_version":
    "polygon_completed_daily_ohlcv_artifact_version/v1",
  "artifact_id": <computed artifact_id>,
  "material_fingerprint": <exact material fingerprint>,
  "temporal_identity": <complete EvidenceTemporalIdentity.to_dict()>,
  "provenance": <complete EvidenceProvenance.to_dict()>
}
```

`artifact_version` is `canonical_fingerprint` of this payload. The adapter then
passes the computed ID and version, subject tuple, temporal identity,
provenance, and material fingerprint to the existing private governed Polygon
artifact wrapper. The existing `EvidenceArtifact` factory remains solely
responsible for the final artifact fingerprint; the adapter does not duplicate
that computation.

### Material and construction-gate classification

The boundary is fixed as follows:

| Class | Exact contents |
| --- | --- |
| Material identity | Complete material projection defined above, including request, source, external and canonical subject, complete mapping resolution, query as-of, adjusted-response proof, retained rows, and retained row count |
| Generic Evidence provenance | Governed origin, fixed producer, one governed source reference, empty transformations, empty predecessors |
| Evidence temporal identity | Requested half-open observation interval, material fingerprint as source revision, actual receipt, explicit creation; all unavailable source times null |
| Construction gates only | Response ticker, raw count metadata, results presence, pagination state/reference, exact raw timestamp after session-date derivation |
| Acquisition-only/transient | Raw timestamp, metadata presence distinctions after approved null projection, and sanitized pagination reference |

Credentials, API keys, HTTP headers, retry state, raw HTTP objects, HTTP clients,
raw `next_url`, sanitized `next_page_reference`, provider objects, and network
dependencies appear in none of these Evidence identities.

### Identity sensitivity

With every unlisted input held equal:

| Difference | Material | Artifact ID | Artifact version / final artifact fingerprint |
| --- | --- | --- | --- |
| Different non-null request ID | changes | same | changes |
| Different `response_received_at` | same | same | changes |
| Different `artifact_created_at` | same | same | changes |
| Different consistent count metadata | same | same | same |
| Counts absent versus present-null | same | same | same |
| Pagination absent versus present-null | same | same | same |
| Non-null next-page indication | no Candidate | no Candidate | no Candidate |
| Different requested bounds with the same retained rows | changes | changes | changes |
| Different `query_as_of`, same resolved canonical subject ID | changes | same | changes |
| Different `query_as_of`, different resolved canonical subject ID | changes | changes | changes |
| Different mapping provenance with the same canonical subject ID | changes | same | changes |
| Equivalent Decimal spellings for `open`, `high`, `low`, `close`, or `volume` | same | same | same |
| Corrected OHLCV | changes | same | changes |
| Response ticker absent versus present-null | same | same | same |
| Exact present-match response ticker versus unavailable | same | same | same |

Count and response-ticker metadata can only have the stated identity behavior
when they pass all construction gates. A mismatch produces no Candidate.

`query_as_of` enters material directly and also drives instrument resolution.
The artifact-ID payload does not hash `query_as_of`, but it does hash the
resolved canonical subject identity. A changed query time therefore affects
`artifact_id` indirectly exactly when it changes the resolved canonical
subject ID. Equivalent Decimal-spelling identity applies only to the five
canonical material OHLCV fields; a Decimal source timestamp produces no
Candidate even when it is numerically integral.

### Candidate lifecycle

Successful construction invokes the exact production-owned authorization and
returns a canonical material plus `EvidenceArtifact`. It creates no validation
record, admission record, validity event, freshness evaluation, `ACTIVE` state,
consumability conclusion, or research permission.

Candidate is inferred from absent admission history under ADR 0035. The adapter
does not add a Candidate enum or manufacture an `EvidenceAdmissionState`.
The result is unvalidated, unadmitted, not consumable, and not permitted for
research.

### Package and dependency direction

The implementation boundary, when separately authorized, is:

```text
market_platform.evidence_ingress.polygon_completed_daily_ohlcv
```

The allowed dependency direction is:

```text
market_platform.data.providers.polygon
    -> no Evidence dependency

market_platform.evidence_ingress.polygon_completed_daily_ohlcv
    -> Polygon acquisition types
    -> instrument domain types and resolve_instrument_mapping(...)
    -> Evidence models and private governed Polygon minting wrapper

market_platform.evidence
    -> no evidence_ingress or data-provider dependency
```

Provider acquisition remains separate from Evidence construction. The adapter
performs no network I/O. `DataProvider`, `PolygonProvider`, and the Evidence
root API remain unchanged, and no root-package export is added by this
architecture checkpoint.

### Legacy quarantine

The ingress must not reuse, convert through, or establish correspondence by
similar naming with pre-ADR-0035 semantic types, including:

- `StrategyEvidence`;
- `DailyResearchEvidence`;
- `CompletedDailyPriceSeries`;
- `HistoricalPriceSeries`;
- `DailyInstrumentIntegrityEvidence`;
- state-model `*Evidence` calculation records; or
- other legacy research, strategy, replay, or risk values named evidence.

No Candidate produced under this contract enters Daily Technical research.
ADR 0035 Evidence semantics and the ADR 0037 v0.79 bridge deferral govern.

## Consequences

- All previously open construction choices now have deterministic construction
  rules.
- Count absence remains visible as unknown while contradictory counts cannot
  mint a Candidate.
- Every row must pass the independent requested-bounds gate before completed-
  day filtering excludes current and strictly future New York dates.
- Caller-controlled query time cannot look ahead past actual source receipt.
- Existing instrument, Evidence reference, temporal, provenance, and final
  artifact projections are reused rather than duplicated.
- Equivalent exact numeric values share identity, while transport request IDs,
  query context, source vintages, and temporal receipt/creation remain
  distinguishable as prescribed.
- A successful Candidate still establishes neither validation nor source truth.

## Explicit exclusions

This decision does not implement or authorize:

- production code, tests, an ingress package, or a CLI;
- acquisition, HTTP, retries, pagination following, or network access;
- a new Evidence authorization or a modification to ADR 0037;
- a Polygon-specific instrument registry or research-registry dependency;
- persistence, caching, serialization transport, or artifact storage;
- Evidence Validation, admission, validity, freshness, consumability, or
  research use;
- exchange-calendar, regular-session, early-close, holiday, or market-quality
  validation;
- a generic Decimal framework or generic Evidence ingress framework; or
- any legacy Daily Technical or Strategy bridge.
