<p align="center"><strong>Language / Язык:</strong> <a href="#english">English</a> · <a href="#russian">Русский</a></p>

<h1 id="english">English</h1>

## Overview

**ISRC / UPC Lookup Aggregator** is a small **FastAPI** backend that queries several **public** music metadata sources **in parallel** for **ISRC** (International Standard Recording Code) and **UPC / EAN** barcodes. It returns **one consolidated JSON** document per request, **normalizes** fields where possible, computes a short **summary** (how many providers matched, heuristic **confidence**), and stays **available with partial results** when individual providers time out, rate-limit, or error.

The service is intended as a **technical challenge / reference implementation**: clear structure, explicit tradeoffs, resilience to flaky upstreams—not a full production catalog product.

---

## Features (mapping to the assignment)

| Requirement | How it is addressed |
|-------------|---------------------|
| `GET /lookup/isrc/{code}` | Implemented; invalid ISRC → **422**. |
| `GET /lookup/upc/{code}` | Implemented; UPC-A / EAN-8 / EAN-13 with **check digit** validation → **422** on failure. |
| **Multiple providers (2–3+)** | **MusicBrainz**, **Deezer**, **Discogs**, **Wikidata** (ISRC via SPARQL), **Open Library** (UPC—weak for music but independent signal). Each can be toggled via env. |
| **Unified JSON** | See `app/schemas/lookup.py`; includes `query`, `providers[]`, `summary` (`found_in`, `confidence`). |
| **Reliability** | Per-provider timeouts, retries on transport / certain 5xx, concurrency limits, body size cap; **200** on successful handler with per-provider errors surfaced or filtered per design. |
| **Documentation** | This README (bilingual), `.env.example`, optional `CHECKLIST.md` / `nginx/README.md` / `certs/README.md`. |
| **Stack** | **Python 3.12**, **FastAPI**, **httpx** (async), **Pydantic v2**. |
| **Playwright** | **Not** bundled: current integrations use HTTP/JSON and SPARQL. JS-heavy sites (e.g. IFPI) could be added later in a separate image/stage—documented as a deliberate scope choice. |
| **Optional extras** | **Docker** + **nginx** reverse proxy; retries; in-memory **cache**; **rate limiting** per IP. |

---

## Quick start — Docker (recommended)

```bash
docker compose up --build
```

**Compose services**

- **`nginx`** — custom image (`./nginx/Dockerfile`) reverse-proxies to `api`. By default only host **`NGINX_HTTP_PORT` → 80** is published (default **80**). When **`NGINX_SSL_ENABLED=true`**, merge **`docker-compose.https.yml`** so host **`NGINX_HTTPS_PORT` → 443** is published; nginx then redirects HTTP→HTTPS (**301**).
- **`api`** — FastAPI / uvicorn on **`8000`** (still published for direct access and debugging).

**Through nginx (HTTP)**  
Base URL: `http://localhost` (or `http://localhost:8080` if `NGINX_HTTP_PORT=8080`).

```bash
curl "http://localhost/health"
curl "http://localhost/lookup/isrc/USRC17607839"
```

**Through nginx (HTTPS)**  
Set `NGINX_SSL_ENABLED=true` in `.env`, add PEM files under `./certs/` (see `certs/README.md`), set `OPENAPI_SERVER_URL` / `READY_CHECK_URL` to **`https://…`** (same host/port as in the browser). Start with **both** compose files so port **443** is published:

```bash
docker compose -f docker-compose.yml -f docker-compose.https.yml up --build -d
```

```bash
curl "https://localhost/health" -k   # -k only for self-signed local certs
curl -L "http://localhost/health"      # follows redirect to HTTPS when SSL is on
```

**Direct to uvicorn (bypass nginx)**  
Base URL: `http://localhost:8000`

```bash
curl "http://localhost:8000/health"
curl "http://localhost:8000/lookup/isrc/USRC17607839"
```

### Domain, HTTP vs HTTPS, OpenAPI “Try it out”, and `.env`

Create a `.env` next to `docker-compose.yml` (see `.env.example`). The **`api`** service loads that file as `env_file`, so provider toggles and Discogs credentials are visible inside the container; the explicit `environment:` block only overrides a few keys (logging, CORS, etc.). Match **`OPENAPI_SERVER_URL`** (and optional **`READY_CHECK_URL`**) to what users type in the browser: **`http://…`** vs **`https://…`**. If nginx listens on a **non-default host port** (e.g. `NGINX_HTTP_PORT=7000`), include that port in the URL.

| Variable | Purpose |
|----------|---------|
| `OPENAPI_SERVER_URL` | Public base URL for Swagger / Scalar **Try it out** (scheme + host + port). Examples: `http://localhost`, `https://api.example.com`. |
| `READY_CHECK_URL` | Optional URL probed by `GET /ready`; use the **same scheme and host** as the public edge (e.g. `https://api.example.com/health`). |
| `NGINX_HTTP_PORT` | Host → container `80` (default `80`). Use `8080` if port 80 is busy. |
| `NGINX_HTTPS_PORT` | Host port mapped to nginx `443` **only when** you use `docker-compose.https.yml` (default `443`). |
| `NGINX_SSL_ENABLED` | `true` / `false` (default `false`). When `true`, nginx loads TLS PEMs and redirects port **80** → **HTTPS**. |
| `NGINX_SSL_CERT_DIR` | Host directory mounted as `/etc/nginx/ssl` (default `./certs`). |
| `NGINX_SSL_CERT` | Path **inside the container** to the certificate chain (default `/etc/nginx/ssl/fullchain.pem`). |
| `NGINX_SSL_KEY` | Path **inside the container** to the private key (default `/etc/nginx/ssl/privkey.pem`). |

Nginx behaviour is generated at container start from `nginx/http-only.conf` or `nginx/https.conf.envsubst` (see `nginx/docker-entrypoint.d/09-gen-nginx-conf.sh`). To pin a hostname, edit `server_name _;` in those files to e.g. `server_name api.example.com;` and rebuild the nginx image.

**Interactive docs (after startup)**  
Use the same scheme/host/port as in `OPENAPI_SERVER_URL` (e.g. `https://localhost/docs` when HTTPS is enabled, or `http://localhost/docs` on HTTP only). Direct uvicorn: Swagger UI at `http://localhost:8000/docs`.

Example requests (nginx on default port 80):

```bash
curl "http://localhost/lookup/isrc/USRC17607839"
curl "http://localhost/lookup/upc/5901234123457"
```

---

## Quick start — local (without Docker)

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

Use **Python 3.12** to match the intended runtime.

---

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

---

## Environment variables (application)

Copy `.env.example` to `.env` and adjust. Below are the main **application** settings (nginx-specific variables are summarized above).

| Variable | Purpose |
|----------|---------|
| `APP_VERSION` | OpenAPI `info.version` string; default `0.1.0`. |
| `OPENAPI_SERVER_URL` | Base URL under OpenAPI **`servers`** for Swagger/Scalar **Try it out**. Empty string omits `servers` from the schema. |
| `READY_CHECK_URL` | Optional: URL probed by `GET /ready`. If unreachable or returns `5xx`, `/ready` responds with **503**. |
| `USER_AGENT` | Outgoing `User-Agent` for provider HTTP calls. |
| `HTTP_TIMEOUT_S` | httpx timeout in seconds; default `15`. |
| `HTTP_GET_MAX_RETRIES` | Extra GET attempts on timeout/connection issues or `502`/`503`/`504`; default `2`. |
| `HTTP_GET_RETRY_BACKOFF_S` | Base delay (seconds) for exponential backoff between retries. |
| `OUTBOUND_MAX_CONCURRENT` | Concurrent outbound GETs to providers (semaphore); `0` disables limiting. |
| `MAX_RESPONSE_BODY_BYTES` | Upper bound on provider response body size while streaming (default `2000000`); oversize is treated like a transport failure for that provider. |
| `API_RATE_LIMIT_PER_MINUTE` | Per-IP sliding window (60s) for the API, excluding `/health`, `/ready`, and OpenAPI static routes. `0` disables. |
| `DISCOGS_CONSUMER_KEY` / `DISCOGS_LOGIN` | Discogs **Consumer Key** (developer UI may label it “consumer login”). See `.env.example` for synonyms. |
| `DISCOGS_CONSUMER_SECRET` / `DISCOGS_PASSWORD` | **Consumer Secret**—not your discogs.com login password. Sent as `Authorization: Discogs key=…, secret=…` ([Discogs authentication](https://www.discogs.com/developers/#page:authentication)). |
| `DISCOGS_PERSONAL_ACCESS_TOKEN` | Optional personal token; if set, uses `Discogs token=…` and skips consumer key/secret. |
| `PROVIDER_MUSICBRAINZ_ENABLED` | `true` / `false`; default `true`. |
| `PROVIDER_DEEZER_ENABLED` | `true` / `false`; default `true`. |
| `PROVIDER_DISCOGS_ENABLED` | `true` / `false`. |
| `PROVIDER_WIKIDATA_ENABLED` | `true` / `false` (ISRC-oriented). |
| `PROVIDER_OPEN_LIBRARY_ENABLED` | `true` / `false` (UPC-oriented). |
| `LOOKUP_CACHE_ENABLED` | In-memory cache of full lookup responses; default `true`. |
| `LOOKUP_CACHE_TTL_S` | Cache TTL in seconds (e.g. `300`). `0` disables cache creation. |
| `LOOKUP_CACHE_MAX_ENTRIES` | Max number of cache entries; default `512`. |
| `OPEN_LIBRARY_SEARCH_URL` | Open Library `search.json` endpoint (rarely needs changing). |
| `LOG_LEVEL` | Root log level: `DEBUG`, `INFO`, `WARNING`, … (default `INFO`). |
| `LOG_FILE_PATH` | Rotating app log file, relative to CWD (default `logs/app.log`). Empty disables file logging (stdout only). |
| `LOG_MAX_BYTES` | Max size of one log file before rotation (default `5000000`). |
| `LOG_BACKUP_COUNT` | Number of old log files to retain (default `5`). |
| `CORS_ALLOW_ORIGINS` | Browser CORS: `*` (default), comma-separated origins, or empty to disable CORS middleware. |

---

## HTTP API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness; used by Docker healthcheck. |
| `GET` | `/ready` | Readiness. If `READY_CHECK_URL` is set, performs an extra HTTP GET to that URL. |
| `GET` | `/lookup/isrc/{code}` | ISRC normalization (case and hyphens ignored); **422** on invalid format. |
| `GET` | `/lookup/upc/{code}` | Digits length 8 / 12 / 13; **EAN-13 / UPC-A check digit** validation; **422** on failure. |

Every response should include header **`X-Request-ID`** (from middleware).

### Successful lookup semantics

Successful **lookup** responses use **200** even when individual providers fail; provider-specific problems appear in `providers[].error` (and failed rows may be filtered per implementation—see Architecture).

### HTTP errors (API)

- **422 — validation** (FastAPI/Pydantic): JSON with `detail` as a structured list, `type: "validation_error"`, and `request_id`.
- **422 — business rules** (invalid ISRC/UPC after validation in the route): JSON with `detail` as a human-readable string, `type: "http_error"`, and `request_id`.
- **Other HTTP errors** (`HTTPException`): JSON with `detail`, `type: "http_error"`, and `request_id`.
- **429** (rate limit): JSON with `detail`, `type: "rate_limited"`, and `request_id` when available.
- **5xx unexpected**: JSON with `detail`, `type: "internal_error"`, and `request_id` (also logged with stack trace).

### Swagger / Scalar “Failed to fetch”

1. **`OPENAPI_SERVER_URL` must match the browser URL**, including **port**. If nginx is on `http://203.0.113.10:7000`, set `OPENAPI_SERVER_URL=http://203.0.113.10:7000`. If you omit the port, Try it out may hit the wrong host/port.
2. **Firewall** must allow inbound **TCP** on published ports (e.g. `7000` and `8000`).
3. **CORS** defaults to `*`. If you restrict origins, include the exact origin used to open `/docs` (scheme + host + port).

### HTTP errors (nginx)

- **`proxy_intercept_errors` is off** so JSON bodies from FastAPI are **not** rewritten by nginx.
- If the **upstream is unreachable** or nginx hits **proxy read timeout**, nginx may return small **JSON** payloads (`source: "nginx"`) for **502** / **504** (see `nginx/http-only.conf` and `nginx/https.conf.envsubst`).

---

## Timeouts, resilience, and logging

### Timeout alignment (nginx ↔ app)

| Layer | What it limits | Default / rule of thumb |
|-------|----------------|-------------------------|
| **httpx** (`HTTP_TIMEOUT_S`) | Per outbound GET to a provider | `15` s |
| **Retries** (`HTTP_GET_MAX_RETRIES`) | Extra attempts on timeouts / `502–504` | `2` → up to **3** attempts per GET |
| **Wall time per provider** | Rough upper bound | ≈ `(HTTP_GET_MAX_RETRIES+1) × HTTP_TIMEOUT_S` + backoff |
| **Lookup request** | Providers run **in parallel** | Total wait ≈ **slowest** provider, not the sum |
| **nginx `proxy_read_timeout`** | Max wait for uvicorn after forward | **90 s** — should stay **≥** realistic worst lookup |
| **nginx `proxy_connect_timeout`** | TCP connect to `api:8000` | **10 s** |
| **nginx `proxy_send_timeout`** | Sending request body to uvicorn | **90 s** |

`/ready` uses a short **3 s** client timeout inside the app (independent of the table above).

### Where logs go

- **Containers:** stdout/stderr in `docker compose logs`; API optional rotating file under `./logs` (mounted from host); nginx logs under `./logs/nginx/`.

---

## Architecture and design notes

- **Orchestration:** `asyncio.gather` across providers; overall response stays **200** when the HTTP handler succeeds. Additional **hint** searches may run when code-based lookups miss but other providers returned text (see `lookup_service`).
- **Outbound HTTP:** shared resilient GET — concurrency cap (`OUTBOUND_MAX_CONCURRENT`), response body cap (`MAX_RESPONSE_BODY_BYTES`), limited retries for idempotent GETs on transport errors and `502`/`503`/`504` (no retries on `4xx`).
- **Inbound rate limit:** in-process sliding window per IP (not shared across replicas); health and OpenAPI routes excluded.
- **Normalization:** whitespace collapsing for comparison; original provider strings preserved where applicable.
- **Summary:** `found_in` counts providers with `found=true`. `confidence` is **high** when ≥2 providers agree on normalized title/artist, **medium** for a single hit or partial agreement, **low** on conflict or no hits.
- **Cache:** process-local TTL keyed by `isrc:{code}` / `upc:{code}`; not shared across replicas—for multi-instance production consider Redis (see `CHECKLIST.md`).
- **PostgreSQL / Redis:** not used; state is in-process cache and rate-limit counters only.

### Providers (high level)

| Provider | Role |
|----------|------|
| **musicbrainz** | Recordings by ISRC; releases by barcode; respects ~1 req/s (async lock)—ISRC path can take **~2–3 s** alone. |
| **deezer** | Public search API; `isrc:"…"` / `upc:"…"` style queries without an API key; catalog coverage varies. |
| **discogs** | Barcode search + release details; ISRC via heuristic text search. Requires Discogs auth as documented. |
| **wikidata** | SPARQL for ISRC (`P1243`); not used for UPC in this build. |
| **open_library** | `search.json`; often books/ISBN—weak for music UPC but an independent signal. |

**Public APIs and policies:** integrations use documented HTTP APIs / SPARQL. Respect each provider’s rate limits and terms ([MusicBrainz API](https://musicbrainz.org/doc/MusicBrainz_API), [Discogs API](https://www.discogs.com/developers/), [Wikidata](https://wikidata.org/wiki/Wikidata:Data_access), [Open Library API](https://openlibrary.org/developers/api), [Deezer for developers](https://developers.deezer.com/)). This project is **not** an official client of those organizations.

### Known limitations and production-oriented improvements

- In-memory cache and rate limits **do not** span processes/instances.
- Provider coverage and catalog correctness depend entirely on third parties; **confidence** is heuristic, not legal proof of identity.
- **Playwright** not included; sites that require a full browser need extra packaging and operational cost.
- For a production deployment: shared Redis (cache + rate limit), structured metrics/tracing, secrets management, per-provider circuit breakers, and documented SLAs for upstreams—see `CHECKLIST.md` for a longer list.

---

## Tests

```bash
python -m pytest
```

Integration-style tests in `tests/test_lookup_e2e.py` use `httpx.MockTransport` (no real network). Production-like startup uses `create_app()` without an injected client (`app/main.py`).

---

## Repository layout (partial)

| Path | Role |
|------|------|
| `app/main.py` | FastAPI application factory and middleware. |
| `app/api/routes/` | HTTP routes (`lookup`, `health`). |
| `app/services/lookup_service.py` | Provider orchestration and response assembly. |
| `app/providers/` | One module per upstream integration. |
| `app/schemas/lookup.py` | Response models. |
| `nginx/` | Dockerized reverse proxy config and entrypoint scripts. |
| `docker-compose.yml` | Default stack. |
| `docker-compose.https.yml` | Optional HTTPS port publishing overlay. |
| `client.py` | CLI helper for manual testing. |

---

<h1 id="russian">Русский</h1>

## Обзор

**ISRC / UPC Lookup Aggregator** — это небольшой backend на **FastAPI**, который **параллельно** опрашивает несколько **публичных** источников метаданных для **ISRC** (международный код записи) и штрихкодов **UPC / EAN**. Для каждого запроса возвращается **единый JSON**, поля **нормализуются** где это уместно, формируется краткий **summary** (сколько провайдеров нашли совпадение, эвристическая **уверенность**). Сервис сохраняет **частичные результаты**, если отдельные провайдеры не отвечают, отдают ошибку или лимит.

Проект рассматривается как **техническое задание / эталонная реализация**: понятная структура, явные компромиссы, устойчивость к нестабильным внешним API — не полноценный production‑каталог.

---

## Соответствие требованиям задания

| Требование | Как реализовано |
|------------|-----------------|
| `GET /lookup/isrc/{code}` | Есть; неверный ISRC → **422**. |
| `GET /lookup/upc/{code}` | Есть; UPC-A / EAN-8 / EAN-13 с проверкой **контрольной цифры** → **422** при ошибке. |
| **Несколько провайдеров (2–3+)** | **MusicBrainz**, **Deezer**, **Discogs**, **Wikidata** (ISRC через SPARQL), **Open Library** (UPC — слабый сигнал для музыки, но независимый). Включение через переменные окружения. |
| **Единый JSON** | См. `app/schemas/lookup.py`: `query`, `providers[]`, `summary` (`found_in`, `confidence`). |
| **Надёжность** | Таймауты, повторы при сетевых/части 5xx ограничениях, лимит параллелизма, ограничение размера тела ответа; при успешной обработке запроса — **200**, ошибки провайдеров — в структуре ответа / фильтрации по логике сервиса. |
| **Документация** | Этот README (два языка), `.env.example`, при необходимости `CHECKLIST.md`, `nginx/README.md`, `certs/README.md`. |
| **Стек** | **Python 3.12**, **FastAPI**, **httpx** (async), **Pydantic v2**. |
| **Playwright** | **Не** входит в образ: текущие интеграции — HTTP/JSON и SPARQL. Сайты на тяжёлом JS (например IFPI) можно добавить отдельным этапом сборки — осознанное ограничение объёма. |
| **Дополнительно** | **Docker** + **nginx**; повторы запросов; **кэш** в памяти; **rate limiting** по IP. |

---

## Быстрый старт — Docker (рекомендуется)

```bash
docker compose up --build
```

**Сервисы Compose**

- **`nginx`** — свой образ (`./nginx/Dockerfile`), reverse proxy к `api`. По умолчанию на хост публикуется **`NGINX_HTTP_PORT` → 80** (по умолчанию **80**). Если **`NGINX_SSL_ENABLED=true`**, подключите **`docker-compose.https.yml`**, чтобы опубликовать **`NGINX_HTTPS_PORT` → 443**; nginx делает редирект HTTP→HTTPS (**301**).
- **`api`** — FastAPI / uvicorn на порту **`8000`** (порт также проброшен для прямого доступа и отладки).

**Через nginx (HTTP)**  
Базовый URL: `http://localhost` (или `http://localhost:8080`, если задан `NGINX_HTTP_PORT=8080`).

```bash
curl "http://localhost/health"
curl "http://localhost/lookup/isrc/USRC17607839"
```

**Через nginx (HTTPS)**  
Установите `NGINX_SSL_ENABLED=true` в `.env`, положите PEM в `./certs/` (см. `certs/README.md`), выставьте `OPENAPI_SERVER_URL` / `READY_CHECK_URL` на **`https://…`** (тот же хост/порт, что в браузере). Запускайте **оба** compose-файла, чтобы порт **443** был опубликован:

```bash
docker compose -f docker-compose.yml -f docker-compose.https.yml up --build -d
```

```bash
curl "https://localhost/health" -k   # -k только для самоподписанных локальных сертификатов
curl -L "http://localhost/health"     # следует редиректу на HTTPS при включённом SSL
```

**Напрямую к uvicorn (минуя nginx)**  
Базовый URL: `http://localhost:8000`

```bash
curl "http://localhost:8000/health"
curl "http://localhost:8000/lookup/isrc/USRC17607839"
```

### Домен, HTTP и HTTPS, OpenAPI «Try it out», файл `.env`

Создайте `.env` рядом с `docker-compose.yml` (шаблон — `.env.example`). Сервис **`api`** подхватывает его как `env_file`, поэтому переключатели провайдеров и учётные данные Discogs доступны в контейнере; блок `environment:` в compose переопределяет лишь часть ключей (логирование, CORS и т.д.). **`OPENAPI_SERVER_URL`** и опциональный **`READY_CHECK_URL`** должны совпадать с тем, что пользователь вводит в браузере (**`http://…`** или **`https://…`**). Если nginx слушает **нестандартный порт** на хосте (например `NGINX_HTTP_PORT=7000`), порт **обязательно** укажите в URL.

| Переменная | Назначение |
|------------|------------|
| `OPENAPI_SERVER_URL` | Публичный базовый URL для Swagger / Scalar **Try it out** (схема + хост + порт). |
| `READY_CHECK_URL` | Опционально: URL для проверки из `GET /ready`; та же схема и хост, что у публичного входа. |
| `NGINX_HTTP_PORT` | Проброс хоста → контейнер `80` (по умолчанию `80`). |
| `NGINX_HTTPS_PORT` | Проброс на nginx `443` **только** с `docker-compose.https.yml` (по умолчанию `443`). |
| `NGINX_SSL_ENABLED` | `true` / `false` — TLS в nginx и редирект с **80** на **HTTPS**. |
| `NGINX_SSL_CERT_DIR` | Каталог на хосте, монтируется в `/etc/nginx/ssl` (по умолчанию `./certs`). |
| `NGINX_SSL_CERT` | Путь **внутри контейнера** к цепочке сертификатов. |
| `NGINX_SSL_KEY` | Путь **внутри контейнера** к приватному ключу. |

Поведение nginx генерируется при старте из `nginx/http-only.conf` или `nginx/https.conf.envsubst` (см. `nginx/docker-entrypoint.d/09-gen-nginx-conf.sh`). Для фиксированного имени хоста замените `server_name _;` на, например, `server_name api.example.com;` и пересоберите образ nginx.

**Интерактивная документация**  
Открывайте `/docs` по той же схеме/хосту/порту, что и в `OPENAPI_SERVER_URL`. Прямой доступ к uvicorn: `http://localhost:8000/docs`.

Примеры (nginx на порту 80 по умолчанию):

```bash
curl "http://localhost/lookup/isrc/USRC17607839"
curl "http://localhost/lookup/upc/5901234123457"
```

---

## Быстрый старт — локально (без Docker)

```bash
python -m venv .venv
```

Активация окружения:

- **Windows (PowerShell):** `.\.venv\Scripts\Activate.ps1`
- **Linux / macOS:** `source .venv/bin/activate`

Далее:

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Рекомендуется **Python 3.12**.

---

## Опциональный CLI-клиент

В репозитории есть `client.py` для ручных проверок:

```bash
python client.py --isrc USRC17607839 --pretty
python client.py --upc 5901234123457 --pretty
```

Используйте `--base-url` или переменную окружения `BASE_URL`, если API не на `http://127.0.0.1:8000`.

**Интерактивный режим** (запрос базового URL, затем меню: ISRC, UPC, `/health`, `/ready`, `/openapi.json`):

```bash
python client.py --interactive --pretty
```

---

## Переменные окружения (приложение)

Скопируйте `.env.example` в `.env` и настройте значения. Ниже — основные параметры **приложения** (переменные nginx перечислены в предыдущей таблице).

| Переменная | Назначение |
|------------|------------|
| `APP_VERSION` | Строка версии в OpenAPI `info.version`; по умолчанию `0.1.0`. |
| `OPENAPI_SERVER_URL` | Базовый URL в OpenAPI **`servers`** для **Try it out**. Пустая строка убирает `servers` из схемы. |
| `READY_CHECK_URL` | Опционально: URL для проверки в `GET /ready`; при недоступности или `5xx` — ответ **503**. |
| `USER_AGENT` | Исходящий `User-Agent` для запросов к провайдерам. |
| `HTTP_TIMEOUT_S` | Таймаут httpx в секундах; по умолчанию `15`. |
| `HTTP_GET_MAX_RETRIES` | Дополнительные попытки GET при таймаутах/обрыве или `502`/`503`/`504`; по умолчанию `2`. |
| `HTTP_GET_RETRY_BACKOFF_S` | Базовая задержка (сек) для экспоненциального backoff между повторами. |
| `OUTBOUND_MAX_CONCURRENT` | Ограничение параллельных исходящих GET (семафор); `0` — без ограничения. |
| `MAX_RESPONSE_BODY_BYTES` | Верхняя граница размера тела ответа провайдера при стриминге (по умолчанию `2000000`); превышение обрабатывается как сбой провайдера. |
| `API_RATE_LIMIT_PER_MINUTE` | Скользящее окно по IP на 60 с для API, исключая `/health`, `/ready` и статику OpenAPI. `0` — отключить. |
| `DISCOGS_CONSUMER_KEY` / `DISCOGS_LOGIN` | **Consumer Key** Discogs (в кабинете может называться «логин потребителя»). Синонимы — в `.env.example`. |
| `DISCOGS_CONSUMER_SECRET` / `DISCOGS_PASSWORD` | **Consumer Secret** — это **не** пароль от входа на discogs.com. Заголовок `Authorization: Discogs key=…, secret=…` ([документация](https://www.discogs.com/developers/#page:authentication)). |
| `DISCOGS_PERSONAL_ACCESS_TOKEN` | Опционально: личный токен; если задан — `Discogs token=…`, пара ключ/секрет не используется. |
| `PROVIDER_*_ENABLED` | Включение/выключение отдельных провайдеров (см. английскую таблицу выше — те же имена). |
| `LOOKUP_CACHE_*` | Кэш полных ответов lookup в памяти: включение, TTL, максимум записей. |
| `OPEN_LIBRARY_SEARCH_URL` | Endpoint Open Library `search.json` (обычно менять не нужно). |
| `LOG_*` | Уровень логирования, путь к ротируемому файлу, размер и число ротаций. |
| `CORS_ALLOW_ORIGINS` | CORS для браузера: `*`, список через запятую или пустая строка (middleware отключён). |

---

## HTTP API

| Метод | Путь | Описание |
|-------|------|----------|
| `GET` | `/health` | Liveness; используется Docker healthcheck. |
| `GET` | `/ready` | Readiness; при заданном `READY_CHECK_URL` — дополнительный HTTP GET. |
| `GET` | `/lookup/isrc/{code}` | Нормализация ISRC; **422** при неверном формате. |
| `GET` | `/lookup/upc/{code}` | Длина 8 / 12 / 13 цифр, проверка контрольной цифры; **422** при ошибке. |

В ответах ожидается заголовок **`X-Request-ID`**.

### Успешный lookup

При успешной обработке handler возвращает **200**, даже если часть провайдеров упала; детали — в `providers` и полях ошибок (часть «пустых» ошибочных строк может отфильтровываться — см. реализацию).

### Коды ошибок API

- **422 (валидация FastAPI/Pydantic):** структурированный `detail`, `type: "validation_error"`, `request_id`.
- **422 (бизнес-правила ISRC/UPC):** строковый `detail`, `type: "http_error"`, `request_id`.
- **Другие коды `HTTPException`:** `detail`, `type: "http_error"`, `request_id`.
- **429:** rate limit, `type: "rate_limited"`.
- **5xx непредвиденные:** `type: "internal_error"`, логирование со стеком.

### Swagger / Scalar: «Failed to fetch»

1. **`OPENAPI_SERVER_URL`** должен совпадать с URL в браузере, **включая порт**.
2. На сервере должен быть открыт **firewall** для опубликованных TCP-портов.
3. При ограничении **CORS** добавьте точный origin страницы с `/docs`.

### Ошибки nginx

При недоступности upstream или таймауте прокси nginx может вернуть компактный **JSON** с `source: "nginx"` для **502** / **504** (см. конфиги в каталоге `nginx/`).

---

## Таймауты, устойчивость и логи

Логика согласования таймаутов **httpx**, повторов, **`proxy_read_timeout`** nginx и параллельного опроса провайдеров совпадает с английским разделом **Timeouts, resilience, and logging**: суммарное время запроса определяется **самым медленным** провайдером (параллельный запуск), а не суммой всех.

Логи: **stdout/stderr** контейнера, опционально файлы в `./logs` и `./logs/nginx/` на хосте.

---

## Архитектура и заметки по дизайну

- **Сбор ответов:** параллельный опрос провайдеров; возможны дополнительные **подсказки** (поиск по тексту), если «жёсткий» поиск по коду не дал результата, но другие источники вернули название.
- **Исходящий HTTP:** общий устойчивый GET с лимитом параллелизма, ограничением размера тела и повторами там, где это уместно.
- **Входящий rate limit:** скользящее окно по IP в памяти процесса (не общее между репликами).
- **Нормализация и summary:** как в английском разделе **Architecture** — эвристика согласованности названий/исполнителей.
- **Кэш:** только в памяти процесса; для нескольких инстансов нужен внешний кэш (например Redis). Подробнее — `CHECKLIST.md`.

### Провайдеры (кратко)

**MusicBrainz** — основной структурированный источник для ISRC и штрихкодов с соблюдением лимита запросов. **Deezer** — публичный поиск без ключа. **Discogs** — по штрихкоду и эвристики по ISRC, нужна аутентификация Discogs. **Wikidata** — SPARQL по ISRC. **Open Library** — часто не про музыку, но даёт независимый сигнал для UPC.

Соблюдайте условия использования и лимиты каждого сервиса. Проект **не** является официальным клиентом перечисленных организаций.

### Ограничения и что улучшать в production

Как в английском разделе: общий кэш и rate limit для кластера, метрики, надёжные секреты, circuit breaker по провайдерам, явные SLO на внешние API. Список задач — в `CHECKLIST.md`.

---

## Тесты

```bash
python -m pytest
```

Тесты `tests/test_lookup_e2e.py` используют `httpx.MockTransport` без реальной сети.

---

## Структура репозитория (фрагмент)

| Путь | Роль |
|------|------|
| `app/main.py` | Приложение FastAPI, middleware. |
| `app/api/routes/` | Маршруты HTTP (`lookup`, `health`). |
| `app/services/lookup_service.py` | Оркестрация провайдеров и сбор ответа. |
| `app/providers/` | Интеграции с внешними источниками. |
| `app/schemas/lookup.py` | Модели ответов. |
| `nginx/` | Reverse proxy в Docker. |
| `docker-compose.yml` / `docker-compose.https.yml` | Запуск стека. |
| `client.py` | CLI для ручных проверок. |

---

<p align="center"><a href="#english">↑ English</a> · <a href="#russian">↑ Русский</a></p>
