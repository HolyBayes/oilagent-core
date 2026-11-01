# OilAgent — интеграционный прототип

Первый этап тестового задания «Нефтегазовый аналитик». Сейчас реализованы общий LangGraph core, два настоящих HTTP MCP-сервиса и узкий Git backend кандидатов. **RAG, web, прогнозирование, UI, полноценная оценка качества и выпуск релизов ещё не реализованы.** Аналитический вызов честно возвращает `integration_only`, без вымышленных рыночных ответов.

Архитектура: [ARCHITECTURE.md](ARCHITECTURE.md). Фактические результаты: [docs/INTEGRATION_STATUS.md](docs/INTEGRATION_STATUS.md).

## Два репозитория

Код находится в `OilAgent/core`, артефакты самоулучшений — в соседнем `OilAgent/evolution`. У каждого собственные `.git` и коммиты; core не содержит tracked nested evolution. Source instruction skill хранится в evolution. Подробнее: [docs/VERSIONING.md](docs/VERSIONING.md).

Все команды ниже выполняются **из core/**. В текущем workspace уже есть окружение `../.venv` — его можно активировать через `source ../.venv/bin/activate`; создание нового окружения ниже нужно для чистой установки. Заранее заполненный evolution не требуется: bootstrap или первый запуск Evolution MCP создаёт стартовые артефакты из core.

## Локальный запуск

Проверенная среда: Python 3.13.2, macOS ARM64, Git. Требуемая версия Python ≥3.11; Python 3.11 и Docker пока отдельно не проверены. Виртуальное окружение и upstream checkout исключены из Git.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock
python -m pip install --no-build-isolation --no-deps -e .
python scripts/bootstrap.py
pytest -q
python scripts/smoke_ouroboros.py
```

Bootstrap инициализирует отдельный соседний Evolution Git, если он отсутствует; существующую историю сохраняет. Upstream checkout по умолчанию находится в `../workspace/upstream/ouroboros`. Bootstrap скачивает **точный SHA** из `config/ouroboros-pin.json`, создаёт локальный `.env` с разными случайными MCP-токенами и сохраняет существующий `.env`. Не запускает LLM или полный runtime Ouroboros. `requirements.lock` — snapshot окружения прототипа, включая зависимости проверки upstream; не lock полного desktop-runtime Ouroboros.

Отсутствующая/пустая папка или Git без коммитов получают один seed commit: `policies/retrieval.json` и `ouroboros_skills/oilgas_analyst/SKILL.md`. Skill seed поставляется внутри Python-пакета core, в том числе wheel; после инициализации рабочая версия принадлежит evolution. Это не automatic review/enable или production release. Повторный запуск не добавляет коммитов и не заменяет существующую policy. Незакоммиченные конфликтующие артефакты или существующая история без требуемых main/policy дают явную ошибку вместо перезаписи.

Путь можно задать системной переменной:

```bash
export EVOLUTION_REPO_PATH=/absolute/path/to/evolution
python scripts/bootstrap.py
```

Приоритет: **системный environment → core/.env → ../evolution**. Относительный путь разрешается от core, не от shell cwd. Docker Compose использует переменную как source bind mount на хосте, внутри контейнера Git находится в `/evolution`. Каталог хоста должен быть доступен контейнерному пользователю на запись.

Smoke поднимает два процесса на свободных localhost-портах, проверяет 401 без токена, делает discovery и вызовы через **немодифицированный `ouroboros.mcp_client.MCPManager`**. Проверяется цепочка answer → propose → diff → checks → blocked review → status, идемпотентность proposal, отсутствие release. В конце процессы останавливаются, JSON evidence и логи остаются в `workspace/smoke/<run>/`. По умолчанию ключи LLM явно отключены в дочерних процессах, платных вызовов нет.

Если canonical evolution пока пуст, smoke читает встроенный seed skill и создаёт Git только в изолированном runtime. Канонический путь при этом не заполняется: для его инициализации служат bootstrap или Evolution MCP.

Загрузка instruction skill проверяется штатным upstream loader из external disk payload. Это **не** полный install/review/enable, не самостоятельный выбор tools моделью Ouroboros и не успешная работа аналитика на реальных отчётах.

## Выбор модели

Оба сервиса используют общий adapter из `src/analyst/config.py`. Настройки в локальном `.env`; ключи не публикуйте. Для GigaChat:

```dotenv
LLM_PROVIDER=gigachat
GIGACHAT_MODEL=GigaChat
GIGACHAT_CREDENTIALS=<локальный секрет>
GIGACHAT_SCOPE=GIGACHAT_API_PERS
GIGACHAT_CA_BUNDLE_FILE=/absolute/path/to/ca-bundle.pem
LLM_STRUCTURED_METHOD=function_calling
```

Scope зависит от вашего доступа. CA bundle нужен, если системное доверие не содержит нужную цепочку. Проверка TLS включена. [Официальная интеграция GigaChat](https://github.com/ai-forever/langchain-gigachat/blob/master/libs/gigachat/README.md).

Для OpenAI или совместимого внешнего API:

```dotenv
LLM_PROVIDER=openai
LLM_MODEL=<доступная модель>
LLM_BASE_URL=https://your-provider.example/v1
LLM_API_KEY=<локальный секрет>
LLM_STRUCTURED_METHOD=function_calling
```

Для официального OpenAI можно оставить `LLM_BASE_URL` пустым. Для локального OpenAI-совместимого сервера:

```dotenv
LLM_PROVIDER=local
LLM_MODEL=<установленная модель>
LLM_BASE_URL=http://127.0.0.1:11434/v1
LLM_API_KEY=
LLM_STRUCTURED_METHOD=function_calling
```

Это клиент локального API, не встроенный загрузчик весов. Модель/сервер должны поддерживать выбранный structured output. Доступны `function_calling`, `json_schema`, `json_mode`; поддержка конкретной комбинации требует живого smoke. Локальный профиль требует явного endpoint, ключ необязателен. Настройка модели аналитика не настраивает автоматически модель полного runtime Ouroboros.

После настройки явный запуск с разрешением model calls:

```bash
python scripts/smoke_ouroboros.py --live
```

Будут выполнены routing и отдельный critic. Это ещё не авторство кандидата LLM: smoke отправляет заранее заданную policy, чтобы проверить интерфейс. Полный агентный прогон — следующий gate после настройки runtime Ouroboros.

## Два сервиса

```bash
python -m analyst.mcp_server analyst --port 8011
python -m analyst.mcp_server evolution --port 8012
```

У каждого endpoint `/mcp` и свой `Authorization: Bearer <token>` из `.env`. По умолчанию слушают только `127.0.0.1`.

| Analyst MCP | Evolution MCP |
|---|---|
| `health`, `answer_question` | `propose_change`, `get_diff`, `run_checks`, `request_review`, `get_status` |

`get_status` без ID возвращает baseline SHA. Изменять можно только `policies/retrieval.json` по строгой Pydantic schema; неизвестные поля и пути отклоняются. Кандидат — отдельный Git commit/branch в соседнем `../evolution`, без изменения его main и developer core. `EVOLUTION_REPO_PATH` задаёт Git checkout, `WORKSPACE_PATH` — ignored state/logs вне него. Git запускается списком аргументов без shell. `propose_change` идемпотентен по ключу, конфликт аргументов отклоняется. Состояния persisted, операции сериализованы lock.

`run_checks` использует фиксированную **синтетическую** ranked-list fixture: переход pooled → per_publisher повышает покрытие издателей с 0.5 до 1.0. Это проверка работающей ветви policy, не blind eval и не доказательство качества retrieval. Отсутствие улучшения отклоняется. Без модели critic получает `REVIEW_BLOCKED`. Даже при critic APPROVE остаётся `REVIEWED_UNRELEASED`: release/approval/merge endpoint отсутствует.

Прототип не исполняет candidate Python и не предоставляет shell tools. OS-изоляция автора Ouroboros от trusted runner пока не продемонстрирована; разные bearer-токены сами по себе её не обеспечивают. Пока нет production security или денежных гарантий; доступны request timeouts, ограниченный output и отсутствие автоматических retries модели.

## Контейнеры

```bash
docker compose up --build
```

Поднимает только два MCP-процесса. Токены берутся из `.env`; upstream Ouroboros и UI в compose не включены. Порты опубликованы только на localhost. Evolution service монтирует `../evolution` в `/evolution`; runtime statuses находятся в отдельном named volume. UID контейнера должен иметь write-доступ к этому checkout; не меняйте права всего core ради доступа. В профиле local endpoint относится к контейнеру; для модели на macOS host используйте `http://host.docker.internal:<port>/v1`. Docker build/run ещё не проверены: в текущем окружении daemon недоступен.

## Проверки и объём

```bash
ruff check src scripts tests
ruff format --check src scripts tests
pytest -q
find src scripts tests -name '*.py' -type f -exec wc -l {} +
```

Тесты проверяют защищённые пути/schema, Git isolation main/candidate, повторные proposal/conflicts после рестарта, no-improvement reject, fail-closed critic, отсутствие вымышленных ответов и конфигурацию трёх провайдеров. Успех этих тестов не заменяет eval на публичном корпусе и полноценный Ouroboros agent run.
