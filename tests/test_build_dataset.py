import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import pytest
from build_dataset import (
    extract_open_price,
    align_observed_temp,
    compute_sigma,
    DEFAULT_SIGMA,
)

def test_extract_open_price_returns_open_field():
    candle_data = {
        "ticker": "KXHIGHNY-26APR17-T72",
        "candle": {"open": 0.04, "high": 0.05, "low": 0.03, "close": 0.045, "volume": 100}
    }
    assert extract_open_price(candle_data) == pytest.approx(0.04)

def test_extract_open_price_real_api_format():
    # Actual Kalshi candlestick API format: price nested under candle["price"]["open_dollars"]
    candle_data = {
        "ticker": "KXHIGHTDC-26MAR14-B57.5",
        "candle": {"price": {"open_dollars": "0.0400", "close_dollars": "0.0500"}}
    }
    assert extract_open_price(candle_data) == pytest.approx(0.04)

def test_extract_open_price_missing_returns_none():
    assert extract_open_price(None) is None
    assert extract_open_price({}) is None

def test_align_observed_temp_returns_correct_day():
    actuals = {
        "daily": {
            "time": ["2026-04-16", "2026-04-17", "2026-04-18"],
            "temperature_2m_max": [68.0, 74.2, 71.0],
            "temperature_2m_min": [52.0, 58.1, 55.0],
        }
    }
    hi, lo = align_observed_temp(actuals, "2026-04-17")
    assert hi == pytest.approx(74.2)
    assert lo == pytest.approx(58.1)

def test_align_observed_temp_missing_date_returns_none():
    actuals = {"daily": {"time": ["2026-04-16"], "temperature_2m_max": [68.0], "temperature_2m_min": [52.0]}}
    assert align_observed_temp(actuals, "2026-04-20") == (None, None)

def test_compute_sigma_uses_mos_when_available():
    assert compute_sigma({"sigma": 3.1}) == pytest.approx(3.1)

def test_compute_sigma_falls_back_to_default():
    assert compute_sigma({"sigma": None}) == DEFAULT_SIGMA
    assert compute_sigma({}) == DEFAULT_SIGMA
