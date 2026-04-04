"""Tests for stock_analyzer.utils"""

import pytest
from stock_analyzer.utils import safe_float


class TestSafeFloat:
    def test_valid_string(self):
        assert safe_float("123.45") == 123.45

    def test_valid_int_string(self):
        assert safe_float("100") == 100.0

    def test_valid_float(self):
        assert safe_float(42.5) == 42.5

    def test_valid_int(self):
        assert safe_float(10) == 10.0

    def test_none_returns_default(self):
        assert safe_float(None) is None
        assert safe_float(None, 0) == 0

    def test_none_string_returns_default(self):
        assert safe_float("None") is None
        assert safe_float("None", 1.0) == 1.0

    def test_dash_returns_default(self):
        assert safe_float("-") is None
        assert safe_float("-", 0) == 0

    def test_empty_string_returns_default(self):
        assert safe_float("") is None
        assert safe_float("", 5.0) == 5.0

    def test_non_numeric_string(self):
        assert safe_float("abc") is None
        assert safe_float("abc", -1) == -1

    def test_negative_number(self):
        assert safe_float("-42.5") == -42.5

    def test_zero(self):
        assert safe_float("0") == 0.0
        assert safe_float(0) == 0.0

    def test_scientific_notation(self):
        assert safe_float("1.5e10") == 1.5e10
