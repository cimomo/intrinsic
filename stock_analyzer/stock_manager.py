"""
Stock Manager - Handle stock-specific folders and assumptions persistence
"""

import os
import json
from datetime import datetime, timezone, date
from pathlib import Path
from typing import Optional, Dict, Any, List
from .dcf import DCFAssumptions


class StockManager:
    """
    Manages stock-specific folders and persists DCF assumptions
    """

    def __init__(self, base_dir: str = "data"):
        """
        Initialize stock manager

        Args:
            base_dir: Base directory for stock folders (defaults to data/)
        """
        self.base_dir = Path(base_dir)

    def is_market_data_stale(
        self,
        data: Optional[Dict],
        threshold_days: int = 30
    ) -> bool:
        """
        Check if market data is stale.

        Returns True when:
        - data is None
        - data has no 'fetched_at' key or it's empty
        - 'fetched_at' cannot be parsed as an ISO date
        - 'fetched_at' is more than threshold_days days ago

        Args:
            data: Market data dict (from load_market_data) or None
            threshold_days: Maximum age in days before data is considered stale

        Returns:
            True if stale, False if fresh
        """
        if data is None:
            return True
        fetched_at_str = data.get('fetched_at')
        if not fetched_at_str:
            return True
        try:
            fetched_at = date.fromisoformat(fetched_at_str)
        except (ValueError, TypeError):
            return True
        age_days = (date.today() - fetched_at).days
        return age_days > threshold_days

    def save_market_data(self, data: Dict) -> Path:
        """
        Save market data to data/_market.json.

        The caller is responsible for building a valid market data dict
        (via validated WebFetch output). This method is the trusted write
        path and does no validation.

        Args:
            data: Market data dict with keys fetched_at, risk_free_rate,
                  implied_erp (with default_measure and measures)

        Returns:
            Path to the saved _market.json file
        """
        self.base_dir.mkdir(parents=True, exist_ok=True)
        market_file = self.base_dir / '_market.json'
        with open(market_file, 'w') as f:
            json.dump(data, f, indent=2)
        return market_file

    def load_market_data(self) -> Optional[Dict]:
        """
        Load and validate market data from data/_market.json.

        Returns None on any of:
        - File does not exist
        - Invalid JSON
        - Not a dict
        - Missing required keys (fetched_at, risk_free_rate, implied_erp)
        - implied_erp missing default_measure or measures
        - measures dict is empty
        - default_measure key does not exist in measures dict
        - risk_free_rate outside [0.0, 0.10]
        - any measure value outside [0.01, 0.15]
        - any numeric field is not an int or float

        Returns:
            Validated market data dict, or None
        """
        market_file = self.base_dir / '_market.json'
        if not market_file.exists():
            return None

        try:
            with open(market_file, 'r') as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError, OSError) as e:
            print(f"Warning: could not read {market_file}: {e}")
            return None

        # Structure checks
        if not isinstance(data, dict):
            return None
        if 'fetched_at' not in data:
            return None
        if 'risk_free_rate' not in data:
            return None
        if 'implied_erp' not in data:
            return None

        implied_erp = data['implied_erp']
        if not isinstance(implied_erp, dict):
            return None
        if 'default_measure' not in implied_erp:
            return None
        if 'measures' not in implied_erp:
            return None

        measures = implied_erp['measures']
        if not isinstance(measures, dict) or len(measures) == 0:
            return None
        if implied_erp['default_measure'] not in measures:
            return None

        # Plausibility bounds on risk-free rate: 0% to 10%
        rf = data['risk_free_rate']
        if not isinstance(rf, (int, float)) or isinstance(rf, bool):
            return None
        if rf < 0.0 or rf > 0.10:
            return None

        # Plausibility bounds on each ERP measure: 1% to 15%
        for measure_name, value in measures.items():
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                return None
            if value < 0.01 or value > 0.15:
                return None

        return data

    def get_stock_folder(self, symbol: str) -> Path:
        """
        Get or create the folder for a stock symbol

        Args:
            symbol: Stock ticker symbol (e.g., "MSFT")

        Returns:
            Path to the stock folder
        """
        symbol = symbol.upper()
        stock_folder = self.base_dir / symbol

        # Create folder if it doesn't exist
        stock_folder.mkdir(parents=True, exist_ok=True)

        return stock_folder

    def get_assumptions_file(self, symbol: str) -> Path:
        """
        Get the path to the assumptions file for a stock

        Args:
            symbol: Stock ticker symbol

        Returns:
            Path to the assumptions.json file
        """
        stock_folder = self.get_stock_folder(symbol)
        return stock_folder / "assumptions.json"

    def load_assumptions(self, symbol: str) -> Optional[DCFAssumptions]:
        """
        Load DCF assumptions from file if it exists

        Args:
            symbol: Stock ticker symbol

        Returns:
            DCFAssumptions object if file exists, None otherwise
        """
        assumptions_file = self.get_assumptions_file(symbol)

        if not assumptions_file.exists():
            return None

        try:
            with open(assumptions_file, 'r') as f:
                data = json.load(f)

            # Create DCFAssumptions from loaded data
            assumptions = DCFAssumptions(
                revenue_growth_rate=data.get('revenue_growth_rate', 0.10),
                terminal_growth_rate=data.get('terminal_growth_rate'),  # Will auto-set to risk_free_rate if None
                operating_margin=data.get('operating_margin'),
                target_operating_margin=data.get('target_operating_margin'),
                tax_rate=data.get('tax_rate', 0.21),
                effective_tax_rate=data.get('effective_tax_rate'),
                risk_free_rate=data.get('risk_free_rate', 0.045),
                market_risk_premium=data.get('market_risk_premium', 0.05),
                beta=data.get('beta'),
                debt_to_equity_ratio=data.get('debt_to_equity_ratio'),
                cost_of_debt=data.get('cost_of_debt', 0.05),
                projection_years=data.get('projection_years', 10),
                sales_to_capital_ratio=data.get('sales_to_capital_ratio'),
                terminal_roic=data.get('terminal_roic'),
                cost_of_capital=data.get('cost_of_capital'),
            )

            return assumptions

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"Warning: Could not load assumptions from {assumptions_file}: {e}")
            return None

    def save_assumptions(self, symbol: str, assumptions: DCFAssumptions, manual_overrides: Optional[List[str]] = None) -> Path:
        """
        Save DCF assumptions to file

        Args:
            symbol: Stock ticker symbol
            assumptions: DCFAssumptions object to save
            manual_overrides: List of field names that were manually set by the user.
                If None, preserves any existing _manual_overrides from the file.

        Returns:
            Path to the saved file
        """
        assumptions_file = self.get_assumptions_file(symbol)

        # Preserve existing manual_overrides if caller doesn't specify
        if manual_overrides is None and assumptions_file.exists():
            try:
                with open(assumptions_file, 'r') as f:
                    existing = json.load(f)
                manual_overrides = existing.get('_manual_overrides', [])
            except (json.JSONDecodeError, KeyError):
                manual_overrides = []

        # Convert assumptions to dictionary
        data = {
            'revenue_growth_rate': assumptions.revenue_growth_rate,
            'terminal_growth_rate': assumptions.terminal_growth_rate,
            'operating_margin': assumptions.operating_margin,
            'target_operating_margin': assumptions.target_operating_margin,
            'tax_rate': assumptions.tax_rate,
            'effective_tax_rate': assumptions.effective_tax_rate,
            'risk_free_rate': assumptions.risk_free_rate,
            'market_risk_premium': assumptions.market_risk_premium,
            'beta': assumptions.beta,
            'debt_to_equity_ratio': assumptions.debt_to_equity_ratio,
            'cost_of_debt': assumptions.cost_of_debt,
            'projection_years': assumptions.projection_years,
            'sales_to_capital_ratio': assumptions.sales_to_capital_ratio,
            'terminal_roic': assumptions.terminal_roic,
            'cost_of_capital': assumptions.cost_of_capital,
        }

        if manual_overrides:
            data['_manual_overrides'] = manual_overrides

        # Save to JSON file
        with open(assumptions_file, 'w') as f:
            json.dump(data, f, indent=2)

        return assumptions_file

    def load_manual_overrides(self, symbol: str) -> List[str]:
        """
        Load the list of manually overridden assumption fields for a stock

        Args:
            symbol: Stock ticker symbol

        Returns:
            List of field names that were manually set, or empty list
        """
        assumptions_file = self.get_assumptions_file(symbol)

        if not assumptions_file.exists():
            return []

        try:
            with open(assumptions_file, 'r') as f:
                data = json.load(f)
            return data.get('_manual_overrides', [])
        except (json.JSONDecodeError, KeyError):
            return []

    def get_or_create_assumptions(self, symbol: str, default_assumptions: Optional[DCFAssumptions] = None) -> tuple[DCFAssumptions, bool]:
        """
        Load assumptions from file if it exists, otherwise create and save default assumptions

        Args:
            symbol: Stock ticker symbol
            default_assumptions: Default assumptions to use if file doesn't exist

        Returns:
            Tuple of (DCFAssumptions, was_loaded_from_file)
        """
        # Try to load existing assumptions
        assumptions = self.load_assumptions(symbol)

        if assumptions is not None:
            return assumptions, True

        # Use provided defaults or create new default assumptions
        if default_assumptions is None:
            assumptions = DCFAssumptions()
        else:
            assumptions = default_assumptions

        # Save the assumptions for future use
        self.save_assumptions(symbol, assumptions)

        return assumptions, False

    def get_financial_data_file(self, symbol: str) -> Path:
        """
        Get the path to the financial data cache file for a stock

        Args:
            symbol: Stock ticker symbol

        Returns:
            Path to the financial_data.json file
        """
        stock_folder = self.get_stock_folder(symbol)
        return stock_folder / "financial_data.json"

    def save_financial_data(self, symbol: str, data: Dict[str, Any], source_info: Optional[Dict[str, Any]] = None) -> Path:
        """
        Save fetched financial data to disk

        Args:
            symbol: Stock ticker symbol
            data: Dict with keys like overview, income_statement_annual, etc.
            source_info: Optional dict mapping source names to their metadata
                         (provider, status, fetched_date, latest_period, etc.)

        Returns:
            Path to the saved file
        """
        symbol = symbol.upper()

        # Detect double-wrapping: if data looks like a full envelope from
        # load_financial_data() (has symbol + fetched_at + data keys), the
        # caller forgot to extract data["data"] before saving.
        envelope_keys = {"symbol", "fetched_at", "data"}
        if envelope_keys.issubset(data.keys()) and isinstance(data.get("data"), dict):
            raise ValueError(
                "save_financial_data received a double-wrapped envelope "
                "(has 'symbol', 'fetched_at', and 'data' keys). "
                "Pass existing['data'] (the inner sources dict), not the "
                "full envelope from load_financial_data()."
            )

        now = datetime.now(timezone.utc)
        payload = {
            "symbol": symbol,
            "fetched_at": now.isoformat(),
            "fetched_at_unix": int(now.timestamp()),
        }
        if source_info is not None:
            payload["sources"] = source_info
        payload["data"] = data

        file_path = self.get_financial_data_file(symbol)
        with open(file_path, 'w') as f:
            json.dump(payload, f, indent=2)

        return file_path

    def load_financial_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Load cached financial data from disk

        Args:
            symbol: Stock ticker symbol

        Returns:
            Dict with symbol, fetched_at, fetched_at_unix, data keys, or None if missing/corrupt.
            Note: this is the full envelope. To update and re-save, pass
            result["data"] to save_financial_data(), not the full result.
        """
        file_path = self.get_financial_data_file(symbol)

        if not file_path.exists():
            return None

        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, ValueError):
            return None

    def save_analysis(self, symbol: str, content: str, filename: Optional[str] = None) -> Path:
        """
        Save analysis output to the stock folder

        Args:
            symbol: Stock ticker symbol
            content: Analysis content to save
            filename: Optional filename (defaults to analysis_YYYY-MM-DD.md)

        Returns:
            Path to the saved file
        """
        from datetime import datetime

        stock_folder = self.get_stock_folder(symbol)

        if filename is None:
            today = datetime.now().strftime('%Y-%m-%d')
            filename = f"analysis_{today}.md"

        output_file = stock_folder / filename

        with open(output_file, 'w') as f:
            f.write(content)

        return output_file

    @staticmethod
    def _get_latest_date(reports) -> Optional[str]:
        """Get most recent fiscalDateEnding from a list of report dicts."""
        if not reports:
            return None
        dates = []
        for r in reports:
            if not isinstance(r, dict):
                continue
            d = r.get("fiscalDateEnding")
            if d and d != "None":
                dates.append(d)
        return max(dates) if dates else None  # string comparison works for YYYY-MM-DD

    def validate_data_freshness(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Validate consistency between overview's LatestQuarter and actual data dates.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Validation result dict, or None if no cached data exists
        """
        cached = self.load_financial_data(symbol)
        if cached is None:
            return None

        data = cached.get("data", {})

        # Extract LatestQuarter from overview
        overview = data.get("overview")
        latest_quarter_expected = None
        if isinstance(overview, dict):
            lq = overview.get("LatestQuarter")
            if lq and lq != "None":
                latest_quarter_expected = lq

        # Find latest fiscalDateEnding per source
        source_keys = [
            "income_statement_annual",
            "income_statement_quarterly",
            "balance_sheet",
            "cash_flow",
        ]
        latest_dates: Dict[str, Optional[str]] = {}
        missing_sources: List[str] = []

        for key in source_keys:
            source_data = data.get(key)
            reports = None
            if isinstance(source_data, dict):
                reports = source_data.get("reports")
            elif isinstance(source_data, list):
                reports = source_data

            date = self._get_latest_date(reports)
            if date is not None:
                latest_dates[key] = date
            else:
                latest_dates[key] = None
                if key in data:
                    # Source exists but has no usable dates
                    pass
                else:
                    missing_sources.append(key)

        # Determine latest quarterly date
        latest_quarter_actual = latest_dates.get("income_statement_quarterly")

        # Check if quarterly data is current
        quarterly_data_current = True
        if latest_quarter_expected and latest_quarter_actual:
            quarterly_data_current = latest_quarter_actual >= latest_quarter_expected
        elif latest_quarter_expected and not latest_quarter_actual:
            quarterly_data_current = False

        # Build warnings
        warnings: List[str] = []

        if latest_quarter_expected and latest_quarter_actual and not quarterly_data_current:
            warnings.append(
                f"Quarterly income data (latest: {latest_quarter_actual}) is behind "
                f"overview's LatestQuarter ({latest_quarter_expected}). "
                f"The latest quarter's data may not be available from the data provider yet."
            )

        if latest_quarter_expected and not latest_quarter_actual and "income_statement_quarterly" not in data:
            warnings.append(
                "No quarterly income data available to compare against "
                f"overview's LatestQuarter ({latest_quarter_expected})."
            )

        for src in missing_sources:
            if src != "income_statement_quarterly":  # already warned above
                warnings.append(f"No data found for {src}.")

        # Check if balance_sheet / cash_flow lag behind annual income
        annual_income_date = latest_dates.get("income_statement_annual")
        if annual_income_date:
            for key in ("balance_sheet", "cash_flow"):
                src_date = latest_dates.get(key)
                if src_date and src_date < annual_income_date:
                    warnings.append(
                        f"{key} latest date ({src_date}) is older than "
                        f"annual income statement ({annual_income_date})."
                    )

        return {
            "latest_quarter_expected": latest_quarter_expected,
            "latest_quarter_actual": latest_quarter_actual,
            "quarterly_data_current": quarterly_data_current,
            "latest_dates": latest_dates,
            "missing_sources": missing_sources,
            "warnings": warnings,
        }

    def get_assumptions_summary(self, symbol: str) -> str:
        """
        Get a human-readable summary of the assumptions for a stock

        Args:
            symbol: Stock ticker symbol

        Returns:
            Formatted string with assumptions summary
        """
        assumptions_file = self.get_assumptions_file(symbol)

        if not assumptions_file.exists():
            return f"No assumptions file found for {symbol}. Default assumptions will be used and saved."

        assumptions = self.load_assumptions(symbol)

        if assumptions is None:
            return f"Error loading assumptions for {symbol}."

        summary = f"Loaded assumptions for {symbol} from {assumptions_file}:\n"
        summary += "-" * 60 + "\n"
        summary += f"  Revenue Growth (Years 1-5):  {assumptions.revenue_growth_rate*100:.1f}%\n"
        summary += f"  Terminal Growth:             {assumptions.terminal_growth_rate*100:.1f}%\n"
        summary += f"  Projection Years:            {assumptions.projection_years}\n"
        summary += f"  Risk-Free Rate:              {assumptions.risk_free_rate*100:.1f}%\n"
        summary += f"  Market Risk Premium:         {assumptions.market_risk_premium*100:.1f}%\n"
        summary += f"  Tax Rate (marginal):         {assumptions.tax_rate*100:.0f}%\n"
        if assumptions.effective_tax_rate is not None:
            summary += f"  Effective Tax Rate:          {assumptions.effective_tax_rate*100:.1f}% (transitions to marginal)\n"
        summary += f"  Cost of Debt:                {assumptions.cost_of_debt*100:.1f}%\n"

        if assumptions.operating_margin is not None:
            summary += f"  Operating Margin:            {assumptions.operating_margin*100:.1f}%\n"

        if assumptions.target_operating_margin is not None:
            summary += f"  Target Op. Margin:           {assumptions.target_operating_margin*100:.1f}%\n"

        if assumptions.sales_to_capital_ratio is not None:
            summary += f"  Sales-to-Capital:            {assumptions.sales_to_capital_ratio:.2f}x\n"

        if assumptions.terminal_roic is not None:
            summary += f"  Terminal ROIC:               {assumptions.terminal_roic*100:.1f}% (explicit)\n"
        else:
            summary += f"  Terminal ROIC:               = WACC (default)\n"

        if assumptions.cost_of_capital is not None:
            summary += f"  Cost of Capital:             {assumptions.cost_of_capital*100:.1f}% (manual hurdle rate)\n"

        return summary
