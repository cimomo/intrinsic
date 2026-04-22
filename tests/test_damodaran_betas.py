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


from datetime import date

from stock_analyzer.damodaran_betas import (
    DAMODARAN_BETAS_DATE,
    DAMODARAN_BETAS_STALENESS_MONTHS,
)


class TestDamodaranBetasDate:
    def test_date_is_iso_format(self):
        """DAMODARAN_BETAS_DATE must parse as an ISO date (catches typos like '2026-1-5')."""
        date.fromisoformat(DAMODARAN_BETAS_DATE)

    def test_date_not_stale(self):
        """Fails when the betas table is older than DAMODARAN_BETAS_STALENESS_MONTHS.

        This is an alarm-clock test: it fires on the calendar, not on a code
        change. Damodaran typically refreshes betas.xls in early January; a
        14-month threshold gives a 2-month grace period after the annual
        release. When this fails, refresh from
        pages.stern.nyu.edu/~adamodar/pc/datasets/betas.xls and bump
        DAMODARAN_BETAS_DATE.
        """
        beta_date = date.fromisoformat(DAMODARAN_BETAS_DATE)
        today = date.today()
        months_elapsed = (today.year - beta_date.year) * 12 + (today.month - beta_date.month)
        if today.day < beta_date.day:
            months_elapsed -= 1
        assert months_elapsed < DAMODARAN_BETAS_STALENESS_MONTHS, (
            f"DAMODARAN_BETAS_DATE is {DAMODARAN_BETAS_DATE}, {months_elapsed} months old. "
            f"Threshold is {DAMODARAN_BETAS_STALENESS_MONTHS} months. Refresh from "
            f"pages.stern.nyu.edu/~adamodar/pc/datasets/betas.xls and bump the constant."
        )
