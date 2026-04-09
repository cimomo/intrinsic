# DCF Methodology

How Intrinsic values stocks — the specific choices, formulas, and rationale behind the model. Not a general DCF explainer.

---

## Overview

The model draws heavily from Prof. Aswath Damodaran's (NYU Stern) published framework and datasets. The core idea: **every number needs a story, and every story needs a number.** The math in a DCF is precise — discount rates to four decimal places, terminal values to the dollar — but the inputs are judgment calls. Growth rate, operating margin, capital efficiency, competitive advantage: these are narratives about a company's future, translated into numbers. The real work is grounding each assumption in data and qualitative research, testing them for internal consistency, and challenging them from multiple angles before committing to a valuation.

The valuation flows through two phases — projecting free cash flows, then discounting them back to today:

```
Revenue (base year)
  × (1 + growth rate)         → projected revenue per year
  × operating margin          → operating income
  × (1 - tax rate)            → NOPAT (net operating profit after tax)
  - reinvestment              → free cash flow to the firm

Sum of discounted FCFs        → present value of operating assets
  + terminal value            → enterprise value
  + cash & investments        → }
  - debt                      → } equity value (see Equity bridge)
  ÷ shares outstanding        → fair value per share
```

Reinvestment, terminal value, and the discount rate are where most of the nuance lives.

---

## Model variant: FCFF / WACC

We use **Free Cash Flow to the Firm (FCFF)** discounted at **WACC**. This values the entire firm's operating assets, then applies the equity bridge (add cash and investments, subtract debt) to get equity value. The alternative — Free Cash Flow to Equity (FCFE) discounted at cost of equity — is appropriate for financial services firms where debt is a raw material, not capital. Intrinsic does not currently support FCFE valuation.

```
Fair Value = (PV of Projected FCFs + PV of Terminal Value + Cash & Investments - Debt) / Shares Outstanding
```

---

## Revenue growth

A single growth rate for years 1-5, then linear tapering to the terminal growth rate over years 6-10.

```
Years 1-5:  revenue_growth_rate (e.g., 15%)
Years 6-10: linear interpolation → terminal_growth_rate
Year 10:    terminal_growth_rate
```

**Why one rate, not year-by-year?** Year-by-year forecasts create a false sense of precision. The real judgment is: what average growth rate can this company sustain for the next 5 years? The taper ensures the model doesn't assume high growth persists forever.

The terminal growth rate cannot exceed the risk-free rate. A company growing faster than the economy in perpetuity would eventually become the entire economy.

The growth rate is informed by historical revenue trends, qualitative research signals, and the market-implied growth rate from [reverse DCF](#reverse-dcf).

---

## Reinvestment: the Sales-to-Capital approach

We do **not** use the traditional `FCF = NOPAT - CapEx - ΔWorkingCapital` formula. Instead, we use the Sales-to-Capital ratio approach (from Damodaran's FCFF framework):

```
Reinvestment = ΔRevenue / Sales-to-Capital Ratio
FCF = NOPAT - Reinvestment
```

The S/C ratio tells you how many dollars of revenue a company generates per dollar of invested capital (where Invested Capital = Equity + Debt - Cash - Investments). A ratio of 2.0 is capital-light — $2 of revenue per $1 of capital. A ratio of 0.5 is capital-heavy — $1 of capital needed for every $0.50 of new revenue.

**Why S/C instead of CapEx?** Three reasons:

1. **Internal consistency.** Growth, reinvestment, and revenue are tied together through one ratio. If you assume 15% growth and S/C of 0.7, the reinvestment required is exactly ΔRevenue / 0.7.

2. **Captures all reinvestment.** CapEx-based approaches miss acquisitions, which for many companies are a major form of reinvestment. S/C captures acquisitions naturally because acquired revenue and capital both enter the ratio.

3. **Established approach.** Damodaran uses S/C in his FCFF models and publishes industry S/C ratios annually.

**Calibrating S/C:** There are two ways to measure the ratio historically. The **average** (Revenue / Invested Capital) shows overall capital efficiency. The **incremental** (ΔRevenue / ΔInvested Capital) shows how much capital recent growth has required — this better reflects the company's current investment regime. Both are computed from 5 years of data during calibration. The incremental ratio makes regime changes visible — like a company shifting from capital-light to capital-heavy due to infrastructure investment.

---

## Operating margin convergence

If a target operating margin is set, the margin converges linearly from the current margin to the target over the projection period:

```
Year N margin = current_margin + (target - current_margin) × (N / projection_years)
```

This handles two common scenarios:
- **Expanding margins** — growth company investing for scale, operating leverage kicks in
- **Compressing margins** — currently at peak, facing depreciation headwinds, competition, or reinvestment pressure

If no target is set, the current margin is held flat for all projection years.

---

## Tax rate: effective-to-marginal transition

Two separate tax rate assumptions:

| Assumption | What it represents | Default |
|---|---|---|
| Marginal tax rate | Statutory corporate rate | 21% |
| Effective tax rate | Current rate from income statement | None (= use marginal everywhere) |

When the effective rate is set, the tax rate transitions linearly from effective to marginal over the projection period:

```
Year N tax rate = effective + (marginal - effective) × (N / projection_years)
```

**Terminal value always uses the marginal rate.** None of the reasons for effective/marginal divergence — NOLs, credits, deferrals, international structuring — persist in perpetuity.

**Why this matters:** A company with a 15% effective rate and 21% marginal rate has a meaningful difference in early-year NOPAT. Using marginal everywhere overstates the tax burden in years 1-5 for companies with tax advantages. Using effective everywhere understates terminal-period taxes.

**NOL handling:** For companies with large NOL carryforwards, set the effective rate to 0% (or near-zero). The model ramps from 0% to 21% over 10 years. This "dynamic rates" approach is simpler and more conservative than separately valuing the tax savings.

---

## ROIC: the central metric

Return on Invested Capital determines whether growth creates or destroys value — a central idea in Damodaran's framework.

```
ROIC = NOPAT / Invested Capital
     = Operating Income × (1 - Tax Rate) / (Equity + Debt - Cash - Investments)
```

A company earning ROIC above its cost of capital creates value with every dollar reinvested. A company earning below its cost of capital destroys value — growing faster makes the stock *less* valuable, not more.

ROIC appears throughout the model:
- **Terminal value reinvestment** — how much of NOPAT must be reinvested to sustain terminal growth (g / ROIC)
- **Fundamental growth cross-check** — is the assumed growth rate achievable given capital efficiency? (growth = reinvestment rate × ROIC)
- **Value-of-growth check** — if ROIC < WACC, growth destroys value
- **Terminal ROIC selection** — moat strength determines how much excess return persists in perpetuity

Current ROIC uses GAAP operating income, which includes R&D as an expense. For R&D-heavy tech companies, this understates ROIC compared to an R&D-capitalized approach — see [Known limitations](#known-limitations).

---

## WACC

```
WACC = (E/V) × Re + (D/V) × Rd × (1 - Tc)
```

Where:
```
Re = Rf + β × ERP             (CAPM: Cost of Equity)
Rf = Risk-free rate            (10-year Treasury, default 4.5%)
ERP = Equity risk premium      (default 5.0%)
Rd = Pre-tax cost of debt      (from credit rating; see Cost of debt below)
Tc = Marginal tax rate         (21%)
E = Market cap                 (market value of equity)
D = Total debt                 (book value as proxy for market value)
V = E + D
```

Equity is weighted at market value (market cap). Debt is weighted at book value — close enough for most companies, and market value of debt requires bond pricing data.

**Year-varying WACC.** When the effective tax rate differs from marginal, the debt tax shield varies year by year — a company with a 5% effective rate gets less tax benefit from debt than one at 21%. The model computes a separate WACC for each projection year, using that year's blended tax rate for the debt shield. The terminal value uses the marginal-rate WACC. When effective and marginal rates are the same, all years get the same WACC.

**Hurdle rate override.** If `cost_of_capital` is set, it bypasses WACC computation entirely — beta, ERP, and cost of debt become irrelevant. This is useful when WACC components have known limitations or when the investor has a specific required return.

See [Known limitations](#known-limitations) for how beta and equity risk premium can be improved.

---

## Cost of debt

The pre-tax cost of debt is derived from the company's credit rating, following Damodaran's hierarchy:

1. **Actual credit rating** (S&P, Moody's) — primary. Looked up via web search during calibration.
2. **Synthetic credit rating** — fallback for unrated companies. Derived from interest coverage ratio (EBIT / Interest Expense), mapped through Damodaran's lookup table. Auto-selects large-firm (market cap >= $5B) or small-firm table.
3. **Manual override** — user can set cost of debt directly during calibration.

Once the rating is determined:

```
Cost of Debt = Risk-Free Rate + Default Spread
```

Default spreads come from Damodaran's published tables (updated annually, January). The spread reflects the credit risk premium the market demands for lending to a company with that rating.

**Why not interest expense / total debt?** That ratio reflects the blended coupon on legacy debt — bonds issued years ago at rates that may bear no resemblance to current borrowing costs. A company like Microsoft with old low-coupon bonds shows 2.1% cost of debt, below the risk-free rate. The rating-based approach estimates what the company would pay to borrow *today*.

**Synthetic rating limitations:** Relies on a single ratio (interest coverage). Does not capture assets, cash flow stability, market position, or other factors that rating agencies consider. Most reliable for large manufacturing/technology firms. For the large-cap companies this tool typically analyzes, actual ratings are available via web search and are preferred.

---

## Terminal value: the reinvestment approach

This is the most important nuance in the model. We do **not** naively grow the final year's FCF:

```
Naive (wrong): TV = FCF_year10 × (1 + g) / (WACC - g)
```

Instead, we recalculate reinvestment from scratch using the terminal ROIC:

```
Terminal NOPAT     = Revenue_year11 × Margin × (1 - Marginal Tax Rate)
Reinvestment Rate  = g / Terminal ROIC
Terminal FCF       = Terminal NOPAT × (1 - g / Terminal ROIC)
Terminal Value     = Terminal FCF / (WACC - g)
```

**Why this matters:** The naive approach implicitly assumes year 10's reinvestment intensity continues forever. But terminal growth is much lower than high-growth-phase growth, so less reinvestment is needed per dollar of NOPAT. Conversely, if ROIC is low, more reinvestment is needed. The naive approach gets both directions wrong.

**Example:** A company with 20% ROIC and 4.5% terminal growth:
- Terminal reinvestment rate = 4.5% / 20% = 22.5%
- Terminal FCF = NOPAT × 77.5%
- If year 10's reinvestment happened to be 45% of NOPAT, the naive approach would overstate reinvestment by 2x, *understating* terminal value

This is a common critique of naive DCF implementations.

---

## Terminal ROIC

Controls how much reinvestment is needed to sustain terminal growth.

| Setting | Meaning | When to use |
|---|---|---|
| Default (= WACC) | No excess returns in perpetuity | Default for most companies |
| Explicit override | ROIC > WACC | Wide-moat companies with durable competitive advantages |

**When ROIC = WACC:** Growth adds zero value. The terminal growth rate becomes irrelevant to total value. Mathematically: `Terminal Value = NOPAT / WACC` regardless of the growth rate.

**When ROIC > WACC:** Growth creates value. The higher the ROIC, the less reinvestment is needed per unit of growth, and the more FCF is available. This is the premium for competitive advantage.

The calibration process recommends a terminal ROIC based on moat strength: companies with no moat get WACC (no excess returns), wide-moat companies with widening advantages can retain up to their current ROIC, and everything in between gets a partial spread. The override is capped at 2× WACC — even for the widest moats, competition and disruption erode returns over decades.

**Guards:** Terminal ROIC must be positive and at least equal to the terminal growth rate. Otherwise the company would need to invest more than it earns just to sustain terminal growth — a mathematical impossibility in perpetuity.

---

## Equity bridge

Enterprise value to equity value per share:

```
Equity Value = Enterprise Value
             + Cash & Equivalents
             + Short-Term Investments (Treasuries, corporate bonds, etc.)
             + Long-Term Investments (equity stakes, long-dated bonds)
             - Total Debt
Fair Value = Equity Value / Shares Outstanding
```

Cash and short-term investments are treated as marketable securities added at face value, following Damodaran's default of treating cash as a "neutral asset." Long-term investments are included at book value — these may include a mix of public equity, private company stakes, and long-dated debt instruments.

A complete equity bridge also subtracts preferred stock, minority interests, employee options value, and unfunded pension obligations. These require data beyond what Alpha Vantage provides. For most large-cap companies without significant preferred stock, the current bridge is a reasonable approximation. See [Known limitations](#known-limitations).

---

## Reverse DCF

Solves for the revenue growth rate the market is pricing in:

```
Given: current price, WACC, margin, S/C ratio, terminal growth
Find:  revenue_growth_rate where fair_value ≈ current_price
```

Uses binary search over [-10%, 50%]. The negative lower bound allows finding implied rates for declining companies.

Reverse DCF is an anchor, not a recommendation. It tells you: "the market is pricing in X% growth — if your assumption differs, you should know why."

---

## Sensitivity analysis

A 5×5 matrix of fair values across revenue growth rate (±2%, ±4%) and operating margin (±3%, ±6%). For each cell, the model recalculates fair value from scratch — projecting FCFs, terminal value, and discounting — holding WACC, S/C ratio, and other assumptions constant.

Negative growth rates are allowed in the sensitivity table.

---

## Sanity checks

| Check | What it catches |
|---|---|
| Terminal value concentration | TV > 85% of enterprise value — valuation depends almost entirely on post-year-10 assumptions |
| Implausible fair value | Fair value negative or > 5× current price |
| Negative early FCFs | High reinvestment drives FCF negative in years 1-3 |
| Fundamental growth | Assumed growth exceeds reinvestment rate × ROIC — not achievable from capital efficiency |
| Value-of-growth | ROIC < WACC — growth destroys value |
| Directional bias | All 3 core assumptions lean the same direction — a compounding bet |
| Reverse DCF gap | Assumed growth significantly above market-implied rate |

---

## Assumption defaults

| Assumption | Default | Rationale |
|---|---|---|
| Revenue growth rate | 10% | Moderate placeholder — always calibrate before valuing |
| Terminal growth rate | = risk-free rate (4.5%) | Cannot exceed risk-free rate |
| Projection years | 10 | 5 years high growth + 5 years tapering |
| Operating margin | From financials | Current operating margin |
| Target operating margin | None | No convergence unless explicitly set |
| Marginal tax rate | 21% | US federal corporate rate |
| Effective tax rate | None | Uses marginal for all years unless set |
| Risk-free rate | 4.5% | 10-year Treasury yield |
| Equity risk premium | 5.0% | Historical ERP; Damodaran's implied ERP is ~4.23% |
| Beta | From financial data | Regression beta; bottom-up preferred |
| Cost of debt | 5.0% | Pre-tax; calibrate derives from credit rating + Damodaran spread |
| Sales-to-capital ratio | Computed from financials | Revenue / Invested Capital |
| Terminal ROIC | WACC | No excess returns in perpetuity; override for wide moats |
| Cost of capital | None | Compute WACC from components; set to override with manual hurdle rate |

All defaults except terminal growth rate (hard cap) and marginal tax rate (statutory) should be calibrated for the specific company before running a valuation.

---

## Known limitations

The model is a work in progress. These are the most significant simplifications:

**Equity bridge gaps.** The bridge includes cash, short-term investments, and long-term investments but does not subtract preferred stock, minority interests, employee stock options, or unfunded pension obligations. For tech companies with large option/RSU programs, this overstates equity value per share. The proper approach values outstanding options separately (using an option pricing model) and subtracts them from equity before dividing by actual shares — not diluted shares. Long-term investments are included at book value, which may over- or understate the true value of illiquid private company stakes.

**Regression beta.** The more robust approach is bottom-up betas — averaging unlevered betas across comparable firms in the same industry, then relevering for the target company's capital structure. Regression betas are noisy, backward-looking, and distorted by recent price moves that may not reflect business risk. Damodaran publishes unlevered industry betas annually.

**Static equity risk premium.** The default (5.0%) is a historical average. A forward-looking implied ERP, derived from current market pricing and expected cash flows, better reflects current risk appetite. Damodaran publishes this monthly — his January 2026 estimate is 4.23%, meaning the default overstates cost of equity and depresses fair value.

**Cost of debt approximation.** Cost of debt is derived from credit ratings (actual or synthetic) mapped to default spreads from Damodaran's annual lookup table. The synthetic approach relies solely on interest coverage ratio and may not capture all factors that rating agencies consider. The spread table is a January snapshot, not live market data — during credit crises, actual spreads may be significantly wider. For companies with complex capital structures (convertible debt, structured financing), the single-rating approach may not capture the true borrowing cost.

**No R&D capitalization.** GAAP treats R&D as an operating expense, but for valuation purposes it should be treated as a capital expenditure — adding unamortized R&D back to invested capital and adjusting operating income. Without this adjustment, ROIC is understated by 10-20% for R&D-heavy tech companies, which distorts the terminal value reinvestment calculation.

**No financial services support.** FCFF/WACC is structurally wrong for banks, insurance companies, and financial services firms where debt is a raw material. The model does not currently detect or warn about financial services companies.

**No cyclical normalization.** The model uses the most recent year as the base for projections. For cyclical companies at peak or trough earnings, this overstates or understates fair value. A better approach normalizes margins by averaging over a full business cycle.

---

## References

- Damodaran, Aswath. *Investment Valuation*, 4th Edition. Wiley, 2025.
- Damodaran, Aswath. *The Little Book of Valuation*, Updated Edition. Wiley, 2024.
- Damodaran, Aswath. *The Dark Side of Valuation*, 3rd Edition. Pearson, 2018.
- Damodaran, Aswath. *Narrative and Numbers: The Value of Stories in Business*. Columbia University Press, 2017.
- [Damodaran Online](https://pages.stern.nyu.edu/~adamodar/) — datasets, spreadsheets, lecture notes (updated annually)
