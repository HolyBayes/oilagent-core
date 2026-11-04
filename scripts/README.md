# scripts

Команды подготовки, проверки и выпуска OilAgent, а также точки входа контейнеров.
Обычный запуск сервиса описан в [README Core](../README.md#запуск).

## Как запускать

Все команды ниже выполняются из `core/`, в Python-окружении проекта:

```bash
pip install -r requirements.lock
pip install --no-deps -e .
python -m scripts.index_reports --download
python -m scripts.eval_reports --split development
python -m scripts.eval_reports --split holdout
```

Индексация скачивает PDF и embedding-модель при отсутствии локальных копий.
Для выполнения методов нужен запущенный executor и корректные `RUNNER_URL` / `RUNNER_TOKEN`.
Для CLI, работающего с Docker-установкой, задайте пути из
[инструкции выпуска](../README.md#выпуск-навыков): иначе CLI может использовать отдельное локальное состояние.
Параметры подключения и секреты хранятся в `core/.env`; system env имеет приоритет.

## Данные и оценки

| Скрипт | Назначение |
|---|---|
| [index_reports.py](index_reports.py) | Загрузка и индексация PDF отчетов; `--download` скачивает корпус, `--query "…"` выполняет поиск |
| [search_web.py](search_web.py) | Web-поиск без API-ключа и LLM: `python -m scripts.search_web "запрос"`; `--historical` снимает фильтр свежести |
| [eval_reports.py](eval_reports.py) | Проверка reports retrieval на `development` или `holdout`; `--baseline` отключает вводный контекст страницы |
| [eval_acceptance.py](eval_acceptance.py) | Фиксированные проверки retrieval, маршрутизации и доказательств; без LLM, не заменяют живую проверку ответов |
| [benchmark_rag.py](benchmark_rag.py) | Сравнение разных вариантов RAG поиска, MultiQuery и HyDE на фиксированных вопросах; по умолчанию использует кеш |
| [replay.py](replay.py) | Проверка фактологической обоснованности сохранённого ответа (регуляркой): `python -m scripts.replay REQUEST_ID`; без сети, инструментов и LLM |

`benchmark_rag --generate` вызывает настроенную LLM для отсутствующих в кеше вариантов
запросов; `--generate --only-generate` только заполняет кеш. Результат сравнения —
`workspace/rag-benchmark.json`, кеш — `workspace/rag-queries/`.
Это оценка на известных вопросах, а не независимый тест качества ответов.

## Интеграционные проверки

Запускайте конкретную проверку, а не все скрипты подряд.
Отсутствие LLM-вызовов не означает отсутствие сетевых запросов или записи файлов.

| Скрипт | Что проверяет | Вызовы LLM |
|---|---|---|
| [check_executor.py](check_executor.py) | Изоляцию и ограничения работающего executor | Нет |
| [check_cold_start.py](check_cold_start.py) | Работу агента с пустым evolution в отдельном временном Docker-проекте; нужны Docker и сеть | Нет |
| [smoke_ouroboros.py](smoke_ouroboros.py) | Проверка совместимости MCP-сервисов репозитория с MCPManager Ouroboros; авторизацию MCP; работу evolution и forecasting MCP; нужен закреплённый upstream | Только с `--live` |
| [check_tool_schema.py](check_tool_schema.py) | Совместимость схем Evolution MCP с GigaChat function calling | Только с `--live` |
| [check_forecast_route.py](check_forecast_route.py) | Каталог Analyst MCP; с `--live` — выбор forecast моделью и расчёт | Только с `--live` |
| [check_skill_workflow.py](check_skill_workflow.py) | Проверка, что при явной инструкции вызывается нужный тул и создается новый скилл; отдельное состояние в `workspace/skill-probes/` | Только с `--live` |
| [check_code_workflow.py](check_code_workflow.py) | Проверяет цепочку «модель пишет Python-кандидата → Evolution MCP проверяет его → critic оценивает». | Обязателен `--live` |
| [check_delivery.py](check_delivery.py) | Пять сценариев через работающий Analyst MCP | Да, сразу при запуске |
| [check_native_delivery.py](check_native_delivery.py) | Сценарии через API Ouroboros | Да, сразу при запуске |

Например: `python -m scripts.check_executor`.
HTTP-проверки требуют запущенных сервисов, корректных портов и MCP-токенов;
аналитические вызовы — разрешённых навыков.
Проверки с `--live` расходуют токены настроенной модели.

Часть проверок перезаписывает JSON-доказательства в `docs/`, остальные сохраняют
результаты в `workspace/`. `check_native_delivery` читает сценарии из результата
`check_delivery`. `check_cold_start` проверяет init, но не полный цикл UI и native review.
У двух delivery-скриптов и `check_cold_start` нет CLI-парсера: даже `--help` запускает проверку.

## Выпуск и обновление

| Скрипт | Назначение |
|---|---|
| [code_release.py](code_release.py) | Выпуск пакета кода: `seed`, `stage`, `review`, `enable`, `rollback`, `abort`, `status` |
| [skill_release.py](skill_release.py) | Выпуск инструкций навыка: `stage`, `review`, `enable`, `rollback` |
| [release.py](release.py) | Отдельный выпуск retrieval-policy: `approve`, `rollback`, `status` |
| [qualify_runtime.py](qualify_runtime.py) | `capture` до изменения runtime и `qualify` после него: сравнение на фиксированной оценке |

Эти команды меняют состояние выпуска. Порядок действий и параметры — в
[README Core](../README.md#выпуск-навыков), флаги — через `--help` соответствующей команды.
Native review может вызвать LLM. Stage закрывает аналитические вызовы до активации;
одного успешного checks/critic недостаточно для выпуска.

## Служебные модули

Обычно вызываются запускными скриптами и контейнерами, а не вручную.

| Модуль | Назначение |
|---|---|
| [bootstrap.py](bootstrap.py) | Получает закреплённый upstream Ouroboros, создаёт `.env`, если его нет, и подготавливает Evolution Git |
| [prepare_storage.py](prepare_storage.py) | Переносит прежнее файловое хранилище в общую структуру UI Files |
| [prepare_submodules.py](prepare_submodules.py) | Готовит Compose mounts Git-метаданных Evolution при установке через submodules |
| [container_init.py](container_init.py) | Инициализирует Evolution Git и индекс PDF внутри контейнера, без LLM |
| [container_native.py](container_native.py) | Готовит приватные настройки контейнера и запускает native Ouroboros |
| [native_ouroboros.py](native_ouroboros.py) | Подключает адаптеры провайдера, ограничения инструментов и доставку ответов к Ouroboros |
| [native_worker.py](native_worker.py) | Подключает те же адаптеры в дочернем worker-процессе |
| [native_bridge.py](native_bridge.py) | Опциональный OpenAI-compatible endpoint поверх Codex-маршрута Ouroboros; по умолчанию выключен |
| [ouroboros_runtime.py](ouroboros_runtime.py) | Управляет отдельным локальным runtime без Docker: подготовка, сервер, установка/review навыков и отправка задач |
