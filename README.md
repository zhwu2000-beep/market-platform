# Market Platform

Long-term AI investment research platform built with Python 3.14 and uv.

## Development

Install dependencies:

```bash
uv sync
```

Copy environment variables:

```bash
Copy-Item .env.example .env
```

Run checks:

```bash
uv run pytest
uv run ruff check .
uv run mypy src
```

## Architecture

See [docs/architecture.md](docs/architecture.md).
## Research CLI

The v0.30.0 research workflow produces a current composite market assessment.
It does not yet provide target prices, win probabilities, support/resistance,
position recommendations, or options strategies.

Table output example:

```bash
market-platform research run --symbol MSFT --horizon-days 20
```

```text
Symbol Status Requested Horizon               As Of Direction Strength Trend State Momentum State Volatility State Composite Score Classification                               Summary Warnings
 MSFT   ok                  20 2026-01-02T23:59:59+00:00   bullish   strong    positive       positive             high           0.72 strong_bullish MSFT's current composite signal is classified as bullish; the requested research horizon is 20 days. -
```

JSON output example:

```bash
market-platform research run --symbol MSFT --format json --output reports/research.json
```

```json
{
  "request": {
    "symbol": "MSFT",
    "horizon_days": 20,
    "provider": null,
    "as_of": "2026-01-02T23:59:59+00:00"
  },
  "status": "ok"
}
```
