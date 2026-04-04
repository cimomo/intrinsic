"""Tests for stock_analyzer.metrics"""

import pytest
from stock_analyzer.metrics import FinancialMetrics, CompanyMetrics


# --- Parse Overview ---

class TestParseOverview:
    def test_full_data(self):
        data = {
            'MarketCapitalization': '2800000000000',
            'PERatio': '28.5',
            'PEGRatio': '2.1',
            'PriceToBookRatio': '45.2',
            'ProfitMargin': '0.25',
            'OperatingMarginTTM': '0.30',
            'ReturnOnEquityTTM': '1.47',
            'EPS': '6.15',
            'Beta': '1.25',
        }
        metrics = FinancialMetrics.parse_alpha_vantage_overview(data)
        assert metrics.market_cap == 2_800_000_000_000
        assert metrics.pe_ratio == 28.5
        assert metrics.profit_margin == 0.25
        assert metrics.eps == 6.15

    def test_missing_fields_return_none(self):
        data = {'MarketCapitalization': '1000000'}
        metrics = FinancialMetrics.parse_alpha_vantage_overview(data)
        assert metrics.market_cap == 1_000_000
        assert metrics.pe_ratio is None
        assert metrics.peg_ratio is None
        assert metrics.dividend_yield is None

    def test_none_values_handled(self):
        data = {'MarketCapitalization': 'None', 'PERatio': '-'}
        metrics = FinancialMetrics.parse_alpha_vantage_overview(data)
        assert metrics.market_cap == 0  # default for market_cap
        assert metrics.pe_ratio is None

    def test_empty_dict(self):
        metrics = FinancialMetrics.parse_alpha_vantage_overview({})
        assert metrics.market_cap == 0
        assert metrics.pe_ratio is None


# --- DCF Inputs ---

class TestCalculateDCFInputs:
    @pytest.fixture
    def full_statements(self):
        income = [{'totalRevenue': '400000000000', 'operatingIncome': '120000000000'}]
        balance = [
            {
                'shortLongTermDebtTotal': '100000000000',
                'cashAndCashEquivalentsAtCarryingValue': '60000000000',
                'totalAssets': '350000000000',
                'totalShareholderEquity': '200000000000',
                'totalCurrentAssets': '140000000000',
                'totalCurrentLiabilities': '150000000000',
            },
            {
                'totalCurrentAssets': '130000000000',
                'totalCurrentLiabilities': '140000000000',
            }
        ]
        cashflow = [{'operatingCashflow': '120000000000', 'capitalExpenditures': '-11000000000'}]
        overview = {'MarketCapitalization': '2500000000000', 'Beta': '1.2'}
        return income, balance, cashflow, overview

    def test_extracts_revenue(self, full_statements):
        income, balance, cashflow, overview = full_statements
        inputs = FinancialMetrics.calculate_dcf_inputs(income, balance, cashflow, overview)
        assert inputs['revenue'] == 400_000_000_000

    def test_extracts_market_cap(self, full_statements):
        income, balance, cashflow, overview = full_statements
        inputs = FinancialMetrics.calculate_dcf_inputs(income, balance, cashflow, overview)
        assert inputs['market_cap'] == 2_500_000_000_000

    def test_beta_defaults_to_one(self):
        inputs = FinancialMetrics.calculate_dcf_inputs(
            [{'totalRevenue': '100'}], [{}], [{}], {}
        )
        assert inputs['beta'] == 1.0

    def test_calculates_nwc_change(self, full_statements):
        income, balance, cashflow, overview = full_statements
        inputs = FinancialMetrics.calculate_dcf_inputs(income, balance, cashflow, overview)
        # (140B - 150B) - (130B - 140B) = -10B - (-10B) = 0
        assert inputs['nwc_change'] == 0

    def test_debt_fallback_to_components(self):
        """Falls back to short + long term debt when total not available"""
        income = [{'totalRevenue': '100'}]
        balance = [{'shortTermDebt': '30', 'longTermDebt': '70'}]
        inputs = FinancialMetrics.calculate_dcf_inputs(income, balance, [{}], {})
        assert inputs['total_debt'] == 100

    def test_empty_statements(self):
        inputs = FinancialMetrics.calculate_dcf_inputs([], [], [], {})
        assert inputs['revenue'] == 0
        assert inputs['market_cap'] == 0

    def test_capex_always_positive(self):
        cashflow = [{'capitalExpenditures': '-5000'}]
        inputs = FinancialMetrics.calculate_dcf_inputs([{}], [{}], cashflow, {})
        assert inputs['capex'] == 5000


# --- Format Metrics ---

class TestFormatMetrics:
    def test_contains_sections(self):
        metrics = CompanyMetrics(market_cap=1e12, pe_ratio=25.0, eps=5.0)
        table = FinancialMetrics.format_metrics_table(metrics)
        assert "VALUATION METRICS" in table
        assert "PROFITABILITY" in table
        assert "PER SHARE" in table

    def test_none_values_show_na(self):
        metrics = CompanyMetrics(market_cap=1e12)
        table = FinancialMetrics.format_metrics_table(metrics)
        assert "N/A" in table

    def test_currency_formatting(self):
        metrics = CompanyMetrics(market_cap=2.5e12, eps=6.15)
        table = FinancialMetrics.format_metrics_table(metrics)
        assert "$2500.00B" in table or "$2,500.00B" in table
        assert "$6.15" in table


# --- CAGR ---

class TestGrowthRate:
    def test_simple_growth(self):
        # 100 -> 200 in 1 year = 100% CAGR
        cagr = FinancialMetrics.calculate_growth_rate([100, 200])
        assert cagr == pytest.approx(1.0)

    def test_multi_year(self):
        # 100 -> 121 in 2 years = 10% CAGR
        cagr = FinancialMetrics.calculate_growth_rate([100, 110, 121])
        assert cagr == pytest.approx(0.10)

    def test_negative_start_returns_none(self):
        assert FinancialMetrics.calculate_growth_rate([-100, 200]) is None

    def test_zero_start_returns_none(self):
        assert FinancialMetrics.calculate_growth_rate([0, 200]) is None

    def test_single_value_returns_none(self):
        assert FinancialMetrics.calculate_growth_rate([100]) is None

    def test_custom_years(self):
        cagr = FinancialMetrics.calculate_growth_rate([100, 121], years=2)
        assert cagr == pytest.approx(0.10)


# --- FCF ---

class TestFCF:
    def test_simple(self):
        assert FinancialMetrics.calculate_free_cash_flow(120, 20) == 100

    def test_negative_capex_handled(self):
        assert FinancialMetrics.calculate_free_cash_flow(120, -20) == 100


# --- Quarterly Growth ---

class TestQuarterlyGrowth:
    def test_insufficient_data(self):
        assert "Insufficient" in FinancialMetrics.calculate_quarterly_growth([])
        assert "Insufficient" in FinancialMetrics.calculate_quarterly_growth([{'totalRevenue': '100'}])

    def test_valid_quarters(self):
        quarters = [
            {'fiscalDateEnding': '2025-09-30', 'totalRevenue': '110000000000'},
            {'fiscalDateEnding': '2025-06-30', 'totalRevenue': '105000000000'},
            {'fiscalDateEnding': '2025-03-31', 'totalRevenue': '100000000000'},
        ]
        output = FinancialMetrics.calculate_quarterly_growth(quarters)
        assert "QUARTERLY REVENUE GROWTH" in output
        assert "QoQ Growth" in output

    def test_invalid_revenue_filtered(self):
        quarters = [
            {'fiscalDateEnding': '2025-09-30', 'totalRevenue': '110000000000'},
            {'fiscalDateEnding': '2025-06-30', 'totalRevenue': 'None'},
            {'fiscalDateEnding': '2025-03-31', 'totalRevenue': '100000000000'},
        ]
        output = FinancialMetrics.calculate_quarterly_growth(quarters)
        assert "QUARTERLY REVENUE GROWTH" in output
