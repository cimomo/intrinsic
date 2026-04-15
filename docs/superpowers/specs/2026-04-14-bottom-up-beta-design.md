# Bottom-Up Beta — Design

**Date:** 2026-04-14
**Status:** Approved for implementation
**Audit item:** #9 (Phase 2)

## Problem

The DCF currently uses Alpha Vantage's regression beta as input to CAPM. Regression betas have three structural problems:

1. **High noise** — standard error of ~0.20-0.30 per stock. A reported beta of 1.20 means "0.60 to 1.80" at 95% CI.
2. **Backward-looking** — reflects the company's past business mix and capital structure, not its current state.
3. **Cash distortion** — cash holdings have beta 0, so cash-heavy companies (MSFT, GOOGL, AAPL) show artificially low regression betas.

Damodaran's bottom-up approach replaces this with an industry-derived beta that averages out idiosyncratic noise (across ~50-400 firms per industry) and is rebuilt from the company's current capital structure.

## Damodaran's framework

For a single-business company:

```
Levered Beta = Unlevered Beta × (1 + (1 - t) × D/E)
```

Three inputs:
- **Unlevered Beta** — from Damodaran's industry table, cash-corrected ("pure-play" beta for the business)
- **t** — marginal tax rate (21% for US)
- **D/E** — current market debt-to-equity (debt = total debt; equity = market cap)

This is verbatim what his `fcffsimpleginzu.xlsx` spreadsheet implements. Three caveats applied here:

1. **Cash-corrected unlevered beta** — his published guidance recommends column H ("Unlevered beta corrected for cash") over column F ("Unlevered beta"), even though his mainstream Ginzu spreadsheet defaults to F. We use H per his stated best practice.
2. **Marginal tax rate**, not effective — explicit in his FAQ.
3. **Market D/E**, not book — book equity systematically misstates leverage for any company with a market premium over book value.

Multi-business support is deferred. For conglomerates, the user can manually override the final beta.

## Architecture

### New module: `stock_analyzer/damodaran_betas.py`

Contains:
- `DAMODARAN_BETAS` — dict keyed by industry name (~94 entries), each with `n_firms`, `unlevered_beta`, `cash_firm_value`, `unlevered_beta_corrected`, `de_ratio`
- `DAMODARAN_BETAS_DATE` — string like `"January 2026"` for staleness display
- `AV_TO_DAMODARAN_HINT` — dict mapping common Alpha Vantage industry strings to Damodaran industry names (~30-50 entries covering common cases)
- `DAMODARAN_SECTORS` — our own grouping of the 94 industries into ~10-15 sector buckets (Technology, Energy, Healthcare, Financials, etc.) for the picker UX. Damodaran's table doesn't have sector groupings — we define them.
- `suggest_industry(av_industry: str) -> Optional[str]` — returns suggested Damodaran industry from AV string, or `None` if no good match
- `get_unlevered_beta(industry: str) -> Optional[float]` — returns cash-corrected unlevered beta for industry, or `None` if industry not in table
- `compute_bottom_up_beta(industry, market_de, marginal_tax_rate) -> dict` — applies relevering formula. Returns dict with `levered_beta`, `unlevered_beta`, `industry`, `market_de`, `tax_rate`, `n_firms` for display by calibrate

Mirror the structure of the existing credit-rating tables in `metrics.py`. Same update cadence (annually in January when Damodaran refreshes).

### `DCFAssumptions` dataclass change (in `dcf.py`)

Add one field:
```python
damodaran_industry: Optional[str] = None
```

Pure metadata. The DCF model itself does not read it — calibrate uses it to recall the user's prior industry choice across runs. Beta itself is stored in the existing `beta` field.

### Calibrate skill flow change (`skills/calibrate/SKILL.md`, step 2 — Beta)

**First-time flow (no `damodaran_industry` in `_manual_overrides`):**

```
Beta:
  Regression beta (Alpha Vantage 5y): 0.90
  
  Industry: SEMICONDUCTORS (Alpha Vantage)
  → Suggested Damodaran industry: Semiconductor
  
  Bottom-up beta: 1.42
    = unlevered_β 1.30 (Semiconductor, cash-corrected, 99 firms)
    × (1 + (1 - 0.21) × D/E 0.15)
    
  Recommendation: 1.42 (bottom-up)
    Why: regression betas have ±0.25 standard error; bottom-up
    averages across 99 industry peers and removes cash/leverage noise.
```

`AskUserQuestion` with options:
1. Use bottom-up 1.42 (recommended) → store `beta=1.42`, `damodaran_industry="Semiconductor"`. Only `damodaran_industry` is added to `_manual_overrides`. `beta` is left out so it gets recomputed each run from the locked industry + current D/E.
2. Use regression 0.90 (Alpha Vantage) → store `beta=0.90` and add `beta` to `_manual_overrides`. No industry stored. Future runs keep this value.
3. Pick a different Damodaran industry → drops into sector-then-industry picker (two `AskUserQuestion` calls), then recomputes. Same persistence as option 1.
4. Custom beta value → user enters number, stored as `beta` in `_manual_overrides`. No industry stored. Future runs keep this value.

**Persistence summary:** The industry choice is the locked manual override (recomputed each run with current D/E). The beta value is only marked as manual override when the user explicitly picks regression or custom — i.e., when they're opting *out* of the bottom-up recomputation.

**Sector-then-industry picker (option 3):**

Two `AskUserQuestion` calls. First picks sector (Technology, Energy, Healthcare, etc. — ~10-15 sectors). Second picks industry within sector (~5-15 industries per sector). Avoids drowning the user in a 94-item flat list.

**Recall flow (`damodaran_industry` already in `_manual_overrides`):**

```
Industry: Semiconductor [manual override — set previously]
Bottom-up beta: 1.45 (recomputed with current D/E 0.16)

Use this? [Enter to accept, or change industry]
```

The industry choice is locked but the bottom-up beta is recomputed each run because D/E may have moved.

**Edge cases:**

| Situation | Handling |
|-----------|----------|
| AV returns no `Industry` field | Skip suggestion, show picker as default |
| `suggest_industry` returns `None` (no AV mapping) | Recommendation defaults to picker; show warning "no auto-match for AV industry X — please pick from list" |
| Industry stored in `_manual_overrides` no longer exists in `DAMODARAN_BETAS` (e.g., Damodaran renamed it) | Warn: "Stored industry 'X' not found in current table — please re-pick"; drop back to picker |
| `DAMODARAN_BETAS_DATE` is older than 14 months | Show a banner: "Damodaran industry betas are from {date}, may be stale — consider checking pages.stern.nyu.edu/~adamodar/pc/datasets/betas.xls" |

### No changes required

- `dcf.py` core math — beta is just a better number flowing through existing CAPM/WACC code
- `metrics.py` — beta is already a pass-through from `dcf_inputs['beta']`
- `stock_manager.py` — `assumptions.json` automatically picks up the new field via dataclass serialization
- All other skills (`/value`, `/research`, `/report`, `/fetch`, `/analyze`)

## Data flow

```
calibrate skill
    ↓ reads
av_fetcher.py → overview.Industry ("SEMICONDUCTORS")
                overview.MarketCapitalization
                balance_sheet → total_debt
    ↓
damodaran_betas.suggest_industry("SEMICONDUCTORS") → "Semiconductor"
    ↓
[user picks via AskUserQuestion]
    ↓
damodaran_betas.compute_bottom_up_beta(
    industry="Semiconductor",
    market_de=total_debt / market_cap,
    marginal_tax_rate=0.21,
)
    ↓ returns levered_beta=1.42 + breakdown
    ↓
assumptions.beta = 1.42
assumptions.damodaran_industry = "Semiconductor"
assumptions._manual_overrides += ["damodaran_industry"]   # not "beta"
    ↓ persisted to assumptions.json
    ↓
DCFModel.calculate_wacc(beta=1.42, ...) — unchanged
```

## Testing strategy

### `tests/test_damodaran_betas.py` (new)

TDD. Each function has a failing test first.

1. **`compute_bottom_up_beta` math** — known-input known-output. Use MSFT, NVDA, JPM examples computed by hand. Verify the relevering formula matches Damodaran's spreadsheet output to 3 decimals.
2. **`get_unlevered_beta`** — returns correct value for "Semiconductor" (~1.30); returns `None` for "Not An Industry".
3. **`suggest_industry`** — common AV strings map correctly: "SEMICONDUCTORS" → "Semiconductor", "SERVICES-PREPACKAGED SOFTWARE" → "Software (System & Application)". Unmapped strings return `None`.
4. **Tax rate boundary** — at t=0, levered = unlevered × (1 + D/E); at t=1, levered = unlevered (no tax shield).
5. **D/E boundary** — at D/E=0, levered = unlevered (regardless of t).
6. **Industry not in table** — `compute_bottom_up_beta(industry="Not An Industry", ...)` raises `ValueError` with helpful message.

### `tests/test_dcf.py`

One test: `damodaran_industry` field round-trips through `DCFAssumptions` defaults (None) and explicit assignment.

### `tests/test_stock_manager.py`

One test: `damodaran_industry` survives `_manual_overrides` save/load cycle (i.e., assumptions.json correctly stores and restores the field when it's flagged as manual override).

### Skill-level testing

Not automated. The calibrate skill is markdown — its Python dependencies are covered by the unit tests above. Manual verification: run `/calibrate MSFT` end-to-end and confirm the bottom-up beta flow works.

## Out of scope

- **Multi-business companies** — deferred. User can override final beta manually if needed.
- **International beta tables** (Europe, Japan, Emerging) — US-only for now.
- **Total beta** (private company concept) — not relevant to public-equity valuation.
- **Runtime XLS fetching** — annual updates don't justify the dependency. We hardcode and refresh on plugin version bumps each January.
- **Damodaran industry beta updates within a year** — he doesn't update mid-year, so static is fine.
- **Bottom-up beta for the WACC sensitivity** — the existing sensitivity table varies growth × margin, not beta. No change.

## Open questions resolved

| Question | Answer | Reasoning |
|----------|--------|-----------|
| Data strategy | A — hardcode 94-industry table | Matches existing credit-rating table pattern; annual updates only |
| Industry mapping | B — auto-suggest + always confirm | User often knows business better than string match; persistence means one-time cost |
| Multi-business | A — defer | 80% of analyzed companies are dominantly single-industry |
| Persistence | C — store as manual override | Matches existing pattern; locks user judgment but recomputes derived values |
| Cash correction | Cash-corrected (column H) | Damodaran's own published best practice |
| Tax rate basis | Marginal | Per Damodaran's Ginzu spreadsheet |
| D/E basis | Market | Per Damodaran's Ginzu; book misstates for any premium-over-book company |

## Files affected

| File | Change type |
|------|-------------|
| `stock_analyzer/damodaran_betas.py` | New |
| `stock_analyzer/dcf.py` | Add `damodaran_industry` field to `DCFAssumptions` |
| `stock_analyzer/__init__.py` | Export new module if needed |
| `skills/calibrate/SKILL.md` | Rewrite step 2 beta section |
| `tests/test_damodaran_betas.py` | New |
| `tests/test_dcf.py` | One field round-trip test |
| `tests/test_stock_manager.py` | One persistence test |
| `docs/internal/damodaran-audit.md` | Mark #9 as DONE |
