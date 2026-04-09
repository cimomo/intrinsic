"""
DCF (Discounted Cash Flow) Valuation Model

This module provides a comprehensive DCF valuation implementation for stocks.
It calculates the intrinsic value of a company based on projected free cash flows.
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class DCFAssumptions:
    """Configurable assumptions for DCF model"""

    # Growth rates
    revenue_growth_rate: float = 0.10  # 10% annual revenue growth
    terminal_growth_rate: Optional[float] = None  # Defaults to risk_free_rate if None

    # Margin assumptions
    operating_margin: Optional[float] = None  # Use historical if None
    target_operating_margin: Optional[float] = None  # Converge to this margin over projection period (None = no convergence)
    tax_rate: float = 0.21  # Marginal corporate tax rate (used for terminal value and convergence target)
    effective_tax_rate: Optional[float] = None  # Current effective tax rate (None = use tax_rate for all years)

    # WACC components
    risk_free_rate: float = 0.045  # 10-year Treasury yield
    market_risk_premium: float = 0.05  # Historical equity risk premium
    beta: Optional[float] = None  # Use company beta if None

    # Capital structure
    debt_to_equity_ratio: Optional[float] = None  # Use company D/E if None
    cost_of_debt: float = 0.05  # Pre-tax; calibrate replaces with rating-based estimate

    # Projection period
    projection_years: int = 10  # Years to project FCF (includes 5-year tapering period)

    # Capital efficiency (replaces capex_percent and nwc_percent)
    sales_to_capital_ratio: Optional[float] = None  # Revenue generated per dollar of capital invested

    # Terminal ROIC — determines reinvestment needed to sustain terminal growth
    # None = defaults to WACC (no excess returns in perpetuity, per Damodaran)
    terminal_roic: Optional[float] = None

    # Cost of capital override — manual hurdle rate that bypasses WACC computation
    # None = compute WACC from components (CAPM + cost of debt)
    cost_of_capital: Optional[float] = None

    def __post_init__(self):
        """Set terminal growth rate to risk-free rate if not explicitly provided"""
        if self.terminal_growth_rate is None:
            self.terminal_growth_rate = self.risk_free_rate


class DCFModel:
    """
    Discounted Cash Flow Valuation Model

    Calculates intrinsic stock value using:
    1. Free Cash Flow projections
    2. Terminal value (Gordon Growth Model)
    3. WACC discount rate
    4. Present value calculation
    """

    def __init__(self, assumptions: Optional[DCFAssumptions] = None):
        """
        Initialize DCF model with assumptions

        Args:
            assumptions: DCFAssumptions object with model parameters
        """
        self.assumptions = assumptions or DCFAssumptions()
        self.results: Dict = {}

    def calculate_wacc(
        self,
        beta: float,
        debt_to_equity: float,
        market_cap: float,
        total_debt: float,
        tax_rate: Optional[float] = None
    ) -> float:
        """
        Calculate Weighted Average Cost of Capital (WACC)

        WACC = (E/V) * Re + (D/V) * Rd * (1 - Tc)
        Where:
            E = Market value of equity
            D = Market value of debt
            V = E + D
            Re = Cost of equity (via CAPM)
            Rd = Cost of debt
            Tc = Corporate tax rate

        If cost_of_capital is set on assumptions, returns that directly
        (manual hurdle rate bypasses WACC computation).

        Args:
            beta: Stock beta (volatility vs market)
            debt_to_equity: Debt-to-equity ratio
            market_cap: Market capitalization
            total_debt: Total debt
            tax_rate: Tax rate for debt shield (defaults to marginal if None)

        Returns:
            WACC as decimal (e.g., 0.10 for 10%)
        """
        if self.assumptions.cost_of_capital is not None:
            return self.assumptions.cost_of_capital

        if tax_rate is None:
            tax_rate = self.assumptions.tax_rate

        # Cost of equity using CAPM: Re = Rf + β(Rm - Rf)
        cost_of_equity = (
            self.assumptions.risk_free_rate +
            beta * self.assumptions.market_risk_premium
        )

        # Total firm value
        equity_value = market_cap
        debt_value = total_debt
        total_value = equity_value + debt_value

        # Weights
        equity_weight = equity_value / total_value if total_value > 0 else 1
        debt_weight = debt_value / total_value if total_value > 0 else 0

        # WACC calculation
        wacc = (
            equity_weight * cost_of_equity +
            debt_weight * self.assumptions.cost_of_debt * (1 - tax_rate)
        )

        return wacc

    def _get_margin_for_year(self, year: int, years: int, base_margin: float) -> float:
        """
        Get operating margin for a given projection year.

        If target_operating_margin is set, linearly converges from base_margin
        to target over the projection period. Otherwise returns base_margin.

        Args:
            year: Projection year (1-indexed)
            years: Total projection years
            base_margin: Starting operating margin

        Returns:
            Operating margin for the year
        """
        target = self.assumptions.target_operating_margin
        if target is None or years <= 1:
            return base_margin
        # Linear convergence: year 1 starts moving, year N reaches target
        progress = year / years
        return base_margin + (target - base_margin) * progress

    def _get_tax_rate_for_year(self, year: int, years: int) -> float:
        """
        Get tax rate for a given projection year.

        If effective_tax_rate is set, linearly transitions from effective
        to marginal (tax_rate) over the projection period. Terminal value
        always uses marginal. If effective_tax_rate is None, returns
        tax_rate for all years.

        Args:
            year: Projection year (1-indexed)
            years: Total projection years

        Returns:
            Tax rate for the year
        """
        if self.assumptions.effective_tax_rate is None or years <= 1:
            return self.assumptions.tax_rate
        progress = year / years
        return self.assumptions.effective_tax_rate + (self.assumptions.tax_rate - self.assumptions.effective_tax_rate) * progress

    def project_free_cash_flows(
        self,
        base_revenue: float,
        operating_margin: float,
        sales_to_capital: float,
        years: int
    ) -> Tuple[List[float], List[float], float]:
        """
        Project future free cash flows using sales-to-capital approach

        FCF = NOPAT - Reinvestment
        Where:
            NOPAT = Revenue * Operating Margin * (1 - Tax Rate)
            Reinvestment = Revenue Growth / Sales-to-Capital Ratio

        Growth Rate Pattern:
            Years 1-5: Use full revenue_growth_rate from assumptions
            Years 6-10: Taper down to terminal_growth_rate linearly

        Margin Convergence:
            If target_operating_margin is set, margin linearly converges
            from current operating_margin to target over the projection period.

        Args:
            base_revenue: Starting revenue (most recent year)
            operating_margin: Operating margin as decimal (starting margin)
            sales_to_capital: Revenue generated per dollar of capital
            years: Number of years to project (typically 10)

        Returns:
            Tuple of (projected FCF list, margin per year list, final year revenue)
        """
        fcf_projections = []
        margin_projections = []
        revenue = base_revenue

        # Calculate the difference between initial and terminal growth rates
        growth_rate_diff = self.assumptions.revenue_growth_rate - self.assumptions.terminal_growth_rate

        for year in range(1, years + 1):
            # Determine growth rate for this year
            if year <= 5:
                growth_rate = self.assumptions.revenue_growth_rate
            else:
                tapering_factor = (year - 5) / 5
                growth_rate = self.assumptions.revenue_growth_rate - (growth_rate_diff * tapering_factor)

            # Determine operating margin for this year
            year_margin = self._get_margin_for_year(year, years, operating_margin)
            margin_projections.append(year_margin)

            # Calculate revenue growth in absolute dollars
            revenue_growth = revenue * growth_rate

            # Project revenue to next year
            revenue *= (1 + growth_rate)

            # Calculate NOPAT (Net Operating Profit After Tax)
            year_tax = self._get_tax_rate_for_year(year, years)
            nopat = revenue * year_margin * (1 - year_tax)

            # Calculate reinvestment needed to support growth
            reinvestment = revenue_growth / sales_to_capital if sales_to_capital > 0 else 0

            # Free Cash Flow
            fcf = nopat - reinvestment
            fcf_projections.append(fcf)

        return fcf_projections, margin_projections, revenue

    def calculate_terminal_value(
        self,
        final_year_revenue: float,
        final_year_margin: float,
        wacc: float
    ) -> Tuple[float, Dict]:
        """
        Calculate terminal value using Damodaran's reinvestment-based approach.

        Terminal reinvestment is derived from g/ROIC rather than naively growing
        the final year's FCF. This ensures the terminal period's reinvestment
        is consistent with sustainable growth at a given return on capital.

        Terminal ROIC defaults to WACC (no excess returns in perpetuity).
        Override via assumptions.terminal_roic for wide-moat companies.

        Args:
            final_year_revenue: Revenue in the final projection year
            final_year_margin: Operating margin in the final projection year
            wacc: Weighted average cost of capital

        Returns:
            Tuple of (terminal_value, details_dict) where details_dict contains
            terminal_nopat, terminal_fcf, terminal_roic, terminal_reinvestment_rate
        """
        g = self.assumptions.terminal_growth_rate
        tax = self.assumptions.tax_rate

        # Guard: WACC must exceed terminal growth rate for Gordon Growth Model
        spread = wacc - g
        if spread <= 0:
            raise ValueError(
                f"WACC ({wacc*100:.2f}%) must be greater than terminal growth rate "
                f"({g*100:.2f}%). "
                f"Either increase WACC (higher beta, more debt) or lower the terminal growth rate."
            )

        # Terminal ROIC: use explicit assumption, or default to WACC
        terminal_roic = self.assumptions.terminal_roic if self.assumptions.terminal_roic is not None else wacc

        # Guard: terminal ROIC must exceed terminal growth rate
        # Otherwise reinvestment rate > 100% and terminal FCF is negative in perpetuity
        if terminal_roic <= 0 or terminal_roic < g:
            raise ValueError(
                f"Terminal ROIC ({terminal_roic*100:.2f}%) must be positive and >= terminal growth rate "
                f"({g*100:.2f}%). A lower ROIC implies reinvestment exceeding 100% of NOPAT."
            )

        # Year n+1 revenue and NOPAT
        terminal_revenue = final_year_revenue * (1 + g)
        terminal_nopat = terminal_revenue * final_year_margin * (1 - tax)

        # Terminal reinvestment rate = g / ROIC
        terminal_reinvestment_rate = g / terminal_roic

        # Terminal FCF = NOPAT * (1 - g/ROIC)
        terminal_fcf = terminal_nopat * (1 - terminal_reinvestment_rate)

        # Gordon Growth Model
        terminal_value = terminal_fcf / spread

        details = {
            'terminal_nopat': terminal_nopat,
            'terminal_fcf': terminal_fcf,
            'terminal_roic': terminal_roic,
            'terminal_reinvestment_rate': terminal_reinvestment_rate,
        }

        return terminal_value, details

    def calculate_present_value(
        self,
        cash_flows: List[float],
        discount_rate: float
    ) -> float:
        """
        Calculate present value of cash flows using a flat discount rate.

        Note: calculate_fair_value uses cumulative year-specific discounting
        internally (to support year-varying WACC). This method is retained
        for flat-rate convenience and testing.

        PV = Σ(CF_t / (1 + r)^t)

        Args:
            cash_flows: List of future cash flows
            discount_rate: Discount rate (flat, same for all years)

        Returns:
            Present value of all cash flows
        """
        pv = 0
        for year, cf in enumerate(cash_flows, start=1):
            pv += cf / ((1 + discount_rate) ** year)
        return pv

    def calculate_fair_value(
        self,
        financial_data: Dict,
        shares_outstanding: float,
        current_price: float,
        verbose: bool = True
    ) -> Dict:
        """
        Calculate fair value per share using DCF analysis

        Args:
            financial_data: Dictionary containing:
                - revenue: Most recent annual revenue
                - operating_income: Operating income
                - total_debt: Total debt
                - cash: Cash and cash equivalents
                - short_term_investments: Short-term marketable securities (optional)
                - long_term_investments: Long-term investments (optional)
                - equity: Book value of equity (optional, uses market_cap if not provided)
                - market_cap: Market capitalization
                - beta: Stock beta (optional, defaults to 1.0)
            shares_outstanding: Number of shares outstanding
            current_price: Current stock price
            verbose: Whether to include detailed breakdown

        Returns:
            Dictionary with valuation results including:
                - fair_value: Fair value per share
                - current_price: Current market price
                - upside_percent: Percentage upside/downside
                - wacc: Weighted average cost of capital
                - terminal_value: Terminal value
                - enterprise_value: Total enterprise value
                - sales_to_capital: Sales-to-capital ratio used
        """
        # Validate required fields
        required_fields = ['revenue', 'operating_income', 'market_cap']
        missing = [f for f in required_fields if f not in financial_data or financial_data[f] is None]
        if missing:
            raise ValueError(f"financial_data missing required fields: {', '.join(missing)}")

        if shares_outstanding is None or shares_outstanding <= 0:
            raise ValueError(f"shares_outstanding must be positive, got {shares_outstanding}")

        if current_price is None or current_price <= 0:
            raise ValueError(f"current_price must be positive, got {current_price}")

        # Extract financial data
        revenue = financial_data['revenue']
        operating_income = financial_data['operating_income']
        total_debt = financial_data.get('total_debt', 0)
        market_cap = financial_data['market_cap']
        beta = self.assumptions.beta if self.assumptions.beta is not None else financial_data.get('beta', 1.0)

        if revenue <= 0:
            raise ValueError(f"revenue must be positive, got {revenue}")
        if market_cap <= 0:
            raise ValueError(f"market_cap must be positive, got {market_cap}")

        # Calculate margins and ratios
        operating_margin = (
            self.assumptions.operating_margin or
            (operating_income / revenue if revenue > 0 else 0.15)
        )

        # Calculate sales-to-capital ratio
        # Sales-to-Capital = Revenue / Invested Capital
        # Where Invested Capital = Equity + Debt - Cash - Non-operating Investments
        if self.assumptions.sales_to_capital_ratio is not None:
            sales_to_capital = self.assumptions.sales_to_capital_ratio
        else:
            # Calculate invested capital from balance sheet
            equity = financial_data.get('equity', market_cap)  # Book value of equity
            cash = financial_data.get('cash', 0)
            sti = financial_data.get('short_term_investments', 0)
            lti = financial_data.get('long_term_investments', 0)
            invested_capital = equity + total_debt - cash - sti - lti

            # Calculate sales-to-capital ratio
            if invested_capital > 0:
                sales_to_capital = revenue / invested_capital
            else:
                # Default for typical companies
                # Typical range: 0.5-3.0 depending on industry
                sales_to_capital = 1.5

        # Calculate WACC
        debt_to_equity = total_debt / market_cap if market_cap > 0 else 0
        years = self.assumptions.projection_years

        # Compute per-year WACC when effective_tax_rate causes the tax rate
        # (and thus the debt tax shield) to vary over the projection period.
        # Terminal WACC always uses the marginal rate.
        wacc_per_year = []
        for year in range(1, years + 1):
            year_tax = self._get_tax_rate_for_year(year, years)
            wacc_per_year.append(self.calculate_wacc(beta, debt_to_equity, market_cap, total_debt, tax_rate=year_tax))
        terminal_wacc = self.calculate_wacc(beta, debt_to_equity, market_cap, total_debt, tax_rate=self.assumptions.tax_rate)

        # Use terminal WACC as the reported WACC (stable-state cost of capital)
        wacc = terminal_wacc

        # Project free cash flows
        fcf_projections, margin_projections, final_year_revenue = self.project_free_cash_flows(
            base_revenue=revenue,
            operating_margin=operating_margin,
            sales_to_capital=sales_to_capital,
            years=years
        )

        # Calculate terminal value using reinvestment approach
        final_year_margin = margin_projections[-1] if margin_projections else operating_margin
        terminal_value, terminal_details = self.calculate_terminal_value(
            final_year_revenue=final_year_revenue,
            final_year_margin=final_year_margin,
            wacc=terminal_wacc
        )

        # Discount cash flows using year-specific WACC
        # PV factor for year t = 1 / ∏(1 + wacc_i) for i=1..t
        pv_fcf = 0
        cumulative_discount = 1.0
        for year_idx, fcf in enumerate(fcf_projections):
            cumulative_discount *= (1 + wacc_per_year[year_idx])
            pv_fcf += fcf / cumulative_discount

        # Terminal value discounted through all projection years
        pv_terminal_value = terminal_value / cumulative_discount

        # Enterprise value = PV of FCFs + PV of Terminal Value
        enterprise_value = pv_fcf + pv_terminal_value

        # Equity bridge: Enterprise Value + Cash & Investments - Debt
        cash = financial_data.get('cash', 0)
        short_term_investments = financial_data.get('short_term_investments', 0)
        long_term_investments = financial_data.get('long_term_investments', 0)
        cash_and_investments = cash + short_term_investments + long_term_investments
        equity_value = enterprise_value + cash_and_investments - total_debt

        # Fair value per share
        fair_value_per_share = equity_value / shares_outstanding if shares_outstanding > 0 else 0

        # Calculate upside/downside
        upside_percent = (
            ((fair_value_per_share - current_price) / current_price * 100)
            if current_price > 0 else 0
        )

        # Store results
        self.results = {
            'fair_value': fair_value_per_share,
            'current_price': current_price,
            'upside_percent': upside_percent,
            'wacc': wacc,
            'enterprise_value': enterprise_value,
            'equity_value': equity_value,
            'terminal_value': terminal_value,
            'pv_terminal_value': pv_terminal_value,
            'pv_fcf': pv_fcf,
            'sales_to_capital': sales_to_capital,
            'wacc_per_year': wacc_per_year,
        }
        self.results.update(terminal_details)

        if verbose:
            self.results.update({
                'fcf_projections': fcf_projections,
                'margin_projections': margin_projections,
                'operating_margin': operating_margin,
                'sales_to_capital': sales_to_capital,
                'beta': beta,
                'debt_to_equity': debt_to_equity,
                'shares_outstanding': shares_outstanding,
                'base_revenue': revenue,
                'cash': cash,
                'short_term_investments': short_term_investments,
                'long_term_investments': long_term_investments,
                'total_debt': total_debt,
                'final_year_revenue': final_year_revenue,
            })

        return self.results

    def reverse_dcf(
        self,
        financial_data: Dict,
        shares_outstanding: float,
        target_price: float,
        solve_for: str = 'revenue_growth_rate',
        precision: float = 0.001,
        max_iterations: int = 50
    ) -> Optional[Dict]:
        """
        Solve for the assumption value that produces a given target price.

        Uses binary search to find the value of `solve_for` that makes
        fair_value ≈ target_price.

        Args:
            financial_data: Same as calculate_fair_value
            shares_outstanding: Number of shares outstanding
            target_price: The price to solve for (typically current market price)
            solve_for: Which assumption to solve for. Currently supports:
                - 'revenue_growth_rate' (default)
            precision: Stop when fair value is within this fraction of target (default 0.1%)
            max_iterations: Maximum binary search iterations

        Returns:
            Dict with 'implied_value' (the solved assumption value),
            'fair_value' (resulting fair value), and 'wacc' used,
            or None if no solution found.
        """
        if solve_for != 'revenue_growth_rate':
            raise ValueError(f"reverse_dcf currently only supports solve_for='revenue_growth_rate', got '{solve_for}'")

        if max_iterations <= 0:
            return None

        low = -0.10  # Allow negative growth (declining companies)
        high = 0.50
        mid = (low + high) / 2
        fair_value = 0.0
        result = {}

        original_growth = self.assumptions.revenue_growth_rate

        for _ in range(max_iterations):
            mid = (low + high) / 2
            self.assumptions.revenue_growth_rate = mid

            try:
                result = self.calculate_fair_value(financial_data, shares_outstanding, target_price, verbose=False)
                fair_value = result['fair_value']
            except (ValueError, ZeroDivisionError):
                # This growth rate produces invalid results, narrow the range
                high = mid
                continue

            if abs(fair_value - target_price) / target_price < precision:
                # Found it
                self.assumptions.revenue_growth_rate = original_growth
                return {
                    'implied_value': mid,
                    'fair_value': fair_value,
                    'wacc': result.get('wacc'),
                }

            if fair_value < target_price:
                low = mid
            else:
                high = mid

        # Didn't converge — return best estimate
        self.assumptions.revenue_growth_rate = original_growth
        return {
            'implied_value': mid,
            'fair_value': fair_value,
            'wacc': result.get('wacc'),
        }

    def get_summary(self) -> str:
        """
        Get a formatted summary of the DCF valuation with detailed FCF projections

        Returns:
            Formatted string with comprehensive valuation breakdown
        """
        if not self.results:
            return "No valuation calculated yet. Run calculate_fair_value() first."

        r = self.results

        # Start with header
        summary = "\n" + "=" * 100 + "\n"
        summary += "DCF VALUATION - DETAILED FREE CASH FLOW PROJECTIONS\n"
        summary += "=" * 100 + "\n\n"

        # Key assumptions
        summary += "MODEL ASSUMPTIONS:\n"
        summary += "-" * 100 + "\n"
        summary += f"  Projection Years:      {self.assumptions.projection_years}\n"
        summary += f"  Growth Years 1-5:      {self.assumptions.revenue_growth_rate*100:.1f}%\n"
        summary += f"  Terminal Growth:       {self.assumptions.terminal_growth_rate*100:.1f}% (= risk-free rate)\n"
        summary += f"  Growth Tapering:       Linear over Years 6-10\n"

        if 'operating_margin' in r:
            summary += f"  Operating Margin:      {r['operating_margin']*100:.1f}%\n"
            if self.assumptions.target_operating_margin is not None:
                summary += f"  Target Op. Margin:     {self.assumptions.target_operating_margin*100:.1f}% (converges linearly)\n"

        if self.assumptions.effective_tax_rate is not None:
            summary += f"  Effective Tax Rate:    {self.assumptions.effective_tax_rate*100:.1f}% (Year 1) → {self.assumptions.tax_rate*100:.0f}% (marginal, by Year {self.assumptions.projection_years})\n"
        else:
            summary += f"  Tax Rate:              {self.assumptions.tax_rate*100:.0f}%\n"
        if self.assumptions.cost_of_capital is not None:
            summary += f"  Cost of Capital:       {r['wacc']*100:.2f}% (manual hurdle rate)\n"
        else:
            summary += f"  WACC:                  {r['wacc']*100:.2f}%\n"

        if 'sales_to_capital' in r:
            summary += f"  Sales-to-Capital:      {r['sales_to_capital']:.2f}x\n"

        summary += "\n"

        # Detailed year-by-year projections
        if 'fcf_projections' in r and 'base_revenue' in r:
            summary += "=" * 100 + "\n"
            summary += "YEAR-BY-YEAR FREE CASH FLOW PROJECTIONS\n"
            summary += "=" * 100 + "\n\n"

            # Header
            has_margin_convergence = self.assumptions.target_operating_margin is not None
            if has_margin_convergence:
                summary += f"{'Year':>4} | {'Phase':>8} | {'Growth':>6} | {'Margin':>6} | {'Revenue':>10} | {'NOPAT':>10} | {'Reinvest':>10} | {'FCF':>10} | {'PV Factor':>8} | {'PV of FCF':>10}\n"
            else:
                summary += f"{'Year':>4} | {'Phase':>8} | {'Growth':>6} | {'Revenue':>10} | {'Rev Δ':>9} | {'NOPAT':>10} | {'Reinvest':>10} | {'FCF':>10} | {'PV Factor':>8} | {'PV of FCF':>10}\n"
            summary += "-" * 100 + "\n"

            # Calculate detailed metrics for each year
            revenue = r['base_revenue']
            base_margin = r.get('operating_margin', 0.30)
            margin_projections = r.get('margin_projections', [])
            sales_to_capital = r.get('sales_to_capital', 1.0)
            wacc_per_year = r.get('wacc_per_year', [])
            growth_diff = self.assumptions.revenue_growth_rate - self.assumptions.terminal_growth_rate
            cumulative_pv_fcf = 0
            cumulative_discount = 1.0

            for year in range(1, len(r['fcf_projections']) + 1):
                # Determine growth rate
                if year <= 5:
                    growth_rate = self.assumptions.revenue_growth_rate
                    phase = "High"
                else:
                    tapering_factor = (year - 5) / 5
                    growth_rate = self.assumptions.revenue_growth_rate - (growth_diff * tapering_factor)
                    phase = "Taper"

                # Get margin for this year
                if margin_projections:
                    year_margin = margin_projections[year - 1]
                else:
                    year_margin = base_margin

                # Calculate metrics
                revenue_growth_dollars = revenue * growth_rate
                revenue *= (1 + growth_rate)
                year_tax = self._get_tax_rate_for_year(year, self.assumptions.projection_years)
                nopat = revenue * year_margin * (1 - year_tax)
                reinvestment = revenue_growth_dollars / sales_to_capital if sales_to_capital > 0 else 0
                fcf = r['fcf_projections'][year - 1]

                # PV calculation using year-specific WACC
                year_wacc = wacc_per_year[year - 1] if wacc_per_year else r['wacc']
                cumulative_discount *= (1 + year_wacc)
                pv_factor = 1 / cumulative_discount
                pv_fcf = fcf * pv_factor
                cumulative_pv_fcf += pv_fcf

                if has_margin_convergence:
                    summary += f"{year:4d} | {phase:>8} | {growth_rate*100:5.1f}% | {year_margin*100:5.1f}% | ${revenue/1e9:8.2f}B | ${nopat/1e9:8.2f}B | ${reinvestment/1e9:8.2f}B | ${fcf/1e9:8.2f}B | {pv_factor:8.4f} | ${pv_fcf/1e9:8.2f}B\n"
                else:
                    summary += f"{year:4d} | {phase:>8} | {growth_rate*100:5.1f}% | ${revenue/1e9:8.2f}B | ${revenue_growth_dollars/1e9:7.2f}B | ${nopat/1e9:8.2f}B | ${reinvestment/1e9:8.2f}B | ${fcf/1e9:8.2f}B | {pv_factor:8.4f} | ${pv_fcf/1e9:8.2f}B\n"

            summary += "-" * 100 + "\n"
            summary += f"{'':>4} | {'':>8} | {'':>6} | {'':>10} | {'':>9} | {'':>10} | {'Total PV →':>10} | {'':>10} | {'':>8} | ${cumulative_pv_fcf/1e9:8.2f}B\n"
            summary += "\n"

        # Terminal value calculation
        if 'terminal_nopat' in r:
            summary += "=" * 100 + "\n"
            summary += "TERMINAL VALUE CALCULATION\n"
            summary += "=" * 100 + "\n\n"

            g = self.assumptions.terminal_growth_rate
            terminal_roic = r['terminal_roic']
            terminal_reinv = r['terminal_reinvestment_rate']
            terminal_nopat = r['terminal_nopat']
            terminal_fcf = r['terminal_fcf']
            terminal_value = r['terminal_value']
            # Use cumulative discount from the projection loop if available,
            # otherwise fall back to flat WACC
            wacc_per_year = r.get('wacc_per_year', [])
            if wacc_per_year:
                cum_disc = 1.0
                for w in wacc_per_year:
                    cum_disc *= (1 + w)
                pv_factor_terminal = 1 / cum_disc
            else:
                pv_factor_terminal = 1 / ((1 + r['wacc']) ** self.assumptions.projection_years)

            summary += f"  Terminal Growth Rate:       {g*100:.1f}%\n"
            summary += f"  Terminal ROIC:              {terminal_roic*100:.2f}%"
            if self.assumptions.terminal_roic is not None:
                summary += " (explicit)\n"
            else:
                summary += " (= WACC, no excess returns)\n"
            summary += f"  Reinvestment Rate (g/ROIC): {terminal_reinv*100:.1f}%\n"
            summary += f"  Year {self.assumptions.projection_years + 1} NOPAT:              ${terminal_nopat/1e9:,.2f}B\n"
            summary += f"  Year {self.assumptions.projection_years + 1} FCF:                ${terminal_fcf/1e9:,.2f}B  (NOPAT x {(1-terminal_reinv)*100:.1f}%)\n"
            summary += f"  WACC:                       {r['wacc']*100:.2f}%\n"
            summary += f"  Gordon Growth Formula:      FCF / (WACC - g)\n"
            summary += f"  Terminal Value:             ${terminal_value/1e9:,.2f}B\n"
            summary += f"  PV Factor (Year {self.assumptions.projection_years}):        {pv_factor_terminal:.4f}\n"
            summary += f"  PV of Terminal Value:       ${r['pv_terminal_value']/1e9:,.2f}B\n"
            summary += "\n"

        # Valuation summary
        summary += "=" * 100 + "\n"
        summary += "VALUATION SUMMARY\n"
        summary += "=" * 100 + "\n\n"

        pv_fcf_pct = (r['pv_fcf'] / r['enterprise_value']) * 100 if r['enterprise_value'] > 0 else 0
        pv_terminal_pct = (r['pv_terminal_value'] / r['enterprise_value']) * 100 if r['enterprise_value'] > 0 else 0

        summary += f"  PV of FCF (Years 1-{self.assumptions.projection_years}):   ${r['pv_fcf']/1e9:,.2f}B  ({pv_fcf_pct:.1f}% of EV)\n"
        summary += f"  PV of Terminal Value:     ${r['pv_terminal_value']/1e9:,.2f}B  ({pv_terminal_pct:.1f}% of EV)\n"
        summary += f"  Enterprise Value:         ${r['enterprise_value']/1e9:,.2f}B\n"

        # Equity bridge
        if 'cash' in r:
            cash = r['cash']
            sti = r.get('short_term_investments', 0)
            lti = r.get('long_term_investments', 0)
            debt = r.get('total_debt', 0)
            summary += f"\n  EQUITY BRIDGE:\n"
            summary += f"    + Cash & Equivalents:     ${cash/1e9:,.2f}B\n"
            if sti > 0:
                summary += f"    + Short-Term Investments: ${sti/1e9:,.2f}B\n"
            if lti > 0:
                summary += f"    + Long-Term Investments:  ${lti/1e9:,.2f}B\n"
            summary += f"    - Total Debt:             ${debt/1e9:,.2f}B\n"

        summary += f"  Equity Value:             ${r['equity_value']/1e9:,.2f}B\n"

        if 'shares_outstanding' in r:
            summary += f"  Shares Outstanding:       {r['shares_outstanding']/1e9:.2f}B\n"

        summary += "\n"
        summary += f"  Fair Value per Share:     ${r['fair_value']:.2f}\n"
        summary += f"  Current Price:            ${r['current_price']:.2f}\n"
        summary += f"  Upside/Downside:          {r['upside_percent']:+.1f}%\n"
        summary += "\n"

        # Assessment
        upside = r['upside_percent']
        if upside > 20:
            rec = "Significantly Undervalued"
        elif upside > 10:
            rec = "Undervalued"
        elif upside > -10:
            rec = "Fairly Valued"
        elif upside > -20:
            rec = "Overvalued"
        else:
            rec = "Significantly Overvalued"

        summary += f"  Assessment:               {rec}\n"
        summary += "\n"

        # Sensitivity analysis
        if 'shares_outstanding' in r and 'base_revenue' in r and 'operating_margin' in r:
            summary += self._sensitivity_table()

        summary += "=" * 100 + "\n"

        return summary

    def _sensitivity_table(self) -> str:
        """
        Generate a sensitivity table showing fair value across
        a matrix of revenue growth rate vs. operating margin.

        Returns:
            Formatted sensitivity table string
        """
        r = self.results

        base_growth = round(self.assumptions.revenue_growth_rate, 4)
        base_margin = round(
            self.assumptions.target_operating_margin or r['operating_margin'], 4
        )
        wacc = r['wacc']
        shares = r['shares_outstanding']
        # Compute net debt from bridge components (debt - cash - investments)
        cash_and_inv = r.get('cash', 0) + r.get('short_term_investments', 0) + r.get('long_term_investments', 0)
        net_debt = r.get('total_debt', 0) - cash_and_inv
        base_revenue = r['base_revenue']
        sales_to_capital = r.get('sales_to_capital', 1.0)

        # Growth rate steps: base +/- 2%, 4% in 2% increments
        growth_steps = sorted(set([
            round(base_growth - 0.04, 4),
            round(base_growth - 0.02, 4),
            round(base_growth, 4),
            round(base_growth + 0.02, 4),
            round(base_growth + 0.04, 4),
        ]))
        growth_steps = [g for g in growth_steps if g > -1.0]  # Allow negative growth in sensitivity

        # Operating margin steps: base +/- 3%, 6% in 3% increments
        margin_steps = sorted(set([
            round(base_margin - 0.06, 4),
            round(base_margin - 0.03, 4),
            round(base_margin, 4),
            round(base_margin + 0.03, 4),
            round(base_margin + 0.06, 4),
        ]))
        margin_steps = [m for m in margin_steps if m > 0]

        output = "=" * 100 + "\n"
        output += "SENSITIVITY ANALYSIS - Fair Value per Share\n"
        output += "=" * 100 + "\n\n"
        output += "                                  Operating Margin\n"

        # Header row
        col_width = 11
        output += f"{'Growth':>8}  |"
        for m in margin_steps:
            label = f"{m*100:.1f}%"
            if m == base_margin:
                label += "*"
            output += f"{label:>{col_width}}"
        output += "\n"
        output += "-" * (10 + col_width * len(margin_steps)) + "\n"

        for growth in growth_steps:
            is_base_growth = (growth == base_growth)
            label = f"{growth*100:.1f}%"
            if is_base_growth:
                label += "*"
            output += f"{label:>8}  |"

            for margin in margin_steps:
                fair_value = self._recalc_fair_value(
                    growth, margin, wacc, sales_to_capital,
                    base_revenue, shares, net_debt,
                )
                if fair_value is not None:
                    cell = f"${fair_value:,.0f}"
                    if growth == base_growth and margin == base_margin:
                        cell = f"[{cell}]"
                    output += f"{cell:>{col_width}}"
                else:
                    output += f"{'ERR':>{col_width}}"

            output += "\n"

        output += "\n  * = current assumption    [ ] = base case\n\n"

        return output

    def _recalc_fair_value(
        self,
        revenue_growth: float,
        operating_margin: float,
        wacc: float,
        sales_to_capital: float,
        base_revenue: float,
        shares: float,
        net_debt: float,
    ) -> Optional[float]:
        """
        Recalculate fair value with different growth rate and operating margin.
        The operating_margin parameter is treated as the target margin for
        sensitivity analysis (no convergence within the recalc).

        Uses the wacc_per_year from results if available (year-varying WACC),
        otherwise falls back to the flat wacc parameter.

        The wacc parameter is used for the terminal value spread (Gordon Growth)
        and terminal ROIC default — it should be the terminal/marginal-rate WACC,
        not a year-specific value.

        Returns:
            Fair value per share, or None on error
        """
        # Re-project FCFs with the new assumptions
        growth_diff = revenue_growth - self.assumptions.terminal_growth_rate
        years = self.assumptions.projection_years
        revenue = base_revenue
        fcf_projections = []
        wacc_per_year = self.results.get('wacc_per_year', [])

        for year in range(1, years + 1):
            if year <= 5:
                growth_rate = revenue_growth
            else:
                tapering_factor = (year - 5) / 5
                growth_rate = revenue_growth - (growth_diff * tapering_factor)

            revenue_growth_dollars = revenue * growth_rate
            revenue *= (1 + growth_rate)
            year_tax = self._get_tax_rate_for_year(year, years)
            nopat = revenue * operating_margin * (1 - year_tax)
            reinvestment = revenue_growth_dollars / sales_to_capital if sales_to_capital > 0 else 0
            fcf_projections.append(nopat - reinvestment)

        if not fcf_projections:
            return None

        # PV of FCFs using year-specific WACC
        pv_fcf = 0
        cumulative_discount = 1.0
        for year_idx, fcf in enumerate(fcf_projections):
            year_wacc = wacc_per_year[year_idx] if wacc_per_year else wacc
            cumulative_discount *= (1 + year_wacc)
            pv_fcf += fcf / cumulative_discount

        # Terminal value using reinvestment-based approach
        g = self.assumptions.terminal_growth_rate
        spread = wacc - g
        if spread <= 0:
            return None

        terminal_roic = self.assumptions.terminal_roic if self.assumptions.terminal_roic is not None else wacc
        if terminal_roic <= 0 or terminal_roic < g:
            return None

        terminal_revenue = revenue * (1 + g)
        terminal_nopat = terminal_revenue * operating_margin * (1 - self.assumptions.tax_rate)
        terminal_reinv_rate = g / terminal_roic
        terminal_fcf = terminal_nopat * (1 - terminal_reinv_rate)
        pv_terminal = (terminal_fcf / spread) / cumulative_discount

        equity_value = pv_fcf + pv_terminal - net_debt
        return equity_value / shares if shares > 0 else 0
