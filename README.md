# Intrinsic

*From ticker to thesis.*

A Claude Code plugin for stock analysis and [DCF](https://en.wikipedia.org/wiki/Discounted_cash_flow) valuation — with built-in checks that challenge your assumptions before you commit to them.

> [!CAUTION]
> **Not financial advice.** This tool is for informational and educational purposes only. Do your own due diligence.

## Install

```bash
claude plugin add cimomo/intrinsic
```

Requires Python 3.10+ with `requests` (`pip install requests`) and an [Alpha Vantage API key](https://www.alphavantage.co/support/#api-key) (free, 25 requests/day).

## Quick start

```
/analyze MSFT
```

Takes a few minutes. Produces a research document, a DCF valuation, and an investment report — all saved to `data/MSFT/`. Add `--auto` to skip interactive calibration.

## How it works

`/analyze` chains five steps. Each one feeds the next — research shapes assumptions, assumptions drive the DCF, the report checks everything against itself.

### 1. Fetch

Pulls financials from Alpha Vantage and caches them locally. Subsequent analyses reuse the cache.

### 2. Research

Searches the web for earnings results, competitive dynamics, and management commentary. Then does a targeted contrarian search — if the initial read is bullish, it looks for bear arguments, and vice versa.

The output is structured signals that the rest of the pipeline consumes:

- **Growth outlook** (Accelerating / Stable / Decelerating) with a confidence level
- **Moat** (Wide / Narrow / None) and direction (Widening / Stable / Narrowing)
- **Margin trend** (Expanding / Stable / Compressing)
- **Capital intensity** (Light / Moderate / Heavy)
- **Key risks** — the 2-3 things that could break the thesis
- **Key debate** — the central question the market is wrestling with

### 3. Calibrate

Before you set a single assumption, calibrate runs a **reverse DCF** — solving for the revenue growth rate the current stock price implies. If you assume 20% growth and the market prices in 13%, you need to know why you think the market is wrong.

For each core assumption (revenue growth, operating margin, sales-to-capital ratio), calibrate shows what the data suggests, what the research signals point to, and a recommended value with reasoning. You choose: recommended, current, or your own value. Your own values are tracked as **manual overrides** — specific bets that persist across future runs.

After all assumptions are set, three checks run:

- **Coherence check** — do the assumptions make sense together? If all three lean bullish, it says so: "this is a compounding bet."
- **Sensitivity analysis** — which assumption swings fair value the most? If it's also the one with Low confidence from research, it flags the combination.
- **Pre-mortem** — "assume this stock drops 40% in 12 months. What went wrong?"

### 4. Value

10-year DCF with year-by-year projections, tapering growth, terminal value, and a sensitivity grid. Includes trailing and forward FCF yield, sanity checks (e.g., terminal value dominating the valuation), and a confidence-adjusted recommendation.

Confidence-adjusted means the tool downgrades its own output when the inputs are uncertain. A stock showing 20% upside would normally be a BUY — but if research confidence is Medium, it becomes a HOLD. When upside is near zero: "your assumptions produce no margin of safety."

### 5. Report

Synthesizes everything into an opinionated verdict:

- **What You're Paying For** — manual overrides framed as a thesis. The gap between your assumed growth and market-implied growth is your bet, stated plainly.
- **Alignment Check** — do your assumptions match the research? Bullish growth assumption + Decelerating signal with Low confidence = flagged disconnect.
- **Key Assumption Vulnerability** — the one assumption that flips the recommendation, with the specific threshold.
- **What Would Change This** — concrete triggers with timeframes, not "if growth slows."

## Why not just ask Claude to analyze a stock?

You could. But:

- **Hallucinated financials** — plain-session analysis invents numbers. Intrinsic fetches real data from Alpha Vantage.
- **No structure** — Claude skips steps when it's in a hurry. The pipeline can't cut corners.
- **No persistence** — assumptions vanish when the session ends. Intrinsic saves them per stock, across runs.
- **No self-challenge** — Claude won't push back on its own conclusions. Intrinsic has a reverse DCF anchor, coherence check, sensitivity analysis, and pre-mortem built into every run.

## Running steps individually

| Skill | When to use it |
|-------|----------------|
| `/fetch MSFT` | Refresh data after earnings. `/fetch MSFT quote` for just the price |
| `/research MSFT` | Update qualitative view without re-running everything |
| `/calibrate MSFT` | Revisit assumptions after new information |
| `/value MSFT` | Re-run valuation after tweaking assumptions |
| `/report MSFT` | Regenerate report from existing research + valuation |

Valid fetch sources: `overview`, `income_annual`, `income_quarterly`, `balance_sheet`, `cash_flow`, `quote`

## Assumptions persist

DCF assumptions are saved per stock. Manual overrides — values you set during interactive calibration — are tracked separately. When you run `/analyze MSFT --auto` next quarter, auto-calibration updates data-driven assumptions from fresh research but leaves your overrides intact. Your views persist; everything else stays current.

## Output

```
data/MSFT/
  financial_data.json          # cached API data
  assumptions.json             # DCF assumptions (persisted across runs)
  research_2026-04-03.md       # qualitative analysis
  valuation_2026-04-03.md      # DCF valuation
  analysis_2026-04-03.md       # investment report
```

## API limits

Alpha Vantage free tier: 25 requests/day, 5/minute. A full fetch uses 6 API calls (~8 seconds with built-in rate limiting). Everything after fetch reuses cached data.

## License

MIT
