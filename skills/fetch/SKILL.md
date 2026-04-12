---
name: fetch
description: Fetch and cache financial data for a stock
---

Fetch and cache financial data for **$ARGUMENTS**.

This saves data locally so `/analyze` and `/value` can reuse it without burning API calls.

## Python Environment
When running Python code, set `PYTHONPATH` so `stock_analyzer` is importable:
```
PYTHONPATH="${CLAUDE_PLUGIN_ROOT:-.}" python3 -c "from stock_analyzer import ..."
```

## Argument Parsing

Parse `$ARGUMENTS` to extract:
- **ticker**: First argument (required) — the stock symbol
- **sources**: Remaining arguments (optional) — specific data sources to fetch

Valid source names: `overview`, `income_annual`, `income_quarterly`, `balance_sheet`, `cash_flow`, `quote`, `all`

If no sources are specified, or `all` is given, fetch all 6 sources.

**Examples:**
- `/fetch MSFT` → fetch all 6 sources
- `/fetch MSFT quote` → fetch only quote
- `/fetch MSFT income_annual balance_sheet` → fetch specific sources

## Steps:

### 1. Initialize Stock Folder
- Initialize `StockManager` from `stock_analyzer.stock_manager`
- Create the stock folder for the ticker via `get_stock_folder()`

### 2. Fetch via Alpha Vantage

1. Import `AlphaVantageFetcher` from `stock_analyzer.av_fetcher`
2. Try to instantiate `AlphaVantageFetcher(ticker)` — if it raises `ValueError` (missing API key), display error and stop:
   `"Alpha Vantage API key not set. Configure via plugin settings (claude plugin config intrinsic) or export ALPHA_VANTAGE_API_KEY=your_key_here"`
3. Determine which sources to fetch:
   - If specific sources were given → fetch those
   - If no sources given → fetch all 6
4. Fetch each source **sequentially** (rate limiting is built into the fetcher, ~1.5s between calls):
   - `overview` → `fetcher.fetch_overview()`
   - `income_annual` → `fetcher.fetch_income_statement(period="annual", limit=5)`
   - `income_quarterly` → `fetcher.fetch_income_statement(period="quarterly", limit=10)`
   - `balance_sheet` → `fetcher.fetch_balance_sheet(period="annual", limit=5)`
   - `cash_flow` → `fetcher.fetch_cash_flow(period="annual", limit=5)`
   - `quote` → `fetcher.fetch_quote()`
5. Track each result — if fetcher returns `None`, report as failed
6. Track all successful sources as provider **"Alpha Vantage"**

**Important:** The AlphaVantageFetcher has built-in 1.5s rate limiting between requests. A full 6-source fetch takes ~8 seconds. Do NOT make parallel calls — sequential is required to avoid throttling.

**Note on income statements:** Alpha Vantage returns both annual and quarterly reports in a single API call. The fetcher makes one call for `INCOME_STATEMENT` and slices the result by period type. If both `income_annual` and `income_quarterly` are requested, only one API call is made for each (the `_get` call is separate per invocation, so 2 API calls total for income).

**Why 5 years:** The calibrate skill needs 5+ years of annual data to calculate historical average and incremental sales-to-capital ratios. Fetching 5 years instead of 3 costs zero extra API calls — Alpha Vantage returns all available data and the `limit` parameter just controls how many periods are kept.

### 3. Save Cached Data
- Load existing cache via `StockManager.load_financial_data()` (if any)
- **Important:** `load_financial_data()` returns the full envelope `{"symbol", "fetched_at", "sources", "data": {...}}`. Merge into `existing["data"]`, not `existing` itself — `save_financial_data` wraps its input into a new envelope, so passing the full envelope creates double-wrapping (`data.data.overview`).
- If existing cache found: merge new sources into `existing["data"]` (only overwrite the **successfully fetched** sources, preserve the rest)
- If no existing cache: start with an empty dict (missing sources will not be present)
- Build a `source_info` dict tracking each of the 6 sources with: `status` ("ok" or "missing"), `provider` ("Alpha Vantage" or null), `fetched_date`, `latest_period`, and `reason` (for failures)
- For sources not fetched in this run, preserve their existing `source_info` from the cache
- Save merged result via `StockManager.save_financial_data(symbol, data, source_info=source_info)` — `data` here is the merged sources dict, NOT the full envelope
- **Do not save failed/empty results** — only save sources that returned valid data

**Key mapping** (source name → cache key):
- `overview` → `overview`
- `income_annual` → `income_statement_annual`
- `income_quarterly` → `income_statement_quarterly`
- `balance_sheet` → `balance_sheet`
- `cash_flow` → `cash_flow`
- `quote` → `quote`

### 3b. Validate Ticker
After fetching, check that the data looks valid. If the overview was fetched and has no `Name` or `Symbol` field (or they're empty/"None"), the ticker is likely invalid. Display a warning: "Ticker may be invalid — overview returned no company name. Check the symbol and retry." Do not stop — the user might be fetching partial data intentionally.

### 3c. Validate Data Freshness
After saving, call `StockManager.validate_data_freshness(ticker)` on the saved data. This checks consistency between the overview's `LatestQuarter` and the actual dates in the quarterly/annual data. Capture the validation result for display in step 4.

### 4. Display Summary
Show a confirmation with:
- Which sources were fetched successfully
- Which sources were preserved from existing cache
- Which sources failed (if any), with a suggested retry command
- File path where data was saved
- Timestamp of fetch
- Company name (from overview, if available)
- Current price (from quote, if available)
- Period counts for any financial statement sources that were fetched
- **Latest period date** for each source (from `validate_data_freshness()` result's `latest_dates`)
- **Data freshness warnings** from `validate_data_freshness()` result's `warnings` list — display each with a warning prefix
- Reminder: run `/analyze <ticker>` or `/value <ticker>` to analyze using this cached data

**Example summary format:**
```
Source              | Status | Latest Period
--------------------|--------|-------------
overview            | OK     | LatestQuarter: 2025-12-31
income_annual       | OK     | 2025-12-31 (5 periods)
income_quarterly    | OK     | 2025-12-31 (10 periods)
balance_sheet       | OK     | 2025-12-31 (5 periods)
cash_flow           | OK     | 2025-12-31 (5 periods)
quote               | OK     | $25.17
```
