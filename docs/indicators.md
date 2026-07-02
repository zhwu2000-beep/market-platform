# Indicators

Technical indicators live in `src/market_platform/indicators`.

Indicators should consume normalized market data and avoid direct API calls.
This keeps calculations reusable across Polygon, Twelve Data, and future data
sources.
