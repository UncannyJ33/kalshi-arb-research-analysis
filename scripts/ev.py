"""Core math for Kalshi weather market EV analysis. Pure functions only — no I/O."""
from scipy.stats import norm


def taker_fee(price: float) -> float:
    """
    Kalshi taker fee per contract.

    Source: Kalshi Fee Schedule Feb 2026, https://kalshi.com/docs/kalshi-fee-schedule.pdf
    Formula: $0.07 × C × (1 − C) where C is the contract price.
    Charged at execution regardless of outcome. Applies to both buyers and sellers.
    """
    return 0.07 * price * (1.0 - price)


def bucket_probability(forecast: float, sigma: float, bucket_low: float, bucket_high: float) -> float:
    """
    P(daily temperature falls in [bucket_low, bucket_high]) given a Gaussian
    forecast distribution N(forecast, sigma).

    sigma comes from the MOS spread field when available; falls back to 2.5°F
    (published NWS 24h max temp MAE for major US cities).
    """
    if sigma <= 0:
        raise ValueError(f"sigma must be positive, got {sigma}")
    if bucket_low >= bucket_high:
        raise ValueError(f"bucket_low must be < bucket_high, got {bucket_low} >= {bucket_high}")
    return norm.cdf((bucket_high - forecast) / sigma) - norm.cdf((bucket_low - forecast) / sigma)


def trade_ev(p_forecast: float, price: float) -> float:
    """
    Expected value of buying one YES contract at `price`, given forecast
    probability `p_forecast` that the bucket resolves YES.

    EV = p_forecast × $1.00 − (price + taker_fee(price))
    """
    cost = price + taker_fee(price)
    return p_forecast * 1.00 - cost


def is_tail(price: float, threshold: float = 0.05) -> bool:
    """True if a market price falls in the tail (≤ threshold or ≥ 1-threshold)."""
    return price <= threshold or price >= (1.0 - threshold)
