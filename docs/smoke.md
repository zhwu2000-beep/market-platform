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
