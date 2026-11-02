# Пять сценариев Lite

Реальные HTTP MCP вызовы, не UI-диалоги. Полные ответы, источники и usage: [JSON](../docs/lite-delivery-evidence.json). Partial сохранён.

## report

Вопрос: Что EIA в отчёте за октябрь 2025 прогнозировало для цены Brent в первом полугодии 2026?

Статус: `answered`. Request ID: `ab4e5d15-c1b3-422e-871a-5f1997a8a29b`.

Фрагмент ответа: We forecast that Brent crude oil prices will average $52/b in 2026, compared with an average of $69/b in 2025. [R2]  We forecast that oil prices will fall to an average of $62/b in the fourth quarter of 2025 (4Q25) and $52/b in the first half of 2026 (1H26). [R3]   Источники:  [R…

## web

Вопрос: Какие свежие новости о природном газе опубликовало EIA за последние 7 дней?

Статус: `partial`. Request ID: `31aa5928-f4d6-4caa-b6d8-9a1068dc41de`.

Фрагмент ответа: Выдержка источника, не полный ответ: «LNG imports make up increasing share of Colombia's natural gas supply. Colombia is importing more liquefied natural gas (LNG) as domestic production continues to fall. A potential drought this fall and winter could limit the availability of h…

## hybrid

Вопрос: Что EIA в отчёте за октябрь 2025 прогнозировало для цены Brent в первом полугодии 2026; а затем добавь последние новости EIA о природном газе за 7 дней. Раздели источники.

Статус: `partial`. Request ID: `2cf3aa0b-56ce-41f0-b1bd-83c1c1804ae8`.

Фрагмент ответа: Выдержка источника, не полный ответ: «will average $52/b in 2026, compared with an average of $69/b in 2025. The pace at which China continues to purchase oil to fill inventory is a key uncertainty in our forecast. If China’s builds continue at the pace estimated in recent months…

## forecast

Вопрос: Рассчитай новый прогноз Brent на 3 месяца с интервалами 80%, as_of 2026-10-01, история 2016-10-01 — 2026-09-30.

Статус: `forecasted`. Request ID: `226271d4-6115-4722-9322-9eab0358e426`.

Фрагмент ответа: Расчётный прогноз Brent spot, USD/bbl; ETS. Данные по 2026-09. Точки — условные медианы среднемесячной цены; прогнозный интервал 80%.  ARIMA [F1]  | Месяц | Оценка, USD/bbl | Нижняя 80% | Верхняя 80% | |---|---:|---:|---:| | 2026-10 | 121.33 | 104.15 | 141.34 | | 2026-11 | 123.34…

## out_of_scope

Вопрос: Напиши рецепт борща.

Статус: `out_of_scope`. Request ID: `c6deeb80-6797-438e-8200-9b4472d8ed65`.

Фрагмент ответа: Я отвечаю на вопросы нефтегазового рынка.…
