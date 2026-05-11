# ISRC / UPC Lookup Aggregator

A **FastAPI** service that queries multiple public metadata sources in parallel for **ISRC** and **UPC/EAN** identifiers, returns a **single JSON** payload, and keeps responding with **partial results** when individual providers fail.

## Run with Docker

```bash
docker compose up --build
```

Compose starts:

- **`nginx`** — custom image (`./nginx/Dockerfile`) that reverse-proxies to `api`. Listens on host **`NGINX_HTTP_PORT` → 80** (default **80**). When **HTTPS** is enabled, also **`NGINX_HTTPS_PORT` → 443** and **HTTP redirects to HTTPS** (301).
- **`api`** — FastAPI / uvicorn on **`8000`** (still published for direct access and debugging).

**Through nginx (HTTP):**  
Base URL: `http://localhost` (or `http://localhost:8080` if you set `NGINX_HTTP_PORT=8080`).

```bash
curl "http://localhost/health"
curl "http://localhost/lookup/isrc/USRC17607839"
```

**Through nginx (HTTPS):** set `NGINX_SSL_ENABLED=true` in `.env`, place PEM files under `./certs/` (see `certs/README.md`), set `OPENAPI_SERVER_URL` and `READY_CHECK_URL` to **`https://…`** (same host/port as in the browser). Rebuild: `docker compose up --build`. Then:

```bash
curl "https://localhost/health" -k   # -k only for self-signed local certs
curl -L "http://localhost/health"     # follows redirect to HTTPS when SSL is on
```

**Direct to uvicorn (bypass nginx):**  
Base URL: `http://localhost:8000`

```bash
curl "http://localhost:8000/health"
curl "http://localhost:8000/lookup/isrc/USRC17607839"
```

### Domain, HTTP vs HTTPS, OpenAPI “Try it out”, and `.env`

Create a `.env` next to `docker-compose.yml` (see `.env.example`). Match **`OPENAPI_SERVER_URL`** (and optional **`READY_CHECK_URL`**) to what users type in the browser: **`http://…`** for plain HTTP, **`https://…`** when TLS is terminated at nginx.

| Variable | Purpose |
|----------|---------|
| `OPENAPI_SERVER_URL` | Public base URL for Swagger / Scalar **Try it out** (scheme + host + port). Examples: `http://localhost`, `https://api.example.com`. |
| `READY_CHECK_URL` | Optional URL probed by `GET /ready`; use the **same scheme and host** as the public edge (e.g. `https://api.example.com/health`). |
| `NGINX_HTTP_PORT` | Host → container `80` (default `80`). Use `8080` if port 80 is busy. |
| `NGINX_HTTPS_PORT` | Host → container `443` when SSL is enabled (default `443`). |
| `NGINX_SSL_ENABLED` | `true` / `false` (default `false`). When `true`, nginx loads TLS PEMs and redirects port **80** → **HTTPS**. |
| `NGINX_SSL_CERT_DIR` | Host directory mounted as `/etc/nginx/ssl` (default `./certs`). |
| `NGINX_SSL_CERT` | Path **inside the container** to the certificate chain (default `/etc/nginx/ssl/fullchain.pem`). |
| `NGINX_SSL_KEY` | Path **inside the container** to the private key (default `/etc/nginx/ssl/privkey.pem`). |

Nginx behaviour is generated at container start from `nginx/http-only.conf` or `nginx/https.conf.envsubst` (see `nginx/docker-entrypoint.d/99-gen-nginx-conf.sh`). To pin a hostname, edit `server_name _;` in those files to e.g. `server_name api.example.com;` and rebuild the nginx image.

**Interactive docs (after startup):**  
Use the same scheme/host/port as in `OPENAPI_SERVER_URL` (e.g. `https://localhost/docs` when HTTPS is enabled, or `http://localhost/docs` on HTTP only). Direct uvicorn: [Swagger UI](http://localhost:8000/docs), etc.

Example requests (nginx on default port 80):

```bash
curl "http://localhost/lookup/isrc/USRC17607839"
curl "http://localhost/lookup/upc/5901234123457"
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

**Interactive mode** (prompts for the API base URL, then a menu: ISRC, UPC, `/health`, `/ready`, `/openapi.json`):

```bash
python client.py --interactive --pretty
```

## Environment variables

The easiest path is a `.env` file: copy `.env.example` to `.env` and adjust values.

| Variable | Purpose |
|----------|---------|
| `APP_VERSION` | OpenAPI `info.version` string; default `0.1.0`. |
| `OPENAPI_SERVER_URL` | Base URL listed under OpenAPI **`servers`** for Swagger/Scalar **Try it out**. Use **`http://…`** or **`https://…`** to match how clients reach nginx (e.g. `http://localhost`, `https://api.example.com`). Empty string omits `servers` from the schema. |
| `READY_CHECK_URL` | Optional: URL probed by `GET /ready`. If unreachable or returns `5xx`, `/ready` responds with **503**. Use the same scheme as the public URL (`http` vs `https`). |
| `NGINX_HTTP_PORT` | Host port mapped to nginx HTTP `80` (default `80`). |
| `NGINX_HTTPS_PORT` | Host port mapped to nginx HTTPS `443` (default `443`). |
| `NGINX_SSL_ENABLED` | `true` / `false` — terminate TLS in nginx and redirect HTTP→HTTPS (default `false`). |
| `NGINX_SSL_CERT_DIR` | Host directory mounted at `/etc/nginx/ssl` (default `./certs`). |
| `NGINX_SSL_CERT` | PEM chain path **inside the container** (default `/etc/nginx/ssl/fullchain.pem`). |
| `NGINX_SSL_KEY` | Private key path **inside the container** (default `/etc/nginx/ssl/privkey.pem`). |
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
| `LOG_LEVEL` | Root log level: `DEBUG`, `INFO`, `WARNING`, … (default `INFO`). |
| `LOG_FILE_PATH` | Rotating app log file, relative to the process working directory (default `logs/app.log`). Set to empty to disable file logging (stdout only). |
| `LOG_MAX_BYTES` | Max size of one log file before rotation (default `5000000`). |
| `LOG_BACKUP_COUNT` | Number of old log files to retain (default `5`). |

## Endpoints

- `GET /health` — liveness; used by Docker healthcheck.
- `GET /ready` — readiness. If `READY_CHECK_URL` is set, performs an extra HTTP GET to that URL.
- `GET /lookup/isrc/{code}` — ISRC normalization (case and hyphens ignored); **422** on invalid format.
- `GET /lookup/upc/{code}` — digits of length 8 / 12 / 13; for 12 and 13, **EAN-13 / UPC-A check digit** validation.

## Timeouts, errors & logging

### Where logs go (recommended patterns)

- **Containers / Kubernetes:** the usual production pattern is **stdout/stderr only** and log shipping (Loki, CloudWatch, ELK, Datadog, etc.). No files inside the container.
- **This project (Docker Compose):** the API also writes a **rotating file** under `logs/app.log` (configurable) and mounts `./logs` from the host so logs **survive container restarts**. Nginx writes `access.log` / `error.log` under `./logs/nginx/`. You still get stdout in `docker compose logs`.

### Timeout alignment (nginx ↔ app)

| Layer | What it limits | Default / rule of thumb |
|-------|----------------|-------------------------|
| **httpx** (`HTTP_TIMEOUT_S`) | Per outbound GET to a provider | `15` s |
| **Retries** (`HTTP_GET_MAX_RETRIES`) | Extra attempts on timeouts / `502–504` | `2` → up to **3** attempts per GET |
| **Wall time per provider** | Rough upper bound | \(\approx (\text{HTTP\_GET\_MAX\_RETRIES}+1) \times \text{HTTP\_TIMEOUT\_S}\) + backoff (order of **45–60 s** with defaults) |
| **Lookup request** | Providers run **in parallel** | Total wait ≈ **slowest** provider, not the sum |
| **nginx `proxy_read_timeout`** | Max wait for a response from uvicorn after the request is forwarded | **90 s** in `nginx/http-only.conf` / generated HTTPS config — must stay **≥** the realistic worst lookup; raise it if you increase `HTTP_TIMEOUT_S` or retries |
| **nginx `proxy_connect_timeout`** | TCP connect to `api:8000` | **10 s** |
| **nginx `proxy_send_timeout`** | Sending the request body to uvicorn | **90 s** (large bodies are unlikely here) |

`/ready` uses a short **3 s** client timeout inside the app (independent of the table above).

### HTTP errors (API)

- **422 — Pydantic / OpenAPI validation** (malformed parameters where FastAPI validates first): JSON with `detail` as a structured list, `type: "validation_error"`, and `request_id`.
- **422 — business rules** (e.g. invalid ISRC/UPC after `validate_*` in the route): JSON with `detail` as a human-readable string, `type: "http_error"`, and `request_id`.
- **Other HTTP errors** (`HTTPException`): JSON with `detail`, `type: "http_error"`, and `request_id`.
- **429** (rate limit middleware): JSON with `detail`, `type: "rate_limited"`, and `request_id` when available.
- **5xx unexpected** (unhandled exception): JSON with `detail`, `type: "internal_error"`, and `request_id` (also logged with stack trace).
- Successful **lookup** responses stay **200** even when individual providers fail; provider errors are in `providers[].error`.

Every response should include header **`X-Request-ID`** (from middleware).

### HTTP errors (nginx)

- **`proxy_intercept_errors` is off** so JSON error bodies from FastAPI are **not** rewritten by nginx.
- If the **upstream is unreachable** or nginx hits a **proxy read timeout**, nginx returns small **JSON** payloads (`source: "nginx"`) for **502** / **504** (see `error_page` in `nginx/http-only.conf` and `nginx/https.conf.envsubst`).

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
