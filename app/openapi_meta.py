"""Static OpenAPI / docs metadata (kept out of ``main`` for readability)."""

APP_OPENAPI_DESCRIPTION = """
Агрегирует метаданные по **ISRC** и **UPC/EAN** из нескольких публичных HTTP-источников
(MusicBrainz, Discogs, Wikidata SPARQL для ISRC, Open Library для UPC).

Ответ **200** даже при частичных сбоях: ошибки провайдеров попадают в поле `error` у
соответствующего элемента `providers`.
""".strip()

OPENAPI_TAGS_METADATA = [
    {
        "name": "lookup",
        "description": "Поиск метаданных по нормализованному ISRC или UPC/EAN.",
    },
    {
        "name": "service",
        "description": "Проверки живости и готовности процесса (без внешних зависимостей).",
    },
]
