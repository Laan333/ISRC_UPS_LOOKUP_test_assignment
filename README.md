# ISRC / UPC Lookup Aggregator

A **FastAPI** service that queries multiple public metadata sources in parallel for **ISRC** and **UPC/EAN** identifiers, returns a **single JSON** payload, and keeps responding with **partial results** when individual providers fail.

## Run with Docker

```bash
docker compose up --build
```

API base URL: `http://localhost:8000`  
Smoke check:

```bash
curl http://localhost:8000/health
```

**Interactive docs (after startup):** [Swagger UI](http://localhost:8000/docs), [ReDoc](http://localhost:8000/redoc), [Scalar](http://localhost:8000/scalar). In Swagger or Scalar, open the **lookup** tag, choose `GET /lookup/isrc/{code}` or `GET /lookup/upc/{code}`, click **Execute** / **Test Request**, and use the example value from the parameter description.

Example requests:

```bash
curl "http://localhost:8000/lookup/isrc/USRC17607839"
curl "http://localhost:8000/lookup/upc/5901234123457"
```

## Run locally (without Docker)

```bash
python -m venv .venv
```

Activate the virtual environment:

- **Windows (PowerShell):** `.\.venv\Scripts\Activate.ps1`
- **Linux / macOS:** `source .venv/bin/activate`

Then:

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Optional CLI client

The repo includes `client.py` for quick manual checks:

```bash
python client.py --isrc USRC17607839 --pretty
python client.py --upc 5901234123457 --pretty
```

Use `--base-url` or the `BASE_URL` environment variable if the API is not on `http://127.0.0.1:8000`.

## Environment variables

The easiest path is a `.env` file: copy `.env.example` to `.env` and adjust values.

| Variable | Purpose |
|----------|---------|
| `APP_VERSION` | OpenAPI `info.version` string; default `0.1.0`. |
| `OPENAPI_SERVER_URL` | Base URL listed under OpenAPI **`servers`** for Swagger/Scalar **Try it out** (e.g. `http://127.0.0.1:8000`). Empty string omits `servers` from the schema. |
| `READY_CHECK_URL` | Optional: URL probed by `GET /ready`. If unreachable or returns `5xx`, `/ready` responds with **503**. |
| `USER_AGENT` | Outgoing `User-Agent` for provider HTTP calls. |
| `HTTP_TIMEOUT_S` | httpx timeout in seconds; default `15`. |
| `HTTP_GET_MAX_RETRIES` | Extra GET attempts on timeout/connection issues or `502`/`503`/`504`; default `2`. |
| `HTTP_GET_RETRY_BACKOFF_S` | Base delay (seconds) for exponential backoff between retries. |
| `OUTBOUND_MAX_CONCURRENT` | Concurrent outbound GETs to providers (semaphore); `0` disables limiting. |
| `MAX_RESPONSE_BODY_BYTES` | Upper bound on provider response body size while streaming (default `2000000`); oversize is treated like a transport failure for that provider. |
| `API_RATE_LIMIT_PER_MINUTE` | Per-IP sliding window (60s) for the API, excluding `/health`, `/ready`, and OpenAPI static routes. `0` disables. |
| `DISCOGS_PERSONAL_ACCESS_TOKEN` | Optional Discogs token for friendlier rate limits. |
| `PROVIDER_MUSICBRAINZ_ENABLED` | `true` / `false`; default `true`. |
| `PROVIDER_DEEZER_ENABLED` | `true` / `false`; default `true`. |
| `PROVIDER_DISCOGS_ENABLED` | `true` / `false`. |
| `PROVIDER_WIKIDATA_ENABLED` | `true` / `false` (ISRC only). |
| `PROVIDER_OPEN_LIBRARY_ENABLED` | `true` / `false` (UPC only). |
| `LOOKUP_CACHE_ENABLED` | In-memory cache of full lookup responses; default `true`. |
| `LOOKUP_CACHE_TTL_S` | Cache TTL in seconds (e.g. `300`). `0` disables cache creation. |
| `LOOKUP_CACHE_MAX_ENTRIES` | Max number of cache entries; default `512`. |
| `OPEN_LIBRARY_SEARCH_URL` | Open Library `search.json` endpoint (rarely needs changing). |

## Endpoints

- `GET /health` — liveness; used by Docker healthcheck.
- `GET /ready` — readiness. If `READY_CHECK_URL` is set, performs an extra HTTP GET to that URL.
- `GET /lookup/isrc/{code}` — ISRC normalization (case and hyphens ignored); **422** on invalid format.
- `GET /lookup/upc/{code}` — digits of length 8 / 12 / 13; for 12 and 13, **EAN-13 / UPC-A check digit** validation.

## Architecture / technical notes

- **Stack:** Python 3.12, FastAPI, httpx (async), Pydantic v2. **Playwright** is not bundled in the image: current providers use HTTP/JSON or SPARQL. JS-heavy sites (e.g. IFPI) could be added later via an extra Docker build stage if needed.
- **Providers**
  - **musicbrainz** — recordings by ISRC, releases by barcode; ~1 request/s to MusicBrainz (async lock).
  - **deezer** — public Deezer search API; supports `isrc:"…"` and `upc:"…"` style queries without an API key (catalog coverage varies).
  - **discogs** — release search by barcode; ISRC path is heuristic and may miss.
  - **wikidata** — SPARQL on P1243 (ISRC); not used for UPC in this build.
  - **open_library** — Open Library `search.json?q=…`; often books/ISBN; weak for music UPC but adds an independent signal.
- **Public APIs and policies:** integrations rely on documented HTTP APIs / SPARQL. Respect each provider’s rate limits and terms — [MusicBrainz API](https://musicbrainz.org/doc/MusicBrainz_API), [Discogs API](https://www.discogs.com/developers/), [Wikidata Query Service](https://wikidata.org/wiki/Wikidata:Data_access) / [Terms of Use](https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use), [Open Library API](https://openlibrary.org/developers/api), [Deezer API for developers](https://developers.deezer.com/). This project is not an official client of those organizations.
- **Cache:** process-local TTL keyed by `isrc:{code}` / `upc:{code}`; not shared across replicas — for production multi-instance setups consider Redis (see `CHECKLIST.md`).
- **Orchestration:** `asyncio.gather` across providers; failures surface in `providers[].error` while the overall response stays **200** when the HTTP handler succeeds.
- **Outbound HTTP:** shared `resilient_get` — outbound concurrency cap (`OUTBOUND_MAX_CONCURRENT`), response body cap (`MAX_RESPONSE_BODY_BYTES`), and limited retries for idempotent GETs on transport errors and `502`/`503`/`504` (no retries on `4xx`).
- **Inbound rate limit:** in-process sliding window per IP (not shared across replicas); health and OpenAPI routes are excluded.
- **Normalization:** whitespace collapsing for comparison; original provider strings are preserved where applicable in the payload.
- **Summary:** `found_in` counts providers with `found=true`. `confidence` is `high` when ≥2 providers agree on normalized title/artist, `medium` for a single hit or partial agreement, `low` on conflict or no hits.
- **PostgreSQL / Redis:** not used; the API is stateless aside from in-process cache and rate-limit state. For production with multiple replicas, Redis (shared cache + rate limiting) and quota accounting are reasonable next steps — see `CHECKLIST.md`.

## Tests

```bash
python -m pytest
```

Integration tests in `tests/test_lookup_e2e.py` build the app via `create_app(http_client=…)` with `httpx.MockTransport` (no real network). Production-like startup uses `create_app()` with no injected client (see `app/main.py`).
