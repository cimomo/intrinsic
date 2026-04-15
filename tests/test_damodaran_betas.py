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
