"""Tests for stock_analyzer.stock_manager"""

import json
import pytest
from stock_analyzer.stock_manager import StockManager
from stock_analyzer.dcf import DCFAssumptions


@pytest.fixture
def manager(tmp_path):
    """StockManager using a temp directory"""
    return StockManager(base_dir=str(tmp_path))


@pytest.fixture
def tmp_path_str(tmp_path):
    return str(tmp_path)


class TestFolderCreation:
    def test_creates_folder(self, manager):
        folder = manager.get_stock_folder("MSFT")
        assert folder.exists()
        assert folder.name == "MSFT"

    def test_uppercases_symbol(self, manager):
        folder = manager.get_stock_folder("msft")
        assert folder.name == "MSFT"

    def test_idempotent(self, manager):
        folder1 = manager.get_stock_folder("AAPL")
        folder2 = manager.get_stock_folder("AAPL")
        assert folder1 == folder2


class TestAssumptions:
    def test_save_and_load(self, manager):
        assumptions = DCFAssumptions(revenue_growth_rate=0.15, tax_rate=0.25)
        manager.save_assumptions("TSLA", assumptions)
        loaded = manager.load_assumptions("TSLA")
        assert loaded is not None
        assert loaded.revenue_growth_rate == 0.15
        assert loaded.tax_rate == 0.25

    def test_load_nonexistent_returns_none(self, manager):
        assert manager.load_assumptions("FAKE") is None

    def test_get_or_create_new(self, manager):
        assumptions, was_loaded = manager.get_or_create_assumptions("GOOG")
        assert not was_loaded
        # File should now exist
        assert manager.get_assumptions_file("GOOG").exists()

    def test_get_or_create_existing(self, manager):
        custom = DCFAssumptions(revenue_growth_rate=0.20)
        manager.save_assumptions("META", custom)
        loaded, was_loaded = manager.get_or_create_assumptions("META")
        assert was_loaded
        assert loaded.revenue_growth_rate == 0.20

    def test_get_or_create_with_custom_defaults(self, manager):
        custom = DCFAssumptions(revenue_growth_rate=0.25, cost_of_debt=0.06)
        assumptions, was_loaded = manager.get_or_create_assumptions("AMZN", default_assumptions=custom)
        assert not was_loaded
        assert assumptions.revenue_growth_rate == 0.25
        assert assumptions.cost_of_debt == 0.06

    def test_terminal_growth_defaults_on_load(self, manager):
        """terminal_growth_rate=None in JSON should auto-set to risk_free_rate"""
        assumptions = DCFAssumptions(risk_free_rate=0.04)
        # Manually write JSON with null terminal_growth_rate
        file_path = manager.get_assumptions_file("TEST")
        data = {
            'revenue_growth_rate': 0.10,
            'terminal_growth_rate': None,
            'risk_free_rate': 0.04,
        }
        with open(file_path, 'w') as f:
            json.dump(data, f)
        loaded = manager.load_assumptions("TEST")
        assert loaded.terminal_growth_rate == 0.04

    def test_target_operating_margin_persisted(self, manager):
        assumptions = DCFAssumptions(target_operating_margin=0.35)
        manager.save_assumptions("NVDA", assumptions)
        loaded = manager.load_assumptions("NVDA")
        assert loaded.target_operating_margin == 0.35

    def test_corrupted_json_returns_none(self, manager):
        file_path = manager.get_assumptions_file("BAD")
        with open(file_path, 'w') as f:
            f.write("{invalid json")
        assert manager.load_assumptions("BAD") is None


class TestManualOverrides:
    def test_save_with_manual_overrides(self, manager):
        assumptions = DCFAssumptions(revenue_growth_rate=0.08)
        manager.save_assumptions("MSFT", assumptions, manual_overrides=["revenue_growth_rate"])
        with open(manager.get_assumptions_file("MSFT"), 'r') as f:
            data = json.load(f)
        assert data['_manual_overrides'] == ["revenue_growth_rate"]

    def test_save_preserves_existing_manual_overrides(self, manager):
        assumptions = DCFAssumptions(revenue_growth_rate=0.08)
        manager.save_assumptions("MSFT", assumptions, manual_overrides=["revenue_growth_rate"])
        # Save again without specifying manual_overrides
        assumptions2 = DCFAssumptions(revenue_growth_rate=0.08, tax_rate=0.22)
        manager.save_assumptions("MSFT", assumptions2)
        with open(manager.get_assumptions_file("MSFT"), 'r') as f:
            data = json.load(f)
        assert data['_manual_overrides'] == ["revenue_growth_rate"]

    def test_save_with_empty_manual_overrides_clears_list(self, manager):
        assumptions = DCFAssumptions()
        manager.save_assumptions("MSFT", assumptions, manual_overrides=["beta"])
        # Now save with explicit empty list
        manager.save_assumptions("MSFT", assumptions, manual_overrides=[])
        with open(manager.get_assumptions_file("MSFT"), 'r') as f:
            data = json.load(f)
        assert '_manual_overrides' not in data

    def test_load_manual_overrides(self, manager):
        assumptions = DCFAssumptions()
        manager.save_assumptions("MSFT", assumptions, manual_overrides=["revenue_growth_rate", "beta"])
        overrides = manager.load_manual_overrides("MSFT")
        assert overrides == ["revenue_growth_rate", "beta"]

    def test_load_manual_overrides_missing_field(self, manager):
        """Old assumptions files without _manual_overrides return empty list"""
        assumptions = DCFAssumptions()
        manager.save_assumptions("MSFT", assumptions, manual_overrides=[])
        overrides = manager.load_manual_overrides("MSFT")
        assert overrides == []

    def test_load_manual_overrides_missing_file(self, manager):
        overrides = manager.load_manual_overrides("FAKE")
        assert overrides == []

    def test_load_manual_overrides_corrupted_json(self, manager):
        file_path = manager.get_assumptions_file("BAD")
        with open(file_path, 'w') as f:
            f.write("{invalid json")
        assert manager.load_manual_overrides("BAD") == []

    def test_load_assumptions_ignores_manual_overrides(self, manager):
        """load_assumptions() should work fine with _manual_overrides in the file"""
        assumptions = DCFAssumptions(revenue_growth_rate=0.12)
        manager.save_assumptions("MSFT", assumptions, manual_overrides=["revenue_growth_rate"])
        loaded = manager.load_assumptions("MSFT")
        assert loaded is not None
        assert loaded.revenue_growth_rate == 0.12


class TestSaveAnalysis:
    def test_saves_with_auto_filename(self, manager):
        path = manager.save_analysis("MSFT", "Test analysis content")
        assert path.exists()
        assert path.name.startswith("analysis_")
        assert path.name.endswith(".md")
        assert path.read_text() == "Test analysis content"

    def test_saves_with_custom_filename(self, manager):
        path = manager.save_analysis("MSFT", "Custom output", filename="custom.txt")
        assert path.name == "custom.txt"
        assert path.read_text() == "Custom output"

    def test_saves_in_stock_folder(self, manager):
        path = manager.save_analysis("AAPL", "Content")
        assert "AAPL" in str(path)


class TestFinancialData:
    SAMPLE_DATA = {
        "overview": {"Symbol": "MSFT", "Name": "Microsoft Corporation"},
        "income_statement_annual": {"symbol": "MSFT", "period": "annual", "reports": [{"fiscalDateEnding": "2025-06-30"}]},
        "income_statement_quarterly": {"symbol": "MSFT", "period": "quarterly", "reports": [{"fiscalDateEnding": "2025-12-31"}]},
        "balance_sheet": {"symbol": "MSFT", "period": "annual", "reports": [{"fiscalDateEnding": "2025-06-30"}]},
        "cash_flow": {"symbol": "MSFT", "period": "annual", "reports": [{"fiscalDateEnding": "2025-06-30"}]},
        "quote": {"symbol": "MSFT", "price": "420.50"},
    }

    def test_save_and_load_round_trip(self, manager):
        manager.save_financial_data("MSFT", self.SAMPLE_DATA)
        loaded = manager.load_financial_data("MSFT")
        assert loaded is not None
        assert loaded["symbol"] == "MSFT"
        assert loaded["data"] == self.SAMPLE_DATA
        assert "fetched_at" in loaded
        assert "fetched_at_unix" in loaded

    def test_load_nonexistent_returns_none(self, manager):
        assert manager.load_financial_data("FAKE") is None

    def test_overwrite(self, manager):
        manager.save_financial_data("MSFT", {"overview": {"old": True}})
        manager.save_financial_data("MSFT", self.SAMPLE_DATA)
        loaded = manager.load_financial_data("MSFT")
        assert loaded["data"] == self.SAMPLE_DATA

    def test_uppercase_symbol(self, manager):
        manager.save_financial_data("msft", self.SAMPLE_DATA)
        loaded = manager.load_financial_data("MSFT")
        assert loaded is not None
        assert loaded["symbol"] == "MSFT"

    def test_corrupted_json_returns_none(self, manager):
        file_path = manager.get_financial_data_file("BAD")
        with open(file_path, 'w') as f:
            f.write("{corrupted json!!")
        assert manager.load_financial_data("BAD") is None

    def test_file_path(self, manager):
        path = manager.get_financial_data_file("AAPL")
        assert path.name == "financial_data.json"
        assert "AAPL" in str(path)


class TestDataFreshness:
    """Tests for validate_data_freshness()"""

    def _save(self, manager, symbol, data):
        """Helper to save financial data dict and return validation result."""
        manager.save_financial_data(symbol, data)
        return manager.validate_data_freshness(symbol)

    def test_all_data_current(self, manager):
        """Quarterly latest matches LatestQuarter → no warnings."""
        data = {
            "overview": {"Symbol": "MSFT", "LatestQuarter": "2025-12-31"},
            "income_statement_annual": {"reports": [{"fiscalDateEnding": "2025-06-30"}]},
            "income_statement_quarterly": {"reports": [
                {"fiscalDateEnding": "2025-12-31"},
                {"fiscalDateEnding": "2025-09-30"},
            ]},
            "balance_sheet": {"reports": [{"fiscalDateEnding": "2025-06-30"}]},
            "cash_flow": {"reports": [{"fiscalDateEnding": "2025-06-30"}]},
        }
        result = self._save(manager, "MSFT", data)
        assert result["quarterly_data_current"] is True
        assert result["latest_quarter_expected"] == "2025-12-31"
        assert result["latest_quarter_actual"] == "2025-12-31"
        assert result["warnings"] == []
        assert result["missing_sources"] == []

    def test_quarterly_behind(self, manager):
        """Quarterly latest < LatestQuarter → warning generated."""
        data = {
            "overview": {"Symbol": "TTD", "LatestQuarter": "2025-12-31"},
            "income_statement_annual": {"reports": [{"fiscalDateEnding": "2024-12-31"}]},
            "income_statement_quarterly": {"reports": [
                {"fiscalDateEnding": "2025-09-30"},
                {"fiscalDateEnding": "2025-06-30"},
            ]},
            "balance_sheet": {"reports": [{"fiscalDateEnding": "2024-12-31"}]},
            "cash_flow": {"reports": [{"fiscalDateEnding": "2024-12-31"}]},
        }
        result = self._save(manager, "TTD", data)
        assert result["quarterly_data_current"] is False
        assert result["latest_quarter_actual"] == "2025-09-30"
        assert len(result["warnings"]) == 1
        assert "2025-09-30" in result["warnings"][0]
        assert "2025-12-31" in result["warnings"][0]

    def test_missing_quarterly(self, manager):
        """No quarterly data at all → listed in missing_sources."""
        data = {
            "overview": {"Symbol": "XYZ", "LatestQuarter": "2025-12-31"},
            "income_statement_annual": {"reports": [{"fiscalDateEnding": "2024-12-31"}]},
            "balance_sheet": {"reports": [{"fiscalDateEnding": "2024-12-31"}]},
            "cash_flow": {"reports": [{"fiscalDateEnding": "2024-12-31"}]},
        }
        result = self._save(manager, "XYZ", data)
        assert "income_statement_quarterly" in result["missing_sources"]
        assert result["quarterly_data_current"] is False
        assert result["latest_quarter_actual"] is None
        assert any("No quarterly income data" in w for w in result["warnings"])

    def test_no_overview(self, manager):
        """No overview data → LatestQuarter is None, no comparison warning."""
        data = {
            "income_statement_annual": {"reports": [{"fiscalDateEnding": "2024-12-31"}]},
            "income_statement_quarterly": {"reports": [{"fiscalDateEnding": "2025-09-30"}]},
            "balance_sheet": {"reports": [{"fiscalDateEnding": "2024-12-31"}]},
            "cash_flow": {"reports": [{"fiscalDateEnding": "2024-12-31"}]},
        }
        result = self._save(manager, "NOOV", data)
        assert result["latest_quarter_expected"] is None
        assert result["quarterly_data_current"] is True  # no expected = no mismatch
        assert result["warnings"] == []

    def test_no_cached_data(self, manager):
        """No cached data → returns None gracefully."""
        result = manager.validate_data_freshness("NONEXISTENT")
        assert result is None

    def test_latest_dates_populated(self, manager):
        """All latest_dates are correctly extracted."""
        data = {
            "overview": {"Symbol": "TEST"},
            "income_statement_annual": {"reports": [
                {"fiscalDateEnding": "2024-12-31"},
                {"fiscalDateEnding": "2023-12-31"},
            ]},
            "income_statement_quarterly": {"reports": [
                {"fiscalDateEnding": "2025-06-30"},
                {"fiscalDateEnding": "2025-03-31"},
            ]},
            "balance_sheet": {"reports": [{"fiscalDateEnding": "2024-12-31"}]},
            "cash_flow": {"reports": [{"fiscalDateEnding": "2024-12-31"}]},
        }
        result = self._save(manager, "TEST", data)
        assert result["latest_dates"]["income_statement_annual"] == "2024-12-31"
        assert result["latest_dates"]["income_statement_quarterly"] == "2025-06-30"
        assert result["latest_dates"]["balance_sheet"] == "2024-12-31"
        assert result["latest_dates"]["cash_flow"] == "2024-12-31"

    def test_stale_balance_sheet_warns(self, manager):
        """Balance sheet older than annual income → warning."""
        data = {
            "overview": {"Symbol": "STALE"},
            "income_statement_annual": {"reports": [{"fiscalDateEnding": "2024-12-31"}]},
            "income_statement_quarterly": {"reports": [{"fiscalDateEnding": "2024-12-31"}]},
            "balance_sheet": {"reports": [{"fiscalDateEnding": "2023-12-31"}]},
            "cash_flow": {"reports": [{"fiscalDateEnding": "2024-12-31"}]},
        }
        result = self._save(manager, "STALE", data)
        assert any("balance_sheet" in w for w in result["warnings"])

    def test_empty_reports_list(self, manager):
        """Empty reports list → source has None date."""
        data = {
            "overview": {"Symbol": "EMPTY"},
            "income_statement_annual": {"reports": []},
            "income_statement_quarterly": {"reports": []},
            "balance_sheet": {"reports": [{"fiscalDateEnding": "2024-12-31"}]},
            "cash_flow": {"reports": [{"fiscalDateEnding": "2024-12-31"}]},
        }
        result = self._save(manager, "EMPTY", data)
        assert result["latest_dates"]["income_statement_annual"] is None
        assert result["latest_dates"]["income_statement_quarterly"] is None


class TestAssumptionsSummary:
    def test_summary_for_existing(self, manager):
        manager.save_assumptions("MSFT", DCFAssumptions(revenue_growth_rate=0.12))
        summary = manager.get_assumptions_summary("MSFT")
        assert "12.0%" in summary
        assert "MSFT" in summary

    def test_summary_for_nonexistent(self, manager):
        summary = manager.get_assumptions_summary("FAKE")
        assert "No assumptions file found" in summary


from datetime import date, timedelta


class TestMarketDataStaleness:
    """Tests for StockManager.is_market_data_stale()"""

    def test_none_data_is_stale(self, manager):
        assert manager.is_market_data_stale(None) is True

    def test_missing_fetched_at_is_stale(self, manager):
        data = {"risk_free_rate": 0.04}
        assert manager.is_market_data_stale(data) is True

    def test_empty_fetched_at_is_stale(self, manager):
        data = {"fetched_at": "", "risk_free_rate": 0.04}
        assert manager.is_market_data_stale(data) is True

    def test_malformed_fetched_at_is_stale(self, manager):
        data = {"fetched_at": "not-a-date", "risk_free_rate": 0.04}
        assert manager.is_market_data_stale(data) is True

    def test_today_is_not_stale(self, manager):
        data = {"fetched_at": date.today().isoformat()}
        assert manager.is_market_data_stale(data) is False

    def test_29_days_ago_is_not_stale(self, manager):
        old = (date.today() - timedelta(days=29)).isoformat()
        data = {"fetched_at": old}
        assert manager.is_market_data_stale(data) is False

    def test_30_days_ago_is_not_stale(self, manager):
        # Boundary: exactly 30 days is still fresh (> threshold is stale)
        old = (date.today() - timedelta(days=30)).isoformat()
        data = {"fetched_at": old}
        assert manager.is_market_data_stale(data) is False

    def test_31_days_ago_is_stale(self, manager):
        old = (date.today() - timedelta(days=31)).isoformat()
        data = {"fetched_at": old}
        assert manager.is_market_data_stale(data) is True

    def test_custom_threshold(self, manager):
        old = (date.today() - timedelta(days=8)).isoformat()
        data = {"fetched_at": old}
        assert manager.is_market_data_stale(data, threshold_days=7) is True
        assert manager.is_market_data_stale(data, threshold_days=10) is False
