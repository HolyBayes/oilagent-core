# Native UI

Из core запускается `./run.sh -d`, UI по умолчанию <http://127.0.0.1:8765>. В текущем workspace host UI уже работает на 8765, контейнерная проверочная установка — на 8875. Изменение портов и конфигурация — в README.

При новой установке skill `oilgas_analyst` из evolution регистрируется штатно, затем требует обычных review/enable. Они не обходятся и не выполняются скрыто на startup. Для host runtime доступны команды `scripts/ouroboros_runtime.py review`, `enable`, `serve`. Clean review тех же байтов в той же установке переиспользуется. Background consciousness/evolution выключены.

Путь: браузер → Main → `mcp_analyst__answer_question` → общий core. Host adapter закрепляет session ID по chat ID и после реального успешного MCP-вызова доставляет canonical answer, source links, таблицы, ограничения и request ID. Свободный финальный пересказ не заменяет результат core.

Реальный Chromium-прогон подтвердил новый forecast: обе модели, единицы, 80% интервалы и «исторический дневной ряд» переданы без прежней подмены на ежемесячный отчёт. [Evidence](native-delivery-evidence.json). Старые неуспехи сохранены в ui-evidence.json, а не переписаны в успешные.

Upstream checkout на pin не меняется на диске. Наш launcher адаптирует native GigaChat union schema, стартовые MCP schemas в Nano, сериализацию provider calls, ограничения tools и canonical delivery в процессе запуска. Это адаптированный runtime. Native review/host validation не заменены собственным approval.

Авторский ToolRegistry допускает analytic/Evolution MCP и необходимые discovery/completion tools; shell и произвольное изменение файлов отклоняются. В контейнере core/evolution read-only, eval и Docker socket не смонтированы. Это конкретная демонстрационная граница, не enterprise security certificate.

Native контекст дорогой; повторять платные browser/author пробы на каждый edit не нужно. Повседневные проверки — pytest, fixed acceptance и HTTP smoke без модели. Измеренные расходы и ограничения: INTEGRATION_STATUS.md.
