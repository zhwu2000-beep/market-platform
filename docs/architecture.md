# Architecture

Market Platform is organized around explicit boundaries:

- `config`: environment-backed settings and constants.
- `logging`: process-wide logging setup.
- `data`: provider contracts, provider registry, normalized data models, and source-specific providers.
- `indicators`: technical indicator calculations independent of data sources.
- `charts`: chart creation independent of data acquisition.
- `research`: workflows that combine data, indicators, charts, and AI analysis.
- `ai`: prompts, agents, and summarization helpers.
- `storage`: cache, database, and repository abstractions.
- `utils`: generic helpers that are not domain workflows.
- `cli`: command line entrypoints.

The data layer exposes a unified `DataProvider` interface. Application code
depends on this interface rather than vendor clients directly.

## Data Provider Boundary

Every provider implements the same asynchronous contract:

- `get_daily_prices()`
- `get_intraday_prices()`
- `get_latest_price()`
- `health_check()`

All provider methods return `pandas.DataFrame` objects. Price methods use the
canonical columns `symbol`, `timestamp`, `open`, `high`, `low`, `close`,
`volume`, and `provider`. Health checks use `provider`, `status`, `checked_at`,
`latency_ms`, and `message`.

Provider timestamps are normalized to UTC at the data boundary. Daily,
intraday, and latest price responses all use the `timestamp` column, while
health checks use `checked_at`. This keeps downstream indicators, storage,
charts, notebooks, and research workflows independent from each vendor's date
format and local timezone assumptions.

Provider implementations must wrap vendor-specific failures in project-level
exceptions: `DataProviderError`, `AuthenticationError`, `RateLimitError`, and
`NetworkError`. Third-party client exceptions should not cross the provider
boundary because that would couple the rest of the application to a specific
API library and make fallback providers harder to add.

Concrete providers such as Polygon and Twelve Data will normalize external
responses into these DataFrame schemas. The abstraction layer intentionally
does not perform API calls; it defines the contract that future provider
implementations must satisfy.

## Shared HTTP Client

Provider implementations must use the shared `HTTPClient` layer for all network
access. Providers should not call `httpx.get()`, `httpx.post()`, or create
ad-hoc HTTP clients directly.

The HTTP client is a separate boundary from provider normalization for three
reasons:

- Consistency: timeout, default headers, `User-Agent`, JSON parsing, retry
  behavior, and request logging are applied the same way for every provider.
- Isolation: HTTP status codes and transport failures are converted into the
  same provider exception hierarchy used by the data layer.
- Extensibility: the current client exposes synchronous methods, while keeping
  the provider boundary narrow enough to add an async implementation later
  without changing downstream research, storage, indicators, or chart code.

The shared client uses `httpx` internally, supports exponential-backoff retry
for transient failures, and returns parsed JSON to provider implementations.
Providers remain responsible for converting parsed vendor payloads into the
canonical DataFrame schemas.

Concrete provider implementations sit above this HTTP layer. Their job is to
choose provider endpoints, attach credentials from `Settings`, call the shared
client, and normalize the returned JSON into project schemas. They do not own
cache policy, bulk download orchestration, indicator calculation, charting, or
direct third-party HTTP client usage.
