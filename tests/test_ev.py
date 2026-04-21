import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from ev import taker_fee, bucket_probability, trade_ev, is_tail

def test_taker_fee_at_midpoint():
    # 0.07 × 0.50 × 0.50 = 0.0175
    assert abs(taker_fee(0.50) - 0.0175) < 1e-6

def test_taker_fee_at_tail_5pct():
    # 0.07 × 0.05 × 0.95 = 0.003325
    assert abs(taker_fee(0.05) - 0.003325) < 1e-6

def test_taker_fee_at_tail_1pct():
    # 0.07 × 0.01 × 0.99 = 0.000693
    assert abs(taker_fee(0.01) - 0.000693) < 1e-6

def test_taker_fee_symmetric():
    # fee(C) == fee(1-C)
    assert abs(taker_fee(0.10) - taker_fee(0.90)) < 1e-9

def test_bucket_probability_centered():
    # Gaussian centered at 72.5 with sigma=2.5
    # P(72 < x < 73) should be near the PDF peak value × 1°F width ≈ 15-17%
    p = bucket_probability(forecast=72.5, sigma=2.5, bucket_low=72.0, bucket_high=73.0)
    assert 0.14 < p < 0.18

def test_bucket_probability_tail():
    # bucket 5 sigma away from mean — near zero
    p = bucket_probability(forecast=72.5, sigma=2.5, bucket_low=85.0, bucket_high=86.0)
    assert p < 0.001

def test_bucket_probability_sums_to_one():
    # integrating over all 1-degree buckets from 20 to 130 should be ~1.0
    total = sum(
        bucket_probability(72.5, 2.5, float(t), float(t + 1))
        for t in range(20, 130)
    )
    assert abs(total - 1.0) < 0.001

def test_ev_positive_when_forecast_above_breakeven():
    # market at 5%, forecast says 10% — should be positive EV
    ev = trade_ev(p_forecast=0.10, price=0.05)
    assert ev > 0

def test_ev_negative_when_fairly_priced():
    # market at 5%, forecast also says 5% — EV is negative (fees)
    ev = trade_ev(p_forecast=0.05, price=0.05)
    assert ev < 0

def test_is_tail_5pct():
    assert is_tail(0.05) is True
    assert is_tail(0.04) is True
    assert is_tail(0.95) is True
    assert is_tail(0.96) is True
    assert is_tail(0.06) is False
    assert is_tail(0.94) is False
