# Интеграционный прототип: фактический статус

Дата: 1 ноября 2026. Это отчёт о проверках конкретного прототипа, не заключение о готовности аналитика.

## Подтверждено выполнением

- Ouroboros upstream 7.9.0 закреплён на полном SHA `add0ce3296c722ef99a536c52f8dcddf36494b36`.
- Два отдельных процесса FastMCP по HTTP, у каждого свой bearer-токен. Без токена — 401; токен Analyst не подходит Evolution.
- Немодифицированный `ouroboros.mcp_client.MCPManager` обнаружил и вызвал оба сервиса. Не использовались monkeypatch transport или mock MCP-клиент.
- Analyst MCP вызывает настоящий общий LangGraph graph; результат содержит request ID, evidence, claims и явный статус. Без модели/индекса — `insufficient_evidence`; реальный PDF-ответ проверен отдельно.
- Evolution MCP предоставляет пять методов. Предложение создаёт настоящий Git commit/branch; baseline main не меняется. Повтор proposal с тем же ключом возвращает прежний candidate. Изменённые аргументы с тем же ключом отклоняются.
- Exact diff и SHA256 получены через MCP. Защищённый путь `../core.py` отвергнут через реальный MCP-вызов.
- Fixed check исполняет реальную ветвь retrieval-policy на синтетической ranked-list fixture: publisher coverage 0.5 → 1.0. Это только интеграционный пример, не метрика на реальном корпусе.
- Без LLM critic возвращает `REVIEW_BLOCKED`, approval не создаётся. Во всём прототипе `release_available=false`; merge/release tools отсутствуют.
- Полный Ouroboros server запущен на pin. Local-source skill зарегистрирован штатно (для него copy/install не нужен), прошёл clean review exact hash и enable без owner-attestation. Подробности: [LIVE_INTEGRATION.md](LIVE_INTEGRATION.md).
- 103 offline-теста проходят. Покрыты отсутствующая/пустая папка, unborn Git main/master, повторный запуск, сохранение существующей policy и приоритет system env над .env. Ruff lint/format и `pip check` проходят. `docker compose config --quiet` проходит без раскрытия secrets.
- В коде поддержаны GigaChat, внешний OpenAI-compatible API и локальный OpenAI-compatible endpoint без обязательного ключа. Живые structured routing и domain critic проверены на GigaChat-2-Max; другие провайдеры пока проверены offline.

Сохранённый результат HTTP-прогона: [integration-evidence.json](integration-evidence.json). Генератор: [smoke_ouroboros.py](../scripts/smoke_ouroboros.py). Сырые логи и полный runtime state — в ignored workspace, без публикации tokens.

Реальный корпус: 154 PDF-страницы, 475 фрагментов. Успешный cited EIA answer и неудачные попытки, development diagnostics и расход 7192 токена (включая compact schema probe) сохранены в [RAG.md](RAG.md).

Политика web-источников находится в committed main evolution (`eedd606`); core содержит валидатор и bootstrap seed. Прямой MCP web-tool и ограниченный web-fallback graph реализованы без API-ключа. На web-этапе GigaChat не вызывался; последующие проверки PDF/forecast заняли 4424 токена. Native GigaChat сам выбрал MCP forecast tool, общий graph вернул forecasted.

Диапазоны истории передаются в MCP как `start_date`/`end_date`. Кеш по покрытию скачивает только недостающие интервалы, без TTL. Реальная HTTP MCP проверка с публичным FRED/EIA прошла без LLM: [history-cache-evidence.json](history-cache-evidence.json).

## Не подтверждено / не реализовано

- Полный autonomous Evolution author run остаётся неподтверждённым. Аналитические Main worker вызовы через native UI уже проверены: отчёт и расчёт выполняют настоящий Analyst MCP; финальный пересказ forecast неверно называет источник. UI принят только частично: [UI.md](UI.md).
- Полный author task получил HTTP 422 после enable MCP schemas; candidate не создан. Исправление inline schemas проверено offline и компактным native GigaChat probe (715 токенов); повтор полного Main worker не выполнен ради экономии.
- OS-изоляция и полный успешный model-authored цикл proposal/check/critic/release ещё не подтверждены; native skill review/enable и settings blocking проверены.
- Стабильный живой web-ответ через LLM: бесплатный DDGS backend ответил, но два adapter-запроса дали ошибку; граф проверен offline. [Свидетельства и ограничения](WEB.md). Сценарный расчёт и blind eval; исправление атрибуции источника в native UI. Расчётный forecast ARIMA/ETS реализован и проверен через MCP/GigaChat: [FORECAST.md](FORECAST.md). PDF corpus, локальные embeddings/Chroma и первый cited answer реализованы; ограничения и известный промах — в [RAG.md](RAG.md).
- Ручной release/approval/rollback, trust manifest, Developer Git release SHA и межверсионная совместимость. Core и evolution теперь оформлены отдельными соседними Git-репозиториями с коммитами; утверждённого production release ещё нет. Подробности: [VERSIONING.md](VERSIONING.md).
- OS/container sandbox автора Ouroboros и trusted runner. Раздельные токены/процессы сами по себе это не доказывают.
- Полные request budgets/cost accounting. В прототипе — model timeout, необязательный max output (по умолчанию None) и отключённые автоматические retries модели.
- Docker build/run: Docker daemon недоступен. Синтаксическая проверка compose не заменяет запуск контейнеров.
- Python 3.11, Linux и другие платформы: текущий успешный прогон — Python 3.13.2/macOS ARM64. Dockerfile использует Python 3.13.

## Следующие gates

1. Промах OPEC исправлен; отложенные вопросы показывают 4/9 вместо 3/9 без регрессий. Разобрать пять оставшихся промахов и расширить оценку на другие выпуски. Текущее присутствие издателей не доказывает фактическую полноту ответа. [Результаты](RETRIEVAL_EVAL.md).
2. Проверить живой web-answer при доступном бесплатном провайдере; подключить сценарный расчёт и закрыть ошибку источника в UI. Два forecast-метода с backtest уже проверены по HTTP MCP.
3. Связать кандидат retrieval-policy с реальной оценкой на корпусе; добавить human release/rollback и подтвердить isolation.
4. Не повторять тяжёлые платные Main worker пробы до устранения известных причин. Аналитические MCP-вызовы в UI подтверждены, авторский цикл Evolution и достоверный финальный пересказ остаются отдельными gates. Сохранить текущее hash-bound skill review.

Первичные источники интерфейсов: [Ouroboros MCP client на pin](https://github.com/razzant/ouroboros/blob/add0ce3296c722ef99a536c52f8dcddf36494b36/ouroboros/mcp_client.py), [skill loader на pin](https://github.com/razzant/ouroboros/blob/add0ce3296c722ef99a536c52f8dcddf36494b36/ouroboros/skill_loader.py), [официальная GigaChat интеграция](https://github.com/ai-forever/langchain-gigachat/blob/master/libs/gigachat/README.md).
