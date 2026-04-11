# R&D Informational Reframe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Revert the R&D adjusted-basis precedence chain in `dcf.py` and reframe the adjusted margin/S/C/ROIC values as calibration-time reference anchors, with calibrate explicitly asking for starting operating margin.

**Architecture:** `metrics.py` continues to compute adjusted values (research asset, adjusted NOPAT delta, adjusted ROIC, adjusted margin, adjusted S/C) — these become purely informational. `dcf.py` reverts to a simple two-tier resolution: user assumption or raw fallback, no middle adjusted tier. `calibrate` step 6b adds an explicit starting-margin question (currently only target is asked), steps 6b/6c add display blocks showing raw + adjusted as anchors, and step 7 gains a ROIC panel showing raw/adjusted/user-implied/terminal with downstream coherence checks computed from user picks.

**Tech Stack:** Python 3, pytest, markdown skill files. No new dependencies.

**Design doc:** `docs/internal/2026-04-11-rd-informational-design.md` (already committed)

---

## File Structure

**Code files modified:**
- `stock_analyzer/dcf.py` — two precedence-chain reverts (~15 lines net delta)
- `tests/test_dcf.py` — remove `TestRdAdjustedBasis` class (lines 947-1033, end of file); add two small sanity tests

**Skill files modified:**
- `skills/calibrate/SKILL.md` — step 6b adds display block + two questions; step 6c adds display block; step 7 adds ROIC panel + rewrites fundamental growth check formula

**Docs modified:**
- `docs/dcf-methodology.md` — R&D capitalization section (~lines 142-178) updated to reflect informational role
- `docs/internal/damodaran-audit.md` — item #13 third-pass note (line 514 summary row, line 557 Phase 3 list, and the detail section around line 379)

**Files NOT touched:**
- `stock_analyzer/metrics.py` — all R&D capitalization math stays
- `tests/test_metrics.py` — all `test_adjusted_*` tests stay (still test display fields)
- `skills/value/SKILL.md` — already displays raw + adjusted correctly
- Any other files

---

## Task Order and Dependencies

Tasks 1 → 2 → 3 must run in order. Task 1 removes tests that would break during Tasks 2/3. Tasks 4 → 5 → 6 must run in `SKILL.md` source-order because each edit's `old_string` must match the current file state — if Task 5 is run before Task 4, line numbers shift but the old_strings still work; the order here is for clarity. Tasks 7 and 8 are doc updates that can run in any order after the code changes. Task 9 is final validation.

---

## Task 1: Remove `TestRdAdjustedBasis` class

**Files:**
- Modify: `tests/test_dcf.py` (lines 947-1033, the entire final class in the file)

**Context:** These four tests enforce the precedence-chain behavior we're reverting. They must be removed BEFORE Tasks 2 and 3 run, otherwise the precedence-chain reverts would break them mid-flight. This is cleanup, not TDD — there's no failing-test step because we're deleting tests rather than adding them.

- [ ] **Step 1: Verify the current state of `TestRdAdjustedBasis`**

Run: `grep -n "class TestRdAdjustedBasis\|def test_dcf_uses_adjusted\|def test_dcf_user_assumption_still_wins\|def test_forward_reverse_dcf_roundtrip_on_adjusted_path\|def test_dcf_falls_back_to_raw" tests/test_dcf.py`

Expected output (line numbers may shift by ±2 depending on prior edits):
```
947:class TestRdAdjustedBasis:
968:    def test_dcf_uses_adjusted_operating_margin_when_present(self, adjusted_financial_data):
981:    def test_dcf_uses_adjusted_sales_to_capital_when_assumption_is_none(self, adjusted_financial_data):
993:    def test_dcf_user_assumption_still_wins_over_adjusted(self, adjusted_financial_data):
1005:    def test_forward_reverse_dcf_roundtrip_on_adjusted_path(self, adjusted_financial_data):
```

- [ ] **Step 2: Delete the class**

Use the Edit tool with the following `old_string`:

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

And `new_string` = empty string `""`.

Note: the class is the very last thing in `test_dcf.py`. Deleting it may leave a trailing newline or not — that's fine either way.

- [ ] **Step 3: Run the test suite to verify green**

Run: `cd /Users/kaichen/Projects/intrinsic && PYTHONPATH=. python3 -m pytest tests/ -q 2>&1 | tail -5`

Expected: ending like `304 passed in 0.2s` (was 308; 4 tests removed). No failures, no errors.

- [ ] **Step 4: Commit**

```bash
git add tests/test_dcf.py
git commit -m "$(cat <<'EOF'
Remove TestRdAdjustedBasis class

These four tests enforce the dcf.py precedence-chain behavior that is
being reverted in the next two commits (adjusted margin and S/C flowing
through dcf.py automatically). Under the new frame, adjusted values
are calibration-time reference only — removed tests that codified the
now-obsolete auto-plumb behavior.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Revert `dcf.py` margin precedence chain (TDD)

**Files:**
- Modify: `stock_analyzer/dcf.py` (lines 407-411)
- Modify: `tests/test_dcf.py` (append new test class after existing `TestEquityBridge`)

**Context:** The current margin resolution uses a three-tier `or` chain: `user → adjusted → raw`. The new resolution has two tiers: `user → raw`. Bonus: replacing `or` with `is not None` fixes a pre-existing edge case where `operating_margin=0.0` would silently fall through the `or` chain.

- [ ] **Step 1: Write the failing test**

Append this test class to the end of `tests/test_dcf.py` (after `TestEquityBridge`, which is the last class now that `TestRdAdjustedBasis` is gone):

```python


class TestDcfMarginRawOrUserFallback:
    """R&D informational reframe: dcf.py margin resolution is user-or-raw.

    adjusted_operating_margin in financial_data must be ignored by the DCF —
    it is purely a display field now.
    """

    @pytest.fixture
    def financial_data_with_adjusted(self):
        return {
            'revenue': 200_000_000_000,
            'operating_income': 80_000_000_000,   # raw margin = 40%
            'total_debt': 50_000_000_000,
            'cash': 20_000_000_000,
            'short_term_investments': 10_000_000_000,
            'long_term_investments': 5_000_000_000,
            'equity': 100_000_000_000,
            'market_cap': 2_000_000_000_000,
            'beta': 1.1,
            'adjusted_operating_margin': 0.60,    # 60% adjusted — must NOT be used
            'adjusted_sales_to_capital': 1.35,
        }

    def test_dcf_uses_raw_margin_when_user_assumption_unset(self, financial_data_with_adjusted):
        """When operating_margin is None, DCF uses raw operating_income/revenue, NOT adjusted_operating_margin."""
        assumptions = DCFAssumptions(
            revenue_growth_rate=0.10,
            terminal_growth_rate=0.04,
            operating_margin=None,          # unset — fallback path
            sales_to_capital_ratio=1.0,     # pinned to isolate margin
            terminal_roic=0.15,
        )
        model = DCFModel(assumptions)
        result = model.calculate_fair_value(
            financial_data_with_adjusted,
            shares_outstanding=1e10,
            current_price=100.0,
            verbose=True,
        )
        # Raw is 80B / 200B = 0.40. Adjusted is 0.60. The DCF MUST pick raw.
        assert result['operating_margin'] == pytest.approx(0.40, rel=1e-9)

    def test_dcf_uses_user_assumption_when_set(self, financial_data_with_adjusted):
        """User-set operating_margin wins over both raw and adjusted."""
        assumptions = DCFAssumptions(
            revenue_growth_rate=0.10,
            terminal_growth_rate=0.04,
            operating_margin=0.55,          # user pick
            sales_to_capital_ratio=1.0,
            terminal_roic=0.15,
        )
        model = DCFModel(assumptions)
        result = model.calculate_fair_value(
            financial_data_with_adjusted,
            shares_outstanding=1e10,
            current_price=100.0,
            verbose=True,
        )
        assert result['operating_margin'] == pytest.approx(0.55, rel=1e-9)
```

- [ ] **Step 2: Run the failing test to verify it fails**

Run: `cd /Users/kaichen/Projects/intrinsic && PYTHONPATH=. python3 -m pytest tests/test_dcf.py::TestDcfMarginRawOrUserFallback::test_dcf_uses_raw_margin_when_user_assumption_unset -v 2>&1 | tail -20`

Expected: FAIL. The assertion `result['operating_margin'] == pytest.approx(0.40, rel=1e-9)` fails because current code has `financial_data.get('adjusted_operating_margin')` in the `or` chain and would return `0.60`. Error message similar to:

```
assert 0.60 == 0.40 ± 4.0e-09
```

The second test (`test_dcf_uses_user_assumption_when_set`) should already pass under the current code — user assumption is the top tier of the existing chain.

- [ ] **Step 3: Revert the margin precedence chain in `dcf.py`**

Use the Edit tool on `stock_analyzer/dcf.py`.

`old_string`:
```python
        # Calculate margins and ratios
        operating_margin = (
            self.assumptions.operating_margin or
            financial_data.get('adjusted_operating_margin') or
            (operating_income / revenue if revenue > 0 else 0.15)
        )
```

`new_string`:
```python
        # Calculate margins and ratios.
        # R&D informational reframe: user assumption or raw fallback only.
        # adjusted_operating_margin (when present in financial_data) is a
        # display field consumed by calibrate/value skills, not the DCF.
        if self.assumptions.operating_margin is not None:
            operating_margin = self.assumptions.operating_margin
        elif revenue > 0:
            operating_margin = operating_income / revenue
        else:
            operating_margin = 0.15
```

- [ ] **Step 4: Run the failing test to verify it passes**

Run: `cd /Users/kaichen/Projects/intrinsic && PYTHONPATH=. python3 -m pytest tests/test_dcf.py::TestDcfMarginRawOrUserFallback -v 2>&1 | tail -10`

Expected: both tests PASS.

- [ ] **Step 5: Run the full test suite to verify no regression**

Run: `cd /Users/kaichen/Projects/intrinsic && PYTHONPATH=. python3 -m pytest tests/ -q 2>&1 | tail -5`

Expected: ending like `306 passed in 0.2s` (was 304 after Task 1; +2 new tests = 306). No failures.

- [ ] **Step 6: Commit**

```bash
git add stock_analyzer/dcf.py tests/test_dcf.py
git commit -m "$(cat <<'EOF'
Revert margin precedence chain in dcf.py

User assumption or raw fallback only. adjusted_operating_margin in
financial_data becomes a display-only field consumed by calibrate and
value skills, not by the DCF. Also fixes a pre-existing edge case where
operating_margin=0.0 would silently fall through the `or` chain (now
uses `is not None`).

Add TestDcfMarginRawOrUserFallback locking in the new resolution rule:
raw fallback when user assumption is None, even when adjusted is present
in financial_data.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Revert `dcf.py` S/C precedence chain (TDD)

**Files:**
- Modify: `stock_analyzer/dcf.py` (lines 416-419 — the middle `elif` branch)
- Modify: `tests/test_dcf.py` (append new test class after `TestDcfMarginRawOrUserFallback`)

**Context:** Parallel to Task 2 for the S/C resolution. The current S/C resolution has three branches: `user → adjusted → raw balance-sheet computation`. The new resolution has two: `user → raw balance-sheet computation`.

- [ ] **Step 1: Write the failing test**

Append this test class to the end of `tests/test_dcf.py`:

```python


class TestDcfSalesToCapitalRawOrUserFallback:
    """R&D informational reframe: dcf.py S/C resolution is user-or-raw.

    adjusted_sales_to_capital in financial_data must be ignored by the DCF —
    it is purely a display field now.
    """

    @pytest.fixture
    def financial_data_with_adjusted(self):
        return {
            'revenue': 200_000_000_000,
            'operating_income': 80_000_000_000,
            'total_debt': 50_000_000_000,
            'cash': 20_000_000_000,
            'short_term_investments': 10_000_000_000,
            'long_term_investments': 5_000_000_000,
            'equity': 100_000_000_000,         # raw IC = 100 + 50 - 20 - 10 - 5 = 115
            'market_cap': 2_000_000_000_000,
            'beta': 1.1,
            'adjusted_operating_margin': 0.475,
            'adjusted_sales_to_capital': 1.35,  # must NOT be used
        }

    def test_dcf_uses_raw_sc_when_user_assumption_unset(self, financial_data_with_adjusted):
        """When sales_to_capital_ratio is None, DCF uses raw Rev/IC, NOT adjusted_sales_to_capital.

        Raw IC = equity + total_debt - cash - sti - lti = 100B + 50B - 20B - 10B - 5B = 115B.
        Raw S/C = 200B / 115B ≈ 1.7391. Adjusted is 1.35. The DCF MUST pick raw.
        """
        assumptions = DCFAssumptions(
            revenue_growth_rate=0.10,
            terminal_growth_rate=0.04,
            operating_margin=0.40,            # pinned to isolate S/C
            sales_to_capital_ratio=None,      # unset — fallback path
            terminal_roic=0.15,
        )
        model = DCFModel(assumptions)
        result = model.calculate_fair_value(
            financial_data_with_adjusted,
            shares_outstanding=1e10,
            current_price=100.0,
            verbose=True,
        )
        expected_raw_sc = 200_000_000_000 / 115_000_000_000
        assert result['sales_to_capital'] == pytest.approx(expected_raw_sc, rel=1e-9)

    def test_dcf_uses_user_sc_when_set(self, financial_data_with_adjusted):
        """User-set sales_to_capital_ratio wins over both raw and adjusted."""
        assumptions = DCFAssumptions(
            revenue_growth_rate=0.10,
            terminal_growth_rate=0.04,
            operating_margin=0.40,
            sales_to_capital_ratio=2.5,       # user pick
            terminal_roic=0.15,
        )
        model = DCFModel(assumptions)
        result = model.calculate_fair_value(
            financial_data_with_adjusted,
            shares_outstanding=1e10,
            current_price=100.0,
            verbose=True,
        )
        assert result['sales_to_capital'] == pytest.approx(2.5, rel=1e-9)
```

- [ ] **Step 2: Run the failing test to verify it fails**

Run: `cd /Users/kaichen/Projects/intrinsic && PYTHONPATH=. python3 -m pytest tests/test_dcf.py::TestDcfSalesToCapitalRawOrUserFallback::test_dcf_uses_raw_sc_when_user_assumption_unset -v 2>&1 | tail -20`

Expected: FAIL. Under current code, the middle `elif` branch returns `1.35` (adjusted), but the test expects `1.7391` (raw). Error similar to:

```
assert 1.35 == 1.7391... ± ...
```

The second test (user-assumption path) should already pass under current code.

- [ ] **Step 3: Revert the S/C precedence chain in `dcf.py`**

Use the Edit tool on `stock_analyzer/dcf.py`.

`old_string`:
```python
        # Calculate sales-to-capital ratio
        # Sales-to-Capital = Revenue / Invested Capital
        # Where Invested Capital = Equity + Debt - Cash - Non-operating Investments
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

`new_string`:
```python
        # Calculate sales-to-capital ratio.
        # Sales-to-Capital = Revenue / Invested Capital
        # Where Invested Capital = Equity + Debt - Cash - Non-operating Investments.
        # R&D informational reframe: user assumption or raw fallback only.
        # adjusted_sales_to_capital (when present in financial_data) is a
        # display field consumed by calibrate/value skills, not the DCF.
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

- [ ] **Step 4: Run the failing test to verify it passes**

Run: `cd /Users/kaichen/Projects/intrinsic && PYTHONPATH=. python3 -m pytest tests/test_dcf.py::TestDcfSalesToCapitalRawOrUserFallback -v 2>&1 | tail -10`

Expected: both tests PASS.

- [ ] **Step 5: Run the full test suite to verify no regression**

Run: `cd /Users/kaichen/Projects/intrinsic && PYTHONPATH=. python3 -m pytest tests/ -q 2>&1 | tail -5`

Expected: ending like `308 passed in 0.2s` (306 after Task 2 + 2 new tests).

- [ ] **Step 6: Commit**

```bash
git add stock_analyzer/dcf.py tests/test_dcf.py
git commit -m "$(cat <<'EOF'
Revert S/C precedence chain in dcf.py

User assumption or raw balance-sheet fallback only. adjusted_sales_to_capital
in financial_data becomes a display-only field consumed by calibrate and
value skills, not by the DCF.

Add TestDcfSalesToCapitalRawOrUserFallback locking in the new resolution rule.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Update `calibrate` step 6b — display block + starting margin question

**Files:**
- Modify: `skills/calibrate/SKILL.md` (lines 282-286, the current "Operating Margin / Target Operating Margin" section)

**Context:** Current step 6b asks only for target operating margin and uses adjusted as the anchor. New step 6b shows both raw and adjusted as reference anchors, asks explicitly for starting margin (stored to `assumptions.operating_margin`), then asks for target margin (stored to `assumptions.target_operating_margin`).

- [ ] **Step 1: Replace the step 6b block**

Use the Edit tool on `skills/calibrate/SKILL.md`.

`old_string`:
```markdown
**b. Operating Margin / Target Operating Margin**
- **Primary anchor (when `dcf_inputs['adjusted_operating_margin']` is present):** Current adjusted margin (R&D capitalized) is the anchor for the target. Display as: `"Current margin: X.X% adjusted (R&D capitalized, N-year amortization) | Y.Y% raw GAAP"`. Adjusted is the economic margin — what the business would show if R&D were treated as capex; raw is what Alpha Vantage reports from GAAP financials.
- **Fallback (when adjusted is None — zero-R&D companies):** Display raw operating margin only.
- **Historical trend:** Show raw 5-year margin range as directional context — is the company expanding or compressing margin? Note that true multi-year adjusted margin history is unavailable given Alpha Vantage's 5-year data window and typical amortization lives, so the historical trend is shown on the raw scale and interpreted as directional.
- Consider: is margin expanding or contracting? What's a realistic target on the adjusted basis?
```

`new_string`:
```markdown
**b. Operating Margin — Starting and Target**

**Display anchors before asking any questions.** Read the data once and show:

```
Current operating margin:
  Raw (GAAP, R&D expensed):       X.X%
  Adjusted (R&D capitalized):     Y.Y%   [N-year amortization]
  5-year raw range:               A.A% – B.B%   [trend: expanding / stable / compressing]
```

Omit the "Adjusted" row when `dcf_inputs['adjusted_operating_margin']` is `None` (zero-R&D companies). Use `dcf_inputs['rd_amortizable_life']` for the N-year note. The raw historical range comes from the 5-year annual income statement; if Alpha Vantage coverage is short, state how many years you have.

**Explain what the user is seeing:** Raw is what Alpha Vantage reports from GAAP financials (R&D expensed as an operating expense). Adjusted is what the business would show if R&D were treated as capital expenditure — amortized over N years rather than expensed in the year incurred. The adjusted number is the economic operating margin; the raw number is the accounting number. The anchors are reference points for your picks — pick values that reflect your view of the business, not an algorithmic default.

**Question 1 — Starting operating margin (year 0).** Use `AskUserQuestion` with these options:
- Raw X.X%
- Adjusted Y.Y% (omit when `adjusted_operating_margin` is None)
- Custom (user types a value)

Store the answer to `assumptions.operating_margin`. This is the margin the DCF uses for year 1 before any convergence.

**Question 2 — Target operating margin (year 10 for linear convergence).** Use `AskUserQuestion` with these options:
- Same as starting (flat margin, no convergence)
- Expand to Z% (when there's a margin-expansion story — suggest a specific Z based on research, e.g. picked_starting + 2pp)
- Contract to W% (when there's a margin-compression story)
- Custom

When the user picks "same as starting," set `assumptions.target_operating_margin = None` so the DCF's existing "no convergence" path runs. Otherwise store the picked value to `assumptions.target_operating_margin`.

**Research context:** If research is available, factor in the Margin & Profitability → Margin signal when recommending. Example: "Research: Wide moat, durable pricing power — recommending starting at adjusted 47.5% and target 48% (slight expansion consistent with operating leverage)."

**If the user picks values significantly above both raw and adjusted anchors, challenge constructively.** Example: "That's X pp above even the R&D-adjusted economic margin of Y.Y%. What specifically do you see that the numbers don't?"

Consider: is margin expanding or contracting? What's a realistic trajectory over 10 years?
```

- [ ] **Step 2: Verify the edit by reading back the section**

Run: `sed -n '280,335p' skills/calibrate/SKILL.md`

Expected: section starts with `**b. Operating Margin — Starting and Target**` and the new content is present. The line count grows (old 5 lines → new ~40 lines). The adjacent sections (step 6a ending at ~line 280 and step 6c starting after the new block) should still be intact.

- [ ] **Step 3: Commit**

```bash
git add skills/calibrate/SKILL.md
git commit -m "$(cat <<'EOF'
calibrate step 6b: explicit starting margin question + display block

Current step 6b only asks for target margin and uses adjusted as the
sole anchor. New version shows raw + adjusted + 5-year range as
reference anchors, then asks two explicit questions: starting margin
(year 0, stored to assumptions.operating_margin) and target margin
(year 10, stored to assumptions.target_operating_margin). Under the
R&D informational reframe, the user picks both explicitly instead of
relying on dcf.py's reverted precedence chain to derive starting
margin from adjusted_operating_margin.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Update `calibrate` step 6c — display block

**Files:**
- Modify: `skills/calibrate/SKILL.md` (the "Sales-to-Capital Ratio" section, currently around lines 288-296; line numbers will have shifted due to Task 4)

**Context:** Step 6c keeps its single S/C question but gains a display block showing raw + adjusted as reference anchors. No new questions — S/C is a single value in the DCF.

- [ ] **Step 1: Replace the step 6c block**

Use the Edit tool on `skills/calibrate/SKILL.md`.

`old_string`:
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

`new_string`:
```markdown
**c. Sales-to-Capital Ratio**

**Display anchors before asking.** Show:

```
Current sales-to-capital:
  Raw (R&D expensed):               X.Xx   (= revenue / (equity + debt - cash - investments))
  Adjusted (R&D capitalized):       Y.Yx   (= revenue / (raw IC + research asset))
```

Omit the "Adjusted" row when `dcf_inputs['adjusted_sales_to_capital']` is `None`.

**Historical trend (raw, directional context):** Always calculate 5+ years of historical raw data. Compute both:
- **Raw Average S/C** = Revenue / Invested Capital (Equity + Debt - Cash - Investments)
- **Raw Incremental S/C** = ΔRevenue / ΔInvested Capital (year-over-year — this is what the DCF model uses during projection years)

Use web sources if Alpha Vantage doesn't have enough history. True multi-year adjusted S/C history is unavailable given the 5-year Alpha Vantage data window and typical amortization lives, so the raw trend table is the best directional signal for whether capital efficiency is improving or deteriorating.

Present the full historical table to the user before asking for a value.

**Explain what the user is seeing:** Raw treats R&D as an operating expense, so invested capital excludes the accumulated research asset. Adjusted treats R&D as capital expenditure, so the research asset is part of invested capital — the denominator is larger, and the ratio is lower. Pick what reflects your view of the business's true capital intensity.

**Question:** Use `AskUserQuestion` with these options:
- Raw S/C (X.Xx)
- Adjusted S/C (Y.Yx) — omit when `adjusted_sales_to_capital` is None
- Custom (user types a value)

Store the answer to `assumptions.sales_to_capital_ratio`.

Consider: is there a regime change (e.g., capital-light → capital-heavy)? Is the historical trend improving or deteriorating? Does the adjusted number represent a more honest picture of what this business needs?
```

- [ ] **Step 2: Verify the edit**

Run: `grep -c "Raw (R&D expensed):" skills/calibrate/SKILL.md`

Expected: `1` (this string appears only in the new step 6c block).

Run: `grep -c "Primary anchor (when \`dcf_inputs\['adjusted_sales_to_capital'\]\` is present)" skills/calibrate/SKILL.md`

Expected: `0` (the old step 6c wording is gone).

- [ ] **Step 3: Commit**

```bash
git add skills/calibrate/SKILL.md
git commit -m "$(cat <<'EOF'
calibrate step 6c: display block for raw + adjusted S/C anchors

Current step 6c already presents raw and adjusted as primary anchor vs
fallback. New version is a display block that shows both side-by-side
as reference anchors (matching step 6b pattern), then asks a single
AskUserQuestion with raw/adjusted/custom options. No change to the
underlying stored field (assumptions.sales_to_capital_ratio) — only
how the anchors are framed to the user.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Update `calibrate` step 7 — ROIC panel + user-implied formulas

**Files:**
- Modify: `skills/calibrate/SKILL.md` (the "### 7. Coherence Check" section, currently around lines 347-381)

**Context:** Step 7 currently uses `dcf_inputs['adjusted_roic'] × dcf_inputs['adjusted_invested_capital']` as "Damodaran canonical NOPAT" for the fundamental growth check. Under the reframe, the check should use the user's own picks: `user_NOPAT = Revenue × picked_margin × (1 − tax_rate)` and `implied_projection_ROIC = picked_margin × picked_S/C × (1 − tax_rate)`. A new ROIC panel surfaces raw + adjusted + implied + terminal in one place at the top of step 7.

- [ ] **Step 1: Replace the step 7 opening (ROIC context + basis consistency paragraphs)**

Use the Edit tool on `skills/calibrate/SKILL.md`.

`old_string`:
```markdown
### 7. Coherence Check

After all assumptions are set, step back and review them as a whole. This is a reasoning step — no new data or web searches needed.

**ROIC context:** Before running consistency checks, get ROIC from `calculate_dcf_inputs()`. If `dcf_inputs['adjusted_roic']` is available (R&D capitalized), use it as the primary ROIC for all checks below. Display:

```
Current ROIC: X.X% (with R&D capitalized, Y-year amortization)
  Unadjusted ROIC: Z.Z% (R&D as operating expense)
  Research asset: $XXB
  WACC: W.W% | Spread: S.S%
```

If `adjusted_roic` is None (no R&D data), fall back to `dcf_inputs['roic']` and display as before. The adjusted ROIC reflects the true return on all capital deployed, including intangible R&D capital.

**Basis consistency:** When adjusted values are available, the user has picked margin (step 6b), S/C (step 6c), and terminal ROIC (step 6d) all on the adjusted basis, so the coherence checks below are all on the adjusted basis automatically. Specifically: the fundamental growth check's "NOPAT" and "reinvestment rate" refer to the adjusted quantities, and the value-of-growth check compares adjusted ROIC to WACC.

**Cross-assumption consistency:** Do the assumptions make sense together?
- **Value of growth:** If ROIC < WACC, growth destroys value — higher growth makes the stock *less* valuable. Flag prominently: "ROIC (X%) is below WACC (Y%). At these returns, growth destroys value. Either ROIC must improve (higher margins or better capital efficiency) or the growth assumption is working against you."
- **Fundamental growth check:** Compute `reinvestment_rate = (Revenue × growth_rate / sales_to_capital) / NOPAT` where `sales_to_capital` is the user's picked value (on the adjusted basis when available) and `NOPAT` is `dcf_inputs['adjusted_roic'] × dcf_inputs['adjusted_invested_capital']` — Damodaran's canonical adjusted NOPAT, which pairs exactly with adjusted ROIC below. Fall back to `dcf_inputs['roic'] × dcf_inputs['invested_capital']` when no R&D data. Then `fundamental_growth = reinvestment_rate × ROIC` where ROIC is adjusted when available. If the assumed revenue growth rate significantly exceeds fundamental growth, flag: "Assumed growth (X%) exceeds what current ROIC and reinvestment support (Y%). Achieving X% requires improving ROIC or increasing reinvestment beyond current levels."
```

`new_string`:
```markdown
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
- **Fundamental growth check:** Compute:
  ```
  user_NOPAT         = Revenue × assumptions.operating_margin × (1 - assumptions.tax_rate)
  reinvestment_rate  = (Revenue × growth_rate / assumptions.sales_to_capital_ratio) / user_NOPAT
  fundamental_growth = reinvestment_rate × implied_projection_ROIC
  ```
  Compare `fundamental_growth` to the assumed revenue growth rate. If the assumed growth significantly exceeds fundamental growth, flag: "Assumed growth (X%) exceeds what your picked margin + S/C + tax rate support (Y%). Achieving X% requires raising margins, improving capital efficiency, or raising reinvestment beyond current levels."
```

- [ ] **Step 2: Verify the edit**

Run: `grep -c "adjusted_invested_capital" skills/calibrate/SKILL.md`

Expected: `0`. The field name appears nowhere in the new step 7 text — the old "Damodaran canonical NOPAT" formula (`dcf_inputs['adjusted_roic'] × dcf_inputs['adjusted_invested_capital']`) is the only place it appeared in SKILL.md, and the edit removes it.

Run: `grep -c "implied_projection_ROIC" skills/calibrate/SKILL.md`

Expected: at least `2` (in the ROIC panel explanation and in the fundamental growth check formula).

Run: `grep -c "Your implied projection ROIC" skills/calibrate/SKILL.md`

Expected: `1` (in the ROIC panel display template).

- [ ] **Step 3: Commit**

```bash
git add skills/calibrate/SKILL.md
git commit -m "$(cat <<'EOF'
calibrate step 7: ROIC panel + user-implied coherence checks

Replace the old "Damodaran canonical NOPAT" formula
(adjusted_roic × adjusted_invested_capital) with user-implied values
derived from the picks made in step 6b/6c. Step 7 now opens with a
ROIC panel showing raw, adjusted, user-implied projection, and
user-picked terminal ROIC in one place — the single most important
reference for the downstream value-of-growth and fundamental growth
checks.

The implied projection ROIC uses starting margin (year 0) and
marginal tax rate — a going-forward steady-state anchor comparable
to the terminal ROIC pick.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Update `docs/dcf-methodology.md` R&D capitalization section

**Files:**
- Modify: `docs/dcf-methodology.md` (lines 142-178, the "## R&D capitalization" section)

**Context:** Update the R&D section to describe the new informational role: values are computed and displayed, but the DCF itself uses whatever the user picks in calibration (or falls back to raw GAAP when uncalibrated).

- [ ] **Step 1: Replace the R&D capitalization section**

Use the Edit tool on `docs/dcf-methodology.md`.

`old_string`:
```markdown
## R&D capitalization

GAAP treats R&D as an operating expense. For valuation, Damodaran treats it as a capital expenditure — building an intangible research asset on the balance sheet and amortizing it over the product's commercial life. This adjustment produces a more accurate ROIC without changing free cash flow.

**Research asset** — straight-line amortization over N years, using pre-tax R&D (verified from Damodaran's R&DConv.xls spreadsheet):

```
Research Asset = Sum of R&D[year-i] × (N-i)/N   for i = 0 to N-1
```

The current year's R&D enters at 100% with zero amortization. Each prior year decays by 1/N. Year -N is fully amortized out (0 in asset) but contributes its final R&D/N to current-year amortization.

**Adjusted NOPAT:**

```
Adjusted NOPAT = EBIT(1-t) + R&D - Amortization
```

R&D and amortization enter at full pre-tax values. This works because R&D remains fully tax-deductible regardless of the valuation reclassification — taxes paid don't change. The "ignored tax benefit" (= (R&D - Amort) × t) is naturally captured.

**Adjusted Invested Capital:**

```
Adjusted IC = Equity + Debt - Cash - Investments + Research Asset
```

**FCF is unchanged.** R&D added back to NOPAT and R&D added to CapEx cancel exactly. What changes: NOPAT, invested capital, and ROIC — which flow into terminal reinvestment (g/ROIC), the fundamental growth check, and the value-of-growth check.

**Amortizable life by industry** (from Damodaran's R&DConv.xls):

| Industry | Life | Rationale |
|---|---|---|
| Software, Internet | 3 years | Short product cycles |
| Semiconductors, Electronics | 5 years | Moderate cycles |
| Pharma, Aerospace, Chemicals | 10 years | Long development/approval timelines |

The industry is determined from Alpha Vantage sector/industry data, with overrides for cases where the sector default is wrong (e.g., semiconductors within Technology).
```

`new_string`:
```markdown
## R&D capitalization

GAAP treats R&D as an operating expense. For valuation, Damodaran treats it as a capital expenditure — building an intangible research asset on the balance sheet and amortizing it over the product's commercial life. This adjustment produces a more accurate picture of operating margin, capital efficiency, and return on invested capital — without changing free cash flow.

**Role in our model: informational, not algorithmic.** The adjusted margin, S/C, and ROIC computed from R&D capitalization serve a display role. They appear in `calibrate` as reference anchors alongside raw GAAP values, and in `value`'s metrics table. They do NOT automatically flow into the DCF's projection math. The user explicitly picks starting operating margin, target operating margin, sales-to-capital ratio, and terminal ROIC in calibration; the DCF runs on those picks. When uncalibrated, the DCF falls back to raw GAAP values.

This is a deliberate divergence from Damodaran's `fcffginzu.xls`, which grosses up projection-starting EBIT by `delta × (1 + t_marginal)` to plumb adjusted values through the forward projection automatically. Our approach trades that automation for user deliberation — `calibrate` is designed as a thinking tool for a deliberate investor, not a plug-and-play calculator.

**Research asset** — straight-line amortization over N years, using pre-tax R&D (verified from Damodaran's R&DConv.xls spreadsheet):

```
Research Asset = Sum of R&D[year-i] × (N-i)/N   for i = 0 to N-1
```

The current year's R&D enters at 100% with zero amortization. Each prior year decays by 1/N. Year -N is fully amortized out (0 in asset) but contributes its final R&D/N to current-year amortization.

**Adjusted NOPAT** (used to compute `adjusted_roic` for display):

```
Adjusted NOPAT = EBIT(1-t) + R&D - Amortization
```

R&D and amortization enter at full pre-tax values. This is Damodaran's canonical pre-tax add-back: R&D remains fully tax-deductible regardless of the valuation reclassification, so the pre-tax amounts naturally capture the "ignored tax benefit" (= (R&D - Amort) × t). Note that under the informational-role framing, this NOPAT is shown in ROIC context displays but is never fed through the DCF's `× (1 − t)` projection formula — the DCF uses whatever margin the user explicitly picks.

**Adjusted Invested Capital:**

```
Adjusted IC = Equity + Debt - Cash - Investments + Research Asset
```

Used in `adjusted_roic = Adjusted NOPAT / Adjusted IC` and `adjusted_sales_to_capital = Revenue / Adjusted IC`, both display-only fields.

**FCF is unchanged by the adjustment** in Damodaran's explicit-CapEx formulation: R&D added back to NOPAT and R&D added to CapEx cancel exactly. Our DCF uses an S/C-based reinvestment approach rather than explicit CapEx tracking, so this invariance is not strictly preserved across a raw-vs-adjusted S/C swap. This is intentional — the S/C approach is a steady-state simplification that doesn't try to replicate Damodaran's invariance inside a different projection model.

**Amortizable life by industry** (from Damodaran's R&DConv.xls):

| Industry | Life | Rationale |
|---|---|---|
| Software, Internet | 3 years | Short product cycles |
| Semiconductors, Electronics | 5 years | Moderate cycles |
| Pharma, Aerospace, Chemicals | 10 years | Long development/approval timelines |

The industry is determined from Alpha Vantage sector/industry data, with overrides for cases where the sector default is wrong (e.g., semiconductors within Technology).
```

- [ ] **Step 2: Verify the edit**

Run: `grep -n "informational, not algorithmic" docs/dcf-methodology.md`

Expected: one match in the R&D capitalization section.

Run: `grep -c "display role\|informational role" docs/dcf-methodology.md`

Expected: at least 1.

- [ ] **Step 3: Commit**

```bash
git add docs/dcf-methodology.md
git commit -m "$(cat <<'EOF'
docs: update R&D capitalization section to reflect informational role

Add explicit language that adjusted margin, S/C, and ROIC serve a
display role in calibrate and value — they do not flow into the DCF
automatically. Explain the deliberate divergence from Damodaran's
fcffginzu.xls gross-up construction. Note the S/C-based reinvestment
approach means Damodaran's FCF-invariance claim doesn't strictly hold
across a raw/adjusted S/C swap under our model.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Update `docs/internal/damodaran-audit.md` item #13 third-pass note

**Files:**
- Modify: `docs/internal/damodaran-audit.md` (line 514 summary table row, line 557 Phase 3 DONE list entry)

**Context:** The audit doc has two places where item #13 is summarized — the summary table (line 514) and the Phase 3 DONE list (line 557). Both need a third-pass note. Line numbers may have shifted from prior edits; rely on the `grep -n` results from the context-gathering phase.

- [ ] **Step 1: Update line 514 (summary table row)**

Use the Edit tool on `docs/internal/damodaran-audit.md`.

`old_string`:
```markdown
| 13 | R&D capitalization | 3 | MEDIUM-HIGH | **DONE** | Pre-tax asset per Damodaran R&DConv.xls, industry amortizable life. First pass (2026-04-09): adjusted ROIC in calibrate/value. Second pass (2026-04-11): adjusted margin and adjusted S/C flow through calibrate anchors and DCF starting-point extraction — forward/reverse DCF consistent on adjusted basis |
```

`new_string`:
```markdown
| 13 | R&D capitalization | 3 | MEDIUM-HIGH | **DONE** | Pre-tax asset per Damodaran R&DConv.xls, industry amortizable life. First pass (2026-04-09): adjusted ROIC in calibrate/value. Second pass (2026-04-11): adjusted margin and adjusted S/C flow through calibrate anchors and DCF starting-point extraction. Third pass (2026-04-11 late): reframe from algorithmic to informational — adjusted values are display-only reference anchors in calibrate and value; DCF runs on user picks with raw GAAP fallback. Eliminates tax-treatment mixing surfaced in post-ship review. See `docs/internal/2026-04-11-rd-informational-design.md` |
```

- [ ] **Step 2: Update line 557 (Phase 3 DONE list entry)**

Use the Edit tool on `docs/internal/damodaran-audit.md`.

`old_string`:
```markdown
- Item 13: R&D capitalization per Damodaran's R&DConv.xls. Pre-tax research asset with straight-line amortization, industry-specific amortizable life (3yr software, 5yr semi, 10yr pharma). First pass (2026-04-09): adjusted ROIC flows into calibrate coherence checks and terminal ROIC anchoring. Second pass (2026-04-11): adjusted operating margin and adjusted S/C now also feed calibrate step 6b/6c anchors and the DCF starting-point extraction, so terminal ROIC is paired with adjusted NOPAT instead of mixing raw with adjusted. Forward and reverse DCF maintain round-trip consistency on the adjusted path. See `docs/internal/2026-04-11-rd-adjusted-basis-design.md` and `docs/internal/2026-04-11-rd-adjusted-basis-plan.md`. FCF unchanged.
```

`new_string`:
```markdown
- Item 13: R&D capitalization per Damodaran's R&DConv.xls. Pre-tax research asset with straight-line amortization, industry-specific amortizable life (3yr software, 5yr semi, 10yr pharma). First pass (2026-04-09): adjusted ROIC flows into calibrate coherence checks and terminal ROIC anchoring. Second pass (2026-04-11): adjusted operating margin and adjusted S/C also fed calibrate step 6b/6c anchors and DCF starting-point extraction. Third pass (2026-04-11 late): after post-ship review surfaced a tax-treatment mixing issue (DCF's `× (1 − t)` applied to pre-tax adjusted margin produced post-tax add-back NOPAT, off from Damodaran canonical pre-tax add-back by `t × delta` per year), reframed the fix from algorithmic to informational. Adjusted values are now display-only reference anchors in calibrate and value; DCF runs on user picks with raw GAAP fallback when uncalibrated. Calibrate step 6b now asks explicitly for starting margin (previously only target). Step 7 opens with a ROIC panel showing raw/adjusted/user-implied/terminal in one place. See `docs/internal/2026-04-11-rd-informational-design.md` and `docs/internal/2026-04-11-rd-informational-plan.md`. FCF invariance doesn't strictly hold in our S/C-based projection model under the new frame, but the S/C simplification was never compatible with Damodaran's explicit-CapEx invariance in the first place.
```

- [ ] **Step 3: Verify both edits**

Run: `grep -c "Third pass (2026-04-11 late)" docs/internal/damodaran-audit.md`

Expected: `2` (both the summary table row and the Phase 3 list entry).

Run: `grep -c "2026-04-11-rd-informational-design.md" docs/internal/damodaran-audit.md`

Expected: `2` (referenced from both rows).

- [ ] **Step 4: Commit**

```bash
git add docs/internal/damodaran-audit.md
git commit -m "$(cat <<'EOF'
audit: add third-pass note to item #13 (R&D capitalization)

Third pass reframes R&D capitalization from algorithmic DCF input to
calibration-time reference display. Eliminates the tax-treatment
mixing issue the second pass introduced and moves the decision of
which basis to use onto the user via explicit starting-margin picking
in calibrate step 6b. References the new design/plan docs.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Final validation

**Files:** (no edits; validation only)

**Context:** Confirm the full test suite passes, no unexpected drift, and the implementation matches the design doc.

- [ ] **Step 1: Run the full test suite**

Run: `cd /Users/kaichen/Projects/intrinsic && PYTHONPATH=. python3 -m pytest tests/ -q 2>&1 | tail -10`

Expected: ending like `308 passed in 0.2-0.5s`. Test count calculation:
- Starting count before this plan: 308
- Task 1 removed 4 tests: 304
- Task 2 added 2 tests: 306
- Task 3 added 2 tests: 308

Final count: **308 passed**.

If any tests fail, STOP and diagnose before proceeding.

- [ ] **Step 2: Quick sanity check against MSFT cached data**

Run:
```bash
cd /Users/kaichen/Projects/intrinsic && PYTHONPATH=. python3 -c "
import json
from pathlib import Path
from stock_analyzer.dcf import DCFModel, DCFAssumptions
from stock_analyzer.metrics import FinancialMetrics

msft_path = Path('data/MSFT/financial_data.json')
if not msft_path.exists():
    print('MSFT cache not found — skipping sanity check')
    exit(0)

data = json.loads(msft_path.read_text())
inputs = FinancialMetrics.calculate_dcf_inputs(
    income_statement=data['data']['income_statement_annual']['reports'],
    balance_sheet=data['data']['balance_sheet']['reports'],
    cash_flow=data['data']['cash_flow']['reports'],
    overview=data['data']['overview'],
    income_annual=data['data']['income_statement_annual']['reports'],
)

# adjusted_* fields are still computed and exposed as display
assert inputs['adjusted_operating_margin'] is not None, 'adjusted_operating_margin should still be computed'
assert inputs['adjusted_sales_to_capital'] is not None, 'adjusted_sales_to_capital should still be computed'
assert inputs['adjusted_roic'] is not None, 'adjusted_roic should still be computed'
assert inputs['research_asset'] is not None, 'research_asset should still be computed'

# Default DCF with operating_margin=None should NOT use adjusted_operating_margin
# (the new two-tier chain falls back to raw EBIT/Revenue)
quote = data['data'].get('quote', {})
price = float(quote.get('price', 400.0))
shares = inputs['market_cap'] / price

model = DCFModel(DCFAssumptions())  # defaults: operating_margin=None
result = model.calculate_fair_value(inputs, shares, price, verbose=True)

raw_margin = inputs['operating_income'] / inputs['revenue']
adj_margin = inputs['adjusted_operating_margin']
print(f'raw margin:      {raw_margin*100:.3f}%')
print(f'adjusted margin: {adj_margin*100:.3f}%')
print(f'DCF used margin: {result[\"operating_margin\"]*100:.3f}%')
assert abs(result['operating_margin'] - raw_margin) < 1e-9, (
    f'DCF should use raw margin, but picked {result[\"operating_margin\"]}'
)
print('OK: DCF correctly ignored adjusted_operating_margin when user margin is None')
"
```

Expected: print statements showing raw, adjusted, and DCF-used margins, with DCF margin equal to raw. `OK:` line at the end. No AssertionError.

- [ ] **Step 3: Verify the implementation matches the design doc**

Run: `git log --oneline -10`

Expected output shows 9 commits at the top (the design doc commit plus 8 implementation commits from Tasks 1-8):
```
<hash> audit: add third-pass note to item #13 (R&D capitalization)
<hash> docs: update R&D capitalization section to reflect informational role
<hash> calibrate step 7: ROIC panel + user-implied coherence checks
<hash> calibrate step 6c: display block for raw + adjusted S/C anchors
<hash> calibrate step 6b: explicit starting margin question + display block
<hash> Revert S/C precedence chain in dcf.py
<hash> Revert margin precedence chain in dcf.py
<hash> Remove TestRdAdjustedBasis class
<hash> Design: reframe R&D capitalization as informational, not algorithmic
```

- [ ] **Step 4: Run the finishing-a-development-branch skill**

Invoke `superpowers:finishing-a-development-branch`. This will verify tests, present merge/push options to the user, and handle the chosen workflow.

---

## Out of scope (from the design doc — NOT touched by this plan)

- Any changes to `stock_analyzer/metrics.py` (R&D capitalization math stays unchanged)
- Any changes to `DCFAssumptions` dataclass
- Forward DCF math, reverse DCF, terminal value formula, WACC, equity bridge, sensitivity grid
- `skills/value/SKILL.md` (already displays raw + adjusted correctly)
- Tax rate derivation in `metrics.py` (effective vs marginal) — pre-existing design
- Industry amortizable life table corrections (separate audit follow-up)
- Damodaran-style gross-up (`delta × (1 + t_marginal)`) — considered and explicitly rejected
- Migration logic for existing `assumptions.json` files — silent drift, no code migration
- `test_adjusted_*` tests in `test_metrics.py` — kept, they still test display fields
