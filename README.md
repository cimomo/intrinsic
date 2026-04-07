# Intrinsic

*From ticker to thesis.*

A Claude Code plugin for stock analysis and [DCF](https://en.wikipedia.org/wiki/Discounted_cash_flow) valuation.

The problem with most DCF models is that small changes in assumptions compound into enormous swings in fair value. Assume 16% growth instead of 13% and the stock goes from "fairly valued" to "30% upside." The math is precise; the inputs are guesses. Intrinsic focuses on the inputs — grounding each assumption in data and qualitative research, then challenging them from multiple angles before you commit.

> [!CAUTION]
> **Not financial advice.** This tool is for informational and educational purposes only. Do your own due diligence.

## Install

```bash
claude plugin marketplace add cimomo/intrinsic
claude plugin install intrinsic
```

Requires Python 3.10+ with `requests` (`pip install requests`) and an [Alpha Vantage API key](https://www.alphavantage.co/support/#api-key) (free, 25 requests/day).

## Quick start

```
/analyze MSFT
```

Takes a few minutes. Produces a research document, a DCF valuation, and an investment report — all saved to `data/MSFT/`. Add `--auto` to skip interactive calibration.

## How it works

`/analyze` chains five steps. Each one feeds the next — research shapes assumptions, assumptions drive the DCF, the report checks everything against itself. The through-line is assumption quality: every step either improves an assumption, tests it, or tells you what happens if it's wrong.

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

These signals aren't decoration — they directly influence the assumptions in step 3. An "Accelerating" growth signal with "High" confidence justifies a higher growth rate than "Stable" with "Medium" confidence. The research skill also reviews its own signal ratings against the evidence, downgrading any that are more generous than the prose supports.

### 3. Calibrate

This is where assumptions get pressure-tested.

Before you set a single number, calibrate calculates what growth rate the current stock price already implies. This anchors everything: if you assume 20% growth and the market prices in 13%, the tool asks you directly — what do you see that the market doesn't?

For each core assumption (revenue growth, operating margin, sales-to-capital ratio), calibrate shows what the data suggests, what the research signals point to, and a recommended value with reasoning. In interactive mode, you choose: recommended, current, or your own value. Your own values are tracked as **manual overrides** — specific bets that persist across future runs.

After all assumptions are set, three checks run:

- **Coherence check** — do the assumptions make sense together? High growth + expanding margins + efficient capital use is a compounding bet. If all three lean bullish, it says so directly.
- **Sensitivity analysis** — which assumption has the biggest impact on fair value? If it's also the one with Low confidence from research, it flags the combination.
- **Pre-mortem** — "assume this stock drops 40% in 12 months. What went wrong?"

### 4. Value

Projects free cash flows over 10 years, discounts them back to today, and calculates what the stock is worth. You get a fair value estimate, a range showing how it shifts under different assumptions, and a recommendation.

The recommendation is **confidence-adjusted** — the tool downgrades its own output when the research inputs are uncertain. A stock showing 20% upside would normally be a BUY, but if research confidence is Medium, it becomes a HOLD. When upside is near zero: "your assumptions produce no margin of safety."

### 5. Report

Synthesizes everything into an opinionated verdict:

- **What You're Paying For** — your manual overrides framed as a specific thesis. What do you believe that the market doesn't?
- **Alignment Check** — do your assumptions actually match the research? Bullish growth assumption + Decelerating signal with Low confidence = flagged disconnect.
- **Where You're Most Exposed** — the one assumption that flips the recommendation if wrong, with the specific threshold.
- **What Would Change This** — concrete triggers with timeframes, not "if growth slows."

## Why not just ask Claude to analyze a stock?

You could. But:

- **Hallucinated financials** — plain-session analysis invents numbers. Intrinsic fetches real data from Alpha Vantage.
- **No structure** — Claude skips steps when it's in a hurry. The pipeline can't cut corners.
- **No persistence** — assumptions vanish when the session ends. Intrinsic saves them per stock, across runs.
- **No self-challenge** — Claude won't push back on its own conclusions. Intrinsic checks your assumptions for coherence, shows you which ones matter most, and asks what would have to go wrong for you to lose money.

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

## DCF methodology

The valuation model follows Aswath Damodaran's (NYU Stern) framework — FCFF discounted at WACC, with reinvestment derived from the Sales-to-Capital ratio, terminal value using g/ROIC reinvestment, and tax rates transitioning from effective to marginal. See [docs/dcf-methodology.md](docs/dcf-methodology.md) for the full approach, formulas, and rationale behind each design choice.

## API limits

Alpha Vantage free tier: 25 requests/day, 5/minute. A full fetch uses 6 API calls (~8 seconds with built-in rate limiting). Everything after fetch reuses cached data.

## License

MIT
