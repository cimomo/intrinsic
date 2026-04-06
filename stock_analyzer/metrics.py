"""
Financial Metrics Calculator

Utilities for calculating and formatting financial metrics from company data.
"""

from typing import Dict, List, Optional
from dataclasses import dataclass
from .utils import safe_float


@dataclass
class CompanyMetrics:
    """Container for company financial metrics"""

    # Valuation metrics
    market_cap: float
    pe_ratio: Optional[float] = None
    peg_ratio: Optional[float] = None
    price_to_book: Optional[float] = None
    price_to_sales: Optional[float] = None
    ev_to_ebitda: Optional[float] = None

    # Profitability metrics
    profit_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    return_on_equity: Optional[float] = None
    return_on_assets: Optional[float] = None
    roic: Optional[float] = None

    # Growth metrics
    revenue_growth: Optional[float] = None
    earnings_growth: Optional[float] = None

    # Financial health
    current_ratio: Optional[float] = None
    debt_to_equity: Optional[float] = None
    interest_coverage: Optional[float] = None

    # Per share metrics
    eps: Optional[float] = None
    book_value_per_share: Optional[float] = None
    free_cash_flow_per_share: Optional[float] = None

    # Dividend metrics
    dividend_yield: Optional[float] = None
    payout_ratio: Optional[float] = None


class FinancialMetrics:
    """
    Helper class for calculating and formatting financial metrics
    """

    @staticmethod
    def parse_alpha_vantage_overview(overview_data: Dict) -> CompanyMetrics:
        """
        Parse Alpha Vantage company overview data into CompanyMetrics

        Args:
            overview_data: Raw data from Alpha Vantage COMPANY_OVERVIEW

        Returns:
            CompanyMetrics object with parsed values
        """

        return CompanyMetrics(
            market_cap=safe_float(overview_data.get('MarketCapitalization'), 0),
            pe_ratio=safe_float(overview_data.get('PERatio')),
            peg_ratio=safe_float(overview_data.get('PEGRatio')),
            price_to_book=safe_float(overview_data.get('PriceToBookRatio')),
            price_to_sales=safe_float(overview_data.get('PriceToSalesRatioTTM')),
            ev_to_ebitda=safe_float(overview_data.get('EVToEBITDA')),
            profit_margin=safe_float(overview_data.get('ProfitMargin')),
            operating_margin=safe_float(overview_data.get('OperatingMarginTTM')),
            return_on_equity=safe_float(overview_data.get('ReturnOnEquityTTM')),
            return_on_assets=safe_float(overview_data.get('ReturnOnAssetsTTM')),
            revenue_growth=safe_float(overview_data.get('QuarterlyRevenueGrowthYOY')),
            earnings_growth=safe_float(overview_data.get('QuarterlyEarningsGrowthYOY')),
            debt_to_equity=safe_float(overview_data.get('DebtToEquity')),
            eps=safe_float(overview_data.get('EPS')),
            book_value_per_share=safe_float(overview_data.get('BookValue')),
            dividend_yield=safe_float(overview_data.get('DividendYield')),
        )

    @staticmethod
    def calculate_dcf_inputs(
        income_statement: List[Dict],
        balance_sheet: List[Dict],
        cash_flow: List[Dict],
        overview: Dict
    ) -> Dict:
        """
        Extract and calculate inputs needed for DCF valuation

        Args:
            income_statement: Annual income statements
            balance_sheet: Annual balance sheets
            cash_flow: Annual cash flow statements
            overview: Company overview data

        Returns:
            Dictionary with DCF input parameters
        """

        # Get most recent year's data
        latest_income = income_statement[0] if income_statement else {}
        latest_balance = balance_sheet[0] if balance_sheet else {}
        latest_cashflow = cash_flow[0] if cash_flow else {}

        # Extract key figures
        revenue = safe_float(latest_income.get('totalRevenue'), 0)
        operating_income = safe_float(latest_income.get('operatingIncome'), 0)

        # Try to get total debt from various possible field names
        total_debt = safe_float(latest_balance.get('shortLongTermDebtTotal'), 0)

        # If not available, try calculating from individual components
        if total_debt == 0:
            total_debt = (
                safe_float(latest_balance.get('shortTermDebt'), 0) +
                safe_float(latest_balance.get('longTermDebt'), 0)
            )

        cash = safe_float(latest_balance.get('cashAndCashEquivalentsAtCarryingValue'), 0)
        total_assets = safe_float(latest_balance.get('totalAssets'), 0)
        equity = safe_float(latest_balance.get('totalShareholderEquity'), 0)

        # CapEx and working capital
        capex = abs(safe_float(latest_cashflow.get('capitalExpenditures'), 0))
        operating_cashflow = safe_float(latest_cashflow.get('operatingCashflow'), 0)

        # Calculate working capital change (simplified)
        current_assets = safe_float(latest_balance.get('totalCurrentAssets'), 0)
        current_liabilities = safe_float(latest_balance.get('totalCurrentLiabilities'), 0)

        # Previous year's working capital for change calculation
        if len(balance_sheet) > 1:
            prev_balance = balance_sheet[1]
            prev_current_assets = safe_float(prev_balance.get('totalCurrentAssets'), 0)
            prev_current_liabilities = safe_float(prev_balance.get('totalCurrentLiabilities'), 0)
            nwc_change = (
                (current_assets - current_liabilities) -
                (prev_current_assets - prev_current_liabilities)
            )
        else:
            nwc_change = current_assets - current_liabilities

        # Get beta and market cap from overview
        beta = safe_float(overview.get('Beta'), 1.0)
        market_cap = safe_float(overview.get('MarketCapitalization'), 0)

        # Calculate ROIC: NOPAT / Invested Capital
        tax_rate = 0.21  # Default marginal tax rate
        tax_expense = safe_float(latest_income.get('incomeTaxExpense'), 0)
        pre_tax_income = safe_float(latest_income.get('incomeBeforeTax'), 0)
        if pre_tax_income > 0 and tax_expense >= 0:
            tax_rate = tax_expense / pre_tax_income

        invested_capital = equity + total_debt - cash
        roic = None
        if invested_capital > 0:
            nopat = operating_income * (1 - tax_rate)
            roic = nopat / invested_capital

        return {
            'revenue': revenue,
            'operating_income': operating_income,
            'total_debt': total_debt,
            'cash': cash,
            'equity': equity,
            'market_cap': market_cap,
            'beta': beta,
            'capex': capex,
            'nwc_change': nwc_change,
            'operating_cashflow': operating_cashflow,
            'total_assets': total_assets,
            'roic': roic,
            'invested_capital': invested_capital,
        }

    @staticmethod
    def format_metrics_table(metrics: CompanyMetrics) -> str:
        """
        Format metrics into a readable table

        Args:
            metrics: CompanyMetrics object

        Returns:
            Formatted string table
        """

        def format_value(value, is_percent=False, is_currency=False):
            """Format value for display"""
            if value is None:
                return "N/A"
            if is_percent:
                return f"{value*100:.2f}%"
            if is_currency:
                if value >= 1e9:
                    return f"${value/1e9:.2f}B"
                elif value >= 1e6:
                    return f"${value/1e6:.2f}M"
                else:
                    return f"${value:,.2f}"
            return f"{value:.2f}"

        table = f"""
Financial Metrics
{'=' * 60}

VALUATION METRICS
  Market Cap:        {format_value(metrics.market_cap, is_currency=True)}
  P/E Ratio:         {format_value(metrics.pe_ratio)}
  PEG Ratio:         {format_value(metrics.peg_ratio)}
  Price to Book:     {format_value(metrics.price_to_book)}
  Price to Sales:    {format_value(metrics.price_to_sales)}
  EV/EBITDA:         {format_value(metrics.ev_to_ebitda)}

PROFITABILITY
  Profit Margin:     {format_value(metrics.profit_margin, is_percent=True)}
  Operating Margin:  {format_value(metrics.operating_margin, is_percent=True)}
  ROIC:              {format_value(metrics.roic, is_percent=True)}
  ROE:               {format_value(metrics.return_on_equity, is_percent=True)}
  ROA:               {format_value(metrics.return_on_assets, is_percent=True)}

GROWTH
  Revenue Growth:    {format_value(metrics.revenue_growth, is_percent=True)}
  Earnings Growth:   {format_value(metrics.earnings_growth, is_percent=True)}

FINANCIAL HEALTH
  Debt to Equity:    {format_value(metrics.debt_to_equity)}
  Current Ratio:     {format_value(metrics.current_ratio)}

PER SHARE
  EPS:               {format_value(metrics.eps, is_currency=True)}
  Book Value:        {format_value(metrics.book_value_per_share, is_currency=True)}
  FCF per Share:     {format_value(metrics.free_cash_flow_per_share, is_currency=True)}

DIVIDENDS
  Dividend Yield:    {format_value(metrics.dividend_yield, is_percent=True)}
  Payout Ratio:      {format_value(metrics.payout_ratio, is_percent=True)}
"""
        return table

    @staticmethod
    def calculate_growth_rate(values: List[float], years: int = None) -> Optional[float]:
        """
        Calculate compound annual growth rate (CAGR)

        Args:
            values: List of values in chronological order (oldest first)
            years: Number of years (default: len(values) - 1)

        Returns:
            CAGR as decimal, or None if calculation not possible
        """
        if len(values) < 2 or values[0] <= 0 or values[-1] <= 0:
            return None

        years = years or (len(values) - 1)
        if years <= 0:
            return None

        cagr = (values[-1] / values[0]) ** (1 / years) - 1
        return cagr

    @staticmethod
    def calculate_free_cash_flow(
        operating_cashflow: float,
        capex: float
    ) -> float:
        """
        Calculate Free Cash Flow

        FCF = Operating Cash Flow - Capital Expenditures

        Args:
            operating_cashflow: Cash from operations
            capex: Capital expenditures

        Returns:
            Free cash flow
        """
        return operating_cashflow - abs(capex)

    @staticmethod
    def calculate_quarterly_growth(quarterly_data: list) -> str:
        """
        Calculate and format quarterly revenue growth rates (QoQ and YoY)

        Args:
            quarterly_data: List of quarterly income statements (most recent first)
                           Each item should have 'fiscalDateEnding' and 'totalRevenue'

        Returns:
            Formatted string with quarterly growth analysis table
        """
        if not quarterly_data or len(quarterly_data) < 2:
            return "Insufficient quarterly data for growth analysis"

        # Parse and sort quarters (most recent first)
        quarters = []
        for q in quarterly_data[:8]:  # Limit to 8 quarters (2 years)
            revenue = safe_float(q.get('totalRevenue'))
            if revenue is not None and revenue > 0:
                quarters.append({
                    'date': q.get('fiscalDateEnding'),
                    'revenue': revenue
                })

        if len(quarters) < 2:
            return "Insufficient valid revenue data for growth analysis"

        # Calculate growth rates
        output = "\n" + "=" * 100 + "\n"
        output += "QUARTERLY REVENUE GROWTH ANALYSIS (Last 8 Quarters)\n"
        output += "=" * 100 + "\n\n"

        output += f"{'Quarter':>12} | {'Revenue':>12} | {'QoQ Growth':>12} | {'YoY Growth':>12} | {'Trend':>15}\n"
        output += "-" * 100 + "\n"

        for i, quarter in enumerate(quarters):
            revenue_b = quarter['revenue'] / 1e9

            # Calculate QoQ (Quarter over Quarter) - compare to previous quarter
            qoq_growth = None
            qoq_str = "N/A"
            if i < len(quarters) - 1:
                prev_revenue = quarters[i + 1]['revenue']
                if prev_revenue > 0:
                    qoq_growth = ((quarter['revenue'] - prev_revenue) / prev_revenue) * 100
                    qoq_str = f"{qoq_growth:+.1f}%"

            # Calculate YoY (Year over Year) - compare to same quarter last year (4 quarters ago)
            yoy_growth = None
            yoy_str = "N/A"
            if i + 4 < len(quarters):
                year_ago_revenue = quarters[i + 4]['revenue']
                if year_ago_revenue > 0:
                    yoy_growth = ((quarter['revenue'] - year_ago_revenue) / year_ago_revenue) * 100
                    yoy_str = f"{yoy_growth:+.1f}%"

            # Determine trend
            trend = ""
            if yoy_growth is not None:
                if yoy_growth > 15:
                    trend = "🟢 Accelerating"
                elif yoy_growth > 5:
                    trend = "🟢 Strong"
                elif yoy_growth > 0:
                    trend = "🟡 Moderate"
                elif yoy_growth > -5:
                    trend = "🟡 Slowing"
                else:
                    trend = "🔴 Declining"

            output += f"{quarter['date']:>12} | ${revenue_b:>10.2f}B | {qoq_str:>12} | {yoy_str:>12} | {trend:>15}\n"

        output += "\n"

        # Calculate summary statistics
        if len(quarters) >= 4:
            recent_2q_yoy = []
            for i in range(min(2, len(quarters))):
                if i + 4 < len(quarters):
                    year_ago_revenue = quarters[i + 4]['revenue']
                    if year_ago_revenue > 0:
                        yoy = ((quarters[i]['revenue'] - year_ago_revenue) / year_ago_revenue) * 100
                        recent_2q_yoy.append(yoy)

            if recent_2q_yoy:
                avg_recent_yoy = sum(recent_2q_yoy) / len(recent_2q_yoy)
                output += f"Recent Average YoY Growth (last 2 quarters): {avg_recent_yoy:+.1f}%\n"

        # Add growth trend analysis
        if len(quarters) >= 8:
            old_yoy = []
            for i in range(4, min(6, len(quarters))):
                if i + 4 < len(quarters):
                    year_ago_revenue = quarters[i + 4]['revenue']
                    if year_ago_revenue > 0:
                        yoy = ((quarters[i]['revenue'] - year_ago_revenue) / year_ago_revenue) * 100
                        old_yoy.append(yoy)

            if recent_2q_yoy and old_yoy:
                avg_old_yoy = sum(old_yoy) / len(old_yoy)
                avg_recent_yoy = sum(recent_2q_yoy) / len(recent_2q_yoy)

                if avg_recent_yoy > avg_old_yoy + 2:
                    output += "Growth Trend: 📈 ACCELERATING (recent growth exceeding historical trend)\n"
                elif avg_recent_yoy < avg_old_yoy - 2:
                    output += "Growth Trend: 📉 DECELERATING (recent growth below historical trend)\n"
                else:
                    output += "Growth Trend: ➡️  STABLE (consistent growth trajectory)\n"

        output += "\n" + "=" * 100 + "\n\n"

        return output
