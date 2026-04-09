# Synthetic Credit Rating Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the broken `interest_expense / total_debt` cost of debt heuristic with Damodaran's rating-based approach (actual rating primary, synthetic fallback).

**Architecture:** Two new functions in `metrics.py` (`get_synthetic_rating`, `get_spread_for_rating`) plus lookup tables. Calibrate skill updated to web search for actual rating, use synthetic as fallback. No changes to `dcf.py` — cost of debt remains a float in `DCFAssumptions`.

**Tech Stack:** Python 3, pytest, no new dependencies.

**Spec:** `docs/internal/2026-04-08-synthetic-credit-rating-design.md`

---

### Task 1: Add lookup tables to `metrics.py`

**Files:**
- Modify: `stock_analyzer/metrics.py` (add after line 9, before the `CompanyMetrics` class)

- [ ] **Step 1: Add the Damodaran spread tables as module-level constants**

Add after the imports (line 9), before the `CompanyMetrics` class (line 12):

```python
# Damodaran's synthetic credit rating tables
# Source: https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/ratings.html
# Updated: January 2026 (large firms), January 2017 (small firms)
# Format: (min_coverage, rating, spread)
# Sorted descending by coverage threshold — first match wins.

SYNTHETIC_RATING_TABLE_LARGE = [
    (8.50, "Aaa/AAA", 0.0040),
    (6.50, "Aa2/AA",  0.0055),
    (5.50, "A1/A+",   0.0070),
    (4.25, "A2/A",    0.0078),
    (3.00, "A3/A-",   0.0089),
    (2.50, "Baa2/BBB", 0.0111),
    (2.25, "Ba1/BB+", 0.0138),
    (2.00, "Ba2/BB",  0.0184),
    (1.75, "B1/B+",   0.0275),
    (1.50, "B2/B",    0.0321),
    (1.25, "B3/B-",   0.0509),
    (0.80, "Caa/CCC", 0.0885),
    (0.65, "Ca2/CC",  0.1261),
    (0.20, "C2/C",    0.1600),
]
SYNTHETIC_RATING_DEFAULT_LARGE = ("D2/D", 0.1900)

SYNTHETIC_RATING_TABLE_SMALL = [
    (12.50, "Aaa/AAA", 0.0060),
    (9.50,  "Aa2/AA",  0.0080),
    (7.50,  "A1/A+",   0.0100),
    (6.00,  "A2/A",    0.0110),
    (4.50,  "A3/A-",   0.0125),
    (4.00,  "Baa2/BBB", 0.0160),
    (3.50,  "Ba1/BB+", 0.0250),
    (3.00,  "Ba2/BB",  0.0300),
    (2.50,  "B1/B+",   0.0375),
    (2.00,  "B2/B",    0.0450),
    (1.50,  "B3/B-",   0.0550),
    (1.25,  "Caa/CCC", 0.0650),
    (0.80,  "Ca2/CC",  0.0800),
    (0.50,  "C2/C",    0.1050),
]
SYNTHETIC_RATING_DEFAULT_SMALL = ("D2/D", 0.1400)

SMALL_FIRM_MARKET_CAP_THRESHOLD = 5_000_000_000  # $5B

# Actual credit rating to default spread mapping (large-firm spreads).
# Agency ratings already incorporate firm size, so large-firm spreads are
# appropriate regardless of market cap. Sub-notches within a Damodaran
# bucket map to the same spread.
RATING_TO_SPREAD = {
    # S&P notation
    "AAA": 0.0040,
    "AA+": 0.0055, "AA": 0.0055, "AA-": 0.0055,
    "A+": 0.0070,  "A": 0.0078,  "A-": 0.0089,
    "BBB+": 0.0111, "BBB": 0.0111, "BBB-": 0.0111,
    "BB+": 0.0138, "BB": 0.0184, "BB-": 0.0184,
    "B+": 0.0275,  "B": 0.0321,  "B-": 0.0509,
    "CCC": 0.0885, "CC": 0.1261, "C": 0.1600, "D": 0.1900,
    # Moody's notation
    "Aaa": 0.0040,
    "Aa1": 0.0055, "Aa2": 0.0055, "Aa3": 0.0055,
    "A1": 0.0070,  "A2": 0.0078,  "A3": 0.0089,
    "Baa1": 0.0111, "Baa2": 0.0111, "Baa3": 0.0111,
    "Ba1": 0.0138, "Ba2": 0.0184, "Ba3": 0.0184,
    "B1": 0.0275,  "B2": 0.0321,  "B3": 0.0509,
    "Caa1": 0.0885, "Caa2": 0.0885, "Caa3": 0.0885,
    "Ca": 0.1261,
}
```

- [ ] **Step 2: Verify the module still imports cleanly**

Run: `cd /Users/kaichen/Projects/intrinsic && PYTHONPATH=. python3 -c "from stock_analyzer.metrics import SYNTHETIC_RATING_TABLE_LARGE, RATING_TO_SPREAD; print(f'Large table: {len(SYNTHETIC_RATING_TABLE_LARGE)} rows, rating dict: {len(RATING_TO_SPREAD)} entries')"`

Expected: `Large table: 14 rows, rating dict: 34 entries`

- [ ] **Step 3: Commit**

```bash
git add stock_analyzer/metrics.py
git commit -m "Add Damodaran synthetic rating lookup tables (audit #11)

Large-firm table (Jan 2026) and small-firm table (Jan 2017) from
Damodaran's published datasets. Also adds actual rating-to-spread
mapping dict for S&P and Moody's notation."
```

---

### Task 2: Implement `get_synthetic_rating()` with TDD

**Files:**
- Modify: `stock_analyzer/metrics.py` (add function after lookup tables, before `CompanyMetrics` class)
- Modify: `tests/test_metrics.py` (add new test class)

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_metrics.py`, after the existing imports on line 2:

```python
from stock_analyzer.metrics import (
    FinancialMetrics, CompanyMetrics,
    get_synthetic_rating, get_spread_for_rating,
    SYNTHETIC_RATING_TABLE_LARGE, RATING_TO_SPREAD,
)
```

Replace the existing import line:
```python
from stock_analyzer.metrics import FinancialMetrics, CompanyMetrics
```

Then add a new test class after the `TestCalculateDCFInputs` class (after line 221):

```python
# --- Synthetic Credit Rating ---

class TestGetSyntheticRating:
    def test_large_firm_aaa(self):
        """Coverage > 8.5 for large firm → Aaa/AAA"""
        result = get_synthetic_rating(coverage_ratio=57.2, market_cap=100e9)
        assert result['rating'] == 'Aaa/AAA'
        assert result['default_spread'] == 0.0040
        assert result['firm_size'] == 'large'

    def test_large_firm_bbb(self):
        """Coverage 2.5-3.0 for large firm → Baa2/BBB"""
        result = get_synthetic_rating(coverage_ratio=2.7, market_cap=10e9)
        assert result['rating'] == 'Baa2/BBB'
        assert result['default_spread'] == 0.0111

    def test_large_firm_boundary_exact(self):
        """Exact boundary value (8.50) → Aaa/AAA (inclusive lower bound)"""
        result = get_synthetic_rating(coverage_ratio=8.50, market_cap=10e9)
        assert result['rating'] == 'Aaa/AAA'

    def test_large_firm_just_below_boundary(self):
        """Just below 8.50 → Aa2/AA"""
        result = get_synthetic_rating(coverage_ratio=8.49, market_cap=10e9)
        assert result['rating'] == 'Aa2/AA'

    def test_small_firm_same_coverage_different_rating(self):
        """Same coverage (9.0) yields A1/A+ for small firm but Aaa/AAA for large"""
        large = get_synthetic_rating(coverage_ratio=9.0, market_cap=10e9)
        small = get_synthetic_rating(coverage_ratio=9.0, market_cap=3e9)
        assert large['rating'] == 'Aaa/AAA'
        assert small['rating'] == 'A1/A+'

    def test_small_firm_higher_spread(self):
        """Small firm AAA spread (0.60%) > large firm AAA spread (0.40%)"""
        small = get_synthetic_rating(coverage_ratio=13.0, market_cap=3e9)
        large = get_synthetic_rating(coverage_ratio=13.0, market_cap=10e9)
        assert small['default_spread'] == 0.0060
        assert large['default_spread'] == 0.0040

    def test_market_cap_threshold(self):
        """$5B is the cutoff — at $5B use large table, below use small"""
        at_threshold = get_synthetic_rating(coverage_ratio=9.0, market_cap=5e9)
        below_threshold = get_synthetic_rating(coverage_ratio=9.0, market_cap=4.99e9)
        assert at_threshold['firm_size'] == 'large'
        assert below_threshold['firm_size'] == 'small'

    def test_zero_interest_expense_infinite_coverage(self):
        """Debt-free company (infinite coverage) → AAA"""
        result = get_synthetic_rating(coverage_ratio=float('inf'), market_cap=10e9)
        assert result['rating'] == 'Aaa/AAA'
        assert result['default_spread'] == 0.0040

    def test_negative_coverage_d_rating(self):
        """Negative EBIT → negative coverage → D rating"""
        result = get_synthetic_rating(coverage_ratio=-2.0, market_cap=10e9)
        assert result['rating'] == 'D2/D'
        assert result['default_spread'] == 0.1900

    def test_zero_coverage_d_rating(self):
        """Zero coverage → D rating"""
        result = get_synthetic_rating(coverage_ratio=0.0, market_cap=10e9)
        assert result['rating'] == 'D2/D'

    def test_returns_coverage_ratio(self):
        """Result includes the input coverage ratio"""
        result = get_synthetic_rating(coverage_ratio=5.0, market_cap=10e9)
        assert result['coverage_ratio'] == 5.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/kaichen/Projects/intrinsic && python -m pytest tests/test_metrics.py::TestGetSyntheticRating -v`

Expected: FAIL — `ImportError: cannot import name 'get_synthetic_rating'`

- [ ] **Step 3: Implement `get_synthetic_rating()`**

Add to `stock_analyzer/metrics.py`, after the lookup table constants, before the `CompanyMetrics` class:

```python
def get_synthetic_rating(coverage_ratio: float, market_cap: float) -> dict:
    """
    Map interest coverage ratio to synthetic credit rating and default spread.

    Uses Damodaran's lookup tables, auto-selecting large-firm or small-firm
    table based on market cap (threshold: $5B).

    Args:
        coverage_ratio: EBIT / Interest Expense
        market_cap: Company market capitalization in dollars

    Returns:
        Dict with 'rating', 'default_spread', 'coverage_ratio', 'firm_size'
    """
    if market_cap >= SMALL_FIRM_MARKET_CAP_THRESHOLD:
        table = SYNTHETIC_RATING_TABLE_LARGE
        default = SYNTHETIC_RATING_DEFAULT_LARGE
        firm_size = "large"
    else:
        table = SYNTHETIC_RATING_TABLE_SMALL
        default = SYNTHETIC_RATING_DEFAULT_SMALL
        firm_size = "small"

    for min_coverage, rating, spread in table:
        if coverage_ratio >= min_coverage:
            return {
                "rating": rating,
                "default_spread": spread,
                "coverage_ratio": coverage_ratio,
                "firm_size": firm_size,
            }

    rating, spread = default
    return {
        "rating": rating,
        "default_spread": spread,
        "coverage_ratio": coverage_ratio,
        "firm_size": firm_size,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/kaichen/Projects/intrinsic && python -m pytest tests/test_metrics.py::TestGetSyntheticRating -v`

Expected: All 11 tests PASS

- [ ] **Step 5: Commit**

```bash
git add stock_analyzer/metrics.py tests/test_metrics.py
git commit -m "Add get_synthetic_rating() with tests (audit #11)

Maps interest coverage ratio to Damodaran synthetic credit rating
and default spread. Auto-selects large/small firm table based on
market cap threshold ($5B)."
```

---

### Task 3: Implement `get_spread_for_rating()` with TDD

**Files:**
- Modify: `stock_analyzer/metrics.py` (add function after `get_synthetic_rating()`)
- Modify: `tests/test_metrics.py` (add new test class)

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_metrics.py`, after the `TestGetSyntheticRating` class:

```python
class TestGetSpreadForRating:
    def test_sp_aaa(self):
        assert get_spread_for_rating("AAA") == 0.0040

    def test_moodys_aaa(self):
        assert get_spread_for_rating("Aaa") == 0.0040

    def test_sp_aa_plus(self):
        assert get_spread_for_rating("AA+") == 0.0055

    def test_moodys_aa2(self):
        assert get_spread_for_rating("Aa2") == 0.0055

    def test_sp_a(self):
        assert get_spread_for_rating("A") == 0.0078

    def test_sp_bbb_minus(self):
        assert get_spread_for_rating("BBB-") == 0.0111

    def test_moodys_ba1(self):
        assert get_spread_for_rating("Ba1") == 0.0138

    def test_unknown_rating_returns_none(self):
        assert get_spread_for_rating("XYZ") is None

    def test_empty_string_returns_none(self):
        assert get_spread_for_rating("") is None

    def test_case_sensitive(self):
        """Ratings are case-sensitive — 'aaa' is not 'AAA'"""
        assert get_spread_for_rating("aaa") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/kaichen/Projects/intrinsic && python -m pytest tests/test_metrics.py::TestGetSpreadForRating -v`

Expected: FAIL — `ImportError: cannot import name 'get_spread_for_rating'`

- [ ] **Step 3: Implement `get_spread_for_rating()`**

Add to `stock_analyzer/metrics.py`, after `get_synthetic_rating()`:

```python
def get_spread_for_rating(rating: str) -> Optional[float]:
    """
    Map an actual credit rating to its default spread.

    Accepts both S&P (AAA, AA+, etc.) and Moody's (Aaa, Aa1, etc.) notation.
    Uses the large-firm spread table — agency ratings already incorporate
    firm size, so applying small-firm spreads would double-count the size penalty.

    Args:
        rating: Credit rating string (e.g., "AA+", "Aa2")

    Returns:
        Default spread as a decimal (e.g., 0.0055), or None if rating not recognized
    """
    return RATING_TO_SPREAD.get(rating)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/kaichen/Projects/intrinsic && python -m pytest tests/test_metrics.py::TestGetSpreadForRating -v`

Expected: All 10 tests PASS

- [ ] **Step 5: Commit**

```bash
git add stock_analyzer/metrics.py tests/test_metrics.py
git commit -m "Add get_spread_for_rating() with tests (audit #11)

Maps actual S&P/Moody's credit ratings to default spreads from
Damodaran's large-firm table."
```

---

### Task 4: Extract interest expense and compute interest coverage in `metrics.py`

**Files:**
- Modify: `stock_analyzer/metrics.py:112-184` (`calculate_dcf_inputs()` return dict)
- Modify: `tests/test_metrics.py` (add tests, update fixture)

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_metrics.py`, after the `TestGetSpreadForRating` class:

```python
class TestInterestCoverageAndSyntheticDebt:
    @pytest.fixture
    def statements_with_interest(self):
        income = [{
            'totalRevenue': '400000000000',
            'operatingIncome': '120000000000',
            'interestExpense': '2500000000',
        }]
        balance = [{
            'shortLongTermDebtTotal': '100000000000',
            'cashAndCashEquivalentsAtCarryingValue': '60000000000',
            'totalShareholderEquity': '200000000000',
            'totalAssets': '350000000000',
        }]
        overview = {'MarketCapitalization': '2500000000000', 'Beta': '1.2'}
        return income, balance, [{}], overview

    def test_interest_expense_extracted(self, statements_with_interest):
        income, balance, cashflow, overview = statements_with_interest
        inputs = FinancialMetrics.calculate_dcf_inputs(income, balance, cashflow, overview)
        assert inputs['interest_expense'] == 2_500_000_000

    def test_interest_coverage_computed(self, statements_with_interest):
        income, balance, cashflow, overview = statements_with_interest
        inputs = FinancialMetrics.calculate_dcf_inputs(income, balance, cashflow, overview)
        # 120B / 2.5B = 48.0
        assert inputs['interest_coverage'] == pytest.approx(48.0)

    def test_synthetic_rating_in_dcf_inputs(self, statements_with_interest):
        income, balance, cashflow, overview = statements_with_interest
        inputs = FinancialMetrics.calculate_dcf_inputs(income, balance, cashflow, overview)
        # Coverage 48.0, market cap $2.5T → large firm → Aaa/AAA
        assert inputs['synthetic_rating'] == 'Aaa/AAA'
        assert inputs['synthetic_spread'] == 0.0040

    def test_zero_interest_expense(self):
        """Debt-free company → infinite coverage → AAA"""
        income = [{'totalRevenue': '100000', 'operatingIncome': '30000',
                   'interestExpense': '0'}]
        balance = [{'totalShareholderEquity': '80000'}]
        inputs = FinancialMetrics.calculate_dcf_inputs(income, balance, [{}],
                    {'MarketCapitalization': '10000000000'})
        assert inputs['interest_coverage'] == float('inf')
        assert inputs['synthetic_rating'] == 'Aaa/AAA'

    def test_missing_interest_expense(self):
        """No interest expense field → None for all synthetic fields"""
        income = [{'totalRevenue': '100000', 'operatingIncome': '30000'}]
        balance = [{'totalShareholderEquity': '80000'}]
        inputs = FinancialMetrics.calculate_dcf_inputs(income, balance, [{}], {})
        assert inputs['interest_expense'] is None
        assert inputs['interest_coverage'] is None
        assert inputs['synthetic_rating'] is None
        assert inputs['synthetic_spread'] is None

    def test_negative_operating_income(self):
        """Negative EBIT → negative coverage → D rating"""
        income = [{'totalRevenue': '100000', 'operatingIncome': '-20000',
                   'interestExpense': '5000'}]
        balance = [{'totalShareholderEquity': '80000'}]
        inputs = FinancialMetrics.calculate_dcf_inputs(income, balance, [{}],
                    {'MarketCapitalization': '10000000000'})
        assert inputs['interest_coverage'] == pytest.approx(-4.0)
        assert inputs['synthetic_rating'] == 'D2/D'

    def test_small_firm_synthetic_rating(self):
        """Small firm ($2B) uses different table"""
        income = [{'totalRevenue': '5000000000', 'operatingIncome': '500000000',
                   'interestExpense': '100000000'}]
        balance = [{'totalShareholderEquity': '2000000000'}]
        inputs = FinancialMetrics.calculate_dcf_inputs(income, balance, [{}],
                    {'MarketCapitalization': '2000000000'})
        # Coverage = 5.0, market cap $2B → small firm → A3/A- (4.50-6.00 range)
        assert inputs['synthetic_rating'] == 'A3/A-'
        assert inputs['synthetic_spread'] == 0.0125
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/kaichen/Projects/intrinsic && python -m pytest tests/test_metrics.py::TestInterestCoverageAndSyntheticDebt -v`

Expected: FAIL — `KeyError: 'interest_expense'`

- [ ] **Step 3: Add interest expense extraction and synthetic rating to `calculate_dcf_inputs()`**

In `stock_analyzer/metrics.py`, in the `calculate_dcf_inputs()` method:

After the `operating_income` extraction (line 113), add:

```python
        interest_expense = safe_float(latest_income.get('interestExpense'))
```

Before the `return` statement (line 168), add the interest coverage and synthetic rating computation:

```python
        # Interest coverage and synthetic credit rating
        interest_coverage = None
        synthetic_rating = None
        synthetic_spread = None
        if interest_expense is not None and interest_expense > 0:
            interest_coverage = operating_income / interest_expense
            synthetic = get_synthetic_rating(interest_coverage, market_cap)
            synthetic_rating = synthetic['rating']
            synthetic_spread = synthetic['default_spread']
        elif interest_expense == 0:
            # Debt-free company — infinite coverage → best rating
            interest_coverage = float('inf')
            synthetic = get_synthetic_rating(float('inf'), market_cap)
            synthetic_rating = synthetic['rating']
            synthetic_spread = synthetic['default_spread']
        # else: interest_expense is None (missing data) → all stay None
```

Add to the return dict:

```python
            'interest_expense': interest_expense,
            'interest_coverage': interest_coverage,
            'synthetic_rating': synthetic_rating,
            'synthetic_spread': synthetic_spread,
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/kaichen/Projects/intrinsic && python -m pytest tests/test_metrics.py::TestInterestCoverageAndSyntheticDebt -v`

Expected: All 8 tests PASS

- [ ] **Step 5: Run all metrics tests to confirm nothing broke**

Run: `cd /Users/kaichen/Projects/intrinsic && python -m pytest tests/test_metrics.py -v`

Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add stock_analyzer/metrics.py tests/test_metrics.py
git commit -m "Add interest coverage and synthetic rating to DCF inputs (audit #11)

Extracts interestExpense from income statement, computes coverage ratio,
and maps to synthetic credit rating using Damodaran's tables. Returns
interest_expense, interest_coverage, synthetic_rating, synthetic_spread
in the DCF inputs dict."
```

---

### Task 5: Populate `interest_coverage` in `CompanyMetrics`

**Files:**
- Modify: `stock_analyzer/metrics.py:56-84` (`parse_alpha_vantage_overview()`)
- Modify: `tests/test_metrics.py` (update `TestParseOverview`)

Note: Alpha Vantage overview doesn't have interest coverage directly, but it does provide `EBITDA` and other fields. However, interest coverage requires income statement data (operating income / interest expense) which isn't in the overview. The `CompanyMetrics` field exists but can't be populated from the overview alone.

The better approach: populate it in `calculate_dcf_inputs()` and return it there (already done in Task 4). The `CompanyMetrics.interest_coverage` field stays as-is — it can be populated by any caller that has income statement data.

**Skip this task** — interest coverage is already computed and returned from `calculate_dcf_inputs()` (Task 4). The `CompanyMetrics` field doesn't need to change; it was already optional and designed for future use.

---

### Task 6: Update `__init__.py` exports

**Files:**
- Modify: `stock_analyzer/__init__.py`

- [ ] **Step 1: Check current exports**

Run: `cd /Users/kaichen/Projects/intrinsic && cat stock_analyzer/__init__.py`

- [ ] **Step 2: Add new function exports if `__init__.py` has explicit exports**

If `__init__.py` uses `__all__` or explicit imports, add `get_synthetic_rating` and `get_spread_for_rating`. If it's just a bare init or uses wildcard patterns, no changes needed.

- [ ] **Step 3: Verify imports work**

Run: `cd /Users/kaichen/Projects/intrinsic && PYTHONPATH=. python3 -c "from stock_analyzer.metrics import get_synthetic_rating, get_spread_for_rating; print('OK')"`

Expected: `OK`

- [ ] **Step 4: Commit (if changes were needed)**

```bash
git add stock_analyzer/__init__.py
git commit -m "Export synthetic rating functions from stock_analyzer"
```

---

### Task 7: Update calibrate skill

**Files:**
- Modify: `skills/calibrate/SKILL.md` (lines 23-26, 69-71)

- [ ] **Step 1: Update the assumption categories header**

Replace the current cost of debt line in the assumption categories section (line 24):

```
- Cost of Debt (interest expense / total debt)
```

With:

```
- Cost of Debt (from credit rating + Damodaran default spread)
```

- [ ] **Step 2: Replace the cost of debt section in Step 2 (mechanical assumptions)**

Replace lines 70-71 (the current cost of debt logic) with:

```markdown
- **Cost of Debt:** Derive from credit rating and Damodaran's default spread table.
  1. Read the synthetic rating from `calculate_dcf_inputs()` (fields: `synthetic_rating`, `synthetic_spread`, `interest_coverage`).
  2. **Web search** for the actual credit rating: search `"{company_name} credit rating S&P Moody's"`. Extract the rating if clearly stated (e.g., "Aaa", "AA+").
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
  5. Set `cost_of_debt` in assumptions to the computed value.
  - **Auto mode:** Skip web search, use synthetic only. Display: "Cost of debt: X.X% (synthetic Rating, coverage X.Xx — auto mode, no rating lookup)"
  - **Manual override:** If `cost_of_debt` is in `_manual_overrides`, keep the user's value: "Cost of debt: keeping manual override at X.X% (Rating suggests Y.Y%)"
```

- [ ] **Step 3: Verify the skill file is well-formed**

Read the full file and check that the markdown is valid and the step numbering is consistent.

- [ ] **Step 4: Commit**

```bash
git add skills/calibrate/SKILL.md
git commit -m "Update calibrate skill: rating-based cost of debt (audit #11)

Replace interest_expense/total_debt heuristic with Damodaran's approach:
web search for actual credit rating (primary), synthetic from interest
coverage (fallback), default spread from lookup table."
```

---

### Task 8: Update documentation

**Files:**
- Modify: `docs/dcf-methodology.md` (WACC section, Known limitations section)
- Modify: `docs/internal/damodaran-audit.md` (item #11 status)

- [ ] **Step 1: Update WACC section in dcf-methodology.md**

In `docs/dcf-methodology.md`, replace the line (line 153):

```
Rd = Pre-tax cost of debt      (default 5.0%)
```

With:

```
Rd = Pre-tax cost of debt      (from credit rating; see Cost of debt below)
```

- [ ] **Step 2: Add a Cost of debt section to dcf-methodology.md**

Add a new section after the WACC section (after line 167, before the Terminal value section). Insert before the `---` separator:

```markdown
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
```

- [ ] **Step 3: Update Known limitations in dcf-methodology.md**

Replace the "No synthetic credit rating" paragraph in the Known limitations section with:

```markdown
**Cost of debt approximation.** Cost of debt is derived from credit ratings (actual or synthetic) mapped to default spreads from Damodaran's annual lookup table. The synthetic approach relies solely on interest coverage ratio and may not capture all factors that rating agencies consider. The spread table is a January snapshot, not live market data — during credit crises, actual spreads may be significantly wider. For companies with complex capital structures (convertible debt, structured financing), the single-rating approach may not capture the true borrowing cost.
```

- [ ] **Step 4: Update damodaran-audit.md item #11 status**

In `docs/internal/damodaran-audit.md`, update the summary table row for item 11 (line 490):

```
| 11 | Synthetic credit rating (cost of debt) | 2 | MEDIUM | **DONE** | Rating-based cost of debt: actual rating primary, synthetic fallback, Damodaran spread table |
```

Also update the Phase 2 section text to note #11 is complete.

- [ ] **Step 5: Commit**

```bash
git add docs/dcf-methodology.md docs/internal/damodaran-audit.md
git commit -m "Update docs for rating-based cost of debt (audit #11)

Add cost of debt section to DCF methodology, update known limitations,
mark audit item #11 as DONE."
```

---

### Task 9: Run full test suite

**Files:** None (verification only)

- [ ] **Step 1: Run all tests**

Run: `cd /Users/kaichen/Projects/intrinsic && python -m pytest tests/ -v`

Expected: All tests PASS. No regressions from existing tests.

- [ ] **Step 2: Verify MSFT financial data works with new code**

Run: `cd /Users/kaichen/Projects/intrinsic && PYTHONPATH=. python3 -c "
from stock_analyzer.metrics import FinancialMetrics
from stock_analyzer.stock_manager import StockManager
import json

sm = StockManager()
data = sm.load_financial_data('MSFT')
income = data['data'].get('income_statement_annual', [])
balance = data['data'].get('balance_sheet', [])
cashflow = data['data'].get('cash_flow', [])
overview = data['data'].get('overview', {})

inputs = FinancialMetrics.calculate_dcf_inputs(income, balance, cashflow, overview)
print(f'Interest expense: \${inputs[\"interest_expense\"]/1e9:.1f}B')
print(f'Interest coverage: {inputs[\"interest_coverage\"]:.1f}x')
print(f'Synthetic rating: {inputs[\"synthetic_rating\"]}')
print(f'Default spread: {inputs[\"synthetic_spread\"]*100:.2f}%')
print(f'Cost of debt (Rf + spread): {(0.045 + inputs[\"synthetic_spread\"])*100:.1f}%')
"`

Expected output (approximately):
```
Interest expense: $2.4B
Interest coverage: ~50x
Synthetic rating: Aaa/AAA
Default spread: 0.40%
Cost of debt (Rf + spread): 4.9%
```

This confirms the new code produces the expected 4.9% cost of debt for MSFT, replacing the broken 2.1% heuristic.
