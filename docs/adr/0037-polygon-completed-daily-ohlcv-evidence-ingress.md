# ADR 0037: Polygon Completed-Daily OHLCV Evidence Ingress

## Status

Accepted.

This decision is the first checkpoint for v0.78.0. It defines the bounded
production contract but does not yet authorize implementation work beyond this
ADR.

## Context

ADR 0035 defines Evidence as an identified, versioned, provenance-bearing
representation of source observations, measurements, or assertions. It also
separates semantic authorization, validation, admission, validity, freshness,
and consumability. The v0.77.0 implementation deliberately contains an empty
production Evidence authorization catalog and no source adapter.

The repository already has a Polygon-named provider and a separate Daily
Technical research path. Polygon.io officially became Massive.com on
2025-10-30 without replacing the underlying service. During the announced
migration, `api.polygon.io` and `api.massive.com` operate in parallel and
existing integrations remain compatible. Brand or service continuity does not
make their hosts, endpoints, or acquisition profiles interchangeable for
Evidence authorization.

The current production provider uses `https://api.polygon.io` and calls the
Stocks Custom Bars endpoint at
`/v2/aggs/ticker/{ticker}/range/1/day/{from}/{to}` with `adjusted=true`,
`sort=asc`, and `limit=50000`. It requires the response's `adjusted` field to be
the exact boolean `true`, accepts finite numeric `t`, `o`, `h`, `l`, `c`, and
`v` values, derives the session date by converting `t` to
`America/New_York`, labels that date as midnight UTC, and sorts rows ascending.

Massive documents the stock aggregates as Eastern Time windows constructed
from qualifying trades and covering pre-market, regular-market, and
after-hours sessions. It documents `adjusted=true` as modifying historical
Aggregate OHLCV values to reflect stock splits, including the possibility that
adjusted volume is decimal, while dividend adjustment is not provided. The
endpoint supplies no publication timestamp or stable revision/vintage
identifier. The platform preserves the provider-reported adjusted values but
does not infer the provider's internal mathematical adjustment algorithm.

The existing Daily Technical path turns provider rows into its own released
research evidence, applies a New York civil-date cutoff, and may consume the
result. That path predates ADR 0035 Evidence Artifact semantics. It is not the
v0.78 Evidence ingress and must remain isolated from it.

## Decision

### Scope and dependency direction

V0.78 introduces exactly one production-governed ingress:
**Polygon completed-daily OHLCV for one canonically resolved U.S. equity or
ETF over one bounded interval**.

This is a dedicated source contract, not a universal Evidence adapter
framework. The eventual adapter must live outside `market_platform.evidence`.
It may depend inward on the Evidence and instrument contracts; the Evidence
domain must not depend outward on Polygon, the data-provider package, HTTP, an
API key, pandas, or any network client.

The adapter receives its Polygon daily-acquisition dependency through an
explicit constructor or call boundary. It reuses the existing injected HTTP
client/provider infrastructure and canonical instrument resolver where their
released contracts apply. Provider construction continues to validate
configuration lazily. No Evidence-domain object initiates network access.

### Exact governed identities

The first production membership is the exact conjunction below:

- vendor/service identity: `Massive.com (formerly Polygon.io)`;
- Evidence source namespace: `massive`;
- source ID: `stocks_custom_bars_1_day_adjusted_api_polygon_io`;
- source version: `1.0.0`;
- Evidence type: `polygon_completed_daily_ohlcv`;
- information class: `EvidenceInformationClass.SOURCE_MEASUREMENT`;
- material schema ID: `polygon_completed_daily_ohlcv_material`;
- material schema version ID: `1.0.0`;
- governing contract namespace: `market_platform.evidence`;
- governing contract ID: `polygon_completed_daily_ohlcv`;
- governing contract version: `1.0.0`;
- authorization ID: `production.polygon_completed_daily_ohlcv`; and
- authorization version: `1.0.0`.

The source reference retains `EvidenceAuthority.EXTERNAL_ORIGIN`. Its canonical
reference fingerprint is part of exact membership. The governed vendor/service
identity is Massive.com, formerly Polygon.io. The governed capability is only
Stocks Custom Bars / Aggregates:
`GET /v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{from}/{to}`. Neither
the vendor identity nor this route family authorizes another Massive/Polygon
capability.

`source_version=1.0.0` identifies the exact acquisition profile implemented by
the reviewed production provider: API base `https://api.polygon.io`, the route
above with multiplier `1` and timespan `day`, `adjusted=true`, `sort=asc`,
`limit=50000`, exact adjusted-response proof, ET window/session meaning, and
the normalization described by this ADR. The provider's internal name
`polygon` and the external-instrument namespace `polygon` remain compatibility
identities for this implementation; neither is the Evidence source identity
by itself.

A new source version is required if the provider, API base/host, upstream route
family, timespan/window construction, adjustment flag or meaning,
qualifying-trade or session coverage, timestamp interpretation,
pagination/completeness behavior, or source-response semantics changes.
`https://api.massive.com` is not authorized by v0.78 merely because the vendor
states that it is compatible with `https://api.polygon.io`; migration to that
base requires an explicit reviewed acquisition-profile/source-contract version
change unless governance first proves and records that the new request remains
within the exact governed profile. A corporate rebrand alone does not change
Evidence authority. Credentials, deployment location, retry count, HTTP-client
implementation, and receipt time do not by themselves change source version.

A new material schema version is required for a field, type, ordering,
duplicate, missing-value, numeric-normalization, interval, or material-
fingerprint change. A new Evidence contract version is required for a change
to evidence type, subject correspondence, temporal meaning, authority,
information class, lifecycle promises, or admissible semantic scope. A change
in any governed dimension requires a newly reviewed exact authorization
membership; versions never acquire broader meaning in place.

The material-schema fingerprint and any optional source/contract definition
fingerprints must be static repository constants derived from their complete
normative definitions. They must not be computed from caller-supplied
definitions at runtime.

### Canonical subject and symbol correspondence

The caller supplies an exact Polygon `ExternalInstrumentIdentity` and an
explicit mapping `as_of`. The external identity namespace is `polygon`; its
case-sensitive ticker is the ticker sent to Polygon. It is resolved through
the existing canonical instrument mapping boundary. Resolution must yield
exactly one active `CanonicalInstrument`, otherwise ingress fails closed.

The source response ticker, when present, must exactly equal the requested
Polygon ticker. Every normalized row must correspond to that same ticker. The
artifact subject is an `EvidenceSubjectReference` for the resolved
`CanonicalInstrumentId`, with the canonical-instrument schema version and
fingerprint retained. Uppercasing a caller's free-form symbol is not canonical
instrument resolution and cannot replace it. The mapping identity,
fingerprint, and `resolved_as_of` belong in provenance/material identity.

### Exact bounded material contract

One `polygon_completed_daily_ohlcv_material/1.0.0` value is an immutable
envelope containing exactly:

- the material schema identity and version;
- the exact governed source reference;
- `vendor_service=massive.com_formerly_polygon.io`;
- `api_base=https://api.polygon.io` and the exact Stocks Custom Bars route
  template;
- multiplier `1`, timespan `day`, `adjusted=true`, `sort=asc`, and
  `limit=50000` as the exact acquisition profile;
- the exact Polygon external identity;
- the exact canonical subject and mapping-resolution provenance;
- the inclusive requested `start_session_date` and `end_session_date`;
- the explicit UTC `query_as_of` used for completion filtering;
- `market_timezone=America/New_York`;
- `timespan=1_day`;
- `session_scope=polygon_qualifying_trades_all_sessions`;
- `price_adjustment=split_adjusted_not_dividend_adjusted`;
- `adjusted_response=true`; and
- an ordered tuple of zero or more rows containing exactly `session_date`,
  `open`, `high`, `low`, `close`, and `volume`.

Actual request provenance is the exact API base, resolved route, external
ticker, inclusive date bounds, and fixed non-credential query semantics in
this envelope, plus the provider request ID when the response supplies one.
It must correspond exactly to the governed acquisition profile. A request
through another base, including `api.massive.com`, cannot be relabeled as this
profile. API keys and other credentials are never provenance fields.

The requested dates are exact dates with
`start_session_date <= end_session_date`. Both endpoints are inclusive. A row
is retained only when its New York session date lies in that interval and is
completed under the rule below. A request or response that cannot demonstrate
bounded completeness within the provider's `50000` base-aggregate limit,
including an unconsumed `next_url` or inconsistent count metadata, fails
closed rather than yielding a partial artifact.

Each source `t` must be a finite numeric Unix-millisecond value. Its canonical
row label is the civil date obtained by converting that instant to
`America/New_York`; the source instant must not be misrepresented as the bar's
publication or completion time. Rows are canonically ordered by strictly
ascending `session_date`. Multiple rows resolving to the same session date are
duplicates and reject the entire material. Provider order is not trusted as
canonical order.

`o`, `h`, `l`, `c`, and `v` are required. JSON null, booleans, strings,
NaN, infinities, absent fields, and other non-numeric values reject the
material. Finite integer and decimal-compatible source numbers are normalized
to one canonical base-10 representation: no exponent, no insignificant
trailing fractional zeros, and zero is never negative. The source number's
mathematical value is preserved; no rounding, price rescaling, unit
conversion, gap filling, or derived OHLCV calculation is allowed. Structural
normalization is not Evidence Validation. Market plausibility, OHLC
relationships, and source truth remain unvalidated in v0.78.

`volume` is the provider-reported aggregate `v` value. Under this exact
`adjusted=true` acquisition profile it is classified as provider-reported
split-adjusted aggregate volume. It may be non-integral and must therefore use
the decimal-capable numeric normalization above rather than an integer-only
contract. The platform preserves the exact normalized numeric value returned
by the governed profile. It does not independently assert, reconstruct, or
invent the provider's exact mathematical split-adjustment formula, and it
performs or represents no dividend adjustment.

No row is synthesized for a weekend, holiday, halt, or interval with no
qualifying trade. A missing session is represented by the absence of a row,
not by nulls or a zero-volume bar. The material may be empty, but emptiness is
visible through row count and is not proof of complete source coverage.

The material fingerprint is the repository canonical SHA-256 fingerprint of
the complete envelope above, excluding only the fingerprint field itself.
Consequently it binds source/version, external and canonical identity,
mapping provenance, interval, query as-of, temporal/session and adjustment
semantics, normalized row order, every OHLCV value, and row count. Equivalent
source numeric spellings normalize to one fingerprint; a changed row,
correction, bound, subject, mapping, or semantic version changes it.

The Evidence Artifact ID is the stable canonical fingerprint of an identity
projection containing the governing contract reference, canonical subject ID,
and inclusive requested session-date interval. The artifact version is the
canonical fingerprint of a version projection containing that artifact ID,
the exact material fingerprint, complete temporal identity, and complete
provenance. The artifact fingerprint remains the ADR 0035
`EvidenceArtifact` fingerprint over the complete artifact projection. This
separates a stable semantic series from a particular received vintage and
prevents a later correction or later receipt from reusing an artifact version.

### Daily-bar and corporate-action semantics

The governed bar is Polygon's one-day Stocks Custom Bars aggregate, not a
platform-computed exchange-calendar bar and not a regular-hours-only bar. Its
window is labeled in `America/New_York`, is constructed from Polygon-qualifying
trades, and covers Polygon's pre-market, regular-market, and after-hours stock
sessions. `open`, `high`, `low`, and `close` retain Polygon's meanings within
that window; `volume` retains the bounded meaning above.

For `query_as_of`, let `cutoff_session_date` be its civil date in
`America/New_York`. A completed daily bar must have
`session_date < cutoff_session_date`. Thus the entire current New York date is
excluded, even after the regular or extended session has closed. This
conservative rule avoids claiming an intraday bar is final and matches the
existing repository's completed-date cutoff without coupling the two paths.
Future support for same-day post-close completion would require a new contract
with an explicit trading calendar, early-close rules, source publication lag,
and correction window.

Polygon is authoritative only for which qualifying-trade aggregate rows it
returns. V0.78 does not embed or validate an exchange holiday calendar and
does not infer that every weekday is a trading session. Future-dated rows,
current-date rows after completion filtering, out-of-bound rows, and duplicate
session dates fail closed or are excluded only as explicitly stated by this
contract; they are never silently relabeled.

The response must prove exact boolean `adjusted=true`. Under the governed
vendor semantics, historical Aggregate OHLCV values are adjusted for stock
splits, adjusted volume may be decimal, and no dividend adjustment is
represented. The platform performs no additional corporate-action processing
and does not claim the provider's internal adjustment formula. A later split
or vendor correction may therefore cause a repeated query for an earlier
interval to return different values. Such a response is a new source vintage
and new material/artifact version; it never rewrites an earlier artifact.

### Temporal model

The source and artifact times remain distinct under ADR 0035:

- **Observation/reference interval:**
  `observation_period_start` is the first inclusive requested session date at
  midnight `America/New_York`, converted to UTC, and
  `observation_period_end` is the day after the last inclusive requested
  session date at midnight `America/New_York`, converted to UTC. The interval
  is half-open and preserves daylight-saving transitions. Individual row
  session dates remain in the material. `observed_at` is inapplicable to a
  multi-row interval and is absent.
- **Effective time:** OHLCV aggregates do not have a separate platform-defined
  effective interval in v0.78; `effective_from` and `effective_until` are
  absent rather than copied from another timestamp.
- **Publication/source availability:** the endpoint supplies no per-row or
  response publication timestamp. `published_at` is absent. Availability is
  not inferred from a session close, response timestamp, or plan-recency
  description.
- **Source revision/vintage:** the Massive/Polygon service supplies no stable
  revision ID. The material fingerprint is the source-vintage identity retained
  in `source_revision`. Re-fetching identical normalized material preserves
  that vintage; any source correction or split-driven historical change
  creates a different vintage.
- **Receipt time:** `platform_received_at` is the explicit UTC instant at which
  the complete provider response was received by the adapter. It is not a
  publication, observation, or completion time.
- **Artifact creation time:** `artifact_created_at` is the explicit UTC instant
  at which the immutable Evidence Artifact was created, and must not precede
  receipt. It is not receipt or source availability.
- **Task/query as-of:** `query_as_of` is caller-supplied, UTC-normalized, and
  determines both instrument-mapping resolution and the conservative
  completed-date cutoff. It is retained in material/query provenance, not
  collapsed into the artifact's source times. Later validation/admission or
  consumption evaluation uses its own explicit `knowledge_as_of` and
  `effective_as_of` under ADR 0035.

No one of these timestamps substitutes for another. In particular, receipt or
artifact creation does not prove that a bar was published, final, fresh, or
known at an earlier task as-of.

### Authority and information class

The exact authority is always `EvidenceAuthority.EXTERNAL_ORIGIN` because the
represented aggregates originate with the Massive.com service, formerly
Polygon.io, and its external market-data sources, not a platform-owned system
of record. The corporate rebrand and API-domain migration do not create a
platform-origin observation and therefore do not change this authority.

The exact information class is
`EvidenceInformationClass.SOURCE_MEASUREMENT`. OHLCV values are numerical
aggregations of qualifying source trades, so they are measurements rather
than prose/assertions and are not a platform-authored observation. Provider
access, canonical instrument mapping, normalization, fingerprinting,
validation, storage, CLI projection, or any other platform processing can
never promote them to `PLATFORM_ORIGIN`.

### First production authorization and fail-closed membership

V0.78 introduces the first exact production-approved Evidence contract
membership. The production trust root must remain private, production-owned,
immutable/static in code, and limited to exact positive membership. Callers
cannot obtain or replace the catalog, inject a runtime catalog, register a
contract, issue an approval, mutate membership, or use a public factory to
grant production approval.

The ingress API accepts no authorization argument and exposes no issuer,
resolver, approval lookup, or minting handle. An artifact or CLI projection
may describe the authorization identity required for audit, as the released
artifact contract already does, but that passive value gives its holder no
authority to create another production artifact.

`EvidenceContractAuthorization` describes a conjunction; possession,
serialization, copying, fabrication, or reconstruction of an equal-looking
value does not grant approval. Artifact creation must resolve the candidate
against the private production membership and use the internally governed
record.

Acceptance tests must demonstrate fail-closed rejection of reconstructed or
near-matching contracts, including mismatches in any of:

- source namespace, identity, source version, or source fingerprint;
- material schema identity, version, or schema fingerprint;
- Evidence contract namespace, identity, version, or contract fingerprint;
- authorization identity or version;
- Evidence authority; or
- Evidence information class.

No wildcard, compatible-version range, fallback source, caller equality hook,
subclass, alternate catalog, or partial field comparison may grant membership.

### Artifact lifecycle

The dedicated v0.78 adapter may return the canonical material together with
an `EvidenceArtifact` created under the exact governed authorization. This
means only that the artifact is semantically authorized to represent that
source/material contract.

For every artifact returned by the v0.78 ingress:

```text
semantic authorization = exact production membership
validation             = not completed; no validation records
admission              = absent; Candidate under ADR 0035
consumable             = false
```

Authorization is not validation. Validation is not admission. Admission is not
consumability. An admission record cannot be manufactured by this path, and
the absence of an admission record must not be projected as an implicit pass.
The v0.78 artifact has no claim to `Passed`, `Admitted`, `Active`, or fresh-for-
task status and cannot enter Specialist Intelligence or research consumption.

Production authorization is not proof that a Polygon row is true, complete,
accurate, internally coherent, fresh, final against later corrections, or
suitable for research. It proves only that governance recognizes the exact
semantic source/material conjunction as eligible to produce a Candidate
Evidence Artifact.

### Existing-pipeline isolation

V0.78 must not change the current Daily Technical research semantic path,
provider-selection behavior, released Daily Technical contracts, fingerprints,
or results. The new Evidence Artifact cannot be converted, projected, or
passed into `CompletedDailyPriceSeries`, Daily Technical analysis,
Interpretation, Assessment, or Strategy. There is no fallback between paths.

The bridge from admitted Evidence to Daily Technical is deferred to v0.79 and
requires separately reviewed validation, admission, freshness, validity, and
consumption correspondence. Similar source values or matching material
fingerprints do not create that bridge.

### Read-only CLI inspection

The eventual v0.78 CLI command is a read-only acquisition-and-inspection path.
It may resolve a canonical instrument, acquire the bounded material, create
the Candidate artifact, and print a deterministic projection. It must not
persist, validate, admit, activate, consume, analyze, or publish the artifact.

Its projection must make at least these values explicit:

- artifact ID, version, schema version, and fingerprint;
- `External-Origin` authority and `Source-Measurement` class;
- Massive.com-formerly-Polygon.io vendor/service identity;
- exact Stocks Custom Bars capability and governed `api.polygon.io`
  acquisition-profile source identity and version;
- actual request provenance: API base, route, ticker, interval, and fixed query
  semantics, with credentials excluded;
- canonical subject identity and fingerprint;
- requested query interval, query as-of, and observation interval;
- row count and latest completed bar session date, or explicit absence;
- material schema version and material fingerprint;
- `validation=not_completed`;
- `admission=absent_candidate`;
- `consumable=false`; and
- an explicit warning that the artifact is unvalidated, unadmitted, and not
  approved for research use, including `NOT PERMITTED FOR RESEARCH` or an
  exactly equivalent unmistakable statement.

The CLI must not use words such as valid, admitted, approved evidence, ready,
fresh, verified, or research-ready for this lifecycle state.

## Consequences

- The Evidence foundation gains one narrow, reviewable production trust-root
  membership without a public authorization mechanism.
- Massive/Polygon daily material has canonical service, capability,
  acquisition-profile, request-provenance, subject, numeric, temporal, session,
  adjustment, revision, and fingerprint semantics.
- External authority and Candidate lifecycle state remain visible after
  platform processing.
- Provider/network ownership remains outside the Evidence domain and remains
  injectable for mocked boundary tests.
- A later source-semantic or contract change requires an explicit new version
  and governance review rather than silent compatibility.
- V0.79 must add validation/admission and an explicit Daily Technical bridge
  before this Evidence can become consumable.

## Reconnaissance limits

The existing provider and official Massive documentation establish the
vendor/service continuity, current repository API base, endpoint,
qualifying-trade aggregate, all-session ET scope, split-not-dividend adjustment,
split-adjusted decimal-capable volume, response fields,
timestamp-at-window-start meaning, and source ordering option. They do not
expose a publication timestamp, stable source revision identifier, or the exact
internal mathematical algorithm used to transform adjusted OHLCV values.

Those limits do not leave the governed material ambiguous: publication remains
absent, normalized material content is the vintage identity, and each OHLCV
number is the exact normalized provider-reported split-adjusted value. The
provider's internal transformation algorithm is not part of the platform
contract unless it is separately documented and governed.

## Explicit exclusions

V0.78 does not include:

- persistence, databases, repositories, caches, retention, or retrieval of a
  prior artifact;
- automated Evidence Validation, admission, validity, freshness approval, or
  consumability;
- Daily Technical consumption or changes to its existing semantic path;
- Strategy changes;
- watchlists;
- Agents, Agent exposure, LLMs, or multi-Agent orchestration;
- portfolio or account logic;
- Risk Control or risk approval;
- Trade Governance, planning, order intent, or authorization;
- execution, broker integration, or broker submission;
- FRED, SEC, News, Options, or any other provider/source ingress;
- generic plugin loading, a generic Evidence adapter framework, or a generic
  adapter registry;
- runtime authorization injection, public authorization catalogs, public
  issuers, mutators, registration, or generic authorization APIs; or
- any bridge that represents the Candidate artifact as admitted or consumable.
