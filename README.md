# OilAgent

Нефтегазовый аналитик для публичных данных: native UI Ouroboros → Analyst MCP → LangGraph, локальный RAG OPEC/EIA, web, расчётные ARIMA/ETS и сценарии сокращения добычи. Отдельный Evolution MCP создаёт Git-кандидатов ограниченной retrieval-policy; оценка, critic и операторский выпуск отделены от аналитики.

Фактический статус и ограничения: [INTEGRATION_STATUS](docs/INTEGRATION_STATUS.md). Краткий отчёт: [ARCHITECTURE_SUMMARY](docs/ARCHITECTURE_SUMMARY.md). Архитектура: [ARCHITECTURE.md](ARCHITECTURE.md). Реальные примеры: [demo_dialogues](examples/demo_dialogues.md).

## Развёртывание и вход в UI

Нужны запущенный Docker Desktop/Engine с Compose v2, Python 3 и доступ к выбранной модели. Все команды ниже выполняются из `OilAgent/core/`.

1. Подготовьте конфигурацию, сохранив существующую, если она уже есть:

   ```bash
   cd /path/to/OilAgent/core
   if [ ! -f .env ]; then cp .env.example .env; fi
   chmod 600 .env
   ```

   В `.env` задайте `LLM_PROVIDER=gigachat`, `GIGACHAT_MODEL=GigaChat-2-Max`, `GIGACHAT_CREDENTIALS` (Authorization key) и соответствующий `GIGACHAT_SCOPE`. При необходимости укажите `GIGACHAT_CA_BUNDLE_FILE`. Профили OpenAI/local описаны ниже. Секреты остаются в локальном `.env`.

2. Соберите и запустите сервисы:

   ```bash
   ./run.sh -d
   docker compose ps -a
   docker compose logs --tail 50 init analyst evolution ouroboros
   ```

   `run.sh` заполнит пустые MCP-токены разными случайными значениями. Если `.env` отсутствует, скрипт создаст его сам; доступ к модели всё равно нужно настроить. Дождитесь успешного завершения `init`, healthy у `analyst`/`evolution` и запуска `ouroboros`. Первая сборка и индексация могут занять заметное время.

3. Откройте **<http://127.0.0.1:8765>** в браузере на машине запуска. Это native UI Ouroboros. В **Skills** найдите `oilgas_analyst`, выполните штатный **Review**, дождитесь результата и включите skill. Review вызывает модель; скрытого платного review при старте нет. Результат для тех же байтов в той же установке переиспользуется.

4. В чате **Main** отправьте, например: «Построй прогноз Brent на 3 месяца методами ARIMA и ETS, покажи интервалы и источник исторических данных». Текущий путь: Main → `answer_question` → расчётный модуль. Ответ должен содержать обе модели, источник и request ID. Один лишь доступный UI ещё не подтверждает доступ к модели или успешное выполнение MCP.

По умолчанию UI слушает только loopback хоста; MCP доступны на `http://127.0.0.1:8011/mcp` и `http://127.0.0.1:8012/mcp` с Bearer-токенами из `.env`. MCP URL не является адресом UI. Для удалённого сервера можно пробросить UI по SSH: `ssh -L 8765:127.0.0.1:8765 user@server`, затем открыть тот же адрес в локальном браузере.

Команда собирает CPU-образы, готовит независимый evolution Git, проверяет/загружает PDF и индексирует их, затем поднимает два MCP и native UI. Данные контейнерной установки находятся в `workspace/container/`; публичные PDF/веса из имеющегося локального кеша переиспользуются. Загрузка с нуля зависит от доступности OPEC/EIA/Hugging Face. Первичная попытка download из Docker получила TLS timeout; запуск с проверенным кешем и новым Linux-индексом подтверждён. Повторный запуск сохраняет Git, индекс, диалоги, review и кеш цен.

Если порты заняты, используйте `UI_PORT=8875 ANALYST_PORT=8811 EVOLUTION_PORT=8812 ./run.sh -d` и откройте **<http://127.0.0.1:8875>**. Для постоянной настройки запишите эти переменные в `.env`. `DEPLOY_WORKSPACE` задаёт каталог deployment state, `EVOLUTION_REPO_PATH` — путь к независимому evolution Git (по умолчанию `../evolution`). В данном рабочем каталоге ранее проверены две отдельные установки: контейнерная на 8875 и host UI на 8765; их диалоги и review хранятся отдельно.

```bash
docker compose ps
docker compose logs --tail 30 analyst evolution ouroboros
docker compose down
# После изменения .env или обновления кода:
./run.sh -d
```

`down` останавливает сервисы, сохранённые данные остаются. UI авторского контура имеет read-only core/evolution, не видит eval-набор и Docker socket. Выпуск разрешён только операторскому CLI на хосте. [Проверка контейнеров](docs/deployment-evidence.json).

Если UI не открывается, проверьте `docker compose ps -a` и логи: ошибка `init` блокирует зависимые сервисы. Ошибки модели смотрите в логах `analyst`/`ouroboros`; после исправления `.env` повторите `./run.sh -d`. Первый запуск без готового кеша требует сетевого доступа к источникам PDF и моделей.

## Skills, subagents и границы текущей интеграции

Сейчас в UI установлен **один instruction skill `oilgas_analyst`**. RAG, web и forecast реализованы в core как MCP-инструменты/аналитические маршруты, а не как отдельные native skills. Профиль Ouroboros открывает Analyst MCP только через `answer_question`; прямой `forecast_brent` в этом профиле модели недоступен. Проверенный UI-прогноз ARIMA/ETS получен через общий вход, а не через самостоятельный выбор native Main инструмента `forecast_brent`. [Сохранённое подтверждение](docs/native-delivery-evidence.json).

Аналитические subagents выключены (`OUROBOROS_SUBAGENTS_MODE=off`). Настроенный `oilagent-reviewer` предназначен для review и не является аналитическим специалистом. Launcher дополнительно запрещает delegation/file-write tools. Evolution MCP меняет только `policies/retrieval.json`: он **не создаёт и не улучшает native skills**. Наличие папки skills в evolution Git само по себе этого не обеспечивает.

Совместить архитектуру со штатными skills/subagents Ouroboros можно. Следующее разделение — план доработки, ещё не реализованный функционал:

| Native skill | Назначение | Существующая опора в core |
|---|---|---|
| `oilgas_analyst` | Координация и итоговый ответ | Общий аналитический маршрут |
| `report_rag` | Поиск и сопоставление отчётов | Report retrieval и проверка цитат |
| `web_research` | Свежие публикации и источники | Web/RSS и проверка дат |
| `oil_forecast` | ARIMA/ETS и сценарии | `forecast_brent`, `supply_cut`, кеш истории |

Skill и subagent — разные сущности: skill задаёт инструкции/возможности, subagent выполняет выделенную задачу в отдельной сессии. Простой прогноз может выполнять Main с forecast skill и прямым MCP-вызовом; сложное исследование — штатные specialist subagents через `schedule_subagent`. Для этого нужны изменение профиля, разрешений launcher и grants дочерних сессий, а также сквозные проверки. Одного переключения subagents в настройках недостаточно.

Создание/изменение skills требует отдельного пути: native authoring → кандидат в evolution Git → оценка поведения → штатный review точных байтов → включение принятой версии. Текущая оценка retrieval-policy не оценивает изменения skill-инструкций или делегирования. Эти возможности нельзя считать реализованными до интеграции и проверки такого цикла.

## Модель и конфигурация

Выбран GigaChat-2-Max: у кандидата есть доступ к Sber API, модель отвечает по-русски и прошла живые проверки structured routing, PDF/web/hybrid, расчётных маршрутов и native MCP. Это практический выбор для демонстрации; сравнительного benchmark моделей не проводилось.

```dotenv
LLM_PROVIDER=gigachat
GIGACHAT_MODEL=GigaChat-2-Max
GIGACHAT_CREDENTIALS=
GIGACHAT_SCOPE=GIGACHAT_API_PERS
GIGACHAT_CA_BUNDLE_FILE=
LLM_MAX_OUTPUT_TOKENS=
```

Scope зависит от доступа. Custom CA bundle копируется в отдельный read-only mount; TLS verification включена. Пустое/отсутствующее `LLM_MAX_OUTPUT_TOKENS` или строка `None` не задаёт output cap в core SDK payload. Лимиты самого провайдера/платформы сохраняются. Автоматические retries core выключены. GigaChat-вызовы сериализованы общим файловым slot внутри установки. Независимые установки с одним ключом не следует нагружать одновременно; распределённой квоты аккаунта нет.

Другие профили:

```dotenv
LLM_PROVIDER=openai
LLM_MODEL=your-model
LLM_BASE_URL=https://your-compatible-endpoint/v1
LLM_API_KEY=
```

```dotenv
LLM_PROVIDER=local
LLM_MODEL=your-installed-model
LLM_BASE_URL=http://127.0.0.1:11434/v1
LLM_API_KEY=
```

В Docker адрес модели на macOS-хосте — `http://host.docker.internal:<port>/v1`. Нужна поддержка выбранного `LLM_STRUCTURED_METHOD=function_calling|json_schema|json_mode`. OpenAI/local покрыты офлайн-тестами конфигурации; **живые проверки пропущены по решению пользователя**.

Остальные параметры — в [.env.example](.env.example): пути, retrieval top-k, web freshness, request limits, retention, цены для optional cost reservation. System env имеет приоритет. Защитные schema/caps и фиксированные спецификации моделей не редактируются policy-кандидатом.

## Аналитические возможности

- PDF: два фиксированных публичных выпуска OPEC MOMR/EIA STEO за октябрь 2025, E5 на закреплённой revision и Chroma; источник, дата, PDF page и точные цитаты. PDF и веса не публикуются в Git; загрузчик проверяет SHA256. OPEC PDF не перераспространяется.
- Web: DuckDuckGo/DDGS и официальный RSS EIA без ключа. Доверенные домены читаются из committed main `evolution/policies/web_sources.json`; рабочие/candidate правки не активируются. Даты публикации и получения различаются. RSS — публикация/описание, DDGS — поисковая выдержка; чтение полной статьи не заявляется.
- Hybrid: независимый синтез report/web по своим вопросам и evidence, затем программное объединение ссылок и проверка полноты. Есть один repair на запрос; после отказа — явно помеченная подтверждённая выдержка/partial. Exact quote не доказывает смысловую релевантность.
- Forecast: ARIMA + ETS, горизонты 1–6 месяцев, nominal 80% prediction intervals, rolling calibration/test и naive benchmark. История EIA spot загружается через FRED только для непокрытых интервалов, без TTL и перезаписи кешированных значений. `start_date`/`end_date` — включительные даты истории. [Методика](docs/FORECAST.md).
- Scenario: условная оценка сокращения добычи по явным пользовательским P0/Q0/cut и диапазонам эластичностей. Это sensitivity analysis, не статистический прогноз; отсутствующие коэффициенты не придумываются.
- Котировки: последняя доступная delayed Brent/WTI futures quote с exchange/type/timestamp/unit; не подмена EIA spot и не real-time feed. Urals feed не подключён.
- Диалог: серверный session ID, последние шесть вопросов и параметры, SQLite TTL; предыдущий ответ не становится evidence. Новая policy закрепляется на новую сессию, несовместимое обновление core сбрасывает контекст.
- Сравнения: защищённая разность только двух проверенных measurements с совпадающими metric/geography/unit/period/vintage/type; несовместимость показывается явно.

Примеры:

```text
Что EIA в отчёте за октябрь 2025 прогнозировало для Brent в первом полугодии 2026?
Какие последние новости EIA о природном газе?
Рассчитай Brent на 3 месяца по состоянию на 2026-10-01, история 2016-01-01…2026-09-30.
А теперь на полгода?
Оцени сокращение на 2 млн б/с: цена 70 USD/bbl, добыча 100 млн б/с,
эластичность спроса [-0.3,-0.1], предложения [0,0.1], прочие условия неизменны.
```

Analyst MCP: `health`, `answer_question(question, session_id="")`, `forecast_brent`, `supply_cut`, `market_quote`, `submit_feedback`, `search_reports`, `search_web_sources`. Native Main получает общий `answer_question`; его финальный ответ программно передаёт canonical core result, а не повторный пересказ.

## Самоулучшение и два Git

`core/` и соседний `evolution/` — самостоятельные репозитории. Путь evolution задаётся `EVOLUTION_REPO_PATH`; пустая папка/unborn Git подготавливается автоматически. Core, evaluator и schemas защищены; кандидат меняет только `policies/retrieval.json`.

Policy задаёт bounded strategy/top-k, reranker/вес и query-context той же PDF-страницы. Serving читает developer seed либо проверенный release bundle, **не незакоммиченные правки и не candidate branch**. Начальный serving сохраняет прежнее per-publisher поведение, baseline не ухудшался ради демонстрации.

Evolution MCP: `propose_change`, `get_diff`, `run_checks`, `request_review`, `get_status`. Нужен существующий request trace; число кандидатов ограничено. `run_checks` сравнивает настоящий PDF retrieval на замороженных development/validation случаях, требует роста и отсутствия регрессий. Critic доступен после PASS. Ни approval, ни merge/release, ни shell через MCP нет.

```bash
python scripts/release.py status
python scripts/release.py approve CANDIDATE_ID --sha FULL_CANDIDATE_SHA --operator YOUR_NAME
python scripts/release.py rollback PREVIOUS_RELEASE_ID
# Возврат к исходному поведению:
python scripts/release.py rollback developer-seed
```

CLI принимает только актуальные checks, APPROVE того же SHA и eval/code/corpus bindings. Bundle имеет hash, activation атомарна; interruption reconcile, tampering и rollback покрыты тестами. Нативный автор реально создал кандидата: score 5/19 → 7/19, но одна регрессия привела к **REJECTED**, без critic и активации. Это демонстрация работающего quality gate, не успешный production release. [Свидетельства](docs/evolution-run-evidence.json).

## Проверки и воспроизведение

Для запуска без Docker используйте Python 3.11+; проверены Python 3.13/macOS ARM64 и Linux ARM64 в контейнере:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.lock
pip install --no-deps -e .
python scripts/bootstrap.py
python scripts/index_reports.py --download
pytest -q
ruff check src scripts tests
ruff format --check src scripts tests
python scripts/eval_acceptance.py
python scripts/smoke_ouroboros.py
```

Последние две команды не вызывают модель. `smoke_ouroboros.py --live` требует явного разрешения на платные вызовы. Для host native runtime отдельное окружение и штатный review/enable: [LIVE_INTEGRATION](docs/LIVE_INTEGRATION.md). Traces: `TRACE_PATH`, очистка по `TRACE_RETENTION_DAYS`; `submit_feedback` сохраняет мнение отдельно от market evidence. `python scripts/replay.py REQUEST_ID` проверяет сохранённые цитаты без сети/LLM.

## Известные ограничения

Функциональные guards не делают аналитика безошибочным. В serving baseline фиксированный acceptance-набор даёт 25/30; пять retrieval-промахов сохраняются. Это не answer accuracy и не blind benchmark. ETS intervals имеют недостаточное фактическое coverage, naive на текущем backtest немного лучше. Web и provider могут быть недоступны; quote delayed, месячная EIA история имеет публикационный лаг. OCR, произвольный Python evolution, торговля, private banking data и enterprise SSO/RBAC в задачу не входят.

Глобальный остаток квоты не выводится из суммы локальных usage. Native context дорогой: отдельный author run израсходовал 145537 prompt + 839 completion токенов. Отдельно учитываются cached tokens, review и прямые core-пробы. Денежная admission reservation требует заданных цен и явного output bound; при default None строгая денежная гарантия не заявляется.

Публикация GitHub/GitLab не выполнена: remote/целевой URL не задан, подключённый GitHub при read-only проверке не ответил. Локальные изменения версионируются в обоих Git; секреты и runtime state в Git не включаются.
