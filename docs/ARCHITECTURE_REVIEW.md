# Ревью архитектуры до реализации

Дата: 1 ноября 2026. Основание: оригинальный DOCX, ARCHITECTURE.original.md и upstream-документация. Код отсутствует; эксплуатационная работоспособность не проверялась. Ниже — архитектурные замечания и предложения, а не подтверждённые дефекты работающей системы.

## Что сохранить

Один аналитический core для UI/MCP; сначала RAG, затем актуальные web-данные; provenance по страницам; ARIMA/ETS с baseline; различие временного прогноза и сценария; отделение автора кандидата от выпуска; запрет импорта candidate Python; раздельные истории core/policies и закрепление релиза на сессию. Эти решения полезны для задачи.

## Существенные замечания

| Приоритет | Основание в исходном плане | Проблема и последствие | Предлагаемое изменение |
|---|---|---|---|
| Высокий | §8–9, 12–13 | Два MCP, семь VCS tools, универсальные patches, двойной lifecycle и release-manager при 2800 LOC. Бюджет перечислен, реализуемость не показана | Сохранить оба MCP и две Git-истории; пять узких evolution methods, декларативная policy, fixed runner вместо generic Git API |
| Высокий | §5.3 | Обязательный фильтр published_at по году вопроса путает выпуск отчёта и период показателя | Разделить publication vintage и reference period; при неизвестных metadata не применять ложный строгий фильтр |
| Высокий | §4.3, 10–11 | Source ID и наличие числа не доказывают, что фрагмент поддерживает тезис | Claims со spans/unit/period, проверка вычислений, ручной faithfulness eval; убрать обещание фактической гарантии |
| Высокий | §7.2–7.4 | Не определено, что произойдёт с «следующими месяцами» на старом frozen CSV | data_end отдельно от generated_at; либо обновление, либо честный прогноз от старого среза |
| Высокий | §9.4 | Нет исполняемого контракта policy, первичной метрики, причинно связанного изменения поведения | Ограниченная schema с реально исполняемой стратегией per_publisher; paired before/after; no-improvement блокирует release |
| Высокий | §3, конфигурация Ouroboros | Конкретные review env-настройки предложены без pin/smoke. Текущий upstream прямо отмечает inert review env keys | Проверить settings/API/config по полному SHA; отсутствие защит не компенсировать промптом |
| Средний | §4.1, 14 | session_id есть, механизм follow-up и потери памяти не определён | Ограниченная session memory; история не evidence; явно нет resume после рестарта |
| Средний | §6.2 | Проверка конечного URL после redirect сама по себе запаздывает для SSRF | В MVP только search snippets; при fetch проверять DNS/IP/каждый redirect до соединения |
| Средний | §7.3 | Выбор модели и calibration не разложены по горизонту; возможна утечка при подборе | Train-only tuning; rolling origins h=1..3; calibration residuals по h, reporting coverage и малой выборки |
| Средний | §7.3 | Scenario sensitivity назван, но формула, inputs, ограничения и output отсутствуют | Условная модель с явными эластичностями, уточнение без параметров, отдельный контракт сценария |
| Средний | §4.2, 14 | Есть один repair и timeout, нет общих tokens/cost/tools/stop outcomes | Общий request budget с учётом retry, частичный ответ и UNRELEASED candidate при остановке |
| Средний | §8–10 | Ограниченный VCS MCP можно обойти shell Ouroboros при общей identity | OS/container permissions, отсутствие credentials/socket, runner вне среды автора |
| Средний | §11 | Mocks и live integration могут создать ложное впечатление подтверждённого качества | Раздельные offline contracts, live smoke, ручная разметка и реальные диалоги |

## Изменение объёма — предложение

В обновлённом ARCHITECTURE.md предложен недельный MVP. После обсуждения сохраняются **оба MCP** и две Git-истории: Evolution MCP нужен для самостоятельного прохождения Ouroboros этапов proposal/check/review. Сокращается универсальность backend: первая исполняемая поверхность — строгая retrieval-policy; автоматическое исполнение Python patches отложено. Человек утверждает выпуск. Исходный документ доступен без изменений. Это архитектурное предложение, а не дополнительное требование Сбербанка.

Отдельно: исходная оценка 2800 строк не обязана быть неверной, но пока не подтверждена. Не следует добиваться лимита плотным кодом, неучтёнными скриптами или переносом алгоритмов в YAML. Главный критерий — понятный и воспроизводимый вертикальный срез.

## Что необходимо доказать прототипом

День 1: pinned Ouroboros → реальный MCP call → тот же core; skill lifecycle и фактические настройки; живой structured output выбранной модели. День 2: проверенные PDF страницы/числа. День 4: реальные backtests и интервалы. День 6: реальный candidate от Ouroboros и парные eval, либо честный no-op/reject. Привязка review к SHA, отсутствие обхода release и rollback проверяются отдельно.

## Первичные источники

- [Configuration](https://github.com/razzant/ouroboros/blob/main/docs/architecture/07-configuration.md): settings и inert review env keys.
- [Creating Skills](https://github.com/razzant/ouroboros/blob/main/docs/CREATING_SKILLS.md): manifest/lifecycle; ownership bucket native зарезервирован для bundled skills. «Штатный lifecycle» не означает «поместить custom skill в native bucket».
- [MCP client](https://github.com/razzant/ouroboros/blob/main/ouroboros/mcp_client.py): MCP client и конфигурация серверов.
- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence): thread memory, checkpoints, stores; in-memory state не переживает рестарт.

Просмотрены доступные main-версии 1 ноября 2026. Это не проверка выбранного SHA. Ссылки и их содержание меняются; реализация обязана закрепить фактически проверенную версию.
