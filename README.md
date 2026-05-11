# ISRC / UPC Lookup Aggregator

FastAPI-сервис: параллельный опрос публичных источников метаданных по **ISRC** и **UPC/EAN**, единый JSON, частичные ответы при сбоях отдельных провайдеров.

## Запуск (Docker)

```bash
docker compose up --build
```

API: `http://localhost:8000`  
Проверка: `curl http://localhost:8000/health`

**Интерактивная документация (после запуска):** [Swagger UI](http://localhost:8000/docs), [ReDoc](http://localhost:8000/redoc), [Scalar](http://localhost:8000/scalar). В Swagger или Scalar откройте группу **lookup**, выберите `GET /lookup/isrc/{code}` или `GET /lookup/upc/{code}`, нажмите **Execute** / **Test Request** и подставьте пример кода из описания параметра.

Примеры:

```bash
curl "http://localhost:8000/lookup/isrc/USRC17607839"
curl "http://localhost:8000/lookup/upc/5901234123457"
```

Локально без Docker:

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Переменные окружения

Проще всего начать с файла `.env`: скопируйте `.env.example` → `.env` и отредактируйте значения.

| Переменная | Назначение |
|------------|------------|
| `APP_VERSION` | Строка версии в OpenAPI (`info.version`), по умолчанию `0.1.0`. |
| `OPENAPI_SERVER_URL` | URL сервера в OpenAPI для **Try it out** (например `http://127.0.0.1:8000`). Пустое значение — список `servers` в схеме не задаётся. |
| `READY_CHECK_URL` | Опционально: URL, который проверяется в `GET /ready`. Если URL недоступен/даёт 5xx — `/ready` вернёт `503`. |
| `USER_AGENT` | Заголовок `User-Agent` для исходящих HTTP-запросов (MusicBrainz, Discogs, Wikidata). |
| `HTTP_TIMEOUT_S` | Таймаут httpx (секунды), по умолчанию `15`. |
| `HTTP_GET_MAX_RETRIES` | Дополнительные попытки GET при таймауте/обрыве или ответах `502`/`503`/`504` (по умолчанию `2`). |
| `HTTP_GET_RETRY_BACKOFF_S` | Базовая пауза экспоненциального backoff между попытками (секунды). |
| `OUTBOUND_MAX_CONCURRENT` | Одновременных исходящих GET к провайдерам (семафор); `0` — без лимита. |
| `MAX_RESPONSE_BODY_BYTES` | Верхняя граница размера тела ответа провайдера при чтении (по умолчанию `2000000`); при превышении провайдер получает ошибку как при сетевом сбое. |
| `API_RATE_LIMIT_PER_MINUTE` | Лимит запросов с одного IP на окно 60 с для API (кроме `/health`, `/ready`, OpenAPI). `0` — отключить. |
| `DISCOGS_PERSONAL_ACCESS_TOKEN` | Опционально: токен Discogs для более щадящих лимитов. |
| `PROVIDER_MUSICBRAINZ_ENABLED` | `true`/`false`, по умолчанию `true`. |
| `PROVIDER_DEEZER_ENABLED` | `true`/`false`, по умолчанию `true`. |
| `PROVIDER_DISCOGS_ENABLED` | `true`/`false`. |
| `PROVIDER_WIKIDATA_ENABLED` | `true`/`false` (только ISRC). |
| `PROVIDER_OPEN_LIBRARY_ENABLED` | `true`/`false` (только UPC). |
| `LOOKUP_CACHE_ENABLED` | In-memory кэш готовых ответов lookup, по умолчанию `true`. |
| `LOOKUP_CACHE_TTL_S` | TTL кэша в секундах (например `300`). При `0` кэш не создаётся. |
| `LOOKUP_CACHE_MAX_ENTRIES` | Верхняя граница числа записей в кэше (по умолчанию `512`). |
| `OPEN_LIBRARY_SEARCH_URL` | URL `.../search.json` Open Library (редко нужно менять). |

## Эндпоинты

- `GET /health` — для Docker healthcheck.
- `GET /ready` — readiness. Если задан `READY_CHECK_URL`, дополнительно проверяет доступность указанного URL.
- `GET /lookup/isrc/{code}` — нормализация ISRC (без учёта регистра и дефисов), `422` при неверном формате.
- `GET /lookup/upc/{code}` — цифры 8/12/13, для 12 и 13 — проверка контрольной цифры EAN/UPC-A.

## Architecture / Technical notes

- **Стек:** Python 3.12, FastAPI, httpx (async), Pydantic v2. **Playwright** в образ не включён: текущие провайдеры работают по HTTP/JSON (MusicBrainz, Discogs, Wikidata SPARQL). Тяжёлые JS-сайты (IFPI и т.п.) можно добавить отдельным stage в Dockerfile при появлении провайдера.
- **Провайдеры:**  
  - **musicbrainz** — записи по ISRC, релизы по штрихкоду. Соблюдение ~1 запрос/с к MusicBrainz (async lock).  
  - **deezer** — публичный поиск по каталогу Deezer; умеет `isrc:` и `upc:` без ключей (покрытие зависит от каталога).  
  - **discogs** — поиск релиза по штрихкоду; по ISRC — эвристический поиск (может не находить).  
  - **wikidata** — SPARQL по свойству P1243 (ISRC); для UPC не используется.  
  - **open_library** — поиск по каталогу Open Library (`search.json?q=…`); чаще находит книги/ISBN, для музыкальных UPC часто пусто, но даёт дополнительный независимый сигнал.
- **Публичные API и условия:** интеграции строятся на документированных HTTP API / SPARQL; соблюдайте лимиты и политики площадок — [MusicBrainz API](https://musicbrainz.org/doc/MusicBrainz_API), [Discogs API](https://www.discogs.com/developers/), [Wikidata Query Service](https://wikidata.org/wiki/Wikidata:Data_access) / [Terms of Use](https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use), [Open Library API](https://openlibrary.org/developers/api). Этот сервис не является официальным клиентом перечисленных организаций.
- **Кэш:** in-memory TTL по ключу `isrc:{code}` / `upc:{code}` внутри процесса; при нескольких репликах кэши не общие — для production смотреть Redis (см. CHECKLIST).
- **Оркестрация:** `asyncio.gather` по провайдерам; ошибки уходят в поле `error` у соответствующего элемента `providers`, общий ответ остаётся `200`.
- **Исходящие HTTP:** общий `resilient_get` — ограничение параллелизма (`OUTBOUND_MAX_CONCURRENT`), лимит размера тела ответа (`MAX_RESPONSE_BODY_BYTES`) при чтении, и ограниченные повторы только для идемпотентных GET при сетевых сбоях и `502`/`503`/`504` (без повторов на `4xx`).
- **Входящий rate limit:** скользящее окно 60 с на IP в памяти процесса (не общий для реплик); health/OpenAPI исключены.
- **Нормализация:** схлопывание пробелов для сравнения; в ответе сохраняются исходные строки от источника где применимо.
- **Summary:** `found_in` — число провайдеров с `found=true`. `confidence`: `high` при ≥2 согласованных названиях/артистах, `medium` при одном найденном или частичном согласии, `low` при противоречиях или отсутствии результатов.
- **PostgreSQL / Redis:** не используются; API без своей БД, кэш только в памяти процесса. Для production с несколькими репликами разумно добавить Redis (общий кэш + rate limit) и учёт квот — см. CHECKLIST.

## Тесты

```bash
pytest
```

Интеграционные тесты `tests/test_lookup_e2e.py` поднимают приложение через `create_app(http_client=…)` с `httpx.MockTransport`, без реальной сети. Для продакшен-подобного запуска используется `create_app()` без аргументов (см. `app/main.py`).
