# OilAgent Core

MCP, LangGraph и изолированный Python executor для [OilAgent](https://github.com/HolyBayes/oilagent).
[Архитектура](ARCHITECTURE.md) · [Проверки](docs/VALIDATION.md) · [Диалоги](examples/demo_dialogues.md)

## Запуск

Нужны Docker с Compose v2, Python 3.11+ и доступ к LLM. Из папки `core/`:

```bash
cp .env.example .env  # Только при первой установке.
chmod 600 .env
# Заполните GIGACHAT_CREDENTIALS, scope и при необходимости CA bundle.
./run.sh -d
```

UI: **http://127.0.0.1:8765**. В Skills выполните Review и включите
`oilgas_analyst`, `oil_forecast`, `report_rag`, `web_research`. Review расходует токены.
Первый запуск скачивает PDF и embedding-модель; файлы видны в UI Files.

```bash
./compose.sh ps -a
./compose.sh logs --tail 50 init analyst evolution ouroboros
./compose.sh stop ouroboros  # Остановить UI.
./compose.sh down            # Остановить стек, сохранив данные.
```

## Конфигурация

Параметры — в [.env.example](.env.example); system env имеет приоритет.

| Параметры | Назначение |
|---|---|
| `LLM_PROVIDER` | `gigachat`, `openai` или `local` |
| `GIGACHAT_*` | Модель, credentials, scope, CA; по умолчанию Lite для экономии |
| `LLM_MODEL`, `LLM_BASE_URL`, `LLM_API_KEY` | OpenAI-compatible/local; для local ключ необязателен |
| `LLM_MAX_OUTPUT_TOKENS` | Пусто / `None`: output cap не отправляется провайдеру |
| `RAG_HYDE_ENABLED`, `RAG_HYDE_PROVIDER`, `RAG_HYDE_MODEL` | Расширение запросов; по умолчанию `true`, `gigachat`, `GigaChat-2` |
| `EVOLUTION_REPO_PATH` | Отдельный Git; по умолчанию `../evolution`, пустой каталог инициализируется |
| `USER_FILES_PATH`, `DEPLOY_WORKSPACE` | Файлы пользователя и состояние Docker |
| `REPORT_MANIFEST_PATH` | Host-файл manifest, подключаемый read-only в Docker |
| `UI_PORT`, `ANALYST_PORT`, `EVOLUTION_PORT`, `RUNNER_PORT` | Host-порты; MCP требует Bearer-токены из `.env` |
| `REQUEST_*` | Бюджет одного аналитического запроса; общий денежный лимит установки отсутствует |

Изменения `.env` применяются через `./run.sh -d`. Модель на macOS-хосте доступна
из Docker через `host.docker.internal`. OpenAI/local и выключенный Codex bridge живьём не проверялись.

В Compose внутренние пути фиксированы. `WORKSPACE_PATH`, `RELEASE_PATH`, `RAG_INDEX_PATH`,
`REPORTS_PATH`, `EMBEDDING_CACHE_PATH`, `TRACE_PATH`, `SESSION_DB_PATH`, `BRENT_DATA_PATH`
настраивают Python CLI; CSV override через `BRENT_DATA_PATH` в Compose не подключён.
Embedding/revision — в `config/embedding.json`. Новый корпус требует переиндексации и оценки выпуска.

HyDE использует отдельную модель и кеш. MCP `search_reports(query="…", hyde_model="…")`
переопределяет модель на вызов; `hyde=false` пропускает расширение запросов.
Кеш не расходует LLM-вызовы. Native Main/review и Evolution checks/critic учитываются отдельно.

## Выпуск навыков

Чат создаёт кандидата, запускает checks и critic. Применение выполняет оператор:
`stage → restart UI → native review → enable`. Stage закрывает аналитические вызовы до активации.
Native review проверяет точный пакет; enable сохраняет переключатели Skills.

Для CLI установите зависимости: `pip install -r requirements.lock && pip install --no-deps -e .`.
Из `core/` задайте пути Docker-установки:

```bash
export WORKSPACE_PATH=workspace/container/evolution-runtime
export RELEASE_PATH=workspace/container/releases
export RAG_INDEX_PATH=workspace/container/rag
```

После recursive clone `evolution` находится на detached HEAD. Перед выпуском проверьте,
что HEAD совпадает с `main`, и переключитесь на неё. При несовпадении сначала согласуйте baseline.

```bash
test "$(git -C ../evolution rev-parse HEAD)" = "$(git -C ../evolution rev-parse main)" && git -C ../evolution switch main
python -m scripts.code_release seed --operator NAME  # Один раз, если active release ещё нет.
```

Для кандидата вместо `seed` выполните `stage`; затем используйте возвращённый `RELEASE_ID`:

```bash
python -m scripts.code_release stage CANDIDATE_ID --sha FULL_SHA --operator NAME
./compose.sh restart ouroboros
python -m scripts.code_release review RELEASE_ID
python -m scripts.code_release enable RELEASE_ID --operator NAME
```

`rollback PREVIOUS_RELEASE_ID --operator NAME` готовит откат; затем нужны те же restart/review/enable.
Новый скилл после выпуска включает владелец в UI. Начальный запуск не требует CLI-выпуска.

## Обновление runtime

На старой версии выполните `python -m scripts.qualify_runtime capture --operator NAME`.
После обновления: `./run.sh -d executor`, затем
`python -m scripts.qualify_runtime qualify RECEIPT_ID --operator NAME`,
`./run.sh -d` и review/enable возвращённого release. Пути — как выше.
Не удаляйте active pointer для обхода проверки.

Если review исчерпал попытки после сбоя, настройте `OUROBOROS_REVIEW_MAX_CYCLES` в `.env`.
Это также позволяет изменить лимит, когда Docker UI отклоняет сохранение Settings без Network Password.
