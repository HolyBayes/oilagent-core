# Native UI

Из core запускается `./run.sh -d`, UI по умолчанию <http://127.0.0.1:8765>. После обновления контейнерная установка запускается на 8765; старый проверочный порт 8875 больше не является адресом по умолчанию. Изменение портов и конфигурация — в README.

При новой установке skill `oilgas_analyst` из evolution регистрируется штатно, затем требует обычных review/enable. Они не обходятся и не выполняются скрыто на startup. Для host runtime доступны команды `scripts/ouroboros_runtime.py review`, `enable`, `serve`. Clean review тех же байтов в той же установке переиспользуется. Background consciousness/evolution выключены.

Путь: браузер → Main → `mcp_analyst__answer_question` → общий core. Host adapter закрепляет session ID по chat ID и после реального успешного MCP-вызова доставляет canonical answer, source links, таблицы, ограничения и request ID. Свободный финальный пересказ не заменяет результат core.

Реальный Chromium-прогон подтвердил новый forecast: обе модели, единицы, 80% интервалы и «исторический дневной ряд» переданы без прежней подмены на ежемесячный отчёт. [Evidence](native-delivery-evidence.json). Старые неуспехи сохранены в ui-evidence.json, а не переписаны в успешные.

Upstream checkout на pin не меняется на диске. Наш launcher адаптирует native GigaChat union schema, стартовые MCP schemas в Nano, сериализацию provider calls, ограничения tools и canonical delivery в процессе запуска. Это адаптированный runtime. Native review/host validation не заменены собственным approval.

Авторский ToolRegistry допускает analytic/Evolution MCP и необходимые discovery/completion tools; shell и произвольное изменение файлов отклоняются. В контейнере core/evolution read-only, eval и Docker socket не смонтированы. Это конкретная демонстрационная граница, не enterprise security certificate.

Native контекст дорогой; повторять платные browser/author пробы на каждый edit не нужно. Повседневные проверки — pytest, fixed acceptance и HTTP smoke без модели. Измеренные расходы и ограничения: INTEGRATION_STATUS.md.

## Native skills/subagents, версия 0.4

В Skills доступны отдельные oilgas_analyst/report_rag/web_research/oil_forecast с независимыми review/enable. Forecast открыт напрямую; канонический расчётный ответ сохраняется и при вызове forecast(asset="brent"). В Settings → Agents настроены три аналитических API-model rows и отдельный reviewer; mode auto, максимум два ребёнка, глубина один. Main может использовать простой прямой MCP-вызов или делегировать части исследования через schedule_subagent и дождаться результатов. У детей нет Evolution mutation, shell/file-write или nested delegation.

Runtime adapters устанавливаются также в spawn/forkserver workers через собственную picklable entrypoint, не через изменение upstream. Изменение instruction skills идёт через Git-кандидат и отдельные model routing checks; native review/enable оператор выполняет отдельно. Процедура и ограничения staging — в README. Старые evidence ниже/в соседних файлах относятся к версии 0.3 и общему answer_question; они не доказывают прямое forecast/delegation в 0.4.

Files теперь использует USER_FILES_PATH (workspace/files): Reports/Prices/Models и uploads находятся в одном физическом дереве, не в экспортной копии для UI. Модель текущего запуска — GigaChat 2 Lite. Четыре skills сохраняют clean review точных байтов, выполненный ранее на Max. Native subagent run на Max и компактный Lite smoke — разные свидетельства; см. native-subagents-evidence.json и lite-evidence.json.

Optional Codex model bridge подготовлен для Analyst/Evolution; он выключен и не проверен с живым аккаунтом. Штатное подключение аккаунта выполняется в UI; процедура и ограничения — в README.
