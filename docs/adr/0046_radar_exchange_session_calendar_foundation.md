# ADR 0046: Radar Exchange Session Calendar Foundation

## Status

Accepted

The architecture decision is approved based on the completed v0.83 Exchange
Calendar Adoption Spike. This ADR records that decision only. It adds no
production implementation or dependency and does not authorize changes to frozen
v0.82 semantics. Implementation and dependency adoption remain separate work.

## Context and inspected baseline

- Branch: `feature/v0.83.0-radar`.
- HEAD, local `main`, and local `origin/main`:
  `1e60406a153105eca2b76db735635b8553108827`.
- v0.82.0 is fully released and frozen.
- Worktree and index were clean before drafting; refs were inspected without
  fetching.
- ADR0043, ADR0044 and ADR0045 exist; ADR0046 was the next available number.

v0.83 introduces Radar: wide, shallow, inexpensive, non-authoritative market
scanning before selected instruments are escalated into governed research:

```text
Radar -> selected candidate -> escalation boundary -> existing v0.82 Governed Research
```

Radar Gate 0 needs reliable regular-session dates, opens, actual closes,
early-close facts, previous/next sessions, latest completed sessions, and ordered
session ranges. The project previously lacked a reliable expected-exchange-session
capability. These are infrastructure facts, not investment or Evidence authority,
and do not replace governed Evidence Freshness.

The approved spike ran outside the repository in an isolated TEMP environment on
Python 3.14.6. All 573 TEMP-only assertions passed. No repository calendar
implementation or permanent calendar dependency exists at this decision point.

## Decision 1: Market-platform-owned contract

Freeze the conceptual `ExchangeSessionCalendar` contract with exactly these eight
public operations. `aware datetime` denotes a timezone-aware standard-library
`datetime`, not a new public type:

```text
is_session(session_date: date) -> bool
session_open(session_date: date) -> aware datetime
session_close(session_date: date) -> aware datetime
is_early_close(session_date: date) -> bool
previous_session(session_date: date) -> date
next_session(session_date: date) -> date
latest_completed_session(as_of: aware datetime) -> date
sessions_in_range(start: date, end: date) -> tuple[date, ...]
```

The concrete Python protocol/class location, private helper layout, and concrete
owned error names are not frozen by this ADR. Do not add a generic multi-exchange
registry or scheduling framework to satisfy this contract.

## Decision 2: Public types, ranges and errors

Public date/time inputs and outputs use Python standard-library `date` and
`datetime` values. pandas `Timestamp`, `DatetimeIndex`, `DataFrame`, and other
backend-specific types must remain inside the adapter. `session_open()` and
`session_close()` return timezone-aware UTC datetime values.

`session_open()`, `session_close()`, and `is_early_close()` require a real session.
A holiday/weekend input fails through market-platform-owned calendar errors; it
must not be silently reinterpreted as another session. `is_session()` returns
false for a non-session date within supported coverage.

`latest_completed_session()` rejects naive datetime values without assuming a
local timezone. `sessions_in_range()` rejects `start > end`. Valid ranges return
an ordered tuple of dates, include either endpoint when it is a session, and
contain no non-session dates. A range containing no sessions returns an empty
tuple.

The adapter must define and know its supported date coverage. Queries outside
that coverage, or requiring an answer beyond it, fail explicitly through
market-platform-owned calendar errors. Do not guess or extrapolate schedules.
Backend-specific exception classes must not become public contract types.
The TEMP proof of concept's 2025-2027 coverage is not a frozen production horizon.

## Decision 3: Strict navigation and actual-close completion

`previous_session(date)` returns the nearest exchange session STRICTLY BEFORE
the supplied calendar date. `next_session(date)` returns the nearest session
STRICTLY AFTER it. Neither returns the input date even when it is a session.
For example, previous-session navigation from a Monday session returns the prior
Friday or earlier exchange session. Weekend/holiday inputs return the nearest
earlier/later session respectively.

`latest_completed_session(as_of)` returns the most recent regular session whose
ACTUAL regular-session close satisfies `session_close <= as_of`. It is based on
close time, not merely calendar date. Before open, during the session, or just
before close, the current session is not yet completed. Weekend/holiday queries
return the preceding completed session, subject to supported coverage.

Exact-close inclusion is mandatory:

| Session | As-of time in ET | Latest completed session |
| --- | --- | --- |
| Normal 16:00 close | 15:59:59.999999 | Previous completed session |
| Normal 16:00 close | 16:00:00 | Current session |
| 2026-11-27 early close | 12:59:59.999999 | Previous completed session |
| 2026-11-27 early close | 13:00:00 | 2026-11-27 |

Early-close completion uses the actual early close; it never waits until the
normal 16:00 ET close. `is_early_close()` is a public fact so callers need not
infer it by comparing against a hard-coded 16:00 ET value.

DST handling must come from authoritative timezone/calendar behavior, not fixed
UTC offsets. Regular 09:30-16:00 ET sessions legitimately have different UTC
opens/closes across U.S. DST transitions. Extended-hours trading is outside this
regular completed-daily-session contract.

Session completion and provider availability are separate facts:

```text
exchange session completed != provider data available
```

A completed session does not imply that Polygon or any other provider has
published or delivered its completed daily bar.

## Decision 4: Initial backend and private venue mapping

Select **A: `exchange-calendars == 4.13.2` behind a market-platform-owned adapter**.
market-platform owns the contract and semantics; third-party libraries supply
replaceable infrastructure implementations:

```text
market-platform ExchangeSessionCalendar contract
-> market-platform adapter
-> exchange-calendars backend
```

Public market-platform trading venue identity remains **NASDAQ**. In 4.13.2,
the spike independently verified that both `get_calendar("NASDAQ")` and
`get_calendar("XNAS")` resolve to `XNYSExchangeCalendar`, with backend name
`XNYS`. Its tested 2026 schedule matched all supplied Nasdaq acceptance facts.

`NASDAQ -> XNYS` is a PRIVATE adapter implementation mapping. It does not prove
Nasdaq and NYSE are universally identical or historically/future equivalent.
`XNYS` must not leak into canonical instrument identity, external instrument
identity, operator mapping documents, Evidence, Radar public results, Radar
Profile identity, public `ExchangeSessionCalendar` results, or other
market-platform domain contracts. Backend replacement must not require changing
the public `NASDAQ` identity or the released operator mapping.

Use exchange-calendars as an external dependency; do not vendor or modify its
source. Any future fork/vendor decision requires separate evidence and review.

## Decision 5: Dependency rationale and evaluated alternative

The approved initial backend pin is `exchange-calendars == 4.13.2`. The spike
verified published/runtime metadata consistent with Python `>=3.10,<4`, a
Python 3.14 support classifier, and published license `Apache-2.0`. It ran
successfully in the isolated Python 3.14.6 environment. These license statements
record published metadata only, not legal conclusions.

The implementation task must validate dependency resolution against the actual
market-platform project environment and lockfile before adoption is committed.
The spike used pandas 3.0.6 and NumPy 2.5.3; it did not establish compatibility
with every version allowed by project constraints or modify the project lock.

Selection reasons:

1. It passed all bounded contract and Nasdaq reference checks.
2. It ran successfully on Python 3.14.6.
3. It provides required session navigation, open/close and early-close facts
   directly.
4. It can remain hidden behind a small market-platform-owned interface.
5. Reuse avoids owning complete holiday, exceptional-closure and historical
   session tables within market-platform.
6. It avoids an additional package/API layer with no demonstrated contract
   advantage.

`pandas-market-calendars == 5.4.0` was also evaluated. It passed the bounded
functional checks, ran on Python 3.14.6, publishes an MIT license, and depends on
exchange-calendars. Its tested NASDAQ path resolves to its NYSE implementation.
It has its own schedule implementation; it is not characterized as defective
or incorrect, or merely as forwarding every call to exchange-calendars.
It is not selected because it demonstrated no material semantic advantage for
this contract while adding another package/API layer.

## Spike reference validation

The approved spike checked these operator-supplied Nasdaq 2026 regular-session
references. Both candidates matched every row:

| Date | Expected and observed result |
| --- | --- |
| 2026-01-01 | Closed |
| 2026-01-19 | Closed |
| 2026-02-16 | Closed |
| 2026-04-03 | Closed |
| 2026-05-25 | Closed |
| 2026-06-19 | Closed |
| 2026-07-03 | Closed |
| 2026-09-07 | Closed |
| 2026-11-26 | Closed |
| 2026-12-25 | Closed |
| 2026-11-27 | Early close at 13:00 ET |
| 2026-12-24 | Early close at 13:00 ET |

Validation also covered fourteen nearby ordinary weekdays at 09:30-16:00 ET;
previous/next navigation across weekends, Good Friday, Independence Day observed,
and Thanksgiving; latest-completed behavior before/during/after a regular session,
on weekends and holidays, and around early closes; exact regular-close and
early-close inclusion; both U.S. DST transitions and UTC conversions; inclusive
ordered ranges; naive timestamp rejection; reversed-range handling; backend
exception containment; and coverage failures.

For 2026, the tested backend produced **251 sessions** and exactly the two supplied
early-close dates. Both candidates' full 2026 session dates, opens, closes and
early-close flags agreed. The approved 573 assertions include adapter-derived
behavior, not a claim that every contract operation is native to each library.

These validations establish fitness for the bounded Radar regular-session
contract. They do NOT prove universal Nasdaq/NYSE equivalence or correctness for
every historical/future exceptional closure.

## Decision 6: Radar Gate-0 role and authority boundary

The calendar foundation supports a future Gate-0 question:

```text
last_observed_session + latest_completed_session(as_of)
-> determine whether a newer expected regular session exists
```

The calendar supplies the session fact only. It does not decide whether a
provider bar arrived, observed OHLCV changed, the change is material, an instrument
becomes a Radar Candidate, or Governed Research should execute. Those decisions
belong to later Radar contracts; none is defined here.

`ExchangeSessionCalendar` MUST NOT by itself:

- create or validate Evidence;
- establish governed Evidence Freshness, admit Evidence, activate validity, or
  qualify Evidence;
- create Bridge output;
- publish Technical, Interpretation, Assessment, or Strategy;
- create a Radar Candidate or determine MeaningfulChange;
- invoke Governed Research;
- make investment recommendations;
- create order intent or execution authority.

The calendar remains non-authoritative Radar infrastructure. Calendar facts may
support later observation reasoning but grant no Evidence validity, admission,
research authority, or investment authority. Frozen v0.82 governed semantics
remain unchanged.

## Decision 7: Replacement and maintenance

Backend names, pandas types, other library types, dispatcher/caching details, and
backend exceptions remain private. Future replacement must preserve the public
contract. Dependency/library changes must never silently change instrument
identity. Backend version may appear in internal diagnostics.

Official-reference regression tests should protect the bounded semantics, and
project tests should explicitly cover NASDAQ-facing behavior, including strict
navigation, exact-close inclusion, early close, DST, supported coverage, owned
errors, and the distinction between completion and data availability. These are
requirements for later implementation, not tests added or run by this ADR task.

The principal known risk is calendar correctness outside tested dates,
especially exceptional closures. Exceptional closures and new calendar releases
require regression awareness. Manage this through the market-platform-owned
contract, bounded official-reference regression tests, and a replaceable adapter
backend rather than duplicating the entire exchange holiday database internally.

## Non-goals

This ADR does not define or implement:

- generic RadarGate, RadarProfile, or RadarPipeline;
- MeaningfulChangePolicy or material_numeric_movement;
- watchlist persistence or previous-observation persistence;
- candidate prioritization, scheduler/trigger implementation, or batch symbol
  orchestration;
- Governed Research composition;
- Fundamental Radar, Macro Radar, or Options Radar;
- Strategy Playbooks or backtesting;
- execution, broker integration, or Shadow Observer.

No additional Radar contracts, production code, dependencies, test changes,
`pyproject.toml` changes, or `uv.lock` changes are part of this decision-record task.
