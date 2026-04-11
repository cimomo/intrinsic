# Design Spec: R&D Adjusted-Basis Consistency Fix

**Date:** 2026-04-11
**Status:** Draft
**Follow-up to:** `docs/internal/2026-04-09-rd-capitalization-design.md` (audit item #13)

---

## Problem

The original R&D capitalization work (audit #13, completed 2026-04-09) added `adjusted_roic`, `adjusted_invested_capital`, `research_asset`, `rd_amortization`, and related fields to `calculate_dcf_inputs()`. It also updated `calibrate` and `value` skills to display `adjusted_roic` as the anchor for setting terminal ROIC, and to use `adjusted_roic` in the calibrate coherence check.

However, the fix stopped at ROIC. The rest of the DCF pipeline still runs on raw GAAP values:

- **Calibrate step 6b (operating margin)** shows current raw operating margin and raw historical trend as the anchor for picking target margin.
- **Calibrate step 6c (sales-to-capital)** shows raw average and raw incremental S/C as the anchor for picking the S/C ratio.
- **`dcf.py:407-410`** derives the DCF's year-1 starting margin as `operating_income / revenue` — raw operating income.
- **`dcf.py:415-431`** falls back to `revenue / invested_capital` where `invested_capital` is the raw balance-sheet figure — used whenever the user hasn't explicitly set a `sales_to_capital_ratio` assumption.
- **Calibrate step 7 coherence checks** (fundamental growth + value of growth) use `adjusted_roic` but compute reinvestment rate from raw NOPAT and raw S/C, producing a basis-mixed number.

When a user picks `terminal_roic` anchored on adjusted ROIC (e.g. 19% for a wide-moat company where adjusted ROIC is 22% and WACC is 10%), but the DCF then computes `terminal_fcf = raw_nopat × (1 − g/terminal_roic)`, the identity `FCF = NOPAT × (1 − g/ROIC)` breaks because NOPAT and ROIC are no longer paired. The resulting terminal FCF is neither the correct raw FCF nor the correct adjusted FCF.

Damodaran is explicit (Chapter 10, page 17): capitalizing R&D must leave FCF unchanged. The mixing violates that invariant. For R&D-heavy names like MSFT and NVDA where the raw-vs-adjusted ROIC spread is several percentage points, this translates to roughly 4-5% of fair value per share — real, but bounded.

The same mixing also affects `reverse_dcf`, since it reuses `calculate_fair_value` in its binary search, and affects calibrate's fundamental growth check, which was intended to catch "you assumed X% growth but your reinvestment doesn't support it" but produces garbled numbers when ROIC is on a different basis than NOPAT and S/C.

## Goal

Make every value the user picks in calibrate, and every value the DCF consumes during projection and terminal value calculation, sit on the same adjusted basis when R&D capitalization data is available. Fall back to raw seamlessly when it isn't. Restore internal consistency to forward DCF, reverse DCF, and calibrate's coherence checks, without changing any of the DCF math itself.

## Scope

**In scope:**
- Add `adjusted_operating_margin` and `adjusted_sales_to_capital` to `calculate_dcf_inputs()` return dict as pre-computed fields.
- Modify `dcf.py` to prefer adjusted values at its two starting-point extraction sites (margin and S/C).
- Update calibrate skill steps 6b, 6c, and 7 to display adjusted anchors with raw values shown in parentheses for reference.
- Update value skill step 2 metrics table to show adjusted margin and adjusted S/C alongside the already-present adjusted ROIC.
- Add tests for the two new metrics fields and one integration test verifying forward/reverse DCF consistency on the adjusted path.
- Update `docs/internal/damodaran-audit.md` item #13 status to reflect this second-pass fix.

**Out of scope (explicit non-goals):**
- Historical adjusted margin time series — Alpha Vantage's 5-year annual income statement window is insufficient for multi-year clean adjusted history on most amortization lives (see Data Constraint below). Current-year adjusted margin is the anchor; raw historical trend stays as trend context.
- Historical adjusted S/C time series — same data constraint.
- Fetching more historical data from Alpha Vantage or additional providers.
- Auto-migration of existing `assumptions.json` files. Silent drift — users re-calibrate on demand.
- Basis marker field in `assumptions.json` — no `_basis` flag.
- User-facing opt-out to force raw basis. Manual overrides via `_manual_overrides` remain the escape hatch for disagreeing with R&D capitalization on specific stocks.
- Changes to `DCFAssumptions` dataclass, terminal value formula, reverse DCF algorithm, WACC computation, equity bridge, sensitivity grid, or any other DCF internal.
- Industry amortizable-life table corrections (Auto Manufacturers, Telecom Equipment, etc.) — those are tracked as a separate follow-up noted during the audit.

## Data Constraint

To compute a "clean" historical adjusted margin for year Y with amortizable life N, we need R&D data for years Y through Y−N. Alpha Vantage returns 5 years of annual income statements per call, so:

| Amortizable life | Clean historical years computable |
|---|---|
| 3 years (software, MSFT/GOOG) | 2 years (current + 1 prior) |
| 5 years (semiconductors, NVDA) | 0 prior years, partial current |
| 10 years (drugs, aerospace) | 0 prior years, partial current |

This constraint makes multi-year adjusted margin history impossible without a data layer change. The design accepts this: calibrate shows **current-year adjusted as the anchor**, with **raw historical range as the trend context** ("directional" information — is the company expanding or compressing margin over time, on the raw scale).

## Solution

### metrics.py changes

Inside `calculate_dcf_inputs()`, extend the existing R&D capitalization block at `stock_analyzer/metrics.py:454-479`. After `adjusted_roic` is computed, derive two additional pre-computed fields:

```python
adjusted_operating_margin = None
adjusted_sales_to_capital = None

if rd_cap and rd_cap["research_asset"] > 0:
    # ... existing lines setting research_asset, rd_amortization, etc. ...
    adjusted_ic = invested_capital + research_asset
    if adjusted_ic > 0:
        nopat_raw = operating_income * (1 - tax_rate)
        adjusted_nopat = nopat_raw + rd_cap["adjusted_nopat_delta"]
        adjusted_roic = adjusted_nopat / adjusted_ic
        adjusted_invested_capital = adjusted_ic

        # New: adjusted operating margin (pre-tax economic margin)
        adjusted_operating_income = operating_income + rd_cap["adjusted_nopat_delta"]
        if revenue > 0:
            adjusted_operating_margin = adjusted_operating_income / revenue

        # New: adjusted sales-to-capital (revenue per unit of adjusted capital)
        adjusted_sales_to_capital = revenue / adjusted_ic
```

Both fields are added to the return dict at the bottom of the function, next to the existing `adjusted_*` fields. They resolve to `None` when no R&D data is available, matching the existing convention.

`adjusted_operating_income` is a local variable used only for readability in the margin derivation; it is not returned.

### dcf.py changes

Two starting-point swaps, both at `stock_analyzer/dcf.py` inside `calculate_fair_value()`.

**Margin derivation at line 407-410:**

```python
operating_margin = (
    self.assumptions.operating_margin or
    financial_data.get('adjusted_operating_margin') or
    (operating_income / revenue if revenue > 0 else 0.15)
)
```

Precedence: user-set assumption wins over adjusted, adjusted wins over raw fallback.

**S/C fallback at line 415-431:**

```python
if self.assumptions.sales_to_capital_ratio is not None:
    sales_to_capital = self.assumptions.sales_to_capital_ratio
elif financial_data.get('adjusted_sales_to_capital') is not None:
    sales_to_capital = financial_data['adjusted_sales_to_capital']
else:
    # Existing raw fallback
    equity = financial_data.get('equity', market_cap)
    cash = financial_data.get('cash', 0)
    sti = financial_data.get('short_term_investments', 0)
    lti = financial_data.get('long_term_investments', 0)
    invested_capital = equity + total_debt - cash - sti - lti
    if invested_capital > 0:
        sales_to_capital = revenue / invested_capital
    else:
        sales_to_capital = 1.5
```

Same precedence pattern: user assumption > adjusted > raw fallback.

**Nothing else in `dcf.py` changes.** `calculate_terminal_value`, `reverse_dcf`, `_recalc_fair_value`, `_project_fcfs`, the WACC computation, the equity bridge, the sensitivity grid — all continue to consume whatever starting margin and S/C are resolved at the two swap sites, so they automatically inherit adjusted values when available. The mixing inconsistency resolves itself once the two resolution sites prefer adjusted.

### calibrate skill changes

**Step 6b (Operating Margin)** at `skills/calibrate/SKILL.md:282-284`. Replace the current raw-only framing with an adjusted-primary display:

- When `dcf_inputs['adjusted_operating_margin']` is present, show it as the primary anchor with raw margin in parentheses and raw 5-year range as trend context. Example phrasing: `"Current margin: 47% adjusted (44% raw GAAP). 5-year raw trend: 40-44% — expanding."`
- When adjusted is absent (zero-R&D company), fall back to the current raw-only display.

**Step 6c (Sales-to-Capital)** at `skills/calibrate/SKILL.md:286-292`. Same pattern:
- Current adjusted S/C as the primary anchor, with raw average and raw incremental shown as context.
- The existing instruction to compute 5+ years of raw historical S/C stays in place — that trend context is still the best available signal for whether capital efficiency is improving or deteriorating.
- Fallback: raw-only display when adjusted is unavailable.

**Step 6d (Terminal ROIC)** at `skills/calibrate/SKILL.md:294-341` — unchanged. Already uses adjusted ROIC correctly.

**Step 7 (Coherence check)** at `skills/calibrate/SKILL.md:343-375`. Small wording clarification: the fundamental growth check formula should explicitly say "adjusted NOPAT" and "adjusted ROIC" to remove ambiguity. No computation changes — the formula becomes internally consistent automatically because all the inputs (margin, S/C, ROIC) are now on the adjusted basis after the user completes step 6.

### value skill changes

**Step 2 (Key Metrics)** at `skills/value/SKILL.md:30-51`. Extend the existing metrics display to include adjusted margin and adjusted S/C alongside the already-present adjusted ROIC:

```
Operating Margin: X.X% (adjusted, R&D capitalized) | Raw GAAP: Y.Y%
Sales-to-Capital:  Z.Zx (adjusted)                  | Raw: W.Wx
ROIC:              A.A% (adjusted, N-year amortization) | Unadjusted: B.B%
```

Fallback to raw-only display when adjusted fields are absent.

## Fallback behavior (zero-R&D companies)

For companies without R&D (financial services, most utilities, retail without product development lines), `calculate_rd_capitalization` returns `None`, and every `adjusted_*` field in the `calculate_dcf_inputs` return dict resolves to `None`. The precedence chains in `dcf.py` fall through to the raw fallback paths, and the skills fall through to raw-only display. Behavior is identical to today's code for these companies. No special handling required.

## Tests

Add to `tests/test_metrics.py`:

1. **`test_adjusted_operating_margin_basic`** — given known operating_income, current R&D, rd_amortization, and revenue, assert `adjusted_operating_margin` matches hand-computed value.
2. **`test_adjusted_sales_to_capital_basic`** — given known revenue and adjusted_invested_capital, assert `adjusted_sales_to_capital` matches.
3. **`test_adjusted_fields_none_when_no_rd`** — verify both new fields resolve to `None` when R&D data is absent, matching existing `adjusted_roic` behavior.

Add to `tests/test_dcf.py`:

4. **`test_dcf_prefers_adjusted_margin`** — construct `dcf_inputs` with both `operating_income` and `adjusted_operating_margin` set, verify the DCF's year-1 NOPAT uses the adjusted margin, not `operating_income / revenue`.
5. **`test_dcf_prefers_adjusted_sales_to_capital`** — construct `dcf_inputs` with both raw IC fields and `adjusted_sales_to_capital` set, verify the DCF's reinvestment calculation uses the adjusted value.
6. **`test_dcf_falls_back_to_raw_when_adjusted_absent`** — verify zero-R&D companies flow through the raw paths unchanged.
7. **`test_reverse_dcf_consistent_with_forward_on_adjusted_path`** — run forward DCF with adjusted flow, call reverse DCF with the resulting fair value as target, verify the implied growth rate matches the input revenue growth rate within tolerance (sanity check that forward and reverse are internally consistent).

## Migration

None. Existing `assumptions.json` files continue to work. The first time a user re-runs `/calibrate` on a previously-calibrated stock, they see adjusted anchors and can re-pick values. The first time they re-run `/value` without re-calibrating, they get a fair value number that differs from the pre-fix version by the basis-mixing correction — typically a few percent for R&D-heavy names, zero for R&D-less names. This is accepted as the cost of correctness.

No basis marker field in `assumptions.json`. No detection logic. No warning banner.

## Follow-up to audit #13

`docs/internal/damodaran-audit.md` currently marks item #13 (R&D capitalization) as "DONE" in Phase 3. That status reflected only the display of adjusted ROIC. After this fix lands, item #13 is genuinely complete: the adjusted values actually flow through calibration and valuation, rather than decorating them. Update the audit doc to note the second-pass fix and the date.

## Files changed

| File | Change |
|------|--------|
| `stock_analyzer/metrics.py` | Add `adjusted_operating_margin` and `adjusted_sales_to_capital` pre-computed fields to `calculate_dcf_inputs()` output (~10 lines) |
| `stock_analyzer/dcf.py` | Two precedence-chain swaps: margin derivation (line 407-410) and S/C fallback (line 415-431) (~5 lines of modifications) |
| `skills/calibrate/SKILL.md` | Update steps 6b, 6c, and 7 wording to read adjusted fields and display adjusted-primary with raw in parentheses |
| `skills/value/SKILL.md` | Update step 2 Key Metrics display to show adjusted margin and adjusted S/C alongside adjusted ROIC |
| `tests/test_metrics.py` | Three new tests for the two new fields and their None-fallback |
| `tests/test_dcf.py` | Four new tests for DCF precedence and forward/reverse consistency |
| `docs/internal/damodaran-audit.md` | Update item #13 status to reflect second-pass fix |

## Risks

- **Fair value shifts for previously-calibrated stocks.** Accepted — see Migration section. Users re-calibrate on demand.
- **Skill markdown drift.** The calibrate and value skill text both describe how to display adjusted anchors. If the formula or field names ever change, both skill files need updating. Mitigated by having the pre-computed fields in metrics.py as the single source of truth — skills just read field names, no formula logic in prose.
- **Precedence chain readability in `dcf.py`.** Three-level `or`/`elif` chains are slightly harder to scan than the current two-level fallback. Mitigated by the chains being short (2-4 lines each) and by comments explaining the order.

## What this does NOT change

- DCF math (terminal value formula, reinvestment identity, WACC, equity bridge)
- Reverse DCF algorithm
- Sensitivity grid behavior
- `DCFAssumptions` dataclass
- Alpha Vantage fetch layer
- Research, report, or analyze orchestrator skills
- Data cache structure (`financial_data.json`)
- Manual override mechanism
