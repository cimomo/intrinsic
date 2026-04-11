# Design Spec: R&D Capitalization as Informational, Not Algorithmic

**Date:** 2026-04-11
**Status:** Draft
**Follow-up to:** `docs/internal/2026-04-11-rd-adjusted-basis-design.md` (third pass on audit item #13)

---

## Problem

The previous design (`2026-04-11-rd-adjusted-basis-design.md`) added a precedence chain in `dcf.py` so that `adjusted_operating_margin` and `adjusted_sales_to_capital` flow automatically from `calculate_dcf_inputs()` into the DCF's starting-point extraction when R&D data is available. The intent was to keep forward and reverse DCF internally consistent on the adjusted basis.

A post-ship review surfaced a tax-treatment mixing bug. `adjusted_operating_margin` is computed as `(EBIT + R&D − Amortization) / revenue` — a pre-tax economic margin — but the DCF's NOPAT formula multiplies by `(1 − tax_rate)`, which effectively applies the "post-tax add-back" form `(EBIT + R&D − Amort)(1 − t)`. Damodaran's canonical formula (verified against `R&DConv.xls` row 30) is the pre-tax add-back `EBIT(1 − t) + (R&D − Amort)`, where the R&D delta preserves its tax shield. The difference is `tax × (R&D − Amort)` per year — for NVDA about $2.4B/year, propagating to roughly 2% of fair value.

Investigation of Damodaran's full DCF (`fcffginzu.xls`) showed he compensates with an engineering approximation: the projection-starting EBIT is grossed up by `delta × (1 + t_marginal)` (cell `Valuation Model!C41 = D3 + 'R&D converter'!D40`, where `D40 = delta × marginal_tax_rate`). This lands within rounding of the canonical formula when effective tax rate is near `t_marginal / (1 + t_marginal)`, and degrades to a ~6% under-count of the delta term by year 10 as the projection's tax rate transitions to marginal.

Replicating this in our code would require: threading `t_marginal` into `metrics.py`, computing the gross-up once, accepting a degrading approximation as the DCF's tax rate transitions across the projection, and maintaining two distinct "adjusted margin" values (display vs DCF projection). It would also leave the uncalibrated `/value` path on a silent auto-plumb basis that the user never consciously picked.

## Reframe

The core insight from the investigation: **R&D capitalization is informational, not algorithmic.** Its purpose is to give the user a clearer picture of the business — what the firm earns on its capital when R&D is treated as the investment it really is. Once the user has that picture, they form a view and pick DCF assumptions (starting margin, target margin, S/C, terminal ROIC) that reflect their judgment. The DCF computes fair value from those picks.

Damodaran automates this translation in his spreadsheet because his tool is designed to be plug-and-play for students. Our `calibrate` skill is designed as a thinking tool for a deliberate investor — we can surface the raw and adjusted anchors and let the user drive. This eliminates the basis-mixing problem at its root: if the DCF never tries to interpret the basis of its inputs, there is nothing to mix.

The `metrics.py` R&D capitalization computations (research asset, amortization, adjusted NOPAT delta, adjusted ROIC, adjusted margin, adjusted S/C) all remain — they now serve a display role rather than a DCF-input role. The user sees them in `calibrate` as reference anchors alongside raw values, and in `value`'s metrics table. The DCF never consumes them directly.

## Scope

**In scope:**
- Revert `dcf.py` margin and S/C precedence chains to user-or-raw (two-tier, not three-tier)
- Add explicit starting operating margin question to `calibrate` step 6b
- Add raw/adjusted display block to `calibrate` step 6b and 6c (anchors for user picks)
- Rewrite `calibrate` step 7 with a ROIC panel that surfaces raw, adjusted, user-implied projection, and terminal ROIC in one place
- Update `calibrate` step 7 fundamental growth check to compute NOPAT from user's picks
- Remove `TestRdAdjustedBasis` class from `tests/test_dcf.py`
- Add two sanity tests confirming the simplified precedence (user assumption or raw fallback)
- Update `docs/dcf-methodology.md` R&D capitalization section
- Update `docs/internal/damodaran-audit.md` item #13 with third-pass note

**Out of scope:**
- Any changes to `metrics.py` — the R&D capitalization math (research asset formula, industry amortization table, adjusted ROIC / margin / S/C derivation) stays as-is
- Any changes to `DCFAssumptions` dataclass
- Any changes to the forward DCF math, reverse DCF, terminal value formula, WACC computation, equity bridge, sensitivity grid
- `value` skill metrics table — already displays raw alongside adjusted correctly
- Tax rate derivation in `metrics.py` (effective vs marginal) — pre-existing design, unaffected by this reframe
- Damodaran-style gross-up (`delta × (1 + t_marginal)`) — considered and explicitly rejected in favor of the user-driven approach
- Industry amortizable life table corrections (Auto Manufacturers, Telecom Equipment) — separate audit follow-up
- Auto-migration of existing `assumptions.json` files — silent drift, same pattern as previous pass
- `/value` metrics table — no changes (already correct)
- `/research`, `/report`, `/analyze`, `/fetch` skills — unaffected

## Solution

### `stock_analyzer/dcf.py` changes

Two changes inside `calculate_fair_value()`.

**Margin resolution** (currently lines 407-410, the `or`-chain introduced in the previous fix):

```python
if self.assumptions.operating_margin is not None:
    operating_margin = self.assumptions.operating_margin
elif revenue > 0:
    operating_margin = operating_income / revenue
else:
    operating_margin = 0.15
```

User assumption wins; otherwise derive from raw GAAP. The `is not None` check replaces the truthy `or` chain, which also fixes a pre-existing edge case where an explicit `operating_margin=0.0` would silently fall through.

**S/C resolution** (currently lines 415-431): delete the middle branch that reads `adjusted_sales_to_capital`. Remaining structure:

```python
if self.assumptions.sales_to_capital_ratio is not None:
    sales_to_capital = self.assumptions.sales_to_capital_ratio
else:
    # existing raw balance-sheet fallback (unchanged):
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

Nothing else in `dcf.py` changes. `project_free_cash_flows`, `calculate_terminal_value`, `reverse_dcf`, `_recalc_fair_value`, WACC computation, equity bridge, sensitivity grid — all unaffected.

### `skills/calibrate/SKILL.md` changes

**Step 6b (Operating Margin)** gains an explicit starting-margin question in addition to the existing target-margin question.

Current step 6b anchors the target-margin pick on `dcf_inputs['adjusted_operating_margin']` and does not explicitly ask for the starting margin — it falls through to the DCF's precedence chain, which under the previous design silently used adjusted.

New step 6b structure:

1. **Display block** (before any questions):
   ```
   Current operating margin:
     Raw (GAAP, R&D expensed):       X.X%
     Adjusted (R&D capitalized):     Y.Y%   [N-year amortization]
     5-year raw range:               A.A% – B.B%   [trend: expanding / stable / compressing]

   Raw is what Alpha Vantage reports from GAAP financials. Adjusted is what
   the business would show if R&D were treated as capital expenditure
   (amortized over N years rather than expensed). Use these as reference
   points for your pick — pick what reflects your view of the business.
   ```

   Adjusted row is omitted when `dcf_inputs['adjusted_operating_margin']` is `None`.

2. **Question 1 — Starting operating margin (year 0).** `AskUserQuestion` with options: raw X.X%, adjusted Y.Y% (when available), custom. Stored to `assumptions.operating_margin`.

3. **Question 2 — Target operating margin (year 10 for convergence).** `AskUserQuestion` with options: same as starting (flat), expand to Z%, contract to W%, custom. When the user picks "same as starting," set `target_operating_margin = None` so the DCF's existing "no convergence" path runs.

Both questions are informed by the same display block above.

**Step 6c (Sales-to-Capital Ratio)** gets the same display pattern before its existing single S/C question. No new questions — S/C is a single value in the DCF, no starting/target split needed. New display:

```
Current sales-to-capital:
  Raw (R&D expensed):               X.Xx
  Adjusted (R&D capitalized):       Y.Yx
  5-year raw historical range:      [Avg/Incremental S/C table as today]

Raw treats R&D as operating expense; adjusted treats the accumulated
research asset as invested capital. Pick what reflects your view of
the business's true capital intensity.
```

Adjusted row omitted when `dcf_inputs['adjusted_sales_to_capital']` is `None`. The historical raw trend table stays as-is — directional context that's still the best available signal.

**Step 6d (Terminal ROIC)** — unchanged. Already uses `dcf_inputs['adjusted_roic']` correctly as the anchor for terminal ROIC selection.

**Step 7 (Coherence check)** opens with a ROIC panel:

```
ROIC context:
  WACC (floor):                  W.W%
  Raw current ROIC:              X.X%   (GAAP, R&D expensed)
  Adjusted current ROIC:         Y.Y%   (Damodaran, R&D capitalized)   [when available]
  Your implied projection ROIC:  Z.Z%   (= starting margin × S/C × after-tax)
  Your terminal ROIC pick:       T.T%   (convergence target for stable growth)
```

The implied projection ROIC is derived from the user's picks and the DCF's marginal tax rate:

```
implied_projection_ROIC = picked_operating_margin × picked_sales_to_capital × (1 − assumptions.tax_rate)
```

This uses the **starting margin** (year 0) rather than target — it represents the ROIC the firm will realize near the start of the projection, which is the relevant anchor for the fundamental growth check. It uses **marginal** tax rate (not `effective_tax_rate`) because it's a going-forward average and should match the terminal-state assumption the rest of the coherence check references.

Downstream checks reference the panel:

- **Value of growth.** Compare implied projection ROIC to WACC. If below, flag: "Your picks imply ROIC of Z.Z% vs WACC of W.W% — at these returns, growth destroys value."

- **Fundamental growth check.** Formula:

  ```
  user_NOPAT         = Revenue × picked_operating_margin × (1 − assumptions.tax_rate)
  reinvestment_rate  = (Revenue × growth_rate / picked_sales_to_capital) / user_NOPAT
  fundamental_growth = reinvestment_rate × implied_projection_ROIC
  ```

  Compare `fundamental_growth` to the assumed revenue growth rate. Flag significant divergence with the same language as today.

- **Implied reinvestment vs CapEx, directional bias check, sanity vs research** — unchanged in logic. Any ROIC reference in these checks resolves to implied projection ROIC.

The previous formula `dcf_inputs['adjusted_roic'] × dcf_inputs['adjusted_invested_capital']` is no longer used anywhere in coherence checks.

### `skills/value/SKILL.md` changes

None. Step 2 metrics table already displays raw and adjusted side-by-side for margin, S/C, and ROIC — correct under the new frame. The display role is preserved.

### `docs/dcf-methodology.md` changes

Update the R&D capitalization section to reflect the new role. Add language such as:

> The adjusted margin, S/C, and ROIC values computed from R&D capitalization serve an informational role — they are displayed in `calibrate` as reference anchors alongside raw values, and in `value`'s metrics table. They do not automatically flow into the DCF's projection math. The user explicitly picks operating margin, S/C, and terminal ROIC in calibration; the DCF runs on those picks. This is a deliberate divergence from Damodaran's `fcffginzu.xls`, which uses a grossed-up EBIT construction (`EBIT + delta × (1 + t_marginal)`) to plumb adjusted values through the forward projection automatically. Our approach trades that automation for user deliberation: `calibrate` is designed as a thinking tool, not a plug-and-play calculator.

Add a one-line note that `adjusted NOPAT = EBIT(1 − t) + (R&D − Amort)` (pre-tax add-back, per Damodaran canonical) remains the formula used to compute `adjusted_roic` for display, but is never fed through a `× (1 − t)` DCF projection under the new frame.

### `docs/internal/damodaran-audit.md` changes

Item #13 summary row gains a third-pass note:

> Third pass (2026-04-11 late): reframe from "adjusted values flow through DCF automatically" to "adjusted values are displayed as calibration-time reference; user picks DCF inputs explicitly." Eliminates the tax-treatment mixing issue surfaced in post-ship review and matches the deliberate-investor model `calibrate` is designed around. See `docs/internal/2026-04-11-rd-informational-design.md`.

The audit item stays in DONE status. The point of the original fix — giving the user a clearer picture of R&D-heavy businesses and supporting calibration on the economic basis — is preserved. Only the mechanism changes.

## Tests

### Removed

From `tests/test_dcf.py`:
- `TestRdAdjustedBasis` class (4 tests): `test_dcf_uses_adjusted_operating_margin_when_present`, `test_dcf_uses_adjusted_sales_to_capital_when_assumption_is_none`, `test_dcf_user_assumption_still_wins_over_adjusted`, `test_forward_reverse_dcf_roundtrip_on_adjusted_path`. These test the precedence chain we're reverting.

### Kept

In `tests/test_metrics.py`, all `test_adjusted_*` tests stay unchanged. The fields are still computed and exposed by `calculate_dcf_inputs()`; they now serve a display role rather than a DCF-input role. Their correctness tests remain meaningful.

### Added

To `tests/test_dcf.py`:

- `test_dcf_margin_user_or_raw_fallback` — constructs `financial_data` with both `operating_income` and `adjusted_operating_margin` set. Asserts: (a) when `assumptions.operating_margin` is set, that value wins; (b) when `assumptions.operating_margin` is `None`, the DCF's resolved margin equals `operating_income / revenue` (raw), NOT `adjusted_operating_margin`, regardless of whether the adjusted field is present in `financial_data`.

- `test_dcf_sc_user_or_raw_fallback` — parallel test for S/C. Asserts: (a) user-set `sales_to_capital_ratio` wins; (b) when unset, the DCF uses the raw balance-sheet derivation even when `adjusted_sales_to_capital` is present in `financial_data`.

## Fallback behavior

### Uncalibrated `/value`

When the user runs `/value` without having run `/calibrate`, the DCF uses raw values: margin from `operating_income / revenue`, S/C from `revenue / invested_capital` (where invested capital is the raw balance-sheet computation). For R&D-heavy stocks this is ~1-2% lower fair value than under the previous precedence-chain behavior. The design accepts this as the cost of the honest default — the uncalibrated path produces a GAAP DCF, and the user who wants R&D-aware thinking should run `/calibrate`.

### Zero-R&D companies (financial services, most utilities, etc.)

`calculate_rd_capitalization` returns `None` → every `adjusted_*` field in `calculate_dcf_inputs` is `None`. Calibrate's display blocks fall through to raw-only. Value's metrics table falls through to raw-only. No behavior change vs today.

### Partial R&D data (short historical window)

When `calculate_rd_capitalization` succeeds but amortization history is limited (common for 5-year Alpha Vantage fetch with 5 or 10-year amortization), the adjusted numbers are still computed on the available window. They're shown alongside raw in the display — user's judgment covers the partial-data caveat.

## Migration

Silent drift, same pattern as the previous pass. Existing `assumptions.json` files have `operating_margin = None` almost universally, because `calibrate` has never asked for starting margin. On next `/value` run after this change lands, those files use raw fallback — a ~1-2% fair value shift on R&D-heavy stocks. Users re-calibrate on demand to set an explicit starting margin.

This is the second basis drift in the same area within a short window (previous drift was adjusted→mixed when the prior design shipped). Acknowledged explicitly but not blocked on.

No code-level migration logic. No auto-population of values on load. No warnings at load time.

## Risks

- **Second basis drift.** Fair values for previously-calibrated stocks shift 1-2% on next run if R&D-heavy. Accepted — see Migration.

- **Users who relied on the auto-plumb behavior.** Anyone who explicitly expected the previous behavior (where uncalibrated `/value` quietly used adjusted fields) sees different numbers. The design rationale is honesty: the user should explicitly pick what basis to use, not inherit it from whether R&D data happened to be present.

- **Calibrate skill prose drift.** Step 6b and 6c both describe raw-vs-adjusted anchor display. If the underlying `metrics.py` field names or the `AskUserQuestion` option patterns ever evolve, both sites need updating in lockstep. Mitigated by both being flat prose following the same template and by `metrics.py` remaining the single source of truth for the numbers.

- **Implied ROIC formula hides the tax assumption.** `implied_projection_ROIC = margin × S/C × (1 − tax_rate)` uses the DCF's marginal tax rate. If the user has set `effective_tax_rate`, the actual year-1 realized ROIC will be slightly higher (less tax). The panel number is meant as a going-forward steady-state anchor, not a year-by-year exact value. A future refinement could show a second row for "year-1 effective ROIC" if the effective-vs-marginal transition matters to the user, but that's out of scope here.

- **Starting margin vs target margin in the fundamental growth check.** The check uses starting margin for NOPAT and implied ROIC. If the user has set a significantly higher target margin (margin expansion story), the later years of the projection realize a different implied ROIC than the check assumes. The check is best-interpreted as "given the firm's starting economics, is the growth rate supportable?" which is the correct framing for catching over-optimistic growth assumptions.

## What this does NOT change

- DCF projection math (revenue × margin × (1 − t) − reinvestment, terminal value formula, WACC, equity bridge)
- Reverse DCF algorithm
- Sensitivity grid behavior
- `DCFAssumptions` dataclass
- `metrics.py` R&D capitalization computation — research asset formula, industry amortization table, adjusted NOPAT delta, adjusted ROIC, adjusted margin, adjusted S/C — all still computed, now display-only
- `value` skill metrics table — already displays raw + adjusted correctly
- Alpha Vantage fetch layer
- Data cache structure (`financial_data.json`)
- Manual override mechanism (`_manual_overrides` tracking)
- `research`, `report`, `analyze`, `fetch` skills
- Tax rate derivation (effective from raw financials in `metrics.py`, marginal in `DCFAssumptions`)

## Files changed

| File | Change |
|------|--------|
| `stock_analyzer/dcf.py` | Revert margin and S/C precedence chains to user-or-raw (~15 lines net delta) |
| `skills/calibrate/SKILL.md` | Step 6b: add starting margin question + display block; Step 6c: add display block; Step 7: ROIC panel + user-implied formulas (~60 lines revised) |
| `tests/test_dcf.py` | Remove `TestRdAdjustedBasis` class (~65 lines); add two sanity tests (~30 lines) |
| `docs/dcf-methodology.md` | Update R&D capitalization section to reflect informational role (~15 lines) |
| `docs/internal/damodaran-audit.md` | Add item #13 third-pass note |
| `docs/internal/2026-04-11-rd-informational-design.md` | This design doc (new) |

Net implementation delta: roughly 150-200 lines changed, 100 lines removed, heavily concentrated in `skills/calibrate/SKILL.md`.
