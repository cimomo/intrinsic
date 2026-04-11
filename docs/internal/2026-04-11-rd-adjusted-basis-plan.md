# R&D Adjusted-Basis Consistency Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make calibrate anchors, the DCF starting margin, and the S/C fallback all flow through on the adjusted basis so forward and reverse DCF stop mixing raw NOPAT with adjusted ROIC.

**Architecture:** Add two pre-computed adjusted fields (`adjusted_operating_margin`, `adjusted_sales_to_capital`) to `calculate_dcf_inputs()`. Swap two precedence chains in `dcf.py` to prefer those fields when present, falling back to raw when absent. Update calibrate step 6b/6c/7 and value step 2 to display adjusted-primary with raw in parentheses. No changes to DCF math, terminal value formula, reverse DCF algorithm, WACC, or equity bridge.

**Tech Stack:** Python 3.10+, pytest, Alpha Vantage data (already cached)

**Design spec:** `docs/internal/2026-04-11-rd-adjusted-basis-design.md`

---

## File Map

| File | Responsibility | Change type |
|---|---|---|
| `stock_analyzer/metrics.py` | Compute adjusted margin and adjusted S/C inside existing R&D capitalization block | Modify (add ~10 lines) |
| `stock_analyzer/dcf.py` | Prefer adjusted fields in margin derivation and S/C fallback | Modify (2 precedence chains) |
| `tests/test_metrics.py` | Unit tests for the two new fields | Modify (add to existing `TestDCFInputsRdCapitalization` class) |
| `tests/test_dcf.py` | Integration tests for DCF precedence and forward/reverse consistency | Modify (add new `TestRdAdjustedBasis` class at end) |
| `skills/calibrate/SKILL.md` | Step 6b, 6c, 7 display and wording | Modify (prose) |
| `skills/value/SKILL.md` | Step 2 metrics table display | Modify (prose) |
| `docs/internal/damodaran-audit.md` | Item #13 status note | Modify (note second-pass fix) |

Task ordering: metrics layer first (Tasks 1-2), then DCF layer (Tasks 3-4), then end-to-end sanity (Task 5), then skill prose (Tasks 6-9), then audit doc (Task 10). Each task is a green-test commit, no broken intermediate states.

---

### Task 1: Add `adjusted_operating_margin` to `calculate_dcf_inputs()`

**Files:**
- Modify: `stock_analyzer/metrics.py` (R&D capitalization block at lines 454-479 and return dict at lines 481-507)
- Test: `tests/test_metrics.py` (add to `TestDCFInputsRdCapitalization` class at line 709+)

- [ ] **Step 1: Write failing tests**

Add to `tests/test_metrics.py` inside the existing `TestDCFInputsRdCapitalization` class (after the existing tests, before the end of the class):

```python
    def test_adjusted_operating_margin_present(self, statements_with_rd):
        income, income_annual, balance, cashflow, overview = statements_with_rd
        inputs = FinancialMetrics.calculate_dcf_inputs(
            income, balance, cashflow, overview, income_annual=income_annual
        )
        assert "adjusted_operating_margin" in inputs
        assert inputs["adjusted_operating_margin"] is not None

    def test_adjusted_operating_margin_value(self, statements_with_rd):
        """Adjusted margin = (EBIT + R&D - Amort) / Revenue"""
        income, income_annual, balance, cashflow, overview = statements_with_rd
        inputs = FinancialMetrics.calculate_dcf_inputs(
            income, balance, cashflow, overview, income_annual=income_annual
        )
        # Fixture: EBIT=80B, Revenue=200B, current R&D=30B, prior R&D=25B and 20B, 3-year life
        # Amortization = (25B + 20B) / 3 = 15B (limited history — year -3 data not in fixture)
        # Adjusted EBIT = 80 + 30 - 15 = 95B
        # Adjusted margin = 95 / 200 = 0.475
        assert inputs["adjusted_operating_margin"] == pytest.approx(0.475, rel=1e-4)

    def test_adjusted_operating_margin_none_when_no_rd(self, statements_with_rd):
        income, _, balance, cashflow, overview = statements_with_rd
        inputs = FinancialMetrics.calculate_dcf_inputs(income, balance, cashflow, overview)
        assert inputs["adjusted_operating_margin"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/kaichen/Projects/intrinsic && python -m pytest tests/test_metrics.py::TestDCFInputsRdCapitalization::test_adjusted_operating_margin_present tests/test_metrics.py::TestDCFInputsRdCapitalization::test_adjusted_operating_margin_value tests/test_metrics.py::TestDCFInputsRdCapitalization::test_adjusted_operating_margin_none_when_no_rd -v`

Expected: FAIL with `KeyError: 'adjusted_operating_margin'` or `assert 'adjusted_operating_margin' in inputs` assertion error.

- [ ] **Step 3: Implement the new field**

In `stock_analyzer/metrics.py`, inside `calculate_dcf_inputs()`, modify the R&D capitalization block (around line 454-479) to compute `adjusted_operating_margin`.

Find this block:

```python
        # R&D capitalization (Damodaran methodology)
        adjusted_roic = None
        adjusted_invested_capital = None
        research_asset = None
        rd_amortization = None
        current_rd = None
        rd_amortizable_life = None

        if income_annual:
            sector = overview.get("Sector")
            industry = overview.get("Industry")
            rd_life = get_rd_amortizable_life(sector, industry)
            rd_cap = calculate_rd_capitalization(income_annual, rd_life)

            if rd_cap and rd_cap["research_asset"] > 0:
                research_asset = rd_cap["research_asset"]
                rd_amortization = rd_cap["amortization"]
                current_rd = rd_cap["current_rd"]
                rd_amortizable_life = rd_life

                adjusted_ic = invested_capital + research_asset
                if adjusted_ic > 0:
                    nopat_raw = operating_income * (1 - tax_rate)
                    adjusted_nopat = nopat_raw + rd_cap["adjusted_nopat_delta"]
                    adjusted_roic = adjusted_nopat / adjusted_ic
                    adjusted_invested_capital = adjusted_ic
```

Replace with (adding `adjusted_operating_margin` initialization and computation):

```python
        # R&D capitalization (Damodaran methodology)
        adjusted_roic = None
        adjusted_invested_capital = None
        adjusted_operating_margin = None
        research_asset = None
        rd_amortization = None
        current_rd = None
        rd_amortizable_life = None

        if income_annual:
            sector = overview.get("Sector")
            industry = overview.get("Industry")
            rd_life = get_rd_amortizable_life(sector, industry)
            rd_cap = calculate_rd_capitalization(income_annual, rd_life)

            if rd_cap and rd_cap["research_asset"] > 0:
                research_asset = rd_cap["research_asset"]
                rd_amortization = rd_cap["amortization"]
                current_rd = rd_cap["current_rd"]
                rd_amortizable_life = rd_life

                adjusted_ic = invested_capital + research_asset
                if adjusted_ic > 0:
                    nopat_raw = operating_income * (1 - tax_rate)
                    adjusted_nopat = nopat_raw + rd_cap["adjusted_nopat_delta"]
                    adjusted_roic = adjusted_nopat / adjusted_ic
                    adjusted_invested_capital = adjusted_ic

                    # Adjusted operating margin: pre-tax economic margin
                    # = (EBIT + R&D - Amort) / Revenue, where (R&D - Amort) = adjusted_nopat_delta
                    adjusted_operating_income = operating_income + rd_cap["adjusted_nopat_delta"]
                    if revenue > 0:
                        adjusted_operating_margin = adjusted_operating_income / revenue
```

Then add `adjusted_operating_margin` to the return dict. Find:

```python
            'adjusted_roic': adjusted_roic,
            'adjusted_invested_capital': adjusted_invested_capital,
            'research_asset': research_asset,
```

Replace with:

```python
            'adjusted_roic': adjusted_roic,
            'adjusted_invested_capital': adjusted_invested_capital,
            'adjusted_operating_margin': adjusted_operating_margin,
            'research_asset': research_asset,
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/kaichen/Projects/intrinsic && python -m pytest tests/test_metrics.py::TestDCFInputsRdCapitalization -v`

Expected: All tests PASS including the three new ones. Run the whole metrics test file to confirm no regressions:

Run: `cd /Users/kaichen/Projects/intrinsic && python -m pytest tests/test_metrics.py -v`

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add stock_analyzer/metrics.py tests/test_metrics.py
git commit -m "$(cat <<'EOF'
Add adjusted_operating_margin to calculate_dcf_inputs output

Pre-computed economic operating margin (raw EBIT plus R&D capitalization
delta, divided by revenue) used as the anchor in calibrate and as the
DCF's starting-margin source. None when no R&D data is available.
EOF
)"
```

---

### Task 2: Add `adjusted_sales_to_capital` to `calculate_dcf_inputs()`

**Files:**
- Modify: `stock_analyzer/metrics.py` (same R&D capitalization block, same return dict)
- Test: `tests/test_metrics.py` (add to `TestDCFInputsRdCapitalization`)

- [ ] **Step 1: Write failing tests**

Add to `tests/test_metrics.py` inside `TestDCFInputsRdCapitalization`, after the tests from Task 1:

```python
    def test_adjusted_sales_to_capital_present(self, statements_with_rd):
        income, income_annual, balance, cashflow, overview = statements_with_rd
        inputs = FinancialMetrics.calculate_dcf_inputs(
            income, balance, cashflow, overview, income_annual=income_annual
        )
        assert "adjusted_sales_to_capital" in inputs
        assert inputs["adjusted_sales_to_capital"] is not None

    def test_adjusted_sales_to_capital_value(self, statements_with_rd):
        """Adjusted S/C = Revenue / Adjusted Invested Capital"""
        income, income_annual, balance, cashflow, overview = statements_with_rd
        inputs = FinancialMetrics.calculate_dcf_inputs(
            income, balance, cashflow, overview, income_annual=income_annual
        )
        expected = inputs["revenue"] / inputs["adjusted_invested_capital"]
        assert inputs["adjusted_sales_to_capital"] == pytest.approx(expected, rel=1e-9)

    def test_adjusted_sales_to_capital_none_when_no_rd(self, statements_with_rd):
        income, _, balance, cashflow, overview = statements_with_rd
        inputs = FinancialMetrics.calculate_dcf_inputs(income, balance, cashflow, overview)
        assert inputs["adjusted_sales_to_capital"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/kaichen/Projects/intrinsic && python -m pytest tests/test_metrics.py::TestDCFInputsRdCapitalization::test_adjusted_sales_to_capital_present tests/test_metrics.py::TestDCFInputsRdCapitalization::test_adjusted_sales_to_capital_value tests/test_metrics.py::TestDCFInputsRdCapitalization::test_adjusted_sales_to_capital_none_when_no_rd -v`

Expected: FAIL with missing field.

- [ ] **Step 3: Implement the new field**

In `stock_analyzer/metrics.py`, in the same R&D capitalization block modified in Task 1, add `adjusted_sales_to_capital` initialization and computation.

Find (this now includes the `adjusted_operating_margin` additions from Task 1):

```python
        # R&D capitalization (Damodaran methodology)
        adjusted_roic = None
        adjusted_invested_capital = None
        adjusted_operating_margin = None
        research_asset = None
```

Replace with:

```python
        # R&D capitalization (Damodaran methodology)
        adjusted_roic = None
        adjusted_invested_capital = None
        adjusted_operating_margin = None
        adjusted_sales_to_capital = None
        research_asset = None
```

Find (inside the inner `if adjusted_ic > 0:` block):

```python
                    # Adjusted operating margin: pre-tax economic margin
                    # = (EBIT + R&D - Amort) / Revenue, where (R&D - Amort) = adjusted_nopat_delta
                    adjusted_operating_income = operating_income + rd_cap["adjusted_nopat_delta"]
                    if revenue > 0:
                        adjusted_operating_margin = adjusted_operating_income / revenue
```

Replace with:

```python
                    # Adjusted operating margin: pre-tax economic margin
                    # = (EBIT + R&D - Amort) / Revenue, where (R&D - Amort) = adjusted_nopat_delta
                    adjusted_operating_income = operating_income + rd_cap["adjusted_nopat_delta"]
                    if revenue > 0:
                        adjusted_operating_margin = adjusted_operating_income / revenue

                    # Adjusted sales-to-capital: revenue per unit of adjusted capital
                    adjusted_sales_to_capital = revenue / adjusted_ic
```

Then add `adjusted_sales_to_capital` to the return dict. Find:

```python
            'adjusted_roic': adjusted_roic,
            'adjusted_invested_capital': adjusted_invested_capital,
            'adjusted_operating_margin': adjusted_operating_margin,
            'research_asset': research_asset,
```

Replace with:

```python
            'adjusted_roic': adjusted_roic,
            'adjusted_invested_capital': adjusted_invested_capital,
            'adjusted_operating_margin': adjusted_operating_margin,
            'adjusted_sales_to_capital': adjusted_sales_to_capital,
            'research_asset': research_asset,
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/kaichen/Projects/intrinsic && python -m pytest tests/test_metrics.py -v`

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add stock_analyzer/metrics.py tests/test_metrics.py
git commit -m "$(cat <<'EOF'
Add adjusted_sales_to_capital to calculate_dcf_inputs output

Pre-computed revenue-per-adjusted-capital ratio, used as the anchor
in calibrate step 6c and as the DCF's S/C fallback source. None when
no R&D data is available.
EOF
)"
```

---

### Task 3: `dcf.py` prefers `adjusted_operating_margin` for starting margin

**Files:**
- Modify: `stock_analyzer/dcf.py` (margin derivation at line 407-410)
- Test: `tests/test_dcf.py` (add new class `TestRdAdjustedBasis` at end of file)

- [ ] **Step 1: Write failing test**

Add to the end of `tests/test_dcf.py`:

```python


class TestRdAdjustedBasis:
    """Tests for R&D adjusted-basis consistency — DCF prefers adjusted fields when present."""

    @pytest.fixture
    def adjusted_financial_data(self):
        """Financial data with both raw and adjusted fields populated."""
        return {
            'revenue': 200_000_000_000,
            'operating_income': 80_000_000_000,      # raw: 40% margin
            'total_debt': 50_000_000_000,
            'cash': 20_000_000_000,
            'short_term_investments': 10_000_000_000,
            'long_term_investments': 5_000_000_000,
            'equity': 100_000_000_000,
            'market_cap': 2_000_000_000_000,
            'beta': 1.1,
            'adjusted_operating_margin': 0.475,      # 47.5% economic margin
            'adjusted_sales_to_capital': 1.35,       # derived elsewhere
            'adjusted_invested_capital': 140_000_000_000,
        }

    def test_dcf_uses_adjusted_operating_margin_when_present(self, adjusted_financial_data):
        """Year-1 margin should be 47.5% (adjusted), not 40% (raw EBIT/Revenue)."""
        assumptions = DCFAssumptions(
            revenue_growth_rate=0.10,
            terminal_growth_rate=0.04,
            sales_to_capital_ratio=1.0,  # pinned so we isolate margin
            terminal_roic=0.15,
        )
        model = DCFModel(assumptions)
        result = model.calculate_fair_value(adjusted_financial_data, shares_outstanding=1e10, current_price=100.0, verbose=True)
        # The result dict exposes the base operating margin used
        assert result['operating_margin'] == pytest.approx(0.475, rel=1e-9)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/kaichen/Projects/intrinsic && python -m pytest tests/test_dcf.py::TestRdAdjustedBasis::test_dcf_uses_adjusted_operating_margin_when_present -v`

Expected: FAIL. The test asserts margin is 0.475 but today's code computes `operating_income / revenue = 80B / 200B = 0.40`.

- [ ] **Step 3: Implement the precedence swap**

In `stock_analyzer/dcf.py`, modify the margin derivation at lines 407-410.

Find:

```python
        operating_margin = (
            self.assumptions.operating_margin or
            (operating_income / revenue if revenue > 0 else 0.15)
        )
```

Replace with:

```python
        operating_margin = (
            self.assumptions.operating_margin or
            financial_data.get('adjusted_operating_margin') or
            (operating_income / revenue if revenue > 0 else 0.15)
        )
```

Precedence: user-set assumption wins over adjusted, adjusted wins over raw fallback.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/kaichen/Projects/intrinsic && python -m pytest tests/test_dcf.py::TestRdAdjustedBasis -v`

Expected: PASS. Run the whole DCF test file to catch regressions:

Run: `cd /Users/kaichen/Projects/intrinsic && python -m pytest tests/test_dcf.py -v`

Expected: All tests PASS. The existing tests use `sample_financial_data` which has no `adjusted_operating_margin` key, so they fall through to the raw branch — no behavior change.

- [ ] **Step 5: Commit**

```bash
git add stock_analyzer/dcf.py tests/test_dcf.py
git commit -m "$(cat <<'EOF'
DCF prefers adjusted_operating_margin when present

Precedence chain: user assumption > adjusted_operating_margin from
financial_data > raw operating_income/revenue fallback. Fixes the
mixing where terminal ROIC was anchored on adjusted ROIC but the
starting margin came from raw GAAP, breaking the g/ROIC identity.
EOF
)"
```

---

### Task 4: `dcf.py` prefers `adjusted_sales_to_capital` for S/C fallback

**Files:**
- Modify: `stock_analyzer/dcf.py` (S/C fallback at lines 415-431)
- Test: `tests/test_dcf.py` (extend `TestRdAdjustedBasis`)

- [ ] **Step 1: Write failing test**

Add to `TestRdAdjustedBasis` in `tests/test_dcf.py`:

```python
    def test_dcf_uses_adjusted_sales_to_capital_when_assumption_is_none(self, adjusted_financial_data):
        """When user hasn't set S/C assumption, DCF should prefer adjusted_sales_to_capital over the raw balance-sheet fallback."""
        assumptions = DCFAssumptions(
            revenue_growth_rate=0.10,
            terminal_growth_rate=0.04,
            sales_to_capital_ratio=None,  # force fallback path
            terminal_roic=0.15,
        )
        model = DCFModel(assumptions)
        result = model.calculate_fair_value(adjusted_financial_data, shares_outstanding=1e10, current_price=100.0, verbose=True)
        assert result['sales_to_capital'] == pytest.approx(1.35, rel=1e-9)

    def test_dcf_user_assumption_still_wins_over_adjusted(self, adjusted_financial_data):
        """User-set sales_to_capital_ratio assumption overrides both adjusted and raw."""
        assumptions = DCFAssumptions(
            revenue_growth_rate=0.10,
            terminal_growth_rate=0.04,
            sales_to_capital_ratio=2.5,  # user override
            terminal_roic=0.15,
        )
        model = DCFModel(assumptions)
        result = model.calculate_fair_value(adjusted_financial_data, shares_outstanding=1e10, current_price=100.0, verbose=True)
        assert result['sales_to_capital'] == pytest.approx(2.5, rel=1e-9)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/kaichen/Projects/intrinsic && python -m pytest tests/test_dcf.py::TestRdAdjustedBasis::test_dcf_uses_adjusted_sales_to_capital_when_assumption_is_none -v`

Expected: FAIL. Current code computes S/C from raw IC fallback, not from `adjusted_sales_to_capital`.

(The user-override test will actually PASS today because the assumption path is unchanged — that's fine, it locks in the behavior as a regression guard.)

- [ ] **Step 3: Implement the precedence swap**

In `stock_analyzer/dcf.py`, modify the S/C block at lines 415-431.

Find:

```python
        if self.assumptions.sales_to_capital_ratio is not None:
            sales_to_capital = self.assumptions.sales_to_capital_ratio
        else:
            # Calculate invested capital from balance sheet
            equity = financial_data.get('equity', market_cap)  # Book value of equity
            cash = financial_data.get('cash', 0)
            sti = financial_data.get('short_term_investments', 0)
            lti = financial_data.get('long_term_investments', 0)
            invested_capital = equity + total_debt - cash - sti - lti

            # Calculate sales-to-capital ratio
            if invested_capital > 0:
                sales_to_capital = revenue / invested_capital
            else:
                # Default for typical companies
                # Typical range: 0.5-3.0 depending on industry
                sales_to_capital = 1.5
```

Replace with:

```python
        if self.assumptions.sales_to_capital_ratio is not None:
            sales_to_capital = self.assumptions.sales_to_capital_ratio
        elif financial_data.get('adjusted_sales_to_capital') is not None:
            sales_to_capital = financial_data['adjusted_sales_to_capital']
        else:
            # Calculate invested capital from balance sheet
            equity = financial_data.get('equity', market_cap)  # Book value of equity
            cash = financial_data.get('cash', 0)
            sti = financial_data.get('short_term_investments', 0)
            lti = financial_data.get('long_term_investments', 0)
            invested_capital = equity + total_debt - cash - sti - lti

            # Calculate sales-to-capital ratio
            if invested_capital > 0:
                sales_to_capital = revenue / invested_capital
            else:
                # Default for typical companies
                # Typical range: 0.5-3.0 depending on industry
                sales_to_capital = 1.5
```

Precedence: user assumption > adjusted > raw IC fallback > constant default.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/kaichen/Projects/intrinsic && python -m pytest tests/test_dcf.py -v`

Expected: All tests PASS. Existing tests that use `sample_financial_data` (which has no `adjusted_sales_to_capital` key) continue to exercise the raw fallback path.

- [ ] **Step 5: Commit**

```bash
git add stock_analyzer/dcf.py tests/test_dcf.py
git commit -m "$(cat <<'EOF'
DCF prefers adjusted_sales_to_capital in S/C fallback

Precedence chain: user assumption > adjusted_sales_to_capital from
financial_data > raw balance-sheet fallback > constant default.
Matches the pattern used in the margin derivation.
EOF
)"
```

---

### Task 5: Integration test — forward DCF and reverse DCF are consistent on the adjusted path

**Files:**
- Test: `tests/test_dcf.py` (extend `TestRdAdjustedBasis`)

This task has no production code changes. Its purpose is to lock in a round-trip property: if you run the forward DCF with adjusted fields present and then call reverse DCF with the resulting fair value as the target price, the implied growth rate should match the input revenue growth rate. If the forward and reverse are internally consistent, this test stays green. If a future change accidentally breaks one path's basis handling, this test will surface it.

- [ ] **Step 1: Write the round-trip test**

Add to `TestRdAdjustedBasis` in `tests/test_dcf.py`:

```python
    def test_forward_reverse_dcf_roundtrip_on_adjusted_path(self, adjusted_financial_data):
        """Forward DCF produces a fair value; reverse DCF with that fair value as target
        should return the same growth rate. Locks in internal consistency of the adjusted path."""
        input_growth = 0.12
        assumptions = DCFAssumptions(
            revenue_growth_rate=input_growth,
            terminal_growth_rate=0.04,
            sales_to_capital_ratio=None,   # let adjusted_sales_to_capital feed through
            terminal_roic=0.15,
            operating_margin=None,          # let adjusted_operating_margin feed through
        )
        model = DCFModel(assumptions)
        shares = 1e10

        # Forward: compute fair value at input_growth
        forward = model.calculate_fair_value(
            adjusted_financial_data, shares_outstanding=shares, current_price=100.0, verbose=False
        )
        target_price = forward['fair_value']

        # Reverse: solve for growth given fair value = target_price
        reverse = model.reverse_dcf(
            adjusted_financial_data,
            shares_outstanding=shares,
            target_price=target_price,
            precision=0.0001,
        )
        assert reverse is not None
        assert reverse['implied_value'] == pytest.approx(input_growth, abs=0.005)
```

- [ ] **Step 2: Run the test**

Run: `cd /Users/kaichen/Projects/intrinsic && python -m pytest tests/test_dcf.py::TestRdAdjustedBasis::test_forward_reverse_dcf_roundtrip_on_adjusted_path -v`

Expected: PASS. After Tasks 3 and 4 are in place, both forward and reverse DCF consume the same adjusted margin and S/C, so the round-trip must close.

If this test fails, do not push past the failure — it means there's still mixing somewhere. Investigate by computing the forward DCF's fair value by hand with the expected adjusted values, compare to what the test sees, and identify the step where the numbers drift.

- [ ] **Step 3: Commit**

```bash
git add tests/test_dcf.py
git commit -m "$(cat <<'EOF'
Test forward/reverse DCF round-trip on adjusted path

Locks in internal consistency: forward DCF with a growth rate g
and reverse DCF targeting the resulting fair value should return g.
Catches any future regression that reintroduces raw/adjusted mixing.
EOF
)"
```

---

### Task 6: Update calibrate SKILL.md step 6b — Operating Margin display

**Files:**
- Modify: `skills/calibrate/SKILL.md` (step 6b at lines 282-284)

- [ ] **Step 1: Make the edit**

Find in `skills/calibrate/SKILL.md`:

```markdown
**b. Operating Margin / Target Operating Margin**
- Look at: current operating margin from financials, historical trend, peer comparison
- Consider: is margin expanding or contracting? What's a realistic target?
```

Replace with:

```markdown
**b. Operating Margin / Target Operating Margin**
- **Primary anchor (when `dcf_inputs['adjusted_operating_margin']` is present):** Current adjusted margin (R&D capitalized) is the anchor for the target. Display as: `"Current margin: X.X% adjusted (R&D capitalized, N-year amortization) | Y.Y% raw GAAP"`. Adjusted is the economic margin — what the business would show if R&D were treated as capex; raw is what Alpha Vantage reports from GAAP financials.
- **Fallback (when adjusted is None — zero-R&D companies):** Display raw operating margin only.
- **Historical trend:** Show raw 5-year margin range as directional context — is the company expanding or compressing margin? Note that true multi-year adjusted margin history is unavailable given Alpha Vantage's 5-year data window and typical amortization lives, so the historical trend is shown on the raw scale and interpreted as directional.
- Consider: is margin expanding or contracting? What's a realistic target on the adjusted basis?
```

- [ ] **Step 2: Verify the edit**

Run: `grep -n "adjusted_operating_margin\|adjusted margin" /Users/kaichen/Projects/intrinsic/skills/calibrate/SKILL.md`

Expected: grep shows the new lines in step 6b.

- [ ] **Step 3: Commit**

```bash
git add skills/calibrate/SKILL.md
git commit -m "$(cat <<'EOF'
Update calibrate step 6b to anchor on adjusted operating margin

Show adjusted margin (R&D capitalized) as the primary anchor with raw
GAAP in parentheses. Historical trend stays on raw scale as directional
context since multi-year adjusted margin history is unavailable.
EOF
)"
```

---

### Task 7: Update calibrate SKILL.md step 6c — Sales-to-Capital display

**Files:**
- Modify: `skills/calibrate/SKILL.md` (step 6c at lines 286-292)

- [ ] **Step 1: Make the edit**

Find in `skills/calibrate/SKILL.md`:

```markdown
**c. Sales-to-Capital Ratio**
- **Always calculate 5+ years of historical data before recommending.** Compute both:
  - **Average S/C** = Revenue / Invested Capital (where Invested Capital = Equity + Debt - Cash - Investments)
  - **Incremental S/C** = ΔRevenue / ΔInvested Capital (year-over-year — this is what the DCF model actually uses)
- Use web sources if Alpha Vantage doesn't have enough history
- Present the full historical table to the user before asking for a value
- Consider: is there a regime change (e.g., capital-light → capital-heavy)? Is the trend improving or deteriorating?
```

Replace with:

```markdown
**c. Sales-to-Capital Ratio**
- **Primary anchor (when `dcf_inputs['adjusted_sales_to_capital']` is present):** Current adjusted S/C (Revenue / Adjusted Invested Capital, where Adjusted Invested Capital includes the research asset) is the anchor. Display as: `"Current S/C: X.Xx adjusted (research asset capitalized) | Y.Yx raw"`. Adjusted is the economic ratio; raw treats R&D as an expense.
- **Fallback (when adjusted is None — zero-R&D companies):** Display raw S/C only.
- **Historical trend (raw, directional context):** Always calculate 5+ years of historical raw data. Compute both:
  - **Raw Average S/C** = Revenue / Invested Capital (Equity + Debt - Cash - Investments)
  - **Raw Incremental S/C** = ΔRevenue / ΔInvested Capital (year-over-year — this is what the DCF model uses during projection years)
- Use web sources if Alpha Vantage doesn't have enough history. True multi-year adjusted S/C history is unavailable for the same data-window reason as margin history, so the raw trend table is the best directional signal.
- Present the full historical table to the user before asking for a value.
- Consider: is there a regime change (e.g., capital-light → capital-heavy)? Is the trend improving or deteriorating? Pick the target on the adjusted scale.
```

- [ ] **Step 2: Verify the edit**

Run: `grep -n "adjusted_sales_to_capital\|adjusted S/C" /Users/kaichen/Projects/intrinsic/skills/calibrate/SKILL.md`

Expected: grep shows the new lines in step 6c.

- [ ] **Step 3: Commit**

```bash
git add skills/calibrate/SKILL.md
git commit -m "$(cat <<'EOF'
Update calibrate step 6c to anchor on adjusted sales-to-capital

Show adjusted S/C (revenue over adjusted invested capital) as primary
anchor with raw S/C in parentheses. Historical raw trend retained as
directional context since multi-year adjusted history is unavailable.
EOF
)"
```

---

### Task 8: Update calibrate SKILL.md step 7 — coherence check wording

**Files:**
- Modify: `skills/calibrate/SKILL.md` (coherence check at lines 347-360)

- [ ] **Step 1: Make the edit**

Find in `skills/calibrate/SKILL.md`:

```markdown
**ROIC context:** Before running consistency checks, get ROIC from `calculate_dcf_inputs()`. If `dcf_inputs['adjusted_roic']` is available (R&D capitalized), use it as the primary ROIC for all checks below. Display:

```
Current ROIC: X.X% (with R&D capitalized, Y-year amortization)
  Unadjusted ROIC: Z.Z% (R&D as operating expense)
  Research asset: $XXB
  WACC: W.W% | Spread: S.S%
```

If `adjusted_roic` is None (no R&D data), fall back to `dcf_inputs['roic']` and display as before. The adjusted ROIC reflects the true return on all capital deployed, including intangible R&D capital. Use it for the value-of-growth check and fundamental growth check below.
```

Replace with:

```markdown
**ROIC context:** Before running consistency checks, get ROIC from `calculate_dcf_inputs()`. If `dcf_inputs['adjusted_roic']` is available (R&D capitalized), use it as the primary ROIC for all checks below. Display:

```
Current ROIC: X.X% (with R&D capitalized, Y-year amortization)
  Unadjusted ROIC: Z.Z% (R&D as operating expense)
  Research asset: $XXB
  WACC: W.W% | Spread: S.S%
```

If `adjusted_roic` is None (no R&D data), fall back to `dcf_inputs['roic']` and display as before. The adjusted ROIC reflects the true return on all capital deployed, including intangible R&D capital.

**Basis consistency:** When adjusted values are available, the user has picked margin (step 6b), S/C (step 6c), and terminal ROIC (step 6d) all on the adjusted basis, so the coherence checks below are all on the adjusted basis automatically. Specifically: the fundamental growth check's "NOPAT" and "reinvestment rate" refer to the adjusted quantities, and the value-of-growth check compares adjusted ROIC to WACC.
```

Find (further down in the same step 7):

```markdown
- **Fundamental growth check:** Compute `reinvestment_rate = (Revenue × growth_rate / sales_to_capital) / NOPAT` (where Revenue and NOPAT are current-year values). Then `fundamental_growth = reinvestment_rate × ROIC`. If the assumed revenue growth rate significantly exceeds fundamental growth, flag: "Assumed growth (X%) exceeds what current ROIC and reinvestment support (Y%). Achieving X% requires improving ROIC or increasing reinvestment beyond current levels."
```

Replace with:

```markdown
- **Fundamental growth check:** Compute `reinvestment_rate = (Revenue × growth_rate / sales_to_capital) / NOPAT` where `sales_to_capital` is the user's picked value (on the adjusted basis when available) and `NOPAT` is the adjusted NOPAT (= Revenue × adjusted_operating_margin × (1 − tax), or raw NOPAT as fallback when no R&D data). Then `fundamental_growth = reinvestment_rate × ROIC` where ROIC is adjusted when available. If the assumed revenue growth rate significantly exceeds fundamental growth, flag: "Assumed growth (X%) exceeds what current ROIC and reinvestment support (Y%). Achieving X% requires improving ROIC or increasing reinvestment beyond current levels."
```

- [ ] **Step 2: Verify the edit**

Run: `grep -n "adjusted basis\|adjusted NOPAT\|Basis consistency" /Users/kaichen/Projects/intrinsic/skills/calibrate/SKILL.md`

Expected: grep shows the new wording.

- [ ] **Step 3: Commit**

```bash
git add skills/calibrate/SKILL.md
git commit -m "$(cat <<'EOF'
Clarify calibrate step 7 coherence check basis consistency

Spell out that when adjusted values are available, the fundamental
growth check uses adjusted NOPAT and adjusted ROIC, matching the
basis of the S/C and margin the user picked in step 6.
EOF
)"
```

---

### Task 9: Update value SKILL.md step 2 — Key Metrics display

**Files:**
- Modify: `skills/value/SKILL.md` (step 2 at lines 30-51)

- [ ] **Step 1: Make the edit**

Find in `skills/value/SKILL.md`:

```markdown
  - Profitability metrics (margins, ROIC, ROE, ROA). Set ROIC on the `CompanyMetrics` object:
    - If `dcf_inputs['adjusted_roic']` is available: `metrics.roic = dcf_inputs['adjusted_roic']`
    - Display both: "ROIC: X.X% (R&D capitalized, Y-year amortization) | Unadjusted: Z.Z%"
    - Show research asset: "Research Asset: $XXB | R&D/Revenue: X.X%"
    - If no R&D data: `metrics.roic = dcf_inputs['roic']` (same as before)
```

Replace with:

```markdown
  - Profitability metrics (margins, ROIC, ROE, ROA). When `dcf_inputs['adjusted_operating_margin']`, `dcf_inputs['adjusted_sales_to_capital']`, and `dcf_inputs['adjusted_roic']` are available, display all three on the adjusted basis with raw shown in parentheses:
    - `"Operating Margin: X.X% (adjusted, R&D capitalized) | Y.Y% raw GAAP"`
    - `"Sales-to-Capital: Z.Zx (adjusted) | W.Wx raw"`
    - `"ROIC: A.A% (adjusted, N-year amortization) | B.B% unadjusted"`
    - Set `metrics.roic = dcf_inputs['adjusted_roic']`
    - Show research asset: `"Research Asset: $XXB | R&D/Revenue: X.X%"`
    - If no R&D data: display raw values only and `metrics.roic = dcf_inputs['roic']` (same as before)
```

- [ ] **Step 2: Verify the edit**

Run: `grep -n "adjusted_operating_margin\|adjusted, R&D capitalized\|adjusted) |" /Users/kaichen/Projects/intrinsic/skills/value/SKILL.md`

Expected: grep shows the new display lines.

- [ ] **Step 3: Commit**

```bash
git add skills/value/SKILL.md
git commit -m "$(cat <<'EOF'
Update value step 2 to display adjusted margin, S/C, and ROIC

Show all three adjusted metrics with raw GAAP in parentheses when
R&D data is available. Falls back to raw-only display for zero-R&D
companies. Mirrors the adjusted-primary anchoring in calibrate.
EOF
)"
```

---

### Task 10: Update damodaran-audit.md — note second-pass fix for item #13

**Files:**
- Modify: `docs/internal/damodaran-audit.md` (summary table row at line 514, Phase 3 DONE list at line 557)

- [ ] **Step 1: Update the summary table row**

Find in `docs/internal/damodaran-audit.md` (around line 514):

```markdown
| 13 | R&D capitalization | 3 | MEDIUM-HIGH | **DONE** | Pre-tax asset per Damodaran R&DConv.xls, industry amortizable life, adjusted ROIC in calibrate/value |
```

Replace with:

```markdown
| 13 | R&D capitalization | 3 | MEDIUM-HIGH | **DONE** | Pre-tax asset per Damodaran R&DConv.xls, industry amortizable life. First pass (2026-04-09): adjusted ROIC in calibrate/value. Second pass (2026-04-11): adjusted margin and adjusted S/C flow through calibrate anchors and DCF starting-point extraction — forward/reverse DCF consistent on adjusted basis |
```

- [ ] **Step 2: Update the Phase 3 DONE list entry**

Find in `docs/internal/damodaran-audit.md` (around line 557):

```markdown
**DONE (1 of 7):**
- Item 13: R&D capitalization per Damodaran's R&DConv.xls. Pre-tax research asset with straight-line amortization, industry-specific amortizable life (3yr software, 5yr semi, 10yr pharma). Adjusted ROIC flows into calibrate coherence checks and terminal ROIC anchoring. FCF unchanged.
```

Replace with:

```markdown
**DONE (1 of 7):**
- Item 13: R&D capitalization per Damodaran's R&DConv.xls. Pre-tax research asset with straight-line amortization, industry-specific amortizable life (3yr software, 5yr semi, 10yr pharma). First pass (2026-04-09): adjusted ROIC flows into calibrate coherence checks and terminal ROIC anchoring. Second pass (2026-04-11): adjusted operating margin and adjusted S/C now also feed calibrate step 6b/6c anchors and the DCF starting-point extraction, so terminal ROIC is paired with adjusted NOPAT instead of mixing raw with adjusted. Forward and reverse DCF maintain round-trip consistency on the adjusted path. See `docs/internal/2026-04-11-rd-adjusted-basis-design.md` and `docs/internal/2026-04-11-rd-adjusted-basis-plan.md`. FCF unchanged.
```

- [ ] **Step 3: Verify**

Run: `grep -n "Second pass\|2026-04-11" /Users/kaichen/Projects/intrinsic/docs/internal/damodaran-audit.md`

Expected: grep shows both new references (one in the table row, one in the DONE list entry).

- [ ] **Step 4: Commit**

```bash
git add docs/internal/damodaran-audit.md
git commit -m "$(cat <<'EOF'
Note R&D capitalization audit item #13 second-pass fix

Adjusted margin and adjusted S/C now flow through calibrate anchors
and DCF starting-point extraction, completing the original goal of
item #13 beyond the narrow first-pass scope of adjusted ROIC display.
EOF
)"
```

---

## Verification — end-to-end

After Task 10 is committed, run the full test suite once to confirm nothing is broken:

```bash
cd /Users/kaichen/Projects/intrinsic && python -m pytest tests/ -v
```

Expected: all tests PASS.

Then do a quick hand-check with MSFT (the repo's primary R&D-heavy example) to confirm the flow:

```bash
cd /Users/kaichen/Projects/intrinsic && PYTHONPATH=. python3 -c "
from stock_analyzer.metrics import FinancialMetrics
from stock_analyzer.stock_manager import StockManager

sm = StockManager()
data = sm.load_financial_data('MSFT')
inputs = FinancialMetrics.calculate_dcf_inputs(
    data['data']['income_statement_annual']['annualReports'],
    data['data']['balance_sheet']['annualReports'],
    data['data']['cash_flow']['annualReports'],
    data['data']['overview'],
    income_annual=data['data']['income_statement_annual']['annualReports'],
)
print(f'Raw margin:        {inputs[\"operating_income\"] / inputs[\"revenue\"]:.4f}')
print(f'Adjusted margin:   {inputs[\"adjusted_operating_margin\"]:.4f}')
print(f'Raw S/C:           {inputs[\"revenue\"] / inputs[\"invested_capital\"]:.4f}')
print(f'Adjusted S/C:      {inputs[\"adjusted_sales_to_capital\"]:.4f}')
print(f'Raw ROIC:          {inputs[\"roic\"]:.4f}')
print(f'Adjusted ROIC:     {inputs[\"adjusted_roic\"]:.4f}')
"
```

Expected: adjusted values are populated and differ from raw. If adjusted margin > raw margin (R&D add-back > amortization), you're seeing the R&D adjustment increasing reported economic profitability — correct for a growing R&D spender like MSFT.

---

## Notes for the implementer

- **Each commit should be a green-test commit.** Do not advance to the next task if tests are failing.
- **Follow existing patterns.** The precedence chains in dcf.py mirror the shape of the existing `operating_margin` precedence (user assumption > fallback). Don't introduce new idioms.
- **Skill markdown edits are text changes, not logic changes.** There's no test for them, but you should grep after each edit to verify the new content is present.
- **No DCF math changes.** If you find yourself editing `calculate_terminal_value`, `_project_fcfs`, `calculate_wacc`, or the reverse DCF binary search, stop and re-read the design spec — those are explicitly out of scope.
- **Silent-drift migration is intentional.** Do not add a basis marker to `assumptions.json`, do not write a migration script, do not print a warning banner when old assumptions are loaded. Users re-calibrate on demand.
