"""Tests for stock_analyzer.av_fetcher"""

import os
import pytest
from unittest.mock import patch, MagicMock
from stock_analyzer.av_fetcher import AlphaVantageFetcher


# --- Sample API Responses ---

SAMPLE_OVERVIEW = {
    "Symbol": "MSFT",
    "Name": "Microsoft Corporation",
    "MarketCapitalization": "2800000000000",
    "PERatio": "35.2",
}

SAMPLE_INCOME = {
    "symbol": "MSFT",
    "annualReports": [
        {"fiscalDateEnding": "2025-06-30", "totalRevenue": "250000000000"},
        {"fiscalDateEnding": "2024-06-30", "totalRevenue": "220000000000"},
        {"fiscalDateEnding": "2023-06-30", "totalRevenue": "200000000000"},
        {"fiscalDateEnding": "2022-06-30", "totalRevenue": "180000000000"},
    ],
    "quarterlyReports": [
        {"fiscalDateEnding": "2025-03-31", "totalRevenue": "65000000000"},
        {"fiscalDateEnding": "2024-12-31", "totalRevenue": "62000000000"},
    ],
}

SAMPLE_BALANCE_SHEET = {
    "symbol": "MSFT",
    "annualReports": [
        {"fiscalDateEnding": "2025-06-30", "totalAssets": "500000000000"},
        {"fiscalDateEnding": "2024-06-30", "totalAssets": "450000000000"},
    ],
}

SAMPLE_CASH_FLOW = {
    "symbol": "MSFT",
    "annualReports": [
        {"fiscalDateEnding": "2025-06-30", "operatingCashflow": "100000000000"},
    ],
}

SAMPLE_QUOTE = {
    "Global Quote": {
        "01. symbol": "MSFT",
        "05. price": "420.50",
        "08. previous close": "418.00",
    }
}


@pytest.fixture
def fetcher():
    """Create an AlphaVantageFetcher with a test API key, no rate limiting."""
    f = AlphaVantageFetcher("MSFT", api_key="test_key")
    f._last_request_time = 0.0
    return f


def _mock_response(json_data, status_code=200):
    """Create a mock requests.Response."""
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.raise_for_status.return_value = None
    resp.status_code = status_code
    return resp


# --- Constructor ---

class TestConstructor:
    def test_missing_api_key_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="API key not found"):
                AlphaVantageFetcher("MSFT")

    def test_explicit_api_key(self):
        f = AlphaVantageFetcher("msft", api_key="my_key")
        assert f.api_key == "my_key"
        assert f.symbol == "MSFT"

    def test_plugin_env_var(self):
        with patch.dict(os.environ, {"CLAUDE_PLUGIN_OPTION_ALPHA_VANTAGE_API_KEY": "plugin_key"}, clear=True):
            f = AlphaVantageFetcher("MSFT")
            assert f.api_key == "plugin_key"

    def test_env_var_fallback(self):
        with patch.dict(os.environ, {"ALPHA_VANTAGE_API_KEY": "env_key"}, clear=True):
            f = AlphaVantageFetcher("MSFT")
            assert f.api_key == "env_key"

    def test_plugin_env_takes_precedence(self):
        with patch.dict(os.environ, {
            "CLAUDE_PLUGIN_OPTION_ALPHA_VANTAGE_API_KEY": "plugin_key",
            "ALPHA_VANTAGE_API_KEY": "env_key",
        }, clear=True):
            f = AlphaVantageFetcher("MSFT")
            assert f.api_key == "plugin_key"

    def test_symbol_uppercased(self):
        f = AlphaVantageFetcher("aapl", api_key="test")
        assert f.symbol == "AAPL"


# --- Rate Limiting ---

class TestRateLimit:
    @patch("stock_analyzer.av_fetcher.time")
    def test_rate_limit_sleeps_when_too_fast(self, mock_time, fetcher):
        mock_time.time.return_value = 100.5
        fetcher._last_request_time = 100.0  # 0.5s ago, need 1.5s
        fetcher._rate_limit()
        mock_time.sleep.assert_called_once_with(pytest.approx(1.0, abs=0.1))

    @patch("stock_analyzer.av_fetcher.time")
    def test_rate_limit_no_sleep_when_enough_time(self, mock_time, fetcher):
        mock_time.time.return_value = 102.0
        fetcher._last_request_time = 100.0  # 2s ago, > 1.5s
        fetcher._rate_limit()
        mock_time.sleep.assert_not_called()


# --- _get() ---

class TestGet:
    @patch("stock_analyzer.av_fetcher._requests")
    def test_successful_get(self, mock_requests, fetcher):
        mock_requests.get.return_value = _mock_response({"Symbol": "MSFT"})
        result = fetcher._get({"function": "OVERVIEW", "symbol": "MSFT"})
        assert result == {"Symbol": "MSFT"}
        # Verify API key was injected
        call_args = mock_requests.get.call_args
        assert call_args[1]["params"]["apikey"] == "test_key"

    @patch("stock_analyzer.av_fetcher._requests")
    def test_throttle_returns_none(self, mock_requests, fetcher):
        mock_requests.get.return_value = _mock_response({
            "Information": "Thank you for using Alpha Vantage! Our standard API rate limit..."
        })
        assert fetcher._get({"function": "OVERVIEW"}) is None

    @patch("stock_analyzer.av_fetcher._requests")
    def test_note_returns_none(self, mock_requests, fetcher):
        mock_requests.get.return_value = _mock_response({
            "Note": "Thank you for using Alpha Vantage!"
        })
        assert fetcher._get({"function": "OVERVIEW"}) is None

    @patch("stock_analyzer.av_fetcher._requests")
    def test_error_message_returns_none(self, mock_requests, fetcher):
        mock_requests.get.return_value = _mock_response({
            "Error Message": "Invalid API call."
        })
        assert fetcher._get({"function": "OVERVIEW"}) is None


# --- fetch_overview ---

class TestFetchOverview:
    @patch("stock_analyzer.av_fetcher._requests")
    def test_success(self, mock_requests, fetcher):
        mock_requests.get.return_value = _mock_response(SAMPLE_OVERVIEW)
        result = fetcher.fetch_overview()
        assert result["Symbol"] == "MSFT"
        assert result["MarketCapitalization"] == "2800000000000"

    @patch("stock_analyzer.av_fetcher._requests")
    def test_missing_symbol_field(self, mock_requests, fetcher):
        mock_requests.get.return_value = _mock_response({"Name": "Test"})
        assert fetcher.fetch_overview() is None

    @patch("stock_analyzer.av_fetcher._requests")
    def test_api_error_returns_none(self, mock_requests, fetcher):
        mock_requests.get.side_effect = Exception("Connection error")
        assert fetcher.fetch_overview() is None


# --- fetch_income_statement ---

class TestFetchIncomeStatement:
    @patch("stock_analyzer.av_fetcher._requests")
    def test_annual_reports(self, mock_requests, fetcher):
        mock_requests.get.return_value = _mock_response(SAMPLE_INCOME)
        result = fetcher.fetch_income_statement(period="annual", limit=3)
        assert result["symbol"] == "MSFT"
        assert len(result["reports"]) == 3
        assert "reports" in result

    @patch("stock_analyzer.av_fetcher._requests")
    def test_quarterly_reports(self, mock_requests, fetcher):
        mock_requests.get.return_value = _mock_response(SAMPLE_INCOME)
        result = fetcher.fetch_income_statement(period="quarterly", limit=2)
        assert len(result["reports"]) == 2
        assert "reports" in result

    @patch("stock_analyzer.av_fetcher._requests")
    def test_empty_reports_returns_none(self, mock_requests, fetcher):
        mock_requests.get.return_value = _mock_response({
            "symbol": "MSFT", "annualReports": []
        })
        assert fetcher.fetch_income_statement() is None

    @patch("stock_analyzer.av_fetcher._requests")
    def test_limit_caps_results(self, mock_requests, fetcher):
        mock_requests.get.return_value = _mock_response(SAMPLE_INCOME)
        result = fetcher.fetch_income_statement(period="annual", limit=2)
        assert len(result["reports"]) == 2

    @patch("stock_analyzer.av_fetcher._requests")
    def test_api_failure_returns_none(self, mock_requests, fetcher):
        mock_requests.get.side_effect = Exception("timeout")
        assert fetcher.fetch_income_statement() is None


# --- fetch_balance_sheet ---

class TestFetchBalanceSheet:
    @patch("stock_analyzer.av_fetcher._requests")
    def test_success(self, mock_requests, fetcher):
        mock_requests.get.return_value = _mock_response(SAMPLE_BALANCE_SHEET)
        result = fetcher.fetch_balance_sheet(limit=2)
        assert result["symbol"] == "MSFT"
        assert len(result["reports"]) == 2

    @patch("stock_analyzer.av_fetcher._requests")
    def test_api_failure_returns_none(self, mock_requests, fetcher):
        mock_requests.get.side_effect = Exception("error")
        assert fetcher.fetch_balance_sheet() is None


# --- fetch_cash_flow ---

class TestFetchCashFlow:
    @patch("stock_analyzer.av_fetcher._requests")
    def test_success(self, mock_requests, fetcher):
        mock_requests.get.return_value = _mock_response(SAMPLE_CASH_FLOW)
        result = fetcher.fetch_cash_flow(limit=1)
        assert result["symbol"] == "MSFT"
        assert len(result["reports"]) == 1

    @patch("stock_analyzer.av_fetcher._requests")
    def test_api_failure_returns_none(self, mock_requests, fetcher):
        mock_requests.get.side_effect = Exception("error")
        assert fetcher.fetch_cash_flow() is None


# --- fetch_quote ---

class TestFetchQuote:
    @patch("stock_analyzer.av_fetcher._requests")
    def test_success(self, mock_requests, fetcher):
        mock_requests.get.return_value = _mock_response(SAMPLE_QUOTE)
        result = fetcher.fetch_quote()
        assert result["Global Quote"]["05. price"] == "420.50"

    @patch("stock_analyzer.av_fetcher._requests")
    def test_missing_global_quote(self, mock_requests, fetcher):
        mock_requests.get.return_value = _mock_response({"data": "none"})
        assert fetcher.fetch_quote() is None

    @patch("stock_analyzer.av_fetcher._requests")
    def test_missing_price(self, mock_requests, fetcher):
        mock_requests.get.return_value = _mock_response({
            "Global Quote": {"01. symbol": "MSFT"}
        })
        assert fetcher.fetch_quote() is None

    @patch("stock_analyzer.av_fetcher._requests")
    def test_api_failure_returns_none(self, mock_requests, fetcher):
        mock_requests.get.side_effect = Exception("error")
        assert fetcher.fetch_quote() is None
