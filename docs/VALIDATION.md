# Проверки

- Pytest: 183 тест проходит, включая regression test стартовых MCP schemas. Unit tests исполняют только точные developer seeds; кандидаты запускаются отдельным executor.
- Последний fixed acceptance: 25/30; реальные retrieval-кейсы — 8/13. Это не точность 30 ответов модели.
- Чистый bootstrap: прошёл с отдельной копией исходников и пустыми данными, с кешированными Docker layers. PDF/веса скачаны заново. Проверены init и индекс, не полный новый UI с review: [cold-start-evidence.json](cold-start-evidence.json).
- Пять native UI gateway задач на Lite: report/web/hybrid answered, forecast forecasted, out_of_scope. Каждая имеет реальный Analyst trace; модели проверены по native call records. [Результаты](native-lite-delivery-evidence.json), [диалоги](../examples/demo_dialogues.md).
- Исправлены переполнение полного synthesis prompt, примесь старых PDF в свежий web-контекст и различие report query в обычном/hybrid запросе. Цитаты и числа проверяются прежними контрактами. До исправления web/hybrid были partial: [история](lite-delivery-evidence.json).
- Native delivery без инструментов вызывает один report-first pipeline; неподтверждённый текст модели не отдаётся. Structural checks не доказывают семантическую полноту: report ответ по H1 цитирует весь 2026 год. Это остаётся ограничением RAG.
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
