# Проверки

| Проверка | Результат | Свидетельства |
|---|---|---|
| Офлайн | 233 локальных pytest, Ruff check/format | [CI](https://github.com/HolyBayes/oilagent-core/actions/workflows/ci.yml) |
| Запуск с нуля | Новый recursive clone, `.env`, данные, четыре первичных review/toggle, пять Main-задач | [JSON](from-zero-evidence.json) |
| Fixed acceptance | 30/30; поиск цитат 13/13, дополнительный набор 12/19 | [JSON](rag-evidence.json) |
| RAG strategy | 13/13; кандидат без прироста и ухудшенное слияние отклонены | [JSON](query-strategy-evidence.json) |
| Отключение модулей | Backend и native Main запрещают вызовы выключенного скилла | [Backend](module-gates-evidence.json), [UI](module-gates-native-evidence.json) |

В прогоне с нуля report/web/hybrid — `answered`, forecast — `forecasted`,
внепрофильный — `out_of_scope`. У всех есть backend traces; период 1H26 проверен вручную.
UI проверен через штатный HTTP API, не ручными кликами. Данные и review-кеши не переносились;
Docker build layers могли использовать кеш. [Диалоги](../examples/demo_dialogues.md).

Это небольшие известные наборы, а не общая точность ответов или blind benchmark.
Семь дополнительных RAG-кейсов не решены. Naive лучше выбранной прогнозной модели на проверенном срезе;
покрытие ETS ниже номинального. OpenAI/local и Codex bridge живьём не проверены.

## Воспроизведение

Из `core/` с установленными зависимостями:

```bash
pytest -q
ruff check src runner scripts tests
ruff format --check src runner scripts tests
```

`check_executor.py` проверяет изоляцию без LLM, `check_cold_start.py` — отдельный bootstrap.
`check_delivery.py` и `check_native_delivery.py` выполняют по пять платных сценариев на работающих
сервисах. Эти скрипты лежат в `scripts/`; native-проверка использует порт 8765 и сохраняет результаты в docs.

`benchmark_rag.py` сравнивает vector/hybrid/MultiQuery/HyDE по кешу;
`--generate` разрешает платные запросы. Для локальных RAG-оценок нужны пути
`WORKSPACE_PATH`, `RELEASE_PATH`, `RAG_INDEX_PATH` и работающий executor — см. [выпуск](../README.md#выпуск-навыков).
Остальные JSON в docs — история проверок; их model/identity/release могут отличаться от текущих.
