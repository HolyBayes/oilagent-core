# Проверки

- Pytest: 213 тестов проходят, включая regression test стартовых MCP schemas. Unit tests исполняют только точные developer seeds; кандидаты запускаются отдельным executor.
- Последний fixed acceptance в рабочем контейнере: 30/30; реальные retrieval-кейсы — 13/13 вместо 8/13. Дополнительный известный набор: 12/19 вместо 5/19, без регрессий. Это не точность ответов модели. [Результаты RAG](rag-evidence.json).
- Чистый bootstrap: прошёл с отдельной копией исходников и пустыми данными, с кешированными Docker layers. PDF/веса скачаны заново. Проверены init и индекс, не полный новый UI с review: [cold-start-evidence.json](cold-start-evidence.json).
- Пять native UI gateway задач на Lite: report/web/hybrid answered, forecast forecasted, out_of_scope. Каждая имеет реальный Analyst trace; модели проверены по native call records. [Результаты](native-lite-delivery-evidence.json), [диалоги](../examples/demo_dialogues.md).
- Исправлены переполнение полного synthesis prompt, примесь старых PDF в свежий web-контекст и различие report query в обычном/hybrid запросе. Цитаты и числа проверяются прежними контрактами. До исправления web/hybrid были partial: [история](lite-delivery-evidence.json).
- Native delivery без инструментов вызывает один report-first pipeline; неподтверждённый текст модели не отдаётся. Structural checks не доказывают семантическую полноту: report ответ по H1 цитирует весь 2026 год. Поиск нужных фрагментов H1 исправлен; полнота нового ответа модели отдельно не перепроверялась.
- OpenAI/local и Codex bridge живьём не проверены. Текущая установка — Lite; старые Max-прогоны не считаются проверками Lite.

## Воспроизведение

```bash
pytest -q
ruff check src runner scripts tests
ruff format --check src runner scripts tests
python scripts/check_executor.py          # Живая изоляция, без LLM.
python scripts/check_cold_start.py        # Отдельный bootstrap, без LLM.
python scripts/check_delivery.py          # Пять платных HTTP MCP сценариев.
python scripts/check_native_delivery.py   # Пять платных native UI gateway задач.
```

Дополнительные JSON-свидетельства в этой папке исторические: сверяйте identity/model/release. Живой цикл Python: нулевой прирост отклонён, неверный ABI остановлен; после developer repair — 1/3 → 3/3 на трёх fixed ranking cases, critic/review, активация, откат, восстановление. Это не доказательство общего улучшения web.

- Module gates: disabled/missing/stale skill и недоступный UI запрещают sync/async вызовы; неизвестный owner запрещает регистрацию. Публичный Forecast MCP, сценарий и native Main отклоняют расчёт при выключенном forecasting; включённый RAG работает. [Backend](module-gates-evidence.json), [native](module-gates-native-evidence.json).

## Сравнение поиска

13 известных вопросов к OPEC/EIA, одинаковый бюджет контекста и до четырёх страниц на издателя. Метрика — присутствие всех эталонных фрагментов в контексте; это не слепой тест. MultiQuery объединяет исходный запрос и два английских варианта через RRF; HyDE усредняет эмбеддинги запроса и гипотетического абзаца. Сгенерированный текст не становится источником или цитатой. Слияние MultiQuery сохраняет первое представление страницы; другие варианты слияния не проверены.

| Поиск | Подтверждения в контексте |
|---|---:|
| vector | 9/13 |
| hybrid | 13/13 |
| multiquery_vector | 8/13 |
| multiquery_hybrid | 12/13 |
| hyde_vector | 10/13 |
| hyde_hybrid | 13/13 |

Сравнение выше выполнено до смены настройки по умолчанию. По запросу пользователя сервис теперь использует HyDE + гибрид; прирост относительно гибридного поиска на этих вопросах не показан. Production HyDE имеет отдельную модель и prompt; новые живые генерации не проверялись. Офлайн проверены параметры MCP/Main, отдельный выбор провайдера/модели, бюджет, кеш и одновременные запросы, сохранение PDF-происхождения цитат. В рабочем контейнере проверены настройки Lite, сборка structured schema и HTTP MCP tools/list, без LLM-вызовов. Убраны повторяющийся текст/служебные поля из prompt, исправлены распознавание OPEC+ и кварталов; полные исходные доказательства сохранены. При проверке полного synthesis prompt все 13 наборов подтверждений сохранились. Семь промахов дополнительного набора остаются.

На английские варианты и гипотетические абзацы потрачено 13 запросов Lite, 3 676 токенов; повторное сравнение использует кеш. Время в JSON не включает генерацию и первоначальную загрузку модели. Реализации основаны на [HyDE](https://arxiv.org/abs/2212.10496) и [query fusion/RRF](https://developers.llamaindex.ai/python/framework/integrations/retrievers/reciprocal_rerank_fusion/); отдельный метод HyPO не реализован.

```bash
python scripts/eval_acceptance.py
python scripts/benchmark_rag.py             # Только кеш, без LLM.
# --generate разрешает платную генерацию недостающих вариантов.
```

Скриптам нужны пути WORKSPACE_PATH, RELEASE_PATH, RAG_INDEX_PATH работающей установки и доступ к локальному executor. Данные и эталоны при исправлении не менялись.
