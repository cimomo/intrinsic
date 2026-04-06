---
name: calibrate
description: Review and update DCF assumptions for a stock interactively
---

Review and update DCF assumptions for **$ARGUMENTS**.

**Mode:** If `$ARGUMENTS` contains `--auto`, run in auto mode (see below). Otherwise, run interactively.

## Python Environment
When running Python code, set `PYTHONPATH` so `stock_analyzer` is importable:
```
PYTHONPATH="${CLAUDE_PLUGIN_ROOT:-.}" python3 -c "from stock_analyzer import ..."
```

## Assumption Categories

Assumptions are split into three tiers based on how much attention they need:

**Core assumptions** — company-specific, change with new data, worth deliberating. Research context matters here.
- Revenue Growth Rate (Years 1-5)
- Operating Margin / Target Operating Margin
- Sales-to-Capital Ratio
- Terminal ROIC (how much competitive advantage persists in perpetuity)

**Mechanical assumptions** — company-specific but derivable from financial data, no judgment needed.
- Beta (from company overview)
- Cost of Debt (interest expense / total debt)
- Tax Rate (tax expense / pre-tax income)

**Market/fixed assumptions** — rarely change, near-constant.
- Risk-Free Rate (10-year Treasury, default 4.5%)
- Market Risk Premium (standard 5%)
- Terminal Growth Rate (defaults to risk-free rate)
- Projection Years (default 10)

## Auto Mode (`--auto`)

When `--auto` is present, skip all `AskUserQuestion` calls. Follow the same steps as interactive mode but:
- Apply recommended values directly without asking (respecting `_manual_overrides`)
- Self-correct during coherence check
- Self-correct during sensitivity awareness if high-impact + low confidence
- Generate pre-mortem reasoning
- Save automatically

Strip `--auto` from the ticker symbol (e.g., `MSFT --auto` → ticker is `MSFT`).

## Steps:

### 1. Load Current Assumptions and Financial Data
- Initialize `StockManager` and load existing assumptions for **$ARGUMENTS**
- Load `_manual_overrides` via `StockManager.load_manual_overrides(symbol)`
- Load cached financial data via `StockManager.load_financial_data()` if available
- Display the current assumptions file contents

### 1b. Load Research Context (if available)
- Look for the most recent `research_*.md` file in `data/<SYMBOL>/`
- **If found:** Read it and note its date. If older than 30 days, display a warning: "Using research from {date} — consider re-running /research first"
- **If not found:** Note that no research is available. Proceed with data-only calibration and display: "No research file found — recommendations based on financial data only"

### 2. Reverse DCF — What Does the Market Imply?

Before setting assumptions, calculate what revenue growth rate the current stock price implies. This gives calibrate a crucial anchor.

Use `DCFModel.reverse_dcf(financial_data, shares_outstanding, current_price)` to solve for the revenue growth rate that produces fair value = current price. This uses binary search internally — no manual loops needed.

Display:
```
Market-implied revenue growth: ~X%
  (At current price of $XXX, with WACC X.X% and current margin assumptions)
  Your data-driven estimate will be compared against this.
```

This is context, not a recommendation. It tells you: "the market is pricing in X% growth — if your assumption differs, you should know why."

**Auto mode:** Calculate and display. Use as a reasonableness check when setting revenue growth.
**Interactive mode:** Calculate and display before presenting core assumptions.

### 3. Core Assumptions (detailed review)

For each core assumption, do the following:
1. Show the **current value** from the assumptions file
2. Show **what the financial data suggests** — derive a recommended value from the cached financial data, company overview, and recent trends
3. **If research is available:** Start with the relevant signal fields as anchors, then consider the full research context — including risks, competitive dynamics, key debate, and any other findings that affect this assumption. Primary signal anchors:
   - **Revenue growth:** Growth Outlook → Growth signal + Confidence level
   - **Operating margin / target:** Margin & Profitability → Margin signal
   - **Sales-to-capital ratio:** Capital Efficiency → Capital intensity
   - The signals are starting points, not the only inputs. Any research finding can influence any assumption.
   - If qualitative findings push the recommendation away from the data-only value, state this explicitly: "Data suggests X%. Adjusting to Y% because [specific research finding]."
   - Research can push beyond the data-supported range, but moderately.
4. **If no research:** Derive recommendation from data only
5. Explain **your reasoning** briefly, using this format:
   ```
   Assumption Name: recommended% (current: current%)
     Financial data: [what the numbers show]
     Research context: [what qualitative findings suggest, if available]
     → Recommending X% because [reasoning combining both]
   ```
6. **Interactive mode:** Ask the user what value to use (current, recommended, or custom)
7. **Auto mode:** Apply the recommended value (unless field is in `_manual_overrides` — then keep and show what auto would recommend)

Go through these in order:

**a. Revenue Growth Rate (Years 1-5)**
- Look at: recent YoY quarterly revenue growth trends, annual revenue growth, analyst estimates
- Consider: is growth accelerating or decelerating? Is the current assumption realistic?
- **Interactive mode:** If the user picks a value significantly above the market-implied rate from the reverse DCF, challenge constructively: "That's X% above what the market prices in. What specifically do you see that the market doesn't?" This isn't to block them — it's to ensure the choice is deliberate.

**b. Operating Margin / Target Operating Margin**
- Look at: current operating margin from financials, historical trend, peer comparison
- Consider: is margin expanding or contracting? What's a realistic target?

**c. Sales-to-Capital Ratio**
- **Always calculate 5+ years of historical data before recommending.** Compute both:
  - **Average S/C** = Revenue / Invested Capital (where Invested Capital = Equity + LT Debt - Cash)
  - **Incremental S/C** = ΔRevenue / ΔInvested Capital (year-over-year — this is what the DCF model actually uses)
- Use web sources if Alpha Vantage doesn't have enough history
- Present the full historical table to the user before asking for a value
- Consider: is there a regime change (e.g., capital-light → capital-heavy)? Is the trend improving or deteriorating?

**d. Terminal ROIC (Competitive Advantage Persistence)**

Terminal ROIC determines how much the company must reinvest to sustain terminal growth. It is the single most impactful assumption on terminal value — the difference between ROIC = WACC and ROIC = 20% can swing fair value by 20-40%.

**Anchors — always show these before recommending:**
- **Current ROIC** from `calculate_dcf_inputs()` (returned as `dcf_inputs['roic']`)
- **WACC** (the floor — no competitive advantage persists)
- **Implied ROIC from model assumptions:** `operating_margin × sales_to_capital × (1 - tax_rate)`. This is what the DCF's own year-10 numbers imply, and represents the ROIC if current operating efficiency continues.
- **Constraint:** Terminal ROIC must be >= terminal growth rate (otherwise reinvestment > 100%)

**Framework for setting terminal ROIC — use research moat signals:**

The core question: *How much of today's excess returns (ROIC above WACC) will persist in perpetuity?*

| Research signal | Terminal ROIC | Reasoning |
|----------------|---------------|-----------|
| Moat: None | = WACC | Competition fully erodes excess returns |
| Moat: Narrow, Direction: Narrowing | = WACC | Advantages eroding, converge to no-moat |
| Moat: Narrow, Direction: Stable | Midpoint of WACC and current ROIC | Some advantages persist but partially erode |
| Moat: Wide, Direction: Narrowing | Midpoint of WACC and current ROIC | Strong today but declining |
| Moat: Wide, Direction: Stable | 75% of the way from WACC to current ROIC | Strong and durable |
| Moat: Wide, Direction: Widening | Current ROIC (or implied ROIC) | Advantages strengthening |

This table is a starting point. **Go deeper — reason about the specific source of advantage:**
- **Network effects** (MSFT ecosystem, NVDA CUDA, platform businesses) → very durable, among the strongest moats. ROIC decay is slow.
- **Switching costs** (enterprise software, embedded systems) → durable, but can erode with generational technology shifts.
- **Intangible assets** (brand, patents, regulatory licenses) → patents expire, brands fade, but regulatory moats persist. Duration matters.
- **Cost advantages / scale** (manufacturing, distribution) → can be disrupted by new technology or geographic shifts.
- **Data advantages** (proprietary datasets, feedback loops) → durable if the data compounds; weak if the data becomes commoditized.

For each source of advantage identified in the research, ask: *What would have to happen for this advantage to disappear?* If the answer is "a generational technology shift" or "a fundamental change in how the industry works," the advantage is likely to persist and terminal ROIC should reflect that.

**How to present the recommendation:**
```
Terminal ROIC:
  WACC (floor):           9.9%    ← no excess returns, competition wins
  Current ROIC:          29.1%    ← today's returns
  Implied ROIC (model):  25.3%    ← what your margin + S/C assumptions imply
  Recommended:           22.0%    ← 75% toward current ROIC
    Research: Wide moat (Stable) — Azure/M365 ecosystem creates deep switching costs
    and network effects. Enterprise lock-in is multi-year. No plausible path to full
    moat erosion within 10-year horizon.
    Impact: Terminal ROIC of 22% vs WACC-default changes fair value by +$64
```

**Guard:** In all cases, cap terminal ROIC at 2× WACC. Even the strongest moats should not imply returns exceeding double the cost of capital in perpetuity. If the table or current ROIC suggests a value above 2× WACC, use 2× WACC and note the cap.

**Interactive mode:** Present the anchors, the table-based recommendation, and the specific reasoning. Ask: "recommended (22%), WACC default (9.9%), or custom?"

**Auto mode:** Apply the table-based recommendation using research moat signals. If no research is available, keep default (= WACC). If the recommended value is a manual override, keep the override and show what auto would recommend.

### 4. Mechanical Assumptions (auto-derive from data)

Derive these silently from the financial data. No detailed reasoning needed — just show a one-line summary per field.

- **Beta:** Use beta from company overview data. Display: "Beta: X.XX (from overview)"
- **Cost of Debt:** Calculate as interest expense / total debt from financials. Display: "Cost of debt: X.X% (interest expense / total debt)"
  - **Sanity check:** If cost of debt is more than 100bps below the risk-free rate, flag: "Cost of debt (X.X%) is well below risk-free rate (Y.Y%) — this reflects the blended coupon on legacy debt, not marginal borrowing cost. New issuances are likely at Z%. WACC may be slightly understated." This is informational — don't auto-correct, but ensure the user is aware.
- **Tax Rate:** Calculate as effective tax rate (tax expense / pre-tax income). Display: "Tax rate: X.X% (effective rate from income statement)"

If a mechanical assumption is in `_manual_overrides`, keep the user's value and note: "Beta: keeping manual override at X.XX (data suggests Y.YY)"

**Interactive mode:** After showing all three, ask once: "Any of these to adjust? [Enter to accept all]" — only drill into specifics if the user says yes.

### 5. Market/Fixed Assumptions (keep defaults)

These rarely need changing. Show a compact summary:

```
Market/Fixed Assumptions (unchanged):
  Risk-free rate:      4.5%
  Market risk premium:  5.0%
  Terminal growth rate: 4.5% (= risk-free rate)
  Projection years:    10
```

If any value looks clearly outdated (e.g., risk-free rate is 4.5% but current Treasury is 3.8%), flag it: "Risk-free rate may be outdated — current 10-year Treasury is ~3.8%. Update? [y/N]"

**Interactive mode:** Ask once: "Any of these to adjust? [Enter to accept all]"

**Auto mode:** Keep current values. Only update risk-free rate if a WebSearch was already done and the current value is more than 50bps off.

### 6. Coherence Check

After all assumptions are set (core + mechanical + market/fixed), step back and review them as a whole. This is a reasoning step — no new data or web searches needed.

**ROIC context:** Before running consistency checks, compute ROIC from `calculate_dcf_inputs()` (returned as `dcf_inputs['roic']`). Display it: "Current ROIC: X.X% | WACC: Y.Y% | Spread: Z.Z%". This anchors the checks below.

**Cross-assumption consistency:** Do the assumptions make sense together?
- **Value of growth:** If ROIC < WACC, growth destroys value — higher growth makes the stock *less* valuable. Flag prominently: "ROIC (X%) is below WACC (Y%). At these returns, growth destroys value. Either ROIC must improve (higher margins or better capital efficiency) or the growth assumption is working against you."
- **Fundamental growth check:** Compute `reinvestment_rate = (Revenue × growth_rate / sales_to_capital) / NOPAT` (where Revenue and NOPAT are current-year values). Then `fundamental_growth = reinvestment_rate × ROIC`. If the assumed revenue growth rate significantly exceeds fundamental growth, flag: "Assumed growth (X%) exceeds what current ROIC and reinvestment support (Y%). Achieving X% requires improving ROIC or increasing reinvestment beyond current levels."
- High revenue growth + low sales-to-capital → implies heavy reinvestment. Calculate the implied reinvestment: Revenue × Growth Rate / S-C Ratio. Compare this to actual CapEx. If they diverge significantly, either S/C is wrong or not all CapEx is growth-related — state which you're assuming.
- Expanding margins + high revenue growth → is the company actually showing operating leverage, or does growth require investment that pressures margins?
- Moat rated "Narrowing" or "None" → should terminal growth be at or below risk-free rate?
- High revenue growth + low beta → is this really a low-risk high-growth company, or is beta understating the risk?
- Revenue growth decelerating + expanding target margins → is the margin expansion story replacing the growth story? Does that make sense?
- **Directional bias check:** Are all three core assumptions leaning the same direction (all bullish or all bearish)? If so, be direct: "All three core assumptions lean bullish — growth, margins, AND capital efficiency. This is a compounding bet. If any one is wrong, the others likely are too. The user should know they're making a consistently optimistic set of assumptions." Don't soften this with "passed with notes."

**Sanity check against research (if available):** Do the combined assumptions align with the qualitative story?
- Research says "Low confidence" on growth but assumptions are aggressive → flag the disconnect
- Research identifies major risks (High likelihood) but assumptions don't reflect conservatism → flag
- Key Debate suggests market is skeptical about a specific factor but assumptions are optimistic on it → flag

**What to do with findings:**
- **Auto mode:** Self-correct. Adjust the inconsistent assumptions and note what changed: "Coherence check: reduced revenue growth from 18% to 15% — inconsistent with Decelerating growth signal and Low confidence"
- **Interactive mode:** Flag each inconsistency to the user and ask if they want to adjust: "Revenue growth is set at 18% but research confidence is Low and growth is Decelerating. Revise? [y/N]"

If no inconsistencies are found, display: "Coherence check passed — assumptions are internally consistent"

### 7. Sensitivity Awareness — What Matters Most?

Run a quick sensitivity check on the 4 core assumptions. For each, vary by ±20% from the current value and calculate the resulting fair value using `DCFModel`. For terminal ROIC, also show the WACC-default value as the downside case. Display:

```
Sensitivity (±20% change in assumption → fair value impact):
  Revenue growth:    $XXX to $XXX  (±$XX, ±XX%)  ← highest impact
  Operating margin:  $XXX to $XXX  (±$XX, ±XX%)
  Sales-to-capital:  $XXX to $XXX  (±$XX, ±XX%)
  Terminal ROIC:     $XXX to $XXX  (±$XX, ±XX%)  [WACC-default: $XXX]
```

Flag the highest-impact assumption: "Fair value is most sensitive to revenue growth — a ±20% change swings fair value by ±$XX. This assumption deserves the most scrutiny."

**Auto mode:** If the highest-impact assumption also has Low confidence from research, flag: "Revenue growth has the highest impact on fair value AND Low confidence from research — consider using the conservative end of the range." Self-correct if warranted.

**Interactive mode:** Challenge the user when the highest-impact assumption is vulnerable:
- If the highest-impact assumption has Low confidence from research: "Revenue growth drives the most value and has Low confidence. Want to revise? [y/N]"
- If the highest-impact assumption is a manual override: "[Assumption] is the most sensitive assumption AND a manual override — your specific bet has the biggest impact on fair value. A ±20% swing means ±$XX. Are you comfortable with this exposure? [y/N]"
- Both conditions can apply simultaneously — flag both.

### 8. Pre-Mortem — What Could Go Wrong?

Final gut check. One paragraph of reasoning:

"Assume this stock drops 40% in the next 12 months. What went wrong?"

Consider:
- Which assumption was most likely wrong, and in which direction?
- What event or development would break the thesis?
- Is there a risk not captured in the Key Risks section that could cause this?

Display the pre-mortem reasoning. This is informational — it doesn't change assumptions, but it provides important context that gets saved with the calibration output and informs the final report.

**Auto mode:** Generate and display.
**Interactive mode:** Generate and display. Ask: "Does this change your view on any assumptions? [y/N]"

### 9. Save Updated Assumptions
- Save via `StockManager.save_assumptions(symbol, assumptions, manual_overrides=overrides)`
- **Interactive mode:** Track `_manual_overrides` throughout:
  - Start with the loaded list from `StockManager.load_manual_overrides(symbol)`
  - User chooses "recommended" → remove field from list
  - User chooses "custom" (types a specific value) → add field to list
  - User chooses "current" (keep existing) → no change to list
  - Note: coherence check adjustments accepted by the user are NOT manual overrides (they're corrections)
  - Pass the final list to `save_assumptions()`
- **Auto mode:** Pass through the loaded `_manual_overrides` unchanged to `save_assumptions()`. Coherence check self-corrections do not affect the manual overrides list — they only adjust non-manual fields.
- Display a before/after comparison table (including any coherence check adjustments)
- Run a quick fair value calculation to show the impact of changes

### Important Notes
- **Interactive mode:** Use `AskUserQuestion` for core assumptions and the group prompts for mechanical/market
- Present the recommended value as the first option
- Always show the math/data behind core assumption recommendations
- If no cached financial data is available, note which recommendations are less reliable
