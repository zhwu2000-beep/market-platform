# Data Providers

Provider implementations live in `src/market_platform/data/providers`.

The platform starts with:

- Polygon
- Twelve Data

The architecture reserves room for:

- Finnhub
- SEC EDGAR
- FRED
- News data
- Options data

Application code should depend on the unified `DataProvider` interface rather
than a concrete vendor client.

## Preferred Entry Point

Upper layers should prefer:

```python
from market_platform.data import get_provider

provider = get_provider("polygon")
```

Provider names are normalized, so `get_provider(" POLYGON ")` also works.
Provider construction remains lazy, and a missing `POLYGON_API_KEY` fails only
when `PolygonProvider` actually makes a request.

## Provider Switching

`get_provider("polygon")` returns `PolygonProvider`, and
`get_provider("twelvedata")` returns `TwelveDataProvider`. Both providers
implement the shared `DataProvider` interface, and provider names are
normalized before lookup.

Both providers currently support `get_daily_prices()`. Polygon also supports
`get_latest_price()` and `get_intraday_prices()`. Twelve Data intraday and
latest price methods are still not implemented.

## Routing

`MarketDataService.get_daily_prices(symbol, start, end)` uses configured
provider order and fallback when `provider` is not specified. Passing
`provider="polygon"` or `provider="twelvedata"` selects that provider only and
disables fallback for that call.

## Provider Comparison

`compare_daily_prices()` compares two already-normalized daily OHLCV
DataFrames. `compare_provider_daily_prices()` fetches daily prices from two
provider instances and then compares the normalized results.

The comparison output includes matched timestamps, `left_only` timestamps,
`right_only` timestamps, `close_diff`, `close_diff_pct`, and `volume_diff`.
This is comparison only, not fallback. It does not choose the better provider
automatically.

## Provider Responsibilities

Concrete providers are responsible for a narrow boundary:

- Read provider credentials from `Settings`.
- Send network requests through the shared `HTTPClient`.
- Convert provider JSON payloads into the canonical DataFrame schemas.
- Normalize timestamps to UTC.
- Convert provider-specific failures into `DataProviderError`,
  `AuthenticationError`, `RateLimitError`, or `NetworkError`.

Providers should not call `httpx` directly, hard-code API keys, calculate
indicators, manage storage/cache policy, render charts, or orchestrate bulk
download workflows. Those responsibilities belong to other layers.

## Polygon

`PolygonProvider` currently implements:

- `health_check()`
- `get_daily_prices()`
- `get_intraday_prices()`

Supported intraday intervals are `1min`, `5min`, `15min`, `30min`, and
`1hour`. Intraday data uses the same standardized OHLCV schema as daily
prices, with timestamps normalized to UTC. Unsupported intervals raise
`ValueError`.

The options and websocket surfaces are intentionally not implemented yet.
Daily price data is returned with the standard price columns: `symbol`,
`timestamp`, `open`, `high`, `low`, `close`, `volume`, and `provider`.

Polygon integration tests are skipped by default. To run the real API test,
set both `POLYGON_API_KEY` and `RUN_POLYGON_INTEGRATION=1`.

`get_latest_price()` currently uses Polygon's previous close endpoint
(`/v2/aggs/ticker/{symbol}/prev`). The returned price comes from the previous
close OHLC response and should not be treated as real-time last trade data.
The standardized output schema is `symbol`, `timestamp`, `price`, and
`provider`.

## Data Latest

Use `market-platform data latest --symbol MSFT` to fetch the latest price for
a symbol.

Supported options:

- `--provider` to choose a specific provider
- `--format table|json|csv` to control the output format
- `--output` to write the formatted result to a file

Examples:

```bash
market-platform data latest --symbol MSFT
market-platform data latest --symbol MSFT --provider polygon --format json
market-platform data latest --symbol MSFT --format csv --output reports/msft.csv
```
