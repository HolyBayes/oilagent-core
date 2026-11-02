# Нефтегазовый аналитик: реализованное решение

2 ноября 2026. Два самостоятельных Git: core с доверенным кодом и evolution с policies/instruction skill. Ориентир по строкам снят; приоритет — читаемость и проверяемое поведение.

## Решения и причины

Native UI закреплённого Ouroboros вызывает один Analyst MCP/LangGraph. Это сохраняет обязательную платформу и единую аналитику. Выбран GigaChat-2-Max: доступен в Sber API и прошёл русскоязычные structured/tool проверки. OpenAI-compatible и local поддержаны, живые проверки по решению пользователя пропущены.

RAG использует E5/Chroma и два фиксированных публичных PDF OPEC/EIA. Manifest содержит даты, URL и hashes; numeric claims допускаются только с проверенных страниц. Web без платного ключа: DDGS и официальный RSS EIA, allowlist из committed main evolution. Hybrid отдельно обрабатывает report/web контексты и программно объединяет ссылки. Typed claims проверяются по IDs, точным цитатам и числам; это не доказательство смысла. При проблемах — один repair, затем partial или явно помеченная выдержка.

Forecast — реальные ARIMA и ETS, дополнительно naive. Есть rolling calibration/test по горизонту, nominal 80% prediction intervals, срез и source hashes. История EIA/FRED кешируется по покрытым датам, догружаются только пробелы. Supply-cut сценарий использует только явные пользовательские P0/Q0/cut/эластичности. Последняя биржевая котировка имеет timestamp/type и пометку delayed futures; она не подменяет spot.

SQLite хранит bounded context и release pin сессии. Request guards ограничивают время, input, tool/LLM calls и repair; shared provider slot предотвращает конкурирующие GigaChat-запросы. Output cap по умолчанию None. Traces/feedback/replay отделены от источников истины.

## Самоулучшение и поставка

Ouroboros предлагает только bounded retrieval-policy, через отдельный Evolution MCP. Реальные paired checks на frozen development/validation требуют роста без регрессий. После PASS возможен critic; exact approval и atomic bundle activation доступны только оператору. Есть rollback и interruption reconcile. Автор не получает write к core/evaluator/release; контейнерные probes проверили read-only paths, отсутствие holdout и Docker socket.

`./run.sh -d` собирает CPU-образы, готовит индекс и запускает два MCP/native UI. Secrets через env/private state. Первый skill review/enable остаётся явным штатным шагом; hidden paid startup отсутствует. Public asset cache переиспользуется с hash-проверкой PDF; network-only загрузка зависит от доступности внешних сайтов.

## Проверки и пределы

133 тестов и lint/format прошли; fixed acceptance — 25/30, это не answer accuracy. Есть реальные PDF/web/hybrid/forecast/scenario/quote диалоги и Chromium UI-check. Native author создал candidate: 5/19 → 7/19, но validation regression вызвала REJECTED. Active policy не менялась; production release не заявлен.

Пять retrieval-промахов, смысловая faithfulness, недостаточное ETS coverage, delayed quotes, неполный EIA tail и внешние outages остаются ограничениями. Нет опубликованного GitHub/GitLab URL. Следующие улучшения: новые закрытые корпуса/кейсы, качество retrieval/сопоставления, ручная оценка фактов, свежие данные и эксплуатационные проверки на других платформах. Детали и evidence: INTEGRATION_STATUS.md и examples/demo_dialogues.md.
