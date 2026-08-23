# ADR 0032: Daily technical strategy application boundary

## Status

Accepted for v0.75.0.

## Context

V0.72 established verified daily technical research, v0.73 established the
Interpretation and Assessment domain layers, and v0.74 established the
Strategy domain layer. Callers still need one application operation that
composes those released domain boundaries without taking ownership of their
semantics or coupling a transport to the domain.

The application operation must begin from verified research. Accepting an
unverified daily research result would let callers bypass the instrument and
history integrity boundary. Reusing the historical `ResearchResult` or the
legacy `Strategy` model would also join distinct semantic families and weaken
the explicit daily technical lineage.

## Decision

`market_platform.application` owns the transport-neutral orchestration for the
daily technical Strategy use case. Domain packages do not import the
application layer, and the application boundary does not own acquisition,
presentation, persistence, or transport behavior.

The public operation is an async
`DailyTechnicalStrategyApplicationService`.

### Application request contract

The request type is `DailyTechnicalStrategyApplicationRequest`. Its schema
name is `daily_technical_strategy_application_request`, its version is `v1`,
and the exact retained `schema_version` value is
`daily_technical_strategy_application_request/v1`.

The request retains exactly:

- `verified_research`: an exact
  `IntegrityCheckedDailyTechnicalResearchResult`;
- fixed `schema_version`; and
- computed `request_fingerprint`.

Raw daily research, `DailyTechnicalResearchResult`, and historical
`ResearchResult` are not accepted substitutes. Verified daily research is a
mandatory input, not an optional enrichment or a value reconstructed by the
service. The request contains no caller-selected policy, policy identity,
presentation option, transport metadata, or execution setting.

The application request owns `request_fingerprint`. It is computed by the
application request from exactly the fixed request schema and the complete
canonical `verified_research` projection; callers do not supply it and domain
objects do not own it. It identifies only the normalized application intent
to apply the v0.75 fixed application profile to those exact verified research
semantics. The fixed request schema binds that profile, so the profile is not
duplicated as a request field.

`request_fingerprint` is not a fingerprint of any domain value, is not proof
of domain authorship, and is not a replacement for research, Interpretation,
Assessment, or Strategy lineage. Domain correspondence continues to use the
released domain fingerprints and explicit semantic checks. V0.75 adds exactly
this one application fingerprint family. It adds no response, pipeline,
aggregate, or other application fingerprint family.

### Fixed application profile and policy binding

The service receives the following three policies through dependency
injection:

- `DailyTechnicalInterpretationPolicy`
- `DailyTechnicalAssessmentPolicy`
- `DailyTechnicalStrategyPolicy`

The v0.75 application profile is the closed tuple of released classic
identities, including each identity's exact kind, policy ID, revision, typed
configuration, configuration schema, and fingerprint:

- Interpretation: `classic_daily_technical@1.0.0` with its released default
  `ClassicDailyTechnicalInterpretationConfiguration`;
- Assessment: `classic_daily_technical_coherence@1.0.0` with its released
  default `ClassicDailyTechnicalAssessmentConfiguration`; and
- Strategy: `classic_daily_technical_strategy@1.0.0` with its released default
  `ClassicDailyTechnicalStrategyConfiguration`.

Before any domain stage executes, the service captures and validates the
three injected policy identities and requires each complete identity to equal
the corresponding expected identity from that fixed profile. A mismatch
fails the application call before the Interpretation policy is invoked. The
profile is application-owned and is not a caller-selectable registry or
transport input.

Dependency injection permits replacement of a policy implementation only
when the replacement implements the matching released semantics and exposes
the exact expected released identity. It does not permit arbitrary policy
families to be substituted under v0.75. A different semantic family requires
an explicit future application-profile and contract-version decision.

### Orchestration and correspondence

The service composes the released domain boundaries in exactly one direction:

```text
IntegrityCheckedDailyTechnicalResearchResult
    -> DailyTechnicalInterpretation
    -> DailyTechnicalAssessment
    -> DailyTechnicalStrategy
```

Interpretation is derived from the verified research with the injected
Interpretation policy. Assessment is derived from that Interpretation with the
injected Assessment policy. Strategy is derived from that same Interpretation
and its matching Assessment with the injected Strategy policy. Each policy is
invoked once per application call through its released domain composition
boundary.

### Application response contract

The response type is `DailyTechnicalStrategyApplicationResponse`. Its schema
name is `daily_technical_strategy_application_response`, its version is `v1`,
and the exact retained `schema_version` value is
`daily_technical_strategy_application_response/v1`.

The success response retains exactly:

- `application_request_fingerprint`: the submitted request's exact
  `request_fingerprint`;
- `interpretation`: the complete in-memory
  `DailyTechnicalInterpretation` domain value;
- `assessment`: the complete in-memory `DailyTechnicalAssessment` domain
  value;
- `strategy`: the complete in-memory `DailyTechnicalStrategy` domain value;
  and
- fixed `schema_version`.

The three domain fields retain the complete domain objects, not summaries,
flattened copies, or independently reconstructed projections. The response
does not retain the request or verified research again; its request binding is
`application_request_fingerprint`, while the retained domain values preserve
their released lineage. External JSON, dictionary, or transport serialization
is a separate future bounded-projection decision. Complete in-memory retention
does not require unlimited external payload exposure. The response has no
computed fingerprint.

Response construction performs application correspondence validation across
the complete chain. It must establish that:

- the Interpretation corresponds to the request's verified research;
- the Assessment corresponds to that Interpretation;
- the Strategy corresponds to that Interpretation and Assessment;
- instrument, analysis time, source fingerprints, and policy identities agree
  wherever the released contracts require them; and
- the response cannot pair the request with unrelated, reordered, or
  independently produced domain results.

Application correspondence validation verifies relationships between
completed artifacts by checking types, identities, lineage, and the links
already defined by the domain contracts. Domain runners and policies remain
the sole authorities for semantic validation. The application layer only
orchestrates the completed artifacts and validates their correspondence; it
must not recompute Interpretation states, Assessment findings or outcome, or
Strategy modes or rule codes.

The boundary is success-only. Exceptions propagate without retry, fallback,
translation to an alternate policy, rollback, or a partial response. A failure
at any stage produces no application response.

Async preserves the established async verified-research workflow boundary for
future end-to-end composition and avoids introducing a synchronous seam into
that call path. It does not claim that the application service performs or
owns I/O. The service starts from a completed verified result, and its three
domain stages remain ordered and dependent rather than concurrent.

### Parallel research ontology

The existing `research-workflow-v1` ontology remains parallel and untouched.
`DefaultResearchWorkflow`, the `research run` command, and `ResearchResult`
remain separate from this application boundary. They are not inputs,
adapters, migration surfaces, or compatibility targets for the daily
technical Strategy operation, and no conversion is defined in either
direction.

This application boundary also does not reuse or adapt the legacy
`market_platform.strategy.Strategy` family. It does not populate or consume
`ResearchResult.strategy_candidates` or `ResearchResult.position_actions`.

## Deferred Scope

V0.75 adds no CLI command or rendering, HTTP or other transport adapter,
provider acquisition, persistence, cache, queue, retry policy, fallback
policy, rollback mechanism, or partial-result contract.

Any future CLI for this use case must invoke
`DailyTechnicalStrategyApplicationService`. The CLI may own only input parsing,
response rendering, and process exit-code mapping. It must not call the three
domain runners directly, reproduce their ordering or correspondence checks,
or otherwise create a second copy of domain orchestration. Any acquisition and
verification needed to produce the request's `verified_research` belongs to a
separate boundary, not to CLI-owned domain orchestration.

Automatic scheduling or recurring execution management is also a non-goal.
Scheduling, watchlists, recurring jobs, and operational execution belong to a
separate future operational layer.

Trade Planning remains a separate future layer. The response contains no
entry price, stop loss, profit target, quantity, position target, risk
allocation, order intent, execution instruction, broker mapping, submission,
or other trading action. V0.75 adds no Trade Planning, risk evaluation or
decision, broker integration, execution, or scheduling authority.

## Consequences

Callers gain one async, transport-neutral application operation for the
verified daily research-to-Strategy pipeline. Dependency injection remains an
implementation seam within the fixed v0.75 profile; it is not a policy-family
selection feature. The ordering and lineage of results remain fixed and
validated.

The application service introduces no second source of domain semantics and no
compatibility bridge to `research-workflow-v1`, historical research, or legacy
Strategy models. Future CLI, HTTP, UI, Agent, Trade Planning, risk, broker,
execution, or scheduling work is not part of this decision.
