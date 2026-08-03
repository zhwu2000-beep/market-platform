# Smoke Workflow

This document standardizes the real-provider smoke workflow for market data
commands in v0.22.0.

Separate offline validation from real-provider smoke checks:

1. `uv run ruff check src tests`
2. `uv run mypy src`
3. `uv run pytest --basetemp W:\AI\Projects\market-platform.pytest-temp`
4. `.\scripts\smoke_twelve_data.ps1`
5. Cleanup generated files
6. Merge, tag, and push

Real-provider smoke requires `TWELVE_DATA_API_KEY`.

The smoke workflow may create:

- `.market-platform/cache/`
- `tmp\smoke_twelve_data\`

Recommended smoke commands:

```powershell
.\scripts\smoke_twelve_data.ps1
```

If you want to run the checks manually instead of the script, use:

```powershell
uv run market-platform data providers health --provider twelve_data --format table
uv run market-platform data fetch --symbol MSFT --start 2026-07-01 --end 2026-07-08 --provider twelve_data --format json --cache --refresh
uv run market-platform data fetch --symbol MSFT --start 2026-07-01 --end 2026-07-08 --provider twelve_data --format json --cache
uv run market-platform data latest --symbol MSFT --provider twelve_data --format table --cache --refresh
uv run market-platform data latest --symbol MSFT --provider twelve_data --format table --cache
uv run market-platform data intraday --symbol AAPL --interval 5min --provider twelve_data --format csv --cache --refresh
uv run market-platform data intraday --symbol AAPL --interval 5min --provider twelve_data --format csv --cache
```

Cleanup commands:

```powershell
Remove-Item -LiteralPath .market-platform\cache -Recurse -Force
Remove-Item -LiteralPath tmp\smoke_twelve_data -Recurse -Force
```

If the smoke passes, continue with merge, tag, and push for the release.
## Historical replay context window

`--start` and `--end` are inclusive evaluation dates. Use `--context-start` to
acquire and retain earlier daily bars for signal and structure context without
creating replay steps before `--start`:

```powershell
uv run market-platform replay run --symbol MSFT --context-start 2026-01-01 --start 2026-03-01 --end 2026-03-31 --format json
```

When `--context-start` is omitted it defaults to `--start`. `--max-bars` limits
only evaluation-window rows; context rows do not consume that limit.

Replay provenance is an additive programmatic boundary. The existing CLI table,
JSON, and CSV schemas intentionally remain result-only; callers that require run
identity use `HistoricalReplayService.run_execution()` with an explicit
`SoftwareRevision`.

Versioned Replay artifacts are also programmatic in v0.50.0. Construct an
`HistoricalReplayArtifact` from that execution and use
`save_historical_replay_artifact()`, `load_historical_replay_artifact()`, or
`verify_historical_replay_artifact()`. The CLI has no artifact flags or commands,
and existing smoke output is unchanged. Artifact files contain Replay results and
provenance but do not contain canonical OHLCV rows.

Historical Replay experiments are programmatic and in-memory in v0.51.0. Load or
construct verified Artifacts separately, create an
`HistoricalReplayExperimentSpecification`, and call
`create_historical_replay_experiment()`. Comparison performs no provider access,
Replay execution, or file I/O. Existing CLI and smoke output remain unchanged.

Historical Replay internally precomputes exact observation fingerprints in
v0.52.0. Required rows are projected and JSON-encoded once, while the complete
legacy SHA-256 byte stream is still hashed for each evaluated prefix. This changes
no CLI option, output schema, observation digest, Replay result, Artifact, or
experiment behavior. Benchmark validation should continue to use an output path
outside the repository and must confirm the established 100/300/500-bar result
fingerprints and exact production/instrumented parity.

Historical Replay research workflows are synchronous, programmatic, and
in-memory in v0.53.0. Construct explicit member and workflow specifications from
one `HistoricalPriceSeries`, inject `HistoricalReplayService`, and call
`HistoricalReplayResearchWorkflowService.run()`. The workflow creates existing
Replay Artifacts and, when all requested candidates succeed, the existing
Historical Replay Experiment. It performs no provider access or file I/O and adds
no CLI command or smoke output. Existing provider-facing `research run` behavior
is unchanged.

The v0.54.0 historical research application boundary is also synchronous and
programmatic. Decode a strict inline request through
`HistoricalReplayResearchApplicationRequest.from_dict()`, inject the built-in or
custom safe resolvers and the existing workflow service, then call
`HistoricalReplayResearchApplicationService.execute()`. Its response dictionary
is a bounded identity/status summary; complete Artifacts and the optional
Experiment remain accessible only through the typed in-memory workflow result.
No CLI, provider, filesystem, HTTP, TradingView, Agent, or broker smoke behavior
is added.

The v0.55.0 trading-signal foundation is domain-only and programmatic. Construct
a `TradingSignal` with explicit source event identity, venue-qualified
instrument, exact `Decimal` target, and finite validity window. Evaluate it at an
explicit time and call `create_order_intent_from_signal()` with the fixed
`ExactTargetPositionIntentPolicy`. The result is a pre-risk target-position
proposal, not authorization or a broker order. No CLI, provider, filesystem,
network, HTTP, TradingView, account, risk, persistence, or execution smoke
behavior is added.

The v0.56.0 application boundary remains synchronous and programmatic. Decode a
strict `TradingSignalApplicationRequest` or `OrderIntentApplicationRequest`, then
invoke the corresponding explicit service. Inputs use bounded visible-ASCII
identities, fixed-point Decimal text, and aware RFC-3339 timestamps; responses
are bounded domain identity projections. This is not authenticated ingress or
durable idempotent processing, and it adds no CLI, HTTP, TradingView, account,
risk, persistence, broker, provider, filesystem, or network smoke behavior.

The v0.57.0 instrument foundation is also domain-only and programmatic.
Construct bounded canonical, external, and mapping-source identities; create
explicit UTC temporal mappings; and call `resolve_instrument_mapping()` with an
explicit `as_of`. Resolution fails closed for duplicates, missing or inactive
records, ambiguity, and conflict. It does not alter v0.56 requests and adds no
snapshot, registry, persistence, provider, broker, TradingView, HTTP, account,
risk, execution, CLI, Agent, filesystem, or network smoke behavior.

The v0.58.0 trading-state foundation is domain-only and programmatic. Construct
explicit source and paper/live account identities, then construct independently
timed immutable cash, position, open-order exposure, and market-quote snapshots.
Collections accept exact built-in lists or tuples, enforce fixed count limits,
sort by semantic identity, reject duplicates, and fingerprint exact canonical
Decimal and UTC content. Freshness and skew evaluation require explicit times
and limits and never consult a clock. Parallel snapshots do not imply atomic
capture. This release adds no bundle, application command, persistence,
provider/broker adapter, TradingView/HTTP behavior, risk decision, execution,
CLI, Agent, filesystem, network, or real-provider smoke action.


The v0.59.0 structural-risk foundation is also domain-only and programmatic.
Construct a `StructuralRiskPolicy`, explicit `RiskEvidenceCoverage`, and a
`RiskEvaluationContext` containing one released Order Intent, one released
Instrument Resolution, and all four independently timed v0.58 snapshots. Call
`evaluate_structural_risk()` with no clock, I/O, or external service.

The evaluator reconstructs released inputs and applies stage-gated intent,
mapping/instrument, account, freshness/skew, coverage, and quote checks.
`approved` means only that the supplied evidence passed those structural checks
at the explicit evaluation time. It is not financial sufficiency, human
approval, short authorization, or broker execution authority. A later answer
requires a new context and evaluator run; there is no `valid_until` or
revalidation helper.

V0.59 adds no provider or broker call, persistence, TradingView/HTTP behavior,
application command, execution plan, CLI, Agent, filesystem, network, or
real-provider smoke action. Its smoke coverage is the offline focused and
compatibility test suites plus the unchanged Historical Replay fingerprint
benchmark.

The v0.60.0 position-target translation foundation is likewise domain-only and
programmatic. Supply an exact approved `RiskEvaluationContext`, its corresponding
`RiskDecision`, and the same canonical UTC evaluation time to
`translate_position_target()`.

Illustrative mechanical results are:

| Target | Current complete-account position | Result |
|---|---:|---|
| long 10 | long 4 | target `10`, current `4`, delta `6`, `buy` |
| flat | long 4 | target `0`, current `4`, delta `-4`, `sell` |
| short 3 | short 3 | target `-3`, current `-3`, delta `0`, `no_action` |
| long 10 | any target open-order exposure | unavailable; no netting |

These are bounded audit translations, not orders or permission to trade or
short. Planning at another time requires new evidence, context, risk decision,
and translation. V0.60 adds no provider/broker call, filesystem behavior,
application command, CLI, TradingView, approval, submission, or real-provider
smoke action.

V0.60 offline validation includes 197 focused translation tests, 870 focused
v0.55-v0.60 compatibility tests, the reconciled 648-test wider compatibility
selection, and 2,408 passed with one established skip repository-wide. Deleted
or structurally fabricated retained snapshot headers and rows are translated at
the narrow execution-planning correspondence boundary; unexpected programming
exceptions continue to propagate.

The v0.61.0 broker-neutral execution-instruction foundation consumes one exact
canonical `PositionTargetTranslation` through
`derive_broker_neutral_execution_instruction()`:

| Translation delta/action | Result |
|---|---|
| `+6`, `buy` | one `buy` instruction with positive quantity `6` |
| `-4`, `sell` | one `sell` instruction with positive quantity `4` |
| `0`, `no_action` | exactly `None`; the translation remains the audit artifact |

The instruction projection contains side, positive fixed-point quantity, source
translation fingerprint, canonical instrument evidence, account fingerprint,
and copied `plan_as_of`. It contains no market/limit/stop field, price, TIF,
route, broker symbol/account, or executable payload. No market-order default is
implied.

The instruction remains a non-executable acquisition/disposal proposal. It is
not financial, short, compliance, human, or broker authorization and cannot be
submitted. V0.61 adds no provider/broker call, filesystem, network, clock,
persistence, application service, CLI, TradingView, or live-order behavior.

V0.61 offline validation includes 85 focused instruction tests, 955 focused
v0.55-v0.61 compatibility tests, the complete reconciled 648-test wider
compatibility selection, and 2,493 passed with one established skip
repository-wide. The current execution-planning API contains the original eight
v0.60 exports plus exactly four v0.61 additions, for twelve exports total and
exactly two fingerprint families.

The v0.62.0 explicit order-style choice foundation is domain-only:

| Construction | Result |
|---|---|
| `OrderStyleChoice(OrderStyle.MARKET)` | explicit `market` choice |
| `OrderStyleChoice(OrderStyle.LIMIT)` | explicit `limit` choice with no price |
| `OrderStyleChoice()` | rejected; no implicit market default |
| `OrderStyleChoice("market")` | rejected; strings are not coerced |

The projection contains only schema, lowercase style, and fingerprint. The
choice has no price, TIF, time, instruction, account, instrument, authorization,
or broker field. MARKET is not immediate execution or submission authority, and
LIMIT is not yet an order specification.

V0.62 offline validation includes 51 focused style-choice tests, 1,006
focused v0.55-v0.62 compatibility tests, the complete reconciled 648-test
wider compatibility selection, and 2,544 passed with one established skip
repository-wide. Mypy covers 168 source files. The execution-planning API
preserves the original twelve exports and adds exactly three v0.62 names for
fifteen total; exactly three execution-planning fingerprint families exist.
The ten-path implementation remains unstaged, uncommitted, and READY FOR REVIEW.
