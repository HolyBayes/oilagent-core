# Пять финальных native-диалогов Lite

Одна попытка каждого сценария через UI Main. Источники и статусы сверены с Analyst traces. [Полные ответы](../docs/native-lite-delivery-evidence.json). Это демонстрация, не общая оценка точности.

## report

Что EIA в отчёте за октябрь 2025 прогнозировало для цены Brent в первом полугодии 2026?

Task `f0b2dd01e47c4c85`; Analyst: partial.

We forecast that oil prices will fall to an average of $62/b in the fourth quarter of 2025 (4Q25) and $52/b in the first half of 2026 (1H26). [R3]


Источники:

[R3] EIA Short-Term Energy Outlook — October 2025, выпуск 2025-10-07, PDF стр. 5: https://www.eia.gov/outlooks/steo/archives/oct25.pdf#page=5

Запрос: `39ec528d-858e-4eb3-9851-49f98c5abbf4`; статус: `partial`.

## web

Какие свежие новости о природном газе опубликовало EIA за последние 7 дней?

Task `262ee206892e4d15`; Analyst: answered.

LNG imports make up increasing share of Colombia's natural gas supply. [W1]


Источники:

[W1] web, eia.gov: LNG imports make up increasing share of Colombia's natural gas supply, публикация 2026-10-29T09:00:00-05:00, получено 2026-11-03T06:54:31.357524+00:00: https://www.eia.gov/todayinenergy/detail.php?id=68364

Запрос: `7b5c45bc-c616-4544-9cd0-9ca5e56594af`; статус: `answered`.

## hybrid

Что EIA в отчёте за октябрь 2025 прогнозировало для цены Brent в первом полугодии 2026; а затем добавь последние новости EIA о природном газе за 7 дней. Раздели источники.

Task `fd1c2955c31a40b1`; Analyst: answered.

EIA прогнозировало, что средняя цена Brent в первом полугодии 2026 года составит $52 за баррель. [R3]

LNG imports make up increasing share of Colombia's natural gas supply. [W1]

Colombia is importing more liquefied natural gas (LNG) as domestic production continues to fall. [W1]

A potential drought this fall and winter could limit the availability of hydroelectric generation and boost the country's demand for natural gas power generation. [W1]

Colombia's government has declared a national disaster in anticipation of a drought resulting from an expected strong El Niño. [W1]


Источники:

[R3] EIA Short-Term Energy Outlook — October 2025, выпуск 2025-10-07, PDF стр. 5: https://www.eia.gov/outlooks/steo/archives/oct25.pdf#page=5

[W1] web, eia.gov: LNG imports make up increasing share of Colombia's natural gas supply, публикация 2026-10-29T09:00:00-05:00, получено 2026-11-03T06:54:46.079850+00:00: https://www.eia.gov/todayinenergy/detail.php?id=68364

Запрос: `903ece3f-e925-4960-a4e2-b4b3f28e555a`; статус: `answered`.

## forecast

Рассчитай новый прогноз Brent на 3 месяца с интервалами 80%, as_of 2026-10-01, история 2016-10-01 — 2026-09-30.

Task `8cf6b8509b7f4c99`; Analyst: forecasted.

Расчётный прогноз Brent spot, USD/bbl; ETS. Данные по 2026-09. Точки — условные медианы среднемесячной цены; прогнозный интервал 80%.

ARIMA [F1]

| Месяц | Оценка, USD/bbl | Нижняя 80% | Верхняя 80% |
|---|---:|---:|---:|
| 2026-10 | 121.33 | 104.15 | 141.34 |
| 2026-11 | 123.34 | 96.37 | 157.86 |
| 2026-12 | 123.89 | 89.90 | 170.75 |

ETS [F1]

| Месяц | Оценка, USD/bbl | Нижняя 80% | Верхняя 80% |
|---|---:|---:|---:|
| 2026-10 | 114.28 | 105.43 | 123.88 |
| 2026-11 | 114.41 | 104.70 | 125.01 |
| 2026-12 | 114.53 | 102.56 | 127.89 |

ARIMA и ETS рассчитаны отдельно; выбор сделан на calibration, не на test.

Ограничения: Интервалы не охватывают все структурные и геополитические шоки. Кеш может содержать загрузки разных дат; исторические версии публикаций не восстанавливаются. Naive лучше выбранной модели по средней MAE для h=1..6 на отложенном периоде.

[F1] Исторический дневной ряд: EIA Europe Brent Spot Price FOB — daily historical observations, USD/bbl; средние по доступным наблюдениям месяца. Последнее дневное наблюдение: 2026-09-30. https://www.eia.gov/dnav/pet/hist_xls/RBRTEd.xls

Запрос: `99209a1b-0dc9-4c4d-84b8-e68cddd50240`; статус: `forecasted`.

## out_of_scope

Напиши рецепт борща.

Task `187e58a3aa804e0e`; Analyst: out_of_scope.

Я отвечаю на вопросы нефтегазового рынка.

Запрос: `6784b4d6-bea5-4794-9de4-94132bea748e`; статус: `out_of_scope`.

Отчётный пример имеет статус partial: неподтверждённые дополнительные числа отфильтрованы. Сохранённая цитата прямо относится к 1H26; hybrid корректно использует тот же период.
