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

The intraday, options, and websocket surfaces are intentionally not implemented
yet. Daily price data is returned with the standard price columns: `symbol`,
`timestamp`, `open`, `high`, `low`, `close`, `volume`, and `provider`.

Polygon integration tests are skipped by default. To run the real API test,
set both `POLYGON_API_KEY` and `RUN_POLYGON_INTEGRATION=1`.
