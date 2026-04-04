"""
Alpha Vantage Direct Fetcher

Fetches financial data directly from the Alpha Vantage REST API with
built-in rate limiting (1.5s between requests) to avoid throttling.

Data is already in Alpha Vantage format, so no normalization is needed.
Downstream code (metrics.py, dcf.py) works without changes.

Free tier: 25 requests/day, max 5 requests/minute.
A full stock fetch uses 6 API calls (~8 seconds with rate limiting).

Set your API key via the ALPHA_VANTAGE_API_KEY environment variable.
Get a free key at: https://www.alphavantage.co/support/#api-key
"""

import os
import time
from typing import Dict, List, Optional

try:
    import requests as _requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

AV_BASE_URL = "https://www.alphavantage.co/query"

# Minimum seconds between API calls to avoid rate limiting
RATE_LIMIT_DELAY = 1.5


class AlphaVantageFetcher:
    """
    Fetches financial data directly from Alpha Vantage REST API.

    Includes built-in rate limiting to avoid throttling on the free tier.
    Returns data in native Alpha Vantage format (no normalization needed).
    """

    def __init__(self, symbol: str, api_key: Optional[str] = None):
        if not REQUESTS_AVAILABLE:
            raise ImportError("requests is not installed. Run: pip install requests")
        self.symbol = symbol.upper()
        self.api_key = (
            api_key
            or os.environ.get("CLAUDE_PLUGIN_OPTION_ALPHA_VANTAGE_API_KEY")
            or os.environ.get("ALPHA_VANTAGE_API_KEY", "")
        )
        if not self.api_key:
            raise ValueError(
                "Alpha Vantage API key not found. Set the ALPHA_VANTAGE_API_KEY "
                "environment variable or pass api_key to AlphaVantageFetcher. "
                "Get a free key at: https://www.alphavantage.co/support/#api-key"
            )
        self._last_request_time = 0.0

    def _rate_limit(self):
        """Enforce minimum delay between API calls."""
        elapsed = time.time() - self._last_request_time
        if elapsed < RATE_LIMIT_DELAY:
            time.sleep(RATE_LIMIT_DELAY - elapsed)
        self._last_request_time = time.time()

    def _get(self, params: Dict) -> Optional[Dict]:
        """Make a rate-limited GET request to Alpha Vantage.

        Returns parsed JSON on success, None on error or throttle.
        """
        self._rate_limit()
        params["apikey"] = self.api_key
        resp = _requests.get(AV_BASE_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        # Check for throttle or error responses
        if "Information" in data or "Note" in data:
            return None
        if "Error Message" in data:
            return None
        return data

    def fetch_overview(self) -> Optional[Dict]:
        """Fetch company overview. Returns native AV format."""
        try:
            data = self._get({"function": "OVERVIEW", "symbol": self.symbol})
            if not data or "Symbol" not in data:
                return None
            return data
        except Exception as e:
            print(f"[AlphaVantage] fetch_overview({self.symbol}) failed: {e}")
            return None

    def fetch_income_statement(self, period: str = "annual", limit: int = 3) -> Optional[Dict]:
        """Fetch income statement. Returns dict with 'reports' key."""
        try:
            data = self._get({"function": "INCOME_STATEMENT", "symbol": self.symbol})
            if not data:
                return None

            key = "quarterlyReports" if period == "quarterly" else "annualReports"
            reports = data.get(key, [])[:limit]
            if not reports:
                return None

            return {
                "symbol": self.symbol,
                key: reports,
                "reports": reports,
            }
        except Exception as e:
            print(f"[AlphaVantage] fetch_income_statement({self.symbol}) failed: {e}")
            return None

    def fetch_balance_sheet(self, period: str = "annual", limit: int = 3) -> Optional[Dict]:
        """Fetch balance sheet. Returns dict with 'reports' key."""
        try:
            data = self._get({"function": "BALANCE_SHEET", "symbol": self.symbol})
            if not data:
                return None

            key = "quarterlyReports" if period == "quarterly" else "annualReports"
            reports = data.get(key, [])[:limit]
            if not reports:
                return None

            return {
                "symbol": self.symbol,
                key: reports,
                "reports": reports,
            }
        except Exception as e:
            print(f"[AlphaVantage] fetch_balance_sheet({self.symbol}) failed: {e}")
            return None

    def fetch_cash_flow(self, period: str = "annual", limit: int = 3) -> Optional[Dict]:
        """Fetch cash flow statement. Returns dict with 'reports' key."""
        try:
            data = self._get({"function": "CASH_FLOW", "symbol": self.symbol})
            if not data:
                return None

            key = "quarterlyReports" if period == "quarterly" else "annualReports"
            reports = data.get(key, [])[:limit]
            if not reports:
                return None

            return {
                "symbol": self.symbol,
                key: reports,
                "reports": reports,
            }
        except Exception as e:
            print(f"[AlphaVantage] fetch_cash_flow({self.symbol}) failed: {e}")
            return None

    def fetch_quote(self) -> Optional[Dict]:
        """Fetch current quote. Returns native AV 'Global Quote' format."""
        try:
            data = self._get({"function": "GLOBAL_QUOTE", "symbol": self.symbol})
            if not data or "Global Quote" not in data:
                return None
            gq = data["Global Quote"]
            if not gq or "05. price" not in gq:
                return None
            return data
        except Exception as e:
            print(f"[AlphaVantage] fetch_quote({self.symbol}) failed: {e}")
            return None
