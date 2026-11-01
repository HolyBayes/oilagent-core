# Интеграционный прототип: фактический статус

Дата: 1 ноября 2026. Это отчёт о проверках конкретного прототипа, не заключение о готовности аналитика.

## Подтверждено выполнением

- Ouroboros upstream 7.9.0 закреплён на полном SHA `add0ce3296c722ef99a536c52f8dcddf36494b36`.
- Два отдельных процесса FastMCP по HTTP, у каждого свой bearer-токен. Без токена — 401; токен Analyst не подходит Evolution.
- Немодифицированный `ouroboros.mcp_client.MCPManager` обнаружил и вызвал оба сервиса. Не использовались monkeypatch transport или mock MCP-клиент.
- Analyst MCP вызывает настоящий общий LangGraph graph; результат содержит request ID и честный статус `integration_only`.
- Evolution MCP предоставляет пять методов. Предложение создаёт настоящий Git commit/branch; baseline main не меняется. Повтор proposal с тем же ключом возвращает прежний candidate. Изменённые аргументы с тем же ключом отклоняются.
- Exact diff и SHA256 получены через MCP. Защищённый путь `../core.py` отвергнут через реальный MCP-вызов.
- Fixed check исполняет реальную ветвь retrieval-policy на синтетической ranked-list fixture: publisher coverage 0.5 → 1.0. Это только интеграционный пример, не метрика на реальном корпусе.
- Без LLM critic возвращает `REVIEW_BLOCKED`, approval не создаётся. Во всём прототипе `release_available=false`; merge/release tools отсутствуют.
- Upstream skill loader разобрал подготовленный external instruction skill и вычислил content hash. Skill остался выключенным и без executable review. Plain disk loading не выдан за полный lifecycle install/review/enable.
- После проверки пустого evolution — 34 offline-теста проходят. Покрыты отсутствующая/пустая папка, unborn Git main/master, повторный запуск, сохранение существующей policy и приоритет system env над .env. Ruff lint/format и `pip check` проходят. `docker compose config --quiet` проходит без раскрытия secrets.
- В коде поддержаны GigaChat, внешний OpenAI-compatible API и локальный OpenAI-compatible endpoint без обязательного ключа. Конструкторы/конфигурация проверены offline, inference не выполнялся.

Сохранённый результат HTTP-прогона: [integration-evidence.json](integration-evidence.json). Генератор: [smoke_ouroboros.py](../scripts/smoke_ouroboros.py). Сырые логи и полный runtime state — в ignored workspace, без публикации tokens.

## Не подтверждено / не реализовано

- Полный autonomous run Ouroboros, выбор tools моделью и самостоятельное авторство кандидата. Smoke отправляет заданный candidate для проверки протокола.
- Живые structured routing и critic: доступ к модели ещё не настроен. `--live` без credentials/endpoint завершается до вызовов, не выдаёт успешный live status.
- Полный штатный lifecycle skill, mode/settings enforcement и модель полного runtime Ouroboros.
- Настоящий PDF corpus, embeddings/vector store, web, forecast, UI и blind eval.
- Ручной release/approval/rollback, trust manifest, Developer Git release SHA и межверсионная совместимость. Core и evolution теперь оформлены отдельными соседними Git-репозиториями с коммитами; утверждённого production release ещё нет. Подробности: [VERSIONING.md](VERSIONING.md).
- OS/container sandbox автора Ouroboros и trusted runner. Раздельные токены/процессы сами по себе это не доказывают.
- Полные request budgets/cost accounting. В прототипе — model timeout, max output и отключённые автоматические retries модели.
- Docker build/run: Docker daemon недоступен. Синтаксическая проверка compose не заменяет запуск контейнеров.
- Python 3.11, Linux и другие платформы: текущий успешный прогон — Python 3.13.2/macOS ARM64. Dockerfile использует Python 3.13.

## Следующие gates

1. Заполнить локальный `.env` для выбранной модели, выполнить `python scripts/smoke_ouroboros.py --live`. Это проверяет router/critic, но ещё не автономного автора.
2. Настроить pinned runtime Ouroboros, пройти штатное skill review/enable и инициировать один реальный ограниченный агентный цикл. Зафиксировать настройки, prompts/usage и фактическое авторство.
3. Подключить публичный PDF corpus и закончить первый проверяемый RAG-ответ. Затем web и два forecast-метода.
4. Заменить synthetic-only checks на фиксированный development/holdout eval, реализовать human release/rollback и подтвердить isolation.

Первичные источники интерфейсов: [Ouroboros MCP client на pin](https://github.com/razzant/ouroboros/blob/add0ce3296c722ef99a536c52f8dcddf36494b36/ouroboros/mcp_client.py), [skill loader на pin](https://github.com/razzant/ouroboros/blob/add0ce3296c722ef99a536c52f8dcddf36494b36/ouroboros/skill_loader.py), [официальная GigaChat интеграция](https://github.com/ai-forever/langchain-gigachat/blob/master/libs/gigachat/README.md).
