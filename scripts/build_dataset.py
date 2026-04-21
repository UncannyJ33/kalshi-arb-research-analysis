"""
Merge Kalshi markets + candlesticks + IEM MOS forecasts + Open-Meteo actuals
into a single analysis-ready parquet file.

Output: data/processed/dataset.parquet

Each row = one (series_ticker, market_ticker, weather_date, bucket) observation.

Key columns:
  series_ticker, market_ticker, city_id, market_type, weather_date
  floor_strike, cap_strike       — bucket bounds in °F
  market_open_price              — YES contract price at 10 AM ET open on D-1
  result                         — "yes" or "no" (from Kalshi settlement)
  expiration_value               — actual temperature from NWS CLI
  observed_high, observed_low    — from Open-Meteo
  mos_forecast_high, mos_forecast_low — from IEM GFS-MOS
  sigma                          — forecast uncertainty (MOS spread or 2.5°F fallback)
  sigma_source                   — "mos" or "fallback"
  p_forecast                     — bucket_probability(mos_forecast, sigma, floor, cap)

Run: python scripts/build_dataset.py
"""
import sys
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from cities import CITIES
from ev import bucket_probability

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
KALSHI_DIR = DATA_DIR / "kalshi"
CANDLES_DIR = DATA_DIR / "kalshi_candles"
FORECASTS_DIR = DATA_DIR / "forecasts"
ACTUALS_DIR = DATA_DIR / "actuals"
PROCESSED_DIR = DATA_DIR / "processed"

DEFAULT_SIGMA = 2.5  # °F — NWS published 24h max temp MAE for major US cities

# EST offset from UTC used to convert Kalshi close_time (UTC) → ET weather date.
# Kalshi markets close at 11:59 PM ET; close_time is stored as UTC.
# EST = UTC-5 (covers Nov–Mar); EDT = UTC-4 (covers Mar–Nov).
# Using a fixed 5-hour offset slightly over-corrects in summer (EDT) but the
# resulting date is always the correct weather day because 4:59 AM UTC - 5h = 11:59 PM
# the prior day regardless of DST (close_time is 4:59 AM UTC in EST season and
# 3:59 AM UTC in EDT season — both safely resolve to 11:59 PM ET).
_UTC_TO_ET_HOURS = 5


def extract_open_price(candle_data: dict | None) -> float | None:
    """Extract the open price from a cached candlestick dict.

    The Kalshi candlestick API returns the open price nested under
    candle["price"]["open_dollars"] (a decimal string, e.g. "0.0400").
    A flat candle["open"] float is also accepted for test fixtures.
    """
    if not candle_data:
        return None
    candle = candle_data.get("candle", {})
    if not candle:
        return None
    # Actual cached format: candle["price"]["open_dollars"]
    price = candle.get("price")
    if price and "open_dollars" in price:
        return float(price["open_dollars"])
    # Test-fixture / legacy flat format: candle["open"]
    return candle.get("open")


def align_observed_temp(actuals: dict, weather_date: str) -> tuple[float | None, float | None]:
    """Return (observed_high, observed_low) for weather_date from Open-Meteo actuals dict."""
    daily = actuals.get("daily", {})
    times = daily.get("time", [])
    if weather_date not in times:
        return None, None
    idx = times.index(weather_date)
    hi = daily["temperature_2m_max"][idx]
    lo = daily["temperature_2m_min"][idx]
    return hi, lo


def compute_sigma(forecast: dict) -> float:
    """Return sigma from forecast dict, falling back to DEFAULT_SIGMA."""
    s = forecast.get("sigma")
    return float(s) if s is not None else DEFAULT_SIGMA


def extract_daily_forecast_cached(forecast_data: dict, weather_date: str) -> dict | None:
    """
    Extract high/low temp for weather_date from a cached IEM GFS-MOS file.

    The cached format uses pandas orient='table': {"schema": ..., "data": [...], "_meta": ...}
    Each data entry has "ftime_utc" (ISO string) and "tmp" (°F integer).
    Returns {"t_high": float, "t_low": float, "sigma": None} or None.
    """
    entries = forecast_data.get("data", [])
    day_temps = []
    for entry in entries:
        ftime = entry.get("ftime_utc", "")
        if ftime.startswith(weather_date):
            t = entry.get("tmp")
            if t is not None:
                day_temps.append(float(t))
    if not day_temps:
        return None
    return {"t_high": max(day_temps), "t_low": min(day_temps), "sigma": None}


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def build_rows() -> list[dict]:
    rows = []
    sigma_sources = {"mos": 0, "fallback": 0}

    for city_id, city_cfg in CITIES.items():
        actuals = load_json(ACTUALS_DIR / f"{city_id}.json")
        if actuals is None:
            logger.warning(f"{city_id}: no actuals data, skipping")
            continue

        for series_cfg in city_cfg["series"]:
            series_ticker = series_cfg["ticker"]
            market_type = series_cfg["market_type"]
            markets = load_json(KALSHI_DIR / f"{series_ticker}.json")
            if not markets:
                logger.warning(f"{series_ticker}: no market data")
                continue

            for market in markets:
                ticker = market.get("ticker", "")
                close_time = market.get("close_time", "")
                if not close_time:
                    continue

                # Derive weather_date from close_time (11:59 PM ET on weather day).
                # close_time is stored in UTC; subtract ET offset to recover local date.
                utc_dt = datetime.fromisoformat(close_time.replace("Z", "+00:00"))
                weather_date = (utc_dt - timedelta(hours=_UTC_TO_ET_HOURS)).strftime("%Y-%m-%d")

                # Load candlestick (market open price at 10 AM ET on D-1)
                candle_data = load_json(CANDLES_DIR / f"{ticker}.json")
                open_price = extract_open_price(candle_data)
                if open_price is None:
                    continue

                # Load MOS forecast
                forecast_data = load_json(FORECASTS_DIR / f"{city_id}_{weather_date}.json")
                if forecast_data is None:
                    continue
                daily_fc = extract_daily_forecast_cached(forecast_data, weather_date)
                if daily_fc is None:
                    continue

                # Observed actuals
                obs_hi, obs_lo = align_observed_temp(actuals, weather_date)
                if obs_hi is None:
                    continue

                # Sigma
                sigma = compute_sigma(daily_fc)
                sigma_source = "mos" if daily_fc.get("sigma") is not None else "fallback"

                # Forecast temperature for this market type
                forecast_temp = daily_fc["t_high"] if market_type == "high" else daily_fc["t_low"]

                # Bucket bounds from Kalshi market object
                floor_strike = market.get("floor_strike")
                cap_strike = market.get("cap_strike")
                if floor_strike is None or cap_strike is None:
                    continue

                # Count sigma source only for rows that pass all filters
                sigma_sources[sigma_source] += 1

                p_fc = bucket_probability(
                    forecast=forecast_temp,
                    sigma=sigma,
                    bucket_low=float(floor_strike),
                    bucket_high=float(cap_strike),
                )

                rows.append({
                    "series_ticker": series_ticker,
                    "market_ticker": ticker,
                    "city_id": city_id,
                    "city_name": city_cfg["name"],
                    "market_type": market_type,
                    "weather_date": weather_date,
                    "floor_strike": float(floor_strike),
                    "cap_strike": float(cap_strike),
                    "market_open_price": float(open_price),
                    "result": market.get("result"),
                    "expiration_value": market.get("expiration_value"),
                    "observed_high": obs_hi,
                    "observed_low": obs_lo,
                    "mos_forecast_high": daily_fc["t_high"],
                    "mos_forecast_low": daily_fc["t_low"],
                    "sigma": sigma,
                    "sigma_source": sigma_source,
                    "p_forecast": p_fc,
                })

    total = len(rows)
    fallback_pct = 100 * sigma_sources["fallback"] / max(total, 1)
    logger.info(f"Built {total} rows. Sigma fallback rate: {fallback_pct:.1f}%")
    if fallback_pct > 30:
        logger.info(
            f"Sigma fallback rate is {fallback_pct:.1f}% — GFS-MOS data does not include "
            "a spread field, so all rows use DEFAULT_SIGMA=2.5°F. "
            "Document as methodology caveat in findings.md."
        )
    return rows


def main():
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    rows = build_rows()
    if not rows:
        logger.error("No rows built. Check that all pull scripts ran successfully.")
        return

    df = pd.DataFrame(rows)
    out_path = PROCESSED_DIR / "dataset.parquet"
    df.to_parquet(out_path, index=False)
    logger.info(f"Wrote {len(df)} rows → {out_path}")
    logger.info(f"Columns: {list(df.columns)}")
    logger.info(f"Date range: {df['weather_date'].min()} → {df['weather_date'].max()}")
    logger.info(f"Cities: {sorted(df['city_id'].unique())}")


if __name__ == "__main__":
    main()
