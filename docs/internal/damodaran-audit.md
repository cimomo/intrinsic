# Damodaran Framework Audit

Systematic comparison of Intrinsic's DCF implementation against Prof. Aswath Damodaran's valuation framework (NYU Stern). Damodaran is the primary intellectual foundation for this project — this audit identifies where we align, where we diverge, and what's worth fixing.

**Date:** 2026-04-05 (updated 2026-04-06)

---

## Background

Damodaran's core idea: **it's not growth that creates value — it's growth at returns above the cost of capital.** His framework centers on ROIC (Return on Invested Capital) as the bridge between a company's narrative and its numbers. Every assumption in a DCF should connect to a coherent business story, and the math should enforce internal consistency.

His signature contributions relevant to us:
- Narrative and Numbers — every number needs a story, every story needs a number
- Growth = Reinvestment Rate x ROIC (growth is never free)
- Terminal value reinvestment must be recalculated, not naively grown
- Implied ERP over historical ERP
- Bottom-up (industry) betas over regression betas
- R&D as capital expenditure, not operating expense
- SBC is a real expense — never add it back
- The bridge from enterprise value to equity per share has many steps
- The 3P test: Possible, Plausible, Probable

---

## Where we align well

These are solid. No changes needed.

| Area | Damodaran | Intrinsic | Notes |
|------|-----------|-----------|-------|
| FCFF framework | Discount FCFF at WACC, equity bridge to per-share value | Same | Core structure is correct |
| Sales-to-capital ratio | His preferred reinvestment measure | Core to the model | `dcf.py` uses S/C exclusively |
| Terminal growth <= risk-free rate | Hard constraint | Defaults `terminal_growth = risk_free_rate` | `dcf.py:42-43` |
| Growth tapering | High-growth -> stable transition | Linear taper years 6-10 | Reasonable simplification |
| Margin convergence | Target margins tied to narrative | Optional `target_operating_margin` | `dcf.py:118-138` |
| Reverse DCF | What does the market imply? | Built into calibrate | `dcf.py:418-493` |
| Narrative -> Numbers | Research informs assumptions | Research signals feed calibration | The whole pipeline architecture |
| Sensitivity analysis | Test which assumptions matter most | Growth x margin matrix | `dcf.py:663-743` |
| Self-challenge | Test against counter-arguments | Coherence check, pre-mortem, contrarian search | Multiple overlapping mechanisms |
| Assumption persistence | Track and revisit | Manual overrides survive across runs | `stock_manager.py` |
| SBC as operating expense | Never add back; it's a real cost | GAAP operating income includes SBC | Alpha Vantage reports GAAP figures |
| Acquisitions in reinvestment | Include M&A as reinvestment | S/C ratio naturally captures this | Acquired revenue + capital both enter S/C |

---

## Gaps

### Phase 1: Make the model ROIC-aware

These form a natural cluster. Damodaran's central insight is that value creation depends on the spread between ROIC and WACC. Right now our model is growth-aware but not return-aware.

#### 1. No ROIC computation anywhere

**Priority:** HIGH
**Effort:** Small
**Files:** `stock_analyzer/metrics.py`, `skills/value/SKILL.md`

ROIC is the single most important metric in Damodaran's framework:

```
ROIC = NOPAT / Invested Capital
     = Operating Income * (1 - Tax Rate) / (Equity + Debt - Cash - Investments)
```

We have ROE and ROA in `CompanyMetrics` but not ROIC. It should be:
- Computed in `metrics.py` (we already have all the inputs)
- Displayed in the value skill's metrics table
- Available for the terminal value fix and fundamental growth check

#### 2. Terminal value reinvestment

**Priority:** HIGH
**Effort:** Small (~20 lines)
**Files:** `stock_analyzer/dcf.py`

Current (`dcf.py:237`):
```python
fcf_year_n_plus_1 = final_year_fcf * (1 + self.assumptions.terminal_growth_rate)
```

Damodaran's approach:
```
Terminal Reinvestment Rate = g / ROIC
Terminal NOPAT = Revenue(year 11) * margin * (1 - tax)
Terminal FCF = Terminal NOPAT * (1 - g/ROIC)
TV = Terminal FCF / (WACC - g)
```

Why it matters: naively growing the last FCF by `(1+g)` implicitly assumes the same reinvestment intensity continues forever. If ROIC is high and terminal growth is low, the true terminal FCF should be *higher* (less reinvestment needed). If ROIC is low, it should be *lower*. For a company with 20% ROIC and 4.5% terminal growth, the reinvestment rate should be 22.5% — very different from whatever year 10's reinvestment happened to be.

This is Damodaran's most commonly cited critique of "textbook DCFs."

Depends on: ROIC computation (#1).

#### 3. Fundamental growth cross-check

**Priority:** MEDIUM-HIGH
**Effort:** Small
**Files:** `skills/calibrate/SKILL.md`

Damodaran's formula: `Expected Growth = Reinvestment Rate x ROIC`

Calibrate recommends growth rates from revenue trends and research signals but never checks whether the assumed growth is *achievable* given the company's capital efficiency. Example:

> You assume 15% growth. ROIC is 10%, reinvestment rate is 80%. Fundamental growth = 8%. To hit 15%, the company needs to either double its ROIC or reinvest 150% of NOPAT. Is that plausible?

This should be a sanity check after setting the revenue growth assumption. Not a gate — just information.

#### 4. Value-of-growth check

**Priority:** MEDIUM
**Effort:** Small
**Files:** `skills/calibrate/SKILL.md` (coherence check section)

If ROIC < WACC, growing faster destroys value. The coherence check should flag:

> At your implied ROIC of 8% vs WACC of 10%, each dollar of growth destroys value. Higher growth makes this stock *less* valuable, not more.

This is a critical Damodaran principle that our coherence check doesn't test.

#### 5. Reverse DCF can't find negative growth

**Priority:** MEDIUM
**Effort:** Trivial
**Files:** `stock_analyzer/dcf.py`

`dcf.py:455`: `low = 0.0, high = 0.50`

For declining companies (mature industries, disruption), the market may price in negative growth. Reverse DCF will hit the 0% floor and give a misleading result. Damodaran explicitly handles negative growth rates and advocates for negative terminal growth in declining industries.

Fix: change `low` to `-0.10` (or `-0.05`).

#### 6. Sensitivity table filters out negative growth

**Priority:** LOW-MEDIUM
**Effort:** Trivial
**Files:** `stock_analyzer/dcf.py`

`dcf.py:691`: `growth_steps = [g for g in growth_steps if g >= 0]`

If a stock's base growth is 2%, the sensitivity table can't show the -2% scenario — often the most informative downside case. Remove the filter, or at least allow one negative step.

#### 7. Equity bridge: enterprise value to per-share value

**Priority:** HIGH
**Effort:** Medium
**Files:** `stock_analyzer/dcf.py`, `stock_analyzer/metrics.py`

Previous bridge (before fix):
```python
net_debt = total_debt - cash
equity_value = enterprise_value - net_debt
```

Current bridge (after fix):
```python
cash_and_investments = cash + short_term_investments + long_term_investments
equity_value = enterprise_value + cash_and_investments - total_debt
```

Damodaran's complete bridge:
```
Value of Operating Assets (PV of FCFs + PV of Terminal Value)
+ Cash and Marketable Securities (excess cash only)
+ Value of Cross-Holdings (minority investments at market value)
+ Value of Other Non-Operating Assets
= Firm Value
- Market Value of Debt (including capitalized leases)
- Preferred Stock (at market or redemption value)
- Minority Interests (at market value, not book)
- Value of Employee Options (OPM, not treasury stock method)
- Unfunded Pension / Healthcare Obligations
- Contingent Liabilities (probability-weighted)
= Common Equity Value
/ Actual Shares Outstanding (NOT diluted)
= Value Per Share
```

We're missing subtractions AND additions:

**Missing subtractions:** Preferred stock, minority interests, employee options, unfunded pension. The biggest for tech companies: **employee options**. Damodaran is emphatic that outstanding options/RSUs represent an equity claim that must be valued (via Black-Scholes or option pricing model) and subtracted from equity value *before* dividing by shares. Using diluted share count is "an extremely sloppy way" to handle this. What NOT to do: treasury stock method (ignores time value, always overvalues shares) or "fully diluted" (ignores exercise cash proceeds, undervalues shares).

**Missing additions:** Cross-holdings / minority investments (at market value), other non-operating assets.

**Cash quality:** Damodaran distinguishes operating cash (needed for business) from excess cash. Only excess cash should be added back. For multinationals, cash trapped overseas may deserve a discount for repatriation taxes (though post-2017 TCJA this matters less for US companies). He warns against assuming zero operating cash needs.

For preferred stock and minority interests: Alpha Vantage provides these in the balance sheet data. Pension obligations may require additional data.

The options piece requires: number of options outstanding, average strike price, average time to expiration, stock volatility. Some of this is available from 10-K filings but not from Alpha Vantage directly. A simpler approximation: estimate SBC as % of revenue and apply a dilution factor.

Note on SBC double-counting: deducting SBC from operating income (future SBC reducing future cash flows) AND subtracting option value from equity (past grants as existing equity claims) is NOT double-counting — they address different time periods. Damodaran is explicit on this point.

#### 8. Tax rate transition: effective to marginal

**Priority:** MEDIUM-HIGH
**Effort:** Small
**Files:** `stock_analyzer/dcf.py`, `skills/calibrate/SKILL.md`

Current: single `tax_rate` (21% default) used for all 10 years and terminal value.

Damodaran's approach:
- Near-term years: use effective tax rate (reflects NOLs, credits, deferrals)
- Transition to marginal tax rate over the projection period
- Terminal value: **must** use marginal rate — none of the reasons for effective/marginal divergence persist in perpetuity

For companies with large NOL carryforwards (historically Tesla, Uber, etc.): effective rate may be near 0% initially, ramping to marginal as NOLs are consumed. Using 21% throughout overstates the tax burden in early years.

Also: the tax rate in the WACC cost-of-debt tax shield (`Rd * (1-t)`) should match the tax rate used for that year's operating income. If using 0% tax on income, you can't simultaneously use `(1-0.21)` for the debt shield.

Implementation: add `effective_tax_rate` as a separate assumption; use it for years 1-5, linearly transition to `tax_rate` (marginal) by year 10. Terminal value always uses marginal.

#### 8b. WACC tax rate consistency

**Priority:** LOW-MEDIUM
**Effort:** Small
**Files:** `stock_analyzer/dcf.py`

`dcf.py:118`: The debt tax shield uses the fixed marginal rate:
```python
debt_weight * self.assumptions.cost_of_debt * (1 - self.assumptions.tax_rate)
```

When `effective_tax_rate` is set, NOPAT uses a year-specific blended rate (transitioning from effective to marginal), but the WACC debt shield always uses marginal. Damodaran says these must match — you can't tax NOPAT at 5% effective while simultaneously claiming a `(1 - 0.21)` debt shield.

Fix: when `effective_tax_rate` is set, `calculate_wacc()` should accept a year parameter and use `_get_tax_rate_for_year()` for the debt shield. In practice this means WACC varies year by year — which Damodaran does in his more detailed models.

Impact is small for low-leverage investment-grade companies, but material for high-leverage firms with large NOL shields (effective rate near 0% means almost no debt tax benefit in early years).

---

### Phase 2: Better inputs

These improve input quality without changing the model's logic.

#### 9. Bottom-up beta

**Priority:** MEDIUM-HIGH
**Effort:** Medium
**Files:** `stock_analyzer/metrics.py`, `skills/calibrate/SKILL.md`

Current: uses Alpha Vantage regression beta (`metrics.py:149`).

Damodaran's approach:
1. Start with unlevered industry beta (he publishes these annually for 95 industries)
2. Relever for the company's D/E: `Levered Beta = Unlevered Beta * (1 + (1-t) * D/E)`

Regression betas are noisy and backward-looking — a stock that crashed recently shows high beta even if business risk hasn't changed.

Options:
- **Minimal:** Add the relevering formula to calibrate, let the user input industry unlevered beta
- **Better:** Hardcode Damodaran's industry beta table (he publishes it freely)
- **Best:** Fetch from his dataset at runtime

#### 10. Implied ERP

**Priority:** MEDIUM
**Effort:** Small
**Files:** `stock_analyzer/dcf.py`

`dcf.py:28`: `market_risk_premium: float = 0.05` (static)

Damodaran publishes monthly implied ERP. His January 2026 estimate: **4.23%** (over T-bond at 4.18%), with expected return on stocks of 8.41%. Our default of 5.0% is 77bps above his current estimate — this overstates cost of equity by ~0.7-0.8% for a beta-1 stock, which depresses fair value.

His argument: historical ERP is backward-looking, noisy, and moves counterintuitively (falls during crises when risk is highest, which makes no economic sense). He published "ERP: The 2026 Edition" (March 2026, SSRN) with updated methodology.

Options:
- **Minimal:** Update the default to 4.5% (closer to his recent estimates)
- **Better:** Add a note in calibrate when the assumption looks stale
- **Best:** Fetch his latest implied ERP spreadsheet from `pages.stern.nyu.edu/~adamodar/pc/datasets/histimpl.xls`

#### 11. Synthetic credit rating for cost of debt

**Priority:** MEDIUM
**Effort:** Medium
**Files:** `stock_analyzer/dcf.py` or `metrics.py`, `skills/calibrate/SKILL.md`

Current: static 5% default (`dcf.py:31`), calibrate tries interest expense / total debt.

This is already a known issue (see `docs/internal/feedback/invest-2026-04-04.md` — GOOGL's 0.3% cost of debt broke WACC). Damodaran's approach:

1. Calculate interest coverage ratio: `EBIT / Interest Expense`
2. Map to synthetic credit rating (he publishes the lookup table)
3. Map rating to default spread
4. Cost of debt = Risk-free rate + Default spread

**Lookup table (large non-financial firms, January 2026):**

| Coverage Ratio | Rating | Default Spread |
|---|---|---|
| > 8.50 | Aaa/AAA | 0.40% |
| 6.50 – 8.50 | Aa2/AA | 0.55% |
| 5.50 – 6.50 | A1/A+ | 0.70% |
| 4.25 – 5.50 | A2/A | 0.78% |
| 3.00 – 4.25 | A3/A- | 0.89% |
| 2.50 – 3.00 | Baa2/BBB | 1.11% |
| 2.25 – 2.50 | Ba1/BB+ | 1.38% |
| 2.00 – 2.25 | Ba2/BB | 1.84% |
| 1.75 – 2.00 | B1/B+ | 2.75% |
| 1.50 – 1.75 | B2/B | 3.21% |
| 1.25 – 1.50 | B3/B- | 5.09% |
| 0.80 – 1.25 | Caa/CCC | 8.85% |
| 0.65 – 0.80 | Ca2/CC | 12.61% |
| 0.20 – 0.65 | C2/C | 16.00% |
| < 0.20 | D2/D | 19.00% |

Source: `pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/ratings.html` (separate tables exist for small-cap and financial services firms).

GOOGL example: interest coverage > 8.5x → AAA → 0.40% spread → cost of debt = 4.5% + 0.4% = 4.9%. Far more reasonable than the 0.3% from interest expense / total debt (which reflects blended coupon on legacy low-rate debt).

This would fix the GOOGL problem structurally rather than with a heuristic.

#### 12. Cyclical earnings normalization

**Priority:** MEDIUM
**Effort:** Medium
**Files:** `skills/calibrate/SKILL.md`, `skills/value/SKILL.md`

Current: uses the most recent annual revenue and operating income as the base for projections.

For cyclical companies (commodities, autos, semiconductors, construction) at peak earnings, this overstates the base and inflates fair value. At trough earnings, it understates.

Damodaran's approach: normalize earnings using either (a) average margins over a full cycle (5-10 years), or (b) industry-average margins applied to current revenue. The relative averaging method is preferred — it uses current scale but historical profitability levels.

The calibrate skill could detect cyclicality from revenue/margin volatility in the financial data and suggest normalized margins when the current year appears to be peak or trough.

#### 12b. Value decomposition (assets in place vs growth)

**Priority:** LOW-MEDIUM
**Effort:** Small
**Files:** `skills/value/SKILL.md`, `stock_analyzer/dcf.py`

Damodaran decomposes value into:
- **Value of assets in place:** `NOPAT / WACC` — what the company is worth with zero growth, earning current returns forever
- **Value of growth:** `Total Value - Value of Assets in Place`

If 80% of value comes from growth, every growth assumption is load-bearing. If ROIC = WACC, value of growth is zero regardless of growth rate. If ROIC < WACC, value of growth is negative.

This is a powerful one-liner sanity check for the value skill: "At your assumptions, X% of value comes from growth. The market attributes Y%." No model changes needed — just compute and display.

#### 12c. Implied revenue / TAM sanity check

**Priority:** LOW-MEDIUM
**Effort:** Small
**Files:** `skills/calibrate/SKILL.md` or `skills/value/SKILL.md`

Year-10 revenue from the DCF implies a certain market size. For MSFT at 15% growth, year-10 revenue ≈ $1.1T. Damodaran warns against growth assumptions that require implausible market share — a $500B revenue company growing at 15% needs $75B in new revenue per year.

Not a gate — just a display: "Your assumptions imply $XXB revenue by year 10. Consider whether this is plausible relative to the total addressable market."

Growth declines as companies scale. A 10x increase in revenue is feasible for a $2M company but not for a $2B company. The calibrate skill doesn't currently check this.

---

### Phase 3: Structural adjustments

Higher effort, most impactful for specific company types.

#### 13. R&D capitalization

**Priority:** MEDIUM-HIGH (for tech)
**Effort:** Medium
**Files:** `stock_analyzer/metrics.py`, `stock_analyzer/dcf.py`

Damodaran treats R&D as capital expenditure. Full methodology:

**Step 1 — Create the Research Asset:**
Sum unamortized R&D over the amortizable life. If amortizable life = 5 years:
```
Research Asset = R&D_year1 * (4/5) + R&D_year2 * (3/5) + R&D_year3 * (2/5) + R&D_year4 * (1/5)
```
(Current year's R&D is fully unamortized, prior years decay linearly)

**Step 2 — Adjust Operating Income:**
- Add back current year's R&D expense (removing it from operating expenses)
- Subtract amortization of the research asset
- Net effect: Operating Income increases if R&D is growing (current R&D > amortization of past R&D)

**Step 3 — Adjust Invested Capital:**
- Add the Research Asset to book equity and invested capital

**Step 4 — Recalculate ROIC:**
- `Adjusted ROIC = Adjusted NOPAT / Adjusted Invested Capital`
- For high-ROIC firms with growing R&D, adjusted ROIC is typically *lower* (invested capital increases by more than NOPAT)

**Tax treatment:** R&D remains fully tax-deductible in the year incurred (per US tax code), even though it's capitalized for valuation purposes. This creates a tax benefit that must be captured.

**Impact on FCF:** None — the reclassification doesn't change free cash flows. What it changes: ROIC, reinvestment rate, implied growth rate, and internal consistency.

**Amortizable life by industry:**
- Pharmaceutical: 10+ years (FDA approval timeline)
- Aerospace/Defense: 10 years
- Technology/Software: 3-5 years
- Product-specific R&D: until commercialization or abandonment

For tech companies this is a 10-20% swing in operating income and significantly changes ROIC. Without this adjustment, ROIC is understated for R&D-heavy companies, which distorts the terminal value reinvestment calculation and fundamental growth check.

Requires: R&D expense from income statement (Alpha Vantage provides `researchAndDevelopment`), assumption about amortization period.

#### 14. Industry base rate comparisons

**Priority:** MEDIUM
**Effort:** Large
**Files:** `skills/calibrate/SKILL.md`

Damodaran always anchors against industry data — median margins, betas, ROIC, S/C ratios across 95 industry groups. Calibrate relies entirely on company history plus research signals. No context like:

> Only 5% of companies sustain >15% revenue growth for 10 years. Industry median S/C is 1.8x vs your 2.5x. Industry median operating margin is 22% — you're assuming 35%.

Options:
- **Minimal:** Add base rate warnings to calibrate for extreme assumptions (hardcode thresholds)
- **Better:** Embed Damodaran's industry dataset and look up by sector
- **Best:** Fetch annually from his website

#### 15. Financial services companies

**Priority:** MEDIUM
**Effort:** Small (detection + warning)
**Files:** `skills/calibrate/SKILL.md`, `skills/value/SKILL.md`

Damodaran is explicit: **FCFF/WACC does not work for banks, insurance companies, or financial services firms.** Debt is a raw material, not capital. CapEx and working capital have no traditional meaning. Only equity-side valuation (DDM, bank FCFE, or excess return model) is valid.

Our tool will produce wrong answers for banks and not warn the user. At minimum: detect financial services companies (from Alpha Vantage sector/industry data) and display a prominent warning. A full fix would require an alternative valuation path (DDM or excess return model), which is a larger effort.

#### 16. Distress probability adjustment

**Priority:** LOW-MEDIUM
**Effort:** Medium
**Files:** `stock_analyzer/dcf.py`

For companies in financial distress, Damodaran uses a two-step approach:

```
Adjusted Value = Going Concern Value x (1 - p_distress) + Distress Sale Value x p_distress
```

Probability of distress can be estimated from bond ratings (he publishes cumulative default rate tables) or from bond prices. Distress sale value is typically 50-70% of going-concern value.

Our model assumes the company survives as a going concern. For healthy companies this is fine. For companies with high leverage or negative cash flows, the going-concern assumption overstates value.

At minimum: flag when interest coverage is very low or debt/equity is very high. A full implementation would apply the probability adjustment.

#### 17. Operating lease capitalization

**Priority:** LOW-MEDIUM
**Effort:** Medium
**Files:** `stock_analyzer/metrics.py`

Damodaran capitalizes operating leases as debt. Under ASC 842 / IFRS 16, many leases are already on the balance sheet, so this matters less than it used to. Mainly relevant for retail, airlines, and other asset-heavy businesses. Low priority for a tech-focused plugin.

#### 18. Country risk premium

**Priority:** LOW-MEDIUM
**Effort:** Medium
**Files:** `stock_analyzer/dcf.py`, `skills/calibrate/SKILL.md`

Damodaran uses revenue-weighted country risk for multinationals:
```
Country ERP = Mature Market ERP + Country Risk Premium
Country Risk Premium = Default Spread * (Equity Vol / Bond Vol)
```

Matters for companies with significant emerging-market revenue. He publishes country risk premiums annually.

#### 19. Multi-stage WACC

**Priority:** LOW
**Effort:** Medium
**Files:** `stock_analyzer/dcf.py`

Damodaran sometimes transitions beta -> 1.0 and D/E -> industry average during the stable period. Impact is usually small. Not worth the complexity for now.

---

## Summary table

| # | Gap | Phase | Priority | Status | Commit |
|---|-----|-------|----------|--------|--------|
| 1 | ROIC computation | 1 | HIGH | **DONE** | `75a5321` — ROIC in metrics, value skill, calibrate coherence check |
| 2 | Terminal value reinvestment (g/ROIC) | 1 | HIGH | **DONE** | `419e49b` — Damodaran reinvestment approach, terminal ROIC defaults to WACC, configurable for wide-moat |
| 3 | Fundamental growth cross-check | 1 | MEDIUM-HIGH | **DONE** | `75a5321` — Added to calibrate coherence check with #1 |
| 4 | Value-of-growth check (ROIC vs WACC) | 1 | MEDIUM | **DONE** | `75a5321` — Added to calibrate coherence check with #1 |
| 5 | Reverse DCF negative growth | 1 | MEDIUM | **DONE** | `07c90e9` — Search bounds [-10%, 50%] |
| 6 | Sensitivity table negative growth | 1 | LOW-MEDIUM | **DONE** | `07c90e9` — Removed >= 0 filter |
| 7 | Equity bridge (options, preferred, minority, cross-holdings) | 1 | HIGH | **DONE** | Cash + short/long-term investments in bridge; preferred/minority/options as documented limitations |
| 8 | Tax rate transition (effective -> marginal) | 1 | MEDIUM-HIGH | **DONE** | `b235a96` — effective_tax_rate transitions to marginal over projection period |
| 8b | WACC tax rate consistency | 1 | LOW-MEDIUM | **DONE** | Year-varying WACC when effective_tax_rate is set + cost_of_capital hurdle rate override |
| 9 | Bottom-up beta | 2 | MEDIUM-HIGH | TODO | |
| 10 | Implied ERP | 2 | MEDIUM | TODO | Current default 5.0% vs Damodaran's Jan 2026 implied 4.23% |
| 11 | Synthetic credit rating (cost of debt) | 2 | MEDIUM | **DONE** | Rating-based cost of debt: actual rating primary, synthetic fallback, Damodaran spread table |
| 12 | Cyclical earnings normalization | 2 | MEDIUM | TODO | |
| 12b | Value decomposition (assets in place vs growth) | 2 | LOW-MEDIUM | TODO | Sanity check: what % of value comes from growth? |
| 12c | Implied revenue / TAM check | 2 | LOW-MEDIUM | TODO | Sanity check: is year-10 revenue plausible? |
| 13 | R&D capitalization | 3 | MEDIUM-HIGH | TODO | |
| 14 | Industry base rate comparisons | 3 | MEDIUM | TODO | |
| 15 | Financial services warning | 3 | MEDIUM | TODO | |
| 16 | Distress probability adjustment | 3 | LOW-MEDIUM | TODO | |
| 17 | Operating lease capitalization | 3 | LOW-MEDIUM | TODO | |
| 18 | Country risk premium | 3 | LOW-MEDIUM | TODO | |
| 19 | Multi-stage WACC | 3 | LOW | TODO | |

---

## Implementation plan

### Phase 1 — Model correctness (items 1-8)

**DONE (7 of 8):**
- Items 1, 3, 4 shipped together (`75a5321`): ROIC computation + calibrate coherence check with fundamental growth and value-of-growth warnings
- Item 2 (`419e49b`): Terminal value uses g/ROIC reinvestment. Terminal ROIC defaults to WACC, overridable for wide-moat companies. Promoted to core assumption in calibrate with moat-based framework.
- Items 5, 6 (`07c90e9`): Negative growth allowed in reverse DCF and sensitivity table
- Item 8 (`b235a96`): Tax rate transitions from effective to marginal over projection period. Terminal value always uses marginal.

**Remaining:** None — Phase 1 complete.

**Recently completed:**
- **Item 7 (equity bridge):** Equity bridge now includes cash, short-term investments (Treasuries, corporate bonds — verified from MSFT/NVDA 10-K filings), and long-term investments (mix of public equity, private stakes, long-dated bonds). All three are added back in `calculate_fair_value()`, with the full bridge displayed as separate line items in `get_summary()`. Invested capital (for ROIC and auto S/C ratio) also updated to exclude all non-operating assets (`equity + debt - cash - STI - LTI`), per Damodaran: *"The reason we net out cash is to be consistent with the use of operating income as our measure of earnings."* Same principle applies to all non-operating assets. **Known limitations:** Alpha Vantage doesn't provide preferred stock or minority interest fields — both are zero for MSFT/NVDA but would matter for companies like Berkshire. Employee options require 10-K data (strike prices, counts) beyond our data source; SBC is already deducted from GAAP operating income (future dilution), but existing option overhang is not valued.
- **Item 8b (WACC tax consistency):** `calculate_wacc()` now uses year-specific tax rate for debt shield when `effective_tax_rate` is set. Also added `cost_of_capital` hurdle rate override that bypasses WACC computation entirely.

### Phase 2 — Better inputs (items 9-12)

**DONE (1 of 6):**
- Item 11: Rating-based cost of debt. Actual credit rating (web search) as primary, synthetic from interest coverage as fallback, Damodaran's January 2026 spread table. Large-firm and small-firm tables, auto-selected by market cap. Replaces broken `interest_expense / total_debt` heuristic.

**Remaining:**
- **#9 (bottom-up beta)** requires either hardcoding Damodaran's industry beta table or fetching it
- **#10 (implied ERP)** is a small default update or web lookup. Current default (5.0%) is 77bps above Damodaran's Jan 2026 implied ERP (4.23%).
- **#12 (cyclical normalization)** is a calibrate skill change
- **#12b (value decomposition)** is a simple sanity check display — no model changes
- **#12c (implied revenue / TAM)** is a calibrate or value sanity check — no model changes

### Phase 3 — Structural adjustments (items 13-19)

Not started. Higher effort, most impactful for specific company types.

### Test count

226 tests. Key additions:
- 9 ROIC tests (metrics.py edge cases)
- 10 terminal value tests (g/ROIC reinvestment, terminal ROIC default/override/guards)
- 4 tax rate transition tests (interpolation, convergence, terminal uses marginal)
- 2 negative growth tests (reverse DCF, sensitivity table)
- 2 integration tests (explicit terminal ROIC, _recalc consistency)
- 5 WACC tax consistency tests + 6 cost of capital override tests
- 7 equity bridge tests (investments increase fair value, per-share impact, backward compat, bridge components in results/summary, net cash company, sensitivity table consistency)

---

## Considered and excluded

These are Damodaran topics we reviewed and deliberately excluded:

| Topic | Why excluded |
|-------|-------------|
| Monte Carlo simulation | Valuable but high complexity; our sensitivity analysis + pre-mortem partially cover the same ground |
| Real options (patents, reserves) | Too specialized; only relevant for biotech/mining |
| Convertible debt decomposition | Rare edge case; few companies have material convertibles |
| DDM / bank FCFE valuation path | Better handled by warning users away from financial services (#15) than building a second model |
| Sum-of-parts valuation | Conglomerate-specific; too complex for default pipeline |
| Dual-class share valuation | Niche; voting premium is hard to estimate |
| Market value of debt estimation | Book value is close enough for most companies; effort not justified |

---

## What we do that Damodaran doesn't emphasize

Worth noting — Intrinsic has several mechanisms that go beyond standard Damodaran:

- **Contrarian search** in research (deliberate search for the opposing case)
- **Signal self-review** (research downgrades its own ratings when prose doesn't support them)
- **Manual override tracking** (makes the user's specific bets explicit and persistent)
- **Confidence-adjusted recommendations** (downgrades output when research inputs are uncertain)
- **Pre-mortem** ("assume it drops 40% — what went wrong?")
- **Alignment check** in the report (do assumptions match research signals?)

These are assumption-quality mechanisms that Damodaran would likely endorse in spirit, even if they're not part of his published framework. They address his concern about "dreamstate DCFs" — valuations disconnected from any coherent narrative.

---

## References

Key Damodaran resources for implementation:

| Resource | URL | Use |
|----------|-----|-----|
| Industry betas | `pages.stern.nyu.edu/~adamodar/pc/datasets/betas.xls` | Bottom-up beta (#9) |
| Ratings & spreads (dataset) | `pages.stern.nyu.edu/~adamodar/pc/datasets/ratings.xls` | Synthetic cost of debt (#11) |
| Ratings lookup (web table) | `pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/ratings.html` | Synthetic cost of debt (#11) — Jan 2026 update |
| Implied ERP | `pages.stern.nyu.edu/~adamodar/pc/datasets/histimpl.xls` | Implied ERP (#10) |
| Sales-to-capital by industry | `pages.stern.nyu.edu/~adamodar/pc/datasets/capex.xls` | Industry base rates (#14) |
| Margins & ROIC by sector | `pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/mgnroc.html` | Industry base rates (#14) |
| Margins by industry | `pages.stern.nyu.edu/~adamodar/pc/datasets/margin.xls` | Industry base rates (#14) |
| Country risk premiums | `pages.stern.nyu.edu/~adamodar/pc/datasets/ctryprem.xlsx` | Country risk (#18) |
| FCFF valuation template | `pages.stern.nyu.edu/~adamodar/pc/fcffsimpleginzu.xlsx` | Reference implementation |
| WACC calculator | `pages.stern.nyu.edu/~adamodar/pc/wacccalc.xls` | Reference implementation |
| ERP 2026 paper (SSRN) | `papers.ssrn.com/sol3/papers.cfm?abstract_id=6361419` | ERP methodology reference |
| Return on capital measures | `pages.stern.nyu.edu/~adamodar/pdfiles/papers/returnmeasures.pdf` | ROIC methodology |
| R&D capitalization guide | `pages.stern.nyu.edu/~adamodar/New_Home_Page/valquestions/R&D.htm` | R&D capitalization (#13) |
| Equity value per share | `pages.stern.nyu.edu/~adamodar/New_Home_Page/littlebook/valuepershare.htm` | Equity bridge (#7) |
| SBC & employee options | `aswathdamodaran.substack.com/p/share-count-confusion-dilution-employee-18-07-26` | Options treatment (#7) |
