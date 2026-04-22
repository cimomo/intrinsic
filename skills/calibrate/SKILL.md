---
name: calibrate
description: Review and update DCF assumptions for a stock
---

Review and update DCF assumptions for **$ARGUMENTS**.

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

## Assumption Categories

Assumptions are split into three tiers based on how much attention they need:

**WACC inputs** — derive first so WACC is known before judgment calls.

*Mechanical (auto-derived from data):*
- Beta (bottom-up: Damodaran industry unlevered beta + company D/E + marginal tax rate; falls back to AV regression on user choice)
- Cost of Debt (from credit rating + Damodaran default spread)
- Tax Rate: marginal (21% default) + effective (from income statement; transitions to marginal over projection period)

*Market/fixed (rarely change):*
- Risk-Free Rate (10-year Treasury, default 4.5%)
- Market Risk Premium (standard 5%)
- Terminal Growth Rate (defaults to risk-free rate)
- Projection Years (default 10)

**After WACC is computed** — the user can override it with a manual hurdle rate (cost_of_capital).

**Core assumptions** — company-specific, change with new data, worth deliberating. Research context matters here.
- Revenue Growth Rate (Years 1-5)
- Operating Margin / Target Operating Margin
- Sales-to-Capital Ratio
- Terminal ROIC (how much competitive advantage persists in perpetuity — compared against WACC)

## Steps:

### 1. Load Current Assumptions and Financial Data
- Initialize `StockManager` and load existing assumptions for **$ARGUMENTS**
- Load `_manual_overrides` via `StockManager.load_manual_overrides(symbol)`
- Load cached financial data via `StockManager.load_financial_data()` if available
- When calling `FinancialMetrics.calculate_dcf_inputs()`, pass `income_annual=` with the annual income statement reports from cached data (`cached['data']['income_statement_annual']['reports']`). This enables R&D capitalization for adjusted ROIC.
- Display the current assumptions file contents

### 1b. Load Research Context (if available)
- Look for the most recent `research_*.md` file in `data/<SYMBOL>/`
- **If found:** Read it and note its date. If older than 30 days, display a warning: "Using research from {date} — consider re-running /research first"
- **If not found:** Note that no research is available. Proceed with data-only calibration and display: "No research file found — recommendations based on financial data only"

### 2. WACC Inputs — Mechanical Assumptions (auto-derive from data)

Derive these from the financial data first, so WACC is established before any judgment calls.

- **Beta:** Always compute bottom-up from Damodaran's industry table and re-ask the user. A stored `beta` in `_manual_overrides` is displayed as context, not a bypass — drift from D/E changes, tax rate changes, or a refreshed industry table surfaces every run.

  1. Read the regression beta from `dcf_inputs['beta']` (Alpha Vantage 5y monthly), the AV industry from `cached["data"]["overview"]["Industry"]`, and compute market D/E = `total_debt / market_cap` (both in `dcf_inputs`).
  2. **Market cap fallback:** If `market_cap` is 0 or missing, skip bottom-up this run. If `beta` is already in `_manual_overrides`, leave `assumptions.beta` and `_manual_overrides` unchanged (honor the prior choice) and warn: "Market cap unavailable — bottom-up disabled this run. Keeping stored beta X.XX." Otherwise, set `assumptions.beta = av_beta` without adding to `_manual_overrides` (transient data gap, not a deliberate choice) and warn: "Market cap unavailable — falling back to AV regression beta X.XX. Re-run /fetch to enable bottom-up beta." Proceed to the next assumption.
  3. **Pick Damodaran industry** (one of):
     - If `assumptions.damodaran_industry` is set and still exists in `damodaran_betas.DAMODARAN_BETAS` → use it.
     - If the stored industry is no longer in the table (Damodaran renamed it) → warn "Stored industry '<X>' not found in current table — please re-pick" and go to the sector-then-industry picker (step 7).
     - Else call `damodaran_betas.suggest_industry(av_industry)` → if non-None, use the suggestion.
     - Else (AV industry missing or no match) → warn "no auto-match for AV industry '<X>' — please pick from list" and go to the sector-then-industry picker (step 7).
  4. Compute `bottom_up = damodaran_betas.compute_bottom_up_beta(industry, market_de, marginal_tax_rate=assumptions.tax_rate)`. Use `assumptions.tax_rate` (not a hardcoded 0.21) so non-US or user-overridden tax rates apply.
  5. **Display block.** If `damodaran_betas.DAMODARAN_BETAS_DATE` is older than 14 months, prepend a staleness banner: "Damodaran industry betas are from <DATE>, may be stale — consider checking pages.stern.nyu.edu/~adamodar/pc/datasets/betas.xls". Show the `Stored` row only when `beta` is in `_manual_overrides`; show the `Regression (AV)` row only when `av_beta` is not None (AV occasionally omits regression beta for thinly traded stocks). Otherwise omit those rows:
     ```
     Beta:
       Stored:          X.XX   [manual override set previously]
       Regression (AV): R.RR
       Bottom-up:       Y.YY
         = unlevered_β U.UU (<INDUSTRY>, cash-corrected, N firms)
         × (1 + (1 - T.TT) × D/E D.DD)   [T.TT = assumptions.tax_rate]

       Recommendation: Y.YY (bottom-up)
         Why: regression betas have ±0.25 standard error; bottom-up
         averages across N industry peers and removes cash/leverage noise.
     ```
  6. **Ask** via `AskUserQuestion`. Build the option list from the items below; include each only when its condition holds. `AskUserQuestion` handles numbering, so list the conditional options without fixed labels.
     - **Use bottom-up Y.YY (recommended)** — always offered. Persistence: `assumptions.beta = bottom_up`, `assumptions.damodaran_industry = industry`. Add `damodaran_industry` to `_manual_overrides`; **remove `beta` from `_manual_overrides`** if present (so calibrate recomputes next run from current D/E).
     - **Keep stored X.XX** — offered only when `beta` is in `_manual_overrides`. Persistence: no change to `assumptions.beta`, `damodaran_industry`, or `_manual_overrides`.
     - **Use regression R.RR (Alpha Vantage)** — offered only when `av_beta` is not None. Persistence: `assumptions.beta = av_beta`. Add `beta` to `_manual_overrides`; clear `damodaran_industry` from the assumption and from `_manual_overrides`.
     - **Pick a different Damodaran industry** — always offered. Go to the sector-then-industry picker (step 7), then apply the same persistence as "Use bottom-up" above with the newly chosen industry.
     - **Custom beta value** — always offered. User enters a number via follow-up. `assumptions.beta = entered_value`. Add `beta` to `_manual_overrides`; clear `damodaran_industry` from the assumption and from `_manual_overrides`.
  7. **Sector-then-industry picker:** Two `AskUserQuestion` calls. First, pick sector from `damodaran_betas.DAMODARAN_SECTORS.keys()`. Second, pick industry from `DAMODARAN_SECTORS[chosen_sector]`. Recompute `compute_bottom_up_beta` with the new industry and apply "Use bottom-up" persistence from step 6.
- **Cost of Debt:** Derive from credit rating and Damodaran's default spread table.
  1. Read the synthetic rating from `calculate_dcf_inputs()` (fields: `synthetic_rating`, `synthetic_spread`, `interest_coverage`).
  2. **Web search** for the actual credit rating. Rating agencies publish ratings in many places, and older articles rank high — a naive search almost always returns a stale rating, not the latest action. Use a time-targeted query: search `"{company_name} credit rating S&P Moody's {current_year-1} {current_year}"`. If the first search returns a rating but no source explicitly states a date in {current_year-1} or {current_year} when the rating was assigned, affirmed, or changed, do a **verification search**: `"{company_name} credit rating affirmed upgraded downgraded {current_year}"` to discover the actual current rating. Extract the rating if clearly stated with a recent date (e.g., "Aaa", "AA+").
  3. **If actual rating found:** Use `get_spread_for_rating(rating)` to get the spread. Compute cost of debt = risk-free rate + spread. Display:
     ```
     Cost of debt: X.X% (Rating — Agency, spread X.XX%)
       Synthetic cross-check: Rating (coverage X.Xx) — consistent/diverges
     ```
     If synthetic and actual diverge (different rating bucket), add: "Note: actual rating considers factors beyond interest coverage"
  4. **If no actual rating found:** Use synthetic. Display:
     ```
     Cost of debt: X.X% (synthetic Rating, coverage X.Xx, spread X.XX%)
       No agency rating found — using synthetic
     ```
  5. Set `cost_of_debt` in assumptions to the computed value. **Skip this step if `cost_of_debt` is in `_manual_overrides`** — the override handler below sets the final value based on the user's choice.
  6. **Sanity check:** After setting `cost_of_debt` (whether derived or user-chosen override), validate against `risk_free_rate`:
     - If `cost_of_debt < risk_free_rate`: warn "Cost of debt (X.X%) is below risk-free rate (Y.Y%) — economically implausible for any corporate debt. Likely cause: stored as after-tax or legacy value. Re-run calibrate or use the override handler's `[1] Use derived` to fix."
     - If `cost_of_debt > 15%`: warn "Cost of debt (X.X%) is unusually high — verify the credit rating and spread."
     - This check applies to both freshly computed and loaded values, including manual overrides. The warning does not auto-recompute; the user drives any change.
  - **Manual override:** If `cost_of_debt` is in `_manual_overrides`, still run steps 1-4 (compute the derived value) and display both:
    ```
    Cost of debt:
      Stored:  X.X%   [manual override set previously]
      Derived: Y.Y%   (Rating — Agency, spread X.XX%)
    ```
    Use `AskUserQuestion`:
    - `[1] Use derived Y.Y% (recommended)` → `assumptions.cost_of_debt = derived`; remove `cost_of_debt` from `_manual_overrides`.
    - `[2] Keep stored X.X%` → no change. If the stored value fails the sanity check (< risk_free_rate), note: "Your override (X.X%) is below the risk-free rate — kept anyway, but flagged as economically implausible. Pick `[1] Use derived` to replace it."
    - `[3] Custom value` → user enters; `assumptions.cost_of_debt = entered_value`. Keep `cost_of_debt` in `_manual_overrides`.
- **Tax Rate (marginal):** Default 21% for US companies. Only change if the company is domiciled in a different tax jurisdiction. Display: "Tax rate (marginal): 21%"
- **Effective Tax Rate:** Calculate from income statement: tax expense / pre-tax income. Set as `effective_tax_rate` in assumptions. The DCF model transitions from this rate in year 1 to the marginal rate by year 10. Terminal value always uses marginal. Display: "Effective tax rate: X.X% (from income statement) → transitions to 21% marginal"
  - If effective rate is within 2% of marginal, skip the transition — set `effective_tax_rate` to None and note: "Effective rate (X.X%) is close to marginal (21%) — no transition needed"
  - If effective rate is 0% or negative (NOLs, tax credits), set it and note: "Effective rate near 0% — company has tax shield from NOLs. Early-year NOPAT will be higher, transitioning to marginal by year 10"

Beta and cost of debt have already been resolved via the inline flows above. For the remaining mechanical fields (marginal tax rate, effective tax rate), ask once: "Tax settings correct? [Enter to accept, or specify changes]" — only drill into specifics if the user requests a change.

### 3. WACC Inputs — Market Data (refresh from Damodaran)

Fetches implied ERP and T-bond rate from Damodaran's homepage, caches them in `data/_market.json`, and writes the user's chosen values into the stock's assumptions.

#### 3a. Load and check the market file

1. Call `StockManager.load_market_data()` to read `data/_market.json`
2. Call `StockManager.is_market_data_stale(data, threshold_days=30)` to check freshness
3. **If stale** (missing file, no `fetched_at`, malformed date, or >30 days old): invoke the WebFetch tool with the following prompt on `https://pages.stern.nyu.edu/~adamodar/New_Home_Page/home.htm`:

   > Extract from Damodaran's homepage: (1) the current T-bond rate used as risk-free, (2) the five implied ERP measures (trailing 12mo adjusted payout, trailing 12mo cash yield, net cash yield, normalized earnings & payout, avg CF yield last 10y). Return as JSON matching this schema: `{"risk_free_rate": <decimal>, "measures": {"trailing_12mo_adjusted_payout": <decimal>, "trailing_12mo_cash_yield": <decimal>, "net_cash_yield": <decimal>, "normalized_earnings_payout": <decimal>, "avg_cf_yield_10y": <decimal>}}`. All values as decimals (e.g., 4.67% → 0.0467). If any value is missing or not found, return `null` for that field.

4. **Parse and validate** the WebFetch response:
   - Must be parseable as JSON
   - Must have `risk_free_rate` (float, 0.0 to 0.10)
   - Must have all 5 measures (each float, 0.01 to 0.15)
   - If any validation fails: treat as fetch failure (go to step 3b "fetch failure fallback")

5. **On successful fetch**, construct the market data dict and save it:

   ```python
   from datetime import date
   market_data = {
       "fetched_at": date.today().isoformat(),
       "source": "damodaran.com homepage",
       "source_url": "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/home.htm",
       "risk_free_rate": <parsed_rf>,
       "implied_erp": {
           "default_measure": "trailing_12mo_adjusted_payout",
           "measures": {
               "trailing_12mo_adjusted_payout": <parsed_value>,
               "trailing_12mo_cash_yield": <parsed_value>,
               "net_cash_yield": <parsed_value>,
               "normalized_earnings_payout": <parsed_value>,
               "avg_cf_yield_10y": <parsed_value>,
           }
       }
   }
   manager.save_market_data(market_data)
   ```

6. **If fresh**: use the cached market data directly without fetching.

**Fetch failure fallback:** If WebFetch errors out, returns unparseable content, or returns values outside plausibility bounds, display a loud warning:

```
⚠ Unable to refresh market data from Damodaran ({reason}).
  Using stored values from {ticker} (may be stale): ERP {stored_erp}%, Rf {stored_rf}%.
```

Skip steps 3b and 3c entirely. Use the stock's existing `market_risk_premium` and `risk_free_rate` as-is, leave `_manual_overrides` unchanged, and proceed to Section 4 (compute WACC).

#### 3b. Display the market data

Show the current Damodaran values and the stock's current stored values:

```
Market data (from Damodaran, fetched YYYY-MM-DD, N days ago):
  Risk-free rate (10y Treasury):    X.XX%

  Implied ERP — 5 measures:
  [1] Trailing 12mo adjusted payout: X.XX%  ← default
  [2] Trailing 12mo cash yield:      X.XX%
  [3] Net cash yield:                X.XX%
  [4] Normalized earnings & payout:  X.XX%
  [5] Avg CF yield last 10y:         X.XX%

  {TICKER} currently uses: Rf X.XX%, ERP X.XX% ({match_description})
```

Compute `{match_description}` by matching the stock's stored `market_risk_premium` against the market file's measures:
- If it matches `default_measure` exactly → "matches default measure"
- If it matches another measure → "matches measure [N] {measure_label}"
- If it doesn't match any measure → "(manual override — does not match current Damodaran measures)"

Also compute `{N days ago}` from `date.today() - date.fromisoformat(market_data['fetched_at'])`.

#### 3c. User interaction

Branch selection is based on whether the stock's stored `market_risk_premium` equals the current default measure value (trailing 12mo adjusted payout). This is a direct value comparison — `_manual_overrides` status is not consulted for branch selection.

**If stored ERP == current default measure value:**

Use `AskUserQuestion` with this prompt:
> `Accept default (trailing adj payout X.XX%, Rf X.XX%)? Options: [1] Accept default, [2] Pick different ERP measure, [3] Custom ERP value, [4] Keep stored (no change)`

**If stored ERP != current default measure value** (either a non-default menu choice or a custom override):

> `Stock currently uses ERP X.XX% ({match_description} — computed in step 3b). Options: [1] Keep stored, [2] Accept default (trailing adj payout X.XX%), [3] Pick different ERP measure, [4] Custom ERP value`

The `{match_description}` here is the same label computed in step 3b — either "matches measure [N] {measure_label}" when the stored value equals a non-default Damodaran measure, or "manual override — does not match current Damodaran measures" when it doesn't match any. Reusing the match description keeps the user-facing text precise about whether their historical choice still corresponds to a Damodaran-published measure.

If user picks "different ERP measure", show a follow-up prompt:
> `Select ERP measure: [1] Trailing 12mo adjusted payout X.XX%, [2] Trailing 12mo cash yield X.XX%, [3] Net cash yield X.XX%, [4] Normalized earnings & payout X.XX%, [5] Avg CF yield last 10y X.XX%`

If user picks "custom", ask:
> `Enter custom ERP value (as decimal, e.g., 0.05 for 5%):`

Apply the result:

| User choice | `market_risk_premium` | `_manual_overrides` for `market_risk_premium` |
|---|---|---|
| Accept default (trailing adj payout) | Set to default measure value | **Remove** if present |
| Pick different menu measure | Set to that measure's value | **Add** if not present |
| Custom value | Set to entered value | **Add** if not present |
| Keep stored | No change | No change |

**Risk-free rate:** Damodaran publishes only one T-bond rate, so this is a 3-choice prompt rather than a 5-measure menu:
> `Risk-free rate: [1] Accept current market value X.XX% (from Damodaran), [2] Custom value, [3] Keep stored X.XX% (no change)`

Apply the result:

| User choice | `risk_free_rate` | `_manual_overrides` for `risk_free_rate` |
|---|---|---|
| Accept market value | Set to fetched value | **Remove** if present |
| Custom value | Set to entered value | **Add** if not present |
| Keep stored | No change | No change |

#### 3d. Show other market-derived values

Terminal growth rate and projection years are not Damodaran-sourced — they remain as before:

```
Terminal growth rate: X.X% (= risk-free rate)
Projection years:     10
```

If the user updates `risk_free_rate`, explicitly set `assumptions.terminal_growth_rate = assumptions.risk_free_rate` at skill runtime. This is a skill-level responsibility: `DCFAssumptions.__post_init__` only sets the default at construction time and does not re-run on field updates, so calibrate must propagate Rf changes into `terminal_growth_rate` itself.

---

**Note:** Refreshing market data via WebFetch requires network access. If running offline or if Damodaran's page is unreachable, calibrate falls back to the stock's stored values with a visible warning (see "Fetch failure fallback" in step 3a).

### 4. Compute and Display WACC

After mechanical and market/fixed assumptions are set, compute and display WACC. This anchors everything that follows.

```
WACC: X.X%
  Cost of equity: X.X% (CAPM: Rf X.X% + β X.XX × ERP X.X%)
  Cost of debt (after tax): X.X%
  Weights: XX% equity / XX% debt
```

**Hurdle rate override:** The hurdle rate is one of the most impactful inputs in the model — overriding computed WACC can swing fair value by $50+/share. This MUST be an `AskUserQuestion`, not a skippable prose prompt.

**If a cost_of_capital override is already set**, use `AskUserQuestion` with:
- Keep current override (X.X%)
- Use computed WACC (Y.Y%)
- Custom

**If no override is set**, use `AskUserQuestion` with:
- Keep computed WACC (X.X%)
- Round to nearest integer (X%)
- Custom

Store the answer to `assumptions.cost_of_capital`. If the user picks computed WACC, set `cost_of_capital` to `None` (use WACC components) and remove from `_manual_overrides`. If the user picks a rounded value, custom value, or keeps an override, add to `_manual_overrides`.

If a hurdle rate is set (existing or new), display:
```
Cost of Capital: X.X% (manual hurdle rate — WACC computation bypassed)
```

### 5. Reverse DCF — What Does the Market Imply?

Before setting core assumptions, calculate what revenue growth rate the current stock price implies. This gives calibrate a crucial anchor.

Use `DCFModel.reverse_dcf(dcf_inputs, shares_outstanding, current_price)` to solve for the revenue growth rate that produces fair value = current price. This uses binary search internally — no manual loops needed.

Display:
```
Market-implied revenue growth: ~X%
  (At current price of $XXX, holding constant: margin X.X%, S/C X.Xx,
   WACC X.X%, terminal ROIC X.X%)
  Your data-driven estimate will be compared against this.
```

**Terminal ROIC sensitivity:** The implied growth rate changes significantly with terminal ROIC — for wide-moat companies, the gap between terminal ROIC = WACC (default) and terminal ROIC = WACC + 5% can swing the implied growth by 5+ percentage points. Label which terminal ROIC is being used so the user knows what the number means.

This is context, not a recommendation. It tells you: "the market is pricing in X% growth — if your assumption differs, you should know why."

### 6. Core Assumptions (detailed review)

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
6. Ask the user what value to use (current, recommended, or custom)

Go through these in order:

**a. Revenue Growth Rate (Years 1-5)**
- Look at: recent YoY quarterly revenue growth trends, annual revenue growth, analyst estimates
- Consider: is growth accelerating or decelerating? Is the current assumption realistic?
- If the user picks a value significantly above the market-implied rate from the reverse DCF, challenge constructively: "That's X% above what the market prices in. What specifically do you see that the market doesn't?" This isn't to block them — it's to ensure the choice is deliberate.

**b. Operating Margin — Starting and Target**

This assumption uses a custom two-question flow in place of the standard six-step protocol defined at the top of Section 6.

**Display anchors before asking any questions.** Read the data once and show:

```
Current operating margin:
  Raw (GAAP, R&D expensed):       X.X%
  Adjusted (R&D capitalized):     Y.Y%   [N-year amortization]
  5-year raw range:               A.A% – B.B%   [trend: expanding / stable / compressing]
```

Omit the "Adjusted" row when `dcf_inputs['adjusted_operating_margin']` is `None` (zero-R&D companies). Use `dcf_inputs['rd_amortizable_life']` for the N-year note. The raw historical range comes from the 5-year annual income statement; if Alpha Vantage coverage is short, state how many years you have.

**Explain what the user is seeing:** Raw is what Alpha Vantage reports from GAAP financials (R&D expensed as an operating expense). Adjusted is what the business would show if R&D were treated as capital expenditure — amortized over N years rather than expensed in the year incurred. The adjusted number is the economic operating margin; the raw number is the accounting number. The anchors are reference points for your picks — pick values that reflect your view of the business, not an algorithmic default.

**If `assumptions.operating_margin` is already set** (e.g., the user is re-running calibrate), note the current saved value before asking Q1: "Current saved value: X.X%".

**Question 1 — Starting operating margin.** Use `AskUserQuestion` with these options:
- Raw X.X%
- Adjusted Y.Y% (omit when `adjusted_operating_margin` is None)
- Custom (user types a value)

Store the answer to `assumptions.operating_margin`. This is the margin the DCF uses for year 1 before any convergence.

**Question 2 — Target operating margin (year 10 for linear convergence).** When rendering these options, label "Same as starting" with the actual value the user picked in Q1 (e.g., "Same as starting — 47.5%") so the user knows what they are confirming. Use `AskUserQuestion` with these options:
- Same as starting — X.X% (flat margin, no convergence — fill X.X% from Q1)
- Expand to Z% (when there's a margin-expansion story — suggest a specific Z based on research, e.g. picked_starting + 2pp)
- Contract to W% (when there's a margin-compression story)
- Custom

When the user picks "same as starting," set `assumptions.target_operating_margin = None` so the DCF's existing "no convergence" path runs. Otherwise store the picked value to `assumptions.target_operating_margin`.

**Research context:** If research is available, factor in the Margin & Profitability → Margin signal when recommending. Example: "Research: Wide moat, durable pricing power — recommending starting at adjusted 47.5% and target 48% (slight expansion consistent with operating leverage)."

**If the user picks values more than 5 percentage points above both raw and adjusted anchors, challenge constructively.** Example: "That's X pp above even the R&D-adjusted economic margin of Y.Y%. What specifically do you see that the numbers don't?"

Consider: is margin expanding or contracting? What's a realistic trajectory over 10 years?

**c. Sales-to-Capital Ratio**

**Display anchors before asking.** Show:

```
Current sales-to-capital:
  Raw (R&D expensed):               X.Xx   (= revenue / IC)
  Adjusted (R&D capitalized):       Y.Yx   (= revenue / (IC + research asset))

  where IC = equity + total_debt - cash - ST investments - LT investments
```

Omit the "Adjusted" row when `dcf_inputs['adjusted_sales_to_capital']` is `None`.

**Historical trend (raw, directional context):** Always calculate 5+ years of historical raw data. Compute both:
- **Raw Average S/C** = Revenue / Invested Capital
- **Raw Incremental S/C** = ΔRevenue / ΔInvested Capital (year-over-year — this is what the DCF model uses during projection years)

**IC formula for all years:** `equity + total_debt - cash - short_term_investments - long_term_investments`. This is the same formula used by `FinancialMetrics.calculate_dcf_inputs()`. Do NOT use a different set of deductions — for companies with large short-term investment balances, omitting ST investments creates a multi-point S/C swing.

Use web sources if Alpha Vantage doesn't have enough history. True multi-year adjusted S/C history is unavailable given the 5-year Alpha Vantage data window and typical amortization lives, so the raw trend table is the best directional signal for whether capital efficiency is improving or deteriorating.

Present the full historical table to the user before asking for a value.

**Explain what the user is seeing:** Raw treats R&D as an operating expense, so invested capital excludes the accumulated research asset. Adjusted treats R&D as capital expenditure, so the research asset is part of invested capital — the denominator is larger, and the ratio is lower. Pick what reflects your view of the business's true capital intensity.

**If `assumptions.sales_to_capital_ratio` is already set** (e.g., the user is re-running calibrate), note the current saved value before asking the question: "Current saved value: X.Xx".

**Question:** Use `AskUserQuestion`. If `dcf_inputs['adjusted_sales_to_capital']` is not None, offer three options:
- Raw S/C (X.Xx)
- Adjusted S/C (Y.Yx)
- Custom (user types a value)

If `dcf_inputs['adjusted_sales_to_capital']` is None, offer two options:
- Raw S/C (X.Xx)
- Custom (user types a value)

Store the answer to `assumptions.sales_to_capital_ratio`.

Consider: is there a regime change (e.g., capital-light → capital-heavy)? Is the historical trend improving or deteriorating? Does the adjusted number represent a more honest picture of what this business needs?

**d. Terminal ROIC (Competitive Advantage Persistence)**

Terminal ROIC determines how much the company must reinvest to sustain terminal growth. It is the single most impactful assumption on terminal value — the difference between ROIC = WACC and ROIC = 20% can swing fair value by 20-40%.

**Anchors — always show these before recommending:**
- **Current ROIC** from `calculate_dcf_inputs()`: use `dcf_inputs['adjusted_roic']` if available (R&D capitalized), else `dcf_inputs['roic']`
- **WACC** from step 4 (the floor — no competitive advantage persists)
- **Implied ROIC from model assumptions:** `operating_margin × sales_to_capital × (1 - tax_rate)`. This is what the DCF's own year-10 numbers imply, and represents the ROIC if current operating efficiency continues.
- **Constraint:** Terminal ROIC must be >= terminal growth rate (otherwise reinvestment > 100%)

**Framework for setting terminal ROIC — use research moat signals:**

The core question: *How much of today's excess returns (ROIC above WACC) will persist in perpetuity?*

| Research signal | Terminal ROIC | Reasoning |
|----------------|---------------|-----------|
| Moat: None | = WACC | Competition fully erodes excess returns |
| Moat: Narrow, Direction: Narrowing | = WACC | Advantages eroding, converge to no-moat |
| Moat: Narrow, Direction: Stable | WACC + 1% | Modest advantage persists but limited |
| Moat: Wide, Direction: Narrowing | WACC + 1% | Strong today but declining toward narrow |
| Moat: Wide, Direction: Stable | WACC + 2% | Durable competitive advantage |
| Moat: Wide, Direction: Widening | WACC + 5% | Truly exceptional, strengthening advantages |

These are fixed spreads above WACC, not interpolations from current ROIC. The spread reflects moat strength independent of the cost of capital — a durable moat earns the same excess return regardless of whether WACC is 8% or 15%. Current ROIC is shown as context but should not anchor perpetuity assumptions.

**Go deeper — reason about the specific source of advantage:**
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
  Current ROIC:          29.1%    ← today's returns (context, not an anchor)
  Implied ROIC (model):  25.3%    ← what your margin + S/C assumptions imply
  Framework:             11.9%    ← WACC + 2% (Wide/Stable)
    Research: Wide moat (Stable) — Azure/M365 ecosystem creates deep switching costs
    and network effects. Enterprise lock-in is multi-year.
    Impact: Terminal ROIC of 11.9% vs WACC-default changes fair value by +$XX
```

**Guard:** Cap terminal ROIC at WACC + 5%. Even the strongest moats erode over decades. If the user picks a custom value above WACC + 5%, note: "Spread above +5% — requires explicit justification for why excess returns of this magnitude persist in perpetuity."

Present the anchors, the framework recommendation, and the specific reasoning. Ask: "framework (X%), WACC default (Y%), or custom?"

### 7. Coherence Check

After all assumptions are set, step back and review them as a whole. This is a reasoning step — no new data or web searches needed.

**ROIC panel — always display at the start of step 7:**

```
ROIC context:
  WACC (floor):                  W.W%
  Raw current ROIC:              X.X%   (GAAP, R&D expensed)
  Adjusted current ROIC:         Y.Y%   (Damodaran, R&D capitalized)   [when available]
  Your implied projection ROIC:  Z.Z%   (= picked margin × picked S/C × after-tax)
  Your terminal ROIC pick:       T.T%   (convergence target for stable growth)
```

Omit the "Adjusted current ROIC" row when `dcf_inputs['adjusted_roic']` is `None` (zero-R&D companies). The implied projection ROIC is derived from the user's own picks:

```python
implied_projection_ROIC = (
    assumptions.operating_margin           # the starting-margin pick from step 6b
    * assumptions.sales_to_capital_ratio   # pick from step 6c
    * (1 - assumptions.tax_rate)           # marginal rate from DCFAssumptions
)
```

Use the **starting margin** (year 0) and the DCF's **marginal** `tax_rate` — this is a going-forward steady-state anchor, not a year-specific value. Even when the user has set `effective_tax_rate`, the panel uses marginal so the number is comparable to the terminal ROIC pick.

**Cross-assumption consistency:** Do the assumptions make sense together?
- **Value of growth:** Compare implied projection ROIC to WACC. If implied ROIC < WACC, growth destroys value — higher growth makes the stock *less* valuable. Flag prominently: "Your picks imply ROIC of Z.Z% vs WACC of W.W% — at these returns, growth destroys value. Either margin/S/C must improve (higher ROIC) or the growth assumption is working against you."
- **Fundamental growth check:** This check asks "given the firm's current cash generation, can it fund the assumed growth by reinvesting?" Unlike the value-of-growth check (which uses user-implied projection ROIC because it tests the *forward* economics), this check uses *historical* NOPAT and ROIC from `dcf_inputs` — the two anchors must come from different sources or the formula collapses to an identity. Compute:
  ```
  # Historical NOPAT — anchored on the firm's actual current profit,
  # not derived from the user's forward-looking margin/S/C picks.
  if dcf_inputs['adjusted_roic'] is not None:
      current_nopat = dcf_inputs['adjusted_roic'] * dcf_inputs['adjusted_invested_capital']
      current_roic  = dcf_inputs['adjusted_roic']
  else:
      current_nopat = dcf_inputs['roic'] * dcf_inputs['invested_capital']
      current_roic  = dcf_inputs['roic']

  reinvestment       = dcf_inputs['revenue'] * growth_rate / assumptions.sales_to_capital_ratio
  reinvestment_rate  = reinvestment / current_nopat
  fundamental_growth = reinvestment_rate * current_roic
  ```
  Compare `fundamental_growth` to the assumed revenue growth rate. If the assumed growth exceeds fundamental growth by more than 2 percentage points, flag: "Assumed growth (X%) exceeds what current cash generation supports (Y%) by more than 2 pp. Achieving X% requires improving capital efficiency (higher S/C) or reinvesting a larger share of NOPAT."
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

**What to do with findings:** Flag each inconsistency to the user and ask if they want to adjust: "Revenue growth is set at 18% but research confidence is Low and growth is Decelerating. Revise? [y/N]"

If no inconsistencies are found, display: "Coherence check passed — assumptions are internally consistent"

### 8. Sensitivity Awareness — What Matters Most?

Run a quick sensitivity check on the 4 core assumptions. For each, vary by ±20% from the current value and calculate the resulting fair value using `DCFModel`. For terminal ROIC, also show the WACC-default value as the downside case. Display:

```
Sensitivity (±20% change in assumption → fair value impact):
  Revenue growth:    $XXX to $XXX  (±$XX, ±XX%)  ← highest impact
  Operating margin:  $XXX to $XXX  (±$XX, ±XX%)
  Sales-to-capital:  $XXX to $XXX  (±$XX, ±XX%)
  Terminal ROIC:     $XXX to $XXX  (±$XX, ±XX%)  [WACC-default: $XXX]
```

Flag the highest-impact assumption: "Fair value is most sensitive to revenue growth — a ±20% change swings fair value by ±$XX. This assumption deserves the most scrutiny."

Challenge the user when the highest-impact assumption is vulnerable:
- If the highest-impact assumption has Low confidence from research: "Revenue growth drives the most value and has Low confidence. Want to revise? [y/N]"
- If the highest-impact assumption is a manual override: "[Assumption] is the most sensitive assumption AND a manual override — your specific bet has the biggest impact on fair value. A ±20% swing means ±$XX. Are you comfortable with this exposure? [y/N]"
- Both conditions can apply simultaneously — flag both.

### 9. Save Updated Assumptions
- Save via `StockManager.save_assumptions(symbol, assumptions, manual_overrides=overrides)`
- Track `_manual_overrides` throughout:
  - Start with the loaded list from `StockManager.load_manual_overrides(symbol)`
  - User chooses "recommended" → remove field from list
  - User chooses "custom" (types a specific value) → add field to list
  - User chooses "current" (keep existing) → no change to list
  - Note: coherence check adjustments accepted by the user are NOT manual overrides (they're corrections)
  - Pass the final list to `save_assumptions()`
- Display a before/after comparison table (including any coherence check adjustments)
- Run a quick fair value calculation to show the impact of changes

### Important Notes
- Use `AskUserQuestion` for core assumptions and the group prompts for mechanical/market
- Present the recommended value as the first option
- Always show the math/data behind core assumption recommendations
- If no cached financial data is available, note which recommendations are less reliable
