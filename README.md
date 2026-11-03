# OilAgent Core

[Главная страница и recursive clone](https://github.com/HolyBayes/oilagent) · [Evolution](https://github.com/HolyBayes/oilagent-evolution)

Нефтегазовый аналитик: Ouroboros UI → Analyst MCP → LangGraph. Отчёты OPEC/EIA, web-поиск, прогноз Brent (ARIMA/ETS), сценарии сокращения добычи. Отдельный Evolution MCP предлагает изменения навыков и Python-методов.

## Запуск

Нужны Docker Desktop/Engine с Compose v2, Python 3.11+ и доступ к модели. Команды выполняются из `core/`.

```bash
cp .env.example .env  # Только при первой установке; существующий .env сохраните.
chmod 600 .env
```

В `.env` заполните `GIGACHAT_CREDENTIALS` и соответствующий `GIGACHAT_SCOPE`. При необходимости задайте `GIGACHAT_CA_BUNDLE_FILE`. Выбрана GigaChat Lite (`GigaChat-2`) для экономии; сравнительного benchmark моделей нет.

```bash
./run.sh -d
./compose.sh ps -a
```

UI: **http://127.0.0.1:8765**. В Skills выполните Review и включите `oilgas_analyst`, `oil_forecast`, `report_rag`, `web_research`. Review вызывает модель. В Main задайте вопрос, например: «Рассчитай Brent на 3 месяца с интервалами».

Первый запуск загружает публичные PDF и embedding-модель; нужны доступные EIA/OPEC/Hugging Face. Секреты и данные не входят в Git. Загруженные данные видны в Files без экспортных копий.

```bash
./compose.sh logs --tail 50 init analyst evolution ouroboros
./compose.sh down  # Данные сохраняются.
```

`UI_PORT`, `ANALYST_PORT`, `EVOLUTION_PORT`, `RUNNER_PORT` меняют порты. В текущей установке UI — 8765, MCP — 8811/8812. MCP требует Bearer-токены из `.env`; адрес MCP не является адресом UI.

## Конфигурация

Основные параметры перечислены в [.env.example](.env.example). System env имеет приоритет.

В Docker `REPORT_MANIFEST_PATH` — путь host-файла manifest, монтируемого read-only в init/Analyst/Evolution. PDF загружаются в Files/Reports. Изменение корпуса требует нового индекса и повторной квалификации выпуска; текущие fixed-кейсы относятся к frozen OPEC/EIA.

`WORKSPACE_PATH`, `RELEASE_PATH`, `RAG_INDEX_PATH`, `REPORTS_PATH`, `EMBEDDING_CACHE_PATH`, `TRACE_PATH`, `SESSION_DB_PATH`, `BRENT_DATA_PATH` задают пути при запуске Python CLI. В Compose внутренние пути фиксированы: host-размещение меняется через `DEPLOY_WORKSPACE`, `USER_FILES_PATH` и `EVOLUTION_REPO_PATH`. Произвольный CSV override через `BRENT_DATA_PATH` в Compose не подключён. Embedding/revision задаются в `config/embedding.json`; горизонты и границы истории являются контрактом, а не env-настройками.

- `EVOLUTION_REPO_PATH`: отдельный Git, по умолчанию `../evolution`; пустой каталог подготавливается автоматически.
- `USER_FILES_PATH`: публичные отчёты, история и веса; по умолчанию `workspace/files`.
- `DEPLOY_WORKSPACE`: состояние контейнеров; по умолчанию `workspace/container`.
- `LLM_PROVIDER=gigachat|openai|local`. Для OpenAI/local задайте `LLM_MODEL`, `LLM_BASE_URL`, `LLM_API_KEY` (для local ключ необязателен). В Docker модель на macOS-хосте доступна через `host.docker.internal`.
- `LLM_MAX_OUTPUT_TOKENS=None`: приложение не задаёт output cap.

OpenAI/local живьём не проверялись по решению пользователя. Optional Codex bridge выключен; подключённого harness нет.

## Возможности и ограничения

Обычные профильные вопросы идут через `answer_question`: сначала отчёты, web дополняет недостающие или свежие данные. Источники маркируются отдельно. Для новых расчётов Main может напрямую вызвать `forecast(asset="brent", horizon_months=3, start_date="…", end_date="…")`. Диапазон истории кешируется; догружаются только пробелы.

Прогноз: ARIMA и ETS, горизонты 1–6 месяцев, номинальные 80% интервалы, rolling backtest и naive benchmark. Это не торговая рекомендация. Сценарий требует явных цены, объёма добычи, сокращения и эластичностей. Последняя котировка — delayed futures, не real-time spot; Urals feed не подключён.

RAG: два выпуска OPEC/EIA за октябрь 2025, HyDE + E5/Chroma + BM25, контекст релевантного участка страницы. Фиксированный офлайн acceptance (без генерации HyDE) — 30/30, включая **13/13 retrieval-кейсов**; дополнительный известный набор — 12/19. Это проверка поиска цитат, а не полноты ответов модели. Сравнение с MultiQuery/HyDE — в [проверках](docs/VALIDATION.md). Naive немного лучше выбранной прогнозной модели на проверенном срезе, покрытие ETS ниже номинального. Web/provider могут быть недоступны; ответ тогда partial или отказ от неподтверждённых выводов.

[Архитектура и причины решений](ARCHITECTURE.md) · [Проверки](docs/VALIDATION.md) · [Диалоги](examples/demo_dialogues.md) · [Оригинальное задание](docs/Разработка_AI_агента_«Нефтегазовый_аналитик».docx).

## Выпуск навыков

Инструкции и методы живут в отдельном `evolution` Git. В `report_rag/query_strategy.py` агент может менять HyDE/MultiQuery, prompt, веса поисковых эмбеддингов и слияние результатов через `read_code` / `propose_code` со slot=`query_strategy`. Стартовые seeds core совпадают с поставляемыми методами evolution, включая web-ranking; это явно обновлённый developer baseline. Candidate не меняет serving. Checks требуют роста без регрессий, затем critic; публикация требует оператора и native review полного пакета. У агента нет shell/merge/enable.

Для operator CLI установите зависимости core в Python-окружение: `pip install -r requirements.lock && pip install --no-deps -e .`.

```bash
export WORKSPACE_PATH=workspace/container/evolution-runtime
export RELEASE_PATH=workspace/container/releases
# Один раз: зафиксировать начальный developer package; команда вернёт RELEASE_ID.
python -m scripts.code_release seed --operator NAME
# Для проверенного кандидата вместо seed:
python -m scripts.code_release stage CANDIDATE_ID --sha FULL_SHA --operator NAME
# Затем для возвращённого RELEASE_ID:
./compose.sh restart ouroboros
python -m scripts.code_release review RELEASE_ID
python -m scripts.code_release enable RELEASE_ID --operator NAME
# Откат также требует restart → review → enable:
python -m scripts.code_release rollback PREVIOUS_RELEASE_ID --operator NAME
```

HyDE использует отдельную модель: `RAG_HYDE_PROVIDER=gigachat`, `RAG_HYDE_MODEL=GigaChat-2` (Lite), независимо от основной LLM. Доступ берётся из соответствующих `GIGACHAT_*` или `LLM_*` параметров. Для `openai/local` задайте также `RAG_HYDE_MODEL` и `LLM_BASE_URL`/`LLM_API_KEY` по провайдеру. После изменения `.env` перезапустите `./run.sh -d`.

MCP: `search_reports(query="…", hyde_model="GigaChat-2")`; без `hyde_model` используется настройка сервиса. `hyde=false` отключает HyDE на один вызов, `RAG_HYDE_ENABLED=false` — по умолчанию и в Main. Один промах кеша добавляет один LLM-запрос в общий бюджет; повторения используют `RAG_INDEX_PATH/hyde.sqlite3`. При ошибке HyDE MCP возвращает ошибку, Main отмечает недоступность RAG. Текущая стратегия по умолчанию — HyDE; `hyde=false` пропускает модуль расширения запросов целиком. Гипотетический абзац используется только для эмбеддинга: источники и цитаты берутся из PDF.

Если форма Settings в Docker требует Network Password, задайте `OUROBOROS_REVIEW_MAX_CYCLES=2` в `.env` и выполните `./run.sh -d`. Это число review-попыток для каждого snapshot пакета.

Stage временно закрывает аналитические вызовы. При обновлении core/executor сначала на старой версии выполните `RAG_INDEX_PATH=workspace/container/rag python -m scripts.qualify_runtime capture --operator NAME`. После обновления: `./run.sh -d executor`, затем `RAG_INDEX_PATH=workspace/container/rag python -m scripts.qualify_runtime qualify RECEIPT_ID --operator NAME`, `./run.sh -d`, review/enable нового release. Это проверяет неизменные skills на новом runtime, без заявления об улучшении. Active pointer для обхода проверки удалять нельзя.

Для обновления старой установки с пятью slots сохраните capture до смены кода; после коммита точного developer extension в evolution выполните qualify с `--add-query-strategy`, затем обычные restart/review/enable. Этот флаг допускает только developer seed нового модуля и точные изменения двух инструкций; существующие методы и эталоны менять нельзя.

Совместимые версии core/evolution зафиксированы submodules в [oilagent](https://github.com/HolyBayes/oilagent). Дальнейшая работа: расширение корпуса и независимая проверка качества.

Переключатель Skills управляет доступом к методам в backend, включая прямые MCP-вызовы, `answer_question` и subagents. Состояние проверяется при вызове; при недоступном UI или устаревшем review выполнение запрещено. Обновление пакета не включает выключенные навыки.

Новый MCP-инструмент обязательно получает владельца в `config/capabilities.json`; без него регистрация запрещена. Внутренние методы используют `requires_skill`, Python slots — владельца из `SLOTS`. Проверки работают для sync и async. Служебные bootstrap/fixed evaluation используют внутренний контекст; передать его через MCP или env нельзя.

`code_release enable` активирует содержимое пакета, но не включает навыки: переключатели меняются только явным действием в UI.

`REQUEST_*` ограничивают один вызов `answer_question` или прямого аналитического MCP tool. Вложенный MCP-вызов переиспользует контекст бюджета. Кеш HyDE не расходует LLM-вызовы. Это не общий денежный лимит всей установки: native Main/review и Evolution checks/critic имеют отдельный учёт. Для двух разных моделей заданные цены дают лишь оценку, не финансовую гарантию.
