# Configuration

Runtime settings are loaded from environment variables and `.env`.

Use `.env.example` as the template for local development. Real secrets belong in
`.env`, which is ignored by Git.

Provider fallback order can be configured with:

```env
MARKET_PLATFORM_DATA_PROVIDER_ORDER=polygon,twelve_data
```

Provider names are normalized before selection, and unknown names raise a
configuration error.
