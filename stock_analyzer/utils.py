"""
Shared utility functions for the stock_analyzer package
"""


def safe_float(value, default=None):
    """
    Safely convert a value to float.

    Handles None, 'None', '-', empty strings, and other non-numeric values
    that commonly appear in financial API responses.

    Args:
        value: Value to convert
        default: Default value if conversion fails

    Returns:
        Float value or default
    """
    if value in (None, 'None', '-', ''):
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default
