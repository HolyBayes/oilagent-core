# OilAgent

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

- `EVOLUTION_REPO_PATH`: отдельный Git, по умолчанию `../evolution`; пустой каталог подготавливается автоматически.
- `USER_FILES_PATH`: публичные отчёты, история и веса; по умолчанию `workspace/files`.
- `DEPLOY_WORKSPACE`: состояние контейнеров; по умолчанию `workspace/container`.
- `LLM_PROVIDER=gigachat|openai|local`. Для OpenAI/local задайте `LLM_MODEL`, `LLM_BASE_URL`, `LLM_API_KEY` (для local ключ необязателен). В Docker модель на macOS-хосте доступна через `host.docker.internal`.
- `LLM_MAX_OUTPUT_TOKENS=None`: приложение не задаёт output cap.

OpenAI/local живьём не проверялись по решению пользователя. Optional Codex bridge выключен; подключённого harness нет.

## Возможности и ограничения

Обычные профильные вопросы идут через `answer_question`: сначала отчёты, web дополняет недостающие или свежие данные. Источники маркируются отдельно. Для новых расчётов Main может напрямую вызвать `forecast(asset="brent", horizon_months=3, start_date="…", end_date="…")`. Диапазон истории кешируется; догружаются только пробелы.

Прогноз: ARIMA и ETS, горизонты 1–6 месяцев, номинальные 80% интервалы, rolling backtest и naive benchmark. Это не торговая рекомендация. Сценарий требует явных цены, объёма добычи, сокращения и эластичностей. Последняя котировка — delayed futures, не real-time spot; Urals feed не подключён.

RAG: два выпуска OPEC/EIA за октябрь 2025, E5 и Chroma. Фиксированный acceptance — 25/30, включая **8/13 retrieval-кейсов**; пять промахов остаются. Exact quote/number checks не доказывают смысловую полноту. Naive немного лучше выбранной прогнозной модели на проверенном срезе, покрытие ETS ниже номинального. Web/provider могут быть недоступны; ответ тогда partial или отказ от неподтверждённых выводов.

[Архитектура и причины решений](ARCHITECTURE.md) · [Проверки](docs/VALIDATION.md) · [Диалоги](examples/demo_dialogues.md) · [Оригинальное задание](docs/Разработка_AI_агента_«Нефтегазовый_аналитик».docx).

## Выпуск навыков

Инструкции и методы живут в отдельном `evolution` Git. Candidate не меняет serving. Checks требуют роста без регрессий, затем critic; публикация требует оператора и native review полного пакета. У агента нет shell/merge/enable.

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

Stage временно закрывает аналитические вызовы. При обновлении core/executor сначала на старой версии выполните `RAG_INDEX_PATH=workspace/container/rag python -m scripts.qualify_runtime capture --operator NAME`. После обновления: `./run.sh -d executor`, затем `RAG_INDEX_PATH=workspace/container/rag python -m scripts.qualify_runtime qualify RECEIPT_ID --operator NAME`, `./run.sh -d`, review/enable нового release. Это проверяет неизменные skills на новом runtime, без заявления об улучшении. Active pointer для обхода проверки удалять нельзя.

GitHub/GitLab remote пока не настроен. Перед сдачей нужны публикация, улучшение retrieval и более широкий набор живых проверок Lite.
