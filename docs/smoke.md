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
