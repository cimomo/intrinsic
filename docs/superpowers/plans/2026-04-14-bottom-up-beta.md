# Bottom-Up Beta Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Alpha Vantage's noisy regression beta with Damodaran's bottom-up beta (industry unlevered beta + cash correction + relevering), driven by the calibrate skill.

**Architecture:** New self-contained module `stock_analyzer/damodaran_betas.py` holds the 94-industry table plus three pure functions: `suggest_industry`, `get_unlevered_beta`, `compute_bottom_up_beta`. The calibrate skill calls these in step 2 and persists the chosen industry in `assumptions.json` via `_manual_overrides`. The DCF engine itself is unchanged — beta is just a better number flowing through existing CAPM.

**Tech Stack:** Python 3.10+, pytest, existing project structure. No new runtime dependencies.

**Spec:** `docs/superpowers/specs/2026-04-14-bottom-up-beta-design.md`

---

## File Map

| File | Status | Responsibility |
|------|--------|----------------|
| `stock_analyzer/damodaran_betas.py` | NEW | 94-industry table + 3 pure functions (relevering math + lookup) |
| `stock_analyzer/dcf.py` | MODIFY | Add `damodaran_industry: Optional[str]` field to `DCFAssumptions` |
| `skills/calibrate/SKILL.md` | MODIFY | Rewrite step 2 beta section |
| `tests/test_damodaran_betas.py` | NEW | Unit tests for the module |
| `tests/test_dcf.py` | MODIFY | One round-trip test for new field |
| `tests/test_stock_manager.py` | MODIFY | One persistence test |
| `docs/internal/damodaran-audit.md` | MODIFY | Mark #9 as DONE |

---

## Task 1: Fetch industry betas data

**Files:**
- Create: `stock_analyzer/damodaran_betas.py` (data only — functions added in later tasks)

**Source:** `https://pages.stern.nyu.edu/~adamodar/pc/datasets/betas.xls`
The relevant columns are: A=Industry Name, B=Number of firms, F=Unlevered beta, G=Cash/Firm value, H=Unlevered beta corrected for cash, D=D/E ratio.

- [ ] **Step 1: Dispatch a subagent to extract the data**

Use the Agent tool with this exact prompt:

```
Fetch the Damodaran industry betas dataset from this URL:
https://pages.stern.nyu.edu/~adamodar/pc/datasets/betas.xls

The file is an Excel spreadsheet. Use Python with openpyxl to parse it
(install via pip if needed: pip install openpyxl). The "Industry Averages"
worksheet has these columns:
- A: Industry Name
- B: Number of firms
- D: D/E Ratio
- F: Unlevered beta (uncorrected)
- G: Cash/Firm value
- H: Unlevered beta corrected for cash

Return a Python dict literal in this exact format, sorted alphabetically by
industry name. Skip the "Total Market" and "Total Market without financials"
summary rows. Each entry should have all four numeric fields (Number of firms
as int, the rest as float):

DAMODARAN_BETAS = {
    "Advertising": {"n_firms": 56, "de_ratio": 0.5247, "unlevered_beta": 1.04,
                    "cash_firm_value": 0.0563, "unlevered_beta_corrected": 1.10},
    "Aerospace/Defense": {...},
    ...
}

Also report the dataset's last-saved date from the Excel file metadata, and the
total industry count after excluding summary rows.

Output the full dict literal as a code block, plus the date and count.
```

- [ ] **Step 2: Create the module file**

Create `stock_analyzer/damodaran_betas.py` with this header and the data from step 1:

```python
"""
Damodaran's industry betas for bottom-up beta computation.

Source: https://pages.stern.nyu.edu/~adamodar/pc/datasets/betas.xls
Last updated: <DATE FROM SUBAGENT>
Industries: <COUNT FROM SUBAGENT>

Each entry includes:
- n_firms: number of firms in the industry sample
- de_ratio: average market debt-to-equity for the industry
- unlevered_beta: industry-average unlevered beta (uncorrected for cash)
- cash_firm_value: industry-average cash / firm value
- unlevered_beta_corrected: cash-corrected unlevered beta (Damodaran's
  recommended pure-play beta — see his FAQ on the betas dataset page)

The cash-corrected column is computed as: unlevered_beta / (1 - cash_firm_value).
This module uses unlevered_beta_corrected as the input to compute_bottom_up_beta.

Update annually when Damodaran refreshes betas.xls (typically January).
To regenerate: re-run the data extraction described in
docs/superpowers/plans/<this-plan>.md, Task 1.
"""

from typing import Dict, Optional

DAMODARAN_BETAS_DATE = "<DATE FROM SUBAGENT>"

DAMODARAN_BETAS: Dict[str, Dict] = {
    # ... full dict from subagent output
}
```

- [ ] **Step 3: Verify the data loaded**

Run a quick smoke check:

```bash
PYTHONPATH=. python3 -c "from stock_analyzer.damodaran_betas import DAMODARAN_BETAS; print(f'{len(DAMODARAN_BETAS)} industries'); print(list(DAMODARAN_BETAS.keys())[:3])"
```

Expected: prints around 90-95 industries and the first three names alphabetically.

- [ ] **Step 4: Commit**

```bash
git add stock_analyzer/damodaran_betas.py
git commit -m "audit #9: add Damodaran industry betas table

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Add `get_unlevered_beta()` with TDD

**Files:**
- Modify: `stock_analyzer/damodaran_betas.py`
- Create: `tests/test_damodaran_betas.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_damodaran_betas.py`:

```python
"""Tests for stock_analyzer.damodaran_betas"""

import pytest
from stock_analyzer.damodaran_betas import (
    DAMODARAN_BETAS,
    get_unlevered_beta,
)


class TestGetUnleveredBeta:
    def test_known_industry(self):
        """Returns cash-corrected unlevered beta for known industry."""
        beta = get_unlevered_beta("Semiconductor")
        # Match the value stored in DAMODARAN_BETAS for this industry
        assert beta == DAMODARAN_BETAS["Semiconductor"]["unlevered_beta_corrected"]

    def test_unknown_industry_returns_none(self):
        """Returns None for industry not in table."""
        assert get_unlevered_beta("Not An Industry") is None

    def test_empty_string_returns_none(self):
        assert get_unlevered_beta("") is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_damodaran_betas.py::TestGetUnleveredBeta -v
```

Expected: ImportError on `get_unlevered_beta` (function not defined yet).

- [ ] **Step 3: Implement minimally**

Append to `stock_analyzer/damodaran_betas.py`:

```python
def get_unlevered_beta(industry: str) -> Optional[float]:
    """Return cash-corrected unlevered beta for an industry, or None if not found."""
    entry = DAMODARAN_BETAS.get(industry)
    return entry["unlevered_beta_corrected"] if entry else None
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/test_damodaran_betas.py::TestGetUnleveredBeta -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add stock_analyzer/damodaran_betas.py tests/test_damodaran_betas.py
git commit -m "audit #9: add get_unlevered_beta lookup

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Add `compute_bottom_up_beta()` with TDD

**Files:**
- Modify: `stock_analyzer/damodaran_betas.py`
- Modify: `tests/test_damodaran_betas.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_damodaran_betas.py`:

```python
from stock_analyzer.damodaran_betas import compute_bottom_up_beta


class TestComputeBottomUpBeta:
    def test_known_industry_relevers_correctly(self):
        """Levered beta = unlevered × (1 + (1-t) × D/E)."""
        result = compute_bottom_up_beta(
            industry="Semiconductor",
            market_de=0.15,
            marginal_tax_rate=0.21,
        )
        unlevered = DAMODARAN_BETAS["Semiconductor"]["unlevered_beta_corrected"]
        expected = unlevered * (1 + (1 - 0.21) * 0.15)
        assert result["levered_beta"] == pytest.approx(expected, rel=1e-9)
        assert result["unlevered_beta"] == pytest.approx(unlevered, rel=1e-9)
        assert result["industry"] == "Semiconductor"
        assert result["market_de"] == pytest.approx(0.15, rel=1e-9)
        assert result["tax_rate"] == pytest.approx(0.21, rel=1e-9)
        assert result["n_firms"] == DAMODARAN_BETAS["Semiconductor"]["n_firms"]

    def test_zero_de_means_levered_equals_unlevered(self):
        """At D/E = 0, no leverage adjustment."""
        result = compute_bottom_up_beta(
            industry="Semiconductor",
            market_de=0.0,
            marginal_tax_rate=0.21,
        )
        assert result["levered_beta"] == pytest.approx(result["unlevered_beta"], rel=1e-9)

    def test_full_tax_means_no_tax_shield(self):
        """At t = 1, the (1-t) term zeroes out — levered = unlevered regardless of D/E."""
        result = compute_bottom_up_beta(
            industry="Semiconductor",
            market_de=0.5,
            marginal_tax_rate=1.0,
        )
        assert result["levered_beta"] == pytest.approx(result["unlevered_beta"], rel=1e-9)

    def test_zero_tax_full_leverage_passthrough(self):
        """At t = 0, levered = unlevered × (1 + D/E)."""
        result = compute_bottom_up_beta(
            industry="Semiconductor",
            market_de=0.5,
            marginal_tax_rate=0.0,
        )
        unlevered = DAMODARAN_BETAS["Semiconductor"]["unlevered_beta_corrected"]
        assert result["levered_beta"] == pytest.approx(unlevered * 1.5, rel=1e-9)

    def test_unknown_industry_raises(self):
        """Unknown industry raises ValueError with helpful message."""
        with pytest.raises(ValueError, match="Not An Industry"):
            compute_bottom_up_beta(
                industry="Not An Industry",
                market_de=0.15,
                marginal_tax_rate=0.21,
            )
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/test_damodaran_betas.py::TestComputeBottomUpBeta -v
```

Expected: ImportError on `compute_bottom_up_beta`.

- [ ] **Step 3: Implement the function**

Append to `stock_analyzer/damodaran_betas.py`:

```python
def compute_bottom_up_beta(
    industry: str,
    market_de: float,
    marginal_tax_rate: float,
) -> Dict:
    """
    Compute bottom-up levered beta using Damodaran's relevering formula.

    Levered Beta = Unlevered Beta × (1 + (1 - t) × D/E)

    Uses the cash-corrected unlevered beta from the industry table
    (Damodaran's recommended pure-play beta).

    Args:
        industry: Damodaran industry name (must exist in DAMODARAN_BETAS)
        market_de: Company's current market debt-to-equity ratio
        marginal_tax_rate: Marginal tax rate (typically 0.21 for US)

    Returns:
        Dict with: levered_beta, unlevered_beta, industry, market_de,
        tax_rate, n_firms

    Raises:
        ValueError: If industry not in DAMODARAN_BETAS
    """
    entry = DAMODARAN_BETAS.get(industry)
    if entry is None:
        raise ValueError(
            f"Industry '{industry}' not found in DAMODARAN_BETAS table. "
            f"Check available industries via list(DAMODARAN_BETAS.keys())."
        )
    unlevered = entry["unlevered_beta_corrected"]
    levered = unlevered * (1 + (1 - marginal_tax_rate) * market_de)
    return {
        "levered_beta": levered,
        "unlevered_beta": unlevered,
        "industry": industry,
        "market_de": market_de,
        "tax_rate": marginal_tax_rate,
        "n_firms": entry["n_firms"],
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/test_damodaran_betas.py::TestComputeBottomUpBeta -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add stock_analyzer/damodaran_betas.py tests/test_damodaran_betas.py
git commit -m "audit #9: add compute_bottom_up_beta with relevering formula

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Add AV→Damodaran industry hint mapping with TDD

**Files:**
- Modify: `stock_analyzer/damodaran_betas.py`
- Modify: `tests/test_damodaran_betas.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_damodaran_betas.py`:

```python
from stock_analyzer.damodaran_betas import suggest_industry, AV_TO_DAMODARAN_HINT


class TestSuggestIndustry:
    def test_known_av_industry_maps(self):
        """Common AV industries map to a Damodaran industry."""
        assert suggest_industry("SEMICONDUCTORS") == "Semiconductor"
        assert suggest_industry("SERVICES-PREPACKAGED SOFTWARE") == "Software (System & Application)"

    def test_case_insensitive(self):
        """Mapping is case-insensitive (AV strings vary)."""
        assert suggest_industry("semiconductors") == "Semiconductor"
        assert suggest_industry("Semiconductors") == "Semiconductor"

    def test_unknown_av_industry_returns_none(self):
        """Unmapped AV strings return None."""
        assert suggest_industry("MADE UP INDUSTRY ZZZ") is None

    def test_empty_string_returns_none(self):
        assert suggest_industry("") is None

    def test_none_returns_none(self):
        assert suggest_industry(None) is None

    def test_all_hint_targets_exist_in_betas_table(self):
        """Every value in AV_TO_DAMODARAN_HINT must exist as a key in DAMODARAN_BETAS."""
        missing = [
            damodaran for damodaran in AV_TO_DAMODARAN_HINT.values()
            if damodaran not in DAMODARAN_BETAS
        ]
        assert missing == [], f"Hints map to non-existent industries: {missing}"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/test_damodaran_betas.py::TestSuggestIndustry -v
```

Expected: ImportError on `suggest_industry` and `AV_TO_DAMODARAN_HINT`.

- [ ] **Step 3: Implement**

Append to `stock_analyzer/damodaran_betas.py`. Use this starter mapping (the implementation agent may extend it after reviewing common Alpha Vantage industry strings):

```python
# Mapping from Alpha Vantage industry strings (Industry field in OVERVIEW)
# to Damodaran industry names. AV uses SEC standard industrial classification
# in uppercase; Damodaran uses his own ~94-category taxonomy. Mismatches are
# resolved by matching the closest Damodaran category (manual mapping).
#
# Keys are normalized to UPPERCASE — suggest_industry() uppercases its input.
AV_TO_DAMODARAN_HINT: Dict[str, str] = {
    # Technology
    "SEMICONDUCTORS": "Semiconductor",
    "SEMICONDUCTORS & RELATED DEVICES": "Semiconductor",
    "SERVICES-PREPACKAGED SOFTWARE": "Software (System & Application)",
    "SERVICES-COMPUTER PROGRAMMING, DATA PROCESSING, ETC.": "Software (System & Application)",
    "COMPUTER & OFFICE EQUIPMENT": "Computers/Peripherals",
    "ELECTRONIC COMPUTERS": "Computers/Peripherals",
    "COMMUNICATIONS EQUIPMENT, NEC": "Telecom. Equipment",
    "RADIO & TV BROADCASTING & COMMUNICATIONS EQUIPMENT": "Telecom. Equipment",
    "SERVICES-COMPUTER INTEGRATED SYSTEMS DESIGN": "Information Services",
    "SERVICES-COMPUTER PROCESSING & DATA PREPARATION": "Information Services",
    # Financials
    "STATE COMMERCIAL BANKS": "Bank (Money Center)",
    "NATIONAL COMMERCIAL BANKS": "Bank (Money Center)",
    "SAVINGS INSTITUTIONS, FEDERALLY CHARTERED": "Banks (Regional)",
    "SECURITY BROKERS, DEALERS & FLOTATION COMPANIES": "Investments & Asset Management",
    "FIRE, MARINE & CASUALTY INSURANCE": "Insurance (Prop/Cas.)",
    "LIFE INSURANCE": "Insurance (Life)",
    # Healthcare
    "PHARMACEUTICAL PREPARATIONS": "Drugs (Pharmaceutical)",
    "BIOLOGICAL PRODUCTS, (NO DIAGNOSTIC SUBSTANCES)": "Biotechnology",
    "ELECTROMEDICAL & ELECTROTHERAPEUTIC APPARATUS": "Healthcare Products",
    "SERVICES-HEALTH SERVICES": "Healthcare Support Services",
    # Energy
    "CRUDE PETROLEUM & NATURAL GAS": "Oil/Gas (Production and Exploration)",
    "PETROLEUM REFINING": "Oil/Gas (Integrated)",
    "NATURAL GAS DISTRIBUTION": "Utility (Natural Gas)",
    # Consumer
    "RETAIL-VARIETY STORES": "Retail (General)",
    "RETAIL-DEPARTMENT STORES": "Retail (General)",
    "RETAIL-EATING PLACES": "Restaurant/Dining",
    "BEVERAGES": "Beverage (Soft)",
    # Industrial
    "MOTOR VEHICLES & PASSENGER CAR BODIES": "Auto & Truck",
    "AIRCRAFT": "Aerospace/Defense",
    "GUIDED MISSILES & SPACE VEHICLES & PARTS": "Aerospace/Defense",
    # Real Estate
    "REAL ESTATE INVESTMENT TRUSTS": "R.E.I.T.",
    # Media
    "SERVICES-MOTION PICTURE & VIDEO TAPE PRODUCTION": "Entertainment",
    "TELEVISION BROADCASTING STATIONS": "Broadcasting",
    "CABLE & OTHER PAY TELEVISION SERVICES": "Cable TV",
    "SERVICES-ADVERTISING": "Advertising",
}


def suggest_industry(av_industry: Optional[str]) -> Optional[str]:
    """
    Suggest a Damodaran industry name from an Alpha Vantage industry string.

    Returns the Damodaran name if the AV string is in our mapping, or None
    if no good match exists. The calibrate skill should always confirm with
    the user before using the suggestion.
    """
    if not av_industry:
        return None
    return AV_TO_DAMODARAN_HINT.get(av_industry.strip().upper())
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/test_damodaran_betas.py::TestSuggestIndustry -v
```

Expected: 6 passed. If `test_all_hint_targets_exist_in_betas_table` fails, fix the offending hint values to match actual Damodaran industry names from `DAMODARAN_BETAS`.

- [ ] **Step 5: Commit**

```bash
git add stock_analyzer/damodaran_betas.py tests/test_damodaran_betas.py
git commit -m "audit #9: add AV-to-Damodaran industry hint mapping

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Add sector grouping for the picker UX

**Files:**
- Modify: `stock_analyzer/damodaran_betas.py`
- Modify: `tests/test_damodaran_betas.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_damodaran_betas.py`:

```python
from stock_analyzer.damodaran_betas import DAMODARAN_SECTORS


class TestDamodaranSectors:
    def test_sectors_cover_all_industries(self):
        """Every industry in DAMODARAN_BETAS appears in exactly one sector."""
        all_sector_industries = []
        for sector, industries in DAMODARAN_SECTORS.items():
            all_sector_industries.extend(industries)

        # No duplicates across sectors
        assert len(all_sector_industries) == len(set(all_sector_industries)), \
            "Some industry appears in multiple sectors"

        # All beta-table industries are covered
        missing = set(DAMODARAN_BETAS.keys()) - set(all_sector_industries)
        assert missing == set(), f"Industries missing from sector grouping: {missing}"

        # No phantom industries (sector entries that aren't in the betas table)
        phantom = set(all_sector_industries) - set(DAMODARAN_BETAS.keys())
        assert phantom == set(), f"Sector entries not in DAMODARAN_BETAS: {phantom}"

    def test_reasonable_sector_count(self):
        """Should have between 8 and 18 sector buckets — enough granularity, not overwhelming."""
        assert 8 <= len(DAMODARAN_SECTORS) <= 18
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_damodaran_betas.py::TestDamodaranSectors -v
```

Expected: ImportError on `DAMODARAN_SECTORS`.

- [ ] **Step 3: Implement**

The implementation agent must read the actual industry list from `DAMODARAN_BETAS.keys()` (94 names) and group them into ~10-15 sectors. Use this template structure (the agent will fill in industries from the actual table):

Append to `stock_analyzer/damodaran_betas.py`:

```python
# Our own sector grouping for the calibrate skill's industry picker.
# Damodaran's table doesn't have sector groupings — we define them.
# Every industry in DAMODARAN_BETAS must appear in exactly one sector.
#
# Use the full industry list from DAMODARAN_BETAS to populate this dict.
# Suggested sectors (adjust based on actual industry names):
#   Technology, Healthcare, Financials, Energy, Materials, Industrials,
#   Consumer Discretionary, Consumer Staples, Communication Services,
#   Utilities, Real Estate, Transportation
DAMODARAN_SECTORS: Dict[str, list] = {
    "Technology": [
        "Computer Services",
        "Computers/Peripherals",
        "Information Services",
        "Semiconductor",
        "Semiconductor Equip",
        "Software (Entertainment)",
        "Software (Internet)",
        "Software (System & Application)",
        # ...
    ],
    "Healthcare": [
        "Biotechnology",
        "Drugs (Biotechnology)",
        "Drugs (Pharmaceutical)",
        "Healthcare Information and Technology",
        "Healthcare Products",
        "Healthcare Support Services",
        # ...
    ],
    # ... add remaining sectors covering all industries from DAMODARAN_BETAS
}
```

The implementation agent should pull the exact industry names from `DAMODARAN_BETAS.keys()` (printed via `python3 -c "from stock_analyzer.damodaran_betas import DAMODARAN_BETAS; print('\n'.join(sorted(DAMODARAN_BETAS.keys())))"`) and place each one in the most appropriate sector. The two tests above are the contract — every industry must land in exactly one sector.

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/test_damodaran_betas.py::TestDamodaranSectors -v
```

Expected: 2 passed. If "missing" or "phantom" assertions fail, list shows the discrepancies — add or remove from `DAMODARAN_SECTORS` until both sets are empty.

- [ ] **Step 5: Run the full test module**

```bash
python3 -m pytest tests/test_damodaran_betas.py -v
```

Expected: all tests pass (16 tests total: 3 + 5 + 6 + 2).

- [ ] **Step 6: Commit**

```bash
git add stock_analyzer/damodaran_betas.py tests/test_damodaran_betas.py
git commit -m "audit #9: add DAMODARAN_SECTORS grouping for picker UX

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Add `damodaran_industry` field to `DCFAssumptions` with TDD

**Files:**
- Modify: `stock_analyzer/dcf.py:13-52` (the `DCFAssumptions` dataclass)
- Modify: `tests/test_dcf.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_dcf.py` (in the `TestDCFAssumptions` class near the top of the file):

```python
class TestDCFAssumptionsDamodaranIndustry:
    def test_default_is_none(self):
        """damodaran_industry defaults to None for backward compatibility."""
        a = DCFAssumptions()
        assert a.damodaran_industry is None

    def test_explicit_value(self):
        """damodaran_industry accepts a string value."""
        a = DCFAssumptions(damodaran_industry="Semiconductor")
        assert a.damodaran_industry == "Semiconductor"

    def test_field_does_not_affect_dcf_math(self):
        """damodaran_industry is metadata — must not change WACC or fair value."""
        from stock_analyzer.dcf import DCFModel
        dcf_inputs = {
            'revenue': 400_000_000_000,
            'operating_income': 120_000_000_000,
            'total_debt': 100_000_000_000,
            'cash': 60_000_000_000,
            'short_term_investments': 0,
            'long_term_investments': 0,
            'equity': 200_000_000_000,
            'market_cap': 2_500_000_000_000,
            'beta': 1.2,
        }
        a_without = DCFAssumptions()
        a_with = DCFAssumptions(damodaran_industry="Semiconductor")
        m1 = DCFModel(a_without)
        m2 = DCFModel(a_with)
        r1 = m1.calculate_fair_value(dcf_inputs, 10e9, 250.0, verbose=True)
        r2 = m2.calculate_fair_value(dcf_inputs, 10e9, 250.0, verbose=True)
        assert r1["fair_value"] == pytest.approx(r2["fair_value"], rel=1e-9)
        assert r1["wacc"] == pytest.approx(r2["wacc"], rel=1e-9)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/test_dcf.py::TestDCFAssumptionsDamodaranIndustry -v
```

Expected: AttributeError or TypeError on the `damodaran_industry` argument.

- [ ] **Step 3: Add the field**

Edit `stock_analyzer/dcf.py`. Find the existing `DCFAssumptions` dataclass (around lines 13-52). Add this field anywhere in the dataclass — placing it after `cost_of_capital` (around line 47) keeps related metadata together. Insert this new field:

```python
    # Bottom-up beta tracking (audit #9). Pure metadata used by calibrate
    # to recall the user's prior industry choice across runs. The DCF model
    # itself does not read this field — beta lives in the existing `beta` field.
    damodaran_industry: Optional[str] = None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/test_dcf.py::TestDCFAssumptionsDamodaranIndustry -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add stock_analyzer/dcf.py tests/test_dcf.py
git commit -m "audit #9: add damodaran_industry field to DCFAssumptions

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Verify `damodaran_industry` persistence in `stock_manager`

**Files:**
- Modify: `tests/test_stock_manager.py`

The existing assumption persistence code uses `dataclasses.asdict()` and round-trips fields automatically. This task confirms that — no production code change is expected.

- [ ] **Step 1: Find an existing assumption persistence test in `tests/test_stock_manager.py`**

Open the file and locate the test class that tests `save_assumptions` / `load_assumptions` (likely named `TestSaveLoadAssumptions` or similar). Verify the test pattern.

```bash
grep -n "save_assumptions\|load_assumptions\|_manual_overrides" tests/test_stock_manager.py
```

- [ ] **Step 2: Write the failing test**

Append to `tests/test_stock_manager.py` (place inside the existing assumptions test class, or in a new `TestDamodaranIndustryPersistence` class — match whichever style is already used in the file):

```python
class TestDamodaranIndustryPersistence:
    def test_damodaran_industry_round_trips(self, tmp_path, monkeypatch):
        """damodaran_industry survives save/load via assumptions.json."""
        from stock_analyzer.stock_manager import StockManager
        from stock_analyzer.dcf import DCFAssumptions

        # Use tmp_path as the data root
        monkeypatch.chdir(tmp_path)
        manager = StockManager()

        a = DCFAssumptions(damodaran_industry="Semiconductor")
        manager.save_assumptions("TEST", a)

        loaded, was_loaded = manager.get_or_create_assumptions("TEST")
        assert was_loaded is True
        assert loaded.damodaran_industry == "Semiconductor"

    def test_damodaran_industry_in_manual_overrides(self, tmp_path, monkeypatch):
        """damodaran_industry can be marked as a manual override and survive."""
        from stock_analyzer.stock_manager import StockManager
        from stock_analyzer.dcf import DCFAssumptions

        monkeypatch.chdir(tmp_path)
        manager = StockManager()

        a = DCFAssumptions(damodaran_industry="Semiconductor")
        manager.save_assumptions("TEST", a, manual_overrides=["damodaran_industry"])

        overrides = manager.load_manual_overrides("TEST")
        assert "damodaran_industry" in overrides

        loaded, _ = manager.get_or_create_assumptions("TEST")
        assert loaded.damodaran_industry == "Semiconductor"
```

If the existing `save_assumptions` signature differs (e.g., `manual_overrides` is passed differently), match the actual signature — read `stock_analyzer/stock_manager.py` first to confirm.

- [ ] **Step 3: Run tests to verify they pass**

```bash
python3 -m pytest tests/test_stock_manager.py::TestDamodaranIndustryPersistence -v
```

Expected: both pass without code changes (the dataclass-based persistence handles new fields automatically).

If a test fails, the production code may need a fix — for example, a hardcoded list of fields to persist. Investigate `stock_manager.save_assumptions` and `get_or_create_assumptions` and adjust as needed.

- [ ] **Step 4: Run the full suite to confirm no regressions**

```bash
python3 -m pytest tests/ -q
```

Expected: all tests pass (~325+ tests total).

- [ ] **Step 5: Commit**

```bash
git add tests/test_stock_manager.py
git commit -m "audit #9: test damodaran_industry persistence

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Update calibrate skill — beta section

**Files:**
- Modify: `skills/calibrate/SKILL.md` — the "Beta:" bullet inside step 2 (currently around line 90, "Use beta from company overview data...")

- [ ] **Step 1: Locate the existing beta block**

```bash
grep -n "^- \*\*Beta:\*\*" skills/calibrate/SKILL.md
```

The current text is one line:
```
- **Beta:** Use beta from company overview data. Display: "Beta: X.XX (from overview)"
```

- [ ] **Step 2: Replace the beta bullet with the bottom-up flow**

Use the Edit tool to replace that single bullet with the new multi-paragraph block. The exact replacement:

**Old (one bullet):**
```
- **Beta:** Use beta from company overview data. Display: "Beta: X.XX (from overview)"
```

**New (multi-paragraph block):**
```
- **Beta:** Use Damodaran's bottom-up beta from the industry table.
  1. Read the regression beta from `dcf_inputs['beta']` (Alpha Vantage 5y) and the industry from `cached["data"]["overview"]["Industry"]`.
  2. Compute market D/E from `total_debt / market_cap` (both already in `dcf_inputs`).
  3. **First-time flow** (no `damodaran_industry` in `_manual_overrides`):
     - Call `damodaran_betas.suggest_industry(av_industry)` to get a suggested Damodaran industry. If `None`, prompt the user to pick from the full list.
     - Call `damodaran_betas.compute_bottom_up_beta(industry, market_de, marginal_tax_rate=0.21)` for the suggested industry. Display:
       ```
       Beta:
         Regression beta (Alpha Vantage 5y): X.XX
         
         Industry: <AV_INDUSTRY> (Alpha Vantage)
         → Suggested Damodaran industry: <DAMODARAN_INDUSTRY>
         
         Bottom-up beta: Y.YY
           = unlevered_β U.UU (<DAMODARAN_INDUSTRY>, cash-corrected, N firms)
           × (1 + (1 - 0.21) × D/E D.DD)
           
         Recommendation: Y.YY (bottom-up)
           Why: regression betas have ±0.25 standard error; bottom-up
           averages across N industry peers and removes cash/leverage noise.
       ```
     - Use `AskUserQuestion` with these options:
       - `[1] Use bottom-up Y.YY (recommended)` → set `assumptions.beta = bottom_up_levered`, `assumptions.damodaran_industry = industry`. Add `damodaran_industry` to `_manual_overrides` (NOT `beta` — leaving `beta` out lets calibrate recompute it next run from current D/E).
       - `[2] Use regression X.XX (Alpha Vantage)` → set `assumptions.beta = av_beta`. Add `beta` to `_manual_overrides`. Do not store `damodaran_industry`.
       - `[3] Pick a different Damodaran industry` → drop into the sector-then-industry picker (see below).
       - `[4] Custom beta value` → user enters number. Set `assumptions.beta = entered_value`. Add `beta` to `_manual_overrides`. Do not store `damodaran_industry`.
  4. **Sector-then-industry picker (option 3):** Use two `AskUserQuestion` calls. First, pick sector from `damodaran_betas.DAMODARAN_SECTORS.keys()`. Second, pick industry from `DAMODARAN_SECTORS[chosen_sector]`. Then recompute `compute_bottom_up_beta` with the new industry and apply the same persistence as option 1.
  5. **Recall flow** (`damodaran_industry` is in `_manual_overrides`):
     - Recompute the bottom-up beta with the stored industry and current D/E. Display:
       ```
       Industry: <STORED_INDUSTRY> [manual override — set previously]
       Bottom-up beta: Y.YY (recomputed with current D/E D.DD)
       
       Use this? [Enter to accept, or change industry]
       ```
     - If the user wants to change, drop into the sector-then-industry picker as in option 3.
  6. **Edge cases:**
     - If `cached["data"]["overview"]["Industry"]` is missing or empty: skip the suggestion, go straight to the picker.
     - If `suggest_industry` returns `None`: warn "no auto-match for AV industry '<X>' — please pick from list" and go to picker.
     - If the stored `damodaran_industry` no longer exists in `damodaran_betas.DAMODARAN_BETAS` (e.g., Damodaran renamed it): warn "Stored industry '<X>' not found in current table — please re-pick" and drop to picker.
     - If `damodaran_betas.DAMODARAN_BETAS_DATE` is older than 14 months: show a banner "Damodaran industry betas are from <DATE>, may be stale — consider checking pages.stern.nyu.edu/~adamodar/pc/datasets/betas.xls".
  7. **Manual override on `beta` directly:** If `beta` is in `_manual_overrides` (regardless of whether `damodaran_industry` is also there), keep the stored beta value and skip the bottom-up flow. Display: "Beta: keeping manual override at X.XX". This handles options 2 and 4 above on subsequent runs.
```

(Use the Edit tool with the exact old/new strings.)

- [ ] **Step 3: Update the assumption category section to reflect the change**

Earlier in the file (around line 53-56), the "Mechanical (auto-derived from data):" block lists "Beta (from company overview)". Update it to reflect the new approach. Use Edit:

**Old:**
```
- Beta (from company overview)
```

**New:**
```
- Beta (bottom-up: Damodaran industry unlevered beta + company D/E + marginal tax rate; falls back to AV regression on user choice)
```

- [ ] **Step 4: Verify the skill file is syntactically clean**

```bash
grep -c "^### 2\." skills/calibrate/SKILL.md
```

Expected: prints `1` (only one Step 2 heading — no accidental duplicates from the edit).

- [ ] **Step 5: Commit**

```bash
git add skills/calibrate/SKILL.md
git commit -m "audit #9: rewrite calibrate beta section for bottom-up flow

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Mark audit item #9 as DONE

**Files:**
- Modify: `docs/internal/damodaran-audit.md`

`docs/internal/` is gitignored, so this change stays local — that's expected.

- [ ] **Step 1: Edit the audit doc**

Use the Edit tool:

**Old:**
```
#### 9. Bottom-up beta

**Priority:** MEDIUM-HIGH
```

**New:**
```
#### 9. Bottom-up beta — DONE

**Priority:** MEDIUM-HIGH
```

- [ ] **Step 2: No commit needed**

The file is gitignored. Skip the commit.

---

## Task 10: Final verification and push

- [ ] **Step 1: Run the full test suite**

```bash
python3 -m pytest tests/ -v 2>&1 | tail -30
```

Expected: all tests pass. Note the final count (should be ~330+ tests, up from 316).

- [ ] **Step 2: Push all commits**

```bash
git push 2>&1
```

Expected: pushes Tasks 1-8 commits to origin/main.

- [ ] **Step 3: Display summary**

Print:
- Number of commits added in this plan
- Final test count
- Files changed (from `git diff --stat HEAD~N..HEAD` where N = number of commits)

---

## Acceptance criteria

After all tasks complete:

- [ ] `stock_analyzer/damodaran_betas.py` exists with ~94 industries
- [ ] `compute_bottom_up_beta()` matches Damodaran's relevering formula
- [ ] `tests/test_damodaran_betas.py` covers all 5 test classes (~16 tests)
- [ ] `DCFAssumptions.damodaran_industry` field exists, defaults to None, doesn't affect DCF math
- [ ] `assumptions.json` round-trips the field
- [ ] `skills/calibrate/SKILL.md` step 2 implements the new beta flow with all 4 user options + recall + edge cases
- [ ] Full test suite passes (~330+ tests)
- [ ] All work committed and pushed
- [ ] `docs/internal/damodaran-audit.md` shows #9 as DONE
