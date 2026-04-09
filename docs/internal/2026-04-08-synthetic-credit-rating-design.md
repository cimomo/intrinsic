# Synthetic Credit Rating for Cost of Debt

**Date:** 2026-04-08
**Audit item:** #11 (Phase 2 — Better inputs)

---

## Problem

Cost of debt estimation is broken for cash-rich companies. The current approach — `interest_expense / total_debt` — reflects the blended coupon on legacy debt, not marginal borrowing cost. This produces absurd results:

- **GOOGL:** 0.3% cost of debt (below any rational floor)
- **MSFT:** 2.1% cost of debt (below the 4.5% risk-free rate)

The static 5% default in `DCFAssumptions` is a guess that happens to be reasonable for some companies but has no analytical basis.

## Solution

Replace the legacy heuristic with Damodaran's rating-based approach, following his actual hierarchy:

1. **Actual credit rating** (from web search during calibrate) — primary
2. **Synthetic credit rating** (from interest coverage ratio) — fallback for unrated companies, cross-check for rated ones
3. **Cost of debt** = risk-free rate + default spread (from Damodaran's lookup table)

## Approach: Hybrid (actual primary, synthetic fallback)

Calibrate web searches for the actual credit rating and uses it to derive cost of debt. The synthetic rating (computed in Python from interest coverage) serves as a cross-check for rated companies and the primary input for unrated ones. Damodaran's static spread table maps ratings to default spreads — no FRED API or live spread data needed.

**Why not live spreads from FRED?** In normal markets, Damodaran's annual table and FRED OAS spreads differ by ~3 basis points (BBB: 1.11% table vs 1.14% FRED in March 2026). The difference only becomes material during credit crises. The static table avoids a new API dependency for negligible accuracy gain.

**Why not synthetic-only?** Damodaran's actual hierarchy is: market bond yields > agency ratings > synthetic. Synthetic relies on a single ratio (interest coverage) and was designed as a fallback for unrated firms. For the large-cap companies we typically analyze, actual ratings are freely available via web search and are the better input.

---

## Design

### 1. Data layer (`metrics.py`)

**New extractions in `extract_dcf_inputs()`:**

- `interest_expense`: from latest annual income statement (`interestExpense` field)
- `interest_coverage`: `operating_income / interest_expense`

**New function: `get_synthetic_rating()`**

Takes interest coverage ratio and market cap, returns:
```python
{
    "rating": str,           # e.g. "Aaa/AAA"
    "default_spread": float, # e.g. 0.004
    "coverage_ratio": float, # e.g. 57.2
    "firm_size": str,        # "large" or "small"
}
```

Auto-selects large-firm or small-firm lookup table based on market cap (threshold: $5B per Damodaran).

**New function: `get_spread_for_rating()`**

Takes an actual rating string (e.g., "AA+", "Aa2", "AAA"), returns the default spread from Damodaran's table. Handles both S&P and Moody's notation. Returns None if the rating string isn't recognized.

**Populate existing `interest_coverage` field** in `CompanyMetrics` (currently always None).

**Edge cases:**
- Zero interest expense (debt-free company) → coverage = +inf → AAA → 0.40% spread
- Negative operating income → negative coverage → D rating → 19.00% spread
- Missing interest expense data → return None for all synthetic fields

### 2. Lookup tables (in `metrics.py`)

Two module-level constants, sourced from Damodaran's published tables.

**Large firms (market cap >= $5B) — January 2026:**

| Min Coverage | Max Coverage | Rating | Spread |
|---|---|---|---|
| 8.50 | +inf | Aaa/AAA | 0.40% |
| 6.50 | 8.50 | Aa2/AA | 0.55% |
| 5.50 | 6.50 | A1/A+ | 0.70% |
| 4.25 | 5.50 | A2/A | 0.78% |
| 3.00 | 4.25 | A3/A- | 0.89% |
| 2.50 | 3.00 | Baa2/BBB | 1.11% |
| 2.25 | 2.50 | Ba1/BB+ | 1.38% |
| 2.00 | 2.25 | Ba2/BB | 1.84% |
| 1.75 | 2.00 | B1/B+ | 2.75% |
| 1.50 | 1.75 | B2/B | 3.21% |
| 1.25 | 1.50 | B3/B- | 5.09% |
| 0.80 | 1.25 | Caa/CCC | 8.85% |
| 0.65 | 0.80 | Ca2/CC | 12.61% |
| 0.20 | 0.65 | C2/C | 16.00% |
| -inf | 0.20 | D2/D | 19.00% |

Source: https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/ratings.html

**Small firms (market cap < $5B) — January 2017:**

| Min Coverage | Max Coverage | Rating | Spread |
|---|---|---|---|
| 12.50 | +inf | Aaa/AAA | 0.60% |
| 9.50 | 12.50 | Aa2/AA | 0.80% |
| 7.50 | 9.50 | A1/A+ | 1.00% |
| 6.00 | 7.50 | A2/A | 1.10% |
| 4.50 | 6.00 | A3/A- | 1.25% |
| 4.00 | 4.50 | Baa2/BBB | 1.60% |
| 3.50 | 4.00 | Ba1/BB+ | 2.50% |
| 3.00 | 3.50 | Ba2/BB | 3.00% |
| 2.50 | 3.00 | B1/B+ | 3.75% |
| 2.00 | 2.50 | B2/B | 4.50% |
| 1.50 | 2.00 | B3/B- | 5.50% |
| 1.25 | 1.50 | Caa/CCC | 6.50% |
| 0.80 | 1.25 | Ca2/CC | 8.00% |
| 0.50 | 0.80 | C2/C | 10.50% |
| -inf | 0.50 | D2/D | 14.00% |

Source: https://pages.stern.nyu.edu/adamodar/New_Home_Page/datafile/smallrating.htm

**Actual rating → spread mapping dict:**

Maps common S&P and Moody's notations to the corresponding spread from the large-firm table. Sub-notches within a Damodaran bucket (e.g., AA+, AA, AA-) map to the same spread. Always uses large-firm spreads — the actual agency rating already incorporates firm size, so applying the small-firm spread table would double-count the size penalty. The small-firm table is only used for synthetic ratings (where coverage ratio alone doesn't capture size risk).

```python
RATING_TO_SPREAD = {
    # S&P → spread (large-firm table)
    "AAA": 0.0040,
    "AA+": 0.0055, "AA": 0.0055, "AA-": 0.0055,
    "A+": 0.0070, "A": 0.0078, "A-": 0.0089,
    "BBB+": 0.0111, "BBB": 0.0111, "BBB-": 0.0111,
    "BB+": 0.0138, "BB": 0.0184, "BB-": 0.0184,
    "B+": 0.0275, "B": 0.0321, "B-": 0.0509,
    "CCC": 0.0885, "CC": 0.1261, "C": 0.1600, "D": 0.1900,
    # Moody's equivalents
    "Aaa": 0.0040,
    "Aa1": 0.0055, "Aa2": 0.0055, "Aa3": 0.0055,
    "A1": 0.0070, "A2": 0.0078, "A3": 0.0089,
    "Baa1": 0.0111, "Baa2": 0.0111, "Baa3": 0.0111,
    "Ba1": 0.0138, "Ba2": 0.0184, "Ba3": 0.0184,
    "B1": 0.0275, "B2": 0.0321, "B3": 0.0509,
    "Caa1": 0.0885, "Caa2": 0.0885, "Caa3": 0.0885,
    "Ca": 0.1261,
}
```

**Update cadence:** Swap tables when Damodaran publishes his annual January update. Comment at the top notes the source URL and date.

### 3. Calibrate skill flow

**Step 2 (mechanical assumptions) — cost of debt section:**

Replace the current `interest_expense / total_debt` logic with:

1. Read synthetic rating from financial data (computed by `metrics.py`)
2. Web search for actual credit rating: `"{company_name} credit rating S&P Moody's"`
3. If actual rating found, use `get_spread_for_rating()` to get spread; compute cost of debt = risk-free rate + spread
4. If no actual rating found, use synthetic cost of debt from financial data
5. Display results (see formats below)
6. Set `cost_of_debt` in assumptions

**Display formats:**

Actual rating found, consistent with synthetic:
```
Cost of debt: 4.9% (Aaa/AAA — Moody's, spread 0.40%)
  Synthetic cross-check: Aaa/AAA (coverage 57.2x) — consistent
```

Actual rating found, diverges from synthetic:
```
Cost of debt: 5.5% (Aa2/AA — Moody's, spread 0.55%)
  Synthetic cross-check: A1/A+ (coverage 6.1x) — diverges
  Note: actual rating considers factors beyond interest coverage
```

No actual rating found (unrated company):
```
Cost of debt: 5.6% (synthetic A1/A+, coverage 6.1x, spread 0.70%)
  No agency rating found — using synthetic
```

Manual override preserved:
```
Cost of debt: keeping manual override at 6.0% (Aaa/AAA suggests 4.9%)
```

**Auto mode:** Skip web search, use synthetic only:
```
Cost of debt: 4.9% (synthetic Aaa/AAA, coverage 57.2x — auto mode, no rating lookup)
```

**Drop the legacy `interest_expense / total_debt` heuristic entirely.**

### 4. DCF model (`dcf.py`)

**No changes.** Cost of debt is already a float in `DCFAssumptions`. Calibrate sets it; the model consumes it. The rating derivation is a calibration concern, not a model concern.

### 5. Assumption storage

**No new fields in `DCFAssumptions` or `assumptions.json`.** The synthetic rating, spread, and coverage ratio are computed on the fly from financial data. Only the resulting `cost_of_debt` float is persisted.

### 6. Tests

**`tests/test_metrics.py` additions:**

- `test_interest_coverage_computation` — operating income / interest expense
- `test_synthetic_rating_large_firm` — coverage maps to correct rating (large table)
- `test_synthetic_rating_small_firm` — same coverage yields different rating (small table)
- `test_synthetic_rating_market_cap_threshold` — $10B vs $2B firm
- `test_synthetic_rating_zero_interest_expense` — debt-free → AAA
- `test_synthetic_rating_negative_ebit` — unprofitable → D
- `test_synthetic_rating_missing_data` — returns None
- `test_spread_for_actual_rating` — S&P and Moody's notation both work
- `test_spread_for_unknown_rating` — returns None
- `test_synthetic_cost_of_debt` — risk-free + spread
- `test_interest_coverage_in_company_metrics` — field now populated

**No new tests in `test_dcf.py`** — cost_of_debt consumption is already covered.

### 7. Doc updates

- `docs/dcf-methodology.md`: update cost of debt section — rating-based approach, Damodaran hierarchy, synthetic fallback
- `docs/internal/damodaran-audit.md`: mark item #11 DONE, update summary table
- `skills/calibrate/SKILL.md`: replace interest_expense/total_debt logic with rating-based flow

---

## Out of scope

- FRED live OAS spreads (future enhancement if needed)
- Financial services company detection (audit item #15)
- Bottom-up beta (audit item #9)
- Implied ERP (audit item #10)

## References

- [Damodaran: Ratings, Coverage Ratios and Default Spreads (large firms)](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/ratings.html)
- [Damodaran: Small Firm Ratings](https://pages.stern.nyu.edu/adamodar/New_Home_Page/datafile/smallrating.htm)
- [Damodaran: Estimating a Synthetic Rating](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/valquestions/syntrating.htm)
- [Damodaran: Riskfree Rates and Default Spreads (PDF)](https://pages.stern.nyu.edu/~adamodar/pdfiles/cfovhds/Riskfree&spread.pdf)
