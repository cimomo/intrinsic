"""Tests for stock_analyzer.dcf"""

import pytest
from stock_analyzer.dcf import DCFModel, DCFAssumptions


# --- Fixtures ---

@pytest.fixture
def default_assumptions():
    return DCFAssumptions()


@pytest.fixture
def custom_assumptions():
    return DCFAssumptions(
        revenue_growth_rate=0.10,
        terminal_growth_rate=0.025,
        risk_free_rate=0.045,
        market_risk_premium=0.05,
        tax_rate=0.21,
        cost_of_debt=0.05,
        projection_years=10,
    )


@pytest.fixture
def sample_financial_data():
    return {
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


# --- DCFAssumptions ---

class TestDCFAssumptions:
    def test_defaults(self):
        a = DCFAssumptions()
        assert a.revenue_growth_rate == 0.10
        assert a.tax_rate == 0.21
        assert a.projection_years == 10

    def test_terminal_growth_defaults_to_risk_free(self):
        a = DCFAssumptions(risk_free_rate=0.04)
        assert a.terminal_growth_rate == 0.04

    def test_terminal_growth_explicit_override(self):
        a = DCFAssumptions(risk_free_rate=0.04, terminal_growth_rate=0.025)
        assert a.terminal_growth_rate == 0.025

    def test_target_operating_margin_default_none(self):
        a = DCFAssumptions()
        assert a.target_operating_margin is None

    def test_effective_tax_rate_default_none(self):
        a = DCFAssumptions()
        assert a.effective_tax_rate is None


# --- WACC ---

class TestWACC:
    def test_all_equity(self):
        """Company with no debt: WACC = cost of equity"""
        model = DCFModel(DCFAssumptions(risk_free_rate=0.04, market_risk_premium=0.05))
        wacc = model.calculate_wacc(beta=1.0, debt_to_equity=0, market_cap=1000, total_debt=0)
        expected_cost_of_equity = 0.04 + 1.0 * 0.05  # 9%
        assert wacc == pytest.approx(expected_cost_of_equity)

    def test_with_debt(self):
        """WACC should be lower than cost of equity when debt is present (tax shield)"""
        model = DCFModel(DCFAssumptions(
            risk_free_rate=0.04, market_risk_premium=0.05,
            cost_of_debt=0.05, tax_rate=0.21
        ))
        cost_of_equity = 0.04 + 1.0 * 0.05  # 9%
        wacc = model.calculate_wacc(beta=1.0, debt_to_equity=0.5, market_cap=1000, total_debt=500)
        assert wacc < cost_of_equity

    def test_high_beta_increases_wacc(self):
        model = DCFModel()
        wacc_low = model.calculate_wacc(beta=0.8, debt_to_equity=0, market_cap=1000, total_debt=0)
        wacc_high = model.calculate_wacc(beta=1.5, debt_to_equity=0, market_cap=1000, total_debt=0)
        assert wacc_high > wacc_low

    def test_zero_total_value(self):
        """Edge case: zero market cap and zero debt"""
        model = DCFModel()
        wacc = model.calculate_wacc(beta=1.0, debt_to_equity=0, market_cap=0, total_debt=0)
        # equity_weight=1, debt_weight=0
        expected = 0.045 + 1.0 * 0.05
        assert wacc == pytest.approx(expected)


# --- FCF Projections ---

class TestProjectFCF:
    def test_returns_correct_length(self, custom_assumptions):
        model = DCFModel(custom_assumptions)
        fcfs, margins, final_rev = model.project_free_cash_flows(
            base_revenue=100e9, operating_margin=0.30,
            sales_to_capital=2.0, years=10
        )
        assert len(fcfs) == 10
        assert len(margins) == 10

    def test_fcf_positive_for_profitable_company(self, custom_assumptions):
        model = DCFModel(custom_assumptions)
        fcfs, _, _ = model.project_free_cash_flows(
            base_revenue=100e9, operating_margin=0.30,
            sales_to_capital=2.0, years=10
        )
        assert all(fcf > 0 for fcf in fcfs)

    def test_growth_tapering(self):
        """Years 6-10 growth should taper toward terminal rate"""
        assumptions = DCFAssumptions(
            revenue_growth_rate=0.20, terminal_growth_rate=0.03, projection_years=10
        )
        model = DCFModel(assumptions)
        fcfs, _, _ = model.project_free_cash_flows(
            base_revenue=100e9, operating_margin=0.25,
            sales_to_capital=2.0, years=10
        )
        # FCF growth rate should slow in later years
        growth_5_6 = fcfs[5] / fcfs[4] - 1
        growth_9_10 = fcfs[9] / fcfs[8] - 1
        assert growth_9_10 < growth_5_6

    def test_no_margin_convergence_by_default(self, custom_assumptions):
        model = DCFModel(custom_assumptions)
        _, margins, _ = model.project_free_cash_flows(
            base_revenue=100e9, operating_margin=0.25,
            sales_to_capital=2.0, years=10
        )
        assert all(m == 0.25 for m in margins)

    def test_margin_convergence(self):
        assumptions = DCFAssumptions(target_operating_margin=0.40, projection_years=10)
        model = DCFModel(assumptions)
        _, margins, _ = model.project_free_cash_flows(
            base_revenue=100e9, operating_margin=0.20,
            sales_to_capital=2.0, years=10
        )
        # Year 1 starts moving toward target
        assert margins[0] > 0.20
        # Year 10 reaches target
        assert margins[-1] == pytest.approx(0.40)
        # Monotonically increasing
        for i in range(1, len(margins)):
            assert margins[i] > margins[i - 1]

    def test_margin_convergence_downward(self):
        """Margin should converge down if target < current"""
        assumptions = DCFAssumptions(target_operating_margin=0.15, projection_years=10)
        model = DCFModel(assumptions)
        _, margins, _ = model.project_free_cash_flows(
            base_revenue=100e9, operating_margin=0.30,
            sales_to_capital=2.0, years=10
        )
        assert margins[-1] == pytest.approx(0.15)
        assert margins[0] < 0.30

    def test_zero_sales_to_capital(self):
        """Zero sales-to-capital should mean zero reinvestment"""
        model = DCFModel(DCFAssumptions(projection_years=3))
        fcfs, _, _ = model.project_free_cash_flows(
            base_revenue=100e9, operating_margin=0.20,
            sales_to_capital=0, years=3
        )
        # FCF = NOPAT (no reinvestment subtracted)
        assert all(fcf > 0 for fcf in fcfs)

    def test_returns_final_revenue(self):
        """Final revenue reflects cumulative growth"""
        assumptions = DCFAssumptions(revenue_growth_rate=0.10, projection_years=5)
        model = DCFModel(assumptions)
        _, _, final_rev = model.project_free_cash_flows(
            base_revenue=100e9, operating_margin=0.30,
            sales_to_capital=2.0, years=5
        )
        # 100B * 1.10^5 = 161.05B
        assert final_rev == pytest.approx(100e9 * 1.10**5)

    def test_tax_rate_transition(self):
        """Effective tax rate transitions to marginal over projection period"""
        assumptions = DCFAssumptions(
            revenue_growth_rate=0.10, tax_rate=0.21,
            effective_tax_rate=0.05, projection_years=10,
        )
        model = DCFModel(assumptions)
        fcfs_transition, _, _ = model.project_free_cash_flows(
            base_revenue=100e9, operating_margin=0.30,
            sales_to_capital=2.0, years=10
        )
        # Without transition (flat 21%)
        assumptions_flat = DCFAssumptions(
            revenue_growth_rate=0.10, tax_rate=0.21,
            projection_years=10,
        )
        model_flat = DCFModel(assumptions_flat)
        fcfs_flat, _, _ = model_flat.project_free_cash_flows(
            base_revenue=100e9, operating_margin=0.30,
            sales_to_capital=2.0, years=10
        )
        # Early years: lower tax → higher NOPAT → higher FCF
        assert fcfs_transition[0] > fcfs_flat[0]
        # Year 10: tax rate converged to marginal, FCFs should be equal
        assert fcfs_transition[-1] == pytest.approx(fcfs_flat[-1])

    def test_no_transition_when_effective_is_none(self):
        """When effective_tax_rate is None, all years use marginal rate"""
        assumptions = DCFAssumptions(tax_rate=0.21, projection_years=5)
        model = DCFModel(assumptions)
        # All years should use 21%
        for year in range(1, 6):
            assert model._get_tax_rate_for_year(year, 5) == 0.21

    def test_tax_transition_year_by_year(self):
        """Verify linear interpolation of tax rate"""
        assumptions = DCFAssumptions(tax_rate=0.21, effective_tax_rate=0.01)
        model = DCFModel(assumptions)
        # Year 1/10 = 10% progress: 0.01 + 0.20 * 0.1 = 0.03
        assert model._get_tax_rate_for_year(1, 10) == pytest.approx(0.03)
        # Year 5/10 = 50% progress: 0.01 + 0.20 * 0.5 = 0.11
        assert model._get_tax_rate_for_year(5, 10) == pytest.approx(0.11)
        # Year 10/10 = 100% progress: 0.01 + 0.20 * 1.0 = 0.21
        assert model._get_tax_rate_for_year(10, 10) == pytest.approx(0.21)


# --- WACC Tax Consistency & Cost of Capital Override ---

class TestWACCTaxConsistency:
    def test_wacc_uses_year_specific_tax_for_debt_shield(self):
        """When effective_tax_rate is set, WACC debt shield should use year-specific rate"""
        assumptions = DCFAssumptions(
            tax_rate=0.21, effective_tax_rate=0.05,
            cost_of_debt=0.05, risk_free_rate=0.045, market_risk_premium=0.05,
        )
        model = DCFModel(assumptions)
        # Year 1 tax = 0.05 + (0.21-0.05) * 1/10 = 0.066
        wacc_year1 = model.calculate_wacc(beta=1.0, debt_to_equity=0.5, market_cap=1000, total_debt=500, tax_rate=0.066)
        # Year 10 tax = 0.21
        wacc_year10 = model.calculate_wacc(beta=1.0, debt_to_equity=0.5, market_cap=1000, total_debt=500, tax_rate=0.21)
        # Lower tax rate → less debt shield → higher WACC
        assert wacc_year1 > wacc_year10

    def test_wacc_varies_in_fair_value_when_effective_set(self):
        """Fair value calculation should use year-varying WACC when effective_tax_rate is set"""
        # With effective tax rate (year-varying WACC)
        assumptions_eff = DCFAssumptions(
            revenue_growth_rate=0.10, tax_rate=0.21, effective_tax_rate=0.05,
            cost_of_debt=0.05, projection_years=10,
        )
        model_eff = DCFModel(assumptions_eff)
        result_eff = model_eff.calculate_fair_value(
            {'revenue': 100e9, 'operating_income': 30e9, 'total_debt': 50e9,
             'cash': 20e9, 'equity': 80e9, 'market_cap': 200e9, 'beta': 1.0},
            shares_outstanding=1e9, current_price=100, verbose=True
        )
        # wacc_per_year should exist and have 10 entries
        assert 'wacc_per_year' in result_eff
        assert len(result_eff['wacc_per_year']) == 10
        # Early years should have higher WACC (less debt shield)
        assert result_eff['wacc_per_year'][0] > result_eff['wacc_per_year'][-1]

    def test_wacc_flat_when_no_effective_tax(self):
        """Without effective_tax_rate, all years should have the same WACC"""
        assumptions = DCFAssumptions(
            revenue_growth_rate=0.10, tax_rate=0.21,
            cost_of_debt=0.05, projection_years=10,
        )
        model = DCFModel(assumptions)
        result = model.calculate_fair_value(
            {'revenue': 100e9, 'operating_income': 30e9, 'total_debt': 50e9,
             'cash': 20e9, 'equity': 80e9, 'market_cap': 200e9, 'beta': 1.0},
            shares_outstanding=1e9, current_price=100, verbose=True
        )
        wacc_per_year = result['wacc_per_year']
        # All years should be the same
        assert all(w == pytest.approx(wacc_per_year[0]) for w in wacc_per_year)

    def test_negative_effective_tax_rate(self):
        """Negative effective tax rate (large NOLs/credits) should not crash"""
        assumptions = DCFAssumptions(
            revenue_growth_rate=0.10, tax_rate=0.21, effective_tax_rate=-0.05,
            cost_of_debt=0.05, projection_years=10,
        )
        model = DCFModel(assumptions)
        result = model.calculate_fair_value(
            {'revenue': 100e9, 'operating_income': 30e9, 'total_debt': 50e9,
             'cash': 20e9, 'equity': 80e9, 'market_cap': 200e9, 'beta': 1.0},
            shares_outstanding=1e9, current_price=100, verbose=True
        )
        # Should produce a valid result (higher fair value from tax benefits)
        assert result['fair_value'] > 0
        # Year 1 WACC should be higher than year 10 (negative tax = no debt shield)
        assert result['wacc_per_year'][0] > result['wacc_per_year'][-1]

    def test_zero_debt_wacc_unaffected_by_tax_transition(self):
        """For zero-debt companies, year-varying tax rate should not affect WACC"""
        assumptions = DCFAssumptions(
            revenue_growth_rate=0.10, tax_rate=0.21, effective_tax_rate=0.05,
            cost_of_debt=0.05, projection_years=10,
        )
        model = DCFModel(assumptions)
        result = model.calculate_fair_value(
            {'revenue': 100e9, 'operating_income': 30e9, 'total_debt': 0,
             'cash': 20e9, 'equity': 80e9, 'market_cap': 200e9, 'beta': 1.0},
            shares_outstanding=1e9, current_price=100, verbose=True
        )
        # All years should have the same WACC (debt weight is zero)
        assert all(w == pytest.approx(result['wacc_per_year'][0]) for w in result['wacc_per_year'])


class TestCostOfCapitalOverride:
    def test_hurdle_rate_overrides_wacc(self):
        """cost_of_capital should bypass WACC computation entirely"""
        assumptions = DCFAssumptions(
            cost_of_capital=0.12,
            risk_free_rate=0.045, market_risk_premium=0.05,
            cost_of_debt=0.05,
        )
        model = DCFModel(assumptions)
        wacc = model.calculate_wacc(beta=1.0, debt_to_equity=0.5, market_cap=1000, total_debt=500)
        assert wacc == 0.12

    def test_hurdle_rate_ignores_beta_and_erp(self):
        """Changing beta/ERP should not affect WACC when cost_of_capital is set"""
        assumptions = DCFAssumptions(cost_of_capital=0.10)
        model = DCFModel(assumptions)
        wacc1 = model.calculate_wacc(beta=0.5, debt_to_equity=0, market_cap=1000, total_debt=0)
        wacc2 = model.calculate_wacc(beta=2.0, debt_to_equity=1.0, market_cap=1000, total_debt=1000)
        assert wacc1 == 0.10
        assert wacc2 == 0.10

    def test_hurdle_rate_used_in_fair_value(self):
        """Fair value should use the manual hurdle rate"""
        assumptions = DCFAssumptions(
            revenue_growth_rate=0.10, cost_of_capital=0.10, projection_years=10,
        )
        model = DCFModel(assumptions)
        result = model.calculate_fair_value(
            {'revenue': 100e9, 'operating_income': 30e9, 'total_debt': 50e9,
             'cash': 20e9, 'equity': 80e9, 'market_cap': 200e9, 'beta': 1.0},
            shares_outstanding=1e9, current_price=100, verbose=True
        )
        assert result['wacc'] == 0.10
        # All years should be the same flat rate
        assert all(w == 0.10 for w in result['wacc_per_year'])

    def test_hurdle_rate_ignores_effective_tax(self):
        """When cost_of_capital is set, effective_tax_rate should not affect WACC"""
        assumptions = DCFAssumptions(
            cost_of_capital=0.10, effective_tax_rate=0.05, tax_rate=0.21,
        )
        model = DCFModel(assumptions)
        wacc = model.calculate_wacc(beta=1.0, debt_to_equity=0.5, market_cap=1000, total_debt=500, tax_rate=0.05)
        assert wacc == 0.10

    def test_hurdle_rate_default_is_none(self):
        """cost_of_capital should default to None (compute WACC from components)"""
        assumptions = DCFAssumptions()
        assert assumptions.cost_of_capital is None

    def test_hurdle_rate_with_effective_tax_rate(self):
        """cost_of_capital override gives flat WACC but NOPAT still uses tax transition"""
        assumptions = DCFAssumptions(
            revenue_growth_rate=0.10, cost_of_capital=0.10,
            tax_rate=0.21, effective_tax_rate=0.05, projection_years=10,
        )
        model = DCFModel(assumptions)
        result = model.calculate_fair_value(
            {'revenue': 100e9, 'operating_income': 30e9, 'total_debt': 50e9,
             'cash': 20e9, 'equity': 80e9, 'market_cap': 200e9, 'beta': 1.0},
            shares_outstanding=1e9, current_price=100, verbose=True
        )
        # WACC should be flat at 10% for all years
        assert all(w == 0.10 for w in result['wacc_per_year'])
        # But FCFs should differ from flat-tax case (NOPAT uses transitioning tax)
        assumptions_flat_tax = DCFAssumptions(
            revenue_growth_rate=0.10, cost_of_capital=0.10,
            tax_rate=0.21, projection_years=10,
        )
        model_flat = DCFModel(assumptions_flat_tax)
        result_flat = model_flat.calculate_fair_value(
            {'revenue': 100e9, 'operating_income': 30e9, 'total_debt': 50e9,
             'cash': 20e9, 'equity': 80e9, 'market_cap': 200e9, 'beta': 1.0},
            shares_outstanding=1e9, current_price=100, verbose=True
        )
        # Lower effective tax → higher early NOPAT → higher fair value
        assert result['fair_value'] > result_flat['fair_value']


# --- Terminal Value ---

class TestTerminalValue:
    def test_positive_terminal_value(self, custom_assumptions):
        model = DCFModel(custom_assumptions)
        tv, details = model.calculate_terminal_value(
            final_year_revenue=500e9, final_year_margin=0.30, wacc=0.10
        )
        assert tv > 0
        assert details['terminal_nopat'] > 0
        assert details['terminal_fcf'] > 0

    def test_wacc_equals_terminal_growth_raises(self):
        assumptions = DCFAssumptions(terminal_growth_rate=0.05)
        model = DCFModel(assumptions)
        with pytest.raises(ValueError, match="WACC.*must be greater"):
            model.calculate_terminal_value(
                final_year_revenue=500e9, final_year_margin=0.30, wacc=0.05
            )

    def test_wacc_below_terminal_growth_raises(self):
        assumptions = DCFAssumptions(terminal_growth_rate=0.05)
        model = DCFModel(assumptions)
        with pytest.raises(ValueError, match="WACC.*must be greater"):
            model.calculate_terminal_value(
                final_year_revenue=500e9, final_year_margin=0.30, wacc=0.03
            )

    def test_higher_growth_increases_terminal_value(self):
        model_low = DCFModel(DCFAssumptions(terminal_growth_rate=0.02))
        model_high = DCFModel(DCFAssumptions(terminal_growth_rate=0.03))
        tv_low, _ = model_low.calculate_terminal_value(
            final_year_revenue=500e9, final_year_margin=0.30, wacc=0.10
        )
        tv_high, _ = model_high.calculate_terminal_value(
            final_year_revenue=500e9, final_year_margin=0.30, wacc=0.10
        )
        assert tv_high > tv_low

    def test_terminal_roic_defaults_to_wacc(self):
        """When terminal_roic is None, it defaults to WACC"""
        assumptions = DCFAssumptions(terminal_growth_rate=0.03)
        model = DCFModel(assumptions)
        _, details = model.calculate_terminal_value(
            final_year_revenue=500e9, final_year_margin=0.30, wacc=0.10
        )
        assert details['terminal_roic'] == 0.10
        # Reinvestment rate = g/WACC = 3%/10% = 30%
        assert details['terminal_reinvestment_rate'] == pytest.approx(0.30)

    def test_explicit_terminal_roic(self):
        """Explicit terminal_roic overrides WACC default"""
        assumptions = DCFAssumptions(terminal_growth_rate=0.03, terminal_roic=0.20)
        model = DCFModel(assumptions)
        _, details = model.calculate_terminal_value(
            final_year_revenue=500e9, final_year_margin=0.30, wacc=0.10
        )
        assert details['terminal_roic'] == 0.20
        # Reinvestment rate = g/ROIC = 3%/20% = 15%
        assert details['terminal_reinvestment_rate'] == pytest.approx(0.15)

    def test_higher_terminal_roic_increases_terminal_value(self):
        """Higher ROIC means less reinvestment, more FCF, higher TV"""
        model_low = DCFModel(DCFAssumptions(terminal_growth_rate=0.03, terminal_roic=0.08))
        model_high = DCFModel(DCFAssumptions(terminal_growth_rate=0.03, terminal_roic=0.20))
        tv_low, _ = model_low.calculate_terminal_value(
            final_year_revenue=500e9, final_year_margin=0.30, wacc=0.10
        )
        tv_high, _ = model_high.calculate_terminal_value(
            final_year_revenue=500e9, final_year_margin=0.30, wacc=0.10
        )
        assert tv_high > tv_low

    def test_terminal_fcf_formula(self):
        """Terminal FCF = NOPAT * (1 - g/ROIC)"""
        assumptions = DCFAssumptions(
            terminal_growth_rate=0.045, terminal_roic=0.15, tax_rate=0.21
        )
        model = DCFModel(assumptions)
        _, details = model.calculate_terminal_value(
            final_year_revenue=100e9, final_year_margin=0.40, wacc=0.10
        )
        # Year 11 revenue = 100B * 1.045 = 104.5B
        # NOPAT = 104.5B * 0.40 * 0.79 = 33.022B
        # Reinvestment rate = 4.5%/15% = 30%
        # FCF = 33.022B * 0.70 = 23.1154B
        assert details['terminal_nopat'] == pytest.approx(104.5e9 * 0.40 * 0.79)
        assert details['terminal_reinvestment_rate'] == pytest.approx(0.30)
        assert details['terminal_fcf'] == pytest.approx(details['terminal_nopat'] * 0.70)

    def test_terminal_value_uses_marginal_not_effective_tax(self):
        """Terminal value should use marginal tax rate even when effective is set"""
        assumptions = DCFAssumptions(
            tax_rate=0.21, effective_tax_rate=0.05,
            terminal_growth_rate=0.03,
        )
        model = DCFModel(assumptions)
        _, details = model.calculate_terminal_value(
            final_year_revenue=100e9, final_year_margin=0.30, wacc=0.10
        )
        # Terminal NOPAT should use marginal (21%), not effective (5%)
        expected_nopat = 100e9 * 1.03 * 0.30 * (1 - 0.21)
        assert details['terminal_nopat'] == pytest.approx(expected_nopat)

    def test_terminal_roic_below_growth_raises(self):
        """Terminal ROIC below terminal growth rate is invalid (reinvestment > 100%)"""
        assumptions = DCFAssumptions(terminal_growth_rate=0.045, terminal_roic=0.03)
        model = DCFModel(assumptions)
        with pytest.raises(ValueError, match="Terminal ROIC.*must be positive"):
            model.calculate_terminal_value(
                final_year_revenue=500e9, final_year_margin=0.30, wacc=0.10
            )

    def test_terminal_roic_zero_raises(self):
        """Zero terminal ROIC is invalid"""
        assumptions = DCFAssumptions(terminal_growth_rate=0.03, terminal_roic=0.0)
        model = DCFModel(assumptions)
        with pytest.raises(ValueError, match="Terminal ROIC.*must be positive"):
            model.calculate_terminal_value(
                final_year_revenue=500e9, final_year_margin=0.30, wacc=0.10
            )

    def test_terminal_roic_equals_growth_rate(self):
        """When ROIC = g, reinvestment = 100%, terminal FCF = 0, terminal value = 0"""
        assumptions = DCFAssumptions(terminal_growth_rate=0.03, terminal_roic=0.03)
        model = DCFModel(assumptions)
        tv, details = model.calculate_terminal_value(
            final_year_revenue=500e9, final_year_margin=0.30, wacc=0.10
        )
        assert details['terminal_reinvestment_rate'] == pytest.approx(1.0)
        assert details['terminal_fcf'] == pytest.approx(0, abs=1)
        assert tv == pytest.approx(0, abs=1)


# --- Present Value ---

class TestPresentValue:
    def test_single_cash_flow(self):
        model = DCFModel()
        pv = model.calculate_present_value([100], 0.10)
        assert pv == pytest.approx(100 / 1.10)

    def test_multiple_cash_flows(self):
        model = DCFModel()
        pv = model.calculate_present_value([100, 100], 0.10)
        expected = 100 / 1.10 + 100 / (1.10 ** 2)
        assert pv == pytest.approx(expected)

    def test_zero_discount_rate(self):
        model = DCFModel()
        pv = model.calculate_present_value([100, 200, 300], 0.0)
        assert pv == pytest.approx(600)

    def test_empty_cash_flows(self):
        model = DCFModel()
        pv = model.calculate_present_value([], 0.10)
        assert pv == 0


# --- Fair Value (Integration) ---

class TestCalculateFairValue:
    def test_returns_required_keys(self, sample_financial_data):
        model = DCFModel()
        results = model.calculate_fair_value(sample_financial_data, 10e9, 100.0)
        for key in ['fair_value', 'current_price', 'upside_percent', 'wacc',
                     'enterprise_value', 'equity_value', 'terminal_value']:
            assert key in results

    def test_fair_value_positive(self, sample_financial_data):
        model = DCFModel()
        results = model.calculate_fair_value(sample_financial_data, 10e9, 100.0)
        assert results['fair_value'] > 0

    def test_upside_calculation(self, sample_financial_data):
        model = DCFModel()
        results = model.calculate_fair_value(sample_financial_data, 10e9, 100.0)
        expected_upside = (results['fair_value'] - 100.0) / 100.0 * 100
        assert results['upside_percent'] == pytest.approx(expected_upside)

    def test_verbose_includes_projections(self, sample_financial_data):
        model = DCFModel()
        results = model.calculate_fair_value(sample_financial_data, 10e9, 100.0, verbose=True)
        assert 'fcf_projections' in results
        assert 'margin_projections' in results
        assert 'base_revenue' in results

    def test_non_verbose_excludes_projections(self, sample_financial_data):
        model = DCFModel()
        results = model.calculate_fair_value(sample_financial_data, 10e9, 100.0, verbose=False)
        assert 'fcf_projections' not in results

    def test_enterprise_value_equals_pv_sum(self, sample_financial_data):
        model = DCFModel()
        r = model.calculate_fair_value(sample_financial_data, 10e9, 100.0)
        assert r['enterprise_value'] == pytest.approx(r['pv_fcf'] + r['pv_terminal_value'])

    def test_custom_sales_to_capital(self, sample_financial_data):
        assumptions = DCFAssumptions(sales_to_capital_ratio=3.0)
        model = DCFModel(assumptions)
        r = model.calculate_fair_value(sample_financial_data, 10e9, 100.0)
        assert r['sales_to_capital'] == 3.0

    def test_auto_sales_to_capital(self, sample_financial_data):
        """When not set, sales-to-capital is calculated from balance sheet"""
        model = DCFModel()
        r = model.calculate_fair_value(sample_financial_data, 10e9, 100.0)
        equity = sample_financial_data['equity']
        debt = sample_financial_data['total_debt']
        cash = sample_financial_data['cash']
        sti = sample_financial_data.get('short_term_investments', 0)
        lti = sample_financial_data.get('long_term_investments', 0)
        expected = sample_financial_data['revenue'] / (equity + debt - cash - sti - lti)
        assert r['sales_to_capital'] == pytest.approx(expected)

    def test_explicit_terminal_roic(self, sample_financial_data):
        """Explicit terminal_roic flows through to results and increases fair value"""
        model_default = DCFModel()
        model_moat = DCFModel(DCFAssumptions(terminal_roic=0.20))
        r_default = model_default.calculate_fair_value(sample_financial_data, 10e9, 100.0)
        r_moat = model_moat.calculate_fair_value(sample_financial_data, 10e9, 100.0)
        # Results include terminal details
        assert 'terminal_roic' in r_default
        assert 'terminal_reinvestment_rate' in r_default
        # Default uses WACC, explicit uses 0.20
        assert r_default['terminal_roic'] == pytest.approx(r_default['wacc'])
        assert r_moat['terminal_roic'] == 0.20
        # Higher ROIC → less reinvestment → higher terminal FCF → higher fair value
        assert r_moat['fair_value'] > r_default['fair_value']

    def test_recalc_consistent_with_main(self, sample_financial_data):
        """_recalc_fair_value produces same result as calculate_fair_value for base case"""
        assumptions = DCFAssumptions(
            revenue_growth_rate=0.10,
            operating_margin=0.30,
            sales_to_capital_ratio=2.0,
            terminal_roic=0.18,
        )
        model = DCFModel(assumptions)
        r = model.calculate_fair_value(sample_financial_data, 10e9, 100.0, verbose=True)
        # Compute net_debt from bridge components
        cash_and_inv = r['cash'] + r.get('short_term_investments', 0) + r.get('long_term_investments', 0)
        net_debt = r['total_debt'] - cash_and_inv
        # _recalc_fair_value with same growth and margin should match
        target_margin = assumptions.target_operating_margin or r['operating_margin']
        recalc_fv = model._recalc_fair_value(
            revenue_growth=assumptions.revenue_growth_rate,
            operating_margin=target_margin,
            wacc=r['wacc'],
            sales_to_capital=r['sales_to_capital'],
            base_revenue=r['base_revenue'],
            shares=r['shares_outstanding'],
            net_debt=net_debt,
        )
        assert recalc_fv == pytest.approx(r['fair_value'], rel=1e-6)

    def test_recalc_consistent_with_year_varying_wacc(self, sample_financial_data):
        """_recalc_fair_value matches calculate_fair_value when effective_tax_rate is set"""
        assumptions = DCFAssumptions(
            revenue_growth_rate=0.10,
            operating_margin=0.30,
            sales_to_capital_ratio=2.0,
            terminal_roic=0.18,
            tax_rate=0.21,
            effective_tax_rate=0.05,
        )
        model = DCFModel(assumptions)
        r = model.calculate_fair_value(sample_financial_data, 10e9, 100.0, verbose=True)
        # wacc_per_year should vary (effective != marginal)
        assert r['wacc_per_year'][0] != pytest.approx(r['wacc_per_year'][-1])
        # Compute net_debt from bridge components
        cash_and_inv = r['cash'] + r.get('short_term_investments', 0) + r.get('long_term_investments', 0)
        net_debt = r['total_debt'] - cash_and_inv
        # _recalc_fair_value should match
        target_margin = assumptions.target_operating_margin or r['operating_margin']
        recalc_fv = model._recalc_fair_value(
            revenue_growth=assumptions.revenue_growth_rate,
            operating_margin=target_margin,
            wacc=r['wacc'],
            sales_to_capital=r['sales_to_capital'],
            base_revenue=r['base_revenue'],
            shares=r['shares_outstanding'],
            net_debt=net_debt,
        )
        assert recalc_fv == pytest.approx(r['fair_value'], rel=1e-6)


# --- Validation ---

class TestValidation:
    def test_missing_revenue_raises(self):
        model = DCFModel()
        data = {'operating_income': 100, 'market_cap': 1000}
        with pytest.raises(ValueError, match="revenue"):
            model.calculate_fair_value(data, 100, 10.0)

    def test_missing_market_cap_raises(self):
        model = DCFModel()
        data = {'revenue': 100, 'operating_income': 50}
        with pytest.raises(ValueError, match="market_cap"):
            model.calculate_fair_value(data, 100, 10.0)

    def test_none_revenue_raises(self):
        model = DCFModel()
        data = {'revenue': None, 'operating_income': 100, 'market_cap': 1000}
        with pytest.raises(ValueError, match="revenue"):
            model.calculate_fair_value(data, 100, 10.0)

    def test_zero_revenue_raises(self):
        model = DCFModel()
        data = {'revenue': 0, 'operating_income': 0, 'market_cap': 1000}
        with pytest.raises(ValueError, match="revenue must be positive"):
            model.calculate_fair_value(data, 100, 10.0)

    def test_zero_shares_raises(self):
        model = DCFModel()
        data = {'revenue': 100, 'operating_income': 50, 'market_cap': 1000}
        with pytest.raises(ValueError, match="shares_outstanding"):
            model.calculate_fair_value(data, 0, 10.0)

    def test_zero_price_raises(self):
        model = DCFModel()
        data = {'revenue': 100, 'operating_income': 50, 'market_cap': 1000}
        with pytest.raises(ValueError, match="current_price"):
            model.calculate_fair_value(data, 100, 0)

    def test_negative_price_raises(self):
        model = DCFModel()
        data = {'revenue': 100, 'operating_income': 50, 'market_cap': 1000}
        with pytest.raises(ValueError, match="current_price"):
            model.calculate_fair_value(data, 100, -5)


# --- Reverse DCF ---

class TestReverseDCF:
    def test_implied_growth_near_target(self, sample_financial_data):
        """reverse_dcf should find a growth rate that produces fair_value ≈ target_price"""
        model = DCFModel(DCFAssumptions())
        # First get fair value at default 10% growth
        result = model.calculate_fair_value(sample_financial_data, 10e9, 100.0, verbose=False)
        target_price = result['fair_value']

        # Now solve: what growth rate produces this fair value?
        reverse = model.reverse_dcf(sample_financial_data, 10e9, target_price)
        assert reverse is not None
        assert abs(reverse['implied_value'] - 0.10) < 0.005  # should be close to 10%

    def test_higher_price_implies_higher_growth(self, sample_financial_data):
        """A higher target price should imply a higher growth rate"""
        model = DCFModel(DCFAssumptions())
        low_result = model.reverse_dcf(sample_financial_data, 10e9, 50.0)
        high_result = model.reverse_dcf(sample_financial_data, 10e9, 200.0)
        assert low_result is not None
        assert high_result is not None
        assert high_result['implied_value'] > low_result['implied_value']

    def test_does_not_mutate_assumptions(self, sample_financial_data):
        """reverse_dcf should restore the original growth rate after solving"""
        assumptions = DCFAssumptions(revenue_growth_rate=0.15)
        model = DCFModel(assumptions)
        model.reverse_dcf(sample_financial_data, 10e9, 100.0)
        assert model.assumptions.revenue_growth_rate == 0.15

    def test_unsupported_solve_for_raises(self, sample_financial_data):
        model = DCFModel()
        with pytest.raises(ValueError, match="currently only supports"):
            model.reverse_dcf(sample_financial_data, 10e9, 100.0, solve_for='beta')

    def test_returns_wacc(self, sample_financial_data):
        model = DCFModel(DCFAssumptions())
        result = model.reverse_dcf(sample_financial_data, 10e9, 100.0)
        assert result is not None
        assert 'wacc' in result
        assert result['wacc'] > 0

    def test_can_find_negative_growth(self, sample_financial_data):
        """Reverse DCF should find negative growth for very low target prices"""
        model = DCFModel(DCFAssumptions())
        # A very low target price should imply negative growth
        result = model.reverse_dcf(sample_financial_data, 10e9, 5.0)
        assert result is not None
        assert result['implied_value'] < 0


# --- Sensitivity Table ---

class TestSensitivityTable:
    def test_negative_growth_in_table(self, sample_financial_data):
        """Sensitivity table should include negative growth when base is low"""
        assumptions = DCFAssumptions(revenue_growth_rate=0.02, sales_to_capital_ratio=2.0)
        model = DCFModel(assumptions)
        model.calculate_fair_value(sample_financial_data, 10e9, 100.0, verbose=True)
        summary = model.get_summary()
        # Base growth is 2%, so -2% step should appear
        assert "-2.0%" in summary or "-2.0%*" in summary


# --- Summary ---

class TestGetSummary:
    def test_no_results_message(self):
        model = DCFModel()
        assert "No valuation calculated" in model.get_summary()

    def test_summary_contains_key_sections(self, sample_financial_data):
        model = DCFModel()
        model.calculate_fair_value(sample_financial_data, 10e9, 100.0, verbose=True)
        summary = model.get_summary()
        assert "MODEL ASSUMPTIONS" in summary
        assert "YEAR-BY-YEAR" in summary
        assert "TERMINAL VALUE" in summary
        assert "VALUATION SUMMARY" in summary
        assert "SENSITIVITY ANALYSIS" in summary
        assert "Recommendation:" in summary

    def test_summary_shows_margin_convergence(self, sample_financial_data):
        assumptions = DCFAssumptions(target_operating_margin=0.40)
        model = DCFModel(assumptions)
        model.calculate_fair_value(sample_financial_data, 10e9, 100.0, verbose=True)
        summary = model.get_summary()
        assert "Target Op. Margin" in summary
        assert "Margin" in summary  # column header

    def test_recommendation_bands(self, sample_financial_data):
        """Verify different upside percentages produce correct recommendations"""
        model = DCFModel()
        model.calculate_fair_value(sample_financial_data, 10e9, 100.0, verbose=True)
        # Manually override upside to test bands
        model.results['upside_percent'] = 25
        assert "STRONG BUY" in model.get_summary()

        model.results['upside_percent'] = 15
        assert "BUY" in model.get_summary()

        model.results['upside_percent'] = 0
        assert "HOLD" in model.get_summary()

        model.results['upside_percent'] = -15
        assert "SELL" in model.get_summary()

        model.results['upside_percent'] = -25
        assert "STRONG SELL" in model.get_summary()


# --- Equity Bridge ---

class TestEquityBridge:
    def test_investments_increase_fair_value(self, sample_financial_data):
        """Short-term and long-term investments should increase equity value"""
        # Pin S/C ratio to isolate the bridge effect from the invested capital effect
        model = DCFModel(DCFAssumptions(sales_to_capital_ratio=2.0))
        r_no_inv = model.calculate_fair_value(sample_financial_data, 10e9, 100.0)

        data_with_inv = {**sample_financial_data, 'short_term_investments': 50e9, 'long_term_investments': 15e9}
        model2 = DCFModel(DCFAssumptions(sales_to_capital_ratio=2.0))
        r_with_inv = model2.calculate_fair_value(data_with_inv, 10e9, 100.0)

        # With S/C pinned, enterprise value is the same — only the bridge differs
        assert r_with_inv['enterprise_value'] == pytest.approx(r_no_inv['enterprise_value'])
        assert r_with_inv['equity_value'] > r_no_inv['equity_value']
        assert r_with_inv['fair_value'] > r_no_inv['fair_value']

    def test_investment_per_share_impact(self):
        """Each dollar of investments adds exactly one dollar to equity value"""
        data = {
            'revenue': 100e9, 'operating_income': 30e9, 'total_debt': 50e9,
            'cash': 10e9, 'short_term_investments': 0, 'long_term_investments': 0,
            'equity': 80e9, 'market_cap': 200e9, 'beta': 1.0,
        }
        # Pin S/C ratio so investments only affect the bridge, not reinvestment
        model1 = DCFModel(DCFAssumptions(sales_to_capital_ratio=2.0))
        r1 = model1.calculate_fair_value(data, 10e9, 100.0)

        data_inv = {**data, 'short_term_investments': 40e9}
        model2 = DCFModel(DCFAssumptions(sales_to_capital_ratio=2.0))
        r2 = model2.calculate_fair_value(data_inv, 10e9, 100.0)

        # $40B more investments / 10B shares = $4.00/share more
        assert r2['fair_value'] - r1['fair_value'] == pytest.approx(4.0)

    def test_missing_investments_default_to_zero(self):
        """When investments fields are absent, they default to zero (backward compat)"""
        data = {
            'revenue': 100e9, 'operating_income': 30e9, 'total_debt': 50e9,
            'cash': 10e9, 'equity': 80e9, 'market_cap': 200e9, 'beta': 1.0,
        }
        model = DCFModel()
        r = model.calculate_fair_value(data, 10e9, 100.0)
        # Should not crash, and equity bridge uses only cash
        assert r['fair_value'] > 0
        assert r['equity_value'] == pytest.approx(r['enterprise_value'] + 10e9 - 50e9)

    def test_verbose_results_include_bridge_components(self, sample_financial_data):
        """Verbose results should include all bridge components"""
        data = {**sample_financial_data, 'short_term_investments': 50e9, 'long_term_investments': 15e9}
        model = DCFModel()
        r = model.calculate_fair_value(data, 10e9, 100.0, verbose=True)
        assert r['cash'] == 60e9
        assert r['short_term_investments'] == 50e9
        assert r['long_term_investments'] == 15e9
        assert r['total_debt'] == 100e9

    def test_summary_shows_equity_bridge(self, sample_financial_data):
        """Summary should display the equity bridge with line items"""
        data = {**sample_financial_data, 'short_term_investments': 50e9, 'long_term_investments': 15e9}
        model = DCFModel()
        model.calculate_fair_value(data, 10e9, 100.0, verbose=True)
        summary = model.get_summary()
        assert "EQUITY BRIDGE" in summary
        assert "Cash & Equivalents" in summary
        assert "Short-Term Investments" in summary
        assert "Long-Term Investments" in summary
        assert "Total Debt" in summary

    def test_net_cash_company(self):
        """Company with more cash+investments than debt should have equity > EV"""
        data = {
            'revenue': 100e9, 'operating_income': 30e9, 'total_debt': 10e9,
            'cash': 20e9, 'short_term_investments': 50e9, 'long_term_investments': 10e9,
            'equity': 80e9, 'market_cap': 200e9, 'beta': 1.0,
        }
        model = DCFModel()
        r = model.calculate_fair_value(data, 10e9, 100.0)
        # Cash + investments - debt = 20B + 50B + 10B - 10B = 70B net cash
        assert r['equity_value'] > r['enterprise_value']

    def test_sensitivity_table_uses_full_bridge(self, sample_financial_data):
        """Sensitivity table should account for investments in net debt"""
        data = {**sample_financial_data, 'short_term_investments': 50e9, 'long_term_investments': 15e9}
        assumptions = DCFAssumptions(sales_to_capital_ratio=2.0)
        model = DCFModel(assumptions)
        r = model.calculate_fair_value(data, 10e9, 100.0, verbose=True)
        # The base case in sensitivity table should match the main fair value
        summary = model.get_summary()
        # Check that the bracketed base case value in the sensitivity table
        # approximately matches the computed fair value
        import re
        match = re.search(r'\[\$([0-9,]+)\]', summary)
        assert match is not None
        base_case_from_table = float(match.group(1).replace(',', ''))
        assert base_case_from_table == pytest.approx(r['fair_value'], rel=0.01)
