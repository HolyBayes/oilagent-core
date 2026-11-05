# Исходный код Core

Пакет `analyst` содержит MCP-серверы, аналитические сценарии и управление выпуском изменений.
[Запуск сервиса](../README.md#запуск) · [Архитектура](../ARCHITECTURE.md) · [Скрипты оператора](../scripts/README.md)

## Структура

```text
analyst/
├── __init__.py           # Объявление пакета.
│
├── mcp_server.py         # Analyst MCP и Evolution MCP: инструменты, HTTP, Bearer-токены.
├── graph.py              # LangGraph: маршрутизация, поиск, синтез и ответ.
├── contracts.py          # Схемы политики, маршрута, утверждений и вердикта critic.
├── config.py             # Пути, env, LLM-клиенты и структурированные ответы модели.
├── runtime.py            # Подготовка локального Ouroboros и его настроек.
├── capabilities.py       # Допуск к инструментам по состоянию скиллов в Ouroboros.
├── budget.py             # Лимиты времени, вызовов, входных данных и стоимости запроса.
├── provider_lock.py      # Сериализация вызовов GigaChat между процессами.
│
├── rag.py                # PDF, чанки, embeddings, индекс и поиск.
├── hyde.py               # Генерация и кеш поисковых представлений, HyDE-поиск.
├── ranking.py            # Лексическое BM25-ранжирование и обработка слов запроса.
├── retrieval.py          # Отбор доказательств по политике поиска и издателям.
├── evidence.py           # Контекст, проверка цитат и чисел, формирование ответа.
├── measurements.py       # Нормализация величин, единиц и периодов для сравнения.
├── web.py                # Web-поиск и политика доверенных источников.
├── feeds.py              # Резервный поиск новостей через официальные RSS.
│
├── prices.py             # Загрузка истории цен, кеш диапазонов и snapshots данных.
├── quotes.py             # Delayed-котировки фьючерсов Brent/WTI.
├── forecast.py           # Подготовка ряда, вызов метода прогноза и оформление результата.
├── scenario.py           # Входные параметры и вызов сценария сокращения предложения.
│
├── sessions.py           # Состояние аналитических диалогов в SQLite.
├── traces.py             # Записи выполнения запросов и обратная связь пользователя.
│
├── evolution.py          # Git-кандидаты, diff, checks и LLM-critic.
├── skill_evolution.py    # Создание, валидация и оценка кандидатов SKILL.md.
├── code_packages.py      # Слоты методов, валидация Python-кода и сборка пакетов.
├── code_evaluation.py    # Оценка Python-кандидатов и сравнение с baseline.
├── quality.py            # Оценка retrieval-policy на фиксированных PDF-кейсах.
├── code_releases.py      # Snapshot пакета, stage, native review, активация и откат.
├── skill_release.py      # Выпуск инструкций; в пакетном режиме — через code_releases.
├── releases.py           # Отдельный выпуск retrieval-policy и проверка его совместимости.
│
├── method_runtime.py     # Выбор метода из snapshot и закрепление версий на запрос.
├── method_contracts.py   # Проверка результатов изменяемых методов на стороне core.
├── code_executor.py      # HTTP-клиент изолированного executor.
│
└── seeds/                # Начальные версии для подготовки Evolution Git.
    ├── web_sources.json  # Начальная конфигурация web-источников.
    ├── oilgas_analyst/
    │   └── SKILL.md      # Общий аналитик и инструкции по самоулучшению.
    ├── oil_forecast/
    │   └── SKILL.md      # Инструкции прогнозирования.
    ├── report_rag/
    │   └── SKILL.md      # Инструкции анализа отчётов.
    ├── web_research/
    │   └── SKILL.md      # Инструкции web-поиска.
    └── implementations/
        ├── forecast.py        # Начальный алгоритм ARIMA/ETS.
        ├── scenario.py        # Начальный сценарный расчёт.
        ├── chunking.py        # Разбиение текста на фрагменты.
        ├── reranking.py       # Лексическое и гибридное ранжирование фрагментов.
        ├── query_strategy.py  # План HyDE, расширение запроса и слияние выдачи.
        └── search_strategy.py # Ранжирование web-результатов.
```

## Основные потоки

**Аналитика:** Ouroboros вызывает инструмент в `mcp_server.py`. Для `answer_question`
сценарий задаёт `graph.py`; специализированные инструменты вызывают поиск или расчёт напрямую.
`evidence.py` проверяет вхождение цитат, числа и поля. Семантическая проверка утверждений
по источникам пока не реализована.

**Исполнение Python:** `method_runtime.py` выбирает реализацию из активного snapshot,
`code_executor.py` отправляет её в [Isolated Python execution queue](../runner/README.md),
а `method_contracts.py` проверяет результат. Например, `analyst/forecast.py` готовит данные,
но сам алгоритм ARIMA/ETS находится в изменяемом методе `forecast`.

**Самоулучшение инструкций и методов:** агент по инструкциям скилла вызывает Evolution MCP →
`evolution.py` создаёт Git-кандидата → checks → наш LLM-critic по diff и метрикам →
операторский stage через `code_releases.py` → snapshot в `workspace` → перезапуск Ouroboros →
native review точного пакета → операторский enable. Активный snapshot предоставляет
обновлённые инструкции Ouroboros и код executor. Retrieval-policy выпускается отдельно
через `releases.py`, без native review.

`seeds/` содержит начальные шаблоны. Изменения в `evolution/` попадают в исполнение через
выпуск; исходники `core/src/` при этом не перезаписываются. Snapshot и данные находятся
в `workspace`, вне Git. Настройки моделей core независимы от настроек Main в UI Ouroboros;
HyDE имеет отдельные параметры провайдера и модели.
