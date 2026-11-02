# Фактический статус


Обновление native-интеграции: четыре skills 0.4.0 с независимыми clean review/enable; direct `forecast(asset="brent")`; три штатных specialist rows и реальный completed parent/child run. Его model был Max. Текущий запуск переведён на GigaChat 2 Lite; отдельный короткий Lite → HTTP MCP расчёт прошёл, диапазон взят из cache без сетевой загрузки. Files показывает единое хранилище PDF/CSV/model cache; старые пути — aliases. Optional Codex model bridge подготовлен и покрыт contract tests, но выключен и живьём без подключённого harness не проверен.

Свидетельства расширения: [native subagents/reviews](native-subagents-evidence.json), [skill creation/checks/critic](skill-workflow-evidence.json), [Lite](lite-evidence.json), [Files](native-files-evidence.json). В skill experiment новая capability прошла 3/3 и получила APPROVE; она не установлена. Это не демонстрация улучшения существующего production skill. Предыдущие записи ниже относятся к своим версиям/моделям.

Обновлено 2 ноября 2026. Это демонстрационная реализация на публичных данных, не заключение о production readiness. Предыдущий аудит сохранён в [REQUIREMENTS_AUDIT](REQUIREMENTS_AUDIT.md) и относится к указанным там старым коммитам.

## Реализовано

- Native UI Ouroboros 7.9.0 на полном pin, общий Analyst MCP/LangGraph, штатный hash-bound review/enable instruction skill 0.3.0. UI отдаёт canonical ответ core; новая реальная браузерная проверка исправленной атрибуции прошла.
- Локальный OPEC/EIA PDF RAG: 154 страницы, 475 E5/Chroma chunks. Web через DDGS и официальный RSS EIA, домены из committed evolution main, отдельные даты, captions/snippets без притворного чтения полного текста.
- Hybrid: поиск в отчётах и web, независимые вопросы/контексты и программное объединение с citations. Живой сквозной ответ с report/web получен. Невалидные quotes, wrong source IDs и stale report parameters разобраны и покрыты проверками; provider outage сохраняет partial/подтверждённые выдержки.
- ARIMA + ETS + naive, 80% prediction intervals и rolling calibration/test, MCP history dates и incremental coverage cache без TTL. Два метода проверены также в Linux-контейнере.
- Supply-cut sensitivity по явным допущениям, проверка знаков/единиц/границ; missing inputs → clarify. Последняя delayed Brent/WTI futures quote с timestamp и типом; не EIA spot и не real-time feed.
- SQLite session context, последние шесть вопросов, server IDs, follow-up horizon, release pin; reset при несовместимом коде. Core не считает прошлый ответ evidence.
- Typed facts/assumptions/excerpts, protected measurement comparison, один repair на запрос, программный renderer/fallback, общий бюджет LLM/tools/input/time, shared GigaChat slot и optional monetary admission reservation.
- Private traces, retention, explicit unverified feedback и offline replay. Отдельные bearer-токены MCP, bounded policy, scope/path checks, idempotent proposals и persisted artifacts.
- Serving действительно читает release policy. Evolution checks используют настоящий PDF retrieval на frozen cases, затем critic при PASS; операторские immutable bundles, exact bindings, atomic activation/reconcile и rollback. Release отсутствует в MCP.
- `./run.sh -d`: CPU Docker build, init, два MCP и native UI. Порты localhost, protected read-only mounts, eval и Docker socket не видны автору. Secrets не включены в образы/Git; managed model settings обновляются из env при рестарте контейнера.

## Проверки

| Проверка | Результат / предел |
|---|---|
| Pytest | 161 тест прошёл; сторонние deprecation warnings сохранены |
| Ruff lint/format | Проходят |
| Fixed acceptance | 25/30; 13 реальных retrieval cases + 17 deterministic contracts; LLM не вызывается |
| PDF/web/hybrid/scenario/quote/forecast/follow-up | Живые GigaChat/публичные данные, примеры и неуспехи сохранены; это выбранные cases, не blind answer benchmark |
| Native UI | Реальный Chromium → Main → HTTP MCP; обе таблицы и provenance переданы canonical renderer |
| Native author | Реальный Main создал candidate и вызвал real checks; REJECTED за validation regression |
| Release/rollback | Positive/negative fixtures, stale SHA/check bindings, tamper и interrupted write/reconcile; production bundle не выпускался |
| Docker/Linux ARM64 | Оба образа, init нового Linux-индекса, MCP каталог/auth, два forecast-метода и UI HTTP прошли; assets переиспользованы из проверенного cache |
| Author isolation | Write probes к core/evolution отклонены; holdout и Docker socket не видны в контейнере; это конкретные probes, не полное security-аудирование |
| Providers openai/local | Offline configuration/schema checks; live пропущен пользователем |

Свидетельства: [реальные диалоги](../examples/demo_dialogues.md), [deployment](deployment-evidence.json), [native author](evolution-run-evidence.json), [completion](completion-evidence.json), [acceptance](acceptance-evidence.json), [forecast/cache](FORECAST.md).

## Что остаётся ограничением

Пять исходных retrieval-промахов не исчезли от наличия новых tools. Выбранные live-ответы не доказывают полноту по всем отраслевым темам, смысловую поддержку каждого claim и отсутствие галлюцинаций. Exact quote/number checks — структурная проверка; quality rubric и raw evidence прилагаются.

Новый policy-кандидат дал development 4/9 → 5/9 и validation 1/10 → 2/10, но потерял `h_brent_q4`. Gate отклонил его. Действующая policy не изменена; это **не успешная активация самоулучшения**. Positive release/critic path на реальном улучшившемся без регрессий кандидате ещё не продемонстрирован; автоматического обхода этого gate нет.

ETS backtest coverage ниже nominal 80%, naive немного лучше на текущем срезе. Publication lag EIA может оставить history tail неполным; forecast показывает настоящие data_end/даты. Yahoo quote задержанная, Urals feed отсутствует. DDGS и GigaChat иногда дают ошибки/timeout; retries не маскируют это. Network-only cold asset download в Docker получил TLS timeout; bootstrap с проверенным кешем работает.

Денежная гарантия не обещается без актуального тарифа и output bound; default `LLM_MAX_OUTPUT_TOKENS=None` сохранён. Unknown usage/reservations отмечаются. Native context дорогой: один новый author task — 145537 prompt + 839 completion токенов; его не нужно повторять при каждом изменении.

GitHub/GitLab URL не предоставлен, remote не настроен; read-only GitHub connector не ответил. Публикация не выполнена. x86/Linux и Python 3.11 отдельно не проверены. OCR, private data, enterprise SSO, торговля и arbitrary Python evolution вне принятой области.
