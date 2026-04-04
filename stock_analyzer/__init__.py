"""
Stock Analyzer Package

A comprehensive toolkit for stock analysis including:
- DCF (Discounted Cash Flow) valuation
- Financial metrics calculation
- Company fundamental analysis

API key resolution order:
1. CLAUDE_PLUGIN_OPTION_ALPHA_VANTAGE_API_KEY (set by Claude Code plugin config)
2. ALPHA_VANTAGE_API_KEY environment variable
3. .env file via python-dotenv (development fallback)
"""

# Load .env file from project root (development fallback for API keys)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from .dcf import DCFModel, DCFAssumptions
from .metrics import FinancialMetrics
from .stock_manager import StockManager
from .utils import safe_float
from .av_fetcher import AlphaVantageFetcher

__version__ = "1.0.0"
__all__ = [
    "DCFModel", "DCFAssumptions", "FinancialMetrics", "StockManager",
    "safe_float", "AlphaVantageFetcher",
]
