# Intrinsic

*From ticker to thesis.*

A Claude Code plugin for equity research and DCF valuation.

> [!CAUTION]
> **Not financial advice.** This tool is for informational and educational purposes only. The analysis, valuations, and recommendations it produces are based on automated models and publicly available data, which may be incomplete, outdated, or incorrect. Always do your own due diligence and consult a qualified financial advisor before making investment decisions.

## Install

```bash
claude plugin add cimomo/intrinsic
```

Requires Python 3.10+ with `requests` installed (`pip install requests`).

During setup, you'll be prompted for your Alpha Vantage API key. Get a free one at [alphavantage.co](https://www.alphavantage.co/support/#api-key) (25 requests/day).

## How it works

`/analyze MSFT` runs a five-step pipeline:

1. **Fetch** — pulls financials from Alpha Vantage (income statements, balance sheet, cash flow, quote) and caches them locally
2. **Research** — web searches for earnings results, competitive dynamics, management commentary, and the bear case. Produces structured signals: growth outlook, moat, margin trend, capital intensity, key risks, and the central debate the market is having about the stock
3. **Calibrate** — sets DCF assumptions (revenue growth, target margin, sales-to-capital ratio) using both financial data and research signals. Runs a reverse DCF to show what growth the market is pricing in, then checks assumptions for coherence and runs sensitivity analysis
4. **Value** — 10-year DCF with year-by-year projections, sensitivity grid, and a confidence-adjusted recommendation (research confidence downgrades the recommendation when uncertainty is high)
5. **Report** — synthesizes everything into an opinionated verdict: what you're betting on, where your assumptions are vulnerable, and specific triggers that would change the thesis

### Auto vs interactive

```
/analyze MSFT --auto    # full pipeline, no questions asked
/analyze MSFT           # pauses at calibrate for you to review each assumption
```

The `--auto` flag matters at the calibrate step. In auto mode, assumptions are set from data + research signals, respecting any manual overrides you've previously set. In interactive mode, you review each core assumption with the data and research context, and decide what value to use.

Interactive calibration is where you make the tool yours — you're not just running a model, you're encoding a specific view on the company.

### Running steps individually

Each step can run on its own:

| Skill | When to use it |
|-------|----------------|
| `/fetch MSFT` | Refresh data (e.g., after earnings). Use `/fetch MSFT quote` for just the price |
| `/research MSFT` | Update qualitative view without re-running the full pipeline |
| `/calibrate MSFT` | Revisit assumptions after new information — the most hands-on step |
| `/value MSFT` | Re-run valuation after tweaking assumptions |
| `/report MSFT` | Regenerate the report from existing research + valuation files |

The pipeline is designed so each step's output feeds the next. But if you've already fetched and researched, you can jump straight to `/calibrate` and `/value` without re-doing earlier work.

### Assumptions persist

DCF assumptions are saved per stock in `assumptions.json`. When you manually set a value during calibration, it's tracked as a manual override — future auto-calibrations won't touch it. This means `/analyze MSFT --auto` gets smarter over time: it respects your views while updating everything else from fresh data.

## Output

Analysis files are saved to `data/<SYMBOL>/`:

```
data/MSFT/
  financial_data.json          # cached API data
  assumptions.json             # DCF assumptions (persisted across runs)
  research_2026-04-03.md       # qualitative analysis
  valuation_2026-04-03.md      # DCF valuation
  analysis_2026-04-03.md       # final investment report
```

## API limits

Alpha Vantage free tier: 25 requests/day, 5/minute. A full fetch uses 6 API calls (~8 seconds with built-in rate limiting). Subsequent analyses reuse cached data — zero API calls.

## License

MIT
