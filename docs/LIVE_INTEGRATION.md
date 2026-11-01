# Живая интеграция: результаты и воспроизводимость

Срез: 1 ноября 2026. Полный Ouroboros не патчен; pin указан в config/ouroboros-pin.json. Подтверждённые факты: [live-integration-evidence.json](live-integration-evidence.json).

## Что проверено

- GigaChat авторизация и TLS с локальным CA bundle работают. Alias `GigaChat` API отклонил; выбран доступный по API `GigaChat-2-Max`.
- Настоящий `smoke_ouroboros.py --live`: HTTP MCP → LangGraph → structured routing, proposal/checks → отдельный critic. Critic вернул REQUEST_CHANGES; кандидат не выпущен. В этом smoke policy задаёт скрипт, поэтому он не подтверждает автономное авторство.
- Полный isolated Ouroboros server: health 200, supervisor ready, native discovery обоих MCP, настройки `blocking` и auto-grants=false.
- Local-source instruction skill Ouroboros регистрирует и читает на месте. Поэтому install endpoint штатно отвечает `local_source`, а не копирует пакет. Через обычный review endpoint получен clean verdict, затем включены exact bytes по content hash `e8b88bf266a40bb47d07b3dd8595ca41475a68b7ab389c7b3fbb84992fbd7423`. Owner attestation/skip review не использовались.
- Default `LLM_MAX_OUTPUT_TOKENS=None`: пустое/отсутствующее значение и строка None не передают max_tokens в GigaChat/OpenAI payload. Явное положительное значение задаёт лимит. Тесты проверяют сформированные SDK payload без сетевых запросов.

## Что не получилось

Один native author task `5fd897b03fed48bf` выполнил list_available_tools и enable_tools, затем получил HTTP 422 на GigaChat route. Proposal не выполнен, candidate не создан. В сохранённом provider wire request MCP schema содержала `$ref/$defs` и nullable `anyOf`. После enable появилась эта схема и возник отказ; это гипотеза несовместимости provider subset, а не доказанная сервером точная причина — readable provider detail отсутствует.

Исправлено в нашем MCP: вложенная policy публикуется inline, get_status без ID использует необязательную строку без null union. Сервер по-прежнему валидирует policy через строгую Pydantic schema: произвольные fields/types/paths не разрешены. Offline tests и keyless HTTP проверяют контракт. Платный native retry не выполнен: необходимо сначала уменьшить его большой фиксированный контекст. Нельзя считать сквозной model-authored цикл успешным.

## Расход

| Проверка | Provider-reported input | Output | Всего |
|---|---:|---:|---:|
| Успешное native skill review | 43430 | 6 | 43436 |
| Два успешных model responses author task до HTTP 422 | 77056 | 64 | 77120 |
| **Известный native расход** | **120486** | **70** | **120556** |

Короткие routing/critic core calls старый wrapper выполнил без сохранения usage; их точный расход в этом отчёте неизвестен. У ошибочных native попыток встречаются отсутствующие usage — они перечислены в evidence. Это не полный подтверждённый расход аккаунта и не денежная оценка. Квота пользователя 1 млн токенов остаётся ограничением планирования, независимо от ответа balance API.

Новый wrapper сохраняет provider usage в route state и candidate critic result. Это учёт, не глобальный счётчик/квота аккаунта. Live tests не входят в pytest. Повторное clean review того же hash переиспользуется без платного запроса. `run` проверяет текущий reviewed/enabled skill, выключает другие skills в isolated runtime, запрещает static shell/write/Git tools и сохраняет finish/discovery tools. Это не доказательство OS sandbox.

## Подготовка

Из core, в основном Python окружении:

```bash
python scripts/bootstrap.py
python -m venv workspace/ouroboros-venv
workspace/ouroboros-venv/bin/python -m pip install -r ../workspace/upstream/ouroboros/requirements-runtime.lock
python scripts/ouroboros_runtime.py prepare
python scripts/ouroboros_runtime.py serve
```

`prepare` выполняется при остановленном сервере. Он создаёт отдельный checkout без remote, отдельные data/settings и owner state. Секреты записываются только в ignored .env/private settings с mode 600. Другие provider/GitHub/host secrets не передаются процессу. Системное окружение не перенастраивается. Настройки roster/sources сериализуются как JSON **строки**, как требует pinned config loader.

Профиль провайдера общий: `LLM_PROVIDER=gigachat|openai|local`. Для GigaChat CA bundle задаётся в `GIGACHAT_CA_BUNDLE_FILE`; в native profile он переводится в `OUROBOROS_EXTRA_CA_BUNDLE`. TLS verification включена. Инструкция и публичная ссылка на root certificate: [документация GigaChat](https://developers.sber.ru/docs/ru/gigachat/certificates). В текущем workspace bundle объединяет certifi roots и загруженный с официального URL Russian Trusted Root CA; глобальный certifi/системное хранилище не менялись.

В отдельных терминалах поднимаются оба MCP по README. Для изолированного domain Git задайте `EVOLUTION_REPO_PATH` на тестовый каталог; canonical evolution менять не требуется. MCP endpoint/token в private native settings должны соответствовать сервисам.

Команды API из основного окружения:

```bash
python scripts/ouroboros_runtime.py catalog
python scripts/ouroboros_runtime.py install  # local source: registered_in_place
python scripts/ouroboros_runtime.py review   # только если нет актуального review
python scripts/ouroboros_runtime.py enable
python scripts/ouroboros_runtime.py skill
# Платный native task: не повторять до оптимизации контекста/проверки payload.
python scripts/ouroboros_runtime.py run --prompt-file /path/to/experiment.txt
```

Default native profile задаёт 3 раунда, 300 секунд и 1 review wave. Это параметры upstream, не доказанный общий token cap: в неуспешном task были дополнительные host failure/finalization действия. USD-параметры профиля не являются подтверждённым ограничением токенов GigaChat. Один исправленный review после старого неверного alias потребовал штатно применить исходный предел двух waves через owner settings API; дальнейших review не планируется. Успешный verdict сохраняется и переиспользуется.

56 offline tests проходят; live-результаты сохраняются отдельно. Работа RAG/web/forecast/UI и production release по-прежнему не реализована. Core и canonical Evolution Git независимы; этот experiment не изменял canonical evolution.


## Дополнение: компактная проверка без полного runtime

После описанного выше Main worker failure выполнен отдельный native GigaChat probe: все пять Evolution schemas отправлены без изменения; модель выдала proposal arguments, in-process MCP создал Git-кандидат, synthetic checks прошли. Расход 715 токенов, critic/release не вызывались. [Сохранённый результат](schema-probe-evidence.json), [скрипт](../scripts/check_tool_schema.py). Полный Main worker не повторялся; его предыдущий неуспех остаётся открытым gate. Probe доказывает совместимость schemas и авторство bounded candidate в коротком контексте, а не успешность всего runtime.
