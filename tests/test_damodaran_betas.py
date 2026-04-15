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
