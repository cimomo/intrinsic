# CLAUDE.md

## Project Overview

Stock analysis plugin for Claude Code. Combines qualitative research with DCF valuation to produce investment reports. Data from Alpha Vantage API, processed through Python modules, presented via skills.

## Skills

```
/fetch <ticker> [sources...]        # Fetch & cache financial data from Alpha Vantage
/research <ticker>                 # Qualitative analysis -> saves research_YYYY-MM-DD.md
/calibrate <ticker> [--auto]       # Walk through DCF assumptions (interactive or auto)
/value <ticker>                    # Metrics + DCF valuation -> saves valuation_YYYY-MM-DD.md
/report <ticker>                   # Synthesize research + valuation -> saves analysis_YYYY-MM-DD.md
/analyze <ticker> [--auto]          # Orchestrator: fetch -> research -> calibrate -> value -> report
```

## Architecture

### Data Flow
1. **AlphaVantageFetcher** (`av_fetcher.py`) -> Raw financial data (JSON) from Alpha Vantage REST API
2. **FinancialMetrics** (`metrics.py`) -> Parses raw data into structured metrics and DCF inputs
3. **DCFModel** (`dcf.py`) -> 10-year FCF projection, terminal value, fair value per share
4. **StockManager** (`stock_manager.py`) -> Folder management, assumption persistence, data caching
5. **Skills** -> Orchestrate the workflow

### Python Environment
When running as a plugin, `stock_analyzer` modules are importable via:
```
PYTHONPATH="${CLAUDE_PLUGIN_ROOT:-.}" python3 -c "from stock_analyzer import ..."
```

### API Key Resolution
1. `CLAUDE_PLUGIN_OPTION_ALPHA_VANTAGE_API_KEY` (plugin config)
2. `ALPHA_VANTAGE_API_KEY` environment variable
3. `.env` file via python-dotenv (development fallback)

## Analysis Workflow

The `/analyze` skill chains sub-skills in sequence:

1. `/fetch` -> fetches fresh data (including current quote price)
2. `/research` -> saves `research_YYYY-MM-DD.md`
3. `/calibrate --auto` -> calibrates DCF assumptions from research signals
4. `/value` -> saves `valuation_YYYY-MM-DD.md`
5. `/report` -> saves `analysis_YYYY-MM-DD.md`

Each sub-skill can also be run independently.

## Stock Folder Management

Each stock gets its own folder under `data/` (e.g., `data/MSFT/`):
- `assumptions.json` — DCF assumptions (persisted across runs, includes `_manual_overrides`)
- `financial_data.json` — Cached API data with per-source metadata
- `research_YYYY-MM-DD.md` — Qualitative analysis
- `valuation_YYYY-MM-DD.md` — DCF valuation
- `analysis_YYYY-MM-DD.md` — Final investment report

**StockManager** handles folder creation, assumption load/save, financial data caching, and data freshness validation. Always use `verbose=True` when calling `DCFModel.calculate_fair_value()`.

## Default Assumptions

Located in `DCFAssumptions` dataclass (`dcf.py`):
- Revenue growth: 10% (years 1-5, then tapers to terminal rate over years 6-10)
- Terminal growth: defaults to risk-free rate (4.5%)
- Projection period: 10 years
- Risk-free rate: 4.5% (10-year Treasury)
- Market risk premium: 5%
- Tax rate: 21% (marginal; effective_tax_rate transitions to marginal over projection period when set)
- Cost of debt: 5%
- Terminal ROIC: defaults to WACC (no excess returns in perpetuity; override for wide-moat companies)

## Data Handling

**Missing Data:** All parsing uses `safe_float()` which returns `None` or defaults for missing fields.

**Alpha Vantage:** Free tier: 25 requests/day, 5/minute. A full 6-source fetch takes ~8 seconds with built-in rate limiting (1.5s between requests). Set API key via plugin config or `ALPHA_VANTAGE_API_KEY` env var.

**Data Freshness:** After fetching, `/fetch` validates that quarterly income data includes the latest quarter from the overview. Use `StockManager.validate_data_freshness(symbol)` programmatically.

## Financial Data Caching

Use `/fetch <ticker>` to fetch and cache all data once. Analysis skills automatically check for cached data before making API calls.

**Cache structure** (`financial_data.json`):
- `symbol`, `fetched_at`, `fetched_at_unix` — metadata
- `sources` — per-source status, provider, dates
- `data.overview`, `data.income_statement_annual`, `data.income_statement_quarterly`, `data.balance_sheet`, `data.cash_flow`, `data.quote`

**Valid source names:** `overview`, `income_annual`, `income_quarterly`, `balance_sheet`, `cash_flow`, `quote`, `all`

No automatic expiration — user controls freshness by re-running `/fetch`.

## Testing

```bash
cd /path/to/intrinsic
python -m pytest tests/
```
