# Архитектура

Ouroboros координирует Main, discovery навыков, specialist subagents и native review. Analyst MCP предоставляет стабильные инструменты; LangGraph выполняет поиск и проверку ответа. Evolution MCP создаёт предложения, оператор выпускает их.

```mermaid
flowchart LR
  UI[Ouroboros Main / subagents] --> MCP[Analyst MCP / LangGraph]
  MCP --> DATA[Отчёты, web, кеш истории]
  MCP --> RUN[Изолированный Python executor]
  REL[Immutable skill release] --> RUN
  REL --> UI
  UI --> EVO[Evolution MCP / candidate Git]
  EVO --> CHECK[Fixed checks / critic]
  CHECK --> OP[Оператор / native review]
  OP --> REL
```

## Разделение

- **core Git**: MCP, данные, контракты, проверка цитат, backtest, evaluator и release controls.
- **evolution Git**: четыре `SKILL.md`; forecast/scenario в `oil_forecast`, chunking/reranking в `report_rag`, search_strategy в `web_research`; retrieval/source policies.
- **workspace**: единственное Files-хранилище Reports/Prices/Models, индексы, traces, диалоги и immutable bundles. В Git не входит.

Методы экспортируют `run(request)`, получают только разрешённые данные. Core восстанавливает метаданные по исходным индексам и проверяет результаты; методы не могут подставить произвольные ссылки. Python из evolution не импортируется в MCP.

Executor не имеет host mounts, Docker socket и модельных секретов. Trusted parent помещает каждый job в chroot, меняет UID/GID, устанавливает seccomp и resource limits. Один job выполняется, до четырёх ждут не более десяти секунд. Есть wall timeout, ограничение вывода и очистка потомков. Это не защита от уязвимостей ядра.

## Аналитика

Фактические вопросы: report-first через `answer_question`; достаточные отчётные данные основные, web используется для пробелов и свежести. Свежие новости, котировки и новые расчёты допускают прямые инструменты. Источник, дата публикации и время получения различаются.

E5/Chroma выбраны для локального multilingual retrieval. PDF чанки сохраняют report/date/page и offsets. Web ограничен списком доверенных доменов; используется DDGS и RSS EIA без платного поискового ключа. Claims проверяются по исходным цитатам/числам; это структурная, а не полная смысловая проверка.

ARIMA(1,1,0) и damped ETS работают на log месячной цены. Core передаёт исторические префиксы, отдельно калибрует и оценивает интервалы по горизонту, сравнивает с naive. Модель выбирается на calibration, не на test. Supply-cut — условная чувствительность по явным пользовательским эластичностям.

## Самоулучшение

Кандидат меняет policy, инструкции или один из пяти фиксированных Python slots. Fixed paired checks требуют прироста без индивидуальных регрессий; тесты и эталоны остаются в core. Это не blind holdout. После PASS нужен critic; затем оператор stage, native restart/review и enable.

Инструкции и Python выпускаются одним snapshot. На переходе admission закрыт. Запрос закрепляет методы одной версии; chunking выбирает собственный индекс по хешу. Rollback восстанавливает skill files отдельным коммитом и переключает pointer. У разработчика остаётся право явного изменения baseline; это не считается доказанным самоулучшением.

## Компромиссы

Два frozen PDF ограничивают покрытие; нужен более широкий корпус и независимые кейсы. Номинальные интервалы не гарантируют 80% coverage. Lite выбран для экономии, сравнительной оценки моделей нет. Следующие приоритеты: качество retrieval, смысловая проверка ответов, проверка полного UI на чистой установке и публикация репозитория.

Авторизация модулей общая: protected registry связывает MCP/специалистов с навыками, а runtime проверяет enabled и актуальный native review перед исполнением. Неизвестный владелец запрещён. Gates стоят на MCP, внутренних методах и Python slots; инструкции модели не заменяют эти проверки. При публикации существующие переключатели сохраняются.
