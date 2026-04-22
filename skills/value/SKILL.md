---
name: value
description: Quantitative metrics and DCF valuation for a stock
---

Perform quantitative analysis and DCF valuation for ticker symbol **$ARGUMENTS**.

## Python Environment
When running Python code, set `PYTHONPATH` so `stock_analyzer` is importable:
```
PYTHONPATH="${CLAUDE_PLUGIN_ROOT:-.}" python3 -c "from stock_analyzer import ..."
```

## Canonical Run (reference)

Minimal, copy-pasteable call chain that bypasses the three common pitfalls (staticmethod on `FinancialMetrics`, `dcf_inputs` vs raw cached shape, zero-arg `get_summary()`):

```python
from stock_analyzer import StockManager, FinancialMetrics, DCFModel

manager = StockManager()
cached = manager.load_financial_data("$ARGUMENTS")          # raw cached JSON payload
assumptions, _ = manager.get_or_create_assumptions("$ARGUMENTS")

dcf_inputs = FinancialMetrics.calculate_dcf_inputs(         # staticmethod, NO instance
    income_statement=cached["data"]["income_statement_annual"]["reports"],
    balance_sheet=cached["data"]["balance_sheet"]["reports"],
    cash_flow=cached["data"]["cash_flow"]["reports"],
    overview=cached["data"]["overview"],
    income_annual=cached["data"]["income_statement_annual"]["reports"],  # enables R&D-adjusted metrics
)

shares = float(cached["data"]["overview"]["SharesOutstanding"])
price  = float(cached["data"]["quote"]["Global Quote"]["05. price"])

model = DCFModel(assumptions)
model.calculate_fair_value(dcf_inputs, shares, price, verbose=True)  # dcf_inputs, NOT cached
print(model.get_summary())                                           # zero args
implied = model.reverse_dcf(dcf_inputs, shares, price)               # also dcf_inputs
```

**Gotchas:**
- `FinancialMetrics.calculate_dcf_inputs(...)` is a staticmethod. The class has no useful instance — do NOT write `FinancialMetrics(data).calculate_dcf_inputs(...)`.
- `DCFModel.calculate_fair_value` and `DCFModel.reverse_dcf` both take the **`dcf_inputs` dict**, not the raw cached JSON. Passing raw cached data raises `ValueError: dcf_inputs missing required fields: revenue, operating_income, market_cap`.
- `DCFModel.get_summary()` takes **zero args** — it reads from `self.results` set by the prior `calculate_fair_value()` call.
- Credit-spread lookup is `stock_analyzer.metrics.get_spread_for_rating(rating)` → `Optional[float]`; there is no `stock_analyzer.credit_spreads` module. Returns `None` for unknown ratings (including compound strings like `"Aaa/AAA"` — split to `"Aaa"` or `"AAA"` first), so guard before arithmetic or `rf + spread` raises `TypeError: unsupported operand type(s) for +: 'float' and 'NoneType'`.

**Return shapes (all return dicts — don't treat as scalars, don't `.get()` with a guessed default):**
- `DCFModel.calculate_fair_value(...)` → dict (also assigned to `model.results`). **Trap:** the per-share key is `fair_value`, **NOT** `fair_value_per_share` — `.get('fair_value_per_share', 0)` silently returns 0. `fcf_projections` and `margin_projections` are verbose-only (also `beta`, `debt_to_equity`, `shares_outstanding`, cash/debt fields). Read `model.results.keys()` after the call for the full shape.
- `DCFModel.reverse_dcf(...)` → dict `{implied_value, fair_value, wacc}`, or `None` if no solution. `implied_value` is the solved growth rate as decimal (e.g. 0.2064 for 20.64%). Use `result['implied_value']`, not `result` — `result * 100` raises `TypeError: dict and int`.
- `damodaran_betas.compute_bottom_up_beta(...)` → dict `{levered_beta, unlevered_beta, industry, market_de, tax_rate, n_firms}`. Use `result['levered_beta']`, not `result` — formatting the dict raises `TypeError: unsupported format string passed to dict.__format__`.
- `DCFModel.value_decomposition()` → dict `{assets_in_place, growth_value, growth_percent}`.

## Steps:

### 1. Initialize and Load Data
- Initialize `StockManager` to manage stock-specific folder
- Load or create DCF assumptions for **$ARGUMENTS** using `StockManager.get_or_create_assumptions()`
- Load `_manual_overrides` via `StockManager.load_manual_overrides(symbol)`
- Display assumption provenance:
  - **If `was_loaded` is True:** "Using calibrated assumptions" + show which are manual overrides (e.g., "2 manual overrides: revenue_growth_rate, sales_to_capital_ratio")
  - **If `was_loaded` is False:** "Using default assumptions — consider running /calibrate first"
- Display the loaded assumptions summary
- When calling `FinancialMetrics.calculate_dcf_inputs()`, pass `income_annual=` with the annual income statement reports from cached data (`cached['data']['income_statement_annual']['reports']`). This enables R&D capitalization for adjusted ROIC.
- Try `StockManager.load_financial_data("$ARGUMENTS")` to check for cached data
- **If cached data exists:** Use it (display "Using cached data from {fetched_at}")
- **If no cached data:** Invoke `/fetch $ARGUMENTS` first, then load the cached data
- Load the most recent `research_*.md` file in `data/<SYMBOL>/` if it exists — used for confidence-adjusted assessment (step 4) and key risk context (step 5). If not found, note: "No research context available."

### 2. Display Key Metrics
- Parse and display the financial metrics in a formatted table
- Use `stock_analyzer.metrics.FinancialMetrics` to parse and format the data
- Show:
  - Valuation metrics (P/E, PEG, P/B, etc.)
  - Profitability metrics (margins, ROIC, ROE, ROA). When R&D capitalization data is available (`dcf_inputs['adjusted_operating_margin']` is not None), display raw and adjusted symmetrically as reference anchors — neither is primary:
    ```
    Operating Margin:
      Raw (GAAP, R&D expensed):      X.X%
      Adjusted (R&D capitalized):    Y.Y%   [N-year amortization]
    Sales-to-Capital:
      Raw:                           X.Xx
      Adjusted:                      Y.Yx
    ROIC:
      Raw (GAAP):                    X.X%
      Adjusted (R&D capitalized):    Y.Y%
    Research Asset: $XXB | R&D/Revenue: X.X%
    ```
    Raw is the GAAP accounting view; adjusted treats R&D as amortized capital to show the economic view. Neither is "the" metric — they are two reference anchors for the user's judgment. The DCF below runs on whichever basis the user explicitly picked in `/calibrate`, or raw GAAP when uncalibrated.
    - **Sources** — pull every value above from `dcf_inputs` (annual income statement basis), NOT from `metrics.operating_margin` (which is Alpha Vantage's TTM figure and can drift from the annual-derived number the DCF actually uses):
      - Raw Operating Margin: `dcf_inputs['operating_income'] / dcf_inputs['revenue']`
      - Raw S/C: `dcf_inputs['revenue'] / dcf_inputs['invested_capital']`
      - Raw ROIC: `dcf_inputs['roic']`
      - Adjusted Operating Margin: `dcf_inputs['adjusted_operating_margin']`
      - Adjusted S/C: `dcf_inputs['adjusted_sales_to_capital']`
      - Adjusted ROIC: `dcf_inputs['adjusted_roic']`
      - Research Asset: `dcf_inputs['research_asset']`; R&D/Revenue = `dcf_inputs['current_rd'] / dcf_inputs['revenue']`; N = `dcf_inputs['rd_amortizable_life']`
    - Leave `metrics.roic` at its default (`dcf_inputs['roic']`, raw) — no override. Raw and adjusted ROIC appear as separate rows above.
    - If no R&D data (`dcf_inputs['adjusted_operating_margin']` is None): display single-row Operating Margin / ROIC from `metrics` as before, no raw/adjusted split, no Sales-to-Capital row.
  - Growth rates
  - Financial health indicators
  - Per-share metrics
  - **FCF Yield (trailing and forward):**
    - Trailing: FCF per share / current price (e.g., "Trailing FCF Yield: 2.6% ($9.64 FCF/share at $373)")
    - Forward: Use Year 1 projected FCF from the DCF model (calculated later in step 4, but preview here using: Revenue × (1+g) × target margin × (1-tax) - reinvestment). Display as: "Forward FCF Yield: ~2.2% ($61B projected FCF / $2.78T market cap)"
    - If forward yield is significantly lower than trailing (>30% lower), note: "Forward FCF yield is X% vs trailing Y% — CapEx growth compresses near-term cash flow."
  - **Quarterly Revenue Growth Analysis** (last 8 quarters):
    - Display table with: Quarter, Revenue, QoQ Growth %, YoY Growth %
    - Calculate QoQ (Quarter-over-Quarter): Compare to previous quarter
    - Calculate YoY (Year-over-Year): Compare to same quarter last year
    - Highlight growth trends and acceleration/deceleration

### 3. Reverse DCF Context
- Run `DCFModel.reverse_dcf(dcf_inputs, shares_outstanding, current_price)` to get market-implied revenue growth rate
- Display: "Market-implied revenue growth: ~X% (at $XXX, holding constant: margin Y%, S/C Z, WACC W%, terminal ROIC T%)"
- Show which assumptions are held constant — the implied growth changes if you change margin, S/C, or terminal ROIC
- This gives context for interpreting the DCF result — if your fair value differs from current price, the user can see exactly which growth assumption drives the gap

### 4. Perform DCF Valuation
- Use `stock_analyzer.dcf.DCFModel` with the loaded assumptions
- Import `FinancialMetrics` from `stock_analyzer.metrics`
- Use `FinancialMetrics.calculate_dcf_inputs()` to prepare the data
- **IMPORTANT**: Call `calculate_fair_value()` with `verbose=True` to ensure detailed projections are included
- Display the full DCF summary using `get_summary()`:
  - All DCF assumptions used (growth rate, terminal growth, WACC, operating margin, target margin if set)
  - Year-by-year FCF projections showing: Year, Phase, Growth Rate, Margin (if converging), Revenue, NOPAT, Reinvestment, FCF, PV Factor, and PV of FCF
  - **If target margin < current margin** (margins converging downward), call this out explicitly: "Note: margins converge downward from current X% to target Y%, reflecting [reason from research, e.g., expected depreciation headwind]." Downward convergence is unusual and easy to miss in the projection table.
  - Terminal value calculation breakdown
  - Valuation summary: PV of FCFs, PV of terminal value, enterprise value, equity bridge (cash, investments, debt), equity value
  - Fair value per share vs current price with upside/downside percentage
  - Sensitivity analysis table (growth rate vs operating margin)
  - Valuation assessment — factor in research confidence if research was loaded in step 1:
    - Extract the **Confidence** level (High/Medium/Low) from the research
    - Adjust the assessment language based on confidence:
      - **High confidence:** Use standard bands (>20% Significantly Undervalued, >10% Undervalued, ±10% Fairly Valued, >10% downside Overvalued, >20% downside Significantly Overvalued)
      - **Medium confidence:** Tighten one level (>20% becomes Undervalued not Significantly Undervalued, >10% becomes Fairly Valued not Undervalued)
      - **Low confidence:** Tighten two levels and add caveat: "Low confidence — assumptions are highly uncertain"
    - If no research available, use standard bands with a note: "No research context — assessment based on DCF only"
    - **Near-zero upside (±2%):** When upside is within ±2%, add: "Your assumptions produce no margin of safety." If manual overrides exist, add: "The investment case rests on [list manual overrides] — if these don't pan out, there's no cushion." If no manual overrides, add: "The stock is priced to your assumptions — no edge at this price."

### 5. Sanity Check
After the DCF calculation, verify the output is reasonable:
- **Value decomposition:** Call `model.value_decomposition()` and display:
  ```
  Value decomposition: X% assets in place ($XXB), Y% growth ($XXB)
  ```
  - If growth is >80% of EV: "Most of the value comes from growth — every growth and reinvestment assumption is load-bearing."
  - If growth value is negative: "Growth destroys value at these assumptions (ROIC < WACC) — the company would be worth more with zero growth."
- **Implied revenue scale:** Display: "Your assumptions imply $XXXB revenue by year 10 (up from $XXXB today, a X.Xx increase). Consider whether this is plausible relative to the total addressable market." Use `final_year_revenue` and `base_revenue` from the DCF results. If the increase is >5x, add: "A X.Xx increase requires $XXXB in cumulative new revenue — verify the TAM supports this."
- **Terminal value concentration:** If PV of terminal value is >85% of enterprise value, flag: "Warning: terminal value represents X% of enterprise value — the valuation depends almost entirely on post-year-10 assumptions." This is common for growth companies but the user should know.
- **Implausible fair value:** If fair value is negative or >5x current price, flag: "Warning: fair value of $X appears implausible — check input assumptions." Do not stop, but display prominently.
- **Negative FCF in early years:** If projected FCF is negative in years 1-3, note: "Projected FCF is negative in early years due to high reinvestment — valuation depends on later-year cash flows." This is expected for high-growth, capital-heavy companies.

### 6. Key Risk from Sensitivity
After generating the DCF summary, identify which assumption has the highest impact on fair value from the sensitivity table. Display a one-line callout:
- "Key valuation risk: operating margin is the most sensitive assumption — fair value ranges from $XXX to $XXX across the sensitivity grid. If [specific downside scenario from research Key Risks, if available], fair value could fall to $XXX."
- If research is available, connect the highest-impact assumption to the most relevant Key Risk. If not, just flag the sensitivity.

### 7. Save Valuation Output
- Save the valuation to `data/<SYMBOL>/valuation_YYYY-MM-DD.md`
- Use `StockManager.save_analysis(symbol, content, filename="valuation_YYYY-MM-DD.md")` with today's date
- The saved file should include: metrics table (step 2), reverse DCF context (step 3), full DCF summary (step 4), sanity check warnings (step 5), and key risk callout (step 6)

### 8. Display Summary
Show a concise summary:
- Fair value as a range using the sensitivity table bounds: "Fair value: $386 (range: $304-$488)"
- Market-implied growth from step 3 vs your assumed growth: "Market implies 13.3%, you assume 16%"
- Current price vs base fair value with upside/downside percentage
- Confidence-adjusted assessment from step 4
- Key assumptions (growth rate, target margin, S/C ratio, WACC)
- Location of saved valuation file

## Important Notes:
- Import from `stock_analyzer`: `DCFModel`, `DCFAssumptions`, `FinancialMetrics`, `StockManager`
- If a metric can't be calculated (missing data), show "N/A" with a brief reason — don't skip the row silently
- Always use `verbose=True` for `calculate_fair_value()` to get year-by-year projections
