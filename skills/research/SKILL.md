---
name: research
description: Qualitative research and analysis for a stock
---

Perform qualitative research and analysis for ticker symbol **$ARGUMENTS**.

The research output serves two purposes: (1) provide structured qualitative intelligence that feeds into `/calibrate` (calibrate) and `/report`, and (2) be a useful standalone document for the user.

## Python Environment
When running Python code, set `PYTHONPATH` so `stock_analyzer` is importable:
```
PYTHONPATH="${CLAUDE_PLUGIN_ROOT:-.}" python3 -c "from stock_analyzer import ..."
```

## Output Template

The research document MUST follow this structure exactly. Every signal field MUST have a value.

```
# {Company} ({TICKER}) — Research
**Date:** YYYY-MM-DD

## Business Context
[2-3 sentences: what the company does, how it makes money, scale]

## Growth Outlook
**Growth signal:** Accelerating / Stable / Decelerating
**Confidence:** High / Medium / Low
[prose]

## Competitive Position & Moat
**Moat:** Wide / Narrow / None
**Direction:** Widening / Stable / Narrowing
[prose]

## Margin & Profitability
**Margin signal:** Expanding / Stable / Compressing
[prose]

## Capital Efficiency
**Capital intensity:** Light / Moderate / Heavy
[prose]

## Key Risks
[2-3 material risks only]

## Key Debate
[prose]
```

## Steps:

### 1. Load Financial Data for Context
- Initialize `StockManager` from `stock_analyzer.stock_manager`
- Try `StockManager.load_financial_data("$ARGUMENTS")` to check for cached data
- **If cached data exists:** Use it (display "Using cached data from {fetched_at}")
- **If no cached data:** Invoke `/fetch $ARGUMENTS` first, then load the cached data
- **If no data available at all** (fetch failed, no API key): Proceed with web-only research. Note in the output: "Research based on public sources only — no financial data context available."

### 2. Identify Questions from the Data
Before searching, review the financial data for anything surprising or unclear. Examples:
- Revenue growth changing direction (accelerating/decelerating)
- Margin anomalies (sudden expansion or compression)
- CapEx spikes or drops
- Unusual debt changes or large acquisitions on the balance sheet
- Cash flow diverging from net income
- Quarterly volatility vs smooth annual trends

These become the primary research questions. If nothing stands out, proceed with general coverage.

### 3. Web Research
- Start with recent earnings results and management commentary — highest information density
- Then expand to: competitive dynamics, industry trends, analyst views, stock-specific controversy
- Follow up on anything that materially affects growth, margin, or competitive position outlook
- Prefer primary sources (earnings transcripts, SEC filings, reputable financial publications) over social media or blogs
- Prioritize recent information (last 1-2 quarters)
- Let depth match the stock — well-covered large-caps need less digging than obscure mid-caps

### 3b. Contrarian Search
After forming initial views from step 3, do a targeted search for the opposing case. Web searches have confirmation bias — you tend to find what you're looking for.

- If your initial view is bullish (growth accelerating, moat widening): search for bear arguments, competitive threats, execution risks, reasons the stock has underperformed
- If your initial view is bearish (growth slowing, margins compressing): search for turnaround signals, catalysts, reasons bulls are optimistic
- If your initial view is neutral: search for both strong bull and strong bear cases

The goal is not to change your mind — it's to ensure your view has been tested against the strongest counter-arguments. Findings from this step should show up in the research as conflicting evidence, Key Risks, or Key Debate as appropriate.

### 4. Write the Research Document

Fill every section using the output template above.

**## Business Context**
- 2-3 sentences: what the company does, how it makes money, current scale
- Orientation for the reader, not deep analysis

**## Growth Outlook**
- What's driving growth: TAM, market dynamics, new products/markets, share gains, pricing power
- Be specific about magnitudes: "revenue growing 25% YoY, accelerating from 20% → 23% → 25% over last 3 quarters" — not "revenue grew strongly"
- Include potential catalysts that could accelerate growth beyond current trajectory
- Realistic 3-5 year trajectory
- **Growth signal:** Accelerating / Stable / Decelerating
- **Confidence:**
  - **High:** multiple data points converge, clear trend, guidance aligns with results
  - **Medium:** directional trend visible but some conflicting signals or limited data
  - **Low:** major uncertainty, contradictory evidence, or business in transition

**## Competitive Position & Moat**
- What advantages exist, with evidence: market share %, retention rates, pricing power, switching costs
- Are advantages widening or narrowing? What threatens them?
- **Moat:** Wide / Narrow / None
- **Direction:** Widening / Stable / Narrowing

**## Margin & Profitability**
- Current margins and trend: "operating margin expanded from 30% → 35% over 3 years" — not "margins are expanding"
- Operating leverage: does growth improve margins or require proportional cost increases?
- Path to mature margins — is the company in an investment phase or already at scale?
- **Margin signal:** Expanding / Stable / Compressing

**## Capital Efficiency**
- How much reinvestment does growth require? Asset-light vs heavy
- CapEx as % of revenue, working capital intensity
- How much revenue does each dollar of invested capital generate?
- **Capital intensity:** Light / Moderate / Heavy

**## Key Risks**
- 2-3 material risks only — the ones that could break the thesis
- For each risk: what triggers it, likelihood (High / Medium / Low), impact on thesis
- Not a laundry list — if it wouldn't change the investment decision, leave it out

**## Key Debate**
- The central question the market is wrestling with for this stock right now
- What consensus believes
- Where consensus might be wrong

### Writing quality
- Every sentence should inform an investment decision — cut generic filler
- Cite the basis for each signal: "Moat: Wide — 85% Fortune 500 Azure adoption, 400M+ M365 seats"
- When evidence conflicts, say so: "Growth signal: Stable — management guides 30% acceleration, but actual results have underperformed guidance by 5-10% over last 4 quarters"

### 5. Self-Review

After writing the draft, re-read it and check:

**Signal-prose consistency:** Is each signal rating justified by the evidence in its section?
- If Moat is "Wide" — does the prose cite multiple strong, durable advantages with evidence?
- If Growth signal is "Accelerating" — does the prose show specific acceleration in the numbers?
- If Confidence is "High" — were there multiple converging data points, or just one source?
- If a signal feels generous relative to the evidence, downgrade it.

**Evidence quality:** For each major claim, is the basis cited? Flag any assertion that reads like opinion without data. Either find support or soften the language.

**Completeness:** Are any sections thin or hand-wavy compared to others? Note the weakest section for step 6.

### 6. Second-Pass on Weakest Section

Identify which section has the least evidence or most generic reasoning. Do one more targeted web search to strengthen it specifically.

For example:
- If Capital Efficiency is thin ("the company is asset-light") — search for CapEx trends, reinvestment rates, capital allocation commentary from earnings calls
- If Competitive Position lacks data — search for market share reports, competitive benchmarks, customer retention data
- If Key Risks feels like a generic list — search for the specific controversy or threat that analysts are debating

One focused search to turn the weakest section from adequate to solid. Then update the draft.

### 7. Save Research Output
- Save to `data/<SYMBOL>/research_YYYY-MM-DD.md` with today's date
- Use `StockManager.save_analysis(symbol, content, filename="research_YYYY-MM-DD.md")`

### 8. Display Summary
Show a concise summary:
- Business context one-liner
- All signal values at a glance: Growth, Confidence, Moat, Direction, Margin, Capital intensity
- Number of key risks and their headlines
- Key debate one-liner
- Location of saved research file
