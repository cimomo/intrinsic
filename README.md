# Intrinsic

A Claude Code plugin for stock analysis. Combines qualitative research with DCF valuation to produce opinionated investment reports.

## What it does

- **Research** a company's competitive position, growth outlook, and risks
- **Value** it with a full DCF model (10-year projection, sensitivity analysis, reverse DCF)
- **Report** a synthesized investment thesis with actionable triggers

All data comes from Alpha Vantage's API. Each stock gets its own folder with cached data, calibrated assumptions, and saved analyses.

## Install

```bash
claude plugin add /path/to/intrinsic
```

Requires Python 3.10+ with `requests` installed (`pip install requests`).

During setup, you'll be prompted for your Alpha Vantage API key. Get a free one at [alphavantage.co](https://www.alphavantage.co/support/#api-key) (25 requests/day).

## Skills

| Skill | Description |
|-------|-------------|
| `/fetch MSFT` | Fetch and cache financial data from Alpha Vantage |
| `/research MSFT` | Qualitative analysis (growth, moat, margins, risks) |
| `/calibrate MSFT` | Interactive review of DCF assumptions |
| `/value MSFT` | Metrics + DCF valuation with sensitivity analysis |
| `/report MSFT` | Synthesize research + valuation into investment report |
| `/analyze MSFT` | Run the full pipeline: fetch, research, calibrate, value, report |

### Quick start

```
/analyze MSFT --auto
```

This runs the full pipeline with automatic assumption calibration. For interactive calibration (you review each assumption), drop the `--auto` flag.

### Selective fetching

```
/fetch MSFT quote              # refresh only the quote
/fetch MSFT income_annual      # refresh specific sources
```

Valid sources: `overview`, `income_annual`, `income_quarterly`, `balance_sheet`, `cash_flow`, `quote`, `all`

## Output

Analysis files are saved to `data/<SYMBOL>/` in your project directory:

```
data/MSFT/
  financial_data.json          # cached API data
  assumptions.json             # DCF assumptions (persisted across runs)
  research_2026-04-03.md       # qualitative analysis
  valuation_2026-04-03.md      # DCF valuation
  analysis_2026-04-03.md       # final investment report
```

## API limits

Alpha Vantage free tier: 25 requests/day, 5/minute. A full fetch uses 6 API calls (~8 seconds with built-in rate limiting). Subsequent analyses reuse cached data with zero API calls.

## License

MIT
