"""
Financial Metrics Calculator

Utilities for calculating and formatting financial metrics from company data.
"""

from typing import Dict, List, Optional
from dataclasses import dataclass
from .utils import safe_float


# Damodaran's synthetic credit rating tables
# Source: https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/ratings.html
# Updated: January 2026 (large firms), January 2017 (small firms)
# Format: (min_coverage, rating, spread)
# Sorted descending by coverage threshold — first match wins.

SYNTHETIC_RATING_TABLE_LARGE = [
    (8.50, "Aaa/AAA", 0.0040),
    (6.50, "Aa2/AA",  0.0055),
    (5.50, "A1/A+",   0.0070),
    (4.25, "A2/A",    0.0078),
    (3.00, "A3/A-",   0.0089),
    (2.50, "Baa2/BBB", 0.0111),
    (2.25, "Ba1/BB+", 0.0138),
    (2.00, "Ba2/BB",  0.0184),
    (1.75, "B1/B+",   0.0275),
    (1.50, "B2/B",    0.0321),
    (1.25, "B3/B-",   0.0509),
    (0.80, "Caa/CCC", 0.0885),
    (0.65, "Ca2/CC",  0.1261),
    (0.20, "C2/C",    0.1600),
]
SYNTHETIC_RATING_DEFAULT_LARGE = ("D2/D", 0.1900)

SYNTHETIC_RATING_TABLE_SMALL = [
    (12.50, "Aaa/AAA", 0.0060),
    (9.50,  "Aa2/AA",  0.0080),
    (7.50,  "A1/A+",   0.0100),
    (6.00,  "A2/A",    0.0110),
    (4.50,  "A3/A-",   0.0125),
    (4.00,  "Baa2/BBB", 0.0160),
    (3.50,  "Ba1/BB+", 0.0250),
    (3.00,  "Ba2/BB",  0.0300),
    (2.50,  "B1/B+",   0.0375),
    (2.00,  "B2/B",    0.0450),
    (1.50,  "B3/B-",   0.0550),
    (1.25,  "Caa/CCC", 0.0650),
    (0.80,  "Ca2/CC",  0.0800),
    (0.50,  "C2/C",    0.1050),
]
SYNTHETIC_RATING_DEFAULT_SMALL = ("D2/D", 0.1400)

SMALL_FIRM_MARKET_CAP_THRESHOLD = 5_000_000_000  # $5B

# Actual credit rating to default spread mapping (large-firm spreads).
# Agency ratings already incorporate firm size, so large-firm spreads are
# appropriate regardless of market cap. Sub-notches within a Damodaran
# bucket map to the same spread.
RATING_TO_SPREAD = {
    # S&P notation
    "AAA": 0.0040,
    "AA+": 0.0055, "AA": 0.0055, "AA-": 0.0055,
    "A+": 0.0070,  "A": 0.0078,  "A-": 0.0089,
    "BBB+": 0.0111, "BBB": 0.0111, "BBB-": 0.0111,
    "BB+": 0.0138, "BB": 0.0184, "BB-": 0.0184,
    "B+": 0.0275,  "B": 0.0321,  "B-": 0.0509,
    "CCC+": 0.0885, "CCC": 0.0885, "CCC-": 0.0885,
    "CC": 0.1261, "C": 0.1600, "D": 0.1900,
    # Moody's notation
    "Aaa": 0.0040,
    "Aa1": 0.0055, "Aa2": 0.0055, "Aa3": 0.0055,
    "A1": 0.0070,  "A2": 0.0078,  "A3": 0.0089,
    "Baa1": 0.0111, "Baa2": 0.0111, "Baa3": 0.0111,
    "Ba1": 0.0138, "Ba2": 0.0184, "Ba3": 0.0184,
    "B1": 0.0275,  "B2": 0.0321,  "B3": 0.0509,
    "Caa1": 0.0885, "Caa2": 0.0885, "Caa3": 0.0885,
    "Ca": 0.1261,
}


def get_synthetic_rating(coverage_ratio: float, market_cap: float) -> dict:
    """
    Map interest coverage ratio to synthetic credit rating and default spread.

    Uses Damodaran's lookup tables, auto-selecting large-firm or small-firm
    table based on market cap (threshold: $5B).

    Args:
        coverage_ratio: EBIT / Interest Expense
        market_cap: Company market capitalization in dollars

    Returns:
        Dict with 'rating', 'default_spread', 'coverage_ratio', 'firm_size'
    """
    if market_cap >= SMALL_FIRM_MARKET_CAP_THRESHOLD:
        table = SYNTHETIC_RATING_TABLE_LARGE
        default = SYNTHETIC_RATING_DEFAULT_LARGE
        firm_size = "large"
    else:
        table = SYNTHETIC_RATING_TABLE_SMALL
        default = SYNTHETIC_RATING_DEFAULT_SMALL
        firm_size = "small"

    for min_coverage, rating, spread in table:
        if coverage_ratio >= min_coverage:
            return {
                "rating": rating,
                "default_spread": spread,
                "coverage_ratio": coverage_ratio,
                "firm_size": firm_size,
            }

    rating, spread = default
    return {
        "rating": rating,
        "default_spread": spread,
        "coverage_ratio": coverage_ratio,
        "firm_size": firm_size,
    }


def get_spread_for_rating(rating: str) -> Optional[float]:
    """
    Map an actual credit rating to its default spread.

    Accepts both S&P (AAA, AA+, etc.) and Moody's (Aaa, Aa1, etc.) notation.
    Uses the large-firm spread table — agency ratings already incorporate
    firm size, so applying small-firm spreads would double-count the size penalty.

    Args:
        rating: Credit rating string (e.g., "AA+", "Aa2")

    Returns:
        Default spread as a decimal (e.g., 0.0055), or None if rating not recognized
    """
    return RATING_TO_SPREAD.get(rating)


# Damodaran's R&D amortizable life by sector/industry
# Source: R&DConv.xls lookup table (January 2025 update)
# Maps Alpha Vantage sector/industry strings to amortization periods

_RD_AMORTIZABLE_LIFE_BY_SECTOR = {
    "technology": 3,
    "communication services": 3,
    "consumer cyclical": 3,
    "consumer defensive": 3,
    "financial services": 2,
    "healthcare": 10,
    "industrials": 10,
    "energy": 5,
    "basic materials": 5,
    "real estate": 3,
    "utilities": 10,
}

# Industry-level overrides (substring match, case-insensitive)
_RD_AMORTIZABLE_LIFE_INDUSTRY_OVERRIDES = [
    ("semiconductor", 5),
    ("health information", 3),
    ("medical device", 5),
    ("medical instrument", 5),
    ("electronic", 5),
    ("computer hardware", 5),
    ("scientific instrument", 5),
    ("chemical", 10),
]

_RD_AMORTIZABLE_LIFE_DEFAULT = 3


def get_rd_amortizable_life(sector: Optional[str], industry: Optional[str]) -> int:
    """
    Map Alpha Vantage sector/industry to Damodaran's R&D amortizable life.

    Uses sector as the primary key with industry-level overrides for cases
    where the sector default is wrong (e.g., semiconductors within Technology).

    Args:
        sector: Company sector from Alpha Vantage overview (e.g., "Technology")
        industry: Company industry from Alpha Vantage overview (e.g., "Semiconductors")

    Returns:
        Amortizable life in years (2, 3, 5, or 10)
    """
    industry_lower = (industry or "").lower()
    for keyword, life in _RD_AMORTIZABLE_LIFE_INDUSTRY_OVERRIDES:
        if keyword in industry_lower:
            return life

    sector_lower = (sector or "").lower()
    return _RD_AMORTIZABLE_LIFE_BY_SECTOR.get(sector_lower, _RD_AMORTIZABLE_LIFE_DEFAULT)


def calculate_rd_capitalization(
    annual_reports: List[Dict],
    amortizable_life: int,
) -> Optional[Dict]:
    """
    Capitalize R&D expenses using Damodaran's methodology.

    Converts R&D from an operating expense to a capital expense by building
    a research asset (unamortized R&D) and computing the current-year
    amortization. Uses pre-tax R&D (verified from Damodaran's R&DConv.xls).

    The adjusted_nopat_delta (= current R&D - amortization) is pre-tax.
    The caller adds it to EBIT(1-t) to get adjusted NOPAT — this works
    because R&D remains fully tax-deductible, so the pre-tax amounts
    naturally capture the "ignored tax benefit."

    FCF is unchanged by this adjustment. What changes: NOPAT, invested
    capital, and ROIC — which flow into terminal reinvestment (g/ROIC),
    fundamental growth checks, and value-of-growth checks.

    Args:
        annual_reports: Annual income statements, most recent first.
            Each must have 'researchAndDevelopment' and 'fiscalDateEnding'.
        amortizable_life: Years over which to amortize R&D (from industry lookup).

    Returns:
        Dict with research_asset, amortization, current_rd, adjusted_nopat_delta,
        rd_expenses, amortizable_life. Returns None if no R&D data available.
    """
    if not annual_reports:
        return None

    # Extract R&D expenses (most recent first)
    rd_expenses = []
    for report in annual_reports:
        rd = safe_float(report.get("researchAndDevelopment"))
        if rd is not None and rd > 0:
            year = report.get("fiscalDateEnding", "")
            rd_expenses.append((year, rd))

    if not rd_expenses:
        return None

    current_rd = rd_expenses[0][1]

    # Build research asset and compute amortization
    # Per Damodaran's R&DConv.xls:
    # - Current year (i=0): unamortized = N/N = 1.0, amortization = 0
    # - Year -1 (i=1): unamortized = (N-1)/N, amortization = R&D/N
    # - Year -(N-1): unamortized = 1/N, amortization = R&D/N
    # - Year -N: unamortized = 0, amortization = R&D/N (final year out)
    n = amortizable_life
    research_asset = 0.0
    amortization = 0.0

    for i, (year, rd) in enumerate(rd_expenses):
        if i >= n:
            break  # Beyond amortizable window
        unamortized_fraction = (n - i) / n
        research_asset += rd * unamortized_fraction
        if i > 0:  # Current year has zero amortization
            amortization += rd / n

    # Year -N contributes to amortization but has 0 in asset
    if len(rd_expenses) > n:
        amortization += rd_expenses[n][1] / n

    adjusted_nopat_delta = current_rd - amortization

    return {
        "research_asset": research_asset,
        "amortization": amortization,
        "current_rd": current_rd,
        "adjusted_nopat_delta": adjusted_nopat_delta,
        "rd_expenses": rd_expenses[:n],
        "amortizable_life": n,
    }


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
        overview: Dict,
        income_annual: Optional[List[Dict]] = None,
    ) -> Dict:
        """
        Extract and calculate inputs needed for DCF valuation

        Args:
            income_statement: Annual income statements
            balance_sheet: Annual balance sheets
            cash_flow: Annual cash flow statements
            overview: Company overview data
            income_annual: Optional annual income statements for R&D capitalization.
                When provided, computes adjusted ROIC using Damodaran's R&D
                capitalization methodology. Backward compatible — callers that omit
                this parameter receive None for all R&D-adjusted fields.

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
        interest_expense = safe_float(latest_income.get('interestExpense'))

        # Try to get total debt from various possible field names
        total_debt = safe_float(latest_balance.get('shortLongTermDebtTotal'), 0)

        # If not available, try calculating from individual components
        if total_debt == 0:
            total_debt = (
                safe_float(latest_balance.get('shortTermDebt'), 0) +
                safe_float(latest_balance.get('longTermDebt'), 0)
            )

        cash = safe_float(latest_balance.get('cashAndCashEquivalentsAtCarryingValue'), 0)
        short_term_investments = safe_float(latest_balance.get('shortTermInvestments'), 0)
        long_term_investments = safe_float(latest_balance.get('longTermInvestments'), 0)
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

        invested_capital = equity + total_debt - cash - short_term_investments - long_term_investments
        roic = None
        if invested_capital > 0:
            nopat = operating_income * (1 - tax_rate)
            roic = nopat / invested_capital

        # Interest coverage and synthetic credit rating
        interest_coverage = None
        synthetic_rating = None
        synthetic_spread = None
        if interest_expense is not None and interest_expense > 0:
            interest_coverage = operating_income / interest_expense
            synthetic = get_synthetic_rating(interest_coverage, market_cap)
            synthetic_rating = synthetic['rating']
            synthetic_spread = synthetic['default_spread']
        elif interest_expense == 0:
            # Debt-free company — infinite coverage → best rating
            interest_coverage = float('inf')
            synthetic = get_synthetic_rating(float('inf'), market_cap)
            synthetic_rating = synthetic['rating']
            synthetic_spread = synthetic['default_spread']
        # else: interest_expense is None (missing data) → all stay None

        # R&D capitalization (Damodaran methodology)
        adjusted_roic = None
        adjusted_invested_capital = None
        adjusted_operating_margin = None
        adjusted_sales_to_capital = None
        research_asset = None
        rd_amortization = None
        current_rd = None
        rd_amortizable_life = None

        if income_annual:
            sector = overview.get("Sector")
            industry = overview.get("Industry")
            rd_life = get_rd_amortizable_life(sector, industry)
            rd_cap = calculate_rd_capitalization(income_annual, rd_life)

            if rd_cap and rd_cap["research_asset"] > 0:
                research_asset = rd_cap["research_asset"]
                rd_amortization = rd_cap["amortization"]
                current_rd = rd_cap["current_rd"]
                rd_amortizable_life = rd_life

                adjusted_ic = invested_capital + research_asset
                if adjusted_ic > 0:
                    nopat_raw = operating_income * (1 - tax_rate)
                    adjusted_nopat = nopat_raw + rd_cap["adjusted_nopat_delta"]
                    adjusted_roic = adjusted_nopat / adjusted_ic
                    adjusted_invested_capital = adjusted_ic

                    # Adjusted operating margin: pre-tax economic margin
                    # = (EBIT + R&D - Amort) / Revenue, where (R&D - Amort) = adjusted_nopat_delta
                    adjusted_operating_income = operating_income + rd_cap["adjusted_nopat_delta"]
                    if revenue > 0:
                        adjusted_operating_margin = adjusted_operating_income / revenue

                    # Adjusted sales-to-capital: revenue per unit of adjusted capital
                    adjusted_sales_to_capital = revenue / adjusted_ic

        return {
            'revenue': revenue,
            'operating_income': operating_income,
            'total_debt': total_debt,
            'cash': cash,
            'short_term_investments': short_term_investments,
            'long_term_investments': long_term_investments,
            'equity': equity,
            'market_cap': market_cap,
            'beta': beta,
            'capex': capex,
            'nwc_change': nwc_change,
            'operating_cashflow': operating_cashflow,
            'total_assets': total_assets,
            'roic': roic,
            'invested_capital': invested_capital,
            'interest_expense': interest_expense,
            'interest_coverage': interest_coverage,
            'synthetic_rating': synthetic_rating,
            'synthetic_spread': synthetic_spread,
            'adjusted_roic': adjusted_roic,
            'adjusted_invested_capital': adjusted_invested_capital,
            'adjusted_operating_margin': adjusted_operating_margin,
            'adjusted_sales_to_capital': adjusted_sales_to_capital,
            'research_asset': research_asset,
            'rd_amortization': rd_amortization,
            'current_rd': current_rd,
            'rd_amortizable_life': rd_amortizable_life,
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
