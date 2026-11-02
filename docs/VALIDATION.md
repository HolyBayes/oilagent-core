# Проверки

- Pytest: 181 тест проходит, включая regression test стартовых MCP schemas. Unit tests исполняют только точные developer seeds; кандидаты запускаются отдельным executor.
- Последний fixed acceptance: 25/30; реальные retrieval-кейсы — 8/13. Это не точность 30 ответов модели.
- Чистый bootstrap: прошёл с отдельной копией исходников и пустыми данными, с кешированными Docker layers. PDF/веса скачаны заново. Проверены init и индекс, не полный новый UI с review: [cold-start-evidence.json](cold-start-evidence.json).
- Пять новых Lite-сценариев через HTTP MCP: report answered, web partial, hybrid partial, forecast forecasted, out_of_scope. Статус answered сам по себе не доказывает смысловую полноту. [Диалоги](../examples/demo_dialogues.md), [данные](lite-delivery-evidence.json).
- Native report-first smoke выявил ответ без MCP и неподтверждённые цифры. Исправление: первичные схемы MCP загружаются сразу; выдача без аналитических инструментов блокируется. Итоговый native smoke прошёл через реальный Analyst MCP и вернул canonical partial с существующим request trace: [результат](report-first-final.json). Это подтверждает путь данных, но не полноту ответа на вопрос о полугодии.
- OpenAI/local и Codex bridge живьём не проверены. Текущая установка — Lite; старые Max-прогоны не считаются проверками Lite.

## Воспроизведение

```bash
pytest -q
ruff check src runner scripts tests
ruff format --check src runner scripts tests
python scripts/check_executor.py          # Живая изоляция, без LLM.
python scripts/check_cold_start.py        # Отдельный bootstrap, без LLM.
python scripts/check_delivery.py          # Пять платных Lite-сценариев.
```

Дополнительные JSON-свидетельства в этой папке исторические: сверяйте identity/model/release. Живой цикл Python: нулевой прирост отклонён, неверный ABI остановлен; после developer repair — 1/3 → 3/3 на трёх fixed ranking cases, critic/review, активация, откат, восстановление. Это не доказательство общего улучшения web.
