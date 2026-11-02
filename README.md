# OilAgent

Нефтегазовый аналитик для публичных данных: native UI Ouroboros → Analyst MCP → LangGraph, локальный RAG OPEC/EIA, web, расчётные ARIMA/ETS и сценарии сокращения добычи. Отдельный Evolution MCP создаёт Git-кандидатов retrieval-policy, инструкций и Python-методов skills; оценка, critic и операторский выпуск отделены от аналитики.

Фактический статус и ограничения: [INTEGRATION_STATUS](docs/INTEGRATION_STATUS.md). Краткий отчёт: [ARCHITECTURE_SUMMARY](docs/ARCHITECTURE_SUMMARY.md). Архитектура: [ARCHITECTURE.md](ARCHITECTURE.md). Реальные примеры: [demo_dialogues](examples/demo_dialogues.md).

## Развёртывание и вход в UI

Нужны запущенный Docker Desktop/Engine с Compose v2, Python 3 и доступ к выбранной модели. Все команды ниже выполняются из `OilAgent/core/`.

1. Подготовьте конфигурацию, сохранив существующую, если она уже есть:

   ```bash
   cd /path/to/OilAgent/core
   if [ ! -f .env ]; then cp .env.example .env; fi
   chmod 600 .env
   ```

   В `.env` задайте `LLM_PROVIDER=gigachat`, `GIGACHAT_MODEL=GigaChat-2`, `GIGACHAT_CREDENTIALS` (Authorization key) и соответствующий `GIGACHAT_SCOPE`. При необходимости укажите `GIGACHAT_CA_BUNDLE_FILE`. Профили OpenAI/local описаны ниже. Секреты остаются в локальном `.env`.

2. Соберите и запустите сервисы:

   ```bash
   ./run.sh -d
   ./compose.sh ps -a
   ./compose.sh logs --tail 50 init analyst evolution ouroboros
   ```

   `run.sh` заполнит пустые MCP-токены разными случайными значениями. Если `.env` отсутствует, скрипт создаст его сам; доступ к модели всё равно нужно настроить. Дождитесь успешного завершения `init`, healthy у `analyst`/`evolution` и запуска `ouroboros`. Первая сборка и индексация могут занять заметное время.

3. Откройте **<http://127.0.0.1:8765>** в браузере на машине запуска. Это native UI Ouroboros. В **Skills** видны четыре пакета из раздела ниже. Для первоначальной фиксации пакета выполните seed → restart → review → enable по инструкции «Самоулучшение skills и Python». Review вызывает модель; скрытого платного review при старте нет. Результат для тех же байтов в той же установке переиспользуется.

4. В чате **Main** отправьте, например: «Построй прогноз Brent на 3 месяца методами ARIMA и ETS, покажи интервалы и источник исторических данных». Для этого запроса Main может вызвать `forecast(asset="brent", ...)` напрямую. Ответ должен содержать обе модели, источник и request ID. Один лишь доступный UI ещё не подтверждает доступ к модели или успешное выполнение MCP.

По умолчанию UI слушает только loopback хоста; MCP доступны на `http://127.0.0.1:8011/mcp` и `http://127.0.0.1:8012/mcp` с Bearer-токенами из `.env`. MCP URL не является адресом UI. Для удалённого сервера можно пробросить UI по SSH: `ssh -L 8765:127.0.0.1:8765 user@server`, затем открыть тот же адрес в локальном браузере.

Команда собирает CPU-образы, готовит независимый evolution Git, проверяет/загружает PDF и индексирует их, затем поднимает private executor, два MCP и native UI. Данные контейнерной установки находятся в `workspace/container/`; публичные PDF/веса из имеющегося локального кеша переиспользуются. Загрузка с нуля зависит от доступности OPEC/EIA/Hugging Face. Первичная попытка download из Docker получила TLS timeout; запуск с проверенным кешем и новым Linux-индексом подтверждён. Повторный запуск сохраняет Git, индекс, диалоги, review и кеш цен.

Если порты заняты, используйте `UI_PORT=8875 ANALYST_PORT=8811 EVOLUTION_PORT=8812 ./run.sh -d` и откройте **<http://127.0.0.1:8875>**. Для постоянной настройки запишите эти переменные в `.env`. `DEPLOY_WORKSPACE` задаёт каталог deployment state, `EVOLUTION_REPO_PATH` — путь к независимому evolution Git (по умолчанию `../evolution`). Текущая контейнерная установка использует UI 8765 и MCP 8811/8812 (host-порты 8011/8012 заняты); эти overrides сохранены в локальном `.env`. Ранее проверялись отдельные host/UI 8765 и Docker/UI 8875; их исторические диалоги/review относятся к тем установкам.

```bash
./compose.sh ps
./compose.sh logs --tail 30 analyst evolution ouroboros
./compose.sh down
# После изменения .env или обновления кода:
./run.sh -d
```

`down` останавливает сервисы, сохранённые данные остаются. UI авторского контура имеет read-only core/evolution, не видит eval-набор и Docker socket. Выпуск разрешён только операторскому CLI на хосте. [Проверка контейнеров](docs/deployment-evidence.json).

Если UI не открывается, проверьте `./compose.sh ps -a` и логи: ошибка `init` блокирует зависимые сервисы. Ошибки модели смотрите в логах `analyst`/`ouroboros`; после исправления `.env` повторите `./run.sh -d`. Первый запуск без готового кеша требует сетевого доступа к источникам PDF и моделей.

## Files: исходные данные без копий для UI

`USER_FILES_PATH` задаёт единый физический каталог (по умолчанию `core/workspace/files`). Native Files открывает именно его; те же файлы напрямую смонтированы в init/Analyst/Evolution:

- `OilAgent/Reports/` — загруженные OPEC/EIA PDF;
- `OilAgent/Prices/` — исторические CSV, provenance и указатель текущего snapshot;
- `OilAgent/Models/` — кеш весов и tokenizer;
- пользовательские uploads и Deliverables — в том же дереве Files.

Загрузчики сразу пишут сюда. Старые `workspace/reports|prices|models` и контейнерные cache-пути после миграции становятся ссылками на эти данные. Перенос не скачивает файлы заново; разные старые указатели/документы сохраняются в Imports, одинаковые копии объединяются. Перед первым переносом старых bind mounts `run.sh` останавливает сервисы; последующие старты не требуют миграции. Путь Files не включает `.env`, native settings, traces или evaluator. Наличие нового PDF в Files само по себе не добавляет его в фиксированный RAG corpus: corpus manifest остаётся операторским.

## Skills, subagents и границы текущей интеграции

В native UI регистрируются четыре instruction skills из `evolution/ouroboros_skills/`. Каждый имеет собственную версию, hash-bound review и переключатель включения:

| Skill | Назначение | MCP |
|---|---|---|
| `oilgas_analyst` | Координация, итоговый ответ и явные improvement experiments | `answer_question`, Evolution MCP |
| `report_rag` | Датированные PDF, сопоставление и цитаты | `search_reports`, `answer_question` |
| `web_research` | Свежие публикации, даты и тип источника | `search_web_sources`, `market_quote` |
| `oil_forecast` | Новые ARIMA/ETS и supply-cut сценарии | `forecast(asset="brent", ...)`, `supply_cut` |

При первой установке выполните seed → native restart → review → enable из раздела ниже. Python-методы ARIMA/ETS, сценария, chunking, reranking и поиска живут в тех же пакетах evolution. Core сохраняет MCP, загрузку/кеш данных, контракты, метрики и выпуск. Методы выполняются отдельным изолированным сервисом, а не импортируются в MCP. На существующем evolution обновление developer seed не перезаписывает инструкции автоматически.

Main имеет прямой доступ к Forecast MCP. Для простого прогноза делегирование не нужно. Для составной задачи настроены штатные API-model subagents `report-analyst`, `web-analyst`, `forecast-analyst`; отдельный `oilagent-reviewer` участвует в review. Ouroboros может отображать ID как `модель~row-id`, поскольку все используют один provider. В Settings → Agents доступны roster и настройки; выполненные дочерние задачи появляются после фактического `schedule_subagent`, а не при одном открытии UI.

Делегирование работает через native `schedule_subagent`/`wait_tasks`/`get_task_result`: не более двух одновременных детей, один уровень вложенности, без file-write/shell и Evolution mutations у детей. Launcher устанавливает одинаковые guards/schema/delivery adapters и в Main, и в spawn/forkserver workers. Specialist — отдельная сессия; skill — инструкции, которые она использует. Для простых запросов дополнительные модельные вызовы не требуются.

### Самоулучшение skills и Python

`read_skill`/`propose_skill` читают и меняют инструкции. `read_code`/`propose_code` работают с пятью фиксированными слотами `forecast`, `scenario`, `chunking`, `reranking`, `search_strategy`; Python экспортирует `run(request)`. Кандидат получает отдельный Git-коммит, версия owning skill повышается; main и serving не меняются. Нужен существующий trace.

Проверки Python выполняют реальные методы в изоляции, сравнивают с serving baseline на фиксированных метриках и требуют улучшения без индивидуальных регрессий. Для нового chunking строится отдельный индекс по хешу реализации. Это **не слепой holdout**. Проверки инструкций делают платные парные вызовы модели для выбора MCP/аргументов; policy использует PDF без LLM. Далее нужен отдельный critic. Агент не получает shell, merge, release или enable.

Пакет публикуется целиком: инструкции + методы одной immutable версии. На время stage приём аналитических вызовов закрывается. После native restart/review атомарный pointer выбирает пакет и соответствующий индекс; один запрос закрепляет одну версию методов. Подробности границы изоляции и критериев: [CODE_EVOLUTION_STATUS](docs/CODE_EVOLUTION_STATUS.md).

Операторские команды выполняются с установленными Python-зависимостями core (см. раздел проверок). Для контейнерной установки:

```bash
export WORKSPACE_PATH=workspace/container/evolution-runtime
export RELEASE_PATH=workspace/container/releases
# Один раз после первого ./run.sh: подготовить исходный пакет из evolution main.
python -m scripts.code_release seed --operator NAME
# Команда вернёт RELEASE_ID. После каждой подготовки нового пакета:
./compose.sh restart ouroboros
python -m scripts.code_release review RELEASE_ID
python -m scripts.code_release enable RELEASE_ID --operator NAME
```

`review` использует GigaChat Lite и переиспользует действующие clean reviews точных хешей. Можно выполнить Review в UI, затем CLI enable. Для кандидата с успешными checks/critic вместо `seed`:

```bash
python -m scripts.code_release stage CANDIDATE_ID --sha FULL_SHA --operator NAME
# Затем restart → review → enable с возвращённым RELEASE_ID.
python -m scripts.code_release status
# Откат: подготовить прежний пакет, затем тот же restart → review → enable.
python -m scripts.code_release rollback PREVIOUS_RELEASE_ID --operator NAME
# Отмена stage: вернуть активный source; приём останется закрыт до restart/enable.
python -m scripts.code_release abort STAGED_RELEASE_ID --operator NAME
```

Первичный seed не требует искусственного прироста качества: это воспроизводимая исходная реализация, а не самоулучшение. Он тоже требует native whole-package review. `seed` не перезаписывает действующий release. При откате новый Git-коммит восстанавливает skill files, сохраняя несвязанные файлы/policies. Legacy `skill_release.py` оставлен для старых instruction-only установок; в пакетной установке stage/enable используют единый выпуск.

### Обновление core или executor

Release привязан к хешам core, данных и executor. Обычный рестарт сохраняет хеш образа; изменённый runtime требует повторной проверки. До изменения кода/образа сохраните замеры старой версии, затем обновите код и выполните:

```bash
# На старой версии, с теми же WORKSPACE_PATH/RELEASE_PATH и реальным индексом:
export RAG_INDEX_PATH=workspace/container/rag
python -m scripts.qualify_runtime capture --operator NAME
# Сохраните RECEIPT_ID. После обновления кода:
./run.sh -d executor
python -m scripts.qualify_runtime qualify RECEIPT_ID --operator NAME
./run.sh -d
# Затем review → enable возвращённого RELEASE_ID, как выше.
```

Проверка сравнивает все пять методов с замерами до обновления. Она допускает только те же байты skills и те же данные, без регрессий; прирост не заявляется. Изменённый Python проходит обычный candidate/checks/critic. Между сменой runtime и активацией проверенного пакета вызовы закрыты проверкой identity. Не удаляйте active pointer для обхода проверки.

## Модель и конфигурация

Текущий профиль — GigaChat 2 Lite (`GigaChat-2` в API), по выбору пользователя для экономии. Прежние сквозные проверки и reviews выполнялись на GigaChat-2-Max; их результаты не считаются проверкой качества Lite. Сравнительного benchmark моделей не проводилось. [API-имя модели](https://developers.sber.ru/docs/ru/gigachat/guides/selecting-a-model).

```dotenv
LLM_PROVIDER=gigachat
GIGACHAT_MODEL=GigaChat-2
GIGACHAT_CREDENTIALS=
GIGACHAT_SCOPE=GIGACHAT_API_PERS
GIGACHAT_CA_BUNDLE_FILE=
LLM_MAX_OUTPUT_TOKENS=
```

Scope зависит от доступа. Custom CA bundle копируется в отдельный read-only mount; TLS verification включена. Пустое/отсутствующее `LLM_MAX_OUTPUT_TOKENS` или строка `None` не задаёт output cap в core SDK payload. Лимиты самого провайдера/платформы сохраняются. Автоматические retries core выключены. GigaChat-вызовы сериализованы общим файловым slot внутри установки. Независимые установки с одним ключом не следует нагружать одновременно; распределённой квоты аккаунта нет.

Другие профили:

```dotenv
LLM_PROVIDER=openai
LLM_MODEL=your-model
LLM_BASE_URL=https://your-compatible-endpoint/v1
LLM_API_KEY=
```

```dotenv
LLM_PROVIDER=local
LLM_MODEL=your-installed-model
LLM_BASE_URL=http://127.0.0.1:11434/v1
LLM_API_KEY=
```

В Docker адрес модели на macOS-хосте — `http://host.docker.internal:<port>/v1`. Нужна поддержка выбранного `LLM_STRUCTURED_METHOD=function_calling|json_schema|json_mode`. OpenAI/local покрыты офлайн-тестами конфигурации; **живые проверки пропущены по решению пользователя**.

Остальные параметры — в [.env.example](.env.example): пути, retrieval top-k, web freshness, request limits, retention, цены для optional cost reservation. System env имеет приоритет. Защитные schema/caps и фиксированные спецификации моделей не редактируются policy-кандидатом.

### Встроенный Codex как общий LLM-бэкенд

Ouroboros поддерживает model operations через `claudexor::codex=<model>` отдельно от делегирования coding sessions. Наш optional bridge `/oilagent/v1/chat/completions` направляет LLM-запросы core в тот же owned model route; инструменты выполняет core, bridge их не запускает. Список providers остаётся `gigachat|openai|local`.

Сначала подключите Codex через Accounts в native UI и выберите фактически доступный model ID. Затем для контейнерного запуска настройте `.env`:

```dotenv
LLM_PROVIDER=local
LLM_MODEL=claudexor::codex=MODEL_ID_FROM_UI
LLM_BASE_URL=http://ouroboros:8765/oilagent/v1
OUROBOROS_LLM_BRIDGE_ENABLED=true
LLM_API_KEY=VALUE_OF_LOCAL_LLM_BRIDGE_TOKEN
```

`run.sh` создаёт отдельный приватный `LLM_BRIDGE_TOKEN`; скопируйте его значение в `LLM_API_KEY` локально. Это внутренний Bearer-токен, не Codex OAuth token. Для host core вместо docker service URL используйте `http://127.0.0.1:8765/oilagent/v1`. Вызовите `./run.sh -d`: native Main/subagents используют Codex напрямую, Analyst/Evolution — через bridge. Текущий запуск остаётся на Lite; bridge по умолчанию выключен.

Bridge ограничен выбранным Codex model ID, не исполняет произвольные команды, сохраняет tools/tool_choice/usage и не подставляет нули вместо неизвестных token counts. Поддерживаются non-streaming calls и `LLM_STRUCTURED_METHOD=function_calling`; `response_format`/json_schema/json_mode отклоняются явно. Нет авторизованного model source — запрос завершится ошибкой, без скрытого fallback на другую модель. Контракт покрыт офлайн-тестами; **живая проверка Codex ещё не выполнена, подключённого harness в текущей установке нет**. [Codex app-server](https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server), [локальная реализация](scripts/native_bridge.py).

## Аналитические возможности

- PDF: два фиксированных публичных выпуска OPEC MOMR/EIA STEO за октябрь 2025, E5 на закреплённой revision и Chroma; источник, дата, PDF page и точные цитаты. PDF и веса не публикуются в Git; загрузчик проверяет SHA256. OPEC PDF не перераспространяется.
- Web: DuckDuckGo/DDGS и официальный RSS EIA без ключа. Доверенные домены читаются из committed main `evolution/policies/web_sources.json`; рабочие/candidate правки не активируются. Даты публикации и получения различаются. RSS — публикация/описание, DDGS — поисковая выдержка; чтение полной статьи не заявляется.
- Hybrid: независимый синтез report/web по своим вопросам и evidence, затем программное объединение ссылок и проверка полноты. Есть один repair на запрос; после отказа — явно помеченная подтверждённая выдержка/partial. Exact quote не доказывает смысловую релевантность.
- Forecast: ARIMA + ETS, горизонты 1–6 месяцев, nominal 80% prediction intervals, rolling calibration/test и naive benchmark. История EIA spot загружается через FRED только для непокрытых интервалов, без TTL и перезаписи кешированных значений. `start_date`/`end_date` — включительные даты истории. [Методика](docs/FORECAST.md).
- Scenario: условная оценка сокращения добычи по явным пользовательским P0/Q0/cut и диапазонам эластичностей. Это sensitivity analysis, не статистический прогноз; отсутствующие коэффициенты не придумываются.
- Котировки: последняя доступная delayed Brent/WTI futures quote с exchange/type/timestamp/unit; не подмена EIA spot и не real-time feed. Urals feed не подключён.
- Диалог: серверный session ID, последние шесть вопросов и параметры, SQLite TTL; предыдущий ответ не становится evidence. Новая policy закрепляется на новую сессию, несовместимое обновление core сбрасывает контекст.
- Сравнения: защищённая разность только двух проверенных measurements с совпадающими metric/geography/unit/period/vintage/type; несовместимость показывается явно.

Примеры:

```text
Что EIA в отчёте за октябрь 2025 прогнозировало для Brent в первом полугодии 2026?
Какие последние новости EIA о природном газе?
Рассчитай Brent на 3 месяца по состоянию на 2026-10-01, история 2016-01-01…2026-09-30.
А теперь на полгода?
Оцени сокращение на 2 млн б/с: цена 70 USD/bbl, добыча 100 млн б/с,
эластичность спроса [-0.3,-0.1], предложения [0,0.1], прочие условия неизменны.
```

Analyst MCP: `health`, `answer_question(question, session_id="")`, `forecast(asset="brent", ...)`, `supply_cut`, `market_quote`, `submit_feedback`, `search_reports`, `search_web_sources`. Native Main получает прямые аналитические MCP; для `answer_question` и `forecast` адаптер передаёт canonical core result с request ID.

## Самоулучшение и два Git

`core/` и соседний `evolution/` — самостоятельные репозитории. Путь evolution задаётся `EVOLUTION_REPO_PATH`; пустая папка/unborn Git подготавливается автоматически. Core, evaluator и schemas защищены; кандидат меняет retrieval-policy, инструкции skill либо один разрешённый Python-метод с версией его пакета.

Policy задаёт bounded strategy/top-k, reranker/вес и query-context той же PDF-страницы. Serving читает developer seed либо проверенный release bundle, **не незакоммиченные правки и не candidate branch**. Начальный serving сохраняет прежнее per-publisher поведение, baseline не ухудшался ради демонстрации.

Evolution MCP: `propose_change`, `propose_skill`, `read_skill`, `propose_code`, `read_code`, `get_diff`, `run_checks`, `request_review`, `get_status`. Нужен существующий request trace; число кандидатов ограничено. Для policy `run_checks` сравнивает настоящий PDF retrieval на замороженных development/validation случаях, требует роста и отсутствия регрессий. Critic доступен после PASS. Ни approval, ни merge/release, ни shell через MCP нет.

```bash
python scripts/release.py status
python scripts/release.py approve CANDIDATE_ID --sha FULL_CANDIDATE_SHA --operator YOUR_NAME
python scripts/release.py rollback PREVIOUS_RELEASE_ID
# Возврат к исходному поведению:
python scripts/release.py rollback developer-seed
```

CLI принимает только актуальные checks, APPROVE того же SHA и eval/code/corpus bindings. Bundle имеет hash, activation атомарна; interruption reconcile, tampering и rollback покрыты тестами. Нативный автор реально создал кандидата: score 5/19 → 7/19, но одна регрессия привела к **REJECTED**, без critic и активации. Это демонстрация работающего quality gate, не успешный production release. [Свидетельства](docs/evolution-run-evidence.json).

## Проверки и воспроизведение

Для запуска без Docker используйте Python 3.11+; проверены Python 3.13/macOS ARM64 и Linux ARM64 в контейнере:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.lock
pip install --no-deps -e .
./run.sh -d executor  # Численные методы требуют изолированный broker и на host.
python scripts/bootstrap.py
python scripts/index_reports.py --download
pytest -q
ruff check src runner scripts tests
ruff format --check src runner scripts tests
python scripts/eval_acceptance.py
python scripts/smoke_ouroboros.py
```

Последние две команды не вызывают модель. `smoke_ouroboros.py --live` требует явного разрешения на платные вызовы. Для host native runtime отдельное окружение и штатный review/enable: [LIVE_INTEGRATION](docs/LIVE_INTEGRATION.md). Traces: `TRACE_PATH`, очистка по `TRACE_RETENTION_DAYS`; `submit_feedback` сохраняет мнение отдельно от market evidence. `python scripts/replay.py REQUEST_ID` проверяет сохранённые цитаты без сети/LLM.

## Известные ограничения

Функциональные guards не делают аналитика безошибочным. В serving baseline фиксированный acceptance-набор даёт 25/30; пять retrieval-промахов сохраняются. Это не answer accuracy и не blind benchmark. ETS intervals имеют недостаточное фактическое coverage, naive на текущем backtest немного лучше. Web и provider могут быть недоступны; quote delayed, месячная EIA история имеет публикационный лаг. OCR, Python вне фиксированных method slots, торговля, private banking data и enterprise SSO/RBAC в задачу не входят.

Глобальный остаток квоты не выводится из суммы локальных usage. Native context дорогой: отдельный author run израсходовал 145537 prompt + 839 completion токенов. Отдельно учитываются cached tokens, review и прямые core-пробы. Денежная admission reservation требует заданных цен и явного output bound; при default None строгая денежная гарантия не заявляется.

Публикация GitHub/GitLab не выполнена: remote/целевой URL не задан, подключённый GitHub при read-only проверке не ответил. Локальные изменения версионируются в обоих Git; секреты и runtime state в Git не включаются.
