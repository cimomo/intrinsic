"""Tests for stock_analyzer.metrics"""

import pytest
from stock_analyzer.metrics import (
    FinancialMetrics, CompanyMetrics,
    get_synthetic_rating, get_spread_for_rating,
    SYNTHETIC_RATING_TABLE_LARGE, RATING_TO_SPREAD,
)


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
                'shortTermInvestments': '50000000000',
                'longTermInvestments': '15000000000',
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

    def test_extracts_investments(self, full_statements):
        """Short-term and long-term investments are extracted from balance sheet"""
        income, balance, cashflow, overview = full_statements
        inputs = FinancialMetrics.calculate_dcf_inputs(income, balance, cashflow, overview)
        assert inputs['short_term_investments'] == 50_000_000_000
        assert inputs['long_term_investments'] == 15_000_000_000

    def test_investments_default_to_zero(self):
        """When investment fields are absent, they default to zero"""
        income = [{'totalRevenue': '100'}]
        balance = [{'cashAndCashEquivalentsAtCarryingValue': '10'}]
        inputs = FinancialMetrics.calculate_dcf_inputs(income, balance, [{}], {})
        assert inputs['short_term_investments'] == 0
        assert inputs['long_term_investments'] == 0

    def test_invested_capital_excludes_investments(self):
        """Invested capital subtracts cash, STI, and LTI (non-operating assets)"""
        income = [{'totalRevenue': '100000', 'operatingIncome': '30000'}]
        balance = [{
            'totalShareholderEquity': '200000',
            'shortLongTermDebtTotal': '50000',
            'cashAndCashEquivalentsAtCarryingValue': '20000',
            'shortTermInvestments': '40000',
            'longTermInvestments': '10000',
        }]
        inputs = FinancialMetrics.calculate_dcf_inputs(income, balance, [{}], {})
        # Invested Capital = 200K + 50K - 20K - 40K - 10K = 180K
        assert inputs['invested_capital'] == 180_000

    def test_capex_always_positive(self):
        cashflow = [{'capitalExpenditures': '-5000'}]
        inputs = FinancialMetrics.calculate_dcf_inputs([{}], [{}], cashflow, {})
        assert inputs['capex'] == 5000

    def test_roic_with_effective_tax_rate(self, full_statements):
        """ROIC uses effective tax rate from income statement"""
        income, balance, cashflow, overview = full_statements
        # Add tax data: 20% effective rate (24B tax on 120B pre-tax)
        income[0]['incomeTaxExpense'] = '24000000000'
        income[0]['incomeBeforeTax'] = '120000000000'
        inputs = FinancialMetrics.calculate_dcf_inputs(income, balance, cashflow, overview)
        # NOPAT = 120B * (1 - 0.20) = 96B
        # Invested Capital = 200B + 100B - 60B - 50B - 15B = 175B
        # ROIC = 96B / 175B ≈ 0.5486
        assert inputs['roic'] == pytest.approx(96e9 / 175e9)
        assert inputs['invested_capital'] == 175_000_000_000

    def test_roic_defaults_to_marginal_tax_when_no_tax_data(self, full_statements):
        """Falls back to 21% marginal rate when tax data missing"""
        income, balance, cashflow, overview = full_statements
        inputs = FinancialMetrics.calculate_dcf_inputs(income, balance, cashflow, overview)
        # NOPAT = 120B * (1 - 0.21) = 94.8B
        # Invested Capital = 200B + 100B - 60B - 50B - 15B = 175B
        # ROIC = 94.8B / 175B ≈ 0.5417
        assert inputs['roic'] == pytest.approx(94.8e9 / 175e9)

    def test_roic_negative_operating_income(self):
        """Negative operating income produces negative ROIC"""
        income = [{'totalRevenue': '100000', 'operatingIncome': '-20000'}]
        balance = [{'totalShareholderEquity': '80000', 'shortLongTermDebtTotal': '30000',
                    'cashAndCashEquivalentsAtCarryingValue': '10000'}]
        inputs = FinancialMetrics.calculate_dcf_inputs(income, balance, [{}], {})
        # Invested Capital = 80K + 30K - 10K = 100K
        # NOPAT = -20K * (1 - 0.21) = -15.8K
        # ROIC = -15.8K / 100K = -0.158
        assert inputs['roic'] == pytest.approx(-0.158)
        assert inputs['roic'] < 0

    def test_roic_none_when_invested_capital_zero_or_negative(self):
        """ROIC is None when cash exceeds equity + debt"""
        income = [{'totalRevenue': '100000', 'operatingIncome': '30000'}]
        balance = [{'totalShareholderEquity': '20000', 'shortLongTermDebtTotal': '10000',
                    'cashAndCashEquivalentsAtCarryingValue': '50000'}]
        inputs = FinancialMetrics.calculate_dcf_inputs(income, balance, [{}], {})
        # Invested Capital = 20K + 10K - 50K = -20K
        assert inputs['roic'] is None

    def test_roic_zero_operating_income(self):
        """Zero operating income produces ROIC of zero, not None"""
        income = [{'totalRevenue': '100000', 'operatingIncome': '0'}]
        balance = [{'totalShareholderEquity': '80000', 'shortLongTermDebtTotal': '20000',
                    'cashAndCashEquivalentsAtCarryingValue': '10000'}]
        inputs = FinancialMetrics.calculate_dcf_inputs(income, balance, [{}], {})
        assert inputs['roic'] == 0.0

    def test_roic_empty_statements(self):
        """ROIC is None when no data available"""
        inputs = FinancialMetrics.calculate_dcf_inputs([], [], [], {})
        assert inputs['roic'] is None

    def test_roic_negative_pretax_income_uses_marginal_rate(self):
        """Negative pre-tax income (non-operating losses) falls back to 21% marginal"""
        income = [{'totalRevenue': '100000', 'operatingIncome': '20000',
                   'incomeBeforeTax': '-5000', 'incomeTaxExpense': '0'}]
        balance = [{'totalShareholderEquity': '80000', 'shortLongTermDebtTotal': '20000',
                    'cashAndCashEquivalentsAtCarryingValue': '10000'}]
        inputs = FinancialMetrics.calculate_dcf_inputs(income, balance, [{}], {})
        # pre_tax_income < 0 → falls back to 21% marginal
        # NOPAT = 20K * (1 - 0.21) = 15.8K
        # Invested Capital = 80K + 20K - 10K = 90K
        assert inputs['roic'] == pytest.approx(15800 / 90000)

    def test_roic_negative_tax_expense_uses_marginal_rate(self):
        """Negative tax expense (tax credits/refunds) falls back to 21% marginal"""
        income = [{'totalRevenue': '100000', 'operatingIncome': '20000',
                   'incomeBeforeTax': '15000', 'incomeTaxExpense': '-2000'}]
        balance = [{'totalShareholderEquity': '80000', 'shortLongTermDebtTotal': '20000',
                    'cashAndCashEquivalentsAtCarryingValue': '10000'}]
        inputs = FinancialMetrics.calculate_dcf_inputs(income, balance, [{}], {})
        # tax_expense < 0 → falls back to 21% marginal
        # NOPAT = 20K * (1 - 0.21) = 15.8K
        # Invested Capital = 90K
        assert inputs['roic'] == pytest.approx(15800 / 90000)


# --- Synthetic Credit Rating ---

class TestGetSyntheticRating:
    def test_large_firm_aaa(self):
        """Coverage > 8.5 for large firm -> Aaa/AAA"""
        result = get_synthetic_rating(coverage_ratio=57.2, market_cap=100e9)
        assert result['rating'] == 'Aaa/AAA'
        assert result['default_spread'] == 0.0040
        assert result['firm_size'] == 'large'

    def test_large_firm_bbb(self):
        """Coverage 2.5-3.0 for large firm -> Baa2/BBB"""
        result = get_synthetic_rating(coverage_ratio=2.7, market_cap=10e9)
        assert result['rating'] == 'Baa2/BBB'
        assert result['default_spread'] == 0.0111

    def test_large_firm_boundary_exact(self):
        """Exact boundary value (8.50) -> Aaa/AAA (inclusive lower bound)"""
        result = get_synthetic_rating(coverage_ratio=8.50, market_cap=10e9)
        assert result['rating'] == 'Aaa/AAA'

    def test_large_firm_just_below_boundary(self):
        """Just below 8.50 -> Aa2/AA"""
        result = get_synthetic_rating(coverage_ratio=8.49, market_cap=10e9)
        assert result['rating'] == 'Aa2/AA'

    def test_small_firm_same_coverage_different_rating(self):
        """Same coverage (9.0) yields A1/A+ for small firm but Aaa/AAA for large"""
        large = get_synthetic_rating(coverage_ratio=9.0, market_cap=10e9)
        small = get_synthetic_rating(coverage_ratio=9.0, market_cap=3e9)
        assert large['rating'] == 'Aaa/AAA'
        assert small['rating'] == 'A1/A+'

    def test_small_firm_higher_spread(self):
        """Small firm AAA spread (0.60%) > large firm AAA spread (0.40%)"""
        small = get_synthetic_rating(coverage_ratio=13.0, market_cap=3e9)
        large = get_synthetic_rating(coverage_ratio=13.0, market_cap=10e9)
        assert small['default_spread'] == 0.0060
        assert large['default_spread'] == 0.0040

    def test_market_cap_threshold(self):
        """$5B is the cutoff — at $5B use large table, below use small"""
        at_threshold = get_synthetic_rating(coverage_ratio=9.0, market_cap=5e9)
        below_threshold = get_synthetic_rating(coverage_ratio=9.0, market_cap=4.99e9)
        assert at_threshold['firm_size'] == 'large'
        assert below_threshold['firm_size'] == 'small'

    def test_zero_interest_expense_infinite_coverage(self):
        """Debt-free company (infinite coverage) -> AAA"""
        result = get_synthetic_rating(coverage_ratio=float('inf'), market_cap=10e9)
        assert result['rating'] == 'Aaa/AAA'
        assert result['default_spread'] == 0.0040

    def test_negative_coverage_d_rating(self):
        """Negative EBIT -> negative coverage -> D rating"""
        result = get_synthetic_rating(coverage_ratio=-2.0, market_cap=10e9)
        assert result['rating'] == 'D2/D'
        assert result['default_spread'] == 0.1900

    def test_zero_coverage_d_rating(self):
        """Zero coverage -> D rating"""
        result = get_synthetic_rating(coverage_ratio=0.0, market_cap=10e9)
        assert result['rating'] == 'D2/D'

    def test_returns_coverage_ratio(self):
        """Result includes the input coverage ratio"""
        result = get_synthetic_rating(coverage_ratio=5.0, market_cap=10e9)
        assert result['coverage_ratio'] == 5.0


class TestGetSpreadForRating:
    def test_sp_aaa(self):
        assert get_spread_for_rating("AAA") == 0.0040

    def test_moodys_aaa(self):
        assert get_spread_for_rating("Aaa") == 0.0040

    def test_sp_aa_plus(self):
        assert get_spread_for_rating("AA+") == 0.0055

    def test_moodys_aa2(self):
        assert get_spread_for_rating("Aa2") == 0.0055

    def test_sp_a(self):
        assert get_spread_for_rating("A") == 0.0078

    def test_sp_bbb_minus(self):
        assert get_spread_for_rating("BBB-") == 0.0111

    def test_moodys_ba1(self):
        assert get_spread_for_rating("Ba1") == 0.0138

    def test_unknown_rating_returns_none(self):
        assert get_spread_for_rating("XYZ") is None

    def test_empty_string_returns_none(self):
        assert get_spread_for_rating("") is None

    def test_case_sensitive(self):
        """Ratings are case-sensitive — 'aaa' is not 'AAA'"""
        assert get_spread_for_rating("aaa") is None


class TestInterestCoverageAndSyntheticDebt:
    @pytest.fixture
    def statements_with_interest(self):
        income = [{
            'totalRevenue': '400000000000',
            'operatingIncome': '120000000000',
            'interestExpense': '2500000000',
        }]
        balance = [{
            'shortLongTermDebtTotal': '100000000000',
            'cashAndCashEquivalentsAtCarryingValue': '60000000000',
            'totalShareholderEquity': '200000000000',
            'totalAssets': '350000000000',
        }]
        overview = {'MarketCapitalization': '2500000000000', 'Beta': '1.2'}
        return income, balance, [{}], overview

    def test_interest_expense_extracted(self, statements_with_interest):
        income, balance, cashflow, overview = statements_with_interest
        inputs = FinancialMetrics.calculate_dcf_inputs(income, balance, cashflow, overview)
        assert inputs['interest_expense'] == 2_500_000_000

    def test_interest_coverage_computed(self, statements_with_interest):
        income, balance, cashflow, overview = statements_with_interest
        inputs = FinancialMetrics.calculate_dcf_inputs(income, balance, cashflow, overview)
        # 120B / 2.5B = 48.0
        assert inputs['interest_coverage'] == pytest.approx(48.0)

    def test_synthetic_rating_in_dcf_inputs(self, statements_with_interest):
        income, balance, cashflow, overview = statements_with_interest
        inputs = FinancialMetrics.calculate_dcf_inputs(income, balance, cashflow, overview)
        # Coverage 48.0, market cap $2.5T -> large firm -> Aaa/AAA
        assert inputs['synthetic_rating'] == 'Aaa/AAA'
        assert inputs['synthetic_spread'] == 0.0040

    def test_zero_interest_expense(self):
        """Debt-free company -> infinite coverage -> AAA"""
        income = [{'totalRevenue': '100000', 'operatingIncome': '30000',
                   'interestExpense': '0'}]
        balance = [{'totalShareholderEquity': '80000'}]
        inputs = FinancialMetrics.calculate_dcf_inputs(income, balance, [{}],
                    {'MarketCapitalization': '10000000000'})
        assert inputs['interest_coverage'] == float('inf')
        assert inputs['synthetic_rating'] == 'Aaa/AAA'

    def test_missing_interest_expense(self):
        """No interest expense field -> None for all synthetic fields"""
        income = [{'totalRevenue': '100000', 'operatingIncome': '30000'}]
        balance = [{'totalShareholderEquity': '80000'}]
        inputs = FinancialMetrics.calculate_dcf_inputs(income, balance, [{}], {})
        assert inputs['interest_expense'] is None
        assert inputs['interest_coverage'] is None
        assert inputs['synthetic_rating'] is None
        assert inputs['synthetic_spread'] is None

    def test_negative_operating_income(self):
        """Negative EBIT -> negative coverage -> D rating"""
        income = [{'totalRevenue': '100000', 'operatingIncome': '-20000',
                   'interestExpense': '5000'}]
        balance = [{'totalShareholderEquity': '80000'}]
        inputs = FinancialMetrics.calculate_dcf_inputs(income, balance, [{}],
                    {'MarketCapitalization': '10000000000'})
        assert inputs['interest_coverage'] == pytest.approx(-4.0)
        assert inputs['synthetic_rating'] == 'D2/D'

    def test_small_firm_synthetic_rating(self):
        """Small firm ($2B) uses different table"""
        income = [{'totalRevenue': '5000000000', 'operatingIncome': '500000000',
                   'interestExpense': '100000000'}]
        balance = [{'totalShareholderEquity': '2000000000'}]
        inputs = FinancialMetrics.calculate_dcf_inputs(income, balance, [{}],
                    {'MarketCapitalization': '2000000000'})
        # Coverage = 5.0, market cap $2B -> small firm -> A3/A- (4.50-6.00 range)
        assert inputs['synthetic_rating'] == 'A3/A-'
        assert inputs['synthetic_spread'] == 0.0125

    def test_interest_expense_none_string(self):
        """Alpha Vantage returns 'None' string for missing fields"""
        income = [{'totalRevenue': '100000', 'operatingIncome': '30000',
                   'interestExpense': 'None'}]
        balance = [{'totalShareholderEquity': '80000'}]
        inputs = FinancialMetrics.calculate_dcf_inputs(income, balance, [{}], {})
        assert inputs['interest_expense'] is None
        assert inputs['interest_coverage'] is None


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
