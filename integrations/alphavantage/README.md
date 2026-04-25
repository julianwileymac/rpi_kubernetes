# alphavantage-client

Custom sync/async [Alpha Vantage](https://www.alphavantage.co/documentation/) client engine
built for the rpi_kubernetes data layer. Covers all 9 AV categories (Time Series, Index Data,
Options, Alpha Intelligence, Fundamentals, Forex, Crypto, Commodities, Economic Indicators,
plus 50+ Technical Indicators).

Why not just use [`RomelTorres/alpha_vantage`](https://github.com/RomelTorres/alpha_vantage)?
The upstream library is unmaintained (last meaningful commit several years ago) and lacks:

* A working rate limiter (free tier is 25 req/day; paid tiers 75-1200 RPM).
* Retry/backoff on transient errors and rate-limit soft-fails (AV returns HTTP 200 with
  a `Note`/`Information` key on throttling).
* Response caching.
* Typed error hierarchy and Pydantic response models.
* A unified sync+async facade.

This library addresses each of those and keeps an optional `alpha_vantage>=3.0` fallback
dependency so downstream code can still invoke the upstream parsers when useful.

## Quick start

```python
from alphavantage_client import AlphaVantageClient

client = AlphaVantageClient()  # loads API key from env/file/k8s mount
quote = client.timeseries.global_quote("IBM")
print(quote.price)
```

Async:

```python
import asyncio
from alphavantage_client import AlphaVantageClient

async def main():
    async with AlphaVantageClient() as client:
        quote = await client.timeseries.aglobal_quote("IBM")
        print(quote.price)

asyncio.run(main())
```

## Credentials

Resolution order (first match wins):

1. Explicit `api_key=` kwarg on `AlphaVantageClient(...)`.
2. `ALPHAVANTAGE_API_KEY` env var.
3. File path from `ALPHAVANTAGE_API_KEY_FILE` env var.
4. Default local file: `C:\Users\Julian Wiley\Documents\alphavantage_api_token.txt` (Windows)
   or `~/.alphavantage/api_key` (Unix).
5. K8s secret mount: `/var/run/secrets/alphavantage/api-key`.

Raises `InvalidApiKeyError` if none resolve.

See `docs/alpha-vantage.md` in the parent repo for the full integration guide.
