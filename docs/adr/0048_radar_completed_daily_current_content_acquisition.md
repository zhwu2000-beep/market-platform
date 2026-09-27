# ADR 0048: Radar Completed-Daily Current Content Acquisition

## Status

Accepted

This ADR freezes production acquisition semantics for v0.83 completed-daily
Radar `CURRENT_MARKET_CONTENT_LOOKUP`. It records decisions only; production
adapter implementation remains separate work. It changes no source, tests,
dependencies or frozen research behavior.

## Context and inspected baseline

- Branch: `feature/v0.83.0-radar`.
- HEAD: `9daf760eeb1f5e0e9137fd2f39863661839bb907`.
- Parent: `e0ae06566d8b7929c0f0a4876606e6ed38aa2e5c`.
- Local `main` and local `origin/main`:
  `1e60406a153105eca2b76db735635b8553108827`.
- Worktree and index were clean before drafting; refs were inspected without
  fetching.
- [ADR0046](0046_radar_exchange_session_calendar_foundation.md) and
  [ADR0047](0047_radar_core_gate_profile_and_pipeline_contracts.md) remain Accepted,
  frozen and unchanged. ADR0048 is the next available number.

The existing session/content Trigger compares completed session, content scope
and normalized content identity. Its production binding must preserve:

```text
same completed session + same comparable current market content -> UNCHANGED
```

A stale local cache cannot establish current upstream equality. Calendar
completion, provider availability and content identity remain separate facts.
The decisions below apply narrowly to v0.83 completed-daily Radar.

## Decision 1: Fixed 250 completed-session window

Current content uses exactly **250 completed exchange sessions**, inclusive of
`calendar.latest_completed_session(as_of)`. The start is the 249th previous
completed session. Expected labels come from Radar's `ExchangeSessionCalendar`,
not provider rows, calendar-day subtraction or a RadarProfile.

This bounds cost, keeps same-session reruns at exactly the same scope, provides
initial history for current lightweight technical calculations, avoids growing
history cost and avoids Profile-specific raw observation identity. Weekends,
holidays and intraday clock movement do not move the scope while the latest
completed session remains unchanged.

Never shorten the window for recently listed instruments, missing bars or
provider gaps. If 250 valid expected sessions cannot be established or supplied,
current content is not `PRESENT`; Decision 7 determines unavailability or failure.

When a new completed session arrives, `history_start` rolls forward by one
session. This is intentional: after validating current correspondence, the
Trigger returns `NEW_COMPLETED_SESSION` before same-session scope/fingerprint
comparison. This does not bypass current-content acquisition or validation.
Raw checkpoint state does not include a RadarProfile fingerprint.

## Decision 2: Full bounded refresh when current content is evaluated

Whenever `CURRENT_MARKET_CONTENT_LOOKUP` is actually resolved, the complete
250-session comparison range must be freshly acquired from the production
provider path for this execution. Facts remain lazy: an execution that never
requests history need not acquire it. Decision 9 permits sharing the same fresh
acquisition within that execution.

No same-session `UNCHANGED` decision may rely solely on previously cached CSV
content. `MarketDataCache` may serve unrelated CLI/data workflows, but is not a
freshness or equality authority for Radar. Failed refresh must never fall back
to cached content to emit `PRESENT`. If trustworthy current bounded content
cannot be acquired, return `UNAVAILABLE` or fail under Decision 7.

`UNCHANGED` means equality against the successfully acquired and validated
provider response for this execution. It does not mean that no correction can be
published after that response.

## Decision 3: Metadata-preserving Polygon acquisition

Use the existing `PolygonProvider.get_completed_daily_acquisition` production
transport boundary and its `PolygonCompletedDailyAcquisition` result. The generic
DataFrame daily path is not authoritative here: it discards pagination/count
correspondence metadata needed to judge the acquisition.

Before emitting `PRESENT`, the adapter must verify:

- the exact requested external ticker and exact requested start/end bounds;
- a present, acceptable response adjusted flag that is exact boolean `true`;
- response ticker correspondence when supplied;
- no additional page is indicated;
- results are present and nonempty;
- metadata, including supplied counts and presence/value correspondence, has no
  contradiction invalidating the response;
- exact expected Calendar session coverage and valid OHLCV representation.

The configured Polygon daily request remains `adjusted=true`. Radar v1 content
is **split-adjusted, non-dividend-adjusted completed daily OHLCV**, consistent
with `RadarMarketContentScope` v1. This asserts no stronger corporate-action
semantics than the existing repository contracts support. Optional metadata
must be interpreted according to its contract, not invented equivalences
between differently defined counts.

## Decision 4: Exact completed-session coverage

The conceptual validation sequence is:

1. Compute `latest = calendar.latest_completed_session(as_of)` using the fixed
   evaluation as-of instant.
2. Navigate 249 previous sessions to obtain `start`. Obtain the ordered expected
   tuple from `calendar.sessions_in_range(start, latest)` and require exactly
   250 completed sessions ending at `latest`.
3. Acquire only the inclusive bounded `[start, latest]` range using the trusted
   external provider symbol and validate acquisition metadata.
4. Convert each raw daily timestamp to its exchange-local session date using
   existing Polygon `America/New_York` daily-label semantics, including DST.
5. Reject duplicate timestamps or session labels, non-session labels and labels
   outside the requested bounds. Never drop or merge offending rows to make
   coverage appear complete.
6. Order accepted labels chronologically and require the complete label tuple
   to equal the expected Calendar tuple exactly. Missing latest/internal
   sessions are unavailable, not an invitation to shrink the range or fill bars.
7. Verify mapping correspondence throughout the retained window and validate
   OHLCV. Represent each accepted session date consistently as midnight UTC for
   `HistoricalPriceSeries`, not as the actual session open or close instant.
8. Only after coverage validation construct normalized history and its content
   fingerprint; only fully validated content may be `PRESENT`.

Radar uses ADR0046 actual-close Calendar semantics, including exact-close
inclusion and early closes. Calendar completion does not prove provider
publication. Frozen research completed-daily cutoff behavior is unchanged and
must not be reused as Radar's completion authority.

## Decision 5: Current content identity

`HistoricalPriceSeries.content_fingerprint` remains the market-content identity.
Do not introduce a second Radar-specific OHLCV hashing algorithm. Supply the
existing identity implementation with a trusted canonical trading symbol
representation, consistent midnight-UTC daily labels and normalized OHLCV
values. The canonical symbol used in normalized history is distinct from the
external symbol used to request Polygon data.

Provider name, retrieval time, request ID, mapping provenance, cache metadata,
Evidence identity and research metadata remain outside this fingerprint.
`RadarCurrentMarketContent` contains:

- `instrument`: the requested `CanonicalInstrumentId`;
- `completed_session`: `latest`;
- `content_scope`: `RadarMarketContentScope(start, latest)`;
- `normalized_market_content_identity`:
  `HistoricalPriceSeries.content_fingerprint`.

Equal scope is required before same-session identity comparison. Content
inequality is not a MeaningfulChange classification or research authority.

## Decision 6: Historical instrument mapping correspondence

Reuse existing pure instrument mapping contracts and resolution. Never assume
that a canonical display/ticker string equals the Polygon request symbol. Use
the trusted external identity's provider symbol for acquisition.

Every retained daily session must have mapping coverage that resolves
unambiguously to the requested `CanonicalInstrumentId`. The same supported
mapping correspondence must hold across the entire retained window; do not
stitch different mappings or infer continuity from matching ticker text.

Reuse the repository's conservative daily historical-coverage rules where
applicable: supported mapping boundaries are midnight UTC, `valid_from` is
inclusive and `expires_at` is exclusive, and every daily label requires the
same exact unambiguous selected mapping. The historical all-row coverage logic
in `application/polygon_completed_daily_production_qualification.py` is a
semantic precedent only. Do not invoke qualification, Evidence admission or
other governed lifecycles, or import their research cutoff as Radar completion.

Expected missing/inactive mapping or unavailable historical coverage makes
content unavailable. Ambiguous, conflicting or duplicate mappings, or resolution
to another canonical instrument, fail. Unsupported partial-day mapping
boundaries fail rather than being inferred or rounded into daily coverage.

## Decision 7: Unavailable versus failure

Expected `UNAVAILABLE` conditions include:

- typed `NetworkError` or `RateLimitError`, or another explicitly typed temporary
  provider condition;
- a provider response behind the latest completed session;
- an empty or absent result set;
- a missing expected internal session;
- a valid indication that another page is required;
- expected mapping not found/inactive or historical coverage unavailable.

Failure conditions include:

- credentials, authentication or configuration errors;
- malformed or contradictory provider response metadata, including invalid
  request/response correspondence or unacceptable adjustment metadata;
- malformed, nonfinite or invalid OHLCV;
- duplicate timestamps/session labels;
- non-session or out-of-range daily labels;
- ambiguous, conflicting or duplicate mapping, or mapping to another canonical
  instrument;
- unsupported partial-day mapping boundaries;
- unsupported Calendar/venue coverage;
- programming errors or invalid fingerprint construction.

Malformed content must not be hidden by an otherwise expected unavailable
condition. A valid pagination indication is unavailable; malformed pagination
metadata is failure. A trustworthy short response is unavailable; contradictory
count metadata is failure.

Generic `DataProviderError` is **not automatically temporary**. Do not classify
by exception message text. Until an explicitly typed temporary-HTTP distinction
exists, unclassified generic provider errors fail conservatively, including
generic provider 5xx errors. This ADR requires no shared HTTP exception taxonomy
change. Failures propagate through existing execution failure handling; they
are not synthetic `UNAVAILABLE`, `UNCHANGED` or ordinary Gate dispositions.

## Decision 8: No CSV cache as Radar equality authority

Reject cache-only current-content `PRESENT`, cache fallback after failed refresh
and `cache-hit => UNCHANGED` for v0.83. The current CSV cache does not encode:

- canonical instrument correspondence;
- Calendar completeness;
- adjustment policy;
- current upstream revision identity;
- Radar acquisition-policy revision.

Diagnostic or performance caching may be reconsidered later under an explicit
freshness contract. Existing cache availability is not such a contract.

## Decision 9: Execution-local history reuse

Use one provider acquisition and normalization per instrument evaluation when
history is actually requested. Conceptually introduce a reusable completed-daily
history fact/result from which `CURRENT_MARKET_CONTENT_LOOKUP` and future
technical facts derive. Future indicator facts consume the same validated
`HistoricalPriceSeries` rather than refetching history.

`RadarEvaluationContext` fact loaders are independent zero-argument callables.
The production binding may therefore share one private per-evaluation lazy
history producer among those loaders. It must:

- remain execution-local, with no process-global cache;
- retain success, unavailability and ordinary failure consistently, without
  retrying acquisition through a different fact loader;
- perform at most one acquisition per instrument execution;
- expose read-only fact results, with no Gate-to-Gate publishing or mutable
  scratchpad.

Private memoization retains the producer's outcome; it is not a Gate output
channel or durable observation state. Concrete fact names and private helper
layout remain implementation details.

## Decision 10: Synchronous fact-loader boundary

`RadarEvaluationContext` uses synchronous zero-argument fact loaders. Do not put
event-loop management into `RadarEvaluationContext`,
`RadarSessionContentTriggerGate` or `RadarPipeline`.

The production adapter accepts or constructs a synchronous acquisition boundary
appropriate for its runtime composition. The existing Polygon acquisition
method is async; bridging to/from it belongs in outer runtime/composition code
with explicit event-loop semantics. Do not assume a generic internal
`asyncio.run` that fails inside an existing event loop. This freezes ownership,
not a new async framework. Keep provider HTTP access behind injected clients and
configuration validation lazy.

## Decision 11: Non-authority

The completed-daily production adapter remains Radar infrastructure. It does not
create, validate, admit or qualify Evidence; publish governed Technical,
Interpretation, Assessment or Strategy; create `RadarCandidate`; classify
MeaningfulChange; or authorize trading. A freshly acquired market-content result
is only a shallow scanning input, independent of the governed research chain.

## Consequences

Benefits are honest same-session correction detection within the retained
250-session scope, bounded request size, deterministic comparable scope and one
acquisition reusable by future Radar facts. No governed research chain is needed
to establish this scanning input.

Costs are intentional:

- Each symbol requires one bounded provider refresh whenever current content is
  evaluated; very large or frequently evaluated universes may be expensive.
- Corrections outside the retained 250-session range are not detected.
- Newly listed instruments with fewer than 250 required sessions are unavailable
  under v0.83.
- Generic provider 5xx classification may remain conservative until typed
  transport errors improve.

These are deliberate v0.83 tradeoffs, not universal permanent requirements.
Changing them requires an explicit later decision preserving honest scope and
freshness correspondence.

## Rejected alternatives

| Alternative | Reason rejected for v0.83 |
| --- | --- |
| Latest-bar-only refresh | Misses same-session corrections elsewhere in the retained comparison range. |
| Cache-only equality | Cached equality does not establish current upstream equality. |
| Cache fallback after provider failure | Masks inability to obtain trustworthy current content. |
| Earliest-available/full-history identity | Creates variable or growing scope and cost instead of the fixed bounded contract. |
| Profile-dependent comparison windows | Couples raw observation identity to Profile behavior. |
| Research completed-daily preparation as Radar completion authority | Uses frozen research cutoff semantics instead of actual-close Calendar semantics. |
| Evidence lifecycle as Radar acquisition | Adds governed authority dependencies to a shallow scanning input. |
| Separate provider fetch per future indicator Gate | Duplicates cost and can supply inconsistent content within one execution. |

## Non-goals

This ADR adds no production adapter, async framework, cache redesign, shared HTTP
error taxonomy, concrete indicator Gate, Profile, persistence, scheduler,
candidate lifecycle or governed research integration. It changes neither
ADR0046/ADR0047 nor frozen research semantics. Implementation and its tests are
separate work; no tests or network requests are part of this documentation task.
