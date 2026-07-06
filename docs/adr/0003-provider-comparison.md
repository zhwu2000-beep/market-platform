# ADR 0003: Provider Comparison

## Status
Accepted

## Context
- The project now has multiple providers that can return daily OHLCV data.
- Provider switching works through `get_provider()`.
- Before adding fallback or automatic provider selection, the project needs a way to compare normalized outputs.
- Comparison should be based on standardized DataFrames, not raw provider responses.

## Decision
- Add a provider comparison foundation in v0.5.0.
- Start with daily OHLCV comparison only.
- Compare already-normalized DataFrames.
- Keep comparison logic separate from providers and `ProviderRegistry`.
- Do not implement fallback in this version.
- Do not fetch data inside the comparison function.
- Initial comparison should focus on:
  - matched timestamps
  - missing timestamps on either side
  - close price difference
  - volume difference when available
  - provider names

## Consequences
- Provider quality can be evaluated before fallback logic is introduced.
- Polygon and Twelve Data outputs can be compared through the shared schema.
- Comparison remains testable without live API calls.
- Future fallback policy can be based on measured differences.

## Alternatives Considered
- Implementing fallback immediately, rejected because comparison should come first.
- Comparing raw provider payloads, rejected because normalized schemas are more stable.
- Adding a third provider immediately, rejected because two providers are enough to validate comparison.
