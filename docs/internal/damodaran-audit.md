# Damodaran Framework Audit

Systematic comparison of Intrinsic's DCF implementation against Prof. Aswath Damodaran's valuation framework (NYU Stern). Damodaran is the primary intellectual foundation for this project — this audit identifies where we align, where we diverge, and what's worth fixing.

**Date:** 2026-04-05

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
| FCFF framework | Discount FCFF at WACC, subtract net debt | Same | Core structure is correct |
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
     = Operating Income * (1 - Tax Rate) / (Equity + Debt - Cash)
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

Current bridge (`dcf.py:376-381`):
```python
net_debt = total_debt - cash
equity_value = enterprise_value - net_debt
fair_value_per_share = equity_value / shares_outstanding
```

Damodaran's complete bridge:
```
Equity per share = (Enterprise Value
                    + Cash
                    - Total Debt
                    - Preferred Stock (at market value)
                    - Minority Interests (at market value, not book)
                    - Value of Employee Options (Black-Scholes)
                    - Unfunded Pension / Healthcare Obligations)
                    / Shares Outstanding (actual, not diluted)
```

We're missing four subtractions. The biggest for tech companies: **employee options**. Damodaran is emphatic that outstanding options/RSUs represent an equity claim that must be valued (via Black-Scholes or binomial model) and subtracted from equity value *before* dividing by shares. Using diluted share count is "an extremely sloppy way" to handle this.

For preferred stock and minority interests: Alpha Vantage provides these in the balance sheet data. Pension obligations may require additional data.

The options piece requires: number of options outstanding, average strike price, average time to expiration, stock volatility. Some of this is available from 10-K filings but not from Alpha Vantage directly. A simpler approximation: estimate SBC as % of revenue and apply a dilution factor.

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

Damodaran publishes monthly implied ERP (currently ~4.23% as of Jan 2026). His argument: historical ERP is backward-looking, noisy, and moves counterintuitively (falls during crises when risk is highest).

Options:
- **Minimal:** Update the default to 4.5% (closer to his recent estimates)
- **Better:** Add a note in calibrate when the assumption looks stale
- **Best:** Fetch his latest implied ERP spreadsheet

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

This would fix the GOOGL problem structurally rather than with a heuristic.

#### 12. Cyclical earnings normalization

**Priority:** MEDIUM
**Effort:** Medium
**Files:** `skills/calibrate/SKILL.md`, `skills/value/SKILL.md`

Current: uses the most recent annual revenue and operating income as the base for projections.

For cyclical companies (commodities, autos, semiconductors, construction) at peak earnings, this overstates the base and inflates fair value. At trough earnings, it understates.

Damodaran's approach: normalize earnings using either (a) average margins over a full cycle (5-10 years), or (b) industry-average margins applied to current revenue. The relative averaging method is preferred — it uses current scale but historical profitability levels.

The calibrate skill could detect cyclicality from revenue/margin volatility in the financial data and suggest normalized margins when the current year appears to be peak or trough.

---

### Phase 3: Structural adjustments

Higher effort, most impactful for specific company types.

#### 13. R&D capitalization

**Priority:** MEDIUM-HIGH (for tech)
**Effort:** Medium
**Files:** `stock_analyzer/metrics.py`, `stock_analyzer/dcf.py`

Damodaran treats R&D as capital expenditure:
- Remove R&D from operating expenses (operating income goes up)
- Add amortization of capitalized R&D back (partially offsets)
- Add unamortized R&D to invested capital (affects ROIC and S/C)

For tech companies this is a 10-20% swing in operating income and significantly changes ROIC. Without this adjustment, ROIC is understated for R&D-heavy companies, which distorts the terminal value reinvestment calculation and fundamental growth check.

Requires: R&D expense from income statement (Alpha Vantage provides `researchAndDevelopment`), assumption about amortization period (Damodaran typically uses 3-5 years for tech).

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

| # | Gap | Phase | Priority | Effort |
|---|-----|-------|----------|--------|
| 1 | ROIC computation | 1 | HIGH | Small |
| 2 | Terminal value reinvestment (g/ROIC) | 1 | HIGH | Small |
| 7 | Equity bridge (options, preferred, minority) | 1 | HIGH | Medium |
| 3 | Fundamental growth cross-check | 1 | MEDIUM-HIGH | Small |
| 8 | Tax rate transition (effective -> marginal) | 1 | MEDIUM-HIGH | Small |
| 4 | Value-of-growth check (ROIC vs WACC) | 1 | MEDIUM | Small |
| 5 | Reverse DCF negative growth | 1 | MEDIUM | Trivial |
| 6 | Sensitivity table negative growth | 1 | LOW-MEDIUM | Trivial |
| 9 | Bottom-up beta | 2 | MEDIUM-HIGH | Medium |
| 10 | Implied ERP | 2 | MEDIUM | Small |
| 11 | Synthetic credit rating (cost of debt) | 2 | MEDIUM | Medium |
| 12 | Cyclical earnings normalization | 2 | MEDIUM | Medium |
| 13 | R&D capitalization | 3 | MEDIUM-HIGH | Medium |
| 14 | Industry base rate comparisons | 3 | MEDIUM | Large |
| 15 | Financial services warning | 3 | MEDIUM | Small |
| 16 | Distress probability adjustment | 3 | LOW-MEDIUM | Medium |
| 17 | Operating lease capitalization | 3 | LOW-MEDIUM | Medium |
| 18 | Country risk premium | 3 | LOW-MEDIUM | Medium |
| 19 | Multi-stage WACC | 3 | LOW | Medium |

---

## Implementation plan

**Phase 1 — Model correctness** (items 1-8). Two clusters:

*ROIC-aware model (items 1-6):*
1. Add ROIC to `metrics.py` — new field in `CompanyMetrics`, compute in `calculate_dcf_inputs()`
2. Fix terminal value in `dcf.py` — use `g/ROIC` reinvestment rate
3. Add fundamental growth check to calibrate skill — `g_fundamental = reinvestment_rate * ROIC`
4. Add value-of-growth warning to calibrate coherence check — flag when ROIC < WACC
5. Allow negative growth in reverse DCF — change `low` bound
6. Allow negative growth in sensitivity table — remove `>= 0` filter

*Equity bridge and tax (items 7-8):*
7. Complete the enterprise-to-equity bridge — subtract preferred stock, minority interests, estimate option dilution
8. Add tax rate transition — effective in early years, marginal by terminal year

After Phase 1, the model would reflect Damodaran's two central ideas: (a) value creation depends on ROIC vs WACC, and (b) the bridge from enterprise value to equity per share has more steps than most implementations include.

**Phase 2 — Better inputs** (items 9-12): bottom-up beta, implied ERP, synthetic cost of debt, cyclical normalization. These improve assumption quality without changing model structure.

**Phase 3 — Structural adjustments** (items 13-19): R&D capitalization, industry base rates, financial services warning, distress, leases, country risk, multi-stage WACC. Higher effort, most impactful for specific company types.

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
| Ratings & spreads | `pages.stern.nyu.edu/~adamodar/pc/datasets/ratings.xls` | Synthetic cost of debt (#11) |
| Implied ERP | `pages.stern.nyu.edu/~adamodar/pc/datasets/histimpl.xls` | Implied ERP (#10) |
| Sales-to-capital by industry | `pages.stern.nyu.edu/~adamodar/pc/datasets/capex.xls` | Industry base rates (#14) |
| Margins by industry | `pages.stern.nyu.edu/~adamodar/pc/datasets/margin.xls` | Industry base rates (#14) |
| Country risk premiums | `pages.stern.nyu.edu/~adamodar/pc/datasets/ctryprem.xlsx` | Country risk (#18) |
| FCFF valuation template | `pages.stern.nyu.edu/~adamodar/pc/fcffsimpleginzu.xlsx` | Reference implementation |
| WACC calculator | `pages.stern.nyu.edu/~adamodar/pc/wacccalc.xls` | Reference implementation |
