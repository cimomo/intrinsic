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
        fcfs, margins = model.project_free_cash_flows(
            base_revenue=100e9, operating_margin=0.30,
            sales_to_capital=2.0, years=10
        )
        assert len(fcfs) == 10
        assert len(margins) == 10

    def test_fcf_positive_for_profitable_company(self, custom_assumptions):
        model = DCFModel(custom_assumptions)
        fcfs, _ = model.project_free_cash_flows(
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
        fcfs, _ = model.project_free_cash_flows(
            base_revenue=100e9, operating_margin=0.25,
            sales_to_capital=2.0, years=10
        )
        # FCF growth rate should slow in later years
        growth_5_6 = fcfs[5] / fcfs[4] - 1
        growth_9_10 = fcfs[9] / fcfs[8] - 1
        assert growth_9_10 < growth_5_6

    def test_no_margin_convergence_by_default(self, custom_assumptions):
        model = DCFModel(custom_assumptions)
        _, margins = model.project_free_cash_flows(
            base_revenue=100e9, operating_margin=0.25,
            sales_to_capital=2.0, years=10
        )
        assert all(m == 0.25 for m in margins)

    def test_margin_convergence(self):
        assumptions = DCFAssumptions(target_operating_margin=0.40, projection_years=10)
        model = DCFModel(assumptions)
        _, margins = model.project_free_cash_flows(
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
        _, margins = model.project_free_cash_flows(
            base_revenue=100e9, operating_margin=0.30,
            sales_to_capital=2.0, years=10
        )
        assert margins[-1] == pytest.approx(0.15)
        assert margins[0] < 0.30

    def test_zero_sales_to_capital(self):
        """Zero sales-to-capital should mean zero reinvestment"""
        model = DCFModel(DCFAssumptions(projection_years=3))
        fcfs, _ = model.project_free_cash_flows(
            base_revenue=100e9, operating_margin=0.20,
            sales_to_capital=0, years=3
        )
        # FCF = NOPAT (no reinvestment subtracted)
        assert all(fcf > 0 for fcf in fcfs)


# --- Terminal Value ---

class TestTerminalValue:
    def test_positive_terminal_value(self, custom_assumptions):
        model = DCFModel(custom_assumptions)
        tv = model.calculate_terminal_value(final_year_fcf=50e9, wacc=0.10)
        assert tv > 0

    def test_wacc_equals_terminal_growth_raises(self):
        assumptions = DCFAssumptions(terminal_growth_rate=0.05)
        model = DCFModel(assumptions)
        with pytest.raises(ValueError, match="WACC.*must be greater"):
            model.calculate_terminal_value(final_year_fcf=50e9, wacc=0.05)

    def test_wacc_below_terminal_growth_raises(self):
        assumptions = DCFAssumptions(terminal_growth_rate=0.05)
        model = DCFModel(assumptions)
        with pytest.raises(ValueError, match="WACC.*must be greater"):
            model.calculate_terminal_value(final_year_fcf=50e9, wacc=0.03)

    def test_higher_growth_increases_terminal_value(self):
        model_low = DCFModel(DCFAssumptions(terminal_growth_rate=0.02))
        model_high = DCFModel(DCFAssumptions(terminal_growth_rate=0.03))
        tv_low = model_low.calculate_terminal_value(final_year_fcf=50e9, wacc=0.10)
        tv_high = model_high.calculate_terminal_value(final_year_fcf=50e9, wacc=0.10)
        assert tv_high > tv_low


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
        expected = sample_financial_data['revenue'] / (equity + debt - cash)
        assert r['sales_to_capital'] == pytest.approx(expected)


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
