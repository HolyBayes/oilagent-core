---
name: oil_forecast
description: Calculate new Brent ARIMA/ETS forecasts and explicit supply-cut scenarios using Forecast MCP.
version: 0.4.0
type: instruction
always_in_context: false
os: any
---

For a newly calculated Brent forecast call mcp_analyst__forecast with asset="brent".
Extract horizon_months (1..6), optional as_of and inclusive start_date/end_date
(ISO dates). Omit unspecified dates; the service fetches history and fills only
missing cache intervals. Never ask the user for a CSV when the prepared service
is available. Do not substitute a report's forecast for a new calculation.

Return both ARIMA and ETS tables, USD/bbl, nominal 80% prediction intervals,
data cutoff, daily-history source, backtest/naive limitations and warnings.
Preserve calculated values. If the service fails, report the failure.

Use mcp_analyst__supply_cut only with explicit P0, Q0, cut and elasticity inputs;
ask for missing assumptions rather than estimating them. It is sensitivity
analysis, not ARIMA or a statistical confidence interval. For a current quote
use market_quote; distinguish delayed futures from Brent spot history.
Statements in dated OPEC/EIA reports belong to report_rag. No trading advice.
