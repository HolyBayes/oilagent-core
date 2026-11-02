# Пять native-сценариев Lite

Задачи созданы через API штатного UI и выполнены Main. Источники и request ID сверены с Analyst traces. Полные данные: [JSON](../docs/native-lite-delivery-evidence.json). Проверка структурная, не оценка общей точности.

## report

Что EIA в отчёте за октябрь 2025 прогнозировало для цены Brent в первом полугодии 2026?

Task `28915ebde89142cb` → `answered`, request `3a5ceb6a-8663-453c-8812-948b6e802963`.

Фрагмент: We forecast that Brent crude oil prices will average $52/b in 2026, compared with an average of $69/b in 2025. [R2]   Источники:  [R2] EIA Short-Term Energy Outlook — October 2025, выпуск 2025-10-07, PDF стр. 6: https://www.eia.gov/outlooks/steo/arch…

## web

Какие свежие новости о природном газе опубликовало EIA за последние 7 дней?

Task `eed0e6c98a044940` → `answered`, request `2415c285-4526-46f6-a5ad-4893c847b5c1`.

Фрагмент: LNG imports make up increasing share of Colombia's natural gas supply. [W1]  Colombia is importing more liquefied natural gas (LNG) as domestic production continues to fall. [W1]  A potential drought this fall and winter could limit the availability …

## hybrid

Что EIA в отчёте за октябрь 2025 прогнозировало для цены Brent в первом полугодии 2026; а затем добавь последние новости EIA о природном газе за 7 дней. Раздели источники.

Task `e604947066724439` → `answered`, request `266d39aa-56bf-4b1d-a310-50ca1aa09d94`.

Фрагмент: EIA прогнозировало, что цена Brent в первом полугодии 2026 года составит $52 за баррель. [R2]  LNG imports make up increasing share of Colombia's natural gas supply. [W1]  Colombia is importing more liquefied natural gas (LNG) as domestic production …

## forecast

Рассчитай новый прогноз Brent на 3 месяца с интервалами 80%, as_of 2026-10-01, история 2016-10-01 — 2026-09-30.

Task `3a8bd764e1e1483e` → `forecasted`, request `74ec04fe-2562-4fb2-9f74-c093972fee09`.

Фрагмент: Расчётный прогноз Brent spot, USD/bbl; ETS. Данные по 2026-09. Точки — условные медианы среднемесячной цены; прогнозный интервал 80%.  ARIMA [F1]  | Месяц | Оценка, USD/bbl | Нижняя 80% | Верхняя 80% | |---|---:|---:|---:| | 2026-10 | 121.33 | 104.15…

## out_of_scope

Напиши рецепт борща.

Task `38f2bae8e3bc4206` → `out_of_scope`, request `bb505a9f-bc19-4eb3-917c-e8b1d8dc85d3`.

Фрагмент: Я отвечаю на вопросы нефтегазового рынка.…

Отчётный ответ цитирует 2026 год целиком вместо явного H1; полнота этого ответа остаётся ограничением RAG.
